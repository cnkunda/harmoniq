# Harmoniq — Product Requirements Document & Roadmap

**Document purpose:** Single source of truth for product vision, scope, scoring strategy, release gates, and roadmap. It consolidates [PRODUCT_SOLO_PLATEAU.md](./PRODUCT_SOLO_PLATEAU.md), [E2E_DEMO.md](./E2E_DEMO.md), [SCORING.md](./SCORING.md), and the build specification in [README.md](../README.md). Engineering commit order and granular tasks remain in [PRIORITIES.md](../PRIORITIES.md).

**Last updated:** 2026-04-19

---

## 1. Executive summary

**Harmoniq** is an AI-powered, **song-first** guitar practice companion for **React Native + Web** (iOS, Android, browser). The core promise: *pick up your guitar, open the app, and play something that sounds musical within about twenty minutes — without a grindable curriculum, streaks, or generic leveling.*

The product is intentionally **narrow**: it targets guitarists who are **past absolute basics** and want **lead playing that sounds musical** — phrasing, timing, bends, and vocabulary that connects across chord changes — not abstract drills or mass-market onboarding volume.

Delivery is anchored in a repeatable session loop (**Listen → Study → Slow → Play → Review**) built around **real tracks** the learner chooses (YouTube or upload), with stems, tabs, lyrics alignment, coaching, and **confidence-aware scoring** so feedback stays honest without becoming punitive.

---

## 2. Problem, audience, and positioning

### 2.1 Who it is for

Harmoniq serves two adjacent audiences on the same path:

| Segment | Situation |
|--------|-----------|
| **Lead-building** | Comfortable with chords and rhythm; **not yet soloing expressively**. Investing in scales, boxes, and patterns as **scaffolding**: clean motion, predictable landings, repeatable ideas. |
| **Mechanical solo plateau** | Already improvises, but lines feel **rushed or scalar**; wants **feel** on **real sections** they care about, not endless abstract drills. |

Shared traits:

- Want feedback on **real music** (sections, stems, phrases), not only drills.
- May be **pre-expressive-solo** — patterns are **tools**, not the destination.
- Often find mass-market tutor apps optimized for onboarding volume unsatisfying; **gamification becomes noise**.

**Reference taste profile (from README):** Intermediate guitarist drawn to expressive players (e.g. John Mayer, Tommy Emmanuel, Jack White) — not necessarily “speed first.”

### 2.2 What “success” means (musical outcomes, not XP)

Success is measured in **musical outcomes**:

| Dimension | Meaning in Harmoniq |
|-----------|---------------------|
| **Early lead work** | Clean motion, predictable landings, simple motivic repetition — judged musically before chasing advanced nuance. |
| **Phrasing** | Breathing, rests, intentional landing notes — not only faster scalar runs. |
| **Time feel** | Placement relative to the pocket (rush vs lay back), not metronome clicks alone. |
| **Pitch control** | Bends and vibrato that sound intentional under pressure. |
| **Harmonic connection** | Phrases that acknowledge the progression — not endless noodling in one box. |

Technical drills exist to serve **solo-shaped work on real tracks first**.

### 2.3 Positioning

- **Not** a Yousician-style breadth-first leveling product.
- **Not** driven by streaks / achievements as primary retention.
- **Is** an **adaptive practice companion**: listens, infers where the player is, and surfaces **one high-value focus** per session, tied to material they care about.

### 2.4 Non-goals

- Breadth-first leveling for casual mass acquisition.
- Heavy streak / achievement loops as the primary retention driver.
- One-size onboarding that assumes everyone starts from zero.
- (From README v1 boundary) User accounts / cloud sync, social sharing, chord dictionary / rhythm curriculum as core product, multi-instrument focus, subscriptions (until explicitly in scope), Spotify integration **as shipped v1 core** — note near-term roadmap may propose Spotify “listening mode” as a planned initiative (see §10).

---

## 3. Product principles

These principles govern tradeoffs (from README — summarized):

1. **Feel over score** — Teach musicality; frame feedback musically (“rushing the phrase end”) not robotically (“wrong note”).
2. **Song-first** — Sessions anchor to a real song the user chose; avoid abstract-only exercises as the default path.
3. **No guilt, no schedule** — No streak guilt; meet the player where they are today.
4. **One thing at a time** — Prefer one sharp observation over overwhelming lists.
5. **The app disappears** — Fewer taps, fewer decisions, more playing.
6. **Real-time is sacred** — Live play stays on-device; latency-sensitive paths must not depend on network during performance.
7. **Nodes move slowly** — Skill nodes update gradually (weighted averages + spaced repetition) so improvement feels credible, not like point farming.

