import re
from pathlib import Path
from typing import Any

from loguru import logger

from providers.openai_compatible_provider import build_provider
from utils.json_utils import write_json
from utils.srt_utils import SubtitleItem, format_srt, parse_srt_text, read_srt, strip_code_fence, validate_basic, write_srt


def translate_subtitles(context, config: dict[str, Any]) -> dict[str, Path]:
    step_config = config.get("steps", {}).get("translate", {})
    source = context.zh_ai_checked_srt_path if context.zh_ai_checked_srt_path.exists() else context.zh_clean_srt_path
    output = context.en_raw_srt_path
    report_path = context.reports_dir / "translation_report.json"
    if output.exists() and not step_config.get("overwrite", False):
        return {"en_raw_srt": output, "translation_report": report_path}
    source_items = read_srt(source)
    try:
        provider = build_provider(step_config.get("provider", "default"), config)
        prompt_template = Path(step_config.get("prompt_path", "prompts/translate_en.txt")).read_text(encoding="utf-8")
        model = step_config.get("model")
        response = provider.complete(prompt_template.replace("{{srt}}", source.read_text(encoding="utf-8")), model)
        items = _parse_translated_srt(response)
        repair_report = {"whole_response_count": len(items), "chunk_retry_used": False, "single_item_repairs": 0}
        if len(items) != len(source_items):
            logger.warning(
                "Translated subtitle count differs from source: translated={}, source={}. Retrying in chunks.",
                len(items),
                len(source_items),
            )
            repair_report["chunk_retry_used"] = True
            items, chunk_repairs = _translate_in_chunks(provider, prompt_template, source_items, step_config, model)
            repair_report["single_item_repairs"] += chunk_repairs
        items = _align_to_source(source_items, items)
        bad_indexes = _bad_translation_indexes(items)
        if bad_indexes:
            logger.warning("Repairing {} translated subtitle(s) with invalid/unfinished text.", len(bad_indexes))
            repair_report["single_item_repairs"] += len(bad_indexes)
            items = _repair_bad_items(provider, source_items, items, bad_indexes, model)
        errors = []
        errors.extend(validate_basic(items))
        errors.extend(_translation_quality_errors(items))
        if errors:
            raise ValueError("; ".join(errors))
        write_srt(output, items)
        report = {
            "passed": True,
            "source": str(source),
            "subtitle_count": len(items),
            "source_subtitle_count": len(source_items),
            "strategy": step_config.get("strategy", "understand_full_context_first"),
            "whole_context_understanding_required": True,
            "repair": repair_report,
        }
    except Exception as exc:
        logger.warning("Translation failed: {}", exc)
        if not step_config.get("allow_placeholder_on_failure", False):
            raise
        items = [
            type(item)(index=item.index, start_ms=item.start_ms, end_ms=item.end_ms, text="[Translation unavailable]")
            for item in source_items
        ]
        write_srt(output, items)
        report = {
            "passed": False,
            "fallback_used": True,
            "error": str(exc),
            "subtitle_count": len(items),
            "strategy": step_config.get("strategy", "understand_full_context_first"),
            "whole_context_understanding_required": True,
        }
    write_json(report_path, report)
    return {"en_raw_srt": output, "translation_report": report_path}


def _parse_translated_srt(response: str) -> list[SubtitleItem]:
    return parse_srt_text(strip_code_fence(response))


def _translate_in_chunks(
    provider,
    prompt_template: str,
    source_items: list[SubtitleItem],
    step_config: dict[str, Any],
    model: str | None,
) -> tuple[list[SubtitleItem], int]:
    chunk_size = max(1, int(step_config.get("chunk_size", 20)))
    translated: list[SubtitleItem] = []
    single_item_repairs = 0
    for start in range(0, len(source_items), chunk_size):
        chunk = source_items[start : start + chunk_size]
        response = provider.complete(prompt_template.replace("{{srt}}", format_srt(chunk)), model)
        chunk_items = _parse_translated_srt(response)
        if len(chunk_items) != len(chunk):
            logger.warning(
                "Chunk translation count mismatch at source index {}-{}: translated={}, source={}. Retrying strict chunk.",
                chunk[0].index,
                chunk[-1].index,
                len(chunk_items),
                len(chunk),
            )
            chunk_items, repaired_count = _translate_strict_chunk(provider, chunk, model)
            single_item_repairs += repaired_count
        translated.extend(_align_to_source(chunk, chunk_items))
    return translated, single_item_repairs


