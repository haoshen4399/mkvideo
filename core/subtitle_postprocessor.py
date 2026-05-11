from pathlib import Path
from typing import Any

from core.subtitle_visual import frame_has_subtitle_text
from utils.json_utils import write_json
from utils.srt_utils import SubtitleItem, read_srt, validate_basic, write_srt


def postprocess_zh_subtitles(context, config: dict[str, Any]) -> dict[str, Path]:
    step_config = config.get("steps", {}).get("zh_postprocess", {})
    output = context.zh_clean_srt_path
    report_path = context.reports_dir / "zh_postprocess_report.json"
    if output.exists() and not step_config.get("overwrite", False):
        return {"zh_clean_srt": output, "zh_postprocess_report": report_path}

    items = [item for item in read_srt(context.zh_raw_srt_path) if item.text.strip()]
    min_duration = int(step_config.get("min_duration_ms", 800))
    max_duration = int(step_config.get("max_duration_ms", 7000))
    fixed: list[SubtitleItem] = []
    changes: list[str] = []
    first_visual_start_ms = _detect_first_visual_subtitle_start_ms(context.input_video, step_config)
    for item in items:
        text = _normalize_zh_punctuation(item.text.strip())
        start_ms = max(0, item.start_ms)
        end_ms = max(start_ms + min_duration, item.end_ms)
        if (
            not fixed
            and first_visual_start_ms is not None
            and start_ms < int(step_config.get("first_start_guard_max_original_ms", 500))
            and first_visual_start_ms > int(step_config.get("first_start_guard_min_shift_ms", 800))
        ):
            start_ms = min(first_visual_start_ms, max(0, end_ms - min_duration))
            changes.append(f"adjust first subtitle start to visual subtitle at {start_ms}ms")
        if end_ms - start_ms > max_duration:
            end_ms = start_ms + max_duration
            changes.append(f"limit duration at index {item.index}")
        if fixed and start_ms < fixed[-1].end_ms:
            start_ms = fixed[-1].end_ms + 1
            end_ms = max(end_ms, start_ms + min_duration)
            changes.append(f"fix overlap at index {item.index}")
        if fixed and end_ms - start_ms < min_duration and step_config.get("merge_short_subtitle", True):
            fixed[-1].text = f"{fixed[-1].text}{text}"
            fixed[-1].end_ms = max(fixed[-1].end_ms, end_ms)
            changes.append(f"merge short subtitle at index {item.index}")
            continue
        fixed.append(SubtitleItem(index=len(fixed) + 1, start_ms=start_ms, end_ms=end_ms, text=text))
    if step_config.get("filter_repeated_text_runs", True):
        fixed, repeat_changes = _filter_repeated_text_runs(fixed, step_config)
        changes.extend(repeat_changes)
    visual_summary = {"enabled": False}
    if step_config.get("visual_presence_filter_enabled", True):
        fixed, visual_summary, visual_changes = _filter_items_without_visual_subtitle(
            fixed, context.input_video, step_config
        )
        changes.extend(visual_changes)
    errors = validate_basic(fixed)
    if errors:
        raise ValueError("; ".join(errors))
    write_srt(output, fixed)
    write_json(
        report_path,
        {
            "passed": True,
            "changes": changes,
            "subtitle_count": len(fixed),
            "visual_presence_filter": visual_summary,
        },
    )
    return {"zh_clean_srt": output, "zh_postprocess_report": report_path}


def _filter_repeated_text_runs(
    items: list[SubtitleItem], step_config: dict[str, Any]
) -> tuple[list[SubtitleItem], list[str]]:
    min_count = int(step_config.get("repeated_text_min_count", 4))
    min_span_ms = int(step_config.get("repeated_text_min_span_ms", 4000))
    filtered: list[SubtitleItem] = []
    changes: list[str] = []
    idx = 0
    while idx < len(items):
        current_key = _repeat_key(items[idx].text)
        end = idx + 1
        while end < len(items) and _repeat_key(items[end].text) == current_key:
            end += 1
        run = items[idx:end]
        run_span_ms = run[-1].end_ms - run[0].start_ms
        if current_key and len(run) >= min_count and run_span_ms >= min_span_ms:
            changes.append(
                f"drop repeated ASR run '{run[0].text}' count={len(run)} span={run_span_ms}ms"
            )
        else:
            filtered.extend(run)
        idx = end
    return [
        SubtitleItem(index=index, start_ms=item.start_ms, end_ms=item.end_ms, text=item.text)
        for index, item in enumerate(filtered, start=1)
    ], changes


def _repeat_key(text: str) -> str:
    return (
        text.strip()
        .replace("这一次", "这次")
        .replace("，", "")
        .replace("。", "")
        .replace("？", "")
        .replace("！", "")
        .replace(",", "")
        .replace(".", "")
        .replace("?", "")
        .replace("!", "")
    )


