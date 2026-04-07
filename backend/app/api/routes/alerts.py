import csv
from datetime import datetime, timezone
from io import StringIO
import json
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user, require_admin
from app.runtime import broadcast
from app.schemas import (
    AlertHistoryEntry,
    AlertReviewUpdate,
    LabeledAlertExportResponse,
    JobStatus,
    RetrainingManifestResponse,
    RetrainingJobRequest,
    ReviewedAlertEvaluationResponse,
    ReviewedAlertPromotionGateResponse,
    ReviewedAlertReadinessResponse,
)
from app.services.alert_pipeline import ensure_valid_station
from app.services.reviewed_alert_evaluation import build_reviewed_alert_evaluation
from app.services.reviewed_alert_promotion_gate import build_reviewed_alert_promotion_gate
from app.services.reviewed_alert_readiness import build_reviewed_alert_readiness
from app.services.retraining_manifest import build_retraining_manifest
from app.celery_app import celery_app
from app.services.store_pg import PostgresStore


router = APIRouter()


def _serialize_labeled_alert_rows(alerts: list[dict]) -> str:
    buffer = StringIO()
    fieldnames = [
        "id",
        "timestamp",
        "station_id",
        "severity",
        "score",
        "reasons",
        "feature_contributions",
        "incident_status",
        "incident_note",
        "review_label",
        "review_note",
        "reviewed_at",
        "reviewed_by",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(alerts)
    return buffer.getvalue()


@router.get("/api/alerts/latest")
def latest_alerts(
    limit: int = Query(default=50, ge=1, le=1000),
    station_id: str | None = Query(default=None),
    since_minutes: int | None = Query(default=180, ge=1, le=10080),
    db: Session = Depends(get_db),
) -> list[dict]:
    ensure_valid_station(station_id)
    data = PostgresStore(db).latest_alerts(limit=limit, station_id=station_id, since_minutes=since_minutes)
    return [alert.model_dump(mode="json") for alert in data]


@router.post("/api/alerts/labeled/retraining-jobs", response_model=JobStatus)
def prepare_retraining_job(
    payload: RetrainingJobRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> dict:
    ensure_valid_station(payload.station_id)
    job_id = str(uuid4())
    job = PostgresStore(db).create_job(
        job_id=job_id,
        job_type="prepare_retraining_run",
        requested_by=user.get("sub", "admin"),
        parameters={
            "station_id": payload.station_id or "",
            "since_minutes": payload.since_minutes,
            "limit": payload.limit,
            "recent_count": payload.recent_count,
        },
    )
    try:
        celery_app.send_task(
            "tasks.prepare_reviewed_alert_training_job",
            args=[payload.station_id, payload.since_minutes, payload.limit, payload.recent_count],
            task_id=job_id,
        )
    except Exception as exc:
        failed = PostgresStore(db).update_job_status(job_id, "failed", error_message=str(exc))
        if failed is None:
            raise
        return failed.model_dump(mode="json")
    return job.model_dump(mode="json")


@router.get("/api/alerts/labeled/export", response_model=LabeledAlertExportResponse)
def export_labeled_alerts(
    format: Literal["json", "csv"] = Query(default="json"),
    label: Literal["true_anomaly", "false_positive"] | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    station_id: str | None = Query(default=None),
    since_minutes: int | None = Query(default=10080, ge=1, le=43200),
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    ensure_valid_station(station_id)
    alerts = PostgresStore(db).reviewed_alerts(
        limit=limit,
        label=label,
        station_id=station_id,
        since_minutes=since_minutes,
    )

    if format == "csv":
        rows = [
            {
                "id": alert.id,
                "timestamp": alert.timestamp.isoformat(),
                "station_id": alert.station_id,
                "severity": alert.severity,
                "score": alert.score,
                "reasons": json.dumps(alert.reasons or []),
                "feature_contributions": json.dumps(alert.feature_contributions or {}),
                "incident_status": alert.incident_status or "",
                "incident_note": alert.incident_note or "",
                "review_label": alert.review_label or "",
                "review_note": alert.review_note or "",
                "reviewed_at": alert.reviewed_at.isoformat() if alert.reviewed_at else "",
                "reviewed_by": alert.reviewed_by or "",
            }
            for alert in alerts
        ]
        filename = f"anomalyguard-labeled-alerts-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.csv"
        return PlainTextResponse(
            _serialize_labeled_alert_rows(rows),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return {
        "exported_at": datetime.now(timezone.utc),
        "count": len(alerts),
        "label_filter": label,
        "station_id": station_id,
        "since_minutes": since_minutes,
        "items": [alert.model_dump(mode="json") for alert in alerts],
    }


@router.get("/api/alerts/labeled/manifest", response_model=RetrainingManifestResponse)
def retraining_manifest(
    label: Literal["true_anomaly", "false_positive"] | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    station_id: str | None = Query(default=None),
    since_minutes: int | None = Query(default=10080, ge=1, le=43200),
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict:
    ensure_valid_station(station_id)
    alerts = PostgresStore(db).reviewed_alerts(
        limit=limit,
        label=label,
        station_id=station_id,
        since_minutes=since_minutes,
    )
    manifest = build_retraining_manifest(
        alerts=alerts,
        label=label,
        station_id=station_id,
        since_minutes=since_minutes,
        limit=limit,
    )
    return manifest.model_dump(mode="json")


@router.get("/api/alerts/labeled/evaluation", response_model=ReviewedAlertEvaluationResponse)
def reviewed_alert_evaluation(
    limit: int = Query(default=500, ge=1, le=5000),
    station_id: str | None = Query(default=None),
    since_minutes: int | None = Query(default=10080, ge=1, le=43200),
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict:
    ensure_valid_station(station_id)
    alerts = PostgresStore(db).reviewed_alerts(
        limit=limit,
        station_id=station_id,
        since_minutes=since_minutes,
    )
    evaluation = build_reviewed_alert_evaluation(
        alerts=alerts,
        station_id=station_id,
        since_minutes=since_minutes,
    )
    return evaluation.model_dump(mode="json")


@router.get("/api/alerts/labeled/readiness", response_model=ReviewedAlertReadinessResponse)
def reviewed_alert_readiness(
    limit: int = Query(default=500, ge=1, le=5000),
    recent_count: int = Query(default=50, ge=1, le=500),
    station_id: str | None = Query(default=None),
    since_minutes: int | None = Query(default=10080, ge=1, le=43200),
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict:
    ensure_valid_station(station_id)
    alerts = PostgresStore(db).reviewed_alerts(
        limit=limit,
        station_id=station_id,
        since_minutes=since_minutes,
    )
    readiness = build_reviewed_alert_readiness(
        alerts=alerts,
        station_id=station_id,
        since_minutes=since_minutes,
        limit=limit,
        recent_count=recent_count,
    )
    return readiness.model_dump(mode="json")


@router.get("/api/alerts/labeled/promotion-gate", response_model=ReviewedAlertPromotionGateResponse)
def reviewed_alert_promotion_gate(
    limit: int = Query(default=500, ge=1, le=5000),
    recent_count: int = Query(default=50, ge=1, le=500),
    station_id: str | None = Query(default=None),
    since_minutes: int | None = Query(default=10080, ge=1, le=43200),
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict:
    ensure_valid_station(station_id)
    alerts = PostgresStore(db).reviewed_alerts(
        limit=limit,
        station_id=station_id,
        since_minutes=since_minutes,
    )
    manifest = build_retraining_manifest(
        alerts=alerts,
        label=None,
        station_id=station_id,
        since_minutes=since_minutes,
        limit=limit,
    )
    evaluation = build_reviewed_alert_evaluation(
        alerts=alerts,
        station_id=station_id,
        since_minutes=since_minutes,
    )
    readiness = build_reviewed_alert_readiness(
        alerts=alerts,
        station_id=station_id,
        since_minutes=since_minutes,
        limit=limit,
        recent_count=recent_count,
    )
    gate = build_reviewed_alert_promotion_gate(
        manifest=manifest,
        evaluation=evaluation,
        readiness=readiness,
    )
    return gate.model_dump(mode="json")


@router.get("/api/alerts/{alert_id}/history", response_model=list[AlertHistoryEntry])
def alert_history(
    alert_id: str,
    limit: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
) -> list[dict]:
    store = PostgresStore(db)
    if store.alert_with_incident(alert_id) is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    history = store.alert_history(alert_id, limit=limit)
    return [entry.model_dump(mode="json") for entry in history]


@router.get("/api/alerts/{alert_id}/explain")
def explain_alert(alert_id: str, db: Session = Depends(get_db), user: dict = Depends(get_current_user)) -> dict:
    row = PostgresStore(db).get_alert(alert_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {
        "id": row.id,
        "timestamp": row.timestamp,
        "station_id": row.station_id,
        "score": row.score,
        "severity": row.severity,
        "reasons": row.reasons,
        "feature_contributions": row.feature_contributions,
        "explanation": row.explanation_text,
        "requested_by": user.get("sub"),
    }


@router.post("/api/alerts/{alert_id}/review")
async def review_alert(
    alert_id: str,
    payload: AlertReviewUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> dict:
    updated = PostgresStore(db).set_alert_review(
        alert_id=alert_id,
        label=payload.label,
        reviewed_by=user.get("sub", "admin"),
        note=payload.note.strip(),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    response = updated.model_dump(mode="json")
    await broadcast("alert_review", response)
    return response
