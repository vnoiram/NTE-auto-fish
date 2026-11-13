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
        bot._roi_bar = None
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

    def test_result_recovers_with_one_bar_without_losing_confirmation_streak(self):
        bot = self._make_tick_bot(FishingState.RESULT, None, 150)
        for _ in range(3):
            bot._tick()
        bot._enter_struggling.assert_called_once_with(press_hook=False)
        bot._handle_result.assert_not_called()

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

    def test_visible_bars_block_lower_priority_actions_while_confirming(self):
        for state in (FishingState.IDLE, FishingState.WAITING, FishingState.RESULT):
            with self.subTest(state=state):
                bot = self._make_tick_bot(state, 100, 150)
                bot.vision.check_blue_trigger.return_value = True
                bot._tick()
                bot._tick()
                bot._enter_struggling.assert_not_called()
                bot.vision.check_blue_trigger.assert_not_called()
                bot._handle_idle.assert_not_called()
                bot._handle_waiting.assert_not_called()
                bot._handle_result.assert_not_called()
                bot.sm.transition.assert_not_called()

    def test_bite_overrides_idle_and_result_states(self):
        for state in (FishingState.IDLE, FishingState.RESULT):
            with self.subTest(state=state):
                bot = self._make_tick_bot(state, None, None)
                bot._bait_error_count = 4
                bot.vision.check_blue_trigger.return_value = True
                bot._tick()
                bot._enter_struggling.assert_called_once_with()
                bot._handle_idle.assert_not_called()
                bot._handle_result.assert_not_called()

    def test_no_detection_preserves_state_and_runs_its_handler(self):
        for state, handler in (
            (FishingState.IDLE, "_handle_idle"),
            (FishingState.WAITING, "_handle_waiting"),
            (FishingState.RESULT, "_handle_result"),
        ):
            with self.subTest(state=state):
                bot = self._make_tick_bot(state, None, None)
                bot._tick()
                getattr(bot, handler).assert_called_once_with()
                bot.sm.transition.assert_not_called()

    def test_bite_overrides_waiting_timeout(self):
        bot = self._make_waiting_bot(True)
        bot.sm.time_in_state = 100.0
        bot._handle_waiting()
        bot._enter_struggling.assert_called_once_with()
        bot.sm.transition.assert_not_called()

    def test_waiting_handler_checks_bars_before_bite(self):
        bot = self._make_tick_bot(FishingState.WAITING, 100, 150)
        bot.vision.check_blue_trigger.return_value = True
        for _ in range(3):
            NTEFishingBot._handle_waiting(bot)
        bot._enter_struggling.assert_called_once_with(press_hook=False)
        bot.vision.check_blue_trigger.assert_not_called()

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
            bounds = (target - 20, target + 20) if target is not None else None
            flat += [(cursor, None), (target, None, bounds)]
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

    def test_safe_zone_needs_no_centering_even_with_noise_and_taps_enabled(self):
        for humanized in (False, True):
            for cursor in (130, 135, 150, 165, 170):
                with self.subTest(humanized=humanized, cursor=cursor):
                    bot = self._make_struggling_bot([(cursor, 150)])
                    bot.cfg.humanization.enabled = humanized
                    bot.pid.update.return_value = 100.0
                    bot._last_action = "RIGHT"
                    bot._hum_pulse_state = "HOLD"
                    bot._hum_reaction_end = float("inf")
                    bot._handle_struggling()
                    bot.input.hold.assert_not_called()
                    bot.input.pulse_hold.assert_not_called()
                    bot.input.release.assert_any_call(bot.cfg.keys.left)
                    bot.input.release.assert_any_call(bot.cfg.keys.right)
                    bot.pid.update.assert_not_called()
                    bot.pid.reset.assert_called_once_with()
                    self.assertEqual(bot._last_action, "NONE")
                    self.assertEqual(bot._hum_pulse_state, "IDLE")

    def test_far_outside_zone_holds_direction_across_expired_pulses(self):
        for cursor, action in ((50, "RIGHT"), (250, "LEFT")):
            for humanized in (False, True):
                with self.subTest(cursor=cursor, humanized=humanized):
                    bot = self._make_struggling_bot([(cursor, 150)] * 4)
                    bot.cfg.humanization.enabled = humanized
                    bot._hum_pulse_state = "GAP"
                    bot._hum_pulse_end = 0.0
                    # Even PID overshoot/noise cannot send recovery the wrong way.
                    bot.pid.update.return_value = -999.0 if action == "RIGHT" else 999.0
                    key = bot.cfg.keys.right if action == "RIGHT" else bot.cfg.keys.left
                    for _ in range(4):
                        bot._handle_struggling()
                    self.assertEqual(bot.input.hold.call_count, 4)
                    bot.input.hold.assert_called_with(key)
                    self.assertNotIn(
                        (key,), [c.args for c in bot.input.release.call_args_list]
                    )
                    bot.input.pulse_hold.assert_not_called()
                    self.assertEqual(bot._last_action, action)

    def test_entering_safe_zone_immediately_releases_recovery_hold(self):
        bot = self._make_struggling_bot([(50, 150), (135, 150)])
        bot.cfg.humanization.enabled = True
        bot._handle_struggling()
        bot.input.hold.assert_called_once_with(bot.cfg.keys.right)
        bot.input.reset_mock()
        bot._handle_struggling()
        bot.input.hold.assert_not_called()
        bot.input.pulse_hold.assert_not_called()
        bot.input.release.assert_any_call(bot.cfg.keys.right)
        self.assertEqual(bot._last_action, "NONE")

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

    def test_default_icon_area_moves_left_by_twenty_five_pixels(self):
        bot = self._bot()
        bot._apply_roi_offsets()
        shifted = dict(bot._roi_icon)
        bot.cfg.roi.icon_offset_x = 0
        bot._apply_roi_offsets()
        self.assertEqual(shifted["left"], bot._roi_icon["left"] - 25)
        for key in ("top", "width", "height"):
            self.assertEqual(shifted[key], bot._roi_icon[key])


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
        bot._detect_active_fishing = MagicMock(return_value=False)
        bot._handle_idle()
        bot._grab.assert_not_called()
        bot._enter_waiting.assert_called_once_with()


