"""Initial schema: jobs, coach_hydration, chord_enrichment, recompute_jobs

Revision ID: 0001
Revises:
Create Date: 2026-07-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("job_id", sa.String(64), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="processing", index=True),
        sa.Column("progress", sa.Float, nullable=True),
        sa.Column("stage_label", sa.String(256), nullable=True),
        sa.Column("analysis_stage", sa.String(64), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("processing_started_at", sa.Float, nullable=True),
        sa.Column("result", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "coach_hydration",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(64), nullable=False, index=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("sections", JSONB, nullable=True),
        sa.Column("fallback_reason", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "chord_enrichment",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(64), nullable=False, index=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("total_events", sa.Integer, nullable=True),
        sa.Column("corrected_events", sa.Integer, nullable=True),
        sa.Column("llm_latency_p50", sa.Float, nullable=True),
        sa.Column("llm_latency_p95", sa.Float, nullable=True),
        sa.Column("fallback_reason", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "recompute_jobs",
        sa.Column("job_id", sa.String(64), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("progress", sa.Float, nullable=True),
        sa.Column("stage_label", sa.String(256), nullable=True),
        sa.Column("beat_grid", JSONB, nullable=True),
        sa.Column("chord_timeline", JSONB, nullable=True),
        sa.Column("solo_notes", JSONB, nullable=True),
        sa.Column("musicxml", sa.Text, nullable=True),
        sa.Column("bar_timestamps", JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("recompute_jobs")
    op.drop_table("chord_enrichment")
    op.drop_table("coach_hydration")
    op.drop_table("jobs")
