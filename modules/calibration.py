"""Suggest HSV ranges from a screenshot of the bite prompt or the fishing gauge.

Pure image helpers with no GUI or capture dependency, so they can be tested
with synthetic images.
"""

import threading
from dataclasses import dataclass

import cv2
import numpy as np

_HUE_SPAN = 180
_PEAK_RADIUS = 8  # hue distance from the peak that still belongs to the cluster
_HUE_SMOOTH = 5
_MARGIN = (3, 20, 20)  # safety margin added around the measured H/S/V range
_BLUE_HUE = (85, 140)  # bite prompt is blue; prefer this band when present


@dataclass(frozen=True)
class Suggestion:
    lower: tuple[int, int, int]
    upper: tuple[int, int, int]
    pixels: int
    peak_hue: int


def _clamp(value: float, hi: int) -> int:
    return int(max(0, min(hi, round(value))))


_BG_BINS = (45, 8, 8)  # H/4, S/32, V/32
_BG_MIN_FRACTION = 0.002  # a bin holding this share of the area counts as background
_BG_EMA_ALPHA = 0.3


def _bin_index(hsv: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return (
        np.minimum(hsv[..., 0] // 4, _BG_BINS[0] - 1),
        hsv[..., 1] // 32,
        hsv[..., 2] // 32,
    )


class BackgroundSampler:
    """Learns which colours the scene shows around the gauge while it is hidden.

    Keeps a smoothed per-bin share of the sampled area, so the model follows
    gradual lighting changes such as a sunset.
    """

    def __init__(self) -> None:
        self._fraction: np.ndarray | None = None
        self.samples = 0

    def add(self, bgr: np.ndarray) -> None:
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        hist, _ = np.histogramdd(
            np.stack([a.ravel() for a in _bin_index(hsv)], axis=1),
            bins=[np.arange(n + 1) for n in _BG_BINS],
        )
        frac = hist / max(hsv.shape[0] * hsv.shape[1], 1)
        if self._fraction is None:
            self._fraction = frac
        else:
            self._fraction = (
                _BG_EMA_ALPHA * frac + (1.0 - _BG_EMA_ALPHA) * self._fraction
            )
        self.samples += 1

    def signature(self) -> list[float] | None:
        """Hue and brightness distribution of the background (53 values)."""
        if self._fraction is None:
            return None
        hue = self._fraction.sum(axis=(1, 2))
        val = self._fraction.sum(axis=(0, 1))
        total = float(hue.sum()) or 1.0
        return [float(x) / total for x in np.concatenate([hue, val])]

    def mask(self, hsv: np.ndarray) -> np.ndarray | None:
        """Boolean mask of pixels whose colour is common in the background."""
        if self._fraction is None:
            return None
        h, s, v = _bin_index(hsv)
        return self._fraction[h, s, v] >= _BG_MIN_FRACTION


def dominant_range(
    hsv: np.ndarray,
    *,
    ignore_mask: np.ndarray | None = None,
    min_sat: int = 80,
    min_val: int = 100,
    min_pixels: int = 20,
    hue_band: tuple[int, int] | None = None,
    exclude_hue: tuple[int, int] | None = None,
) -> Suggestion | None:
    """Return the HSV range of the most frequent saturated hue, or None."""
    h = hsv[..., 0]
    mask = (hsv[..., 1] >= min_sat) & (hsv[..., 2] >= min_val)
    if ignore_mask is not None:
        mask &= ~ignore_mask
    if hue_band is not None:
        mask &= (h >= hue_band[0]) & (h <= hue_band[1])
    if exclude_hue is not None:
        mask &= (h < exclude_hue[0]) | (h > exclude_hue[1])
    if int(mask.sum()) < min_pixels:
        return None

    hist = np.bincount(h[mask].ravel(), minlength=_HUE_SPAN).astype(np.float64)
    kernel = np.ones(_HUE_SMOOTH) / _HUE_SMOOTH
    padded = np.concatenate([hist[-_HUE_SMOOTH:], hist, hist[:_HUE_SMOOTH]])
    smooth = np.convolve(padded, kernel, mode="same")[_HUE_SMOOTH:-_HUE_SMOOTH]
    peak = int(np.argmax(smooth))

    members = mask & (np.abs(h.astype(np.int16) - peak) <= _PEAK_RADIUS)
    count = int(members.sum())
    if count < min_pixels:
        return None

    lows, highs = [], []
    for ch, top in zip(range(3), (179, 255, 255)):
        vals = hsv[..., ch][members]
        lows.append(_clamp(np.percentile(vals, 2) - _MARGIN[ch], top))
        highs.append(_clamp(np.percentile(vals, 98) + _MARGIN[ch], top))
    return Suggestion(tuple(lows), tuple(highs), count, peak)


def suggest_bite(bgr: np.ndarray) -> Suggestion | None:
    """Bite prompt: most frequent blue-ish colour, else most frequent colour."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return dominant_range(hsv, hue_band=_BLUE_HUE) or dominant_range(hsv)


# (min_sat, min_val) pairs tried in order, strict to loose.
_SAFE_LEVELS = ((170, 180), (80, 120), (50, 80), (30, 50))
_CURSOR_LEVELS = ((40, 235), (40, 200), (30, 150))


_HINT_HUE_PAD = 20
_ICON_MARGIN = 0.12  # the gauge ROI can include round icons at both ends


def _hint_band(hint) -> tuple[int, int] | None:
    """Hue band around a known HSV range (lower, upper), or None without a hint."""
    if hint is None:
        return None
    lower, upper = hint
    return (max(0, lower[0] - _HINT_HUE_PAD), min(179, upper[0] + _HINT_HUE_PAD))


def suggest_gauge(
    bgr: np.ndarray,
    safe_hint=None,
    cursor_hint=None,
    background: BackgroundSampler | None = None,
) -> tuple[Suggestion | None, Suggestion | None]:
    """Fishing gauge: (safe_zone, cursor).

    The safe zone is the most frequent saturated colour in the gauge. The
    cursor is the brightest remaining colour, excluding the safe-zone hue.
    Hints are the current (lower, upper) ranges: when given, each element is
    searched only near its known hue so unrelated UI colours are not adopted.
    Colours the background sampler has seen are ignored. Thresholds are
    relaxed step by step when nothing is found.
    """
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    ignore = background.mask(hsv) if background is not None else None
    cols = slice(
        int(hsv.shape[1] * _ICON_MARGIN), int(hsv.shape[1] * (1 - _ICON_MARGIN))
    )
    hsv = hsv[:, cols]
    if ignore is not None:
        ignore = ignore[:, cols]
    safe_band = _hint_band(safe_hint)
    cursor_band = _hint_band(cursor_hint)
    safe = None
    for sat, val in _SAFE_LEVELS:
        safe = dominant_range(
            hsv, min_sat=sat, min_val=val, hue_band=safe_band, ignore_mask=ignore
        )
        if safe is not None:
            break
    exclude = None
    if safe is not None and cursor_band is None:
        exclude = (safe.peak_hue - 2 * _PEAK_RADIUS, safe.peak_hue + 2 * _PEAK_RADIUS)
    cursor = None
    for sat, val in _CURSOR_LEVELS:
        cursor = dominant_range(
            hsv,
            min_sat=sat,
            min_val=val,
            min_pixels=10,
            hue_band=cursor_band,
            exclude_hue=exclude,
            ignore_mask=ignore,
        )
        if cursor is not None:
            break
    return safe, cursor


_START_SAFE_BAND = (0.25, 0.75)  # fish bar region (fraction of width) at fight start
_START_CURSOR_BAND = (0.44, 0.56)  # cursor line is at the centre at fight start


def suggest_gauge_at_start(
    bgr: np.ndarray,
    safe_hint=None,
    cursor_hint=None,
    background: BackgroundSampler | None = None,
) -> tuple[Suggestion | None, Suggestion | None]:
    """Gauge colours for the first frames of a fight.

    At the start the cursor is a thin line in the middle of the gauge and the
    safe zone is a horizontal bar around it, so the safe zone is searched in
    the central half and the cursor only in a narrow strip at the centre.
    """
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    width = hsv.shape[1]

    def crop(frac: tuple[float, float]) -> slice:
        return slice(int(width * frac[0]), max(int(width * frac[1]), 1))

    safe_cols = crop(_START_SAFE_BAND)
    cursor_cols = crop(_START_CURSOR_BAND)
    ignore = background.mask(hsv) if background is not None else None

    def sub(mask, cols):
        return None if mask is None else mask[:, cols]

    safe = None
    for sat, val in _SAFE_LEVELS:
        safe = dominant_range(
            hsv[:, safe_cols],
            min_sat=sat,
            min_val=val,
            hue_band=_hint_band(safe_hint),
            ignore_mask=sub(ignore, safe_cols),
        )
        if safe is not None:
            break

    cursor_band = _hint_band(cursor_hint)
    exclude = None
    if safe is not None and cursor_band is None:
        exclude = (safe.peak_hue - 2 * _PEAK_RADIUS, safe.peak_hue + 2 * _PEAK_RADIUS)
    cursor = None
    for sat, val in _CURSOR_LEVELS:
        cursor = dominant_range(
            hsv[:, cursor_cols],
            min_sat=sat,
            min_val=val,
            min_pixels=10,
            hue_band=cursor_band,
            exclude_hue=exclude,
            ignore_mask=sub(ignore, cursor_cols),
        )
        if cursor is not None:
            break
    return safe, cursor


class GaugeAssist:
    """Collects fight-start gauge measurements and compares them with the live detection.

    Assist only: it never changes settings by itself. ``summary`` returns the
    median suggestion so the user can apply it once enough samples agree.
    """

    def __init__(self, max_samples: int = 30) -> None:
        self._max = max_samples
        self._lock = threading.Lock()
        self._safe: list[Suggestion] = []
        self._cursor: list[Suggestion] = []
        self._hits: list[bool] = []
        self.misses = 0

    def add(self, safe, cursor, current_detection_ok: bool) -> None:
        with self._lock:
            if safe is not None:
                self._safe = (self._safe + [safe])[-self._max :]
            if cursor is not None:
                self._cursor = (self._cursor + [cursor])[-self._max :]
            self._hits = (self._hits + [current_detection_ok])[-self._max :]

    def add_miss(self) -> None:
        with self._lock:
            self.misses += 1

    def reset(self) -> None:
        with self._lock:
            self._safe, self._cursor, self._hits, self.misses = [], [], [], 0

    @property
    def samples(self) -> int:
        with self._lock:
            return len(self._hits)

    @property
    def hit_rate(self) -> float | None:
        """Share of fight starts where the current settings found both bars."""
        with self._lock:
            return sum(self._hits) / len(self._hits) if self._hits else None

    @staticmethod
    def _median(items: list[Suggestion]) -> Suggestion | None:
        if not items:
            return None
        lower = tuple(int(np.median([i.lower[k] for i in items])) for k in range(3))
        upper = tuple(int(np.median([i.upper[k] for i in items])) for k in range(3))
        return Suggestion(
            lower,
            upper,
            int(np.median([i.pixels for i in items])),
            int(np.median([i.peak_hue for i in items])),
        )

    def summary(self) -> tuple[Suggestion | None, Suggestion | None]:
        with self._lock:
            return self._median(self._safe), self._median(self._cursor)


def describe(bgr: np.ndarray) -> str:
    """Short diagnostic: mean brightness, colourful pixel share and top hues."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    colourful = (hsv[..., 1] >= 30) & (hsv[..., 2] >= 50)
    share = float(colourful.mean()) * 100
    text = f"{bgr.shape[1]}x{bgr.shape[0]}px, V mean {float(hsv[..., 2].mean()):.0f}, colorful {share:.2f}%"
    if colourful.any():
        hist = np.bincount(hsv[..., 0][colourful].ravel(), minlength=_HUE_SPAN)
        top = np.argsort(hist)[::-1][:3]
        text += ", top H " + "/".join(
            f"{int(h)}({int(hist[h])})" for h in top if hist[h]
        )
    return text
