from pathlib import Path
from typing import Any

from loguru import logger

from providers.openai_compatible_provider import build_provider
from utils.json_utils import read_json, write_json
from utils.srt_utils import read_srt
from utils.text_utils import parse_json_object


def analyze_position(context, config: dict[str, Any]) -> dict[str, Path]:
    step_config = config.get("steps", {}).get("screenshot_position", {})
    output = context.subtitle_position_path
    if output.exists() and not step_config.get("overwrite", False):
        return {"subtitle_position": output}
    video_info = read_json(context.video_info_path)
    sample_count = int(step_config.get("sample_count", 3))
    sample_frames: list[str] = []
    subtitle_bands: list[dict[str, int]] = []
    brightness_values: list[float] = []
    try:
        import cv2

        capture = cv2.VideoCapture(str(context.input_video))
        fps = capture.get(cv2.CAP_PROP_FPS) or video_info.get("fps") or 25
        duration = float(video_info.get("duration") or 0)
        sample_seconds = _sample_seconds(context, duration, sample_count, step_config)
        ratios = [round(second / duration, 6) if duration > 0 else 0 for second in sample_seconds]
        for idx, second in enumerate(sample_seconds, start=1):
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(second * fps))
            success, frame = capture.read()
            if not success:
                continue
            frame_path = context.screenshots_dir / f"frame_{idx:03d}.jpg"
            _write_cv_image(frame_path, frame)
            sample_frames.append(str(frame_path))
            band = _detect_original_subtitle_band(frame, step_config)
            if band:
                subtitle_bands.append(band)
            height = frame.shape[0]
            bottom = frame[int(height * 0.72) :, :]
            brightness_values.append(float(bottom.mean()))
        capture.release()
    except Exception as exc:
        logger.warning("OpenCV screenshot analysis failed, using default position: {}", exc)

    avg_brightness = sum(brightness_values) / len(brightness_values) if brightness_values else 128
    position = {
        "position": "bottom_center",
        "margin_v": int(step_config.get("margin_v", 80)),
        "font_size_en": int(step_config.get("font_size_en", _font_size(video_info.get("height", 1080)))),
        "font_color": "white",
        "outline_color": "black",
        "outline_width": 3 if avg_brightness > 190 else 2,
        "shadow": 1,
        "sample_frames": sample_frames,
        "sample_seconds": sample_seconds,
        "sample_ratios": ratios,
        "reason": "bottom area sampled with simple brightness rule" if sample_frames else "opencv unavailable, default bottom center",
    }
    if step_config.get("vision_enabled", True) and sample_frames:
        position = _apply_vision_position(position, [Path(path) for path in sample_frames], video_info, step_config, config)
    position = _apply_relative_subtitle_position(position, subtitle_bands, video_info, step_config)
    write_json(output, position)
    return {"subtitle_position": output}


def _font_size(height: int) -> int:
    if height >= 1440:
        return 46
    if height >= 1080:
        return 38
    if height >= 720:
        return 30
    return 24


def _sample_ratios(sample_count: int, strategy: str) -> list[float]:
    if strategy == "middle_nearby":
        if sample_count <= 1:
            return [0.5]
        base = [0.45, 0.5, 0.55]
        if sample_count <= 3:
            return base[:sample_count]
        extra_count = sample_count - 3
        extras = [(i + 1) / (extra_count + 1) for i in range(extra_count)]
        return sorted(base + [ratio for ratio in extras if ratio not in base])
    if strategy != "random":
        return [0.1, 0.5, 0.9] if sample_count == 3 else [(i + 1) / (sample_count + 1) for i in range(sample_count)]
    import random

    return sorted(random.uniform(0.08, 0.92) for _ in range(sample_count))


def _sample_seconds(context, duration: float, sample_count: int, step_config: dict[str, Any]) -> list[float]:
    strategy = step_config.get("sample_strategy", "middle_seconds")
    interval = float(step_config.get("sample_interval_seconds", 1))
    if duration <= 0:
        return [0]
    if strategy == "active_source_subtitle" and context.zh_clean_srt_path.exists():
        active_seconds = _active_source_subtitle_seconds(context, duration, sample_count, interval)
        if active_seconds:
            return active_seconds
    if strategy in {"middle_seconds", "middle_nearby"}:
        center = duration / 2
        start_offset = -((sample_count - 1) / 2) * interval
        return [
            max(0, min(duration, center + start_offset + idx * interval))
            for idx in range(sample_count)
        ]
    return [duration * ratio for ratio in _sample_ratios(sample_count, strategy)]


def _active_source_subtitle_seconds(context, duration: float, sample_count: int, interval: float) -> list[float]:
    items = [item for item in read_srt(context.zh_clean_srt_path) if item.end_ms > item.start_ms]
    if not items:
        return []
    center_ms = duration * 500
    ordered = sorted(items, key=lambda item: abs(((item.start_ms + item.end_ms) / 2) - center_ms))
    seconds: list[float] = []
    for item in ordered:
        midpoint = round(max(0, min(duration, ((item.start_ms + item.end_ms) / 2) / 1000)), 3)
        if all(abs(midpoint - existing) >= interval for existing in seconds):
            seconds.append(midpoint)
        if len(seconds) >= sample_count:
            return sorted(seconds)
    return sorted(seconds)


