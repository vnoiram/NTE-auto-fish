"""Suggest HSV ranges from a screenshot of the bite prompt or the fishing gauge.

Pure image helpers with no GUI or capture dependency, so they can be tested
with synthetic images.
"""

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


def dominant_range(
    hsv: np.ndarray,
    *,
    min_sat: int = 80,
    min_val: int = 100,
    min_pixels: int = 20,
    hue_band: tuple[int, int] | None = None,
    exclude_hue: tuple[int, int] | None = None,
) -> Suggestion | None:
    """Return the HSV range of the most frequent saturated hue, or None."""
    h = hsv[..., 0]
    mask = (hsv[..., 1] >= min_sat) & (hsv[..., 2] >= min_val)
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


def suggest_gauge(bgr: np.ndarray) -> tuple[Suggestion | None, Suggestion | None]:
    """Fishing gauge: (safe_zone, cursor).

    The safe zone is the most frequent saturated colour in the gauge. The
    cursor is the brightest remaining colour, excluding the safe-zone hue.
    """
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    safe = dominant_range(hsv, min_val=120)
    exclude = None
    if safe is not None:
        exclude = (safe.peak_hue - 2 * _PEAK_RADIUS, safe.peak_hue + 2 * _PEAK_RADIUS)
    cursor = dominant_range(
        hsv, min_sat=60, min_val=200, min_pixels=10, exclude_hue=exclude
    )
    return safe, cursor
