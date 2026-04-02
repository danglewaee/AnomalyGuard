import uuid
from datetime import datetime
from typing import Any

from app.db import SessionLocal
from app.schemas import AnomalyAlert, StationProfile, WaterReading
from app.services.detector import HybridAnomalyDetector
from app.services.kafka_publisher import AlertKafkaPublisher
from app.services.mlflow_logger import log_ingest_metrics
from app.services.stations import register_station
from app.services.store_pg import PostgresStore
from app.services.usgs_ingest import fetch_usgs_readings
from app.services.vn_openmeteo_ingest import fetch_vn_openmeteo_readings


def _reading_from_payload(raw: dict[str, Any]) -> WaterReading:
    return WaterReading(
        timestamp=datetime.fromisoformat(raw["timestamp"]),
        station_id=raw["station_id"],
        ph=raw["ph"],
        tds=raw["tds"],
        turbidity=raw["turbidity"],
        temperature_c=raw["temperature_c"],
        do_mg_l=raw["do_mg_l"],
        flow_l_min=raw["flow_l_min"],
    )


def _persist_reading_batch(
    station: StationProfile,
    readings: list[WaterReading],
    *,
    source: str,
    ingest_note: str,
) -> dict[str, Any]:
    register_station(station)
    detector = HybridAnomalyDetector()
    publisher = AlertKafkaPublisher()
    inserted = 0
    skipped_duplicates = 0
    alerts = 0

    with SessionLocal() as db:
        store = PostgresStore(db)
        existing_timestamps = store.existing_reading_timestamps(
            station.station_id,
            [reading.timestamp for reading in readings],
        )
        seen_timestamps = set(existing_timestamps)
        for reading in readings:
            if reading.timestamp in seen_timestamps:
                skipped_duplicates += 1
                continue

            store.add_reading(reading)
            inserted += 1
            seen_timestamps.add(reading.timestamp)

            result = detector.score(reading)
            if not result.is_anomaly:
                continue

            explain_text = "Top factors: " + ", ".join([f"{k}={v:.2f}" for k, v in result.contributions.items()])
            alert = AnomalyAlert(
                id=str(uuid.uuid4()),
                timestamp=reading.timestamp,
                station_id=reading.station_id,
                severity=result.severity,
                score=result.score,
                reasons=result.reasons,
                feature_contributions=result.contributions,
            )
            store.add_alert(alert, explanation_text=explain_text)
            persisted_alert = store.alert_with_incident(alert.id) or alert
            publisher.publish_alert(persisted_alert.model_dump(mode="json"))
            alerts += 1

    log_ingest_metrics(source, inserted, alerts, skipped_duplicates=skipped_duplicates)
    return {
        "source": source,
        "ingest_note": ingest_note,
        "station": station.model_dump(mode="json"),
        "inserted_readings": inserted,
        "skipped_duplicates": skipped_duplicates,
        "generated_alerts": alerts,
    }


def run_vn_ingest_pipeline(station_id: str, days: int) -> dict[str, Any]:
    station, readings = fetch_vn_openmeteo_readings(station_id, days)
    return _persist_reading_batch(
        station,
        readings,
        source="api/open-meteo-vn",
        ingest_note="Real VN hydro+temperature feed with derived quality proxies.",
    )


def run_usgs_ingest_pipeline(site_no: str, hours: int) -> dict[str, Any]:
    station, readings = fetch_usgs_readings(site_no, hours)
    return _persist_reading_batch(
        station,
        readings,
        source="api/usgs",
        ingest_note="USGS site ingestion.",
    )
