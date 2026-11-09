"""Compatibility smoke tests for the Dear PyGui version pinned by the app."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import dearpygui.dearpygui as dpg

from gui.bridge import BotBridge
from gui.i18n import set_language
from gui.pages.dashboard import create_dashboard
from gui.pages.logs import create_logs
from gui.pages.settings import create_settings
from gui.sidebar import create_sidebar
from gui.theme import build_global_theme


class TestDearPyGuiCompatibility(unittest.TestCase):
    def test_full_ui_builds_with_current_dearpygui_api(self):
        bridge = BotBridge()
        monitor = SimpleNamespace(is_primary=True, width=1920, height=1080)

        set_language("ja")
        dpg.create_context()
        try:
            dpg.bind_theme(build_global_theme())
            with patch("gui.pages.settings.get_monitors", return_value=[monitor]):
                with dpg.window(tag="PrimaryWindow"):
                    with dpg.group(horizontal=True):
                        create_sidebar(lambda _page: None)
                        with dpg.child_window(tag="pages"):
                            with dpg.child_window(tag="page_dashboard"):
                                create_dashboard(bridge)
                            with dpg.child_window(tag="page_settings"):
                                create_settings(bridge)
                            with dpg.child_window(tag="page_logs"):
                                create_logs(bridge)

            self.assertTrue(dpg.does_item_exist("PrimaryWindow"))
            self.assertTrue(dpg.does_item_exist("pid_plot"))
            self.assertTrue(dpg.does_item_exist("btn_save"))
            self.assertTrue(dpg.does_item_exist("cfg_timing_key_press"))
            self.assertTrue(dpg.does_item_exist("cfg_hum_flick_chance"))
            self.assertTrue(dpg.does_item_exist("cfg_hum_db_battle_chance"))
            self.assertTrue(dpg.does_item_exist("cfg_hum_random_action_chance"))
            self.assertTrue(dpg.does_item_exist("cfg_hum_timing_scale_min"))
            self.assertTrue(dpg.does_item_exist("cfg_hum_timing_extra_chance"))
            self.assertTrue(dpg.does_item_exist("cfg_hum_timing_extra_max"))
            self.assertTrue(dpg.does_item_exist("cfg_hum_hook_dist"))
            self.assertTrue(dpg.does_item_exist("log_container"))
            self.assertEqual(
                dpg.get_item_configuration("btn_save")["label"],
                "設定を保存",
            )
            self.assertEqual(
                dpg.get_item_configuration("cfg_language")["items"],
                ["English", "日本語"],
            )
        finally:
            dpg.destroy_context()
            set_language("en")


if __name__ == "__main__":
    unittest.main()
