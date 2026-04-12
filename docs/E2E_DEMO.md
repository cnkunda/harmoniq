# End-to-end demo — cold start to full session

This document is the **kill switch** for v1: a new developer (or QA on a second machine) should be able to run the stack and complete a **Listen → Study → Slow → Play → Review** session without tribal knowledge.

**Companion docs:** [backend/README.md](../backend/README.md), root [README.md](../README.md), [ERROR_QA.md](./ERROR_QA.md), [FEEL_REAL_QA.md](./FEEL_REAL_QA.md) (Phase 5 realism gate).

---

## 0. What you are proving

| # | Checkpoint |
|---|------------|
| 1 | Backend answers `GET /health` |
| 2 | App loads and reaches **Home** (after onboarding on first launch) |
| 3 | **Add Song** completes analyze and saves a lesson |
| 4 | **Session** runs all five steps; **Review** can call **Run score** (backend up) |
| 5 | Optional: **Jam** starts on web with mic allowed |

---

## 1. Prerequisites

Install on the host machine:

| Tool | Notes |
|------|--------|
| **Node.js** | LTS (matches Expo 54); `node -v` |
| **npm** | Comes with Node |
| **Python 3.11+** | Backend; 3.12 OK |
| **ffmpeg** | On `PATH`; `ffmpeg -version` |
| **Git** | Clone this repo |

**Physical device / simulator**

- **Web:** Chrome or Edge; mic tests need **`http://localhost`** or **HTTPS** (see README).
- **iOS / Android:** For **live pitch** and some mic paths you need a **development build** with native modules (e.g. `react-native-audio-api`), not only Expo Go — see README *Mic / real-time pitch*.

---

## 2. Repository and branches

```bash
git clone <your-remote-url> harmoniq
cd harmoniq
```

Use `master` (or the release branch you are tagging). No submodule steps are required for the default demo.

---

## 3. Backend (FastAPI)

From **`backend/`**:

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -U pip
pip install -e .
```

Environment:

```bash
copy .env.example .env   # Windows
# cp .env.example .env   # Unix
```

- Set **`ANTHROPIC_API_KEY`** if you want coach / Claude-backed copy on analyze or onboarding (optional for stub paths; some routes fall back locally if the key is empty and the server handles it).
- **`DATA_DIR`** defaults to `./data` (gitignored).

Start the API (bind all interfaces so phones on LAN can reach you):

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Verify:**

```bash
curl -s http://127.0.0.1:8000/health
```

Expect: `{"status":"ok"}` (or equivalent).

**Smoke analyze (optional, no app):**

```bash
curl -s -X POST http://127.0.0.1:8000/analyze -H "Content-Type: application/json" -d "{\"youtube_url\":\"https://www.youtube.com/watch?v=REPLACE_WITH_VIDEO_ID\"}"
```

Poll `GET /analyze/{job_id}` until `status` is `complete` or `failed`.  
Forced failure hook for UI testing: POST body `{"youtube_url":"force_error"}` (see [backend/README.md](../backend/README.md)).

> **Heavy pipeline:** First real run may download Demucs / Whisper weights and take a long time. For a **fast UI-only** pass, your backend revision may still serve a **stub** lesson — check [backend/README.md](../backend/README.md) for current behavior.

---

## 4. Frontend (Expo)

From **repo root**:

```bash
copy .env.example .env   # if you do not already have .env
```

Set **`EXPO_PUBLIC_API_URL`** to the machine that runs the API:

| Scenario | Example value |
|----------|----------------|
| Web + backend on same PC | `http://localhost:8000` |
| Phone on Wi‑Fi, backend on PC | `http://192.168.x.x:8000` (PC LAN IP) |

Install and start:

```bash
npm install
npx expo start
```

Then:

- **Web:** press `w` or run `npx expo start --web`
- **iOS:** `i` (Xcode / Simulator) or `npx expo run:ios` for dev client
- **Android:** `a` or `npx expo run:android`

**Sanity check:** Open the app; you should not see permanent red errors in Metro. If API calls fail, confirm `EXPO_PUBLIC_API_URL` matches where `uvicorn` is listening and that no firewall blocks port **8000**.

---

## 5. First launch — onboarding

On a **fresh install**, [app/index.tsx](../app/index.tsx) sends users to **`/onboarding`** until completion.

1. Complete **mic** permission and **three phrase** screens (needs **`POST /score`** for scoring).
2. **Results** seeds skills and may call the coach endpoint; offline fallback copy is OK.
3. Land on **Home** (`/(tabs)`).

**Developers repeating the demo:** clear app storage / uninstall, or reset the onboarding flag in app prefs (implementation: `PREF_ONBOARDING_COMPLETE` in [src/db/schema.ts](../src/db/schema.ts)) via your platform’s storage tools.

---

## 6. Add a song (analyze)

From **Home** → **Add Song**.

