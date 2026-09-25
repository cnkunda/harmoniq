# Chord Model Performance Refactor Plan

## Problem Statement

The chord model achieves ~70% synthetic validation accuracy but only ~35% real-world validation accuracy, producing a ~36% domain gap. The model has been stuck without improvement. Root cause analysis identified three structural issues that must be addressed in order of impact.

## Root Causes (Verified Against Codebase)

### 1. Vocabulary too large for available real data (277 classes)
- `backend/app/chord_vocab.py:52` defines `NUM_CLASSES = 277` (23 qualities x 12 roots + N)
- With ~833 real .npz files across 5 sources (each containing hundreds of sliding windows), most of the 277 classes have zero real training examples
- The model learns synthetic-only representations for ~200 classes
- BTC and Korzeniowski achieve 73-76% at 25 classes (12 major + 12 minor + N)

### 2. Feature resolution too low (40 bins)
- `build_chord_tflite.py:89-93`: `BINS_PER_OCTAVE=12, NUM_OCTAVES=3, CHROMA_BINS=36, BASS_BINS=4, FEATURE_DIM=40`
- Covers E2-B4, missing upper harmonic partials that distinguish chord qualities
- Every competitive system uses 144+ bins (24 bins/octave x 6 octaves)
- `BASS_BINS` is redundant: `cqt[:4].copy()` appended as separate channel (`build_chord_tflite.py:394,446`)

### 3. Training curriculum learns synthetic patterns first
- Stage 1 (epochs 1-30): synthetic-heavy (`build_chord_tflite.py:3656-3738`)
- Stage 2 (epochs 31-100): real-heavy (`build_chord_tflite.py:3740-3832`)
- Model spends most plastic early epochs learning synthetic feature distributions
- `GradualTransitionCallback` ramps from `_s1_real_pct` (~26%) to 80% (`build_chord_tflite.py:3807-3815`)

### Important Correction to Original Analysis
The original analysis claimed synthetic uses L1-normalized templates while real uses "librosa log-magnitude CQT." This is **incorrect**. Both use L1-normalized magnitude CQT:
- Synthetic: `build_chord_tflite.py:442-444` — `cqt = cqt / total`
- Real extraction: `extract_guitarset_cqt.py:69-70` — `cqt = cqt / norms` (L1)
- Real extraction: `extract_idmt_cqt.py:62-63` — same pattern

The domain gap is caused by structural differences (clean integer-bin spikes vs spread overtone energy), not normalization mismatch.

---

## Implementation Plan: 3 Commits

### Pre-Commit: Shared Constants Module

Before any commits, extract duplicated constants into a single importable location. Currently 8+ files independently re-declare the same constants, making coordinated changes fragile.

**New file: `backend/app/cqt_constants.py`**

```python
"""Shared CQT feature constants for training and inference.

Single source of truth — all extraction scripts, training, and inference
import from here instead of re-declaring constants.
"""
BINS_PER_OCTAVE = 24
NUM_OCTAVES = 6
CHROMA_BINS = BINS_PER_OCTAVE * NUM_OCTAVES  # 144
BASS_BINS = 0
FEATURE_DIM = CHROMA_BINS  # 144
WINDOW = 128
HOP_FRAMES = 64
TARGET_SR = 44100
HOP_SEC = 0.1
```

**Files to update** (replace standalone constant blocks with imports):

| File | Lines | Change |
|------|-------|--------|
| `backend/scripts/build_chord_tflite.py` | 89-93 | Replace with `from app.cqt_constants import *` |
| `backend/scripts/extract_guitarset_cqt.py` | 41-46 | Replace with import |
| `backend/scripts/extract_idmt_cqt.py` | 37-42 | Replace with import |
| `backend/scripts/extract_guitar_techs_cqt.py` | 48-50 | Replace with import |
| `backend/scripts/extract_egset12_cqt.py` | 42-44 | Replace with import |
| `backend/scripts/extract_damp_vpb.py` | 46-48 | Replace with import (active AGENTS.md says unavailable, but file exists) |
| `backend/scripts/extract_jaah_cqt.py` | 35-42 | No constants block — imports `N_CHORD_IDX` from `user_audio_pipeline`. Has hardcoded `n_bins=36` at line 62 (fixed in Commit B). |
| `backend/scripts/crawl_chord_videos.py` | 57-60 | Replace with import |
| `backend/scripts/render_synthetic_guitar.py` | 41-45 | Replace with import |
| `backend/scripts/user_audio_pipeline.py` | 35-38 | Replace with import |
| `backend/scripts/pseudo_label_pipeline.py` | 42-44 | Replace with import |
| `backend/scripts/cqt_distribution_analyzer.py` | 23-25 | Replace with import |
| `backend/app/chord_inference.py` | 67-71 | Replace with import |

