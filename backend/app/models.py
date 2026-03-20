from sqlalchemy import DateTime, Float, Integer, String, Text, text
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
    community_name: Mapped[str] = mapped_column(String(255), default="")
    water_use_type: Mapped[str] = mapped_column(String(32), default="mixed")
    community_risk_level: Mapped[str] = mapped_column(String(32), index=True, default="low")
    affected_groups: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    potential_impact: Mapped[str] = mapped_column(Text, default="")
    recommended_actions: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    time_to_acknowledge_minutes: Mapped[int] = mapped_column(Integer, default=60)
    time_to_intervene_minutes: Mapped[int] = mapped_column(Integer, default=240)
    escalation_target: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(32), index=True, default="new")
    status_note: Mapped[str] = mapped_column(Text, default="")
    risk_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    data_quality_flag: Mapped[str] = mapped_column(String(32), default="uncertain")


class NotificationRecord(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    alert_id: Mapped[str] = mapped_column(String(64), index=True)
    station_id: Mapped[str] = mapped_column(String(128), index=True)
    channel: Mapped[str] = mapped_column(String(32), index=True)
    recipient: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    delivery_status: Mapped[str] = mapped_column(String(32), index=True, default="queued")
    delivery_detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), index=True)
    delivered_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
