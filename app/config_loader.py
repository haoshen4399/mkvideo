from pathlib import Path
from typing import Any

import yaml
from copy import deepcopy


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if "app" not in data or "steps" not in data:
        raise ValueError("Config must contain 'app' and 'steps' sections.")
    return data


def write_config_snapshot(config: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = _redact_sensitive_values(config)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(snapshot, handle, allow_unicode=True, sort_keys=False)


def _redact_sensitive_values(config: dict[str, Any]) -> dict[str, Any]:
    snapshot = deepcopy(config)
    for provider in snapshot.get("llm_providers", {}).values():
        if provider.get("api_key"):
            provider["api_key"] = "***REDACTED***"
    return snapshot
