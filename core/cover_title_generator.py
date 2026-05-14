from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import cv2
from loguru import logger
from PIL import Image, ImageDraw, ImageFont

from providers.openai_compatible_provider import build_provider
from utils.json_utils import write_json
from utils.srt_utils import read_srt, strip_code_fence


def generate_cover_title(context, config: dict[str, Any]) -> dict[str, Path]:
    step_config = config.get("steps", {}).get("cover_title", {})
    cover_path = context.cover_dir / str(step_config.get("filename", "cover.jpg"))
    report_path = context.reports_dir / "cover_title_report.json"
    if cover_path.exists() and not step_config.get("overwrite", False):
        return {"cover_image": cover_path, "cover_title_report": report_path}

    zh_source = context.zh_ai_checked_srt_path if context.zh_ai_checked_srt_path.exists() else context.zh_clean_srt_path
    en_source = context.en_checked_srt_path if context.en_checked_srt_path.exists() else context.en_raw_srt_path
    if not zh_source.exists():
        raise FileNotFoundError(f"cover_title requires Chinese subtitles: {zh_source}")

    zh_items = read_srt(zh_source)
    en_items = read_srt(en_source) if en_source.exists() else []
    zh_text = _subtitle_text(zh_items)
    en_text = _subtitle_text(en_items)

    fallback_used = False
    error = None
    if step_config.get("ai_summary_enabled", True):
        try:
            groups = _summarize_title_groups(zh_text, en_text, step_config, config)
        except Exception as exc:
            logger.warning("Cover title AI summary failed, using local fallback: {}", exc)
            fallback_used = True
            error = str(exc)
            groups = _local_title_groups(context.input_video.stem, zh_text)
    else:
        fallback_used = True
        groups = _local_title_groups(context.input_video.stem, zh_text)

    groups = _normalize_groups(groups)
    _render_cover(context.input_video, cover_path, groups, step_config)

    report = {
        "passed": True,
        "cover_image": str(cover_path),
        "zh_source": str(zh_source),
        "en_source": str(en_source) if en_source.exists() else None,
        "layout": "en_top",
        "groups": groups,
        "fallback_used": fallback_used,
        "error": error,
    }
    write_json(report_path, report)
    return {"cover_image": cover_path, "cover_title_report": report_path}


def _summarize_title_groups(
    zh_text: str,
    en_text: str,
    step_config: dict[str, Any],
    config: dict[str, Any],
) -> list[dict[str, str]]:
    provider = build_provider(step_config.get("provider", "default"), config)
    max_chars = int(step_config.get("summary_max_chars", 4500))
    prompt = _build_prompt(zh_text[:max_chars], en_text[:max_chars])
    response = provider.complete(prompt, step_config.get("model"))
    data = _parse_json_object(response)
    groups = data.get("groups")
    if not isinstance(groups, list):
        raise ValueError("Cover title response missing groups list")
    return groups


