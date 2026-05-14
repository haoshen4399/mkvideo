from pathlib import Path
from typing import Any, Callable
import hashlib
import json

from loguru import logger

from app.context import TaskContext
from app.task_state import TaskState
from core.asr_engine import run_asr
from core.ass_builder import build_ass
from core.audio_extractor import extract_audio
from core.cover_title_generator import generate_cover_title
from core.cover_intro import prepend_cover_intro
from core.final_visual_qc import run_final_visual_qc
from core.position_analyzer import analyze_position
from core.subtitle_postprocessor import postprocess_zh_subtitles
from core.subtitle_layout_fitter import fit_subtitle_layout
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
        "cover_title",
        "screenshot_position",
        "build_ass",
        "render_video",
        "subtitle_layout_fit",
        "cover_intro",
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
        self.resume = resume or bool(config.get("app", {}).get("resume", False))
        self.start_from = start_from
        self.stop_after = stop_after
        self.only_steps = set(only_steps or [])
        self.overwrite_steps = set(overwrite_steps or [])
        app_config = config.get("app", {})
        self.rerun_on_config_change = bool(app_config.get("rerun_on_config_change", True))
        self.cascade_on_step_rerun = bool(app_config.get("cascade_on_step_rerun", True))
        self._upstream_reran = False
        self._forced_rerun_steps: dict[str, bool] = {}
        self._run_statuses: dict[str, str] = {step: "not_run" for step in self.STEP_ORDER}
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
            "cover_title": generate_cover_title,
            "screenshot_position": analyze_position,
            "build_ass": build_ass,
            "render_video": render_video,
            "subtitle_layout_fit": fit_subtitle_layout,
            "cover_intro": prepend_cover_intro,
            "final_visual_qc": run_final_visual_qc,
        }

    def run(self) -> None:
        if not self.resume and not self.start_from and not self.only_steps:
            self.state.reset()
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
                self._run_statuses[step] = "disabled"
                continue
            if self._should_skip(step):
                logger.info("Skip successful step: {}", step)
                self._run_statuses[step] = "skipped"
                continue
            if not self.resume:
                self._force_step_overwrite(step)
            self._run_step(step)
            if self.cascade_on_step_rerun:
                self._upstream_reran = True
            if self.stop_after and step == self.stop_after:
                logger.info("Stop after configured step: {}", step)
                break
        partial = bool(self.stop_after or self.only_steps)
        state_status = "partial" if partial else "success"
        if partial and all(self.state.step_status(step) == "success" for step in self.STEP_ORDER):
            state_status = "success"
        self.state.mark_done(state_status)
        if partial:
            logger.success("Pipeline partial run completed: {}", self.context.task_dir)
        else:
            logger.success("Pipeline completed: {}", self.context.final_video_path)
        self.log_step_summary()

    def step_statuses(self) -> dict[str, str]:
        return dict(self._run_statuses)

    def log_step_summary(self) -> None:
        logger.info("Step summary for video: {}", self.context.input_video.name)
        for step, status in self.step_statuses().items():
            logger.info("  {:<20} {}", step, _status_label(status))

    def _run_step(self, step: str) -> None:
        logger.info("Start step: {}", step)
        self._run_statuses[step] = "running"
        self.state.mark_running(step)
        try:
            artifacts = self.handlers[step](self.context, self.config)
        except Exception as exc:
            self._restore_forced_step_overwrite(step)
            logger.exception("Step failed: {}", step)
            self.state.mark_failed(step, exc)
            self._run_statuses[step] = "failed"
            raise
        self.state.mark_success(
            step,
            {key: str(value) for key, value in artifacts.items()},
            config_hash=self._step_config_hash(step),
        )
        self._restore_forced_step_overwrite(step)
        self._run_statuses[step] = "success"
        logger.success("Step completed: {}", step)

    def _should_skip(self, step: str) -> bool:
        if self.start_from:
            return False
        if not self.resume:
            return False
        step_config = self.config.get("steps", {}).get(step, {})
        if step_config.get("overwrite", False):
            return False
        if self._upstream_reran and self.cascade_on_step_rerun:
            logger.info("Rerun dependent step after upstream change: {}", step)
            self._force_step_overwrite(step)
            return False
        if self.rerun_on_config_change and self.state.step_config_hash(step) != self._step_config_hash(step):
            logger.info("Rerun step because config changed: {}", step)
            self._force_step_overwrite(step)
            return False
        return self.state.step_status(step) == "success"

    def _is_enabled(self, step: str) -> bool:
        return self.config.get("steps", {}).get(step, {}).get("enabled", True)

    def _force_step_overwrite(self, step: str) -> None:
        step_config = self.config.setdefault("steps", {}).setdefault(step, {})
        if step not in self._forced_rerun_steps:
            self._forced_rerun_steps[step] = bool(step_config.get("overwrite", False))
        step_config["overwrite"] = True

    def _restore_forced_step_overwrite(self, step: str) -> None:
        if step not in self._forced_rerun_steps:
            return
        self.config.setdefault("steps", {}).setdefault(step, {})["overwrite"] = self._forced_rerun_steps.pop(step)

    def _step_config_hash(self, step: str) -> str:
        payload = {
            "step": step,
            "step_config": self._functional_step_config(step),
            "provider_config": self._provider_config_for_step(step),
            "prompt_hash": self._prompt_hash_for_step(step),
            "pipeline_version": 2,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _provider_config_for_step(self, step: str) -> dict[str, Any] | None:
        step_config = self.config.get("steps", {}).get(step, {})
        provider_names = [step_config.get("provider"), step_config.get("fallback_provider")]
        providers = self.config.get("llm_providers", {})
        selected = {}
        for name in provider_names:
            if name and name in providers:
                selected[name] = self._redact_provider_config(providers[name])
        return selected or None

    def _functional_step_config(self, step: str) -> dict[str, Any]:
        step_config = dict(self.config.get("steps", {}).get(step, {}))
        step_config.pop("overwrite", None)
        return step_config

    def _prompt_hash_for_step(self, step: str) -> str | None:
        prompt_path = self.config.get("steps", {}).get(step, {}).get("prompt_path")
        if not prompt_path:
            return None
        path = Path(prompt_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _redact_provider_config(provider: dict[str, Any]) -> dict[str, Any]:
        redacted = dict(provider)
        if redacted.get("api_key"):
            redacted["api_key"] = "***REDACTED***"
        return redacted


def _status_label(status: str) -> str:
    labels = {
        "success": "OK",
        "failed": "FAILED",
        "running": "RUNNING",
        "pending": "PENDING",
        "not_run": "NOT_RUN",
        "skipped": "SKIPPED",
        "disabled": "DISABLED",
    }
    return labels.get(status, status.upper())
