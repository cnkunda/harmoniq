# AlphaTab harness (`index.html`)

Self-contained page loaded inside **React Native `WebView`** (mobile) or embedded in **web** (iframe / `postMessage`). **AlphaTab** is loaded from jsDelivr — **pinned** to `@coderline/alphatab@1.6.1` (do not switch to `@latest` in production without testing).

SoundFont setup in this harness:

- SoundFont URL is currently pinned to `GeneralUser.sf2` (see `assets/soundfonts/SOURCES.md`)
- Harness emits `soundFontLoad` status messages so app surfaces can show loading feedback

## Visual defaults (Harmoniq README)

| Element | Hex |
|--------|-----|
| Page background | `#2B1D0E` |
| Note heads / primary glyphs | `#FFFFFF` (`mainGlyphColor`; see `src/constants/tabHarnessTheme.ts`) |
| Staff lines / bar separators | `#9B8D7B` (`staffLineColor` / `barSeparatorColor`; lighter for better visibility on dark chrome) |

**Server SVG prerender:** `backend/scripts/alphatab_prerender.mjs` merges color overrides into the default `Settings().display.resources` (never replace the whole object — fonts are required). **Native WebView:** `TabViewport` may pass `prerenderArtifactUrl`, but the harness does not fetch or paint that overlay yet — prerender flash-free loading is **Expo web** only until native catches up.

## Parent → harness (`postMessage`)

Send **JSON strings** (or a plain object where the environment allows it). Shape matches `types/tabMessage.ts` **`TabInboundMessage`**.

### `setScore`

Load a Guitar Pro 5 (binary) file from Base64 (standard base64, no `data:` prefix):

```json
{ "type": "setScore", "gp5Base64": "<base64 of .gp5 bytes>" }
```

Invalid base64 or corrupt GP data produces an outbound **`error`** message.

### `setAudioSrc`

```json
{ "type": "setAudioSrc", "audioSrc": "http://<lan-host>:8000/lesson-file?rel=data%2Fjobs%2F...%2Fguitar.wav" }
```

Sets the external media source used as the canonical playback timeline for cursor sync.

### `setPlaybackRate`

```json
{ "type": "setPlaybackRate", "playbackRate": 0.65 }
```

Updates external audio playback rate and immediately refreshes AlphaTab position.

### `seekTo`

```json
{ "type": "seekTo", "positionMs": 12500 }
```

Seeks external audio to millisecond position and immediately calls `updatePosition`.

### `getPosition`

```json
{ "type": "getPosition" }
```

Requests current external audio position in milliseconds.

### `getSongDetails` (Commit 57)

Request a JSON snapshot of static **score metadata** (title, artist, tempo, GP section markers, etc.). Optional `requestId` is echoed on the **`songDetails`** reply so hosts can correlate with `Promise`-based callers.

```json
{ "type": "getSongDetails", "requestId": "sd_optional_correlation_id" }
```

### `setTheme`

Merge partial colors into AlphaTab **`display.resources`** (camelCase keys as in library settings), then call `api.updateSettings()`.

```json
{
  "type": "setTheme",
  "colors": {
    "mainGlyphColor": "#F0DEB4",
    "staffLineColor": "#5C4535",
    "secondaryGlyphColor": "#D4A574",
    "barSeparatorColor": "#5C4535",
    "scoreInfoColor": "#A08060",
    "barNumberColor": "#8B7D6B"
  }
}
```

Only keys present in the payload are overwritten. See `TabThemeColors` in `types/tabMessage.ts` for the typed subset used by the app.

### `setSoundFontProfile` (Commit 60)

Load or swap the bundled AlphaTab synth bank (`general_user` | `fluid_r3_mono`). See `types/tabMessage.ts` and `docs/MANUAL_QA.md` (Phase 5 / soundfont).

```json
{ "type": "setSoundFontProfile", "profileId": "fluid_r3_mono" }
```

### `setRuntimeDiagnosticsEnabled` (Commit 61)

Opt-in harness periodic outbound **`runtimeDiagnostics`** windows (dev / explicit env only). Parent should send `false` in production builds.

```json
{ "type": "setRuntimeDiagnosticsEnabled", "enabled": true }
```

### `diagPing` (Commit 61)

RN WebView bridge RTT probe — harness replies with **`diagPong`** carrying the same `requestId` and `t0`.

```json
{ "type": "diagPing", "requestId": "uuid", "t0": 1710000000000 }
```

### `setRenderPreset` (Commit 56)

