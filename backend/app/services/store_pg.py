from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AlertRecord,
    DeviceCredentialEventRecord,
    DeviceStateRecord,
    IncidentEventRecord,
    IncidentRecord,
    JobRecord,
    ModelRegistryEntryRecord,
    ModelRegistryEventRecord,
    ReadingRecord,
)
from app.schemas import (
    AlertHistoryEntry,
    AnomalyAlert,
    DeviceCredentialAuditEntry,
    JobStatus,
    ModelRegistryEntrySummary,
    ModelRegistryEventEntry,
    StationProfile,
    WaterReading,
)
from app.services.device_support import normalize_device_control
from app.services.metrics import observe_job_queue_seconds, observe_job_run_seconds, record_job_status_transition


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

    def existing_reading_timestamps(self, station_id: str, timestamps: list[datetime]) -> set[datetime]:
        if not timestamps:
            return set()

        stmt = select(ReadingRecord.timestamp).where(
            ReadingRecord.station_id == station_id,
            ReadingRecord.timestamp.in_(timestamps),
        )
        rows = self.db.scalars(stmt).all()
        return set(rows)

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
            self._record_alert_history(
                alert_id=alert.id,
                station_id=alert.station_id,
                event_type="detected",
                event_value=alert.severity,
                changed_by="system",
                note="",
                created_at=alert.timestamp,
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

    def reviewed_alerts(
        self,
        limit: int,
        *,
        label: str | None = None,
        station_id: str | None = None,
        since_minutes: int | None = None,
    ) -> list[AnomalyAlert]:
        stmt = select(AlertRecord, IncidentRecord).join(IncidentRecord, IncidentRecord.id == AlertRecord.id).where(
            IncidentRecord.review_label.is_not(None)
        )
        if label:
            stmt = stmt.where(IncidentRecord.review_label == label)
        if station_id:
            stmt = stmt.where(AlertRecord.station_id == station_id)
        if since_minutes and since_minutes > 0:
            since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
            stmt = stmt.where(IncidentRecord.reviewed_at >= since)

        rows = self.db.execute(
            stmt.order_by(IncidentRecord.reviewed_at.desc(), AlertRecord.timestamp.desc()).limit(limit)
        ).all()
        return [self._alert_to_schema(alert_row, incident_row) for alert_row, incident_row in rows]

    def alert_history(self, alert_id: str, limit: int = 25) -> list[AlertHistoryEntry]:
        stmt = (
            select(IncidentEventRecord)
            .where(IncidentEventRecord.alert_id == alert_id)
            .order_by(IncidentEventRecord.created_at.desc(), IncidentEventRecord.id.desc())
            .limit(limit)
        )
        rows = self.db.scalars(stmt).all()
        rows.reverse()
        return [self._history_to_schema(row) for row in rows]

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

        self._record_alert_history(
            alert_id=alert_id,
            station_id=incident.station_id,
            event_type="incident_status",
            event_value=status,
            changed_by=changed_by,
            note=note,
            created_at=now,
        )
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
        incident.last_changed_by = reviewed_by

        self._record_alert_history(
            alert_id=alert_id,
            station_id=incident.station_id,
            event_type="review_label",
            event_value=label,
            changed_by=reviewed_by,
            note=note,
            created_at=now,
        )

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
        record_job_status_transition(job_type, "queued")
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
        queue_seconds: float | None = None
        run_seconds: float | None = None
        row.status = status
        row.updated_at = now
        if status == "running" and row.started_at is None:
            row.started_at = now
            queue_seconds = (row.started_at - row.created_at).total_seconds()
        if status in {"succeeded", "failed"}:
            row.completed_at = now
            if row.started_at is not None:
                run_seconds = (row.completed_at - row.started_at).total_seconds()

        if result_payload is not None:
            row.result_payload = result_payload
        if error_message is not None:
            row.error_message = error_message

        self.db.commit()
        self.db.refresh(row)
        record_job_status_transition(row.job_type, status)
        if queue_seconds is not None:
            observe_job_queue_seconds(row.job_type, queue_seconds)
        if run_seconds is not None:
            observe_job_run_seconds(row.job_type, status, run_seconds)
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

    def record_device_credential_event(
        self,
        *,
        station_id: str,
        event_type: str,
        actor: str,
        key_fingerprint: str,
        note: str,
        metadata_payload: dict | None = None,
    ) -> DeviceCredentialAuditEntry:
        row = DeviceCredentialEventRecord(
            station_id=station_id,
            event_type=event_type,
            actor=actor,
            key_fingerprint=key_fingerprint,
            note=note,
            metadata_payload=metadata_payload or {},
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return self._device_credential_event_to_schema(row)

    def device_credential_events(
        self,
        *,
        limit: int = 100,
        station_id: str | None = None,
    ) -> list[DeviceCredentialAuditEntry]:
        stmt = select(DeviceCredentialEventRecord)
        if station_id:
            stmt = stmt.where(DeviceCredentialEventRecord.station_id == station_id)
        rows = self.db.scalars(
            stmt.order_by(DeviceCredentialEventRecord.created_at.desc(), DeviceCredentialEventRecord.id.desc()).limit(limit)
        ).all()
        return [self._device_credential_event_to_schema(row) for row in rows]

    def upsert_model_registry_entry(
        self,
        *,
        manifest_id: str,
        job_id: str,
        promotion_decision: str,
        approve_for_shadow: bool,
        approve_for_canary: bool,
        station_id: str | None,
        since_minutes: int | None,
        recommendation: str,
        readiness_score: int,
        current_precision: float | None,
        recommended_threshold: float | None,
        reviewed_count: int,
        blocker_count: int,
        warning_count: int,
        mlflow_run_id: str,
        run_name: str,
        status_note: str,
        changed_by: str,
        bundle_payload: dict | None,
    ) -> ModelRegistryEntrySummary:
        now = datetime.now(timezone.utc)
        row = self.db.get(ModelRegistryEntryRecord, manifest_id)
        if row is None:
            row = ModelRegistryEntryRecord(
                manifest_id=manifest_id,
                job_id=job_id,
                state="prepared",
                promotion_decision=promotion_decision,
                approve_for_shadow=approve_for_shadow,
                approve_for_canary=approve_for_canary,
                station_id=station_id or "",
                since_minutes=since_minutes,
                recommendation=recommendation,
                readiness_score=readiness_score,
                current_precision=current_precision,
                recommended_threshold=recommended_threshold,
                reviewed_count=reviewed_count,
                blocker_count=blocker_count,
                warning_count=warning_count,
                mlflow_run_id=mlflow_run_id,
                run_name=run_name,
                status_note=status_note,
                last_changed_by=changed_by,
                bundle_payload=bundle_payload or {},
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)
            self._record_model_registry_event(
                manifest_id=manifest_id,
                from_state="",
                to_state="prepared",
                actor=changed_by,
                note=status_note,
                metadata_payload={
                    "promotion_decision": promotion_decision,
                    "approve_for_shadow": approve_for_shadow,
                    "approve_for_canary": approve_for_canary,
                    "job_id": job_id,
                },
                created_at=now,
            )
        else:
            row.job_id = job_id or row.job_id
            row.promotion_decision = promotion_decision
            row.approve_for_shadow = approve_for_shadow
            row.approve_for_canary = approve_for_canary
            row.station_id = station_id or ""
            row.since_minutes = since_minutes
            row.recommendation = recommendation
            row.readiness_score = readiness_score
            row.current_precision = current_precision
            row.recommended_threshold = recommended_threshold
            row.reviewed_count = reviewed_count
            row.blocker_count = blocker_count
            row.warning_count = warning_count
            row.mlflow_run_id = mlflow_run_id
            row.run_name = run_name
            row.status_note = status_note
            row.last_changed_by = changed_by
            row.bundle_payload = bundle_payload or {}
            row.updated_at = now

        self.db.commit()
        self.db.refresh(row)
        return self._model_registry_entry_to_schema(row)

    def get_model_registry_entry(self, manifest_id: str) -> ModelRegistryEntrySummary | None:
        row = self.db.get(ModelRegistryEntryRecord, manifest_id)
        if row is None:
            return None
        return self._model_registry_entry_to_schema(row)

    def list_model_registry_entries(
        self,
        *,
        limit: int = 20,
        state: str | None = None,
    ) -> list[ModelRegistryEntrySummary]:
        stmt = select(ModelRegistryEntryRecord)
        if state:
            stmt = stmt.where(ModelRegistryEntryRecord.state == state)
        rows = self.db.scalars(
            stmt.order_by(ModelRegistryEntryRecord.updated_at.desc(), ModelRegistryEntryRecord.created_at.desc()).limit(limit)
        ).all()
        return [self._model_registry_entry_to_schema(row) for row in rows]

    def update_model_registry_state(
        self,
        *,
        manifest_id: str,
        target_state: str,
        changed_by: str,
        note: str,
        metadata_payload: dict | None = None,
    ) -> ModelRegistryEntrySummary | None:
        row = self.db.get(ModelRegistryEntryRecord, manifest_id)
        if row is None:
            return None

        now = datetime.now(timezone.utc)
        previous_state = row.state
        row.state = target_state
        row.updated_at = now
        row.last_changed_by = changed_by
        row.status_note = note
        if target_state in {"shadow", "canary"}:
            row.promoted_at = now
        if target_state == "rolled_back":
            row.rolled_back_at = now

        self._record_model_registry_event(
            manifest_id=manifest_id,
            from_state=previous_state,
            to_state=target_state,
            actor=changed_by,
            note=note,
            metadata_payload=metadata_payload or {},
            created_at=now,
        )
        self.db.commit()
        self.db.refresh(row)
        return self._model_registry_entry_to_schema(row)

    def model_registry_history(self, manifest_id: str, limit: int = 20) -> list[ModelRegistryEventEntry]:
        stmt = (
            select(ModelRegistryEventRecord)
            .where(ModelRegistryEventRecord.manifest_id == manifest_id)
            .order_by(ModelRegistryEventRecord.created_at.desc(), ModelRegistryEventRecord.id.desc())
            .limit(limit)
        )
        rows = self.db.scalars(stmt).all()
        rows.reverse()
        return [self._model_registry_event_to_schema(row) for row in rows]

    def counts(self) -> dict[str, int]:
        readings = self.db.scalar(select(func.count()).select_from(ReadingRecord)) or 0
        alerts = self.db.scalar(select(func.count()).select_from(AlertRecord)) or 0
        devices = self.db.scalar(select(func.count()).select_from(DeviceStateRecord)) or 0
        credential_events = self.db.scalar(select(func.count()).select_from(DeviceCredentialEventRecord)) or 0
        jobs = self.db.scalar(select(func.count()).select_from(JobRecord)) or 0
        model_registry_entries = self.db.scalar(select(func.count()).select_from(ModelRegistryEntryRecord)) or 0
        model_registry_events = self.db.scalar(select(func.count()).select_from(ModelRegistryEventRecord)) or 0
        return {
            "readings": int(readings),
            "alerts": int(alerts),
            "device_states": int(devices),
            "device_credential_events": int(credential_events),
            "jobs": int(jobs),
            "model_registry_entries": int(model_registry_entries),
            "model_registry_events": int(model_registry_events),
        }

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

    def _record_alert_history(
        self,
        *,
        alert_id: str,
        station_id: str,
        event_type: str,
        event_value: str,
        changed_by: str,
        note: str,
        created_at: datetime,
    ) -> None:
        self.db.add(
            IncidentEventRecord(
                alert_id=alert_id,
                station_id=station_id,
                event_type=event_type,
                event_value=event_value,
                note=note,
                changed_by=changed_by,
                created_at=created_at,
            )
        )

    def _history_to_schema(self, row: IncidentEventRecord) -> AlertHistoryEntry:
        return AlertHistoryEntry(
            id=row.id,
            alert_id=row.alert_id,
            station_id=row.station_id,
            event_type=row.event_type,
            event_value=row.event_value,
            note=row.note or "",
            changed_by=row.changed_by or "",
            created_at=row.created_at,
        )

    def _device_credential_event_to_schema(self, row: DeviceCredentialEventRecord) -> DeviceCredentialAuditEntry:
        return DeviceCredentialAuditEntry(
            id=row.id,
            station_id=row.station_id,
            event_type=row.event_type,
            actor=row.actor or "",
            key_fingerprint=row.key_fingerprint or "",
            note=row.note or "",
            metadata_payload=row.metadata_payload or {},
            created_at=row.created_at,
        )

    def _record_model_registry_event(
        self,
        *,
        manifest_id: str,
        from_state: str,
        to_state: str,
        actor: str,
        note: str,
        metadata_payload: dict,
        created_at: datetime,
    ) -> None:
        self.db.add(
            ModelRegistryEventRecord(
                manifest_id=manifest_id,
                from_state=from_state,
                to_state=to_state,
                actor=actor,
                note=note,
                metadata_payload=metadata_payload,
                created_at=created_at,
            )
        )

    def _model_registry_entry_to_schema(self, row: ModelRegistryEntryRecord) -> ModelRegistryEntrySummary:
        return ModelRegistryEntrySummary(
            manifest_id=row.manifest_id,
            job_id=row.job_id or "",
            state=row.state,
            promotion_decision=row.promotion_decision,
            approve_for_shadow=row.approve_for_shadow,
            approve_for_canary=row.approve_for_canary,
            station_id=row.station_id or None,
            since_minutes=row.since_minutes,
            recommendation=row.recommendation,
            readiness_score=row.readiness_score,
            current_precision=row.current_precision,
            recommended_threshold=row.recommended_threshold,
            reviewed_count=row.reviewed_count,
            blocker_count=row.blocker_count,
            warning_count=row.warning_count,
            mlflow_run_id=row.mlflow_run_id or "",
            run_name=row.run_name or "",
            status_note=row.status_note or "",
            last_changed_by=row.last_changed_by or "",
            created_at=row.created_at,
            updated_at=row.updated_at,
            promoted_at=row.promoted_at,
            rolled_back_at=row.rolled_back_at,
            bundle_payload=row.bundle_payload or {},
        )

    def _model_registry_event_to_schema(self, row: ModelRegistryEventRecord) -> ModelRegistryEventEntry:
        return ModelRegistryEventEntry(
            id=row.id,
            manifest_id=row.manifest_id,
            from_state=row.from_state or "",
            to_state=row.to_state,
            actor=row.actor or "",
            note=row.note or "",
            metadata_payload=row.metadata_payload or {},
            created_at=row.created_at,
        )
