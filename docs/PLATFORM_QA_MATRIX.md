# Platform QA matrix (AlphaTab & Play)

Short reference for **web vs native** behavior around the tab surface and Play session. Full manual steps stay in `docs/FEEL_REAL_QA.md` (including B2/E1).

| Area | Web (Expo web / DOM) | Native (WebView harness) |
|------|------------------------|---------------------------|
| AlphaTab host | `AlphaTabWeb` (DOM) | `AlphaTabWebView` → `assets/alphatab-harness/index.html` |
| `noteEvent` bridge | Same `types/tabMessage.ts` contract | Same contract; `NOTE_EVENT_MIN_MS` in harness should match `ALPHA_TAB_NOTE_EVENT_MIN_INTERVAL_MS` (`src/constants/alphaTabBridge.ts`) |
| Stem + tab sync | `SessionStemAndTab` | Same component; WebView messaging vs `postMessage` to window |

**Harness version:** When changing `assets/alphatab-harness/index.html`, note the commit or a short hash in the PR so testers know the WebView bundle changed.

**Automated smoke:** Vitest covers `alphaTabBridge` pacing and `encodeTabMessage` / `decodeTabMessage` (`src/constants/alphaTabBridge.test.ts`, `src/tabMessage.codec.test.ts`).
