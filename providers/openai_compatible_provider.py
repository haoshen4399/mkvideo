import os
import time
from pathlib import Path
from typing import Any

from loguru import logger

from providers.llm_base import LLMProvider
from utils.image_utils import image_to_data_url


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, config: dict[str, Any]) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai SDK is not installed.") from exc
        api_key = config.get("api_key") or os.getenv(config.get("api_key_env", "OPENAI_API_KEY"))
        if not api_key:
            raise RuntimeError(
                f"Missing API key. Set '{config.get('api_key_env', 'OPENAI_API_KEY')}' env or fill api_key in config."
            )
        self.config = config
        self.max_retries = int(config.get("max_retries", 2))
        self.retry_backoff_seconds = float(config.get("retry_backoff_seconds", 2))
        self.client = OpenAI(
            api_key=api_key,
            base_url=config.get("base_url"),
            timeout=config.get("timeout", 180),
            max_retries=self.max_retries,
        )

    def _chat_completion(self, **kwargs: Any) -> Any:
        attempts = self.max_retries + 1
        for attempt in range(attempts):
            try:
                return self.client.chat.completions.create(**kwargs)
            except Exception:
                if attempt >= attempts - 1:
                    raise
                delay = self.retry_backoff_seconds * (2**attempt)
                logger.warning(
                    "LLM request failed, retrying in {:.1f}s ({}/{})",
                    delay,
                    attempt + 2,
                    attempts,
                )
                time.sleep(delay)

    def complete(self, prompt: str, model: str | None = None) -> str:
        response = self._chat_completion(
            model=model or self.config.get("default_model"),
            messages=[{"role": "user", "content": prompt}],
            temperature=self.config.get("temperature", 0.2),
        )
        return response.choices[0].message.content or ""

    def complete_with_images(self, prompt: str, image_paths: list[Path], model: str | None = None) -> str:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for image_path in image_paths:
            content.append({"type": "image_url", "image_url": {"url": image_to_data_url(image_path)}})
        response = self._chat_completion(
            model=model or self.config.get("default_model"),
            messages=[{"role": "user", "content": content}],
            temperature=self.config.get("temperature", 0.2),
        )
        return response.choices[0].message.content or ""


def build_provider(name: str, config: dict[str, Any]) -> LLMProvider:
    providers = config.get("llm_providers", {})
    provider_config = providers.get(name)
    if not provider_config:
        raise KeyError(f"LLM provider not configured: {name}")
    if provider_config.get("type") != "openai_compatible":
        raise ValueError(f"Unsupported provider type: {provider_config.get('type')}")
    return OpenAICompatibleProvider(provider_config)