---

### Commit A: Vocabulary Reduction (277 → 25 classes)

**Impact**: Highest. **Risk**: Medium. **Files**: ~15 modified.

#### A1. `backend/app/chord_vocab.py` — Add MIREX mapping

Add after existing definitions (line 52):

```python
# MIREX 25-class vocabulary: 12 major + 12 minor + N
# Maps each of the 277 original classes to the closest major/minor/N class.
MIREX_QUALITY_MAP: dict[str, str] = {
    # Identity — these are already in the 25-class vocab
    "maj": "maj", "min": "min",
    # Map to major (share major triad or are major-ish harmonically)
    "7": "maj", "maj7": "maj", "9": "maj", "maj9": "maj",
    "11": "maj", "13": "maj",
    "7#9": "maj", "7b9": "maj", "7#5": "maj", "7b5": "maj", "alt7": "maj",
    "sus2": "maj", "sus4": "maj", "7sus4": "maj",
    "aug": "maj", "6": "maj",
    # Map to minor (share minor triad)
    "min7": "min", "min9": "min", "min6": "min",
    "dim": "min", "dim7": "min",
}

# 25-class vocabulary
MIREX_VOCAB: list[str] = (
    [f"{root}:maj" for root in ROOT_NOTES]
    + [f"{root}:min" for root in ROOT_NOTES]
    + ["N"]
)
MIREX_TO_IDX: dict[str, int] = {chord: i for i, chord in enumerate(MIREX_VOCAB)}
NUM_CLASSES_MIREX = 25

# Lookup: for each of the 277 class indices, what is its quality string?
_CHORD_CLASS_QUALITIES: list[str] = []
for _q in CHORD_INTERVALS:
    for _ in range(12):
        _CHORD_CLASS_QUALITIES.append(_q)

def mirex_label(chord_277_idx: int) -> int:
    """Map a 277-class index to the corresponding 25-class index.

    N (index 276) maps to N (index 24).
    Chord classes map through MIREX_QUALITY_MAP to the nearest major/minor.
    """
    if chord_277_idx >= NUM_CLASSES - 1:
        return NUM_CLASSES_MIREX - 1  # N → 24
    quality = _CHORD_CLASS_QUALITIES[chord_277_idx]
    root = chord_277_idx % 12
    target_quality = MIREX_QUALITY_MAP.get(quality, "maj")
    return MIREX_TO_IDX[f"{ROOT_NOTES[root]}:{target_quality}"]
```

#### A2. `backend/scripts/build_chord_tflite.py` — Training changes

| Line(s) | Change |
|---------|--------|
| 44-51 | Add imports: `MIREX_VOCAB, NUM_CLASSES_MIREX, mirex_label, MIREX_QUALITY_MAP` |
| 104 | `N_INDEX = NUM_CLASSES_MIREX - 1  # 24` (was `NUM_CLASSES - 1 = 276`) |
| 112-118 | Simplify `QUALITY_GROUPS` to `{"triad": {"maj", "min"}, "no_chord": {"N"}}`. Note: this is cosmetic — the other 3 groups (`extended`, `altered`, `suspended_other`) are removed from per-epoch logging but never used in training logic. `compute_grouped_accuracy` handles missing groups gracefully via `mask.sum() == 0 → reports 0.0` |
| 883 | In `generate_dataset`: after building `X, y`, map labels: `y = np.array([mirex_label(idx) for idx in y], dtype=np.int32)` |
| ~3540 | In `run_pipeline` after `mix_datasets` (line 3531) and before train/val split (line 3547): map all real data labels: `y_all = np.array([mirex_label(y) for y in y_all], dtype=np.int32)` |
| 1412 | `_n_chord_classes` stays at 276 (used for template generation, not label space) |
| 1594 | **Critical fix**: `_label_after_pitch_shift` — change `if label_idx >= self._n_chord_classes:` to `if label_idx >= N_INDEX:` (was checking >=276, must check >=24) |
| 1741, 1836 | `Dense(NUM_CLASSES, ...)` → `Dense(NUM_CLASSES_MIREX, ...)` |
| 3600 | `y_val_onehot = to_categorical(y_val, NUM_CLASSES_MIREX)` |
| 3607-3611 | `y_val_dict["chord_probs"]` uses `NUM_CLASSES_MIREX` (auto via to_categorical) |

