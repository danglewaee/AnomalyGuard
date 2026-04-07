"""Add model registry state machine tables."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260407_0003"
down_revision: Union[str, None] = "20260405_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "model_registry_entries",
        sa.Column("manifest_id", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("promotion_decision", sa.String(length=32), nullable=False),
        sa.Column("approve_for_shadow", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("approve_for_canary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("station_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("since_minutes", sa.Integer(), nullable=True),
        sa.Column("recommendation", sa.String(length=32), nullable=False, server_default="hold"),
        sa.Column("readiness_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_precision", sa.Float(), nullable=True),
        sa.Column("recommended_threshold", sa.Float(), nullable=True),
        sa.Column("reviewed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocker_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mlflow_run_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("run_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("status_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_changed_by", sa.String(length=128), nullable=False, server_default=""),
        sa.Column(
            "bundle_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("manifest_id"),
    )
    op.create_index(op.f("ix_model_registry_entries_job_id"), "model_registry_entries", ["job_id"], unique=False)
    op.create_index(op.f("ix_model_registry_entries_state"), "model_registry_entries", ["state"], unique=False)
    op.create_index(
        op.f("ix_model_registry_entries_promotion_decision"),
        "model_registry_entries",
        ["promotion_decision"],
        unique=False,
    )
    op.create_index(op.f("ix_model_registry_entries_station_id"), "model_registry_entries", ["station_id"], unique=False)
    op.create_index(op.f("ix_model_registry_entries_created_at"), "model_registry_entries", ["created_at"], unique=False)
    op.create_index(op.f("ix_model_registry_entries_updated_at"), "model_registry_entries", ["updated_at"], unique=False)

    op.create_table(
        "model_registry_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("manifest_id", sa.String(length=64), nullable=False),
        sa.Column("from_state", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("to_state", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "metadata_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_model_registry_events_manifest_id"), "model_registry_events", ["manifest_id"], unique=False)
    op.create_index(op.f("ix_model_registry_events_to_state"), "model_registry_events", ["to_state"], unique=False)
    op.create_index(op.f("ix_model_registry_events_created_at"), "model_registry_events", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_model_registry_events_created_at"), table_name="model_registry_events")
    op.drop_index(op.f("ix_model_registry_events_to_state"), table_name="model_registry_events")
    op.drop_index(op.f("ix_model_registry_events_manifest_id"), table_name="model_registry_events")
    op.drop_table("model_registry_events")

    op.drop_index(op.f("ix_model_registry_entries_updated_at"), table_name="model_registry_entries")
    op.drop_index(op.f("ix_model_registry_entries_created_at"), table_name="model_registry_entries")
    op.drop_index(op.f("ix_model_registry_entries_station_id"), table_name="model_registry_entries")
    op.drop_index(op.f("ix_model_registry_entries_promotion_decision"), table_name="model_registry_entries")
    op.drop_index(op.f("ix_model_registry_entries_state"), table_name="model_registry_entries")
    op.drop_index(op.f("ix_model_registry_entries_job_id"), table_name="model_registry_entries")
    op.drop_table("model_registry_entries")