def _apply_vision_position(
    fallback_position: dict[str, Any],
    frame_paths: list[Path],
    video_info: dict[str, Any],
    step_config: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    prompt = _position_prompt(video_info, fallback_position, step_config)
    try:
        provider_name = step_config.get("provider", "vision")
        provider = build_provider(provider_name, config)
        response = provider.complete_with_images(prompt, frame_paths, step_config.get("model"))
        vision = parse_json_object(response)
        return _merge_vision_position(fallback_position, vision, video_info, provider_name)
    except Exception as exc:
        logger.warning("Vision position analysis failed with primary provider: {}", exc)
        fallback_provider = step_config.get("fallback_provider")
        if not fallback_provider:
            return {**fallback_position, "vision_used": False, "vision_error": str(exc)}
        try:
            provider = build_provider(fallback_provider, config)
            response = provider.complete_with_images(prompt, frame_paths, step_config.get("fallback_model"))
            vision = parse_json_object(response)
            return _merge_vision_position(fallback_position, vision, video_info, fallback_provider)
        except Exception as fallback_exc:
            logger.warning("Vision position fallback failed: {}", fallback_exc)
            return {**fallback_position, "vision_used": False, "vision_error": str(exc), "vision_fallback_error": str(fallback_exc)}


def _merge_vision_position(
    fallback_position: dict[str, Any],
    vision: dict[str, Any],
    video_info: dict[str, Any],
    provider_name: str,
) -> dict[str, Any]:
    height = int(video_info.get("height") or 1080)
    min_margin = max(40, int(height * 0.06))
    max_margin = max(min_margin, int(height * 0.38))
    min_font = max(18, int(height * 0.018))
    max_font = max(min_font, int(height * 0.035))
    margin_v = _clamp_int(vision.get("margin_v", fallback_position["margin_v"]), min_margin, max_margin)
    font_size = _clamp_int(vision.get("font_size_en", fallback_position["font_size_en"]), min_font, max_font)
    outline = _clamp_int(vision.get("outline_width", fallback_position["outline_width"]), 1, 5)
    return {
        **fallback_position,
        "position": vision.get("position", fallback_position["position"]),
        "margin_v": margin_v,
        "font_size_en": font_size,
        "outline_width": outline,
        "shadow": _clamp_int(vision.get("shadow", fallback_position["shadow"]), 0, 3),
        "vision_used": True,
        "vision_provider": provider_name,
        "vision_overlap_risk": bool(vision.get("overlap_risk", False)),
        "reason": vision.get("reason", fallback_position["reason"]),
    }


def _apply_relative_subtitle_position(
    position: dict[str, Any],
    subtitle_bands: list[dict[str, int]],
    video_info: dict[str, Any],
    step_config: dict[str, Any],
) -> dict[str, Any]:
    if step_config.get("placement_mode", "below_original_subtitle") != "below_original_subtitle":
        return position
    if not subtitle_bands:
        return {**position, "relative_position_used": False, "relative_position_reason": "no original subtitle band detected"}

    height = int(video_info.get("height") or 1080)
    band = _median_band(subtitle_bands)
    font_size = int(position.get("font_size_en", _font_size(height)))
    configured_gap = max(
        int(step_config.get("subtitle_gap_px", 22)),
        int(height * float(step_config.get("subtitle_gap_ratio", 0.016))),
    )
    max_gap = max(14, int(height * float(step_config.get("max_subtitle_gap_ratio", 0.024))))
    gap = min(configured_gap, max_gap)
    target_bottom = min(height - 12, band["y2"] + gap + int(font_size * 1.9))
    min_margin = max(24, int(height * 0.025))
    max_margin = max(min_margin, int(height * float(step_config.get("max_relative_margin_ratio", 0.48))))
    margin_v = max(min_margin, min(max_margin, height - target_bottom))
    return {
        **position,
        "position": "below_original_subtitle",
        "margin_v": margin_v,
        "detected_original_subtitle_bbox": band,
        "subtitle_gap_px_used": gap,
        "relative_position_used": True,
        "relative_position_reason": "place English subtitle directly below detected original Chinese subtitle",
    }


def _detect_original_subtitle_band(frame, step_config: dict[str, Any]) -> dict[str, int] | None:
    import cv2
    import numpy as np

    height, width = frame.shape[:2]
    try:
        from core.final_visual_qc import _bands_from_mask, _text_like_mask

        text_bands = _bands_from_mask(
            _text_like_mask(frame),
            min_y_ratio=float(step_config.get("original_subtitle_detection_min_y_ratio", 0.5)),
            max_y_ratio=min(float(step_config.get("original_subtitle_detection_max_y_ratio", 0.86)), 0.9),
        )
        scored_text_bands = [
            (_score_original_candidate(band, width, height, step_config), band)
            for band in text_bands
            if (band.get("width") or band.get("x2", 0) - band.get("x1", 0))
            >= width * float(step_config.get("original_subtitle_min_width_ratio", 0.18))
        ]
        if scored_text_bands:
            band = max(scored_text_bands, key=lambda item: item[0])[1]
            return {
                "x1": int(band.get("x1", 0)),
                "y1": int(band["y1"]),
                "x2": int(band.get("x2", 0)),
                "y2": int(band["y2"]),
                "width": int(band.get("width") or band.get("x2", 0) - band.get("x1", 0)),
                "height": int(band["height"]),
                "component_count": int(band.get("component_count", 0)),
            }
    except Exception:
        pass

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = ((gray > 150) & (hsv[:, :, 1] < 150)).astype("uint8") * 255
    min_y_ratio = float(step_config.get("original_subtitle_detection_min_y_ratio", 0.5))
    max_y_ratio = min(float(step_config.get("original_subtitle_detection_max_y_ratio", 0.86)), 0.86)
    mask[: int(height * min_y_ratio), :] = 0
    mask[int(height * max_y_ratio) :, :] = 0
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 21), np.uint8), iterations=1)
    mask = cv2.dilate(mask, np.ones((3, 11), np.uint8), iterations=1)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates: list[tuple[float, dict[str, int]]] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        center_x = x + w / 2
        center_y = y + h / 2
        if w < width * float(step_config.get("original_subtitle_min_width_ratio", 0.18)):
            continue
        if h < max(16, height * 0.018) or h > height * 0.13:
            continue
        if area < width * height * 0.0025:
            continue
        center_distance = abs(center_x - width / 2)
        if center_distance > width * 0.36:
            continue
        candidate = {"x1": x, "y1": y, "x2": x + w, "y2": y + h, "width": w, "height": h}
        candidates.append((_score_original_candidate(candidate, width, height, step_config), candidate))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _score_original_candidate(band: dict[str, int], width: int, height: int, step_config: dict[str, Any]) -> float:
    band_width = band.get("width") or band.get("x2", 0) - band.get("x1", 0)
    center_x = (band.get("x1", 0) + band.get("x2", 0)) / 2
    center_y = (band.get("y1", 0) + band.get("y2", 0)) / 2
    center_distance = abs(center_x - width / 2)
    preferred_y = height * float(step_config.get("original_subtitle_preferred_y_ratio", 0.64))
    return (
        band_width * 2.2
        + band.get("component_count", 0) * 18
        - center_distance * 1.1
        - abs(center_y - preferred_y) * 0.55
        - max(0, band.get("y2", 0) - height * 0.8) * 1.4
    )


