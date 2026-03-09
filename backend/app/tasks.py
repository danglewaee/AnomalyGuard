from app.celery_app import celery_app
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
