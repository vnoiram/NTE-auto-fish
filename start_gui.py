"""GUI entry point for NTE Auto-Fish.

Started with no arguments it opens the GUI. Started with any argument
(for example ``start``, ``calibrate``, ``config show`` or ``--help``) it runs
the command-line interface instead.
"""

import sys

if __name__ == "__main__":
    if len(sys.argv) > 1:
        from modules.cli import attach_console

        attach_console()
        from main import run_headless

        run_headless(sys.argv[1:])
        sys.exit(0)

from modules.deps import GUI_PACKAGES, exit_if_missing_dependencies

exit_if_missing_dependencies(GUI_PACKAGES)

from gui.app import FishingGUI

if __name__ == "__main__":
    app = FishingGUI()
    app.run()
