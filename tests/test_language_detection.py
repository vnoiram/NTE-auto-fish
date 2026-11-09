import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import config
from config import AppConfig, detect_system_language
from gui import theme


class TestDetectSystemLanguage(unittest.TestCase):
    def test_windows_japanese_ui_language(self):
        fake = SimpleNamespace(
            windll=SimpleNamespace(
                kernel32=SimpleNamespace(GetUserDefaultUILanguage=lambda: 0x0411)
            )
        )
        with patch.object(config.sys, "platform", "win32"), patch.dict(
            "sys.modules", {"ctypes": fake}
        ):
            self.assertEqual(detect_system_language(), "ja")

    def test_windows_english_ui_language(self):
        fake = SimpleNamespace(
            windll=SimpleNamespace(
                kernel32=SimpleNamespace(GetUserDefaultUILanguage=lambda: 0x0409)
            )
        )
        with patch.object(config.sys, "platform", "win32"), patch.dict(
            "sys.modules", {"ctypes": fake}
        ):
            self.assertEqual(detect_system_language(), "en")

    def test_posix_environment(self):
        with patch.object(config.sys, "platform", "linux"), patch.dict(
            os.environ, {"LC_ALL": "", "LC_MESSAGES": "", "LANG": "ja_JP.UTF-8"}
        ):
            self.assertEqual(detect_system_language(), "ja")
        with patch.object(config.sys, "platform", "linux"), patch.dict(
            os.environ, {"LC_ALL": "", "LC_MESSAGES": "", "LANG": "en_US.UTF-8"}
        ), patch.object(config.locale, "getlocale", return_value=("en_US", "UTF-8")):
            self.assertEqual(detect_system_language(), "en")


class TestFirstLaunchLanguage(unittest.TestCase):
    def _run(self, saved_language):
        cfg = AppConfig()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "s.json")
            if saved_language is not None:
                tmp_cfg = AppConfig()
                tmp_cfg.language = saved_language
                tmp_cfg.save(path)
            cfg.load(path)
        return cfg

    def test_load_reports_whether_a_language_was_saved(self):
        self.assertFalse(self._run(None).language_from_file)
        self.assertTrue(self._run("en").language_from_file)

    def test_ensure_settings_loaded_follows_the_os_without_a_saved_language(self):
        with patch.object(config, "CFG", AppConfig()), patch.object(
            config, "_settings_loaded", False
        ), patch.object(config, "detect_system_language", return_value="ja"), patch.object(
            config.AppConfig, "load", lambda self, path=None: setattr(self, "language_from_file", False)
        ):
            config.ensure_settings_loaded()
            self.assertEqual(config.CFG.language, "ja")

    def test_a_saved_language_wins_over_the_os(self):
        cfg = AppConfig()

        def fake_load(self, path=None):
            self.language = "en"
            self.language_from_file = True

        with patch.object(config, "CFG", cfg), patch.object(
            config, "_settings_loaded", False
        ), patch.object(config, "detect_system_language", return_value="ja"), patch.object(
            config.AppConfig, "load", fake_load
        ):
            config.ensure_settings_loaded()
            self.assertEqual(cfg.language, "en")


class TestFont(unittest.TestCase):
    def test_a_japanese_capable_font_is_used_for_every_language(self):
        with patch.object(theme.os.path, "exists", side_effect=lambda p: "meiryo" in p):
            self.assertIn("meiryo", theme.get_font_path("en"))
            self.assertIn("meiryo", theme.get_font_path("ja"))

    def test_falls_back_to_the_latin_font_when_none_is_installed(self):
        with patch.object(theme.os.path, "exists", return_value=False):
            self.assertEqual(theme.get_font_path("en"), theme._FONT_PATH)


if __name__ == "__main__":
    unittest.main()
