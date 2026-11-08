import unittest

from modules.ocr import clean_fish_name, parse_weight, ratios_to_roi


class TestOcrParsing(unittest.TestCase):
    def test_clean_fish_name_strips_symbols_and_collapses_spaces(self):
        self.assertEqual(clean_fish_name("  Gold|en   Carp! "), "Gold en Carp")

    def test_clean_fish_name_keeps_apostrophe_and_hyphen(self):
        self.assertEqual(clean_fish_name("King's Eel-Fish"), "King's Eel-Fish")

    def test_parse_weight_takes_first_number(self):
        self.assertEqual(parse_weight("Weight 1250 g (2)"), "1250")
        self.assertEqual(parse_weight("no digits"), "")

    def test_ratios_to_roi(self):
        roi = ratios_to_roi((0.5, 0.25, 0.75, 0.5), 1000, 800, 100, 50)
        self.assertEqual(roi, {"left": 600, "top": 250, "width": 250, "height": 200})


if __name__ == "__main__":
    unittest.main()
