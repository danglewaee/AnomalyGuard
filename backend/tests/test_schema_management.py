from pathlib import Path
import sys
import unittest

from sqlalchemy.exc import ProgrammingError


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEPS_ROOT = BACKEND_ROOT / ".deps"
if DEPS_ROOT.exists() and str(DEPS_ROOT) not in sys.path:
    sys.path.insert(0, str(DEPS_ROOT))

from app.services.schema_management import MIGRATION_GUIDANCE, assert_schema_ready, get_schema_revision


class _ScalarResult:
    def __init__(self, value: str | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> str | None:
        return self.value


class _ConnectionContext:
    def __init__(self, revision: str | None = None, exc: Exception | None = None) -> None:
        self.revision = revision
        self.exc = exc

    def __enter__(self) -> "_ConnectionContext":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def execute(self, stmt):
        if self.exc is not None:
            raise self.exc
        return _ScalarResult(self.revision)


class _Engine:
    def __init__(self, revision: str | None = None, exc: Exception | None = None) -> None:
        self.revision = revision
        self.exc = exc

    def connect(self) -> _ConnectionContext:
        return _ConnectionContext(self.revision, self.exc)


class _Session:
    def __init__(self, revision: str | None = None, exc: Exception | None = None) -> None:
        self.revision = revision
        self.exc = exc

    def execute(self, stmt):
        if self.exc is not None:
            raise self.exc
        return _ScalarResult(self.revision)


class SchemaManagementTests(unittest.TestCase):
    def test_assert_schema_ready_returns_current_revision(self) -> None:
        self.assertEqual(assert_schema_ready(_Engine(revision="20260404_0001")), "20260404_0001")

    def test_assert_schema_ready_raises_when_revision_is_missing(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "alembic upgrade head"):
            assert_schema_ready(_Engine(revision=None))

    def test_assert_schema_ready_raises_with_guidance_on_missing_table(self) -> None:
        exc = ProgrammingError("SELECT version_num FROM alembic_version", {}, Exception("missing table"))
        with self.assertRaisesRegex(RuntimeError, MIGRATION_GUIDANCE):
            assert_schema_ready(_Engine(exc=exc))

    def test_get_schema_revision_returns_none_when_revision_table_is_missing(self) -> None:
        exc = ProgrammingError("SELECT version_num FROM alembic_version", {}, Exception("missing table"))
        self.assertIsNone(get_schema_revision(_Session(exc=exc)))

    def test_get_schema_revision_returns_none_for_non_session_objects(self) -> None:
        self.assertIsNone(get_schema_revision(object()))
