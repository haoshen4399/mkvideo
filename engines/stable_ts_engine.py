from pathlib import Path
from time import perf_counter
from typing import Any

from engines.whisper_dtw_patch import force_python_dtw
from utils.srt_utils import SubtitleItem, read_srt, write_srt


def transcribe_with_stable_ts(audio_path: Path, output_srt: Path, config: dict[str, Any]) -> dict[str, Any]:
    try:
        import stable_whisper
    except ImportError as exc:
        raise RuntimeError("stable-ts is not installed. Install it with: pip install stable-ts") from exc

    python_dtw_enabled = False
    if bool(config.get("force_python_dtw", True)):
        python_dtw_enabled = force_python_dtw()

    started = perf_counter()
    model_name = config.get("model") or config.get("fallback_model", "large-v3")
    download_root = Path(config.get("download_root", "models/whisper")).resolve()
    download_root.mkdir(parents=True, exist_ok=True)
    model = stable_whisper.load_model(
        model_name,
        device=config.get("device", "cpu"),
        download_root=str(download_root),
    )
    result = model.transcribe(
        str(audio_path),
        language=config.get("language", "zh"),
        temperature=tuple(config.get("temperature", [0.0])),
        compression_ratio_threshold=float(config.get("compression_ratio_threshold", 2.4)),
        logprob_threshold=float(config.get("logprob_threshold", -0.75)),
        no_speech_threshold=float(config.get("no_speech_threshold", 0.6)),
        condition_on_previous_text=bool(config.get("condition_on_previous_text", False)),
        fp16=bool(config.get("fp16", False)),
        beam_size=int(config.get("beam_size", 5)),
        best_of=int(config.get("best_of", 5)),
    )
    _write_stable_result_srt(result, output_srt)
    items = read_srt(output_srt)
    return {
        "engine": "stable-ts",
        "model": model_name,
        "download_root": str(download_root),
        "language": config.get("language", "zh"),
        "duration_seconds": round(perf_counter() - started, 3),
        "subtitle_count": len(items),
        "stabilized_timestamps": True,
        "python_dtw_enabled": python_dtw_enabled,
        "condition_on_previous_text": bool(config.get("condition_on_previous_text", False)),
        "no_speech_threshold": float(config.get("no_speech_threshold", 0.6)),
        "logprob_threshold": float(config.get("logprob_threshold", -0.75)),
    }


def _write_stable_result_srt(result: Any, output_srt: Path) -> None:
    output_srt.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(result, "to_srt_vtt"):
        result.to_srt_vtt(str(output_srt), word_level=False)
        return
    segments = getattr(result, "segments", None) or []
    items: list[SubtitleItem] = []
    for index, segment in enumerate(segments, start=1):
        start = getattr(segment, "start", None)
        end = getattr(segment, "end", None)
        text = getattr(segment, "text", "")
        if start is None or end is None or not str(text).strip():
            continue
        items.append(
            SubtitleItem(
                index=len(items) + 1,
                start_ms=int(float(start) * 1000),
                end_ms=int(float(end) * 1000),
                text=str(text).strip(),
            )
        )
    write_srt(output_srt, items)
