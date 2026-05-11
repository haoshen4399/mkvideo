from pathlib import Path
from typing import Any

from loguru import logger

from core.subtitle_visual import subtitle_visible_near_time
from providers.openai_compatible_provider import build_provider
from utils.json_utils import read_json, write_json
from utils.srt_utils import read_srt
from utils.text_utils import parse_json_object


def run_final_visual_qc(context, config: dict[str, Any]) -> dict[str, Path]:
    step_config = config.get("steps", {}).get("final_visual_qc", {})
    report_path = context.reports_dir / "final_visual_qc_report.json"
    if report_path.exists() and not step_config.get("overwrite", False):
        return {"final_visual_qc_report": report_path}

    frame_paths, original_frame_paths, sample_seconds = _capture_qc_frame_pairs(context, step_config)
    opencv_report = _opencv_rule_qc(frame_paths, original_frame_paths, sample_seconds, context.input_video, step_config)
    report = {
        "passed": opencv_report["passed"],
        "engine": "opencv_only",
        "frames": [str(path) for path in frame_paths],
        "original_frames": [str(path) for path in original_frame_paths],
        "sample_seconds": sample_seconds,
        "issues": [],
        "summary": "AI visual QC disabled or unavailable.",
        "opencv_rule_qc": opencv_report,
    }
    if step_config.get("vision_enabled", True):
        try:
            provider_name = step_config.get("provider", "vision")
            provider = build_provider(provider_name, config)
            prompt = _qc_prompt()
            response = provider.complete_with_images(prompt, frame_paths, step_config.get("model"))
            report = parse_json_object(response)
            report["frames"] = [str(path) for path in frame_paths]
            report["original_frames"] = [str(path) for path in original_frame_paths]
            report["sample_seconds"] = sample_seconds
            report["provider"] = provider_name
            report["ai_passed"] = bool(report.get("passed", True))
        except Exception as exc:
            logger.warning("Final visual QC failed with primary provider: {}", exc)
            fallback_provider = step_config.get("fallback_provider")
            if fallback_provider:
                provider = build_provider(fallback_provider, config)
                response = provider.complete_with_images(_qc_prompt(), frame_paths, step_config.get("fallback_model"))
                report = parse_json_object(response)
                report["frames"] = [str(path) for path in frame_paths]
                report["original_frames"] = [str(path) for path in original_frame_paths]
                report["sample_seconds"] = sample_seconds
                report["provider"] = fallback_provider
                report["ai_passed"] = bool(report.get("passed", True))
            elif step_config.get("fail_on_ai_error", False):
                raise
            else:
                report["ai_error"] = str(exc)

    report["opencv_rule_qc"] = opencv_report
    report["passed"] = bool(report.get("passed", True)) and opencv_report["passed"]
    if not opencv_report["passed"]:
        report.setdefault("issues", [])
        report["issues"].extend(opencv_report["issues"])
        report["summary"] = "OpenCV hard-rule QC failed; " + str(report.get("summary", ""))
    write_json(report_path, report)
    if not report.get("passed", True) and step_config.get("fail_on_overlap", False):
        raise ValueError(f"Final visual QC failed: {report.get('summary') or report.get('issues')}")
    return {"final_visual_qc_report": report_path}