---

## 4. Visual and UX direction (requirements level)

The product should feel **warm, analog, handcrafted** — workshop / jazz-club lighting, not neon SaaS or mobile-game UI.

| Area | Requirement |
|------|-------------|
| **Palette** | Deep walnut / espresso backgrounds; amber primary; cream secondary; muted terracotta (miss) and warm sage (hit). |
| **Typography** | Display: evocative serif; body: warm sans; tab / note names: monospace — exact families and tokens live in design system / README. |
| **Texture & motion** | Subtle grain; soft cards; slow, intentional animation — no bouncy gamified motion. |
| **Icons** | Consistent icon set per implementation (see README / DESIGN_SYSTEM). |

**Release gate:** Coherent wood / amber / cream direction on Home + session flows (see §9.3).

---

## 5. Core user journeys

### 5.1 Cold start → first session

1. **Onboarding** (first launch): mic permission, **three placement phrases** (uses scoring — see §8), results that seed skills; optional coach copy (Claude when configured).
2. **Home** after onboarding: contextual greeting; **Add Song** or demo paths.
3. **Add Song**: YouTube URL or web upload → async **analyze** job → lesson saved locally.
4. **Session**: **Listen → Study → Slow → Play → Review**; **Review** runs **score** when backend is available.

**Offline / demo:** With an empty library, bundled **demo lesson** must play without API (see E2E Phase 1 checks).

### 5.2 The five-step session loop (product requirements)

| Step | Purpose | Key requirements |
|------|---------|------------------|
| **Listen** | Context and sound | Isolated **guitar stem**, structure **section chips**, transport, loop, speed, **stem mixer** (guitar / bass / drums / vocals / piano / other per pipeline), optional smart metronome; coach note from analysis. |
| **Study** | Understand the phrase | **AlphaTab** (WebView on native, DOM on web); **Full / Skeleton** toggle; scale overlay; lyrics timeline when available; capo suggestion; annotations; low-confidence labeling when analysis is uncertain. |
| **Slow** | Controlled repetition | Slowed playback with pitch correction; **SmartScroll** driven by `bar_timestamps` / playback position; highlight difficult bars. |
| **Play** | Perform with feedback | Mic on; mixer defaults suitable for play-along; **real-time pitch** indicator; recording for scoring; silence / Done ends capture. |
| **Review** | Integrate feedback | Coach paragraph; **phrasing visualizer** (user vs reference timing); **Run score**; export MIDI / MusicXML when tab data allows; **Do it again** on failure. |

### 5.3 Practice planning on Home

- Inputs combine **declared** preferences (taste quiz, Settings — style focus, etc.) and **inferred** signals (sessions, skill nodes, weak areas).
- When the learner has **multiple analyzed lessons**, Home should surface a richer **practice path**: **warmup → technique → song/section → free jam** (four steps). The client sends device-persisted **`library_lessons`** on **`POST /practice/plan`** so plans stay correct after backend restart or empty in-memory job store (**embedded `LessonJSON`**).

### 5.4 Jam mode (optional parallel journey)

- Passive exploration over bundled backing loops (and optional AI instrumental when configured).
- Mic-based pitch-class style mapping; **no competitive scoring** in the jam surface — “lit candle,” not dashboard.
- **Stop & Save** persists vocabulary snapshot; **jam-score** may fail gracefully while still saving snapshot per app behavior.

### 5.5 Library, progress, settings

- **Library:** Lessons and saved licks; session history access; **Export MIDI** where GP5/tab data exists.
- **Progress:** Skill graph, journal, jam vocabulary panel — **no XP / level badges** as core framing.
- **Settings:** Guitar, tuning, practice style weighting, audio, coach voice, data export/clear.

---

## 6. Functional scope

### 6.1 In scope for v1 (summary)

Aligned with README “V1 Scope Summary”:

- Onboarding placement; Home with spaced-repetition-driven suggestions; full **five-step** session loop; web + native clients.
- Analyze pipeline: YouTube + upload; **htdemucs_6s** guitar stem; librosa structure; Whisper lyrics; basic-pitch → GP5; skeleton/alternate tabs when confidence allows; Claude coach strings when API present.
- AlphaTab integration with shared message contract; SmartScroll via timestamps; smart metronome; section chips; mixer; pitch on device for play path.
- Review phrasing visualization; MIDI export; lick library + drill/transpose concepts as specified in README.
- Jam mode with bundled beds + inference + summaries.
- Local-first persistence (**SQLite** / **IndexedDB**); caching by audio hash + pipeline version.
- Error copy that respects the README error-state table — **no raw stacks** in UI.

