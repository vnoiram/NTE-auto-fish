"""Dashboard page — status cards, controls, PID plot, telemetry, visual tracker."""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable

import dearpygui.dearpygui as dpg
import numpy as np

from config import CFG
from gui.bridge import BotBridge, BotStatus
from gui.components import (
    apply_glass_card_theme,
    caption_text,
    metric_row,
    section_header,
    styled_button,
)
from gui.i18n import tr
from modules.preview import BAR_SIZE, BUTTON_SIZE, ICON_SIZE, OCR_SIZE
from gui.theme import (
    ACCENT,
    ACCENT_BLUE,
    CARD_GAP,
    CARD_PADDING,
    STATE_PAUSED,
    STATE_PAUSED_ACTIVE,
    STATE_PAUSED_HOVER,
    STATE_RUNNING,
    STATE_RUNNING_ACTIVE,
    STATE_RUNNING_HOVER,
    STATE_STOPPED,
    STATE_STOPPED_ACTIVE,
    STATE_STOPPED_HOVER,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_VERY_MUTED,
    VIS_CURSOR,
    VIS_CURSOR_DOT,
    VIS_SAFE_ZONE,
    VIS_SAFE_ZONE_BD,
    VIS_TRACK,
    build_button_theme,
)
from gui.theme import _ui_scale as _s
from modules.logic import FishingState

# ---------------------------------------------------------------------------
# Module state
# ---------------------------------------------------------------------------

_pid_history: deque[float] = deque([0.0] * 120, maxlen=120)
_card_tags = ["state_card", "fish_card", "time_card", "fps_card"]
_cards_resized = False

# Cached themes
_theme_running: int | None = None
_theme_paused: int | None = None
_theme_stopped: int | None = None
_theme_start: int | None = None
_theme_pause: int | None = None
_theme_stop: int | None = None
_theme_calibrate: int | None = None
log = logging.getLogger("NTEFish")


def _ensure_themes():
    global _theme_running, _theme_paused, _theme_stopped
    global _theme_start, _theme_pause, _theme_stop, _theme_calibrate
    if _theme_running is None:
        _theme_running = _state_button_theme(
            STATE_RUNNING,
            STATE_RUNNING_HOVER,
            STATE_RUNNING_ACTIVE,
        )
        _theme_paused = _state_button_theme(
            STATE_PAUSED,
            STATE_PAUSED_HOVER,
            STATE_PAUSED_ACTIVE,
        )
        _theme_stopped = _state_button_theme(
            STATE_STOPPED,
            STATE_STOPPED_HOVER,
            STATE_STOPPED_ACTIVE,
        )
        _theme_start = build_button_theme("primary")
        _theme_pause = build_button_theme("warning")
        _theme_stop = build_button_theme("danger")
        _theme_calibrate = build_button_theme("neutral")


