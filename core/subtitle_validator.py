from pathlib import Path
from typing import Any

from utils.json_utils import write_json
from utils.srt_utils import read_srt, validate_basic, write_srt


def validate_english_subtitles(context, config: dict[str, Any]) -> dict[str, Path]:
    step_config = config.get("steps", {}).get("en_check", {})
    output = context.en_checked_srt_path
    report_path = context.reports_dir / "en_check_report.json"
    if output.exists() and not step_config.get("overwrite", False):
        return {"en_checked_srt": output, "en_check_report": report_path}

    en_items = read_srt(context.en_raw_srt_path)
    source_path = context.zh_ai_checked_srt_path if context.zh_ai_checked_srt_path.exists() else context.zh_clean_srt_path
    source_items = read_srt(source_path)
    errors = validate_basic(en_items)
    warnings: list[str] = []
    timing_report = _build_timing_report(source_items, en_items)
    if not timing_report["total_time_equal"]:
        errors.append(
            "total subtitle time mismatch: "
            f"source={timing_report['source_total_ms']}ms, en={timing_report['en_total_ms']}ms"
        )
    if not timing_report["span_equal"]:
        errors.append(
            "subtitle span mismatch: "
            f"source={timing_report['source_start_ms']}ms-{timing_report['source_end_ms']}ms, "
            f"en={timing_report['en_start_ms']}ms-{timing_report['en_end_ms']}ms"
        )
    if len(en_items) != len(source_items):
        errors.append(f"subtitle count mismatch: en={len(en_items)}, source={len(source_items)}")
    for idx, (source_item, en_item) in enumerate(zip(source_items, en_items), start=1):
        if en_item.start_ms != source_item.start_ms or en_item.end_ms != source_item.end_ms:
            warnings.append(f"index {idx} time adjusted to source")
            en_item.start_ms = source_item.start_ms
            en_item.end_ms = source_item.end_ms
        lines = en_item.text.splitlines()
        if len(lines) > int(step_config.get("max_lines", 2)):
            warnings.append(f"index {idx} has more than 2 lines")
        max_line_chars = int(step_config.get("max_line_chars", 42))
        wrapped = []
        for line in lines:
            wrapped.extend(_wrap_line(line, max_line_chars))
        if len(wrapped) <= 2:
            en_item.text = "\n".join(wrapped)
        else:
            midpoint = max(1, len(wrapped) // 2)
            en_item.text = "\n".join([" ".join(wrapped[:midpoint]), " ".join(wrapped[midpoint:])])
        duration = max(0.001, (en_item.end_ms - en_item.start_ms) / 1000)
        cps = len(en_item.text.replace("\n", "")) / duration
        if cps > float(step_config.get("max_cps", 17)):
            warnings.append(f"index {idx} cps {cps:.1f} exceeds limit")
        if _looks_mojibake(en_item.text):
            errors.append(f"index {idx} looks garbled")
    if errors:
        write_json(report_path, {"passed": False, "errors": errors, "warnings": warnings, "timing": timing_report})
        raise ValueError("; ".join(errors))
    write_srt(output, en_items)
    timing_report = _build_timing_report(source_items, en_items)
    write_json(
        report_path,
        {
            "passed": True,
            "errors": [],
            "warnings": warnings,
            "subtitle_count": len(en_items),
            "timing": timing_report,
        },
    )
    return {"en_checked_srt": output, "en_check_report": report_path}


def _wrap_line(line: str, limit: int) -> list[str]:
    words = line.split()
    if not words:
        return [line]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _looks_mojibake(text: str) -> bool:
    return "�" in text or "Ã" in text


def _build_timing_report(source_items, en_items) -> dict:
    source_start = source_items[0].start_ms if source_items else 0
    source_end = source_items[-1].end_ms if source_items else 0
    en_start = en_items[0].start_ms if en_items else 0
    en_end = en_items[-1].end_ms if en_items else 0
    source_total = sum(max(0, item.end_ms - item.start_ms) for item in source_items)
    en_total = sum(max(0, item.end_ms - item.start_ms) for item in en_items)
    return {
        "source_start_ms": source_start,
        "source_end_ms": source_end,
        "source_span_ms": max(0, source_end - source_start),
        "source_total_ms": source_total,
        "en_start_ms": en_start,
        "en_end_ms": en_end,
        "en_span_ms": max(0, en_end - en_start),
        "en_total_ms": en_total,
        "span_equal": source_start == en_start and source_end == en_end,
        "total_time_equal": source_total == en_total,
    }