def _median_band(bands: list[dict[str, int]]) -> dict[str, int]:
    def median(values: list[int]) -> int:
        values = sorted(values)
        return values[len(values) // 2]

    x1 = median([band["x1"] for band in bands])
    y1 = median([band["y1"] for band in bands])
    x2 = median([band["x2"] for band in bands])
    y2 = median([band["y2"] for band in bands])
    return {
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
        "width": max(0, x2 - x1),
        "height": max(0, y2 - y1),
        "sample_count": len(bands),
    }


def _clamp_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(maximum, number))


def _position_prompt(video_info: dict[str, Any], fallback_position: dict[str, Any], step_config: dict[str, Any]) -> str:
    return (
        "你是视频字幕排版专家。请观察这 3 张原视频随机截图，判断原视频底部是否已有中文字幕、人物主体或重要画面，"
        "然后给出英文字幕烧录的位置和字号，目标是不要覆盖原中文字幕，不要遮挡人物主体，观众能同时看清原画面和英文字幕。\n"
        f"视频尺寸：{video_info.get('width')}x{video_info.get('height')}。\n"
        f"当前默认建议：margin_v={fallback_position.get('margin_v')}，font_size_en={fallback_position.get('font_size_en')}。\n"
        "只输出 JSON，不要 Markdown。JSON 格式：\n"
        "{\n"
        '  "position": "bottom_center|bottom_center_up|middle_lower",\n'
        '  "margin_v": 180,\n'
        '  "font_size_en": 34,\n'
        '  "outline_width": 2,\n'
        '  "shadow": 1,\n'
        '  "overlap_risk": true,\n'
        '  "reason": "简短说明"\n'
        "}\n"
        "如果截图底部已有中文字幕，请优先上移英文字幕，增大 margin_v；如果英文过大容易遮挡，请适当降低 font_size_en。"
    )


def _write_cv_image(path: Path, frame) -> None:
    import cv2

    path.parent.mkdir(parents=True, exist_ok=True)
    success, encoded = cv2.imencode(path.suffix or ".jpg", frame)
    if not success:
        raise ValueError(f"Failed to encode image: {path}")
    encoded.tofile(str(path))
