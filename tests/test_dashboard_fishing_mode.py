import unittest
from unittest.mock import MagicMock, patch

from config import AppConfig
from gui.bridge import BotStatus
from gui.i18n import set_language
from gui.pages import dashboard
from modules.logic import FishingState


class TestDashboardFishingMode(unittest.TestCase):
    def tearDown(self):
        set_language("en")

    def test_controls_expose_saved_mode_and_both_timeouts(self):
        cfg = AppConfig()
        cfg.bar_only_mode = True
        cfg.timing.bar_only_timeout_secs = 90.0
        cfg.timing.catch_icon_timeout_secs = 0.5
        fake_dpg = MagicMock()
        with (
            patch.object(dashboard, "CFG", cfg),
            patch.object(dashboard, "dpg", fake_dpg),
            patch.object(dashboard, "apply_glass_card_theme"),
        ):
            dashboard._create_fishing_mode_controls()
        self.assertTrue(fake_dpg.add_checkbox.call_args.kwargs["default_value"])
        fields = {
            c.kwargs["tag"]: c.kwargs for c in fake_dpg.add_input_float.call_args_list
        }
        self.assertEqual(fields["bar_only_timeout"]["default_value"], 90.0)
        self.assertEqual(fields["catch_icon_timeout"]["default_value"], 0.5)

    def test_dashboard_changes_save_settings_and_clamp_timeouts(self):
        cfg = AppConfig()
        with (
            patch.object(dashboard, "CFG", cfg),
            patch.object(dashboard, "dpg"),
            patch.object(cfg, "save") as save,
        ):
            dashboard._set_bar_only_mode(None, True)
            dashboard._set_bar_only_timeout(None, 45.0)
            dashboard._set_catch_icon_timeout(None, 0.7)
            self.assertTrue(cfg.bar_only_mode)
            self.assertEqual(cfg.timing.bar_only_timeout_secs, 45.0)
            self.assertEqual(cfg.timing.catch_icon_timeout_secs, 0.7)
            self.assertEqual(save.call_count, 3)
            dashboard._set_bar_only_timeout(None, 0.0)
            dashboard._set_catch_icon_timeout(None, -1.0)
            self.assertEqual(cfg.timing.bar_only_timeout_secs, 1.0)
            self.assertEqual(cfg.timing.catch_icon_timeout_secs, 0.0)
            dashboard._set_bar_only_timeout(None, float("inf"))
            self.assertEqual(cfg.timing.bar_only_timeout_secs, 1.0)

    def test_status_shows_mode_timeout_and_localized_bait_error(self):
        set_language("ja")
        status = BotStatus(
            is_running=True,
            is_stopped=False,
            bar_only_mode=True,
            bar_only_secs_left=42.0,
        )
        self.assertIn("42秒", dashboard._status_message(status))
        status.state = FishingState.STRUGGLING
        self.assertEqual(dashboard._status_message(status), "釣りゲージを追従中")
        status.is_running = False
        status.is_stopped = True
        status.stop_reason = "Bait error: no battle bars detected"
        self.assertIn("エサエラー", dashboard._status_message(status))
