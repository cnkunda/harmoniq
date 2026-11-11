"""Deploy ACE-Step 1.5 on Modal as Harmoniq's jam-bed provider.

Deploy:
    modal deploy scripts/ace_step_modal.py

Then point the backend at the printed URL:
    HARMONIQ_ACE_STEP_BACKING_URL=https://<workspace>--harmoniq-ace-step-generate.modal.run
    # optional: HARMONIQ_MODAL_TOKEN=<bearer token> if the endpoint is protected

The endpoint matches ``app.music_generation.providers.RemoteBackingProvider``:
POST JSON ``{prompt, musical_key, bpm, duration_secs, seed, model}`` → ``audio/wav``.

Notes
- Weights live on a Modal Volume; the first cold start downloads them.
- Keep one replica warm for on-the-fly jams, or rely on Jam's bundled-loop
  hot-swap while the job runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from uuid import uuid4

import modal

CHECKPOINTS_DIR = "/opt/ace-step/checkpoints"
MODEL_VOLUME = modal.Volume.from_name("ACE-Step-v15-model-cache", create_if_missing=True)

image = (
    modal.Image.from_registry("nvidia/cuda:13.0.0-cudnn-devel-ubuntu22.04", add_python="3.12")
    .apt_install("git", "ffmpeg")
    .run_commands(
        "git clone --branch v0.1.6 --depth 1 https://github.com/ace-step/ACE-Step-1.5.git /opt/ace-step",
    )
    .uv_pip_install(
        "/opt/ace-step",
        "hf_transfer==0.1.9",
        "torchcodec==0.10.0",
        "torch~=2.10.0",
    )
    .env({"ACESTEP_PROJECT_ROOT": "/opt/ace-step", "HF_HUB_ENABLE_HF_TRANSFER": "1"})
    .entrypoint([])
)

web_image = modal.Image.debian_slim(python_version="3.12").uv_pip_install(
    "fastapi[standard]==0.115.4",
    "pydantic==2.10.1",
)

app = modal.App("harmoniq-ace-step")


@app.cls(
    gpu="l40s",
    image=image,
    volumes={CHECKPOINTS_DIR: MODEL_VOLUME},
    timeout=600,
    # Keep one warm replica to make on-the-fly jams practical.
    min_containers=1,
)
class MusicGenerator:
    @modal.enter()
    def init(self) -> None:
        from acestep.handler import AceStepHandler
        from acestep.llm_inference import LLMHandler
        from acestep.model_downloader import ensure_lm_model, ensure_main_model

        lm_model_name = "acestep-5Hz-lm-4B"
        ensure_main_model(checkpoints_dir=CHECKPOINTS_DIR)
        ensure_lm_model(model_name=lm_model_name, checkpoints_dir=CHECKPOINTS_DIR)

        self.dit_handler = AceStepHandler()
        init_status, enable_generate = self.dit_handler.initialize_service(
            project_root="/opt/ace-step",
            config_path="acestep-v15-turbo",
            device="cuda",
        )
        if not enable_generate:
            raise RuntimeError(f"DiT model initialization failed: {init_status}")

        self.llm_handler = LLMHandler()
        lm_status, lm_success = self.llm_handler.initialize(
            checkpoint_dir=CHECKPOINTS_DIR,
            lm_model_path=lm_model_name,
            backend="vllm",
            device="cuda",
        )
        if not lm_success:
            raise RuntimeError(f"LM initialization failed: {lm_status}")

    @modal.method()
    def run(self, prompt: str, duration_secs: float, seed: Optional[int]) -> bytes:
        from acestep.inference import GenerationConfig, GenerationParams, generate_music

        safe_duration = max(4.0, min(64.0, float(duration_secs or 16.0)))
        params = GenerationParams(
            caption=prompt,
            lyrics="[Instrumental]",
            duration=safe_duration,
            thinking=True,
        )
        config = GenerationConfig(
            audio_format="wav",
            batch_size=1,
            seeds=[seed] if seed is not None else None,
            use_random_seed=seed is None,
        )
        result = generate_music(
            self.dit_handler,
            self.llm_handler,
            params,
            config,
            save_dir="/dev/shm",
        )
        if not result.success:
            raise RuntimeError(f"Music generation failed: {result.error}")
        return Path(result.audios[0]["path"]).read_bytes()


@app.function(image=web_image, max_containers=1)
@modal.concurrent(max_inputs=8)
@modal.fastapi_endpoint(method="POST")
def generate(payload: dict) -> "object":
    """Harmoniq provider contract: JSON in, audio/wav out."""
    from fastapi import Response

    prompt = str(payload.get("prompt") or "instrumental guitar practice backing track").strip()
    key = payload.get("musical_key")
    bpm = payload.get("bpm")
    if key and "Key:" not in prompt:
        prompt = f"{prompt}, Key: {key}"
    if bpm and "BPM" not in prompt:
        prompt = f"{prompt}, Tempo: approximately {int(bpm)} BPM, consistent tempo"
    prompt = f"{prompt}, drums, bass, comping guitar, no vocals, loop-friendly"

    seed = payload.get("seed")
    duration_secs = float(payload.get("duration_secs") or 16.0)
    wav_bytes = MusicGenerator().run.remote(
        prompt=prompt,
        duration_secs=duration_secs,
        seed=int(seed) if seed is not None else None,
    )
    return Response(content=wav_bytes, media_type="audio/wav")


@app.local_entrypoint()
def smoke(prompt: str = "slow minor blues guitar backing, 70 bpm") -> None:
    """`modal run scripts/ace_step_modal.py::smoke` for a one-off generation."""
    raw = MusicGenerator().run.remote(prompt=prompt, duration_secs=16.0, seed=None)
    out = Path(f"ace-step-smoke-{uuid4().hex[:8]}.wav")
    out.write_bytes(raw)
    print(f"wrote {out} ({len(raw)} bytes)")