def _state_button_theme(bg, hovered, active) -> int:
    with dpg.theme() as theme, dpg.theme_component(dpg.mvButton):
        dpg.add_theme_color(dpg.mvThemeCol_Button, bg)
        dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, hovered)
        dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, active)
        dpg.add_theme_color(dpg.mvThemeCol_Text, (255, 255, 255, 255))
        dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6 * _s)
    return theme


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def create_dashboard(
    bridge: BotBridge,
    on_start: Callable[[], None] | None = None,
    on_stop: Callable[[], None] | None = None,
    on_recalibrate: Callable[[], None] | None = None,
):
    # State is handled by _resize_stat_cards directly now

    # ── Row 1: Status metric cards ──────────────────────────────────────
    # Initial width is a placeholder; update_dashboard_ui resizes on first frame.
    _init_w = 200
    _gap = int(CARD_GAP * _s)
    with dpg.group(horizontal=True, tag="stat_cards_row"):
        _create_stat_card("state_card", "STATE", "Idle", width=_init_w)
        dpg.add_spacer(width=_gap)
        _create_stat_card("fish_card", "FISH CAUGHT", "0", width=_init_w)
        dpg.add_spacer(width=_gap)
        _create_stat_card("time_card", "SESSION TIME", "00:00:00", width=_init_w)
        dpg.add_spacer(width=_gap)
        _create_stat_card("fps_card", "FPS", "0.0", width=_init_w)

    dpg.add_spacer(height=_gap)

    with dpg.child_window(
        height=int(60 * _s),
        tag="control_bar",
        border=True,
        no_scrollbar=True,
    ):
        apply_glass_card_theme("control_bar")
        with dpg.group(horizontal=True):
            styled_button(
                "Start",
                "btn_start_bot",
                callback=lambda s, a, u: _run_callback(on_start, bridge, "resume"),
                variant="primary",
                width=int(80 * _s),
                height=int(28 * _s),
            )
            dpg.add_spacer(width=int(8 * _s))
            styled_button(
                "Pause",
                "btn_pause_bot",
                callback=lambda s, a, u: bridge.send_cmd("pause"),
                variant="warning",
                width=int(80 * _s),
                height=int(28 * _s),
            )
            dpg.add_spacer(width=int(8 * _s))
            styled_button(
                "Stop",
                "btn_stop_bot",
                callback=lambda s, a, u: _run_callback(on_stop, bridge, "stop"),
                variant="danger",
                width=int(80 * _s),
                height=int(28 * _s),
            )
            dpg.add_spacer(width=int(8 * _s))
            styled_button(
                "Calibrate",
                "btn_recalibrate",
                callback=lambda s, a, u: _run_callback(
                    on_recalibrate, bridge, "recalibrate"
                ),
                variant="neutral",
                width=int(90 * _s),
                height=int(28 * _s),
            )
            dpg.add_spacer(width=int(24 * _s))
            dpg.add_text(tr("Ready"), tag="stat_status_message", color=TEXT_MUTED)

    dpg.add_spacer(height=CARD_GAP)

    # ── Row 3: left = compact PID plot + telemetry, right = Vision tracker ─
    # The tracker (live previews) gets the remaining width; the PID plot stays small.
    _left_w = int(320 * _s)
    with dpg.group(horizontal=True):
        with dpg.child_window(
            width=_left_w,
            height=-1,
            tag="left_col",
            border=False,
            no_scrollbar=True,
        ):
            with dpg.child_window(
                height=int(170 * _s),
                tag="pid_card",
                border=True,
                no_scrollbar=True,
            ):
                apply_glass_card_theme("pid_card")
                section_header("PID Output", color=ACCENT)
                with dpg.plot(
                    no_title=True,
                    no_menus=True,
                    no_box_select=True,
                    height=-1,
                    width=-1,
                    tag="pid_plot",
                ):
                    dpg.add_plot_axis(
                        dpg.mvXAxis, no_gridlines=True, no_tick_labels=True
                    )
                    with dpg.plot_axis(dpg.mvYAxis, tag="pid_y"):
                        dpg.add_line_series(
                            list(range(120)),
                            list(_pid_history),
                            label=tr("Output"),
                            tag="pid_series",
                        )
                    dpg.set_axis_limits("pid_y", -110, 110)

            dpg.add_spacer(height=int(CARD_GAP * _s))

            # Telemetry card
            with dpg.child_window(
                height=-1,
                tag="telemetry_card",
                border=True,
            ):
                apply_glass_card_theme("telemetry_card")
                section_header("Telemetry", color=ACCENT_BLUE)
                metric_row("Cursor X", "tele_cursor_x")
                metric_row("Target X", "tele_target_x")
                metric_row("PID output", "stat_pid_output", "0.000")
                metric_row("Lost frames", "stat_lost_frames", "0")
                metric_row("Cursor lost", "tele_lost_cursor")
                metric_row("Target lost", "tele_lost_target")
                metric_row("Button ROI", "tele_button_roi")
                metric_row("Bar ROI", "tele_bar_roi")
                metric_row("Threshold", "tele_min_area")
                metric_row("Scale factor", "tele_scale")

        dpg.add_spacer(width=int(CARD_GAP * _s))

        # Right: Vision tracker card
        with dpg.child_window(
            height=-1,
            tag="vision_card",
            border=True,
        ):
            apply_glass_card_theme("vision_card")
            section_header("Vision Tracker", color=ACCENT)
            _create_visualizer()
            _create_previews()


