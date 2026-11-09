import unittest
from unittest.mock import patch

import dearpygui.dearpygui as dpg

from config import CFG
from gui.bridge import BotBridge, BotStatus
from gui.pages import dashboard


class TestPreviewDrag(unittest.TestCase):
    """Drag math only; DearPyGui calls are patched so no GUI context is needed."""

    def setUp(self):
        self.bridge = BotBridge()
        self.bridge._current_status = BotStatus(
            bar_roi=(100, 50, 1441, 64), button_roi=(3400, 1760, 440, 360)
        )
        dashboard.bind_preview_drag(self.bridge)
        self._saved = (
            CFG.roi.bar_offset_x,
            CFG.roi.bar_offset_y,
            CFG.roi.button_offset_x,
            CFG.roi.button_offset_y,
        )

    def tearDown(self):
        (
            CFG.roi.bar_offset_x,
            CFG.roi.bar_offset_y,
            CFG.roi.button_offset_x,
            CFG.roi.button_offset_y,
        ) = self._saved
        dashboard._on_preview_release()

    def _drag(self, tag, dx, dy):
        with (
            patch.object(dashboard, "_over_preview", side_effect=lambda t: t == tag),
            patch.object(dpg, "does_item_exist", return_value=True),
            patch.object(dpg, "set_value"),
        ):
            dashboard._on_preview_drag(None, [0, dx, dy])

    def test_dragging_the_bar_preview_moves_the_area_opposite(self):
        self._drag("pv_bar", 51.2, 0)  # 51.2 shown px = ~144 screen px
        self.assertEqual(CFG.roi.bar_offset_x, -144)

    def test_dragging_the_bite_preview_changes_only_the_bite_offsets(self):
        before = CFG.roi.bar_offset_x
        self._drag("pv_button", 0, -17.6)  # 360/144 = 2.5 px per shown px
        self.assertEqual(CFG.roi.button_offset_y, 44)
        self.assertEqual(CFG.roi.bar_offset_x, before)

    def test_drag_uses_the_pump_geometry_before_the_bot_was_calibrated(self):
        self.bridge._current_status = BotStatus()  # no ROI known yet
        self.bridge.preview["bar_roi"] = (100, 50, 1441, 64)
        self._drag("pv_bar", 51.2, 0)
        self.assertEqual(CFG.roi.bar_offset_x, -144)
        self.bridge.preview["bar_roi"] = None

    def test_mouse_inside_the_image_rect_counts_even_without_hover(self):
        with (
            patch.object(dpg, "is_item_hovered", return_value=False),
            patch.object(dpg, "get_item_rect_min", return_value=(100, 200)),
            patch.object(dpg, "get_item_rect_size", return_value=(512, 48)),
            patch.object(dpg, "get_mouse_pos", return_value=(300, 220)),
        ):
            self.assertTrue(dashboard._over_preview("pv_bar"))
        with (
            patch.object(dpg, "is_item_hovered", return_value=False),
            patch.object(dpg, "get_item_rect_min", return_value=(100, 200)),
            patch.object(dpg, "get_item_rect_size", return_value=(512, 48)),
            patch.object(dpg, "get_mouse_pos", return_value=(50, 220)),
        ):
            self.assertFalse(dashboard._over_preview("pv_bar"))

    def test_drag_outside_a_preview_does_nothing(self):
        before = CFG.roi.bar_offset_x
        self._drag("elsewhere", 30, 30)
        self.assertEqual(CFG.roi.bar_offset_x, before)


if __name__ == "__main__":
    unittest.main()
