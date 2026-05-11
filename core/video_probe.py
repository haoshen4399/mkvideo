from pathlib import Path
from typing import Any

from utils.ffmpeg_utils import ffprobe_json
from utils.json_utils import write_json

SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".mkv"}


def probe_video(context, config: dict[str, Any]) -> dict[str, Path]:
    input_path = context.input_video
    if not input_path.exists():
        raise FileNotFoundError(f"Input video not found: {input_path}")
    if input_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported video format: {input_path.suffix}")

    probe = ffprobe_json(input_path)
    streams = probe.get("streams", [])
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if not video_stream:
        raise ValueError("No video stream found.")
    if not audio_stream:
        raise ValueError("No audio stream found.")

    duration = float(probe.get("format", {}).get("duration") or video_stream.get("duration") or 0)
    max_minutes = float(config.get("app", {}).get("max_video_minutes", 10))
    if duration > max_minutes * 60:
        raise ValueError(f"Video duration {duration:.1f}s exceeds limit {max_minutes} minutes.")
    fps = _parse_fps(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate") or "0/1")
    info = {
        "filename": input_path.name,
        "duration": duration,
        "width": int(video_stream.get("width", 0)),
        "height": int(video_stream.get("height", 0)),
        "fps": fps,
        "has_audio": True,
        "video_codec": video_stream.get("codec_name"),
        "audio_codec": audio_stream.get("codec_name"),
        "file_size": input_path.stat().st_size,
        "valid": True,
    }
    write_json(context.video_info_path, info)
    return {"video_info": context.video_info_path}


def _parse_fps(value: str) -> float:
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        denominator_float = float(denominator)
        return 0.0 if denominator_float == 0 else round(float(numerator) / denominator_float, 3)
    return float(value or 0)
