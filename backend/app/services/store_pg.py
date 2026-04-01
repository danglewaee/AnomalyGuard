from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AlertRecord, DeviceStateRecord, IncidentRecord, JobRecord, ReadingRecord
from app.schemas import AnomalyAlert, JobStatus, StationProfile, WaterReading
from app.services.device_support import normalize_device_control


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
        incident = self.db.get(IncidentRecord, alert.id)
        if incident is None:
            self.db.add(
                IncidentRecord(
                    id=alert.id,
                    station_id=alert.station_id,
                    status="open",
                    created_at=alert.timestamp,
                    updated_at=alert.timestamp,
                    last_changed_by="system",
                    status_note="",
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
        stmt = select(AlertRecord, IncidentRecord).outerjoin(IncidentRecord, IncidentRecord.id == AlertRecord.id)
        if station_id:
            stmt = stmt.where(AlertRecord.station_id == station_id)
        if since_minutes and since_minutes > 0:
            since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
            stmt = stmt.where(AlertRecord.timestamp >= since)
        rows = self.db.execute(stmt.order_by(AlertRecord.timestamp.desc()).limit(limit)).all()
        return [self._alert_to_schema(alert_row, incident_row) for alert_row, incident_row in rows]

    def get_alert(self, alert_id: str) -> AlertRecord | None:
        return self.db.get(AlertRecord, alert_id)

    def alert_with_incident(self, alert_id: str) -> AnomalyAlert | None:
        row = self.db.execute(
            select(AlertRecord, IncidentRecord)
            .outerjoin(IncidentRecord, IncidentRecord.id == AlertRecord.id)
            .where(AlertRecord.id == alert_id)
        ).first()
        if row is None:
            return None
        alert_row, incident_row = row
        return self._alert_to_schema(alert_row, incident_row)

    def set_incident_status(self, alert_id: str, status: str, changed_by: str, note: str = "") -> AnomalyAlert | None:
        incident = self.db.get(IncidentRecord, alert_id)
        if incident is None:
            alert = self.db.get(AlertRecord, alert_id)
            if alert is None:
                return None
            incident = IncidentRecord(
                id=alert_id,
                station_id=alert.station_id,
                status="open",
                created_at=alert.timestamp,
                updated_at=alert.timestamp,
                last_changed_by="system",
                status_note="",
            )
            self.db.add(incident)

        now = datetime.now(timezone.utc)
        incident.status = status
        incident.updated_at = now
        incident.last_changed_by = changed_by
        incident.status_note = note

        if status == "acknowledged":
            incident.acknowledged_at = now
            incident.resolved_at = None
        elif status == "resolved":
            if incident.acknowledged_at is None:
                incident.acknowledged_at = now
            incident.resolved_at = now
        elif status == "open":
            incident.resolved_at = None

        self.db.commit()
        return self.alert_with_incident(alert_id)

    def set_alert_review(self, alert_id: str, label: str, reviewed_by: str, note: str = "") -> AnomalyAlert | None:
        incident = self.db.get(IncidentRecord, alert_id)
        if incident is None:
            alert = self.db.get(AlertRecord, alert_id)
            if alert is None:
                return None
            incident = IncidentRecord(
                id=alert_id,
                station_id=alert.station_id,
                status="open",
                created_at=alert.timestamp,
                updated_at=alert.timestamp,
                last_changed_by="system",
                status_note="",
            )
            self.db.add(incident)

        now = datetime.now(timezone.utc)
        incident.review_label = label
        incident.review_note = note
        incident.reviewed_at = now
        incident.reviewed_by = reviewed_by
        incident.updated_at = now

        self.db.commit()
        return self.alert_with_incident(alert_id)

    def create_job(self, job_id: str, job_type: str, requested_by: str, parameters: dict | None = None) -> JobStatus:
        now = datetime.now(timezone.utc)
        row = JobRecord(
            id=job_id,
            job_type=job_type,
            status="queued",
            requested_by=requested_by,
            created_at=now,
            updated_at=now,
            parameters=parameters or {},
            result_payload={},
            error_message="",
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return self._job_to_schema(row)

    def get_job(self, job_id: str) -> JobStatus | None:
        row = self.db.get(JobRecord, job_id)
        if row is None:
            return None
        return self._job_to_schema(row)

    def update_job_status(
        self,
        job_id: str,
        status: str,
        *,
        result_payload: dict | None = None,
        error_message: str | None = None,
    ) -> JobStatus | None:
        row = self.db.get(JobRecord, job_id)
        if row is None:
            return None

        now = datetime.now(timezone.utc)
        row.status = status
        row.updated_at = now
        if status == "running" and row.started_at is None:
            row.started_at = now
        if status in {"succeeded", "failed"}:
            row.completed_at = now

        if result_payload is not None:
            row.result_payload = result_payload
        if error_message is not None:
            row.error_message = error_message

        self.db.commit()
        self.db.refresh(row)
        return self._job_to_schema(row)

    def latest_device_states(self, station_id: str | None = None) -> list[dict]:
        stmt = select(DeviceStateRecord)
        if station_id:
            stmt = stmt.where(DeviceStateRecord.station_id == station_id)
        rows = self.db.scalars(stmt.order_by(DeviceStateRecord.last_seen_at.desc(), DeviceStateRecord.station_id.asc())).all()
        return [self._device_state_to_dict(row) for row in rows]

    def device_control_state(self, station_id: str) -> dict:
        row = self.db.get(DeviceStateRecord, station_id)
        if row is None:
            return normalize_device_control(None)
        return normalize_device_control(row.control_state)

    def upsert_device_state(
        self,
        profile: StationProfile,
        telemetry: dict,
        control: dict,
        reading_preview: dict,
        last_seen_at: datetime | None,
    ) -> dict:
        row = self.db.get(DeviceStateRecord, profile.station_id)
        if row is None:
            row = DeviceStateRecord(
                station_id=profile.station_id,
                station_name=profile.station_name,
                region=profile.region,
                last_seen_at=last_seen_at,
                telemetry_payload=telemetry,
                control_state=normalize_device_control(control),
                reading_preview=reading_preview,
            )
            self.db.add(row)
        else:
            row.station_name = profile.station_name
            row.region = profile.region
            row.last_seen_at = last_seen_at
            row.telemetry_payload = telemetry
            row.control_state = normalize_device_control(control)
            row.reading_preview = reading_preview
        self.db.commit()
        self.db.refresh(row)
        return self._device_state_to_dict(row)

    def set_device_control(self, profile: StationProfile, control: dict) -> dict:
        row = self.db.get(DeviceStateRecord, profile.station_id)
        normalized = normalize_device_control(control)
        if row is None:
            row = DeviceStateRecord(
                station_id=profile.station_id,
                station_name=profile.station_name,
                region=profile.region,
                telemetry_payload={},
                control_state=normalized,
                reading_preview={},
            )
            self.db.add(row)
        else:
            row.station_name = profile.station_name
            row.region = profile.region
            row.control_state = normalized
        self.db.commit()
        self.db.refresh(row)
        return self._device_state_to_dict(row)

    def counts(self) -> dict[str, int]:
        readings = self.db.scalar(select(func.count()).select_from(ReadingRecord)) or 0
        alerts = self.db.scalar(select(func.count()).select_from(AlertRecord)) or 0
        devices = self.db.scalar(select(func.count()).select_from(DeviceStateRecord)) or 0
        jobs = self.db.scalar(select(func.count()).select_from(JobRecord)) or 0
        return {"readings": int(readings), "alerts": int(alerts), "device_states": int(devices), "jobs": int(jobs)}

    def _device_state_to_dict(self, row: DeviceStateRecord) -> dict:
        return {
            "station_id": row.station_id,
            "station_name": row.station_name,
            "region": row.region,
            "source": "device",
            "last_seen_at": row.last_seen_at,
            "telemetry": row.telemetry_payload or {},
            "control": normalize_device_control(row.control_state),
            "reading_preview": row.reading_preview or {},
        }

    def _alert_to_schema(self, row: AlertRecord, incident: IncidentRecord | None) -> AnomalyAlert:
        return AnomalyAlert(
            id=row.id,
            timestamp=row.timestamp,
            station_id=row.station_id,
            severity=row.severity,
            score=row.score,
            reasons=row.reasons,
            feature_contributions=row.feature_contributions,
            incident_status=incident.status if incident is not None else "open",
            incident_note=incident.status_note if incident is not None else "",
            incident_updated_at=incident.updated_at if incident is not None else None,
            review_label=incident.review_label if incident is not None else None,
            review_note=incident.review_note if incident is not None else "",
            reviewed_at=incident.reviewed_at if incident is not None else None,
            reviewed_by=incident.reviewed_by if incident is not None else "",
        )

    def _job_to_schema(self, row: JobRecord) -> JobStatus:
        return JobStatus(
            id=row.id,
            job_type=row.job_type,
            status=row.status,
            requested_by=row.requested_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
            started_at=row.started_at,
            completed_at=row.completed_at,
            parameters=row.parameters or {},
            result_payload=row.result_payload or {},
            error_message=row.error_message or "",
        )
