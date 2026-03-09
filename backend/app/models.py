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
