# Harmoniq 170-Class Chord Model — Program Report, Ceilings, and Path to Production

**Status:** research through Phase 4e; production model untouched.
**Date:** 2026-11-24
**Scope:** everything learned from the 170-class chord program: results, negative
results, pitfalls, empirical ceilings, data sources, practice/correction data,
and the concrete path to replacing the production chord model.

This is the document to read first when resuming the program. It supersedes the
narrative in `CHORD_170_HANDOFF.md` for planning; the handoff remains the compact
state/continuation card.

---

## 0. The short answer

1. The current best honest model reaches **macro-F1 0.359, exact 0.576, WCSR-MIREX
   0.699, bass 0.834, slash 0.266, ECE 0.0147** on the fixed external fine test.
2. Bass and calibration gates pass; **macro-F1 (0.45) and slash (0.50) do not**.
   The 95% track-bootstrap CI for the best macro is roughly **[0.286, 0.367]**, so
   0.45 is outside the current evidence, not a near miss.
3. The CQT representation, 96-frame context, 3 seeds, and cross-context ensembles
   are **saturated**. More of the same will not close the gates.
4. The two real levers are:
   - **more real, guitar-domain, rare-quality/inversion-rich data** (owned practice
     data and corrections are the best source; EGDB-PG, Guitar-TECHS
     multi-perspective, and GOAT are the best public sources);
   - **a different training objective/representation** (joint chord+bass /
     structured decomposition from scratch, or a properly adapted pretrained
     encoder) once the data exists.
5. The full 102-class macro gate is currently dominated by classes with almost no
   test support: 15 classes have one frame, 19 have 2–4, 14 have 5–9. Minimum-support
   macro is already **0.500 (≥10 frames)** and **0.527 (≥20 frames)**. A production
   gate must be defined on a statistically meaningful support threshold or on a
   larger, class-balanced test set. Do not silently change the number; decide it
   explicitly.
6. Do not ship any model trained on research-only data (GOAT, JAAH, RWC 2.0,
   HookTheory/SheetSage, MuQ weights, Chordify CASD). Keep a separate research
   track. Production must use CC BY/owned data only.

---

## 1. Current gate status and best artifacts

### 1.1 Fixed external test

- Sources: GuitarSet fine (1,176 windows), EGSet12 fine (63), held-out IDMT fine
  (265), held-out RWC fine (1,617).
- Total: **3,121 windows / 86 tracks**, 1.6 s windows at 10 Hz frames.
- Support: 102 chord classes; 15 classes with one frame, 19 with 2–4, 14 with
  5–9, 19 with 10–19, 35 with 20+.

### 1.2 Best gate row

| Metric | Target | Best honest | Status |
| --- | ---: | ---: | --- |
| Macro-F1, full 102 supported classes | ≥0.45 | **0.359** | fail |
| Macro-F1, classes with ≥10 frames | diagnostic | **0.500** | pass if adopted |
| Macro-F1, classes with ≥20 frames | diagnostic | **0.527** | pass if adopted |
| Bass accuracy, known-bass frames | ≥0.60 | **0.834** | pass |
| Slash accuracy, inversion frames | ≥0.50 | **0.266** | fail |
| ECE, duration-weighted | ≤0.15 | **0.0147** | pass |
| Exact chord accuracy | companion | **0.576** | — |
| WCSR-MIREX | companion | **0.699** | — |
| Top-3 accuracy | companion | **0.779** | — |

### 1.3 Best recipes

**Best macro / MIREX / ECE (two-context ensemble):**

- `context-s96-b3-s2-ft-synth` (96 frames, 3 blocks, synthetic rare-chord
  fine-tune of seed 2) plus
- `context-s128-b4-s1` (128 frames, 4 blocks, seed 1).
- Result: macro 0.359, exact 0.568, MIREX 0.693, bass 0.830, slash 0.238,
  ECE 0.0147, top-3 0.772.
- Bootstrap CI: exact **[0.505, 0.626]**, macro **[0.286, 0.367]**.

**Best exact / MIREX (three-context ensemble):**

- `context-s96-b3-s2-ft-synth` + `context-s128-b4-s1` +
  `context-s96-b3-guitar-only`.
- Result: exact **0.576**, MIREX **0.699**, macro 0.354, bass 0.829, slash 0.240,
  ECE 0.0162, top-3 0.779.

**Best slash:**

- `context-full-s64-guitarft` + `context-s64-guitar-bal-ft`.
- Result: slash **0.266**, macro 0.320, exact 0.544, MIREX 0.677, ECE 0.0145.

**Best bass:**

- `context-s96-b3-s2-ft-synth` + `context-s128-b4-s1` +
  `context-full-s64-guitarft`.
- Result: bass **0.834**, macro 0.342, exact 0.571, MIREX 0.691, slash 0.255.

### 1.4 Checkpoints and data

On `harmoniq-chord170-runs` (`/runs`):

