import os
import json
import ssl
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

from providers.llm_base import LLMProvider
from utils.image_utils import image_to_data_url
from utils.retry_utils import RetryPolicy, is_transient_error, retry_call


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, config: dict[str, Any]) -> None:
        api_key = config.get("api_key") or os.getenv(config.get("api_key_env", "OPENAI_API_KEY"))
        if not api_key:
            raise RuntimeError(
                f"Missing API key. Set '{config.get('api_key_env', 'OPENAI_API_KEY')}' env or fill api_key in config."
            )
        self.config = config
        self.api_key = api_key
        self.base_url = str(config.get("base_url", "")).rstrip("/")
        if not self.base_url:
            raise RuntimeError("Missing base_url for OpenAI-compatible provider.")
        self.max_retries = int(config.get("max_retries", 2))
        self.retry_backoff_seconds = float(config.get("retry_backoff_seconds", 2))
        self.transport = str(config.get("transport", "stdlib")).lower()
        self.client = None
        if self.transport == "openai_sdk":
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError("openai SDK is not installed.") from exc
            self.client = OpenAI(
                api_key=api_key,
                base_url=self.base_url,
                timeout=config.get("timeout", 180),
                max_retries=self.max_retries,
            )

    def _chat_completion(self, **kwargs: Any) -> Any:
        if self.transport != "openai_sdk":
            return self._chat_completion_stdlib(**kwargs)
        if self.client is None:
            raise RuntimeError("openai_sdk transport was selected but client was not initialized.")
        return retry_call(
            "LLM SDK request",
            RetryPolicy(max_attempts=self.max_retries + 1, backoff_seconds=self.retry_backoff_seconds),
            lambda: self.client.chat.completions.create(**kwargs),
            should_retry=is_transient_error,
            on_retry=lambda exc, next_attempt, attempts, delay: _warn(
                "LLM request failed, retrying in {:.1f}s ({}/{})",
                delay,
                next_attempt,
                attempts,
            ),
        )

    def _chat_completion_stdlib(self, **kwargs: Any) -> str:
        attempts = self.max_retries + 1
        url = f"{self.base_url}/chat/completions"
        body = json.dumps(kwargs, ensure_ascii=False).encode("utf-8")
        timeout = float(self.config.get("timeout", 180))
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        def request_once() -> str:
            try:
                with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as response:
                    raw = response.read().decode("utf-8", errors="replace")
                data = json.loads(raw)
                return _extract_chat_content(data)
            except Exception as exc:
                raise RuntimeError(f"LLM HTTP request failed: {exc}") from exc

        return retry_call(
            "LLM HTTP request",
            RetryPolicy(max_attempts=attempts, backoff_seconds=self.retry_backoff_seconds),
            request_once,
            should_retry=is_transient_error,
            on_retry=lambda exc, next_attempt, total_attempts, delay: _warn(
                "LLM request failed, retrying in {:.1f}s ({}/{})",
                delay,
                next_attempt,
                total_attempts,
            ),
        )

    def complete(self, prompt: str, model: str | None = None) -> str:
        if self.config.get("isolate_process", True):
            return _complete_in_subprocess("text", self.config, prompt, [], model)
        response = self._chat_completion(
            model=model or self.config.get("default_model"),
            messages=[{"role": "user", "content": prompt}],
            temperature=self.config.get("temperature", 0.2),
        )
        if isinstance(response, str):
            return response
        return response.choices[0].message.content or ""

    def complete_with_images(self, prompt: str, image_paths: list[Path], model: str | None = None) -> str:
        if self.config.get("isolate_process", True):
            return _complete_in_subprocess("images", self.config, prompt, image_paths, model)
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for image_path in image_paths:
            content.append({"type": "image_url", "image_url": {"url": image_to_data_url(image_path)}})
        response = self._chat_completion(
            model=model or self.config.get("default_model"),
            messages=[{"role": "user", "content": content}],
            temperature=self.config.get("temperature", 0.2),
        )
        if isinstance(response, str):
            return response
        return response.choices[0].message.content or ""


def build_provider(name: str, config: dict[str, Any]) -> LLMProvider:
    providers = config.get("llm_providers", {})
    provider_config = providers.get(name)
    if not provider_config:
        raise KeyError(f"LLM provider not configured: {name}")
    if provider_config.get("type") != "openai_compatible":
        raise ValueError(f"Unsupported provider type: {provider_config.get('type')}")
    return OpenAICompatibleProvider(provider_config)


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


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def _complete_in_subprocess(
    request_type: str,
    provider_config: dict[str, Any],
    prompt: str,
    image_paths: list[Path],
    model: str | None,
) -> str:
    payload = {
        "type": request_type,
        "config": {**provider_config, "isolate_process": False},
        "prompt": prompt,
        "image_paths": [str(path) for path in image_paths],
        "model": model,
    }
    worker = Path(__file__).with_name("openai_compatible_worker.py")
    timeout = int(provider_config.get("subprocess_timeout", provider_config.get("timeout", 180))) + 30
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            [sys.executable, str(worker)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        stdout, stderr = process.communicate(json.dumps(payload, ensure_ascii=True), timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        if process is not None:
            _kill_process(process)
        raise RuntimeError(f"LLM subprocess timed out after {timeout}s") from exc
    except BaseException:
        if process is not None:
            _kill_process(process)
        raise
    result = subprocess.CompletedProcess([sys.executable, str(worker)], process.returncode if process else -1, stdout, stderr)
    if result.returncode != 0:
        raise RuntimeError(f"LLM subprocess failed with exit code {result.returncode}: {_subprocess_error_text(result.stdout, result.stderr)}")
    data = json.loads(result.stdout)
    if not data.get("ok"):
        raise RuntimeError(data.get("error", "LLM subprocess failed"))
    return data.get("content", "")


def _kill_process(process: subprocess.Popen[str]) -> None:
    try:
        process.kill()
    except OSError:
        pass
    try:
        process.communicate(timeout=5)
    except Exception:
        pass


def _subprocess_error_text(stdout: str, stderr: str) -> str:
    try:
        data = json.loads(stdout)
        if isinstance(data, dict) and data.get("error"):
            return str(data["error"])
    except json.JSONDecodeError:
        pass
    return stderr.strip() or stdout.strip()


def _warn(message: str, *args: Any) -> None:
    try:
        text = message.format(*args)
    except Exception:
        text = message
    print(f"WARNING: {text}", file=sys.stderr)
