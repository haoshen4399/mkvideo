from pathlib import Path
from typing import Any
import os
import time

from utils.ffmpeg_utils import FFmpegError, ffmpeg_executable, quote_filter_path, run_command
from utils.json_utils import write_json


def render_video(context, config: dict[str, Any]) -> dict[str, Path]:
    step_config = config.get("steps", {}).get("render_video", {})
    output = context.final_video_path
    if output.exists() and not step_config.get("overwrite", False):
        return {"final_video": output}
    ass_path = context.bilingual_ass_path if step_config.get("ass_mode") == "bilingual" else context.english_ass_path
    render_ass_to_video(context.input_video, ass_path, output, config, step_config, context.logs_dir / "ffmpeg.log")
    write_json(context.reports_dir / "render_report.json", {"passed": True, "output": str(output)})
    return {"final_video": output, "render_report": context.reports_dir / "render_report.json"}


def render_ass_to_video(
    input_video: Path,
    ass_path: Path,
    output: Path,
    config: dict[str, Any],
    step_config: dict[str, Any],
    log_path: Path | None = None,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output.with_name(f"{output.stem}.tmp.{os.getpid()}{output.suffix}")
    temp_output.unlink(missing_ok=True)
    try:
        _run_render_command(input_video, ass_path, temp_output, config, step_config, log_path)
    except FFmpegError:
        if str(step_config.get("audio_codec", "copy")).lower() == "copy":
            fallback_config = {**step_config, "audio_codec": "aac"}
            temp_output.unlink(missing_ok=True)
            _run_render_command(input_video, ass_path, temp_output, config, fallback_config, log_path)
        else:
            raise
    _replace_with_retry(temp_output, output)


def _run_render_command(
    input_video: Path,
    ass_path: Path,
    output: Path,
    config: dict[str, Any],
    step_config: dict[str, Any],
    log_path: Path | None,
) -> None:
    crf = str(step_config.get("crf", 20))
    preset = str(step_config.get("preset", "medium"))
    threads = int(step_config.get("threads", 8))
    command = [
        ffmpeg_executable(config),
        "-y",
        "-nostdin",
        "-i",
        str(input_video),
        "-vf",
        f"ass='{quote_filter_path(ass_path)}'",
        "-c:v",
        "libx264",
        "-crf",
        crf,
        "-preset",
        preset,
        "-threads",
        str(max(1, threads)),
        "-c:a",
        step_config.get("audio_codec", "copy"),
        str(output),
    ]
    run_command(command, log_path)


def _replace_with_retry(source: Path, target: Path, attempts: int = 5) -> None:
    last_error: OSError | None = None
    for attempt in range(attempts):
        try:
            source.replace(target)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"Cannot replace rendered video, file may be open: {target}") from last_error
