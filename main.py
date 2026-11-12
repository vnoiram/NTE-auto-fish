"""Core NTE Auto-Fish runtime.

Entry points:
  - Headless: python main.py
  - GUI:      python start_gui.py
"""

import csv
import json
import logging
import logging.handlers
import os
import random
import sys
import threading
import time
from random import SystemRandom
from typing import TYPE_CHECKING, Optional

from config import (
    CFG,
    DEFAULT_ICON_RATIOS,
    AppConfig,
    ensure_settings_loaded,
    ratios_are_set,
    sample_movement_pulse,
    sample_noise,
    sample_reaction,
    sample_timing,
)
from modules.branding import scoped_runtime_name
from modules.calibration import BackgroundSampler, GaugeAssist, suggest_gauge_at_start
from modules.logic import FishingState, FishingStateMachine, PIDController
from modules.ocr import CatchOcr, ratios_to_roi
from modules.preview import (
    render_bar_preview,
    render_button_preview,
    render_icon_preview,
    render_ocr_preview,
)
from modules.profiles import apply_profile, pick_profile
from modules.session_manager import SessionManager
from modules.utils import APP_DIR, bundled_path

# Third-party imports — deferred so entrypoints can validate dependencies first.
try:
    import cv2
    from screeninfo import get_monitors

    from modules.io_module import CaptureModule, InputModule
    from modules.vision import VisionModule

    _TP_LOADED = True
except ImportError:
    cv2 = CaptureModule = InputModule = VisionModule = None  # type: ignore[assignment]
    get_monitors = None  # type: ignore[assignment]
    _TP_LOADED = False

if TYPE_CHECKING:
    from gui.bridge import BotBridge

# CWD is set inside run() to avoid side effects on import
_RNG = SystemRandom()

_BG_SAMPLE_INTERVAL_SECS = 1.0
_PROFILE_CHECK_INTERVAL_SECS = 5.0
_PREVIEW_INTERVAL_SECS = 0.2
_ERROR_CONFIRM_DELAY_SECS = 0.7  # the real dialog stays; a transient match must too
_BAR_ENTER_FRAMES = 3  # consecutive frames with all selected bars before a fight starts
_ASSIST_WINDOW_SECS = 2.0
_PROFILE_MIN_SAMPLES = 3
_DEFAULT_SCREEN_W = 3840
_DEFAULT_SCREEN_H = 2160
_RESULT_CLOSE_FALLBACK_X = 960
_RESULT_CLOSE_FALLBACK_Y = 540
_BAR_WIDTH_RATIO = 0.375
_MAX_CAPTURE_FAILURES = 5
# _MAX_STRUGGLE_SECS and _BAIT_ERROR_THRESHOLD moved to TimingConfig


def _resource_path(*parts: str) -> str:
    return bundled_path(*parts)


LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
DATE_FORMAT = "%H:%M:%S"

log = logging.getLogger("NTEFish")
_logging_configured = False


def setup_logging() -> None:
    """Configure console and rotating-file logging once (no side effects on import)."""
    global _logging_configured
    if _logging_configured:
        return
    _logging_configured = True
    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        datefmt=DATE_FORMAT,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.handlers.RotatingFileHandler(
                os.path.join(APP_DIR, scoped_runtime_name("fishing_bot.log")),
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            ),
        ],
    )


class CaptureError(RuntimeError):
    """Raised when a screen grab fails (e.g. the display is temporarily unavailable)."""


