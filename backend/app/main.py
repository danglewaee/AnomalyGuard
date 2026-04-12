import asyncio
import json
from contextlib import suppress

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.security import OAuth2PasswordRequestForm
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy.orm import Session

from app.api.routes.alerts import router as alerts_router
from app.api.routes.community import router as community_router
from app.api.routes.device import router as device_router
from app.api.routes.forecasts import router as forecasts_router
from app.api.routes.ingest import router as ingest_router
from app.api.routes.incidents import router as incidents_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.model_registry import router as model_registry_router
from app.config import settings
from app.db import SessionLocal, engine, get_db
from app.dependencies import require_admin
from app.runtime import broadcast, state
from app.schemas import WaterReading
from app.services.auth import create_access_token, verify_password
from app.services.alert_pipeline import ensure_valid_station, insert_reading_and_alert
from app.services.schema_management import assert_schema_ready, get_schema_revision
from app.services.stations import default_station_id, list_stations
from app.services.store_pg import PostgresStore

app = FastAPI(title=settings.app_name, version=settings.app_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_origin_regex=settings.cors_allow_origin_regex or None,
    allow_credentials=bool(settings.cors_allowed_origins or settings.cors_allow_origin_regex),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(jobs_router)
app.include_router(model_registry_router)
app.include_router(community_router)
app.include_router(incidents_router)
app.include_router(alerts_router)
app.include_router(device_router)
app.include_router(forecasts_router)
app.include_router(ingest_router)


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
    assert_schema_ready(engine)
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
    with SessionLocal() as db:
        schema_revision = get_schema_revision(db)
    return {
        "status": "ok",
        "environment": settings.app_env,
        "stream_running": state.stream_task is not None and not state.stream_task.done(),
        "data_source": state.last_data_source,
        "schema_revision": schema_revision,
        "stack": ["fastapi", "postgres", "timescaledb", "celery", "redis", "kafka", "mlflow", "prometheus"],
    }


@app.get("/api/meta")
def meta(db: Session = Depends(get_db)) -> dict:
    store = PostgresStore(db)
    return {
        "data_source": state.last_data_source,
        "last_ingest_note": state.last_ingest_note,
        "schema_revision": get_schema_revision(db),
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


def build_ws_bootstrap_payload(db: Session) -> dict:
    store = PostgresStore(db)
    return {
        "meta": meta(db),
        "stations": stations(),
        "readings": [reading.model_dump(mode="json") for reading in store.latest_readings(limit=120, station_id=None, since_minutes=120)],
        "alerts": [alert.model_dump(mode="json") for alert in store.latest_alerts(limit=40, station_id=None, since_minutes=240)],
        "device_statuses": store.latest_device_states(),
    }


@app.websocket("/ws/stream")
async def ws_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    state.clients.add(websocket)

    try:
        with SessionLocal() as db:
            bootstrap_payload = build_ws_bootstrap_payload(db)

        await websocket.send_text(
            json.dumps(
                {
                    "event": "bootstrap",
                    "payload": bootstrap_payload,
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