- `/runs/chord170/context-s96-b3-s2-ft-synth/best.keras`
- `/runs/chord170/context-s128-b4-s1/best.keras`
- `/runs/chord170/context-s96-b3-guitar-only/best.keras`
- `/runs/chord170/context-s96-b3-s2-ft/best.keras`
- `/runs/chord170/context-s96-b3-s3/best.keras`
- `/runs/chord170/context-full-s64-guitarft/best.keras`
- `/runs/chord170/context-s64-guitar-bal-ft/best.keras`
- `/runs/chord170/context-s96-b3-s2-ft-synth2/best.keras` (6,764-window synthetic scale-up)

On `harmoniq-chord170-data` (`/chord170/backend/data`):

- `chord170/fine/{guitarset,egset12,idmt_smt_guitar,rwc,guitar_techs,idmt_chords}`
- `chord170/slakh_fine` (1,710 tracks, 266,870 windows)
- `chord170/slakh_balanced` (400 tracks, 62,835 windows)
- `chord170/synthetic_guitar` (3,091 windows, 110 classes)
- `chord170/muq` (30,503 windows; research-only representation)
- `chord170/splits.json` (external track splits)

Full artifact: `docs/audit/amt/chord170_phases_1_3.json`.

---

## 2. Production context

- Production model: `backend/app/chord_model.keras`, the 25-class Commit 148
  multi-task model (chord 25 / root 13 / presence 1). On GuitarSet player-05 it
  scores **0.043 exact**.
- The registry-claimed v1.0.3 (277-class) and v1.0.5 provenance issues are
  documented in `CHORD_170_PHASE0_BASELINE.md`; do not trust the old claims.
- Production code, registry, and feature flags are untouched by this program.
- The 170-class model already beats the production model on exact and MIREX, but
  product replacement should not happen until the agreed gates and export/latency
  checks pass.

---

## 3. Data actually used

### 3.1 Real guitar fine windows

| Source | Tracks | Windows | Notes |
| --- | ---: | ---: | --- |
| GuitarSet | 360 | 7,056 | 6 players, acoustic, performed chords |
| EGSet12 | 12 | 235 | electric, test-oriented |
| IDMT-SMT-Guitar d4 | 129 | 2,574 | electric, dataset4 |
| RWC-P | 100 | 15,184 | pop, full mixes, slash bass |
| Guitar-TECHS | 68 | 6,056 | direct input only (4 perspectives exist) |
| IDMT dataset1 chords | 88 | 176 | short chord recordings |
| **Real total** | **757** | **31,281** | |
| Slakh2100-redux fine | 1,710 | 266,870 | full mixes, MIDI-derived labels; dominates full-data runs |
| Balanced Slakh subset | 400 | 62,835 | 115/170 classes, 320/40/40 splits |
| Synthetic guitar | 3,091 | 3,091 | additive synthesis, 110 classes, 12 bass classes |
| MuQ features | 757 | 30,503 | research-only representation |

The external gate never includes Slakh, synthetic, or MuQ windows.

### 3.2 Data quality notes

- GuitarSet labels are performed chords; the label boundaries are derived from
  the lead sheet, so boundary mismatch is a known source of error.
- Guitar-TECHS has ≤100 ms misalignment between perspectives; it must be aligned
  before mixing perspectives.
- IDMT/RWC use annotation slash bass; GuitarSet/EGSet12 derive bass from the
  lowest active note.
- Slakh labels are MIDI-derived by pitch-set template matching, so they are
  internally consistent but not human chord annotations.
- RWC 2.0 is now **CC BY-NC 4.0** (not plain CC BY); it is research-only for a
  commercial product.
- ChoCo core is mostly CC BY 4.0, but JAAH, Chordify CASD, and Mozart subsets are
  NC-SA.
- MuQ weights are **CC BY-NC 4.0**.
- GOAT is **research-only, no commercial use, request access**.

---

## 4. Results timeline

External fine test unless noted. “Macro” is supported-class macro-F1.

| Stage | Macro | Exact | MIREX | Bass | Slash | ECE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Production 25-class (GuitarSet p05 only) | — | 0.043 | — | — | — | — |
| Honest fine baseline after leakage fix | 0.147 | 0.320 | 0.385 | 0.346 | 0.065 | 0.172 |
| Context 1.6 s | 0.190 | 0.373 | 0.501 | 0.688 | 0.103 | 0.145 |
| Fine hop + inversion head | 0.246 | 0.463 | 0.618 | 0.716 | 0.160 | 0.130 |
| Corrected mild augmentation | 0.266 | 0.440 | 0.629 | 0.761 | 0.168 | 0.065 |
| Full Slakh fine (1,710 tracks) | 0.278 | 0.451 | 0.633 | 0.773 | 0.182 | 0.083 |
| Frame supervision (mean frames) | 0.268 | 0.468 | 0.620 | 0.778 | 0.174 | 0.023 |
| Frame supervision (centre frame) | 0.261 | 0.474 | 0.640 | 0.823 | 0.206 | 0.085 |
| Long context 64, full data | 0.293 | 0.517 | 0.659 | 0.824 | 0.234 | 0.108 |
| 64 + guitar-only fine-tune | 0.311 | 0.527 | 0.667 | 0.832 | 0.248 | 0.106 |
| 64 guitar-FT + hybrid decode | 0.297 | 0.523 | 0.661 | 0.832 | 0.260 | 0.105 |
| 96-frame / 3-block seed 2 | 0.328 | 0.541 | 0.669 | 0.811 | 0.224 | 0.048 |
| Synthetic seed2-FT + seed3 ensemble | 0.351 | 0.575 | 0.691 | 0.826 | 0.229 | 0.018 |
| 128-frame / 4-block seed 1 | 0.322 | 0.533 | 0.668 | 0.824 | 0.215 | 0.088 |
| Cross-context 96 + 128 | **0.359** | 0.568 | 0.693 | 0.830 | 0.238 | **0.0147** |
| Three contexts incl. guitar-only | 0.354 | **0.576** | **0.699** | 0.829 | 0.240 | 0.016 |
| FT1 + balanced-FT (best slash) | 0.320 | 0.544 | 0.677 | 0.830 | **0.266** | 0.033 |
| MuQ layer 6 (val only) | 0.076 | — | — | — | — | — |
| MuQ layer 2 (val only) | 0.194 | — | — | — | — | — |

