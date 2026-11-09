#!/usr/bin/env python3
"""Trigger the Windows GitHub Actions build from a Linux workstation."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = "build.yml"
ARTIFACT = "NTE-Auto-Fish-GUI-Windows"


def run(*args: str, capture: bool = False) -> str:
    result = subprocess.run(
        args,
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout.strip() if capture else ""


def workflow_run_ids(ref: str) -> set[str]:
    output = run(
        "gh",
        "run",
        "list",
        "--workflow",
        WORKFLOW,
        "--event",
        "workflow_dispatch",
        "--branch",
        ref,
        "--limit",
        "20",
        "--json",
        "databaseId",
        "--jq",
        ".[].databaseId",
        capture=True,
    )
    return {line for line in output.splitlines() if line}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-name", default="NTE Auto-Fish")
    parser.add_argument("--icon", default="assets/icons/app.ico")
    parser.add_argument("--ref", help="Pushed branch or tag; defaults to the current branch")
    parser.add_argument("--output-dir", default="dist/remote")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for command in ("git", "gh"):
        if shutil.which(command) is None:
            print(f"error: required command not found: {command}", file=sys.stderr)
            return 2

    icon = Path(args.icon)
    if icon.is_absolute():
        print("error: --icon must be a repository-relative .ico path", file=sys.stderr)
        return 2
    if icon.suffix.lower() != ".ico" or not (ROOT / icon).is_file():
        print(f"error: icon is not an existing .ico file: {icon}", file=sys.stderr)
        return 2
    try:
        run("git", "ls-files", "--error-unmatch", str(icon), capture=True)
    except subprocess.CalledProcessError:
        print("error: the icon must be committed so the Windows runner can read it", file=sys.stderr)
        return 2

    ref = args.ref or run("git", "branch", "--show-current", capture=True)
    if not ref:
        print("error: detached HEAD; pass --ref with a pushed branch or tag", file=sys.stderr)
        return 2

    run("gh", "auth", "status")
    before = workflow_run_ids(ref)
    run(
        "gh",
        "workflow",
        "run",
        WORKFLOW,
        "--ref",
        ref,
        "-f",
        f"app_name={args.app_name}",
        "-f",
        f"icon_path={icon.as_posix()}",
    )

    run_id = ""
    for _ in range(30):
        current = workflow_run_ids(ref)
        created = current - before
        if created:
            run_id = max(created, key=int)
            break
        time.sleep(2)
    if not run_id:
        print("error: timed out while locating the triggered workflow run", file=sys.stderr)
        return 1

    run("gh", "run", "watch", run_id, "--exit-status")
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    run("gh", "run", "download", run_id, "--name", ARTIFACT, "--dir", str(output_dir))
    print(output_dir)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"error: command failed with exit code {exc.returncode}", file=sys.stderr)
        raise SystemExit(exc.returncode) from None
