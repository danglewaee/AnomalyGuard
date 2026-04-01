from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AnomalyGuard Water API"
    app_version: str = "1.0.0"

    database_url: str = "postgresql+psycopg://anomaly:anomaly@db:5432/anomalyguard"
    jwt_secret_key: str = "change-me-in-env"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120

    admin_username: str = "admin"
    admin_password: str = "admin123"
    device_api_key: str = "anomalyguard-device-key"

    enable_simulator: bool = True
    poll_interval_seconds: float = 1.0

    redis_url: str = "redis://redis:6379/0"
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_topic_alerts: str = "anomaly-alerts"
    enable_kafka_publish: bool = False

    mlflow_tracking_uri: str = "file:./mlruns"
    community_impact_profile_path: str = ""


settings = Settings()