Per-source premium for the best macro ensemble: EGSet12 0.263 / exact 0.476;
GuitarSet 0.307 / 0.476; IDMT 0.609 / 0.747; RWC 0.305 / 0.609. The IDMT source is
much easier; GuitarSet/EGSet12/RWC carry the generalization burden.

---

## 5. What worked

1. **Short, boundary-accurate windows (1.6 s).** The original 12.8 s windows
   averaged multiple chords and generalized poorly. 1.6 s is the base.
2. **Long context after per-frame labels.** 64 frames (6.4 s) with per-frame
   supervision improved macro from 0.278 to 0.311 after guitar fine-tuning.
   96 frames / 3 blocks reached 0.328 single-seed.
3. **Frame-level labels and masked bass loss.** Added by `add_frame_labels.py`;
   no CQT recompute. They enabled long-context training and centre-frame eval.
4. **Guitar-domain fine-tuning.** Slakh-pretrained then fine-tuned on real guitar
   sources was a reliable gain: macro 0.293→0.311, slash 0.234→0.248.
5. **Seed and cross-context ensembles.** Two-model probability averaging was the
   strongest selection lever: macro +0.03, exact +0.02, MIREX +0.02 over the best
   single seed. Cross-context (96 + 128) added representation diversity.
6. **Small synthetic rare-chord corpus.** 3,091 windows from Isophonics/Billboard/
   JAAH `.lab` improved exact/MIREX/ECE slightly (+0.004) but not macro.
7. **Temperature/prior calibration for ECE only.** It can improve ECE, but prior
   calibration fitted on guitar val hurt macro; do not use it for the macro gate.
8. **Balanced Slakh subset.** 400 tracks selected by class/inversion coverage
   reduced full-mix dominance and improved macro versus full Slakh in the
   from-scratch long-context run.

### 5.1 Winning configuration (for reproduction)

`context-s96-b3-s2-ft-synth`:

- 96-frame context, 3 transformer blocks, d_model 192.
- Per-frame chord/bass/root/quality/inversion heads + 12-class pitch head.
- Train on guitar + balanced Slakh; then fine-tune on guitar + synthetic
  (3,091 windows), 6–8 epochs at lr 2e-4.
- Evaluate with centre-frame selection and a second model trained on 128 frames.

`context-s128-b4-s1`:

- 128-frame context, 4 blocks, seed 1, guitar + balanced Slakh, 30 epochs.

The two-model average is the best macro/MIREX/ECE finalist.

---

## 6. What did not work

These are documented negative results. Do not repeat without a changed premise.

### 6.1 Data and labels

1. **Slakh full-mix dominance.** Full Slakh improved exact/MIREX/bass but diluted
   the solo-guitar macro. The gate is solo guitar; full mixes are a domain shift.
2. **Synthetic corpus scale-up.** Going from 3,091 to 6,764 windows raised macro
   +0.002 but cost exact/MIREX/ECE. More of the same additive timbre is not the
   answer.
3. **Synthetic fine-tuning of the guitar-only model.** Val macro fell 0.289→0.266.
   The synthetic domain can hurt a domain-matched base.
4. **Synthetic-only pretraining at small scale.** Earlier VST synthetic runs were
   worse; 30 synthetic epochs were excluded by the original program constraint.
5. **BTC pseudo-labels on 264 YouTube clips.** 283 windows, no gain.
6. **RWC/IDMT as a full mix proxy.** RWC-P is the only RWC subset with chord
   labels; the other RWC genres do not solve the chord-data problem.
7. **Adding monophonic/technique recordings as chord data.** IDMT datasets 2/3
   are single-note/technique corpora; they do not teach chords.

### 6.2 Objective and model

8. **Structured composition head as a decoder.** Root × quality × presence
   composition reached exact 0.154 / MIREX 0.210; the flat chord head stayed at
   exact 0.527 after the same fine-tune. Composition from an already-trained flat
   model does not work.
9. **Window-level Viterbi/CRF smoothing.** Best exact 0.525 at self-transition
   0.05 vs 0.527 unsmoothed; higher self-transition was much worse. The window
   predictions are already locally consistent; CRF does not add macro.
10. **Root/quality head fusion.** Negative in earlier phases; do not re-fuse.
11. **Bass composition from the inversion head.** Worse than the 13-class bass
    head.
