from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AlertRecord, NotificationRecord, ReadingRecord
from app.schemas import AlertNotification, AnomalyAlert, WaterReading


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
                community_name=alert.community_name,
                water_use_type=alert.water_use_type,
                community_risk_level=alert.community_risk_level,
                affected_groups=alert.affected_groups,
                potential_impact=alert.potential_impact,
                recommended_actions=alert.recommended_actions,
                time_to_acknowledge_minutes=alert.time_to_acknowledge_minutes,
                time_to_intervene_minutes=alert.time_to_intervene_minutes,
                escalation_target=alert.escalation_target,
                status=alert.status,
                status_note=alert.status_note,
                risk_confidence=alert.risk_confidence,
                data_quality_flag=alert.data_quality_flag,
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
                reasons=r.reasons or [],
                feature_contributions=r.feature_contributions or {},
                community_name=getattr(r, "community_name", "") or "",
                water_use_type=getattr(r, "water_use_type", "mixed") or "mixed",
                community_risk_level=getattr(r, "community_risk_level", "low") or "low",
                affected_groups=getattr(r, "affected_groups", []) or [],
                potential_impact=getattr(r, "potential_impact", "") or "",
                recommended_actions=getattr(r, "recommended_actions", []) or [],
                time_to_acknowledge_minutes=getattr(r, "time_to_acknowledge_minutes", 60) or 60,
                time_to_intervene_minutes=getattr(r, "time_to_intervene_minutes", 240) or 240,
                escalation_target=getattr(r, "escalation_target", "") or "",
                status=getattr(r, "status", "new") or "new",
                status_note=getattr(r, "status_note", "") or "",
                risk_confidence=getattr(r, "risk_confidence", 0.0) or 0.0,
                data_quality_flag=getattr(r, "data_quality_flag", "uncertain") or "uncertain",
            )
            for r in rows
        ]

    def get_alert(self, alert_id: str) -> AlertRecord | None:
        return self.db.get(AlertRecord, alert_id)

    def update_alert_status(self, alert_id: str, status: str, note: str = "") -> AlertRecord | None:
        row = self.db.get(AlertRecord, alert_id)
        if row is None:
            return None
        row.status = status
        row.status_note = note or row.status_note or ""
        self.db.commit()
        self.db.refresh(row)
        return row

    def upsert_notification(self, notification: AlertNotification) -> None:
        self.db.merge(
            NotificationRecord(
                id=notification.id,
                alert_id=notification.alert_id,
                station_id=notification.station_id,
                channel=notification.channel,
                target_role=notification.target_role,
                recipient=notification.recipient,
                title=notification.title,
                body=notification.body,
                delivery_status=notification.delivery_status,
                delivery_detail=notification.delivery_detail,
                created_at=notification.created_at,
                delivered_at=notification.delivered_at,
            )
        )
        self.db.commit()

    def update_notification_delivery(
        self,
        notification_id: str,
        delivery_status: str,
        delivery_detail: str,
        delivered_at: datetime | None,
    ) -> NotificationRecord | None:
        row = self.db.get(NotificationRecord, notification_id)
        if row is None:
            return None
        row.delivery_status = delivery_status
        row.delivery_detail = delivery_detail
        row.delivered_at = delivered_at
        self.db.commit()
        self.db.refresh(row)
        return row

    def notifications_for_alert(self, alert_id: str) -> list[AlertNotification]:
        stmt = select(NotificationRecord).where(NotificationRecord.alert_id == alert_id)
        rows = self.db.scalars(stmt.order_by(NotificationRecord.created_at.desc())).all()
        return [
            AlertNotification(
                id=r.id,
                alert_id=r.alert_id,
                station_id=r.station_id,
                channel=r.channel,
                target_role=getattr(r, "target_role", "system-log") or "system-log",
                recipient=r.recipient,
                title=r.title,
                body=r.body,
                delivery_status=r.delivery_status,
                delivery_detail=r.delivery_detail,
                created_at=r.created_at,
                delivered_at=r.delivered_at,
            )
            for r in rows
        ]

    def counts(self) -> dict[str, int]:
        readings = self.db.scalar(select(func.count()).select_from(ReadingRecord)) or 0
        alerts = self.db.scalar(select(func.count()).select_from(AlertRecord)) or 0
        notifications = self.db.scalar(select(func.count()).select_from(NotificationRecord)) or 0
        return {"readings": int(readings), "alerts": int(alerts), "notifications": int(notifications)}
