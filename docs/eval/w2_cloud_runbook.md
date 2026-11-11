# W2 teacher comparison — cloud GPU runbook

The W2 harness (`backend/scripts/compare_teachers.py`) is CPU/GPU agnostic and
resumable. The local GTX 1050 (4 GB) cannot hold MR-MT3's forward pass on the
long RWC-P full-mix tracks (200–320 s), and the CPU fallback is impractical
(RTF ≈ 20–40). Run the remaining work on a rented GPU instead.

**Recommended GPU:** ≥ 8 GB VRAM (16–24 GB comfortable). An RTX 4090 / A10G /
L4 finishes the remaining 14 MR-MT3 + 50 YourMT3 tracks in well under an hour
of GPU time.

Everything below assumes the same repo checkout; the harness path resolution,
cache keys, and report schema are identical to local runs.

---

## 1. Build the bundle (local, from `backend/`)

```bash
cd backend
python scripts/stage_w2_cloud_bundle.py --out /tmp/w2_bundle
tar -C /tmp/w2_bundle -czf w2_bundle.tgz .
```

The bundle contains:

- the fixed 50-track sample audio + ground truth (~1.0 GB),
- the committed sample manifest (`docs/eval/w2_teacher_sample.json`),
- the existing teacher-output cache (~17 MB): **MT3 50/50** (so no JAX/T5X
  install or re-inference is needed) and **MR-MT3 36/50**,
- the backend code needed to run the harness.

Add `--include-checkpoints` to ship the PyTorch weights (~700 MB) instead of
downloading them on the box.

`--no-code` stages data + caches only (use when you will `git clone` the repo
on the cloud box instead).

---

## 2. Platform quickstarts

### Cerebrium (current choice)

The repo ships a ready Cerebrium project in `cerebrium_w2/` (`main.py` +
`cerebrium.toml`). The 50-track bundle lives in Cerebrium **persistent
storage** (50 GB, mounted at `/persistent-storage`), not in the deployment
image, so deploys stay small and the bundle/checkpoints/cache survive runs.

```bash
pip install cerebrium && cerebrium login

# 1. Build the bundle locally (from backend/)
cd backend
python scripts/stage_w2_cloud_bundle.py --out /tmp/w2_bundle
tar -C /tmp/w2_bundle -czf /tmp/w2_bundle.tgz .

# 2. Upload it to the project's persistent storage (from cerebrium_w2/)
cd ../cerebrium_w2
cerebrium cp /tmp/w2_bundle.tgz w2_bundle.tgz

# 3. Optional sanity check: teacher availability + cache coverage
cerebrium run main.py::status

# 4. Full comparison on an A10 (24 GB). First run extracts the bundle and
#    downloads both checkpoints (sha256-verified) into persistent storage.
cerebrium run main.py::run --teachers mt3,mr_mt3,yourmt3,musicfm
```

`main.py` writes the report to
`/persistent-storage/w2/docs/audit/amt/w2_teacher_comparison.{json,md}` and
prints the Markdown + a summary at the end of the run.

If a single run hits the platform's runtime limit, shard by teacher and
finish with a cache-only report (each run is resumable from the cache):

```bash
cerebrium run main.py::run --teachers mr_mt3
cerebrium run main.py::run --teachers yourmt3
cerebrium run main.py::run --teachers mt3,mr_mt3,yourmt3,musicfm --cached-only true
# or bound a run to a track range:
cerebrium run main.py::run --teachers mr_mt3 --offset 0 --limit 10
```

Download the results back into the repo checkout:

```bash
cerebrium download w2/docs/audit/amt/w2_teacher_comparison.md
cerebrium download w2/docs/audit/amt/w2_teacher_comparison.json
cerebrium download w2/backend/data/evaluation/teacher_outputs
```

`cerebrium.toml` uses `compute = "AMPERE_A10"` (24 GB VRAM), 8 vCPU, 32 GB
RAM, Python 3.11, and installs `git`/`ffmpeg`/`libsndfile1` plus
`cerebrium_w2/requirements.txt`. Cerebrium's pip parser rejects PEP 508
direct references (`name @ git+https://...`), so `mt3-infer` is installed
from GitHub in `[cerebrium.deployment] shell_commands` with `--no-deps`
(the requirements file supplies its PyPI dependencies).

