import json
import subprocess
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


def run_command(command: list[str], log_path: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True)
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write("\n$ " + " ".join(command) + "\n")
            handle.write(result.stdout)
            handle.write(result.stderr)
    if result.returncode != 0:
        raise FFmpegError(result.stderr.strip() or f"Command failed: {' '.join(command)}")
    return result


def ffprobe_json(input_path: Path) -> dict:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(input_path),
    ]
    result = run_command(command)
    return json.loads(result.stdout)


def quote_filter_path(path: Path) -> str:
    text = str(path.resolve()).replace("\\", "/")
    text = text.replace(":", "\\:").replace("'", "\\'")
    return text
