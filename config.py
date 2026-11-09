"""Single source of runtime configuration for NTE Auto-Fish."""

import json
import logging
import math
import os
import threading
from dataclasses import asdict, dataclass, field
from random import SystemRandom

from modules.branding import scoped_runtime_name
from modules.profiles import default_profiles
from modules.utils import APP_DIR

DEFAULT_SETTINGS_PATH = os.path.join(APP_DIR, scoped_runtime_name("settings.json"))
SUPPORTED_LANGUAGES = frozenset({"en", "ja"})
log = logging.getLogger("NTEFish")
_RNG = SystemRandom()


_INVALID = object()
_HSV_MAX = (179, 255, 255)


def _validate_hsv_triplet(key: str, value):
    """Return a (H, S, V) tuple of ints within OpenCV's 8-bit HSV limits, or _INVALID."""
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return _INVALID
    out = []
    for item, limit in zip(value, _HSV_MAX):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return _INVALID
        if not 0 <= item <= limit:
            return _INVALID
        out.append(int(item))
    return tuple(out)


def _coerce_setting(current, value, allow_negative=False):
    """Validate a loaded value against the type of the current default; _INVALID if unusable."""
    if isinstance(current, bool):
        return value if isinstance(value, bool) else _INVALID
    if isinstance(current, (int, float)):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return _INVALID
        if not math.isfinite(value) or (value < 0 and not allow_negative):
            return _INVALID
        return int(value) if isinstance(current, int) else float(value)
    if isinstance(current, str):
        return value if isinstance(value, str) else _INVALID
    if isinstance(current, tuple):
        if not isinstance(value, (list, tuple)) or len(value) != len(current):
            return _INVALID
        if not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in value
        ):
            return _INVALID
        return tuple(value)
    if isinstance(current, dict):
        return value if isinstance(value, dict) else _INVALID
    return value


@dataclass
class HsvRange:
    lower: tuple[int, int, int]
    upper: tuple[int, int, int]


@dataclass
class HsvConfig:
    blue: HsvRange = field(
        default_factory=lambda: HsvRange((100, 160, 140), (130, 255, 255))
    )
    safe_zone: HsvRange = field(
        default_factory=lambda: HsvRange((75, 190, 190), (100, 255, 255))
    )
    cursor: HsvRange = field(
        default_factory=lambda: HsvRange((18, 115, 240), (40, 150, 255))
    )


@dataclass
class PidConfig:
    kp: float = 0.45
    ki: float = 0.05
    kd: float = 0.005
    integral_limit: float = 150.0
    deadband: float = 5.0
    adaptive: bool = True
    ema_alpha: float = 0.25
    max_dt: float = 0.1


@dataclass
class RoiConfig:
    button: dict = field(
        default_factory=lambda: {
            "top": 1760,
            "left": 3400,
            "width": 440,
            "height": 360,
        }
    )
    bar: dict = field(
        default_factory=lambda: {
            "top": 60,
            "left": 700,
            "width": 2440,
            "height": 160,
        }
    )
    ignore_margin_ratio: float = 0.02
    # Manual corrections (pixels at the current resolution) when the game UI does not
    # sit where the ratio-based areas expect (windowed mode, other aspect ratios).
    bar_offset_x: int = 0
    bar_offset_y: int = 0
    bar_width_delta: int = 0
    bar_height_delta: int = 0
    button_offset_x: int = 0
    button_offset_y: int = 0


@dataclass
class TimingConfig:
    cast_animation_secs: float = 1.8
    bite_timeout_secs: float = 45.0
    lost_frames_threshold: int = 40
    result_wait_secs: float = 3.0
    key_press_duration: float = 0.05
    waiting_poll_interval: float = 0.05
    struggling_poll_interval: float = 0.01
    bait_error_threshold: int = 3
    max_struggle_secs: float = 120.0


