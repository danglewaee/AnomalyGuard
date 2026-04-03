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


def log_retraining_run_metrics(
    *,
    run_name: str,
    manifest_id: str,
    station_id: str | None,
    since_minutes: int | None,
    readiness_score: int,
    recommendation: str,
    current_precision: float | None,
    recommended_threshold: float | None,
    label_counts: dict[str, int],
    drift_metrics: dict[str, float | None],
) -> str:
    if mlflow is None:
        return ""

    with mlflow.start_run(run_name=run_name, nested=True) as run:
        mlflow.log_param("manifest_id", manifest_id)
        mlflow.log_param("station_id", station_id or "all")
        mlflow.log_param("since_minutes", since_minutes or 0)
        mlflow.log_param("recommendation", recommendation)
        mlflow.log_metric("readiness_score", readiness_score)
        if current_precision is not None:
            mlflow.log_metric("current_precision", current_precision)
        if recommended_threshold is not None:
            mlflow.log_metric("recommended_threshold", recommended_threshold)
        for label, count in label_counts.items():
            mlflow.log_metric(f"label_count_{label}", count)
        for key, value in drift_metrics.items():
            if value is not None:
                mlflow.log_metric(key, value)
        return getattr(run.info, "run_id", "") or ""
