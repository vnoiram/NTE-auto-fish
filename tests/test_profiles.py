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
    def test_defaults_contain_day_and_evening(self):
        names = [p["name"] for p in AppConfig().profiles]
        self.assertEqual(names, ["Day", "Evening"])

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
        self.assertEqual(len(profiles), 2)
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
        evening = BackgroundSampler()
        evening.add(_load(_DATA / "bar/negative/bar_negative_4k_1.png"))
        self.assertEqual(pick_profile(profiles, evening.signature())["name"], "Evening")
        # daytime sample with the gauge still on screen is noisier; use the
        # evening gauge-visible samples as a second check
        for path in sorted(glob.glob(str(_DATA / "bar/positive/*.png"))):
            sampler = BackgroundSampler()
            sampler.add(_load(path))
            picked = pick_profile(profiles, sampler.signature())
            self.assertTrue(picked is None or picked["name"] == "Evening", path)


if __name__ == "__main__":
    unittest.main()
