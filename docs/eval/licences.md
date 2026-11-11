# Licence audit — W1 data engine and teacher models

Audited 2026-11-03. This table is a research-use audit, not legal advice.
When in doubt, treat a source as non-redistributable and keep it out of the
public release.

## Datasets

| Source | Licence | Commercial use | Redistribution | Used in W1 | Notes |
| --- | --- | --- | --- | --- | --- |
| GuitarSet | CC BY 4.0 | Yes | Yes, with attribution | Yes | Zenodo 3371780; 360 acoustic tracks, JAMS string/fret/chord/beat annotations. |
| Guitar-TECHS | CC BY 4.0 | Yes | Yes, with attribution | Yes | Zenodo 14963133; 4.1 GB; per-string MIDI, direct-input + micamp perspectives. |
| EGSet12 | CC BY 4.0 | Yes | Yes, with attribution | Yes | Zenodo 11406378; 12 electric guitar performances. |
| RWC-P (RWC 2.0) | CC BY-NC 4.0 | No | No | Yes (eval only) | Non-commercial research; audio is opt-in and must not be redistributed. |
| IDMT-SMT-Guitar | Fraunhofer IDMT academic licence | No | No | Yes | Academic/non-commercial use; check the upstream agreement before redistribution. |
| YouTube crawl | YouTube Terms of Service | No | No | Yes (labels/metadata only) | Audio is not redistributable; keep it local and out of releases. |
| JAAH | CC BY-NC-SA 4.0 | No | Share-alike, non-commercial | No | Annotations only; not used in W1. |
| DadaGP | Research access on request | No | No | No (W4) | Paper text is CC BY 4.0, but the dataset is distributed on request for research. |
| Slakh2100 | CC BY 4.0 (official Zenodo) | Yes | Yes, with attribution | No | A Hugging Face mirror claims CC BY-NC-SA; trust the official Zenodo record. |
| Local user jobs | User-provided | Unknown | No | Yes (local only) | Never include user audio in a public release. |

## Teacher / model weights

| Model | Code licence | Weight licence | W1/W2 use | Notes |
| --- | --- | --- | --- | --- |
| MT3 (Magenta) | Apache-2.0 | Apache-2.0 checkpoint | Yes (W1 teacher) | `magenta/mt3`; JAX/T5X. |
| MR-MT3 | MIT | MIT (Hugging Face `gudgud1014/MR-MT3`) | W2 candidate | Leakage mitigation; PyTorch. Weight sha256 pinned in `mt3-infer` checkpoint catalogue. |
| YourMT3+ | GPL-3.0 repository | Apache-2.0 declared on the 2025 challenge leaderboard | W2 candidate | Weights downloaded from HF `mimbres/YourMT3` (GTX-1050-class GPU is the practical floor; long RWC tracks may need CPU fallback). GPL code runs out-of-process via the `mt3-infer` worker. |
| mt3-infer toolkit | MIT | — | W2 infrastructure | `openmirlab/mt3-infer`; vendored MR-MT3/YourMT3 inference, MIT. |
| MusicFM | MIT / Apache-2.0 dual | MIT / Apache-2.0 | W2 candidate | Encoder-only foundation model. |
| MIROS | Inference code published | Weight licence not declared | W2 candidate | Do not redistribute weights until clarified. |
| HT-MT3 | — | — | **Not a real model** | The cited arXiv 2305.12345 is an unrelated physics paper. Replaced by MR-MT3. |

## Redistribution policy

- Committed: manifests, scripts, dataset card, licence audit, metrics, reports.
- Not committed: audio, model checkpoints, RWC-P/IDMT/YouTube/user audio.
- Public release: only CC BY 4.0 sources with attribution; keep RWC-P,
  IDMT, YouTube, and user audio out of the release.
- Model weights: never commit; download at runtime and record the source
  and hash.