def _capture_qc_frame_pairs(context, step_config: dict[str, Any]) -> tuple[list[Path], list[Path], list[float]]:
    import cv2

    final_dir = context.final_qc_screenshots_dir
    original_dir = context.final_qc_dir / "original_screenshots"
    final_dir.mkdir(parents=True, exist_ok=True)
    original_dir.mkdir(parents=True, exist_ok=True)
    final_capture = cv2.VideoCapture(str(context.final_video_path))
    original_capture = cv2.VideoCapture(str(context.input_video))
    if not final_capture.isOpened() or not original_capture.isOpened():
        raise ValueError("Cannot open original or final video for visual QC.")
    frame_count = int(final_capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = final_capture.get(cv2.CAP_PROP_FPS) or 25
    if frame_count <= 0 or fps <= 0:
        raise ValueError("Video has no readable frames.")
    duration = frame_count / fps if fps else 0
    seconds = _qc_sample_seconds(context, duration, int(step_config.get("sample_count", 10)), step_config)
    final_paths: list[Path] = []
    original_paths: list[Path] = []
    for index, second in enumerate(seconds, start=1):
        frame_index = max(0, min(frame_count - 1, int(second * fps)))
        final_capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        original_capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        final_success, final_frame = final_capture.read()
        original_success, original_frame = original_capture.read()
        if not final_success or not original_success:
            continue
        final_path = final_dir / f"final_qc_{index:03d}.jpg"
        original_path = original_dir / f"original_qc_{index:03d}.jpg"
        _write_cv_image(final_path, final_frame)
        _write_cv_image(original_path, original_frame)
        final_paths.append(final_path)
        original_paths.append(original_path)
    final_capture.release()
    original_capture.release()
    return final_paths, original_paths, seconds


def _qc_sample_seconds(context, duration: float, sample_count: int, step_config: dict[str, Any]) -> list[float]:
    import random

    if duration <= 0:
        return [0]
    interval = float(step_config.get("sample_interval_seconds", 1))
    strategy = step_config.get("sample_strategy", "middle_window_seconds")
    if strategy == "active_subtitle_middle":
        active_seconds = _active_subtitle_sample_seconds(context, duration, sample_count, interval)
        if active_seconds:
            return active_seconds
    if strategy == "middle_window_seconds":
        center = duration / 2
        start_offset = -((sample_count - 1) / 2) * interval
        return [
            max(0, min(duration, center + start_offset + idx * interval))
            for idx in range(sample_count)
        ]
    if strategy == "middle_plus_random_seconds":
        center_count = min(3, sample_count)
        center = duration / 2
        center_start = -((center_count - 1) / 2) * interval
        seconds = [
            max(0, min(duration, center + center_start + idx * interval))
            for idx in range(center_count)
        ]
        while len(seconds) < sample_count:
            candidate = random.uniform(duration * 0.08, duration * 0.92)
            if all(abs(candidate - existing) >= interval for existing in seconds):
                seconds.append(candidate)
        return sorted(seconds)
    return [(idx + 1) * duration / (sample_count + 1) for idx in range(sample_count)]


def _active_subtitle_sample_seconds(context, duration: float, sample_count: int, interval: float) -> list[float]:
    if not context.en_checked_srt_path.exists():
        return []
    items = [item for item in read_srt(context.en_checked_srt_path) if item.end_ms > item.start_ms]
    if not items:
        return []
    center_ms = duration * 500
    ordered = sorted(items, key=lambda item: abs(((item.start_ms + item.end_ms) / 2) - center_ms))
    seconds: list[float] = []
    for item in ordered:
        midpoint = ((item.start_ms + item.end_ms) / 2) / 1000
        midpoint = max(item.start_ms / 1000 + 0.05, min(item.end_ms / 1000 - 0.05, midpoint))
        if all(abs(midpoint - existing) >= interval for existing in seconds):
            seconds.append(round(max(0, min(duration, midpoint)), 3))
        if len(seconds) >= sample_count:
            return sorted(seconds)
    for item in ordered:
        midpoint = round(max(0, min(duration, ((item.start_ms + item.end_ms) / 2) / 1000)), 3)
        if midpoint not in seconds:
            seconds.append(midpoint)
        if len(seconds) >= sample_count:
            break
    return sorted(seconds)


def _qc_prompt() -> str:
    return (
        "你是视频字幕视觉质检员。请检查这些成品视频截图中，原视频里的中文字幕和新烧录的英文字幕是否重叠、混在一起、"
        "相互遮挡，或者明显影响观众阅读。还必须检查英文字幕是否过大、是否被画面边缘裁切、是否显示不完整、是否跑到顶部或遮挡主体。\n"
        "只输出 JSON，不要 Markdown。JSON 格式：\n"
        "{\n"
        '  "passed": true,\n'
        '  "summary": "简短结论",\n'
        '  "overlap_detected": false,\n'
        '  "readability": "good|acceptable|poor",\n'
        '  "english_subtitle_complete": true,\n'
        '  "english_subtitle_too_large": false,\n'
        '  "edge_clipping_detected": false,\n'
        '  "issues": [{"frame": "第几张", "problem": "问题", "suggestion": "建议"}],\n'
        '  "recommended_margin_v": 180,\n'
        '  "recommended_font_size_en": 34\n'
        "}\n"
        "如果英文字幕压住中文、两种字幕贴得太近、文字互相混杂、难以阅读、被裁切、显示不完整或字号明显过大，passed 必须为 false。"
    )


def _opencv_rule_qc(
    final_frame_paths: list[Path],
    original_frame_paths: list[Path],
    sample_seconds: list[float],
    original_video_path: Path,
    step_config: dict[str, Any],
) -> dict[str, Any]:
    if not step_config.get("opencv_rule_enabled", True):
        return {"passed": True, "enabled": False, "issues": []}
    frame_reports = []
    issues = []
    warnings = []
    for index, (final_path, original_path) in enumerate(zip(final_frame_paths, original_frame_paths), start=1):
        second = sample_seconds[index - 1] if index - 1 < len(sample_seconds) else None
        report = _analyze_frame_pair_with_opencv(final_path, original_path, second, original_video_path, step_config)
        frame_reports.append(report)
        issues.extend(report["issues"])
        warnings.extend(report.get("warnings", []))
    return {
        "passed": not issues,
        "enabled": True,
        "checked_frame_count": len(frame_reports),
        "issues": issues,
        "warnings": warnings,
        "frames": frame_reports,
    }


def _analyze_frame_pair_with_opencv(
    final_path: Path,
    original_path: Path,
    second: float | None,
    original_video_path: Path,
    step_config: dict[str, Any],
) -> dict[str, Any]:
    import cv2
    import numpy as np

    final_frame = _read_cv_image(final_path)
    original_frame = _read_cv_image(original_path)
    if final_frame is None or original_frame is None:
        return {
            "frame": str(final_path),
            "original_frame": str(original_path),
            "second": second,
            "passed": False,
            "issues": [{"frame": str(final_path), "problem": "cannot read frame pair"}],
        }
    height, width = final_frame.shape[:2]
    original_frame = cv2.resize(original_frame, (width, height))
    final_mask = _text_like_mask(final_frame)
    original_mask = _text_like_mask(original_frame)
    added_mask = _added_text_mask(final_frame, original_frame, final_mask)
    added_text_bands = _bands_from_mask(
        added_mask,
        min_y_ratio=float(step_config.get("final_subtitle_min_y_ratio", 0.35)),
        max_y_ratio=float(step_config.get("final_subtitle_max_y_ratio", 0.98)),
    )
    final_text_bands = _bands_from_mask(
        final_mask,
        min_y_ratio=float(step_config.get("final_subtitle_min_y_ratio", 0.35)),
        max_y_ratio=float(step_config.get("final_subtitle_max_y_ratio", 0.98)),
    )
    english_bbox = _pick_english_band(added_text_bands) or _mask_bbox(added_mask, min_area=80) or _pick_english_band(final_text_bands)
    original_bands = _bands_from_mask(
        original_mask,
        min_y_ratio=float(step_config.get("original_subtitle_min_y_ratio", 0.25)),
        max_y_ratio=float(step_config.get("original_subtitle_max_y_ratio", 0.88)),
    )

    issues = []
    warnings = []
    edge_margin = int(step_config.get("edge_margin_px", 8))
    max_band_height = int(height * float(step_config.get("max_subtitle_band_height_ratio", 0.085)))
    min_gap = int(height * float(step_config.get("min_subtitle_gap_ratio", 0.035)))
    max_gap = max(
        int(step_config.get("max_subtitle_gap_px", 96)),
        int(height * float(step_config.get("max_subtitle_gap_ratio", 0.075))),
    )

    if not english_bbox:
        issues.append({"frame": str(final_path), "problem": "new English subtitle not detected", "suggestion": "check ASS rendering"})
    else:
        if english_bbox["height"] > max_band_height:
            issues.append(
                {
                    "frame": str(final_path),
                    "problem": f"English subtitle bbox too tall: {english_bbox['height']}px",
                    "suggestion": "reduce font_size_en or check ASS PlayRes",
                }
            )
        if (
            english_bbox["x1"] <= edge_margin
            or english_bbox["x2"] >= width - edge_margin
            or english_bbox["y1"] <= edge_margin
            or english_bbox["y2"] >= height - edge_margin
        ):
            issues.append(
                {
                    "frame": str(final_path),
                    "problem": "English subtitle bbox is clipped by frame edge",
                    "suggestion": "move subtitle away from edge",
                    }
                )
        primary_original_band = _pick_primary_original_subtitle_band(original_bands, english_bbox, width, height, step_config)
        if primary_original_band:
            subtitle_gap = english_bbox["y1"] - primary_original_band["y2"]
            if subtitle_gap < 0:
                issues.append(
                    {
                        "frame": str(final_path),
                        "problem": f"English subtitle overlaps original Chinese subtitle: overlap={abs(subtitle_gap)}px",
                        "suggestion": "move English subtitle below the detected Chinese subtitle band",
                    }
                )
            elif subtitle_gap < min_gap:
                warnings.append(
                    {
                        "frame": str(final_path),
                        "problem": f"English subtitle too close to original Chinese subtitle: gap={subtitle_gap}px",
                        "suggestion": "increase subtitle_gap_px or lower the English subtitle slightly",
                    }
                )
            elif subtitle_gap > max_gap:
                issues.append(
                    {
                        "frame": str(final_path),
                        "problem": f"English subtitle too far from original Chinese subtitle: gap={subtitle_gap}px",
                        "suggestion": "reduce subtitle_gap_px or increase margin_v so the bilingual subtitles stay together",
                    }
                )
        if step_config.get("require_original_subtitle_evidence", True) and second is not None:
            visible = subtitle_visible_near_time(original_video_path, second, step_config)
            if visible is False:
                warnings.append(
                    {
                        "frame": str(final_path),
                        "problem": "English subtitle appears where the original frame has no subtitle evidence",
                        "suggestion": "review frame manually or tune source visual validation",
                    }
                )
        min_horizontal_overlap = float(step_config.get("min_horizontal_overlap_ratio", 0.25))
        for band in original_bands:
            if _horizontal_overlap_ratio(english_bbox, band) < min_horizontal_overlap:
                continue
            overlap = not (english_bbox["y2"] < band["y1"] or english_bbox["y1"] > band["y2"])
            vertical_overlap = max(0, min(english_bbox["y2"], band["y2"]) - max(english_bbox["y1"], band["y1"]))
            if overlap and band["y1"] >= english_bbox["y1"] and vertical_overlap < int(step_config.get("min_vertical_overlap_px", 5)):
                continue
            if not overlap and band["y1"] >= english_bbox["y2"]:
                continue
            gap = min(abs(english_bbox["y1"] - band["y2"]), abs(band["y1"] - english_bbox["y2"]))
            band_center_x = (band["x1"] + band["x2"]) / 2
            centered_band = abs(band_center_x - width / 2) <= width * float(
                step_config.get("source_subtitle_center_tolerance_ratio", 0.18)
            )
            if overlap and centered_band:
                issues.append(
                    {
                        "frame": str(final_path),
                        "problem": f"English subtitle too close to original subtitle/text band: gap={gap}px",
                        "suggestion": "increase margin_v or reduce font_size_en",
                    }
                )
            elif overlap or gap < min_gap:
                warnings.append(
                    {
                        "frame": str(final_path),
                        "problem": f"English subtitle near non-primary text band: gap={gap}px",
                        "suggestion": "review frame manually if the background UI text matters",
                    }
                )

    return {
        "frame": str(final_path),
        "original_frame": str(original_path),
        "second": second,
        "passed": not issues,
        "width": width,
        "height": height,
        "english_bbox": english_bbox,
        "primary_original_subtitle_bbox": _pick_primary_original_subtitle_band(original_bands, english_bbox, width, height, step_config)
        if english_bbox
        else None,
        "added_text_bands": added_text_bands,
        "final_text_bands": final_text_bands,
        "original_text_bands": original_bands,
        "issues": issues,
        "warnings": warnings,
    }


def _read_cv_image(path: Path):
    import cv2
    import numpy as np

    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def _text_like_mask(frame):
    import cv2
    import numpy as np

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    bright_white = ((gray > 185) & (hsv[:, :, 1] < 105)).astype("uint8") * 255
    edges = cv2.Canny(gray, 80, 180)
    mask = cv2.bitwise_and(bright_white, cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1))
    return cv2.dilate(mask, np.ones((3, 5), np.uint8), iterations=1)


