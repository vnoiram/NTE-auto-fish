"""Computer vision helpers for HSV detection."""

import cv2
import numpy as np

from config import CFG, HsvRange

_ERROR_BRIGHTNESS_THRESHOLD = 50
_ERROR_WHITE_PIXEL_MIN = 1200
_ERROR_WHITE_RATIO_MIN = 0.004
_ERROR_WHITE_RATIO_MAX = 0.35
# The cast-error text sits in the middle of a full-width band. White UI text near
# the screen edges (hints, key prompts) in a dark scene must not count.
_ERROR_CENTER_BAND = (0.25, 0.75)
_ERROR_CENTER_SHARE_MIN = 0.85

_DEFAULT_MIN_AREA = 40.0
_KERNEL_3x3 = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))


class VisionModule:
    """Stateless image processing utilities."""

    @staticmethod
    def to_hsv(bgr_img: np.ndarray) -> np.ndarray:
        """Convert a BGR image to HSV color space."""
        return cv2.cvtColor(bgr_img, cv2.COLOR_BGR2HSV)

    @staticmethod
    def get_hsv_centroid_x(
        bgr_img: np.ndarray,
        lower: tuple,
        upper: tuple,
        min_area: float = _DEFAULT_MIN_AREA,
        ignore_margin_ratio: float = 0.0,
        last_known_x: float | None = None,
        hsv_img: np.ndarray | None = None,
    ):
        """Return the horizontal centroid for pixels inside an HSV range."""
        hsv = (
            hsv_img if hsv_img is not None else cv2.cvtColor(bgr_img, cv2.COLOR_BGR2HSV)
        )
        mask = cv2.inRange(
            hsv,
            np.array(lower, dtype=np.uint8),
            np.array(upper, dtype=np.uint8),
        )
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, _KERNEL_3x3)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return None, 0.0

        valid_contours = []
        img_width = bgr_img.shape[1]

        for contour in contours:
            x, _, w, h = cv2.boundingRect(contour)
            bbox_area = w * h

            if bbox_area < min_area:
                continue

            if ignore_margin_ratio > 0.0:
                left_limit = img_width * ignore_margin_ratio
                right_limit = img_width * (1.0 - ignore_margin_ratio)
                if x < left_limit or (x + w) > right_limit:
                    continue

            valid_contours.append(contour)

        if not valid_contours:
            return None, 0.0

        if last_known_x is None:
            last_known_x = img_width / 2.0

        def distance_to_last(contour) -> float:
            x, _, w, _ = cv2.boundingRect(contour)
            return abs((x + w / 2.0) - last_known_x)

        valid_contours.sort(key=distance_to_last)

        main_contour = valid_contours[0]
        main_x, _, main_w, main_h = cv2.boundingRect(main_contour)
        group_min_x = main_x
        group_max_x = main_x + main_w
        total_area = main_w * main_h
        gap_threshold = img_width * 0.05

        for contour in valid_contours[1:]:
            x, _, w, h = cv2.boundingRect(contour)
            gap = max(0, max(group_min_x - (x + w), x - group_max_x))
            if gap <= gap_threshold:
                group_min_x = min(group_min_x, x)
                group_max_x = max(group_max_x, x + w)
                total_area += w * h

        cx = int((group_min_x + group_max_x) / 2.0)
        return cx, float(total_area)

    @staticmethod
    def check_error_region(
        bgr_img: np.ndarray,
        brightness_threshold: float = _ERROR_BRIGHTNESS_THRESHOLD,
        white_pixel_min: int = _ERROR_WHITE_PIXEL_MIN,
    ) -> bool:
        """Return True when the region shows a dark background with white text (error dialog)."""
        gray = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2GRAY)
        mean_brightness = float(np.mean(gray))
        if mean_brightness > brightness_threshold:
            return False
        total_pixels = gray.shape[0] * gray.shape[1]
        white_pixels = int(
            cv2.countNonZero(cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)[1])
        )
        if white_pixels < white_pixel_min:
            return False
        ratio = white_pixels / max(total_pixels, 1)
        if not (_ERROR_WHITE_RATIO_MIN <= ratio <= _ERROR_WHITE_RATIO_MAX):
            return False
        white = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)[1]
        width = white.shape[1]
        lo = int(width * _ERROR_CENTER_BAND[0])
        hi = int(width * _ERROR_CENTER_BAND[1])
        center_white = int(cv2.countNonZero(white[:, lo:hi]))
        return center_white / max(white_pixels, 1) >= _ERROR_CENTER_SHARE_MIN

    @staticmethod
    def check_blue_trigger(
        bgr_img: np.ndarray,
        hsv_range: HsvRange | None = None,
        min_pixels: int | None = None,
        hsv_img: np.ndarray | None = None,
    ) -> bool:
        """Return true when enough bite-trigger pixels are present."""
        hsv = (
            hsv_img if hsv_img is not None else cv2.cvtColor(bgr_img, cv2.COLOR_BGR2HSV)
        )
        blue = hsv_range or CFG.hsv.blue
        threshold = CFG.min_blue_pixels if min_pixels is None else min_pixels
        lower = np.array(blue.lower, dtype=np.uint8)
        upper = np.array(blue.upper, dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)
        return cv2.countNonZero(mask) >= threshold