# ---------------------------------------------------------------------------
# Update (called every frame)
# ---------------------------------------------------------------------------


def update_dashboard_ui(bridge: BotBridge):
    status = bridge.latest_status()
    bind_preview_drag(bridge)
    if not status.is_stopped and bridge.preview_active:
        bridge.preview_active = False  # the running bot takes over the previews
    _refresh_area_check_button()
    _set_enabled("btn_area_check", status.is_stopped and not bridge.snapshot_busy)
    _set_enabled("btn_area_retake", status.is_stopped and bridge.preview_active)

    # Resize stat cards to fill the row dynamically on window resize.
    _resize_stat_cards()

    # Stat cards
    dpg.set_value("state_card_value", _state_label(status.state))
    dpg.set_value("fish_card_value", str(status.fish_count))
    secs = int(status.session_secs)
    h, m, s = secs // 3600, (secs % 3600) // 60, secs % 3600 % 60
    dpg.set_value("time_card_value", f"{h:02d}:{m:02d}:{s:02d}")
    dpg.set_value("fps_card_value", f"{status.fps:.1f}")

    # Status message
    dpg.set_value("stat_status_message", _status_message(status))

    # Telemetry
    dpg.set_value("stat_pid_output", f"{status.pid_output:.3f}")
    dpg.set_value("stat_lost_frames", str(status.lost_frames))
    dpg.set_value("tele_cursor_x", _fmt_optional(status.cursor_x))
    dpg.set_value("tele_target_x", _fmt_optional(status.target_x))
    dpg.set_value("tele_lost_cursor", str(status.lost_cursor_frames))
    dpg.set_value("tele_lost_target", str(status.lost_target_frames))
    dpg.set_value("tele_button_roi", _fmt_roi(status.button_roi))
    dpg.set_value("tele_bar_roi", _fmt_roi(status.bar_roi))
    dpg.set_value("tele_min_area", f"{status.scaled_min_area:.1f} px")
    dpg.set_value("tele_scale", f"{status.current_scale:.3f}x")

    # Button states
    _set_enabled("btn_start_bot", not status.is_running)
    _set_enabled("btn_pause_bot", not status.is_stopped and status.is_running)
    _set_enabled("btn_stop_bot", not status.is_stopped)
    _set_enabled("btn_recalibrate", not status.is_stopped and not status.is_running)

    # PID plot
    _pid_history.append(status.pid_output)
    dpg.set_value("pid_series", [list(range(len(_pid_history))), list(_pid_history)])

    # Visualizer
    _update_visualizer(status)
    _update_previews(bridge)


_last_container_w = 0