class TestCastFailurePriority(unittest.TestCase):
    def _bot(self):
        bot = NTEFishingBot.__new__(NTEFishingBot)
        bot.cfg = AppConfig()
        bot.cfg.humanization.enabled = False
        bot.sm = MagicMock()
        bot.sm.state = FishingState.IDLE
        bot.input = MagicMock()
        bot._stop_event = MagicMock()
        bot._stop_flag = False
        bot._log = MagicMock()
        bot._push_status = MagicMock()
        bot._bait_error_count = 0
        bot._icon_check_active = MagicMock(return_value=True)
        bot._count_action_icons = MagicMock(return_value=4)
        bot._detect_active_fishing = MagicMock(return_value=False)
        bot._enter_waiting = MagicMock()
        bot.request_stop = MagicMock()
        return bot

    def test_cast_failure_requires_at_least_four_icons_in_both_checks(self):
        for counts, failed in (
            ([3], False),
            ([4, 3], False),
            ([4, 4], True),
            ([5, 5], True),
        ):
            with self.subTest(counts=counts):
                bot = self._bot()
                bot._count_action_icons.side_effect = counts
                self.assertEqual(bot._cast_failed_by_icons(), failed)

    def test_post_cast_detection_prevents_failure(self):
        bot = self._bot()
        bot._detect_active_fishing.return_value = True
        bot._handle_idle()
        bot._count_action_icons.assert_not_called()
        self.assertEqual(bot._bait_error_count, 0)
        bot._enter_waiting.assert_not_called()

    def test_detection_during_icon_confirmation_prevents_failure(self):
        bot = self._bot()
        bot._detect_active_fishing.side_effect = [False, True]
        bot._handle_idle()
        self.assertEqual(bot._bait_error_count, 0)
        bot._enter_waiting.assert_not_called()
        bot.request_stop.assert_not_called()

    def test_bait_exhaustion_stops_on_fifth_failure(self):
        bot = self._bot()
        for _ in range(4):
            bot._handle_cast_failure("icons visible")
            bot.request_stop.assert_not_called()
        bot._handle_cast_failure("icons visible")
        self.assertEqual(bot._bait_error_count, 5)
        bot.request_stop.assert_called_once_with("Bait error limit reached")

    def test_detection_during_failure_wait_overrides_stop(self):
        bot = self._bot()
        bot._bait_error_count = 4
        bot._detect_active_fishing.return_value = True
        bot._handle_cast_failure("icons visible")
        bot.request_stop.assert_not_called()
        bot.sm.transition.assert_not_called()

    def test_bite_appearing_during_error_wait_interrupts_retry(self):
        bot = self._bot()
        bot._detect_active_fishing = NTEFishingBot._detect_active_fishing.__get__(bot)
        bot._scan_battle_bars = MagicMock(return_value=False)
        bot._detect_bite = MagicMock(side_effect=[False, False, True])
        bot._handle_cast_failure("terrain mistaken for icons")
        bot._scan_battle_bars.assert_called()
        self.assertEqual(bot._detect_bite.call_count, 3)
        bot._stop_event.wait.assert_called_once_with(
            timeout=bot.cfg.timing.waiting_poll_interval
        )
        bot.sm.transition.assert_not_called()
        bot.request_stop.assert_not_called()

    def test_bars_appearing_during_error_wait_take_priority_over_bite(self):
        bot = self._bot()
        bot._detect_active_fishing = NTEFishingBot._detect_active_fishing.__get__(bot)
        bot._scan_battle_bars = MagicMock(side_effect=[False, False, True])
        bot._detect_bite = MagicMock(return_value=False)
        bot._handle_cast_failure("terrain mistaken for icons")
        self.assertEqual(bot._detect_bite.call_count, 2)
        bot._stop_event.wait.assert_called_once_with(
            timeout=bot.cfg.timing.waiting_poll_interval
        )
        bot.sm.transition.assert_not_called()
        bot.request_stop.assert_not_called()

    def test_stop_during_error_wait_interrupts_polling(self):
        bot = self._bot()

        def stop_after_wait(**kwargs):
            bot._stop_flag = True

        bot._stop_event.wait.side_effect = stop_after_wait
        bot._handle_cast_failure("icons visible")
        bot._stop_event.wait.assert_called_once()
        bot.sm.transition.assert_not_called()
        bot.request_stop.assert_not_called()


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
        bot.sm = MagicMock()
        bot.pid = MagicMock()
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
        bot.sm = MagicMock()
        bot.pid = MagicMock()
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


