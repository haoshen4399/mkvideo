from pathlib import Path
from typing import Any

from utils.json_utils import read_json
from utils.srt_utils import read_srt


def build_ass(context, config: dict[str, Any]) -> dict[str, Path]:
    step_config = config.get("steps", {}).get("build_ass", {})
    output = context.bilingual_ass_path if step_config.get("mode") == "bilingual" else context.english_ass_path
    if output.exists() and not step_config.get("overwrite", False):
        return {"ass": output}
    position = read_json(context.subtitle_position_path)
    video_info = read_json(context.video_info_path)
    en_items = read_srt(context.en_checked_srt_path)
    zh_items = read_srt(context.zh_ai_checked_srt_path) if context.zh_ai_checked_srt_path.exists() else []
    mode = step_config.get("mode", "en_only")
    style = _ass_header(position, step_config, video_info)
    events = []
    for idx, item in enumerate(en_items):
        text = _escape_ass(item.text)
        if mode == "bilingual" and idx < len(zh_items):
            text = f"{_escape_ass(zh_items[idx].text)}\\N{text}"
        events.append(
            f"Dialogue: 0,{_ass_time(item.start_ms)},{_ass_time(item.end_ms)},Default,,0,0,0,,{text}"
        )
    output.write_text(style + "\n".join(events) + "\n", encoding="utf-8-sig")
    return {"ass": output}


def _ass_header(position: dict[str, Any], step_config: dict[str, Any], video_info: dict[str, Any]) -> str:
    font_name = step_config.get("font_name", "Arial")
    font_size = int(step_config.get("font_size", position.get("font_size_en", 38)))
    margin_v = int(position.get("margin_v", 80))
    outline = int(position.get("outline_width", 2))
    play_res_x = int(video_info.get("width") or 1080)
    play_res_y = int(video_info.get("height") or 1920)
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {play_res_x}\n"
        f"PlayResY: {play_res_y}\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n"
        "YCbCr Matrix: TV.709\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,"
        f"0,0,0,0,100,100,0,0,1,{outline},1,2,40,40,{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def _escape_ass(text: str) -> str:
    return text.replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def _ass_time(ms: int) -> str:
    centiseconds = max(0, round(ms / 10))
    hours = centiseconds // 360000
    centiseconds %= 360000
    minutes = centiseconds // 6000
    centiseconds %= 6000
    seconds = centiseconds // 100
    cs = centiseconds % 100
    return f"{hours}:{minutes:02d}:{seconds:02d}.{cs:02d}"
