"""Reorder PRIORITIES.md: Planned → Complete → Skipped; collapse commits 1–44; remove Git appendix; trim Phase 0 prose."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "PRIORITIES.md"
lines = PATH.read_text(encoding="utf-8").splitlines(keepends=True)


def line_idx(pred, start: int = 0) -> int:
    for i in range(start, len(lines)):
        if pred(lines[i]):
            return i
    raise RuntimeError("block not found")


# Parse titles for 1–44 from completion index
INDEX_TITLES: dict[int, str] = {}
in_rows = False
for line in lines:
    if line.startswith("| # | Title | Phase |"):
        in_rows = True
        continue
    if in_rows:
        if line.strip().startswith("|---"):
            continue
        if not line.strip().startswith("|"):
            break
        m = re.match(r"^\|\s*(\d+)\s*\|\s*([^|]+)\|\s*([^|]+)\|", line)
        if m:
            num = int(m.group(1))
            if 1 <= num <= 44:
                INDEX_TITLES[num] = m.group(2).strip()

archive_lines = [
    "## Roadmap archive (Phase 1–4, commits 1–44)\n",
    "\n",
    "| # | Summary | Status |\n",
    "|---|---------|--------|\n",
]
for n in range(1, 45):
    archive_lines.append(f"| {n} | {INDEX_TITLES.get(n, '—')} | Complete |\n")
archive_lines.append("\n")

# Slice indices
idx_phase5 = line_idx(lambda s: s.startswith("## Phase 5 — Feel Real"), 0)
idx_64 = line_idx(lambda s: s.startswith("## 64. Left-handed mode"), 0)
idx_65 = line_idx(lambda s: s.startswith("## 65. Adaptive curriculum"), 0)
idx_75 = line_idx(lambda s: s.startswith("## 75. Ghost player"), 0)
idx_cross = line_idx(lambda s: s.startswith("## Phase 5 cross-cutting rules"), 0)
idx_archive_old = line_idx(lambda s: s.startswith("## Roadmap archive"), 0)
idx_open = line_idx(lambda s: s.startswith("## Open follow-ups (legacy post-commit 41)"), 0)
idx_app_idx = line_idx(lambda s: s.startswith("## Appendix — Roadmap completion index"), 0)
idx_p0 = line_idx(lambda s: s.startswith("## Appendix — Completed Phase 0"), 0)
idx_01 = line_idx(lambda s: s.startswith("## 0.1."), idx_p0)
idx_git = line_idx(lambda s: s.startswith("## Git commit messages and branch strategy"), 0)
idx_crossref = line_idx(lambda s: s.startswith("*Cross-reference:"), idx_git)

head = lines[:idx_phase5]
complete_main = lines[idx_phase5:idx_64] + lines[idx_65:idx_75]
skipped = lines[idx_64:idx_65]
tail_cross = lines[idx_cross:idx_archive_old]
open_follow = lines[idx_open:idx_app_idx]
appendix_idx = lines[idx_app_idx:idx_p0]
p0_table = lines[idx_p0:idx_01]
footer = lines[idx_crossref:]

reading_order = """
### Reading order (pre-MVP)

| Group | Commits |
|--------|---------|
| **Planned** | 75 – 77 |
| **Complete** | 0.1–0.6, 1–58, 59–61, 62–63, 65–74 |
| **Skipped** | 64 |

