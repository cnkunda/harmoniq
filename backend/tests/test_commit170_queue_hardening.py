"""Tests for Commit 170: DLQ wiring, priority dispatch, metrics, batch enqueue."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.schemas import JobStatus


@pytest.fixture
def client() -> TestClient:
    from app.main import app

    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_jobs():
    from app.jobs import coach_hydration, jobs

    jobs.clear()
    coach_hydration.clear()
    yield
    jobs.clear()
    coach_hydration.clear()


# ---------------------------------------------------------------------------
# DLQ consolidation
# ---------------------------------------------------------------------------


def test_dead_letter_reexports_single_job_store_implementation():
    from app import dead_letter, job_store

    assert dead_letter.push_to_dlq is job_store.push_to_dlq
    assert dead_letter.requeue_from_dlq is job_store.requeue_from_dlq
    assert dead_letter.get_dlq_entry is job_store.get_dlq_entry


def test_push_to_dlq_stores_job_data_and_caps_list():
    from app import job_store

    mock_r = MagicMock()
    with patch.object(job_store, "get_redis", return_value=mock_r):
        job_store.push_to_dlq(
            "job-1",
            "boom",
            error_code="stem_separation_failed",
            retry_count=2,
            job_data={"youtube_url": "https://example.com", "upload_path": None},
        )

    raw = mock_r.lpush.call_args.args[1]
    entry = json.loads(raw)
    assert entry["job_id"] == "job-1"
    assert entry["error_code"] == "stem_separation_failed"
    assert entry["retry_count"] == 2
    assert entry["job_data"]["youtube_url"] == "https://example.com"
    assert "failed_at" in entry
    assert mock_r.ltrim.called


def test_get_dlq_entry_does_not_remove_entry():
    from app import job_store

    entry = {"job_id": "job-1", "error": "boom", "job_data": None}
    mock_r = MagicMock()
    mock_r.llen.return_value = 1
    mock_r.lindex.return_value = json.dumps(entry)

    with patch.object(job_store, "get_redis", return_value=mock_r):
        assert job_store.get_dlq_entry(0) == entry

    mock_r.lrem.assert_not_called()


# ---------------------------------------------------------------------------
# DLQ endpoints
# ---------------------------------------------------------------------------


def test_dlq_requires_operator_token(client, monkeypatch):
    monkeypatch.setenv("HARMONIQ_OPERATOR_TOKEN", "secret")
    response = client.get("/jobs/dlq")
    assert response.status_code == 403


def test_dlq_lists_entries_with_token(client, monkeypatch):
    monkeypatch.setenv("HARMONIQ_OPERATOR_TOKEN", "secret")
    entry = {"job_id": "job-1", "error": "boom", "error_code": "analysis_failed"}
    with patch("app.job_store.inspect_dlq", return_value=[entry]):
        response = client.get("/jobs/dlq", headers={"X-Operator-Token": "secret"})

    assert response.status_code == 200
    assert response.json() == [entry]


def test_requeue_does_not_remove_invalid_entry(client, monkeypatch):
    monkeypatch.setenv("HARMONIQ_OPERATOR_TOKEN", "secret")
    with patch("app.job_store.get_dlq_entry", return_value={"job_id": "job-1"}), patch(
        "app.job_store.requeue_from_dlq"
    ) as requeue_mock:
        response = client.post(
            "/jobs/dlq/0/requeue", headers={"X-Operator-Token": "secret"}
        )

    assert response.status_code == 409
    requeue_mock.assert_not_called()


def test_requeue_dispatches_new_job(client, monkeypatch):
    monkeypatch.setenv("HARMONIQ_OPERATOR_TOKEN", "secret")
    entry = {
        "job_id": "job-1",
        "job_data": {"youtube_url": "https://example.com", "upload_path": None},
    }
    with patch("app.job_store.get_dlq_entry", return_value=entry), patch(
        "app.job_store.requeue_from_dlq", return_value=entry
    ), patch("app.jobs.enqueue_analyze_job") as enqueue_mock:
        response = client.post(
            "/jobs/dlq/0/requeue", headers={"X-Operator-Token": "secret"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["requeued_from"] == "job-1"
    assert body["job_id"] != "job-1"
    enqueue_mock.assert_called_once()
    assert enqueue_mock.call_args.kwargs["youtube_url"] == "https://example.com"


def test_requeue_rejects_non_integer_index(client, monkeypatch):
    monkeypatch.setenv("HARMONIQ_OPERATOR_TOKEN", "secret")
    response = client.post(
        "/jobs/dlq/requeue",
        json={"index": "not-a-number"},
        headers={"X-Operator-Token": "secret"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Priority
# ---------------------------------------------------------------------------


def test_priority_is_preserved_across_progress_updates():
    from app import jobs as jobs_mod

    job_id = "job-priority"
    jobs_mod.jobs[job_id] = JobStatus(status="processing", priority="urgent")
    jobs_mod._set_job_processing_progress(job_id, 0.5, "Halfway")
    assert jobs_mod.jobs[job_id].priority == "urgent"

    jobs_mod._set_job_analysis_stage(job_id, "stems_separating", 0.6, "Stems")
    assert jobs_mod.jobs[job_id].priority == "urgent"


def test_priority_dispatch_uses_queue_and_numeric_priority():
    pytest.importorskip("celery")
    from app import jobs as jobs_mod

    mock_task = MagicMock()
    with patch("app.tasks.analyze_job_task", mock_task):
        jobs_mod.enqueue_analyze_job(
            "job-dispatch",
            youtube_url="https://example.com",
            upload_path=None,
            priority="urgent",
        )

    kwargs = mock_task.apply_async.call_args.kwargs
    assert kwargs["priority"] == 9
    assert kwargs["queue"] == "analyze.urgent"
    assert jobs_mod.jobs["job-dispatch"].priority == "urgent"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def test_queue_depth_sums_priority_buckets():
    from app import metrics

    mock_r = MagicMock()
    sizes = {
        "analyze.normal": 1,
        "analyze.normal\x06\x163": 2,
        "analyze.normal\x06\x169": 3,
    }
    mock_r.llen.side_effect = lambda key: sizes.get(key, 0)

    with patch("app.job_store.get_redis", return_value=mock_r), patch(
        "app.job_store.dlq_length", return_value=4
    ):
        metrics.update_queue_metrics()

    assert metrics.queue_depth.labels(queue="analyze.normal")._value.get() == 6
    assert metrics.dlq_length_gauge._value.get() == 4


def test_gpu_metrics_skip_gracefully_without_nvidia_smi(monkeypatch):
    from app import metrics

    def _raise(*args, **kwargs):
        raise FileNotFoundError("nvidia-smi")

    monkeypatch.setattr(metrics.subprocess, "run", _raise)
    metrics._gpu_cache["ts"] = 0.0
    metrics.update_gpu_metrics()


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------


def test_batch_enqueue_dispatches_each_item(client, monkeypatch):
    from app import jobs as jobs_mod

    calls = []
    monkeypatch.setattr(
        jobs_mod, "enqueue_analyze_job", lambda **kwargs: calls.append(kwargs)
    )

    response = client.post(
        "/analyze/batch",
        json={"urls": ["https://a.example", "https://b.example"], "priority": "low"},
    )

    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert len(calls) == 2
    assert all(call["priority"] == "low" for call in calls)


def test_batch_rejects_empty_payload(client):
    response = client.post("/analyze/batch", json={})
    assert response.status_code == 400
