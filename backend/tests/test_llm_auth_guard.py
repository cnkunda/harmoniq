"""Tests for the Anthropic authentication fail-fast guard."""

from __future__ import annotations

import pytest

from app import circuit_breaker


class _AuthError(Exception):
    status_code = 401


@pytest.fixture(autouse=True)
def _reset_auth_guard(monkeypatch):
    monkeypatch.setattr(circuit_breaker, "_anthropic_auth_failed_until", 0.0)
    yield
    monkeypatch.setattr(circuit_breaker, "_anthropic_auth_failed_until", 0.0)


def test_is_auth_error_detects_401():
    assert circuit_breaker.is_auth_error(_AuthError())
    assert not circuit_breaker.is_auth_error(RuntimeError("boom"))


def test_auth_failure_blocks_and_success_clears():
    assert not circuit_breaker.anthropic_auth_blocked()
    circuit_breaker.note_anthropic_auth_failure()
    assert circuit_breaker.anthropic_auth_blocked()
    circuit_breaker.note_anthropic_auth_success()
    assert not circuit_breaker.anthropic_auth_blocked()


def test_blocked_enrichment_raises_instead_of_calling_api(monkeypatch):
    from app import chord_enrichment
    from app.circuit_breaker import CircuitBreakerError

    monkeypatch.setenv("HARMONIQ_ENABLE_ENRICHMENT_IN_TESTS", "1")
    circuit_breaker.note_anthropic_auth_failure()

    with pytest.raises(CircuitBreakerError):
        chord_enrichment._call_claude_enrichment(
            api_key="sk-test",
            key="C major",
            chord_batch=[{"timestamp": 0.0, "chord": "C:maj"}],
        )
