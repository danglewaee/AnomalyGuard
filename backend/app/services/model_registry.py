from app.schemas import (
    ModelRegistryEntrySummary,
    ModelRegistryEventEntry,
)
from app.services.store_pg import PostgresStore


_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "prepared": {"shadow"},
    "shadow": {"canary", "rolled_back"},
    "canary": {"rolled_back"},
    "rolled_back": set(),
}


def register_retraining_candidate(
    store: PostgresStore,
    *,
    job_id: str,
    actor: str,
    bundle: dict,
) -> ModelRegistryEntrySummary:
    manifest = bundle.get("manifest") or {}
    promotion_gate = bundle.get("promotion_gate") or {}
    readiness = bundle.get("readiness") or {}
    evaluation = bundle.get("evaluation") or {}

    manifest_id = str(manifest.get("manifest_id") or "").strip()
    if not manifest_id:
        raise ValueError("Retraining bundle is missing manifest_id.")

    return store.upsert_model_registry_entry(
        manifest_id=manifest_id,
        job_id=job_id,
        promotion_decision=str(promotion_gate.get("promotion_decision") or "blocked"),
        approve_for_shadow=bool(promotion_gate.get("approve_for_shadow")),
        approve_for_canary=bool(promotion_gate.get("approve_for_canary")),
        station_id=manifest.get("station_id"),
        since_minutes=manifest.get("since_minutes"),
        recommendation=str(readiness.get("recommendation") or bundle.get("recommendation") or "hold"),
        readiness_score=int(readiness.get("readiness_score") or 0),
        current_precision=evaluation.get("current_precision"),
        recommended_threshold=evaluation.get("recommended_threshold"),
        reviewed_count=int(manifest.get("count") or 0),
        blocker_count=len(promotion_gate.get("blockers") or []),
        warning_count=len(promotion_gate.get("warnings") or []),
        mlflow_run_id=str(bundle.get("mlflow_run_id") or ""),
        run_name=str(bundle.get("run_name") or ""),
        status_note=str(
            bundle.get("ingest_note")
            or f"Prepared candidate {manifest_id} with promotion gate {promotion_gate.get('promotion_decision') or 'blocked'}."
        ),
        changed_by=actor,
        bundle_payload=bundle,
    )


def list_registry_entries(
    store: PostgresStore,
    *,
    limit: int,
    state: str | None = None,
) -> list[ModelRegistryEntrySummary]:
    return store.list_model_registry_entries(limit=limit, state=state)


def get_registry_history(
    store: PostgresStore,
    *,
    manifest_id: str,
    limit: int,
) -> list[ModelRegistryEventEntry]:
    return store.model_registry_history(manifest_id, limit=limit)


def transition_registry_entry(
    store: PostgresStore,
    *,
    manifest_id: str,
    target_state: str,
    actor: str,
    note: str,
) -> ModelRegistryEntrySummary:
    entry = store.get_model_registry_entry(manifest_id)
    if entry is None:
        raise LookupError("Model registry entry not found.")

    allowed_targets = _ALLOWED_TRANSITIONS.get(entry.state, set())
    if target_state not in allowed_targets:
        raise ValueError(f"Cannot move candidate from {entry.state} to {target_state}.")

    if target_state == "shadow" and not entry.approve_for_shadow:
        raise ValueError("Promotion gate does not approve this candidate for shadow mode.")
    if target_state == "canary" and not entry.approve_for_canary:
        raise ValueError("Promotion gate does not approve this candidate for canary rollout.")

    transition_note = note.strip()
    if not transition_note:
        if target_state == "rolled_back":
            transition_note = "Rolled back by operator."
        elif target_state == "shadow":
            transition_note = "Promoted to shadow mode."
        else:
            transition_note = "Promoted to canary rollout."

    updated = store.update_model_registry_state(
        manifest_id=manifest_id,
        target_state=target_state,
        changed_by=actor,
        note=transition_note,
        metadata_payload={
            "promotion_decision": entry.promotion_decision,
            "approve_for_shadow": entry.approve_for_shadow,
            "approve_for_canary": entry.approve_for_canary,
        },
    )
    if updated is None:
        raise LookupError("Model registry entry not found.")
    return updated
