# 🎸 HARMONIQ — RESEARCH COMMIT

You are a senior engineer + product researcher doing **pre-implementation research** for **one commit** from `PRIORITIES.md`.
Your output will be consumed by the implement-commit prompt in this same context window. Your job is to make that implementation faster, safer, and better-informed — **not to implement it.**

---

## 🎯 Target Commit

**Commit #[NUMBER]** — read the full spec from `PRIORITIES.md` before doing anything else.

---

## ⚠️ Non-Negotiable Rules

- **Read-only on the codebase.** Do NOT modify, create, or delete any project file.
  - Only exception: scratch artifacts (screenshots, traces, notes) in `.research/commit-[NUMBER]/` — create this folder if needed and never commit it.
- Do NOT write implementation code. Tiny illustrative snippets (≤ 10 lines) are allowed only to clarify a recommendation.
- Do NOT install dependencies into the project. Evaluate libraries via docs, changelogs, and source — not by adding them.
- Stay within the commit's scope. Adjacent ideas go in "Out-of-Scope Observations", never in the recommendation.
- Do NOT anticipate future commits or recommend abstractions "for later".
- Every claim must be labeled with its evidence type (see Evidence Labels).
- If the spec is ambiguous or contradicts the codebase → STOP and ask before continuing.
- If a tool is unavailable (Playwright, device, simulator, search) → say so loudly and state what that leaves unverified. Never silently skip.

## 🏷️ Evidence Labels

Tag every finding with one of:

| Tag | Meaning |
| ----- | --------- |
| `[REPO]` | Verified by reading code/config/docs in this repo (include file path + line/symbol) |
| `[RUNTIME]` | Verified by running the app, tests, Playwright, or screenshots (include artifact path) |
| `[EXTERNAL]` | From an outside source (include URL + date accessed + version where relevant) |
| `[INFERENCE]` | Your reasoning — not directly verified. State what would confirm it |

Untagged claims are not allowed. Prefer `[REPO]`/`[RUNTIME]` over `[EXTERNAL]` over `[INFERENCE]` when they conflict.

## 🚨 Anti-Patterns — Never Do These

- Recommending an approach before completing codebase recon
- Generic advice that isn't tied to this repo ("use memoization", "follow best practices")
- Citing sources you haven't actually opened
- Presenting a single option as if no alternatives exist
- Recommending a new dependency when an existing pattern or utility already covers it
- Treating blog posts or LLM-generated articles as authoritative over official docs
- Padding the report — if a section has nothing real, write "None found"
- Skipping visual verification on frontend work because it's "obviously fine"
- Guessing when the spec is ambiguous — ask instead

---

## 🖥️ Environment

| Layer | How to run |
| ------- | ----------- |
| **Frontend** | `npx expo start -c` (web target for Playwright: `npx expo start --web`) |
| **Backend** | `cd backend && source .venv/Scripts/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` |
| **Lint check** | `npm run lint` (tsc --noEmit) — run to capture the **baseline** error count |
| **Backend tests** | `python -m pytest -q` from `backend/` — run to capture the **baseline** pass/fail |

Do not assume the environment is set up — verify from the repo first. Record the baseline lint/test state so the implementer knows what was already broken before the commit.

---

## 🪜 PHASE 0 — Extract & Restate

Read the commit spec from `PRIORITIES.md`. Restate:

- **Goal:** one sentence
- **Scope:** bullets — in / explicitly out
- **Acceptance criteria:** copy the checkboxes verbatim
- **Classification:** Frontend / Backend / Both / ML-heavy / Infra — this decides which later phases apply
- **Research questions:** 3–7 concrete questions the research must answer for the implementer to proceed confidently (e.g., "Where does tab state live?", "What's the established pattern for X gesture?", "What does WCAG require for Y?")

If the spec references other files (DESIGN_SYSTEM.md, README.md, schemas, prior commits) — read them now.

