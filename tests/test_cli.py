import unittest
from unittest.mock import patch

from config import AppConfig, ensure_settings_loaded
from modules import cli


class TestCliParsing(unittest.TestCase):
    def test_parse_value_types(self):
        self.assertIs(cli._parse_value("yes", True), True)
        self.assertEqual(cli._parse_value("3", 1), 3)
        self.assertEqual(cli._parse_value("0.5", 1.0), 0.5)
        self.assertEqual(cli._parse_value("(1, 2, 3)", (0, 0, 0)), (1, 2, 3))
        self.assertEqual(cli._parse_value("x", "a"), "x")

    def test_config_set_rejects_out_of_range_hsv(self):
        with patch.object(cli, "CFG", AppConfig()) as cfg, patch.object(cfg, "save") as save:
            cli._cmd_config_set(type("A", (), {"key": "hsv.blue.lower", "value": "0,0,999"})())
            self.assertEqual(cfg.hsv.blue.lower, AppConfig().hsv.blue.lower)
            save.assert_not_called()

    def test_config_set_rejects_negative_number(self):
        with patch.object(cli, "CFG", AppConfig()) as cfg, patch.object(cfg, "save") as save:
            cli._cmd_config_set(type("A", (), {"key": "pid.max_dt", "value": "-1"})())
            self.assertEqual(cfg.pid.max_dt, AppConfig().pid.max_dt)
            save.assert_not_called()

    def test_config_set_accepts_valid_value(self):
        with patch.object(cli, "CFG", AppConfig()) as cfg, patch.object(cfg, "save") as save:
            cli._cmd_config_set(type("A", (), {"key": "pid.kp", "value": "0.7"})())
            self.assertEqual(cfg.pid.kp, 0.7)
            save.assert_called_once()

    def test_run_cli_dispatches_start(self):
        created = []

        class FakeBot:
            def __init__(self):
                created.append(self)
                self.calls = []

            def calibrate(self):
                self.calls.append("calibrate")

            def run(self):
                self.calls.append("run")

        cli.run_cli(FakeBot, ["start"])
        self.assertEqual(created[0].calls, ["calibrate", "run"])


class TestLazySettings(unittest.TestCase):
    def test_import_does_not_load_settings_until_requested(self):
        import config
        with patch.object(config, "_settings_loaded", False), patch.object(config.CFG, "load") as load:
            ensure_settings_loaded()
            ensure_settings_loaded()
            load.assert_called_once()


if __name__ == "__main__":
    unittest.main()
