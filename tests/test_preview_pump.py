import unittest
from types import SimpleNamespace

import numpy as np

from config import AppConfig
from gui.preview_pump import PreviewPump
from modules.preview import OCR_SIZE, render_ocr_preview
from modules.roi import compute_icon_roi


class FakeOcr:
    def __init__(self, available=True):
        self.available = available
        self.last_regions = {}
        self.read_calls = 0

    def read(self, capture, name_roi, weight_roi):
        self.read_calls += 1
        img = np.full((20, 80, 3), 120, np.uint8)
        gray = np.zeros((20, 80), np.uint8)
        self.last_regions = {"name": (img, gray, "Carp"), "weight": (img, gray, "1200")}
        return "Carp", "1200"


class TestPreviewPumpOcr(unittest.TestCase):
    MON = SimpleNamespace(x=0, y=0, width=1920, height=1080)

    def test_ocr_reads_the_current_areas_and_publishes_images_and_text(self):
        pv = {}
        PreviewPump._read_ocr(FakeOcr(), None, self.MON, pv, render_ocr_preview)
        self.assertEqual(pv["ocr_name_text"], "Carp")
        self.assertEqual(pv["ocr_weight_text"], "1200")
        self.assertEqual(pv["ocr_name"].shape, (OCR_SIZE[1], OCR_SIZE[0], 4))

    def test_unavailable_ocr_is_reported(self):
        pv = {}
        PreviewPump._read_ocr(FakeOcr(False), None, self.MON, pv, render_ocr_preview)
        self.assertEqual(pv["ocr_name_text"], "OCR unavailable")


class TestIconRoi(unittest.TestCase):
    def test_default_icon_area_sits_in_the_lower_right_with_a_small_margin(self):
        roi = compute_icon_roi(AppConfig(), SimpleNamespace(x=0, y=0, width=1920, height=1080))
        self.assertLess(roi["left"] + roi["width"], 1920)
        self.assertGreater(roi["left"] + roi["width"], 1900)
        self.assertLess(roi["top"] + roi["height"], 1080)
        self.assertEqual(roi["width"], 515)


if __name__ == "__main__":
    unittest.main()
