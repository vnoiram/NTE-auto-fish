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

    def _make_struggling_bot(self, detections, threshold=2):
        bot = NTEFishingBot.__new__(NTEFishingBot)
        bot.cfg = AppConfig()
        bot.cfg.humanization.enabled = False
        bot.cfg.debug_mode = False
        bot.cfg.timing.lost_frames_threshold = threshold
        bot.sm = MagicMock()
        bot.sm.time_in_state = 0.0
        bot._roi_bar = {"width": 400, "height": 100}
        bot._scaled_min_area = 1
        bot._grab = MagicMock(return_value=object())
        bot.vision = MagicMock()
        bot.vision.to_hsv.return_value = object()
        # one (cursor, target) pair per frame; cursor is queried first
        flat = []
        for cursor, target in detections:
            flat += [(cursor, None), (target, None)]
        bot.vision.get_hsv_centroid_x.side_effect = flat
        bot.input = MagicMock()
        bot._stop_event = MagicMock()
        bot._bar_detected_in_struggle = False
        bot._battle_visible = False
        bot._battle_absent_frames = 0
        bot._lost_frames = 0
        bot._lost_cursor_frames = 0
        bot._lost_target_frames = 0
        bot._cursor_x_rel = None
        bot._target_x_rel = None
        bot._last_pid_out = 0.0
        bot._log = MagicMock()
        bot.pid = MagicMock()
        bot.pid.update.return_value = 0.0
        bot._hum_target_action = "NONE"
        bot._hum_reaction_end = 0.0
        bot._last_action = "NONE"
        bot._hum_pulse_state = "IDLE"
        return bot

    def test_struggling_returns_to_waiting_if_no_bar_was_ever_seen(self):
        bot = self._make_struggling_bot([(None, None), (None, None)])
        bot._enter_waiting = MagicMock()

        bot._handle_struggling()
        bot._enter_waiting.assert_not_called()
        bot._handle_struggling()

        self.assertFalse(bot._bar_detected_in_struggle)
        bot._enter_waiting.assert_called_once_with()

    def test_struggling_stays_while_any_selected_bar_is_visible(self):
        # only the cursor is visible for many frames: no transition at all
        bot = self._make_struggling_bot([(100, None)] * 5)
        for _ in range(5):
            bot._handle_struggling()
        bot.sm.transition.assert_not_called()
        self.assertTrue(bot._bar_detected_in_struggle)

    def test_struggling_ignores_bar_that_is_not_selected(self):
        bot = self._make_struggling_bot([(100, None), (100, None)])
        bot.cfg.battle_detect_cursor = False
        bot.cfg.battle_detect_safe_zone = True
        bot._enter_waiting = MagicMock()
        bot._handle_struggling()
        bot._handle_struggling()
        bot._enter_waiting.assert_called_once_with()

    def test_struggling_goes_to_result_after_bars_disappear(self):
        bot = self._make_struggling_bot([(100, 150), (None, None), (None, None)])
        bot._handle_struggling()
        bot._handle_struggling()
        bot.sm.transition.assert_not_called()
        bot._handle_struggling()
        bot.sm.transition.assert_called_once_with(FishingState.RESULT)

    def test_max_struggle_does_not_end_battle_while_bars_visible(self):
        bot = self._make_struggling_bot([(100, 150), (100, 150)])
        bot._handle_struggling()
        bot.sm.time_in_state = bot.cfg.timing.max_struggle_secs + 1
        bot._handle_struggling()
        bot.sm.transition.assert_not_called()