def _added_text_mask(final_frame, original_frame, final_mask):
    import cv2
    import numpy as np

    diff = cv2.absdiff(final_frame, original_frame)
    diff_gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    changed = (diff_gray > 18).astype("uint8") * 255
    changed = cv2.dilate(changed, np.ones((5, 9), np.uint8), iterations=1)
    original_text = _text_like_mask(original_frame)
    original_text = cv2.dilate(original_text, np.ones((9, 15), np.uint8), iterations=1)
    new_region = cv2.bitwise_and(changed, cv2.bitwise_not(original_text))
    added = cv2.bitwise_and(final_mask, new_region)
    return cv2.dilate(added, np.ones((3, 5), np.uint8), iterations=1)


def _mask_bbox(mask, min_area: int) -> dict[str, int] | None:
    import cv2

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if area >= min_area and h >= 8 and w >= 8:
            boxes.append((x, y, x + w, y + h))
    if not boxes:
        return None
    x1 = min(box[0] for box in boxes)
    y1 = min(box[1] for box in boxes)
    x2 = max(box[2] for box in boxes)
    y2 = max(box[3] for box in boxes)
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "width": x2 - x1, "height": y2 - y1}


def _pick_english_band(bands: list[dict[str, int]]) -> dict[str, int] | None:
    if not bands:
        return None
    # The rendered English subtitle is expected to be the lowest text band added by this pipeline.
    band = max(bands, key=lambda item: (item["y2"], item.get("component_count", 0)))
    return {
        "x1": band.get("x1", 0),
        "y1": band["y1"],
        "x2": band.get("x2", 0),
        "y2": band["y2"],
        "width": max(0, band.get("x2", 0) - band.get("x1", 0)),
        "height": band["height"],
        "component_count": band.get("component_count", 0),
    }


