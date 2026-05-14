import re
import hashlib
from pathlib import Path
from typing import Any

from loguru import logger

from core.final_visual_qc import _analyze_frame_pair_with_opencv, _estimated_source_visual_bottom
from core.video_renderer import render_ass_to_video
from utils.json_utils import read_json, write_json
from utils.srt_utils import read_srt


POS_RE = re.compile(r"\\pos\(([-\d.]+),([-\d.]+)\)")


def fit_subtitle_layout(context, config: dict[str, Any]) -> dict[str, Path]:
    step_config = config.get("steps", {}).get("subtitle_layout_fit", {})
    report_path = context.reports_dir / "subtitle_layout_fit_report.json"
    if report_path.exists() and not step_config.get("overwrite", False):
        return {"subtitle_layout_fit_report": report_path, "final_video": context.final_video_path}
    if not step_config.get("enabled", True):
        write_json(report_path, {"passed": True, "enabled": False, "adjusted_count": 0})
        return {"subtitle_layout_fit_report": report_path, "final_video": context.final_video_path}

    ass_path = context.english_ass_path
    if not ass_path.exists() or not context.final_video_path.exists():
        raise FileNotFoundError("subtitle_layout_fit requires english.ass and rendered final video.")

    fit_dir = context.task_dir / "layout_fit"
    fit_dir.mkdir(parents=True, exist_ok=True)
    backup_path = fit_dir / "english_before_layout_fit.ass"
    current_ass_hash = _file_hash(ass_path)
    try:
        previous_report = read_json(report_path) if report_path.exists() else {}
    except Exception:
        previous_report = {}
    report_is_newer_than_ass = report_path.exists() and report_path.stat().st_mtime >= ass_path.stat().st_mtime
    restored_backup = False
    if (
        backup_path.exists()
        and (
            (
                previous_report.get("fitted_ass_hash")
                and current_ass_hash == previous_report.get("fitted_ass_hash")
            )
            or (
                not previous_report.get("fitted_ass_hash")
                and previous_report.get("adjusted_count", 0)
                and report_is_newer_than_ass
            )
        )
    ):
        ass_path.write_text(backup_path.read_text(encoding="utf-8-sig"), encoding="utf-8-sig")
        current_ass_hash = _file_hash(ass_path)
        restored_backup = True
    else:
        backup_path.write_text(ass_path.read_text(encoding="utf-8-sig"), encoding="utf-8-sig")

    video_info = read_json(context.video_info_path)
    position = read_json(context.subtitle_position_path) if context.subtitle_position_path.exists() else {}
    qc_config = {
        **config.get("steps", {}).get("final_visual_qc", {}),
        "_detected_original_subtitle_bbox": position.get("detected_original_subtitle_bbox"),
    }
    render_config = config.get("steps", {}).get("render_video", {})
    max_iterations = int(step_config.get("max_iterations", 2))
    target_gap = int(step_config.get("target_gap_px", 18))
    min_gap = int(step_config.get("min_gap_px", 12))
    max_gap = int(step_config.get("max_gap_px", 28))
    max_adjust_px = int(step_config.get("max_adjust_px", 60))
    min_confidence = str(step_config.get("min_source_confidence", "original"))
    if restored_backup:
        render_ass_to_video(
            context.input_video,
            ass_path,
            context.final_video_path,
            config,
            render_config,
            context.logs_dir / "ffmpeg_layout_fit.log",
        )

    iterations = []
    adjusted_total = 0
    last_adjustments: dict[int, int] = {}
    for iteration in range(1, max_iterations + 1):
        measurements = _measure_subtitle_gaps(context, fit_dir, video_info, qc_config, step_config, iteration)
        adjustments = _build_adjustments(measurements, target_gap, min_gap, max_gap, max_adjust_px, min_confidence)
        last_adjustments = adjustments
        iterations.append(
            {
                "iteration": iteration,
                "measurement_count": len(measurements),
                "adjustment_count": len(adjustments),
                "measurements": measurements,
                "adjustments": adjustments,
            }
        )
        if not adjustments:
            break
        _apply_ass_adjustments(ass_path, adjustments, int(video_info.get("height") or 1280), step_config)
        adjusted_total += len(adjustments)
        render_ass_to_video(
            context.input_video,
            ass_path,
            context.final_video_path,
            config,
            render_config,
            context.logs_dir / "ffmpeg_layout_fit.log",
        )
        logger.info("Subtitle layout fit iteration {} adjusted {} event(s).", iteration, len(adjustments))

    if last_adjustments:
        final_measurements = _measure_subtitle_gaps(
            context,
            fit_dir,
            video_info,
            qc_config,
            step_config,
            max_iterations + 1,
        )
        final_adjustments = _build_adjustments(
            final_measurements,
            target_gap,
            min_gap,
            max_gap,
            max_adjust_px,
            min_confidence,
        )
        iterations.append(
            {
                "iteration": "final_check",
                "measurement_count": len(final_measurements),
                "adjustment_count": len(final_adjustments),
                "measurements": final_measurements,
                "adjustments": final_adjustments,
            }
        )

    report = {
        "passed": True,
        "enabled": True,
        "target_gap_px": target_gap,
        "min_gap_px": min_gap,
        "max_gap_px": max_gap,
        "adjusted_count": adjusted_total,
        "iterations": iterations,
        "backup_ass": str(backup_path),
        "ass": str(ass_path),
        "input_ass_hash": current_ass_hash,
        "fitted_ass_hash": _file_hash(ass_path),
        "final_video": str(context.final_video_path),
    }
    write_json(report_path, report)
    return {"subtitle_layout_fit_report": report_path, "final_video": context.final_video_path}


