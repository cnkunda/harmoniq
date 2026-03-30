# AlphaTab harness (`index.html`)

Self-contained page loaded inside **React Native `WebView`** (mobile) or embedded in **web** (iframe / `postMessage`). **AlphaTab** is loaded from jsDelivr — **pinned** to `@coderline/alphatab@1.3.1` (do not switch to `@latest` in production without testing).

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

### `scrollToBar`

Scroll the notation so the given **master bar** is in view. Index is **0-based** (first bar = `0`), consistent with `LessonJSON` bar indexing used for SmartScroll in the app spec.

```json
{ "type": "scrollToBar", "barIndex": 4 }
```

If the score is not rendered yet (`boundsLookup` not ready), the harness posts **`error`** with a short reason. If the index does not exist, it posts **`error`**.

Implementation note: uses `boundsLookup.findMasterBarByIndex` and `uiFacade.scrollToY` (alphaTab 1.3.1).

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
| `error` | `message: string` | AlphaTab errors, bad `setScore`, invalid `scrollToBar`, etc. |

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
5. Call `scrollToBar` with an index that exists in that score.

## Security / UX

- **Context menu** disabled (`contextmenu` → `preventDefault`).
- **Links** inside the score: clicks on external `a[href]` are **prevented** so the WebView does not navigate away.

## Related code

- Type definitions: `types/tabMessage.ts`
- WebView shell (later commit): `components/AlphaTabWebView.tsx`
- DOM / web (later commit): `components/AlphaTabWeb.tsx`
