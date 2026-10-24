"""Celery application configuration for Harmoniq.

Canonical app lives in ``app.celery_app``; this module re-exports it for
backwards compatibility.
"""

from __future__ import annotations

from app.celery_app import app as celery_app

__all__ = ["celery_app"]
