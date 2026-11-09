import unittest
from types import SimpleNamespace

import numpy as np

from config import AppConfig
from gui.bridge import BotBridge
from gui.preview_pump import PreviewPump, SnapshotCapture
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
        roi = compute_icon_roi(
            AppConfig(), SimpleNamespace(x=0, y=0, width=1920, height=1080)
        )
        self.assertLess(roi["left"] + roi["width"], 1920)
        self.assertGreater(roi["left"] + roi["width"], 1900)
        self.assertLess(roi["top"] + roi["height"], 1080)
        self.assertEqual(roi["width"], 515)


class TestSnapshotAdjusting(unittest.TestCase):
    MON = SimpleNamespace(x=0, y=0, width=1920, height=1080)

    def test_snapshot_capture_crops_screen_coordinates(self):
        image = np.zeros((1080, 1920, 3), np.uint8)
        image[100:150, 200:300] = 255
        snap = SnapshotCapture(image, 0, 0)
        crop = snap.grab_bgr({"left": 200, "top": 100, "width": 100, "height": 50})
        self.assertEqual(crop.shape, (50, 100, 3))
        self.assertTrue((crop == 255).all())

    def test_snapshot_capture_honours_the_monitor_origin_and_clamps(self):
        image = np.zeros((1080, 1920, 3), np.uint8)
        snap = SnapshotCapture(image, 1920, 0)
        crop = snap.grab_bgr(
            {"left": 1920 + 1900, "top": 1070, "width": 500, "height": 500}
        )
        self.assertEqual(crop.shape[:2], (10, 20))

    def test_render_uses_the_snapshot_without_capturing(self):
        image = np.full((1080, 1920, 3), 30, np.uint8)
        pump = PreviewPump(BotBridge())
        before = pump._bridge.preview["version"]
        pump._render(SnapshotCapture(image, 0, 0), self.MON)
        pv = pump._bridge.preview
        self.assertEqual(pv["version"], before + 1)
        self.assertIsNotNone(pv["bar"])
        self.assertIsNotNone(pv["icons"])
        self.assertTrue(pv["icons_text"].startswith("icons "))

    def test_settings_key_changes_when_an_area_is_moved(self):
        from config import CFG

        key = PreviewPump._settings_key(self.MON)
        saved = CFG.roi.bar_offset_x
        try:
            CFG.roi.bar_offset_x = saved + 25
            self.assertNotEqual(key, PreviewPump._settings_key(self.MON))
        finally:
            CFG.roi.bar_offset_x = saved
        self.assertEqual(key, PreviewPump._settings_key(self.MON))


if __name__ == "__main__":
    unittest.main()


class TestPumpLog(unittest.TestCase):
    def test_pump_log_is_capped_and_bumps_version(self):
        from gui.preview_pump import add_pump_log

        pv = {"pump_log": [], "version": 0}
        for i in range(30):
            add_pump_log(pv, f"step {i}")
        self.assertEqual(len(pv["pump_log"]), 12)
        self.assertTrue(pv["pump_log"][-1].endswith("step 29"))
        self.assertEqual(pv["version"], 30)