def _resize_stat_cards():
    """Calculate card width from actual container size and apply dynamically."""
    global _last_container_w
    try:
        container_w = dpg.get_item_rect_size("page_container")[0]
    except Exception:
        log.debug("Failed to read page_container size for card resize.", exc_info=True)
        return
    if container_w <= 0 or container_w == _last_container_w:
        return
    _last_container_w = container_w
    gap = int(CARD_GAP * _s)
    pad = int(CARD_PADDING * _s)
    usable = container_w - 3 * gap - 2 * pad
    card_w = max(int(120 * _s), usable // 4)
    for tag in _card_tags:
        try:
            dpg.configure_item(tag, width=card_w)
        except Exception:
            log.debug("Failed to resize stat card: %s", tag, exc_info=True)


# ---------------------------------------------------------------------------
# Visualizer
# ---------------------------------------------------------------------------


_PREVIEW_TEXTURES = {
    "pv_bar": BAR_SIZE,
    "pv_button": BUTTON_SIZE,
    "pv_icons": ICON_SIZE,
    "pv_ocr_name": OCR_SIZE,
    "pv_ocr_weight": OCR_SIZE,
}
_last_preview_version = -1


def _create_previews():
    """Live capture previews: bar, bite prompt and the OCR source images."""
    with dpg.texture_registry():
        for tag, (w, h) in _PREVIEW_TEXTURES.items():
            dpg.add_dynamic_texture(w, h, [0.0] * (w * h * 4), tag=f"{tag}_tex")
    _create_drag_handlers()
    dpg.add_checkbox(
        label=tr("Live view while the bot runs"),
        tag="pv_live",
        default_value=CFG.tracker_preview_enabled,
        callback=lambda s, v: setattr(CFG, "tracker_preview_enabled", bool(v)),
    )
    dpg.add_button(
        label=tr("Check and adjust areas"),
        tag="btn_area_check",
        callback=_toggle_area_check,
    )
    dpg.add_button(
        label=tr("Retake snapshot"), tag="btn_area_retake", callback=_retake_snapshot
    )
    dpg.add_text("", tag="pv_pump_status")
    dpg.add_slider_float(
        label=tr("Preview zoom"),
        tag="pv_zoom",
        min_value=_ZOOM_MIN,
        max_value=_ZOOM_MAX,
        default_value=_zoom(),
        format="%.1fx",
        width=int(220 * _s),
        callback=lambda s, v: _set_zoom(v),
    )
    dpg.add_spacer(height=int(6 * _s))
    caption_text(
        "Press \"Check and adjust areas\" while the bot is stopped, then drag a preview "
        "image to shift its scan area (the area follows your drag). "
        "Fine tuning and resizing: Settings > Vision & Detection."
    )
    caption_text(
        "Live capture: green = safe zone color match, yellow = cursor color match, "
        "magenta = bite color match. Red line = cursor, green box = safe zone."
    )
    dpg.add_text(tr("Bar area"), color=TEXT_MUTED)
    dpg.add_image("pv_bar_tex", tag="pv_bar", width=BAR_SIZE[0], height=BAR_SIZE[1])
    dpg.add_text("", tag="pv_judge_text", wrap=int(480 * _s))
    dpg.add_text(tr("Bite prompt area"), color=TEXT_MUTED)
    with dpg.group(horizontal=True):
        dpg.add_image(
            "pv_button_tex", tag="pv_button", width=BUTTON_SIZE[0], height=BUTTON_SIZE[1]
        )
        dpg.add_text("", tag="pv_blue_text")
    dpg.add_text(tr("Cast check area (action-bar icons)"), color=TEXT_MUTED)
    dpg.add_image(
        "pv_icons_tex", tag="pv_icons", width=ICON_SIZE[0], height=ICON_SIZE[1]
    )
    dpg.add_text("", tag="pv_icons_text")
    dpg.add_text(tr("OCR source (top: crop, bottom: binarized)"), color=TEXT_MUTED)
    with dpg.group(horizontal=True):
        with dpg.group():
            dpg.add_image(
                "pv_ocr_name_tex", tag="pv_ocr_name", width=OCR_SIZE[0], height=OCR_SIZE[1]
            )
            dpg.add_text("", tag="pv_ocr_name_text")
        with dpg.group():
            dpg.add_image(
                "pv_ocr_weight_tex",
                tag="pv_ocr_weight",
                width=OCR_SIZE[0],
                height=OCR_SIZE[1],
            )
            dpg.add_text("", tag="pv_ocr_weight_text")
    _apply_zoom()


# Drag a preview to shift its scan area: key -> (config attrs for x/y offsets, size)
_DRAG_AREAS = {
    "pv_bar": ("bar_offset_x", "bar_offset_y", "cfg_roi_bar_x", "cfg_roi_bar_y", BAR_SIZE),
    "pv_button": (
        "button_offset_x",
        "button_offset_y",
        "cfg_roi_btn_x",
        "cfg_roi_btn_y",
        BUTTON_SIZE,
    ),
}
_drag_state: dict = {"target": None, "start": None}
_drag_bridge: BotBridge | None = None


def bind_preview_drag(bridge: BotBridge) -> None:
    """Let the dashboard know where the live scan-area sizes come from."""
    global _drag_bridge
    _drag_bridge = bridge


def _create_drag_handlers() -> None:
    with dpg.handler_registry():
        dpg.add_mouse_drag_handler(button=0, threshold=2.0, callback=_on_preview_drag)
        dpg.add_mouse_release_handler(button=0, callback=_on_preview_release)
        dpg.add_mouse_wheel_handler(callback=_on_preview_wheel)


_ZOOM_MIN, _ZOOM_MAX = 0.5, 3.0
_PREVIEW_IMAGES = {
    "pv_bar": BAR_SIZE,
    "pv_button": BUTTON_SIZE,
    "pv_icons": ICON_SIZE,
    "pv_ocr_name": OCR_SIZE,
    "pv_ocr_weight": OCR_SIZE,
}


def _zoom() -> float:
    return max(_ZOOM_MIN, min(_ZOOM_MAX, float(CFG.tracker_preview_zoom)))


def _apply_zoom() -> None:
    """Resize the displayed preview images (the textures themselves stay small)."""
    z = _zoom()
    for tag, (w, h) in _PREVIEW_IMAGES.items():
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, width=int(w * z), height=int(h * z))


