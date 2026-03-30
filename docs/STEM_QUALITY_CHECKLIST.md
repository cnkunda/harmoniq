# Stem separation quality gate (`htdemucs_6s`)

Formal go/no-go checks for **guitar** stem usability before building tabs, transcription, or coach features on top of separation.

## Stop here if fail

If **either** the automated smoke script **or** the listening checks below **fail**, **stop**: do not treat stems as validated for downstream pipeline work. Fix the input (different mix, mastering, or source), re-run Demucs on a capable machine, or adjust expectations — **do not** tune Demucs hyperparameters as part of this gate (out of scope).

Re-run this gate after changing the separation model, upgrading Demucs, or materially changing ingest (sample rate, mono fold-down, etc.).

## Automated smoke (`backend/scripts/smoke_stems.py`)

From the backend package root (with your venv active and Demucs installed per `backend/README.md`):

```bash
cd backend
python scripts/smoke_stems.py path/to/mix1.wav path/to/mix2.wav
```

Optional diagnostic PNGs (requires `matplotlib`: `pip install matplotlib`):

```bash
python scripts/smoke_stems.py path/to/mix1.wav path/to/mix2.wav --spectrograms
```

Artifacts are written under `artifacts/stem_smoke/<slug>/` (gitignored). The script exits **non-zero** if any track fails the automated gates.

### When automation disagrees with your ears

Heuristics can **false-positive** (e.g. vocal envelope correlation high in dense vocal+guitar pop even when isolation is usable). If the script fails but the guitar stem sounds clearly usable and bleed is acceptable, **trust listening**: note the override in the verification log, re-run after changing thresholds only as a team decision, and still treat obvious garbage (silent stem, vocal-heavy stem) as **FAIL**.

`ffmpeg` / `demucs` errors are raised with command output in the message when possible — if something still fails mysteriously, confirm `ffmpeg` and your venv’s `demucs` run from the same shell.

### Manual-only path

If you cannot run Demucs locally (no GPU/CPU budget, install blocked, etc.), **do not** rely on the script. Complete the **Verification log** using stems produced elsewhere: same criteria — guitar must be clearly audible on the guitar stem with acceptable bleed. Record **FAIL** if the stem is unusable. The **Stop here if fail** rule still applies.

## Listening checks

For each song, listen to **guitar stem alone**, then **mix minus guitar** if helpful:

1. **Guitar audible** — the stem is not silence, noise, or only room; the part you expect to transcribe is recognizable.
2. **Minimal bleed** — vocals, drums, and cymbals are not dominant in the guitar stem; occasional leakage may be acceptable if the guitar part is still the focus.

## “No guitar” / bad isolation

Treat as **FAIL** if:

- The guitar stem is near-silent while the full mix obviously contains guitar.
- The guitar stem is mostly vocals or drums (heavy bleed).
- The automated script reports failure (see script output for which gate failed).

Align with product copy intent: users should get a clear “couldn’t isolate a clean guitar track” style outcome rather than silently bad tabs.

## Verification log (minimum two songs)

Complete **two distinct mixes** before relying on stem quality for feature work: **one easy** (simpler arrangement, guitar relatively clear in the mix) and **one dense** (busy full-band or vocal-heavy). That pair stress-tests bleed and “no guitar” behavior better than two similar tracks.

| # | Mix type | Song / source | Date | Operator | `smoke_stems` | Audible guitar | Low bleed | Notes |
|---|----------|----------------|------|----------|----------------|----------------|-----------|-------|
| 1 | Easy | | | | PASS / FAIL | Y / N | Y / N | |
| 2 | Dense | | | | PASS / FAIL | Y / N | Y / N | |

*Example row format (replace with real data after your runs):*

| # | Mix type | Song / source | Date | Operator | `smoke_stems` | Audible guitar | Low bleed | Notes |
|---|----------|----------------|------|----------|----------------|----------------|-----------|-------|
| *sample* | Easy | *Local WAV — guitar-forward* | *—* | *—* | *PASS* | *Y* | *Y* | *Replace with real verification.* |

Both numbered rows **1** and **2** must be filled with real outcomes (not the italic sample alone), with row **1** = easy and row **2** = dense.
