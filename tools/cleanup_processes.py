from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path


TARGET_NAMES = {"python.exe", "ffmpeg.exe", "ffprobe.exe"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean stale mkvideo Python/FFmpeg processes.")
    parser.add_argument("--dry-run", action="store_true", help="List matching processes without killing them.")
    parser.add_argument("--force", action="store_true", help="Also kill matching parent python.exe processes.")
    parser.add_argument("--min-age-seconds", type=float, default=60.0, help="Only kill processes older than this.")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    current_pid = os.getpid()
    processes = _list_processes()
    matches = [
        process
        for process in processes
        if _is_mkvideo_process(process, root)
        and int(process.get("pid") or 0) != current_pid
        and _process_age_seconds(process) >= args.min_age_seconds
        and (args.force or not _looks_like_parent_python(process, root))
    ]

    if not matches:
        print("No stale mkvideo processes found.")
        return 0

    action = "Would kill" if args.dry_run else "Killing"
    for process in matches:
        print(
            f"{action}: pid={process['pid']} name={process['name']} "
            f"parent={process.get('parent_pid') or ''} command={process.get('command_line') or ''}"
        )
        if not args.dry_run:
            _kill_pid(int(process["pid"]))
    return 0


def _list_processes() -> list[dict[str, str]]:
    try:
        return _list_processes_with_powershell_cim()
    except Exception:
        return _list_processes_with_get_process()


def _list_processes_with_powershell_cim() -> list[dict[str, str]]:
    script = r"""
$ErrorActionPreference = 'Stop'
Get-CimInstance Win32_Process -Filter "name = 'python.exe' or name = 'ffmpeg.exe' or name = 'ffprobe.exe'" |
  Select-Object @{n='pid';e={$_.ProcessId}}, @{n='parent_pid';e={$_.ParentProcessId}}, @{n='name';e={$_.Name}}, @{n='path';e={$_.ExecutablePath}}, @{n='command_line';e={$_.CommandLine}}, @{n='age_seconds';e={(New-TimeSpan -Start $_.CreationDate -End (Get-Date)).TotalSeconds}} |
  ConvertTo-Json -Compress
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    raw = _json_output(result)
    if result.returncode != 0 and not raw:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    if not raw:
        return []
    data = json.loads(raw)
    if isinstance(data, dict):
        data = [data]
    return [
        {
            "pid": str(row.get("pid") or "").strip(),
            "parent_pid": str(row.get("parent_pid") or "").strip(),
            "name": str(row.get("name") or "").strip(),
            "path": str(row.get("path") or "").strip(),
            "command_line": str(row.get("command_line") or "").strip(),
            "age_seconds": str(row.get("age_seconds") or "").strip(),
        }
        for row in data
    ]


def _list_processes_with_get_process() -> list[dict[str, str]]:
    script = r"""
$names = @('python','ffmpeg','ffprobe')
Get-Process -Name $names -ErrorAction SilentlyContinue |
  Select-Object @{n='pid';e={$_.Id}}, @{n='parent_pid';e={''}}, @{n='name';e={$_.ProcessName + '.exe'}}, @{n='path';e={$_.Path}}, @{n='command_line';e={''}}, @{n='age_seconds';e={(New-TimeSpan -Start $_.StartTime -End (Get-Date)).TotalSeconds}} |
  ConvertTo-Json -Compress
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    raw = _json_output(result)
    if result.returncode != 0 and not raw:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    if not raw:
        return []
    data = json.loads(raw)
    if isinstance(data, dict):
        data = [data]
    return [
        {
            "pid": str(row.get("pid") or "").strip(),
            "parent_pid": str(row.get("parent_pid") or "").strip(),
            "name": str(row.get("name") or "").strip(),
            "path": str(row.get("path") or "").strip(),
            "command_line": str(row.get("command_line") or "").strip(),
            "age_seconds": str(row.get("age_seconds") or "").strip(),
        }
        for row in data
    ]


def _list_processes_with_wmic() -> list[dict[str, str]]:
    # Kept as a last-resort implementation for older Windows setups.
    result = subprocess.run(
        [
            "wmic",
            "process",
            "where",
            "name='python.exe' or name='ffmpeg.exe' or name='ffprobe.exe'",
            "get",
            "ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine",
            "/format:csv",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Failed to list processes with wmic.")

    rows = []
    for row in csv.DictReader(line for line in result.stdout.splitlines() if line.strip()):
        rows.append(
            {
                "pid": row.get("ProcessId", "").strip(),
                "parent_pid": row.get("ParentProcessId", "").strip(),
                "name": row.get("Name", "").strip(),
                "path": row.get("ExecutablePath", "").strip(),
                "command_line": row.get("CommandLine", "").strip(),
                "age_seconds": "",
            }
        )
    return rows


def _json_output(result: subprocess.CompletedProcess[str]) -> str:
    for text in (result.stdout, result.stderr):
        text = text.strip()
        if text.startswith("{") or text.startswith("["):
            return text
    return ""


def _is_mkvideo_process(process: dict[str, str], root: Path) -> bool:
    name = process.get("name", "").lower()
    if name not in TARGET_NAMES:
        return False

    root_text = str(root).lower()
    command = (process.get("command_line") or "").lower()
    executable = (process.get("path") or "").lower()

    if root_text in command or root_text in executable:
        return True

    # The configured FFmpeg in this project usually lives at D:\ffmpeg.
    if name in {"ffmpeg.exe", "ffprobe.exe"} and ("d:\\ffmpeg" in executable or "d:/ffmpeg" in executable):
        return True
    if name == "python.exe" and not command and executable.endswith("\\.venv\\scripts\\python.exe"):
        return True
    return False


def _process_age_seconds(process: dict[str, str]) -> float:
    try:
        return float(process.get("age_seconds") or 10**9)
    except ValueError:
        return 10**9


def _looks_like_parent_python(process: dict[str, str], root: Path) -> bool:
    name = process.get("name", "").lower()
    if name != "python.exe":
        return False
    command = (process.get("command_line") or "").lower()
    root_text = str(root).lower()
    return "main.py" in command and root_text in command


def _kill_pid(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)


if __name__ == "__main__":
    raise SystemExit(main())
