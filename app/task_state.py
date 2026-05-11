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
            self.data = read_json(path)
        else:
            self.data = {
                "video": str(video),
                "status": "pending",
                "last_success_step": None,
                "failed_step": None,
                "steps": {step: "pending" for step in steps},
                "artifacts": {},
                "errors": {},
                "updated_at": None,
            }
            self.save()

    def save(self) -> None:
        self.data["updated_at"] = datetime.now().isoformat(timespec="seconds")
        write_json(self.path, self.data)

    def step_status(self, step: str) -> str:
        return self.data["steps"].get(step, "pending")

    def mark_running(self, step: str) -> None:
        self.data["status"] = "running"
        self.data["failed_step"] = None
        self.data["steps"][step] = "running"
        self.save()

    def mark_success(self, step: str, artifacts: dict[str, str] | None = None) -> None:
        self.data["steps"][step] = "success"
        self.data["last_success_step"] = step
        if artifacts:
            self.data["artifacts"][step] = artifacts
        self.save()

    def mark_failed(self, step: str, error: Exception) -> None:
        self.data["status"] = "failed"
        self.data["failed_step"] = step
        self.data["steps"][step] = "failed"
        self.data["errors"][step] = str(error)
        self.save()

    def mark_done(self, status: str = "success") -> None:
        self.data["status"] = status
        self.data["failed_step"] = None
        self.save()