**Backward compatibility for `collect_real_n_templates`** (line 314-346):

The function uses `n_idx = NUM_CLASSES - 1` to find N frames in .npz files. With vocab reduction, this becomes 24, but .npz files still have N at index 276. Fix:

```python
def collect_real_n_templates(data_dirs: list[Path]) -> list[np.ndarray]:
    n_idx_new = NUM_CLASSES_MIREX - 1  # 24 (new N index)
    n_idx_old = NUM_CLASSES - 1        # 276 (old N index in stale .npz files)
    templates: list[np.ndarray] = []
    for data_dir in data_dirs:
        cqt_dir = data_dir / "processed" / "cqt"
        if not cqt_dir.exists():
            continue
        for npz_path in sorted(cqt_dir.glob("*.npz")):
            try:
                data = np.load(npz_path)
                features = data["features"]
                labels = data["labels"]
                n_mask = (labels == n_idx_new) | (labels == n_idx_old)
                templates.extend(features[n_mask])
            except Exception as e:
                print(f"  [WARN] skipping {npz_path.name}: {e}")
    return templates
```

#### A3. `backend/app/chord_inference.py` — Inference with 25 classes

| Line(s) | Change |
|---------|--------|
| 33-44 | Replace independent vocabulary with MIREX imports. Remove lines 33-44 entirely. |
| New imports | `from app.chord_vocab import MIREX_VOCAB, NUM_CLASSES_MIREX, MIREX_TO_IDX, MIREX_QUALITY_MAP` |
| After imports | `CHORD_VOCAB = MIREX_VOCAB` |
| | `_CHORD_TO_IDX = MIREX_TO_IDX` |
| | `_NUM_CLASSES = NUM_CLASSES_MIREX` |
| 46-60 | `CHROMA_VOCAB` / `_CHROMA_TO_FULL_IDX`: update to map chroma predictions to 25-class indices. The chroma path already restricts to 5 qualities (maj, min, 7, maj7, min7). Map these through `MIREX_QUALITY_MAP`: 7→maj, maj7→maj, min7→min. So chroma only predicts maj/min/N → 25 classes. |
| 75-87 | `_circular_cqt_pad`: unchanged in Commit A (Commit B handles bins) |
| 195-213 | `_extract_features`: unchanged in Commit A (Commit B handles bins) |

#### A4. `backend/app/viterbi_decoder.py`

| Line | Change |
|------|--------|
| 42 | `vocab_size: int = 25` (was 277) |

#### A5. `backend/app/chord_transitions.py` — 25x25 transition matrix

| Line(s) | Change |
|---------|--------|
| 14-18 | Import `MIREX_VOCAB, NUM_CLASSES_MIREX` instead of `CHORD_VOCAB, _NUM_CLASSES` |
| 18 | `_NUM_CLASSES = NUM_CLASSES_MIREX  # 25` |
| 24 | `_CHORD_TO_IDX = {chord: i for i, chord in enumerate(MIREX_VOCAB)}` |
| 74-79 | `_parse_chord`: now parses 25-class labels (e.g., "C:maj", "C:min", "N") |
| 50-60 | Diatonic patterns reference quality strings. With only "maj" and "min", the patterns simplify. "7" and "dim" entries map to "maj" and "min" respectively. Add quality remapping at load time. |
| Cache | Delete `data/transition_matrix.npy` (the module-level singleton in `chord_transitions.py`) and `data/annotations/transition_matrix_empirical.npy` (from `build_empirical_transition_matrix.py`). Re-run `python scripts/build_empirical_transition_matrix.py` to rebuild the latter before training. |

#### A6. `backend/scripts/build_empirical_transition_matrix.py`

