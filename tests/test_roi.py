import unittest
from types import SimpleNamespace

from config import AppConfig
from modules.roi import compute_rois


class TestComputeRois(unittest.TestCase):
    def test_default_4k_matches_the_calibrated_areas(self):
        mon = SimpleNamespace(x=0, y=0, width=3840, height=2160)
        bar, button = compute_rois(AppConfig(), mon)
        # automatic areas at 4K: bar 1209,118 1441x64 widened by 20 px per side
        # (same centre); bite 3400,1760 440x360
        self.assertLessEqual(abs(bar["left"] - 1189), 1)
        self.assertLessEqual(abs(bar["top"] - 118), 1)
        self.assertLessEqual(abs(bar["width"] - 1481), 1)
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


class TestAreaResize(unittest.TestCase):
    def test_width_and_height_deltas_resize_button_and_icon_areas(self):
        from config import AppConfig
        from modules.roi import compute_icon_roi

        mon = SimpleNamespace(x=0, y=0, width=1920, height=1080)
        cfg = AppConfig()
        b0, i0 = compute_rois(cfg, mon)[1], compute_icon_roi(cfg, mon)
        cfg.roi.button_width_delta, cfg.roi.button_height_delta = -20, 10
        cfg.roi.icon_width_delta, cfg.roi.icon_height_delta = 30, -5
        b1, i1 = compute_rois(cfg, mon)[1], compute_icon_roi(cfg, mon)
        self.assertEqual((b1["width"] - b0["width"], b1["height"] - b0["height"]), (-20, 10))
        self.assertEqual((i1["width"] - i0["width"], i1["height"] - i0["height"]), (30, -5))
