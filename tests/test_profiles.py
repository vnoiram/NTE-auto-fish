import glob
import unittest
from pathlib import Path

import cv2
import numpy as np

from config import AppConfig
from modules.calibration import BackgroundSampler
from modules.profiles import (
    apply_profile,
    default_profiles,
    make_profile,
    pick_profile,
    upsert_profile,
)

_DATA = Path(__file__).parent / "vision" / "data"


def _load(path) -> np.ndarray:
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)


class TestProfiles(unittest.TestCase):
    def test_defaults_contain_day_evening_and_night(self):
        names = [p["name"] for p in AppConfig().profiles]
        self.assertEqual(names, ["Day", "Evening", "Night"])

    def test_make_and_apply_round_trip(self):
        cfg = AppConfig()
        cfg.hsv.cursor.lower = (1, 2, 3)
        cfg.min_blue_pixels = 77
        profile = make_profile("Night", cfg, [0.1] * 53)
        other = AppConfig()
        apply_profile(other, profile)
        self.assertEqual(other.hsv.cursor.lower, (1, 2, 3))
        self.assertEqual(other.min_blue_pixels, 77)
        self.assertEqual(other.active_profile, "Night")

    def test_upsert_replaces_same_name(self):
        profiles = default_profiles()
        upsert_profile(profiles, {**profiles[0], "min_blue_pixels": 5})
        self.assertEqual(len(profiles), 3)
        self.assertEqual(profiles[0]["min_blue_pixels"], 5)

    def test_pick_returns_none_when_too_far(self):
        far = [0.0] * 52 + [4.0]
        self.assertIsNone(pick_profile(default_profiles(), far))

    def test_pick_ignores_malformed_profiles(self):
        profiles = ["x", {"name": "bad"}, *default_profiles()]
        sig = default_profiles()[0]["signature"]
        self.assertEqual(pick_profile(profiles, sig)["name"], "Day")

    def test_sample_backgrounds_select_expected_profile(self):
        profiles = default_profiles()

        def pick(path):
            sampler = BackgroundSampler()
            sampler.add(_load(_DATA / path))
            return pick_profile(profiles, sampler.signature())

        self.assertEqual(pick("bar/negative/bar_negative_4k_1.png")["name"], "Evening")
        self.assertEqual(pick("bar/positive/bar_positive_fhd_nigh_1.png")["name"], "Night")
        # gauge-visible evening samples must never be mistaken for day or night
        for path in sorted(glob.glob(str(_DATA / "bar/positive/*4k*.png"))):
            picked = pick(Path(path).relative_to(_DATA))
            self.assertTrue(picked is None or picked["name"] == "Evening", path)


if __name__ == "__main__":
    unittest.main()
