from collections import Counter
from datetime import datetime, timedelta, timezone

from app.schemas import (
    AnomalyAlert,
    DriftMetric,
    ReadinessCheck,
    ReviewedAlertReadinessResponse,
)
from app.services.reviewed_alert_evaluation import build_reviewed_alert_evaluation
from app.services.retraining_manifest import build_retraining_manifest


_MIN_RECENT_WINDOW = 5
_MIN_SCORE_VARIATION = 3
_LABEL_DRIFT_THRESHOLD = 0.2
_SCORE_DRIFT_THRESHOLD = 0.12
_STATION_CONCENTRATION_DRIFT_THRESHOLD = 0.3
_RECENT_ACTIVITY_WINDOW = timedelta(days=7)


def _safe_delta(reference: float | None, candidate: float | None) -> DriftMetric:
    if reference is None or candidate is None:
        return DriftMetric(reference=reference, candidate=candidate, absolute_delta=None)
    return DriftMetric(
        reference=round(reference, 3),
        candidate=round(candidate, 3),
        absolute_delta=round(abs(candidate - reference), 3),
    )


def _mean_score(alerts: list[AnomalyAlert]) -> float | None:
    if not alerts:
        return None
    return sum(alert.score for alert in alerts) / len(alerts)


def _top_station_share(alerts: list[AnomalyAlert]) -> float | None:
    if not alerts:
        return None
    counts = Counter(alert.station_id for alert in alerts)
    return max(counts.values()) / len(alerts)


def _label_share(alerts: list[AnomalyAlert], label: str) -> float | None:
    if not alerts:
        return None
    return sum(1 for alert in alerts if alert.review_label == label) / len(alerts)