| Line(s) | Change |
|---------|--------|
| 24 | Import `NUM_CLASSES_MIREX, mirex_label` |
| All | Map annotation chords through `mirex_label()` before counting transitions |
| 381 | Output matrix becomes (25, 25) |

Note: No `--force` flag exists (docstring at line 8 is wrong). Script always overwrites.

#### A7. Tests to update

**21 assertion lines with hardcoded 277:**

| File | Lines | Change |
|------|-------|--------|
| `test_cqt_features.py` | L252, L271, L278, L286, L335, L406, L415, L451, L514 | `(None, 277)` → `(None, 25)` |
| `test_chord_transitions.py` | L28, L115 | `(277, 277)` → `(25, 25)` |
| `test_chord_augmentation.py` | L490 | `f".../277..."` → `f".../25..."` |
| `test_inference_logic.py` | L99, L117, L151, L164 | `np.zeros((1, 277))` → `(1, 25)`; `np.full(277, ...)` → `np.full(25, ...)` |
| `test_viterbi_decoder.py` | L12, L18, L202 | `vocab_size: int = 277` → `25` |
| `test_viterbi_chord_progression.py` | L77, L297 | `np.zeros((1, 277))` → `(1, 25)`; `vocab_size = 277` → `25` |
| `test_cqt_distribution.py` | L41 | `labels[n_windows:] = 276` → `= NUM_CLASSES_MIREX - 1` |

#### A8. `N_CHORD_IDX` fallback fix (7 scripts)

**Problem**: 7 scripts use `CHORD_TO_IDX.get("N", CHROMA_BINS * BASS_BINS - 1)` as a fallback for the N-class index. With BASS_BINS=0 (Commit B), this evaluates to `144 * 0 - 1 = -1`. While `CHORD_TO_IDX.get("N")` should always succeed (the vocab always includes "N"), the fallback is fragile.

**Fix across all 7 files**: Change `CHROMA_BINS * BASS_BINS - 1` → `NUM_CLASSES - 1` (the canonical N index in 277-class vocab, which is 276). This preserves backward compatibility during the transition period when .npz files still have 277-class labels.

| File | Line | Change |
|------|------|--------|
| `extract_guitarset_cqt.py` | 49 | `CHROMA_BINS * BASS_BINS - 1` → `NUM_CLASSES - 1` |
| `extract_idmt_cqt.py` | 45 | same |
| `extract_damp_vpb.py` | 52 | same |
| `crawl_chord_videos.py` | 64 | same |
| `user_audio_pipeline.py` | 41 | same |
| `render_synthetic_guitar.py` | 49 | same |

Two scripts already use the correct fallback (`276` literal at `extract_egset12_cqt.py:48` and `extract_guitar_techs_cqt.py:54`) — these are fine but should be changed to `NUM_CLASSES - 1` for consistency.

`build_empirical_transition_matrix.py:26` already uses `NUM_CLASSES - 1` — no change needed.

---

### Commit B: Feature Expansion (40 → 144 CQT bins)

**Impact**: High. **Risk**: High (12 augmentation functions affected by BASS_BINS=0). **Files**: ~12 modified.

#### B1. `backend/scripts/build_chord_tflite.py`

**Constants** (lines 89-93): Already handled by pre-commit (import from `cqt_constants`).

**`make_cqt_template`** (lines 401-447):