### Modal (serverless)

The repo ships a Modal app in `backend/scripts/w2_modal.py` (A10G, 6 h
timeout, bundle + checkpoints in a Modal Volume).

```bash
pip install modal && modal token new   # $30/mo free credit with a card

# 1. Build the bundle locally (from backend/) and upload it to the volume
cd backend
python scripts/stage_w2_cloud_bundle.py --out /tmp/w2_bundle
modal volume create harmoniq-w2
modal volume put harmoniq-w2 /tmp/w2_bundle /w2

# 2. Sanity check: teacher availability + cache coverage
modal run scripts/w2_modal.py::status

# 3. Full comparison (MT3 from cache; MR-MT3 fills the 14 missing RWC-P
#    tracks; YourMT3+ runs all 50)
modal run scripts/w2_modal.py::compare --teachers mt3,mr_mt3,yourmt3,musicfm
```

The first run extracts the bundle and downloads both checkpoints
(sha256-verified) into the volume. If a run hits the timeout, shard by teacher
and finish cache-only (each run is resumable):

```bash
modal run scripts/w2_modal.py::compare --teachers mr_mt3
modal run scripts/w2_modal.py::compare --teachers yourmt3
modal run scripts/w2_modal.py::compare --teachers mt3,mr_mt3,yourmt3,musicfm --cached-only true
```

Pull results back:

```bash
modal volume get harmoniq-w2 /w2/docs/audit/amt ./amt
modal volume get harmoniq-w2 /w2/backend/data/evaluation/teacher_outputs ./teacher_outputs
```

### vast.ai / RunPod (cheapest per hour)

```bash
# pick a template with CUDA 12.x + Python 3.11, then from your machine:
scp w2_bundle.tgz user@HOST:/workspace/
ssh user@HOST
cd /workspace && tar -xzf w2_bundle.tgz && cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-w2-cloud.txt
```

### Lightning AI (free GPU hours)

Upload `w2_bundle.tgz` in a Studio (or `lightning upload`), then in the Studio
terminal:

```bash
tar -xzf w2_bundle.tgz && cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-w2-cloud.txt
```

---

## 3. Checkpoints and environment

```bash
cd backend
source .venv/bin/activate

# mt3-infer (MIT) is installed by requirements-w2-cloud.txt.
export HARMONIQ_MT3_INFER_PATH=$(python -c 'import mt3_infer,os;print(os.path.dirname(os.path.dirname(mt3_infer.__file__)))')
export HARMONIQ_MT3_CHECKPOINT_DIR=$PWD/data/models/mt3infer
export HARMONIQ_TEACHER_DEVICE=cuda
export HARMONIQ_TEACHER_TIMEOUT_S=14400
```

If you did not ship checkpoints (`--include-checkpoints`), download them and
verify the sha256 recorded in the `mt3-infer` catalogue
(`mt3_infer/config/checkpoints.toml`):

```bash
mkdir -p data/models/mt3infer/mr_mt3 \
         data/models/mt3infer/yourmt3/mc13_256_g4_all_v7_mt3f_sqr_rms_moe_wf4_n8k2_silu_rope_rp_b36_nops

curl -L -o data/models/mt3infer/mr_mt3/mt3.pth \
  https://huggingface.co/gudgud1014/MR-MT3/resolve/main/mt3.pth
sha256sum data/models/mt3infer/mr_mt3/mt3.pth
# expect b8a3807ed265059abd25ad7f68142c06c35e8f6144dcaa45bd55946a3745398f

curl -L -o data/models/mt3infer/yourmt3/mc13_256_g4_all_v7_mt3f_sqr_rms_moe_wf4_n8k2_silu_rope_rp_b36_nops/last.ckpt \
  "https://huggingface.co/spaces/mimbres/YourMT3/resolve/main/amt/logs/2024/mc13_256_g4_all_v7_mt3f_sqr_rms_moe_wf4_n8k2_silu_rope_rp_b36_nops/checkpoints/last.ckpt"
sha256sum data/models/mt3infer/yourmt3/mc13_256_g4_all_v7_mt3f_sqr_rms_moe_wf4_n8k2_silu_rope_rp_b36_nops/last.ckpt
# expect ae38e415c79efd5592dcb9b658cdb99ddb11d4c4e1eaa364cab04a052473fc25
```

