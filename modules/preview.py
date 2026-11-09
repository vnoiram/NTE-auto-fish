"""Render small live previews of what the bot sees, for the dashboard tracker.

Pure image helpers (no GUI dependency). The outputs are RGBA uint8 arrays with
fixed sizes so the GUI can keep one dynamic texture per preview.
"""

import cv2
import numpy as np

# Small on purpose: previews are for aligning areas, and big textures made the GUI heavy.
BAR_SIZE = (384, 36)  # (width, height)
BUTTON_SIZE = (132, 108)
ICON_SIZE = (192, 58)
OCR_SIZE = (192, 72)  # raw crop on top, binarised image below

_SAFE_TINT = (60, 255, 120)  # RGB
_CURSOR_COLOR = (255, 230, 0)
_BLUE_TINT = (255, 0, 200)


def _to_rgba(bgr_small: np.ndarray) -> np.ndarray:
    rgb = cv2.cvtColor(bgr_small, cv2.COLOR_BGR2RGB)
    alpha = np.full(rgb.shape[:2] + (1,), 255, np.uint8)
    return np.concatenate([rgb, alpha], axis=2)


def _in_range(bgr_small: np.ndarray, rng) -> np.ndarray:
    hsv = cv2.cvtColor(bgr_small, cv2.COLOR_BGR2HSV)
    return cv2.inRange(
        hsv, np.array(rng.lower, dtype=np.uint8), np.array(rng.upper, dtype=np.uint8)
    )


def _tint(rgba: np.ndarray, mask: np.ndarray, color, strength: float = 0.6) -> None:
    sel = mask > 0
    if sel.any():
        rgba[sel, :3] = (
            rgba[sel, :3] * (1 - strength) + np.array(color) * strength
        ).astype(np.uint8)


def render_bar_preview(
    bar_bgr: np.ndarray,
    cursor_x: int | None,
    target_x: int | None,
    safe_range,
    cursor_range,
) -> np.ndarray:
    """Bar ROI with the colour matches tinted and the detected positions marked."""
    width, height = BAR_SIZE
    small = cv2.resize(bar_bgr, BAR_SIZE, interpolation=cv2.INTER_AREA)
    rgba = _to_rgba(small)
    _tint(rgba, _in_range(small, safe_range), _SAFE_TINT)
    _tint(rgba, _in_range(small, cursor_range), _CURSOR_COLOR, 0.8)

    src_w = max(bar_bgr.shape[1], 1)
    if target_x is not None:
        x = int(np.clip(target_x / src_w * width, 0, width - 1))
        cv2.rectangle(rgba, (max(x - 2, 0), 0), (min(x + 2, width - 1), height - 1), (0, 255, 0, 255), 1)
    if cursor_x is not None:
        x = int(np.clip(cursor_x / src_w * width, 0, width - 1))
        cv2.line(rgba, (x, 0), (x, height - 1), (255, 0, 0, 255), 1)
    cv2.rectangle(rgba, (0, 0), (width - 1, height - 1), (255, 255, 255, 120), 1)
    return rgba


def render_button_preview(button_bgr: np.ndarray, blue_range) -> tuple[np.ndarray, int]:
    """Button ROI with bite-colour pixels highlighted; also returns their count."""
    mask_full = _in_range(button_bgr, blue_range)
    count = int(cv2.countNonZero(mask_full))
    small = cv2.resize(button_bgr, BUTTON_SIZE, interpolation=cv2.INTER_AREA)
    rgba = _to_rgba(small)
    small_mask = cv2.resize(mask_full, BUTTON_SIZE, interpolation=cv2.INTER_NEAREST)
    _tint(rgba, small_mask, _BLUE_TINT, 0.85)
    cv2.rectangle(rgba, (0, 0), (BUTTON_SIZE[0] - 1, BUTTON_SIZE[1] - 1), (255, 255, 255, 120), 1)
    return rgba, count


def render_ocr_preview(raw_bgr: np.ndarray, binary: np.ndarray) -> np.ndarray:
    """Stack the OCR source crop over the binarised image the engine read."""
    width, height = OCR_SIZE
    half = height // 2
    top = cv2.resize(raw_bgr, (width, half), interpolation=cv2.INTER_AREA)
    bottom = cv2.resize(binary, (width, half), interpolation=cv2.INTER_AREA)
    bottom = cv2.cvtColor(bottom, cv2.COLOR_GRAY2BGR)
    rgba = _to_rgba(np.concatenate([top, bottom], axis=0))
    cv2.line(rgba, (0, half), (width - 1, half), (255, 255, 255, 160), 1)
    return rgba



def render_icon_preview(icon_bgr: np.ndarray) -> np.ndarray:
    """The lower-right action-bar strip used for the cast check."""
    small = cv2.resize(icon_bgr, ICON_SIZE, interpolation=cv2.INTER_AREA)
    rgba = _to_rgba(small)
    cv2.rectangle(rgba, (0, 0), (ICON_SIZE[0] - 1, ICON_SIZE[1] - 1), (255, 255, 255, 120), 1)
    return rgba
