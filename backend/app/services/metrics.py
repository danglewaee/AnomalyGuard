from prometheus_client import Counter, Histogram

READINGS_INGESTED = Counter("anomalyguard_readings_ingested_total", "Total number of ingested readings")
ALERTS_GENERATED = Counter("anomalyguard_alerts_generated_total", "Total number of generated alerts")
INGEST_DURATION = Histogram("anomalyguard_ingest_duration_seconds", "Ingestion request duration")

MEMORY_UPSERTED = Counter("anomalyguard_memory_upsert_total", "Total number of memory upserts")
MEMORY_DELETED = Counter("anomalyguard_memory_delete_total", "Total number of memory deletes")
MEMORY_SEARCH_TOTAL = Counter(
    "anomalyguard_memory_search_total",
    "Total number of memory searches partitioned by cache usage",
    ["cache"],
)
MEMORY_SEARCH_DURATION = Histogram(
    "anomalyguard_memory_search_duration_seconds",
    "Memory search request duration in seconds",
)