def _translate_strict_chunk(provider, source_items: list[SubtitleItem], model: str | None) -> tuple[list[SubtitleItem], int]:
    prompt = (
        "Translate the following Chinese SRT into natural American English subtitles.\n"
        "Return ONLY valid SRT.\n"
        "Keep exactly the same subtitle indexes, timestamps, and number of blocks.\n"
        "Do not merge, split, omit, or add any subtitle block.\n\n"
        f"{format_srt(source_items)}"
    )
    items = _parse_translated_srt(provider.complete(prompt, model))
    if len(items) == len(source_items):
        return items, 0

    by_index = {item.index: item for item in items}
    repaired: list[SubtitleItem] = []
    repaired_count = 0
    for source_item in source_items:
        item = by_index.get(source_item.index)
        if item is None:
            item = _translate_single_item(provider, source_item, model)
            repaired_count += 1
        repaired.append(item)
    return repaired, repaired_count


def _translate_single_item(provider, source_item: SubtitleItem, model: str | None) -> SubtitleItem:
    prompt = (
        "Translate this Chinese subtitle into concise natural American English.\n"
        "Return only the English text. Do not include numbering, timestamps, Markdown, or explanations.\n\n"
        f"{source_item.text}"
    )
    text = strip_code_fence(provider.complete(prompt, model)).strip()
    text = " ".join(line.strip() for line in text.splitlines() if line.strip())
    if not text:
        raise ValueError(f"Empty translation for subtitle index {source_item.index}")
    return SubtitleItem(
        index=source_item.index,
        start_ms=source_item.start_ms,
        end_ms=source_item.end_ms,
        text=text,
    )


def _align_to_source(source_items: list[SubtitleItem], translated_items: list[SubtitleItem]) -> list[SubtitleItem]:
    by_index = {item.index: item for item in translated_items}
    aligned: list[SubtitleItem] = []
    for offset, source_item in enumerate(source_items):
        item = by_index.get(source_item.index)
        if item is None and offset < len(translated_items):
            item = translated_items[offset]
        if item is None:
            raise ValueError(f"Missing translation for subtitle index {source_item.index}")
        text = item.text
        aligned.append(
            SubtitleItem(
                index=source_item.index,
                start_ms=source_item.start_ms,
                end_ms=source_item.end_ms,
                text=text.strip(),
            )
        )
    return aligned


def _bad_translation_indexes(items: list[SubtitleItem]) -> list[int]:
    bad = []
    for item in items:
        text = item.text.strip()
        if not text or "[Translation unavailable]" in text or _contains_cjk(text):
            bad.append(item.index)
    return bad


def _repair_bad_items(
    provider,
    source_items: list[SubtitleItem],
    translated_items: list[SubtitleItem],
    bad_indexes: list[int],
    model: str | None,
) -> list[SubtitleItem]:
    by_index = {item.index: item for item in translated_items}
    source_by_index = {item.index: item for item in source_items}
    for index in bad_indexes:
        source_item = source_by_index.get(index)
        if source_item is None:
            continue
        by_index[index] = _translate_single_item(provider, source_item, model)
    return _align_to_source(source_items, [by_index[item.index] for item in source_items if item.index in by_index])


def _translation_quality_errors(items: list[SubtitleItem]) -> list[str]:
    errors = []
    for item in items:
        text = item.text.strip()
        if not text:
            errors.append(f"index {item.index} has empty translation")
        if "[Translation unavailable]" in text:
            errors.append(f"index {item.index} uses placeholder translation")
        if _contains_cjk(text):
            errors.append(f"index {item.index} still contains Chinese text")
    return errors


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))