def _pick_primary_original_subtitle_band(
    bands: list[dict[str, int]],
    english_bbox: dict[str, int],
    width: int,
    height: int,
    step_config: dict[str, Any],
) -> dict[str, int] | None:
    candidates: list[tuple[float, dict[str, int]]] = []
    min_width = width * float(step_config.get("primary_source_min_width_ratio", 0.18))
    center_tolerance = width * float(step_config.get("source_subtitle_center_tolerance_ratio", 0.24))
    preferred_y = height * float(step_config.get("primary_source_preferred_y_ratio", 0.64))
    min_source_y2 = height * float(step_config.get("primary_source_min_y2_ratio", 0.55))
    for band in bands:
        band_width = band.get("width") or band.get("x2", 0) - band.get("x1", 0)
        if band_width < min_width:
            continue
        if band["y2"] < min_source_y2:
            continue
        center_x = (band.get("x1", 0) + band.get("x2", 0)) / 2
        if abs(center_x - width / 2) > center_tolerance:
            continue
        if band["y1"] >= english_bbox["y2"]:
            continue
        if _horizontal_overlap_ratio(english_bbox, {**band, "width": band_width}) < float(
            step_config.get("min_horizontal_overlap_ratio", 0.25)
        ):
            continue
        center_y = (band["y1"] + band["y2"]) / 2
        gap = english_bbox["y1"] - band["y2"]
        score = (
            band_width * 0.4
            + band.get("component_count", 0) * 16
            + band["y2"] * 1.25
            - abs(center_y - preferred_y) * 0.25
            - abs(gap - height * 0.035) * 5.0
        )
        candidates.append((score, {**band, "width": band_width}))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _horizontal_overlap_ratio(first: dict[str, int], second: dict[str, int]) -> float:
    overlap = max(0, min(first["x2"], second["x2"]) - max(first["x1"], second["x1"]))
    smaller_width = max(1, min(first["width"], second.get("width", second["x2"] - second["x1"])))
    return overlap / smaller_width