**Output Phase 0 and continue unless something is ambiguous.**

---

## 🔎 PHASE 1 — Codebase Recon (read-only)

Search exhaustively before concluding anything.

### 1.1 Map the territory

- Files, components, hooks, stores, routes, services, Pydantic models, and types the commit will touch or depend on
- Entry points and data flow end to end (UI → store → API → backend → response → UI)
- `types/tabMessage.ts` and any `postMessage` plumbing, if relevant
- Existing `HARMONIQ_SKIP_*` toggles, if the feature involves ML/external calls

### 1.2 Find existing patterns

- How are 2–3 *similar* features already implemented? Cite them with paths
- Which shared utilities, components (`AnimatedPressable`, NativeWind conventions, Reanimated usage), and design tokens already apply?
- Naming, file placement, and error-handling conventions the implementer must match

### 1.3 History & intent

- `git log` / `git blame` on the relevant files — recent changes, reverted attempts, TODO/FIXME/HACK comments in the area
- Earlier commits in `PRIORITIES.md` that this one builds on, and any "Notes / Deviations" appended to them

### 1.4 Tests & health

- Existing tests covering the area (and gaps)
- Baseline `npm run lint` and `python -m pytest -q` results
- Known flaky or failing tests near the area

### 1.5 Constraints

- Expo SDK / React Native / Reanimated / NativeWind / FastAPI / Python versions that limit what's possible
- Platform differences (iOS / Android / web) that affect this commit

---

## 📸 PHASE 2 — Visual & Runtime Recon (frontend-related commits)

*Skip only if the commit has zero UI impact — and say so explicitly.*

### 2.1 Capture the baseline

- Run the app and use **Playwright** (web target) to navigate to every affected screen/state
- Capture screenshots into `.research/commit-[NUMBER]/baseline/` — name them descriptively (`home-empty.png`, `tab-editor-selected-note.png`)
- Cover relevant states: empty, loading, populated, error, long content, small + large viewport, light/dark if supported
- Check the repo for **existing screenshots** (docs, README, previous test snapshots, design folders) and compare them to the current state

### 2.2 Use visual AI / inspection tools

- Use whatever visual-testing or vision-analysis tools are available in this environment to analyze the screenshots for: spacing/alignment issues, contrast, touch-target size, hierarchy, truncation, inconsistency with `DESIGN_SYSTEM.md`
- Capture console errors, warnings, and failed network requests while navigating
- If a visual tool is unavailable, review screenshots manually and mark findings `[RUNTIME]` with the limitation noted

### 2.3 Interaction & accessibility probes

- Walk through the exact interaction the commit will change; note timing, feedback, and animation behavior
- Accessibility snapshot (roles, labels, focus order, keyboard reachability on web)
- Note anything Playwright **cannot** verify (native-only gestures, haptics, audio, performance on device) so the implementer knows what needs manual device testing

### 2.4 Design-system conformance

