from typing import Any

from utils.srt_utils import SubtitleItem


def build_asr_quality_report(items: list[SubtitleItem], config: dict[str, Any]) -> dict[str, Any]:
    max_gap_ms = int(config.get("quality_max_gap_ms", 9000))
    min_duration_ms = int(config.get("quality_min_duration_ms", 250))
    max_duration_ms = int(config.get("quality_max_duration_ms", 9000))
    gaps = []
    short_items = []
    long_items = []
    previous = None
    for item in items:
        if previous and item.start_ms - previous.end_ms > max_gap_ms:
            gaps.append(
                {
                    "after_index": previous.index,
                    "before_index": item.index,
                    "start_ms": previous.end_ms,
                    "end_ms": item.start_ms,
                    "gap_ms": item.start_ms - previous.end_ms,
                }
            )
        if item.duration_ms < min_duration_ms:
            short_items.append({"index": item.index, "duration_ms": item.duration_ms, "text": item.text})
        if item.duration_ms > max_duration_ms:
            long_items.append({"index": item.index, "duration_ms": item.duration_ms, "text": item.text})
        previous = item
    return {
        "first_start_ms": items[0].start_ms if items else None,
        "last_end_ms": items[-1].end_ms if items else None,
        "subtitle_count": len(items),
        "max_allowed_gap_ms": max_gap_ms,
        "large_gaps": gaps[:50],
        "large_gap_count": len(gaps),
        "short_item_count": len(short_items),
        "long_item_count": len(long_items),
        "short_items": short_items[:20],
        "long_items": long_items[:20],
        "passed": not gaps and not long_items,
    }
