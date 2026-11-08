import json
import tempfile
import unittest
from pathlib import Path

from config import AppConfig


class TestAppConfig(unittest.TestCase):
    def test_save_and_load_roundtrip(self):
        cfg = AppConfig()
        cfg.pid.kp = 0.73
        cfg.hotkeys.toggle = "f9"

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            cfg.save(str(path))

            loaded = AppConfig()
            loaded.load(str(path))

        self.assertEqual(loaded.pid.kp, 0.73)
        self.assertEqual(loaded.hotkeys.toggle, "f9")

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


if __name__ == "__main__":
    unittest.main()
