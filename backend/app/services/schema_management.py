from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


MIGRATION_GUIDANCE = "Run `alembic upgrade head` from the backend directory before starting the API."


def get_schema_revision(db: Session) -> str | None:
    if not hasattr(db, "execute"):
        return None
    try:
        return db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    except SQLAlchemyError:
        return None


def assert_schema_ready(engine: Engine) -> str:
    try:
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    except SQLAlchemyError as exc:
        raise RuntimeError(f"Database schema is not initialized. {MIGRATION_GUIDANCE}") from exc

    if not revision:
        raise RuntimeError(f"Database schema is missing an Alembic revision. {MIGRATION_GUIDANCE}")

    return revision
