"""Tests for Commit 8 fallback metrics and metric-update resilience."""

from __future__ import annotations

import pytest

from app import metrics


def test_record_fallback_increments_counter() -> None:
    prometheus_client = pytest.importorskip("prometheus_client")
    labels = {"stage": "test_stage", "reason": "exception"}
    before = prometheus_client.REGISTRY.get_sample_value(
        "harmoniq_fallback_total", labels
    ) or 0.0

    metrics.record_fallback("test_stage")

    after = prometheus_client.REGISTRY.get_sample_value(
        "harmoniq_fallback_total", labels
    )
    assert after == before + 1


def test_queue_depth_skips_unreadable_buckets() -> None:
    class FakeRedis:
        def llen(self, key: str) -> int:
            if key.endswith("\x06\x163"):
                raise ValueError("unreadable bucket")
            return 2

    # Priorities 0, 6, and 9 are readable; 3 is skipped.
    assert metrics._queue_depth(FakeRedis(), "analyze.normal") == 6


def test_update_queue_metrics_survives_redis_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.job_store as job_store

    def _raise() -> None:
        raise RuntimeError("redis down")

    monkeypatch.setattr(job_store, "get_redis", _raise)
    metrics.update_queue_metrics()  # must not raise
