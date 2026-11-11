# Jam Backing Generation

Harmoniq generates practice beds through an ordered provider chain. The backend
never assumes a single model; every response reports what actually produced the
audio.

## Provider chain

`HARMONIQ_BACKING_PROVIDERS` (default **ace_step_modal,lyria,mrt2,bundled**).
`synth` is always appended as a last resort. Unavailable providers are skipped.

| Provider | What it is | Env |
|---|---|---|
| `ace_step_modal` | ACE-Step 1.5 on Modal (GPU) | `HARMONIQ_ACE_STEP_BACKING_URL`, `HARMONIQ_MODAL_TOKEN` (optional) |
| `lyria` | Lyria proxy endpoint | `HARMONIQ_LYRIA_BACKING_URL`, `GEMINI_API_KEY` (bearer) |
| `mrt2` | Local Magenta RealTime 2 (CPU) | `pip install "harmoniq-backend[mrt2]"` |
| `bundled` | Bundled MP3 practice loops | always available |
| `synth` | Emergency sine bed | always available |

Other knobs: `HARMONIQ_BACKING_TIMEOUT_S` (per-attempt deadline, default 45 s),
`HARMONIQ_SKIP_MRT2` is not needed (availability is import-based).

## Remote provider contract

Both remote providers speak the same contract, implemented by
`app.music_generation.providers.RemoteBackingProvider`:

```
POST <url>
Content-Type: application/json
Authorization: Bearer <token>          # optional

{
  "prompt": "...", "musical_key": "A minor", "bpm": 70,
  "duration_secs": 16, "seed": null, "model": "ace_step_modal"
}
```

Response: raw `audio/wav` bytes **or** JSON `{"audio_base64": "..."}`.
The backend verifies key/BPM, trims to the last downbeat, fades the loop seam,
and reports `provider`, `used_fallback`, `key_label`, `key_confidence`, `bpm`,
and `beat_grid`.

## Deploying ACE-Step 1.5 on Modal

`backend/scripts/ace_step_modal.py` is a self-contained Modal app:

```bash
cd backend
modal deploy scripts/ace_step_modal.py
```

Copy the printed endpoint URL into:

```bash
HARMONIQ_ACE_STEP_BACKING_URL=https://<workspace>--harmoniq-ace-step-generate.modal.run
```

Smoke test:

```bash
modal run scripts/ace_step_modal.py::smoke
# or:
curl -X POST "$HARMONIQ_ACE_STEP_BACKING_URL" \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"slow minor blues","musical_key":"A minor","bpm":70,"duration_secs":16}' \
  --output bed.wav
```

Notes:

- Weights live on the `ACE-Step-v15-model-cache` Modal Volume; first start downloads them.
- `min_containers=1` keeps a warm replica so jams don't wait for a cold start.
  Remove it to save cost if you only use Jam occasionally.
- The app clamps duration to 4–64 s and always generates instrumental audio.
- Jam starts on the bundled loop and hot-swaps the generated bed when the async
  job completes, so generation latency never blocks practice.

## Lyria

`app/music_generation/providers.py` calls `HARMONIQ_LYRIA_BACKING_URL` with the
same contract, using `GEMINI_API_KEY` as the bearer token when set. Lyria's
realtime API is a websocket; point the proxy at it and convert the stream to WAV
before returning. If no URL is configured the provider is skipped.

## Async jobs

- `POST /jam/backing` — synchronous (used by low-latency/remote cases).
- `POST /jam/backing/jobs` → `{job_id}`; `GET /jam/backing/jobs/{job_id}` —
  poll-based async path used by Jam's hot-swap. Jobs are in-memory, bounded to
  32 entries, and expire after one hour.

## Phrase practice

Jam snapshots store `backing_source`, key, BPM, progression, prompt, provider,
and duration (`jam_snapshots` migration v22). "Practice this phrase" for an AI
jam regenerates a bed with that context (the exact original audio is not cached
yet) and loops the phrase region at 0.75× speed.