def _build_prompt(zh_text: str, en_text: str) -> str:
    return f"""你是短剧封面标题策划。请根据字幕总结封面标题，不要照抄某一句字幕。

要求：
1. 输出 2 组标题，每组包含英文 en 和中文 zh。
2. 英文在上，中文在下，所以每组英文要短、自然、有点击欲。
3. 中文每组 6-10 个汉字，英文每组不超过 34 个字符。
4. 聚焦剧情冲突、反转、关系，不要写解释性长句。
5. 只输出 JSON，不要 Markdown。

JSON 格式：
{{
  "groups": [
    {{"en": "短英文标题", "zh": "短中文标题"}},
    {{"en": "短英文标题", "zh": "短中文标题"}}
  ]
}}

中文字幕：
{zh_text}

英文字幕：
{en_text}
"""


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = strip_code_fence(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def _subtitle_text(items) -> str:
    lines = []
    for item in items:
        text = re.sub(r"\s+", " ", item.text).strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def _local_title_groups(video_stem: str, zh_text: str) -> list[dict[str, str]]:
    if all(keyword in zh_text for keyword in ["离婚", "妈"]) and ("定位" in zh_text or "GPS" in zh_text):
        return [
            {"en": "Wife Sets a Divorce Trap", "zh": "妻子设局逼离婚"},
            {"en": "Mother-in-law Was Behind It", "zh": "丈母娘竟是主谋"},
        ]

    title = re.sub(r"^[a-zA-Z0-9]+", "", video_stem)
    title = re.sub(r"#.*", "", title)
    title = re.sub(r"[，,。！？!?\s]+", "", title)
    if len(title) >= 12:
        return [
            {"en": "A Shocking Family Twist", "zh": title[:8]},
            {"en": "The Truth Comes Out", "zh": title[8:16]},
        ]
    return [
        {"en": "A Shocking Family Twist", "zh": title[:8] or "家庭冲突爆发"},
        {"en": "The Truth Comes Out", "zh": title[8:16] or "真相终于揭开"},
    ]


def _normalize_groups(groups: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized = []
    for group in groups[:2]:
        en = str(group.get("en", "")).strip()
        zh = str(group.get("zh", "")).strip()
        if not en or not zh:
            continue
        normalized.append({"en": _compact_en(en), "zh": _compact_zh(zh)})
    if len(normalized) < 2:
        normalized = [
            {"en": "A Shocking Family Twist", "zh": "家庭冲突爆发"},
            {"en": "The Truth Comes Out", "zh": "真相终于揭开"},
        ]
    return normalized


def _compact_zh(text: str) -> str:
    text = re.sub(r"[，,。！？!?\s]+", "", text)
    return text[:10]


def _compact_en(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:34].rstrip()


def _render_cover(video_path: Path, output_path: Path, groups: list[dict[str, str]], step_config: dict[str, Any]) -> None:
    width = int(step_config.get("width", 720))
    height = int(step_config.get("height", 1280))
    frame = _select_cover_frame(video_path, step_config)
    base = _fit_cover(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)), width, height).convert("RGBA")
    base = Image.alpha_composite(base, _bottom_gradient(width, height))

    title_layer = _draw_grouped_title(width, height, groups, step_config)
    cover = Image.alpha_composite(base, title_layer)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cover.convert("RGB").save(output_path, quality=int(step_config.get("jpeg_quality", 94)), subsampling=0)


def _select_cover_frame(video_path: Path, step_config: dict[str, Any]):
    sample_seconds = step_config.get("sample_seconds") or [12, 18, 24, 36, 48, 72, 96]
    cap = cv2.VideoCapture(str(video_path))
    best = None
    best_score = -1.0
    for sec in sample_seconds:
        cap.set(cv2.CAP_PROP_POS_MSEC, float(sec) * 1000)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        score = float(gray.std()) + min(float(gray.mean()), 180.0) * 0.12
        if score > best_score:
            best_score = score
            best = frame
    cap.release()
    if best is None:
        raise RuntimeError(f"Could not read cover frame: {video_path}")
    return best


def _fit_cover(image: Image.Image, width: int, height: int) -> Image.Image:
    scale = max(width / image.width, height / image.height)
    resized = image.resize((math.ceil(image.width * scale), math.ceil(image.height * scale)), Image.Resampling.LANCZOS)
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _bottom_gradient(width: int, height: int) -> Image.Image:
    gradient = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(gradient)
    start_y = int(height * 0.53)
    for y in range(start_y, height):
        t = (y - start_y) / max(1, height - start_y)
        draw.line([(0, y), (width, y)], fill=int(148 * (t**1.75)))
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    overlay.putalpha(gradient)
    return overlay


