from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import require_admin, require_device_key
from app.runtime import broadcast, state
from app.schemas import DeviceControlState, DeviceTelemetry, StationProfile
from app.services.alert_pipeline import insert_reading_and_alert
from app.services.device_support import build_device_station_profile, build_device_telemetry_snapshot, telemetry_to_reading
from app.services.stations import get_station, has_station, list_stations, register_station
from app.services.store_pg import PostgresStore


router = APIRouter()


@router.get("/api/device/status")
def device_statuses(station_id: str | None = Query(default=None), db: Session = Depends(get_db)) -> list[dict]:
    return PostgresStore(db).latest_device_states(station_id=station_id)


@router.get("/api/device/control/{station_id}")
def get_device_control(station_id: str, db: Session = Depends(get_db), _: None = Depends(require_device_key)) -> dict:
    return {"station_id": station_id, "control": PostgresStore(db).device_control_state(station_id)}


@router.put("/api/device/control/{station_id}")
async def set_device_control(
    station_id: str,
    payload: DeviceControlState,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> dict:
    if has_station(station_id):
        profile = get_station(station_id)
    else:
        profile = register_station(
            StationProfile(
                station_id=station_id,
                station_name=f"Device {station_id}",
                region="Edge device station",
                timezone="Asia/Ho_Chi_Minh",
                latitude=10.8231,
                longitude=106.6297,
                source="device",
            )
        )

    state_payload = PostgresStore(db).set_device_control(profile, payload.model_dump(mode="json"))
    await broadcast("device_control", state_payload)
    return {"status": "ok", "station_id": station_id, "control": state_payload["control"], "requested_by": user.get("sub")}


@router.post("/api/device/telemetry")
async def ingest_device_telemetry(
    payload: DeviceTelemetry,
    db: Session = Depends(get_db),
    _: None = Depends(require_device_key),
) -> dict:
    profile = build_device_station_profile(payload)
    known_station = has_station(profile.station_id)
    register_station(profile)
    payload.station_id = profile.station_id

    store = PostgresStore(db)
    control_state = store.device_control_state(profile.station_id)
    reading, derived = telemetry_to_reading(payload, control_state)
    telemetry_snapshot = build_device_telemetry_snapshot(payload, control_state, reading, derived)

    state_payload = store.upsert_device_state(
        profile=profile,
        telemetry=telemetry_snapshot,
        control=control_state,
        reading_preview=reading.model_dump(mode="json"),
        last_seen_at=reading.timestamp,
    )

    alert = insert_reading_and_alert(db, reading)

    state.last_data_source = "device/esp32"
    state.last_ingest_note = "Live device telemetry with inferred proxies for missing turbidity, dissolved oxygen, or flow fields."

    await broadcast("device_status", state_payload)
    await broadcast("reading", reading.model_dump(mode="json"))
    if alert is not None:
        await broadcast("alert", alert.model_dump(mode="json"))
    if not known_station:
        await broadcast("stations_updated", {"stations": [station.model_dump(mode="json") for station in list_stations()]})

    return {
        "status": "ok",
        "station": profile.model_dump(mode="json"),
        "control": control_state,
        "telemetry": telemetry_snapshot,
        "reading": reading.model_dump(mode="json"),
        "generated_alert": alert.model_dump(mode="json") if alert is not None else None,
        "derived_fields": derived,
    }