class NTEFishingBot:
    def __init__(
        self,
        cfg: AppConfig = CFG,
        bridge: Optional["BotBridge"] = None,
        hide_ui_callback: callable | None = None,
        show_ui_callback: callable | None = None,
    ) -> None:
        setup_logging()
        ensure_settings_loaded()
        if not _TP_LOADED:
            raise RuntimeError(
                "Missing runtime dependencies. Install with: "
                f"{sys.executable} -m pip install -r requirements.txt"
            )

        self.cfg = cfg
        self.bridge = bridge
        self._hide_ui = hide_ui_callback
        self._show_ui = show_ui_callback

        if bridge:
            from gui.bridge import BridgeHandler

            root = logging.getLogger()
            for existing in list(root.handlers):
                if isinstance(existing, BridgeHandler) and existing.bridge is bridge:
                    root.removeHandler(existing)
            handler = BridgeHandler(bridge)
            handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
            # Add to root logger to capture all messages, or just 'NTEFish'
            root.addHandler(handler)

        self.capture = CaptureModule()
        self.input = InputModule()
        self.vision = VisionModule()
        self.sm = FishingStateMachine()
        self.pid = PIDController(
            kp=cfg.pid.kp,
            ki=cfg.pid.ki,
            kd=cfg.pid.kd,
            integral_limit=cfg.pid.integral_limit,
            deadband=cfg.pid.deadband,
            adaptive=cfg.pid.adaptive,
        )

        self._roi_button: dict = dict(cfg.roi.button)
        self._roi_bar: dict = dict(cfg.roi.bar)
        self._roi_error: dict = {}
        self._roi_icon: dict = {}
        self._bait_error_count = 0
        self._lost_frames = 0
        self._lost_cursor_frames = 0
        self._lost_target_frames = 0
        self._fish_count = 0
        self._screen_w = 0
        self._screen_h = 0
        self._mon_x = 0
        self._mon_y = 0
        self._current_scale = 1.0
        self._scaled_min_area = 30.0
        self._scaled_blue_pixels = 300
        self._scaled_error_white_min = 1200

        self._last_pid_out = 0.0
        self._cursor_x_rel = None
        self._target_x_rel = None
        self._session_start = time.time()
        self._is_paused = False
        self._stop_flag = False
        self._stop_event = threading.Event()
        self._is_stopped = True
        self._start_delay_pending = False
        self._active_secs = 0.0
        self._fish_limit_target = None
        self._time_limit_until = None
        self._time_limit_notified = False
        self._fps = 0.0
        self._last_time = time.time()
        self._last_action = "NONE"
        self._consecutive_waiting_timeouts = 0
        self._waiting_timeout_secs = cfg.timing.bite_timeout_secs
        self._battle_visible = False
        self._battle_absent_frames = 0
        self._next_spam_at = 0.0
        self._next_bg_sample_at = 0.0
        self._next_preview_at = 0.0
        self._assist_done = True
        self._assist = bridge.gauge_assist if bridge is not None else GaugeAssist()
        self._background = (
            bridge.background if bridge is not None else BackgroundSampler()
        )

        self._last_fish_name: str = ""
        self._last_fish_weight_g: str = ""
        self._bar_detected_in_struggle = False
        self._reset_humanization_state()

        self._log("Bot initialized.")
        self._csv_handle = None
        self._csv_writer = None
        sessions_dir = os.path.join(APP_DIR, scoped_runtime_name("sessions"))
        self._session_manager = SessionManager(sessions_dir=sessions_dir)
        self._ocr = CatchOcr()

    def _grab(self, roi: dict):
        try:
            return self.capture.grab_bgr(roi)
        except Exception as exc:
            raise CaptureError(str(exc)) from exc

    def _reset_humanization_state(self) -> None:
        self._hum_reaction_end = 0.0
        self._hum_pulse_end = 0.0
        self._hum_pulse_state = "IDLE"
        self._hum_target_action = "NONE"
        self._hum_gap_scale = 1.0
        self._hum_flick_pending = False
        self._hum_deadband_play_enabled = False

    def _roll_deadband_play_for_battle(self) -> None:
        hcfg = self.cfg.humanization
        chance = max(0.0, min(1.0, hcfg.deadband_play_battle_chance))
        self._hum_deadband_play_enabled = (
            hcfg.enabled and hcfg.deadband_tap_enabled and _RNG.random() < chance
        )

    def _should_send_deadband_tap(self) -> bool:
        hcfg = self.cfg.humanization
        return (
            self._hum_deadband_play_enabled
            and hcfg.deadband_tap_enabled
            and _RNG.random() < hcfg.deadband_tap_chance
        )

    @property
    def is_stopped(self) -> bool:
        return self._is_stopped

    def prepare_for_run(self, paused: bool = False) -> None:
        self._stop_flag = False
        self._stop_event.clear()
        self._is_stopped = False
        self._is_paused = paused
        self._start_delay_pending = not paused
        self._active_secs = 0.0
        self._fish_limit_target = None
        self._time_limit_until = None
        self._time_limit_notified = False
        self.sm = FishingStateMachine()
        self.pid.reset()
        self._fish_count = 0
        self._bait_error_count = 0
        self._lost_frames = 0
        self._lost_cursor_frames = 0
        self._lost_target_frames = 0
        self._last_pid_out = 0.0
        self._cursor_x_rel = None
        self._cursor_last_seen = None
        self._target_x_rel = None
        self._fps = 0.0
        self._session_start = time.time()
        self._last_time = time.time()
        self._last_action = "NONE"
        self._consecutive_waiting_timeouts = 0
        self._waiting_timeout_secs = self.cfg.timing.bite_timeout_secs
        self._battle_visible = False
        self._battle_absent_frames = 0
        self._next_spam_at = 0.0
        self._last_fish_name = ""
        self._last_fish_weight_g = ""
        self._bar_detected_in_struggle = False
        self._reset_humanization_state()
        self._roll_deadband_play_for_battle()
        if not paused and self.cfg.fish_logging_enabled:
            self._session_manager.start_session()

    def request_stop(self, reason: str = "") -> None:
        self._stop_reason = reason
        self._stop_flag = True
        self._stop_event.set()
        self._is_paused = True
        self._is_stopped = True
        self._last_pid_out = 0.0
        self._fps = 0.0
        self.input.release_all()

    def publish_status(self) -> None:
        self._push_status()

    def _log(self, msg: str, level: int = logging.INFO):
        log.log(level, msg)

    def _push_status(self):
        if not self.bridge:
            return
        from gui.bridge import BotStatus

        self.bridge.push_status(
            BotStatus(
                state=self.sm.state,
                fish_count=self._fish_count,
                session_secs=time.time() - self._session_start,
                pid_output=self._last_pid_out,
                cursor_x=self._cursor_x_rel,
                target_x=self._target_x_rel,
                bar_width=self._roi_bar.get("width", 0),
                button_roi=self._roi_tuple(self._roi_button),
                bar_roi=self._roi_tuple(self._roi_bar),
                fps=0.0 if self._is_paused or self._is_stopped else self._fps,
                lost_frames=self._lost_frames,
                lost_cursor_frames=self._lost_cursor_frames,
                lost_target_frames=self._lost_target_frames,
                is_running=(
                    not self._is_paused and not self._stop_flag and not self._is_stopped
                ),
                is_stopped=self._is_stopped,
                scaled_min_area=self._scaled_min_area,
                current_scale=self._current_scale,
                last_fish_name=self._last_fish_name,
                last_fish_weight_g=self._last_fish_weight_g,
                stop_reason=getattr(self, "_stop_reason", ""),
                bait_error_count=getattr(self, "_bait_error_count", 0),
                bait_error_limit=self.cfg.timing.bait_error_threshold,
                fish_left=(
                    max(0, self._fish_limit_target - self._fish_count)
                    if self._fish_limit_target is not None
                    else None
                ),
                secs_left=(
                    max(0.0, self._time_limit_until - self._active_secs)
                    if self._time_limit_until is not None
                    else None
                ),
            )
        )

    @staticmethod
    def _roi_tuple(roi: dict) -> tuple[int, int, int, int]:
        return (
            int(roi.get("left", 0)),
            int(roi.get("top", 0)),
            int(roi.get("width", 0)),
            int(roi.get("height", 0)),
        )

    def _poll_commands(self):
        if not self.bridge:
            return
        self._apply_limit_request()
        while True:
            cmd = self.bridge.poll_cmd()
            if cmd is None:
                break
            self._handle_command(cmd)
            if self._stop_flag:
                break

    def _handle_command(self, cmd: str) -> None:
        if cmd == "pause":
            self._is_paused = True
            self.input.release_all()
            self._log("Bot paused by user.")
        elif cmd == "resume":
            if not self._is_stopped:
                if self.cfg.monitor_index != getattr(
                    self, "_calibrated_monitor", self.cfg.monitor_index
                ):
                    # The game monitor was changed while paused: measure again.
                    self._log("[Calibration] Monitor changed; recalibrating.")
                    self.calibrate()
                    if self._stop_flag:
                        return
                self._bait_error_count = 0
                self._is_paused = False
                self._start_delay_pending = True
                if (
                    self.cfg.fish_logging_enabled
                    and self._session_manager.active_session_id() is None
                ):
                    self._session_manager.start_session()
                self._log("Bot resumed by user.")
        elif cmd == "recalibrate":
            self._is_paused = True
            self.input.release_all()
            self._log("Recalibration requested.")
            self.calibrate()
        elif cmd == "stop":
            self.request_stop()
            self._log("Bot stop requested.")

    def get_active_monitor(self):
        monitors = get_monitors()

        index = max(0, min(self.cfg.monitor_index, len(monitors) - 1))

        return monitors[index]

    def _ratio_roi(self, ratios) -> dict:
        """Screen-absolute ROI from drag-and-drop (left, top, right, bottom) ratios."""
        left = round(self._screen_w * ratios[0])
        top = round(self._screen_h * ratios[1])
        return self._offset_roi(
            {
                "left": left,
                "top": top,
                "width": max(8, round(self._screen_w * ratios[2]) - left),
                "height": max(4, round(self._screen_h * ratios[3]) - top),
            }
        )

    def _apply_roi_offsets(self) -> None:
        """Apply saved drag-and-drop areas and the manual corrections to the defaults."""
        default_bar = getattr(self, "_roi_bar_default", None)
        default_button = getattr(self, "_roi_button_default", None)
        if default_bar is None or default_button is None:
            return
        cfg = self.cfg
        r = cfg.roi
        key = (
            tuple(cfg.bar_roi_ratios),
            tuple(cfg.button_roi_ratios),
            tuple(cfg.icon_roi_ratios),
            r.bar_offset_x,
            r.bar_offset_y,
            r.bar_width_delta,
            r.bar_height_delta,
            r.button_offset_x,
            r.button_offset_y,
            r.icon_offset_x,
            r.icon_offset_y,
            r.button_width_delta,
            r.button_height_delta,
            r.icon_width_delta,
            r.icon_height_delta,
        )
        if key == getattr(self, "_roi_offsets_applied", None):
            return
        self._roi_offsets_applied = key
        base_bar = (
            self._ratio_roi(cfg.bar_roi_ratios)
            if ratios_are_set(cfg.bar_roi_ratios)
            else default_bar
        )
        base_button = (
            self._ratio_roi(cfg.button_roi_ratios)
            if ratios_are_set(cfg.button_roi_ratios)
            else default_button
        )
        self._roi_bar = {
            "left": base_bar["left"] + r.bar_offset_x,
            "top": base_bar["top"] + r.bar_offset_y,
            "width": max(8, base_bar["width"] + r.bar_width_delta),
            "height": max(4, base_bar["height"] + r.bar_height_delta),
        }
        self._roi_button = {
            "left": base_button["left"] + r.button_offset_x,
            "top": base_button["top"] + r.button_offset_y,
            "width": max(8, base_button["width"] + r.button_width_delta),
            "height": max(4, base_button["height"] + r.button_height_delta),
        }
        icon = self._ratio_roi(
            cfg.icon_roi_ratios
            if ratios_are_set(cfg.icon_roi_ratios)
            else DEFAULT_ICON_RATIOS
        )
        icon["left"] += r.icon_offset_x
        icon["top"] += r.icon_offset_y
        icon["width"] = max(8, icon["width"] + r.icon_width_delta)
        icon["height"] = max(4, icon["height"] + r.icon_height_delta)
        self._roi_icon = icon
        self._log(
            f"[Calibration] Scan areas: bar={self._roi_bar} button={self._roi_button} "
            f"icons={self._roi_icon}"
        )

    def _offset_roi(self, roi: dict) -> dict:
        """Shift a monitor-local ROI to screen-absolute coordinates."""
        return {
            "left": roi["left"] + self._mon_x,
            "top": roi["top"] + self._mon_y,
            "width": roi["width"],
            "height": roi["height"],
        }

    def calibrate(self) -> None:
        self._log("[Calibration] Capturing full screen...")

        mon = self.get_active_monitor()
        self._calibrated_monitor = self.cfg.monitor_index

        region = {
            "left": mon.x,
            "top": mon.y,
            "width": mon.width,
            "height": mon.height,
        }

        try:
            self.capture.grab_bgr(region)  # verify the screen can be captured
        except Exception as e:
            self._log(
                f"[Calibration] Failed to capture screen: {e}. Is the game fullscreen and minimized?",
                logging.ERROR,
            )
            self.request_stop("Screen capture failed at calibration")
            return

        self._screen_w, self._screen_h = mon.width, mon.height
        self._mon_x, self._mon_y = mon.x, mon.y
        self._current_scale = min(
            self._screen_w / _DEFAULT_SCREEN_W, self._screen_h / _DEFAULT_SCREEN_H
        )

        # Scale area and pixel thresholds quadratically with resolution
        scale_sq = self._current_scale * self._current_scale
        self._scaled_min_area = max(self.cfg.detection_min_area * scale_sq, 1.0)
        self._scaled_blue_pixels = int(max(self.cfg.min_blue_pixels * scale_sq, 1.0))
        self._scaled_error_white_min = int(max(1200 * scale_sq, 10.0))

        self._log(f"[Calibration] Screen resolution: {self._screen_w}x{self._screen_h}")

        # --- Bar ROI (ratio-based, primary method) ---
        progress_json = _resource_path("templates", "progress.json")
        try:
            with open(progress_json, encoding="utf-8") as handle:
                data = json.load(handle)
            if data and isinstance(data, list) and "ratios" in data[0]:
                ratios = data[0]["ratios"]
                self._roi_bar = self._offset_roi(
                    {
                        "top": round(self._screen_h * ratios["top"]),
                        "left": round(self._screen_w * ratios["left"]),
                        "width": round(self._screen_w * ratios["width"]),
                        "height": round(self._screen_h * ratios["height"]),
                    }
                )
                self._log(f"[Calibration] Bar ROI (ratio) -> {self._roi_bar}")
            else:
                raise ValueError("no valid ratio data")
        except Exception:
            scale_w = self._screen_w / _DEFAULT_SCREEN_W
            scale_h = self._screen_h / _DEFAULT_SCREEN_H
            self._roi_bar = self._offset_roi(
                {
                    "top": int(118 * scale_h),
                    "left": int(1209 * scale_w),
                    "width": int(1441 * scale_w),
                    "height": int(64 * scale_h),
                }
            )
            self._log(f"[Calibration] Bar ROI (fallback) -> {self._roi_bar}")

        # --- Button ROI ---
        scale_w = self._screen_w / _DEFAULT_SCREEN_W
        scale_h = self._screen_h / _DEFAULT_SCREEN_H
        self._roi_button = self._offset_roi(
            {
                "top": int(1760 * scale_h),
                "left": int(3400 * scale_w),
                "width": int(440 * scale_w),
                "height": int(360 * scale_h),
            }
        )
        self._log(f"[Calibration] Button ROI -> {self._roi_button}")

        self._roi_bar_default = dict(self._roi_bar)
        self._roi_button_default = dict(self._roi_button)
        self._roi_offsets_applied = None
        self._apply_roi_offsets()

        self._load_error_roi()

        self._log("[Calibration] Done.")

    def _load_error_roi(self) -> None:
        error_json = _resource_path("templates", "error.json")
        if not os.path.exists(error_json):
            return
        try:
            with open(error_json, encoding="utf-8") as handle:
                data = json.load(handle)
            if data and isinstance(data, list) and "ratios" in data[0]:
                ratios = data[0]["ratios"]
                self._roi_error = self._offset_roi(
                    {
                        "top": round(self._screen_h * ratios["top"]),
                        "left": round(self._screen_w * ratios["left"]),
                        "width": round(self._screen_w * ratios["width"]),
                        "height": round(self._screen_h * ratios["height"]),
                    }
                )
                self._log(f"[Calibration] Loaded dialog ROI -> {self._roi_error}")
        except Exception as exc:
            self._log(f"Failed to load {error_json}: {exc}", logging.ERROR)

    def run(self) -> None:
        os.chdir(APP_DIR)

        if self._stop_flag:
            self._is_paused = True
            self._is_stopped = True
            self._push_status()
            return

        self._is_stopped = False
        self._stop_reason = ""
        self._log("Main loop started.")
        self._session_start = time.time()
        self._last_time = time.time()

        capture_failures = 0
        try:
            while not self._stop_flag:
                now = time.time()
                dt = now - self._last_time
                self._last_time = now
                if dt > 0:
                    current_fps = 1.0 / dt
                    self._fps = self._fps * 0.9 + current_fps * 0.1

                self._poll_commands()
                self._push_status()

                if self._is_paused:
                    self._stop_event.wait(timeout=0.1)
                    continue

                self._active_secs += max(0.0, min(dt, 5.0))
                if self._run_time_limit_reached():
                    continue

                if self._start_delay_pending:
                    self._start_delay_pending = False
                    self._wait_start_delay()
                    continue

                try:
                    self._tick()
                    capture_failures = 0
                except CaptureError as exc:
                    capture_failures += 1
                    self.input.release_all()
                    if capture_failures >= _MAX_CAPTURE_FAILURES:
                        self._log(
                            f"Screen capture failed {capture_failures} times in a row: {exc}",
                            logging.ERROR,
                        )
                        self._stop_reason = "Screen capture failed repeatedly"
                        break
                    self._log(
                        f"Screen capture failed ({capture_failures}/{_MAX_CAPTURE_FAILURES}): {exc}",
                        logging.WARNING,
                    )
                    self._stop_event.wait(timeout=0.5)
        except KeyboardInterrupt:
            self._log("Ctrl+C received.")
        except Exception as exc:
            log.exception("Bot crashed")
            self._stop_reason = f"Crashed: {type(exc).__name__}"
        finally:
            self._is_paused = True
            self._is_stopped = True
            self._last_pid_out = 0.0
            self._fps = 0.0
            try:
                self.input.release_all()
            except Exception:
                log.debug("Failed to release held keys during shutdown.", exc_info=True)
            try:
                self.capture.close()
            except Exception:
                log.debug(
                    "Failed to close capture module during shutdown.", exc_info=True
                )
            try:
                if self._csv_handle:
                    self._csv_handle.close()
                    self._csv_handle = None
            except Exception:
                log.debug(
                    "Failed to close debug CSV handle during shutdown.", exc_info=True
                )
            try:
                self._session_manager.end_session()
            except Exception:
                log.debug("Failed to close session on shutdown.", exc_info=True)
            try:
                self._push_status()
                self._log(f"Bot stopped. Fish caught: {self._fish_count}")
            except Exception:
                log.debug("Failed to push final status during shutdown.", exc_info=True)

    def _tick(self) -> None:
        """Run one iteration of the control loop."""
        self._apply_roi_offsets()
        state = self.sm.state

        # Preserve the current state unless a higher-priority screen detection
        # overrides it: battle bars > bite prompt > casting/result handling.
        if state is not FishingState.STRUGGLING and self._detect_active_fishing():
            return

        if state is FishingState.IDLE:
            self._handle_idle()
        elif state is FishingState.WAITING:
            self._handle_waiting()
        elif state is FishingState.STRUGGLING:
            self._handle_struggling()
        elif state is FishingState.RESULT:
            self._handle_result()

    def _detect_active_fishing(self) -> bool:
        """Override the current state when bars or a bite prompt are visible."""
        if self._scan_battle_bars(self.sm.state):
            return True
        return self._detect_bite()

    def _detect_bite(self) -> bool:
        btn_img = self._grab(self._roi_button)
        self._publish_button_preview(btn_img)
        if not self.vision.check_blue_trigger(
            btn_img,
            self.cfg.hsv.blue,
            self._scaled_blue_pixels,
        ):
            return False
        self._log(f"[{self.sm.state.value}] Fish hooked (blue trigger).")
        self._enter_struggling()
        return True

    def _scan_battle_bars(self, state: FishingState) -> bool:
        """Reserve priority for visible bars, entering after consecutive frames."""
        if not self._roi_bar:
            return False
        bar_img = self._grab(self._roi_bar)
        hsv_img = self.vision.to_hsv(bar_img)
        cursor_x, _ = self._find_cursor(bar_img, hsv_img)
        target_x, _ = self._find_target(bar_img, hsv_img)
        self._publish_bar_preview(
            bar_img,
            cursor_x,
            target_x,
            f"enter battle after {_BAR_ENTER_FRAMES} frames in a row "
            f"(now {getattr(self, '_bar_streak', 0)})",
        )
        if not self._battle_bars_all_visible(cursor_x, target_x):
            self._bar_streak = 0
            if state is FishingState.WAITING:
                self._sample_background(bar_img, cursor_x, target_x)
            return False
        self._bar_streak = getattr(self, "_bar_streak", 0) + 1
        if self._bar_streak < _BAR_ENTER_FRAMES:
            # Keep the current state while confirming; do not hook or recast.
            return True
        self._bar_streak = 0
        self._log(f"[{state.value}] Battle bars detected -> STRUGGLING.")
        self._enter_struggling(press_hook=False)
        self._push_status()
        return True

    def _find_cursor(self, bar_img, hsv_img=None, last_x=None):
        return self.vision.get_hsv_centroid_x(
            bar_img,
            self.cfg.hsv.cursor.lower,
            self.cfg.hsv.cursor.upper,
            min_area=self._scaled_min_area,
            ignore_margin_ratio=self.cfg.roi.ignore_margin_ratio,
            last_known_x=last_x,
            hsv_img=hsv_img,
        )

    def _find_target(self, bar_img, hsv_img=None, last_x=None):
        return self.vision.get_hsv_centroid_x(
            bar_img,
            self.cfg.hsv.safe_zone.lower,
            self.cfg.hsv.safe_zone.upper,
            min_area=self._scaled_min_area,
            ignore_margin_ratio=0.0,
            last_known_x=last_x,
            hsv_img=hsv_img,
        )

    def _publish_icon_preview(self, img, count: int) -> None:
        bridge = getattr(self, "bridge", None)
        if bridge is None or not self.cfg.tracker_preview_enabled:
            return
        try:
            bridge.preview["icons"] = render_icon_preview(img)
            bridge.preview["icons_text"] = (
                f"icons {count} (failed cast at >= {self.cfg.cast_icon_fail_min})"
            )
            bridge.preview["version"] += 1
        except Exception:
            log.debug("Icon preview failed.", exc_info=True)

    def _selected_bars(self, cursor_x, target_x) -> list[bool]:
        """Visibility of each bar chosen for battle detection."""
        use_cursor = self.cfg.battle_detect_cursor
        use_target = self.cfg.battle_detect_safe_zone
        if not use_cursor and not use_target:
            use_cursor = use_target = True  # never let detection be fully disabled
        seen = []
        if use_cursor:
            seen.append(cursor_x is not None)
        if use_target:
            seen.append(target_x is not None)
        return seen

    def _battle_bars_visible(self, cursor_x, target_x) -> bool:
        """True while ANY selected bar is on screen (used to stay in the fight)."""
        return any(self._selected_bars(cursor_x, target_x))

    def _battle_bars_all_visible(self, cursor_x, target_x) -> bool:
        """True when EVERY selected bar is on screen (used to enter the fight)."""
        return all(self._selected_bars(cursor_x, target_x))

    def _enter_struggling(self, press_hook: bool = True) -> None:
        """Common setup when transitioning into STRUGGLING from any state."""
        self._bait_error_count = 0
        self._consecutive_waiting_timeouts = 0
        self._bar_detected_in_struggle = False
        self._battle_visible = False
        self._battle_absent_frames = 0
        self._bar_streak = 0
        self._assist_done = False
        self._reset_humanization_state()

        if press_hook:
            # Humanized hook reaction latency
            if self.cfg.humanization.enabled:
                react = sample_reaction(
                    self.cfg.humanization.hook_reaction_min,
                    self.cfg.humanization.hook_reaction_max,
                    self.cfg.humanization.hook_reaction_dist,
                )
                react = sample_timing(react, self.cfg.humanization)
                if react > 0:
                    self._stop_event.wait(timeout=react)
            hook_dur = self.cfg.timing.key_press_duration
            if self.cfg.humanization.enabled:
                hook_dur = sample_timing(hook_dur, self.cfg.humanization, minimum=0.02)
            self.input.press(self.cfg.keys.cast, hook_dur)
        self.pid.reset()
        self._lost_frames = 0
        self._lost_cursor_frames = 0
        self._lost_target_frames = 0
        self._cursor_x_rel = None
        self._cursor_last_seen = None
        self._target_x_rel = None
        self.sm.transition(FishingState.STRUGGLING)

    def _icon_check_active(self) -> bool:
        return bool(
            self.cfg.bait_error_detection_enabled
            and self.cfg.cast_icon_check_enabled
            and self._roi_icon
        )

    def _count_action_icons(self) -> int:
        img = self._grab(self._roi_icon)
        count = self.vision.count_icons(img, self._current_scale)
        self._publish_icon_preview(img, count)
        return count

    def _cast_failed_by_icons(self) -> bool:
        """True when the action-bar icons are still shown after the cast (no bait)."""
        need = self.cfg.cast_icon_fail_min
        if self._count_action_icons() < need:
            return False
        # confirm: the icons really are still there and not a passing frame
        self._stop_event.wait(timeout=_ERROR_CONFIRM_DELAY_SECS)
        return self._count_action_icons() >= need

    def _handle_cast_failure(self, detail: str) -> None:
        """Count a failed cast; stop once the bait-error limit is reached."""
        self._bait_error_count += 1
        self._log(
            f"[ERROR] Cast error ({self._bait_error_count}/{self.cfg.timing.bait_error_threshold}), "
            f"retrying... ({detail})"
        )
        self.input.release_all()
        err_wait = 5.0
        if self.cfg.humanization.enabled:
            err_wait = sample_timing(err_wait, self.cfg.humanization, minimum=3.0)
        self._stop_event.wait(timeout=err_wait)
        if self._stop_flag or self._detect_active_fishing():
            return
        if self._bait_error_count >= self.cfg.timing.bait_error_threshold:
            self._log("[ERROR] Bait likely exhausted, stopping bot.")
            self.request_stop("Bait error limit reached")
            self._push_status()
            return
        self.sm.transition(FishingState.IDLE)
        self._push_status()

    def _apply_limit_request(self) -> None:
        """Start counting the dashboard's auto-stop limits from now."""
        req = self.bridge.limit_request if self.bridge else None
        if req is None:
            return
        self.bridge.limit_request = None
        fish, secs = req
        self._fish_limit_target = self._fish_count + fish if fish > 0 else None
        self._time_limit_until = self._active_secs + secs if secs > 0 else None
        self._time_limit_notified = False
        self._log(
            f"[Limit] Auto stop set: {fish or '-'} fish / {secs or '-'} s from now."
        )

    def _run_time_limit_reached(self) -> bool:
        until = self._time_limit_until
        if until is None or self._active_secs < until:
            return False
        if self.sm.state is not FishingState.IDLE:
            # Let the current cast / fight / result finish; stop before the next cast.
            if not self._time_limit_notified:
                self._time_limit_notified = True
                self._log("[Limit] Time is up; stopping after the current fish.")
            return False
        self._log("[Limit] Run time limit reached.")
        self.request_stop("Run time limit reached")
        self._push_status()
        return True

    def _wait_start_delay(self) -> None:
        """Pause a random moment after start/resume before the first cast."""
        t = self.cfg.timing
        lo = max(0.0, min(t.start_delay_min_secs, t.start_delay_max_secs))
        hi = max(0.0, max(t.start_delay_min_secs, t.start_delay_max_secs))
        delay = random.uniform(lo, hi)  # nosec B311
        if delay > 0:
            self._log(f"[Start] Waiting {delay:.1f}s before the first cast.")
            self._stop_event.wait(timeout=delay)

    def _handle_idle(self) -> None:
        self._log("[IDLE] Casting...")
        cast_dur = self.cfg.timing.key_press_duration
        if self.cfg.humanization.enabled:
            cast_dur = sample_timing(cast_dur, self.cfg.humanization, minimum=0.02)
        self.input.press(self.cfg.keys.cast, cast_dur)
        use_icons = self._icon_check_active()
        error_check_delay = 0.3
        if self.cfg.humanization.enabled:
            error_check_delay = sample_timing(
                error_check_delay,
                self.cfg.humanization,
                minimum=0.1,
            )
        self._stop_event.wait(timeout=error_check_delay)
        # Wait out the rest of the cast animation
        anim_secs = self.cfg.timing.cast_animation_secs
        if self.cfg.humanization.enabled:
            anim_secs = sample_timing(anim_secs, self.cfg.humanization, minimum=0.8)
        remaining = anim_secs - error_check_delay
        if remaining > 0:
            self._stop_event.wait(timeout=remaining)
        if self._stop_flag:
            return
        if self._detect_active_fishing():
            return
        # The action-bar icons vanish once the line is cast; still visible = no cast.
        if use_icons and self._cast_failed_by_icons():
            # The screen may have changed during the icon confirmation delay.
            if self._stop_flag or self._detect_active_fishing():
                return
            self._handle_cast_failure("action-bar icons still visible")
            return
        self._enter_waiting()

    def _enter_waiting(self) -> None:
        timeout = self.cfg.timing.bite_timeout_secs
        if self.cfg.humanization.enabled:
            timeout = sample_timing(timeout, self.cfg.humanization, minimum=5.0)
        self._waiting_timeout_secs = timeout
        self._next_spam_at = 0.0
        self.sm.transition(FishingState.WAITING)

    def _gauge_assist_step(self, bar_img, cursor_x, target_x) -> None:
        """Measure the gauge on the first frames of a fight (assist only)."""
        if getattr(self, "_assist_done", True) or not self.cfg.gauge_assist_enabled:
            return
        assist = getattr(self, "_assist", None)
        if assist is None:
            return
        elapsed = self.sm.time_in_state
        safe, cursor = suggest_gauge_at_start(
            bar_img,
            (self.cfg.hsv.safe_zone.lower, self.cfg.hsv.safe_zone.upper),
            (self.cfg.hsv.cursor.lower, self.cfg.hsv.cursor.upper),
            getattr(self, "_background", None),
        )
        if safe is None or cursor is None:
            if elapsed > _ASSIST_WINDOW_SECS:
                self._assist_done = True
                assist.add_miss()
            return
        self._assist_done = True
        assist.add(safe, cursor, cursor_x is not None and target_x is not None)
        callback = (
            getattr(self.bridge, "assist_callback", None) if self.bridge else None
        )
        if callback is not None:
            try:
                callback()
            except Exception:
                log.debug("Gauge assist callback failed", exc_info=True)

    def _preview_due(self):
        """Return the bridge when a new tracker preview should be published."""
        bridge = getattr(self, "bridge", None)
        if bridge is None or not self.cfg.tracker_preview_enabled:
            return None
        now = time.perf_counter()
        if now < getattr(self, "_next_preview_at", 0.0):
            return None
        self._next_preview_at = now + _PREVIEW_INTERVAL_SECS
        return bridge

    def _judge_text(self, cursor_x, target_x, detail: str) -> str:
        """One line on how the bars are being judged, for the live tracker."""
        cfg = self.cfg
        used = []
        if cfg.battle_detect_cursor:
            used.append("cursor")
        if cfg.battle_detect_safe_zone:
            used.append("safe zone")
        if not used:
            used = ["cursor", "safe zone"]
        return (
            f"[{self.sm.state.value}] cursor {'found' if cursor_x is not None else '-'}, "
            f"safe zone {'found' if target_x is not None else '-'} | "
            f"used for battle: {' + '.join(used)} | {detail}"
        )

    def _publish_bar_preview(
        self, bar_img, cursor_x, target_x, detail: str = ""
    ) -> None:
        bridge = self._preview_due()
        if bridge is None:
            return
        try:
            bridge.preview["judge_text"] = self._judge_text(cursor_x, target_x, detail)
            bridge.preview["bar"] = render_bar_preview(
                bar_img,
                cursor_x,
                target_x,
                self.cfg.hsv.safe_zone,
                self.cfg.hsv.cursor,
            )
            bridge.preview["version"] += 1
        except Exception:
            log.debug("Bar preview failed.", exc_info=True)

    def _publish_button_preview(self, btn_img) -> None:
        bridge = getattr(self, "bridge", None)
        if bridge is None or not self.cfg.tracker_preview_enabled:
            return
        now = time.perf_counter()
        if now < getattr(self, "_next_button_preview_at", 0.0):
            return
        self._next_button_preview_at = now + _PREVIEW_INTERVAL_SECS
        try:
            rgba, count = render_button_preview(btn_img, self.cfg.hsv.blue)
            bridge.preview["button"] = rgba
            bridge.preview["blue_pixels"] = count
            bridge.preview["blue_threshold"] = int(self._scaled_blue_pixels)
            bridge.preview["version"] += 1
        except Exception:
            log.debug("Button preview failed.", exc_info=True)

    def _publish_ocr_preview(self) -> None:
        bridge = getattr(self, "bridge", None)
        if bridge is None or not self.cfg.tracker_preview_enabled:
            return
        try:
            for key in ("name", "weight"):
                region = self._ocr.last_regions.get(key)
                if region is None:
                    continue
                raw, binary, text = region
                bridge.preview[f"ocr_{key}"] = render_ocr_preview(raw, binary)
                bridge.preview[f"ocr_{key}_text"] = text
            bridge.preview["version"] += 1
        except Exception:
            log.debug("OCR preview failed.", exc_info=True)

    def _sample_background(self, bar_img, cursor_x, target_x) -> None:
        """While waiting the gauge is hidden: learn the colours behind it."""
        background = getattr(self, "_background", None)
        if background is None or cursor_x is not None or target_x is not None:
            return
        now = time.perf_counter()
        if now < getattr(self, "_next_bg_sample_at", 0.0):
            return
        self._next_bg_sample_at = now + _BG_SAMPLE_INTERVAL_SECS
        background.add(bar_img)

    def _maybe_switch_profile(self) -> None:
        """Apply the profile closest to the current background, if enabled."""
        background = getattr(self, "_background", None)
        if background is None or not self.cfg.profile_auto_switch:
            return
        if not self.cfg.profiles or background.samples < _PROFILE_MIN_SAMPLES:
            return
        now = time.perf_counter()
        if now < getattr(self, "_next_profile_check_at", 0.0):
            return
        self._next_profile_check_at = now + _PROFILE_CHECK_INTERVAL_SECS
        signature = background.signature()
        if signature is None:
            return
        profile = pick_profile(self.cfg.profiles, signature)
        if profile is None or profile["name"] == self.cfg.active_profile:
            return
        apply_profile(self.cfg, profile)
        scale_sq = self._current_scale * self._current_scale
        self._scaled_blue_pixels = int(max(self.cfg.min_blue_pixels * scale_sq, 1.0))
        self._log(f"[Profile] Switched to '{profile['name']}' (background match).")

    def _spam_cast_if_due(self) -> None:
        """Press the cast key at random intervals while waiting for a bite."""
        if not self.cfg.spam_cast_enabled:
            return
        now = time.perf_counter()
        if now < self._next_spam_at:
            return
        lo, hi = sorted(
            (self.cfg.spam_cast_interval_min, self.cfg.spam_cast_interval_max)
        )
        lo = max(lo, 0.1)
        self._next_spam_at = now + _RNG.uniform(lo, max(hi, lo))
        dur = self.cfg.timing.key_press_duration
        if self.cfg.humanization.enabled:
            dur = sample_timing(dur, self.cfg.humanization, minimum=0.02)
        self.input.press(self.cfg.keys.cast, dur)

    def _handle_waiting(self) -> None:
        if self._detect_bite():
            return
        if self.sm.time_in_state > self._waiting_timeout_secs:
            self._consecutive_waiting_timeouts += 1
            if self._consecutive_waiting_timeouts >= 2:
                self._log(
                    f"[WAITING] Consecutive timeout ({self._consecutive_waiting_timeouts}), "
                    "checking if stuck in result screen...",
                    logging.WARNING,
                )
                self._dismiss_result()
                self._consecutive_waiting_timeouts = 0
            else:
                self._log("[WAITING] Timeout, recasting.", logging.WARNING)

            self.sm.transition(FishingState.IDLE)
            return

        self._maybe_switch_profile()

        if self.cfg.spam_cast_enabled:
            self._spam_cast_if_due()

        poll = self.cfg.timing.waiting_poll_interval
        if self.cfg.humanization.enabled:
            poll = sample_timing(poll, self.cfg.humanization, minimum=0.005)
        self._stop_event.wait(timeout=poll)

    def _handle_struggling(self) -> None:
        if (
            self.sm.time_in_state > self.cfg.timing.max_struggle_secs
            # bars on screen keep the fight going, up to twice the limit as a
            # last resort against a false match that would never end
            and (
                not self._battle_visible
                or self.sm.time_in_state > 2 * self.cfg.timing.max_struggle_secs
            )
        ):
            self._log(
                f"[STRUGGLING] Max duration ({self.cfg.timing.max_struggle_secs}s) reached, ending.",
                logging.WARNING,
            )
            self.input.release_all()
            self.sm.transition(FishingState.RESULT)
            return

        bar_img = self._grab(self._roi_bar)
        hsv_img = self.vision.to_hsv(bar_img)

        last_cursor = (
            self._cursor_x_rel
            if self._cursor_x_rel is not None
            else getattr(self, "_cursor_last_seen", None)
        )
        cursor_x, _ = self._find_cursor(bar_img, hsv_img, last_cursor)
        target_x, _ = self._find_target(bar_img, hsv_img, self._target_x_rel)

        self._cursor_x_rel = cursor_x
        if cursor_x is not None:
            self._cursor_last_seen = cursor_x
        self._target_x_rel = target_x
        self._gauge_assist_step(bar_img, cursor_x, target_x)
        self._publish_bar_preview(
            bar_img,
            cursor_x,
            target_x,
            "in battle, stays while a used bar is visible "
            f"(bars gone for {self._battle_absent_frames}/"
            f"{self.cfg.timing.lost_frames_threshold} frames)",
        )

        output = 0.0
        action = "NONE"
        error = 0.0

        self._battle_visible = self._battle_bars_visible(cursor_x, target_x)
        if self._battle_visible:
            self._bar_detected_in_struggle = True
            self._battle_absent_frames = 0
        else:
            self._battle_absent_frames += 1

        if cursor_x is not None and target_x is not None:
            self.pid.update_params(
                kp=self.cfg.pid.kp,
                ki=self.cfg.pid.ki,
                kd=self.cfg.pid.kd,
                deadband=self.cfg.pid.deadband,
                adaptive=self.cfg.pid.adaptive,
                integral_limit=self.cfg.pid.integral_limit,
                ema_alpha=self.cfg.pid.ema_alpha,
                max_dt=self.cfg.pid.max_dt,
            )
            self._lost_frames = 0
            self._lost_cursor_frames = 0
            self._lost_target_frames = 0
            error = float(target_x) - float(cursor_x)
            bar_half = self._roi_bar.get("width", 400) / 2
            output = self.pid.update(
                float(cursor_x), float(target_x), bar_half_width=bar_half
            )
            self._last_pid_out = output
            hcfg = self.cfg.humanization
            deadband = self.cfg.pid.deadband
            bar_width = self._roi_bar.get("width", 400)
            intensity = min(1.0, abs(error) / max(bar_width / 2, 1.0))

            if hcfg.enabled:
                now = time.perf_counter()

                # PID noise overlay
                if hcfg.pid_noise_enabled:
                    output += sample_noise(
                        hcfg.pid_noise_amplitude, hcfg.pid_noise_dist
                    )

                # Determine the desired action based on PID output
                desired_action = "NONE"
                if output > deadband:
                    desired_action = "RIGHT"
                elif output < -deadband:
                    desired_action = "LEFT"

                # Check if we need to start a new reaction delay
                if desired_action != self._hum_target_action:
                    self._hum_flick_pending = desired_action in {
                        "LEFT",
                        "RIGHT",
                    } and self._hum_target_action in {"LEFT", "RIGHT"}
                    self._hum_target_action = desired_action

                    # Adaptive humanization
                    if hcfg.adaptive_enabled:
                        latency_factor = max(
                            hcfg.adaptive_latency_min_scale,
                            1.0 - intensity * (1.0 - hcfg.adaptive_latency_min_scale),
                        )
                    else:
                        latency_factor = 1.0

                    react_delay = sample_reaction(
                        hcfg.reaction_latency_min * latency_factor,
                        hcfg.reaction_latency_max * latency_factor,
                        hcfg.reaction_latency_dist,
                    )

                    # If we are just stopping, or continuing a similar motion, reduce latency
                    if (
                        desired_action == "NONE"
                        or (desired_action == "RIGHT" and self._last_action == "RIGHT")
                        or (desired_action == "LEFT" and self._last_action == "LEFT")
                    ):
                        react_delay *= 0.3

                    self._hum_reaction_end = now + react_delay

                # Determine the *effective* action we should take right now
                if now < self._hum_reaction_end:
                    # Still in reaction time, keep doing whatever we were doing (or NONE if we just started)
                    effective_action = self._last_action
                else:
                    effective_action = self._hum_target_action

                # Handle pulsing logic for the effective action
                if effective_action == "RIGHT" or effective_action == "LEFT":
                    target_key = (
                        self.cfg.keys.right
                        if effective_action == "RIGHT"
                        else self.cfg.keys.left
                    )
                    opposite_key = (
                        self.cfg.keys.left
                        if effective_action == "RIGHT"
                        else self.cfg.keys.right
                    )

                    # Release the opposite key immediately
                    self.input.release(opposite_key)

                    # Manage pulsing state machine
                    if self._hum_pulse_state == "IDLE" or now >= self._hum_pulse_end:
                        if (
                            self._hum_pulse_state == "GAP"
                            or self._hum_pulse_state == "IDLE"
                        ):
                            # Transition to HOLD
                            allow_flick = (
                                self._hum_flick_pending
                                and effective_action == self._hum_target_action
                            )
                            pulse = sample_movement_pulse(
                                hcfg,
                                allow_flick=allow_flick,
                            )
                            if allow_flick:
                                self._hum_flick_pending = False
                            if hcfg.adaptive_enabled:
                                hold_factor = 1.0 + intensity * (
                                    hcfg.adaptive_pulse_hold_max_scale - 1.0
                                )
                            else:
                                hold_factor = 1.0

                            if pulse.random_action:
                                random_key = (
                                    self.cfg.keys.right
                                    if pulse.random_direction > 0
                                    else self.cfg.keys.left
                                )
                                self.input.pulse_hold(
                                    random_key,
                                    sample_timing(
                                        pulse.random_duration,
                                        hcfg,
                                        minimum=0.005,
                                    ),
                                    0.0,
                                    self._stop_event,
                                )
                                if self._stop_event.is_set():
                                    self.input.release_all()
                                    return
                                now = time.perf_counter()

                            hold_t = (
                                _RNG.uniform(
                                    hcfg.pulse_hold_min * hold_factor,
                                    hcfg.pulse_hold_max * hold_factor,
                                )
                                * pulse.hold_scale
                            )
                            hold_t = sample_timing(hold_t, hcfg, minimum=0.005)
                            self._hum_gap_scale = pulse.gap_scale
                            self._hum_pulse_end = now + hold_t
                            self._hum_pulse_state = "HOLD"
                            self.input.hold(target_key)
                        else:
                            # Transition to GAP (Release)
                            if hcfg.adaptive_enabled:
                                gap_factor = max(
                                    hcfg.adaptive_pulse_gap_min_scale,
                                    1.0
                                    - intensity
                                    * (1.0 - hcfg.adaptive_pulse_gap_min_scale),
                                )
                            else:
                                gap_factor = 1.0
                            gap_t = (
                                _RNG.uniform(
                                    hcfg.pulse_release_min * gap_factor,
                                    hcfg.pulse_release_max * gap_factor,
                                )
                                * self._hum_gap_scale
                            )
                            gap_t = sample_timing(gap_t, hcfg, minimum=0.005)
                            self._hum_pulse_end = now + gap_t
                            self._hum_pulse_state = "GAP"
                            self.input.release(target_key)

                    action = effective_action
                else:
                    # Effective action is NONE
                    self.input.release(self.cfg.keys.left)
                    self.input.release(self.cfg.keys.right)
                    self._hum_pulse_state = "IDLE"

                    if self._should_send_deadband_tap():
                        tap_dir = (
                            self.cfg.keys.right if error > 0 else self.cfg.keys.left
                        )
                        tap_dur = _RNG.uniform(
                            hcfg.deadband_tap_duration_min,
                            hcfg.deadband_tap_duration_max,
                        )
                        tap_dur = sample_timing(tap_dur, hcfg, minimum=0.005)
                        # We use pulse_hold here safely since deadband taps are tiny and rare,
                        # but ideally this should also be non-blocking. Let's just use pulse_hold as it's quick.
                        # Wait, tap_dur is ~0.02s, which is a tiny block, acceptable in deadband.
                        self.input.pulse_hold(tap_dir, tap_dur, 0.0, self._stop_event)

                    action = "NONE"
            else:
                if output > deadband:
                    self.input.hold(self.cfg.keys.right)
                    self.input.release(self.cfg.keys.left)
                    action = "RIGHT"
                elif output < -deadband:
                    self.input.hold(self.cfg.keys.left)
                    self.input.release(self.cfg.keys.right)
                    action = "LEFT"
                else:
                    self.input.release(self.cfg.keys.left)
                    self.input.release(self.cfg.keys.right)
                    action = "NONE"

            self._last_action = action
        else:
            self.input.release(self.cfg.keys.left)
            self.input.release(self.cfg.keys.right)
            self._last_pid_out = 0.0
            if cursor_x is None:
                self._lost_cursor_frames += 1
            else:
                self._lost_cursor_frames = 0
            if target_x is None:
                self._lost_target_frames += 1
            else:
                self._lost_target_frames = 0
            self._lost_frames += 1
            action = "LOST"

            if self._lost_frames % 10 == 0:
                missing = []
                if cursor_x is None:
                    missing.append("Cursor")
                if target_x is None:
                    missing.append("Safe zone")
                self._log(
                    f"[STRUGGLING] Missing: {', '.join(missing)} "
                    f"({self._lost_frames}/{self.cfg.timing.lost_frames_threshold})",
                    logging.DEBUG,
                )

        if self.cfg.debug_mode:
            cursor_text = f"{cursor_x}" if cursor_x is not None else "None"
            target_text = f"{target_x}" if target_x is not None else "None"
            try:
                if not self._csv_handle:
                    csv_path = os.path.join(
                        APP_DIR, scoped_runtime_name("fishing_data.csv")
                    )
                    self._csv_handle = open(csv_path, "a", newline="", encoding="utf-8")
                    self._csv_writer = csv.writer(self._csv_handle)

                self._csv_writer.writerow(
                    [
                        f"{time.time():.3f}",
                        cursor_text,
                        target_text,
                        f"{error:.1f}",
                        f"{output:.3f}",
                        action,
                    ]
                )
                # Flush occasionally or let OS handle it for performance
                if _RNG.random() < 0.05:
                    self._csv_handle.flush()
            except Exception:
                log.debug("Failed to append debug CSV row.", exc_info=True)

        if self._battle_absent_frames >= self.cfg.timing.lost_frames_threshold:
            self._log(
                "[STRUGGLING] Battle bars gone "
                f"for {self._battle_absent_frames} frames."
            )
            self.input.release_all()
            if self._bar_detected_in_struggle:
                self.sm.transition(FishingState.RESULT)
            else:
                self._log(
                    "[STRUGGLING] Never saw the battle bars — "
                    "assuming false hook, returning to hit wait.",
                    logging.WARNING,
                )
                self.input.release_all()
                self._enter_waiting()

        poll = self.cfg.timing.struggling_poll_interval
        if self.cfg.humanization.enabled:
            poll = sample_timing(poll, self.cfg.humanization, minimum=0.005)
        self._stop_event.wait(timeout=poll)

    def _append_catch(self, name: str, weight_g: str) -> None:
        """Write one catch to the active session and cache for the UI."""
        self._last_fish_name = name
        self._last_fish_weight_g = weight_g
        if self.cfg.fish_logging_enabled and (name or weight_g):
            self._session_manager.append_catch(name, weight_g)

    def _ocr_catch_screen(self) -> tuple[str, str]:
        """OCR the result card; returns ("", "") if logging is off, OCR is unavailable or fails."""
        if (
            not self.cfg.fish_logging_enabled
            or not self._screen_w
            or not self._screen_h
        ):
            return "", ""

        def _roi(ratios) -> dict:
            return ratios_to_roi(
                ratios, self._screen_w, self._screen_h, self._mon_x, self._mon_y
            )

        hide_ui = show_ui = None
        if self.bridge:
            try:
                import dearpygui.dearpygui as _dpg

                if _dpg.is_dearpygui_running():
                    hide_ui, show_ui = self._hide_ui, self._show_ui
            except ImportError:
                pass  # headless install without dearpygui
        return self._ocr.read(
            self.capture,
            _roi(self.cfg.ocr_name_roi_ratios),
            _roi(self.cfg.ocr_weight_roi_ratios),
            hide_ui=hide_ui,
            show_ui=show_ui,
        )

    def _handle_result(self) -> None:
        # Check for error dialog early — it auto-dismisses in ~2s
        if self._roi_error:
            err_img = self._grab(self._roi_error)
            if self.vision.check_error_region(
                err_img, white_pixel_min=self._scaled_error_white_min
            ):
                self._log("[RESULT] Error dialog detected (fish escaped?).")
                self.sm.transition(FishingState.IDLE)
                self._push_status()
                return

        result_w = self.cfg.timing.result_wait_secs
        if self.cfg.humanization.enabled:
            result_w = sample_timing(result_w, self.cfg.humanization, minimum=1.0)
        self._stop_event.wait(timeout=result_w)
        if self._stop_flag:
            return

        # Verify the mini-game actually ended before counting a fish.
        # If the cursor or safe zone is still visible on the bar, the
        # STRUGGLING → RESULT transition was premature (tracking was
        # temporarily lost). Release keys and go back to IDLE to recast.
        bar_img = self._grab(self._roi_bar)
        cur_x, _ = self._find_cursor(bar_img)
        tgt_x, _ = self._find_target(bar_img)
        if self._battle_bars_visible(cur_x, tgt_x):
            self._log(
                "[RESULT] Mini-game still active (bar elements detected) — "
                "recovering to IDLE.",
                logging.WARNING,
            )
            self.input.release_all()
            self.sm.transition(FishingState.IDLE)
            return

        fish_name, weight_g = self._ocr_catch_screen()
        self._publish_ocr_preview()
        self._fish_count += 1
        catch_info = f" ({fish_name}, {weight_g} g)" if fish_name or weight_g else ""
        self._log(f"[RESULT] Fish #{self._fish_count}{catch_info}.")
        self._append_catch(fish_name, weight_g)
        self._dismiss_result()
        self.sm.transition(FishingState.IDLE)
        target = self._fish_limit_target
        if target is not None and self._fish_count >= target:
            self._log("[Limit] Fish count limit reached.")
            self.request_stop("Fish count limit reached")
            self._push_status()

    def _dismiss_result(self) -> None:
        """Dismiss the result screen by clicking or pressing the exit key."""
        if self._stop_flag:
            return

        if self.cfg.spam_cast_enabled:
            # The cast-key spam while waiting closes the result screen.
            return

        if self.cfg.result_close_method == "click":
            base_x = self._screen_w // 2 if self._screen_w else _RESULT_CLOSE_FALLBACK_X
            # Typically click towards the lower middle (e.g. around 75% height)
            base_y = (
                int(self._screen_h * 0.75)
                if self._screen_h
                else int(_RESULT_CLOSE_FALLBACK_Y * 1.5)
            )

            if self.cfg.humanization.enabled:
                hcfg = self.cfg.humanization
                cx = (
                    self._mon_x
                    + base_x
                    + _RNG.randint(-hcfg.mouse_offset_x, hcfg.mouse_offset_x)
                )
                cy = (
                    self._mon_y
                    + base_y
                    + _RNG.randint(-hcfg.mouse_offset_y, hcfg.mouse_offset_y)
                )
                self.input.humanized_click(
                    cx,
                    cy,
                    amp=hcfg.mouse_move_curve_amplitude,
                    d_min=hcfg.mouse_move_duration_min,
                    d_max=hcfg.mouse_move_duration_max,
                )
            else:
                cx = self._mon_x + base_x
                cy = self._mon_y + base_y
                self.input.click(cx, cy)
        else:
            exit_dur = self.cfg.timing.key_press_duration
            if self.cfg.humanization.enabled:
                exit_dur = sample_timing(exit_dur, self.cfg.humanization, minimum=0.02)
            self.input.press(self.cfg.keys.exit, exit_dur)

        close_delay = 0.5
        if self.cfg.humanization.enabled:
            close_delay = sample_timing(close_delay, self.cfg.humanization, minimum=0.2)
        self._stop_event.wait(timeout=close_delay)


def run_headless(argv: list[str] | None = None) -> None:
    """Run the command-line interface (shared by main.py and the GUI executable)."""
    # Validate dependencies before runtime startup.
    from modules.deps import CLI_PACKAGES, exit_if_missing_dependencies

    exit_if_missing_dependencies(CLI_PACKAGES)

    from modules.cli import _set_dpi_awareness, run_cli

    setup_logging()
    ensure_settings_loaded()
    _set_dpi_awareness()
    run_cli(NTEFishingBot, argv)


if __name__ == "__main__":
    run_headless()
