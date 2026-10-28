"""Circuit breaker for Harmoniq.

Wraps external service calls (Anthropic, model server) with circuit breaker
protection to prevent cascading failures when upstream services are down.
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger("harmoniq.circuit_breaker")

# ---------------------------------------------------------------------------
# Circuit breaker states
# ---------------------------------------------------------------------------

class CircuitState(str, Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing recovery

class CircuitBreakerError(Exception):
    """Raised when the circuit is open and calls are being rejected."""

# ---------------------------------------------------------------------------
# Circuit breaker implementation
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """Simple circuit breaker with configurable thresholds.

    Args:
        name: Identifier for logging.
        failure_threshold: Number of consecutive failures before opening.
        recovery_timeout: Seconds to wait before transitioning to half-open.
        success_threshold: Consecutive successes in half-open to close.
    """

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        success_threshold: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0.0

    @property
    def state(self) -> CircuitState:
        """Current circuit state (with automatic half-open transition)."""
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                logger.info("circuit_breaker name=%s state=open->half_open", self.name)
        return self._state

    def record_success(self) -> None:
        """Record a successful call."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                logger.info("circuit_breaker name=%s state=half_open->closed", self.name)
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            logger.warning("circuit_breaker name=%s state=half_open->open (failure in half-open)", self.name)
        elif self._state == CircuitState.CLOSED and self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                "circuit_breaker name=%s state=closed->open (failures=%d)",
                self.name,
                self._failure_count,
            )

    def allow_request(self) -> bool:
        """Check if a request is allowed through the circuit."""
        current_state = self.state  # triggers half-open transition check
        if current_state == CircuitState.CLOSED:
            return True
        if current_state == CircuitState.HALF_OPEN:
            return True  # Allow one probe request
        return False  # OPEN

    def __call__(self, func: Callable) -> Callable:
        """Decorator that wraps a function with circuit breaker protection."""

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not self.allow_request():
                raise CircuitBreakerError(
                    f"Circuit breaker '{self.name}' is OPEN — call rejected"
                )
            try:
                result = func(*args, **kwargs)
                self.record_success()
                return result
            except Exception:
                self.record_failure()
                raise

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    def reset(self) -> None:
        """Manually reset the circuit to closed."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        logger.info("circuit_breaker name=%s reset", self.name)

    def metrics(self) -> dict:
        """Return current circuit breaker state for observability."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
        }


# ---------------------------------------------------------------------------
# Anthropic authentication failure guard
# ---------------------------------------------------------------------------

#: A rejected API key will not become valid during a request burst. Stop
#: spending latency (and log volume) on further calls for this cooldown.
_AUTH_FAILURE_COOLDOWN_SECONDS = 300.0
_auth_lock = threading.Lock()
_anthropic_auth_failed_until = 0.0


def is_auth_error(exc: BaseException) -> bool:
    """Return True when *exc* represents an invalid or rejected API key."""
    status_code = getattr(exc, "status_code", None)
    if status_code == 401:
        return True
    return exc.__class__.__name__ == "AuthenticationError"


def anthropic_auth_blocked() -> bool:
    """Return True while the process is in the post-401 cooldown window."""
    with _auth_lock:
        return time.time() < _anthropic_auth_failed_until


def note_anthropic_auth_failure() -> None:
    """Record an authentication failure and start the cooldown window."""
    global _anthropic_auth_failed_until
    with _auth_lock:
        _anthropic_auth_failed_until = time.time() + _AUTH_FAILURE_COOLDOWN_SECONDS
    logger.warning(
        "circuit_breaker name=anthropic auth_failed; suppressing LLM calls for %.0fs",
        _AUTH_FAILURE_COOLDOWN_SECONDS,
    )


def note_anthropic_auth_success() -> None:
    """Clear the cooldown after a successful authenticated call."""
    global _anthropic_auth_failed_until
    with _auth_lock:
        _anthropic_auth_failed_until = 0.0


# ---------------------------------------------------------------------------
# Pre-configured breakers
# ---------------------------------------------------------------------------

anthropic_breaker = CircuitBreaker(
    name="anthropic",
    failure_threshold=5,
    recovery_timeout=60.0,
)

model_server_breaker = CircuitBreaker(
    name="model_server",
    failure_threshold=3,
    recovery_timeout=30.0,
)


def get_all_breakers() -> list[CircuitBreaker]:
    """Return all registered circuit breakers for observability."""
    return [anthropic_breaker, model_server_breaker]
