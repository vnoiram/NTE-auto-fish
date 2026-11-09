import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.modules.setdefault("pydirectinput", MagicMock())

from gui import app
from gui.pages import settings


class TestGuiPerformance(unittest.TestCase):
    def test_main_loop_does_not_refresh_setting_values(self):
        gui = app.FishingGUI.__new__(app.FishingGUI)
        gui.bridge = object()
        gui._position_viewport_away_from_roi = MagicMock()
        gui._start_bot = MagicMock()
        gui._shutdown = MagicMock()

        frame_count = 60
        perf_counter_values = [
            value
            for frame in range(frame_count)
            for value in (frame / 60.0, frame / 60.0)
        ]

        with (
            patch.object(
                app.dpg,
                "is_dearpygui_running",
                side_effect=[True] * frame_count + [False],
            ),
            patch.object(app.dpg, "show_viewport"),
            patch.object(app.dpg, "render_dearpygui_frame"),
            patch.object(app.dpg, "destroy_context"),
            patch.object(app, "update_dashboard_ui"),
            patch.object(app, "update_logs_ui"),
            patch.object(app, "update_settings_ui") as update_settings,
            patch.object(app, "apply_pending_settings_actions") as pending_actions,
            patch("time.perf_counter", side_effect=perf_counter_values),
            patch("time.sleep"),
        ):
            gui.run()

        update_settings.assert_not_called()
        self.assertEqual(pending_actions.call_count, 4)

    def test_native_viewport_title_is_ascii(self):
        self.assertTrue(app.APP_TITLE.isascii())

    def test_runtime_refresh_does_not_save_settings(self):
        fake_dpg = MagicMock()
        fake_dpg.does_item_exist.side_effect = lambda tag: (
            tag
            in {
                "page_settings",
                "cfg_vision_min_area",
            }
        )
        fake_dpg.is_item_shown.return_value = True
        bridge = MagicMock()
        bridge.latest_status.return_value = SimpleNamespace(current_scale=1.0)

        with (
            patch.object(settings, "dpg", fake_dpg),
            patch.object(settings, "_session_manager", None),
            patch.object(settings, "_monitor_labels", return_value=["Monitor 0"]),
            patch.object(settings, "update_hsv_preview"),
            patch.object(settings.CFG, "save") as save,
        ):
            settings.update_settings_ui(bridge)
            save.assert_not_called()

            settings._save(bridge)
            save.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
