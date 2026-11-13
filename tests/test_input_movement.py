import sys
import unittest
from unittest.mock import MagicMock, patch

sys.modules.setdefault("pydirectinput", MagicMock())

from modules.io_module import InputModule


class TestSmoothMouseMovement(unittest.TestCase):
    @patch("modules.io_module.pydirectinput")
    def test_progresses_over_the_full_duration_and_finishes_at_target(self, backend):
        backend.position.return_value = (0, 0)
        clock = [0.0]
        event = MagicMock()
        event.is_set.return_value = False

        def wait(timeout):
            clock[0] += timeout
            return False

        event.wait.side_effect = wait
        with patch("modules.io_module.time.monotonic", side_effect=lambda: clock[0]):
            reached = InputModule().smooth_move(600, 300, 2.0, stop_event=event)
        self.assertTrue(reached)
        self.assertAlmostEqual(clock[0], 2.0)
        points = [c.args for c in backend.moveTo.call_args_list]
        self.assertGreater(len(points), 60)
        self.assertLess(points[0][0], 100)
        self.assertEqual(points[-1], (600, 300))
        self.assertTrue(all(a[0] <= b[0] for a, b in zip(points, points[1:])))
        backend.click.assert_not_called()

    @patch("modules.io_module.pydirectinput")
    def test_stop_interrupts_the_trajectory(self, backend):
        backend.position.return_value = (0, 0)
        event = MagicMock()
        event.is_set.return_value = False
        event.wait.side_effect = [False, True]
        self.assertFalse(InputModule().smooth_move(600, 300, 2.0, stop_event=event))
        self.assertEqual(backend.moveTo.call_count, 1)
        backend.click.assert_not_called()

    @patch("modules.io_module.pydirectinput")
    def test_zero_duration_moves_once_to_exact_target(self, backend):
        backend.position.return_value = (0, 0)
        self.assertTrue(InputModule().smooth_move(-400, 200, 0.0))
        backend.moveTo.assert_called_once_with(-400, 200)
