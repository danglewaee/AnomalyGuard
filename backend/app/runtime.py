import json
from contextlib import suppress

from fastapi import WebSocket

from app.config import settings
from app.services.auth import get_password_hash
from app.services.detector import HybridAnomalyDetector
from app.services.kafka_publisher import AlertKafkaPublisher
from app.services.simulator import WaterReadingSimulator


class AppState:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.simulator = WaterReadingSimulator()
        self.detectors: dict[str, HybridAnomalyDetector] = {}
        self.stream_task = None
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
