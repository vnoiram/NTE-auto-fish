import unittest
from pathlib import Path

import cv2
import numpy as np

from modules.vision import VisionModule

_DATA = Path(__file__).parent / "data" / "cast"


def _load(path: Path) -> np.ndarray:
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)


class TestCountIcons(unittest.TestCase):
    def test_cast_succeeded_leaves_only_the_f_icon(self):
        for path in sorted((_DATA / "positive").glob("*.png")):
            with self.subTest(image=path.name):
                count = VisionModule.count_icons(_load(path), 0.5)
                self.assertLessEqual(count, 1)

    def test_no_cast_shows_all_action_icons(self):
        for path in sorted((_DATA / "negative").glob("*.png")):
            with self.subTest(image=path.name):
                count = VisionModule.count_icons(_load(path), 0.5)
                self.assertGreaterEqual(count, 3)

    def test_counts_hold_at_4k_scale(self):
        for sub, expected in (("negative", 4), ("positive", 1)):
            for path in sorted((_DATA / sub).glob("*.png")):
                big = cv2.resize(_load(path), None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
                with self.subTest(image=path.name):
                    self.assertEqual(VisionModule.count_icons(big, 1.0), expected)


if __name__ == "__main__":
    unittest.main()
