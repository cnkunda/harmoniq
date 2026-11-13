# Model Provenance and Archive

Last updated: 2026-11-12.

## Active model (runtime)

Runtime model loading uses the files in `backend/app/`, not `backend/research/`:

- `backend/app/chord_model.tflite` — default TFLite model (`CHORD_MODEL_PATH` in
  `app/model_server.py`; `_TFLITE_PATH` in `app/chord_inference.py`).
- `backend/app/chord_model.keras` — Keras model (`_KERAS_PATH`).
- `backend/app/chord_model.weights.h5` — training weights.

`backend/app/model_registry.json` records the version history. It currently lists
`active_version: "1.0.3"` while v1.0.5 is the multi-task snapshot; promotions
across architectures are a manual decision (see the registry `notes`).

## Research snapshots

Each `backend/research/h-gain-vX/` keeps `metadata.json`, `training_log.csv`, and
the pipeline `.py` files. Only the TFLite binary for v1.0.1–v1.0.4 was moved to
the archive (Commit 9); v1.0.5 stays in-repo.

| Version | Architecture | val_accuracy | val_loss | TFLite location | SHA-256 |
| --- | --- | ---: | ---: | --- | --- |
| 1.0.1 | CRNN | 0.6827 | 0.9463 | archive | `907e457f…a7a733` |
| 1.0.2 | CRNN | 0.6845 | 0.9716 | archive | `714f3349…ff5938` |
| 1.0.3 | CRNN | 0.8375 | 0.6404 | archive | `4ab3e423…33ac7` |
| 1.0.4 | CRNN | 0.5014 | 2.1553 | archive | `afc6f0eb…725432` |
| 1.0.5 | CRNN (multi-task) | 0.4854 | 3.2029 | **in-repo** | `d8dbc1a9…0ac0` |

v1.0.5 metrics are not directly comparable to the single-output v1.0.3 model.

## Archive

**Location:** `/mnt/c/workspace/harmoniq-model-archive` (machine-local, outside
the repository). It is not a shared remote; copy it to shared storage if another
machine needs to restore the binaries.

**Manifest:** `MANIFEST.sha256` lists every archived binary. Verify with:

```bash
cd /mnt/c/workspace/harmoniq-model-archive
sha256sum -c MANIFEST.sha256
```

**Contents:**

| Archived path | Origin |
| --- | --- |
| `h-gain-v1.0.1/chord_model.tflite` | `backend/research/h-gain-v1.0.1/` |
| `h-gain-v1.0.2/chord_model.tflite` | `backend/research/h-gain-v1.0.2/` |
| `h-gain-v1.0.3/chord_model.tflite` | `backend/research/h-gain-v1.0.3/` |
| `h-gain-v1.0.4/chord_model.tflite` | `backend/research/h-gain-v1.0.4/` |
| `dead/bak_phase1/chord_model.tflite` | `backend/app/bak_phase1/` |
| `dead/chord_model_stage1_best.keras.backup` | `backend/app/` |

## Restore

```bash
ARCH=/mnt/c/workspace/harmoniq-model-archive

# 1. Verify the archive.
(cd "$ARCH" && sha256sum -c MANIFEST.sha256)

# 2. Copy the binary back into the research snapshot.
cp -p "$ARCH/h-gain-v1.0.2/chord_model.tflite" \
  backend/research/h-gain-v1.0.2/

# 3. Confirm the checksum.
sha256sum backend/research/h-gain-v1.0.2/chord_model.tflite

# 4. List / promote (promotion reads binaries from the version directory).
cd backend
python scripts/promote_model.py --list
python scripts/promote_model.py --version 1.0.2 --force
```

`promote_model.py` prints `[SKIPPED]` for model files that are absent from the
version directory, so restoring only the TFLite is enough to re-promote that
artifact.

## Pack-size record (Commit 9)

`git count-objects -vH`:

| When | count | size | size-pack |
| --- | ---: | ---: | ---: |
| before removal | 2325 | 25.12 MiB | 507.35 MiB |
| after `git rm` | 2325 | 25.12 MiB | 507.35 MiB |

Removed from tracking: ~9.2 MB (4.4 MB research TFLite binaries + 3.6 MB
`bak_phase1` + 1.3 MB backup). `backend/research/` dropped from 8.0 MB to
3.9 MB on checkout.

**The pack does not shrink.** The historical blobs for these paths
(50 blobs / 467.4 MiB) remain reachable in `main`'s history, and rewriting
history is out of scope for Commit 9. The measurable win is the smaller
checkout; shrinking `size-pack` requires a separate `git filter-repo`/BFG
operation and a coordinated force-push.

## Related commands

```bash
# Archive a new trained model version (writes backend/research/h-gain-vX/).
cd backend
python scripts/version_model.py --version X.Y.Z \
  --weights app/chord_model.weights.h5 --log scripts/training_log.csv

# Show versions and the active model.
python scripts/promote_model.py --list
```
