"""Settings page — two-column category navigation with config panels."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from collections.abc import Callable

import dearpygui.dearpygui as dpg
from screeninfo import get_monitors

from config import (
    CFG,
    DEFAULT_BAR_RATIOS,
    DEFAULT_BUTTON_RATIOS,
    DEFAULT_ICON_RATIOS,
    ratios_are_set,
)
from gui.bridge import BotBridge
from gui.components import (
    apply_glass_card_theme,
    caption_text,
    hsv_editor,
    section_header,
    styled_button,
    update_hsv_preview,
)
from gui.i18n import LANGUAGE_LABELS, language_from_label, language_label, tr
from gui.theme import (
    ACCENT,
    CARD_GAP,
    TEXT_MUTED,
    TEXT_PRIMARY,
    build_settings_cat_theme,
)
from gui.theme import _ui_scale as _s
from modules.utils import VERSION

log = logging.getLogger("NTEFish")

# ---------------------------------------------------------------------------
# Category definitions
# ---------------------------------------------------------------------------

CATEGORIES = [
    ("pid", "PID Tuning"),
    ("vision", "Vision & Detection"),
    ("timing", "Timing"),
    ("input", "Input & Hotkeys"),
    ("humanization", "Humanization"),
    ("system", "System & Updates"),
]

_RESULT_METHODS = {
    "Click center": "click",
    "Press exit key": "key",
}

_LATEST_RELEASE_API_URL = (
    "https://api.github.com/repos/Chizukuo/NTE-auto-fish/releases/latest"
)
_LATEST_RELEASE_API_HOST = "api.github.com"


def _validated_update_api_url() -> str:
    parsed = urllib.parse.urlparse(_LATEST_RELEASE_API_URL)
    if parsed.scheme != "https" or parsed.hostname != _LATEST_RELEASE_API_HOST:
        raise ValueError("Unexpected update check endpoint")
    return _LATEST_RELEASE_API_URL


def _version_tuple(version: str) -> tuple:
    """Parse 'x.y.z' into a comparable tuple; non-numeric parts become 0."""
    parts = []
    for piece in version.split("-")[0].split("."):
        parts.append(int(piece) if piece.isdigit() else 0)
    return tuple(parts)


def _is_trusted_release_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme == "https" and parsed.hostname == "github.com"


_TOOLTIPS = {
    "Kp": "Proportional gain. Higher = stronger correction for large errors.",
    "Ki": "Integral gain. Eliminates steady-state offset over time.",
    "Kd": "Derivative gain. Dampens oscillation from rapid changes.",
    "Deadband": "Error range (pixels) where no correction is applied. Prevents jitter.",
    "Integral limit": "Clamps the integral term to prevent windup.",
    "Adaptive damping": "Automatically reduces Kp when oscillation is detected.",
    "Edge ignore ratio": "Fraction of bar edges to ignore when detecting cursor/target.",
    "Blue pixel trigger": "Minimum blue pixels in button ROI to detect a fish bite.",
    "Cast animation (s)": "Wait time after pressing cast key before checking for bite.",
    "Key press base (s)": "Base hold time for cast, hook, and exit key presses before timing variation.",
    "Bite timeout (s)": "Max seconds to wait for a bite before recasting.",
    "Lost frame limit": "Frames of lost tracking before ending the struggle phase.",
    "Result wait (s)": "Wait time after fish caught before closing the result dialog.",
    "Waiting poll (s)": "Interval between bite-detection checks.",
    "Tracking poll (s)": "Interval between cursor/target position updates.",
    "Bait error limit": "Consecutive cast errors before assuming bait is exhausted and stopping.",
    "Max struggle (s)": "Max seconds in the struggle phase before force-ending (safety timeout).",
    "Toggle": "Hotkey to pause/resume the bot (e.g. f8).",
    "Stop": "Hotkey to stop the bot (e.g. f12).",
    "Humanize input": "Add natural variation to timing and key behavior.",
    "Button hold min (s)": "Minimum W/A button hold duration during struggle.",
    "Button hold max (s)": "Maximum W/A button hold duration during struggle.",
    "Button released min (s)": "Minimum released time between W/A pulses.",
    "Button released max (s)": "Maximum released time between W/A pulses.",
    "Deadband taps": "Send micro-corrections when cursor is near center.",
    "Per-battle play chance": "At battle start, chance to enable center play for that entire fish battle.",
    "Tap chance": "Probability of a micro-tap per cycle in the deadband.",
    "Reaction min": "Minimum reaction delay before responding (seconds).",
    "Reaction max": "Maximum reaction delay before responding (seconds).",
    "Reaction dist": "Distribution: uniform (even), gaussian (clustered), exponential (mostly short).",
    "PID noise": "Add random noise to PID output for less predictable key timing.",
    "Noise amplitude": "Maximum noise magnitude added to PID output (pixels).",
    "Noise dist": "Noise distribution: uniform (flat) or gaussian (bell curve).",
    "Movement scale min": "Smallest multiplier for a normal key-hold pulse.",
    "Movement scale max": "Largest multiplier for a normal key-hold pulse.",
    "Slow move chance": "Chance of shorter holds and longer released gaps.",
    "Slow hold scale": "Multiplier applied to button hold time during slow movement.",
    "Slow gap scale": "Multiplier applied to button released time during slow movement.",
    "Reverse flick chance": (
        "Chance of a fast flick only when changing W/A direction."
    ),
    "Flick hold scale": "Multiplier applied to button hold time during a flick.",
    "Flick gap scale": "Multiplier applied to button released time after a flick.",
    "Random action chance": "Chance of inserting one very short left or right tap.",
    "Timing scale min": "Lowest multiplier applied to every humanized duration.",
    "Timing scale max": "Highest multiplier applied to every humanized duration.",
    "Extra delay chance": "Probability of adding an extra random delay to a humanized duration.",
    "Extra delay min (s)": "Minimum extra delay when the random addition occurs.",
    "Extra delay max (s)": "Maximum extra delay when the random addition occurs.",
    "Adaptive focus": "Speed up response and shorten pulse gaps when the fish is far away.",
    "Latency focus min": "Minimum latency multiplier when fish is at max distance (e.g. 0.3 = 70% reduction).",
    "Pulse gap focus min": "Minimum gap multiplier when fish is at max distance (e.g. 0.2 = 80% reduction).",
    "Pulse hold focus max": "Maximum hold multiplier when fish is at max distance (e.g. 1.5 = 50% increase).",
    "Detection threshold (px)": "Minimum area (pixels) to recognize the cursor or safe zone. This value is shown scaled for your current resolution.",
    "Move dur min (s)": "Minimum duration for mouse movements.",
    "Move dur max (s)": "Maximum duration for mouse movements.",
    "Click jitter X (px)": "Random horizontal offset for result screen clicks.",
    "Click jitter Y (px)": "Random vertical offset for result screen clicks.",
    "Hook reaction min": "Minimum reaction delay when a fish bites (seconds).",
    "Hook reaction max": "Maximum reaction delay when a fish bites (seconds).",
    "Hook reaction dist": "Distribution used to sample the initial hook reaction.",
}

# ---------------------------------------------------------------------------
# Module state
# ---------------------------------------------------------------------------

_active_category: str = "pid"
_settings_built: bool = False
_cat_tags: dict[str, dict] = {}  # {key: {"btn": tag, "indicator": tag, "group": tag}}
_update_check_results: queue.Queue[tuple[str, str]] = queue.Queue()

# Cached themes
_cat_active_theme: int | None = None
_cat_inactive_theme: int | None = None

_session_manager = None  # set via init_session_manager()
_last_known_active_id: str | None = None


def init_session_manager(mgr) -> None:
    """Called once at startup to give the settings page access to session data."""
    global _session_manager
    _session_manager = mgr


def _ensure_themes():
    global _cat_active_theme, _cat_inactive_theme
    if _cat_active_theme is None:
        _cat_active_theme = build_settings_cat_theme(active=True)
        _cat_inactive_theme = build_settings_cat_theme(active=False)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_settings(
    bridge: BotBridge,
    on_hotkeys_changed: Callable[[], None] | None = None,
):
    _ensure_themes()
    # Initial refresh
    # dpg.set_frame_callback(lambda: _refresh_values(bridge))

    with dpg.group(horizontal=True):
        # ── Left column: category list ──────────────────────────────────
        with dpg.child_window(
            width=int(200 * _s),
            height=-1,
            tag="settings_cat_list",
            border=True,
            no_scrollbar=True,
        ):
            apply_glass_card_theme("settings_cat_list")
            dpg.add_spacer(height=int(8 * _s))
            section_header("Categories", color=TEXT_MUTED)

            for key, label in CATEGORIES:
                _create_category_item(key, label)

        dpg.add_spacer(width=int(CARD_GAP * _s))

        # ── Right column: settings content ──────────────────────────────
        with dpg.child_window(
            width=-1,
            height=-1,
            tag="settings_content",
            border=True,
            no_scrollbar=False,
        ):
            apply_glass_card_theme("settings_content")

            _build_pid_settings()
            _build_vision_settings(bridge)
            _build_timing_settings()
            _build_input_settings(bridge, on_hotkeys_changed)
            _build_humanization_settings()
            _build_system_settings()

            dpg.add_spacer(height=int(20 * _s))

            # Save / Reset buttons
            with dpg.group(horizontal=True):
                styled_button(
                    "Save Settings",
                    "btn_save",
                    callback=lambda s, a, u: _save(bridge),
                    variant="primary",
                    width=int(140 * _s),
                    height=int(32 * _s),
                )
                dpg.add_spacer(width=int(12 * _s))
                styled_button(
                    "Reset to Defaults",
                    "btn_reset",
                    callback=lambda s, a, u: _on_reset(bridge, on_hotkeys_changed),
                    variant="neutral",
                    width=int(160 * _s),
                    height=int(32 * _s),
                )

    # Show only the active category
    _switch_category(_active_category)


# ---------------------------------------------------------------------------
# Category navigation
# ---------------------------------------------------------------------------


def _create_category_item(key: str, label: str):
    is_active = key == _active_category
    btn_tag = f"cat_btn_{key}"
    ind_tag = f"cat_ind_{key}"

    with dpg.group(horizontal=True):
        with dpg.drawlist(width=4, height=32, tag=f"cat_ind_dl_{key}"):
            bar_w = max(3, int(4 * _s))
            item_h = int(32 * _s)
            if is_active:
                dpg.draw_rectangle(
                    (0, 0),
                    (bar_w, item_h),
                    color=ACCENT,
                    fill=ACCENT,
                    tag=ind_tag,
                )
            else:
                dpg.draw_rectangle(
                    (0, 0),
                    (bar_w, item_h),
                    color=(0, 0, 0, 0),
                    fill=(0, 0, 0, 0),
                    tag=ind_tag,
                )

        dpg.add_button(
            label=f"  {tr(label)}",
            tag=btn_tag,
            width=int(168 * _s),
            height=item_h,
            callback=lambda s, a, u: _switch_category(key),
        )
        dpg.bind_item_theme(
            btn_tag, _cat_active_theme if is_active else _cat_inactive_theme
        )

    _cat_tags[key] = {"btn": btn_tag, "indicator": ind_tag}


def _switch_category(key: str):
    global _active_category, _settings_built
    if key == _active_category and _settings_built:
        return

    # Hide all groups, deactivate all items
    for cat_key, _ in CATEGORIES:
        group_tag = f"settings_group_{cat_key}"
        if dpg.does_item_exist(group_tag):
            dpg.configure_item(group_tag, show=(cat_key == key))

        if cat_key in _cat_tags:
            tags = _cat_tags[cat_key]
            is_active = cat_key == key
            dpg.bind_item_theme(
                tags["btn"], _cat_active_theme if is_active else _cat_inactive_theme
            )
            dpg.configure_item(
                tags["indicator"],
                color=ACCENT if is_active else (0, 0, 0, 0),
                fill=ACCENT if is_active else (0, 0, 0, 0),
            )

    _active_category = key
    _settings_built = True

    if key == "vision":
        _rebuild_session_list()


# ---------------------------------------------------------------------------
# Settings panels
# ---------------------------------------------------------------------------


def _build_pid_settings():
    with dpg.group(tag="settings_group_pid"):
        section_header("PID Tuning", color=ACCENT)
        caption_text(
            "Proportional-Integral-Derivative controller for fish bar tracking."
        )
        dpg.add_spacer(height=8)

        _slider_with_tooltip(
            "Kp",
            tag="cfg_pid_kp",
            min_val=0.0,
            max_val=2.0,
            fmt="%.3f",
            default=CFG.pid.kp,
            cb=lambda s, d: _set(CFG.pid, "kp", d),
        )
        _slider_with_tooltip(
            "Ki",
            tag="cfg_pid_ki",
            min_val=0.0,
            max_val=0.5,
            fmt="%.3f",
            default=CFG.pid.ki,
            cb=lambda s, d: _set(CFG.pid, "ki", d),
        )
        _slider_with_tooltip(
            "Kd",
            tag="cfg_pid_kd",
            min_val=0.0,
            max_val=1.0,
            fmt="%.3f",
            default=CFG.pid.kd,
            cb=lambda s, d: _set(CFG.pid, "kd", d),
        )
        _slider_with_tooltip(
            "Deadband (px)",
            tag="cfg_pid_deadband",
            min_val=0.0,
            max_val=20.0,
            fmt="%.1f",
            default=CFG.pid.deadband,
            cb=lambda s, d: _set(CFG.pid, "deadband", d),
        )
        _slider_with_tooltip(
            "Integral limit",
            tag="cfg_pid_integral_limit",
            min_val=10.0,
            max_val=500.0,
            fmt="%.0f",
            default=CFG.pid.integral_limit,
            cb=lambda s, d: _set(CFG.pid, "integral_limit", d),
        )
        _checkbox_with_tooltip(
            "Adaptive damping",
            tag="cfg_pid_adaptive",
            default=CFG.pid.adaptive,
            cb=lambda s, d: _set(CFG.pid, "adaptive", d),
        )


def _rebuild_session_list() -> None:
    """Clear and repopulate the session list child-window."""
    if _session_manager is None:
        return
    if not dpg.does_item_exist("session_list_window"):
        return

    dpg.delete_item("session_list_window", children_only=True)

    sessions = _session_manager.load_sessions()
    active_id = _session_manager.active_session_id()

    if not sessions:
        dpg.add_text(
            tr("No sessions yet."), parent="session_list_window", color=TEXT_MUTED
        )
        return

    for meta in reversed(sessions):
        is_active = meta.id == active_id
        prefix = "● " if is_active else "  "
        label = (
            f"{prefix}{meta.start[:16]} · {tr('{count} fish', count=meta.fish_count)}"
        )
        row_tag = f"session_row_{meta.id}"

        with dpg.group(horizontal=True, parent="session_list_window", tag=row_tag):
            text_tag = f"session_text_{meta.id}" if is_active else dpg.generate_uuid()
            dpg.add_text(
                label, tag=text_tag, color=TEXT_PRIMARY if is_active else TEXT_MUTED
            )
            dpg.add_spacer(width=int(8 * _s))
            styled_button(
                "Delete",
                f"session_del_{meta.id}",
                callback=lambda s, a, u: _on_delete_session(u),
                variant="danger",
                width=int(56 * _s),
                height=int(22 * _s),
                user_data=meta.id,
            )
            dpg.add_spacer(width=int(4 * _s))
            styled_button(
                "Export",
                f"session_exp_{meta.id}",
                callback=lambda s, a, u: _on_export_session(u),
                variant="neutral",
                width=int(56 * _s),
                height=int(22 * _s),
                user_data=meta.id,
            )


def _on_delete_session(session_id: str) -> None:
    if _session_manager is None:
        return
    if session_id == _session_manager.active_session_id():
        log.warning("Cannot delete the active session while the bot is running.")
        return
    _session_manager.delete_session(session_id)
    _rebuild_session_list()


def _on_export_session(session_id: str) -> None:
    """Open a small modal with CSV / JSON / XLSX buttons."""
    modal_tag = "export_modal"
    if dpg.does_item_exist(modal_tag):
        dpg.delete_item(modal_tag)

    with dpg.window(
        label=tr("Export Session"),
        tag=modal_tag,
        modal=True,
        no_resize=True,
        width=int(280 * _s),
        height=int(130 * _s),
        pos=(
            dpg.get_viewport_width() // 2 - int(140 * _s),
            dpg.get_viewport_height() // 2 - int(65 * _s),
        ),
    ):
        dpg.add_text(tr("Choose export format:"), color=TEXT_MUTED)
        dpg.add_spacer(height=int(6 * _s))
        with dpg.group(horizontal=True):
            for fmt, ext in [("CSV", "csv"), ("JSON", "json"), ("XLSX", "xlsx")]:
                styled_button(
                    fmt,
                    f"export_btn_{fmt}_{session_id}",
                    callback=lambda s, a, u: _do_export(u[0], u[1], modal_tag),
                    variant="neutral",
                    width=int(56 * _s),
                    height=int(26 * _s),
                    user_data=(session_id, ext),
                )
                dpg.add_spacer(width=int(4 * _s))


def _do_export(session_id: str, fmt: str, modal_tag: str) -> None:
    """Open a DPG path-input modal then write the export."""
    if dpg.does_item_exist(modal_tag):
        dpg.delete_item(modal_tag)

    path_modal = "export_path_modal"
    if dpg.does_item_exist(path_modal):
        dpg.delete_item(path_modal)

    default_name = f"{session_id}.{fmt}"

    def _on_confirm(s, a, u):
        dest = dpg.get_value("export_path_input").strip()
        if dpg.does_item_exist(path_modal):
            dpg.delete_item(path_modal)
        if not dest:
            return
        try:
            _session_manager.export_session(session_id, dest, fmt)
            log.info("Session exported to %s", dest)
        except Exception:
            log.warning("Session export failed.", exc_info=True)

    with dpg.window(
        label=tr("Export as {format}", format=fmt.upper()),
        tag=path_modal,
        modal=True,
        no_resize=True,
        width=int(360 * _s),
        height=int(110 * _s),
        pos=(
            dpg.get_viewport_width() // 2 - int(180 * _s),
            dpg.get_viewport_height() // 2 - int(55 * _s),
        ),
    ):
        dpg.add_text(tr("Save path:"), color=TEXT_MUTED)
        dpg.add_input_text(
            tag="export_path_input",
            default_value=default_name,
            width=-1,
        )
        dpg.add_spacer(height=int(6 * _s))
        with dpg.group(horizontal=True):
            styled_button(
                "Save",
                "export_path_ok",
                callback=_on_confirm,
                variant="neutral",
                width=int(70 * _s),
                height=int(26 * _s),
            )
            dpg.add_spacer(width=int(6 * _s))
            styled_button(
                "Cancel",
                "export_path_cancel",
                callback=lambda s, a, u: (
                    dpg.delete_item(path_modal)
                    if dpg.does_item_exist(path_modal)
                    else None
                ),
                variant="danger",
                width=int(70 * _s),
                height=int(26 * _s),
            )


_CAL_COUNTDOWN_SECS = 3
_cal_pending: dict[str, object] = {}


def _cal_text(kind: str, msg: str) -> None:
    try:
        dpg.set_value(f"cal_{kind}_result", msg)
    except Exception:
        log.debug("Calibration text update failed", exc_info=True)


def _fmt_hsv(sug) -> str:
    return f"H {sug.lower[0]}-{sug.upper[0]}, S {sug.lower[1]}-{sug.upper[1]}, V {sug.lower[2]}-{sug.upper[2]}"


def _start_calibration(kind: str, bridge: BotBridge) -> None:
    status = bridge.latest_status()
    roi_t = status.button_roi if kind == "bite" else status.bar_roi
    if not roi_t or roi_t[2] <= 0 or roi_t[3] <= 0:
        _cal_text(kind, tr("Start the bot once so the scan areas are known."))
        return
    dpg.configure_item(f"cal_{kind}_apply", show=False)
    dpg.configure_item(f"cal_{kind}_btn", enabled=False)
    scale_sq = status.current_scale * status.current_scale
    roi = {"left": roi_t[0], "top": roi_t[1], "width": roi_t[2], "height": roi_t[3]}
    threading.Thread(
        target=_run_calibration, args=(kind, roi, scale_sq, bridge), daemon=True
    ).start()


def _run_calibration(
    kind: str, roi: dict, scale_sq: float, bridge: BotBridge
) -> None:
    from modules.calibration import describe, suggest_bite, suggest_gauge
    from modules.io_module import CaptureModule

    capture = CaptureModule()
    try:
        for left in range(_CAL_COUNTDOWN_SECS, 0, -1):
            _cal_text(kind, tr("Measuring in {n}s...").format(n=left))
            time.sleep(1.0)
        img = capture.grab_bgr(roi)
        log.info("[Calibration] %s area: %s", kind, describe(img))
        if kind == "bite":
            sug = suggest_bite(img)
            if sug is None:
                _cal_text(
                    kind,
                    tr("No matching color found. Is the prompt visible?")
                    + "\n"
                    + describe(img),
                )
                return
            min_px = max(1, int(sug.pixels * 0.5 / max(scale_sq, 1e-6)))
            _cal_pending["bite"] = (sug, min_px)
            _cal_text(
                kind,
                f"{_fmt_hsv(sug)} / {sug.pixels}px -> "
                + tr("pixel trigger {n}").format(n=min_px),
            )
        else:
            safe, cursor = suggest_gauge(
                img,
                (CFG.hsv.safe_zone.lower, CFG.hsv.safe_zone.upper),
                (CFG.hsv.cursor.lower, CFG.hsv.cursor.upper),
                bridge.background,
            )
            if safe is None and cursor is None:
                _cal_text(
                    kind,
                    tr("No matching color found. Is the gauge visible?")
                    + "\n"
                    + describe(img),
                )
                return
            _cal_pending["gauge"] = (safe, cursor)
            lines = []
            if safe is not None:
                lines.append(f"{tr('Safe Zone HSV')}: {_fmt_hsv(safe)}")
            if cursor is not None:
                lines.append(f"{tr('Cursor HSV')}: {_fmt_hsv(cursor)}")
            lines.append(
                tr("Background samples: {n}").format(n=bridge.background.samples)
            )
            _cal_text(kind, "\n".join(lines))
        dpg.configure_item(f"cal_{kind}_apply", show=True)
    except Exception as exc:
        log.warning("Calibration failed: %s", exc, exc_info=True)
        _cal_text(kind, tr("Measurement failed: {e}").format(e=exc))
    finally:
        capture.close()
        try:
            dpg.configure_item(f"cal_{kind}_btn", enabled=True)
        except Exception:
            log.debug("Calibration button re-enable failed", exc_info=True)


def _update_assist_text(bridge: BotBridge) -> None:
    assist = bridge.gauge_assist
    if assist.samples == 0:
        text = tr("No fight-start samples yet.")
        if assist.misses:
            text += f" ({tr('missed')}: {assist.misses})"
    else:
        safe, cursor = assist.summary()
        rate = assist.hit_rate or 0.0
        lines = [
            tr("Samples: {n}, current settings detected both bars: {p}%").format(
                n=assist.samples, p=round(rate * 100)
            )
        ]
        if safe is not None:
            lines.append(f"{tr('Safe Zone HSV')}: {_fmt_hsv(safe)}")
        if cursor is not None:
            lines.append(f"{tr('Cursor HSV')}: {_fmt_hsv(cursor)}")
        if assist.misses:
            lines.append(f"{tr('missed')}: {assist.misses}")
        text = "\n".join(lines)
    try:
        dpg.set_value("cal_assist_text", text)
    except Exception:
        log.debug("Assist text update failed", exc_info=True)


def _apply_assist(bridge: BotBridge) -> None:
    safe, cursor = bridge.gauge_assist.summary()
    if safe is None and cursor is None:
        return
    if any(s is not None and not _plausible(s) for s in (safe, cursor)):
        dpg.set_value("cal_assist_text", tr("Suggestion is too wide to be safe; not applied."))
        return
    if safe is not None:
        _apply_hsv("cfg_hsv_sz", CFG.hsv.safe_zone, safe)
    if cursor is not None:
        _apply_hsv("cfg_hsv_cur", CFG.hsv.cursor, cursor)
    dpg.set_value("cal_assist_text", tr("Applied. Remember to press Save Settings."))


def _reset_assist(bridge: BotBridge) -> None:
    bridge.gauge_assist.reset()
    _update_assist_text(bridge)


_MAX_HUE_SPAN = 30
_MIN_SAT_LOWER = 30


def _plausible(sug) -> bool:
    """Reject suggestions so wide or washed-out that they would match background."""
    return (sug.upper[0] - sug.lower[0]) <= _MAX_HUE_SPAN and sug.lower[1] >= _MIN_SAT_LOWER


def _reset_detection_colors() -> None:
    from config import HsvConfig

    defaults = HsvConfig()
    for key in ("safe_zone", "cursor", "blue"):
        target = getattr(CFG.hsv, key)
        source = getattr(defaults, key)
        target.lower, target.upper = source.lower, source.upper
    _sync_detection_widgets()
    _profile_msg(tr("Detection colors reset to default. Press Save Settings to keep them."))


def _apply_hsv(prefix: str, target, sug) -> None:
    target.lower = tuple(sug.lower)
    target.upper = tuple(sug.upper)
    dpg.set_value(f"{prefix}_lower", list(target.lower))
    dpg.set_value(f"{prefix}_upper", list(target.upper))
    update_hsv_preview(prefix, target)


def _apply_calibration(kind: str) -> None:
    pending = _cal_pending.get(kind)
    if pending is None:
        return
    suggestions = [pending[0]] if kind == "bite" else list(pending)
    if any(s is not None and not _plausible(s) for s in suggestions):
        _cal_text(kind, tr("Suggestion is too wide to be safe; not applied."))
        return
    _cal_pending.pop(kind, None)
    if kind == "bite":
        sug, min_px = pending
        _apply_hsv("cfg_hsv_bl", CFG.hsv.blue, sug)
        CFG.min_blue_pixels = min_px
        dpg.set_value("cfg_min_blue", min_px)
    else:
        safe, cursor = pending
        if safe is not None:
            _apply_hsv("cfg_hsv_sz", CFG.hsv.safe_zone, safe)
        if cursor is not None:
            _apply_hsv("cfg_hsv_cur", CFG.hsv.cursor, cursor)
    dpg.configure_item(f"cal_{kind}_apply", show=False)
    _cal_text(kind, tr("Applied. Remember to press Save Settings."))


def _profile_names() -> list[str]:
    return [
        p["name"] for p in CFG.profiles if isinstance(p, dict) and "name" in p
    ]


def _profile_msg(msg: str) -> None:
    try:
        dpg.set_value("cfg_profile_msg", msg)
    except Exception:
        log.debug("Profile message update failed", exc_info=True)


def _refresh_profile_combo(select: str | None = None) -> None:
    names = _profile_names()
    dpg.configure_item("cfg_profile_combo", items=names)
    dpg.set_value("cfg_profile_combo", select if select in names else (names or [""])[0])


def _sync_detection_widgets() -> None:
    for prefix, rng in (
        ("cfg_hsv_sz", CFG.hsv.safe_zone),
        ("cfg_hsv_cur", CFG.hsv.cursor),
        ("cfg_hsv_bl", CFG.hsv.blue),
    ):
        dpg.set_value(f"{prefix}_lower", list(rng.lower))
        dpg.set_value(f"{prefix}_upper", list(rng.upper))
        update_hsv_preview(prefix, rng)
    dpg.set_value("cfg_min_blue", CFG.min_blue_pixels)


def _apply_selected_profile() -> None:
    from modules.profiles import apply_profile

    name = dpg.get_value("cfg_profile_combo")
    for profile in CFG.profiles:
        if isinstance(profile, dict) and profile.get("name") == name:
            apply_profile(CFG, profile)
            _sync_detection_widgets()
            _profile_msg(tr("Applied profile: {name}").format(name=name))
            return
    _profile_msg(tr("No profile selected."))


def _save_profile(bridge: BotBridge) -> None:
    from modules.profiles import make_profile, upsert_profile

    name = (dpg.get_value("cfg_profile_name") or "").strip()
    if not name:
        _profile_msg(tr("Enter a profile name."))
        return
    signature = bridge.background.signature()
    if signature is None:
        _profile_msg(tr("No background samples yet. Let the bot wait for a bite first."))
        return
    upsert_profile(CFG.profiles, make_profile(name, CFG, signature))
    CFG.active_profile = name
    _refresh_profile_combo(name)
    _profile_msg(tr("Saved profile: {name}. Remember to press Save Settings.").format(name=name))


def _delete_selected_profile() -> None:
    name = dpg.get_value("cfg_profile_combo")
    CFG.profiles[:] = [
        p for p in CFG.profiles if not (isinstance(p, dict) and p.get("name") == name)
    ]
    if CFG.active_profile == name:
        CFG.active_profile = ""
    _refresh_profile_combo()
    _profile_msg(tr("Deleted profile: {name}").format(name=name))


def _build_vision_settings(bridge: BotBridge):
    with dpg.group(tag="settings_group_vision"):
        section_header("Vision & Detection", color=ACCENT)
        caption_text("HSV color ranges and detection sensitivity for game elements.")
        dpg.add_spacer(height=8)

        status = bridge.latest_status()
        scale_sq = status.current_scale * status.current_scale
        current_val = CFG.detection_min_area * scale_sq

        _slider_with_tooltip(
            "Detection threshold (px)",
            tag="cfg_vision_min_area",
            min_val=1.0,
            max_val=100.0,
            fmt="%.1f",
            default=current_val,
            cb=lambda s, d: _set_scaled_min_area(d, bridge),
        )
        dpg.add_spacer(height=4)

        hsv_editor(
            "cfg_hsv_sz", CFG.hsv.safe_zone, label="Safe Zone HSV", default_open=True
        )
        hsv_editor("cfg_hsv_cur", CFG.hsv.cursor, label="Cursor HSV", default_open=True)
        hsv_editor(
            "cfg_hsv_bl", CFG.hsv.blue, label="Bite Trigger HSV", default_open=False
        )
        dpg.add_button(
            label=tr("Reset detection colors to default"),
            callback=_reset_detection_colors,
        )

        dpg.add_spacer(height=4)
        _slider_with_tooltip(
            "Edge ignore ratio",
            tag="cfg_roi_ignore_margin",
            min_val=0.0,
            max_val=0.12,
            fmt="%.3f",
            default=CFG.roi.ignore_margin_ratio,
            cb=lambda s, d: _set(CFG.roi, "ignore_margin_ratio", d),
        )
        dpg.add_spacer(height=int(8 * _s))
        dpg.add_text(tr("Scan area adjustment"), color=TEXT_MUTED)
        caption_text(
            "Shift the bar and bite areas (pixels) if the tracker preview shows "
            "the wrong place, e.g. windowed mode or a different aspect ratio."
        )
        for label, tag, attr, lim in (
            ("Bar area X offset", "cfg_roi_bar_x", "bar_offset_x", 600),
            ("Bar area Y offset", "cfg_roi_bar_y", "bar_offset_y", 600),
            ("Bar area width change", "cfg_roi_bar_w", "bar_width_delta", 800),
            ("Bar area height change", "cfg_roi_bar_h", "bar_height_delta", 200),
            ("Bite area X offset", "cfg_roi_btn_x", "button_offset_x", 600),
            ("Bite area Y offset", "cfg_roi_btn_y", "button_offset_y", 600),
            ("Bite area width change", "cfg_roi_btn_w", "button_width_delta", 800),
            ("Bite area height change", "cfg_roi_btn_h", "button_height_delta", 400),
            ("Cast check area X offset", "cfg_roi_icon_x", "icon_offset_x", 600),
            ("Cast check area Y offset", "cfg_roi_icon_y", "icon_offset_y", 600),
            ("Cast check area width change", "cfg_roi_icon_w", "icon_width_delta", 800),
            ("Cast check area height change", "cfg_roi_icon_h", "icon_height_delta", 400),
        ):
            dpg.add_slider_int(
                label=tr(label),
                tag=tag,
                min_value=-lim,
                max_value=lim,
                width=-int(180 * _s),
                default_value=getattr(CFG.roi, attr),
                callback=lambda s, d, a=attr: setattr(CFG.roi, a, int(d)),
            )
        _input_with_tooltip(
            "Blue pixel trigger",
            tag="cfg_min_blue",
            width=140,
            default=CFG.min_blue_pixels,
            cb=lambda s, d: _set_int(CFG, "min_blue_pixels", d, "cfg_min_blue", 1),
        )

        dpg.add_spacer(height=int(12 * _s))
        dpg.add_separator()
        dpg.add_spacer(height=int(8 * _s))
        dpg.add_text(tr("Adjust from current screen"), color=TEXT_MUTED)
        caption_text(
            "Show the target on screen, press the button, and the colors are "
            "measured after a short countdown. Nothing changes until you apply."
        )
        dpg.add_spacer(height=int(4 * _s))
        dpg.add_text(tr("Bite detection"))
        dpg.add_button(
            label=tr("Measure bite prompt"),
            tag="cal_bite_btn",
            callback=lambda: _start_calibration("bite", bridge),
        )
        dpg.add_text("", tag="cal_bite_result", wrap=int(420 * _s))
        dpg.add_button(
            label=tr("Apply bite result"),
            tag="cal_bite_apply",
            show=False,
            callback=lambda: _apply_calibration("bite"),
        )
        dpg.add_spacer(height=int(6 * _s))
        dpg.add_text(tr("Fishing gauge"))
        dpg.add_button(
            label=tr("Measure fishing gauge"),
            tag="cal_gauge_btn",
            callback=lambda: _start_calibration("gauge", bridge),
        )
        dpg.add_text("", tag="cal_gauge_result", wrap=int(420 * _s))
        dpg.add_button(
            label=tr("Apply gauge result"),
            tag="cal_gauge_apply",
            show=False,
            callback=lambda: _apply_calibration("gauge"),
        )
        dpg.add_spacer(height=int(6 * _s))
        dpg.add_text(tr("Fight-start assist"))
        caption_text(
            "At the start of every fight the cursor and safe zone are centered, "
            "so the colors are measured automatically. Suggestions only; nothing "
            "is applied until you press the button."
        )
        dpg.add_checkbox(
            label=tr("Measure gauge at fight start"),
            tag="cfg_gauge_assist",
            default_value=CFG.gauge_assist_enabled,
            callback=lambda s, d: _set(CFG, "gauge_assist_enabled", d),
        )
        dpg.add_text("", tag="cal_assist_text", wrap=int(420 * _s))
        dpg.add_button(
            label=tr("Apply assist suggestion"),
            callback=lambda: _apply_assist(bridge),
        )
        dpg.add_button(
            label=tr("Reset assist samples"), callback=lambda: _reset_assist(bridge)
        )
        bridge.assist_callback = lambda: _update_assist_text(bridge)
        _update_assist_text(bridge)

        dpg.add_spacer(height=int(12 * _s))
        dpg.add_separator()
        dpg.add_spacer(height=int(8 * _s))
        dpg.add_text(tr("Detection profiles"), color=TEXT_MUTED)
        caption_text(
            "Profiles hold the colors and pixel threshold for a lighting condition "
            "(day, evening, ...). With auto-switch on, the bot picks the profile "
            "closest to the background colors seen while waiting."
        )
        dpg.add_checkbox(
            label=tr("Auto-switch profile by background"),
            tag="cfg_profile_auto",
            default_value=CFG.profile_auto_switch,
            callback=lambda s, d: _set(CFG, "profile_auto_switch", d),
        )
        dpg.add_combo(
            label=tr("Profile"),
            tag="cfg_profile_combo",
            items=_profile_names(),
            default_value=CFG.active_profile or (_profile_names() or [""])[0],
            width=200,
        )
        dpg.add_button(
            label=tr("Apply selected profile"), callback=_apply_selected_profile
        )
        dpg.add_input_text(
            label=tr("Profile name"), tag="cfg_profile_name", width=200, hint="Night"
        )
        dpg.add_button(
            label=tr("Save current settings as profile"),
            callback=lambda: _save_profile(bridge),
        )
        dpg.add_button(
            label=tr("Delete selected profile"), callback=_delete_selected_profile
        )
        dpg.add_text("", tag="cfg_profile_msg", wrap=int(420 * _s))
        dpg.add_spacer(height=int(4 * _s))
        dpg.add_text(tr("Fishing battle detection bars"), color=TEXT_MUTED)
        caption_text(
            "While a checked bar is visible the bot stays in the fishing battle."
        )
        dpg.add_checkbox(
            label=tr("Cursor bar"),
            tag="cfg_battle_cursor",
            default_value=CFG.battle_detect_cursor,
            callback=lambda s, d: _set(CFG, "battle_detect_cursor", d),
        )
        dpg.add_checkbox(
            label=tr("Safe zone bar"),
            tag="cfg_battle_safe_zone",
            default_value=CFG.battle_detect_safe_zone,
            callback=lambda s, d: _set(CFG, "battle_detect_safe_zone", d),
        )

        dpg.add_spacer(height=int(12 * _s))
        dpg.add_separator()
        dpg.add_spacer(height=int(8 * _s))
        dpg.add_text(tr("Fish Logging"), color=TEXT_MUTED)
        dpg.add_spacer(height=int(4 * _s))
        caption_text(
            "Record each caught fish (name + weight) to a per-session CSV file."
        )
        dpg.add_spacer(height=int(4 * _s))
        dpg.add_checkbox(
            label=tr("Enable fish logging"),
            tag="cfg_fish_logging_enabled",
            default_value=CFG.fish_logging_enabled,
            callback=lambda s, d: _set(CFG, "fish_logging_enabled", d),
        )
        dpg.add_spacer(height=int(8 * _s))
        styled_button(
            "Change Scanning Areas",
            "btn_scan_areas",
            callback=lambda s, a, u: _open_scanning_area_editor(),
            variant="neutral",
            width=int(190 * _s),
            height=int(28 * _s),
        )
        dpg.add_spacer(height=int(10 * _s))
        dpg.add_text(tr("Sessions"), color=TEXT_MUTED)
        dpg.add_spacer(height=int(4 * _s))
        with dpg.child_window(
            tag="session_list_window",
            height=int(180 * _s),
            border=True,
        ):
            pass


# ---------------------------------------------------------------------------
# Scanning area editor — fullscreen transparent tkinter overlay
# ---------------------------------------------------------------------------


_scan_editor_open = threading.Event()


def _open_scanning_area_editor() -> None:
    """Spawn a transparent fullscreen overlay on the game monitor.

    Two coloured rectangles (red = Fish Name, blue = Weight) are drawn
    directly over the live game.  The user drags the body to move and
    drags any corner handle to resize.  OK saves to CFG; Cancel discards.
    Runs in its own thread so the DPG UI stays responsive.
    """
    try:
        import tkinter as tk
    except ImportError:
        log.warning(
            "Tkinter is not available in this build; scanning area editor is disabled."
        )
        return

    if _scan_editor_open.is_set():
        log.info("Scanning area editor is already open.")
        return

    monitors = get_monitors()
    mon_idx = max(0, min(CFG.monitor_index, len(monitors) - 1))
    mon = monitors[mon_idx]
    sw, sh = mon.width, mon.height
    off_x = mon.x
    off_y = mon.y

    # Pixels that use this colour become see-through on Windows
    _TRANSPARENT = "#000001"
    _NAME_CLR = "#FF4444"
    _WEIGHT_CLR = "#44AAFF"
    _BAR_CLR = "#44DD66"
    _BITE_CLR = "#FFCC00"
    _ICON_CLR = "#CC66FF"
    # key, colour, label
    _AREAS = (
        ("name", _NAME_CLR, "Fish Name"),
        ("weight", _WEIGHT_CLR, "Weight (g)"),
        ("bar", _BAR_CLR, "Bar area"),
        ("bite", _BITE_CLR, "Bite area"),
        ("icons", _ICON_CLR, "Icon area"),
    )
    _HANDLE = 10  # half-size of corner square
    _BORDER = 3

    def _run() -> None:
        try:
            _run_overlay()
        except Exception:
            log.warning("Scanning area editor failed.", exc_info=True)
        finally:
            _scan_editor_open.clear()

    def _run_overlay() -> None:
        # All Tk objects live and die on this thread.
        root = tk.Tk()
        root.overrideredirect(True)
        root.geometry(f"{sw}x{sh}+{off_x}+{off_y}")
        root.attributes("-topmost", True)
        root.configure(bg=_TRANSPARENT)
        root.attributes("-transparentcolor", _TRANSPARENT)

        canvas = tk.Canvas(root, bg=_TRANSPARENT, highlightthickness=0, cursor="fleur")
        canvas.place(x=0, y=0, width=sw, height=sh)

        # ── Convert config ratios → pixel rects ──────────────────────────
        def r2px(ratios):
            l, t, r, b = ratios
            return [int(l * sw), int(t * sh), int(r * sw), int(b * sh)]

        state = {
            "name": r2px(CFG.ocr_name_roi_ratios),
            "weight": r2px(CFG.ocr_weight_roi_ratios),
            "bar": r2px(
                CFG.bar_roi_ratios
                if ratios_are_set(CFG.bar_roi_ratios)
                else DEFAULT_BAR_RATIOS
            ),
            "bite": r2px(
                CFG.button_roi_ratios
                if ratios_are_set(CFG.button_roi_ratios)
                else DEFAULT_BUTTON_RATIOS
            ),
            "icons": r2px(
                CFG.icon_roi_ratios
                if ratios_are_set(CFG.icon_roi_ratios)
                else DEFAULT_ICON_RATIOS
            ),
            "drag_target": None,
            "drag_mode": None,
            "drag_start": (0, 0),
            "drag_rect_start": None,
        }

        # ── Drawing ───────────────────────────────────────────────────────
        def redraw():
            canvas.delete("overlay")
            for which, color, label_key in _AREAS:
                x1, y1, x2, y2 = state[which]
                lx, rx = min(x1, x2), max(x1, x2)
                ty, by = min(y1, y2), max(y1, y2)
                label = tr(label_key)
                # Rectangle border (no fill — game shows through)
                canvas.create_rectangle(
                    lx, ty, rx, by, outline=color, width=_BORDER, tags="overlay"
                )
                # Label badge above the rectangle
                tx, text_y = lx + 6, ty - 14
                canvas.create_rectangle(
                    tx - 4,
                    text_y - 2,
                    tx + len(label) * 8 + 4,
                    text_y + 16,
                    fill="#1a1a2e",
                    outline=color,
                    width=1,
                    tags="overlay",
                )
                canvas.create_text(
                    tx,
                    text_y + 7,
                    text=label,
                    fill=color,
                    anchor="w",
                    font=("Yu Gothic UI", 11, "bold"),
                    tags="overlay",
                )
                # Corner handles
                for cx, cy in [(lx, ty), (rx, ty), (lx, by), (rx, by)]:
                    canvas.create_rectangle(
                        cx - _HANDLE,
                        cy - _HANDLE,
                        cx + _HANDLE,
                        cy + _HANDLE,
                        fill=color,
                        outline="white",
                        width=1,
                        tags="overlay",
                    )

        # ── Instruction banner ────────────────────────────────────────────
        banner = tr(
            "Drag to move  •  Drag corner squares to resize  "
            "•  Red = Fish Name | Blue = Weight | Green = Bar | Yellow = Bite | Purple = Icons"
        )
        bx = sw // 2
        canvas.create_rectangle(
            bx - 540, 10, bx + 540, 40, fill="#1a1a2e", outline="#444444", width=1
        )
        canvas.create_text(bx, 25, text=banner, fill="white", font=("Yu Gothic UI", 12))

        # ── OK / Cancel buttons (bottom-right) ────────────────────────────
        btn_frame = tk.Frame(root, bg="#1a1a2e", bd=0)

        def do_apply():
            def p2r(rect):
                x1, y1, x2, y2 = rect
                return (
                    max(0.0, min(1.0, min(x1, x2) / sw)),
                    max(0.0, min(1.0, min(y1, y2) / sh)),
                    max(0.0, min(1.0, max(x1, x2) / sw)),
                    max(0.0, min(1.0, max(y1, y2) / sh)),
                )

            CFG.ocr_name_roi_ratios = p2r(state["name"])
            CFG.ocr_weight_roi_ratios = p2r(state["weight"])
            CFG.bar_roi_ratios = p2r(state["bar"])
            CFG.button_roi_ratios = p2r(state["bite"])
            CFG.icon_roi_ratios = p2r(state["icons"])
            CFG.save()
            log.info(
                "Scanning areas saved — name=%s  weight=%s  bar=%s  bite=%s",
                CFG.ocr_name_roi_ratios,
                CFG.ocr_weight_roi_ratios,
                CFG.bar_roi_ratios,
                CFG.button_roi_ratios,
            )
            root.destroy()

        tk.Button(
            btn_frame,
            text="OK",
            bg="#4CAF50",
            fg="white",
            activebackground="#45a049",
            activeforeground="white",
            font=("Yu Gothic UI", 12, "bold"),
            padx=22,
            pady=8,
            bd=0,
            command=do_apply,
        ).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(
            btn_frame,
            text=tr("Cancel"),
            bg="#555555",
            fg="white",
            activebackground="#666666",
            activeforeground="white",
            font=("Yu Gothic UI", 12),
            padx=22,
            pady=8,
            bd=0,
            command=root.destroy,
        ).pack(side=tk.LEFT)
        btn_frame.place(x=sw - 270, y=sh - 64)

        # ── Mouse interaction ─────────────────────────────────────────────
        def hit_test(ex, ey, rect):
            x1, y1, x2, y2 = rect
            lx, rx = min(x1, x2), max(x1, x2)
            ty, by = min(y1, y2), max(y1, y2)
            hs = _HANDLE + 4
            for mode, cx, cy in [
                ("tl", lx, ty),
                ("tr", rx, ty),
                ("bl", lx, by),
                ("br", rx, by),
            ]:
                if abs(ex - cx) <= hs and abs(ey - cy) <= hs:
                    return mode
            if lx <= ex <= rx and ty <= ey <= by:
                return "move"
            return None

        def on_press(event):
            for which in ("icons", "bite", "bar", "weight", "name"):
                mode = hit_test(event.x, event.y, state[which])
                if mode:
                    state["drag_target"] = which
                    state["drag_mode"] = mode
                    state["drag_start"] = (event.x, event.y)
                    state["drag_rect_start"] = list(state[which])
                    return

        def on_drag(event):
            if not state["drag_target"]:
                return
            dx = event.x - state["drag_start"][0]
            dy = event.y - state["drag_start"][1]
            r = state["drag_rect_start"]
            which, mode = state["drag_target"], state["drag_mode"]

            if mode == "move":
                w, h = r[2] - r[0], r[3] - r[1]
                nx = max(0, min(sw - w, r[0] + dx))
                ny = max(0, min(sh - h, r[1] + dy))
                state[which] = [nx, ny, nx + w, ny + h]
            elif mode == "tl":
                state[which] = [max(0, r[0] + dx), max(0, r[1] + dy), r[2], r[3]]
            elif mode == "tr":
                state[which] = [r[0], max(0, r[1] + dy), min(sw, r[2] + dx), r[3]]
            elif mode == "bl":
                state[which] = [max(0, r[0] + dx), r[1], r[2], min(sh, r[3] + dy)]
            elif mode == "br":
                state[which] = [r[0], r[1], min(sw, r[2] + dx), min(sh, r[3] + dy)]
            redraw()

        def on_release(event):
            state["drag_target"] = None
            state["drag_mode"] = None

        canvas.bind("<Button-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)

        redraw()
        root.mainloop()

    _scan_editor_open.set()
    threading.Thread(target=_run, daemon=True).start()


def _build_timing_settings():
    with dpg.group(tag="settings_group_timing"):
        section_header("Timing", color=ACCENT)
        caption_text("Timing parameters for the fishing state machine.")
        dpg.add_spacer(height=8)

        _slider_with_tooltip(
            "Cast animation (s)",
            tag="cfg_timing_cast",
            min_val=0.5,
            max_val=10.0,
            fmt="%.2f",
            default=CFG.timing.cast_animation_secs,
            cb=lambda s, d: _set(CFG.timing, "cast_animation_secs", d),
        )
        _slider_with_tooltip(
            "Bite timeout (s)",
            tag="cfg_timing_bite",
            min_val=5.0,
            max_val=300.0,
            fmt="%.1f",
            default=CFG.timing.bite_timeout_secs,
            cb=lambda s, d: _set(CFG.timing, "bite_timeout_secs", d),
        )
        _input_with_tooltip(
            "Lost frame limit",
            tag="cfg_timing_lost",
            width=140,
            default=CFG.timing.lost_frames_threshold,
            cb=lambda s, d: _set_int(
                CFG.timing,
                "lost_frames_threshold",
                d,
                "cfg_timing_lost",
                1,
            ),
        )
        _slider_with_tooltip(
            "Result wait (s)",
            tag="cfg_timing_result",
            min_val=0.5,
            max_val=15.0,
            fmt="%.2f",
            default=CFG.timing.result_wait_secs,
            cb=lambda s, d: _set(CFG.timing, "result_wait_secs", d),
        )
        _slider_with_tooltip(
            "Key press base (s)",
            tag="cfg_timing_key_press",
            min_val=0.01,
            max_val=1.0,
            fmt="%.3f",
            default=CFG.timing.key_press_duration,
            cb=lambda s, d: _set(CFG.timing, "key_press_duration", d),
        )
        _slider_with_tooltip(
            "Waiting poll (s)",
            tag="cfg_timing_wait_poll",
            min_val=0.005,
            max_val=1.0,
            fmt="%.3f",
            default=CFG.timing.waiting_poll_interval,
            cb=lambda s, d: _set(CFG.timing, "waiting_poll_interval", d),
        )
        _slider_with_tooltip(
            "Tracking poll (s)",
            tag="cfg_timing_track_poll",
            min_val=0.005,
            max_val=0.500,
            fmt="%.3f",
            default=CFG.timing.struggling_poll_interval,
            cb=lambda s, d: _set(CFG.timing, "struggling_poll_interval", d),
        )
        _input_with_tooltip(
            "Bait error limit",
            tag="cfg_timing_bait_err",
            width=140,
            default=CFG.timing.bait_error_threshold,
            cb=lambda s, d: _set_int(
                CFG.timing,
                "bait_error_threshold",
                d,
                "cfg_timing_bait_err",
                1,
            ),
        )
        _slider_with_tooltip(
            "Max struggle (s)",
            tag="cfg_timing_max_struggle",
            min_val=30.0,
            max_val=600.0,
            fmt="%.0f",
            default=CFG.timing.max_struggle_secs,
            cb=lambda s, d: _set(CFG.timing, "max_struggle_secs", d),
        )


def _build_input_settings(
    bridge: BotBridge,
    on_hotkeys_changed: Callable[[], None] | None = None,
):
    with dpg.group(tag="settings_group_input"):
        section_header("Input & Hotkeys", color=ACCENT)
        caption_text("Key bindings for in-game actions and global hotkeys.")
        dpg.add_spacer(height=8)

        dpg.add_text(tr("Key Bindings"), color=TEXT_MUTED)
        dpg.add_spacer(height=4)
        _key_input("Cast key", "cfg_key_cast", CFG.keys.cast, "cast")
        _key_input("Move left", "cfg_key_left", CFG.keys.left, "left")
        _key_input("Move right", "cfg_key_right", CFG.keys.right, "right")
        _key_input("Exit key", "cfg_key_exit", CFG.keys.exit, "exit")

        dpg.add_combo(
            label=tr("Result close"),
            items=[tr(label) for label in _RESULT_METHODS],
            default_value=_result_method_label(CFG.result_close_method),
            width=160,
            tag="cfg_result_close_method",
            callback=lambda s, d: _set_result_method(d),
        )
        dpg.add_checkbox(
            label=tr("Spam cast key while waiting"),
            tag="cfg_spam_cast",
            default_value=CFG.spam_cast_enabled,
            callback=lambda s, d: _set(CFG, "spam_cast_enabled", d),
        )
        caption_text(
            "Presses the cast key at random intervals; closes the result screen "
            "and forces the fight if a bite is missed. Stops when bait runs out."
        )
        _slider_with_tooltip(
            "Spam interval min (s)",
            tag="cfg_spam_min",
            min_val=0.1,
            max_val=5.0,
            fmt="%.2f",
            default=CFG.spam_cast_interval_min,
            cb=lambda s, d: _set(CFG, "spam_cast_interval_min", d),
        )
        _slider_with_tooltip(
            "Spam interval max (s)",
            tag="cfg_spam_max",
            min_val=0.1,
            max_val=5.0,
            fmt="%.2f",
            default=CFG.spam_cast_interval_max,
            cb=lambda s, d: _set(CFG, "spam_cast_interval_max", d),
        )
        dpg.add_checkbox(
            label=tr("Always on top"),
            tag="cfg_always_on_top",
            default_value=CFG.always_on_top,
            callback=lambda s, d: _on_top_changed(d),
        )
        dpg.add_checkbox(
            label=tr("Detect bait exhaustion (cast fails repeatedly)"),
            tag="cfg_bait_error_detect",
            default_value=CFG.bait_error_detection_enabled,
            callback=lambda s, d: _set(CFG, "bait_error_detection_enabled", d),
        )
        dpg.add_checkbox(
            label=tr("Show live capture in tracker"),
            tag="cfg_tracker_preview",
            default_value=CFG.tracker_preview_enabled,
            callback=lambda s, d: (
                _set(CFG, "tracker_preview_enabled", d),
                dpg.set_value("pv_live", d) if dpg.does_item_exist("pv_live") else None,
            ),
        )
        dpg.add_checkbox(
            label=tr("Debug logging"),
            tag="cfg_debug_mode",
            default_value=CFG.debug_mode,
            callback=lambda s, d: _set(CFG, "debug_mode", d),
        )

        monitors = _monitor_labels()
        default_monitor = min(CFG.monitor_index, len(monitors) - 1)

        dpg.add_combo(
            label=tr("Monitor"),
            tag="cfg_monitor_index",
            items=monitors,
            default_value=monitors[default_monitor],
            width=300,
            callback=lambda s, d: _set_monitor(d, monitors),
        )
        dpg.add_checkbox(
            label=tr("Auto-select the game's monitor on launch"),
            tag="cfg_monitor_auto_select",
            default_value=CFG.monitor_auto_select,
            callback=lambda s, d: _set(CFG, "monitor_auto_select", d),
        )

        dpg.add_spacer(height=12)
        dpg.add_text(tr("Global Hotkeys"), color=TEXT_MUTED)
        dpg.add_spacer(height=4)
        _text_input_with_tooltip(
            "Toggle",
            tag="cfg_hotkey_toggle",
            width=200,
            default=CFG.hotkeys.toggle,
            cb=lambda s, d: _set_hotkey("toggle", d, bridge, on_hotkeys_changed),
        )
        _text_input_with_tooltip(
            "Stop",
            tag="cfg_hotkey_stop",
            width=200,
            default=CFG.hotkeys.stop,
            cb=lambda s, d: _set_hotkey("stop", d, bridge, on_hotkeys_changed),
        )


def _build_humanization_settings():
    with dpg.group(tag="settings_group_humanization"):
        section_header("Humanization", color=ACCENT)
        caption_text("Natural variation to make the bot less mechanical.")
        dpg.add_spacer(height=8)

        _checkbox_with_tooltip(
            "Humanize input",
            tag="cfg_hum_enabled",
            default=CFG.humanization.enabled,
            cb=lambda s, d: _set(CFG.humanization, "enabled", d),
        )

        dpg.add_spacer(height=8)
        dpg.add_text(tr("Key Pulse Timing"), color=TEXT_MUTED)
        dpg.add_spacer(height=4)
        _slider_with_tooltip(
            "Button hold min (s)",
            tag="cfg_hum_pulse_hold_min",
            min_val=0.010,
            max_val=0.500,
            fmt="%.3f",
            default=CFG.humanization.pulse_hold_min,
            cb=lambda s, d: _set(CFG.humanization, "pulse_hold_min", d),
        )
        _slider_with_tooltip(
            "Button hold max (s)",
            tag="cfg_hum_pulse_hold_max",
            min_val=0.020,
            max_val=1.000,
            fmt="%.3f",
            default=CFG.humanization.pulse_hold_max,
            cb=lambda s, d: _set(CFG.humanization, "pulse_hold_max", d),
        )
        _slider_with_tooltip(
            "Button released min (s)",
            tag="cfg_hum_pulse_release_min",
            min_val=0.005,
            max_val=0.500,
            fmt="%.3f",
            default=CFG.humanization.pulse_release_min,
            cb=lambda s, d: _set(CFG.humanization, "pulse_release_min", d),
        )
        _slider_with_tooltip(
            "Button released max (s)",
            tag="cfg_hum_pulse_release_max",
            min_val=0.010,
            max_val=1.000,
            fmt="%.3f",
            default=CFG.humanization.pulse_release_max,
            cb=lambda s, d: _set(CFG.humanization, "pulse_release_max", d),
        )

        dpg.add_spacer(height=8)
        dpg.add_text(tr("Deadband Micro-corrections"), color=TEXT_MUTED)
        dpg.add_spacer(height=4)
        _checkbox_with_tooltip(
            "Deadband taps",
            tag="cfg_hum_db_tap",
            default=CFG.humanization.deadband_tap_enabled,
            cb=lambda s, d: _set(CFG.humanization, "deadband_tap_enabled", d),
        )
        _slider_with_tooltip(
            "Per-battle play chance",
            tag="cfg_hum_db_battle_chance",
            min_val=0.0,
            max_val=1.0,
            fmt="%.2f",
            default=CFG.humanization.deadband_play_battle_chance,
            cb=lambda s, d: _set(
                CFG.humanization,
                "deadband_play_battle_chance",
                d,
            ),
        )
        _slider_with_tooltip(
            "Tap chance",
            tag="cfg_hum_db_chance",
            min_val=0.0,
            max_val=1.0,
            fmt="%.2f",
            default=CFG.humanization.deadband_tap_chance,
            cb=lambda s, d: _set(CFG.humanization, "deadband_tap_chance", d),
        )

        dpg.add_spacer(height=8)
        dpg.add_text(tr("Reaction Latency"), color=TEXT_MUTED)
        dpg.add_spacer(height=4)
        _slider_with_tooltip(
            "Reaction min (s)",
            tag="cfg_hum_react_min",
            min_val=0.0,
            max_val=0.750,
            fmt="%.3f",
            default=CFG.humanization.reaction_latency_min,
            cb=lambda s, d: _set(CFG.humanization, "reaction_latency_min", d),
        )
        _slider_with_tooltip(
            "Reaction max (s)",
            tag="cfg_hum_react_max",
            min_val=0.0,
            max_val=1.500,
            fmt="%.3f",
            default=CFG.humanization.reaction_latency_max,
            cb=lambda s, d: _set(CFG.humanization, "reaction_latency_max", d),
        )
        _combo_with_tooltip(
            "Reaction dist",
            tag="cfg_hum_react_dist",
            items=["uniform", "gaussian", "exponential"],
            default=CFG.humanization.reaction_latency_dist,
            cb=lambda s, d: _set(CFG.humanization, "reaction_latency_dist", d),
        )

        dpg.add_spacer(height=8)
        dpg.add_text(tr("PID Noise"), color=TEXT_MUTED)
        dpg.add_spacer(height=4)
        _checkbox_with_tooltip(
            "PID noise",
            tag="cfg_hum_noise_enabled",
            default=CFG.humanization.pid_noise_enabled,
            cb=lambda s, d: _set(CFG.humanization, "pid_noise_enabled", d),
        )
        _slider_with_tooltip(
            "Noise amplitude (px)",
            tag="cfg_hum_noise_amp",
            min_val=0.0,
            max_val=15.0,
            fmt="%.1f",
            default=CFG.humanization.pid_noise_amplitude,
            cb=lambda s, d: _set(CFG.humanization, "pid_noise_amplitude", d),
        )
        _combo_with_tooltip(
            "Noise dist",
            tag="cfg_hum_noise_dist",
            items=["uniform", "gaussian"],
            default=CFG.humanization.pid_noise_dist,
            cb=lambda s, d: _set(CFG.humanization, "pid_noise_dist", d),
        )

        dpg.add_spacer(height=8)
        dpg.add_text(tr("Cursor Movement Styles"), color=TEXT_MUTED)
        dpg.add_spacer(height=4)
        with dpg.group(horizontal=True):
            _slider_with_tooltip(
                "Movement scale min",
                tag="cfg_hum_move_scale_min",
                min_val=0.25,
                max_val=1.5,
                fmt="%.2f",
                default=CFG.humanization.movement_scale_min,
                cb=lambda s, d: _set(CFG.humanization, "movement_scale_min", d),
            )
            _slider_with_tooltip(
                "Movement scale max",
                tag="cfg_hum_move_scale_max",
                min_val=0.5,
                max_val=2.0,
                fmt="%.2f",
                default=CFG.humanization.movement_scale_max,
                cb=lambda s, d: _set(CFG.humanization, "movement_scale_max", d),
            )
        _slider_with_tooltip(
            "Slow move chance",
            tag="cfg_hum_slow_chance",
            min_val=0.0,
            max_val=0.5,
            fmt="%.2f",
            default=CFG.humanization.slow_move_chance,
            cb=lambda s, d: _set(CFG.humanization, "slow_move_chance", d),
        )
        with dpg.group(horizontal=True):
            _slider_with_tooltip(
                "Slow hold scale",
                tag="cfg_hum_slow_hold_scale",
                min_val=0.1,
                max_val=1.0,
                fmt="%.2f",
                default=CFG.humanization.slow_move_hold_scale_max,
                cb=lambda s, d: _set(CFG.humanization, "slow_move_hold_scale_max", d),
            )
            _slider_with_tooltip(
                "Slow gap scale",
                tag="cfg_hum_slow_gap_scale",
                min_val=1.0,
                max_val=3.0,
                fmt="%.2f",
                default=CFG.humanization.slow_move_gap_scale,
                cb=lambda s, d: _set(CFG.humanization, "slow_move_gap_scale", d),
            )
        _slider_with_tooltip(
            "Reverse flick chance",
            tag="cfg_hum_flick_chance",
            min_val=0.0,
            max_val=1.0,
            fmt="%.2f",
            default=CFG.humanization.flick_chance_on_reverse,
            cb=lambda s, d: _set(CFG.humanization, "flick_chance_on_reverse", d),
        )
        with dpg.group(horizontal=True):
            _slider_with_tooltip(
                "Flick hold scale",
                tag="cfg_hum_flick_hold_scale",
                min_val=1.0,
                max_val=3.0,
                fmt="%.2f",
                default=CFG.humanization.flick_hold_scale_max,
                cb=lambda s, d: _set(CFG.humanization, "flick_hold_scale_max", d),
            )
            _slider_with_tooltip(
                "Flick gap scale",
                tag="cfg_hum_flick_gap_scale",
                min_val=0.1,
                max_val=1.0,
                fmt="%.2f",
                default=CFG.humanization.flick_gap_scale,
                cb=lambda s, d: _set(CFG.humanization, "flick_gap_scale", d),
            )
        _slider_with_tooltip(
            "Random action chance",
            tag="cfg_hum_random_action_chance",
            min_val=0.0,
            max_val=0.2,
            fmt="%.2f",
            default=CFG.humanization.random_action_chance,
            cb=lambda s, d: _set(CFG.humanization, "random_action_chance", d),
        )

        dpg.add_spacer(height=8)
        dpg.add_text(tr("Timing Variation Formula"), color=TEXT_MUTED)
        dpg.add_spacer(height=4)
        with dpg.group(horizontal=True):
            _slider_with_tooltip(
                "Timing scale min",
                tag="cfg_hum_timing_scale_min",
                min_val=0.25,
                max_val=1.5,
                fmt="%.2f",
                default=CFG.humanization.timing_scale_min,
                cb=lambda s, d: _set(CFG.humanization, "timing_scale_min", d),
            )
            _slider_with_tooltip(
                "Timing scale max",
                tag="cfg_hum_timing_scale_max",
                min_val=0.5,
                max_val=3.0,
                fmt="%.2f",
                default=CFG.humanization.timing_scale_max,
                cb=lambda s, d: _set(CFG.humanization, "timing_scale_max", d),
            )
        _slider_with_tooltip(
            "Extra delay chance",
            tag="cfg_hum_timing_extra_chance",
            min_val=0.0,
            max_val=1.0,
            fmt="%.2f",
            default=CFG.humanization.timing_extra_chance,
            cb=lambda s, d: _set(CFG.humanization, "timing_extra_chance", d),
        )
        with dpg.group(horizontal=True):
            _slider_with_tooltip(
                "Extra delay min (s)",
                tag="cfg_hum_timing_extra_min",
                min_val=0.0,
                max_val=1.0,
                fmt="%.3f",
                default=CFG.humanization.timing_extra_min,
                cb=lambda s, d: _set(CFG.humanization, "timing_extra_min", d),
            )
            _slider_with_tooltip(
                "Extra delay max (s)",
                tag="cfg_hum_timing_extra_max",
                min_val=0.0,
                max_val=3.0,
                fmt="%.3f",
                default=CFG.humanization.timing_extra_max,
                cb=lambda s, d: _set(CFG.humanization, "timing_extra_max", d),
            )

        dpg.add_spacer(height=8)
        dpg.add_text(tr("Mouse Trajectory (RESULT Stage)"), color=TEXT_MUTED)
        dpg.add_spacer(height=4)
        _slider_with_tooltip(
            "Curve amp (px)",
            tag="cfg_hum_mouse_amp",
            min_val=0.0,
            max_val=300.0,
            fmt="%.0f",
            default=CFG.humanization.mouse_move_curve_amplitude,
            cb=lambda s, d: _set_int(
                CFG.humanization,
                "mouse_move_curve_amplitude",
                d,
                "cfg_hum_mouse_amp",
                0,
            ),
        )
        with dpg.group(horizontal=True):
            _slider_with_tooltip(
                "Move dur min (s)",
                tag="cfg_hum_mouse_dur_min",
                min_val=0.05,
                max_val=0.5,
                fmt="%.2f",
                default=CFG.humanization.mouse_move_duration_min,
                cb=lambda s, d: _set(CFG.humanization, "mouse_move_duration_min", d),
            )
            _slider_with_tooltip(
                "Move dur max (s)",
                tag="cfg_hum_mouse_dur_max",
                min_val=0.1,
                max_val=1.0,
                fmt="%.2f",
                default=CFG.humanization.mouse_move_duration_max,
                cb=lambda s, d: _set(CFG.humanization, "mouse_move_duration_max", d),
            )
        with dpg.group(horizontal=True):
            _input_with_tooltip(
                "Click jitter X (px)",
                tag="cfg_hum_mouse_offset_x",
                width=120,
                default=CFG.humanization.mouse_offset_x,
                cb=lambda s, d: _set_int(
                    CFG.humanization, "mouse_offset_x", d, "cfg_hum_mouse_offset_x", 0
                ),
            )
            _input_with_tooltip(
                "Click jitter Y (px)",
                tag="cfg_hum_mouse_offset_y",
                width=120,
                default=CFG.humanization.mouse_offset_y,
                cb=lambda s, d: _set_int(
                    CFG.humanization, "mouse_offset_y", d, "cfg_hum_mouse_offset_y", 0
                ),
            )

        dpg.add_spacer(height=8)
        dpg.add_text(tr("Hook Reaction (WAITING Stage)"), color=TEXT_MUTED)
        dpg.add_spacer(height=4)
        with dpg.group(horizontal=True):
            _slider_with_tooltip(
                "Hook reaction min",
                tag="cfg_hum_hook_min",
                min_val=0.0,
                max_val=1.0,
                fmt="%.2f",
                default=CFG.humanization.hook_reaction_min,
                cb=lambda s, d: _set(CFG.humanization, "hook_reaction_min", d),
            )
            _slider_with_tooltip(
                "Hook reaction max",
                tag="cfg_hum_hook_max",
                min_val=0.05,
                max_val=2.0,
                fmt="%.2f",
                default=CFG.humanization.hook_reaction_max,
                cb=lambda s, d: _set(CFG.humanization, "hook_reaction_max", d),
            )
        _combo_with_tooltip(
            "Hook reaction dist",
            tag="cfg_hum_hook_dist",
            items=["uniform", "gaussian", "exponential"],
            default=CFG.humanization.hook_reaction_dist,
            cb=lambda s, d: _set(CFG.humanization, "hook_reaction_dist", d),
        )

        dpg.add_spacer(height=8)
        dpg.add_text(tr("Adaptive Focus (Dynamic Speedup)"), color=TEXT_MUTED)
        dpg.add_spacer(height=4)
        _checkbox_with_tooltip(
            "Adaptive focus",
            tag="cfg_hum_adaptive_enabled",
            default=CFG.humanization.adaptive_enabled,
            cb=lambda s, d: _set(CFG.humanization, "adaptive_enabled", d),
        )
        _slider_with_tooltip(
            "Latency focus min",
            tag="cfg_hum_latency_focus_min",
            min_val=0.1,
            max_val=1.0,
            fmt="%.2f",
            default=CFG.humanization.adaptive_latency_min_scale,
            cb=lambda s, d: _set(CFG.humanization, "adaptive_latency_min_scale", d),
        )
        _slider_with_tooltip(
            "Pulse gap focus min",
            tag="cfg_hum_gap_focus_min",
            min_val=0.1,
            max_val=1.0,
            fmt="%.2f",
            default=CFG.humanization.adaptive_pulse_gap_min_scale,
            cb=lambda s, d: _set(CFG.humanization, "adaptive_pulse_gap_min_scale", d),
        )
        _slider_with_tooltip(
            "Pulse hold focus max",
            tag="cfg_hum_hold_focus_max",
            min_val=1.0,
            max_val=2.5,
            fmt="%.2f",
            default=CFG.humanization.adaptive_pulse_hold_max_scale,
            cb=lambda s, d: _set(CFG.humanization, "adaptive_pulse_hold_max_scale", d),
        )


def _check_for_updates():
    dpg.set_value("cfg_system_update_status", tr("Checking for updates..."))
    dpg.hide_item("cfg_system_update_open")

    def _do_check():
        try:
            api_url = _validated_update_api_url()
            req = urllib.request.Request(
                api_url, headers={"User-Agent": "NTE-auto-fish"}
            )
            # The request target is a hard-coded HTTPS GitHub API URL validated above.
            with urllib.request.urlopen(req, timeout=5) as response:  # nosec B310
                data = json.loads(response.read().decode("utf-8"))
                latest_tag = data.get("tag_name", "").lstrip("v")
                html_url = data.get("html_url", "")

                current_ver = VERSION.lstrip("v")

                if current_ver != "Unknown" and latest_tag:
                    if _version_tuple(latest_tag) > _version_tuple(current_ver):
                        msg = tr(
                            "New version available: v{version}!", version=latest_tag
                        )
                        update_url = (
                            html_url if _is_trusted_release_url(html_url) else ""
                        )
                    else:
                        msg = tr(
                            "You are up to date! (v{version})", version=current_ver
                        )
                        update_url = ""
                else:
                    msg = tr("Failed to parse versions.")
                    update_url = ""

                _update_check_results.put((msg, update_url))
        except Exception as e:
            log.warning("Update check failed: %s", e)
            _update_check_results.put((tr("Check failed: {error}", error=e), ""))

    threading.Thread(target=_do_check, daemon=True).start()


def _apply_pending_update_check_results():
    while True:
        try:
            msg, update_url = _update_check_results.get_nowait()
        except queue.Empty:
            break

        dpg.set_value("cfg_system_update_status", msg)
        dpg.set_item_user_data("cfg_system_update_open", update_url)
        if update_url:
            dpg.show_item("cfg_system_update_open")
        else:
            dpg.hide_item("cfg_system_update_open")


def apply_pending_settings_actions() -> None:
    """Apply UI results produced by explicit settings-page actions."""
    _apply_pending_update_check_results()


def _build_system_settings():
    with dpg.group(tag="settings_group_system"):
        section_header("System & Updates", color=ACCENT)
        caption_text("Application updates and system settings.")
        dpg.add_spacer(height=8)

        _combo_with_tooltip(
            "Language",
            tag="cfg_language",
            items=list(LANGUAGE_LABELS.values()),
            default=language_label(CFG.language),
            cb=lambda s, d: _set_language_selection(d),
        )
        caption_text("Language changes take effect after restarting the application.")
        dpg.add_spacer(height=12)

        with dpg.group(horizontal=True):
            styled_button(
                "Check for Updates",
                "cfg_system_update_btn",
                callback=lambda: _check_for_updates(),
                variant="neutral",
                width=int(140 * _s),
                height=int(28 * _s),
            )
            styled_button(
                "Download Update",
                "cfg_system_update_open",
                callback=lambda s, a, u: webbrowser.open(u) if u else None,
                variant="primary",
                width=int(140 * _s),
                height=int(28 * _s),
                user_data="",
                show=False,
            )

        dpg.add_spacer(height=4)
        dpg.add_text("", tag="cfg_system_update_status", color=TEXT_MUTED)

        dpg.add_spacer(height=12)
        dpg.add_text(tr("Project Links"), color=TEXT_MUTED)
        with dpg.group(horizontal=True):
            styled_button(
                "View Releases",
                "btn_gh_releases",
                callback=lambda: webbrowser.open(
                    "https://github.com/Chizukuo/NTE-auto-fish/releases"
                ),
                variant="neutral",
                width=int(140 * _s),
                height=int(28 * _s),
            )
            dpg.add_spacer(width=int(8 * _s))
            styled_button(
                "Report Issue",
                "btn_gh_issues",
                callback=lambda: webbrowser.open(
                    "https://github.com/Chizukuo/NTE-auto-fish/issues"
                ),
                variant="neutral",
                width=int(140 * _s),
                height=int(28 * _s),
            )


# ---------------------------------------------------------------------------
# Helper widgets
# ---------------------------------------------------------------------------


def _slider_with_tooltip(
    label: str,
    tag: str,
    min_val: float,
    max_val: float,
    fmt: str,
    default: float,
    cb: Callable,
):
    dpg.add_slider_float(
        label=tr(label),
        tag=tag,
        min_value=min_val,
        max_value=max_val,
        format=fmt,
        width=-int(180 * _s),
        default_value=default,
        callback=cb,
    )
    _add_tooltip(tag, label)
    tip = _TOOLTIPS.get(label)
    if tip:
        caption_text(tip)
        dpg.add_spacer(height=4)


def _checkbox_with_tooltip(label: str, tag: str, default: bool, cb: Callable):
    dpg.add_checkbox(label=tr(label), tag=tag, default_value=default, callback=cb)
    _add_tooltip(tag, label)
    tip = _TOOLTIPS.get(label)
    if tip:
        caption_text(tip)
        dpg.add_spacer(height=4)


def _input_with_tooltip(
    label: str,
    tag: str,
    width: int,
    default,
    cb: Callable,
):
    dpg.add_input_int(
        label=tr(label), tag=tag, width=width, default_value=default, callback=cb
    )
    _add_tooltip(tag, label)
    tip = _TOOLTIPS.get(label)
    if tip:
        caption_text(tip)
        dpg.add_spacer(height=4)


def _text_input_with_tooltip(
    label: str,
    tag: str,
    width: int,
    default: str,
    cb: Callable,
):
    dpg.add_input_text(
        label=tr(label),
        tag=tag,
        width=width,
        default_value=default,
        on_enter=True,
        callback=cb,
    )
    _add_tooltip(tag, label)
    tip = _TOOLTIPS.get(label)
    if tip:
        caption_text(tip)
        dpg.add_spacer(height=4)


def _combo_with_tooltip(
    label: str,
    tag: str,
    items: list[str],
    default: str,
    cb: Callable,
):
    dpg.add_combo(
        label=tr(label),
        tag=tag,
        items=items,
        default_value=default,
        width=160,
        callback=cb,
    )
    _add_tooltip(tag, label)
    tip = _TOOLTIPS.get(label)
    if tip:
        caption_text(tip)
        dpg.add_spacer(height=4)


def _add_tooltip(tag: str, label: str):
    tip = _TOOLTIPS.get(label)
    if not tip:
        return
    with dpg.tooltip(tag):
        dpg.add_text(tr(tip), color=(200, 200, 210))


def _key_input(label: str, tag: str, default: str, attr: str):
    dpg.add_input_text(
        label=tr(label),
        tag=tag,
        width=140,
        default_value=default,
        on_enter=True,
        callback=lambda s, d: _set_key(attr, d, tag),
    )


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


def _save(bridge: BotBridge):
    CFG.save()
    log.info("Settings saved.")


def _on_reset(
    bridge: BotBridge,
    on_hotkeys_changed: Callable[[], None] | None = None,
):
    CFG.reset()
    update_settings_ui(bridge)
    if on_hotkeys_changed:
        on_hotkeys_changed()
    log.info("Settings reset to defaults.")


def update_settings_ui(bridge: BotBridge):
    if not dpg.does_item_exist("page_settings") or not dpg.is_item_shown(
        "page_settings"
    ):
        return

    _apply_pending_update_check_results()

    status = bridge.latest_status()
    scale_sq = status.current_scale * status.current_scale
    if dpg.does_item_exist("cfg_vision_min_area"):
        dpg.set_value("cfg_vision_min_area", CFG.detection_min_area * scale_sq)

    if _session_manager is not None and dpg.does_item_exist("session_list_window"):
        global _last_known_active_id
        active_id = _session_manager.active_session_id()
        if active_id != _last_known_active_id:
            _last_known_active_id = active_id
            _rebuild_session_list()
        elif active_id and dpg.does_item_exist(f"session_text_{active_id}"):
            count = _session_manager.active_fish_count()
            start = _session_manager.active_session_start()
            label = f"● {start[:16]} · {tr('{count} fish', count=count)}"
            dpg.set_value(f"session_text_{active_id}", label)

    dpg.set_value("cfg_pid_kp", CFG.pid.kp)
    dpg.set_value("cfg_pid_ki", CFG.pid.ki)
    dpg.set_value("cfg_pid_kd", CFG.pid.kd)
    dpg.set_value("cfg_pid_deadband", CFG.pid.deadband)
    dpg.set_value("cfg_pid_integral_limit", CFG.pid.integral_limit)
    dpg.set_value("cfg_pid_adaptive", CFG.pid.adaptive)

    dpg.set_value("cfg_hsv_sz_lower", list(CFG.hsv.safe_zone.lower))
    dpg.set_value("cfg_hsv_sz_upper", list(CFG.hsv.safe_zone.upper))
    dpg.set_value("cfg_hsv_cur_lower", list(CFG.hsv.cursor.lower))
    dpg.set_value("cfg_hsv_cur_upper", list(CFG.hsv.cursor.upper))
    dpg.set_value("cfg_hsv_bl_lower", list(CFG.hsv.blue.lower))
    dpg.set_value("cfg_hsv_bl_upper", list(CFG.hsv.blue.upper))
    update_hsv_preview("cfg_hsv_sz", CFG.hsv.safe_zone)
    update_hsv_preview("cfg_hsv_cur", CFG.hsv.cursor)
    update_hsv_preview("cfg_hsv_bl", CFG.hsv.blue)
    dpg.set_value("cfg_roi_ignore_margin", CFG.roi.ignore_margin_ratio)
    dpg.set_value("cfg_min_blue", CFG.min_blue_pixels)
    for _tag, _attr in (
        ("cfg_roi_bar_x", "bar_offset_x"),
        ("cfg_roi_bar_y", "bar_offset_y"),
        ("cfg_roi_bar_w", "bar_width_delta"),
        ("cfg_roi_bar_h", "bar_height_delta"),
        ("cfg_roi_btn_x", "button_offset_x"),
        ("cfg_roi_btn_y", "button_offset_y"),
        ("cfg_roi_icon_x", "icon_offset_x"),
        ("cfg_roi_icon_y", "icon_offset_y"),
        ("cfg_roi_btn_w", "button_width_delta"),
        ("cfg_roi_btn_h", "button_height_delta"),
        ("cfg_roi_icon_w", "icon_width_delta"),
        ("cfg_roi_icon_h", "icon_height_delta"),
    ):
        dpg.set_value(_tag, getattr(CFG.roi, _attr))
    dpg.set_value("cfg_battle_cursor", CFG.battle_detect_cursor)
    dpg.set_value("cfg_battle_safe_zone", CFG.battle_detect_safe_zone)
    dpg.set_value("cfg_spam_cast", CFG.spam_cast_enabled)
    dpg.set_value("cfg_profile_auto", CFG.profile_auto_switch)
    dpg.set_value("cfg_gauge_assist", CFG.gauge_assist_enabled)
    _refresh_profile_combo(CFG.active_profile)
    dpg.set_value("cfg_spam_min", CFG.spam_cast_interval_min)
    dpg.set_value("cfg_spam_max", CFG.spam_cast_interval_max)
    dpg.set_value("cfg_fish_logging_enabled", CFG.fish_logging_enabled)

    dpg.set_value("cfg_timing_cast", CFG.timing.cast_animation_secs)
    dpg.set_value("cfg_timing_bite", CFG.timing.bite_timeout_secs)
    dpg.set_value("cfg_timing_lost", CFG.timing.lost_frames_threshold)
    dpg.set_value("cfg_timing_result", CFG.timing.result_wait_secs)
    dpg.set_value("cfg_timing_key_press", CFG.timing.key_press_duration)
    dpg.set_value("cfg_timing_wait_poll", CFG.timing.waiting_poll_interval)
    dpg.set_value("cfg_timing_track_poll", CFG.timing.struggling_poll_interval)
    dpg.set_value("cfg_timing_bait_err", CFG.timing.bait_error_threshold)
    dpg.set_value("cfg_timing_max_struggle", CFG.timing.max_struggle_secs)

    dpg.set_value("cfg_key_cast", CFG.keys.cast)
    dpg.set_value("cfg_key_left", CFG.keys.left)
    dpg.set_value("cfg_key_right", CFG.keys.right)
    dpg.set_value("cfg_key_exit", CFG.keys.exit)
    dpg.set_value(
        "cfg_result_close_method", _result_method_label(CFG.result_close_method)
    )
    dpg.set_value("cfg_always_on_top", CFG.always_on_top)
    dpg.set_value("cfg_debug_mode", CFG.debug_mode)
    dpg.set_value("cfg_tracker_preview", CFG.tracker_preview_enabled)
    if dpg.does_item_exist("pv_live"):
        dpg.set_value("pv_live", CFG.tracker_preview_enabled)
    dpg.set_value("cfg_bait_error_detect", CFG.bait_error_detection_enabled)

    if dpg.does_item_exist("cfg_language"):
        dpg.set_value("cfg_language", language_label(CFG.language))

    monitors = _monitor_labels()
    idx = min(CFG.monitor_index, len(monitors) - 1)
    dpg.set_value("cfg_monitor_index", monitors[idx])
    dpg.set_value("cfg_monitor_auto_select", CFG.monitor_auto_select)

    dpg.set_value("cfg_hotkey_toggle", CFG.hotkeys.toggle)
    dpg.set_value("cfg_hotkey_stop", CFG.hotkeys.stop)

    dpg.set_value("cfg_hum_enabled", CFG.humanization.enabled)
    dpg.set_value("cfg_hum_pulse_hold_min", CFG.humanization.pulse_hold_min)
    dpg.set_value("cfg_hum_pulse_hold_max", CFG.humanization.pulse_hold_max)
    dpg.set_value("cfg_hum_pulse_release_min", CFG.humanization.pulse_release_min)
    dpg.set_value("cfg_hum_pulse_release_max", CFG.humanization.pulse_release_max)
    dpg.set_value("cfg_hum_db_tap", CFG.humanization.deadband_tap_enabled)
    dpg.set_value(
        "cfg_hum_db_battle_chance",
        CFG.humanization.deadband_play_battle_chance,
    )
    dpg.set_value("cfg_hum_db_chance", CFG.humanization.deadband_tap_chance)
    dpg.set_value("cfg_hum_react_min", CFG.humanization.reaction_latency_min)
    dpg.set_value("cfg_hum_react_max", CFG.humanization.reaction_latency_max)
    dpg.set_value("cfg_hum_react_dist", CFG.humanization.reaction_latency_dist)
    dpg.set_value("cfg_hum_noise_enabled", CFG.humanization.pid_noise_enabled)
    dpg.set_value("cfg_hum_noise_amp", CFG.humanization.pid_noise_amplitude)
    dpg.set_value("cfg_hum_noise_dist", CFG.humanization.pid_noise_dist)
    dpg.set_value("cfg_hum_move_scale_min", CFG.humanization.movement_scale_min)
    dpg.set_value("cfg_hum_move_scale_max", CFG.humanization.movement_scale_max)
    dpg.set_value("cfg_hum_slow_chance", CFG.humanization.slow_move_chance)
    dpg.set_value("cfg_hum_slow_hold_scale", CFG.humanization.slow_move_hold_scale_max)
    dpg.set_value("cfg_hum_slow_gap_scale", CFG.humanization.slow_move_gap_scale)
    dpg.set_value("cfg_hum_flick_chance", CFG.humanization.flick_chance_on_reverse)
    dpg.set_value("cfg_hum_flick_hold_scale", CFG.humanization.flick_hold_scale_max)
    dpg.set_value("cfg_hum_flick_gap_scale", CFG.humanization.flick_gap_scale)
    dpg.set_value("cfg_hum_random_action_chance", CFG.humanization.random_action_chance)
    dpg.set_value("cfg_hum_timing_scale_min", CFG.humanization.timing_scale_min)
    dpg.set_value("cfg_hum_timing_scale_max", CFG.humanization.timing_scale_max)
    dpg.set_value("cfg_hum_timing_extra_chance", CFG.humanization.timing_extra_chance)
    dpg.set_value("cfg_hum_timing_extra_min", CFG.humanization.timing_extra_min)
    dpg.set_value("cfg_hum_timing_extra_max", CFG.humanization.timing_extra_max)
    dpg.set_value("cfg_hum_adaptive_enabled", CFG.humanization.adaptive_enabled)
    dpg.set_value(
        "cfg_hum_latency_focus_min", CFG.humanization.adaptive_latency_min_scale
    )
    dpg.set_value(
        "cfg_hum_gap_focus_min", CFG.humanization.adaptive_pulse_gap_min_scale
    )
    dpg.set_value(
        "cfg_hum_hold_focus_max", CFG.humanization.adaptive_pulse_hold_max_scale
    )

    dpg.set_value("cfg_hum_mouse_amp", CFG.humanization.mouse_move_curve_amplitude)
    dpg.set_value("cfg_hum_mouse_dur_min", CFG.humanization.mouse_move_duration_min)
    dpg.set_value("cfg_hum_mouse_dur_max", CFG.humanization.mouse_move_duration_max)
    dpg.set_value("cfg_hum_mouse_offset_x", CFG.humanization.mouse_offset_x)
    dpg.set_value("cfg_hum_mouse_offset_y", CFG.humanization.mouse_offset_y)
    dpg.set_value("cfg_hum_hook_min", CFG.humanization.hook_reaction_min)
    dpg.set_value("cfg_hum_hook_max", CFG.humanization.hook_reaction_max)
    dpg.set_value("cfg_hum_hook_dist", CFG.humanization.hook_reaction_dist)


def _set_scaled_min_area(val, bridge: BotBridge):
    status = bridge.latest_status()
    scale_sq = status.current_scale * status.current_scale
    if scale_sq > 0:
        CFG.detection_min_area = val / scale_sq
    else:
        CFG.detection_min_area = val


def _on_top_changed(val):
    CFG.always_on_top = val
    dpg.configure_viewport(0, always_on_top=val)


def _set(obj, attr: str, val):
    setattr(obj, attr, val)


def _set_int(obj, attr: str, val, tag: str, minimum: int):
    next_value = max(minimum, int(val))
    setattr(obj, attr, next_value)
    if next_value != val:
        dpg.set_value(tag, next_value)


def _set_key(attr: str, val: str, tag: str):
    normalized = val.strip().lower()
    if normalized:
        setattr(CFG.keys, attr, normalized)
    else:
        dpg.set_value(tag, getattr(CFG.keys, attr))


def _set_monitor(selected: str, monitors: list[str]):
    try:
        CFG.monitor_index = monitors.index(selected)
    except ValueError:
        CFG.monitor_index = 0


def _set_language_selection(label: str) -> None:
    CFG.language = language_from_label(label)


def _set_result_method(label: str) -> None:
    for source_label, method in _RESULT_METHODS.items():
        if tr(source_label) == label:
            CFG.result_close_method = method
            return


def _set_hotkey(
    attr: str,
    val: str,
    bridge: BotBridge,
    on_hotkeys_changed: Callable[[], None] | None,
):
    normalized = val.strip().lower()
    setattr(CFG.hotkeys, attr, normalized)
    if on_hotkeys_changed:
        on_hotkeys_changed()
    bridge.push_log(f"Hotkey updated: {attr}={normalized or 'disabled'}")


def _result_method_label(value: str) -> str:
    for label, method in _RESULT_METHODS.items():
        if method == value:
            return tr(label)
    return tr("Click center")


def _monitor_labels():
    labels = []

    for i, m in enumerate(get_monitors()):
        primary = f" ({tr('Primary')})" if m.is_primary else ""

        labels.append(
            f"{tr('Monitor {index}', index=i)}{primary} - {m.width}x{m.height}"
        )

    return labels