12. **Larger encoder (conv 96/192, LSTM 192, Dense 384).** Val macro rose but
    external test did not; capacity is not the bottleneck.

### 6.3 Training/selection

13. **Frame supervision alone.** Without long context/data it did not improve
    macro or slash.
14. **SWA / last-K averaging.** Neutral for the 96-frame seeds.
15. **Post-hoc prior calibration for macro.** Fitted on guitar val, it overfit:
    synth ensemble macro 0.351→0.317 and ECE 0.018→0.192. Temperature-only is
    harmless for ECE but does not move macro.
16. **Three-model same-context ensembles.** Diluted the best pair (0.342–0.348
    macro vs 0.359).
17. **128-frame / 4-block.** External macro 0.322/0.306/0.297, worse than 96/3.
    Context/capacity is saturated.
18. **Full augmentation at small scale.** Earlier pitch ±3 + SpecAugment hurt;
    mild/gain augmentation is the safe default.
19. **External-val-only selection.** Noisy and worse; combined val was better.
    With guitar-only fine-tuning, use guitar-only val for the final stage and
    report both.
20. **MuQ direct replacement.** Layer 6 val macro 0.076, layer 2 0.194, CQT
    guitar-only baseline 0.289. MuQ features encode track/timbre identity and do
    not transfer without adaptation.
21. **CQT-bin pitch shift on non-CQT features.** Learned features are not
    frequency-ordered; rolling bins corrupts them. Use `aug-level=gain` for MuQ.

### 6.4 Metric and evaluation

22. **Leakage.** Early Phase 3/4 numbers were invalid because IDMT/RWC tracks had
    appeared in training. Always pass `source=` and use `splits.json`.
23. **Full 102-class macro on 3,121 windows.** 34 classes have <5 frames; the
    metric is dominated by singletons. It is noisy and not a stable production
    target without more support.
24. **Annotator subjectivity.** CASD shows only ~73% major/minor overlap and ~54%
    overlap on complex labels across experts. A single-reference ceiling exists.

---

## 7. Empirical ceilings

### 7.1 CQT + this test set

- **Macro ceiling: ~0.36 full 102-class**, ~0.50 (≥10 frames), ~0.53 (≥20).
- **Slash ceiling: ~0.27** with independent chord/bass heads and 642 inversion
  frames.
- **Exact/MIREX ceiling:** ~0.58 / ~0.70; already strong.
- **Bass/ECE:** already passing; not the bottleneck.

These are ceilings of the current data + CQT + flat objective + this test set,
not universal limits.

### 7.2 Why

- **Data:** real solo-guitar chord data is scarce. GuitarSet 3 h, Guitar-TECHS
  5.2 h (only DI used), EGSet12 12 tracks, IDMT ~5.7 h, RWC-P 100 songs. Slakh is
  full-mix. Rare qualities and inversions are especially scarce.
- **Label geometry:** full 102-class macro rewards rare classes; the test has 15
  singleton classes. A model can improve rare-class F1 without moving the noisy
  full macro much.
- **Objective:** flat 170-way cross-entropy learns common classes; rare-class
  weighting helps only partially.
- **Representation:** CQT is strong for pitch but limited for timbre/effects;
  learned MuQ features overfit track identity without adaptation.
- **Domain:** product practice audio (mic, room, effects, mistakes) is not the
  same as the research corpora.
- **Slash:** chord and bass heads are independent; the bass head is trained with
  masking and inversions but is not jointly decoded with the chord.
- **Selection:** seed variance ~0.018 macro; ensembles help, but not enough to
  create a 0.09 gain.

---

## 8. How to hit the targets

### 8.1 Fix the evaluation protocol first

The current full 102-class macro is not stable enough to be the only production
gate. Decide one of:

**Option A (recommended): two-tier reporting.**

- Primary: macro-F1 over classes with **≥10 frames** in a track-level k-fold
  across all real guitar data.
- Secondary: full 102-class macro, with bootstrap CIs.
- Keep slash, bass, ECE, exact, MIREX, worst-class F1, per-quality F1.
- Require track/player-disjoint splits; report per-player/per-corpus results.

**Option B: enlarge and balance the test set.**

- Collect enough real tracks so every measured class has ≥10 test windows.
- With 102 classes and ~10 windows/class minimum, the test needs many more tracks;
  this is a data-collection task, not a quick fix.
- Keep the current 3,121-window set as a fixed regression test.

**Proposed production gate (to approve):**

| Metric | Proposed target |
| --- | ---: |
| Macro-F1, classes with ≥10 test frames (k-fold) | ≥0.60 |
| Macro-F1, full supported classes (secondary) | ≥0.45 |
| Slash accuracy | ≥0.50 |
| Bass accuracy (known) | ≥0.85 |
| ECE | ≤0.05 |
| Exact accuracy | ≥0.65 |
| WCSR-MIREX | ≥0.75 |
| CPU latency on target device | <120 ms per 1.6 s window |
| Export parity | 100% argmax match with evaluated heads |

Do not move the goalposts silently; record the decision in `PRIORITIES.md` and
the model card.

### 8.2 Data acquisition — public sources that can move the needle

