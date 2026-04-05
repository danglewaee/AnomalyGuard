import json
from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_INSECURE_SECRET_VALUES = {
    "",
    "change-me-in-env",
    "replace-me",
    "admin123",
    "anomalyguard-device-key",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env", ".env.example", "backend/.env.example"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AnomalyGuard Water API"
    app_version: str = "1.0.0"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    allow_insecure_defaults: bool = False

    database_url: str = "postgresql+psycopg://anomaly:anomaly@db:5432/anomalyguard"
    jwt_secret_key: str = ""
    jwt_secret_key_file: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120

    admin_username: str = "admin"
    admin_password: str = ""
    admin_password_file: str = ""
    device_api_key: str = ""
    device_api_key_file: str = ""
    device_keys_path: str = ""
    cors_allow_origins: str = ""
    cors_allow_origin_regex: str = ""

    enable_simulator: bool = True
    poll_interval_seconds: float = 1.0

    redis_url: str = "redis://redis:6379/0"
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_topic_alerts: str = "anomaly-alerts"
    enable_kafka_publish: bool = False

    mlflow_tracking_uri: str = "file:./mlruns"
    community_impact_profile_path: str = ""

    @field_validator("device_keys_path", "jwt_secret_key_file", "admin_password_file", "device_api_key_file")
    @classmethod
    def normalize_optional_path(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def resolve_secrets_and_validate(self) -> "Settings":
        self.jwt_secret_key = self._resolve_secret_value(
            field_name="JWT_SECRET_KEY",
            value=self.jwt_secret_key,
            file_value=self.jwt_secret_key_file,
        )
        self.admin_password = self._resolve_secret_value(
            field_name="ADMIN_PASSWORD",
            value=self.admin_password,
            file_value=self.admin_password_file,
        )
        self.device_api_key = self._resolve_secret_value(
            field_name="DEVICE_API_KEY",
            value=self.device_api_key,
            file_value=self.device_api_key_file,
        )
        self.device_keys_path = self._resolve_optional_existing_path(
            "DEVICE_KEYS_PATH",
            self.device_keys_path,
            required=not bool(self.device_api_key),
        )

        strict_mode = not self.allow_insecure_defaults

        if self.app_env in {"staging", "production"} and self.allow_insecure_defaults:
            raise ValueError("ALLOW_INSECURE_DEFAULTS cannot be enabled outside development or test")

        if strict_mode:
            self._validate_secret("JWT_SECRET_KEY", self.jwt_secret_key, minimum_length=32)
            self._validate_secret("ADMIN_PASSWORD", self.admin_password, minimum_length=12)
            if not self.device_keys_path:
                self._validate_secret("DEVICE_API_KEY", self.device_api_key, minimum_length=24)
            if "*" in self.cors_allowed_origins:
                raise ValueError("Wildcard CORS origins are not allowed in strict mode")
            if not self.cors_allowed_origins and not self.cors_allow_origin_regex:
                raise ValueError("Set CORS_ALLOW_ORIGINS or CORS_ALLOW_ORIGIN_REGEX in strict mode")

        return self

    def _resolve_optional_existing_path(self, field_name: str, value: str, *, required: bool) -> str:
        if not value:
            return ""
        path = self._resolve_path(value)
        if path is None or not path.exists() or not path.is_file():
            if not required:
                return ""
            raise ValueError(f"{field_name} must point to an existing file")
        return str(path)

    def _resolve_secret_value(self, *, field_name: str, value: str, file_value: str) -> str:
        if value:
            return value
        if not file_value:
            return value
        path = self._resolve_path(file_value)
        if path is None or not path.exists() or not path.is_file():
            raise ValueError(f"{field_name}_FILE must point to an existing file")
        return path.read_text(encoding="utf-8").strip()

    @property
    def cors_allowed_origins(self) -> list[str]:
        value = self.cors_allow_origins.strip()
        if not value:
            return []
        if value.startswith("["):
            parsed = json.loads(value)
            if not isinstance(parsed, list):
                raise ValueError("CORS_ALLOW_ORIGINS must be a JSON array or comma-separated string")
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [item.strip() for item in value.split(",") if item.strip()]

    def _validate_secret(self, field_name: str, value: str, *, minimum_length: int) -> None:
        if value in _INSECURE_SECRET_VALUES or len(value) < minimum_length:
            raise ValueError(f"{field_name} must be explicitly configured with a stronger value")

    def _resolve_path(self, value: str) -> Path | None:
        if not value:
            return None
        backend_root = Path(__file__).resolve().parents[1]
        candidate_paths = [Path(value), backend_root / value]
        for path in candidate_paths:
            if path.exists():
                return path
        return candidate_paths[0]


settings = Settings()