@dataclass
class HumanizationConfig:
    enabled: bool = True

    # Key hold pulse modulation (STRUGGLING)
    pulse_hold_min: float = 0.040
    pulse_hold_max: float = 0.180
    pulse_release_min: float = 0.040
    pulse_release_max: float = 0.250

    # Deadband micro-corrections (STRUGGLING)
    deadband_tap_enabled: bool = True
    deadband_play_battle_chance: float = 0.50
    deadband_tap_chance: float = 0.30
    deadband_tap_duration_min: float = 0.015
    deadband_tap_duration_max: float = 0.035

    # Reaction latency (STRUGGLING)
    reaction_latency_min: float = 0.06
    reaction_latency_max: float = 0.25
    reaction_latency_dist: str = "uniform"  # "uniform" / "gaussian" / "exponential"

    # PID output noise overlay (STRUGGLING)
    pid_noise_enabled: bool = True
    pid_noise_amplitude: float = 3.0  # pixels
    pid_noise_dist: str = "gaussian"  # "uniform" / "gaussian"

    # Cursor movement styles (STRUGGLING)
    movement_scale_min: float = 0.85
    movement_scale_max: float = 1.25
    slow_move_chance: float = 0.20
    slow_move_hold_scale_min: float = 0.45
    slow_move_hold_scale_max: float = 0.75
    slow_move_gap_scale: float = 1.60
    flick_chance_on_reverse: float = 0.35
    flick_hold_scale_min: float = 1.60
    flick_hold_scale_max: float = 2.20
    flick_gap_scale: float = 0.45
    random_action_chance: float = 0.05
    random_action_duration_min: float = 0.012
    random_action_duration_max: float = 0.035

    # Adaptive humanization (Intensity-based focus)
    adaptive_enabled: bool = True
    adaptive_latency_min_scale: float = 0.3
    adaptive_pulse_gap_min_scale: float = 0.2
    adaptive_pulse_hold_max_scale: float = 1.5

    # Shared timing formula:
    # base * uniform(scale_min, scale_max)
    # + optional uniform(extra_min, extra_max)
    timing_scale_min: float = 0.85
    timing_scale_max: float = 1.15
    timing_extra_chance: float = 0.08
    timing_extra_min: float = 0.05
    timing_extra_max: float = 0.35

    # Mouse Trajectory (RESULT stage)
    mouse_move_curve_amplitude: int = 150
    mouse_move_duration_min: float = 0.15
    mouse_move_duration_max: float = 0.30
    mouse_offset_x: int = 150
    mouse_offset_y: int = 50

    # Hook Reaction Latency (WAITING stage)
    hook_reaction_min: float = 0.12
    hook_reaction_max: float = 0.45
    hook_reaction_dist: str = "gaussian"


@dataclass
class KeyConfig:
    cast: str = "f"
    left: str = "a"
    right: str = "d"
    exit: str = "esc"


@dataclass
class HotkeyConfig:
    toggle: str = "f8"
    stop: str = "f12"


@dataclass
class AppConfig:
    hsv: HsvConfig = field(default_factory=HsvConfig)
    pid: PidConfig = field(default_factory=PidConfig)
    roi: RoiConfig = field(default_factory=RoiConfig)
    timing: TimingConfig = field(default_factory=TimingConfig)
    keys: KeyConfig = field(default_factory=KeyConfig)
    hotkeys: HotkeyConfig = field(default_factory=HotkeyConfig)
    humanization: HumanizationConfig = field(default_factory=HumanizationConfig)
    language: str = "en"
    detection_min_area: float = 30.0
    min_blue_pixels: int = 300
    result_close_method: str = "click"
    # Fishing-battle detection: while any selected bar is visible, the bot stays in
    # the battle (STRUGGLING) state and never transitions elsewhere.
    battle_detect_cursor: bool = True
    battle_detect_safe_zone: bool = True
    # Press the cast key at random intervals while waiting for a bite. This also
    # closes the result screen and forces the bot into the fight if a bite is missed.
    spam_cast_enabled: bool = False
    spam_cast_interval_min: float = 0.4
    spam_cast_interval_max: float = 1.5
    # Measure the gauge colours at the start of every fight (assist only, never auto-applied).
    gauge_assist_enabled: bool = True
    # Stop when the cast-error dialog (bait exhausted) is detected. Turn off if a dark
    # scene is mistaken for the dialog and the bot never reaches the bite wait.
    bait_error_detection_enabled: bool = True
    # Show live capture previews (bar, bite prompt, OCR source) in the dashboard tracker.
    tracker_preview_enabled: bool = True
    # Detection profiles chosen by background colour (see modules/profiles.py).
    profiles: list = field(default_factory=default_profiles)
    profile_auto_switch: bool = False
    active_profile: str = ""
    debug_mode: bool = False
    always_on_top: bool = True
    monitor_index: int = 0
    fish_logging_enabled: bool = False
    ocr_name_roi_ratios: tuple = (0.35, 0.30, 0.65, 0.42)
    ocr_weight_roi_ratios: tuple = (0.45, 0.43, 0.55, 0.52)

    def save(self, path=None):
        path = path or DEFAULT_SETTINGS_PATH
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(asdict(self), handle, indent=4)
        os.replace(tmp_path, path)

    def reset(self, path=None):
        default_cfg = AppConfig()

        def reset_obj(target, source):
            for field_name in target.__dataclass_fields__:
                val = getattr(source, field_name)
                attr = getattr(target, field_name)
                if hasattr(attr, "__dataclass_fields__"):
                    reset_obj(attr, val)
                else:
                    setattr(target, field_name, val)

        reset_obj(self, default_cfg)
        self.save(path)

    def load(self, path=None):
        path = path or DEFAULT_SETTINGS_PATH
        if not os.path.exists(path):
            return
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)

            def update_obj(obj, values, path=""):
                for key, value in values.items():
                    if not hasattr(obj, key):
                        continue
                    attr = getattr(obj, key)
                    name = f"{path}{key}"
                    if isinstance(value, dict) and hasattr(
                        attr, "__dataclass_fields__"
                    ):
                        update_obj(attr, value, f"{name}.")
                        continue
                    if isinstance(obj, HsvRange):
                        value = _validate_hsv_triplet(key, value)
                    elif obj is self and key == "language":
                        value = value if value in SUPPORTED_LANGUAGES else _INVALID
                    else:
                        value = _coerce_setting(
                            attr,
                            value,
                            allow_negative=key.endswith(("_offset_x", "_offset_y", "_delta")),
                        )
                    if value is _INVALID:
                        log.warning("Ignoring invalid setting %s=%r", name, values[key])
                        continue
                    setattr(obj, key, value)

            update_obj(self, data)
        except (OSError, ValueError, TypeError) as exc:
            log.error("Failed to load settings from %s: %s", path, exc)


