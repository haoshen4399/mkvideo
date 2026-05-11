from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from utils.time_utils import ms_to_srt_time, srt_time_to_ms

TIME_RE = re.compile(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})")


@dataclass
class SubtitleItem:
    index: int
    start_ms: int
    end_ms: int
    text: str

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


def parse_srt_text(text: str) -> list[SubtitleItem]:
    blocks = re.split(r"\n\s*\n", text.strip().replace("\r\n", "\n").replace("\r", "\n"))
    items: list[SubtitleItem] = []
    for block in blocks:
        lines = [line.rstrip() for line in block.split("\n") if line.strip()]
        if len(lines) < 3:
            continue
        try:
            index = int(lines[0].strip())
        except ValueError:
            index = len(items) + 1
        match = TIME_RE.match(lines[1].strip())
        if not match:
            continue
        items.append(
            SubtitleItem(
                index=index,
                start_ms=srt_time_to_ms(match.group(1)),
                end_ms=srt_time_to_ms(match.group(2)),
                text="\n".join(lines[2:]).strip(),
            )
        )
    return items


def read_srt(path: Path) -> list[SubtitleItem]:
    return parse_srt_text(path.read_text(encoding="utf-8-sig"))


def write_srt(path: Path, items: list[SubtitleItem]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_srt(items), encoding="utf-8")


def format_srt(items: list[SubtitleItem]) -> str:
    blocks = []
    for idx, item in enumerate(items, start=1):
        blocks.append(
            f"{idx}\n{ms_to_srt_time(item.start_ms)} --> {ms_to_srt_time(item.end_ms)}\n{item.text.strip()}"
        )
    return "\n\n".join(blocks) + "\n"


def validate_basic(items: list[SubtitleItem]) -> list[str]:
    errors: list[str] = []
    previous_end = -1
    for expected, item in enumerate(items, start=1):
        if item.index != expected:
            errors.append(f"index {item.index} should be {expected}")
        if not item.text.strip():
            errors.append(f"index {expected} has empty text")
        if item.start_ms >= item.end_ms:
            errors.append(f"index {expected} start time is not before end time")
        if item.start_ms < previous_end:
            errors.append(f"index {expected} overlaps previous subtitle")
        previous_end = item.end_ms
    if not items:
        errors.append("subtitle file has no valid items")
    return errors


def strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:\w+)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()