| Source | Size | Labels | Licence/access | Expected value | Priority |
| --- | ---: | --- | --- | --- | --- |
| **Guitar-TECHS multi-perspective** | 4 perspectives × 56 chord tracks + 12 music | per-string MIDI, chord timelines | CC BY 4.0; already downloaded | 4× the same real guitar data with DI/amp/ego/exo timbres; cheap immediate gain | **P0** |
| **EGDB-PG** | 240 tracks, 2 h clean, 514 h rendered, 256 amp/cab presets | MIDI/tab; derive chords | Zenodo CC BY 4.0; 27 GB subset, 135 GB full | Large realistic amp-rendered guitar corpus; timbre robustness | **P0** |
| **GOAT** | 5.9 h DI + 29.5 h amped, 172 files | Guitar Pro/tab/MIDI | Research-only, request, no commercial | Best real electric-guitar chord/tab source; use only in research track | **P1 (research)** |
| **EGFxSet** | 8,970 notes, 12 h 28 | single notes + effect params | CC BY 4.0 | Timbre/effect robustness; not chord labels | P1 (aux) |
| **GuitarSet / Guitar-TECHS / EGSet12** | 3 h + 5.2 h + 12 tracks | existing | CC BY 4.0 | Already used; add perspectives, not new repertoire | done / P0 |
| **EGDB** | 240 tracks, ~1.5–2 h clean | MIDI/tab | CC BY 4.0 | Source of EGDB-PG; can derive chords/inversions | P1 |
| **RWC 2.0** | 23 h 23, 328 tracks | RWC-P chords only | CC BY-NC 4.0 | Research-only; RWC-P already used | P2 (research) |
| **DadaGP** | 26,181 Guitar Pro scores, 1,200 h symbolic | tablature | request; paper CC BY 4.0 | Render with SynthTab; huge symbolic source | P1 (synthetic) |
| **SynthTab** | 13,113 h, 20,715 tracks, 23 timbres | string-accurate tab | check licence/access | Massive synthetic pretraining; domain gap remains | P1 (synthetic) |
| **LA MIDI / Lakh MIDI** | 404k / 176k MIDI | MIDI | check licences | Render guitar chords with soundfonts; synthetic pretraining | P2 |
| **ChoCo symbolic** | 17,803 symbolic annotations | Harte/lead-sheet | CC BY core; JAAH/CASD NC | More symbolic source for synthetic rare chords | P1 |
| **HookTheory / SheetSage** | 22k segments / 13k songs, 50 h | lead-sheet chords | CC BY-NC-SA 3.0 | Research only; chord-progression diversity | P2 |
| **SheetSage-A2S** | 9,468 clips / 61 h | **kern + chords | CC BY-NC-ND; no audio distributed | No derivatives/audio distribution; avoid | reject |
| **JAAH** | 113 jazz recordings | chords | CC BY-NC-SA | Research-only; jazz inversions | P2 |
| **CASD** | 50 songs × 4 annotators | chords + subjectivity | CC BY-NC-SA | Ambiguity/soft-target evaluation, not volume | P2 |
| **Billboard / Isophonics / UsPop / MARL** | 890 / 300 / 195 / 1,217 | chords | annotations open; audio restricted | Only if you have licensed audio; otherwise not usable | P2 |
| **Practice data + corrections** | your users | corrected chord/bass | owned, consent | Highest domain match; rare classes/inversions; feedback loop | **P0** |

**Immediate P0 order:**

1. **Guitar-TECHS all perspectives.** The data is already on the volume for DI;
   add `micamp`, `ego`, `exo` for P1/P2 chord sets. Align ≤100 ms offsets; train
   all four as separate tracks. This is the cheapest real-data multiplier.
2. **EGDB-PG subset.** Download the 27 GB subset (24 presets) first; derive chord
   and inversion labels from MIDI; hold out by track. Scale to 135 GB only after
   a learning-curve check.
3. **Practice/correction data.** Start collecting now; it has the highest product
   value and is licence-safe.

**Research-only P1:** GOAT (request), DadaGP/SynthTab rendering, ChoCo symbolic
expansions. Keep these out of production weights if the product is commercial.

**Rough data budget (estimate, to validate with learning curves):**

- 50–150 hours of real, guitar-domain, class-balanced chord audio, with at least
  10k inversion windows across roots/qualities.
- 10k–50k user-corrected windows (or 2k–5k corrected segments) from practice data,
  sampled for rare classes/inversions and filtered for label quality.
- 100+ hours of amplifier-rendered guitar (EGDB-PG subset) for timbre robustness;
  scale only if the learning curve justifies it.
- A held-out evaluation set with ≥10 windows per measured class, split by
  track/player/recording.
- Annotation cost is dominated by rare-class/inversion coverage, not total hours;
  budget expert review of a gold subset and double annotation for QA.

### 8.3 Practice data and corrections

The product already has a correction path: `backend/app/corrections_dataset.py`
exports `original_value` → `corrected_value` JSONL from job correction histories.
Extend it into a training dataset with audio context and model provenance.

**Record per correction:**

- schema version, job/session id (pseudonymous), user/song hash, timestamp;
- app version, model version/checkpoint hash, feature version;
- audio window hash and a stored CQT/feature vector (not raw audio by default);
- predicted chord, bass, inversion, confidence/top-k;
- corrected chord, bass, inversion, ambiguity tags, user confidence;
- device/mic/room flags (optional), consent/terms version;
- reason/category (misheard quality, wrong root, inversion, timing, other).

