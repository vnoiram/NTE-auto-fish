import sys
import unittest
from unittest.mock import MagicMock, patch

from config import AppConfig
from modules.logic import FishingState

sys.modules.setdefault("pydirectinput", MagicMock())

from main import NTEFishingBot


class TestFishingDetection(unittest.TestCase):
    def _make_waiting_bot(self, hooked):
        bot = NTEFishingBot.__new__(NTEFishingBot)
        bot.cfg = AppConfig()
        bot.cfg.humanization.enabled = False
        bot.sm = MagicMock()
        bot.sm.state = FishingState.WAITING
        bot.sm.time_in_state = 0.0
        bot._waiting_timeout_secs = 30.0
        bot._roi_button = {"width": 100, "height": 100}
        bot._scaled_blue_pixels = 1
        bot._grab = MagicMock(return_value=object())
        bot.vision = MagicMock()
        bot.vision.check_blue_trigger.return_value = hooked
        bot._log = MagicMock()
        bot._enter_struggling = MagicMock()
        bot._stop_event = MagicMock()
        return bot

    def test_waiting_enters_struggling_only_when_hit_is_detected(self):
        not_hooked = self._make_waiting_bot(False)
        hooked = self._make_waiting_bot(True)

        not_hooked._handle_waiting()
        hooked._handle_waiting()

        not_hooked._enter_struggling.assert_not_called()
        hooked._enter_struggling.assert_called_once_with()

    def test_tick_does_not_scan_bar_to_enter_struggling(self):
        bot = self._make_waiting_bot(False)
        bot._handle_waiting = MagicMock()

        bot._tick()

        bot._handle_waiting.assert_called_once_with()
        bot.vision.get_hsv_centroid_x.assert_not_called()
        bot._enter_struggling.assert_not_called()

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


class TestDeadbandPlaySelection(unittest.TestCase):
    def test_battle_gate_is_rolled_once_then_uses_existing_tap_chance(self):
        bot = NTEFishingBot.__new__(NTEFishingBot)
        bot.cfg = AppConfig()
        bot.cfg.humanization.enabled = True
        bot.cfg.humanization.deadband_tap_enabled = True
        bot.cfg.humanization.deadband_play_battle_chance = 0.5
        bot.cfg.humanization.deadband_tap_chance = 0.3

        with patch("main._RNG.random", side_effect=[0.4, 0.2, 0.4]) as random:
            bot._roll_deadband_play_for_battle()

            self.assertTrue(bot._hum_deadband_play_enabled)
            self.assertTrue(bot._should_send_deadband_tap())
            self.assertFalse(bot._should_send_deadband_tap())
            self.assertEqual(random.call_count, 3)

    def test_failed_battle_gate_disables_taps_for_the_whole_battle(self):
        bot = NTEFishingBot.__new__(NTEFishingBot)
        bot.cfg = AppConfig()
        bot.cfg.humanization.enabled = True
        bot.cfg.humanization.deadband_tap_enabled = True
        bot.cfg.humanization.deadband_play_battle_chance = 0.5

        with patch("main._RNG.random", return_value=0.8) as random:
            bot._roll_deadband_play_for_battle()

            self.assertFalse(bot._hum_deadband_play_enabled)
            self.assertFalse(bot._should_send_deadband_tap())
            self.assertFalse(bot._should_send_deadband_tap())
            random.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
