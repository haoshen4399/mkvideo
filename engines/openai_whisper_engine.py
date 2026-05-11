from pathlib import Path
from time import perf_counter
from typing import Any

from utils.srt_utils import SubtitleItem, write_srt


def transcribe_with_openai_whisper(audio_path: Path, output_srt: Path, config: dict[str, Any]) -> dict[str, Any]:
    try:
        import whisper
    except ImportError as exc:
        raise RuntimeError("openai-whisper is not installed.") from exc

    started = perf_counter()
    model_name = config.get("model") or config.get("fallback_model", "large-v3")
    download_root = Path(config.get("download_root", "models/whisper"))
    download_root.mkdir(parents=True, exist_ok=True)
    model = whisper.load_model(model_name, download_root=str(download_root))
    result = model.transcribe(
        str(audio_path),
        language=config.get("language", "zh"),
        verbose=False,
        temperature=tuple(config.get("temperature", [0.0])),
        compression_ratio_threshold=float(config.get("compression_ratio_threshold", 2.4)),
        logprob_threshold=float(config.get("logprob_threshold", -0.75)),
        no_speech_threshold=float(config.get("no_speech_threshold", 0.6)),
        condition_on_previous_text=bool(config.get("condition_on_previous_text", False)),
        word_timestamps=bool(config.get("word_timestamps", True)),
        hallucination_silence_threshold=float(config.get("hallucination_silence_threshold", 1.0)),
        fp16=bool(config.get("fp16", False)),
        beam_size=int(config.get("beam_size", 5)),
        best_of=int(config.get("best_of", 5)),
    )
    segments = result.get("segments", [])
    items = [
        SubtitleItem(index=i, start_ms=int(seg["start"] * 1000), end_ms=int(seg["end"] * 1000), text=seg["text"].strip())
        for i, seg in enumerate(segments, start=1)
        if seg.get("text", "").strip()
    ]
    low_confidence_segments = [
        {
            "index": i,
            "start": round(float(seg.get("start", 0)), 3),
            "end": round(float(seg.get("end", 0)), 3),
            "avg_logprob": seg.get("avg_logprob"),
            "no_speech_prob": seg.get("no_speech_prob"),
            "text": seg.get("text", "").strip(),
        }
        for i, seg in enumerate(segments, start=1)
        if seg.get("text", "").strip()
        and (
            float(seg.get("avg_logprob") or 0) < float(config.get("quality_min_avg_logprob", -1.0))
            or float(seg.get("no_speech_prob") or 0) > float(config.get("quality_max_no_speech_prob", 0.85))
        )
    ]
    write_srt(output_srt, items)
    return {
        "engine": "openai-whisper",
        "model": model_name,
        "download_root": str(download_root),
        "language": result.get("language", config.get("language", "zh")),
        "duration_seconds": round(perf_counter() - started, 3),
        "subtitle_count": len(items),
        "condition_on_previous_text": bool(config.get("condition_on_previous_text", False)),
        "word_timestamps": bool(config.get("word_timestamps", True)),
        "no_speech_threshold": float(config.get("no_speech_threshold", 0.6)),
        "logprob_threshold": float(config.get("logprob_threshold", -0.75)),
        "hallucination_silence_threshold": float(config.get("hallucination_silence_threshold", 1.0)),
        "low_confidence_segment_count": len(low_confidence_segments),
        "low_confidence_segments": low_confidence_segments[:30],
    }