**Sampling for training (active learning):**

- high predictive entropy / low margin;
- ensemble disagreement across the 96/128/64 models;
- rare-class quota (all 14 qualities × 12 roots; hdim7, dim7, minmaj7, min6,
  sus2, sus4, aug, inversions);
- inversion quota (bass ≠ root), all 12 bass classes;
- user-reported corrections;
- random control sample (to avoid selection bias);
- song/player/device diversity.

**Label quality:**

- gold set with double annotation and adjudication;
- measure inter-annotator agreement; store soft labels for ambiguous cases
  (maj6 ≡ min7, sus2/sus4, omitted fifths);
- separate annotation errors from model errors;
- re-audit a fixed sample each release.

**Training with corrections:**

- correction-weighted loss (e.g., 2–5× vs research labels);
- hard-example mining; class-balanced sampler; source/user balancing;
- hold out users/songs/recordings, not random windows;
- report rare-class recall without common-class regression;
- avoid training on the same user/song too many times (overfit);
- snapshot data with timestamps so models remain reproducible;
- keep a shadow model and compare before promotion.

**Legal/privacy:**

- explicit consent and terms for using practice audio/corrections in training;
- data minimization: store features/hashes, not raw audio, unless needed;
- deletion/opt-out path; encryption; retention policy;
- model cards and provenance; no NC/research-only data in commercial weights;
- jurisdiction-specific review before launch.

**Cold start:**

- use the current best model to pre-label practice audio;
- ask users only for low-confidence or wrong segments (high ROI);
- combine with public CC BY data for initial training;
- evaluate on held-out practice sessions, not only research corpora.

### 8.4 Modeling plan after data

1. **Add data first, keep the CQT/96 context baseline.** Train 3 seeds on
   guitar-only + multi-perspective Guitar-TECHS + EGDB-PG subset. Evaluate with
   the revised protocol. Do not change the architecture until the learning curve
   is measured.
2. **Joint chord + bass objective.** The current heads are independent. Try a
   joint (chord, bass) decoder or a structured component model trained **from
   scratch** (not composition from a flat model):
   - root, triad, seventh, bass, inversion, pitch-class heads;
   - consistency loss between composed chord and component heads;
   - CRF/Viterbi for boundary smoothing only;
   - joint slash scoring.
   The previous composition experiment failed because it was an auxiliary head on
   a flat-trained model; a from-scratch component model with inversion-rich data
   is still untested.
3. **Hard-class curriculum.** Base triads first, then sevenths/sixths/sus, then
   altered/rare; gradually shift the sampling distribution to balanced. Prior
   curriculum work reports large class-wise gains for a small frame-accuracy cost.
4. **Pretrained features only with adaptation.** MuQ direct replacement failed.
   If tried again: layer-wise probe (layers 0–3 first), per-frame/per-track
   normalization, domain-adversarial loss, or a two-stream CQT+MuQ model. Do not
   scale a direct swap.
5. **Synthetic data as augmentation, not replacement.** Render with soundfonts/
   amps/effects; use a small blend; validate that exact/MIREX do not regress.
6. **Distill only after gates.** 96/128 ensemble → single student; export parity;
   CPU latency.

### 8.5 Milestones and go/no-go

| Milestone | Work | Exit criteria |
| --- | --- | --- |
| M0 | Agree evaluation protocol (full vs min-support; k-fold; CIs) | Written decision in `PRIORITIES.md`; harness reports both |
| M1 | Guitar-TECHS all perspectives + EGDB-PG subset ingestion | Learning-curve gain; exact/MIREX not regressed |
| M2 | Practice/correction schema + collection + first 5–10k corrections | Held-out correction set; rare-class recall improves |
| M3 | Joint chord+bass/structured model on expanded data | Slash ≥0.40; min-support macro ≥0.55 |
| M4 | 3 seeds + cross-context ensemble + calibration | Production gate table green |
| M5 | Distillation/export/latency/shadow/A-B | Parity, latency, rollback proven |
| M6 | Correction loop at scale | Drift monitoring, periodic retrain |

**Realistic expectation:** with CC BY real data (Guitar-TECHS perspectives +
EGDB-PG) and 10k+ corrections, min-support macro ≥0.55 and slash ≥0.40 are
plausible; full 102-class macro 0.45 on the current 3,121-window test is unlikely
without a larger/balanced test or a metric decision. Do not promise the full gate
before measuring the new data.

---

## 9. Production replacement plan (Phase 5)

Preconditions:

- All agreed gates pass on the held-out external test and a held-out practice set.
- Export parity: TFLite/ONNX outputs match evaluated heads (chord, bass, aux).
- CPU latency <120 ms per 1.6 s window on target devices; memory budget met.
- Calibration ECE ≤0.05; confidence usable for UI.
- Model card, provenance, licence audit, and rollback plan.

Steps:

1. Distill the winning ensemble (96/128/64) into one student, or ship a small
   ensemble if latency allows.
