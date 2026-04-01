import uuid
from time import perf_counter

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.db import get_db
from app.dependencies import require_admin
from app.services.alert_pipeline import ensure_valid_station
from app.services.metrics import INGEST_DURATION
from app.services.store_pg import PostgresStore


router = APIRouter()


@router.post("/api/ingest/vn")
async def ingest_vn(
    station_id: str = Query(default="mekong-can-tho"),
    days: int = Query(default=30, ge=1, le=92),
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> dict:
    ensure_valid_station(station_id)
    t0 = perf_counter()
    job_id = str(uuid.uuid4())
    store = PostgresStore(db)
    job = store.create_job(
        job_id=job_id,
        job_type="ingest_vn",
        requested_by=user.get("sub", "admin"),
        parameters={"station_id": station_id, "days": days},
    )

    try:
        celery_app.send_task("tasks.run_vn_ingest_job", args=[station_id, days], task_id=job_id)
    except Exception as exc:
        job = store.update_job_status(job_id, "failed", error_message=str(exc)) or job

    INGEST_DURATION.observe(perf_counter() - t0)
    return job.model_dump(mode="json")


@router.post("/api/ingest/usgs")
async def ingest_usgs(
    site_no: str = Query(..., min_length=4, max_length=16),
    hours: int = Query(default=24, ge=1, le=168),
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> dict:
    t0 = perf_counter()
    job_id = str(uuid.uuid4())
    store = PostgresStore(db)
    job = store.create_job(
        job_id=job_id,
        job_type="ingest_usgs",
        requested_by=user.get("sub", "admin"),
        parameters={"site_no": site_no, "hours": hours},
    )

    try:
        celery_app.send_task("tasks.run_usgs_ingest_job", args=[site_no, hours], task_id=job_id)
    except Exception as exc:
        job = store.update_job_status(job_id, "failed", error_message=str(exc)) or job

    INGEST_DURATION.observe(perf_counter() - t0)
    return job.model_dump(mode="json")
