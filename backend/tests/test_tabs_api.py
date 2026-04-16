"""HTTP tests for stub tab search API."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_tabs_search_stub_returns_hits():
    r = client.get("/tabs/search", params={"q": "Smoke on the Water"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["provider"] == "stub"
    assert len(data["hits"]) >= 1
    assert data["hits"][0]["id"]
    assert "Smoke" in data["hits"][0]["title"] or "Example" in data["hits"][0]["title"]


def test_tabs_search_empty_query_returns_no_hits():
    r = client.get("/tabs/search", params={"q": "   "})
    assert r.status_code == 200, r.text
    assert r.json()["hits"] == []


def test_tabs_gp5_returns_501():
    r = client.get("/tabs/stub-1/gp5")
    assert r.status_code == 501, r.text
