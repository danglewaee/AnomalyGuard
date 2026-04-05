import hashlib
import json
import secrets
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.schemas import DeviceCredentialAuditEntry, DeviceCredentialRotateResponse, DeviceCredentialSummary
from app.services.device_auth import load_device_key_registry, reset_device_key_registry_cache
from app.services.store_pg import PostgresStore


def device_key_fingerprint(device_key: str) -> str:
    return hashlib.sha256(device_key.encode("utf-8")).hexdigest()[:16]


def list_device_credentials(db: Session) -> list[DeviceCredentialSummary]:
    registry = load_device_key_registry()
    events = PostgresStore(db).device_credential_events(limit=max(100, len(registry) * 10 or 100))
    latest_by_station = _latest_event_by_station(events)
    return [
        DeviceCredentialSummary(
            station_id=station_id,
            key_fingerprint=device_key_fingerprint(device_key),
            last_event_type=latest_by_station[station_id].event_type if station_id in latest_by_station else "",
            last_rotated_at=latest_by_station[station_id].created_at if station_id in latest_by_station else None,
            last_rotated_by=latest_by_station[station_id].actor if station_id in latest_by_station else "",
            registry_managed=True,
        )
        for station_id, device_key in sorted(registry.items())
    ]


def audit_device_credentials(
    db: Session,
    *,
    station_id: str | None = None,
    limit: int = 100,
) -> list[DeviceCredentialAuditEntry]:
    return PostgresStore(db).device_credential_events(station_id=station_id, limit=limit)


def rotate_device_key(
    db: Session,
    *,
    station_id: str,
    rotated_by: str,
    note: str = "",
) -> DeviceCredentialRotateResponse:
    registry = load_device_key_registry()
    registry_path = _require_registry_path()
    event_type = "rotated" if station_id in registry else "provisioned"
    issued_key = secrets.token_urlsafe(24)
    registry[station_id] = issued_key
    _write_registry(registry_path, registry)
    reset_device_key_registry_cache()
    fingerprint = device_key_fingerprint(issued_key)
    audit_entry = PostgresStore(db).record_device_credential_event(
        station_id=station_id,
        event_type=event_type,
        actor=rotated_by,
        key_fingerprint=fingerprint,
        note=note,
        metadata_payload={"registry_path": str(registry_path)},
    )
    return DeviceCredentialRotateResponse(
        station_id=station_id,
        issued_key=issued_key,
        key_fingerprint=fingerprint,
        event_type=event_type,
        rotated_at=audit_entry.created_at,
        rotated_by=rotated_by,
        note=note,
    )


def revoke_device_key(
    db: Session,
    *,
    station_id: str,
    revoked_by: str,
    note: str = "",
) -> DeviceCredentialAuditEntry:
    registry = load_device_key_registry()
    registry_path = _require_registry_path()
    if station_id not in registry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device credential not found")

    removed_key = registry.pop(station_id)
    _write_registry(registry_path, registry)
    reset_device_key_registry_cache()
    return PostgresStore(db).record_device_credential_event(
        station_id=station_id,
        event_type="revoked",
        actor=revoked_by,
        key_fingerprint=device_key_fingerprint(removed_key),
        note=note,
        metadata_payload={"registry_path": str(registry_path)},
    )


def _latest_event_by_station(events: list[DeviceCredentialAuditEntry]) -> dict[str, DeviceCredentialAuditEntry]:
    latest: dict[str, DeviceCredentialAuditEntry] = {}
    for event in events:
        latest.setdefault(event.station_id, event)
    return latest


def _require_registry_path() -> Path:
    if not settings.device_keys_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Device credential registry is not configured",
        )
    return Path(settings.device_keys_path)


def _write_registry(path: Path, registry: dict[str, str]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        temp_path.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")
        temp_path.replace(path)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Device credential registry is not writable",
        ) from exc
