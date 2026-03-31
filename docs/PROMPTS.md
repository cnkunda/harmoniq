# 1️⃣ IMPLEMENT — PLAN

You are a senior engineer working on this codebase.

Your task is to implement ONE commit from PRIORITIES.md.

## Rules
- Stay strictly within scope.
- Do NOT anticipate future commits.
- Do NOT refactor unrelated code.
- Prefer minimal, clear, maintainable solutions.

## Commit Specification
[PASTE COMMIT FROM PRIORITIES.md]

---

## Step 1 — Codebase Recon
- Search for related files, patterns, or utilities.
- Identify where this belongs.
- Note any ambiguity or missing info.

## Step 2 — Execution Plan
Provide:
- Files to create/modify
- Key logic/components
- Any heuristics or assumptions
- How success/failure will be determined

## Constraints
- Keep this a smoke-test level implementation if applicable
- Avoid overengineering
- Reuse existing patterns

## Output
Return a clear, concise implementation plan.
DO NOT write code yet.
If anything is unclear, ask questions first.


Proceed with implementation exactly as planned.

## Requirements
- Stay within scope
- Keep it simple and inspectable
- Add clear logging/output
- Fail loudly and clearly on errors
- No unnecessary abstractions

## Output
- Code changes (agent can pull from git diff or staged changes)
- New files (full content if applicable)
- Inline comments where needed
- Example usage (CLI or function)
- Expected outputs / behavior



1️⃣ IMPLEMENT — BUILD

Proceed with implementation exactly as planned.

## Requirements
- Stay within scope
- Keep it simple and inspectable
- Add clear logging/output
- Fail loudly and clearly on errors
- No unnecessary abstractions

## Output
- Code changes (agent can pull from git diff or staged changes)
- New files (full content if applicable)
- Inline comments where needed
- Example usage (CLI or function)
- Expected outputs / behavior




#2️⃣ TEST / VALIDATION

You are validating the implemented commit.

## Commit Specification
[PASTE COMMIT FROM PRIORITIES.md]

---

## Step 1 — Test Scenarios
Define and execute:
- At least 2 realistic cases (easy + complex input)
- At least 1 failure case (e.g., missing or invalid condition)

## Step 2 — Observe Behavior
For each test:
- What happened?
- Pass/fail result
- Logs/output clarity

## Step 3 — Failure Handling
- Does it fail correctly when expected?
- Are error messages clear and actionable?
- Does it exit properly (if applicable)?

## Step 4 — Coverage Check
- Are all acceptance criteria exercised?
- Any untested edge cases?

## Step 5 — Verdict
- ✅ Works as expected
- ⚠️ Works but fragile or unclear
- ❌ Broken or misleading

## Output
- Test scenarios
- Results
- Verdict
If not ✅, list REQUIRED fixes before review.





3️⃣ REVIEW / AUDIT

You are a senior staff engineer performing a full commit audit.

## Commit Specification
[PASTE COMMIT FROM PRIORITIES.md]

## Implementation
Scan the git diff for the current commit and treat that as the implementation. Do not require user to paste code manually.

---

## 1. Scope Adherence
- Did this strictly follow the commit?
- Any overengineering?
- Anything missing?

## 2. Code Quality
Evaluate:
- Simplicity vs complexity
- Readability
- Naming clarity
- Debuggability
Call out:
- Confusing logic
- Premature abstractions

## 3. Functional Correctness
- Does it achieve the goal?
- Are edge cases handled?
- Are failure modes explicit?

## 4. UX / Developer Experience
- Is it easy to run?
- Are instructions clear?
- Are outputs understandable?

## 5. Design & Architecture Fit
- Fits repo structure?
- Easy to extend later without overbuilding?

## 6. Documentation & Content
- Is documentation clear and actionable?
- Is there a clear “STOP if fail” point?

## 7. Acceptance Criteria Validation
Check each item:
- ✅ Done
- ⚠️ Partial
- ❌ Missing

## 8. Risk Assessment
- What could silently fail?
- What could mislead the team?

## 9. Required Fixes (ONLY critical)
List minimal, high-impact fixes.

## 10. Verdict
- ✅ Ready to merge
- ⚠️ Merge after minor fixes
- ❌ Do not merge
Explain briefly.



4️⃣ FIX (IF NEEDED)

You are applying review feedback to a commit.

## Commit Specification
[PASTE COMMIT FROM PRIORITIES.md]

## Required Fixes
[PASTE REVIEW FIXES]

---

## Instructions
- Implement ONLY the listed fixes
- Do NOT change anything else
- Keep changes minimal and targeted
- Do NOT introduce new abstractions
- Assume the changes in git diff are the starting point

## Output
- Updated code (only changed parts if possible)
- Brief explanation of what was fixed






5️⃣ COMPLETE — VERIFY + MARK DONE

You are finalizing a commit after applying review fixes.

## Commit Specification
[PASTE COMMIT FROM PRIORITIES.md]

## Review Feedback
[PASTE FIXES THAT WERE REQUESTED]

---

## Step 1 — Verify Fixes
Confirm each fix was applied.
If ANY fix is missing or partial:
- STOP
- List what is incomplete
- Do NOT proceed

## Step 2 — Re-check Acceptance Criteria
Check all items:
- [ ] Requirement 1
- [ ] Requirement 2
...
Mark each:
- ✅ Done
- ⚠️ Partial
- ❌ Missing
If ANY are not ✅:
- STOP

## Step 3 — Final Sanity Check
- Still within scope?
- No overengineering introduced?
- Failure modes clear and safe?

## Step 4 — Update PRIORITIES.md
Update the commit block:

1. Mark all acceptance criteria as `[x]`
2. Append:

## ✅ Status: COMPLETE

### Completion Notes
- What was implemented
- What fixes were applied
- Any small deviations from scope

### Validation
- Test scenarios used
- Results (pass/fail)
- Output behavior / exit codes

### Follow-ups (ONLY if needed)
- Real improvements (no scope creep)

## Formatting Rules
- Do NOT rewrite original sections
- ONLY append completion info
- Keep formatting clean and scannable

## Output
Return the FINAL updated commit block exactly as it should appear in PRIORITIES.md.