```python
def make_cqt_template(root: int, quality: str) -> np.ndarray:
    """Generate 144-bin CQT template with overtone modeling.

    Chord tones placed at 24-bins-per-octave resolution covering
    octaves 2-4 (guitar range E2-E5 + harmonics).

    Returns: 144-bin feature vector (no separate bass channel).
    """
    cqt = np.zeros(CHROMA_BINS, dtype=np.float32)  # 144

    if quality == "N":
        return _make_n_silence_template()

    intervals = CHORD_INTERVALS[quality]

    for i, interval in enumerate(intervals):
        # Place in octave 2-3 (bin 24-71)
        if interval >= 14:
            octave = 3
        else:
            octave = 2

        note_in_octave = (root + interval) % 12
        bin_idx = octave * BINS_PER_OCTAVE + note_in_octave  # 24*octave + note

        weight = 1.0 if interval <= 12 else 0.4
        if i == 0:
            weight *= 1.20

        # Fundamental
        cqt[bin_idx] += weight

        # 2nd harmonic (octave above)
        harmonic2_bin = bin_idx + BINS_PER_OCTAVE
        if harmonic2_bin < CHROMA_BINS:
            cqt[harmonic2_bin] += weight * 0.5

        # 3rd harmonic (octave + fifth)
        harmonic3_bin = bin_idx + BINS_PER_OCTAVE + 7
        if harmonic3_bin < CHROMA_BINS:
            cqt[harmonic3_bin] += weight * 0.3

        # Spectral leakage: spread energy to adjacent bins
        for offset in [-1, 1]:
            neighbor = bin_idx + offset
            if 0 <= neighbor < CHROMA_BINS:
                cqt[neighbor] += weight * 0.15

    # Root note reinforcement in octave 2
    root_bin = 2 * BINS_PER_OCTAVE + root
    cqt[root_bin] += 0.5

    # Min-max normalization (matches real extraction normalization)
    cmin, cmax = cqt.min(), cqt.max()
    if cmax > cmin:
        cqt = (cqt - cmin) / (cmax - cmin + 1e-8)

    return cqt.astype(np.float32)  # No bass concatenation
```

**`_make_n_silence_template`** (lines 349-395): Generate 144-bin silence profiles, remove bass concatenation.

**`CircularCqtPad`** (lines 1648-1662):

```python
class CircularCqtPad(tf.keras.layers.Layer):
    """Circular padding on 144-bin CQT (no bass channel)."""

    def call(self, x):
        # x shape: (batch, time, 144)
        return tf.concat([x[:, :, -1:], x, x[:, :, :1]], axis=-1)

    def compute_output_shape(self, input_shape):
        return (input_shape[0], input_shape[1], input_shape[2] + 2)
```

**Augmentation functions — remove bass channel references**:

The pattern `bass = cqt[:BASS_BINS].copy()` followed by `np.concatenate([cqt, bass])` appears in 12 augmentation functions. Each must be updated to return just the CQT (no bass concatenation).

| Function | Lines | Fix |
|----------|-------|-----|
| `apply_inversion` | 482-497 | Remove lines 495-497 (bass copy + concat). Return `cqt.astype(np.float32)` |
| `apply_bass_ambiguity` | 585-617 | **Delete entire function**. Replace with `apply_low_freq_augmentation(cqt, root, quality, strength)` that adds energy to low-frequency bins (0-23) of the 144-bin CQT directly |
| `apply_missing_notes` | 500-520 | Remove bass references if present |
| `apply_extension_dropout` | ~520-545 | Remove bass references if present |
| `apply_guitar_body_resonance` | ~997-1030 | Remove bass concatenation |
| `apply_strumming_onset` | ~1080-1120 | Remove bass concatenation |
| `apply_cqt_leakage` | ~1140-1180 | Remove bass concatenation |
| `apply_cqt_reverb` | ~1180-1220 | Remove bass concatenation |
| `apply_fine_detune` | ~1040-1070 | Remove bass references if present |
| `apply_spectral_tilt` | ~1220-1260 | Remove bass references if present |
| `apply_random_gain` | ~1070-1090 | Remove bass references if present |
| `apply_n_augmentation` | 1236-1268 | Uses `CHROMA_BINS` at line 1254 (`int(CHROMA_BINS * mask_frac)`) — **safe** with 144 bins, no BASS_BINS references. Just confirm no hidden bass usage. |

**Pattern to find and replace** (appears ~12 times):
```python
# BEFORE:
bass = cqt[:BASS_BINS].copy()
return np.concatenate([cqt, bass]).astype(np.float32)

# AFTER:
return cqt.astype(np.float32)
```

#### B2. `backend/app/chord_inference.py`

| Line(s) | Change |
|---------|--------|
| 67-71 | Import from `cqt_constants` (already done in pre-commit) |
| 75-87 | `_circular_cqt_pad`: Remove bass padding. Just CQT circular pad: `tf.concat([x[:, :, -1:], x, x[:, :, :1]], axis=-1)` |
| 204 | `librosa.cqt(..., n_bins=144, bins_per_octave=24)` (was `n_bins=36`) |
| 211-212 | Remove `bass = cqt[:, :4]` and concatenation. Use `features = cqt` directly |