**Option A — YouTube (recommended name-check: “Gravity”-style studio recording)**  
Paste a **full** watch URL, e.g. `https://www.youtube.com/watch?v=...` (use a video you have rights to test with; avoid geo-blocked or DRM-heavy edge cases).

**Option B — Upload (web)**  
Use the drop zone with a license-safe WAV/MP3 (long enough for your backend’s minimum duration).

Wait until the lesson is saved and you return to **Home**. If analyze fails, use [ERROR_QA.md](./ERROR_QA.md) to interpret the banner.

---

## 7. Full practice session

From **Home** → **Start session** (or navigate the session entry your build exposes — default is **Listen**).

Complete the loop in order:

1. **Listen** — stems and transport  
2. **Study** — tab, lyrics, optional low-confidence banner  
3. **Slow** — slowed practice  
4. **Play** — metronome / capture (mic permission)  
5. **Review** — **Run score** (requires backend **`POST /score`**)

**Expected:** Review shows scores or a README-aligned error with **Do it again** if scoring fails ([src/errors/mapErrorToUi.ts](../src/errors/mapErrorToUi.ts)).

---

## 8. Optional — Jam (web)

**Jam** uses the browser mic for pitch histograms. Allow mic for the origin; use **localhost** or **HTTPS**. Start jam → **Stop & Save** ( **`POST /jam-score`** may fail gracefully; snapshot still saves per app behavior).

---

## 9. Known limitations (v1 demo honesty)

Document these when demoing so expectations stay aligned:

| Area | Limitation |
|------|------------|
| **Pipeline** | Full Demucs + Whisper + basic-pitch is heavy; Windows/WSL may need extra setup ([backend/README.md](../backend/README.md)). |
| **Stub vs real** | Backend may return stub `LessonJSON` depending on revision; tabs may be placeholders. |
| **Expo Go** | May not expose all native audio / pitch APIs; use dev builds for parity. |
| **Web mic** | Blocked on non-secure origins except localhost. |
| **Coach** | Claude requires `ANTHROPIC_API_KEY`; some flows use fallback copy. |
| **Offline** | New analyzes need network; local library/session data is device-local. |

---

## 10. Release checklist — go / no-go before “v1 complete”

Use this as a **sign-off gate** (product + engineering). All **must pass** for a tagged v1 candidate unless explicitly waived in writing.

### 10.1 Build and quality

| Item | Owner | Pass |
|------|--------|------|
| `npm run lint` (tsc) clean | Eng | [ ] |
| `npm test` (Vitest) clean | Eng | [ ] |
| `pytest` clean in `backend/` (if shipping backend with this tag) | Eng | [ ] |
| No known **P0** crashes on cold start (web + one native target) | Eng/QA | [ ] |

### 10.2 E2E behavior (this doc)

| Item | Pass |
|------|------|
| Backend health + analyze completes (or documented stub acceptable for tag) | [ ] |
| Onboarding to Home | [ ] |
| Add Song to lesson on Home / session | [ ] |
| Session all five steps navigable | [ ] |
| Review scoring works when backend up | [ ] |

### 10.2a Phase 5 “Feel Real” manual gate

Before declaring **Phase 5** realism shippable, complete the PASS/FAIL/WAIVE grids in **[FEEL_REAL_QA.md](./FEEL_REAL_QA.md)** (sync, notation highlight, soundfont, coach, play accuracy, metronome, loop precision, Study, Jam). **If Commit 45 sync checks fail without waiver, stop** — see the STOP rule at the top of that doc.

### 10.3 Product / design

| Item | Pass |
|------|------|
| Error copy matches README table (no raw stacks in UI) — see [ERROR_QA.md](./ERROR_QA.md) | [ ] |
| Visual direction coherent (wood/amber/cream, typography) on Home + session | [ ] |

### 10.4 Sign-off

| Role | Name | Date | Go / No-go |
|------|------|------|------------|
| Engineering | | | |
| Product / design | | | |

**No-go** = stop; file issues, fix or document waivers, re-run section 10.

---

## 11. Dry-run validation log (maintainers)

Record each full validation on a **second machine** or fresh user account so the “without asking questions” criterion is real.

| Date | Machine OS | Web / iOS / Android | Backend rev / app rev | Result | Notes |
|------|------------|---------------------|------------------------|--------|-------|
| 2026-04-09 | Windows 10 | Web + lint/test | workspace | Pass | Automated `tsc` + Vitest on dev PC; human cross-machine run still recommended |

---

## 12. Troubleshooting quick hits

| Symptom | Check |
|---------|--------|
| App cannot analyze | `EXPO_PUBLIC_API_URL`, backend running, CORS not blocking (FastAPI default is permissive for local dev) |
| Phone cannot reach PC API | Same Wi‑Fi, firewall, use LAN IP not `localhost` on device |
| Mic never works on web | HTTPS or localhost, browser permission, not blocked in site settings |
| Analyze hangs | Backend logs, disk space, first-time model download |

For error banners, see [ERROR_QA.md](./ERROR_QA.md).
