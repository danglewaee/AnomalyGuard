from app.config import settings

try:
    import mlflow
except Exception:  # pragma: no cover - optional runtime dependency
    mlflow = None

if mlflow is not None:
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)


def log_ingest_metrics(source: str, readings: int, alerts: int, skipped_duplicates: int = 0) -> None:
    if mlflow is None:
        return

    with mlflow.start_run(run_name=f"ingest-{source}", nested=True):
        mlflow.log_metric("ingested_readings", readings)
        mlflow.log_metric("generated_alerts", alerts)
        mlflow.log_metric("skipped_duplicate_readings", skipped_duplicates)
