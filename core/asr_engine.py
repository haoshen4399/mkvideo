from pathlib import Path
from typing import Any

from core.asr_quality import build_asr_quality_report
from engines.faster_whisper_engine import transcribe_with_faster_whisper
from engines.openai_whisper_engine import transcribe_with_openai_whisper
from engines.stable_ts_engine import transcribe_with_stable_ts
from engines.whisper_timestamped_engine import transcribe_with_whisper_timestamped
from utils.json_utils import read_json, write_json
from utils.srt_utils import read_srt


def run_asr(context, config: dict[str, Any]) -> dict[str, Path]:
    step_config = config.get("steps", {}).get("asr", {})
    output_path = context.zh_raw_srt_path
    if output_path.exists() and not step_config.get("overwrite", False):
        report_path = context.reports_dir / "asr_report.json"
        report = read_json(report_path) if report_path.exists() else {}
        report["quality"] = build_asr_quality_report(read_srt(output_path), step_config)
        write_json(report_path, report)
        return {"zh_raw_srt": output_path, "asr_report": report_path}
    report = {}
    try:
        report = _run_engine(step_config.get("engine", "faster-whisper"), context.original_audio_path, output_path, step_config)
    except Exception as first_error:
        fallback = step_config.get("fallback_engine")
        if fallback not in {"openai-whisper", "stable-ts", "whisper-timestamped"}:
            raise
        fallback_config = dict(step_config)
        fallback_config["model"] = step_config.get("fallback_model", "medium")
        fallback_config["engine"] = fallback
        try:
            report = _run_engine(fallback, context.original_audio_path, output_path, fallback_config)
            report["fallback_from_error"] = str(first_error)
        except Exception as fallback_error:
            raise RuntimeError(f"ASR failed. First: {first_error}; fallback: {fallback_error}") from fallback_error
    items = read_srt(output_path)
    quality = build_asr_quality_report(items, step_config)
    report["quality"] = quality
    if not quality.get("passed", True):
        quality_report = _try_quality_fallback(context, step_config, output_path, report, quality)
        if quality_report:
            report = quality_report
            quality = report["quality"]
    if not quality.get("passed", True) and step_config.get("fail_on_quality_error", False):
        raise ValueError(f"ASR quality check failed: {quality}")
    if step_config.get("diagnostic_enabled", True) and not quality.get("passed", True):
        report["diagnostic"] = _build_diagnostic_plan(report, step_config)
    write_json(context.reports_dir / "asr_report.json", report)
    return {"zh_raw_srt": output_path, "asr_report": context.reports_dir / "asr_report.json"}


def _run_engine(engine: str, audio_path: Path, output_path: Path, step_config: dict[str, Any]) -> dict[str, Any]:
    if engine == "faster-whisper":
        return transcribe_with_faster_whisper(audio_path, output_path, step_config)
    if engine == "openai-whisper":
        return transcribe_with_openai_whisper(audio_path, output_path, step_config)
    if engine == "stable-ts":
        return transcribe_with_stable_ts(audio_path, output_path, step_config)
    if engine == "whisper-timestamped":
        return transcribe_with_whisper_timestamped(audio_path, output_path, step_config)
    raise ValueError(f"Unsupported ASR engine: {engine}")


def _try_quality_fallback(
    context,
    step_config: dict[str, Any],
    output_path: Path,
    primary_report: dict[str, Any],
    primary_quality: dict[str, Any],
) -> dict[str, Any] | None:
    if not step_config.get("quality_fallback_enabled", True):
        return None
    fallback = step_config.get("quality_fallback_engine")
    if not fallback or fallback == primary_report.get("engine"):
        return None
    fallback_path = output_path.with_name(f"{output_path.stem}_{fallback.replace('-', '_')}.srt")
    fallback_config = dict(step_config)
    fallback_config["engine"] = fallback
    fallback_config["model"] = step_config.get("quality_fallback_model") or step_config.get("fallback_model") or step_config.get("model")
    try:
        fallback_report = _run_engine(fallback, context.original_audio_path, fallback_path, fallback_config)
    except Exception as exc:
        primary_report["quality_fallback_error"] = str(exc)
        return None
    fallback_quality = build_asr_quality_report(read_srt(fallback_path), fallback_config)
    fallback_report["quality"] = fallback_quality
    fallback_report["quality_fallback_from"] = {
        "engine": primary_report.get("engine"),
        "model": primary_report.get("model"),
        "quality": primary_quality,
    }
    if _quality_score(fallback_quality) < _quality_score(primary_quality):
        fallback_path.replace(output_path)
        return fallback_report
    primary_report["quality_fallback_rejected"] = {
        "engine": fallback_report.get("engine"),
        "model": fallback_report.get("model"),
        "quality": fallback_quality,
    }
    fallback_path.unlink(missing_ok=True)
    return None


def _quality_score(quality: dict[str, Any]) -> int:
    return (
        int(quality.get("large_gap_count", 0)) * 5
        + int(quality.get("long_item_count", 0)) * 4
        + int(quality.get("short_item_count", 0))
    )


def _build_diagnostic_plan(report: dict[str, Any], step_config: dict[str, Any]) -> dict[str, Any]:
    quality = report.get("quality", {})
    return {
        "enabled": True,
        "engine": step_config.get("diagnostic_engine", "whisper-timestamped"),
        "model": step_config.get("diagnostic_model", step_config.get("model")),
        "reason": "ASR quality report did not pass; use diagnostic engine on suspicious windows if manual review is needed.",
        "suspicious_windows": quality.get("large_gaps", []) + quality.get("long_items", []) + quality.get("short_items", []),
    }
