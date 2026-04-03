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

from app.api.routes import alerts as alert_routes
from app.api.routes import community as community_routes
from app.api.routes import ingest as ingest_routes
from app.api.routes import incidents as incident_routes
from app.api.routes import jobs as jobs_routes
import app.main as main
from app.schemas import AlertHistoryEntry, AnomalyAlert, JobStatus, StationProfile, WaterReading


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

        with patch.object(ingest_routes, "PostgresStore", FakeStore), patch.object(ingest_routes.celery_app, "send_task", send_task):
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

        with patch.object(ingest_routes, "PostgresStore", FakeStore), patch.object(
            ingest_routes.celery_app,
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

    async def test_review_alert_marks_false_positive_and_broadcasts_review_event(self) -> None:
        now = datetime.now(UTC)
        updated_alert = AnomalyAlert(
            id="alert-review",
            timestamp=now - timedelta(minutes=7),
            station_id="mekong-can-tho",
            severity="low",
            score=0.49,
            reasons=["statistical deviation from recent baseline"],
            feature_contributions={"tds": 1.2},
            incident_status="open",
            incident_note="",
            incident_updated_at=now,
            review_label="false_positive",
            review_note="Sensor calibration drift",
            reviewed_at=now,
            reviewed_by="test-admin",
        )
        broadcast = AsyncMock()
        review_calls: list[dict] = []

        class FakeStore:
            def __init__(self, db: object) -> None:
                self.db = db

            def set_alert_review(self, alert_id: str, label: str, reviewed_by: str, note: str = "") -> AnomalyAlert:
                review_calls.append(
                    {
                        "alert_id": alert_id,
                        "label": label,
                        "reviewed_by": reviewed_by,
                        "note": note,
                    }
                )
                return updated_alert

        with patch.object(alert_routes, "PostgresStore", FakeStore), patch.object(alert_routes, "broadcast", broadcast):
            response = await self.client.post(
                "/api/alerts/alert-review/review",
                json={"label": "false_positive", "note": "Sensor calibration drift"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["review_label"], "false_positive")
        self.assertEqual(review_calls[0]["reviewed_by"], "test-admin")
        broadcast.assert_awaited_once()
        self.assertEqual(broadcast.await_args.args[0], "alert_review")

    async def test_export_labeled_alerts_returns_filtered_json_payload(self) -> None:
        now = datetime.now(UTC)
        exported_alert = AnomalyAlert(
            id="alert-export",
            timestamp=now - timedelta(minutes=30),
            station_id="mekong-can-tho",
            severity="medium",
            score=0.64,
            reasons=["turbidity outside safe range"],
            feature_contributions={"turbidity": 1.7},
            incident_status="acknowledged",
            incident_note="Field check in progress",
            incident_updated_at=now - timedelta(minutes=15),
            review_label="true_anomaly",
            review_note="Confirmed by operator",
            reviewed_at=now - timedelta(minutes=10),
            reviewed_by="test-admin",
        )

        class FakeStore:
            def __init__(self, db: object) -> None:
                self.db = db

            def reviewed_alerts(
                self,
                limit: int,
                *,
                label: str | None = None,
                station_id: str | None = None,
                since_minutes: int | None = None,
            ) -> list[AnomalyAlert]:
                self.last_call = {
                    "limit": limit,
                    "label": label,
                    "station_id": station_id,
                    "since_minutes": since_minutes,
                }
                return [exported_alert]

        with patch.object(alert_routes, "PostgresStore", FakeStore):
            response = await self.client.get(
                "/api/alerts/labeled/export",
                params={
                    "format": "json",
                    "label": "true_anomaly",
                    "station_id": "mekong-can-tho",
                    "since_minutes": 720,
                    "limit": 50,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["label_filter"], "true_anomaly")
        self.assertEqual(payload["station_id"], "mekong-can-tho")
        self.assertEqual(payload["items"][0]["review_label"], "true_anomaly")

    async def test_export_labeled_alerts_can_stream_csv(self) -> None:
        now = datetime.now(UTC)
        exported_alert = AnomalyAlert(
            id="alert-csv",
            timestamp=now - timedelta(minutes=45),
            station_id="mekong-can-tho",
            severity="low",
            score=0.48,
            reasons=["statistical deviation from recent baseline"],
            feature_contributions={"tds": 1.1},
            incident_status="open",
            incident_note="",
            incident_updated_at=now - timedelta(minutes=40),
            review_label="false_positive",
            review_note="Sensor wash cycle",
            reviewed_at=now - timedelta(minutes=35),
            reviewed_by="test-admin",
        )

        class FakeStore:
            def __init__(self, db: object) -> None:
                self.db = db

            def reviewed_alerts(
                self,
                limit: int,
                *,
                label: str | None = None,
                station_id: str | None = None,
                since_minutes: int | None = None,
            ) -> list[AnomalyAlert]:
                return [exported_alert]

        with patch.object(alert_routes, "PostgresStore", FakeStore):
            response = await self.client.get(
                "/api/alerts/labeled/export",
                params={"format": "csv", "label": "false_positive"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers.get("content-type", ""))
        self.assertIn("review_label", response.text)
        self.assertIn("false_positive", response.text)

    async def test_retraining_manifest_reports_balance_and_export_urls(self) -> None:
        now = datetime.now(UTC)
        manifest_alerts = [
            AnomalyAlert(
                id="alert-manifest-1",
                timestamp=now - timedelta(hours=3),
                station_id="mekong-can-tho",
                severity="medium",
                score=0.61,
                reasons=["turbidity outside safe range"],
                feature_contributions={"turbidity": 1.2},
                incident_status="acknowledged",
                incident_note="",
                incident_updated_at=now - timedelta(hours=2),
                review_label="true_anomaly",
                review_note="Confirmed",
                reviewed_at=now - timedelta(hours=2),
                reviewed_by="test-admin",
            ),
            AnomalyAlert(
                id="alert-manifest-2",
                timestamp=now - timedelta(hours=2),
                station_id="saigon-thu-duc",
                severity="low",
                score=0.42,
                reasons=["statistical deviation from recent baseline"],
                feature_contributions={"tds": 1.0},
                incident_status="open",
                incident_note="",
                incident_updated_at=now - timedelta(hours=1, minutes=30),
                review_label="false_positive",
                review_note="Sensor cleanout",
                reviewed_at=now - timedelta(hours=1),
                reviewed_by="test-admin",
            ),
        ]

        class FakeStore:
            def __init__(self, db: object) -> None:
                self.db = db

            def reviewed_alerts(
                self,
                limit: int,
                *,
                label: str | None = None,
                station_id: str | None = None,
                since_minutes: int | None = None,
            ) -> list[AnomalyAlert]:
                return manifest_alerts

        with patch.object(alert_routes, "PostgresStore", FakeStore):
            response = await self.client.get(
                "/api/alerts/labeled/manifest",
                params={"station_id": "mekong-can-tho", "since_minutes": 720, "limit": 100},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["station_id"], "mekong-can-tho")
        self.assertEqual(payload["label_counts"]["true_anomaly"], 1)
        self.assertEqual(payload["label_counts"]["false_positive"], 1)
        self.assertIn("json", payload["export_urls"])
        self.assertIn("csv", payload["export_urls"])
        self.assertTrue(payload["manifest_id"].startswith("labeled-alerts-"))
        self.assertGreater(len(payload["warnings"]), 0)

    async def test_reviewed_alert_evaluation_reports_precision_and_threshold(self) -> None:
        now = datetime.now(UTC)
        evaluation_alerts = [
            AnomalyAlert(
                id="eval-1",
                timestamp=now - timedelta(hours=4),
                station_id="mekong-can-tho",
                severity="medium",
                score=0.61,
                reasons=["turbidity outside safe range"],
                feature_contributions={"turbidity": 1.3},
                incident_status="acknowledged",
                incident_note="",
                incident_updated_at=now - timedelta(hours=3),
                review_label="true_anomaly",
                review_note="Confirmed in field",
                reviewed_at=now - timedelta(hours=2),
                reviewed_by="test-admin",
            ),
            AnomalyAlert(
                id="eval-2",
                timestamp=now - timedelta(hours=3),
                station_id="mekong-can-tho",
                severity="high",
                score=0.82,
                reasons=["ph outside safe range"],
                feature_contributions={"ph": 2.4},
                incident_status="acknowledged",
                incident_note="",
                incident_updated_at=now - timedelta(hours=2),
                review_label="true_anomaly",
                review_note="Confirmed at intake",
                reviewed_at=now - timedelta(hours=1, minutes=30),
                reviewed_by="test-admin",
            ),
            AnomalyAlert(
                id="eval-3",
                timestamp=now - timedelta(hours=2),
                station_id="mekong-can-tho",
                severity="low",
                score=0.49,
                reasons=["statistical deviation from recent baseline"],
                feature_contributions={"tds": 1.0},
                incident_status="open",
                incident_note="",
                incident_updated_at=now - timedelta(hours=1, minutes=45),
                review_label="false_positive",
                review_note="Maintenance drift",
                reviewed_at=now - timedelta(hours=1),
                reviewed_by="test-admin",
            ),
        ]

        class FakeStore:
            def __init__(self, db: object) -> None:
                self.db = db

            def reviewed_alerts(
                self,
                limit: int,
                *,
                label: str | None = None,
                station_id: str | None = None,
                since_minutes: int | None = None,
            ) -> list[AnomalyAlert]:
                return evaluation_alerts

        with patch.object(alert_routes, "PostgresStore", FakeStore):
            response = await self.client.get(
                "/api/alerts/labeled/evaluation",
                params={"station_id": "mekong-can-tho", "since_minutes": 720, "limit": 100},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 3)
        self.assertEqual(payload["station_id"], "mekong-can-tho")
        self.assertEqual(payload["current_alert_threshold"], 0.45)
        self.assertEqual(payload["current_precision"], 0.667)
        self.assertEqual(payload["label_counts"]["true_anomaly"], 2)
        self.assertEqual(payload["label_counts"]["false_positive"], 1)
        self.assertEqual(payload["recommended_threshold"], 0.61)
        self.assertEqual(payload["severity_breakdown"]["medium"]["precision"], 1.0)
        self.assertGreaterEqual(len(payload["threshold_sweep"]), 1)

    async def test_alert_history_returns_operator_timeline(self) -> None:
        now = datetime.now(UTC)
        alert = AnomalyAlert(
            id="alert-history",
            timestamp=now - timedelta(hours=2),
            station_id="mekong-can-tho",
            severity="medium",
            score=0.58,
            reasons=["turbidity outside safe range"],
            feature_contributions={"turbidity": 1.4},
            incident_status="acknowledged",
            incident_note="Field check started",
            incident_updated_at=now - timedelta(minutes=45),
            review_label="true_anomaly",
            review_note="Confirmed at intake",
            reviewed_at=now - timedelta(minutes=20),
            reviewed_by="test-admin",
        )
        timeline = [
            AlertHistoryEntry(
                id=1,
                alert_id="alert-history",
                station_id="mekong-can-tho",
                event_type="detected",
                event_value="medium",
                note="",
                changed_by="system",
                created_at=now - timedelta(hours=2),
            ),
            AlertHistoryEntry(
                id=2,
                alert_id="alert-history",
                station_id="mekong-can-tho",
                event_type="incident_status",
                event_value="acknowledged",
                note="Field check started",
                changed_by="test-admin",
                created_at=now - timedelta(minutes=45),
            ),
            AlertHistoryEntry(
                id=3,
                alert_id="alert-history",
                station_id="mekong-can-tho",
                event_type="review_label",
                event_value="true_anomaly",
                note="Confirmed at intake",
                changed_by="test-admin",
                created_at=now - timedelta(minutes=20),
            ),
        ]

        class FakeStore:
            def __init__(self, db: object) -> None:
                self.db = db

            def alert_with_incident(self, alert_id: str) -> AnomalyAlert | None:
                return alert if alert_id == "alert-history" else None

            def alert_history(self, alert_id: str, limit: int = 25) -> list[AlertHistoryEntry]:
                return timeline[:limit]

        with patch.object(alert_routes, "PostgresStore", FakeStore):
            response = await self.client.get("/api/alerts/alert-history/history", params={"limit": 25})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 3)
        self.assertEqual(payload[0]["event_type"], "detected")
        self.assertEqual(payload[1]["event_value"], "acknowledged")
        self.assertEqual(payload[2]["note"], "Confirmed at intake")

    async def test_reviewed_alert_readiness_detects_recent_drift(self) -> None:
        now = datetime.now(UTC)
        readiness_alerts: list[AnomalyAlert] = []
        for index in range(18):
            is_true = index % 2 == 0
            readiness_alerts.append(
                AnomalyAlert(
                    id=f"ready-base-{index}",
                    timestamp=now - timedelta(hours=30 - index),
                    station_id="mekong-can-tho" if index % 2 == 0 else "saigon-thu-duc",
                    severity="medium" if is_true else "low",
                    score=0.62 + (index * 0.01) if is_true else 0.41 + (index * 0.005),
                    reasons=["baseline"],
                    feature_contributions={"tds": 1.0},
                    incident_status="acknowledged",
                    incident_note="",
                    incident_updated_at=now - timedelta(hours=29 - index),
                    review_label="true_anomaly" if is_true else "false_positive",
                    review_note="baseline review",
                    reviewed_at=now - timedelta(days=4, hours=18 - index),
                    reviewed_by="test-admin",
                )
            )

        for index in range(6):
            readiness_alerts.append(
                AnomalyAlert(
                    id=f"ready-recent-{index}",
                    timestamp=now - timedelta(hours=6 - index),
                    station_id="mekong-can-tho",
                    severity="high",
                    score=0.84 + (index * 0.01),
                    reasons=["recent surge"],
                    feature_contributions={"ph": 2.1},
                    incident_status="acknowledged",
                    incident_note="",
                    incident_updated_at=now - timedelta(hours=5 - index),
                    review_label="true_anomaly",
                    review_note="recent review",
                    reviewed_at=now - timedelta(hours=6 - index),
                    reviewed_by="test-admin",
                )
            )

        class FakeStore:
            def __init__(self, db: object) -> None:
                self.db = db

            def reviewed_alerts(
                self,
                limit: int,
                *,
                label: str | None = None,
                station_id: str | None = None,
                since_minutes: int | None = None,
            ) -> list[AnomalyAlert]:
                return readiness_alerts[:limit]

        with patch.object(alert_routes, "PostgresStore", FakeStore):
            response = await self.client.get(
                "/api/alerts/labeled/readiness",
                params={"since_minutes": 10080, "limit": 100, "recent_count": 6},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 24)
        self.assertEqual(payload["recent_window_count"], 6)
        self.assertEqual(payload["reference_window_count"], 18)
        self.assertEqual(payload["recommendation"], "monitor")
        self.assertFalse(payload["ready_for_training"])
        self.assertGreaterEqual(payload["readiness_score"], 60)
        self.assertEqual(payload["label_counts"]["true_anomaly"], 15)
        self.assertEqual(payload["label_counts"]["false_positive"], 9)
        self.assertEqual(payload["checks"][-1]["key"], "distribution_stability")
        self.assertFalse(payload["checks"][-1]["passed"])
        self.assertEqual(payload["label_distribution_shift"]["true_anomaly"]["absolute_delta"], 0.5)
        self.assertEqual(payload["station_concentration_shift"]["absolute_delta"], 0.5)
        self.assertGreaterEqual(len(payload["warnings"]), 1)

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
            AnomalyAlert(
                id="alert-false-positive",
                timestamp=now - timedelta(minutes=6),
                station_id="river-01",
                severity="high",
                score=0.82,
                reasons=["ph outside safe range"],
                feature_contributions={"ph": 2.1},
                incident_status="open",
                incident_note="",
                incident_updated_at=now - timedelta(minutes=1),
                review_label="false_positive",
                review_note="Probe maintenance window",
                reviewed_at=now - timedelta(minutes=1),
                reviewed_by="test-admin",
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
