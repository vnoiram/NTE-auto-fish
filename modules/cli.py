"""Command-line interface for NTE Auto-Fish (headless mode)."""

import argparse
import ctypes
import json
import logging
from collections.abc import Callable
from dataclasses import asdict

from config import (
    _INVALID,
    CFG,
    DEFAULT_SETTINGS_PATH,
    HsvRange,
    _coerce_setting,
    _validate_hsv_triplet,
)

log = logging.getLogger("NTEFish")

# Set by run_cli(); keeps this module independent of main.py (no circular import).
_bot_factory: Callable = None  # type: ignore[assignment]


def attach_console() -> None:
    """Give a windowed (no-console) Windows executable usable stdout/stderr/stdin.

    Attaches to the parent console when possible; otherwise opens a new console
    window (e.g. when the elevated executable was started from a normal shell).
    """
    import sys

    if sys.platform != "win32":
        return
    kernel32 = ctypes.windll.kernel32
    attach_parent_process = -1
    if not kernel32.AttachConsole(attach_parent_process):
        if not kernel32.AllocConsole():
            return
    sys.stdin = open("CONIN$", encoding="utf-8")  # noqa: SIM115
    sys.stdout = open("CONOUT$", "w", encoding="utf-8")  # noqa: SIM115
    sys.stderr = open("CONOUT$", "w", encoding="utf-8")  # noqa: SIM115


def _set_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        log.debug(
            "SetProcessDpiAwareness failed; trying SetProcessDPIAware.", exc_info=True
        )
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            log.debug("SetProcessDPIAware failed.", exc_info=True)


# ---------------------------------------------------------------------------
# CLI command handlers
# ---------------------------------------------------------------------------


def _cmd_start(_args: argparse.Namespace) -> None:
    bot = _bot_factory()
    bot.calibrate()
    bot.run()


def _cmd_calibrate(_args: argparse.Namespace) -> None:
    bot = _bot_factory()
    bot.calibrate()
    print(f"Button ROI: {bot._roi_button}")
    print(f"Bar ROI:    {bot._roi_bar}")
    if bot._roi_error:
        print(f"Error ROI:  {bot._roi_error}")
    print("Calibration complete.")


def _cmd_reset(_args: argparse.Namespace) -> None:
    CFG.reset()
    print(f"Configuration reset to defaults: {DEFAULT_SETTINGS_PATH}")


def _cmd_config_show(args: argparse.Namespace) -> None:
    data = asdict(CFG)
    section = getattr(args, "section", None)
    if section:
        parts = section.split(".")
        obj = data
        for p in parts:
            if isinstance(obj, dict) and p in obj:
                obj = obj[p]
            else:
                print(f"Unknown config path: {section}")
                return
        print(
            json.dumps(
                {parts[-1]: obj},
                indent=4,
                ensure_ascii=False,
            )
        )
    else:
        print(json.dumps(data, indent=4, ensure_ascii=False))


def _resolve_cfg_path(path: str):
    """Walk the CFG dataclass by dot-separated path. Returns (parent, attr, current_value)."""
    parts = path.split(".")
    obj = CFG
    for p in parts[:-1]:
        if not hasattr(obj, p):
            return None, None, None
        child = getattr(obj, p)
        if hasattr(child, "__dataclass_fields__"):
            obj = child
        else:
            return None, None, None
    attr = parts[-1]
    if not hasattr(obj, attr):
        return None, None, None
    return obj, attr, getattr(obj, attr)


def _parse_value(raw: str, target):
    """Convert a string value to match the target's type."""
    if isinstance(target, bool):
        return raw.lower() in ("true", "1", "yes")
    if isinstance(target, tuple):
        return tuple(int(x.strip()) for x in raw.strip("() ").split(","))
    if isinstance(target, int):
        return int(raw)
    if isinstance(target, float):
        return float(raw)
    return raw


