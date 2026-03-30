# Backing track provenance

## Current assets (commit 0.5)

The five `.mp3` files in this folder are **short synthetic placeholders** (~10 s, mono, 44.1 kHz, 128 kbps) generated locally with **ffmpeg** from pure sine tones. They exist so Jam Mode wiring and `expo-av` bundles can be tested before licensed loops are chosen.

| File | Description (target vibe per README) |
|------|--------------------------------------|
| `am-blues-70bpm.mp3` | Target: A minor slow blues shuffle @ 70 BPM |
| `am-drone-ambient.mp3` | Target: A minor ambient drone, no fixed tempo |
| `g-major-fingerpicking-80bpm.mp3` | Target: G major fingerpicking @ 80 BPM |
| `em-two-chord-90bpm.mp3` | Target: E minor raw two-chord vamp @ 90 BPM |
| `g-major-ballad-65bpm.mp3` | Target: G major ballad @ 65 BPM |

**Replace before shipping:** swap in **royalty-free or original** loops (e.g. [Free Music Archive](https://freemusicarchive.org/), [Looperman](https://www.looperman.com/), or recordings you own). Keep files **under ~3 MB** each where possible (README: 30–60 s loops @ ~128 kbps).

## FFmpeg command used for placeholders

```bash
ffmpeg -f lavfi -i "sine=frequency=<Hz>:duration=10" -ac 1 -ar 44100 -c:a libmp3lame -b:a 128k <out.mp3>
```

Frequencies used: 110, 196, 220, 330, 392 Hz — arbitrary; not musically mixed.

When real audio is added, update this file with **title, artist, license, and URL** for each clip.