def _bands_from_mask(mask, min_y_ratio: float, max_y_ratio: float = 1.0) -> list[dict[str, int]]:
    import cv2

    height, width = mask.shape[:2]
    min_y = height * min_y_ratio
    max_y = height * max_y_ratio
    component_mask = cv2.connectedComponentsWithStats((mask > 0).astype("uint8"), 8)
    _, labels, stats, _ = component_mask
    row_components: list[list[dict[str, int]]] = [[] for _ in range(height)]
    for label in range(1, stats.shape[0]):
        x, y, w, h, area = [int(value) for value in stats[label]]
        if y < min_y or y + h > max_y:
            continue
        if x < width * 0.04 or x + w > width * 0.96:
            continue
        if area < 8 or area > width * height * 0.01:
            continue
        if h < max(6, height * 0.006) or h > height * 0.075:
            continue
        if w < 2 or w > width * 0.35:
            continue
        component = {"x1": x, "y1": y, "x2": x + w, "y2": y + h, "height": h, "width": w}
        for row in range(y, min(height, y + h)):
            row_components[row].append(component)

    active_rows = [len(components) >= 3 for components in row_components]
    bands = _rows_to_bands(active_rows, height, min_height=max(8, int(height * 0.012)))
    enriched = []
    for band in bands:
        components = {}
        for row in range(band["y1"], band["y2"] + 1):
            for component in row_components[row]:
                components[(component["x1"], component["y1"], component["x2"], component["y2"])] = component
        if len(components) < 4:
            continue
        xs = [component["x1"] for component in components.values()] + [component["x2"] for component in components.values()]
        band["x1"] = min(xs)
        band["x2"] = max(xs)
        band["component_count"] = len(components)
        enriched.append(band)
    return enriched


