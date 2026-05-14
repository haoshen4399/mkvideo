import json
import os
import shutil
import subprocess
import time
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


def run_command(
    command: list[str],
    log_path: Path | None = None,
    timeout: int | float | None = None,
) -> subprocess.CompletedProcess[str]:
    timeout = timeout or 3600
    started = time.monotonic()
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        stdout, stderr = process.communicate(timeout=timeout)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Executable not found while running command: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        if process is not None:
            _kill_process(process)
        raise FFmpegError(f"Command timed out after {timeout}s: {' '.join(command)}") from exc
    except BaseException:
        if process is not None:
            _kill_process(process)
        raise
    result = subprocess.CompletedProcess(command, process.returncode if process else -1, stdout, stderr)
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write("\n$ " + " ".join(command) + "\n")
            handle.write(f"# elapsed_seconds={time.monotonic() - started:.3f}\n")
            handle.write(f"# return_code={result.returncode}\n")
            handle.write(result.stdout)
            handle.write(result.stderr)
    if result.returncode != 0:
        summary = _summarize_command_error(result.stderr)
        message = f"Command failed with exit code {result.returncode}"
        if summary:
            message += f":\n{summary}"
        else:
            message += f": {' '.join(command)}"
        raise FFmpegError(message)
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


def _summarize_command_error(stderr: str, max_lines: int = 20) -> str:
    lines = [line for line in stderr.strip().splitlines() if line.strip()]
    if not lines:
        return ""
    non_progress_lines = [line for line in lines if not _looks_like_ffmpeg_progress(line)]
    interesting = [
        line
        for line in non_progress_lines
        if any(token in line.lower() for token in ["error", "failed", "invalid", "unable", "cannot", "denied"])
    ]
    selected = interesting[-max_lines:] if interesting else non_progress_lines[-max_lines:]
    return "\n".join(selected)


def _looks_like_ffmpeg_progress(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("frame=") or stripped.startswith("size=")


def _kill_process(process: subprocess.Popen[str]) -> None:
    try:
        process.kill()
    except OSError:
        pass
    try:
        process.communicate(timeout=5)
    except Exception:
        pass
