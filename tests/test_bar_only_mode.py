import sys
import unittest
from unittest.mock import MagicMock, patch

from config import AppConfig
from modules.logic import FishingState, FishingStateMachine

sys.modules.setdefault("pydirectinput", MagicMock())

from main import NTEFishingBot


def make_bot():
    bot = NTEFishingBot.__new__(NTEFishingBot)
    bot.cfg = AppConfig()
    bot.cfg.bar_only_mode = True
    bot.cfg.humanization.enabled = False
    bot.sm = FishingStateMachine()
    bot._active_bar_only_mode = True
    bot._active_secs = 0.0
    bot._bar_only_wait_started = None
    bot._next_spam_at = 0.0
    bot._bait_error_count = 0
    bot._fish_count = 0
    bot._fish_limit_target = None
    bot._time_limit_until = None
    bot._time_limit_notified = False
    bot._stop_flag = False
    bot._stop_event = MagicMock()
    bot._stop_event.wait.return_value = False
    bot._stop_event.is_set.return_value = False
    bot.input = MagicMock()
    bot.pid = MagicMock()
    bot._log = MagicMock()
    bot._push_status = MagicMock()
    bot._apply_roi_offsets = MagicMock()
    bot._scan_battle_bars = MagicMock(return_value=False)
    bot._handle_struggling = MagicMock()
    bot._handle_idle = MagicMock()
    bot._handle_waiting = MagicMock()
    bot._handle_result = MagicMock()
    bot._detect_bite = MagicMock()
    bot._cast_failed_by_icons = MagicMock()
    bot._count_action_icons = MagicMock(return_value=1)
    bot._ocr_catch_screen = MagicMock(return_value=("Fish", "100"))
    bot._publish_ocr_preview = MagicMock()
    bot._append_catch = MagicMock()
    bot.request_stop = MagicMock()
    return bot