2. Export TFLite and ONNX with all exported heads; verify argmax/score parity.
3. Add `HARMONIQ_CHORD_MODEL_V2` feature flag; keep the old model as fallback.
4. Shadow mode: run v2 on live audio, compare to production without user impact.
5. Canary rollout to a small cohort; monitor exact/MIREX proxy, slash/bass,
   confidence distribution, correction rate, latency, crashes.
6. Promote only if metrics hold; keep a one-command rollback.
7. Update `model_registry.json`, `docs/MODEL_PROVENANCE.md`, `docs/EVALUATION.md`.
8. Do not ship research-only data/weights (GOAT, JAAH, RWC 2.0, HookTheory,
   SheetSage, MuQ weights, CASD).

---

## 10. Remaining phases and checklists

### Phase 4f — Real guitar data (next)

- [ ] Upload/align Guitar-TECHS `micamp`, `ego`, `exo`; extract fine windows and
      frame labels; train all perspectives.
- [ ] Download EGDB-PG 27 GB subset; parse MIDI/tab; derive chord/bass/inversion
      labels; track-level splits.
- [ ] Request GOAT for the research track; do not mix into commercial weights.
- [ ] Verify EGFxSet as timbre augmentation only.
- [ ] Re-run the learning curve with 3 seeds; compare to `context-s96-b3-s2-ft-synth`.

### Phase 4g — Practice/correction loop (start now)

- [ ] Extend `corrections_dataset.py` schema with audio hash/features and model
      version; add consent/terms.
- [ ] Implement low-confidence/rare-class/inversion sampling.
- [ ] Build a gold set and double-annotation QA.
- [ ] Train with correction weighting; hold out users/songs.
- [ ] Evaluate rare-class recall and common-class regression.
- [ ] Add a shadow model/drift dashboard.

### Phase 4h — Joint chord/bass and hard classes

- [ ] Build a from-scratch structured component model (not head fusion).
- [ ] Add inversion-rich training data (EGDB-PG, GOAT, corrections).
- [ ] Try CRF/Viterbi for boundaries only; measure macro separately.
- [ ] Target slash ≥0.40 first, then ≥0.50.

### Phase 5 — Distillation/deployment

- [ ] Student training, export, parity, latency.
- [ ] Feature flag, shadow, canary, rollback.
- [ ] Registry/provenance/docs updates.

### Phase 6 — Correction loop at scale

- [ ] Periodic retraining, drift monitoring, correction-weighted updates.
- [ ] Privacy/licence review; model cards.
- [ ] Rare-class recall without common-class regression.

---

## 11. Continuation prompt for the next session

> You are continuing the Harmoniq 170-class chord program. Production is
> untouched. Read `docs/chord/CHORD_170_PROGRAM_REPORT.md` and
> `docs/audit/amt/chord170_phases_1_3.json`.
>
> Current best: macro 0.359 (full 102 classes), exact 0.576, MIREX 0.699, bass
> 0.834, slash 0.266, ECE 0.0147. Best checkpoints:
> `/runs/chord170/context-s96-b3-s2-ft-synth/best.keras` +
> `/runs/chord170/context-s128-b4-s1/best.keras` (cross-context ensemble).
> Bass and ECE pass; macro and slash fail.
>
> Next work, in order:
> 1. Agree the evaluation protocol: full 102-class macro vs minimum-support
>    macro (≥10/≥20), track-level k-fold, CIs. Write the decision down.
> 2. Add real guitar data: Guitar-TECHS all four perspectives, then EGDB-PG
>    subset (CC BY 4.0). Keep GOAT/MuQ/RWC/HookTheory/JAAH out of commercial
>    weights.
> 3. Start practice/correction data collection now; extend
>    `backend/app/corrections_dataset.py` with audio/features/model provenance.
> 4. Only after the data learning curve, try a from-scratch joint chord+bass /
>    structured component model and/or an adapted pretrained encoder.
> 5. Do not start Phase 5 until all agreed gates pass. One commit per logical
>    change; stage only chord170 files; `npm run lint` and chord tests must pass.
>
> Modal volumes: `harmoniq-chord170-data` (`/chord170`) and
> `harmoniq-chord170-runs` (`/runs`). Re-upload `app` and `scripts` after code
> changes. Use `modal run --detach` for long jobs.

---

## 12. Appendix

### 12.1 Exact commands used

```bash
cd backend

# External fine test (two-context best)
modal run scripts/modal_chord_170.py::eval_context \
  --checkpoint /runs/chord170/context-s96-b3-s2-ft-synth/best.keras \
  --checkpoint-b /runs/chord170/context-s128-b4-s1/best.keras \
  --context-frames 96 --context-frames-b 128 \
  --split test \
  --sources guitarset_fine,egset12_fine,idmt_smt_guitar_fine,rwc_fine \
  --structured-decode none

# Three-context exact/MIREX best
modal run scripts/modal_chord_170.py::eval_context \
  --checkpoint /runs/chord170/context-s96-b3-s2-ft-synth/best.keras \
  --checkpoint-b /runs/chord170/context-s128-b4-s1/best.keras \
  --checkpoint-c /runs/chord170/context-s96-b3-guitar-only/best.keras \
  --context-frames 96 --context-frames-b 128 --context-frames-c 96 \
  --split test \
  --sources guitarset_fine,egset12_fine,idmt_smt_guitar_fine,rwc_fine \
  --structured-decode none

# Best slash
modal run scripts/modal_chord_170.py::eval_context \
  --checkpoint /runs/chord170/context-full-s64-guitarft/best.keras \
  --checkpoint-b /runs/chord170/context-s64-guitar-bal-ft/best.keras \
  --context-frames 64 --context-frames-b 64 \
  --split test \
  --sources guitarset_fine,egset12_fine,idmt_smt_guitar_fine,rwc_fine \
  --structured-decode none
```

