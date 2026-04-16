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