class TestBarOnlyMode(unittest.TestCase):
    def test_waiting_only_scans_bars_and_repeats_casts(self):
        bot = make_bot()
        bot._tick()
        bot.input.press.assert_called_once()
        bot._detect_bite.assert_not_called()
        bot._cast_failed_by_icons.assert_not_called()
        bot._count_action_icons.assert_not_called()
        bot._handle_idle.assert_not_called()
        bot._handle_waiting.assert_not_called()
        bot._handle_result.assert_not_called()
        self.assertFalse(bot.cfg.spam_cast_enabled)

    def test_real_bar_detection_and_battle_loop_return_to_casts(self):
        import cv2
        import numpy as np

        from modules.vision import VisionModule

        bot = make_bot()
        bot.vision = VisionModule()
        bot._scan_battle_bars = NTEFishingBot._scan_battle_bars.__get__(bot)
        bot._handle_struggling = NTEFishingBot._handle_struggling.__get__(bot)
        bot._roi_bar = {"width": 400, "height": 40}
        bot._scaled_min_area = 10
        bot._assist_done = True
        bot.cfg.timing.lost_frames_threshold = 2
        hsv = np.zeros((40, 400, 3), np.uint8)
        hsv[10:30, 100:200] = (85, 220, 220)
        hsv[10:30, 147:153] = (30, 130, 250)
        bars = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        blank = np.zeros_like(bars)
        bot._grab = MagicMock(side_effect=[bars] * 4 + [blank] * 4)
        for _ in range(3):
            bot._tick()
        self.assertEqual(bot.sm.state, FishingState.STRUGGLING)
        bot._tick()
        self.assertEqual(bot.sm.state, FishingState.STRUGGLING)
        bot.input.press.assert_not_called()
        bot._tick()
        self.assertEqual(bot._fish_count, 0)
        bot._tick()
        self.assertEqual(bot.sm.state, FishingState.IDLE)
        self.assertEqual(bot._fish_count, 1)
        bot._count_action_icons.assert_called_once_with()
        bot.input.press.assert_not_called()
        bot._tick()
        bot.input.press.assert_called_once()
        bot._detect_bite.assert_not_called()
        bot._cast_failed_by_icons.assert_not_called()
        bot._handle_result.assert_not_called()

    def test_pending_bar_confirmation_prevents_casts(self):
        bot = make_bot()
        bot._scan_battle_bars.return_value = True
        bot._tick()
        bot.input.press.assert_not_called()
        self.assertEqual(bot.sm.state, FishingState.IDLE)

    def test_battle_detection_takes_priority_over_expired_watchdog(self):
        bot = make_bot()
        bot._bar_only_wait_started = 0.0
        bot._active_secs = 200.0

        def detect(state):
            bot.sm.transition(FishingState.STRUGGLING)
            return True

        bot._scan_battle_bars.side_effect = detect
        bot._tick()
        self.assertIsNone(bot._bar_only_wait_started)
        bot.input.press.assert_not_called()
        bot.request_stop.assert_not_called()

    def test_no_bar_timeout_stops_without_counting_or_casting(self):
        bot = make_bot()
        bot.cfg.timing.bar_only_timeout_secs = 30.0
        bot._tick()
        bot.input.reset_mock()
        bot._active_secs = 30.0
        bot._tick()
        bot.request_stop.assert_called_once_with("Bait error: no battle bars detected")
        bot.input.press.assert_not_called()
        bot._count_action_icons.assert_not_called()
        self.assertEqual(bot._fish_count, 0)

    def test_confirmed_catch_is_counted_before_cast_repeats_resume(self):
        bot = make_bot()
        bot.sm.transition(FishingState.STRUGGLING)
        bot._handle_struggling.side_effect = lambda: bot.sm.transition(
            FishingState.RESULT
        )
        events = []
        bot._count_action_icons.side_effect = lambda: events.append("icons") or 2
        bot.input.press.side_effect = lambda *args: events.append("cast")
        bot._tick()
        self.assertEqual(events, ["icons"])
        self.assertEqual(bot._fish_count, 1)
        self.assertEqual(bot.sm.state, FishingState.IDLE)
        bot._ocr_catch_screen.assert_not_called()
        bot._handle_result.assert_not_called()
        bot.input.click.assert_not_called()
        bot._tick()
        self.assertEqual(events, ["icons", "cast"])
        self.assertEqual(bot._fish_count, 1)

    def test_multiple_battles_restart_watchdog_and_honor_fish_limit(self):
        bot = make_bot()
        bot._fish_limit_target = 2
        for count, now in enumerate((100.0, 230.0), 1):
            bot.sm.transition(FishingState.STRUGGLING)
            bot._active_secs = now
            bot._handle_struggling.side_effect = lambda: bot.sm.transition(
                FishingState.RESULT
            )
            bot._tick()
            self.assertEqual(bot._fish_count, count)
            self.assertEqual(bot._bar_only_wait_started, now)
            bot.input.press.assert_not_called()
            if count == 1:
                bot.request_stop.assert_not_called()
        bot.request_stop.assert_called_once_with("Fish count limit reached")

    def test_reappearing_bars_defer_catch_count_and_cast_restart(self):
        bot = make_bot()
        bot.sm.transition(FishingState.RESULT)
        bot._scan_battle_bars.return_value = True
        bot._tick()
        self.assertEqual(bot.sm.state, FishingState.RESULT)
        self.assertEqual(bot._fish_count, 0)
        bot._count_action_icons.assert_not_called()
        bot.input.press.assert_not_called()

    def test_one_reappearing_bar_recovers_battle_without_counting(self):
        bot = make_bot()
        bot.sm.transition(FishingState.RESULT)
        bot._scan_battle_bars = NTEFishingBot._scan_battle_bars.__get__(bot)
        bot._roi_bar = {"width": 400, "height": 40}
        bot._grab = MagicMock(return_value=object())
        bot.vision = MagicMock()
        bot._find_cursor = MagicMock(return_value=(None, 0.0))
        bot._find_target = MagicMock(return_value=(150, 100.0))
        for _ in range(3):
            bot._tick()
        self.assertEqual(bot.sm.state, FishingState.STRUGGLING)
        self.assertEqual(bot._fish_count, 0)
        bot._count_action_icons.assert_not_called()
        bot.input.press.assert_not_called()

    def test_reappearing_bars_during_zero_icon_retry_prevent_counting(self):
        bot = make_bot()
        bot.sm.transition(FishingState.RESULT)
        bot._count_action_icons.side_effect = [0, 1]
        bot._scan_battle_bars.side_effect = [False, True]
        bot._tick()
        self.assertEqual(bot.sm.state, FishingState.RESULT)
        self.assertEqual(bot._fish_count, 0)
        bot._count_action_icons.assert_called_once_with()
        bot.input.press.assert_not_called()

    def test_confirmed_catch_without_ocr_is_written_to_session_history(self):
        import tempfile

        from modules.session_manager import SessionManager

        bot = make_bot()
        bot.cfg.fish_logging_enabled = True
        bot._append_catch = NTEFishingBot._append_catch.__get__(bot)
        with tempfile.TemporaryDirectory() as folder:
            bot._session_manager = SessionManager(sessions_dir=folder)
            bot._session_manager.start_session()
            bot.sm.transition(FishingState.RESULT)
            bot._tick()
            try:
                self.assertEqual(bot._session_manager.active_fish_count(), 1)
                self.assertEqual(bot._fish_count, 1)
                bot._ocr_catch_screen.assert_not_called()
            finally:
                bot._session_manager.end_session()

    def test_failed_catch_still_resumes_casting_without_reaching_fish_limit(self):
        bot = make_bot()
        bot._fish_limit_target = 1
        bot._count_action_icons.return_value = 4
        bot.sm.transition(FishingState.RESULT)
        bot._tick()
        self.assertEqual(bot._fish_count, 0)
        bot.request_stop.assert_not_called()
        bot._tick()
        bot.input.press.assert_called_once()

    def test_elapsed_run_time_waits_for_battle_then_stops_before_cast(self):
        bot = make_bot()
        bot._active_secs = 60.0
        bot._time_limit_until = 60.0
        bot.sm.transition(FishingState.STRUGGLING)
        self.assertFalse(bot._run_time_limit_reached())
        bot._handle_struggling.side_effect = lambda: bot.sm.transition(
            FishingState.RESULT
        )
        bot._tick()
        self.assertTrue(bot._run_time_limit_reached())
        bot.request_stop.assert_called_once_with("Run time limit reached")
        bot.input.press.assert_not_called()
        self.assertEqual(bot._fish_count, 1)

    def test_switching_modes_keeps_an_ongoing_battle(self):
        bot = make_bot()
        bot.sm.transition(FishingState.STRUGGLING)
        bot.cfg.bar_only_mode = False
        bot._tick()
        bot._handle_struggling.assert_called_once_with()
        self.assertEqual(bot.sm.state, FishingState.STRUGGLING)
        bot.input.release_all.assert_not_called()
        self.assertFalse(bot._active_bar_only_mode)

    def test_mode_switch_after_battle_preserves_pending_catch_check(self):
        bot = make_bot()
        bot._active_bar_only_mode = False
        bot.sm.transition(FishingState.RESULT)
        bot._tick()
        bot._count_action_icons.assert_called_once_with()
        self.assertEqual(bot._fish_count, 1)
        bot.input.press.assert_not_called()

    def test_switching_to_bar_only_resets_normal_waiting_errors(self):
        bot = make_bot()
        bot._active_bar_only_mode = False
        bot.sm.transition(FishingState.WAITING)
        bot._bait_error_count = 4
        bot._bar_only_wait_started = -500.0
        bot._tick()
        self.assertEqual(bot._bait_error_count, 0)
        self.assertEqual(bot.sm.state, FishingState.IDLE)
        self.assertEqual(bot._bar_only_wait_started, 0.0)
        bot._handle_waiting.assert_not_called()
        bot.request_stop.assert_not_called()

    def test_random_cast_gap_is_measured_after_key_release(self):
        bot = make_bot()
        with (
            patch("main.time.perf_counter", side_effect=[10.0, 10.6, 11.0]),
            patch("main._RNG.uniform", side_effect=[0.8, 1.1]),
        ):
            bot._spam_cast_if_due(force=True)
            self.assertAlmostEqual(bot._next_spam_at, 11.4)
            bot._spam_cast_if_due(force=True)
        bot.input.press.assert_called_once()
        self.assertAlmostEqual(bot.input.press.call_args.args[1], 0.55 * 1.1)


