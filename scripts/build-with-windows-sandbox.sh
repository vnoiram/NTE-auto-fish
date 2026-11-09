#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

if ! command -v wslpath >/dev/null 2>&1; then
  echo "error: this launcher requires WSL on a Windows host" >&2
  exit 2
fi

powershell_bin=$(command -v powershell.exe || true)
if [[ -z ${powershell_bin} ]]; then
  powershell_bin="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
fi
if [[ ! -x ${powershell_bin} ]]; then
  echo "error: Windows PowerShell was not found" >&2
  exit 2
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
windows_script=$(wslpath -w "${script_dir}/build_with_windows_sandbox.ps1")

exec "${powershell_bin}" \
  -NoProfile \
  -ExecutionPolicy Bypass \
  -File "${windows_script}" \
  "$@"