def _set_zoom(value: float) -> None:
    CFG.tracker_preview_zoom = max(_ZOOM_MIN, min(_ZOOM_MAX, round(float(value), 2)))
    if dpg.does_item_exist("pv_zoom"):
        dpg.set_value("pv_zoom", CFG.tracker_preview_zoom)
    _apply_zoom()


def _on_preview_wheel(sender, app_data) -> None:
    """Mouse wheel over a preview image zooms all previews."""
    if any(
        dpg.does_item_exist(tag) and _over_preview(tag) for tag in _PREVIEW_IMAGES
    ):
        _set_zoom(_zoom() + 0.1 * (1 if app_data > 0 else -1))


def _toggle_area_check(sender=None, app_data=None) -> None:
    """Start/stop live previews of the scan areas while the bot is stopped."""
    if _drag_bridge is None or _drag_bridge.snapshot_busy:
        return  # a second press while the snapshot is being taken must not switch it off
    _drag_bridge.preview_active = not _drag_bridge.preview_active
    if _drag_bridge.preview_active:
        _drag_bridge.snapshot_request = True  # one screenshot; adjusting then needs no capture
    _drag_bridge.preview["pump_status"] = (
        "Request sent. Hiding the window and capturing (a few seconds)..."
        if _drag_bridge.preview_active
        else ""
    )
    _drag_bridge.preview["version"] += 1
    _refresh_area_check_button()


def _retake_snapshot(sender=None, app_data=None) -> None:
    if _drag_bridge is not None and _drag_bridge.preview_active:
        if _drag_bridge.snapshot_busy:
            return
        _drag_bridge.snapshot_request = True
        _drag_bridge.preview["pump_status"] = "Request sent. Capturing again..."
        _drag_bridge.preview["version"] += 1


def _refresh_area_check_button() -> None:
    if _drag_bridge is None or not dpg.does_item_exist("btn_area_check"):
        return
    if _drag_bridge.preview_active:
        label = tr("Stop checking areas")
    else:
        label = tr("Check and adjust areas")
    dpg.configure_item("btn_area_check", label=label)


def _tr_status(text: str) -> str:
    """Translate the pump's status line (it may end with a size and a time)."""
    if text.startswith("Snapshot ready"):
        return tr("Snapshot ready") + text[len("Snapshot ready"):]
    return tr(text) if text else text


def _over_preview(tag: str) -> bool:
    """Hovered, or the mouse is inside the image rectangle (images may not report hover)."""
    try:
        if dpg.is_item_hovered(tag):
            return True
        x0, y0 = dpg.get_item_rect_min(tag)
        w, h = dpg.get_item_rect_size(tag)
        mx, my = dpg.get_mouse_pos(local=False)
        return x0 <= mx <= x0 + w and y0 <= my <= y0 + h
    except Exception:
        return False


def _on_preview_release(sender=None, app_data=None) -> None:
    _drag_state["target"] = None
    _drag_state["start"] = None