### 12.2 Dataset licence notes

| Dataset | Licence / access |
| --- | --- |
| GuitarSet | CC BY 4.0 (verify current) |
| Guitar-TECHS | CC BY 4.0 |
| EGSet12 | CC BY 4.0 |
| EGFxSet | CC BY 4.0 |
| EGDB / EGDB-PG | Zenodo CC BY 4.0 (verify underlying EGDB terms) |
| RWC 2.0 | CC BY-NC 4.0 — research only |
| GOAT | research-only, request, no commercial |
| DadaGP | request for data; paper CC BY 4.0 |
| SynthTab | check licence/access at synthtab.dev |
| LA MIDI / Lakh MIDI | check licence |
| ChoCo core | CC BY 4.0; JAAH/CASD/Mozart NC-SA |
| HookTheory / SheetSage | CC BY-NC-SA 3.0 |
| SheetSage-A2S | CC BY-NC-ND 4.0; no audio distribution |
| MuQ weights | CC BY-NC 4.0 |
| CASD | CC BY-NC-SA 4.0 |
| Billboard / Isophonics / UsPop / MARL | annotations open; audio restrictions |

### 12.3 Research links used

- MIREX 2026 ACE results: https://music-ir.org/mirex/wiki/2026:Audio_Chord_Estimation_Results
- ChordFormer: https://arxiv.org/abs/2502.11840
- Structured decomposition (ISMIR 2019): https://archives.ismir.net/ismir2019/paper/000078.pdf
- Structured training (ISMIR 2017): https://brianmcfee.net/papers/ismir2017_chord.pdf
- Curriculum learning for rare chords: https://archives.ismir.net/ismir2021/paper/000073.pdf
- SheetSage2: https://arxiv.org/abs/2610.05336
- SLASH MIREX 2026: https://chordict.com/labs/slash-mirex-2026.pdf
- MuQ: https://github.com/tencent-ailab/MuQ
- GOAT: https://arxiv.org/abs/2509.22655 and https://zenodo.org/records/15690894
- Guitar-TECHS: https://guitar-techs.github.io/ and https://zenodo.org/records/14963133
- EGFxSet: https://egfxset.github.io/ and https://zenodo.org/records/7044411
- EGDB-PG: https://zenodo.org/records/19789500 and https://arxiv.org/abs/2504.07406
- SynthTab: https://arxiv.org/abs/2309.09085 and https://www.synthtab.dev
- DadaGP: https://arxiv.org/abs/2107.14653
- ChoCo: https://github.com/smashub/choco/
- CASD: https://github.com/chordify/CASD
- RWC 2.0: https://zenodo.org/communities/rwc-music/ and https://github.com/rwc-music/rwc-annotations
- Serenade human-in-the-loop: https://arxiv.org/abs/2310.11165
- Noisy Student for rare chords: https://arxiv.org/abs/2012.07055

### 12.4 Negative-results index

Use this as a checklist before proposing an experiment:

1. Presence gate / unexported-head selection.
2. MT3-template teacher.
3. Synthetic-only pretraining at small scale.
4. Full augmentation at small scale.
5. Bass composition from the inversion head.
6. Root/quality head fusion.
7. Per-track normalization / global standardization at small scale.
8. External-val-only selection.
9. Larger encoder.
10. BTC pseudo-labels on 264 clips.
11. 25/277-class heads at equal budget.
12. Frame supervision alone.
13. Structured composition decoding.
14. Window-level Viterbi.
15. SWA/last-K averaging.
16. Post-hoc prior calibration for macro.
17. Three-model same-context ensembles.
18. 128-frame / 4-block.
19. Synthetic scale-up.
20. MuQ direct replacement.
21. Guitar-only synthetic fine-tuning.

---

## 13. Bottom line

The current model is a strong research baseline and already far better than the
production 25-class model on exact/MIREX, but it is not a production replacement
for the 170-class goal: full macro 0.359 and slash 0.266 are well short of 0.45
and 0.50, and the 95% CI does not reach the macro gate.

The path to production is not another CQT ensemble. It is:

1. define a statistically meaningful gate;
2. add real, guitar-domain, rare-quality/inversion-rich data (Guitar-TECHS
   perspectives, EGDB-PG, owned practice data);
3. collect corrections with consent and active learning;
4. train a joint chord/bass structured model on that data;
5. only then distill, export, shadow, and replace production.

With those changes, a min-support macro of 0.55–0.60 and slash of 0.40–0.50 is a
reasonable target. The full 102-class macro of 0.45 on the current 3,121-window
test is not a reasonable engineering target without a larger/balanced test or an
explicit metric decision.