def _cmd_config_set(args: argparse.Namespace) -> None:
    parent, attr, current = _resolve_cfg_path(args.key)
    if parent is None:
        print(f"Unknown config key: {args.key}")
        return
    try:
        new_val = _parse_value(args.value, current)
    except (ValueError, TypeError) as exc:
        print(f"Invalid value '{args.value}' for {args.key}: {exc}")
        return
    if isinstance(parent, HsvRange):
        new_val = _validate_hsv_triplet(attr, new_val)
    else:
        new_val = _coerce_setting(current, new_val)
    if new_val is _INVALID:
        print(
            f"Value '{args.value}' is out of range or has the wrong type for {args.key}."
        )
        return
    setattr(parent, attr, new_val)
    CFG.save()
    print(f"{args.key} = {new_val!r}")


def _interactive_menu() -> None:
    while True:
        print()
        print("=== NTE Auto-Fish ===")
        print("1. Start fishing bot")
        print("2. Calibrate (show ROI results)")
        print("3. Show configuration")
        print("4. Edit configuration")
        print("5. Reset configuration to defaults")
        print("0. Exit")
        choice = input("\nSelect [0-5]: ").strip()

        if choice == "1":
            _cmd_start(argparse.Namespace())
            break
        elif choice == "2":
            _cmd_calibrate(argparse.Namespace())
        elif choice == "3":
            _cmd_config_show(argparse.Namespace(section=None))
        elif choice == "4":
            _interactive_edit_config()
        elif choice == "5":
            confirm = input("Reset all settings to defaults? [y/N]: ").strip().lower()
            if confirm == "y":
                _cmd_reset(argparse.Namespace())
        elif choice == "0":
            print("Bye.")
            break
        else:
            print("Invalid choice.")


