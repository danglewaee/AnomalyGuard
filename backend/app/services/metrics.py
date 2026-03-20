from prometheus_client import Counter, Histogram

READINGS_INGESTED = Counter("anomalyguard_readings_ingested_total", "Total number of ingested readings")
ALERTS_GENERATED = Counter("anomalyguard_alerts_generated_total", "Total number of generated alerts")
INGEST_DURATION = Histogram("anomalyguard_ingest_duration_seconds", "Ingestion request duration")
NOTIFICATIONS_QUEUED = Counter(
    "anomalyguard_notifications_queued_total",
    "Total number of queued alert notifications",
    ["channel"],
)
NOTIFICATIONS_DELIVERED = Counter(
    "anomalyguard_notifications_delivered_total",
    "Total number of delivered alert notifications",
    ["channel"],
)
NOTIFICATIONS_FAILED = Counter(
    "anomalyguard_notifications_failed_total",
    "Total number of failed alert notifications",
    ["channel"],
)
