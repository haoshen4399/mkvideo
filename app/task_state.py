from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from utils.json_utils import read_json, write_json


class TaskState:
    def __init__(self, path: Path, video: Path, steps: list[str]) -> None:
        self.path = path
        self.video = video
        self.steps = steps
        if path.exists():
            try:
                self.data = read_json(path)
            except Exception:
                backup = path.with_suffix(path.suffix + ".corrupt")
                try:
                    path.replace(backup)
                except OSError:
                    pass
                self.data = self._default_data()
                self.save()
        else:
            self.data = self._default_data()
            self.save()
        self._ensure_steps()

    def _default_data(self) -> dict[str, Any]:
        return {
            "video": str(self.video),
            "status": "pending",
            "last_success_step": None,
            "failed_step": None,
            "steps": {step: "pending" for step in self.steps},
            "artifacts": {},
            "errors": {},
            "config_hashes": {},
            "updated_at": None,
        }

    def _ensure_steps(self) -> None:
        changed = False
        self.data.setdefault("steps", {})
        for step in self.steps:
            if step not in self.data["steps"]:
                self.data["steps"][step] = "pending"
                changed = True
        for key in ("artifacts", "errors", "config_hashes"):
            if key not in self.data:
                self.data[key] = {}
                changed = True
        if changed:
            self.save()

    def save(self) -> None:
        self.data["updated_at"] = datetime.now().isoformat(timespec="seconds")
        write_json(self.path, self.data)

    def reset(self) -> None:
        self.data["status"] = "pending"
        self.data["last_success_step"] = None
        self.data["failed_step"] = None
        self.data["steps"] = {step: "pending" for step in self.steps}
        self.data["artifacts"] = {}
        self.data["errors"] = {}
        self.data["config_hashes"] = {}
        self.save()

    def step_status(self, step: str) -> str:
        return self.data["steps"].get(step, "pending")

    def step_statuses(self) -> dict[str, str]:
        return {step: self.step_status(step) for step in self.steps}

    def mark_running(self, step: str) -> None:
        self.data["status"] = "running"
        self.data["failed_step"] = None
        self.data["steps"][step] = "running"
        self.save()

    def mark_success(self, step: str, artifacts: dict[str, str] | None = None, config_hash: str | None = None) -> None:
        self.data["steps"][step] = "success"
        self.data["last_success_step"] = step
        self.data.setdefault("errors", {}).pop(step, None)
        if self.data.get("failed_step") == step:
            self.data["failed_step"] = None
        if artifacts:
            self.data["artifacts"][step] = artifacts
        if config_hash:
            self.data.setdefault("config_hashes", {})[step] = config_hash
        self.save()

    def step_config_hash(self, step: str) -> str | None:
        return self.data.get("config_hashes", {}).get(step)

    def mark_failed(self, step: str, error: Exception) -> None:
        self.data["status"] = "failed"
        self.data["failed_step"] = step
        self.data["steps"][step] = "failed"
        self.data["errors"][step] = str(error)
        self.save()

    def mark_done(self, status: str = "success") -> None:
        self.data["status"] = status
        self.data["failed_step"] = None
        if status == "success":
            self.data["errors"] = {}
        self.save()
