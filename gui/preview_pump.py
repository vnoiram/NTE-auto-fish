"""Area check while the bot is stopped: one screenshot, then cheap local updates.

Pressing "Check and adjust areas" takes a single full-screen snapshot of the game
(the app window is hidden for a moment so it is not in the picture). After that no
more capturing happens: the previews are cropped from that snapshot and re-rendered
only when the area settings change (drag, sliders, area editor). OCR runs on the
same snapshot, in its own thread, once the areas stop moving.
"""

import logging
import threading
import time
from collections.abc import Callable
from types import SimpleNamespace

import numpy as np
from screeninfo import get_monitors

from config import CFG
from gui.bridge import BotBridge
from modules.ocr import CatchOcr, ratios_to_roi
from modules.roi import compute_icon_roi, compute_rois
from modules.vision import VisionModule

log = logging.getLogger("NTEFish")

_POLL_SECS = 0.25  # how often settings are checked for changes (cheap)
_OCR_SETTLE_SECS = 0.8  # wait until the OCR areas stop moving before reading
_HIDE_SETTLE_SECS = 0.35  # let the window disappear before capturing
_REFERENCE_W, _REFERENCE_H = 3840, 2160


class SnapshotCapture:
    """grab_bgr() over a stored screenshot, so OCR and previews can reuse it."""

    def __init__(self, image: np.ndarray, mon_x: int, mon_y: int) -> None:
        self.image = image
        self.mon_x = mon_x
        self.mon_y = mon_y

    def grab_bgr(self, roi: dict) -> np.ndarray:
        h, w = self.image.shape[:2]
        x0 = max(0, min(w - 1, roi["left"] - self.mon_x))
        y0 = max(0, min(h - 1, roi["top"] - self.mon_y))
        x1 = max(x0 + 1, min(w, x0 + max(1, roi["width"])))
        y1 = max(y0 + 1, min(h, y0 + max(1, roi["height"])))
        return np.ascontiguousarray(self.image[y0:y1, x0:x1])


def _active_monitor():
    monitors = get_monitors()
    return monitors[max(0, min(CFG.monitor_index, len(monitors) - 1))]


