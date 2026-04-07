from datetime import datetime, timezone

from app.schemas import AnomalyAlert
from app.services.mlflow_logger import log_retraining_run_metrics
from app.services.reviewed_alert_evaluation import build_reviewed_alert_evaluation
from app.services.reviewed_alert_promotion_gate import build_reviewed_alert_promotion_gate
from app.services.reviewed_alert_readiness import build_reviewed_alert_readiness
from app.services.retraining_manifest import build_retraining_manifest


def _drift_delta(metric) -> float | None:
    if metric is None:
        return None
    return getattr(metric, "absolute_delta", None)


def build_reviewed_alert_training_run(
    *,
    alerts: list[AnomalyAlert],
    station_id: str | None,
    since_minutes: int | None,
    limit: int,
    recent_count: int,
) -> dict:
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
    readiness = build_reviewed_alert_readiness(
        alerts=alerts,
        station_id=station_id,
        since_minutes=since_minutes,
        limit=limit,
        recent_count=recent_count,
    )
    promotion_gate = build_reviewed_alert_promotion_gate(
        manifest=manifest,
        evaluation=evaluation,
        readiness=readiness,
    )

    run_name = f"retraining-prep-{manifest.fingerprint[:10]}"
    mlflow_run_id = log_retraining_run_metrics(
        run_name=run_name,
        manifest_id=manifest.manifest_id,
        station_id=station_id,
        since_minutes=since_minutes,
        readiness_score=readiness.readiness_score,
        recommendation=readiness.recommendation,
        current_precision=evaluation.current_precision,
        recommended_threshold=evaluation.recommended_threshold,
        label_counts=manifest.label_counts,
        drift_metrics={
            "true_label_drift": _drift_delta(readiness.label_distribution_shift.get("true_anomaly")),
            "false_label_drift": _drift_delta(readiness.label_distribution_shift.get("false_positive")),
            "mean_score_shift": _drift_delta(readiness.mean_score_shift),
            "station_concentration_shift": _drift_delta(readiness.station_concentration_shift),
        },
        promotion_decision=promotion_gate.promotion_decision,
        approve_for_canary=promotion_gate.approve_for_canary,
        blocker_count=len(promotion_gate.blockers),
    )

    return {
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "run_name": run_name,
        "mlflow_run_id": mlflow_run_id,
        "manifest": manifest.model_dump(mode="json"),
        "evaluation": evaluation.model_dump(mode="json"),
        "readiness": readiness.model_dump(mode="json"),
        "promotion_gate": promotion_gate.model_dump(mode="json"),
        "ready_for_training": readiness.ready_for_training,
        "recommendation": readiness.recommendation,
        "recommended_threshold": evaluation.recommended_threshold,
        "current_precision": evaluation.current_precision,
        "export_urls": manifest.export_urls,
        "suggested_split": manifest.suggested_split,
        "ingest_note": (
            f"Prepared retraining bundle {manifest.manifest_id} "
            f"with recommendation {readiness.recommendation} over {manifest.count} reviewed alerts."
        ),
        "source": "reviewed-alert-training-run",
    }
