# Error states — manual QA (README § Error States)

Each row matches [README.md](../README.md) “Error States”. Expected **Message** and primary **Action** label are fixed in `src/errors/mapErrorToUi.ts` (`README_ERROR_COPY`).

## Mic permission denied

- **Force:** Native Play → tap “Start play capture” → deny microphone when the OS prompts.
- **Expect:** Banner with README mic message; action **Open Settings** (native) opens system settings; no stack trace.

## YouTube URL invalid

- **Force:** Add Song → paste a non-YouTube or clearly invalid URL → Analyze URL; or use a URL the backend rejects with HTTP 400 while `youtube_url` was sent.
- **Expect:** README YouTube message; primary action **Retry** returns to idle so you can edit the URL.

## Analysis job failed

- **Force:** Stop the backend or break `EXPO_PUBLIC_API_BASE_URL` so submit/poll returns 5xx or repeated failure; or trigger a job that fails server-side.
- **Expect:** README analysis-failed message; **Retry**.

## Analysis job timeout (>5 min)

- **Force:** Mock or slow path so the client is still in “analyzing” for **>5 minutes** before an error, or simulate failure after `elapsedMs > 5 * 60 * 1000` in the catch path (dev-only timer tweak).
- **Expect:** README timeout/info message; **Dismiss** (v1 does not send a push; copy matches README intent).

## No internet during analysis

- **Force:** Add Song → start analyze → disable network before the request completes (or use offline in devtools on web).
- **Expect:** README offline message; **Dismiss**.

## Audio too short (<30 sec)

- **Force:** Backend returns 400 with body mentioning short duration / “30 sec” (or heuristic in mapper), or use a clip the API rejects as too short.
- **Expect:** README short-audio message; **Dismiss**.

## Score endpoint failure

- **Force:** Review → “Run score” with backend down or `/score` returning error.
- **Expect:** README score message; primary action **Do it again** re-runs scoring.
- **Also:** Onboarding phrase flow → “Stop & score” after a valid take with backend failing — same copy and **Do it again** resubmits the last captured take without re-recording.

## No guitar stem detected

- **Force:** Backend error body that matches stem/heuristic in `mapAnalyzeFlowError` (e.g. mentions guitar + stem/isolate).
- **Expect:** README no-guitar-stem message; **Try again**.

## Low transcription confidence

- **Force:** Open a lesson with `transcription_confidence` below `TRANSCRIPTION_CONFIDENCE_UNCERTAIN_MAX` in `src/db/schema.ts` (e.g. seed or mock lesson).
- **Expect:** Study shows warning banner with README low-confidence message; **Continue** or dismiss (X) hides it for that section until navigation changes section/job.

## Browser mic blocked

- **Force:** Web → Jam → block mic in site settings (or deny permission) → Start Jamming.
- **Expect:** README browser-mic message (no error toast with raw `getUserMessage`); **Retry** re-attempts `startPitch`.
