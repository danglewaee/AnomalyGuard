from app.db import SessionLocal
from app.celery_app import celery_app
from app.services.ingest_pipeline import run_usgs_ingest_pipeline, run_vn_ingest_pipeline
from app.services.store_pg import PostgresStore
from app.services.usgs_ingest import fetch_usgs_readings
from app.services.vn_openmeteo_ingest import fetch_vn_openmeteo_readings


@celery_app.task(name="tasks.fetch_vn_data")
def fetch_vn_data_task(station_id: str, days: int) -> dict:
    station, readings = fetch_vn_openmeteo_readings(station_id, days)
    return {"station": station.model_dump(mode="json"), "readings": [r.model_dump(mode="json") for r in readings]}


@celery_app.task(name="tasks.fetch_usgs_data")
def fetch_usgs_data_task(site_no: str, hours: int) -> dict:
    station, readings = fetch_usgs_readings(site_no, hours)
    return {"station": station.model_dump(mode="json"), "readings": [r.model_dump(mode="json") for r in readings]}


@celery_app.task(name="tasks.run_vn_ingest_job", bind=True)
def run_vn_ingest_job_task(self, station_id: str, days: int) -> dict:
    job_id = str(self.request.id)
    with SessionLocal() as db:
        PostgresStore(db).update_job_status(job_id, "running", error_message="")

    try:
        result = run_vn_ingest_pipeline(station_id, days)
    except Exception as exc:
        with SessionLocal() as db:
            PostgresStore(db).update_job_status(job_id, "failed", error_message=str(exc))
        raise

    with SessionLocal() as db:
        PostgresStore(db).update_job_status(job_id, "succeeded", result_payload=result, error_message="")
    return result


@celery_app.task(name="tasks.run_usgs_ingest_job", bind=True)
def run_usgs_ingest_job_task(self, site_no: str, hours: int) -> dict:
    job_id = str(self.request.id)
    with SessionLocal() as db:
        PostgresStore(db).update_job_status(job_id, "running", error_message="")

    try:
        result = run_usgs_ingest_pipeline(site_no, hours)
    except Exception as exc:
        with SessionLocal() as db:
            PostgresStore(db).update_job_status(job_id, "failed", error_message=str(exc))
        raise

    with SessionLocal() as db:
        PostgresStore(db).update_job_status(job_id, "succeeded", result_payload=result, error_message="")
    return result
