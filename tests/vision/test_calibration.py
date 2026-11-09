import unittest

import cv2
import numpy as np

from modules.calibration import (
    BackgroundSampler,
    GaugeAssist,
    suggest_gauge_at_start,
    describe,
    suggest_bite,
    suggest_gauge,
)


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

    def test_background_colours_are_ignored(self):
        bg_img = np.full((40, 200, 3), 20, np.uint8)
        bg_img[:, 100:200] = _bgr(26, 150, 250)  # sunset-like yellow backdrop
        img = bg_img.copy()
        img[:, 40:60] = _bgr(88, 230, 230)  # safe zone
        img[:, 90:94] = _bgr(28, 130, 250)  # cursor (distinct saturation bin)
        hints = ((75, 190, 190), (100, 255, 255)), ((18, 115, 240), (40, 150, 255))
        sampler = BackgroundSampler()
        sampler.add(bg_img)
        _, without = suggest_gauge(img, *hints)
        _, with_bg = suggest_gauge(img, *hints, sampler)
        self.assertIsNotNone(without)
        self.assertLess(with_bg.pixels if with_bg else 0, without.pixels)

    def test_fight_start_finds_centered_cursor_and_safe_zone(self):
        img = np.full((40, 400, 3), 20, np.uint8)
        img[:, 140:260] = _bgr(88, 230, 230)  # fish bar around the centre
        img[:, 198:202] = _bgr(28, 80, 255)  # cursor line at the centre
        img[:, 20:60] = _bgr(26, 200, 250)  # yellow background far from centre
        safe, cursor = suggest_gauge_at_start(img)
        self.assertIsNotNone(safe)
        self.assertIsNotNone(cursor)
        self.assertTrue(safe.lower[0] <= 88 <= safe.upper[0])
        self.assertTrue(cursor.lower[0] <= 28 <= cursor.upper[0])

    def test_fight_start_ignores_off_centre_yellow(self):
        img = np.full((40, 400, 3), 20, np.uint8)
        img[:, 140:260] = _bgr(88, 230, 230)
        img[:, 20:60] = _bgr(28, 80, 255)  # yellow only far from the centre
        _, cursor = suggest_gauge_at_start(img)
        self.assertIsNone(cursor)

    def test_gauge_assist_aggregates_median_and_hit_rate(self):
        assist = GaugeAssist()
        img = np.full((40, 400, 3), 20, np.uint8)
        img[:, 140:260] = _bgr(88, 230, 230)
        img[:, 198:202] = _bgr(28, 80, 255)
        safe, cursor = suggest_gauge_at_start(img)
        assist.add(safe, cursor, True)
        assist.add(safe, cursor, False)
        assist.add_miss()
        self.assertEqual(assist.samples, 2)
        self.assertAlmostEqual(assist.hit_rate, 0.5)
        self.assertEqual(assist.misses, 1)
        self.assertEqual(assist.summary()[1].lower, cursor.lower)
        assist.reset()
        self.assertEqual(assist.samples, 0)

    def test_describe_reports_size(self):
        self.assertIn("200x40", describe(np.zeros((40, 200, 3), np.uint8)))


if __name__ == "__main__":
    unittest.main()
