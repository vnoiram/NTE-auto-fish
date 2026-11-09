#!/usr/bin/env python3
"""Build the Windows GUI executable with explicit, reproducible branding."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APP_NAME = "NTE Auto-Fish"
DEFAULT_ICON = Path("assets/icons/app.ico")

EXCLUDED_MODULES = (
    "unittest",
    "test",
    "pydoc",
    "multiprocessing",
    "asyncio",
    "sqlite3",
    "lib2to3",
    "distutils",
    "setuptools",
    "_decimal",
    "_lzma",
    "_bz2",
)


def validate_app_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("app name must not be empty")
    if not value.isascii():
        raise ValueError("app name must contain ASCII characters only")
    if len(value) > 80:
        raise ValueError("app name must be 80 characters or fewer")
    if any(ord(char) < 32 for char in value):
        raise ValueError("app name must not contain control characters")
    return value


def filename_slug(app_name: str) -> str:
    normalized = unicodedata.normalize("NFKD", app_name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", normalized).strip("-.")
    return slug or "Application"


def resolve_icon(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    if path.suffix.lower() != ".ico":
        raise ValueError("Windows builds require an .ico icon")
    if not path.is_file():
        raise ValueError(f"icon does not exist: {path}")
    return path


def read_version() -> str:
    return (ROOT / "version.txt").read_text(encoding="utf-8").strip()


def pyinstaller_command(
    app_name: str,
    icon_path: Path,
    brand_manifest: Path,
    bundled_icon: Path,
    dist_dir: Path,
) -> list[str]:
    slug = filename_slug(app_name)
    work_dir = ROOT / "build" / "pyinstaller"
    spec_dir = ROOT / "build" / "spec"
    add_data = os.pathsep
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        f"--icon={icon_path}",
        "--uac-admin",
        f"--add-data={ROOT / 'templates'}{add_data}templates",
        f"--add-data={ROOT / 'assets'}{add_data}assets",
        f"--add-data={ROOT / 'version.txt'}{add_data}.",
        f"--add-data={brand_manifest}{add_data}.",
        f"--add-data={bundled_icon}{add_data}.",
        "--collect-data=rapidocr",
        "--hidden-import=openpyxl",
        f"--distpath={dist_dir}",
        f"--workpath={work_dir}",
        f"--specpath={spec_dir}",
        f"--name={slug}",
    ]
    for module in EXCLUDED_MODULES:
        command.append(f"--exclude-module={module}")
    command.append(str(ROOT / "start_gui.py"))
    return command


def prepare_branding(app_name: str, icon_path: Path) -> tuple[Path, Path]:
    brand_dir = ROOT / "build" / "branding"
    brand_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = brand_dir / "build_brand.json"
    bundled_icon = brand_dir / "build_icon.ico"
    manifest_path.write_text(
        json.dumps({"app_name": app_name}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if icon_path != bundled_icon.resolve():
        shutil.copy2(icon_path, bundled_icon)
    return manifest_path, bundled_icon


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-name", default=DEFAULT_APP_NAME)
    parser.add_argument("--icon", default=str(DEFAULT_ICON))
    parser.add_argument("--dist-dir", default="dist")
    parser.add_argument("--github-env", help="Append FILENAME to a GitHub Actions env file")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print without building")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        app_name = validate_app_name(args.app_name)
        icon_path = resolve_icon(args.icon)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    dist_dir = Path(args.dist_dir)
    if not dist_dir.is_absolute():
        dist_dir = ROOT / dist_dir
    dist_dir = dist_dir.resolve()
    brand_dir = ROOT / "build" / "branding"
    manifest_path = brand_dir / "build_brand.json"
    bundled_icon = brand_dir / "build_icon.ico"
    command = pyinstaller_command(
        app_name,
        icon_path,
        manifest_path,
        bundled_icon,
        dist_dir,
    )

    if args.dry_run:
        print(subprocess.list2cmdline(command))
        return 0
    if os.name != "nt":
        print(
            "error: the application is Windows-only and PyInstaller is not a cross-compiler; "
            "run scripts/build-from-linux.sh from Linux instead",
            file=sys.stderr,
        )
        return 2
    if importlib.util.find_spec("PyInstaller") is None:
        print("error: install PyInstaller first: python -m pip install pyinstaller", file=sys.stderr)
        return 2

    manifest_path, bundled_icon = prepare_branding(app_name, icon_path)
    dist_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(command, cwd=ROOT, check=True)

    slug = filename_slug(app_name)
    built_exe = dist_dir / f"{slug}.exe"
    artifact_name = f"{slug}-v{read_version()}-Windows-x64.exe"
    artifact_path = dist_dir / artifact_name
    os.replace(built_exe, artifact_path)

    if args.github_env:
        with open(args.github_env, "a", encoding="utf-8") as handle:
            handle.write(f"FILENAME={artifact_name}\n")
    print(artifact_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
