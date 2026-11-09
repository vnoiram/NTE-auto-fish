"""Locate the game window and work out which monitor it is on (Windows only)."""

from __future__ import annotations

import logging
import os
import sys

log = logging.getLogger(__name__)

DEFAULT_TITLE_KEYWORDS = ("neverness to everness", "異環", "异环")


def find_game_monitor_rect(keywords=DEFAULT_TITLE_KEYWORDS):
    """Return (left, top, right, bottom) of the monitor holding the game window, or None."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    own_pid = os.getpid()
    needles = [k.lower() for k in keywords if k]
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _visit(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.lower()
        if not any(n in title for n in needles):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value != own_pid:
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(_visit, 0)
    if not found:
        return None

    class _MonitorInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    user32.MonitorFromWindow.restype = wintypes.HANDLE
    hmon = user32.MonitorFromWindow(found[0], 2)  # MONITOR_DEFAULTTONEAREST
    info = _MonitorInfo()
    info.cbSize = ctypes.sizeof(_MonitorInfo)
    if not user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
        return None
    r = info.rcMonitor
    return (r.left, r.top, r.right, r.bottom)


def pick_monitor_index(monitors, rect) -> int | None:
    """Index of the monitor whose origin matches ``rect``, else None."""
    if rect is None:
        return None
    for i, m in enumerate(monitors):
        if (m.x, m.y) == (rect[0], rect[1]):
            return i
    return None


def auto_select_monitor(cfg) -> bool:
    """Point ``cfg.monitor_index`` at the game's monitor. Returns True if it changed."""
    if not getattr(cfg, "monitor_auto_select", True):
        return False
    try:
        from screeninfo import get_monitors

        idx = pick_monitor_index(get_monitors(), find_game_monitor_rect())
    except Exception:
        log.debug("Game monitor auto-detection failed.", exc_info=True)
        return False
    if idx is None or idx == cfg.monitor_index:
        return False
    cfg.monitor_index = idx
    log.info("Game window found on monitor %d; using it.", idx)
    return True