#### B3. Extraction scripts (7 files)

Each script: update to use `cqt_constants`, remove bass concatenation from `_extract_cqt()`.

**Common pattern** in all extraction scripts:

```python
# BEFORE:
def _extract_cqt(y, sr):
    hop = int(sr * HOP_SEC)
    cqt = librosa.cqt(y=y, sr=sr, hop_length=hop, n_bins=CHROMA_BINS,
                      bins_per_octave=BINS_PER_OCTAVE)
    cqt = np.abs(cqt).T.astype(np.float32)
    norms = cqt.sum(axis=1, keepdims=True).clip(1e-8, None)
    cqt = cqt / norms
    bass = cqt[:, :BASS_BINS]
    features = np.concatenate([cqt, bass], axis=1)
    return features

# AFTER:
def _extract_cqt(y, sr):
    hop = int(sr * HOP_SEC)
    cqt = librosa.cqt(y=y, sr=sr, hop_length=hop, n_bins=CHROMA_BINS,
                      bins_per_octave=BINS_PER_OCTAVE)
    cqt = np.abs(cqt).T.astype(np.float32)
    norms = cqt.sum(axis=1, keepdims=True).clip(1e-8, None)
    cqt = cqt / norms
    return cqt  # 144-bin CQT, no separate bass channel
```

| File | Lines to change |
|------|----------------|
| `extract_guitarset_cqt.py` | 41-46 (constants), 59-74 (`_extract_cqt`) |
| `extract_idmt_cqt.py` | 37-42 (constants), 51-66 (`extract_cqt`) |
| `extract_guitar_techs_cqt.py` | 48-50 (constants), extraction function |
| `extract_egset12_cqt.py` | 42-44 (constants), extraction function |
| `extract_damp_vpb.py` | 46-48 (constants), extraction function (if any — may use `user_audio_pipeline` patterns) |
| `extract_jaah_cqt.py` | Has **hardcoded** `n_bins=36` at line 62 and `bins_per_octave=12` at line 63. Also has `cqt.T.astype(np.float32)  # (T, 36)` at line 67. Change to `n_bins=144`, `bins_per_octave=24`, comment to `# (T, 144)`. Removal of bass channel inherited from `user_audio_pipeline` (see B4). |
| `crawl_chord_videos.py` | 57-60 (constants), extraction function |

#### B4. Other scripts

| File | Change |
|------|--------|
| `render_synthetic_guitar.py` | 41-45: import from `cqt_constants`; **also has its own `extract_cqt()` at lines 55-67** that concatenates bass — same fix as extraction scripts above |
| `user_audio_pipeline.py` | 35-38: import from `cqt_constants`; line 239-242: remove `bass = cqt[:, :BASS_BINS]` and concatenation; `extract_jaah_cqt.py` inherits this fix (imports `N_CHORD_IDX` from this file) |
| `pseudo_label_pipeline.py` | 42-44: import from `cqt_constants` |
| `cqt_distribution_analyzer.py` | 23-25: import from `cqt_constants` |

#### B5. Re-extract all datasets

```bash
cd backend

# GuitarSet (360 files, ~15 min)
python scripts/extract_guitarset_cqt.py --force

# IDMT-SMT-Guitar (129 files, ~10 min)
python scripts/extract_idmt_smt_guitar.py   # re-download if needed
python scripts/extract_idmt_cqt.py --force

# Guitar-TECHS (68 files, ~5 min)
python scripts/extract_guitar_techs_cqt.py --force

# EGSet12 (12 files, ~1 min)
python scripts/extract_egset12_cqt.py --force

# VST Synthetic (5640 files, ~30 min)
python scripts/render_synthetic_guitar.py --force

# YouTube Crawl (264 files, ~10 min)
python scripts/crawl_chord_videos.py --force

# Rebuild CQT distribution stats for domain gap matching
python scripts/cqt_distribution_analyzer.py \
  --guitarset-data-dir data/guitarset \
  --idmt-data-dir data/idmt_smt_guitar \
  --output data/cqt_stats.npz
```

#### B6. Tests to update

**9 lines with hardcoded 40, 6 lines with hardcoded 36:**

