from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.video_renderer import _replace_with_retry
from utils.ffmpeg_utils import ffmpeg_executable, quote_filter_path, run_command
from utils.json_utils import read_json, write_json


def prepend_cover_intro(context, config: dict[str, Any]) -> dict[str, Path]:
    step_config = config.get("steps", {}).get("cover_intro", {})
    report_path = context.reports_dir / "cover_intro_report.json"
    if report_path.exists() and not step_config.get("overwrite", False):
        return {"final_video": context.final_video_path, "cover_intro_report": report_path}
    if not step_config.get("enabled", True):
        write_json(report_path, {"passed": True, "enabled": False, "output": str(context.final_video_path)})
        return {"final_video": context.final_video_path, "cover_intro_report": report_path}

    cover_path = context.cover_dir / str(config.get("steps", {}).get("cover_title", {}).get("filename", "cover.jpg"))
    if not cover_path.exists():
        raise FileNotFoundError(f"cover_intro requires cover image: {cover_path}")
    if not context.final_video_path.exists():
        raise FileNotFoundError(f"cover_intro requires rendered video: {context.final_video_path}")

    video_info = read_json(context.video_info_path) if context.video_info_path.exists() else {}
    duration = float(step_config.get("duration_seconds", 1.0))
    base_video = context.final_video_path.with_name(f"{context.final_video_path.stem}.no_cover_intro.mp4")
    previous_report = _read_report(report_path)
    current_stat = context.final_video_path.stat()
    current_is_previous_output = (
        previous_report.get("output_size") == current_stat.st_size
        and previous_report.get("output_mtime_ns") == current_stat.st_mtime_ns
    )
    if base_video.exists() and current_is_previous_output:
        input_video = base_video
    elif previous_report and _video_starts_with_cover(context.final_video_path, cover_path):
        _write_success_report(report_path, cover_path, base_video, context.final_video_path, duration)
        return {"final_video": context.final_video_path, "cover_intro_report": report_path}
    else:
        base_video.unlink(missing_ok=True)
        context.final_video_path.replace(base_video)
        input_video = base_video

    temp_output = context.final_video_path.with_name(f"{context.final_video_path.stem}.with_cover_intro.{os.getpid()}.mp4")
    temp_output.unlink(missing_ok=True)
    try:
        log_path = context.logs_dir / "ffmpeg_cover_intro.log"
        log_path.unlink(missing_ok=True)
        _prepend_cover(
            cover_path=cover_path,
            input_video=input_video,
            output_video=temp_output,
            config=config,
            step_config=step_config,
            video_info=video_info,
            log_path=log_path,
        )
        _replace_with_retry(temp_output, context.final_video_path)
    except Exception:
        if not context.final_video_path.exists() and base_video.exists():
            base_video.replace(context.final_video_path)
        temp_output.unlink(missing_ok=True)
        raise

    _write_success_report(report_path, cover_path, base_video, context.final_video_path, duration)
    return {"final_video": context.final_video_path, "cover_intro_report": report_path}


def _write_success_report(report_path: Path, cover_path: Path, base_video: Path, output_video: Path, duration: float) -> None:
    output_stat = output_video.stat()
    report = {
        "passed": True,
        "enabled": True,
        "cover": str(cover_path),
        "base_video": str(base_video),
        "duration_seconds": duration,
        "output": str(output_video),
        "output_size": output_stat.st_size,
        "output_mtime_ns": output_stat.st_mtime_ns,
    }
    write_json(report_path, report)


def _read_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return read_json(path)
    except Exception:
        return {}


def _video_starts_with_cover(video_path: Path, cover_path: Path) -> bool:
    try:
        import cv2
        import numpy as np

        capture = cv2.VideoCapture(str(video_path))
        try:
            if not capture.isOpened():
                return False
            fps = capture.get(cv2.CAP_PROP_FPS) or 25
            capture.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(fps * 0.2)))
            success, frame = capture.read()
        finally:
            capture.release()
        if not success:
            return False
        cover_data = np.fromfile(str(cover_path), dtype=np.uint8)
        cover = cv2.imdecode(cover_data, cv2.IMREAD_COLOR)
        if cover is None:
            return False
        cover = cv2.resize(cover, (frame.shape[1], frame.shape[0]))
        diff = np.mean(np.abs(frame.astype("int16") - cover.astype("int16")))
        return bool(diff < 8.0)
    except Exception:
        return False


def _prepend_cover(
    cover_path: Path,
    input_video: Path,
    output_video: Path,
    config: dict[str, Any],
    step_config: dict[str, Any],
    video_info: dict[str, Any],
    log_path: Path,
) -> None:
    width = int(video_info.get("width") or step_config.get("width", 720))
    height = int(video_info.get("height") or step_config.get("height", 1280))
    fps = float(video_info.get("fps") or step_config.get("fps", 30))
    duration = float(step_config.get("duration_seconds", 1.0))
    crf = str(step_config.get("crf", config.get("steps", {}).get("render_video", {}).get("crf", 20)))
    preset = str(step_config.get("preset", config.get("steps", {}).get("render_video", {}).get("preset", "medium")))
    threads = str(max(1, int(step_config.get("threads", config.get("steps", {}).get("render_video", {}).get("threads", 8)))))
    sample_rate = int(step_config.get("audio_sample_rate", 44100))
    channel_layout = str(step_config.get("audio_channel_layout", "stereo"))

    filter_complex = (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},fps={fps},format=yuv420p,setsar=1[v0];"
        f"anullsrc=channel_layout={channel_layout}:sample_rate={sample_rate},atrim=duration={duration}[a0];"
        f"[1:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},fps={fps},format=yuv420p,setsar=1[v1];"
        f"[1:a]aformat=sample_rates={sample_rate}:channel_layouts={channel_layout}[a1];"
        "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]"
    )
    command = [
        ffmpeg_executable(config),
        "-y",
        "-nostdin",
        "-loop",
        "1",
        "-t",
        str(duration),
        "-i",
        str(cover_path),
        "-i",
        str(input_video),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-c:v",
        "libx264",
        "-crf",
        crf,
        "-preset",
        preset,
        "-threads",
        threads,
        "-c:a",
        "aac",
        "-b:a",
        str(step_config.get("audio_bitrate", "128k")),
        "-movflags",
        "+faststart",
        str(output_video),
    ]
    run_command(command, log_path, timeout=float(step_config.get("timeout", 3600)))