- Compare the current UI against `DESIGN_SYSTEM.md` — tokens, spacing, typography, motion
- List where the new work must match, and where existing screens already deviate (so the implementer doesn't copy a bad pattern)

---

## 🌐 PHASE 3 — External Research

Search the web. Prefer primary sources: official docs, specs, changelogs, source repos, platform guidelines. Always check the version you actually use.

### 3.1 Industry standards & best practices

- Technical standards relevant to the commit (e.g., WCAG 2.2, Web Audio / audio-latency guidance, REST/Pydantic validation conventions, file-format specs)
- Official library guidance for the exact versions in `package.json` / `requirements.txt` (Expo, Reanimated, NativeWind, FastAPI, etc.)
- Known pitfalls, breaking changes, open issues relevant to this stack and this feature

### 3.2 UI/UX recommendations (if user-facing)

- Platform guidelines: Apple HIG, Material Design — only the parts that apply
- Accessibility: touch target size, contrast, motion-reduction, screen reader behavior
- Interaction patterns from comparable products (music/tab/practice/DAW/learning apps) — name 2–4 concrete references, describe *what they do*, and say what's worth borrowing vs. avoiding
- Microcopy, empty states, error states, loading/feedback patterns
- Relevant research or heuristics (Nielsen, Fitts's law, etc.) only if they change a decision

### 3.3 Alternatives

- At least **2 viable approaches** (including "extend existing pattern" as a candidate) — never present a single option
- For any new library/tool: maintenance status, last release, bundle/runtime cost, Expo compatibility, license. Default to **not** adding dependencies

### 3.4 Source hygiene

- Cite URL + access date for every `[EXTERNAL]` claim
- Flag outdated sources (older than the library version in use)
- Flag conflicts between sources and say which you trust and why

---

## 🧠 PHASE 4 — Synthesis

Turn the research into decisions.

### 4.1 Options table

| Option | Summary | Fits existing patterns? | Complexity | Risk | UX quality | Evidence |
| -------- | --------- | ------------------------ | ----------- | ------ | ----------- | ---------- |
| A | | | | | | |
| B | | | | | | |

### 4.2 Recommendation

- Pick one option and justify it against the **acceptance criteria** and **scope**
- State what would change your mind
- Explicitly list what the recommendation does **not** include

### 4.3 Risk register

- What could silently fail in production?
- What could mislead the implementer?
- Performance, platform-parity, data-contract, and migration risks
- For each: likelihood, impact, mitigation

### 4.4 Open questions

- Anything that needs the user's decision **before** implementation
- Mark each: 🛑 blocks implementation / ⚠️ can proceed with a stated assumption

**If any 🛑 exists → STOP and ask the user. Do not proceed to Phase 5.**

---

## 📦 PHASE 5 — Handoff Brief

Produce this exact structure so the implement-commit prompt can pick it up directly. Be dense and specific; no filler.

```
# RESEARCH HANDOFF — Commit #[NUMBER]

## 1. Goal / Scope / Acceptance Criteria
(restated from Phase 0)

## 2. Recommended Approach
(2–6 sentences + why it beats the alternatives)

## 3. Files
- Touch: path — what changes
- Read-only references: path — why it matters
- Reuse: existing component/util/pattern — path

## 4. Patterns & Conventions to Match
(with file-path examples from the repo)

## 5. Contracts
- Types / Pydantic models / postMessage commands to add or respect
- Env toggles (`HARMONIQ_SKIP_*`) needed

## 6. UX & Accessibility Requirements
(concrete, testable — sizes, states, copy, motion, a11y)

## 7. Pitfalls & Gotchas
(each with evidence tag)

## 8. Baseline State
- Lint: N errors  |  Tests: N passed / N failed
- Screenshots: .research/commit-[NUMBER]/baseline/ (list)
- Known pre-existing issues the implementer should NOT fix

## 9. Suggested Test Scenarios (for Phase 3 of the implement prompt)
1. Happy path — input / expected
2. Realistic / complex — input / expected
3. Failure case — input / expected
+ What needs manual device verification (cannot be automated)

## 10. Out-of-Scope Observations
(good ideas / bugs noticed — NOT to be implemented in this commit)

## 11. Open Questions & Assumptions
(🛑 / ⚠️ from Phase 4)

## 12. Sources
(URL, date, one-line takeaway)
```

---

## ✅ PHASE 6 — Complete

### Verify

- Every Phase 0 research question has an answer or an explicit "unresolved"
- Every claim has an evidence tag
- No project files were modified (`git status` should show no changes outside `.research/`)
- No implementation code was written
- Recommendation stays within commit scope

### Hand off

End with:

> **Research complete for Commit #[NUMBER].** Ready for implementation. Resolve any 🛑 items above, then run the implement-commit prompt.

Do NOT update `PRIORITIES.md` — that belongs to the implement phase.
