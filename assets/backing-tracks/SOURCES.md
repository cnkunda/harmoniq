# Backing track provenance

## Current assets (offline Jam loops)

Five **original programmatic** stereo practice beds (~24 s, 44.1 kHz, MP3 **192 kbps**). They are **not** recordings of commercial releases: each file is synthesized in-repo as a small “virtual band” (bass + chord pad and/or arpeggio + light drums; ambient track is pad-only with stereo width).

License for these loops: **internal project use and distribution with Harmoniq repo**.

| File | Intended vibe | Source |
|------|----------------|--------|
| `am-blues-70bpm.mp3` | A minor slow blues shuffle | In-repo Python synth + `ffmpeg` MP3 encode |
| `am-drone-ambient.mp3` | A minor ambient pad | In-repo Python synth + `ffmpeg` MP3 encode |
| `g-major-fingerpicking-80bpm.mp3` | G major fingerpicking groove | In-repo Python synth + `ffmpeg` MP3 encode |
| `em-two-chord-90bpm.mp3` | E minor two-chord vamp | In-repo Python synth + `ffmpeg` MP3 encode |
| `g-major-ballad-65bpm.mp3` | G major slow ballad | In-repo Python synth + `ffmpeg` MP3 encode |

## Regeneration

From the repo root (requires **Python 3.11+**, **numpy**, **ffmpeg** on `PATH`):

```bash
python scripts/generate_backing_tracks.py
```

This overwrites the five MP3s under `assets/backing-tracks/`. Older builds used thin `ffmpeg` `aevalsrc` tones; the current script layers **chord progressions / arpeggios, bass eighth-note patterns, and simple drums** so offline Jam sounds like a practice rhythm section rather than a single-note placeholder.

## AI instrumental beds (Jam mode)

When the practice server has `GEMINI_API_KEY`, the app can call **`POST /jam/backing`** and play returned **WAV** (44.1 kHz) as the Jam backing (Gemini Lyria provider). Those files are **generated per session**, not checked into this folder; keep API usage and licensing per your Google/Gemini terms. If generation is unavailable, backend falls back to these bundled loops.

If/when these bundled loops are replaced by external licensed recordings, add exact title/artist/license/URL rows here.

## Smoke test fixtures (not bundled — gitignored)

Stem smoke (`backend/scripts/smoke_stems.py`) expects **real** mixed recordings. Those files live under **`backend/data/smoke_real_audio/`** (gitignored with `backend/data/`), **not** in this folder — the MP3s here remain **Jam UI / offline playback** assets only (synthesized beds).

Stored in `backend/data/smoke_real_audio/`. Download with **`curl -fL --retry 25 --retry-delay 20 -A "Mozilla/5.0"`** (one line per file; `-A` avoids HTML instead of MP3; retries help **503**) — see `backend/scripts/smoke_stems.py` header (no `yt-dlp` required).

| File | Source | License | Recording |
|------|--------|---------|-----------|
| `easy_mix.mp3` | `https://archive.org/download/jamendo-218300/01-1427082-Acoustic%20Guitar%20Studio-The%20Road%20Home%20%5FAcoustic%20Guitar%5F.mp3` | See item `License.txt` on [`jamendo-218300`](https://archive.org/details/jamendo-218300) (Jamendo / CC-style terms) | Acoustic Guitar Studio — *The Road Home (Acoustic Guitar)* |
| `dense_mix.mp3` | `https://archive.org/download/jamendo-115937/01-984873-MiR-Nice%20Together.mp3` | See item `License.txt` on [`jamendo-115937`](https://archive.org/details/jamendo-115937) (Jamendo / CC-style terms) | MiR — *Nice Together* (album track 01) |

These files are for **local QA only**. Do not commit them.