def _filter_items_without_visual_subtitle(
    items: list[SubtitleItem], video_path: Path, step_config: dict[str, Any]
) -> tuple[list[SubtitleItem], dict[str, Any], list[str]]:
    import cv2

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return items, {"enabled": True, "passed": False, "error": "cannot open video"}, []
    fps = capture.get(cv2.CAP_PROP_FPS) or 25
    min_duration_ms = int(step_config.get("visual_presence_min_duration_ms", 700))
    required_ratio = float(step_config.get("visual_presence_required_ratio", 0.25))
    filtered: list[SubtitleItem] = []
    dropped: list[dict[str, Any]] = []
    checked = 0
    try:
        for item in items:
            if item.duration_ms < min_duration_ms:
                filtered.append(item)
                continue
            checked += 1
            sample_ms = (item.start_ms + item.end_ms) / 2
            capture.set(cv2.CAP_PROP_POS_FRAMES, int((sample_ms / 1000) * fps))
            success, frame = capture.read()
            visible = success and frame_has_subtitle_text(frame, step_config)
            if visible:
                filtered.append(item)
                continue
            dropped.append(
                {
                    "index": item.index,
                    "start_ms": item.start_ms,
                    "end_ms": item.end_ms,
                    "text": item.text,
                    "reason": "no original visual subtitle detected at midpoint",
                }
            )
    finally:
        capture.release()
    drop_ratio = len(dropped) / checked if checked else 0
    if drop_ratio > required_ratio:
        summary = {
            "enabled": True,
            "passed": False,
            "checked": checked,
            "dropped": len(dropped),
            "drop_ratio": round(drop_ratio, 4),
            "reason": "too many source subtitles have no visual subtitle evidence",
            "dropped_items": dropped[:20],
        }
        if step_config.get("visual_presence_fail_on_many_drops", True):
            raise ValueError(summary["reason"])
        return items, summary, []
    reindexed = [
        SubtitleItem(index=index, start_ms=item.start_ms, end_ms=item.end_ms, text=item.text)
        for index, item in enumerate(filtered, start=1)
    ]
    changes = [
        f"drop subtitle without original visual evidence at {item['start_ms']}ms: {item['text']}"
        for item in dropped
    ]
    return (
        reindexed,
        {
            "enabled": True,
            "passed": True,
            "checked": checked,
            "dropped": len(dropped),
            "drop_ratio": round(drop_ratio, 4),
            "dropped_items": dropped[:20],
        },
        changes,
    )


def _normalize_zh_punctuation(text: str) -> str:
    return (
        text.replace(",", "，")
        .replace("?", "？")
        .replace("!", "！")
        .replace(";", "；")
        .replace(":", "：")
    )


def _detect_first_visual_subtitle_start_ms(video_path: Path, step_config: dict[str, Any]) -> int | None:
    if not step_config.get("visual_first_subtitle_guard", True):
        return None
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return None
    fps = capture.get(cv2.CAP_PROP_FPS) or 25
    scan_seconds = float(step_config.get("first_subtitle_scan_seconds", 12))
    interval = float(step_config.get("first_subtitle_scan_interval_seconds", 0.25))
    lead_pad_ms = int(step_config.get("first_subtitle_lead_pad_ms", 200))
    min_y_ratio = float(step_config.get("visual_subtitle_min_y_ratio", 0.45))
    max_y_ratio = float(step_config.get("visual_subtitle_max_y_ratio", 0.92))

    current = 0.0
    detected_ms: int | None = None
    while current <= scan_seconds:
        capture.set(cv2.CAP_PROP_POS_FRAMES, int(current * fps))
        success, frame = capture.read()
        if not success:
            current += interval
            continue
        if _frame_has_subtitle_text(frame, min_y_ratio, max_y_ratio, cv2, np):
            detected_ms = max(0, int(current * 1000) - lead_pad_ms)
            break
        current += interval
    capture.release()
    return detected_ms


def _frame_has_subtitle_text(frame, min_y_ratio: float, max_y_ratio: float, cv2, np) -> bool:
    height, width = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    raw_mask = ((gray > 170) & (hsv[:, :, 1] < 120)).astype("uint8") * 255
    mask = raw_mask.copy()
    mask[: int(height * min_y_ratio), :] = 0
    mask[int(height * max_y_ratio) :, :] = 0
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 21), np.uint8), iterations=1)
    mask = cv2.dilate(mask, np.ones((3, 9), np.uint8), iterations=1)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        center_x = x + w / 2
        if not (width * 0.3 <= w <= width * 0.9):
            continue
        if not (height * 0.025 <= h <= height * 0.08):
            continue
        if abs(center_x - width / 2) > width * 0.3:
            continue
        roi = raw_mask[y : y + h, x : x + w]
        count, _, stats, _ = cv2.connectedComponentsWithStats((roi > 0).astype("uint8"), 8)
        component_count = 0
        for label in range(1, count):
            _, _, component_width, component_height, area = [int(value) for value in stats[label]]
            if 8 <= area <= 1000 and component_width >= 2 and component_height >= 5:
                component_count += 1
        if component_count >= 12:
            return True
    return False
