"""Keeps the tracker previews alive while the bot is stopped.

Without this the previews (and dragging them to adjust the scan areas) would
only work after the bot had been started once.
"""

import logging
import threading

from screeninfo import get_monitors

from config import CFG
from gui.bridge import BotBridge
from modules.roi import compute_rois
from modules.vision import VisionModule

log = logging.getLogger("NTEFish")

_INTERVAL_SECS = 0.4
_REFERENCE_W, _REFERENCE_H = 3840, 2160


class PreviewPump:
    def __init__(self, bridge: BotBridge) -> None:
        self._bridge = bridge
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        from modules.io_module import CaptureModule
        from modules.preview import render_bar_preview, render_button_preview

        capture = CaptureModule()
        try:
            while not self._stop.wait(_INTERVAL_SECS):
                try:
                    if not self._bridge.latest_status().is_stopped:
                        continue  # the running bot publishes its own previews
                    if not CFG.tracker_preview_enabled:
                        continue
                    monitors = get_monitors()
                    mon = monitors[max(0, min(CFG.monitor_index, len(monitors) - 1))]
                    bar_roi, button_roi = compute_rois(CFG, mon)
                    scale = min(mon.width / _REFERENCE_W, mon.height / _REFERENCE_H)
                    min_area = max(CFG.detection_min_area * scale * scale, 1.0)

                    bar_img = capture.grab_bgr(bar_roi)
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
                    button_img = capture.grab_bgr(button_roi)
                    pv["button"], pv["blue_pixels"] = render_button_preview(
                        button_img, CFG.hsv.blue
                    )
                    pv["blue_threshold"] = int(
                        max(CFG.min_blue_pixels * scale * scale, 1.0)
                    )
                    pv["bar_roi"] = (
                        bar_roi["left"], bar_roi["top"], bar_roi["width"], bar_roi["height"]
                    )
                    pv["button_roi"] = (
                        button_roi["left"],
                        button_roi["top"],
                        button_roi["width"],
                        button_roi["height"],
                    )
                    pv["version"] += 1
                except Exception:
                    log.debug("Preview pump iteration failed.", exc_info=True)
        finally:
            capture.close()
