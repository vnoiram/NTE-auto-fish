import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from config import AppConfig, HumanizationConfig, sample_movement_pulse


class TestAppConfig(unittest.TestCase):
    def test_save_and_load_roundtrip(self):
        cfg = AppConfig()
        cfg.pid.kp = 0.73
        cfg.hotkeys.toggle = "f9"
        cfg.language = "ja"

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            cfg.save(str(path))

            loaded = AppConfig()
            loaded.load(str(path))

        self.assertEqual(loaded.pid.kp, 0.73)
        self.assertEqual(loaded.hotkeys.toggle, "f9")
        self.assertEqual(loaded.language, "ja")

    def test_load_invalid_json_keeps_existing_values(self):
        cfg = AppConfig()
        cfg.pid.kp = 0.91

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text("{invalid json", encoding="utf-8")
            cfg.load(str(path))

        self.assertEqual(cfg.pid.kp, 0.91)

    def test_save_outputs_valid_json(self):
        cfg = AppConfig()

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            cfg.save(str(path))
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertIn("pid", payload)
        self.assertIn("hsv", payload)

    def test_load_ignores_invalid_values(self):
        cfg = AppConfig()
        payload = {
            "pid": {"kp": "oops", "ki": -1, "kd": 0.01},
            "hsv": {"blue": {"lower": [0, 0, 999], "upper": [130, 255, 255]}},
            "debug_mode": "yes",
            "language": "unsupported",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            cfg.load(str(path))

        defaults = AppConfig()
        self.assertEqual(cfg.pid.kp, defaults.pid.kp)
        self.assertEqual(cfg.pid.ki, defaults.pid.ki)
        self.assertEqual(cfg.pid.kd, 0.01)
        self.assertEqual(cfg.hsv.blue.lower, defaults.hsv.blue.lower)
        self.assertEqual(cfg.hsv.blue.upper, (130, 255, 255))
        self.assertFalse(cfg.debug_mode)
        self.assertEqual(cfg.language, defaults.language)

    def test_flick_profile_is_only_sampled_when_direction_reverses(self):
        cfg = HumanizationConfig(flick_chance_on_reverse=1.0)
        reverse_rng = Mock()
        reverse_rng.random.side_effect = [0.0, 1.0, 0.0]
        reverse_rng.uniform.side_effect = [1.8, 0.02]

        with patch("config._RNG", reverse_rng):
            reverse_pulse = sample_movement_pulse(cfg, allow_flick=True)

        normal_rng = Mock()
        normal_rng.random.side_effect = [1.0, 1.0, 0.0]
        normal_rng.uniform.side_effect = [1.0, 0.02]
        with patch("config._RNG", normal_rng):
            normal_pulse = sample_movement_pulse(cfg, allow_flick=False)

        self.assertEqual(reverse_pulse.profile, "flick")
        self.assertEqual(reverse_pulse.hold_scale, 1.8)
        self.assertEqual(reverse_pulse.gap_scale, cfg.flick_gap_scale)
        self.assertEqual(normal_pulse.profile, "normal")

    def test_slow_profile_can_include_a_short_random_action(self):
        cfg = HumanizationConfig(slow_move_chance=1.0)
        rng = Mock()
        rng.random.side_effect = [0.0, 0.0, 0.8]
        rng.uniform.side_effect = [0.6, 0.02]

        with patch("config._RNG", rng):
            pulse = sample_movement_pulse(cfg, allow_flick=False)

        self.assertEqual(pulse.profile, "slow")
        self.assertTrue(pulse.random_action)
        self.assertEqual(pulse.random_direction, 1)


if __name__ == "__main__":
    unittest.main()
