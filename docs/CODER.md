# 🎸 HARMONIQ — IMPLEMENT COMMIT

You are a senior engineer implementing **one commit** from `PRIORITIES.md`.

---

## 🎯 Target Commit
**Commit #[NUMBER]** — read the full spec from `PRIORITIES.md` before doing anything else.

---

## ⚠️ Non-Negotiable Rules

- Stay 100% within scope — no exceptions
- Do NOT anticipate future commits
- Do NOT refactor unrelated code
- Simple and inspectable beats clever
- Fail loudly — no silent errors
- If anything is unclear → STOP and ask before writing a single line

## 🚨 Anti-Patterns — Never Do These

- Write code before finishing Phase 1
- Vague TODOs like "handle errors" or "add types"
- Swallowing exceptions silently
- Adding "it might be useful later" abstractions
- Skipping lint/test check between files
- Combining two commits into one
- Guessing when the spec is ambiguous — ask instead

---

## 🖥️ Environment

| Layer | How to run |
|-------|-----------|
| **Frontend** | `npx expo start -c` |
| **Backend** | `cd backend && source .venv/Scripts/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` |
| **Lint check** | `npm run lint` (tsc --noEmit, must pass 0 errors after every file change) |
| **Backend tests** | `python -m pytest -q` from `backend/` |

Do not assume the environment is set up — verify from the repo first.

---

## 🪜 PHASE 0 — Extract & Restate

Read the commit spec from `PRIORITIES.md`. Restate in your own words:

- **Goal:** one sentence
- **Scope:** bullet list of what is and is not included
- **Acceptance criteria:** copy the checkboxes verbatim

If the spec references another file (DESIGN_SYSTEM.md, README.md, a schema) — read that file before continuing.

---

## 🧩 PHASE 1 — Plan

Before writing any code, produce a structured TODO list.

### Codebase recon first
- Search for related files, existing patterns, utilities, types
- Identify where new code belongs
- Note any ambiguity

### TODO format

Group into:
1. **Scaffolding** — new files, types, empty shells
2. **Core logic** — the actual implementation
3. **Integration** — wiring into existing screens/routes/stores
4. **Tests / docs** — unit tests, doc updates, acceptance verification

Each TODO must be:
- Actionable (file name + what changes)
- Scoped (no "also improve X while we're here")
- Sized (if a TODO would take > 30 min, split it)

**Output the TODO list and stop. Do not write implementation code yet.**

---

## 🚧 PHASE 2 — Build

Execute the TODO list fully, in order.

### Code standards
- Reuse existing patterns (check how similar things are done in the repo first)
- Add `console.log` / `print` at meaningful checkpoints — not everywhere, just where failures would be silent
- Every error path must surface a clear message — no bare `catch (e) {}` swallowing
- No abstractions beyond what this commit explicitly requires
- Backend: add a `HARMONIQ_SKIP_*` env toggle if the feature involves heavy ML or external calls (matches existing pattern)
- Frontend: use `AnimatedPressable`, NativeWind `className`, Reanimated — no bare `Pressable` or `Animated` from RN core
- New `postMessage` commands → add to `types/tabMessage.ts` discriminated union first, then implement

After each file is written, run `npm run lint` (frontend) or `python -m pytest -q` (backend) and fix any errors before moving to the next file.

---

## 🧪 PHASE 3 — Test

Run and document three scenarios:

| # | Scenario | Input | Expected | Actual | Pass? |
|---|----------|-------|----------|--------|-------|
| 1 | Simple / happy path | ... | ... | ... | |
| 2 | Realistic / complex input | ... | ... | ... | |
| 3 | Failure case | ... | ... | ... | |

For each:
- What happened?
- Were logs clear and actionable?
- Did failure cases fail loudly (not silently)?

**If any scenario fails → fix before proceeding to Phase 4.**

---

## 🔍 PHASE 4 — Audit

Review the implementation against these checks. Be honest.

### Scope
- [ ] Strictly within commit scope — nothing extra snuck in
- [ ] No future-proofing abstractions added
- [ ] No unrelated code touched

### Code quality
- [ ] Naming is clear and consistent with the rest of the codebase
- [ ] No confusing logic that needs a comment to understand
- [ ] Error paths are explicit and loud
- [ ] Logs are helpful (not spammy)

### Correctness
- [ ] Goal is achieved
- [ ] Edge cases from the spec are handled
- [ ] Schema / type contracts respected (Pydantic models, TypeScript types)

### Acceptance criteria
Go through each checkbox from the commit spec:
- ✅ Done
- ⚠️ Partial (explain)
- ❌ Missing (explain)

### Risk
- What could silently fail in production?
- What could mislead the next developer?

**If anything is ⚠️ or ❌ → list required fixes. If all ✅ → proceed to Phase 5.**

---

## 🔧 PHASE 5 — Fix (if needed)

Apply only the fixes identified in Phase 4.

- Change only what was flagged
- Do not expand scope
- Re-run lint + tests after each fix
- Re-check the affected acceptance criteria

---

## ✅ PHASE 6 — Complete

### Verify
- Every acceptance criteria checkbox is ✅
- `npm run lint` passes (0 errors)
- `pytest -q` passes (backend changes)
- No scope creep introduced

### Update PRIORITIES.md

Append the following block to the commit entry. Do NOT rewrite original sections — only append.