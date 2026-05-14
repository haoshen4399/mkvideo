from pathlib import Path
from time import perf_counter
from typing import Any

from engines.whisper_dtw_patch import force_python_dtw
from utils.srt_utils import SubtitleItem, write_srt


def transcribe_with_whisper_timestamped(audio_path: Path, output_srt: Path, config: dict[str, Any]) -> dict[str, Any]:
    try:
        import whisper_timestamped as whisper
    except ImportError as exc:
        raise RuntimeError(
            "whisper-timestamped is not installed. Install it with: pip install whisper-timestamped"
        ) from exc

    python_dtw_enabled = False
    if bool(config.get("force_python_dtw", True)):
        python_dtw_enabled = force_python_dtw()

    started = perf_counter()
    model_name = config.get("model") or config.get("fallback_model", "large-v3")
    download_root = Path(config.get("download_root", "models/whisper")).resolve()
    download_root.mkdir(parents=True, exist_ok=True)
    model = whisper.load_model(
        model_name,
        device=config.get("device", "cpu"),
        download_root=str(download_root),
    )
    result = whisper.transcribe(
        model,
        str(audio_path),
        language=config.get("language", "zh"),
        beam_size=int(config.get("beam_size", 5)),
        best_of=int(config.get("best_of", 5)),
        temperature=tuple(config.get("temperature", [0.0])),
        vad=bool(config.get("timestamped_vad", False)),
        condition_on_previous_text=bool(config.get("condition_on_previous_text", False)),
        fp16=bool(config.get("fp16", False)),
    )
    segments = result.get("segments", [])
    items: list[SubtitleItem] = []
    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        items.append(
            SubtitleItem(
                index=len(items) + 1,
                start_ms=int(float(segment["start"]) * 1000),
                end_ms=int(float(segment["end"]) * 1000),
                text=text,
            )
        )
    write_srt(output_srt, items)
    confidence_values = [
        float(word["confidence"])
        for segment in segments
        for word in segment.get("words", [])
        if word.get("confidence") is not None
    ]
    average_confidence = sum(confidence_values) / len(confidence_values) if confidence_values else None
    return {
        "engine": "whisper-timestamped",
        "model": model_name,
        "download_root": str(download_root),
        "language": result.get("language", config.get("language", "zh")),
        "duration_seconds": round(perf_counter() - started, 3),
        "subtitle_count": len(items),
        "word_timestamps": True,
        "dtw_alignment": True,
        "python_dtw_enabled": python_dtw_enabled,
        "word_confidence_count": len(confidence_values),
        "average_word_confidence": round(average_confidence, 4) if average_confidence is not None else None,
    }
