"""Tests for Commit 148 Phase 1b: CQT distribution analyzer.

Tests the collect_real_cqt_features, compute_cqt_statistics,
save_cqt_stats, and load_cqt_stats functions.
"""
import os
os.environ["KERAS_BACKEND"] = "tensorflow"
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pytest
from numpy.testing import assert_allclose

from scripts.cqt_distribution_analyzer import (
    collect_real_cqt_features,
    compute_cqt_statistics,
    save_cqt_stats,
    load_cqt_stats,
    CHROMA_BINS,
    BASS_BINS,
    FEATURE_DIM,
    WINDOW,
)


class TestCollectRealCqtFeatures:
    """Tests for loading real CQT features from .npz files."""

    def _make_npz(self, path: Path, n_windows: int = 5, n_n_chord: int = 2):
        """Create a temp .npz with features and labels."""
        n_total = n_windows + n_n_chord
        features = np.random.randn(n_total, WINDOW, FEATURE_DIM).astype(np.float32)
        labels = np.zeros(n_total, dtype=np.int32)
        labels[:n_windows] = np.random.randint(0, 200, size=n_windows)
        labels[n_windows:] = 276
        np.savez_compressed(str(path), features=features, labels=labels)

    def test_collects_features_and_filters_n(self):
        with tempfile.TemporaryDirectory() as td:
            cqt_dir = Path(td) / "processed" / "cqt"
            cqt_dir.mkdir(parents=True)
            self._make_npz(cqt_dir / "track01.npz", n_windows=5, n_n_chord=2)

            features = collect_real_cqt_features([Path(td)])
            assert features.shape[0] == 5, "Expected 5 chord windows, no-chord filtered"
            assert features.shape[1] == WINDOW
            assert features.shape[2] == FEATURE_DIM

    def test_multiple_sources_concatenated(self):
        with tempfile.TemporaryDirectory() as td:
            for src in ["src1", "src2"]:
                cqt_dir = Path(td) / src / "processed" / "cqt"
                cqt_dir.mkdir(parents=True)
                self._make_npz(cqt_dir / "track.npz", n_windows=3, n_n_chord=1)

            features = collect_real_cqt_features([
                Path(td) / "src1", Path(td) / "src2",
            ])
            assert features.shape[0] == 6, "Expected 6 chord windows from 2 sources"

    def test_missing_directory_raises(self):
        with pytest.raises(ValueError, match="No real CQT features"):
            collect_real_cqt_features([Path("/nonexistent")])

    def test_empty_npz_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            cqt_dir = Path(td) / "processed" / "cqt"
            cqt_dir.mkdir(parents=True)
            path = cqt_dir / "empty.npz"
            np.savez_compressed(str(path), features=np.zeros((0, WINDOW, FEATURE_DIM)), labels=np.zeros(0, dtype=np.int32))

            with pytest.raises(ValueError, match="No real CQT features"):
                collect_real_cqt_features([Path(td)])


class TestComputeCqtStatistics:
    """Tests for CQT statistics computation."""

    def test_basic_statistics(self):
        features = np.random.randn(50, WINDOW, FEATURE_DIM).astype(np.float32)
        stats = compute_cqt_statistics(features)

        assert "per_bin_mean" in stats
        assert "per_bin_std" in stats
        assert "covariance" in stats
        assert "pca_components" in stats
        assert "pca_explained_variance" in stats
        assert "pca_explained_variance_ratio" in stats
        assert "n_samples" in stats

        assert stats["per_bin_mean"].shape == (FEATURE_DIM,)
        assert stats["per_bin_std"].shape == (FEATURE_DIM,)
        assert stats["covariance"].shape == (FEATURE_DIM, FEATURE_DIM)
        assert stats["pca_explained_variance_ratio"].shape[0] <= 10

    def test_pca_components(self):
        features = np.random.randn(100, WINDOW, FEATURE_DIM).astype(np.float32)
        stats = compute_cqt_statistics(features)
        assert stats["pca_components"].shape[0] <= 10
        assert stats["pca_components"].shape[1] == WINDOW * FEATURE_DIM

    def test_single_window(self):
        features = np.random.randn(1, WINDOW, FEATURE_DIM).astype(np.float32)
        stats = compute_cqt_statistics(features)
        assert stats["n_samples"] == 1
        assert stats["pca_components"].shape[0] == 0

    def test_covariance_symmetric(self):
        features = np.random.randn(50, WINDOW, FEATURE_DIM).astype(np.float32)
        stats = compute_cqt_statistics(features)
        cov = stats["covariance"]
        assert_allclose(cov, cov.T, atol=1e-6, err_msg="Covariance should be symmetric")

    def test_var_ratio_sums_to_one(self):
        features = np.random.randn(50, WINDOW, FEATURE_DIM).astype(np.float32)
        stats = compute_cqt_statistics(features)
        ratio = stats["pca_explained_variance_ratio"]
        assert abs(ratio.sum() - 1.0) < 1e-6

    def test_pca_explained_variance_decreasing(self):
        features = np.random.randn(100, WINDOW, FEATURE_DIM).astype(np.float32)
        stats = compute_cqt_statistics(features)
        ev = stats["pca_explained_variance"]
        for i in range(len(ev) - 1):
            assert ev[i] >= ev[i + 1] - 1e-6, (
                f"Eigenvalues should be non-increasing: {ev[i]} < {ev[i + 1]}"
            )


class TestCqtStatsIO:
    """Tests for save/load round-trip of CQT statistics."""

    def test_save_load_roundtrip(self):
        features = np.random.randn(50, WINDOW, FEATURE_DIM).astype(np.float32)
        stats = compute_cqt_statistics(features)

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "cqt_stats.npz"
            save_cqt_stats(stats, path)
            assert path.exists()

            loaded = load_cqt_stats(path)
            for key in stats:
                assert_allclose(stats[key], loaded[key], atol=1e-6,
                                err_msg=f"Mismatch for {key}")

    def test_load_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            load_cqt_stats(Path("/nonexistent/stats.npz"))
