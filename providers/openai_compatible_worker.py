from __future__ import annotations

import base64
import faulthandler
import json
import mimetypes
import os
import ssl
import sys
import urllib.request
from pathlib import Path
from typing import Any

from utils.retry_utils import RetryPolicy, is_transient_error, retry_call


faulthandler.enable()
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    try:
        payload: dict[str, Any] = json.loads(sys.stdin.read())
        config = dict(payload["config"])
        api_key = config.get("api_key") or os.getenv(config.get("api_key_env", "OPENAI_API_KEY"))
        if not api_key:
            raise RuntimeError(f"Missing API key: {config.get('api_key_env', 'OPENAI_API_KEY')}")

        request_type = payload.get("type", "text")
        prompt = payload.get("prompt", "")
        model = payload.get("model") or config.get("default_model")
        if request_type == "images":
            messages = [{"role": "user", "content": _image_content(prompt, payload.get("image_paths", []))}]
        else:
            messages = [{"role": "user", "content": prompt}]

        content = _chat_completion_stdlib(config, api_key, model, messages)
        sys.stdout.write(json.dumps({"ok": True, "content": content}, ensure_ascii=False))
        return 0
    except Exception as exc:
        sys.stdout.write(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


def _chat_completion_stdlib(
    config: dict[str, Any],
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
) -> str:
    base_url = str(config.get("base_url", "")).rstrip("/")
    if not base_url:
        raise RuntimeError("Missing base_url for OpenAI-compatible provider.")
    attempts = int(config.get("max_retries", 2)) + 1
    retry_backoff_seconds = float(config.get("retry_backoff_seconds", 2))
    timeout = float(config.get("timeout", 180))
    body = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": config.get("temperature", 0.2),
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    def request_once() -> str:
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as response:
                raw = response.read().decode("utf-8", errors="replace")
            return _extract_chat_content(json.loads(raw))
        except Exception as exc:
            raise RuntimeError(f"LLM HTTP request failed: {exc}") from exc

    return retry_call(
        "LLM worker HTTP request",
        RetryPolicy(max_attempts=attempts, backoff_seconds=retry_backoff_seconds),
        request_once,
        should_retry=is_transient_error,
        on_retry=lambda exc, next_attempt, total_attempts, delay: print(
            f"WARNING: LLM request failed, retrying in {delay:.1f}s ({next_attempt}/{total_attempts})",
            file=sys.stderr,
        ),
    )


def _extract_chat_content(data: dict[str, Any]) -> str:
    if "error" in data:
        error = data["error"]
        if isinstance(error, dict):
            raise RuntimeError(error.get("message") or json.dumps(error, ensure_ascii=False))
        raise RuntimeError(str(error))
    choices = data.get("choices")
    if not choices:
        raise RuntimeError(f"LLM response missing choices: {json.dumps(data, ensure_ascii=False)[:1000]}")
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def _image_content(prompt: str, image_paths: list[str]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for image_path in image_paths:
        content.append({"type": "image_url", "image_url": {"url": _image_to_data_url(Path(image_path))}})
    return content


def _image_to_data_url(path: Path) -> str:
    mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return f"data:{mime_type};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


if __name__ == "__main__":
    raise SystemExit(main())
