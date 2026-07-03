"""CQT distribution analysis for synthetic realism improvement (Commit 148 Phase 1b).

Analyzes real CQT features from GuitarSet/IDMT to compute:
- Per-bin mean and variance (40-dim)
- Covariance structure (40x40)
- PCA modes (top-10 components)
- Residual distribution (real CQT - ideal template)

These statistics are used by generate_dataset() to bridge the
synthetic-to-real domain gap via distribution matching.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger("harmoniq.cqt_analysis")

from app.cqt_constants import CHROMA_BINS, BASS_BINS, FEATURE_DIM, WINDOW

def collect_real_cqt_features(data_dirs: list[Path]) -> np.ndarray:
    """Load real CQT features from processed dataset directories.

    Args:
        data_dirs: List of dataset paths containing ``processed/cqt/*.npz`` files.

    Returns:
        (N, 128, 40) array of real CQT windows, excluding no-chord samples.
    """
    from app.chord_vocab import NUM_CLASSES, NUM_CLASSES_MIREX

    all_features: list[np.ndarray] = []
    n_idx_new = NUM_CLASSES_MIREX - 1  # 24 (new N index)
    n_idx_old = NUM_CLASSES - 1        # 276 (old N index in stale .npz files)

    for data_dir in data_dirs:
        cqt_dir = data_dir / "processed" / "cqt"
        if not cqt_dir.exists():
            logger.warning("Directory not found: %s", cqt_dir)
            continue

        for npz_path in sorted(cqt_dir.glob("*.npz")):
            try:
                data = np.load(npz_path)
                features = data["features"]
                labels = data["labels"]
                chord_mask = (labels != n_idx_new) & (labels != n_idx_old)
                filtered = features[chord_mask]
                if len(filtered) > 0:
                    all_features.append(filtered)
            except Exception as exc:
                logger.warning("Skipping %s: %s", npz_path.name, exc)

    if not all_features:
        raise ValueError("No real CQT features found in any data directory")

    result = np.concatenate(all_features, axis=0)
    logger.info(
        "Collected %d real CQT windows from %d source(s)",
        len(result), len(data_dirs),
    )
    return result


def compute_cqt_statistics(features: np.ndarray) -> dict:
    """Compute per-bin statistics, covariance, and PCA from real CQT features.

    Args:
        features: (N, 128, 40) array of real CQT windows.

    Returns:
        Dict with keys:
            - per_bin_mean: (40,) mean across all windows and frames
            - per_bin_std: (40,) standard deviation
            - covariance: (40, 40) covariance matrix of per-bin energies
            - pca_components: (10, 5120) top 10 principal components
            - pca_explained_variance: (10,) eigenvalues
            - pca_explained_variance_ratio: (10,) fraction of variance explained
            - n_samples: int
    """
    N = features.shape[0]

    flat = features.reshape(-1, FEATURE_DIM)

    per_bin_mean = np.mean(flat, axis=0).astype(np.float64)
    per_bin_std = np.std(flat, axis=0).astype(np.float64)

    centered = flat - per_bin_mean
    cov = (centered.T @ centered) / (len(flat) - 1)

    flat_windows = features.reshape(N, -1)
    n_components = min(10, N - 1)
    # Manual PCA to avoid sklearn dependency at inference time
    centered_windows = flat_windows - flat_windows.mean(axis=0, keepdims=True)
    if n_components >= 1:
        U, S, Vt = np.linalg.svd(centered_windows, full_matrices=False)
        pca_components = Vt[:n_components]
        pca_explained_variance = (S[:n_components] ** 2) / (N - 1)
        var_ratio = pca_explained_variance / pca_explained_variance.sum()
    else:
        pca_components = np.zeros((0, flat_windows.shape[1]), dtype=np.float32)
        pca_explained_variance = np.zeros(0, dtype=np.float32)
        var_ratio = np.zeros(0, dtype=np.float32)

    stats = {
        "per_bin_mean": per_bin_mean.astype(np.float32),
        "per_bin_std": per_bin_std.astype(np.float32),
        "covariance": cov.astype(np.float32),
        "pca_components": pca_components.astype(np.float32),
        "pca_explained_variance": pca_explained_variance.astype(np.float32),
        "pca_explained_variance_ratio": var_ratio.astype(np.float32),
        "n_samples": N,
    }
    logger.info(
        "CQT statistics computed: %d windows, %d features, "
        "PCA explains %.1f%% with top %d components",
        N, FEATURE_DIM,
        100.0 * var_ratio.sum() if len(var_ratio) > 0 else 0.0,
        n_components,
    )
    return stats


def save_cqt_stats(stats: dict, path: Path) -> None:
    """Save CQT statistics to an .npz file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **stats)
    logger.info("Saved CQT statistics to %s", path)


def load_cqt_stats(path: Path) -> dict:
    """Load CQT statistics from an .npz file."""
    data = np.load(str(path))
    result = dict(data)
    logger.info("Loaded CQT statistics from %s", path)
    return result


def main():
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        description="Analyze real CQT distribution and save statistics"
    )
    parser.add_argument(
        "--guitarset-data-dir", type=str, required=True,
        help="Path to GuitarSet CQT data directory",
    )
    parser.add_argument(
        "--idmt-data-dir", type=str, default=None,
        help="Path to IDMT-SMT-Guitar CQT data directory",
    )
    parser.add_argument(
        "--output", type=str, default="data/cqt_stats.npz",
        help="Output path for saved statistics",
    )
    args = parser.parse_args()

    data_dirs = [Path(args.guitarset_data_dir)]
    if args.idmt_data_dir:
        data_dirs.append(Path(args.idmt_data_dir))

    features = collect_real_cqt_features(data_dirs)
    stats = compute_cqt_statistics(features)
    save_cqt_stats(stats, Path(args.output))
    print(f"Done. Mean per-bin energy: {stats['per_bin_mean'][:5]}...")


if __name__ == "__main__":
    main()
