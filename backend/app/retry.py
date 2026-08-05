"""Retry utilities for Harmoniq.

Provides exponential backoff decorators using tenacity for:
- Network calls (yt-dlp, Anthropic API)
- Transient pipeline failures (Demucs OOM, beat grid errors)
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger("harmoniq.retry")

# ---------------------------------------------------------------------------
# Retryable exception types
# ---------------------------------------------------------------------------


class TransientError(Exception):
    """Base class for errors that should be retried."""


class NetworkError(TransientError):
    """Network-level failures (timeout, DNS, connection refused)."""


class RateLimitError(TransientError):
    """API rate limit exceeded (429)."""


class ServiceUnavailableError(TransientError):
    """Upstream service temporarily unavailable (503)."""


# ---------------------------------------------------------------------------
# Decorator factory
# ---------------------------------------------------------------------------


def retry_transient(
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 16.0,
    **kwargs: Any,
) -> Callable:
    """Decorator that retries on transient errors with exponential backoff.

    Usage:
        @retry_transient(max_attempts=3)
        def flaky_operation():
            ...
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(TransientError),
        before_sleep=_log_retry_attempt,
        reraise=True,
        **kwargs,
    )


def _log_retry_attempt(retry_state: RetryCallState) -> None:
    """Log each retry attempt with context."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    logger.warning(
        "retry attempt=%d/%s exception=%s",
        retry_state.attempt_number,
        retry_state.retry_object.stop.max_attempt_count if hasattr(retry_state.retry_object.stop, "max_attempt_count") else "?",
        type(exc).__name__ if exc else "?",
    )


# ---------------------------------------------------------------------------
# Non-recoverable error classification
# ---------------------------------------------------------------------------

NON_RECOVERABLE_ERRORS = (
    ValueError,  # Invalid input, bad URL format
    FileNotFoundError,  # Missing file
    PermissionError,  # Access denied
)


def is_recoverable(exc: Exception) -> bool:
    """Determine if an exception represents a recoverable (retryable) error."""
    if isinstance(exc, TransientError):
        return True
    if isinstance(exc, NON_RECOVERABLE_ERRORS):
        return False
    # Network-like errors from httpx/requests
    exc_name = type(exc).__name__.lower()
    if any(kw in exc_name for kw in ("timeout", "connection", "dns", "network")):
        return True
    return False
