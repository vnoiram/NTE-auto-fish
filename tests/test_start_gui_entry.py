import runpy
import sys
import unittest
from unittest.mock import patch


class TestStartGuiEntry(unittest.TestCase):
    def _run(self, argv):
        with (
            patch.object(sys, "argv", ["start_gui.py", *argv]),
            patch("modules.cli.attach_console") as attach,
            patch("main.run_headless") as headless,
        ):
            with self.assertRaises(SystemExit) as ctx:
                runpy.run_path("start_gui.py", run_name="__main__")
        return ctx.exception.code, attach, headless

    def test_arguments_run_the_cli(self):
        code, attach, headless = self._run(["config", "show", "pid"])
        self.assertEqual(code, 0)
        attach.assert_called_once()
        headless.assert_called_once_with(["config", "show", "pid"])

    def test_help_runs_the_cli(self):
        _, _, headless = self._run(["--help"])
        headless.assert_called_once_with(["--help"])


if __name__ == "__main__":
    unittest.main()