### 6.2 Explicitly out of v1 (README)

Accounts/sync, social, chord dictionary as core curriculum, multi-instrument, payments, offline **analysis** (pipeline needs network/backend), note-sequence SmartScroll (v1 uses timestamp sync).

### 6.3 Known honest limitations (demo / release communications)

| Area | Limitation |
|------|------------|
| Pipeline | Full Demucs + Whisper + basic-pitch is heavy; first runs may download weights; Windows/WSL may need extra setup. |
| Stub vs real | Some revisions may return stub lessons for fast UI paths; tabs may be placeholders. |
| Expo Go | May lack full native audio/pitch — dev builds for parity. |
| Web mic | Requires **HTTPS** or **`http://localhost`**. |
| Coach | Claude requires API key; fallback copy acceptable. |
| Offline | New analyzes need network; library/session data is device-local. |

---

## 7. Technical architecture (PRD-level)

Detail stays in README and backend README; at PRD level the system comprises:

| Layer | Responsibility |
|-------|----------------|
| **Client** | Expo Router app; Zustand; local DB; AlphaTab harness; expo-av / Web Audio; `react-native-audio-api` + shared pitch hook on native; Jam and session UX. |
| **Backend (FastAPI)** | `/analyze` jobs; `/score`; `/jam-score`; `/export`; `/practice/plan`; optional coach endpoints; pipeline workers. |
| **Analysis pipeline** | yt-dlp or upload normalize → Demucs **6-stem** → analysis → Whisper → basic-pitch → GP5 → coach enrichment → **LessonJSON** with **confidence** fields. |

**Real-time rule:** Pitch estimation during play stays **on-device** — no network in the hot path.

---

## 8. Scoring, reliability, and progress

### 8.1 Philosophy

Harmoniq differentiates by **non-judgmental coaching** while making **reliability explicit**. Minimum bar: every scoring surface carries **confidence + reliability signals** so users are not misled by low-quality takes. Avoid opaque score jumps and binary good/bad framing.

### 8.2 Delivery areas (always-on behaviors)

Scoring v2 reliability and diagnostics ship **without feature flags**. Phases describe delivery focus and QA, not toggles:

| Phase | Focus | QA signals |
|-------|-------|------------|
| **1 — Jam first** | Jam reliability envelope + tags in API; persist tags in snapshots | Backend jam tests; “Last jam diagnostics” in UI; map persistence |
| **2 — Session score contract** | Diagnostics on `/score`; thread into Review → Progress | Backend score tests; snapshots + node updates; low-signal flags |
| **3 — Onboarding robustness** | Winsorized + confidence-weighted placement aggregation; coach receives confidence | Unit tests for aggregation; onboarding UI shows confidence when applicable |
| **4 — Progress explainability** | Confidence-aware SM-2 updates; Progress policy copy | SM-2 tests; fixed explainability copy (not per-session dynamic blobs on rows) |

### 8.3 Operational calibration

**Weekly review** (process):

1. Sample recent Jam + `/score` payloads from staging / anonymized logs.
2. Track reliability confidence distribution, low-signal rate (`signal_low`, `voiced_sparse`), jam sparse-map rate (`map_sparse`).
3. **Drift rule:** If any KPI moves **>20% week-over-week**, review thresholds, mic guidance, and `scoring_constants.py`.

### 8.4 Competitive benchmark matrix (intent)

| Surface | Harmoniq direction | Notes |
|---------|-------------------|--------|
| Onboarding | Winsorized + confidence-weighted placement | Stability under outlier phrases |
| Session review | Core metrics + **reliability envelope** + diagnostics | Transparency without harsh pass/fail |
| Jam | Tagged reliability + sparse guardrails | Honest vocabulary maps |
| Progress | Multi-signal SM-2 damping | Low-confidence runs should not fake progression |
| Explainability | Coachable, specific copy | Avoid Yousician-style stars / binary failure as primary language |

### 8.5 Automated testing (CI)

- **Backend:** `tests/test_jam_score.py`, `tests/test_score.py`.
- **Client:** Vitest for onboarding aggregate, SM-2, session progress signals.

---

## 9. Quality gates and release criteria

### 9.1 End-to-end demonstration checkpoints

A new developer or QA machine should complete the stack without tribal knowledge. Minimum **proof**:

