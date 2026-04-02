from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEPS_ROOT = BACKEND_ROOT / ".deps"
if DEPS_ROOT.exists() and str(DEPS_ROOT) not in sys.path:
    sys.path.insert(0, str(DEPS_ROOT))

from app.schemas import StationProfile, WaterReading
from app.services.detector import DetectionResult
from app.services.ingest_pipeline import _persist_reading_batch


UTC = timezone.utc


class _SessionContext:
    def __enter__(self) -> object:
        return object()

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class IngestPipelineTests(unittest.TestCase):
    def test_persist_batch_skips_existing_and_in_batch_duplicates(self) -> None:
        station = StationProfile(
            station_id="mekong-can-tho",
            station_name="Can Tho River Gate",
            region="Can Tho, Mekong Delta",
            timezone="UTC",
            latitude=10.0,
            longitude=105.0,
            source="api",
        )
        first_ts = datetime(2026, 4, 2, 0, 0, tzinfo=UTC)
        second_ts = datetime(2026, 4, 2, 1, 0, tzinfo=UTC)
        readings = [
            WaterReading(timestamp=first_ts, station_id=station.station_id, ph=7.1, tds=220.0, turbidity=2.0, temperature_c=28.0, do_mg_l=6.4, flow_l_min=10.0),
            WaterReading(timestamp=second_ts, station_id=station.station_id, ph=7.2, tds=221.0, turbidity=2.1, temperature_c=28.1, do_mg_l=6.3, flow_l_min=10.5),
            WaterReading(timestamp=second_ts, station_id=station.station_id, ph=7.2, tds=221.0, turbidity=2.1, temperature_c=28.1, do_mg_l=6.3, flow_l_min=10.5),
        ]

        added_timestamps: list[datetime] = []

        class FakeStore:
            def __init__(self, db: object) -> None:
                self.db = db

            def existing_reading_timestamps(self, station_id: str, timestamps: list[datetime]) -> set[datetime]:
                return {first_ts}

            def add_reading(self, reading: WaterReading) -> None:
                added_timestamps.append(reading.timestamp)

            def add_alert(self, reading, explanation_text: str = "") -> None:
                raise AssertionError("No alerts should be written in this duplicate-only test")

            def alert_with_incident(self, alert_id: str):
                return None

        detector = MagicMock()
        detector.score.return_value = DetectionResult(
            is_anomaly=False,
            score=0.0,
            severity="low",
            reasons=[],
            contributions={},
        )

        with patch("app.services.ingest_pipeline.SessionLocal", return_value=_SessionContext()), patch(
            "app.services.ingest_pipeline.PostgresStore",
            FakeStore,
        ), patch("app.services.ingest_pipeline.HybridAnomalyDetector", return_value=detector), patch(
            "app.services.ingest_pipeline.AlertKafkaPublisher"
        ), patch("app.services.ingest_pipeline.register_station"), patch(
            "app.services.ingest_pipeline.log_ingest_metrics"
        ) as log_metrics:
            result = _persist_reading_batch(
                station,
                readings,
                source="api/open-meteo-vn",
                ingest_note="test",
            )

        self.assertEqual(added_timestamps, [second_ts])
        self.assertEqual(result["inserted_readings"], 1)
        self.assertEqual(result["skipped_duplicates"], 2)
        self.assertEqual(result["generated_alerts"], 0)
        log_metrics.assert_called_once_with("api/open-meteo-vn", 1, 0, skipped_duplicates=2)

    def test_persist_batch_only_generates_alerts_for_new_readings(self) -> None:
        station = StationProfile(
            station_id="usgs-01646500",
            station_name="USGS Site",
            region="USGS Water Services",
            timezone="UTC",
            latitude=39.0,
            longitude=-77.0,
            source="api",
        )
        existing_ts = datetime(2026, 4, 2, 0, 0, tzinfo=UTC)
        new_ts = datetime(2026, 4, 2, 0, 15, tzinfo=UTC)
        readings = [
            WaterReading(timestamp=existing_ts, station_id=station.station_id, ph=7.0, tds=200.0, turbidity=1.5, temperature_c=18.0, do_mg_l=7.1, flow_l_min=100.0),
            WaterReading(timestamp=new_ts, station_id=station.station_id, ph=9.4, tds=540.0, turbidity=11.0, temperature_c=21.0, do_mg_l=3.2, flow_l_min=115.0),
        ]

        persisted_alert = None
        added_alert_ids: list[str] = []
        published_payloads: list[dict] = []

        class FakeStore:
            def __init__(self, db: object) -> None:
                self.db = db

            def existing_reading_timestamps(self, station_id: str, timestamps: list[datetime]) -> set[datetime]:
                return {existing_ts}

            def add_reading(self, reading: WaterReading) -> None:
                return None

            def add_alert(self, alert, explanation_text: str = "") -> None:
                nonlocal persisted_alert
                added_alert_ids.append(alert.id)
                persisted_alert = alert

            def alert_with_incident(self, alert_id: str):
                return persisted_alert

        detector = MagicMock()
        detector.score.return_value = DetectionResult(
            is_anomaly=True,
            score=0.83,
            severity="high",
            reasons=["ph outside safe range"],
            contributions={"ph": 2.4},
        )
        publisher = MagicMock()
        publisher.publish_alert.side_effect = lambda payload: published_payloads.append(payload)

        with patch("app.services.ingest_pipeline.SessionLocal", return_value=_SessionContext()), patch(
            "app.services.ingest_pipeline.PostgresStore",
            FakeStore,
        ), patch("app.services.ingest_pipeline.HybridAnomalyDetector", return_value=detector), patch(
            "app.services.ingest_pipeline.AlertKafkaPublisher",
            return_value=publisher,
        ), patch("app.services.ingest_pipeline.register_station"), patch(
            "app.services.ingest_pipeline.log_ingest_metrics"
        ):
            result = _persist_reading_batch(
                station,
                readings,
                source="api/usgs",
                ingest_note="test",
            )

        self.assertEqual(result["inserted_readings"], 1)
        self.assertEqual(result["skipped_duplicates"], 1)
        self.assertEqual(result["generated_alerts"], 1)
        self.assertEqual(len(added_alert_ids), 1)
        self.assertEqual(len(published_payloads), 1)
