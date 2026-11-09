import unittest
from types import SimpleNamespace

from config import AppConfig
from modules.roi import compute_rois


class TestComputeRois(unittest.TestCase):
    def test_default_4k_matches_the_calibrated_areas(self):
        mon = SimpleNamespace(x=0, y=0, width=3840, height=2160)
        bar, button = compute_rois(AppConfig(), mon)
        # the bot's automatic areas at 4K: bar 1209,118 1441x64; bite 3400,1760 440x360
        self.assertLessEqual(abs(bar["left"] - 1209), 1)
        self.assertLessEqual(abs(bar["top"] - 118), 1)
        self.assertLessEqual(abs(bar["width"] - 1441), 1)
        self.assertLessEqual(abs(bar["height"] - 64), 1)
        self.assertEqual(
            button, {"left": 3400, "top": 1760, "width": 440, "height": 360}
        )

    def test_monitor_origin_offsets_and_corrections_apply(self):
        cfg = AppConfig()
        cfg.roi.bar_offset_x = 10
        cfg.roi.button_offset_y = -20
        mon = SimpleNamespace(x=1920, y=0, width=1920, height=1080)
        bar, button = compute_rois(cfg, mon)
        self.assertGreaterEqual(bar["left"], 1920)
        self.assertEqual(button["top"], 880 - 20)

    def test_saved_ratios_replace_the_defaults(self):
        cfg = AppConfig()
        cfg.bar_roi_ratios = (0.25, 0.1, 0.75, 0.2)
        mon = SimpleNamespace(x=0, y=0, width=2000, height=1000)
        bar, _ = compute_rois(cfg, mon)
        self.assertEqual(bar, {"left": 500, "top": 100, "width": 1000, "height": 100})


if __name__ == "__main__":
    unittest.main()


class TestAreaReset(unittest.TestCase):
    def test_reset_area_restores_automatic_values(self):
        from config import AppConfig
        from gui.pages.dashboard import reset_area

        cfg = AppConfig()
        cfg.icon_roi_ratios = (0.1, 0.1, 0.2, 0.2)
        cfg.roi.icon_offset_x = 40
        cfg.ocr_name_roi_ratios = (0.0, 0.0, 0.1, 0.1)
        reset_area("icons", cfg)
        reset_area("ocr_name", cfg)
        self.assertEqual(cfg.icon_roi_ratios, (0.0, 0.0, 0.0, 0.0))
        self.assertEqual(cfg.roi.icon_offset_x, 0)
        self.assertEqual(cfg.ocr_name_roi_ratios, AppConfig().ocr_name_roi_ratios)

    def test_icon_offset_moves_the_icon_area(self):
        from types import SimpleNamespace

        from config import AppConfig
        from modules.roi import compute_icon_roi

        mon = SimpleNamespace(x=0, y=0, width=1920, height=1080)
        cfg = AppConfig()
        base = compute_icon_roi(cfg, mon)
        cfg.roi.icon_offset_x, cfg.roi.icon_offset_y = 15, -7
        moved = compute_icon_roi(cfg, mon)
        self.assertEqual((moved["left"] - base["left"], moved["top"] - base["top"]), (15, -7))
