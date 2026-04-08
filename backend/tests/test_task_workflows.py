from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("ALLOW_INSECURE_DEFAULTS", "false")
os.environ.setdefault("JWT_SECRET_KEY", "anomalyguard-test-jwt-0123456789abcdef0123456789")
os.environ.setdefault("ADMIN_USERNAME", "test-admin")
os.environ.setdefault("ADMIN_PASSWORD", "AnomalyGuardTestAdmin!2026")
os.environ.setdefault("DEVICE_API_KEY", "anomalyguard-test-device-key-0123456789")
os.environ.setdefault("CORS_ALLOW_ORIGINS", "http://testserver")


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEPS_ROOT = BACKEND_ROOT / ".deps"
if DEPS_ROOT.exists() and str(DEPS_ROOT) not in sys.path:
    sys.path.insert(0, str(DEPS_ROOT))

from app import tasks
from app.schemas import ModelRegistryEntrySummary


UTC = timezone.utc


class _FakeSession:
    def __enter__(self) -> object:
        return object()

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeStore:
    job_updates: list[dict] = []
    existing_job = SimpleNamespace(requested_by="ops-admin")
    reviewed_alerts_rows: list[dict] = []
    reviewed_alerts_args: dict | None = None

    def __init__(self, db: object) -> None:
        self.db = db

    @classmethod
    def reset(cls) -> None:
        cls.job_updates = []
        cls.existing_job = SimpleNamespace(requested_by="ops-admin")
        cls.reviewed_alerts_rows = []
        cls.reviewed_alerts_args = None

    def update_job_status(
        self,
        job_id: str,
        status: str,
        *,
        result_payload: dict | None = None,
        error_message: str | None = None,
    ) -> SimpleNamespace:
        payload = dict(result_payload or {})
        row = {
            "job_id": job_id,
            "status": status,
            "result_payload": payload,
            "error_message": error_message or "",
        }
        self.__class__.job_updates.append(row)
        return SimpleNamespace(id=job_id, status=status, result_payload=payload, error_message=error_message or "")

    def get_job(self, job_id: str) -> SimpleNamespace:
        return self.__class__.existing_job

    def reviewed_alerts(
        self,
        *,
        limit: int,
        station_id: str | None = None,
        since_minutes: int | None = None,
    ) -> list[dict]:
        self.__class__.reviewed_alerts_args = {
            "limit": limit,
            "station_id": station_id,
            "since_minutes": since_minutes,
        }
        return list(self.__class__.reviewed_alerts_rows)


class TaskWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeStore.reset()

    def test_vn_ingest_job_does_not_register_model_candidate(self) -> None:
        task_self = SimpleNamespace(request=SimpleNamespace(id="job-vn-ingest"))

        with patch("app.tasks.SessionLocal", side_effect=lambda: _FakeSession()), patch(
            "app.tasks.PostgresStore",
            _FakeStore,
        ), patch(
            "app.tasks.run_vn_ingest_pipeline",
            return_value={"source": "vn", "new_readings": 2, "skipped_duplicates": 1},
        ), patch("app.tasks.register_retraining_candidate") as register_candidate:
            result = tasks.run_vn_ingest_job_task.run.__func__(task_self, "station-vn-01", 3)

        self.assertEqual(result["new_readings"], 2)
        self.assertNotIn("registry_entry", result)
        register_candidate.assert_not_called()
        self.assertEqual([row["status"] for row in _FakeStore.job_updates], ["running", "succeeded"])

    def test_retraining_job_registers_model_candidate_and_persists_registry_entry(self) -> None:
        now = datetime.now(UTC)
        bundle = {
            "manifest": {
                "manifest_id": "labeled-alerts-xyz789",
                "fingerprint": "xyz789xyz789xyz789",
                "count": 14,
                "station_id": "station-demo",
                "since_minutes": 180,
            },
            "model_artifact": {
                "candidate_id": "anomalyguard-anomaly-detector-r1000-xyz789xyz789",
                "artifact_key": "anomalyguard-anomaly-detector",
                "artifact_version": "r1000-xyz789xyz789",
                "source_revision": "r1000",
                "artifact_uri": "mlflow://runs/mlflow-retraining",
                "manifest_id": "labeled-alerts-xyz789",
                "manifest_fingerprint": "xyz789xyz789xyz789",
            },
            "promotion_gate": {
                "promotion_decision": "shadow",
                "approve_for_shadow": True,
                "approve_for_canary": False,
                "blockers": [],
                "warnings": ["Need broader station coverage"],
            },
            "readiness": {"recommendation": "ready", "readiness_score": 82},
            "evaluation": {"current_precision": 0.91, "recommended_threshold": 0.77},
        }
        registry_entry = ModelRegistryEntrySummary(
            candidate_id="anomalyguard-anomaly-detector-r1000-xyz789xyz789",
            manifest_id="labeled-alerts-xyz789",
            job_id="job-retraining",
            artifact_key="anomalyguard-anomaly-detector",
            artifact_version="r1000-xyz789xyz789",
            source_revision="r1000",
            artifact_uri="mlflow://runs/mlflow-retraining",
            state="prepared",
            promotion_decision="shadow",
            approve_for_shadow=True,
            approve_for_canary=False,
            station_id="station-demo",
            since_minutes=180,
            recommendation="ready",
            readiness_score=82,
            current_precision=0.91,
            recommended_threshold=0.77,
            reviewed_count=14,
            blocker_count=0,
            warning_count=1,
            mlflow_run_id="",
            run_name="",
            status_note="Prepared candidate for registry.",
            last_changed_by="ops-admin",
            created_at=now,
            updated_at=now,
            promoted_at=None,
            rolled_back_at=None,
            bundle_payload={"manifest": {"manifest_id": "labeled-alerts-xyz789"}},
        )

        task_self = SimpleNamespace(request=SimpleNamespace(id="job-retraining"))

        with patch("app.tasks.SessionLocal", side_effect=lambda: _FakeSession()), patch(
            "app.tasks.PostgresStore",
            _FakeStore,
        ), patch(
            "app.tasks.build_reviewed_alert_training_run",
            return_value=dict(bundle),
        ), patch(
            "app.tasks.register_retraining_candidate",
            return_value=registry_entry,
        ) as register_candidate:
            result = tasks.prepare_reviewed_alert_training_job_task.run.__func__(task_self, None, 180, 50, 20)

        self.assertEqual(_FakeStore.reviewed_alerts_args, {"limit": 50, "station_id": None, "since_minutes": 180})
        register_candidate.assert_called_once()
        self.assertEqual(register_candidate.call_args.kwargs["job_id"], "job-retraining")
        self.assertEqual(register_candidate.call_args.kwargs["actor"], "ops-admin")
        self.assertEqual(result["registry_entry"]["candidate_id"], "anomalyguard-anomaly-detector-r1000-xyz789xyz789")
        self.assertEqual(result["registry_entry"]["manifest_id"], "labeled-alerts-xyz789")
        self.assertEqual(_FakeStore.job_updates[-1]["status"], "succeeded")
        self.assertIn("registry_entry", _FakeStore.job_updates[-1]["result_payload"])