| # | Checkpoint |
|---|------------|
| 1 | Backend `GET /health` OK |
| 2 | App loads → **Home** after onboarding |
| 3 | **Add Song** completes analyze and saves a lesson |
| 4 | **Session** completes all five steps; **Review** can **Run score** (backend up) |
| 5 | Optional: **Jam** on web with mic allowed |
| 6 | **Review** / **Library** export MIDI (and MusicXML from Review) via **`POST /export`** when GP5 exists |
| 7 | **Home** “Your practice path” shows **four** steps when **≥2** analyzed songs exist; `library_lessons` sent to **`POST /practice/plan`** |

**Prerequisites:** Node LTS, Python 3.11+, ffmpeg, Git; `EXPO_PUBLIC_API_URL` correct for LAN vs localhost; dev build for native mic parity.

### 9.2 v1 release checklist (engineering + product)

**Build quality**

- `npm run lint` clean; `npm test` clean; `pytest` clean in `backend/` when shipping backend.
- No known **P0** cold-start crashes on web + one native target.

**Behavior**

- Backend health + analyze completes (or **documented stub** acceptable for tag).
- Onboarding → Home; Add Song → lesson usable in session.
- Home **four-step** plan with **≥2** library songs.
- Full session navigable; Review scoring when backend available.

**Product / design**

- Error copy aligns with README / manual QA — no raw stacks in UI.
- Visual direction coherent (wood / amber / cream).

**Phase 5 “feel real”**

- Complete **MANUAL_QA.md** gates for session realism; **if external-media sync fails without waiver, stop** release.

### 9.3 Sign-off

Release requires explicit engineering + product/design sign-off or documented waivers.

---

## 10. Product roadmap (strategic)

### 10.1 Near-term engineering themes (from PRIORITIES.md)

Engineering executes in commit order in **PRIORITIES.md**. Planned product-facing initiatives listed there include:

| Initiative | User value |
|------------|------------|
| **Ghost player** | Record a reference “ghost” take; play along quietly; compare on Review. |
| **Mood-adaptive session** | Daily mood influences plan intensity and coach tone — human state in the loop. |
| **Listening mode + Spotify** | Passive listening with external playback bridged to tab follow (Premium / constraints TBD in spec). |

These extend the core loop without replacing **song-first** positioning.

### 10.2 Suggested sequencing narrative (README build order)

Historical macro phases from README remain a valid **conceptual** ordering for greenfield teams:

1. Pipeline POC → GP5 visible in AlphaTab.
2. Real-time pitch prototype → timing vs beat grid.
3. Core session UI (minimal loop).
4. Skill model + adaptive Home.
5. Jam, lick library, Settings polish + coach tuning.

Harmoniq’s repo has advanced past early phases; use this as onboarding context, not as a second source of task order.

### 10.3 Longer-term (post-v1) — PRD placeholders

Items marked **not in v1** in README (accounts, sync, social, payments, richer SmartScroll, etc.) require separate PRD revision when prioritized.

---

## 11. AI coach (requirements)

- **Tone:** Warm, plain English; musical judgment; avoid “wrong note”; one actionable observation; no generic praise openers; under four sentences unless a spec says otherwise for a surface.
- **Uses:** Section coach notes, study explanations, session review, jam summaries — driven by structured metrics and user context.
- **Settings:** Coach voice variants (Encouraging / Direct / Mixed) adjust behavior.

Full prompt fragments and API model choice live in README.

---

## 12. Related documents

| Document | Role |
|----------|------|
| [README.md](../README.md) | Full build spec: screens, schemas, endpoints, pipeline detail, AI prompts, v1 lists. |
| [PRIORITIES.md](../PRIORITIES.md) | Engineering roadmap — commits, acceptance criteria. |
| [E2E_DEMO.md](./E2E_DEMO.md) | Step-by-step cold start, troubleshooting, dry-run log. |
| [SCORING.md](./SCORING.md) | Scoring rollout detail, benchmarks, local validation commands. |
| [PRODUCT_SOLO_PLATEAU.md](./PRODUCT_SOLO_PLATEAU.md) | Compact product anchor (audience + implications). |
| [MANUAL_QA.md](./MANUAL_QA.md) | Phase 5 realism, error states, stems/pitch QA. |
| [DESIGN_SYSTEM.md](../DESIGN_SYSTEM.md) | UI implementation reference. |

---

## 13. Document governance

- **PRD changes** should be reviewed when v1 scope, scoring contract, or positioning shifts.
- **README** remains the detailed functional spec for implementers; **PRIORITIES** owns task ordering.
- Keep **E2E_DEMO** procedural truth for “how to run the demo”; this PRD captures **why** and **what must be true** at ship.
