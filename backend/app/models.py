from datetime import datetime

from sqlalchemy import DateTime, Float, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ReadingRecord(Base):
    __tablename__ = "readings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[DateTime] = mapped_column(DateTime(timezone=True), index=True)
    station_id: Mapped[str] = mapped_column(String(128), index=True)
    ph: Mapped[float] = mapped_column(Float)
    tds: Mapped[float] = mapped_column(Float)
    turbidity: Mapped[float] = mapped_column(Float)
    temperature_c: Mapped[float] = mapped_column(Float)
    do_mg_l: Mapped[float] = mapped_column(Float)
    flow_l_min: Mapped[float] = mapped_column(Float)


class AlertRecord(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    timestamp: Mapped[DateTime] = mapped_column(DateTime(timezone=True), index=True)
    station_id: Mapped[str] = mapped_column(String(128), index=True)
    severity: Mapped[str] = mapped_column(String(32), index=True)
    score: Mapped[float] = mapped_column(Float)
    reasons: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    feature_contributions: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    explanation_text: Mapped[str] = mapped_column(Text, default="")


class IncidentRecord(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    station_id: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_changed_by: Mapped[str] = mapped_column(String(128), default="")
    status_note: Mapped[str] = mapped_column(Text, default="")
    review_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str] = mapped_column(String(128), default="")


class IncidentEventRecord(Base):
    __tablename__ = "incident_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    alert_id: Mapped[str] = mapped_column(String(64), index=True)
    station_id: Mapped[str] = mapped_column(String(128), index=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    event_value: Mapped[str] = mapped_column(String(64), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    changed_by: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class JobRecord(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="queued")
    requested_by: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parameters: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    result_payload: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    error_message: Mapped[str] = mapped_column(Text, default="")


class DeviceStateRecord(Base):
    __tablename__ = "device_states"

    station_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    station_name: Mapped[str] = mapped_column(String(128), default="")
    region: Mapped[str] = mapped_column(String(128), default="")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True, nullable=True)
    telemetry_payload: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    control_state: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    reading_preview: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class DeviceCredentialEventRecord(Base):
    __tablename__ = "device_credential_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    station_id: Mapped[str] = mapped_column(String(128), index=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    actor: Mapped[str] = mapped_column(String(128), default="")
    key_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    metadata_payload: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ModelRegistryEntryRecord(Base):
    __tablename__ = "model_registry_entries"

    manifest_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    state: Mapped[str] = mapped_column(String(32), index=True, default="prepared")
    promotion_decision: Mapped[str] = mapped_column(String(32), index=True, default="blocked")
    approve_for_shadow: Mapped[bool] = mapped_column(default=False)
    approve_for_canary: Mapped[bool] = mapped_column(default=False)
    station_id: Mapped[str] = mapped_column(String(128), index=True, default="")
    since_minutes: Mapped[int | None] = mapped_column(nullable=True)
    recommendation: Mapped[str] = mapped_column(String(32), default="hold")
    readiness_score: Mapped[int] = mapped_column(default=0)
    current_precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommended_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviewed_count: Mapped[int] = mapped_column(default=0)
    blocker_count: Mapped[int] = mapped_column(default=0)
    warning_count: Mapped[int] = mapped_column(default=0)
    mlflow_run_id: Mapped[str] = mapped_column(String(128), default="")
    run_name: Mapped[str] = mapped_column(String(128), default="")
    status_note: Mapped[str] = mapped_column(Text, default="")
    last_changed_by: Mapped[str] = mapped_column(String(128), default="")
    bundle_payload: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ModelRegistryEventRecord(Base):
    __tablename__ = "model_registry_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    manifest_id: Mapped[str] = mapped_column(String(64), index=True)
    from_state: Mapped[str] = mapped_column(String(32), default="")
    to_state: Mapped[str] = mapped_column(String(32), index=True)
    actor: Mapped[str] = mapped_column(String(128), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    metadata_payload: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
