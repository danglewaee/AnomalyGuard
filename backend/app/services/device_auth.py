import json
import secrets
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException, status

from app.config import settings


@lru_cache(maxsize=1)
def load_device_key_registry() -> dict[str, str]:
    if not settings.device_keys_path:
        return {}

    path = Path(settings.device_keys_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Device key registry not found at {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Device key registry at {path} is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("Device key registry must be a JSON object keyed by station_id")

    return {
        str(station_id): str(device_key)
        for station_id, device_key in payload.items()
        if str(station_id).strip() and str(device_key).strip()
    }


def reset_device_key_registry_cache() -> None:
    load_device_key_registry.cache_clear()


def validate_device_key(station_id: str, provided_key: str | None) -> None:
    if not provided_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing device key")

    registry = load_device_key_registry()
    expected_key = registry.get(station_id) if registry else settings.device_api_key

    if not expected_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown device identity")

    if not secrets.compare_digest(provided_key, expected_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid device key")
