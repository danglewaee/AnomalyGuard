import asyncio
import json
import uuid
from contextlib import suppress
from datetime import datetime
from time import perf_counter
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.security import OAuth2PasswordRequestForm
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import settings
from app.db import Base, SessionLocal, engine, get_db
from app.dependencies import get_current_user, require_admin
from app.schemas import AnomalyAlert, StationProfile, WaterReading
from app.services.auth import create_access_token, get_password_hash, verify_password
from app.services.detector import HybridAnomalyDetector
from app.services.kafka_publisher import AlertKafkaPublisher
from app.services.metrics import ALERTS_GENERATED, INGEST_DURATION, READINGS_INGESTED
from app.services.mlflow_logger import log_ingest_metrics
from app.services.simulator import WaterReadingSimulator
from app.services.stations import default_station_id, has_station, list_stations, register_station
from app.services.store_pg import PostgresStore

app = FastAPI(title=settings.app_name, version=settings.app_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AppState:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.simulator = WaterReadingSimulator()
        self.detectors: dict[str, HybridAnomalyDetector] = {}
        self.stream_task: asyncio.Task | None = None
        self.poll_interval_seconds = settings.poll_interval_seconds
        self.last_data_source = "simulated"
        self.last_ingest_note = ""
        self.kafka_publisher = AlertKafkaPublisher()
        self.admin_password_hash = get_password_hash(settings.admin_password)

    def detector_for(self, station_id: str) -> HybridAnomalyDetector:
        if station_id not in self.detectors:
            self.detectors[station_id] = HybridAnomalyDetector()
        return self.detectors[station_id]


state = AppState()


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


async def broadcast(event: str, payload: dict) -> None:
    dead_clients = []
    message = json.dumps({"event": event, "payload": payload}, default=str)
    for ws in list(state.clients):
        try:
            await ws.send_text(message)
        except Exception:
            dead_clients.append(ws)

    for ws in dead_clients:
        with suppress(KeyError):
            state.clients.remove(ws)


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
    state.kafka_publisher.publish_alert(alert.model_dump(mode="json"))
    return alert


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


def _persist_ingest_payload(payload: dict[str, Any]) -> tuple[dict, int, int]:
    station = payload["station"]
    register_station(StationProfile(**station))

    inserted = 0
    alerts = 0
    with SessionLocal() as db:
        for raw in payload["readings"]:
            reading = WaterReading(
                timestamp=datetime.fromisoformat(raw["timestamp"]),
                station_id=raw["station_id"],
                ph=raw["ph"],
                tds=raw["tds"],
                turbidity=raw["turbidity"],
                temperature_c=raw["temperature_c"],
                do_mg_l=raw["do_mg_l"],
                flow_l_min=raw["flow_l_min"],
            )
            inserted += 1
            if insert_reading_and_alert(db, reading) is not None:
                alerts += 1

    return station, inserted, alerts


@app.post("/api/ingest/vn")
async def ingest_vn(
    station_id: str = Query(default="mekong-can-tho"),
    days: int = Query(default=30, ge=1, le=92),
    user: dict = Depends(require_admin),
) -> dict:
    ensure_valid_station(station_id)
    t0 = perf_counter()
    task = celery_app.send_task("tasks.fetch_vn_data", args=[station_id, days])
    payload = task.get(timeout=120)

    station, inserted, alerts = await asyncio.to_thread(_persist_ingest_payload, payload)

    state.last_data_source = "api/open-meteo-vn"
    state.last_ingest_note = "Real VN hydro+temperature feed with derived quality proxies."
    INGEST_DURATION.observe(perf_counter() - t0)
    log_ingest_metrics("vn", inserted, alerts)

    await broadcast(
        "station_registered",
        {"station": station, "inserted_readings": inserted, "generated_alerts": alerts, "source": "api/open-meteo-vn"},
    )

    return {
        "status": "ok",
        "source": "api/open-meteo-vn",
        "requested_by": user.get("sub"),
        "station": station,
        "inserted_readings": inserted,
        "generated_alerts": alerts,
    }


@app.post("/api/ingest/usgs")
async def ingest_usgs(
    site_no: str = Query(..., min_length=4, max_length=16),
    hours: int = Query(default=24, ge=1, le=168),
    user: dict = Depends(require_admin),
) -> dict:
    t0 = perf_counter()
    task = celery_app.send_task("tasks.fetch_usgs_data", args=[site_no, hours])
    payload = task.get(timeout=120)

    station, inserted, alerts = await asyncio.to_thread(_persist_ingest_payload, payload)

    state.last_data_source = "api/usgs"
    state.last_ingest_note = "USGS site ingestion."
    INGEST_DURATION.observe(perf_counter() - t0)
    log_ingest_metrics("usgs", inserted, alerts)

    await broadcast(
        "station_registered",
        {"station": station, "inserted_readings": inserted, "generated_alerts": alerts, "source": "api/usgs"},
    )

    return {
        "status": "ok",
        "source": "api/usgs",
        "requested_by": user.get("sub"),
        "station": station,
        "inserted_readings": inserted,
        "generated_alerts": alerts,
    }


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
            bootstrap_meta = meta(db)
            bootstrap_readings = latest_readings(limit=120, station_id=None, since_minutes=120, db=db)
            bootstrap_alerts = latest_alerts(limit=40, station_id=None, since_minutes=240, db=db)

        await websocket.send_text(
            json.dumps(
                {
                    "event": "bootstrap",
                    "payload": {
                        "meta": bootstrap_meta,
                        "stations": stations(),
                        "readings": bootstrap_readings,
                        "alerts": bootstrap_alerts,
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
