from prometheus_client import Counter, Histogram

READINGS_INGESTED = Counter("anomalyguard_readings_ingested_total", "Total number of ingested readings")
ALERTS_GENERATED = Counter("anomalyguard_alerts_generated_total", "Total number of generated alerts")
INGEST_DURATION = Histogram("anomalyguard_ingest_duration_seconds", "Ingestion request duration")
INGEST_BATCHES_COMPLETED = Counter(
    "anomalyguard_ingest_batches_completed_total",
    "Completed ingest batches by source",
    ["source"],
)
INGEST_DUPLICATES_SKIPPED = Counter(
    "anomalyguard_ingest_duplicates_skipped_total",
    "Duplicate ingest readings skipped by source",
    ["source"],
)
JOB_STATUS_TRANSITIONS = Counter(
    "anomalyguard_job_status_transitions_total",
    "Job status transitions by job type and status",
    ["job_type", "status"],
)
JOB_QUEUE_SECONDS = Histogram(
    "anomalyguard_job_queue_seconds",
    "Time jobs spend waiting before they start running",
    ["job_type"],
)
JOB_RUN_SECONDS = Histogram(
    "anomalyguard_job_run_seconds",
    "Time jobs spend running before reaching a terminal status",
    ["job_type", "status"],
)


def record_ingest_summary_metrics(source: str, inserted: int, alerts: int, skipped_duplicates: int = 0) -> None:
    INGEST_BATCHES_COMPLETED.labels(source=source).inc()
    if inserted > 0:
        READINGS_INGESTED.inc(inserted)
    if alerts > 0:
        ALERTS_GENERATED.inc(alerts)
    if skipped_duplicates > 0:
        INGEST_DUPLICATES_SKIPPED.labels(source=source).inc(skipped_duplicates)


def record_job_status_transition(job_type: str, status: str) -> None:
    JOB_STATUS_TRANSITIONS.labels(job_type=job_type, status=status).inc()


def observe_job_queue_seconds(job_type: str, seconds: float) -> None:
    JOB_QUEUE_SECONDS.labels(job_type=job_type).observe(max(0.0, seconds))


def observe_job_run_seconds(job_type: str, status: str, seconds: float) -> None:
    JOB_RUN_SECONDS.labels(job_type=job_type, status=status).observe(max(0.0, seconds))