| File | Lines | Change |
|------|-------|--------|
| `test_cqt_features.py` | L17-22 | Local constants: `CHROMA_BINS=144, BASS_BINS=0, FEATURE_DIM=144` |
| `test_cqt_features.py` | L220 | `n_bins=36` → `n_bins=144` |
| `test_cqt_features.py` | L221 | `cqt.shape[0] == 36` → `144` |
| `test_cqt_features.py` | L224 | `rand(100, 36)` → `rand(100, 144)` |
| `test_cqt_features.py` | L227 | `features.shape == (100, 40)` → `(100, 144)` |
| `test_cqt_features.py` | L230 | `rand(10, 36)` → `rand(10, 144)` |
| `test_boundary_tie.py` | L54, L61 | `np.zeros((T, 40))` → `(T, 144)` |
| `test_boundary_tie.py` | L66 | `windows.shape[2] == 40` → `144` |
| `test_boundary_tie.py` | L70 | `np.ones((T, 40))` → `(T, 144)` |
| `test_chord_augmentation.py` | L512 | `feat_dim = 40` → `144` |
| `test_chord_augmentation.py` | L521 | `np.ones((64, 40))` → `(64, 144)` |
| `test_chord_augmentation.py` | L528 | `np.zeros((9, 40))` → `(9, 144)` |
| `test_chord_augmentation.py` | L538 | `np.random.randn(9, 40)` → `(9, 144)` |
| `test_guitarset_pipeline.py` | L252 | `features[:, :36]` → `features[:, :144]` |
| `test_guitarset_pipeline.py` | L256 | `features[:, 36:]` → removed (no bass channel) |

---

### Commit C: Training Curriculum (Real-First)

**Impact**: Medium. **Risk**: Low (code-only, no data changes). **Files**: 1 modified.

#### C1. `backend/scripts/build_chord_tflite.py` — Reverse curriculum

**Stage 1 (epochs 1-20): Real-only**

| Line(s) | Change |
|---------|--------|
| 3577-3580 | Stage 1 uses only real data. Don't concatenate synthetic: `X_train = X_real_tr.copy()` |
| 3656 | Update label: `"Stage 1: Real-only training (epochs 1-20)"` |
| 3692 | Reduce EarlyStopping patience from 25 to 10 |
| 3726 | Change `epochs=30` to `epochs=20` |
| 109 | `FIRST_DECAY_EPOCHS = 20` (was 30). This halves the cosine LR decay period from 1e-3→1e-5 over 20 epochs instead of 30, concentrating learning in the real-only phase. |

**Stage 2 (epochs 21-100): Real + small synthetic supplement**

| Line(s) | Change |
|---------|--------|
| 3618 | `_s2_synth_cap = max(1, int(len(X_real_tr_s1) * 0.08))` (was 0.25, now 8%) |
| 3749 | `total_steps_s2 = 80 * steps_per_epoch_s2` (was `70` for epochs 31-100; now 80 epochs for epochs 21-100). The cosine decay schedules correctly for the full 80-epoch Stage 2 duration. |
| 3807-3815 | `GradualTransitionCallback(start_ratio=1.0, target_ratio=0.92, transition_epochs=10, start_epoch=20)` |
| 3820 | `initial_epoch=20` (was 30) |

**Overfitting mitigation**:
- 583 real train samples with aggressive augmentation (pitch shift, time stretch, noise, mixup) provides ~10x effective diversity
- Stage 1 epochs reduced from 30 to 20 to prevent overfitting
- Early stopping patience reduced from 25 to 10
- Cosine LR schedule adjusted to decay over 20 epochs instead of 30

---

## Dependency Graph

```
Pre-commit (cqt_constants.py)
    |
    +-- Commit A (vocab) ----+
    |                        +-- Commit C (curriculum)
    +-- Commit B (bins) -----+
```

Commits A and B are independent (can be done in either order). Commit C depends on both A and B.

## Verification After Each Commit