def jitter(base: float, spread: float, minimum: float = 0.0) -> float:
    """Return base +/- spread, clamped to [minimum, ...]."""
    if spread <= 0.0:
        return base
    return max(minimum, base + _RNG.uniform(-spread, spread))


def sample_reaction(min_val: float, max_val: float, dist: str = "uniform") -> float:
    """Sample a reaction delay from the specified distribution."""
    if min_val >= max_val:
        return min_val
    if dist == "gaussian":
        mean = (min_val + max_val) / 2
        std = (max_val - min_val) / 6  # 99.7% within range
        return max(min_val, min(max_val, _RNG.gauss(mean, std)))
    if dist == "exponential":
        span = max_val - min_val
        # mean = span/3, so most values cluster toward the low end
        return min(max_val, min_val + _RNG.expovariate(3.0 / span))
    return _RNG.uniform(min_val, max_val)


def sample_timing(
    base: float,
    cfg: HumanizationConfig,
    minimum: float = 0.0,
) -> float:
    """Apply the shared human timing formula to a base duration."""
    scale_min, scale_max = sorted((cfg.timing_scale_min, cfg.timing_scale_max))
    value = base * _RNG.uniform(max(0.0, scale_min), max(0.0, scale_max))

    chance = max(0.0, min(1.0, cfg.timing_extra_chance))
    if chance > 0.0 and _RNG.random() < chance:
        extra_min, extra_max = sorted((cfg.timing_extra_min, cfg.timing_extra_max))
        value += _RNG.uniform(max(0.0, extra_min), max(0.0, extra_max))

    return max(minimum, value)


def sample_noise(amplitude: float, dist: str = "gaussian") -> float:
    """Sample PID noise from the specified distribution."""
    if dist == "gaussian":
        return _RNG.gauss(0, amplitude / 2)
    return _RNG.uniform(-amplitude, amplitude)


@dataclass(frozen=True)
class MovementPulse:
    """Timing multipliers and an optional harmless extra tap for one pulse."""

    profile: str
    hold_scale: float
    gap_scale: float
    random_action: bool
    random_direction: int
    random_duration: float


def sample_movement_pulse(
    cfg: HumanizationConfig,
    allow_flick: bool = False,
) -> MovementPulse:
    """Sample a normal, slow, or direction-change flick pulse."""
    if allow_flick and _RNG.random() < cfg.flick_chance_on_reverse:
        profile = "flick"
        hold_scale = _RNG.uniform(
            cfg.flick_hold_scale_min,
            cfg.flick_hold_scale_max,
        )
        gap_scale = cfg.flick_gap_scale
    elif _RNG.random() < cfg.slow_move_chance:
        profile = "slow"
        hold_scale = _RNG.uniform(
            cfg.slow_move_hold_scale_min,
            cfg.slow_move_hold_scale_max,
        )
        gap_scale = cfg.slow_move_gap_scale
    else:
        profile = "normal"
        hold_scale = _RNG.uniform(
            cfg.movement_scale_min,
            cfg.movement_scale_max,
        )
        gap_scale = 1.0

    random_action = _RNG.random() < cfg.random_action_chance
    random_direction = -1 if _RNG.random() < 0.5 else 1
    random_duration = _RNG.uniform(
        cfg.random_action_duration_min,
        cfg.random_action_duration_max,
    )
    return MovementPulse(
        profile=profile,
        hold_scale=hold_scale,
        gap_scale=gap_scale,
        random_action=random_action,
        random_direction=random_direction,
        random_duration=random_duration,
    )


CFG = AppConfig()
_settings_loaded = False
_settings_lock = threading.Lock()


def ensure_settings_loaded() -> None:
    """Load the build-scoped settings file once. Called by entry points, not on import."""
    global _settings_loaded
    with _settings_lock:
        if not _settings_loaded:
            CFG.load()
            _settings_loaded = True
