from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config_loader import write_config_snapshot


@dataclass(frozen=True)
class TaskContext:
    input_video: Path
    output_root: Path
    task_dir: Path
    audio_dir: Path
    subtitles_dir: Path
    reports_dir: Path
    logs_dir: Path
    position_dir: Path
    screenshots_dir: Path
    final_qc_dir: Path
    final_qc_screenshots_dir: Path
    render_dir: Path
    cover_dir: Path
    video_info_path: Path
    original_audio_path: Path
    zh_raw_srt_path: Path
    zh_clean_srt_path: Path
    zh_ai_checked_srt_path: Path
    en_raw_srt_path: Path
    en_checked_srt_path: Path
    subtitle_position_path: Path
    english_ass_path: Path
    bilingual_ass_path: Path
    final_video_path: Path
    task_state_path: Path
    config_snapshot_path: Path

    @classmethod
    def create(cls, input_video: Path, output_root: Path, config: dict[str, Any]) -> "TaskContext":
        input_video = input_video.expanduser().resolve()
        output_root = output_root.expanduser().resolve()
        task_name = input_video.stem
        task_dir = output_root / task_name
        audio_dir = task_dir / "audio"
        subtitles_dir = task_dir / "subtitles"
        reports_dir = task_dir / "reports"
        logs_dir = task_dir / "logs"
        position_dir = task_dir / "position"
        screenshots_dir = position_dir / "screenshots"
        final_qc_dir = task_dir / "final_qc"
        final_qc_screenshots_dir = final_qc_dir / "screenshots"
        render_dir = task_dir / "render"
        cover_dir = task_dir / "cover"
        for directory in [
            audio_dir,
            subtitles_dir,
            reports_dir,
            logs_dir,
            screenshots_dir,
            final_qc_screenshots_dir,
            render_dir,
            cover_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)
        context = cls(
            input_video=input_video,
            output_root=output_root,
            task_dir=task_dir,
            audio_dir=audio_dir,
            subtitles_dir=subtitles_dir,
            reports_dir=reports_dir,
            logs_dir=logs_dir,
            position_dir=position_dir,
            screenshots_dir=screenshots_dir,
            final_qc_dir=final_qc_dir,
            final_qc_screenshots_dir=final_qc_screenshots_dir,
            render_dir=render_dir,
            cover_dir=cover_dir,
            video_info_path=reports_dir / "video_info.json",
            original_audio_path=audio_dir / "original.wav",
            zh_raw_srt_path=subtitles_dir / "zh_raw.srt",
            zh_clean_srt_path=subtitles_dir / "zh_clean.srt",
            zh_ai_checked_srt_path=subtitles_dir / "zh_ai_checked.srt",
            en_raw_srt_path=subtitles_dir / "en_raw.srt",
            en_checked_srt_path=subtitles_dir / "en_checked.srt",
            subtitle_position_path=position_dir / "subtitle_position.json",
            english_ass_path=subtitles_dir / "english.ass",
            bilingual_ass_path=subtitles_dir / "bilingual.ass",
            final_video_path=render_dir / "final_en_subtitled.mp4",
            task_state_path=task_dir / "task_state.json",
            config_snapshot_path=task_dir / "task_config_snapshot.yaml",
        )
        write_config_snapshot(config, context.config_snapshot_path)
        return context
