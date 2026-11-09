import sys
import unittest
from unittest.mock import MagicMock

from config import AppConfig
from modules.logic import FishingState

sys.modules.setdefault("pydirectinput", MagicMock())

from main import NTEFishingBot


class TestFishingDetection(unittest.TestCase):
    def _make_bot(self, cursor_x, target_x):
        bot = NTEFishingBot.__new__(NTEFishingBot)
        bot.cfg = AppConfig()
        bot.sm = MagicMock()
        bot.sm.state = FishingState.WAITING
        bot._roi_bar = {"width": 400, "height": 100}
        bot._scaled_min_area = 1
        bot._grab = MagicMock(return_value=object())
        bot.vision = MagicMock()
        bot.vision.to_hsv.return_value = object()
        bot.vision.get_hsv_centroid_x.side_effect = [
            (cursor_x, None),
            (target_x, None),
        ]
        bot._log = MagicMock()
        bot._enter_struggling = MagicMock()
        bot._push_status = MagicMock()
        bot._handle_waiting = MagicMock()
        return bot

    def test_tick_does_not_enter_struggling_when_only_one_bar_element_is_detected(self):
        for cursor_x, target_x in ((100, None), (None, 200)):
            with self.subTest(cursor_x=cursor_x, target_x=target_x):
                bot = self._make_bot(cursor_x, target_x)

                bot._tick()

                bot._enter_struggling.assert_not_called()
                bot._handle_waiting.assert_called_once_with()

    def test_tick_enters_struggling_when_cursor_and_target_are_detected(self):
        bot = self._make_bot(100, 200)

        bot._tick()

        bot._enter_struggling.assert_called_once_with()
        bot._push_status.assert_called_once_with()
        bot._handle_waiting.assert_not_called()

    def test_struggling_returns_to_waiting_without_a_complete_bar(self):
        bot = NTEFishingBot.__new__(NTEFishingBot)
        bot.cfg = AppConfig()
        bot.cfg.humanization.enabled = False
        bot.cfg.debug_mode = False
        bot.cfg.timing.lost_frames_threshold = 2
        bot.sm = MagicMock()
        bot.sm.time_in_state = 0.0
        bot._roi_bar = {"width": 400, "height": 100}
        bot._scaled_min_area = 1
        bot._grab = MagicMock(return_value=object())
        bot.vision = MagicMock()
        bot.vision.to_hsv.return_value = object()
        bot.vision.get_hsv_centroid_x.side_effect = [
            (100, None),
            (None, None),
            (None, None),
            (200, None),
        ]
        bot.input = MagicMock()
        bot._stop_event = MagicMock()
        bot._bar_detected_in_struggle = False
        bot._lost_frames = 0
        bot._lost_cursor_frames = 0
        bot._lost_target_frames = 0
        bot._cursor_x_rel = None
        bot._target_x_rel = None
        bot._last_pid_out = 0.0
        bot._log = MagicMock()

        bot._handle_struggling()
        bot.sm.transition.assert_not_called()

        bot._handle_struggling()

        self.assertFalse(bot._bar_detected_in_struggle)
        self.assertEqual(bot._lost_frames, 2)
        bot.input.release_all.assert_called()
        bot.sm.transition.assert_called_once_with(FishingState.WAITING)


if __name__ == "__main__":
    unittest.main()