def _rows_to_bands(active_rows, frame_height: int, min_height: int) -> list[dict[str, int]]:
    bands = []
    start = None
    for idx, active in enumerate(active_rows):
        if active and start is None:
            start = idx
        elif not active and start is not None:
            if idx - start >= min_height:
                bands.append({"y1": start, "y2": idx - 1, "height": idx - start})
            start = None
    if start is not None and frame_height - start >= min_height:
        bands.append({"y1": start, "y2": frame_height - 1, "height": frame_height - start})
    return _merge_close_bands(bands, max_gap=max(4, int(frame_height * 0.01)))


def _merge_close_bands(bands: list[dict[str, int]], max_gap: int) -> list[dict[str, int]]:
    merged: list[dict[str, int]] = []
    for band in bands:
        if not merged or band["y1"] - merged[-1]["y2"] > max_gap:
            merged.append(dict(band))
        else:
            merged[-1]["y2"] = band["y2"]
            merged[-1]["height"] = merged[-1]["y2"] - merged[-1]["y1"] + 1
    return merged


def _write_cv_image(path: Path, frame) -> None:
    import cv2

    path.parent.mkdir(parents=True, exist_ok=True)
    success, encoded = cv2.imencode(path.suffix or ".jpg", frame)
    if not success:
        raise ValueError(f"Failed to encode image: {path}")
    encoded.tofile(str(path))
