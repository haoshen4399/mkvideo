import json
from pathlib import Path
from typing import Any

from loguru import logger

from providers.openai_compatible_provider import build_provider
from utils.json_utils import write_json
from utils.srt_utils import format_srt, read_srt, strip_code_fence, validate_basic, write_srt


def check_zh_subtitles(context, config: dict[str, Any]) -> dict[str, Path]:
    step_config = config.get("steps", {}).get("zh_ai_check", {})
    source = context.zh_clean_srt_path
    output = context.zh_ai_checked_srt_path
    report_path = context.reports_dir / "zh_check_report.json"
    if output.exists() and not step_config.get("overwrite", False):
        return {"zh_ai_checked_srt": output, "zh_check_report": report_path}

    original_items = read_srt(source)
    fallback_report = {"passed": True, "error_count": 0, "errors": [], "fallback_used": False}
    if step_config.get("enabled", True):
        try:
            fixed_text, report = _call_zh_checker(source.read_text(encoding="utf-8"), step_config, config)
            fixed_items = read_srt(_write_temp_text(context.task_dir / "_zh_ai_check_tmp.srt", fixed_text))
            errors = validate_basic(fixed_items)
            if len(fixed_items) != len(original_items):
                errors.append("AI changed subtitle count")
            if errors:
                raise ValueError("; ".join(errors))
            write_srt(output, fixed_items)
            write_json(report_path, report)
            _remove_temp(context.task_dir / "_zh_ai_check_tmp.srt")
            return {"zh_ai_checked_srt": output, "zh_check_report": report_path}
        except Exception as exc:
            logger.warning("ZH AI check failed: {}", exc)
            if not step_config.get("continue_on_failure", True):
                raise
            fallback_report = {
                "passed": False,
                "error_count": 0,
                "errors": [],
                "fallback_used": True,
                "fallback_reason": str(exc),
            }
    output.write_text(format_srt(original_items), encoding="utf-8")
    write_json(report_path, fallback_report)
    return {"zh_ai_checked_srt": output, "zh_check_report": report_path}


def _call_zh_checker(srt_text: str, step_config: dict[str, Any], config: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    provider = build_provider(step_config.get("provider", "default"), config)
    prompt_template = Path(step_config.get("prompt_path", "prompts/zh_check.txt")).read_text(encoding="utf-8")
    response = provider.complete(prompt_template.replace("{{srt}}", srt_text), step_config.get("model"))
    cleaned = strip_code_fence(response)
    data = json.loads(cleaned)
    fixed = data.get("fixed_srt")
    if not fixed:
        raise ValueError("AI response does not contain fixed_srt")
    return fixed, data


def _write_temp_text(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _remove_temp(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
