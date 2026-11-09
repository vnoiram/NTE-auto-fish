"""Keeps the tracker previews alive while the bot is stopped and the user checks the areas.

Started with the "Check and adjust areas" button, so the screen is only captured on
request. Without it the previews (and dragging them) would need a running bot.
"""

import logging
import threading

from screeninfo import get_monitors

from config import CFG
from gui.bridge import BotBridge
from modules.ocr import CatchOcr, ratios_to_roi
from modules.roi import compute_icon_roi, compute_rois
from modules.vision import VisionModule

log = logging.getLogger("NTEFish")

_INTERVAL_SECS = 0.4
_OCR_EVERY_N = 5  # OCR is slow: read the name/weight areas every few iterations
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

    def _run(self) -> None:
        from modules.io_module import CaptureModule
        from modules.preview import (
            render_bar_preview,
            render_button_preview,
            render_icon_preview,
            render_ocr_preview,
        )

        capture = CaptureModule()
        ocr = CatchOcr()
        tick = 0
        try:
            while not self._stop.wait(_INTERVAL_SECS):
                tick += 1
                try:
                    if not self._bridge.latest_status().is_stopped:
                        continue  # the running bot publishes its own previews
                    if not self._bridge.preview_active:
                        continue  # only while the user checks the areas
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
                    icon_img = capture.grab_bgr(compute_icon_roi(CFG, mon))
                    count = VisionModule.count_icons(icon_img, scale)
                    pv["icons"] = render_icon_preview(icon_img)
                    pv["icons_text"] = (
                        f"icons {count} (failed cast at >= {CFG.cast_icon_fail_min})"
                    )
                    if tick % _OCR_EVERY_N == 1:
                        self._read_ocr(ocr, capture, mon, pv, render_ocr_preview)
                    pv["version"] += 1
                except Exception:
                    log.debug("Preview pump iteration failed.", exc_info=True)
        finally:
            capture.close()
