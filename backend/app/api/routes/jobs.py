from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import require_admin
from app.runtime import state
from app.schemas import JobStatus, StationProfile
from app.services.stations import register_station
from app.services.store_pg import PostgresStore


router = APIRouter()


def _is_ingest_job(job_type: str) -> bool:
    return job_type.startswith("ingest_")


@router.get("/api/jobs/{job_id}", response_model=JobStatus)
def job_status(job_id: str, db: Session = Depends(get_db), _: dict = Depends(require_admin)) -> dict:
    job = PostgresStore(db).get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status == "succeeded" and job.result_payload and _is_ingest_job(job.job_type):
        station_payload = job.result_payload.get("station")
        if isinstance(station_payload, dict):
            try:
                register_station(StationProfile(**station_payload))
            except Exception:
                pass

        state.last_data_source = str(job.result_payload.get("source") or state.last_data_source)
        state.last_ingest_note = str(job.result_payload.get("ingest_note") or state.last_ingest_note)

    return job.model_dump(mode="json")