def _on_preview_drag(sender, app_data) -> None:
    if _drag_bridge is None:
        return
    if _drag_bridge.latest_status().is_stopped and not _drag_bridge.preview_active:
        return  # adjusting needs the area check (or a running bot)
    _, dx, dy = app_data
    if _drag_state["target"] is None:
        for tag in _DRAG_AREAS:
            if dpg.does_item_exist(tag) and _over_preview(tag):
                x_attr, y_attr = _DRAG_AREAS[tag][:2]
                _drag_state["target"] = tag
                _drag_state["start"] = (
                    getattr(CFG.roi, x_attr),
                    getattr(CFG.roi, y_attr),
                )
                break
        else:
            return
    tag = _drag_state["target"]
    x_attr, y_attr, x_tag, y_tag, size = _DRAG_AREAS[tag]
    status = _drag_bridge.latest_status()
    roi = status.bar_roi if tag == "pv_bar" else status.button_roi
    if roi[2] <= 0 or roi[3] <= 0:
        # the bot has not been calibrated yet: use the preview pump's geometry
        roi = _drag_bridge.preview["bar_roi" if tag == "pv_bar" else "button_roi"]
        if roi is None or roi[2] <= 0 or roi[3] <= 0:
            return
    # displayed pixels -> screen pixels; the area moves opposite to the content
    z = _zoom()
    shift_x = dx * roi[2] / (size[0] * z)
    shift_y = dy * roi[3] / (size[1] * z)
    start_x, start_y = _drag_state["start"]
    new_x = int(round(start_x - shift_x))
    new_y = int(round(start_y - shift_y))
    setattr(CFG.roi, x_attr, new_x)
    setattr(CFG.roi, y_attr, new_y)
    for item_tag, value in ((x_tag, new_x), (y_tag, new_y)):
        if dpg.does_item_exist(item_tag):
            dpg.set_value(item_tag, max(-600, min(600, value)))


def _set_texture(tag: str, rgba) -> None:
    if rgba is None:
        return
    data = (np.asarray(rgba, dtype=np.float32) / 255.0).ravel()
    try:
        dpg.set_value(f"{tag}_tex", data)
    except Exception:
        dpg.set_value(f"{tag}_tex", data.tolist())


def _update_previews(bridge: BotBridge) -> None:
    global _last_preview_version
    pv = bridge.preview
    if pv["version"] == _last_preview_version:
        return
    _last_preview_version = pv["version"]
    try:
        for tag, key in (
            ("pv_bar", "bar"),
            ("pv_button", "button"),
            ("pv_icons", "icons"),
            ("pv_ocr_name", "ocr_name"),
            ("pv_ocr_weight", "ocr_weight"),
        ):
            _set_texture(tag, pv[key])
        dpg.set_value(
            "pv_blue_text", f"blue {pv['blue_pixels']} / {pv['blue_threshold']}"
        )
        dpg.set_value("pv_icons_text", pv["icons_text"])
        dpg.set_value("pv_ocr_name_text", pv["ocr_name_text"])
        dpg.set_value("pv_ocr_weight_text", pv["ocr_weight_text"])
    except Exception:
        log.debug("Failed to update tracker previews.", exc_info=True)


def _create_visualizer():
    vis_h = int(72 * _s)
    with dpg.drawlist(width=1, height=vis_h, tag="visualizer"):
        dpg.draw_rectangle(
            (0, 0),
            (1, 1),
            color=(70, 75, 82),
            fill=VIS_TRACK,
            rounding=17,
            tag="vis_track",
        )
        dpg.draw_line(
            (0, 0),
            (0, 1),
            color=(88, 96, 105),
            thickness=2,
            tag="vis_center",
        )
        dpg.draw_rectangle(
            (0, 0),
            (1, 1),
            color=VIS_SAFE_ZONE_BD,
            fill=VIS_SAFE_ZONE,
            rounding=12,
            tag="vis_safe_zone",
        )
        dpg.draw_line(
            (0, 0),
            (0, 1),
            color=VIS_CURSOR,
            thickness=5,
            tag="vis_cursor",
        )
        dpg.draw_circle(
            (0, 0),
            8,
            color=VIS_CURSOR_DOT,
            fill=VIS_CURSOR,
            tag="vis_cursor_dot",
        )