class PreviewPump:
    def __init__(
        self,
        bridge: BotBridge,
        hide_ui: Callable[[], None] | None = None,
        show_ui: Callable[[], None] | None = None,
    ) -> None:
        self._bridge = bridge
        self._hide_ui = hide_ui
        self._show_ui = show_ui
        self._stop = threading.Event()
        self._snapshot: SnapshotCapture | None = None
        self._mon = None
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._ocr_thread = threading.Thread(target=self._run_ocr, daemon=True)

    def start(self) -> None:
        self._thread.start()
        self._ocr_thread.start()

    def stop(self) -> None:
        self._stop.set()

    # -- snapshot -----------------------------------------------------------

    def _take_snapshot(self) -> None:
        from modules.io_module import CaptureModule

        mon = _active_monitor()
        region = {"left": mon.x, "top": mon.y, "width": mon.width, "height": mon.height}
        hidden = False
        capture = CaptureModule()
        try:
            if self._hide_ui:
                try:
                    self._hide_ui()
                    hidden = True
                    time.sleep(_HIDE_SETTLE_SECS)
                except Exception:
                    log.debug("Failed to hide the window for the snapshot.", exc_info=True)
            image = capture.grab_bgr(region)
        finally:
            capture.close()
            if hidden and self._show_ui:
                try:
                    self._show_ui()
                except Exception:
                    log.debug("Failed to show the window after the snapshot.", exc_info=True)
        with self._lock:
            self._snapshot = SnapshotCapture(image, mon.x, mon.y)
            self._mon = SimpleNamespace(
                x=mon.x, y=mon.y, width=mon.width, height=mon.height
            )
        pv = self._bridge.preview
        pv["pump_status"] = time.strftime(
            f"Snapshot {image.shape[1]}x{image.shape[0]} %H:%M:%S"
        )
        pv["version"] += 1

    # -- rendering ----------------------------------------------------------

    @staticmethod
    def _settings_key(mon) -> tuple:
        bar, button = compute_rois(CFG, mon)
        icons = compute_icon_roi(CFG, mon)
        return (
            tuple(bar.values()),
            tuple(button.values()),
            tuple(icons.values()),
            tuple(CFG.hsv.safe_zone.lower + CFG.hsv.safe_zone.upper),
            tuple(CFG.hsv.cursor.lower + CFG.hsv.cursor.upper),
            tuple(CFG.hsv.blue.lower + CFG.hsv.blue.upper),
            CFG.min_blue_pixels,
            CFG.cast_icon_fail_min,
            CFG.detection_min_area,
            CFG.roi.ignore_margin_ratio,
        )

    def _render(self, snap: SnapshotCapture, mon) -> None:
        from modules.preview import (
            render_bar_preview,
            render_button_preview,
            render_icon_preview,
        )

        bar_roi, button_roi = compute_rois(CFG, mon)
        scale = min(mon.width / _REFERENCE_W, mon.height / _REFERENCE_H)
        min_area = max(CFG.detection_min_area * scale * scale, 1.0)

        bar_img = snap.grab_bgr(bar_roi)
        cursor_x, _ = VisionModule.get_hsv_centroid_x(
            bar_img,
            CFG.hsv.cursor.lower,
            CFG.hsv.cursor.upper,
            min_area=min_area,
            ignore_margin_ratio=CFG.roi.ignore_margin_ratio,
        )
        target_x, _ = VisionModule.get_hsv_centroid_x(
            bar_img,
            CFG.hsv.safe_zone.lower,
            CFG.hsv.safe_zone.upper,
            min_area=min_area,
        )
        pv = self._bridge.preview
        pv["bar"] = render_bar_preview(
            bar_img, cursor_x, target_x, CFG.hsv.safe_zone, CFG.hsv.cursor
        )
        pv["button"], pv["blue_pixels"] = render_button_preview(
            snap.grab_bgr(button_roi), CFG.hsv.blue
        )
        pv["blue_threshold"] = int(max(CFG.min_blue_pixels * scale * scale, 1.0))
        icon_img = snap.grab_bgr(compute_icon_roi(CFG, mon))
        pv["icons"] = render_icon_preview(icon_img)
        pv["icons_text"] = (
            f"icons {VisionModule.count_icons(icon_img, scale)} "
            f"(failed cast at >= {CFG.cast_icon_fail_min})"
        )
        pv["bar_roi"] = (
            bar_roi["left"],
            bar_roi["top"],
            bar_roi["width"],
            bar_roi["height"],
        )
        pv["button_roi"] = (
            button_roi["left"],
            button_roi["top"],
            button_roi["width"],
            button_roi["height"],
        )
        pv["version"] += 1

    def _active(self) -> bool:
        return bool(
            self._bridge.latest_status().is_stopped
            and self._bridge.preview_active
            and CFG.tracker_preview_enabled
        )

    def _run(self) -> None:
        last_key = None
        last_error = ""
        while not self._stop.wait(_POLL_SECS):
            try:
                if not self._active():
                    last_key = None
                    with self._lock:
                        if not self._bridge.preview_active:
                            self._snapshot = None
                    continue
                if self._bridge.snapshot_request:
                    self._bridge.snapshot_request = False
                    self._take_snapshot()
                    last_key = None
                with self._lock:
                    snap, mon = self._snapshot, self._mon
                if snap is None:
                    continue
                key = self._settings_key(mon)
                if key != last_key:
                    self._render(snap, mon)
                    last_key = key
                last_error = ""
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                if message != last_error:
                    last_error = message
                    log.warning("Area check failed: %s", message, exc_info=True)
                self._bridge.preview["pump_status"] = f"ERROR {message}"
                self._bridge.preview["version"] += 1

    # -- OCR ----------------------------------------------------------------

    @staticmethod
    def _read_ocr(ocr, capture, mon, pv, render) -> None:
        """OCR the fish name / weight areas as they are set now and show what was read."""
        name_roi = ratios_to_roi(
            CFG.ocr_name_roi_ratios, mon.width, mon.height, mon.x, mon.y
        )
        weight_roi = ratios_to_roi(
            CFG.ocr_weight_roi_ratios, mon.width, mon.height, mon.x, mon.y
        )
        if not ocr.available:
            pv["ocr_name_text"] = pv["ocr_weight_text"] = "OCR unavailable"
            return
        ocr.read(capture, name_roi, weight_roi)
        for key in ("name", "weight"):
            region = ocr.last_regions.get(key)
            if region is None:
                continue
            raw, binary, text = region
            pv[f"ocr_{key}"] = render(raw, binary)
            pv[f"ocr_{key}_text"] = text

    def _run_ocr(self) -> None:
        """Read the OCR areas of the snapshot once they stop moving (own thread)."""
        from modules.preview import render_ocr_preview

        ocr = CatchOcr()
        done_key = None
        pending_key, pending_since = None, 0.0
        while not self._stop.wait(_POLL_SECS):
            try:
                if not self._active():
                    done_key = pending_key = None
                    continue
                with self._lock:
                    snap, mon = self._snapshot, self._mon
                if snap is None:
                    continue
                key = (
                    id(snap),
                    tuple(CFG.ocr_name_roi_ratios),
                    tuple(CFG.ocr_weight_roi_ratios),
                )
                if key == done_key:
                    continue
                now = time.monotonic()
                if key != pending_key:
                    pending_key, pending_since = key, now
                    continue
                if now - pending_since < _OCR_SETTLE_SECS:
                    continue
                pv = self._bridge.preview
                self._read_ocr(ocr, snap, mon, pv, render_ocr_preview)
                pv["version"] += 1
                done_key = key
            except Exception:
                log.debug("Area check OCR failed.", exc_info=True)
