import asyncio
import json
import uuid
from contextlib import suppress
from time import perf_counter

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.security import OAuth2PasswordRequestForm
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.routes.community import router as community_router
from app.api.routes.incidents import router as incidents_router
from app.api.routes.jobs import router as jobs_router
from app.celery_app import celery_app
from app.config import settings
from app.db import Base, SessionLocal, engine, get_db
from app.dependencies import get_current_user, require_admin, require_device_key
from app.runtime import broadcast, state
from app.schemas import (
    AnomalyAlert,
    DeviceControlState,
    DeviceTelemetry,
    StationProfile,
    WaterReading,
)
from app.services.auth import create_access_token, verify_password
from app.services.device_support import build_device_station_profile, build_device_telemetry_snapshot, telemetry_to_reading
from app.services.metrics import ALERTS_GENERATED, INGEST_DURATION, READINGS_INGESTED
from app.services.stations import default_station_id, get_station, has_station, list_stations, register_station
from app.services.store_pg import PostgresStore

app = FastAPI(title=settings.app_name, version=settings.app_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(jobs_router)
app.include_router(community_router)
app.include_router(incidents_router)


def ensure_valid_station(station_id: str | None) -> None:
    if station_id is None:
        return
    if not has_station(station_id):
        raise HTTPException(status_code=404, detail=f"Unknown station_id: {station_id}")


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
            conn.execute(text("SELECT create_hypertable('readings', 'timestamp', if_not_exists => TRUE)"))
        except Exception:
            pass


def insert_reading_and_alert(db: Session, reading: WaterReading) -> AnomalyAlert | None:
    store = PostgresStore(db)
    store.add_reading(reading)
    READINGS_INGESTED.inc()

    result = state.detector_for(reading.station_id).score(reading)
    if not result.is_anomaly:
        return None

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
    ALERTS_GENERATED.inc()
    persisted_alert = store.alert_with_incident(alert.id) or alert
    state.kafka_publisher.publish_alert(persisted_alert.model_dump(mode="json"))
    return persisted_alert


async def stream_loop() -> None:
    while True:
        if settings.enable_simulator:
            station_ids = [s.station_id for s in list_stations() if s.source == "simulated"]
            for station_id in station_ids:
                reading = state.simulator.next(station_id)
                with SessionLocal() as db:
                    alert = insert_reading_and_alert(db, reading)
                await broadcast("reading", reading.model_dump(mode="json"))
                if alert is not None:
                    await broadcast("alert", alert.model_dump(mode="json"))

        await asyncio.sleep(state.poll_interval_seconds)


@app.on_event("startup")
async def startup() -> None:
    init_db()
    if state.stream_task is None or state.stream_task.done():
        state.stream_task = asyncio.create_task(stream_loop())


@app.on_event("shutdown")
async def shutdown() -> None:
    if state.stream_task:
        state.stream_task.cancel()
        with suppress(asyncio.CancelledError):
            await state.stream_task


@app.get("/metrics", response_class=PlainTextResponse)
def metrics_endpoint() -> PlainTextResponse:
    return PlainTextResponse(generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST)


@app.post("/api/auth/token")
def login(form_data: OAuth2PasswordRequestForm = Depends()) -> dict:
    if form_data.username != settings.admin_username:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(form_data.password, state.admin_password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token(subject=form_data.username, role="admin")
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "stream_running": state.stream_task is not None and not state.stream_task.done(),
        "data_source": state.last_data_source,
        "stack": ["fastapi", "postgres", "timescaledb", "celery", "redis", "kafka", "mlflow", "prometheus"],
    }


@app.get("/api/meta")
def meta(db: Session = Depends(get_db)) -> dict:
    store = PostgresStore(db)
    return {
        "data_source": state.last_data_source,
        "last_ingest_note": state.last_ingest_note,
        "timezone": "UTC timestamps from backend; station timezone provided per station",
        "default_station_id": default_station_id(),
        "counts": store.counts(),
    }


@app.get("/api/stations")
def stations() -> list[dict]:
    return [s.model_dump(mode="json") for s in list_stations()]


@app.get("/api/readings/latest")
def latest_readings(
    limit: int = Query(default=100, ge=1, le=2000),
    station_id: str | None = Query(default=None),
    since_minutes: int | None = Query(default=60, ge=1, le=10080),
    db: Session = Depends(get_db),
) -> list[dict]:
    ensure_valid_station(station_id)
    data = PostgresStore(db).latest_readings(limit=limit, station_id=station_id, since_minutes=since_minutes)
    return [r.model_dump(mode="json") for r in data]


@app.get("/api/alerts/latest")
def latest_alerts(
    limit: int = Query(default=50, ge=1, le=1000),
    station_id: str | None = Query(default=None),
    since_minutes: int | None = Query(default=180, ge=1, le=10080),
    db: Session = Depends(get_db),
) -> list[dict]:
    ensure_valid_station(station_id)
    data = PostgresStore(db).latest_alerts(limit=limit, station_id=station_id, since_minutes=since_minutes)
    return [a.model_dump(mode="json") for a in data]


@app.get("/api/alerts/{alert_id}/explain")
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


@app.get("/api/device/status")
def device_statuses(station_id: str | None = Query(default=None), db: Session = Depends(get_db)) -> list[dict]:
    return PostgresStore(db).latest_device_states(station_id=station_id)


@app.get("/api/device/control/{station_id}")
def get_device_control(station_id: str, db: Session = Depends(get_db), _: None = Depends(require_device_key)) -> dict:
    return {"station_id": station_id, "control": PostgresStore(db).device_control_state(station_id)}


@app.put("/api/device/control/{station_id}")
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


@app.post("/api/device/telemetry")
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
        await broadcast("stations_updated", {"stations": stations()})

    return {
        "status": "ok",
        "station": profile.model_dump(mode="json"),
        "control": control_state,
        "telemetry": telemetry_snapshot,
        "reading": reading.model_dump(mode="json"),
        "generated_alert": alert.model_dump(mode="json") if alert is not None else None,
        "derived_fields": derived,
    }


@app.post("/api/ingest/vn")
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


@app.post("/api/ingest/usgs")
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


@app.post("/api/stream/start")
async def start_stream(user: dict = Depends(require_admin)) -> dict:
    if state.stream_task is None or state.stream_task.done():
        state.stream_task = asyncio.create_task(stream_loop())
    return {"stream_running": True, "requested_by": user.get("sub")}


@app.post("/api/stream/stop")
async def stop_stream(user: dict = Depends(require_admin)) -> dict:
    if state.stream_task and not state.stream_task.done():
        state.stream_task.cancel()
        with suppress(asyncio.CancelledError):
            await state.stream_task
    return {"stream_running": False, "requested_by": user.get("sub")}


@app.websocket("/ws/stream")
async def ws_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    state.clients.add(websocket)

    try:
        with SessionLocal() as db:
            store = PostgresStore(db)
            bootstrap_meta = meta(db)
            bootstrap_readings = latest_readings(limit=120, station_id=None, since_minutes=120, db=db)
            bootstrap_alerts = latest_alerts(limit=40, station_id=None, since_minutes=240, db=db)
            bootstrap_device_statuses = store.latest_device_states()

        await websocket.send_text(
            json.dumps(
                {
                    "event": "bootstrap",
                    "payload": {
                        "meta": bootstrap_meta,
                        "stations": stations(),
                        "readings": bootstrap_readings,
                        "alerts": bootstrap_alerts,
                        "device_statuses": bootstrap_device_statuses,
                    },
                },
                default=str,
            )
        )

        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        with suppress(KeyError):
            state.clients.remove(websocket)
