"""Initial schema."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260404_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "readings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("station_id", sa.String(length=128), nullable=False),
        sa.Column("ph", sa.Float(), nullable=False),
        sa.Column("tds", sa.Float(), nullable=False),
        sa.Column("turbidity", sa.Float(), nullable=False),
        sa.Column("temperature_c", sa.Float(), nullable=False),
        sa.Column("do_mg_l", sa.Float(), nullable=False),
        sa.Column("flow_l_min", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_readings_station_id"), "readings", ["station_id"], unique=False)
    op.create_index(op.f("ix_readings_timestamp"), "readings", ["timestamp"], unique=False)

    op.create_table(
        "alerts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("station_id", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column(
            "feature_contributions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("explanation_text", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_alerts_severity"), "alerts", ["severity"], unique=False)
    op.create_index(op.f("ix_alerts_station_id"), "alerts", ["station_id"], unique=False)
    op.create_index(op.f("ix_alerts_timestamp"), "alerts", ["timestamp"], unique=False)

    op.create_table(
        "incidents",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("station_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_changed_by", sa.String(length=128), nullable=False),
        sa.Column("status_note", sa.Text(), nullable=False),
        sa.Column("review_label", sa.String(length=32), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_incidents_created_at"), "incidents", ["created_at"], unique=False)
    op.create_index(op.f("ix_incidents_station_id"), "incidents", ["station_id"], unique=False)
    op.create_index(op.f("ix_incidents_status"), "incidents", ["status"], unique=False)
    op.create_index(op.f("ix_incidents_updated_at"), "incidents", ["updated_at"], unique=False)

    op.create_table(
        "incident_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("alert_id", sa.String(length=64), nullable=False),
        sa.Column("station_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("event_value", sa.String(length=64), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("changed_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_incident_events_alert_id"), "incident_events", ["alert_id"], unique=False)
    op.create_index(op.f("ix_incident_events_created_at"), "incident_events", ["created_at"], unique=False)
    op.create_index(op.f("ix_incident_events_event_type"), "incident_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_incident_events_station_id"), "incident_events", ["station_id"], unique=False)

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_jobs_created_at"), "jobs", ["created_at"], unique=False)
    op.create_index(op.f("ix_jobs_job_type"), "jobs", ["job_type"], unique=False)
    op.create_index(op.f("ix_jobs_status"), "jobs", ["status"], unique=False)
    op.create_index(op.f("ix_jobs_updated_at"), "jobs", ["updated_at"], unique=False)

    op.create_table(
        "device_states",
        sa.Column("station_id", sa.String(length=128), nullable=False),
        sa.Column("station_name", sa.String(length=128), nullable=False),
        sa.Column("region", sa.String(length=128), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("telemetry_payload", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("control_state", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("reading_preview", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.PrimaryKeyConstraint("station_id"),
    )
    op.create_index(op.f("ix_device_states_last_seen_at"), "device_states", ["last_seen_at"], unique=False)

    try:
        op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
        op.execute("SELECT create_hypertable('readings', 'timestamp', if_not_exists => TRUE)")
    except Exception:
        # Fallback for environments that ship plain PostgreSQL instead of TimescaleDB.
        pass


def downgrade() -> None:
    op.drop_index(op.f("ix_device_states_last_seen_at"), table_name="device_states")
    op.drop_table("device_states")
    op.drop_index(op.f("ix_jobs_updated_at"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_status"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_job_type"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_created_at"), table_name="jobs")
    op.drop_table("jobs")
    op.drop_index(op.f("ix_incident_events_station_id"), table_name="incident_events")
    op.drop_index(op.f("ix_incident_events_event_type"), table_name="incident_events")
    op.drop_index(op.f("ix_incident_events_created_at"), table_name="incident_events")
    op.drop_index(op.f("ix_incident_events_alert_id"), table_name="incident_events")
    op.drop_table("incident_events")
    op.drop_index(op.f("ix_incidents_updated_at"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_status"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_station_id"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_created_at"), table_name="incidents")
    op.drop_table("incidents")
    op.drop_index(op.f("ix_alerts_timestamp"), table_name="alerts")
    op.drop_index(op.f("ix_alerts_station_id"), table_name="alerts")
    op.drop_index(op.f("ix_alerts_severity"), table_name="alerts")
    op.drop_table("alerts")
    op.drop_index(op.f("ix_readings_timestamp"), table_name="readings")
    op.drop_index(op.f("ix_readings_station_id"), table_name="readings")
    op.drop_table("readings")
