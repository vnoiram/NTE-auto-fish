"""Scan-area geometry shared by the bot and the GUI preview.

Mirrors the bot's calibration: the bar and bite areas come from drag-and-drop
ratios when saved, otherwise from the automatic defaults, plus the manual
pixel corrections from the settings.
"""

from config import (
    DEFAULT_BAR_RATIOS,
    DEFAULT_BUTTON_RATIOS,
    DEFAULT_ICON_RATIOS,
    ratios_are_set,
)


def _from_ratios(ratios, mon) -> dict:
    left = round(mon.width * ratios[0])
    top = round(mon.height * ratios[1])
    return {
        "left": mon.x + left,
        "top": mon.y + top,
        "width": max(8, round(mon.width * ratios[2]) - left),
        "height": max(4, round(mon.height * ratios[3]) - top),
    }


def compute_rois(cfg, mon) -> tuple[dict, dict]:
    """Return (bar, bite) areas in screen coordinates for a monitor."""
    bar = _from_ratios(
        cfg.bar_roi_ratios
        if ratios_are_set(cfg.bar_roi_ratios)
        else DEFAULT_BAR_RATIOS,
        mon,
    )
    button = _from_ratios(
        cfg.button_roi_ratios
        if ratios_are_set(cfg.button_roi_ratios)
        else DEFAULT_BUTTON_RATIOS,
        mon,
    )
    r = cfg.roi
    bar = {
        "left": bar["left"] + r.bar_offset_x,
        "top": bar["top"] + r.bar_offset_y,
        "width": max(8, bar["width"] + r.bar_width_delta),
        "height": max(4, bar["height"] + r.bar_height_delta),
    }
    button = {
        "left": button["left"] + r.button_offset_x,
        "top": button["top"] + r.button_offset_y,
        "width": max(8, button["width"] + r.button_width_delta),
        "height": max(4, button["height"] + r.button_height_delta),
    }
    return bar, button


def compute_icon_roi(cfg, mon) -> dict:
    """The lower-right action-bar area used to tell a failed cast from a good one."""
    ratios = (
        cfg.icon_roi_ratios
        if ratios_are_set(cfg.icon_roi_ratios)
        else DEFAULT_ICON_RATIOS
    )
    icon = _from_ratios(ratios, mon)
    icon["left"] += cfg.roi.icon_offset_x
    icon["top"] += cfg.roi.icon_offset_y
    icon["width"] = max(8, icon["width"] + cfg.roi.icon_width_delta)
    icon["height"] = max(4, icon["height"] + cfg.roi.icon_height_delta)
    return icon
