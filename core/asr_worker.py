from __future__ import annotations

import faulthandler
import json
import sys
import traceback
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

faulthandler.enable()
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.asr_engine import _run_engine_direct


def main() -> None:
    try:
        payload: dict[str, Any] = json.loads(sys.stdin.read())
        with redirect_stdout(sys.stderr):
            report = _run_engine_direct(
                str(payload["engine"]),
                Path(payload["audio_path"]),
                Path(payload["output_path"]),
                dict(payload.get("config") or {}),
            )
        sys.stdout.write(json.dumps({"ok": True, "report": report}, ensure_ascii=False))
    except Exception as exc:
        sys.stdout.write(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
