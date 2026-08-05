"""MLflow tracking and model registry for Harmoniq.

Logs training runs, metrics, and model versions to MLflow.
Manages model staging (staging → production) and artifact storage.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("harmoniq.mlflow_tracking")

_mlflow_client = None


def _get_tracking_uri() -> str:
    """Get MLflow tracking URI from environment."""
    return os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")


def _get_client():
    """Lazy MLflow client initialization."""
    global _mlflow_client
    if _mlflow_client is not None:
        return _mlflow_client

    try:
        import mlflow

        mlflow.set_tracking_uri(_get_tracking_uri())
        _mlflow_client = mlflow.MlflowClient()
        logger.info("mlflow_client_initialized uri=%s", _get_tracking_uri())
        return _mlflow_client
    except Exception as exc:
        logger.warning("mlflow_init_failed exception=%s", exc)
        return None


def log_experiment(
    run_name: str,
    params: dict[str, Any],
    metrics: dict[str, float],
    tags: dict[str, str] | None = None,
    artifact_path: str | None = None,
    model_path: str | None = None,
) -> str | None:
    """Log an experiment run to MLflow.

    Args:
        run_name: Name for the MLflow run.
        params: Hyperparameters and configuration.
        metrics: Evaluation metrics (val_acc, loss, etc.).
        tags: Optional tags for filtering.
        artifact_path: Optional path to log as artifact.
        model_path: Optional model file to log.

    Returns:
        MLflow run_id if successful, None otherwise.
    """
    try:
        import mlflow

        mlflow.set_tracking_uri(_get_tracking_uri())

        with mlflow.start_run(run_name=run_name) as run:
            mlflow.log_params(params)
            mlflow.log_metrics(metrics)
            if tags:
                mlflow.set_tags(tags)

            if artifact_path and Path(artifact_path).exists():
                mlflow.log_artifact(artifact_path)

            if model_path and Path(model_path).exists():
                mlflow.log_artifact(model_path, artifact_path="model")

            run_id = run.info.run_id
            logger.info("mlflow_run_logged run_id=%s name=%s", run_id, run_name)
            return run_id

    except Exception as exc:
        logger.warning("mlflow_log_failed exception=%s", exc)
        return None


def register_model(
    model_name: str,
    run_id: str,
    stage: str = "staging",
) -> bool:
    """Register a model version in MLflow Model Registry.

    Args:
        model_name: Registry model name (e.g., "harmoniq-chord").
        run_id: MLflow run_id containing the model artifact.
        stage: Initial stage (staging, production, etc.).

    Returns:
        True if registration succeeded.
    """
    try:
        import mlflow

        mlflow.set_tracking_uri(_get_tracking_uri())

        model_uri = f"runs:/{run_id}/model"
        result = mlflow.register_model(model_uri, model_name)
        logger.info("model_registered model=%s version=%s stage=%s", model_name, result.version, stage)

        # Transition to requested stage
        client = mlflow.MlflowClient()
        client.transition_model_version_stage(
            name=model_name,
            version=result.version,
            stage=stage,
        )
        logger.info("model_transitioned model=%s version=%s stage=%s", model_name, result.version, stage)
        return True

    except Exception as exc:
        logger.warning("model_register_failed exception=%s", exc)
        return False


def get_production_model(model_name: str) -> dict | None:
    """Get the current production model version.

    Returns:
        Dict with model metadata, or None if no production model exists.
    """
    try:
        import mlflow

        mlflow.set_tracking_uri(_get_tracking_uri())

        client = mlflow.MlflowClient()
        versions = client.get_latest_versions(model_name, stages=["production"])

        if not versions:
            return None

        version = versions[0]
        return {
            "name": model_name,
            "version": version.version,
            "run_id": version.run_id,
            "stage": version.current_stage,
            "status": version.status,
            "creation_timestamp": version.creation_timestamp,
        }

    except Exception as exc:
        logger.warning("get_production_model_failed exception=%s", exc)
        return None


def compare_model_versions(
    model_name: str,
    version_a: str,
    version_b: str,
) -> dict | None:
    """Compare two model versions by their logged metrics.

    Returns:
        Dict with comparison results, or None if comparison fails.
    """
    try:
        import mlflow

        mlflow.set_tracking_uri(_get_tracking_uri())

        client = mlflow.MlflowClient()
        run_a = client.get_run(version_a)
        run_b = client.get_run(version_b)

        metrics_a = run_a.data.metrics
        metrics_b = run_b.data.metrics

        comparison = {}
        all_keys = set(metrics_a.keys()) | set(metrics_b.keys())
        for key in all_keys:
            val_a = metrics_a.get(key)
            val_b = metrics_b.get(key)
            comparison[key] = {
                "version_a": val_a,
                "version_b": val_b,
                "diff": (val_b - val_a) if val_a is not None and val_b is not None else None,
            }

        return comparison

    except Exception as exc:
        logger.warning("model_compare_failed exception=%s", exc)
        return None
