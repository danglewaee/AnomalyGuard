from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEPS_ROOT = BACKEND_ROOT / ".deps"
if DEPS_ROOT.exists() and str(DEPS_ROOT) not in sys.path:
    sys.path.insert(0, str(DEPS_ROOT))

import httpx

from app.api.routes import community as community_routes
from app.api.routes import incidents as incident_routes
from app.api.routes import jobs as jobs_routes
import app.main as main
from app.schemas import AnomalyAlert, JobStatus, StationProfile, WaterReading


UTC = timezone.utc


class ApiContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        main.state.last_data_source = "simulated"
        main.state.last_ingest_note = ""
        main.app.dependency_overrides[main.get_db] = lambda: object()
        main.app.dependency_overrides[main.require_admin] = lambda: {"sub": "test-admin", "role": "admin"}
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        main.app.dependency_overrides.clear()

    async def test_ingest_vn_returns_queued_job_and_enqueues_background_task(self) -> None:
        created_jobs: list[dict] = []

        class FakeStore:
            def __init__(self, db: object) -> None:
                self.db = db

            def create_job(self, job_id: str, job_type: str, requested_by: str, parameters: dict | None = None) -> JobStatus:
                created_jobs.append(
                    {
                        "job_id": job_id,
                        "job_type": job_type,
                        "requested_by": requested_by,
                        "parameters": parameters or {},
                    }
                )
                now = datetime.now(UTC)
                return JobStatus(
                    id=job_id,
                    job_type=job_type,
                    status="queued",
                    requested_by=requested_by,
                    created_at=now,
                    updated_at=now,
                    parameters=parameters or {},
                )

            def update_job_status(self, *args: object, **kwargs: object) -> JobStatus | None:
                raise AssertionError("update_job_status should not be called on a successful enqueue")

        send_task = MagicMock()

        with patch.object(main, "PostgresStore", FakeStore), patch.object(main.celery_app, "send_task", send_task):
            response = await self.client.post(
                "/api/ingest/vn",
                params={"station_id": "mekong-can-tho", "days": 7},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["job_type"], "ingest_vn")
        self.assertEqual(payload["parameters"], {"station_id": "mekong-can-tho", "days": 7})
        self.assertEqual(created_jobs[0]["requested_by"], "test-admin")

        send_task.assert_called_once()
        self.assertEqual(send_task.call_args.args[0], "tasks.run_vn_ingest_job")
        self.assertEqual(send_task.call_args.kwargs["args"], ["mekong-can-tho", 7])
        self.assertEqual(send_task.call_args.kwargs["task_id"], payload["id"])

    async def test_ingest_vn_returns_failed_job_when_enqueue_raises(self) -> None:
        class FakeStore:
            def __init__(self, db: object) -> None:
                self.db = db

            def create_job(self, job_id: str, job_type: str, requested_by: str, parameters: dict | None = None) -> JobStatus:
                now = datetime.now(UTC)
                return JobStatus(
                    id=job_id,
                    job_type=job_type,
                    status="queued",
                    requested_by=requested_by,
                    created_at=now,
                    updated_at=now,
                    parameters=parameters or {},
                )

            def update_job_status(
                self,
                job_id: str,
                status: str,
                *,
                result_payload: dict | None = None,
                error_message: str | None = None,
            ) -> JobStatus:
                now = datetime.now(UTC)
                return JobStatus(
                    id=job_id,
                    job_type="ingest_vn",
                    status=status,
                    requested_by="test-admin",
                    created_at=now,
                    updated_at=now,
                    completed_at=now,
                    parameters={"station_id": "mekong-can-tho", "days": 3},
                    result_payload=result_payload or {},
                    error_message=error_message or "",
                )

        with patch.object(main, "PostgresStore", FakeStore), patch.object(
            main.celery_app,
            "send_task",
            side_effect=RuntimeError("broker unavailable"),
        ):
            response = await self.client.post(
                "/api/ingest/vn",
                params={"station_id": "mekong-can-tho", "days": 3},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "failed")
        self.assertIn("broker unavailable", payload["error_message"])

    async def test_job_status_updates_runtime_metadata_from_successful_result(self) -> None:
        now = datetime.now(UTC)
        station_payload = {
            "station_id": "delta-01",
            "station_name": "Delta Intake",
            "region": "River District",
            "timezone": "UTC",
            "latitude": 10.25,
            "longitude": 105.12,
            "source": "api",
        }
        completed_job = JobStatus(
            id="job-success",
            job_type="ingest_vn",
            status="succeeded",
            requested_by="test-admin",
            created_at=now - timedelta(minutes=1),
            updated_at=now,
            started_at=now - timedelta(minutes=1),
            completed_at=now,
            parameters={"station_id": "mekong-can-tho", "days": 2},
            result_payload={
                "source": "vn/open-meteo",
                "ingest_note": "Imported 48 readings",
                "station": station_payload,
            },
        )

        class FakeStore:
            def __init__(self, db: object) -> None:
                self.db = db

            def get_job(self, job_id: str) -> JobStatus | None:
                return completed_job if job_id == completed_job.id else None

        with patch.object(jobs_routes, "PostgresStore", FakeStore), patch.object(
            jobs_routes,
            "register_station",
        ) as register_station:
            response = await self.client.get(f"/api/jobs/{completed_job.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(main.state.last_data_source, "vn/open-meteo")
        self.assertEqual(main.state.last_ingest_note, "Imported 48 readings")
        register_station.assert_called_once()
        self.assertEqual(register_station.call_args.args[0].station_id, "delta-01")

    async def test_acknowledge_incident_returns_updated_alert_and_broadcasts(self) -> None:
        now = datetime.now(UTC)
        updated_alert = AnomalyAlert(
            id="alert-123",
            timestamp=now - timedelta(minutes=5),
            station_id="mekong-can-tho",
            severity="medium",
            score=0.61,
            reasons=["turbidity outside safe range"],
            feature_contributions={"turbidity": 1.8},
            incident_status="acknowledged",
            incident_note="Operator investigating",
            incident_updated_at=now,
        )
        status_updates: list[dict] = []
        broadcast = AsyncMock()

        class FakeStore:
            def __init__(self, db: object) -> None:
                self.db = db

            def set_incident_status(self, alert_id: str, status: str, changed_by: str, note: str = "") -> AnomalyAlert:
                status_updates.append(
                    {
                        "alert_id": alert_id,
                        "status": status,
                        "changed_by": changed_by,
                        "note": note,
                    }
                )
                return updated_alert

        with patch.object(incident_routes, "PostgresStore", FakeStore), patch.object(
            incident_routes,
            "broadcast",
            broadcast,
        ):
            response = await self.client.post(
                "/api/incidents/alert-123/acknowledge",
                json={"note": "Operator investigating"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["incident_status"], "acknowledged")
        self.assertEqual(status_updates[0]["status"], "acknowledged")
        self.assertEqual(status_updates[0]["changed_by"], "test-admin")
        broadcast.assert_awaited_once()
        self.assertEqual(broadcast.await_args.args[0], "incident_status")

    async def test_resolve_incident_returns_404_when_alert_is_missing(self) -> None:
        broadcast = AsyncMock()

        class FakeStore:
            def __init__(self, db: object) -> None:
                self.db = db

            def set_incident_status(self, alert_id: str, status: str, changed_by: str, note: str = "") -> None:
                return None

        with patch.object(incident_routes, "PostgresStore", FakeStore), patch.object(
            incident_routes,
            "broadcast",
            broadcast,
        ):
            response = await self.client.post(
                "/api/incidents/missing-alert/resolve",
                json={"note": "Cleared"},
            )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Incident not found")
        broadcast.assert_not_awaited()

    async def test_community_overview_filters_resolved_alerts_and_uses_selected_profile(self) -> None:
        now = datetime.now(UTC)
        stations = [
            StationProfile(
                station_id="river-01",
                station_name="River Intake",
                region="River District",
                timezone="UTC",
                latitude=10.0,
                longitude=105.0,
                source="api",
            )
        ]
        readings = [
            WaterReading(
                timestamp=now - timedelta(minutes=4),
                station_id="river-01",
                ph=7.1,
                tds=210.0,
                turbidity=3.8,
                temperature_c=28.4,
                do_mg_l=6.3,
                flow_l_min=7.0,
            )
        ]
        alerts = [
            AnomalyAlert(
                id="alert-open",
                timestamp=now - timedelta(minutes=5),
                station_id="river-01",
                severity="medium",
                score=0.58,
                reasons=["turbidity outside safe range"],
                feature_contributions={"turbidity": 1.4},
                incident_status="open",
                incident_note="",
                incident_updated_at=now - timedelta(minutes=5),
            ),
            AnomalyAlert(
                id="alert-resolved",
                timestamp=now - timedelta(minutes=10),
                station_id="river-01",
                severity="high",
                score=0.81,
                reasons=["ph outside safe range"],
                feature_contributions={"ph": 2.0},
                incident_status="resolved",
                incident_note="Resolved",
                incident_updated_at=now - timedelta(minutes=2),
            ),
        ]

        class FakeStore:
            def __init__(self, db: object) -> None:
                self.db = db

            def latest_alerts(self, limit: int, station_id: str | None = None, since_minutes: int | None = None) -> list[AnomalyAlert]:
                return alerts

            def latest_readings(
                self,
                limit: int,
                station_id: str | None = None,
                since_minutes: int | None = None,
            ) -> list[WaterReading]:
                return readings

        with patch.object(community_routes, "PostgresStore", FakeStore), patch.object(
            community_routes,
            "list_stations",
            return_value=stations,
        ):
            response = await self.client.get(
                "/api/community/overview",
                params={"since_minutes": 720, "impact_profile": "rural-drinking-water"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["impact_profile"], "rural-drinking-water")
        self.assertEqual(payload["summary"]["recent_alerts"], 1)
        self.assertEqual(payload["summary"]["monitored_zones"], 1)
        self.assertEqual(payload["zones"][0]["risk_level"], "watch")
        self.assertGreaterEqual(len(payload["zones"][0]["priority_sites"]), 1)
