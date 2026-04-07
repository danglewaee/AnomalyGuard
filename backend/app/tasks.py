from app.db import SessionLocal
from app.celery_app import celery_app
from app.services.ingest_pipeline import run_usgs_ingest_pipeline, run_vn_ingest_pipeline
from app.services.model_registry import register_retraining_candidate
from app.services.reviewed_alert_training_run import build_reviewed_alert_training_run
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


@celery_app.task(name="tasks.prepare_reviewed_alert_training_job", bind=True)
def prepare_reviewed_alert_training_job_task(
    self,
    station_id: str | None,
    since_minutes: int | None,
    limit: int,
    recent_count: int,
) -> dict:
    job_id = str(self.request.id)
    with SessionLocal() as db:
        PostgresStore(db).update_job_status(job_id, "running", error_message="")

    try:
        with SessionLocal() as db:
            alerts = PostgresStore(db).reviewed_alerts(
                limit=limit,
                station_id=station_id,
                since_minutes=since_minutes,
            )
        result = build_reviewed_alert_training_run(
            alerts=alerts,
            station_id=station_id,
            since_minutes=since_minutes,
            limit=limit,
            recent_count=recent_count,
        )
    except Exception as exc:
        with SessionLocal() as db:
            PostgresStore(db).update_job_status(job_id, "failed", error_message=str(exc))
        raise

    with SessionLocal() as db:
        store = PostgresStore(db)
        existing_job = store.get_job(job_id)
        requested_by = existing_job.requested_by if existing_job is not None else "system"
        registry_entry = register_retraining_candidate(
            store,
            job_id=job_id,
            actor=requested_by,
            bundle=result,
        )
        result["registry_entry"] = registry_entry.model_dump(mode="json")
        store.update_job_status(job_id, "succeeded", result_payload=result, error_message="")
    return result