def _split_windows(alerts: list[AnomalyAlert], recent_count: int) -> tuple[list[AnomalyAlert], list[AnomalyAlert]]:
    if not alerts:
        return [], []

    ordered = sorted(alerts, key=lambda item: (item.reviewed_at or item.timestamp, item.id))
    if len(ordered) == 1:
        return [], ordered

    candidate_count = min(max(1, recent_count), len(ordered) - 1)
    if candidate_count * 2 >= len(ordered):
        candidate_count = max(1, len(ordered) // 3)

    if candidate_count <= 0:
        candidate_count = 1

    reference = ordered[:-candidate_count]
    candidate = ordered[-candidate_count:]
    return reference, candidate


def build_reviewed_alert_readiness(
    *,
    alerts: list[AnomalyAlert],
    station_id: str | None,
    since_minutes: int | None,
    limit: int,
    recent_count: int,
) -> ReviewedAlertReadinessResponse:
    manifest = build_retraining_manifest(
        alerts=alerts,
        label=None,
        station_id=station_id,
        since_minutes=since_minutes,
        limit=limit,
    )
    evaluation = build_reviewed_alert_evaluation(
        alerts=alerts,
        station_id=station_id,
        since_minutes=since_minutes,
    )
    reference_alerts, candidate_alerts = _split_windows(alerts, recent_count)

    label_distribution_shift = {
        label: _safe_delta(_label_share(reference_alerts, label), _label_share(candidate_alerts, label))
        for label in ("true_anomaly", "false_positive")
    }
    mean_score_shift = _safe_delta(_mean_score(reference_alerts), _mean_score(candidate_alerts))
    station_concentration_shift = _safe_delta(_top_station_share(reference_alerts), _top_station_share(candidate_alerts))

    warnings = list(dict.fromkeys([*manifest.warnings, *evaluation.warnings]))
    latest_reviewed_at = manifest.latest_reviewed_at
    unique_scores = {round(alert.score, 3) for alert in alerts}

    drift_ready = len(reference_alerts) >= 10 and len(candidate_alerts) >= _MIN_RECENT_WINDOW
    if not drift_ready:
        warnings.append("Not enough reviewed history to compare recent drift reliably; keep collecting labeled alerts.")

    label_drift_value = max(
        [
            metric.absolute_delta or 0.0
            for metric in label_distribution_shift.values()
        ],
        default=0.0,
    )
    score_drift_value = mean_score_shift.absolute_delta or 0.0
    station_drift_value = station_concentration_shift.absolute_delta or 0.0

    if drift_ready and label_drift_value >= _LABEL_DRIFT_THRESHOLD:
        warnings.append("Recent reviewed labels are drifting from the baseline mix, so retraining now may lock in a short-lived pattern.")
    if drift_ready and score_drift_value >= _SCORE_DRIFT_THRESHOLD:
        warnings.append("Recent reviewed alert scores shifted noticeably from the baseline, so threshold stability should be reviewed before retraining.")
    if drift_ready and station_drift_value >= _STATION_CONCENTRATION_DRIFT_THRESHOLD:
        warnings.append("Recent reviews are concentrating around a narrower set of stations than the baseline, so retraining may overfit to a local incident.")

    checks = [
        ReadinessCheck(
            key="minimum_samples",
            passed=manifest.count >= 20,
            detail=f"{manifest.count} reviewed alerts available.",
        ),
        ReadinessCheck(
            key="label_balance",
            passed=manifest.label_counts.get("true_anomaly", 0) >= 5 and manifest.label_counts.get("false_positive", 0) >= 5,
            detail=(
                f"true_anomaly={manifest.label_counts.get('true_anomaly', 0)}, "
                f"false_positive={manifest.label_counts.get('false_positive', 0)}."
            ),
        ),
        ReadinessCheck(
            key="station_coverage",
            passed=len(manifest.station_counts) >= 2,
            detail=f"{len(manifest.station_counts)} stations represented in reviewed alerts.",
        ),
        ReadinessCheck(
            key="recent_review_activity",
            passed=bool(
                latest_reviewed_at is not None
                and latest_reviewed_at >= datetime.now(timezone.utc) - _RECENT_ACTIVITY_WINDOW
                and len(candidate_alerts) >= _MIN_RECENT_WINDOW
            ),
            detail=(
                "Recent window has "
                f"{len(candidate_alerts)} labeled alerts and latest review at "
                f"{latest_reviewed_at.isoformat() if latest_reviewed_at else 'n/a'}."
            ),
        ),
        ReadinessCheck(
            key="score_variation",
            passed=len(unique_scores) >= _MIN_SCORE_VARIATION,
            detail=f"{len(unique_scores)} unique alert scores in the reviewed dataset.",
        ),
        ReadinessCheck(
            key="distribution_stability",
            passed=bool(
                drift_ready
                and label_drift_value < _LABEL_DRIFT_THRESHOLD
                and score_drift_value < _SCORE_DRIFT_THRESHOLD
                and station_drift_value < _STATION_CONCENTRATION_DRIFT_THRESHOLD
            ),
            detail=(
                f"label drift={round(label_drift_value, 3)}, "
                f"score drift={round(score_drift_value, 3)}, "
                f"station concentration drift={round(station_drift_value, 3)}."
            ),
        ),
    ]

    passed_count = sum(1 for check in checks if check.passed)
    readiness_score = round((passed_count / len(checks)) * 100) if checks else 0

    if all(check.passed for check in checks):
        recommendation = "ready"
    elif manifest.count >= 10 and passed_count >= 4:
        recommendation = "monitor"
    else:
        recommendation = "hold"

    return ReviewedAlertReadinessResponse(
        generated_at=datetime.now(timezone.utc),
        count=manifest.count,
        station_id=station_id,
        since_minutes=since_minutes,
        recent_window_count=len(candidate_alerts),
        reference_window_count=len(reference_alerts),
        ready_for_training=recommendation == "ready",
        recommendation=recommendation,
        readiness_score=readiness_score,
        current_precision=evaluation.current_precision,
        recommended_threshold=evaluation.recommended_threshold,
        label_counts=manifest.label_counts,
        station_counts=manifest.station_counts,
        checks=checks,
        label_distribution_shift=label_distribution_shift,
        mean_score_shift=mean_score_shift,
        station_concentration_shift=station_concentration_shift,
        warnings=warnings,
    )
