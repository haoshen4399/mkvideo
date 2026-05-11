from pathlib import Path
from typing import Any

from utils.ffmpeg_utils import run_command


def extract_audio(context, config: dict[str, Any]) -> dict[str, Path]:
    step_config = config.get("steps", {}).get("extract_audio", {})
    output_path = context.original_audio_path
    if output_path.exists() and not step_config.get("overwrite", False):
        return {"audio": output_path}
    sample_rate = str(step_config.get("sample_rate", 16000))
    channels = str(step_config.get("channels", 1))
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(context.input_video),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        sample_rate,
        "-ac",
        channels,
        str(output_path),
    ]
    run_command(command, context.logs_dir / "ffmpeg.log")
    return {"audio": output_path}
