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

    def _make_tick_bot(self, state, cursor, target):
        bot = self._make_waiting_bot(False)
        bot.sm.state = state
        bot._roi_bar = {"width": 100, "height": 100}
        bot._scaled_min_area = 1
        bot.vision.get_hsv_centroid_x.side_effect = [(cursor, 0.0), (target, 0.0)] * 3
        bot._push_status = MagicMock()
        bot._handle_waiting = MagicMock()
        bot._handle_idle = MagicMock()
        bot._handle_result = MagicMock()
        return bot

    def test_tick_enters_struggling_when_all_selected_bars_are_visible(self):
        for state in (FishingState.IDLE, FishingState.WAITING, FishingState.RESULT):
            bot = self._make_tick_bot(state, 100, 150)
            for _ in range(3):
                bot._tick()
            bot._enter_struggling.assert_called_once_with(press_hook=False)

    def test_tick_needs_consecutive_frames_before_entering(self):
        bot = self._make_tick_bot(FishingState.IDLE, 100, 150)
        bot._tick()
        bot._tick()
        bot._enter_struggling.assert_not_called()

    def test_battle_bars_take_priority_over_the_bite_prompt(self):
        bot = self._make_tick_bot(FishingState.WAITING, 100, 150)
        bot.vision.check_blue_trigger.return_value = True
        for _ in range(3):
            bot._tick()
        bot._enter_struggling.assert_called_once_with(press_hook=False)

    def test_bite_prompt_still_hooks_when_no_bars_are_visible(self):
        bot = self._make_tick_bot(FishingState.WAITING, None, None)
        bot._handle_waiting = MagicMock()
        bot._tick()
        bot._handle_waiting.assert_called_once_with()

    def test_tick_needs_every_selected_bar_to_enter(self):
        bot = self._make_tick_bot(FishingState.WAITING, 100, None)
        for _ in range(3):
            bot._tick()
        bot._enter_struggling.assert_not_called()

    def test_tick_enters_with_only_the_selected_bar(self):
        bot = self._make_tick_bot(FishingState.WAITING, 100, None)
        bot.cfg.battle_detect_safe_zone = False
        for _ in range(3):
            bot._tick()
        bot._enter_struggling.assert_called_once_with(press_hook=False)

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

    def test_max_struggle_still_ends_a_never_ending_false_match(self):
        bot = self._make_struggling_bot([(100, 150)])
        bot.sm.time_in_state = bot.cfg.timing.max_struggle_secs * 2 + 1
        bot._battle_visible = True
        bot._handle_struggling()
        bot.sm.transition.assert_called_once_with(FishingState.RESULT)


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
        bot._spam_cast_if_due()
        bot.input.press.assert_not_called()

    def test_presses_then_waits_for_next_interval(self):
        bot = self._make_bot(False)
        bot._spam_cast_if_due()
        self.assertEqual(bot.input.press.call_count, 1)
        bot._spam_cast_if_due()
        self.assertEqual(bot.input.press.call_count, 1)


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


class TestRoiOffsets(unittest.TestCase):
    def _bot(self):
        bot = NTEFishingBot.__new__(NTEFishingBot)
        bot.cfg = AppConfig()
        bot._log = MagicMock()
        bot._roi_bar_default = {"left": 100, "top": 50, "width": 1000, "height": 60}
        bot._roi_button_default = {
            "left": 3000,
            "top": 1700,
            "width": 400,
            "height": 300,
        }
        bot._roi_offsets_applied = None
        bot._screen_w, bot._screen_h = 3840, 2160
        bot._mon_x = bot._mon_y = 0
        return bot

    def test_offsets_shift_and_resize_areas(self):
        bot = self._bot()
        bot.cfg.roi.bar_offset_y = -20
        bot.cfg.roi.bar_width_delta = 50
        bot.cfg.roi.button_offset_x = 15
        bot._apply_roi_offsets()
        self.assertEqual(
            bot._roi_bar, {"left": 100, "top": 30, "width": 1050, "height": 60}
        )
        self.assertEqual(bot._roi_button["left"], 3015)

    def test_saved_drag_areas_replace_the_defaults(self):
        bot = self._bot()
        bot._screen_w, bot._screen_h = 2000, 1000
        bot._mon_x = bot._mon_y = 0
        bot.cfg.bar_roi_ratios = (0.25, 0.1, 0.75, 0.2)
        bot.cfg.button_roi_ratios = (0.9, 0.8, 1.0, 1.0)
        bot._apply_roi_offsets()
        self.assertEqual(
            bot._roi_bar, {"left": 500, "top": 100, "width": 1000, "height": 100}
        )
        self.assertEqual(
            bot._roi_button, {"left": 1800, "top": 800, "width": 200, "height": 200}
        )

    def test_zero_offsets_keep_base_and_negative_values_load(self):
        import os
        import tempfile

        bot = self._bot()
        bot._apply_roi_offsets()
        self.assertEqual(bot._roi_bar["top"], 50)
        cfg = AppConfig()
        cfg.roi.bar_offset_y = -35
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "s.json")
            cfg.save(path)
            loaded = AppConfig()
            loaded.load(path)
        self.assertEqual(loaded.roi.bar_offset_y, -35)


