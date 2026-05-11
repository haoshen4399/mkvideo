from pathlib import Path
from typing import Any, Callable

from loguru import logger

from app.context import TaskContext
from app.task_state import TaskState
from core.asr_engine import run_asr
from core.ass_builder import build_ass
from core.audio_extractor import extract_audio
from core.final_visual_qc import run_final_visual_qc
from core.position_analyzer import analyze_position
from core.subtitle_postprocessor import postprocess_zh_subtitles
from core.subtitle_validator import validate_english_subtitles
from core.translator import translate_subtitles
from core.video_probe import probe_video
from core.video_renderer import render_video
from core.zh_ai_checker import check_zh_subtitles


class Pipeline:
    STEP_ORDER = [
        "probe_video",
        "extract_audio",
        "asr",
        "zh_postprocess",
        "zh_ai_check",
        "translate",
        "en_check",
        "screenshot_position",
        "build_ass",
        "render_video",
        "final_visual_qc",
    ]

    def __init__(
        self,
        config: dict[str, Any],
        context: TaskContext,
        resume: bool = False,
        start_from: str | None = None,
        stop_after: str | None = None,
        only_steps: list[str] | None = None,
        overwrite_steps: list[str] | None = None,
    ) -> None:
        self.config = config
        self.context = context
        self.resume = resume or bool(config.get("app", {}).get("resume", True))
        self.start_from = start_from
        self.stop_after = stop_after
        self.only_steps = set(only_steps or [])
        self.overwrite_steps = set(overwrite_steps or [])
        for step in self.overwrite_steps:
            self.config.setdefault("steps", {}).setdefault(step, {})["overwrite"] = True
        self.state = TaskState(context.task_state_path, context.input_video, self.STEP_ORDER)
        self.handlers: dict[str, Callable[[TaskContext, dict[str, Any]], dict[str, Path]]] = {
            "probe_video": probe_video,
            "extract_audio": extract_audio,
            "asr": run_asr,
            "zh_postprocess": postprocess_zh_subtitles,
            "zh_ai_check": check_zh_subtitles,
            "translate": translate_subtitles,
            "en_check": validate_english_subtitles,
            "screenshot_position": analyze_position,
            "build_ass": build_ass,
            "render_video": render_video,
            "final_visual_qc": run_final_visual_qc,
        }

    def run(self) -> None:
        started = self.start_from is None
        logger.info("Task directory: {}", self.context.task_dir)
        for step in self.STEP_ORDER:
            if self.start_from and step == self.start_from:
                started = True
            if not started:
                continue
            if self.only_steps and step not in self.only_steps:
                continue
            if not self._is_enabled(step):
                logger.info("Skip disabled step: {}", step)
                continue
            if self._should_skip(step):
                logger.info("Skip successful step: {}", step)
                continue
            self._run_step(step)
            if self.stop_after and step == self.stop_after:
                logger.info("Stop after configured step: {}", step)
                break
        partial = bool(self.stop_after or self.only_steps)
        self.state.mark_done("partial" if partial else "success")
        if partial:
            logger.success("Pipeline partial run completed: {}", self.context.task_dir)
        else:
            logger.success("Pipeline completed: {}", self.context.final_video_path)

    def _run_step(self, step: str) -> None:
        logger.info("Start step: {}", step)
        self.state.mark_running(step)
        try:
            artifacts = self.handlers[step](self.context, self.config)
        except Exception as exc:
            logger.exception("Step failed: {}", step)
            self.state.mark_failed(step, exc)
            raise
        self.state.mark_success(step, {key: str(value) for key, value in artifacts.items()})
        logger.success("Step completed: {}", step)

    def _should_skip(self, step: str) -> bool:
        if self.start_from:
            return False
        if not self.resume:
            return False
        step_config = self.config.get("steps", {}).get(step, {})
        if step_config.get("overwrite", False):
            return False
        return self.state.step_status(step) == "success"

    def _is_enabled(self, step: str) -> bool:
        return self.config.get("steps", {}).get(step, {}).get("enabled", True)
