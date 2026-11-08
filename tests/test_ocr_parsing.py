import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np

from modules.ocr import CatchOcr, clean_fish_name, parse_weight, ratios_to_roi


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

    def test_read_region_uses_rapidocr_3_result_object(self):
        capture = Mock()
        capture.grab_bgr.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        ocr = CatchOcr()
        ocr._engine = Mock(return_value=SimpleNamespace(txts=("Golden", "Carp")))

        self.assertEqual(ocr._read_region(capture, {}), "Golden Carp")


if __name__ == "__main__":
    unittest.main()
