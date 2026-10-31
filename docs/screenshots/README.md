# README screenshots

These images are embedded in the top-level [`README.md`](../../README.md).

| File | Surface | State |
| --- | --- | --- |
| `home.png` | Home | Seeded library (`Midnight Blues`) with today's practice card and daily lick |
| `study.png` | `/session/study` | Offline demo lesson, Expressive mode, scrolled to the fretboard + chord chart |
| `play.png` | `/session/play` | Demo lesson, microphone capture / pitch-score panel |
| `scale-explorer.png` | `/scale-explorer` | C major Ionian with the CAGED E shape highlighted |
| `progress.png` | `/progress` | Mentor card, coach context, and coach summary |

## Regenerate

From the repo root, with the frontend toolchain in Git Bash:

```bash
README_CAPTURE=1 npx playwright test --config=playwright.config.ts tests/ui/readme-screenshots.spec.ts
```

The spec uses Chromium at 1280×900 and the deterministic UX-audit seed in
`tests/ui/support/uxSeed.ts`. It is skipped during the normal `npm run test:ui`
run unless `README_CAPTURE=1` is set.

Notes:

- The session screenshots use the bundled offline demo lesson, so no backend or
  audio files are required.
- The Expo fast-refresh overlay is hidden via injected CSS.
- The screenshots are committed; re-run the command only when the UI changes.
