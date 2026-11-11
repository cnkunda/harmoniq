"""Commit 1 / W0: reproducible guitar-AMT evaluation harness.

This package is evaluation-only. It does not run inside the analysis
pipeline; ``scripts/eval_amt.py`` imports it to score cached predictions
against a manifest of ground-truth tracks.

The modules are intentionally small and separable:

- ``manifest``      — validated track manifest + path resolution
- ``ground_truth``  — dataset-specific annotation loaders
- ``metrics``       — challenge-style note/chord/calibration metrics
- ``verdict``       — the Pass/Warn/Fail rubric from docs/EVALUATION.md
- ``report``        — deterministic JSON + Markdown assembly
"""

from app.evaluation.manifest import (
    EvalManifest,
    ManifestError,
    TrackSpec,
    load_manifest,
    resolve_manifest_path,
)

__all__ = [
    "EvalManifest",
    "ManifestError",
    "TrackSpec",
    "load_manifest",
    "resolve_manifest_path",
]
