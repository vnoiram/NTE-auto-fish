import unittest

import cv2
import numpy as np

from modules.calibration import describe, suggest_bite, suggest_gauge


def _bgr(h: int, s: int, v: int) -> tuple[int, int, int]:
    px = np.uint8([[[h, s, v]]])
    return tuple(int(c) for c in cv2.cvtColor(px, cv2.COLOR_HSV2BGR)[0, 0])


class TestCalibration(unittest.TestCase):
    def test_bite_picks_blue_even_when_other_colour_is_larger(self):
        img = np.zeros((60, 100, 3), np.uint8)
        img[:, :60] = _bgr(20, 200, 220)  # larger warm area
        img[:, 60:] = _bgr(115, 220, 230)  # blue prompt
        s = suggest_bite(img)
        self.assertIsNotNone(s)
        self.assertLessEqual(s.lower[0], 115)
        self.assertGreaterEqual(s.upper[0], 115)
        self.assertEqual(s.pixels, 60 * 40)

    def test_bite_none_on_dark_image(self):
        self.assertIsNone(suggest_bite(np.zeros((40, 40, 3), np.uint8)))

    def test_gauge_safe_zone_is_dominant_and_cursor_is_other_hue(self):
        img = np.full((40, 200, 3), 20, np.uint8)
        img[:, 40:140] = _bgr(88, 230, 230)  # wide safe zone
        img[:, 90:94] = _bgr(28, 130, 250)  # thin cursor
        safe, cursor = suggest_gauge(img)
        self.assertIsNotNone(safe)
        self.assertIsNotNone(cursor)
        self.assertTrue(safe.lower[0] <= 88 <= safe.upper[0])
        self.assertTrue(cursor.lower[0] <= 28 <= cursor.upper[0])
        self.assertGreater(safe.pixels, cursor.pixels)

    def test_gauge_without_cursor(self):
        img = np.full((40, 200, 3), 20, np.uint8)
        img[:, 40:140] = _bgr(88, 230, 230)
        safe, cursor = suggest_gauge(img)
        self.assertIsNotNone(safe)
        self.assertIsNone(cursor)

    def test_gauge_relaxes_thresholds_for_dull_colours(self):
        img = np.full((40, 200, 3), 20, np.uint8)
        img[:, 40:140] = _bgr(88, 45, 90)  # low saturation / brightness
        safe, _ = suggest_gauge(img)
        self.assertIsNotNone(safe)

    def test_gauge_hints_ignore_unrelated_bright_colours(self):
        img = np.full((40, 200, 3), 20, np.uint8)
        img[:, 40:140] = _bgr(88, 230, 230)  # safe zone
        img[:, 90:94] = _bgr(28, 130, 250)  # yellow cursor
        img[:, 150:190] = _bgr(150, 200, 255)  # bright unrelated purple UI
        safe, cursor = suggest_gauge(
            img, ((75, 190, 190), (100, 255, 255)), ((18, 115, 240), (40, 150, 255))
        )
        self.assertTrue(cursor.lower[0] <= 28 <= cursor.upper[0])
        self.assertLessEqual(cursor.upper[0], 70)
        self.assertLessEqual(safe.upper[0], 120)

    def test_gauge_hint_without_match_returns_none(self):
        img = np.full((40, 200, 3), 20, np.uint8)
        img[:, 150:190] = _bgr(150, 200, 255)
        safe, cursor = suggest_gauge(
            img, ((75, 190, 190), (100, 255, 255)), ((18, 115, 240), (40, 150, 255))
        )
        self.assertIsNone(safe)
        self.assertIsNone(cursor)

    def test_describe_reports_size(self):
        self.assertIn("200x40", describe(np.zeros((40, 200, 3), np.uint8)))


if __name__ == "__main__":
    unittest.main()
