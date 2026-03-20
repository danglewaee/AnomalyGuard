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

    enable_simulator: bool = True
    poll_interval_seconds: float = 1.0

    redis_url: str = "redis://redis:6379/0"
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_topic_alerts: str = "anomaly-alerts"
    enable_kafka_publish: bool = False

    enable_notifications: bool = True
    enable_async_notifications: bool = False
    enable_webhook_notifications: bool = False
    notification_webhook_url: str = ""
    notification_request_timeout_seconds: float = 5.0
    smtp_notifications_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    twilio_sms_enabled: bool = False
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_phone: str = ""
    twilio_api_base: str = "https://api.twilio.com/2010-04-01"

    mlflow_tracking_uri: str = "file:./mlruns"


settings = Settings()
