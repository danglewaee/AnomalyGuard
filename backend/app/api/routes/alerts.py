from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user, require_admin
from app.runtime import broadcast
from app.schemas import AlertReviewUpdate
from app.services.alert_pipeline import ensure_valid_station
from app.services.store_pg import PostgresStore


router = APIRouter()


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