```bash
# After each commit:
cd backend
python -m pytest -q           # all backend tests pass
npm run lint                  # frontend lint passes (no TS changes)

# After Commit A (vocab reduction), rebuild the transition matrix:
python scripts/build_empirical_transition_matrix.py

# After Commit B (re-extract + retrain):
# Run extraction commands from B5 above, then:
python scripts/build_chord_tflite.py \
  --guitarset-data-dir data/guitarset \
  --idmt-data-dir data/idmt_smt_guitar \
  --vst-data-dir data/vst_synthetic \
  --youtube-data-dir data/youtube_crawl \
  --guitar-techs-data-dir data/guitar_techs \
  --egset12-data-dir data/egset12 \
  --empirical-matrix data/annotations/transition_matrix_empirical.npy \
  --cqt-stats-path data/cqt_stats.npz \
  --temperature 0.3
# Check training_log.csv for val_accuracy_real improvement
```

## Expected Outcomes

| Metric | Current | After Commit A | After A+B | After A+B+C |
|--------|---------|----------------|-----------|-------------|
| Real val accuracy | 34.9% | ~45% | ~55% | ~58% |
| Synthetic val accuracy | 70.7% | ~65% | ~60% | ~58% |
| Domain gap | 35.8% | ~20% | ~5% | ~0% |
| GuitarSet test | — | ~40% | ~50% | ~52% |

These estimates are based on BTC achieving 76% at 25 classes with real data only. Our smaller real dataset (833 .npz files) suggests a lower ceiling, but 55% real val is achievable.

## Key Risk Mitigations

### 1. BASS_BINS=0 breaks 12 augmentation functions
**Problem**: 12 augmentation functions write to `result[CHROMA_BINS:]` (the bass channel). With BASS_BINS=0, these writes are silent no-ops.
**Fix**: Remove all bass-channel augmentation code. Replace `apply_bass_ambiguity` with a low-frequency bin augmentation that operates on bins 0-23 of the 144-bin CQT directly. Audit every function that contains `BASS_BINS` or `CHROMA_BINS:` patterns.

### 2. Stale .npz files with 277-class labels
**Problem**: .npz files in `data/*/processed/cqt/` contain labels as 277-class indices. After vocab reduction, N is at index 24, not 276.
**Fix**: The training script maps 277→25 at load time via `mirex_label()`. No re-extraction needed for Commit A. For `collect_real_n_templates`, scan for both old (276) and new (24) N indices.

### 3. chord_inference.py has independent vocabulary copy
**Problem**: `chord_inference.py` lines 33-44 define their own 277-class vocabulary instead of importing from `chord_vocab.py`. It also has hardcoded `n_bins=36` and `bass = cqt[:, :4]` at literal values.
**Fix**: Replace independent vocabulary with imports from `chord_vocab.py`. Find and replace the hardcoded literal values. This file must be updated separately for both Commit A and Commit B.

### 4. _label_after_pitch_shift bug with mapped labels
**Problem**: With mapped labels (0-24), the check `label_idx >= self._n_chord_classes` (276) never triggers for N (index 24). Pitch-shifted N labels would be incorrectly remapped.
**Fix**: Change the check to `label_idx >= N_INDEX` (24) at line 1594.

### 5. compute_grouped_accuracy reports 0.0 for 3 groups
**Problem**: With only maj/min, groups "extended", "altered", and "suspended_other" have zero samples and report 0.0.
**Fix**: Simplify `QUALITY_GROUPS` to `{"triad": {"maj", "min"}, "no_chord": {"N"}}`. The other groups are meaningless at 25 classes.

### 6. Transition matrix has no cache invalidation
**Problem**: `build_empirical_transition_matrix.py` docstring claims `--force` flag exists but it doesn't. Script always overwrites. `chord_transitions.py` caches as a module-level singleton in `data/transition_matrix.npy`.
**Fix**: Delete both `data/transition_matrix.npy` and `data/annotations/transition_matrix_empirical.npy` before re-running. Rebuild via `python scripts/build_empirical_transition_matrix.py`. Consider adding `--force` flag to the script.

### 7. Real-only Stage 1 may overfit
**Problem**: ~583 real train samples in 20 epochs with batch_size=64 gives ~9 steps/epoch. Aggressive augmentation helps but may not be enough.
**Fix**: Cap Stage 1 at 20 epochs (not 30). Use EarlyStopping with patience=10. The existing `AugmentedDataGenerator` applies pitch shift (±2 semitones), time stretch (0.9-1.1x), pink noise, and mixup — providing ~10x effective diversity.
