"""OCR of the catch result card (fish name and weight)."""

import logging
import re
from collections.abc import Callable

log = logging.getLogger("NTEFish")

try:
    from rapidocr import RapidOCR as _RapidOCR

    OCR_IMPORTABLE = True
except ImportError:
    _RapidOCR = None  # type: ignore[assignment,misc]
    OCR_IMPORTABLE = False


_MAX_CROP_H = 120


def clean_fish_name(raw: str) -> str:
    """Keep word characters, spaces, apostrophes and hyphens; collapse whitespace."""
    name = re.sub(r"[^\w '\-]", " ", raw).strip()
    return re.sub(r" {2,}", " ", name)


def parse_weight(raw: str) -> str:
    """Return the first run of digits in *raw* (grams), or an empty string."""
    m = re.search(r"(\d+)", raw)
    return m.group(1) if m else ""


def ratios_to_roi(ratios, screen_w: int, screen_h: int, mon_x: int, mon_y: int) -> dict:
    """Convert (left, top, right, bottom) screen ratios to an absolute capture ROI."""
    left_r, top_r, right_r, bottom_r = ratios
    return {
        "left": mon_x + int(screen_w * left_r),
        "top": mon_y + int(screen_h * top_r),
        "width": int(screen_w * (right_r - left_r)),
        "height": int(screen_h * (bottom_r - top_r)),
    }


class CatchOcr:
    """Lazily initialised RapidOCR wrapper. Disables itself if the engine cannot start."""

    def __init__(self) -> None:
        self._engine = None
        self.available = OCR_IMPORTABLE
        # Last (raw crop, binarised image, text) per region, for the dashboard preview.
        self.last_regions: dict[str, tuple] = {}

    def warm_up(self) -> None:
        """Load the engine now so the first read does not pay the model load cost."""
        self._ensure_engine()

    def _ensure_engine(self) -> bool:
        if not self.available:
            return False
        if self._engine is None:
            try:
                self._engine = _RapidOCR()
            except Exception:
                # e.g. model files missing in a frozen build; don't take the bot down.
                log.warning(
                    "OCR engine failed to initialise; disabling OCR.", exc_info=True
                )
                self.available = False
                return False
        return True

    def _read_region(self, capture, roi: dict, key: str = "") -> str:
        try:
            import cv2  # imported lazily: only needed when OCR actually runs

            img = capture.grab_bgr(roi)
            # Scale up small regions so OCR has enough pixels to work with
            h, w = img.shape[:2]
            if h < 80:
                img = cv2.resize(img, (w * 3, h * 3), interpolation=cv2.INTER_CUBIC)
            elif h > _MAX_CROP_H:
                # Big (4K) crops make detection needlessly slow; text stays legible.
                scale = _MAX_CROP_H / h
                img = cv2.resize(
                    img,
                    (max(1, int(w * scale)), _MAX_CROP_H),
                    interpolation=cv2.INTER_AREA,
                )
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # Otsu picks the optimal split per-image; works for both
            # light-on-dark and dark-on-light text without a hard-coded level.
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
            # Mostly white background means dark text: invert so text is white on black.
            if cv2.countNonZero(thresh) > thresh.size * 0.5:
                thresh = cv2.bitwise_not(thresh)
            bgr = cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)
            result = self._engine(
                bgr, use_cls=False
            )  # one upright line: skip angle classifier
            text = " ".join(result.txts).strip() if result.txts else ""
            if key:
                self.last_regions[key] = (img, thresh, text)
            return text
        except Exception:
            log.debug("OCR region failed.", exc_info=True)
            return ""

    def read(
        self,
        capture,
        name_roi: dict,
        weight_roi: dict,
        hide_ui: Callable[[], None] | None = None,
        show_ui: Callable[[], None] | None = None,
    ) -> tuple[str, str]:
        """Return (name, weight_g); ("", "") when OCR is unavailable.

        *hide_ui* / *show_ui* bracket the capture so the GUI does not cover the card.
        """
        if not self._ensure_engine():
            return "", ""
        if hide_ui:
            try:
                hide_ui()
            except Exception:
                log.debug("Failed to hide UI for OCR capture.", exc_info=True)
        try:
            name = clean_fish_name(self._read_region(capture, name_roi, "name"))
            weight = parse_weight(self._read_region(capture, weight_roi, "weight"))
        finally:
            if show_ui:
                try:
                    show_ui()
                except Exception:
                    log.debug("Failed to show UI after OCR capture.", exc_info=True)
        return name, weight
