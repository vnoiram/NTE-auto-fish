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
        buttons = {
            c.kwargs["tag"]: c.kwargs for c in fake_dpg.add_button.call_args_list
        }
        self.assertIn("btn_mode_normal", buttons)
        self.assertIn("btn_mode_bar_only", buttons)
        self.assertIn("selected", buttons["btn_mode_bar_only"]["label"])
        fake_dpg.add_checkbox.assert_not_called()
        fields = {
            c.kwargs["tag"]: c.kwargs for c in fake_dpg.add_input_float.call_args_list
        }
        self.assertEqual(fields["bar_only_timeout"]["default_value"], 90.0)
        self.assertEqual(fields["catch_icon_timeout"]["default_value"], 0.5)

    def test_mode_card_grows_with_its_controls_instead_of_clipping_them(self):
        fake_dpg = MagicMock()
        with (
            patch.object(dashboard, "dpg", fake_dpg),
            patch.object(dashboard, "apply_glass_card_theme"),
        ):
            dashboard._create_fishing_mode_controls()
        self.assertTrue(fake_dpg.child_window.call_args.kwargs.get("auto_resize_y"))

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

    def test_both_buttons_switch_modes_and_save_without_redundant_writes(self):
        cfg = AppConfig()
        fake_dpg = MagicMock()
        with (
            patch.object(dashboard, "CFG", cfg),
            patch.object(dashboard, "dpg", fake_dpg),
            patch.object(dashboard, "apply_glass_card_theme"),
            patch.object(cfg, "save") as save,
        ):
            dashboard._create_fishing_mode_controls()
            buttons = {
                c.kwargs["tag"]: c.kwargs for c in fake_dpg.add_button.call_args_list
            }
            buttons["btn_mode_normal"]["callback"]()
            save.assert_not_called()
            buttons["btn_mode_bar_only"]["callback"]()
            self.assertTrue(cfg.bar_only_mode)
            buttons["btn_mode_normal"]["callback"]()
            self.assertFalse(cfg.bar_only_mode)
            self.assertEqual(save.call_count, 2)

    def test_highlight_and_selected_label_follow_the_selected_mode(self):
        cfg = AppConfig()
        fake_dpg = MagicMock()
        fake_dpg.does_item_exist.return_value = True
        fake_dpg.is_item_active.return_value = False
        with (
            patch.object(dashboard, "CFG", cfg),
            patch.object(dashboard, "dpg", fake_dpg),
            patch.object(dashboard, "_mode_button_themes", {}),
            patch.object(
                dashboard, "build_button_theme", side_effect=[101, 202]
            ) as build,
        ):
            dashboard._refresh_fishing_mode_controls()
            themes = {
                c.args[0]: c.args[1] for c in fake_dpg.bind_item_theme.call_args_list
            }
            self.assertEqual(themes["btn_mode_normal"], 101)
            self.assertEqual(themes["btn_mode_bar_only"], 202)
            labels = {
                c.args[0]: c.kwargs["label"]
                for c in fake_dpg.configure_item.call_args_list
            }
            self.assertIn("selected", labels["btn_mode_normal"])
            self.assertNotIn("selected", labels["btn_mode_bar_only"])
            cfg.bar_only_mode = True
            fake_dpg.reset_mock()
            dashboard._refresh_fishing_mode_controls()
            themes = {
                c.args[0]: c.args[1] for c in fake_dpg.bind_item_theme.call_args_list
            }
            self.assertEqual(themes["btn_mode_normal"], 202)
            self.assertEqual(themes["btn_mode_bar_only"], 101)
            self.assertEqual(build.call_count, 2)

    def test_mode_message_distinguishes_actual_running_and_pending_selection(self):
        set_language("ja")
        cfg = AppConfig()
        cfg.bar_only_mode = True
        status = BotStatus(is_running=True, is_stopped=False, bar_only_mode=False)
        with patch.object(dashboard, "CFG", cfg):
            self.assertEqual(
                dashboard._mode_status_message(status),
                "切り替え待ち：通常モード → バー検出のみモード",
            )
            status.bar_only_mode = True
            self.assertEqual(
                dashboard._mode_status_message(status),
                "実行中のモード：バー検出のみモード",
            )
            status.is_running = False
            self.assertIn("一時停止中", dashboard._mode_status_message(status))
            status.is_stopped = True
            self.assertEqual(
                dashboard._mode_status_message(status),
                "選択中のモード：バー検出のみモード",
            )

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
