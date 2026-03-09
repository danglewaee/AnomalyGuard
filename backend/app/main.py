import asyncio
import json
import uuid
from contextlib import suppress
from typing import Set

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import AnomalyAlert, WaterReading
from app.services.detector import HybridAnomalyDetector
from app.services.simulator import WaterReadingSimulator
from app.services.stations import default_station_id, get_station, has_station, list_stations, register_station
from app.services.storage import SQLiteStore
from app.services.usgs_ingest import fetch_usgs_readings
from app.services.vn_openmeteo_ingest import fetch_vn_openmeteo_readings

app = FastAPI(title="AnomalyGuard Water API", version="0.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AppState:
    def __init__(self) -> None:
        self.clients: Set[WebSocket] = set()
        self.simulator = WaterReadingSimulator()
        self.detectors: dict[str, HybridAnomalyDetector] = {}
        self.store = SQLiteStore()
        self.stream_task: asyncio.Task | None = None
        self.poll_interval_seconds = 1.0
        self.last_data_source = "simulated"
        self.last_ingest_note = ""

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


async def process_reading(reading: WaterReading, emit: bool) -> AnomalyAlert | None:
    state.store.add_reading(reading)
    if emit:
        await broadcast("reading", reading.model_dump(mode="json"))

    result = state.detector_for(reading.station_id).score(reading)
    if not result.is_anomaly:
        return None

    alert = AnomalyAlert(
        id=str(uuid.uuid4()),
        timestamp=reading.timestamp,
        station_id=reading.station_id,
        severity=result.severity,
        score=result.score,
        reasons=result.reasons,
        feature_contributions=result.contributions,
    )
    state.store.add_alert(alert)
    if emit:
        await broadcast("alert", alert.model_dump(mode="json"))
    return alert


async def stream_loop() -> None:
    while True:
        station_ids = [s.station_id for s in list_stations() if s.source == "simulated"]
        for station_id in station_ids:
            reading = state.simulator.next(station_id)
            await process_reading(reading, emit=True)

        await asyncio.sleep(state.poll_interval_seconds)


@app.on_event("startup")
async def startup() -> None:
    if state.stream_task is None or state.stream_task.done():
        state.stream_task = asyncio.create_task(stream_loop())


@app.on_event("shutdown")
async def shutdown() -> None:
    if state.stream_task:
        state.stream_task.cancel()
        with suppress(asyncio.CancelledError):
            await state.stream_task


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "stream_running": state.stream_task is not None and not state.stream_task.done(),
        "data_source": state.last_data_source,
    }


@app.get("/api/meta")
def meta() -> dict:
    return {
        "data_source": state.last_data_source,
        "last_ingest_note": state.last_ingest_note,
        "timezone": "UTC timestamps from backend; station timezone provided per station",
        "default_station_id": default_station_id(),
        "counts": state.store.counts(),
    }


@app.get("/api/stations")
def stations() -> list[dict]:
    return [s.model_dump(mode="json") for s in list_stations()]


@app.get("/api/readings/latest")
def latest_readings(
    limit: int = Query(default=100, ge=1, le=2000),
    station_id: str | None = Query(default=None),
    since_minutes: int | None = Query(default=60, ge=1, le=10080),
) -> list[dict]:
    ensure_valid_station(station_id)
    if station_id:
        get_station(station_id)
    data = state.store.latest_readings(limit=limit, station_id=station_id, since_minutes=since_minutes)
    return [r.model_dump(mode="json") for r in data]


@app.get("/api/alerts/latest")
def latest_alerts(
    limit: int = Query(default=50, ge=1, le=1000),
    station_id: str | None = Query(default=None),
    since_minutes: int | None = Query(default=180, ge=1, le=10080),
) -> list[dict]:
    ensure_valid_station(station_id)
    if station_id:
        get_station(station_id)
    data = state.store.latest_alerts(limit=limit, station_id=station_id, since_minutes=since_minutes)
    return [a.model_dump(mode="json") for a in data]


@app.post("/api/ingest/vn")
async def ingest_vn(
    station_id: str = Query(default="mekong-can-tho"),
    days: int = Query(default=30, ge=1, le=92),
) -> dict:
    ensure_valid_station(station_id)

    try:
        station, readings = await asyncio.to_thread(fetch_vn_openmeteo_readings, station_id, days)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"VN ingest failed: {exc}") from exc

    if not readings:
        raise HTTPException(status_code=404, detail="No readings returned for this VN station.")

    register_station(station)

    alert_count = 0
    for reading in readings:
        alert = await process_reading(reading, emit=False)
        if alert is not None:
            alert_count += 1

    state.last_data_source = "api/open-meteo-vn"
    state.last_ingest_note = "Real river discharge + temperature in VN; pH/TDS/turbidity/DO are derived proxies."

    await broadcast(
        "station_registered",
        {
            "station": station.model_dump(mode="json"),
            "inserted_readings": len(readings),
            "generated_alerts": alert_count,
            "source": "api/open-meteo-vn",
        },
    )

    return {
        "status": "ok",
        "source": "api/open-meteo-vn",
        "note": state.last_ingest_note,
        "station": station.model_dump(mode="json"),
        "inserted_readings": len(readings),
        "generated_alerts": alert_count,
    }


@app.post("/api/ingest/usgs")
async def ingest_usgs(
    site_no: str = Query(..., min_length=4, max_length=16),
    hours: int = Query(default=24, ge=1, le=168),
) -> dict:
    try:
        station, readings = await asyncio.to_thread(fetch_usgs_readings, site_no, hours)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"USGS ingest failed: {exc}") from exc

    if not readings:
        raise HTTPException(status_code=404, detail="No readings returned for this site.")

    register_station(station)

    alert_count = 0
    for reading in readings:
        alert = await process_reading(reading, emit=False)
        if alert is not None:
            alert_count += 1

    state.last_data_source = "api/usgs"
    state.last_ingest_note = "USGS site ingestion."

    await broadcast(
        "station_registered",
        {
            "station": station.model_dump(mode="json"),
            "inserted_readings": len(readings),
            "generated_alerts": alert_count,
            "source": "api/usgs",
        },
    )

    return {
        "status": "ok",
        "source": "api/usgs",
        "station": station.model_dump(mode="json"),
        "inserted_readings": len(readings),
        "generated_alerts": alert_count,
    }


@app.post("/api/stream/start")
async def start_stream() -> dict:
    if state.stream_task is None or state.stream_task.done():
        state.stream_task = asyncio.create_task(stream_loop())
    return {"stream_running": True}


@app.post("/api/stream/stop")
async def stop_stream() -> dict:
    if state.stream_task and not state.stream_task.done():
        state.stream_task.cancel()
        with suppress(asyncio.CancelledError):
            await state.stream_task
    return {"stream_running": False}


@app.websocket("/ws/stream")
async def ws_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    state.clients.add(websocket)

    try:
        await websocket.send_text(
            json.dumps(
                {
                    "event": "bootstrap",
                    "payload": {
                        "meta": meta(),
                        "stations": stations(),
                        "readings": latest_readings(limit=120, station_id=None, since_minutes=120),
                        "alerts": latest_alerts(limit=40, station_id=None, since_minutes=240),
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
