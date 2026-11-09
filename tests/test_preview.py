import unittest

import cv2
import numpy as np

from config import HsvConfig
from types import SimpleNamespace
from unittest.mock import MagicMock

from modules.ocr import CatchOcr
from modules.preview import (
    BAR_SIZE,
    BUTTON_SIZE,
    OCR_SIZE,
    render_bar_preview,
    render_button_preview,
    render_ocr_preview,
)


def _bgr(h, s, v):
    return tuple(int(c) for c in cv2.cvtColor(np.uint8([[[h, s, v]]]), cv2.COLOR_HSV2BGR)[0, 0])


class TestPreview(unittest.TestCase):
    def test_bar_preview_has_fixed_size_and_marks_positions(self):
        hsv = HsvConfig()
        img = np.full((64, 1441, 3), 30, np.uint8)
        img[:, 600:900] = _bgr(88, 230, 230)
        out = render_bar_preview(img, 700, 750, hsv.safe_zone, hsv.cursor)
        self.assertEqual(out.shape, (BAR_SIZE[1], BAR_SIZE[0], 4))
        self.assertEqual(out.dtype, np.uint8)
        x = int(700 / 1441 * BAR_SIZE[0])
        self.assertTrue((out[5, x, :3] == (255, 0, 0)).all())  # cursor marker

    def test_bar_preview_without_detections(self):
        hsv = HsvConfig()
        out = render_bar_preview(np.zeros((64, 1441, 3), np.uint8), None, None, hsv.safe_zone, hsv.cursor)
        self.assertEqual(out.shape[2], 4)

    def test_button_preview_counts_blue_pixels(self):
        hsv = HsvConfig()
        img = np.full((360, 440, 3), 20, np.uint8)
        img[100:200, 100:200] = _bgr(115, 220, 230)
        out, count = render_button_preview(img, hsv.blue)
        self.assertEqual(count, 100 * 100)
        self.assertEqual(out.shape, (BUTTON_SIZE[1], BUTTON_SIZE[0], 4))

    def test_ocr_preview_stacks_crop_and_binary(self):
        raw = np.full((30, 120, 3), 200, np.uint8)
        binary = np.zeros((30, 120), np.uint8)
        out = render_ocr_preview(raw, binary)
        self.assertEqual(out.shape, (OCR_SIZE[1], OCR_SIZE[0], 4))

    def test_catch_ocr_keeps_the_images_it_read(self):
        ocr = CatchOcr()
        ocr._engine = MagicMock(return_value=SimpleNamespace(txts=["Carp"]))
        capture = MagicMock()
        capture.grab_bgr.return_value = np.full((40, 200, 3), 90, np.uint8)
        text = ocr._read_region(capture, {"left": 0}, "name")
        self.assertEqual(text, "Carp")
        raw, binary, saved_text = ocr.last_regions["name"]
        self.assertEqual(saved_text, "Carp")
        self.assertEqual(raw.shape[:2], binary.shape[:2])


if __name__ == "__main__":
    unittest.main()