class TestBaitErrorDetectionOption(unittest.TestCase):
    def test_idle_skips_the_icon_check_when_disabled(self):
        bot = NTEFishingBot.__new__(NTEFishingBot)
        bot.cfg = AppConfig()
        bot.cfg.humanization.enabled = False
        bot.cfg.bait_error_detection_enabled = False
        bot.cfg.timing.cast_animation_secs = 0.0
        bot.input = MagicMock()
        bot._log = MagicMock()
        bot._stop_event = MagicMock()
        bot._stop_flag = False
        bot._roi_icon = {"width": 10}
        bot._grab = MagicMock()
        bot.vision = MagicMock()
        bot._enter_waiting = MagicMock()
        bot._handle_idle()
        bot._grab.assert_not_called()
        bot._enter_waiting.assert_called_once_with()


class TestJudgeText(unittest.TestCase):
    def test_text_shows_used_bars_and_detections(self):
        bot = NTEFishingBot.__new__(NTEFishingBot)
        bot.cfg = AppConfig()
        bot.cfg.battle_detect_safe_zone = False
        bot.sm = MagicMock()
        bot.sm.state = FishingState.WAITING
        text = bot._judge_text(120, None, "streak 1")
        self.assertIn("WAITING", text)
        self.assertIn("cursor found", text)
        self.assertIn("safe zone -", text)
        self.assertIn("used for battle: cursor", text)
        self.assertNotIn("cursor + safe zone", text)
        self.assertIn("streak 1", text)


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


class StartDelayTest(unittest.TestCase):
    def test_wait_start_delay_uses_the_configured_range_once(self):
        from unittest.mock import MagicMock, patch

        from config import AppConfig

        bot = NTEFishingBot.__new__(NTEFishingBot)
        bot.cfg = AppConfig()
        bot._stop_event = MagicMock()
        bot._log = MagicMock()
        with patch("main.random.uniform", return_value=2.0) as uni:
            bot._wait_start_delay()
        uni.assert_called_once_with(1.4, 2.6)
        bot._stop_event.wait.assert_called_once_with(timeout=2.0)


class RunLimitTest(unittest.TestCase):
    def _bot(self):
        bot = NTEFishingBot.__new__(NTEFishingBot)
        bot.cfg = AppConfig()
        bot.bridge = MagicMock()
        bot._fish_count = 5
        bot._active_secs = 100.0
        bot._fish_limit_target = None
        bot._time_limit_until = None
        bot._time_limit_notified = False
        bot.sm = MagicMock()
        bot.sm.state = FishingState.IDLE
        bot._log = MagicMock()
        bot._push_status = MagicMock()
        bot.request_stop = MagicMock()
        return bot

    def test_request_counts_from_now(self):
        bot = self._bot()
        bot.bridge.limit_request = (3, 120)
        bot._apply_limit_request()
        self.assertEqual(bot._fish_limit_target, 8)
        self.assertEqual(bot._time_limit_until, 220.0)
        self.assertIsNone(bot.bridge.limit_request)

    def test_zero_clears(self):
        bot = self._bot()
        bot._fish_limit_target, bot._time_limit_until = 9, 500.0
        bot.bridge.limit_request = (0, 0)
        bot._apply_limit_request()
        self.assertIsNone(bot._fish_limit_target)
        self.assertIsNone(bot._time_limit_until)

    def test_time_limit_stops_the_bot(self):
        bot = self._bot()
        bot._time_limit_until = 100.0
        self.assertTrue(bot._run_time_limit_reached())
        bot.request_stop.assert_called_once_with("Run time limit reached")

    def test_time_limit_waits_for_the_fish_in_progress(self):
        bot = self._bot()
        bot._time_limit_until = 100.0
        for state in (
            FishingState.WAITING,
            FishingState.STRUGGLING,
            FishingState.RESULT,
        ):
            bot.sm.state = state
            self.assertFalse(bot._run_time_limit_reached())
        bot.request_stop.assert_not_called()
        bot.sm.state = FishingState.IDLE
        self.assertTrue(bot._run_time_limit_reached())

    def test_no_limit_or_not_yet_reached(self):
        bot = self._bot()
        self.assertFalse(bot._run_time_limit_reached())
        bot._time_limit_until = 101.0
        self.assertFalse(bot._run_time_limit_reached())


class MonitorChangeResumeTest(unittest.TestCase):
    def test_resume_recalibrates_when_the_monitor_changed(self):
        bot = NTEFishingBot.__new__(NTEFishingBot)
        bot.cfg = AppConfig()
        bot.cfg.monitor_index = 1
        bot._calibrated_monitor = 0
        bot._is_stopped = False
        bot._is_paused = True
        bot._stop_flag = False
        bot._start_delay_pending = False
        bot._bait_error_count = 0
        bot._session_manager = MagicMock()
        bot._log = MagicMock()
        bot.calibrate = MagicMock()
        bot._handle_command("resume")
        bot.calibrate.assert_called_once()
        self.assertFalse(bot._is_paused)

    def test_resume_skips_calibration_when_unchanged(self):
        bot = NTEFishingBot.__new__(NTEFishingBot)
        bot.cfg = AppConfig()
        bot._calibrated_monitor = bot.cfg.monitor_index
        bot._is_stopped = False
        bot._is_paused = True
        bot._stop_flag = False
        bot._start_delay_pending = False
        bot._bait_error_count = 0
        bot._session_manager = MagicMock()
        bot._log = MagicMock()
        bot.calibrate = MagicMock()
        bot._handle_command("resume")
        bot.calibrate.assert_not_called()