def _update_visualizer(status: BotStatus):
    try:
        panel_size = dpg.get_item_rect_size("vision_card")
        if not panel_size or panel_size[0] <= 80:
            return
        width = max(200, int(panel_size[0] - 40))
    except Exception:
        log.debug("Failed to update visualizer size.", exc_info=True)
        return

    dpg.configure_item("visualizer", width=width, height=int(72 * _s))
    track_left = 18
    track_right = width - 18
    track_top = 20
    track_bottom = 52
    track_mid = (track_left + track_right) / 2
    dpg.configure_item(
        "vis_track", pmin=(track_left, track_top), pmax=(track_right, track_bottom)
    )
    dpg.configure_item("vis_center", p1=(track_mid, 12), p2=(track_mid, 60))

    if status.bar_width <= 0:
        dpg.configure_item("vis_safe_zone", show=False)
        dpg.configure_item("vis_cursor", show=False)
        dpg.configure_item("vis_cursor_dot", show=False)
        return

    track_width = track_right - track_left
    scale = track_width / status.bar_width

    if status.target_x is not None:
        zone_half = max(24, min(64, track_width * 0.045))
        target_x = _scaled_x(status.target_x, status.bar_width, track_left, scale)
        dpg.configure_item(
            "vis_safe_zone",
            show=True,
            pmin=(max(track_left, target_x - zone_half), track_top),
            pmax=(min(track_right, target_x + zone_half), track_bottom),
        )
    else:
        dpg.configure_item("vis_safe_zone", show=False)

    if status.cursor_x is not None:
        cursor_x = _scaled_x(status.cursor_x, status.bar_width, track_left, scale)
        dpg.configure_item(
            "vis_cursor", show=True, p1=(cursor_x, 10), p2=(cursor_x, 62)
        )
        dpg.configure_item("vis_cursor_dot", show=True, center=(cursor_x, 36))
    else:
        dpg.configure_item("vis_cursor", show=False)
        dpg.configure_item("vis_cursor_dot", show=False)


def _scaled_x(value: int, bar_width: int, track_left: int, scale: float) -> float:
    value = max(0, min(bar_width, value))
    return track_left + value * scale


# ---------------------------------------------------------------------------
# Stat card
# ---------------------------------------------------------------------------


def _create_stat_card(tag: str, label: str, default: str, width: int = 200):
    with dpg.child_window(
        width=width,
        height=int(100 * _s),
        tag=tag,
        border=True,
        no_scrollbar=True,
    ):
        apply_glass_card_theme(tag)
        dpg.add_text(tr(label), color=TEXT_VERY_MUTED)
        dpg.add_spacer(height=4)
        dpg.add_text(tr(default), tag=f"{tag}_value", color=TEXT_PRIMARY)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_callback(
    callback: Callable[[], None] | None,
    bridge: BotBridge,
    fallback_cmd: str,
):
    if callback:
        callback()
    else:
        bridge.send_cmd(fallback_cmd)


def _set_enabled(tag: str, enabled: bool):
    if enabled:
        dpg.enable_item(tag)
    else:
        dpg.disable_item(tag)


def _state_label(state: FishingState) -> str:
    labels = {
        FishingState.IDLE: "Idle",
        FishingState.WAITING: "Waiting",
        FishingState.STRUGGLING: "Tracking",
        FishingState.RESULT: "Result",
    }
    return tr(labels.get(state, state.value.title()))


def _status_message(status: BotStatus) -> str:
    if status.is_stopped:
        if status.stop_reason:
            return tr("Stopped: {reason}").format(reason=tr(status.stop_reason))
        return tr("Ready")
    if not status.is_running:
        return tr("Paused")
    if status.state is FishingState.IDLE:
        if status.bait_error_count > 0:
            return tr("Cast error {n}/{limit}, retrying").format(
                n=status.bait_error_count, limit=status.bait_error_limit
            )
        return tr("Casting")
    if status.state is FishingState.WAITING:
        return tr("Waiting for bite")
    if status.state is FishingState.STRUGGLING:
        return tr("Tracking fish bar")
    if status.state is FishingState.RESULT:
        return tr("Closing result")
    return tr("Running")


def _fmt_optional(value: int | None) -> str:
    return str(value) if value is not None else tr("N/A")


def _fmt_roi(roi: tuple[int, int, int, int]) -> str:
    left, top, width, height = roi
    if width <= 0 or height <= 0:
        return tr("N/A")
    return f"{left},{top} {width}x{height}"
