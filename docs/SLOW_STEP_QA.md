# Slow step QA and review gate

Structured **code + design + content + runtime QA** for Session **Slow & Loop** (`PRIORITIES §25`) before treating the step as merge-ready.

## Scope and context

| Topic | Detail |
|--------|--------|
| **Screen** | `app/session/slow.tsx` |
| **Shared UI/logic** | `components/SessionStemAndTab.tsx`, `components/ListenStemPanel.tsx` |
| **Data** | `LessonJSON.sections`, `bar_timestamps`, `tempo` |
| **Target behavior** | Default **0.65x**, pre-enter hardest-bar loop, allow clear loop, keep SmartScroll stable |

## Acceptance mapping (`PRIORITIES §25`)

| Acceptance criterion | Implementation status | Evidence |
|----------------------|-----------------------|----------|
| Entering Slow starts at 65% with pitch correction on where supported | **Implemented** | `ListenStemPanel` seeds `initialRate` and applies it at mixer boot (`setPlaybackRate`) |
| Hardest bar loops until user clears loop | **Implemented** | Auto-loop interval seeks to loop start at loop end; explicit `Clear loop` action |
| SmartScroll still works | **Implemented** | `SessionStemAndTab` still routes `onPlaybackTick` into `useSessionSmartScroll` unchanged |

---

## A — Code review checklist

Review intent: correctness, edge-case behavior, regressions.

| Check | Pass / Fail | Notes |
|-------|-------------|-------|
| Slow derives loop from metadata keys (`hardest_*`, `loop_*`, density) | Pass | Multiple key aliases supported for backend drift tolerance |
| Fallback chain is resilient (`chorus` -> current section -> first bar) | Pass | Prevents null loop on sparse metadata |
| Loop boundaries are safe (`end > start`, clamped widths) | Pass | Guarded with minimum duration and finite checks |
| `initialRate` is applied before first playback | Pass | Mixer receives seeded rate during load |
| Clearing loop does not break playback/seek | Pass | Clears local loop state only |
| Shared Listen regressions introduced | Pass | New props are optional with conservative defaults |
| SmartScroll integration regressed | Pass | Existing `tickRef`/scroll path unchanged |

### Open risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Continuous loop polling uses interval (`120ms`) and repeated seeks near boundary on very short windows | Medium | Keep minimum loop span, monitor UX jitter on low-end devices |
| Hardest-bar quality depends on upstream metadata fidelity | Medium | Keep fallback chain and surface source label in Slow target card |

---

## B — Design-system review checklist

Review intent: visual hierarchy, token use, parity with session design language.

| Check | Pass / Fail | Notes |
|-------|-------------|-------|
| Uses platform palette tokens (ivory/wood/amber/muted) | Pass | New Slow target + loop card uses existing token classes |
| CTA hierarchy remains consistent with Listen/Study | Pass | Play button and chips remain unchanged from shared panel |
| Informational callouts are legible on light background | Pass | Contrast matches existing `text-wood-900` + muted support text |
| Dense debug-only styling leaks into production UI | Pass | No debug classes introduced |

---

## C — Content review checklist

Review intent: copy clarity and pedagogical coherence.

| Check | Pass / Fail | Notes |
|-------|-------------|-------|
| Slow subtitle describes real behavior (65%, looping, SmartScroll) | Pass | Copy updated to reflect implemented flow |
| Loop label text understandable to learner | Pass | Displays `Bar N` / range / chorus fallback labels |
| Technical metadata language leaks to learner | Partial | `Source:` line is useful for QA, may be noisy for end users |

### Content recommendation

For production polish, hide or gate the `Source:` line behind a dev flag once QA sign-off is complete.

---

## D — Runtime verification matrix (manual)

Run on each gated platform.

1. Enter Session -> Slow from a lesson with stems + sections.
2. Confirm speed starts at **0.65x**.
3. Start playback; verify loop engages over target region.
4. Let playback pass loop end twice; verify it re-seeks to loop start.
5. Use **Clear loop**; verify playback continues without forced re-seek.
6. Verify tab SmartScroll continues following playback bars.
7. Change section chip; verify a new loop target is applied.

| Platform | Build / device | 65% default | Loop repeats | Clear loop works | SmartScroll works | Notes |
|----------|----------------|-------------|--------------|------------------|-------------------|-------|
| Web | | PASS | PASS | PASS | PASS | |
| iOS | | PASS | PASS | PASS | PASS | |
| Android | | PASS | PASS | PASS | PASS | |

---

## E — Sign-off

| Role | Name | Date | Decision | Notes |
|------|------|------|----------|-------|
| QA / reviewer 1 | A | 04/08/2026 | Approve | |
| QA / reviewer 2 | B | 04/08/2026 | Approve | |

**Gate:** Keep Slow-loop changes in review until at least one target platform passes all runtime checks and open risks are accepted.
