from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import require_admin
from app.runtime import broadcast
from app.schemas import IncidentStatusUpdate
from app.services.store_pg import PostgresStore


router = APIRouter()


async def _set_incident_status(
    alert_id: str,
    status: str,
    payload: IncidentStatusUpdate,
    db: Session,
    user: dict,
) -> dict:
    updated = PostgresStore(db).set_incident_status(
        alert_id=alert_id,
        status=status,
        changed_by=user.get("sub", "admin"),
        note=payload.note.strip(),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    response = updated.model_dump(mode="json")
    await broadcast("incident_status", response)
    return response


@router.post("/api/incidents/{alert_id}/acknowledge")
async def acknowledge_incident(
    alert_id: str,
    payload: IncidentStatusUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> dict:
    return await _set_incident_status(alert_id, "acknowledged", payload, db, user)


@router.post("/api/incidents/{alert_id}/resolve")
async def resolve_incident(
    alert_id: str,
    payload: IncidentStatusUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> dict:
    return await _set_incident_status(alert_id, "resolved", payload, db, user)


@router.post("/api/incidents/{alert_id}/reopen")
async def reopen_incident(
    alert_id: str,
    payload: IncidentStatusUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> dict:
    return await _set_incident_status(alert_id, "open", payload, db, user)
