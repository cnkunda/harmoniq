"""Provider-chain orchestration tests (J1: ACE-Step -> Lyria -> MRT2 -> bundled)."""
from __future__ import annotations

import time

import pytest

from app.music_generation.registry import provider_names
from app.music_generation.service import generate_with_providers
from app.music_generation.types import (
    BackingRequest,
    GeneratedBacking,
    ProviderUnavailable,
)

class FakeProvider:
    verify_musical_quality = False

    def __init__(
        self,
        name: str,
        *,
        available: bool = True,
        result: GeneratedBacking | None = None,
        error: Exception | None = None,
        delay_s: float = 0.0,
    ) -> None:
        self.name = name
        self._available = available
        self._result = result
        self._error = error
        self._delay_s = delay_s
        self.calls = 0

    def is_available(self) -> bool:
        return self._available

    def generate(self, req: BackingRequest) -> GeneratedBacking:
        self.calls += 1
        if self._delay_s:
            time.sleep(self._delay_s)
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def _result(provider: str, wav: bytes = b"RIFFfake") -> GeneratedBacking:
    return GeneratedBacking(wav_bytes=wav, duration_ms=1000, provider=provider, prompt_used="p")


def _req() -> BackingRequest:
    return BackingRequest(musical_key="A minor", bpm=70, prompt="p")


@pytest.mark.asyncio
async def test_skips_unavailable_and_uses_next_provider() -> None:
    cloud = FakeProvider("ace_step_modal", available=False)
    local = FakeProvider("mrt2", result=_result("mrt2"))
    result = await generate_with_providers(_req(), [cloud, local], timeout_s=1)
    assert result.provider == "mrt2"
    assert result.used_fallback is True
    assert result.attempts == ["ace_step_modal:unavailable"]
    assert result.fallback_reason == "ace_step_modal:unavailable"


@pytest.mark.asyncio
async def test_first_provider_success_is_not_marked_fallback() -> None:
    cloud = FakeProvider("ace_step_modal", result=_result("ace_step_modal"))
    local = FakeProvider("mrt2", result=_result("mrt2"))
    result = await generate_with_providers(_req(), [cloud, local], timeout_s=1)
    assert result.provider == "ace_step_modal"
    assert result.used_fallback is False
    assert local.calls == 0


@pytest.mark.asyncio
async def test_provider_error_falls_through_with_reason() -> None:
    failing = FakeProvider("lyria", error=ProviderUnavailable("no url"))
    bundled = FakeProvider("bundled", result=GeneratedBacking(
        wav_bytes=b"RIFFb", duration_ms=1, provider="bundled", prompt_used="p", used_fallback=True
    ))
    result = await generate_with_providers(_req(), [failing, bundled], timeout_s=1)
    assert result.provider == "bundled"
    assert result.attempts == ["lyria:ProviderUnavailable"]


@pytest.mark.asyncio
async def test_timeout_falls_through() -> None:
    slow = FakeProvider("mrt2", result=_result("mrt2"), delay_s=0.2)
    bundled = FakeProvider("bundled", result=GeneratedBacking(
        wav_bytes=b"RIFFb", duration_ms=1, provider="bundled", prompt_used="p", used_fallback=True
    ))
    result = await generate_with_providers(_req(), [slow, bundled], timeout_s=0.01)
    assert result.provider == "bundled"
    assert "mrt2:timeout" in result.attempts


@pytest.mark.asyncio
async def test_all_providers_failing_raises() -> None:
    a = FakeProvider("mrt2", error=ProviderUnavailable("down"))
    b = FakeProvider("synth", error=ProviderUnavailable("no assets"))
    with pytest.raises(RuntimeError, match="No backing provider succeeded"):
        await generate_with_providers(_req(), [a, b], timeout_s=1)


def test_provider_names_default_chain_and_model_pin(monkeypatch) -> None:
    monkeypatch.delenv("HARMONIQ_BACKING_PROVIDERS", raising=False)
    names = provider_names()
    assert names[0] == "ace_step_modal"
    assert names[-1] == "synth"
    pinned = provider_names("lyria")
    assert pinned[0] == "lyria"
    assert pinned.count("lyria") == 1


# ---------------------------------------------------------------------------
# J2: async generation jobs
# ---------------------------------------------------------------------------

import time
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.music_generation import jobs as backing_jobs

client = TestClient(app)


def _gen_result():
    return GeneratedBacking(
        wav_bytes=b"RIFFasync",
        duration_ms=1200,
        provider="bundled",
        prompt_used="p [fallback_track=x.mp3]",
        used_fallback=True,
        sample_rate=44100,
    )


def test_async_job_completes_and_returns_result() -> None:
    backing_jobs.clear_jobs()
    with patch("app.main.generate_backing", new=AsyncMock(return_value=_gen_result())):
        created = client.post("/jam/backing/jobs", json={"musical_key": "A minor", "bpm": 70})
        assert created.status_code == 200
        job_id = created.json()["job_id"]
        body = None
        for _ in range(40):
            body = client.get(f"/jam/backing/jobs/{job_id}").json()
            if body["status"] == "complete":
                break
            time.sleep(0.05)
    assert body is not None
    assert body["status"] == "complete"
    assert body["result"]["provider"] == "bundled"
    assert body["result"]["used_fallback"] is True


def test_async_job_reports_failure() -> None:
    backing_jobs.clear_jobs()
    with patch("app.main.generate_backing", new=AsyncMock(side_effect=RuntimeError("chain down"))):
        created = client.post("/jam/backing/jobs", json={"musical_key": "A minor"})
        job_id = created.json()["job_id"]
        body = None
        for _ in range(40):
            body = client.get(f"/jam/backing/jobs/{job_id}").json()
            if body["status"] == "failed":
                break
            time.sleep(0.05)
    assert body is not None
    assert body["status"] == "failed"
    assert "chain down" in body["error"]


def test_async_job_unknown_id_404() -> None:
    res = client.get("/jam/backing/jobs/does-not-exist")
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# X1: real HTTP path for the remote provider (no mocked transport)
# ---------------------------------------------------------------------------

import http.server
import io
import threading
import wave


def _tiny_wav(seconds: float = 0.25, sample_rate: int = 8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * int(seconds * sample_rate))
    return buf.getvalue()


def test_remote_provider_fetches_raw_wav_over_http(monkeypatch) -> None:
    from app.music_generation.providers import RemoteBackingProvider

    wav = _tiny_wav()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(wav)))
            self.end_headers()
            self.wfile.write(wav)

        def log_message(self, *_args):
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setenv(
            "HARMONIQ_ACE_STEP_BACKING_URL",
            f"http://127.0.0.1:{server.server_address[1]}/generate",
        )
        provider = RemoteBackingProvider("ace_step_modal", "HARMONIQ_ACE_STEP_BACKING_URL")
        assert provider.is_available()
        result = provider.generate(_req().with_prompt("test prompt"))
        assert result.provider == "ace_step_modal"
        assert result.wav_bytes == wav
        assert result.duration_ms > 0
    finally:
        server.shutdown()
        server.server_close()
