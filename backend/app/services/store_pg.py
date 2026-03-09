from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AlertRecord, ReadingRecord
from app.schemas import AnomalyAlert, WaterReading


class PostgresStore:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add_reading(self, reading: WaterReading) -> None:
        self.db.add(
            ReadingRecord(
                timestamp=reading.timestamp,
                station_id=reading.station_id,
                ph=reading.ph,
                tds=reading.tds,
                turbidity=reading.turbidity,
                temperature_c=reading.temperature_c,
                do_mg_l=reading.do_mg_l,
                flow_l_min=reading.flow_l_min,
            )
        )
        self.db.commit()

    def add_alert(self, alert: AnomalyAlert, explanation_text: str = "") -> None:
        self.db.merge(
            AlertRecord(
                id=alert.id,
                timestamp=alert.timestamp,
                station_id=alert.station_id,
                severity=alert.severity,
                score=alert.score,
                reasons=alert.reasons,
                feature_contributions=alert.feature_contributions,
                explanation_text=explanation_text,
            )
        )
        self.db.commit()

    def latest_readings(self, limit: int, station_id: str | None = None, since_minutes: int | None = None) -> list[WaterReading]:
        stmt = select(ReadingRecord)
        if station_id:
            stmt = stmt.where(ReadingRecord.station_id == station_id)
        if since_minutes and since_minutes > 0:
            since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
            stmt = stmt.where(ReadingRecord.timestamp >= since)
        rows = self.db.scalars(stmt.order_by(ReadingRecord.timestamp.desc()).limit(limit)).all()
        rows.reverse()
        return [
            WaterReading(
                timestamp=r.timestamp,
                station_id=r.station_id,
                ph=r.ph,
                tds=r.tds,
                turbidity=r.turbidity,
                temperature_c=r.temperature_c,
                do_mg_l=r.do_mg_l,
                flow_l_min=r.flow_l_min,
            )
            for r in rows
        ]

    def latest_alerts(self, limit: int, station_id: str | None = None, since_minutes: int | None = None) -> list[AnomalyAlert]:
        stmt = select(AlertRecord)
        if station_id:
            stmt = stmt.where(AlertRecord.station_id == station_id)
        if since_minutes and since_minutes > 0:
            since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
            stmt = stmt.where(AlertRecord.timestamp >= since)
        rows = self.db.scalars(stmt.order_by(AlertRecord.timestamp.desc()).limit(limit)).all()
        return [
            AnomalyAlert(
                id=r.id,
                timestamp=r.timestamp,
                station_id=r.station_id,
                severity=r.severity,
                score=r.score,
                reasons=r.reasons,
                feature_contributions=r.feature_contributions,
            )
            for r in rows
        ]

    def get_alert(self, alert_id: str) -> AlertRecord | None:
        return self.db.get(AlertRecord, alert_id)

    def counts(self) -> dict[str, int]:
        readings = self.db.scalar(select(func.count()).select_from(ReadingRecord)) or 0
        alerts = self.db.scalar(select(func.count()).select_from(AlertRecord)) or 0
        return {"readings": int(readings), "alerts": int(alerts)}
