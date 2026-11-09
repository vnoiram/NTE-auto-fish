"""Detection profiles that are picked by the colours of the scene background.

A profile stores the HSV ranges and the bite pixel threshold together with a
compact signature of the background it was recorded against (for example day,
sunset or night). The closest profile to the current background is applied.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("NTEFish")

# L1 distance between two normalised signatures (range 0..4).
DEFAULT_MAX_DISTANCE = 2.0
_HSV_KEYS = ("safe_zone", "cursor", "blue")


def make_profile(name: str, cfg, signature) -> dict[str, Any]:
    """Snapshot the current detection settings as a profile."""
    return {
        "name": name,
        "signature": [round(float(x), 4) for x in signature],
        "min_blue_pixels": int(cfg.min_blue_pixels),
        "hsv": {
            key: {
                "lower": list(getattr(cfg.hsv, key).lower),
                "upper": list(getattr(cfg.hsv, key).upper),
            }
            for key in _HSV_KEYS
        },
    }


def _valid(profile: Any) -> bool:
    try:
        return (
            isinstance(profile["name"], str)
            and len(profile["signature"]) > 0
            and all(len(profile["hsv"][k]["lower"]) == 3 for k in _HSV_KEYS)
            and all(len(profile["hsv"][k]["upper"]) == 3 for k in _HSV_KEYS)
        )
    except (KeyError, TypeError):
        return False


def upsert_profile(profiles: list, profile: dict) -> None:
    """Add a profile, replacing any existing one with the same name."""
    for i, existing in enumerate(profiles):
        if isinstance(existing, dict) and existing.get("name") == profile["name"]:
            profiles[i] = profile
            return
    profiles.append(profile)


def apply_profile(cfg, profile: dict) -> None:
    """Write a profile's detection settings into cfg (ranges are updated in place)."""
    for key in _HSV_KEYS:
        target = getattr(cfg.hsv, key)
        target.lower = tuple(int(v) for v in profile["hsv"][key]["lower"])
        target.upper = tuple(int(v) for v in profile["hsv"][key]["upper"])
    cfg.min_blue_pixels = int(profile["min_blue_pixels"])
    cfg.active_profile = profile["name"]


def pick_profile(
    profiles: list, signature, max_distance: float = DEFAULT_MAX_DISTANCE
) -> dict | None:
    """Return the profile closest to signature, or None if none is close enough."""
    best, best_dist = None, max_distance
    for profile in profiles:
        if not _valid(profile) or len(profile["signature"]) != len(signature):
            continue
        dist = sum(abs(a - b) for a, b in zip(profile["signature"], signature))
        if dist <= best_dist:
            best, best_dist = profile, dist
    return best


# Background signatures measured from daytime, evening and night game screenshots.
_DAY_SIGNATURE = (
    0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
    0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
    0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0009, 0.0083, 0.8164,
    0.0897, 0.0766, 0.0047, 0.0033, 0.0001, 0.0000, 0.0000, 0.0000, 0.0000,
    0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
    0.0000, 0.0000, 0.0000, 0.5657, 0.2136, 0.1589, 0.0532, 0.0086,
)
_NIGHT_SIGNATURE = (
    0.0139, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
    0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
    0.0000, 0.0000, 0.0000, 0.0000, 0.0003, 0.0000, 0.0000, 0.0019, 0.9392,
    0.0306, 0.0032, 0.0007, 0.0023, 0.0011, 0.0037, 0.0028, 0.0002, 0.0000,
    0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
    0.0079, 0.0578, 0.1429, 0.3878, 0.2509, 0.1231, 0.0257, 0.0040,
)
_EVENING_SIGNATURE = (
    0.0076, 0.0396, 0.0619, 0.0852, 0.4655, 0.2432, 0.0622, 0.0111, 0.0034,
    0.0008, 0.0003, 0.0002, 0.0003, 0.0057, 0.0020, 0.0002, 0.0000, 0.0000,
    0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
    0.0000, 0.0000, 0.0000, 0.0000, 0.0001, 0.0015, 0.0004, 0.0001, 0.0000,
    0.0001, 0.0001, 0.0002, 0.0003, 0.0004, 0.0015, 0.0017, 0.0019, 0.0023,
    0.0006, 0.0150, 0.2495, 0.3042, 0.1124, 0.0762, 0.1057, 0.1364,
)


def default_profiles() -> list[dict[str, Any]]:
    """Built-in day, evening and night profiles; HSV values start at the defaults."""
    from config import HsvConfig

    hsv = HsvConfig()
    profiles = []
    for name, signature in (
        ("Day", _DAY_SIGNATURE),
        ("Evening", _EVENING_SIGNATURE),
        ("Night", _NIGHT_SIGNATURE),
    ):
        profiles.append(
            {
                "name": name,
                "signature": [round(float(x), 4) for x in signature],
                "min_blue_pixels": 300,
                "hsv": {
                    key: {
                        "lower": list(getattr(hsv, key).lower),
                        "upper": list(getattr(hsv, key).upper),
                    }
                    for key in _HSV_KEYS
                },
            }
        )
    return profiles
