import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.runtime import state
from app.schemas import AnomalyAlert, WaterReading
from app.services.metrics import ALERTS_GENERATED, READINGS_INGESTED
from app.services.stations import has_station
from app.services.store_pg import PostgresStore


def ensure_valid_station(station_id: str | None) -> None:
    if station_id is None:
        return
    if not has_station(station_id):
        raise HTTPException(status_code=404, detail=f"Unknown station_id: {station_id}")


def insert_reading_and_alert(db: Session, reading: WaterReading) -> AnomalyAlert | None:
    store = PostgresStore(db)
    store.add_reading(reading)
    READINGS_INGESTED.inc()

    result = state.detector_for(reading.station_id).score(reading)
    if not result.is_anomaly:
        return None

    explain_text = "Top factors: " + ", ".join([f"{key}={value:.2f}" for key, value in result.contributions.items()])
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
    ALERTS_GENERATED.inc()
    persisted_alert = store.alert_with_incident(alert.id) or alert
    state.kafka_publisher.publish_alert(persisted_alert.model_dump(mode="json"))
    return persisted_alert
