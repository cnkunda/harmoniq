# Backing track provenance

## Current assets (commit 47)

These five loops are **original, project-generated practice loops** rendered locally with `ffmpeg` from multi-harmonic source formulas (plus light noise/reverb/compression), exported as 24s stereo MP3 at 44.1kHz.

License for these generated loops: **internal project use and distribution with Harmoniq repo**.

| File | Intended vibe | Source |
|------|----------------|--------|
| `am-blues-70bpm.mp3` | A minor slow blues shuffle | Generated in-repo (`ffmpeg` aevalsrc + dynamics) |
| `am-drone-ambient.mp3` | A minor ambient drone | Generated in-repo (`ffmpeg` aevalsrc + echo) |
| `g-major-fingerpicking-80bpm.mp3` | G major fingerpicking groove | Generated in-repo (`ffmpeg` aevalsrc + dynamics) |
| `em-two-chord-90bpm.mp3` | E minor two-chord vamp | Generated in-repo (`ffmpeg` aevalsrc + dynamics) |
| `g-major-ballad-65bpm.mp3` | G major slow ballad | Generated in-repo (`ffmpeg` aevalsrc + echo) |

## Generation notes

- Tool: `ffmpeg` (lavfi `aevalsrc`, EQ, compression/echo)
- Sample rate: 44.1 kHz
- Channels: stereo
- Duration: ~24s per loop
- Target bitrate: 160 kbps MP3

If/when these are replaced by external licensed recordings, add exact title/artist/license/URL rows here.
