# AlphaTab harness (`index.html`)

Self-contained page loaded inside **React Native `WebView`** (mobile) or embedded in **web** (iframe / `postMessage`). **AlphaTab** is loaded from jsDelivr — **pinned** to `@coderline/alphatab@1.6.1` (do not switch to `@latest` in production without testing).

SoundFont setup in this harness:

- SoundFont URL is currently pinned to `GeneralUser.sf2` (see `assets/soundfonts/SOURCES.md`)
- Harness emits `soundFontLoad` status messages so app surfaces can show loading feedback

## Visual defaults (Harmoniq README)

| Element | Hex |
|--------|-----|
| Page background | `#2B1D0E` |
| Note heads / primary glyphs | `#F0DEB4` |
| Staff lines | `#5C4535` (per `staffLineColor`; matches wood palette) |

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

## Harness → parent

JSON string messages. Parse with **`decodeTabMessage`** from `types/tabMessage.ts`.

| `type` | Fields | When |
|--------|--------|------|
| `ready` | — | Once, after the **first** `renderFinished` event (initial layout; score may still be empty until `setScore`). |
| `error` | `message: string` | AlphaTab errors, bad `setScore`, media handler errors, etc. |
| `position` | `positionMs: number` | Response to `getPosition`. |
| `noteEvent` | `midi: number`, `beat: number`, optional `fret`, `string` | Forwarded from AlphaTab MIDI playback events (debounced to <= 33Hz). |
| `soundFontLoad` | `status: loading \| loaded \| error`, optional `message` | Lifecycle signal from harness SoundFont preload path. |

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