class TestResultMouseMovement(unittest.TestCase):
    def _bot(self):
        bot = NTEFishingBot.__new__(NTEFishingBot)
        bot.cfg = AppConfig()
        bot.cfg.humanization.enabled = False
        bot.cfg.result_close_method = "click"
        bot.cfg.spam_cast_enabled = False
        bot._roi_error = None
        bot._roi_bar = {"width": 400, "height": 40}
        bot.vision = MagicMock()
        bot._screen_w, bot._screen_h = 1920, 1080
        bot._mon_x, bot._mon_y = -1920, 100
        bot._stop_flag = False
        bot._stop_event = MagicMock()
        bot.input = MagicMock()
        bot.input.smooth_move.return_value = True
        bot.sm = MagicMock()
        bot._grab = MagicMock()
        bot._find_cursor = MagicMock(return_value=(None, None))
        bot._find_target = MagicMock(return_value=(None, None))
        bot._count_action_icons = MagicMock(return_value=1)
        bot._ocr_catch_screen = MagicMock(return_value=(None, None))
        bot._publish_ocr_preview = MagicMock()
        bot._append_catch = MagicMock()
        bot._log = MagicMock()
        bot._fish_count = 0
        bot._fish_limit_target = None
        return bot

    def test_moves_during_wait_then_clicks_without_moving_again(self):
        bot = self._bot()
        bot._handle_result()
        bot.input.smooth_move.assert_called_once_with(
            -960, 910, duration=3.0, amp=0, stop_event=bot._stop_event
        )
        bot.input.click.assert_called_once_with()
        actions = [call[0] for call in bot.input.method_calls]
        self.assertLess(actions.index("smooth_move"), actions.index("click"))
        # The result wait is spent moving; only the post-click delay remains.
        bot._stop_event.wait.assert_called_once_with(timeout=0.5)
        bot.input.humanized_click.assert_not_called()

    def test_stop_during_movement_prevents_click_and_catch_count(self):
        bot = self._bot()
        bot.input.smooth_move.return_value = False
        bot._handle_result()
        bot.input.click.assert_not_called()
        bot._ocr_catch_screen.assert_not_called()
        self.assertEqual(bot._fish_count, 0)

    def test_active_battle_after_wait_prevents_click(self):
        bot = self._bot()
        bot._find_cursor.return_value = (100, None)
        bot._handle_result()
        bot.input.click.assert_not_called()
        self.assertEqual(bot._fish_count, 0)

    def test_keyboard_close_uses_the_wait_without_mouse_movement(self):
        bot = self._bot()
        bot.cfg.result_close_method = "key"
        bot._handle_result()
        bot.input.smooth_move.assert_not_called()
        bot.input.click.assert_not_called()
        bot.input.press.assert_called_once_with(
            bot.cfg.keys.exit, bot.cfg.timing.key_press_duration
        )

    def test_spam_cast_leaves_closing_to_the_cast_key(self):
        bot = self._bot()
        bot.cfg.spam_cast_enabled = True
        bot._handle_result()
        bot.input.smooth_move.assert_not_called()
        bot.input.click.assert_not_called()


