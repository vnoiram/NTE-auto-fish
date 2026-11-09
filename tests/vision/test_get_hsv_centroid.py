import unittest
from pathlib import Path

import cv2
import numpy as np

from config import HsvConfig
from modules.vision import _DEFAULT_MIN_AREA, VisionModule


class TestHSVCentroid(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_dir = Path(__file__).parent / "data"

        cls.hsv_centroid_bar_positive_images = sorted(
            (cls.data_dir / "bar/positive").rglob("*.png")
        )

        cls.hsv_centroid_bar_negative_images = sorted(
            (cls.data_dir / "bar/negative").rglob("*.png")
        )

        cls.hsv_centroid_cursor_positive_images = sorted(
            (cls.data_dir / "cursor/positive").rglob("*.png")
        )

        cls.hsv_centroid_cursor_negative_images = sorted(
            (cls.data_dir / "cursor/negative").rglob("*.png")
        )

    def load_image(self, image_path: Path) -> np.ndarray:
        img = cv2.imdecode(
            np.fromfile(image_path, dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )

        if img is None:
            raise Exception(f"Failed to load image: {image_path}")

        return img

    def _get_min_area(self, filename: str) -> float:
        base_area = _DEFAULT_MIN_AREA
        thresholds = {
            "4k": base_area,
            "2k": base_area / 2.0,
            "1080p": base_area / 4.0,
            "fhd": base_area / 4.0,
        }
        parts = filename.lower().split("_")
        res = next((p for p in parts if p in thresholds), "4k")
        return thresholds[res]

    def test_get_bar_positive_cases(self):
        for image_path in self.hsv_centroid_bar_positive_images:
            with self.subTest(image=image_path.name):
                img = self.load_image(image_path)
                min_area = self._get_min_area(image_path.stem)

                result = VisionModule.get_hsv_centroid_x(
                    img,
                    HsvConfig().safe_zone.lower,
                    HsvConfig().safe_zone.upper,
                    min_area=min_area,
                )

                self.assertIsNotNone(result[0])

    def test_get_bar_negative_cases(self):
        for image_path in self.hsv_centroid_bar_negative_images:
            with self.subTest(image=image_path.name):
                img = self.load_image(image_path)
                min_area = self._get_min_area(image_path.stem)

                result = VisionModule.get_hsv_centroid_x(
                    img,
                    HsvConfig().safe_zone.lower,
                    HsvConfig().safe_zone.upper,
                    min_area=min_area,
                )

                self.assertIsNone(result[0])

    def test_get_cursor_positive_cases(self):
        for image_path in self.hsv_centroid_cursor_positive_images:
            with self.subTest(image=image_path.name):
                img = self.load_image(image_path)
                min_area = self._get_min_area(image_path.stem)

                result = VisionModule.get_hsv_centroid_x(
                    img,
                    HsvConfig().cursor.lower,
                    HsvConfig().cursor.upper,
                    min_area=min_area,
                )

                self.assertIsNotNone(result[0])

    def test_get_cursor_negative_cases(self):
        for image_path in self.hsv_centroid_cursor_negative_images:
            with self.subTest(image=image_path.name):
                img = self.load_image(image_path)
                min_area = self._get_min_area(image_path.stem)

                result = VisionModule.get_hsv_centroid_x(
                    img,
                    HsvConfig().cursor.lower,
                    HsvConfig().cursor.upper,
                    min_area=min_area,
                )

                self.assertIsNone(result[0])


if __name__ == "__main__":
    unittest.main()


class TestEdgeTracking(unittest.TestCase):
    def _bar_with_cursor_at(self, x):
        img = np.zeros((60, 1000, 3), np.uint8)
        img[:, x : x + 6] = (0, 255, 255)  # yellow line (BGR) -> HSV hue ~30
        return img

    def _find(self, img, last):
        return VisionModule.get_hsv_centroid_x(
            img,
            (18, 115, 200),
            (40, 255, 255),
            min_area=20,
            ignore_margin_ratio=0.02,
            last_known_x=last,
        )[0]

    def test_cursor_in_the_edge_margin_is_ignored_without_history(self):
        self.assertIsNone(self._find(self._bar_with_cursor_at(2), None))

    def test_cursor_reaching_the_edge_is_tracked_when_it_was_heading_there(self):
        self.assertIsNotNone(self._find(self._bar_with_cursor_at(2), 40.0))
        self.assertIsNotNone(self._find(self._bar_with_cursor_at(992), 960.0))

    def test_margin_still_applies_when_the_cursor_was_far_from_the_edge(self):
        self.assertIsNone(self._find(self._bar_with_cursor_at(2), 500.0))
