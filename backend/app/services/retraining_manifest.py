from collections import Counter
from datetime import datetime, timezone
import hashlib
from urllib.parse import urlencode

from app.schemas import AnomalyAlert, RetrainingManifestResponse


_MIN_READY_SAMPLES = 20
_MIN_PER_LABEL = 5


def _build_fingerprint(alerts: list[AnomalyAlert]) -> str:
    digest = hashlib.sha256()
    for alert in sorted(
        alerts,
        key=lambda item: (
            item.reviewed_at.isoformat() if item.reviewed_at else "",
            item.id,
            item.review_label or "",
        ),
    ):
        digest.update(
            "|".join(
                [
                    alert.id,
                    alert.station_id,
                    alert.review_label or "",
                    alert.reviewed_at.isoformat() if alert.reviewed_at else "",
                    alert.reviewed_by or "",
                ]
            ).encode("utf-8")
        )
    return digest.hexdigest()


def _suggested_split(count: int) -> dict[str, int]:
    if count <= 1:
        return {"train": count, "validation": 0, "test": 0}

    train = max(1, int(count * 0.7))
    validation = int(count * 0.15)
    test = count - train - validation

    if test == 0 and count >= 3:
        test = 1
        train = max(1, train - 1)
    if validation == 0 and count >= 6:
        validation = 1
        train = max(1, train - 1)

    remainder = count - train - validation - test
    train += remainder
    return {"train": train, "validation": validation, "test": test}


def _build_export_urls(
    *,
    label: str | None,
    station_id: str | None,
    since_minutes: int | None,
    limit: int,
) -> dict[str, str]:
    params: dict[str, str] = {"limit": str(limit)}
    if label:
        params["label"] = label
    if station_id:
        params["station_id"] = station_id
    if since_minutes:
        params["since_minutes"] = str(since_minutes)

    json_params = urlencode({"format": "json", **params})
    csv_params = urlencode({"format": "csv", **params})
    return {
        "json": f"/api/alerts/labeled/export?{json_params}",
        "csv": f"/api/alerts/labeled/export?{csv_params}",
    }


def build_retraining_manifest(
    *,
    alerts: list[AnomalyAlert],
    label: str | None,
    station_id: str | None,
    since_minutes: int | None,
    limit: int,
) -> RetrainingManifestResponse:
    label_counts = Counter(alert.review_label or "unlabeled" for alert in alerts)
    station_counts = Counter(alert.station_id for alert in alerts)
    reviewed_at_values = sorted([alert.reviewed_at for alert in alerts if alert.reviewed_at is not None])

    warnings: list[str] = []
    true_count = label_counts.get("true_anomaly", 0)
    false_count = label_counts.get("false_positive", 0)

    if len(alerts) < _MIN_READY_SAMPLES:
        warnings.append(f"Only {len(alerts)} reviewed alerts available; collect at least {_MIN_READY_SAMPLES} before retraining.")
    if true_count < _MIN_PER_LABEL:
        warnings.append(f"Only {true_count} true_anomaly labels available; collect at least {_MIN_PER_LABEL}.")
    if false_count < _MIN_PER_LABEL:
        warnings.append(f"Only {false_count} false_positive labels available; collect at least {_MIN_PER_LABEL}.")
    if len(station_counts) < 2:
        warnings.append("Labels currently cover fewer than 2 stations, so retraining may overfit to one location.")

    fingerprint = _build_fingerprint(alerts)
    manifest_id = f"labeled-alerts-{fingerprint[:12]}"

    return RetrainingManifestResponse(
        generated_at=datetime.now(timezone.utc),
        manifest_id=manifest_id,
        fingerprint=fingerprint,
        count=len(alerts),
        label_filter=label,
        station_id=station_id,
        since_minutes=since_minutes,
        label_counts=dict(label_counts),
        station_counts=dict(station_counts),
        earliest_reviewed_at=reviewed_at_values[0] if reviewed_at_values else None,
        latest_reviewed_at=reviewed_at_values[-1] if reviewed_at_values else None,
        suggested_split=_suggested_split(len(alerts)),
        ready_for_training=not warnings,
        warnings=warnings,
        export_urls=_build_export_urls(
            label=label,
            station_id=station_id,
            since_minutes=since_minutes,
            limit=limit,
        ),
    )