class TestNormalCatchCount(unittest.TestCase):
    _bot = TestResultMouseMovement._bot

    def test_confirmation_occurs_before_either_close_method(self):
        for method in ("click", "key"):
            with self.subTest(method=method):
                bot = self._bot()
                bot.cfg.result_close_method = method
                events = []
                bot.input.smooth_move.side_effect = lambda *a, **k: (
                    events.append("move") or True
                )
                bot._count_action_icons.side_effect = lambda: (
                    events.append("icons") or 2
                )
                bot.input.click.side_effect = lambda: events.append("close")
                bot.input.press.side_effect = lambda *a: events.append("close")
                bot._handle_result()
                self.assertLess(events.index("icons"), events.index("close"))
                if method == "click":
                    self.assertLess(events.index("move"), events.index("icons"))
                self.assertEqual(bot._fish_count, 1)

    def test_bars_returning_during_retry_cancel_both_close_methods(self):
        for method in ("click", "key"):
            with self.subTest(method=method):
                bot = self._bot()
                bot.cfg.result_close_method = method
                bot._scan_battle_bars = MagicMock(side_effect=[False, True])
                bot._count_action_icons.side_effect = [0, 2]
                bot._stop_event.wait.return_value = False
                bot._handle_result()
                bot.input.click.assert_not_called()
                bot.input.press.assert_not_called()
                bot._count_action_icons.assert_called_once_with()
                self.assertEqual(bot._fish_count, 0)

    def test_unconfirmed_catch_is_closed_but_never_counted(self):
        bot = self._bot()
        bot._count_action_icons.return_value = 3
        bot._handle_result()
        self.assertEqual(bot._fish_count, 0)
        bot._ocr_catch_screen.assert_not_called()
        bot.input.click.assert_called_once_with()


class TestBattlePauseResume(unittest.TestCase):
    def _bot(self, detections):
        from modules.logic import FishingStateMachine

        bot = TestFishingDetection._make_struggling_bot(self, detections)
        bot.cfg.bar_only_mode = True
        bot.sm = FishingStateMachine()
        bot.sm.transition(FishingState.STRUGGLING)
        bot._is_paused = False
        bot._is_stopped = False
        bot._stop_flag = False
        bot._start_delay_pending = False
        bot._stop_event.is_set.return_value = False
        bot._stop_event.wait.return_value = False
        return bot

    def test_paused_time_does_not_expire_the_battle(self):
        clock = [10.0]
        with patch("main.time.perf_counter", side_effect=lambda: clock[0]):
            bot = self._bot([(50, 150)])
            clock[0] = 14.0
            bot._handle_command("pause")
            clock[0] = 314.0
            self.assertEqual(bot.sm.time_in_state, 4.0)
            bot._handle_command("resume")
            clock[0] = 315.0
            self.assertEqual(bot.sm.time_in_state, 5.0)
            bot._handle_struggling()
        self.assertEqual(bot.sm.state, FishingState.STRUGGLING)
        bot.input.hold.assert_called_with(bot.cfg.keys.right)

    def test_resuming_keeps_tracking_a_cursor_outside_safe_zone_at_screen_edge(self):
        import cv2
        import numpy as np

        from modules.vision import VisionModule

        bot = self._bot([(5, 150)])
        bot.vision = VisionModule()
        hsv = np.zeros((100, 400, 3), np.uint8)
        hsv[10:30, 130:171] = (85, 220, 220)
        hsv[10:30, 2:8] = (30, 130, 250)
        bot._grab.return_value = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        bot._cursor_x_rel = bot._cursor_last_seen = 5
        bot._target_x_rel = 150
        bot._handle_command("pause")
        bot._handle_command("resume")
        bot._handle_struggling()
        self.assertEqual(bot._cursor_x_rel, 5)
        bot.input.hold.assert_called_with(bot.cfg.keys.right)
        self.assertEqual(bot.sm.state, FishingState.STRUGGLING)

    def test_resuming_battle_does_not_schedule_a_cast_start_delay(self):
        bot = self._bot([(50, 150)])
        bot._handle_command("pause")
        bot._handle_command("resume")
        self.assertFalse(bot._start_delay_pending)
        self.assertEqual(bot.sm.state, FishingState.STRUGGLING)

    def test_released_key_is_pressed_again_on_the_first_tracking_frame(self):
        with patch("main.time.perf_counter", return_value=10.0):
            bot = self._bot([(125, 150)])
            hcfg = bot.cfg.humanization
            hcfg.enabled = True
            hcfg.pid_noise_enabled = False
            hcfg.reaction_latency_min = hcfg.reaction_latency_max = 0.0
            hcfg.random_action_chance = hcfg.slow_move_chance = 0.0
            bot.pid.update.return_value = 20.0
            bot._last_action = bot._hum_target_action = "RIGHT"
            bot._hum_pulse_state = "HOLD"
            bot._hum_pulse_end = 10.5
            bot._hum_reaction_end = 0.0
            bot._handle_command("pause")
            bot._handle_command("resume")
            bot.input.reset_mock()
            bot._handle_struggling()
        bot.input.hold.assert_called_once_with(bot.cfg.keys.right)
        bot.input.press.assert_not_called()