def _draw_grouped_title(
    width: int,
    height: int,
    groups: list[dict[str, str]],
    step_config: dict[str, Any],
) -> Image.Image:
    zh_font_path = _font_path(step_config.get("zh_font_path"), ["C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/msyhbd.ttc"])
    en_font_path = _font_path(step_config.get("en_font_path"), ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/Arial.ttf"])
    safe_w = int(width * float(step_config.get("safe_width_ratio", 0.84)))
    safe_h = int(height * float(step_config.get("safe_height_ratio", 0.255)))
    safe_x = (width - safe_w) // 2
    safe_y = int(height * float(step_config.get("safe_y_ratio", 0.635)))

    chosen = None
    max_zh_size = int(step_config.get("zh_font_size", 60))
    min_zh_size = int(step_config.get("min_zh_font_size", 40))
    en_ratio = float(step_config.get("en_font_ratio", 0.48))
    for zh_size in range(max_zh_size, min_zh_size - 1, -2):
        en_size = max(int(step_config.get("min_en_font_size", 28)), int(zh_size * en_ratio))
        zh_font = ImageFont.truetype(zh_font_path, zh_size)
        en_font = ImageFont.truetype(en_font_path, en_size)
        outer = max(7, int(zh_size * 0.145))
        black = max(3, int(zh_size * 0.063))
        en_stroke = max(2, int(en_size * 0.105))
        pair_gap = int(step_config.get("pair_gap_px", 2))
        group_gap = int(step_config.get("group_gap_px", 11))
        measure = ImageDraw.Draw(Image.new("RGBA", (width, height)))
        widths = []
        heights = []
        for group in groups:
            en_box = measure.textbbox((0, 0), group["en"], font=en_font, stroke_width=en_stroke)
            zh_box = measure.textbbox((0, 0), group["zh"], font=zh_font, stroke_width=outer + black)
            widths.extend([en_box[2] - en_box[0], zh_box[2] - zh_box[0]])
            heights.append((en_box[3] - en_box[1]) + pair_gap + (zh_box[3] - zh_box[1]))
        total_h = sum(heights) + group_gap * (len(groups) - 1)
        if max(widths) <= safe_w and total_h <= safe_h:
            chosen = (zh_font, en_font, outer, black, en_stroke, pair_gap, group_gap, total_h)
            break
    if chosen is None:
        raise RuntimeError("Could not fit cover title inside safe area.")

    zh_font, en_font, outer, black, en_stroke, pair_gap, group_gap, total_h = chosen
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    y = safe_y + (safe_h - total_h) // 2
    layout = str(step_config.get("layout", "en_top")).lower()
    for index, group in enumerate(groups):
        if layout == "zh_top":
            y = _draw_zh_line(draw, group["zh"], zh_font, safe_x, safe_w, y, outer, black)
            y += pair_gap
            y = _draw_en_line(draw, group["en"], en_font, safe_x, safe_w, y, en_stroke)
        else:
            y = _draw_en_line(draw, group["en"], en_font, safe_x, safe_w, y, en_stroke)
            y += pair_gap
            y = _draw_zh_line(draw, group["zh"], zh_font, safe_x, safe_w, y, outer, black)
        if index != len(groups) - 1:
            y += group_gap

    accent_y = safe_y + safe_h - 9
    draw.rounded_rectangle(
        (safe_x + 64, accent_y, safe_x + safe_w - 64, accent_y + 6),
        radius=3,
        fill=(180, 26, 28, 190),
    )
    return layer


def _draw_en_line(draw: ImageDraw.ImageDraw, text: str, font, safe_x: int, safe_w: int, y: int, stroke: int) -> int:
    box = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
    width = box[2] - box[0]
    height = box[3] - box[1]
    x = safe_x + (safe_w - width) // 2 - box[0]
    yy = y - box[1]
    draw.text((x + 2, yy + 2), text, font=font, fill=(85, 10, 12, 225), stroke_width=stroke, stroke_fill=(255, 255, 255, 225))
    draw.text((x, yy), text, font=font, fill=(206, 30, 33, 255), stroke_width=stroke, stroke_fill=(255, 255, 255, 255))
    return y + height


def _draw_zh_line(draw: ImageDraw.ImageDraw, text: str, font, safe_x: int, safe_w: int, y: int, outer: int, black: int) -> int:
    box = draw.textbbox((0, 0), text, font=font, stroke_width=outer + black)
    width = box[2] - box[0]
    height = box[3] - box[1]
    x = safe_x + (safe_w - width) // 2 - box[0]
    yy = y - box[1]
    for dx, dy, alpha in ((7, 8, 255), (4, 5, 238), (2, 3, 220)):
        draw.text(
            (x + dx, yy + dy),
            text,
            font=font,
            fill=(154, 20, 23, alpha),
            stroke_width=outer + black,
            stroke_fill=(255, 255, 255, alpha),
        )
    draw.text((x, yy), text, font=font, fill=(255, 244, 218, 255), stroke_width=outer + black, stroke_fill=(255, 255, 255, 255))
    draw.text((x, yy), text, font=font, fill=(255, 244, 218, 255), stroke_width=black, stroke_fill=(25, 22, 20, 255))
    return y + height


def _font_path(configured: str | None, candidates: list[str]) -> str:
    if configured and Path(configured).exists():
        return configured
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    raise FileNotFoundError(f"No usable font found: {candidates}")