def _measure_subtitle_gaps(
    context,
    fit_dir: Path,
    video_info: dict[str, Any],
    qc_config: dict[str, Any],
    step_config: dict[str, Any],
    iteration: int,
) -> list[dict[str, Any]]:
    import cv2

    items = [item for item in read_srt(context.en_checked_srt_path) if item.end_ms > item.start_ms]
    if not items:
        return []
    max_samples = int(step_config.get("max_sample_count", 0))
    if max_samples > 0 and len(items) > max_samples:
        stride = max(1, len(items) // max_samples)
        sampled = items[::stride][:max_samples]
    else:
        sampled = items

    final_capture = cv2.VideoCapture(str(context.final_video_path))
    original_capture = cv2.VideoCapture(str(context.input_video))
    if not final_capture.isOpened() or not original_capture.isOpened():
        raise ValueError("Cannot open original or final video for subtitle layout fitting.")
    fps = final_capture.get(cv2.CAP_PROP_FPS) or video_info.get("fps") or 25
    frame_count = int(final_capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    frame_dir = fit_dir / f"iteration_{iteration:02d}"
    frame_dir.mkdir(parents=True, exist_ok=True)
    measurements = []
    try:
        for item in sampled:
            second = max(0, ((item.start_ms + item.end_ms) / 2) / 1000)
            frame_index = max(0, min(frame_count - 1, int(second * fps)))
            final_capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            original_capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            final_success, final_frame = final_capture.read()
            original_success, original_frame = original_capture.read()
            if not final_success or not original_success:
                continue
            final_path = frame_dir / f"final_{item.index:04d}.jpg"
            original_path = frame_dir / f"original_{item.index:04d}.jpg"
            _write_cv_image(final_path, final_frame)
            _write_cv_image(original_path, original_frame)
            report = _analyze_frame_pair_with_opencv(final_path, original_path, second, context.input_video, qc_config)
            english = report.get("english_bbox")
            source = report.get("primary_original_subtitle_bbox")
            if not english or not source:
                continue
            source_bottom = _estimated_source_visual_bottom(source, int(report.get("height") or video_info.get("height") or 1280), qc_config)
            actual_gap = int(english["y1"] - source_bottom)
            confidence = _source_confidence(report)
            measurements.append(
                {
                    "index": item.index,
                    "second": second,
                    "actual_gap_px": actual_gap,
                    "source_confidence": confidence,
                    "english_bbox": english,
                    "source_bbox": source,
                    "frame": str(final_path),
                    "original_frame": str(original_path),
                }
            )
    finally:
        final_capture.release()
        original_capture.release()
    return measurements


def _build_adjustments(
    measurements: list[dict[str, Any]],
    target_gap: int,
    min_gap: int,
    max_gap: int,
    max_adjust_px: int,
    min_confidence: str,
) -> dict[int, int]:
    order = {"none": 0, "detected": 1, "visual": 2, "original": 3}
    required = order.get(min_confidence, 1)
    adjustments = {}
    for measurement in measurements:
        if order.get(measurement.get("source_confidence", "none"), 0) < required:
            continue
        actual_gap = int(measurement["actual_gap_px"])
        if min_gap <= actual_gap <= max_gap:
            continue
        delta = target_gap - actual_gap
        delta = max(-max_adjust_px, min(max_adjust_px, delta))
        adjustments[int(measurement["index"])] = delta
    return adjustments


def _apply_ass_adjustments(ass_path: Path, adjustments: dict[int, int], height: int, step_config: dict[str, Any]) -> None:
    lines = ass_path.read_text(encoding="utf-8-sig").splitlines()
    event_index = 0
    min_y = int(height * float(step_config.get("min_y_ratio", 0.50)))
    max_y = int(height * float(step_config.get("max_y_ratio", 0.86)))
    output_lines = []
    for line in lines:
        if line.startswith("Dialogue:"):
            event_index += 1
            delta = adjustments.get(event_index)
            if delta:
                line = _adjust_pos_y(line, delta, min_y, max_y)
        output_lines.append(line)
    ass_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8-sig")


def _adjust_pos_y(line: str, delta: int, min_y: int, max_y: int) -> str:
    match = POS_RE.search(line)
    if not match:
        return line
    x = float(match.group(1))
    y = float(match.group(2))
    new_y = max(min_y, min(max_y, int(round(y + delta))))
    replacement = f"\\pos({int(round(x))},{new_y})"
    return POS_RE.sub(lambda _: replacement, line, count=1)


def _source_confidence(report: dict[str, Any]) -> str:
    source = report.get("primary_original_subtitle_bbox")
    if not source:
        return "none"
    for band in report.get("original_text_bands", []):
        if _similar_band(source, band):
            return "original"
    for band in report.get("final_text_bands", []):
        if _similar_band(source, band):
            return "visual"
    return "detected"


def _similar_band(first: dict[str, int], second: dict[str, int]) -> bool:
    return abs(int(first["y1"]) - int(second["y1"])) <= 6 and abs(int(first["y2"]) - int(second["y2"])) <= 6


def _write_cv_image(path: Path, frame) -> None:
    import cv2

    success, encoded = cv2.imencode(path.suffix or ".jpg", frame)
    if not success:
        raise ValueError(f"Failed to encode image: {path}")
    encoded.tofile(str(path))


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
