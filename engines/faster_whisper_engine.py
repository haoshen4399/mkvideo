from pathlib import Path
from time import perf_counter
from typing import Any

from loguru import logger

from utils.srt_utils import SubtitleItem, write_srt


def transcribe_with_faster_whisper(audio_path: Path, output_srt: Path, config: dict[str, Any]) -> dict[str, Any]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("faster-whisper is not installed.") from exc

    started = perf_counter()
    model = WhisperModel(
        config.get("model", "medium"),
        device=_auto_value(config.get("device", "auto")),
        compute_type=_auto_value(config.get("compute_type", "auto")),
        download_root=config.get("faster_download_root"),
    )
    clip_timestamps = None
    vad_engine = config.get("vad_engine", "silero")
    if config.get("vad_filter", True) and vad_engine == "silero":
        speech_chunks, sample_rate = _silero_speech_chunks(audio_path, config)
        clip_timestamps = _chunks_to_clip_timestamps(speech_chunks, sample_rate, float(config.get("vad_merge_gap_seconds", 4.0)))
        if not clip_timestamps and config.get("strict_vad", True):
            raise RuntimeError("Silero VAD found no speech chunks.")

    transcribe_options = {
        "language": config.get("language", "zh"),
        "beam_size": int(config.get("beam_size", 5)),
        "condition_on_previous_text": bool(config.get("condition_on_previous_text", False)),
        "vad_filter": bool(config.get("vad_filter", True)) and vad_engine == "faster_whisper",
        "word_timestamps": bool(config.get("word_timestamps", True)),
        "no_speech_threshold": float(config.get("no_speech_threshold", 0.6)),
        "log_prob_threshold": float(config.get("logprob_threshold", -0.75)),
        "hallucination_silence_threshold": float(config.get("hallucination_silence_threshold", 1.0)),
    }
    if clip_timestamps:
        transcribe_options["clip_timestamps"] = clip_timestamps
    if transcribe_options["vad_filter"]:
        transcribe_options["vad_parameters"] = {
            "min_silence_duration_ms": int(config.get("vad_min_silence_duration_ms", 300)),
            "speech_pad_ms": int(config.get("vad_speech_pad_ms", 120)),
        }
    try:
        segments, info = model.transcribe(str(audio_path), **transcribe_options)
    except RuntimeError as exc:
        if not transcribe_options["vad_filter"] or "VAD" not in str(exc):
            raise
        if config.get("strict_vad", True):
            raise RuntimeError(f"faster-whisper VAD required but unavailable: {exc}") from exc
        logger.warning("faster-whisper VAD unavailable, retrying without VAD: {}", exc)
        transcribe_options.pop("vad_parameters", None)
        transcribe_options["vad_filter"] = False
        segments, info = model.transcribe(str(audio_path), **transcribe_options)
    items = [
        SubtitleItem(index=i, start_ms=int(segment.start * 1000), end_ms=int(segment.end * 1000), text=segment.text.strip())
        for i, segment in enumerate(segments, start=1)
        if segment.text.strip()
    ]
    write_srt(output_srt, items)
    return {
        "engine": "faster-whisper",
        "model": config.get("model", "medium"),
        "language": getattr(info, "language", config.get("language", "zh")),
        "duration_seconds": round(perf_counter() - started, 3),
        "subtitle_count": len(items),
        "vad_filter_requested": bool(config.get("vad_filter", True)),
        "vad_filter_used": bool(transcribe_options.get("vad_filter", False) or clip_timestamps),
        "vad_engine": vad_engine if config.get("vad_filter", True) else None,
        "speech_chunk_count": len(clip_timestamps) // 2 if clip_timestamps else None,
        "first_speech_start_ms": int(clip_timestamps[0] * 1000) if clip_timestamps else None,
    }


def _auto_value(value: str) -> str:
    if value == "auto":
        return "auto"
    return value


def _silero_speech_chunks(audio_path: Path, config: dict[str, Any]) -> tuple[list[dict[str, int]], int]:
    try:
        import soundfile as sf
        import torch
        from silero_vad import get_speech_timestamps, load_silero_vad
    except ImportError as exc:
        raise RuntimeError("Silero VAD dependencies are not installed.") from exc

    audio, sample_rate = sf.read(str(audio_path), dtype="float32")
    if getattr(audio, "ndim", 1) > 1:
        audio = audio[:, 0]
    wav = torch.from_numpy(audio)
    model = load_silero_vad(onnx=False)
    chunks = get_speech_timestamps(
        wav,
        model,
        sampling_rate=sample_rate,
        min_silence_duration_ms=int(config.get("vad_min_silence_duration_ms", 300)),
        speech_pad_ms=int(config.get("vad_speech_pad_ms", 120)),
        threshold=float(config.get("vad_threshold", 0.5)),
    )
    return chunks, int(sample_rate)


def _chunks_to_clip_timestamps(chunks: list[dict[str, int]], sample_rate: int = 16000, max_gap_seconds: float = 4.0) -> list[float]:
    chunks = _merge_speech_chunks(chunks, sample_rate, max_gap_seconds)
    timestamps: list[float] = []
    for chunk in chunks:
        timestamps.extend([round(chunk["start"] / sample_rate, 3), round(chunk["end"] / sample_rate, 3)])
    return timestamps


def _merge_speech_chunks(chunks: list[dict[str, int]], sample_rate: int, max_gap_seconds: float) -> list[dict[str, int]]:
    if not chunks:
        return []
    # Whisper benefits from complete dialogue turns. Silero can miss short low-energy phrases
    # inside a turn, so bridge moderate gaps after the first speech has been found.
    merged = [dict(chunks[0])]
    for chunk in chunks[1:]:
        gap_seconds = (chunk["start"] - merged[-1]["end"]) / sample_rate
        if gap_seconds <= max_gap_seconds:
            merged[-1]["end"] = chunk["end"]
        else:
            merged.append(dict(chunk))
    return merged
