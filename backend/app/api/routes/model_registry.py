from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import require_admin
from app.runtime import broadcast
from app.schemas import ModelRegistryEntrySummary, ModelRegistryEventEntry, ModelRegistryTransitionRequest
from app.services.model_registry import get_registry_history, list_registry_entries, transition_registry_entry
from app.services.store_pg import PostgresStore


router = APIRouter()


@router.get("/api/model-registry", response_model=list[ModelRegistryEntrySummary])
def model_registry_entries(
    limit: int = Query(default=12, ge=1, le=100),
    state: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
) -> list[dict]:
    return [entry.model_dump(mode="json") for entry in list_registry_entries(PostgresStore(db), limit=limit, state=state)]


@router.get("/api/model-registry/{manifest_id}/history", response_model=list[ModelRegistryEventEntry])
def model_registry_history(
    manifest_id: str,
    limit: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
) -> list[dict]:
    store = PostgresStore(db)
    if store.get_model_registry_entry(manifest_id) is None:
        raise HTTPException(status_code=404, detail="Model registry entry not found")
    return [entry.model_dump(mode="json") for entry in get_registry_history(store, manifest_id=manifest_id, limit=limit)]


@router.post("/api/model-registry/{manifest_id}/transition", response_model=ModelRegistryEntrySummary)
async def transition_model_registry_state(
    manifest_id: str,
    payload: ModelRegistryTransitionRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> dict:
    try:
        updated = transition_registry_entry(
            PostgresStore(db),
            manifest_id=manifest_id,
            target_state=payload.target_state,
            actor=user.get("sub", "admin"),
            note=payload.note,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    response = updated.model_dump(mode="json")
    await broadcast("model_registry_state", response)
    return response
