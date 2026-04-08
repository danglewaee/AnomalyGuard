"""Attach model registry entries to artifact identity."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260408_0004"
down_revision: Union[str, None] = "20260407_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("model_registry_entries", sa.Column("candidate_id", sa.String(length=128), nullable=True))
    op.add_column(
        "model_registry_entries",
        sa.Column("artifact_key", sa.String(length=128), nullable=False, server_default="anomalyguard-anomaly-detector"),
    )
    op.add_column(
        "model_registry_entries",
        sa.Column("artifact_version", sa.String(length=128), nullable=False, server_default="legacy"),
    )
    op.add_column(
        "model_registry_entries",
        sa.Column("source_revision", sa.String(length=128), nullable=False, server_default="legacy"),
    )
    op.add_column("model_registry_entries", sa.Column("artifact_uri", sa.Text(), nullable=False, server_default=""))

    op.execute(
        """
        UPDATE model_registry_entries
        SET candidate_id = CONCAT('legacy-', SUBSTRING(COALESCE(manifest_id, ''), 1, 64)),
            artifact_key = COALESCE(NULLIF(artifact_key, ''), 'anomalyguard-anomaly-detector'),
            artifact_version = COALESCE(NULLIF(artifact_version, ''), CONCAT('legacy-', SUBSTRING(COALESCE(manifest_id, ''), 1, 48))),
            source_revision = COALESCE(NULLIF(source_revision, ''), 'legacy'),
            artifact_uri = COALESCE(artifact_uri, '')
        WHERE candidate_id IS NULL OR candidate_id = ''
        """
    )
    op.alter_column("model_registry_entries", "candidate_id", nullable=False)
    op.drop_constraint("model_registry_entries_pkey", "model_registry_entries", type_="primary")
    op.create_primary_key("pk_model_registry_entries", "model_registry_entries", ["candidate_id"])
    op.create_index("ix_model_registry_entries_manifest_id", "model_registry_entries", ["manifest_id"], unique=False)

    op.add_column("model_registry_events", sa.Column("candidate_id", sa.String(length=128), nullable=True))
    op.execute(
        """
        UPDATE model_registry_events AS events
        SET candidate_id = entries.candidate_id
        FROM model_registry_entries AS entries
        WHERE entries.manifest_id = events.manifest_id
          AND (events.candidate_id IS NULL OR events.candidate_id = '')
        """
    )
    op.execute(
        """
        UPDATE model_registry_events
        SET candidate_id = CONCAT('legacy-', SUBSTRING(COALESCE(manifest_id, ''), 1, 64))
        WHERE candidate_id IS NULL OR candidate_id = ''
        """
    )
    op.alter_column("model_registry_events", "candidate_id", nullable=False)
    op.create_index("ix_model_registry_events_candidate_id", "model_registry_events", ["candidate_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_model_registry_events_candidate_id", table_name="model_registry_events")
    op.drop_column("model_registry_events", "candidate_id")

    op.drop_index("ix_model_registry_entries_manifest_id", table_name="model_registry_entries")
    op.drop_constraint("pk_model_registry_entries", "model_registry_entries", type_="primary")
    op.create_primary_key("model_registry_entries_pkey", "model_registry_entries", ["manifest_id"])
    op.drop_column("model_registry_entries", "artifact_uri")
    op.drop_column("model_registry_entries", "source_revision")
    op.drop_column("model_registry_entries", "artifact_version")
    op.drop_column("model_registry_entries", "artifact_key")
    op.drop_column("model_registry_entries", "candidate_id")