def _interactive_edit_config() -> None:
    categories = [
        (
            "PID parameters",
            [
                ("pid.kp", "Proportional gain"),
                ("pid.ki", "Integral gain"),
                ("pid.kd", "Derivative gain"),
                ("pid.integral_limit", "Integral limit"),
                ("pid.deadband", "Deadband"),
                ("pid.adaptive", "Adaptive (true/false)"),
                ("pid.ema_alpha", "EMA alpha"),
                ("pid.max_dt", "Max dt"),
            ],
        ),
        (
            "HSV thresholds",
            [
                ("hsv.blue.lower", "Blue lower (H,S,V)"),
                ("hsv.blue.upper", "Blue upper (H,S,V)"),
                ("hsv.safe_zone.lower", "Safe zone lower (H,S,V)"),
                ("hsv.safe_zone.upper", "Safe zone upper (H,S,V)"),
                ("hsv.cursor.lower", "Cursor lower (H,S,V)"),
                ("hsv.cursor.upper", "Cursor upper (H,S,V)"),
            ],
        ),
        (
            "Key bindings",
            [
                ("keys.cast", "Cast key"),
                ("keys.left", "Left key"),
                ("keys.right", "Right key"),
                ("keys.exit", "Exit key"),
            ],
        ),
        (
            "Timing",
            [
                ("timing.cast_animation_secs", "Cast animation (s)"),
                ("timing.bite_timeout_secs", "Bite timeout (s)"),
                ("timing.lost_frames_threshold", "Lost frames threshold"),
                ("timing.result_wait_secs", "Result wait (s)"),
                ("timing.key_press_duration", "Key press duration (s)"),
            ],
        ),
        (
            "Humanization",
            [
                ("humanization.enabled", "Enabled (true/false)"),
                (
                    "humanization.mouse_move_curve_amplitude",
                    "Mouse curve amplitude (px)",
                ),
                ("humanization.mouse_move_duration_min", "Mouse move duration min (s)"),
                ("humanization.mouse_move_duration_max", "Mouse move duration max (s)"),
                ("humanization.mouse_offset_x", "Mouse click offset X (px)"),
                ("humanization.mouse_offset_y", "Mouse click offset Y (px)"),
                ("humanization.hook_reaction_min", "Hook reaction delay min (s)"),
                ("humanization.hook_reaction_max", "Hook reaction delay max (s)"),
                ("humanization.pulse_hold_min", "Pulse hold min (s)"),
                ("humanization.pulse_hold_max", "Pulse hold max (s)"),
                ("humanization.pulse_release_min", "Pulse release min (s)"),
                ("humanization.pulse_release_max", "Pulse release max (s)"),
                ("humanization.reaction_latency_min", "Struggle reaction min (s)"),
                ("humanization.reaction_latency_max", "Struggle reaction max (s)"),
                ("humanization.pid_noise_enabled", "PID noise (true/false)"),
                ("humanization.pid_noise_amplitude", "PID noise amplitude (px)"),
                ("humanization.adaptive_enabled", "Adaptive focus (true/false)"),
            ],
        ),
        (
            "Other",
            [
                ("min_blue_pixels", "Min blue pixels"),
                ("result_close_method", "Result close (click/esc)"),
                ("debug_mode", "Debug mode (true/false)"),
            ],
        ),
    ]

    while True:
        print()
        print("--- Edit Configuration ---")
        for i, (name, _) in enumerate(categories, 1):
            print(f"  {i}. {name}")
        print("  0. Back")
        cat_choice = input("\nSelect category [0-5]: ").strip()
        if cat_choice == "0":
            return
        try:
            idx = int(cat_choice) - 1
            cat_name, fields = categories[idx]
        except (ValueError, IndexError):
            print("Invalid choice.")
            continue

        while True:
            print(f"\n--- {cat_name} ---")
            for i, (key, desc) in enumerate(fields, 1):
                _, _, val = _resolve_cfg_path(key)
                print(f"  {i}. {desc} ({key}) = {val!r}")
            print("  0. Back")
            field_choice = input(
                f"\nSelect field to edit [0, 1-{len(fields)}]: "
            ).strip()
            if field_choice == "0":
                break
            try:
                fi = int(field_choice) - 1
                key, desc = fields[fi]
            except (ValueError, IndexError):
                print("Invalid choice.")
                continue
            _, _, current = _resolve_cfg_path(key)
            new_val = input(f"  New value for {desc} (current: {current!r}): ").strip()
            if not new_val:
                print("  Cancelled.")
                continue
            _cmd_config_set(argparse.Namespace(key=key, value=new_val))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="NTE-Auto-Fish",
        description="NTE Auto-Fishing bot — headless/CLI mode",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("start", help="Run the fishing bot")
    sub.add_parser("calibrate", help="Calibrate and show ROI results")
    sub.add_parser("reset", help="Reset the active build's settings file to defaults")

    cfg_parser = sub.add_parser("config", help="View or edit configuration")
    cfg_sub = cfg_parser.add_subparsers(dest="config_action")

    show_parser = cfg_sub.add_parser("show", help="Show current configuration")
    show_parser.add_argument(
        "section", nargs="?", default=None, help="Dot path to show (e.g. pid, hsv.blue)"
    )

    set_parser = cfg_sub.add_parser("set", help="Set a config value")
    set_parser.add_argument("key", help="Dot path, e.g. pid.kp")
    set_parser.add_argument("value", help="New value")
    parser._config_parser = cfg_parser  # type: ignore[attr-defined]
    return parser


def run_cli(bot_factory: Callable, argv=None) -> None:
    """Parse *argv* and dispatch the matching command."""
    global _bot_factory
    _bot_factory = bot_factory
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        _interactive_menu()
    elif args.command == "start":
        _cmd_start(args)
    elif args.command == "calibrate":
        _cmd_calibrate(args)
    elif args.command == "reset":
        _cmd_reset(args)
    elif args.command == "config":
        if args.config_action == "show":
            _cmd_config_show(args)
        elif args.config_action == "set":
            _cmd_config_set(args)
        else:
            parser._config_parser.print_help()  # type: ignore[attr-defined]
    else:
        parser.print_help()