class TestSpamCast(unittest.TestCase):
    def _make_bot(self, error):
        bot = NTEFishingBot.__new__(NTEFishingBot)
        bot.cfg = AppConfig()
        bot.cfg.humanization.enabled = False
        bot.cfg.spam_cast_enabled = True
        bot._next_spam_at = 0.0
        bot._roi_error = {"width": 1}
        bot._scaled_error_white_min = 1
        bot._grab = MagicMock(return_value=object())
        bot.vision = MagicMock()
        bot.vision.check_error_region.return_value = error
        bot.input = MagicMock()
        bot._stop_event = MagicMock()
        bot._log = MagicMock()
        bot.request_stop = MagicMock()
        bot._push_status = MagicMock()
        return bot

    def test_disabled_does_not_press(self):
        bot = self._make_bot(False)
        bot.cfg.spam_cast_enabled = False
        self.assertFalse(bot._spam_cast_if_due())
        bot.input.press.assert_not_called()

    def test_presses_then_waits_for_next_interval(self):
        bot = self._make_bot(False)
        self.assertFalse(bot._spam_cast_if_due())
        self.assertEqual(bot.input.press.call_count, 1)
        self.assertFalse(bot._spam_cast_if_due())
        self.assertEqual(bot.input.press.call_count, 1)

    def test_stops_when_bait_is_exhausted(self):
        bot = self._make_bot(True)
        self.assertTrue(bot._spam_cast_if_due())
        bot.request_stop.assert_called_once_with()

    def test_waiting_enters_fight_when_bars_visible_while_spamming(self):
        bot = TestFishingDetection()._make_waiting_bot(False)
        bot.cfg.spam_cast_enabled = True
        bot._roi_bar = {"width": 100, "height": 100}
        bot._scaled_min_area = 1
        bot.vision.get_hsv_centroid_x.return_value = (50, 0.0)
        bot._handle_waiting()
        bot._enter_struggling.assert_called_once_with(press_hook=False)


class TestProfileSwitching(unittest.TestCase):
    def _bot(self, signature, auto=True):
        from modules.profiles import default_profiles

        bot = NTEFishingBot.__new__(NTEFishingBot)
        bot.cfg = AppConfig()
        bot.cfg.profile_auto_switch = auto
        bot.cfg.profiles = default_profiles()
        bot.cfg.active_profile = "Day"
        bot._current_scale = 1.0
        bot._scaled_blue_pixels = 300
        bot._log = MagicMock()
        bot._background = MagicMock(samples=5)
        bot._background.signature.return_value = signature
        return bot

    def test_switches_to_closest_profile(self):
        from modules.profiles import default_profiles

        evening = default_profiles()[1]
        evening["min_blue_pixels"] = 120
        bot = self._bot(evening["signature"])
        bot.cfg.profiles[1]["min_blue_pixels"] = 120
        bot._maybe_switch_profile()
        self.assertEqual(bot.cfg.active_profile, "Evening")
        self.assertEqual(bot._scaled_blue_pixels, 120)

    def test_disabled_does_nothing(self):
        from modules.profiles import default_profiles

        bot = self._bot(default_profiles()[1]["signature"], auto=False)
        bot._maybe_switch_profile()
        self.assertEqual(bot.cfg.active_profile, "Day")


class TestGaugeAssistStep(unittest.TestCase):
    def _bot(self):
        from modules.calibration import GaugeAssist

        bot = NTEFishingBot.__new__(NTEFishingBot)
        bot.cfg = AppConfig()
        bot.sm = MagicMock()
        bot.sm.time_in_state = 0.1
        bot._assist = GaugeAssist()
        bot._assist_done = False
        bot._background = None
        bot.bridge = None
        return bot

    def test_records_once_per_fight(self):
        import numpy as np

        img = np.full((40, 400, 3), 20, np.uint8)
        img[:, 140:260] = (200, 230, 40)  # greenish-cyan (BGR) bar
        img[:, 198:202] = (60, 220, 255)  # yellow line
        bot = self._bot()
        bot._gauge_assist_step(img, 200, 200)
        bot._gauge_assist_step(img, 200, 200)
        self.assertEqual(bot._assist.samples, 1)
        self.assertTrue(bot._assist_done)

    def test_miss_is_counted_after_window(self):
        import numpy as np

        bot = self._bot()
        bot.sm.time_in_state = 5.0
        bot._gauge_assist_step(np.full((40, 400, 3), 20, np.uint8), None, None)
        self.assertEqual(bot._assist.misses, 1)

    def test_disabled_does_nothing(self):
        import numpy as np

        bot = self._bot()
        bot.cfg.gauge_assist_enabled = False
        bot._gauge_assist_step(np.zeros((10, 10, 3), np.uint8), None, None)
        self.assertEqual(bot._assist.samples, 0)


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
