import unittest

from gui.i18n import (
    get_language,
    language_from_label,
    language_label,
    set_language,
    tr,
)


class TestI18n(unittest.TestCase):
    def tearDown(self):
        set_language("en")

    def test_english_is_default(self):
        set_language("en")
        self.assertEqual(get_language(), "en")
        self.assertEqual(tr("Save Settings"), "Save Settings")

    def test_japanese_translation_and_formatting(self):
        set_language("ja")
        self.assertEqual(tr("Save Settings"), "設定を保存")
        self.assertEqual(tr("{count} fish", count=3), "3 匹")

    def test_unknown_language_falls_back_to_english(self):
        self.assertEqual(set_language("unknown"), "en")
        self.assertEqual(tr("Settings"), "Settings")

    def test_language_labels_round_trip(self):
        self.assertEqual(language_label("ja"), "日本語")
        self.assertEqual(language_from_label("日本語"), "ja")
        self.assertEqual(language_from_label("unknown"), "en")


if __name__ == "__main__":
    unittest.main()
