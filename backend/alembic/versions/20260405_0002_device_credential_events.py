"""Add device credential audit events."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260405_0002"
down_revision: Union[str, None] = "20260404_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "device_credential_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("station_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("key_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column(
            "metadata_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_device_credential_events_station_id"),
        "device_credential_events",
        ["station_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_device_credential_events_event_type"),
        "device_credential_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_device_credential_events_created_at"),
        "device_credential_events",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_device_credential_events_created_at"), table_name="device_credential_events")
    op.drop_index(op.f("ix_device_credential_events_event_type"), table_name="device_credential_events")
    op.drop_index(op.f("ix_device_credential_events_station_id"), table_name="device_credential_events")
    op.drop_table("device_credential_events")
