import json
import os
import shutil
import subprocess
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


def ffmpeg_executable(config: dict | None = None) -> str:
    return _resolve_binary("ffmpeg", config, "ffmpeg_path", "FFMPEG_BINARY")


def ffprobe_executable(config: dict | None = None) -> str:
    return _resolve_binary("ffprobe", config, "ffprobe_path", "FFPROBE_BINARY")


def ensure_ffmpeg_on_path(config: dict | None = None) -> None:
    ffmpeg_path = Path(ffmpeg_executable(config)).resolve()
    ffprobe_path = Path(ffprobe_executable(config)).resolve()
    bin_dirs = [ffmpeg_path.parent, ffprobe_path.parent]
    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    normalized = {str(Path(part).resolve()).lower() for part in path_parts if part}
    prepend = [str(path) for path in bin_dirs if str(path).lower() not in normalized]
    if prepend:
        os.environ["PATH"] = os.pathsep.join(prepend + path_parts)


def _resolve_binary(binary_name: str, config: dict | None, config_key: str, env_key: str) -> str:
    app_config = (config or {}).get("app", {}) if isinstance(config, dict) else {}
    candidates = [
        app_config.get(config_key),
        os.environ.get(env_key),
        shutil.which(binary_name),
        Path("D:/ffmpeg/bin") / f"{binary_name}.exe",
        Path("C:/ffmpeg/bin") / f"{binary_name}.exe",
        Path.cwd() / "tools" / "ffmpeg" / "bin" / f"{binary_name}.exe",
        Path.cwd() / "ffmpeg" / "bin" / f"{binary_name}.exe",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        candidate_path = Path(candidate).expanduser()
        if candidate_path.is_file():
            return str(candidate_path)
        if isinstance(candidate, str) and shutil.which(candidate):
            return candidate
    raise FileNotFoundError(
        f"{binary_name} executable not found. Configure app.{config_key} in config.yaml "
        f"or add {binary_name} to PATH."
    )


def run_command(command: list[str], log_path: Path | None = None) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Executable not found while running command: {command[0]}") from exc
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write("\n$ " + " ".join(command) + "\n")
            handle.write(result.stdout)
            handle.write(result.stderr)
    if result.returncode != 0:
        raise FFmpegError(result.stderr.strip() or f"Command failed: {' '.join(command)}")
    return result


def ffprobe_json(input_path: Path, config: dict | None = None) -> dict:
    command = [
        ffprobe_executable(config),
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
