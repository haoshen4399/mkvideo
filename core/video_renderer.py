from pathlib import Path
from typing import Any

from utils.ffmpeg_utils import ffmpeg_executable, quote_filter_path, run_command
from utils.json_utils import write_json


def render_video(context, config: dict[str, Any]) -> dict[str, Path]:
    step_config = config.get("steps", {}).get("render_video", {})
    output = context.final_video_path
    if output.exists() and not step_config.get("overwrite", False):
        return {"final_video": output}
    ass_path = context.bilingual_ass_path if step_config.get("ass_mode") == "bilingual" else context.english_ass_path
    crf = str(step_config.get("crf", 20))
    preset = str(step_config.get("preset", "medium"))
    command = [
        ffmpeg_executable(config),
        "-y",
        "-i",
        str(context.input_video),
        "-vf",
        f"ass='{quote_filter_path(ass_path)}'",
        "-c:v",
        "libx264",
        "-crf",
        crf,
        "-preset",
        preset,
        "-c:a",
        step_config.get("audio_codec", "copy"),
        str(output),
    ]
    run_command(command, context.logs_dir / "ffmpeg.log")
    write_json(context.reports_dir / "render_report.json", {"passed": True, "output": str(output)})
    return {"final_video": output, "render_report": context.reports_dir / "render_report.json"}
