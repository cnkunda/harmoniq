---
name: ux-improve-loop
description: Run the Harmoniq UI/UX audit loop — capture all Expo web routes, run deterministic DOM checks + vision analysis, fix or waive gaps, verify until complete, and use the fast pre-commit guard for changed routes only. Use when asked to improve UI/UX, audit screens, check design conformance, verify a UI fix, or before committing UI changes.
---

# Harmoniq UI/UX Improvement Loop

You are the agent driving the Harmoniq UI/UX improve loop. Capture → detect → fix → verify.
**Cosmetic fixes only** — never change functionality or business logic to satisfy a gap.

## Commands

| Need | Command |
|------|---------|
| Pre-commit guard (fast, changed routes only) | `npm run ux:guard` |
| Full loop (capture + checks + vision) | `npm run ux:improve` |
| Verify after fixes | `npm run ux:verify` |
| Waive a false positive | `node scripts/audit/ux-improve-loop.mjs --waive "<route>::<slug>" --reason "..."` |
| Full unit tests | `npm run test` |
| Type check (mandatory) | `npm run lint` |

- `npm run ux:guard` maps `git diff` files to routes and checks only those (~1-2 min for 1-3 routes, needs Expo web on :8081). Broad/unresolvable changes (db, tokens, shared components used everywhere) fall back to all routes (~10-15 min, no vision). Exit code 1 = actionable gaps; 0 = clean. It never touches the full-loop state or `ui-feedback-report.json`.
- Full loop takes 60-90+ min (30 routes, moondream vision) — run detached/background, do not block on it inline.
- Reports: `docs/audit/ui-feedback-report.json` (full loop, `isComplete` flag), `docs/audit/ux-guard-report.json` (guard).

## Workflow

1. Start the dev server if needed: `npm run web` (or let Playwright auto-start it; first start ~3 min).
   **Trap:** Metro in CI mode serves a stale bundle — after editing app code, restart Expo (`-c`) or runs will show pre-fix classes.
2. Run guard (pre-commit) or the full loop (see commands above).
3. Read gaps from `allGapsByRoute`: each gap has stable `id` (`<route>::<slug>`), `severity`, `source` (`deterministic` = DOM-measured, authoritative; `vision` = advisory), `evidence`, `suggestedFix`.
4. For each error/warning gap: inspect the route's source file (`sourceFiles` field) and fix cosmetically using design tokens (wood/amber/cream palette, Playfair Display/DM Sans/JetBrains Mono, `AnimatedPressable`, NativeWind classes). Then typecheck, and re-run guard or verify.
5. False positives / accepted design decisions get waived ONCE with a specific reason (persisted in `docs/audit/ux-waivers.json`):
   `node scripts/audit/ux-improve-loop.mjs --waive "/add-song::excessive-padding" --reason "Intentional spacious hero step"`
6. Loop until `isComplete: true` (full loop) or guard exit 0 (pre-commit).
7. Commit UI changes with the guard clean; update `docs/audit/` report files only if the full loop ran.

## Check taxonomy (gap slugs)

Deterministic (in-page DOM measurements in `tests/ui/support/visualChecks.ts`):
`off-palette-color`, `purple-gradient`, `contrast`, `font-family`, `excessive-padding`, `floating-element`, `small-tap-target`, `tiny-text`, `keyboard-overlap`, `empty-screen`, `raw-error-text`, `text-scaling`, plus layout alignment/overflow checks.

Runtime probes (Playwright in `tests/ui/support/capture.ts`):
`tap-feedback` (real pointer press must change a style), `double-activation` (nested interactive firing both handlers), `duplicate-request` (same GET x3+ → `missing-caching`), `persistence` (IndexedDB record counts survive reload → `preferences-wiped`).

Vision (moondream, advisory only): layout clipping, broken screens, alignment, contrast.

Fix guidance per slug lives in `scripts/audit/ux-improve-loop.mjs` (`FIX_GUIDANCE`). Functional gaps (`missing-caching`, `preferences-wiped`) are never waived silently — log them or fix them.

## Rules

- Run the loop from Git Bash; never block a commit on the full loop — use `ux:guard`.
- Never commit with guard or `npm run lint` failing for reasons this loop introduced.
- Do not reply with node IDs or internal report paths mid-conversation; summarize gaps in plain language.
- After a fix wave completes, re-run guard first (fast feedback), then `npm run ux:verify` for the authoritative pass.
