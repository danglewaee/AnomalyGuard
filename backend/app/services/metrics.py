from prometheus_client import Counter, Histogram

READINGS_INGESTED = Counter("anomalyguard_readings_ingested_total", "Total number of ingested readings")
ALERTS_GENERATED = Counter("anomalyguard_alerts_generated_total", "Total number of generated alerts")
INGEST_DURATION = Histogram("anomalyguard_ingest_duration_seconds", "Ingestion request duration")