Weights are never committed to the repo — download at runtime and record the
hash (see `licences.md`).

---

## 4. Run the comparison

```bash
# Full run. MT3 is scored from cache; MR-MT3 skips its 36 cached tracks and
# transcribes the 14 missing RWC-P tracks; YourMT3+ runs all 50.
python scripts/compare_teachers.py \
  --teachers mt3,mr_mt3,yourmt3,musicfm \
  --device cuda \
  --report ../docs/audit/amt/w2_teacher_comparison.json \
  --markdown ../docs/audit/amt/w2_teacher_comparison.md
```

If a long batch is interrupted, just rerun the same command — the cache makes
it resumable (each track is flushed as soon as it finishes). To bound a run,
use `--offset N --limit M` (tracks are sorted by id) or `--teachers mr_mt3`.

Useful flags:

| Flag | Purpose |
| --- | --- |
| `--cached-only` | Score only cached outputs; never run inference |
| `--refresh` | Ignore cached outputs and re-transcribe |
| `--offset/--limit` | Shard a long run |
| `--device cuda` | Run the PyTorch teacher worker on GPU |
| `--timeout SECONDS` | Per-batch worker timeout (default 1800) |

The report is written to `docs/audit/amt/w2_teacher_comparison.{json,md}` and
contains per-teacher summaries, deltas vs MT3, teacher statuses with reasons,
and the go/no-go decision with per-candidate checks.

---

## 5. Bring results back

Copy these back into the repo checkout:

```
backend/data/evaluation/teacher_outputs/     # per-track teacher cache
docs/audit/amt/w2_teacher_comparison.json
docs/audit/amt/w2_teacher_comparison.md
```

Then locally (no GPU needed):

```bash
cd backend
python scripts/compare_teachers.py --teachers mt3,mr_mt3,yourmt3,musicfm \
  --cached-only --report ../docs/audit/amt/w2_teacher_comparison.json
python -m pytest -q tests/test_teachers.py
```

`--cached-only` reproduces the report from the uploaded cache on any machine,
including one without the teacher dependencies (MT3 is scored from cache).

---

## 6. Actual outcome (2026-11-10, Modal A10G)

- MT3: 50/50 from cache; chord acc 0.2667, onset F1 0.5092, leakage 0.6962,
  RTF 3.164.
- MR-MT3: 50/50 on GPU; chord acc 0.2554, onset F1 0.4222, leakage 0.8251,
  retention 0.4269, RTF 0.626. Not recommended as-is — it trades accuracy for
  speed and needs the guitar-program filter.
- YourMT3+: 50/50; chord acc 0.2164, onset F1 0.5723, onset+pitch F1 0.5904,
  leakage 0.5756, retention 0.6090, RTF 0.192. **Recommended teacher.**
- MusicFM: documented placeholder (encoder-only; the MIROS/YourMT3 decoder and
  its weight licence are outstanding).
- Decision: **`go` → YourMT3+** (`docs/audit/amt/w2_teacher_comparison.{json,md}`).

**Known-good runtime pins:** `mt3-infer` 0.2.0 needs transformers 5.x
(`T5Block.forward(past_key_values=...)`) but `get_extended_attention_mask` was
removed in 5.17, so pin `transformers==5.13.0` with `torch==2.5.1` /
`torchaudio==2.5.1` (matching the local environment that produced the cache).

### Long-run tips

- Use `modal run --detach ...` — a local client disconnect cancels a foreground
  run.
- Shard by teacher and source (`--offset/--limit`) so each run commits; a
  preemption restart then only loses the current shard.
- `--cached-only` on any machine reproduces the metrics and the decision from
  the committed cache (cached teachers count as candidates even without their
  runtime installed).