Apply a **named session preset** in one step: merges glyph/staff colors, `display.scale`, and `display.stretchForce` to match `src/session/tabThemePresets.ts`, then `api.updateSettings()`.

```json
{ "type": "setRenderPreset", "presetName": "listen" }
```

Allowed `presetName` values (case-insensitive): `listen`, `study`, `slow`, `play`. Any other string falls back to **`study`** (no harness error).

**Idempotency:** Sending the same preset again is safe (settings re-applied; no error).

**Fallback:** Unknown names normalize to `study` so production hosts never brick the score.

**Outbound ack:** After a successful apply, the harness posts:

```json
{ "type": "renderPresetApplied", "presetName": "study" }
```

(`presetName` is the **normalized** name.) The app may ignore this or use it for telemetry; `decodeTabMessage` in `types/tabMessage.ts` recognizes it.

**Interaction with `setTheme`:** `setRenderPreset` replaces the full preset table for that step. A later `setTheme` with partial `colors` can still override specific resource keys until the next `setRenderPreset`.

## Harness → parent

JSON string messages. Parse with **`decodeTabMessage`** from `types/tabMessage.ts`.

| `type` | Fields | When |
|--------|--------|------|
| `ready` | — | Once, after the **first** `renderFinished` event (initial layout; score may still be empty until `setScore`). |
| `renderPresetApplied` | `presetName: string` | After each successful `setRenderPreset` (normalized name). |
| `error` | `message: string` | AlphaTab errors, bad `setScore`, media handler errors, etc. |
| `position` | `positionMs: number` | Response to `getPosition`. |
| `songDetails` | `score: object` (see `SongScoreMeta` in `types/tabMessage.ts`), optional `requestId` | After each render when the score model changes, on demand via `getSongDetails`, or after a new `setScore`. |
| `songPlayback` | `masterBarIndex: number`, `sectionLabel: string \| null` | When playback cursor maps to a new bar or GP section label (deduped). |
| `noteEvent` | `midi: number`, `beat: number`, optional `fret`, `string` | Forwarded from AlphaTab MIDI playback events (debounced to <= 33Hz). |
| `soundFontLoad` | `status: loading \| loaded \| error`, optional `message` | Lifecycle signal from harness SoundFont preload path. |
| `runtimeDiagnostics` | `windowMs`, `driftMs`, `noteEventHz`, `renderFps`, optional `breachFlags` | Commit **61**: ~5s aggregated AlphaTab harness metrics (same shape as DOM path). |
| `diagPong` | `requestId`, `t0` | Commit **61**: echoed from `diagPing` for RN bridge latency. |

### Threshold sync (Commit 61)

Numeric **FAIL** gates used in `index.html` when building `breachFlags` **must stay aligned** with `RUNTIME_DIAG_THRESHOLDS` in [`src/constants/alphaTabRuntimeDiag.ts`](../../src/constants/alphaTabRuntimeDiag.ts) (`driftMsFail`, `noteEventHzFail`, `renderFpsFail`). The harness duplicates literals for the standalone page; after changing the TS constants, update the matching literals in `assets/alphatab-harness/index.html` (search for `RD_WINDOW_MS`, `drift >`, `hz >`, `rps >`) and any parallel checks in `components/AlphaTabWeb.web.tsx`.

### Native (`WebView`)

The script calls `window.ReactNativeWebView.postMessage(data)` when that object exists.

### Web / iframe

The script uses `window.parent.postMessage(data, '*')` when `parent !== window`. Tighten `targetOrigin` in production when the embed URL is fixed.

## Manual test (Chrome)

1. Open `index.html` from disk (`file://`) or serve the folder locally (**local server recommended** — some browsers restrict workers/CDN from `file:`).
2. Open DevTools → Console.
3. Optional: listen for replies:
   ```js
   window.addEventListener('message', (e) => console.log('harness →', e.data))
   ```
4. Paste a real `setScore` payload with valid GP5 base64 (generate from your pipeline or export a small `.gp5`).
5. Call `setAudioSrc` and verify the cursor follows external media timeline.

## Security / UX

- **Context menu** disabled (`contextmenu` → `preventDefault`).
- **Links** inside the score: clicks on external `a[href]` are **prevented** so the WebView does not navigate away.

## Related code

- Type definitions: `types/tabMessage.ts`
- WebView shell (native): `components/AlphaTabWebView.tsx`
- DOM / Expo web: `components/AlphaTabWeb.web.tsx` (via `components/TabViewport.web.tsx`)
