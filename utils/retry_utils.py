from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    backoff_seconds: float = 1.0
    backoff_multiplier: float = 2.0

    @classmethod
    def from_config(
        cls,
        config: dict | None,
        *,
        attempts_key: str = "max_attempts",
        retries_key: str = "max_retries",
        backoff_key: str = "retry_backoff_seconds",
        default_attempts: int = 1,
        default_backoff: float = 1.0,
    ) -> "RetryPolicy":
        config = config or {}
        if attempts_key in config:
            max_attempts = int(config.get(attempts_key) or default_attempts)
        elif retries_key in config:
            max_attempts = int(config.get(retries_key) or 0) + 1
        else:
            max_attempts = default_attempts
        return cls(
            max_attempts=max(1, max_attempts),
            backoff_seconds=float(config.get(backoff_key, default_backoff)),
            backoff_multiplier=float(config.get("retry_backoff_multiplier", 2.0)),
        )

    def delay_for_attempt(self, attempt_index: int) -> float:
        return max(0.0, self.backoff_seconds * (self.backoff_multiplier**attempt_index))


def retry_call(
    operation_name: str,
    policy: RetryPolicy,
    func: Callable[[], T],
    *,
    should_retry: Callable[[Exception], bool] | None = None,
    on_retry: Callable[[Exception, int, int, float], None] | None = None,
) -> T:
    attempts = max(1, policy.max_attempts)
    for attempt in range(attempts):
        try:
            return func()
        except Exception as exc:
            retryable = should_retry(exc) if should_retry else True
            if not retryable or attempt >= attempts - 1:
                raise
            delay = policy.delay_for_attempt(attempt)
            if on_retry:
                on_retry(exc, attempt + 2, attempts, delay)
            time.sleep(delay)
    raise RuntimeError(f"{operation_name} failed without raising an exception")


def is_transient_error(exc: Exception) -> bool:
    text = str(exc).lower()
    transient_tokens = [
        "timeout",
        "timed out",
        "temporarily",
        "connection",
        "reset",
        "rate limit",
        "429",
        "500",
        "502",
        "503",
        "504",
        "remote end closed",
        "ssl",
        "eof",
    ]
    return any(token in text for token in transient_tokens)
