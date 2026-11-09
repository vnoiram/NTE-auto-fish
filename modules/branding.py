"""Build-time branding loaded from an optional bundled manifest."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass

from modules.utils import bundled_path

log = logging.getLogger("NTEFish")

_DEFAULT_APP_NAME = "NTE Auto-Fish"
_BRANDING_MANIFEST = "build_brand.json"
_CUSTOM_ICON = "build_icon.ico"


@dataclass(frozen=True)
class Branding:
    app_name: str = _DEFAULT_APP_NAME
    build_id: str = ""


def _valid_app_name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if (
        not value
        or not value.isascii()
        or len(value) > 80
        or any(ord(char) < 32 for char in value)
    ):
        return None
    return value


def _valid_build_id(value: object) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if not value or len(value) > 32:
        return ""
    if not all(char.isascii() and (char.isalnum() or char in "._-") for char in value):
        return ""
    return value


def load_branding() -> Branding:
    manifest_path = bundled_path(_BRANDING_MANIFEST)
    try:
        with open(manifest_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return Branding()
    except (OSError, ValueError, TypeError):
        log.warning("Ignoring invalid build branding manifest: %s", manifest_path)
        return Branding()

    app_name = _valid_app_name(payload.get("app_name"))
    build_id = _valid_build_id(payload.get("build_id"))
    return Branding(app_name=app_name or _DEFAULT_APP_NAME, build_id=build_id)


BRANDING = load_branding()
APP_NAME = BRANDING.app_name
BUILD_ID = BRANDING.build_id


def _storage_namespace(branding: Branding) -> str:
    if not branding.build_id:
        return ""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", branding.app_name).strip("-.")
    return f"{slug[:40] or 'Application'}-b{branding.build_id}"


STORAGE_NAMESPACE = _storage_namespace(BRANDING)


def scoped_runtime_name(name: str, namespace: str | None = None) -> str:
    """Add a build namespace to a runtime file or directory name."""
    namespace = STORAGE_NAMESPACE if namespace is None else namespace
    if not namespace:
        return name
    stem, extension = os.path.splitext(name)
    return f"{stem}-{namespace}{extension}"


def app_icon_path() -> str:
    custom_icon = bundled_path(_CUSTOM_ICON)
    if os.path.isfile(custom_icon):
        return custom_icon
    return bundled_path("assets", "icons", "app.ico")
