from datetime import datetime, timezone

from app.schemas import (
    PromotionGateCheck,
    RetrainingManifestResponse,
    ReviewedAlertEvaluationResponse,
    ReviewedAlertPromotionGateResponse,
    ReviewedAlertReadinessResponse,
)


_PRECISION_FLOOR = 0.65
_LABEL_DRIFT_BLOCK_THRESHOLD = 0.35
_SCORE_DRIFT_BLOCK_THRESHOLD = 0.2
_STATION_DRIFT_BLOCK_THRESHOLD = 0.45


def _format_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{round(value * 100)}%"


def _round_score(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}"


def build_reviewed_alert_promotion_gate(
    *,
    manifest: RetrainingManifestResponse,
    evaluation: ReviewedAlertEvaluationResponse,
    readiness: ReviewedAlertReadinessResponse,
) -> ReviewedAlertPromotionGateResponse:
    label_drift = max(
        [
            metric.absolute_delta or 0.0
            for metric in readiness.label_distribution_shift.values()
        ],
        default=0.0,
    )
    score_drift = readiness.mean_score_shift.absolute_delta or 0.0 if readiness.mean_score_shift else 0.0
    station_drift = readiness.station_concentration_shift.absolute_delta or 0.0 if readiness.station_concentration_shift else 0.0
    threshold_metrics = evaluation.recommended_threshold_metrics

    checks = [
        PromotionGateCheck(
            key="dataset_readiness",
            passed=readiness.recommendation == "ready",
            severity="blocker" if readiness.recommendation == "hold" else "warning",
            detail=(
                f"Readiness recommendation is {readiness.recommendation} "
                f"with score {readiness.readiness_score}."
            ),
        ),
        PromotionGateCheck(
            key="precision_floor",
            passed=(evaluation.current_precision or 0.0) >= _PRECISION_FLOOR,
            severity="blocker",
            detail=(
                f"Current reviewed precision is {_format_pct(evaluation.current_precision)}; "
                f"promotion floor is {_format_pct(_PRECISION_FLOOR)}."
            ),
        ),
        PromotionGateCheck(
            key="label_balance",
            passed=manifest.label_counts.get("true_anomaly", 0) >= 5 and manifest.label_counts.get("false_positive", 0) >= 5,
            severity="blocker",
            detail=(
                f"true_anomaly={manifest.label_counts.get('true_anomaly', 0)}, "
                f"false_positive={manifest.label_counts.get('false_positive', 0)}."
            ),
        ),
        PromotionGateCheck(
            key="station_diversity",
            passed=len(manifest.station_counts) >= 2,
            severity="blocker",
            detail=f"{len(manifest.station_counts)} stations represented in the reviewed dataset.",
        ),
        PromotionGateCheck(
            key="threshold_evidence",
            passed=bool(
                threshold_metrics is not None
                and threshold_metrics.precision is not None
                and threshold_metrics.predicted_positive_count >= 5
                and (evaluation.current_precision is None or threshold_metrics.precision >= evaluation.current_precision)
            ),
            severity="warning",
            detail=(
                "Recommended threshold "
                f"{_round_score(evaluation.recommended_threshold)} has precision "
                f"{_format_pct(threshold_metrics.precision if threshold_metrics is not None else None)} "
                f"over {threshold_metrics.predicted_positive_count if threshold_metrics is not None else 0} alerts."
            ),
        ),
        PromotionGateCheck(
            key="drift_guard",
            passed=(
                label_drift < _LABEL_DRIFT_BLOCK_THRESHOLD
                and score_drift < _SCORE_DRIFT_BLOCK_THRESHOLD
                and station_drift < _STATION_DRIFT_BLOCK_THRESHOLD
            ),
            severity="warning",
            detail=(
                f"label drift={round(label_drift, 3)}, "
                f"score drift={round(score_drift, 3)}, "
                f"station concentration drift={round(station_drift, 3)}."
            ),
        ),
    ]

    blockers = [check.detail for check in checks if not check.passed and check.severity == "blocker"]
    warnings = [check.detail for check in checks if not check.passed and check.severity == "warning"]
    warnings = list(dict.fromkeys([*warnings, *manifest.warnings, *evaluation.warnings, *readiness.warnings]))

    required_actions: list[str] = []
    if readiness.recommendation == "hold":
        required_actions.append("Collect more reviewed alerts until readiness moves out of hold.")
    elif readiness.recommendation == "monitor":
        required_actions.append("Keep the candidate in shadow mode until readiness improves from monitor to ready.")
    if (evaluation.current_precision or 0.0) < _PRECISION_FLOOR:
        required_actions.append("Raise reviewed precision above 65% before promoting a candidate.")
    if manifest.label_counts.get("true_anomaly", 0) < 5 or manifest.label_counts.get("false_positive", 0) < 5:
        required_actions.append("Add at least 5 reviewed alerts for both true_anomaly and false_positive labels.")
    if len(manifest.station_counts) < 2:
        required_actions.append("Label alerts from at least two stations before promotion to avoid local overfit.")
    if label_drift >= _LABEL_DRIFT_BLOCK_THRESHOLD or station_drift >= _STATION_DRIFT_BLOCK_THRESHOLD:
        required_actions.append("Wait for label mix and station concentration to stabilize before promotion.")
    if threshold_metrics is None or threshold_metrics.predicted_positive_count < 5:
        required_actions.append("Collect more reviewed positives so the recommended threshold has stronger support.")
    required_actions = list(dict.fromkeys(required_actions))

    if blockers:
        promotion_decision = "blocked"
        approve_for_shadow = False
        approve_for_canary = False
    elif warnings:
        promotion_decision = "shadow"
        approve_for_shadow = True
        approve_for_canary = False
    else:
        promotion_decision = "canary"
        approve_for_shadow = True
        approve_for_canary = True

    precision_rollback_floor = max(0.60, round((evaluation.current_precision or 0.60) - 0.08, 3))
    false_positive_share = 0.0
    if manifest.count > 0:
        false_positive_share = manifest.label_counts.get("false_positive", 0) / manifest.count
    rollback_triggers = [
        f"Rollback if reviewed precision drops below {_format_pct(precision_rollback_floor)} in two consecutive evaluation windows.",
        f"Rollback if false-positive share rises above {_format_pct(min(false_positive_share + 0.15, 0.9))}.",
        f"Rollback if mean alert score shifts by {max(score_drift, 0.12):.3f} or more after promotion.",
        f"Rollback if top-station concentration rises by {max(station_drift, 0.25):.3f} or more after promotion.",
    ]

    return ReviewedAlertPromotionGateResponse(
        generated_at=datetime.now(timezone.utc),
        station_id=manifest.station_id,
        since_minutes=manifest.since_minutes,
        promotion_decision=promotion_decision,
        approve_for_shadow=approve_for_shadow,
        approve_for_canary=approve_for_canary,
        checks=checks,
        blockers=blockers,
        warnings=warnings,
        required_actions=required_actions,
        rollback_triggers=rollback_triggers,
    )
