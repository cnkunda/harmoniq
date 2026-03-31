# 🧠 IMPLEMENT COMMIT

You are implementing **one commit** from `PRIORITIES.md` using the structured workflow in `PROMPTS.md`.

---

## 🎯 Target Commit
Use the commit at:
[Commit #]

Work strictly within this commit.

---

## ⚠️ Core Rules (STRICT)

- Stay 100% within scope
- Do NOT anticipate future commits
- Do NOT refactor unrelated code
- Prefer simple, minimal implementations
- Avoid unnecessary abstractions
- Add logging where helpful
- If anything is unclear → STOP and ask

---

## 🧭 Environment Awareness

Before doing anything:

- Confirm how the project runs (scripts, entrypoints)
- Be aware of:
  - Backend uses Python venv
  - Web uses browser APIs (e.g. Web Audio API)
  - Native uses platform-specific modules

Do not assume environment setup — verify it from the repo.

---

## 🪜 Step 0 — Extract Commit

- Copy the commit spec from PRIORITIES.md
- Briefly restate:
  - Goal
  - Scope
  - Acceptance criteria

---

## 🧩 Step 1 — Generate TODO List

Using:
@PROMPTS.md → IMPLEMENT — PLAN

Create a clear, structured TODO list.

### Requirements for TODOs

Each TODO must:
- Map directly to the commit scope
- Be actionable (not vague)
- Include:
  - Files to create/modify
  - What is being implemented
  - Expected outcome

Group TODOs into:

1. Setup / scaffolding
2. Core implementation
3. Integration (if applicable)
4. Validation / docs

Keep it lean but complete (no overengineering).

---

## 🚧 Step 2 — IMPLEMENT (FULL COMMIT)

Using:
@PROMPTS.md → IMPLEMENT — BUILD

- Execute the TODO list fully
- Keep code:
  - Simple
  - Inspectable
  - Well-logged
- Fail loudly on errors
- Do not introduce abstractions beyond what this commit requires

---

## 🧪 Step 3 — TEST / VALIDATION

Using:
@PROMPTS.md → TEST / VALIDATION

- Run:
  - 1 simple case
  - 1 realistic case
  - 1 failure case (if applicable)
- Clearly document:
  - What happened
  - Pass/fail
  - Output/log clarity

---

## 🔍 Step 4 — REVIEW / AUDIT

Using:
@PROMPTS.md → REVIEW / AUDIT

Focus on:
- Scope adherence
- Overengineering
- Missing pieces
- Clarity of code + logs

---

## 🔧 Step 5 — FIX (IF NEEDED)

Using:
@PROMPTS.md → FIX

- Apply only critical fixes
- Keep changes minimal
- Do not expand scope

---

## ✅ Step 6 — COMPLETE

Using:
@PROMPTS.md → COMPLETE

- Verify all fixes applied
- Ensure all acceptance criteria are met
- Update PRIORITIES.md:
  - Mark [ ] → [x]
  - Append completion block

---

## 🧠 Execution Style

- Be thorough and explicit, not fast
- Think before coding
- Prefer working simplicity over cleverness
- Everything should be easy to debug
- If unsure → ask instead of guessing

---

## 🚨 Anti-Patterns to Avoid

- Skipping the planning step
- Vague TODOs
- Overbuilding beyond scope
- Silent failures
- Adding “future-proof” abstractions