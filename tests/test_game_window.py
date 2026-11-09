import unittest
from types import SimpleNamespace
from unittest.mock import patch

import modules.game_window as gw
from modules.game_window import auto_select_monitor, pick_monitor_index

MONS = [SimpleNamespace(x=0, y=0), SimpleNamespace(x=1920, y=0)]


class TestGameWindow(unittest.TestCase):
    def test_pick_matches_origin(self):
        self.assertEqual(pick_monitor_index(MONS, (1920, 0, 3840, 1080)), 1)
        self.assertIsNone(pick_monitor_index(MONS, (5, 5, 10, 10)))
        self.assertIsNone(pick_monitor_index(MONS, None))

    def test_auto_select_respects_flag(self):
        cfg = SimpleNamespace(monitor_index=0, monitor_auto_select=False)
        self.assertFalse(auto_select_monitor(cfg))
        self.assertEqual(cfg.monitor_index, 0)

    def test_auto_select_sets_index(self):
        import screeninfo

        cfg = SimpleNamespace(monitor_index=0, monitor_auto_select=True)
        with (
            patch.object(
                gw, "find_game_monitor_rect", return_value=(1920, 0, 3840, 1080)
            ),
            patch.object(screeninfo, "get_monitors", return_value=MONS),
        ):
            self.assertTrue(auto_select_monitor(cfg))
        self.assertEqual(cfg.monitor_index, 1)


if __name__ == "__main__":
    unittest.main()
