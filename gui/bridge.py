"""Thread-safe bridge between the bot worker and the DearPyGui UI."""

import dataclasses
import logging
import queue
import time

from modules.logic import FishingState


@dataclasses.dataclass
class BotStatus:
    """Snapshot pushed from the bot thread to the GUI."""

    state: FishingState = FishingState.IDLE
    fish_count: int = 0
    session_secs: float = 0.0
    pid_output: float = 0.0
    cursor_x: int | None = None
    target_x: int | None = None
    bar_width: int = 0
    button_roi: tuple[int, int, int, int] = (0, 0, 0, 0)
    bar_roi: tuple[int, int, int, int] = (0, 0, 0, 0)
    fps: float = 0.0
    lost_frames: int = 0
    lost_cursor_frames: int = 0
    lost_target_frames: int = 0
    is_running: bool = False
    is_stopped: bool = True
    scaled_min_area: float = 40.0
    current_scale: float = 1.0
    last_fish_name: str | None = None
    last_fish_weight_g: str | None = None
    stop_reason: str = ""
    bait_error_count: int = 0
    bait_error_limit: int = 3
    fish_left: int | None = None  # fish still to catch before the auto stop
    secs_left: float | None = None  # running seconds left before the auto stop


from modules.calibration import BackgroundSampler, GaugeAssist  # noqa: E402


class BotBridge:
    """Small queue-based boundary shared by GUI and bot threads."""

    def __init__(self) -> None:
        self._status_q: queue.Queue[BotStatus] = queue.Queue(maxsize=60)
        self._log_q: queue.Queue[str] = queue.Queue(maxsize=500)
        self._cmd_q: queue.Queue[str] = queue.Queue(maxsize=10)
        self._current_status = BotStatus()
        # Colours seen around the gauge while it is hidden; filled by the bot.
        self.background = BackgroundSampler()
        # Gauge measurements taken automatically at the start of each fight.
        self.gauge_assist = GaugeAssist()
        self.assist_callback = None  # called after each new measurement
        # True while the user is checking/adjusting the scan areas with the bot stopped.
        self.preview_active = False
        self.snapshot_request = False  # take a new full-screen snapshot for the area check
        # (fish, seconds) the user set on the dashboard; the bot counts from the moment
        # it picks it up. (0, 0) clears the auto stop.
        self.limit_request: tuple[int, int] | None = None
        self.snapshot_busy = False  # a snapshot is being taken right now
        # Live previews for the dashboard tracker (RGBA uint8 arrays or None).
        self.preview: dict = {
            "bar": None,
            "judge_text": "",
            "button": None,
            "icons": None,
            "icons_text": "",
            "ocr_name": None,
            "ocr_weight": None,
            "ocr_name_text": "",
            "ocr_weight_text": "",
            "icon_roi": None,
            "pump_status": "",
            "pump_log": [],  # recent area-check progress lines, newest last
            "bar_roi": None,
            "button_roi": None,
            "blue_pixels": 0,
            "blue_threshold": 0,
            "version": 0,
        }

    def push_status(self, status: BotStatus) -> None:
        """Push a status frame. Older frames are dropped when the GUI lags."""
        if self._status_q.full():
            try:
                self._status_q.get_nowait()
            except queue.Empty:
                pass
        try:
            self._status_q.put_nowait(status)
        except queue.Full:
            pass

    def push_log(self, msg: str) -> None:
        """Push a log message. The oldest entry is dropped if the queue is full."""
        if self._log_q.full():
            try:
                self._log_q.get_nowait()
            except queue.Empty:
                pass
        try:
            self._log_q.put_nowait(msg)
        except queue.Full:
            pass

    def poll_cmd(self) -> str | None:
        """Return the next command for the bot thread, if any."""
        try:
            return self._cmd_q.get_nowait()
        except queue.Empty:
            return None

    def latest_status(self) -> BotStatus:
        """Drain pending status frames and return only the newest snapshot."""
        latest = self._current_status
        while True:
            try:
                latest = self._status_q.get_nowait()
            except queue.Empty:
                break
        self._current_status = latest
        return latest

    def drain_logs(self) -> list[str]:
        """Return all logs waiting to be rendered."""
        msgs = []
        while True:
            try:
                msgs.append(self._log_q.get_nowait())
            except queue.Empty:
                break
        return msgs

    def send_cmd(self, cmd: str) -> None:
        """Queue a GUI command for the bot.

        Stop is urgent: stale commands are cleared so the worker sees it as
        soon as possible. For other commands, the oldest pending command is
        dropped instead of silently losing the latest user action.
        """
        if cmd == "stop":
            self._drain_cmds()
        try:
            self._cmd_q.put_nowait(cmd)
        except queue.Full:
            try:
                self._cmd_q.get_nowait()
                self._cmd_q.put_nowait(cmd)
            except (queue.Empty, queue.Full):
                pass

    def _drain_cmds(self) -> None:
        while True:
            try:
                self._cmd_q.get_nowait()
            except queue.Empty:
                break


class BridgeHandler(logging.Handler):
    """A logging handler that redirects formatted logs to a BotBridge."""

    def __init__(self, bridge: BotBridge) -> None:
        super().__init__()
        self.bridge = bridge

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.bridge.push_log(msg)
        except Exception:
            self.handleError(record)


def _fmt_time() -> str:
    t = time.localtime()
    return f"{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}"