"""

# Insert reading order after index intro paragraph (after blank line following "Full specs...")
ins = 0
for i, line in enumerate(appendix_idx):
    if line.startswith("Single-page index:"):
        # after next blank line
        j = i + 1
        while j < len(appendix_idx) and appendix_idx[j].strip() == "":
            j += 1
        ins = j
        break
appendix_merged = appendix_idx[:ins] + [reading_order] + appendix_idx[ins:]

p0_note = [
    "\n",
    "> Detailed Phase 0 specs (former §0.1–0.6) removed here; see git history. The table above is canonical.\n",
    "\n",
]

planned = r'''## Roadmap — Planned (next up)

## 75. Ghost player — play alongside your past self

### Goal

Let users record a "ghost take" — a reference recording of themselves playing a section — then play it back quietly alongside a new take in real time, so they can hear their own progress and maintain tempo discipline without a metronome.

### Scope

* `app/session/play.tsx`: add "Record ghost take" mode — after normal recording, user can flag the take as a ghost reference for this section
* `src/audio/ghostPlayer.ts`: load ghost take WAV from SQLite `sessions` audio path; mix ghost at 20% volume under live recording using the existing stem mixer abstraction
* `components/GhostPlayerControl.tsx`: compact toggle below the play step controls — "Play with ghost" switch + ghost take timestamp label; `AnimatedPressable` with amber ghost icon
* SQLite: add `is_ghost_reference: boolean` column to `sessions` table; query most recent ghost for current `job_id` + `section_index`
* Ghost audio plays in sync with session start; stops automatically when recording ends
* `app/session/review.tsx`: overlay ghost waveform as a third series in the phrasing visualizer (faint amber line) alongside reference and user take

### Acceptance Criteria

* [ ] Flagging a take as ghost reference persists to SQLite and appears on next Play session for the same section
* [ ] Ghost audio plays at 20% volume alongside live recording without timing drift over a 30s clip
* [ ] Ghost waveform renders as a third series in Review phrasing visualizer
* [ ] Missing ghost file degrades gracefully without crash
* [ ] `GhostPlayerControl` toggle is disabled with correct copy when no ghost exists for the section

### Status

**Planned**

---

## 76. Mood-adaptive session — player state influences intensity

### Goal

Ask users how they're feeling before a session and adapt the practice plan intensity, BPM defaults, and coach tone accordingly — so Harmoniq feels responsive to human state, not just skill data.

### Scope

* `app/session/mood-check.tsx`: lightweight pre-session modal (shown once per day) — "How are you feeling today?" with four options (Focused / Loose / Tired / On Fire); dismissible "Skip"; auto-skip preference in Settings
* `backend/app/schemas.py`: `MoodState` literal; optional `mood` on `PracticePlanRequest`
* `backend/app/sequencer.py` + `backend/app/coach.py`: mood adjusts plan slots, durations, BPM hints, and coach copy
* Store `mood` with session row in SQLite for later analysis

### Acceptance Criteria

* [ ] Mood check modal appears on first daily session and not again that day
* [ ] `tired` mood produces a plan with shorter duration and no technique drill slot in fixture test
* [ ] Coach intro text for `on_fire` mood is visibly more energetic than `tired` mood in same fixture
* [ ] Skipping mood check generates a standard plan without error
* [ ] `mood` field stored with session record for progress analysis

### Status

**Planned**

---

## 77. Listening mode — Spotify playback + real-time tab follow

### Goal

Play a Spotify track the user loves while Harmoniq follows along with the analyzed tab in real time — bridging passive listening and practice.

### Scope

* `app/listening.tsx`: song picker (analyzed library); "Listen on Spotify" deep link
* `src/audio/spotifyPlaybackBridge.ts`: poll Spotify Web API `GET /me/player` for `progress_ms` / `is_playing`; drive AlphaTab `seekTo` / `setPlaybackRate` (commit 45 contract)
* `backend/app/spotify.py`: `get_playback_state` wrapper; document Premium requirement
* Harness listening flag: read-only follow mode; dev kill-switch `HARMONIQ_SKIP_SPOTIFY_PLAYBACK=1`

### Acceptance Criteria

* [ ] AlphaTab cursor advances in sync with Spotify playback within ±600ms on a known test song
* [ ] "Follow along" toggle disables cursor sync without stopping Spotify playback
* [ ] Non-Premium or disconnected Spotify state shows appropriate `ErrorBanner` without crash
* [ ] Listening mode does not activate mic, metronome, or recording paths
* [ ] `HARMONIQ_SKIP_SPOTIFY_PLAYBACK=1` renders listening screen in static study mode without API calls

### Status

**Planned**

---

'''

head_text = "".join(head)
head_text = head_text.replace(
    "**Phase 0 (commits 0.1–0.6)** — Expo + design scaffold, backend shell, AlphaTab harness, env/backing tracks, shared UI feedback + API client — is **complete**. **Commits 1–58** are delivered in tree. **Phase 5** commits **59–61** (pre-render, SoundFonts, AlphaTab runtime telemetry) are **complete**. **Phase 6** commits **62–63** and **65** are **complete**; commit **64** (left-handed mode) is **skipped** for this side project. **Phase 7** commits **66–69** (coach async hydration through cold-start taste quiz) are **complete**; commits **70–74** (through Riff DNA fingerprint) are **complete**; commits **75–77** remain **planned**. A compact [completion index](#appendix--roadmap-completion-index-commits-1-77) lists every tracked commit through **77**.\n",
    "**Phase 0 (0.1–0.6)** — **complete**. **1–58**, **59–61**, **62–63**, **65**, **66–74** — **complete**. **64** — **skipped**. **75–77** — **planned** (next up). "
    "Index: [commits 1–77](#appendix--roadmap-completion-index-commits-1-77); order: [Planned → Complete → Skipped](#reading-order-pre-mvp).\n",
)
head_text = head_text.replace(
    "| **Roadmap status** | Commits 1–58 delivered in repo. Phase 5 (59–61) complete. Phase 6: commits **62–63** and **65** complete; commit **64** skipped (not needed for side project). Phase 7: commits **66–69** complete; commits **70–77** planned — drill sequencer, guided path UX, voice coach, and novel practice features. |\n",
    "| **Roadmap status** | **Done:** through **74** (incl. taste, practice plan, voice coach, warmup, Riff DNA). **Next:** **75–77**. **Skipped:** **64**. |\n",
)
new_head = list(head_text)

out = (
    new_head
    + [planned]
    + ["## Roadmap — Complete\n", "\n"]
    + complete_main
    + ["## Roadmap — Skipped\n", "\n"]
    + skipped
    + tail_cross
    + archive_lines
    + open_follow
    + appendix_merged
    + p0_table
    + p0_note
    + footer
)

PATH.write_text("".join(out), encoding="utf-8")
print("OK:", PATH, "lines", len(out))
