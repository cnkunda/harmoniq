# Harmoniq — Commit Spec Template

Use this template for every entry in [`PRIORITIES.md`](../PRIORITIES.md). One commit is one independently reviewable spec; do not combine unrelated work. The implementation workflow lives in [`CODER.md`](CODER.md).

---

## Status labels

| Label | Meaning |
| --- | --- |
| `ready` | Can start now; dependencies and inputs are available. |
| `in-progress` | Actively being implemented. |
| `deferred` | Planned, but intentionally ordered after other work. |
| `blocked` | Waiting on an external dependency (GPU, upstream model, licence, device). State the blocker. |
| `aspirational` | Far-future / stretch work that is not an execution commitment. |
| `complete` | All acceptance criteria verified; move the full spec to `priorities-archive.md`. |

Priority: **P0** (current research or release gate), **P1** (next), **P2** (backlog).

---

## Template

```md
## Commit N: Title

**Status:** ready | in-progress | deferred | blocked | aspirational
**Priority:** P0 | P1 | P2
**Depends on:** commits, files, data, hardware, or external decisions
**Evidence:** repository paths, measured metrics, prior commits

**Goal:** one sentence describing the user/research outcome.

**Research questions:** 3–7 concrete questions this commit must answer.

**Current state:** what exists now, what is missing, and the measured baseline.
Reference exact files and numbers. Separate facts from assumptions.

**Prior art / external signals:** source → what to borrow / what to avoid.
Keep links and access dates in the References section.

**Scope:**

In:
- …

Out:
- …

**Workstreams:** *(optional for program-scale commits)*

| ID | Deliverable | Gate |
| --- | --- | --- |
| W0 | … | … |

**Acceptance criteria:** testable checkboxes. Each must be verifiable by a command,
artifact, or documented decision.

- [ ] …

**Verification:** commands to run, expected outputs, and artifacts to update.

**Risks / mitigations:**

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| … | … | … | … |

**Open questions / assumptions:** mark blocking items with 🛑 and non-blocking
assumptions with ⚠️.

**References:** URL (accessed YYYY-MM-DD) — one-line takeaway.
```

---

## Rules

- **Scope discipline:** no future-proofing, no unrelated refactors, no silent scope expansion.
- **Evidence over assertion:** cite a path, metric, or external source for every claim.
- **Acceptance criteria are gates:** if a criterion cannot be checked, rewrite it or remove it.
- **Archive on completion:** append the full spec to [`priorities-archive.md`](../priorities-archive.md) with a completion date and verification summary; remove it from the active section.
- **Superseded work:** preserve the original spec in the archive with a `superseded` status and a pointer to the replacing commit.
- **Renumbering:** active-roadmap numbers are local and may be reset; archived commits retain their original numbers for traceability.
