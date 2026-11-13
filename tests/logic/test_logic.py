import unittest
from unittest.mock import patch

from modules.logic import FishingState, FishingStateMachine, PIDController


class TestPIDController(unittest.TestCase):
    def test_pid_output_direction_matches_error_direction(self):
        pid = PIDController(kp=0.5, ki=0.0, kd=0.0, adaptive=False)

        right_output = pid.update(current=20.0, target=50.0, bar_half_width=100.0)
        left_output = pid.update(current=50.0, target=20.0, bar_half_width=100.0)

        self.assertGreater(right_output, 0.0)
        self.assertLess(left_output, 0.0)

    def test_reset_clears_internal_state(self):
        pid = PIDController(kp=0.5, ki=0.2, kd=0.1, adaptive=True)
        pid.update(current=10.0, target=40.0, bar_half_width=100.0)
        pid.update(current=15.0, target=40.0, bar_half_width=100.0)

        pid.reset()

        self.assertEqual(pid._integral, 0.0)  # internal state contract
        self.assertTrue(pid._first_call)
        self.assertEqual(pid._adaptive_kp_scale, 1.0)


class TestFishingStateMachine(unittest.TestCase):
    def test_repeated_pause_and_resume_do_not_double_count_paused_time(self):
        clock = [0.0]
        with patch("modules.logic.time.perf_counter", side_effect=lambda: clock[0]):
            sm = FishingStateMachine()
            clock[0] = 2.0
            sm.pause()
            clock[0] = 7.0
            sm.pause()
            self.assertEqual(sm.time_in_state, 2.0)
            clock[0] = 10.0
            sm.resume()
            clock[0] = 12.0
            sm.resume()
            self.assertEqual(sm.time_in_state, 4.0)

    def test_changing_state_while_paused_does_not_start_its_timeout(self):
        clock = [0.0]
        with patch("modules.logic.time.perf_counter", side_effect=lambda: clock[0]):
            sm = FishingStateMachine()
            clock[0] = 2.0
            sm.pause()
            clock[0] = 30.0
            sm.transition(FishingState.WAITING)
            self.assertEqual(sm.time_in_state, 0.0)
            sm.resume()
            clock[0] = 31.0
            self.assertEqual(sm.time_in_state, 1.0)

    def test_transition_changes_state(self):
        sm = FishingStateMachine()
        self.assertEqual(sm.state, FishingState.IDLE)

        sm.transition(FishingState.WAITING)
        self.assertEqual(sm.state, FishingState.WAITING)

        sm.transition(FishingState.STRUGGLING)
        self.assertEqual(sm.state, FishingState.STRUGGLING)


if __name__ == "__main__":
    unittest.main()
