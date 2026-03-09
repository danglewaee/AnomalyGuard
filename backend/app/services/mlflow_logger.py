import mlflow

from app.config import settings

mlflow.set_tracking_uri(settings.mlflow_tracking_uri)


def log_ingest_metrics(source: str, readings: int, alerts: int) -> None:
    with mlflow.start_run(run_name=f"ingest-{source}", nested=True):
        mlflow.log_metric("ingested_readings", readings)
        mlflow.log_metric("generated_alerts", alerts)
