from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_export_gp5_too_small_422() -> None:
    tiny = base64.b64encode(b"x" * 16).decode("ascii")
    r = client.post("/export", json={"gp5_base64": tiny, "format": "midi"})
    assert r.status_code == 422
    body = r.json()
    assert "detail" in body
    assert isinstance(body["detail"], str)


def test_export_invalid_base64_422() -> None:
    r = client.post(
        "/export",
        json={"gp5_base64": "not-valid-base64!!!", "format": "midi"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]


def test_export_pdf_unsupported_422() -> None:
    ok_size = base64.b64encode(b"x" * 64).decode("ascii")
    r = client.post("/export", json={"gp5_base64": ok_size, "format": "pdf"})
    assert r.status_code == 422
    assert "PDF" in r.json()["detail"] or "not available" in r.json()["detail"].lower()


def test_export_disabled_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HARMONIQ_SKIP_EXPORT", "1")
    ok_size = base64.b64encode(b"x" * 64).decode("ascii")
    r = client.post("/export", json={"gp5_base64": ok_size, "format": "midi"})
    assert r.status_code == 503
    assert "disabled" in r.json()["detail"].lower()
