# Session metronome clicks (PRIORITIES §50)

## `click-hi.wav` / `click-lo.wav`

- Short mono PCM clicks (44.1 kHz, 16-bit) generated for the native Expo metronome path (`src/audio/metronome.native.ts`).
- **Hi**: ~2 kHz, ~45 ms; **Lo**: ~1.1 kHz, ~38 ms — downbeat vs off-beat contrast.
- Web scheduling uses synthesized square-wave clicks in `src/audio/metronome.web.ts` (same roles; no WAV decode on the hot path).

## Native timing note

Expo `Audio.Sound` playback is driven from JS timers (~25 ms poll). Measured perceived jitter vs stem transport is typically **~20–80 ms** depending on device load — acceptable for v1 per roadmap; web uses `AudioContext` sample-accurate scheduling instead.
