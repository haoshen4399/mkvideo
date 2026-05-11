from pathlib import Path
from typing import Any

from loguru import logger

from providers.openai_compatible_provider import build_provider
from utils.json_utils import write_json
from utils.srt_utils import read_srt, strip_code_fence, validate_basic, write_srt


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
        response = provider.complete(prompt_template.replace("{{srt}}", source.read_text(encoding="utf-8")), step_config.get("model"))
        translated_text = strip_code_fence(response)
        temp_path = context.task_dir / "_en_translate_tmp.srt"
        temp_path.write_text(translated_text, encoding="utf-8")
        items = read_srt(temp_path)
        temp_path.unlink(missing_ok=True)
        if len(items) != len(source_items):
            errors = ["Translated subtitle count differs from source"]
        else:
            errors = []
        for source_item, item in zip(source_items, items):
            item.start_ms = source_item.start_ms
            item.end_ms = source_item.end_ms
        errors.extend(validate_basic(items))
        if errors:
            raise ValueError("; ".join(errors))
        write_srt(output, items)
        report = {
            "passed": True,
            "source": str(source),
            "subtitle_count": len(items),
            "strategy": step_config.get("strategy", "understand_full_context_first"),
            "whole_context_understanding_required": True,
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
