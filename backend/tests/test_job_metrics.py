from datetime import datetime, timedelta, timezone
from pathlib import Path
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

from app.services.store_pg import PostgresStore


UTC = timezone.utc


class _FakeDB:
    def __init__(self) -> None:
        self.rows: dict[str, object] = {}

    def add(self, row: object) -> None:
        self.rows[row.id] = row

    def commit(self) -> None:
        return None

    def refresh(self, row: object) -> None:
        return None

    def get(self, model: object, key: str):
        return self.rows.get(key)


class JobMetricTests(unittest.TestCase):
    def test_create_job_records_queued_transition(self) -> None:
        db = _FakeDB()
        store = PostgresStore(db)

        with patch("app.services.store_pg.record_job_status_transition") as transition_metric:
            job = store.create_job("job-1", "ingest_vn", "tester", {"days": 3})

        self.assertEqual(job.status, "queued")
        transition_metric.assert_called_once_with("ingest_vn", "queued")

    def test_update_job_status_records_queue_and_runtime_observations(self) -> None:
        db = _FakeDB()
        store = PostgresStore(db)
        created = store.create_job("job-2", "ingest_usgs", "tester", {"hours": 24})
        row = db.rows[created.id]
        row.created_at = datetime.now(UTC) - timedelta(seconds=20)

        with patch("app.services.store_pg.record_job_status_transition") as transition_metric, patch(
            "app.services.store_pg.observe_job_queue_seconds"
        ) as queue_metric, patch("app.services.store_pg.observe_job_run_seconds") as run_metric:
            running = store.update_job_status("job-2", "running")
            row.started_at = datetime.now(UTC) - timedelta(seconds=5)
            succeeded = store.update_job_status("job-2", "succeeded", result_payload={"ok": True})

        self.assertEqual(running.status, "running")
        self.assertEqual(succeeded.status, "succeeded")
        transition_metric.assert_any_call("ingest_usgs", "running")
        transition_metric.assert_any_call("ingest_usgs", "succeeded")
        queue_metric.assert_called_once()
        run_metric.assert_called_once()
        self.assertEqual(run_metric.call_args.args[:2], ("ingest_usgs", "succeeded"))
