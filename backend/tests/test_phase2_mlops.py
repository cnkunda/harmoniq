"""Tests for Phase 2: job_store, retry, circuit_breaker, dead_letter, drift_detection.

These tests verify the core MLOps infrastructure without requiring a live Redis instance.
Redis-dependent tests are skipped when Redis is unavailable.
"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.schemas import JobStatus, CoachHydrationStatus, CoachHydrationSection


# ---------------------------------------------------------------------------
# Job store tests (in-memory fallback)
# ---------------------------------------------------------------------------

class TestJobStoreInMemory:
    """Test job_store operations using the in-memory fallback (no Redis)."""

    def test_set_job_processing_progress(self):
        """Verify _set_job_processing_progress updates progress correctly."""
        from app import jobs as jobs_mod

        # Ensure in-memory mode
        with patch.object(jobs_mod, "_use_redis", return_value=False):
            jobs_mod._jobs_memory.clear()

            job_id = "test-progress-1"
            jobs_mod._set_job(
                job_id,
                JobStatus(status="processing", progress=0.0),
            )

            jobs_mod._set_job_processing_progress(job_id, 0.5, "Halfway", "stems_separating")

            job = jobs_mod._get_job(job_id)
            assert job is not None
            assert job.progress == 0.5
            assert job.stage_label == "Halfway"

    def test_enqueue_falls_back_to_thread(self):
        """Verify enqueue_analyze_job falls back to thread when Redis is unavailable."""
        from app import jobs as jobs_mod

        with patch.object(jobs_mod, "_use_redis", return_value=False):
            jobs_mod._jobs_memory.clear()

            job_id = "test-enqueue-1"
            jobs_mod.enqueue_analyze_job(
                job_id,
                youtube_url="https://example.com",
                upload_path=None,
            )

            # Job should be in memory
            job = jobs_mod._get_job(job_id)
            assert job is not None
            assert job.status == "processing"

    def test_coach_hydration_in_memory(self):
        """Verify coach hydration works in in-memory mode."""
        from app import jobs as jobs_mod
        from app.schemas import CoachHydrationStatus

        with patch.object(jobs_mod, "_use_redis", return_value=False):
            jobs_mod._coach_memory.clear()

            job_id = "test-coach-1"
            status = CoachHydrationStatus(
                status="complete",
                sections=[CoachHydrationSection(index=0, coach_note="test", coach_explanation="test")],
            )
            jobs_mod._set_coach(job_id, status)

            result = jobs_mod._get_coach(job_id)
            assert result is not None
            assert result.status == "complete"
            assert len(result.sections) == 1


# ---------------------------------------------------------------------------
# Retry tests
# ---------------------------------------------------------------------------

class TestRetry:
    def test_is_recoverable_transient(self):
        """TransientError should be recoverable."""
        from app.retry import TransientError, is_recoverable

        assert is_recoverable(TransientError("timeout")) is True

    def test_is_recoverable_network(self):
        """Network-like exceptions should be recoverable."""
        from app.retry import is_recoverable

        exc = ConnectionError("connection refused")
        assert is_recoverable(exc) is True

    def test_is_not_recoverable_value_error(self):
        """ValueError should not be recoverable."""
        from app.retry import is_recoverable

        assert is_recoverable(ValueError("bad input")) is False

    def test_retry_decorator_retries(self):
        """retry_transient should retry on transient errors."""
        from app.retry import TransientError, retry_transient

        call_count = 0

        @retry_transient(max_attempts=3, min_wait=0.01, max_wait=0.02)
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TransientError("temporary")
            return "ok"

        result = flaky()
        assert result == "ok"
        assert call_count == 3


# ---------------------------------------------------------------------------
# Circuit breaker tests
# ---------------------------------------------------------------------------

class TestCircuitBreaker:
    def test_initial_state_closed(self):
        """New circuit breaker should be closed (allowing requests)."""
        from app.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker(name="test", failure_threshold=3)
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

    def test_opens_after_threshold(self):
        """Circuit should open after failure_threshold consecutive failures."""
        from app.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker(name="test", failure_threshold=3, recovery_timeout=100)

        for _ in range(3):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_half_open_after_recovery_timeout(self):
        """Circuit should transition to half_open after recovery_timeout."""
        from app.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker(name="test", failure_threshold=2, recovery_timeout=0.1)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.allow_request() is True

    def test_closes_after_success_in_half_open(self):
        """Circuit should close after success in half_open state."""
        from app.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker(name="test", failure_threshold=2, recovery_timeout=0.1, success_threshold=1)

        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_decorator_rejects_when_open(self):
        """Circuit breaker decorator should reject calls when open."""
        from app.circuit_breaker import CircuitBreaker, CircuitBreakerError, CircuitState

        cb = CircuitBreaker(name="test", failure_threshold=2, recovery_timeout=100)

        @cb
        def my_func():
            return "ok"

        cb.record_failure()
        cb.record_failure()

        with pytest.raises(CircuitBreakerError):
            my_func()

    def test_metrics(self):
        """Metrics should return current state."""
        from app.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(name="test", failure_threshold=5)
        m = cb.metrics()
        assert m["name"] == "test"
        assert m["state"] == "closed"
        assert m["failure_count"] == 0


# ---------------------------------------------------------------------------
# Dead letter queue tests
# ---------------------------------------------------------------------------

class TestDeadLetterQueue:
    """Test DLQ operations using in-memory Redis mock."""

    def test_dlq_length_empty(self):
        """DLQ should be empty initially."""
        from app import dead_letter as dlq_mod
        from app import job_store

        with patch.object(job_store, "get_redis") as mock_redis:
            mock_r = MagicMock()
            mock_r.llen.return_value = 0
            mock_redis.return_value = mock_r

            assert dlq_mod.dlq_length() == 0

    def test_inspect_dlq(self):
        """inspect_dlq should return parsed entries."""
        from app import dead_letter as dlq_mod
        from app import job_store

        entry = json.dumps({
            "job_id": "test-1",
            "error": "failed",
            "error_code": "test_error",
            "retry_count": 3,
            "timestamp": time.time(),
        })

        with patch.object(job_store, "get_redis") as mock_redis:
            mock_r = MagicMock()
            mock_r.lrange.return_value = [entry]
            mock_redis.return_value = mock_r

            result = dlq_mod.inspect_dlq()
            assert len(result) == 1
            assert result[0]["job_id"] == "test-1"
            assert result[0]["retry_count"] == 3


# ---------------------------------------------------------------------------
# Drift detection tests
# ---------------------------------------------------------------------------

class TestDriftDetection:
    def test_kl_divergence_identical(self):
        """KL divergence of identical distributions should be ~0."""
        from app.drift_detection import kl_divergence

        p = np.array([0.25, 0.25, 0.25, 0.25])
        q = np.array([0.25, 0.25, 0.25, 0.25])
        kl = kl_divergence(p, q)
        assert kl < 1e-6

    def test_kl_divergence_different(self):
        """KL divergence of different distributions should be > 0."""
        from app.drift_detection import kl_divergence

        p = np.array([0.8, 0.1, 0.05, 0.05])
        q = np.array([0.25, 0.25, 0.25, 0.25])
        kl = kl_divergence(p, q)
        assert kl > 0

    def test_js_divergence_symmetric(self):
        """JS divergence should be symmetric."""
        from app.drift_detection import js_divergence

        p = np.array([0.8, 0.1, 0.05, 0.05])
        q = np.array([0.25, 0.25, 0.25, 0.25])
        assert js_divergence(p, q) == pytest.approx(js_divergence(q, p), abs=1e-10)

    def test_compute_baseline_from_predictions(self):
        """Baseline computation should average across frames."""
        from app.drift_detection import compute_baseline_from_predictions

        preds = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
        baseline = compute_baseline_from_predictions(preds)
        assert baseline.shape == (3,)
        assert baseline[0] == pytest.approx(1 / 3, abs=1e-6)
        assert baseline[1] == pytest.approx(1 / 3, abs=1e-6)
        assert baseline[2] == pytest.approx(1 / 3, abs=1e-6)

    def test_detect_drift_no_baseline(self):
        """Drift detection should gracefully handle missing baseline."""
        from app import drift_detection as dd_mod
        from app.drift_detection import detect_drift

        dd_mod._baseline_distribution = None

        with patch.object(dd_mod, "load_baseline", return_value=False):
            result = detect_drift([[1.0] * 277])
            assert result.is_drifting is False
            assert "No baseline" in result.message

    def test_detect_drift_with_shift(self):
        """Drift detection should detect a shifted distribution."""
        from app import drift_detection as dd_mod
        from app.drift_detection import detect_drift

        # Set baseline to uniform
        dd_mod._baseline_distribution = np.ones(277) / 277

        # Current predictions heavily skewed to chord 0
        current = [[0.0] * 277]
        current[0][0] = 1.0

        result = detect_drift(current, threshold_kl=0.001)
        assert result.is_drifting is True
        assert result.kl_divergence > 0
        assert len(result.top_shifted_chords) > 0

    def test_drift_result_to_dict(self):
        """DriftResult.to_dict should return serializable dict."""
        from app.drift_detection import DriftResult

        result = DriftResult(
            is_drifting=True,
            kl_div=0.1,
            js_div=0.05,
            chi_squared=10.0,
            threshold_kl=0.05,
            threshold_js=0.01,
            top_shifted_chords=[{"chord_index": 0, "diff": 0.5}],
            message="Drift detected",
        )
        d = result.to_dict()
        assert d["is_drifting"] is True
        assert d["kl_divergence"] == 0.1
        assert isinstance(d["top_shifted_chords"], list)
