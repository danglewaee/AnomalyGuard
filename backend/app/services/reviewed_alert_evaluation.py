from collections import Counter
from datetime import datetime, timezone

from app.schemas import (
    AnomalyAlert,
    ReviewedAlertEvaluationResponse,
    SeverityEvaluationBreakdown,
    ThresholdEvaluationPoint,
)


CURRENT_ALERT_THRESHOLD = 0.45


def _safe_divide(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 3)


def _f1_score(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None or precision + recall == 0:
        return None
    return round((2 * precision * recall) / (precision + recall), 3)


def _severity_breakdown(alerts: list[AnomalyAlert]) -> dict[str, SeverityEvaluationBreakdown]:
    by_severity: dict[str, list[AnomalyAlert]] = {"low": [], "medium": [], "high": []}
    for alert in alerts:
        by_severity.setdefault(alert.severity, []).append(alert)

    breakdown: dict[str, SeverityEvaluationBreakdown] = {}
    for severity, items in by_severity.items():
        true_count = sum(1 for item in items if item.review_label == "true_anomaly")
        false_count = sum(1 for item in items if item.review_label == "false_positive")
        breakdown[severity] = SeverityEvaluationBreakdown(
            reviewed_count=len(items),
            true_anomaly=true_count,
            false_positive=false_count,
            precision=_safe_divide(true_count, len(items)),
        )
    return breakdown


def _threshold_points(alerts: list[AnomalyAlert]) -> list[ThresholdEvaluationPoint]:
    positives = sum(1 for alert in alerts if alert.review_label == "true_anomaly")
    candidate_thresholds = sorted({CURRENT_ALERT_THRESHOLD, *[round(alert.score, 3) for alert in alerts]}, reverse=True)
    points: list[ThresholdEvaluationPoint] = []

    for threshold in candidate_thresholds:
        predicted_positive = [alert for alert in alerts if alert.score >= threshold]
        tp = sum(1 for alert in predicted_positive if alert.review_label == "true_anomaly")
        fp = sum(1 for alert in predicted_positive if alert.review_label == "false_positive")
        precision = _safe_divide(tp, len(predicted_positive))
        recall = _safe_divide(tp, positives)
        points.append(
            ThresholdEvaluationPoint(
                threshold=round(threshold, 3),
                predicted_positive_count=len(predicted_positive),
                true_positive=tp,
                false_positive=fp,
                precision=precision,
                recall=recall,
                f1=_f1_score(precision, recall),
            )
        )

    return points


def build_reviewed_alert_evaluation(
    *,
    alerts: list[AnomalyAlert],
    station_id: str | None,
    since_minutes: int | None,
) -> ReviewedAlertEvaluationResponse:
    label_counts = Counter(alert.review_label or "unlabeled" for alert in alerts)
    threshold_sweep = _threshold_points(alerts)
    recommended_point = None
    if threshold_sweep:
        recommended_point = max(
            threshold_sweep,
            key=lambda point: (
                point.f1 if point.f1 is not None else -1.0,
                point.precision if point.precision is not None else -1.0,
                point.threshold,
            ),
        )

    warnings: list[str] = []
    if len(alerts) < 20:
        warnings.append("Fewer than 20 reviewed alerts are available, so offline evaluation is still statistically weak.")
    if label_counts.get("true_anomaly", 0) == 0 or label_counts.get("false_positive", 0) == 0:
        warnings.append("Reviewed alerts currently contain only one label class, so threshold tuning is incomplete.")
    if len({round(alert.score, 3) for alert in alerts}) <= 1 and alerts:
        warnings.append("Alert scores show little variation across reviewed alerts, so threshold recommendations may not be meaningful.")

    return ReviewedAlertEvaluationResponse(
        generated_at=datetime.now(timezone.utc),
        count=len(alerts),
        station_id=station_id,
        since_minutes=since_minutes,
        current_alert_threshold=CURRENT_ALERT_THRESHOLD,
        current_precision=_safe_divide(label_counts.get("true_anomaly", 0), len(alerts)),
        label_counts=dict(label_counts),
        severity_breakdown=_severity_breakdown(alerts),
        recommended_threshold=recommended_point.threshold if recommended_point is not None else None,
        recommended_threshold_metrics=recommended_point,
        threshold_sweep=threshold_sweep,
        warnings=warnings,
    )