class TestCatchConfirmation(unittest.TestCase):
    def test_one_or_two_icons_confirm_and_other_counts_do_not(self):
        for icons in (1, 2, 3, 4):
            with self.subTest(icons=icons):
                bot = make_bot()
                bot._count_action_icons.return_value = icons
                confirmed = bot._record_catch(read_details=False)
                self.assertEqual(confirmed, icons <= 2)
                self.assertEqual(bot._fish_count, int(icons <= 2))
                bot._stop_event.wait.assert_not_called()
                bot._ocr_catch_screen.assert_not_called()

    def test_rare_fish_effect_retries_zero_until_icons_appear(self):
        bot = make_bot()
        bot._count_action_icons.side_effect = [0, 0, 2]
        self.assertTrue(bot._record_catch(read_details=False))
        self.assertEqual(bot._count_action_icons.call_count, 3)
        self.assertEqual(bot._stop_event.wait.call_count, 2)
        self.assertEqual(bot._fish_count, 1)

    def test_zero_icons_stop_retrying_at_configured_deadline_without_counting(self):
        bot = make_bot()
        bot.cfg.timing.catch_icon_timeout_secs = 0.2
        bot._count_action_icons.return_value = 0
        elapsed = [0.0]

        def wait(timeout):
            elapsed[0] += timeout
            return False

        bot._stop_event.wait.side_effect = wait
        with patch("main.time.monotonic", side_effect=lambda: elapsed[0]):
            self.assertFalse(bot._record_catch(read_details=False))
        self.assertAlmostEqual(elapsed[0], 0.2)
        self.assertEqual(bot._fish_count, 0)
        bot._append_catch.assert_not_called()

    def test_stop_interrupts_zero_icon_retry(self):
        bot = make_bot()
        bot._count_action_icons.return_value = 0
        bot._stop_event.wait.return_value = True
        self.assertFalse(bot._record_catch(read_details=False))
        bot._count_action_icons.assert_called_once_with()
        self.assertEqual(bot._fish_count, 0)
