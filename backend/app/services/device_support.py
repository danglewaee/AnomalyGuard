from datetime import datetime, timezone
from typing import Any

from app.schemas import DeviceTelemetry, StationProfile, WaterReading

DEFAULT_DEVICE_CONTROL: dict[str, Any] = {
    "direction": 0,
    "pump": False,
    "isFeeding": False,
    "weight": 100.0,
    "hour": 0,
    "minute": 0,
}


def _clamp_float(value: Any, fallback: float, minimum: float, maximum: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(minimum, min(maximum, numeric))


def _clamp_int(value: Any, fallback: int, minimum: int, maximum: int) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(minimum, min(maximum, numeric))


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def normalize_device_control(raw: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(DEFAULT_DEVICE_CONTROL)
    if not raw:
        return merged

    merged["direction"] = _clamp_int(raw.get("direction"), merged["direction"], 0, 4)
    merged["pump"] = _coerce_bool(raw.get("pump", merged["pump"]))
    merged["isFeeding"] = _coerce_bool(raw.get("isFeeding", merged["isFeeding"]))
    merged["weight"] = _clamp_float(raw.get("weight"), merged["weight"], 0.0, 10_000.0)
    merged["hour"] = _clamp_int(raw.get("hour"), merged["hour"], 0, 23)
    merged["minute"] = _clamp_int(raw.get("minute"), merged["minute"], 0, 59)
    return merged


def normalize_timestamp(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def build_device_station_profile(payload: DeviceTelemetry) -> StationProfile:
    station_id = payload.station_id.strip() or "esp32-device-001"
    return StationProfile(
        station_id=station_id,
        station_name=payload.station_name or f"Device {station_id}",
        region=payload.region or "Edge device station",
        timezone=payload.timezone or "Asia/Ho_Chi_Minh",
        latitude=payload.latitude if payload.latitude is not None else 10.8231,
        longitude=payload.longitude if payload.longitude is not None else 106.6297,
        source="device",
    )


def telemetry_to_reading(payload: DeviceTelemetry, control_state: dict[str, Any]) -> tuple[WaterReading, dict[str, Any]]:
    timestamp = normalize_timestamp(payload.timestamp)
    water_temp = payload.water_temp_c if payload.water_temp_c is not None else payload.temperature_c
    temperature_c = _clamp_float(water_temp, 25.0, -5.0, 80.0)

    inferred_fields: list[str] = []

    if payload.turbidity is None:
        turbidity = round(max(0.2, payload.tds / 80.0), 3)
        inferred_fields.append("turbidity")
    else:
        turbidity = _clamp_float(payload.turbidity, 0.2, 0.0, 5_000.0)

    if payload.do_mg_l is None:
        do_mg_l = round(max(2.0, min(14.0, 14.6 - 0.23 * temperature_c)), 3)
        inferred_fields.append("do_mg_l")
    else:
        do_mg_l = _clamp_float(payload.do_mg_l, 6.0, 0.0, 20.0)

    if payload.flow_l_min is None:
        flow_l_min = round(6.0 if control_state.get("pump") else 1.5, 3)
        inferred_fields.append("flow_l_min")
    else:
        flow_l_min = _clamp_float(payload.flow_l_min, 1.5, 0.0, 10_000.0)

    reading = WaterReading(
        timestamp=timestamp,
        station_id=payload.station_id,
        ph=_clamp_float(payload.ph, 7.0, 0.0, 14.0),
        tds=_clamp_float(payload.tds, 0.0, 0.0, 20_000.0),
        turbidity=turbidity,
        temperature_c=temperature_c,
        do_mg_l=do_mg_l,
        flow_l_min=flow_l_min,
    )

    derived = {
        "temperature_c": temperature_c,
        "turbidity": turbidity,
        "do_mg_l": do_mg_l,
        "flow_l_min": flow_l_min,
        "inferred_fields": inferred_fields,
    }
    return reading, derived


def build_device_telemetry_snapshot(
    payload: DeviceTelemetry,
    control_state: dict[str, Any],
    reading: WaterReading,
    derived: dict[str, Any],
) -> dict[str, Any]:
    return {
        "client_id": payload.client_id or "esp",
        "time": payload.time,
        "ph": reading.ph,
        "tds": reading.tds,
        "ambient_temp_c": payload.temperature_c,
        "humidity": payload.humidity,
        "weight_g": payload.weight_g,
        "water_temp_c": payload.water_temp_c,
        "isFeeding": _coerce_bool(payload.is_feeding),
        "pump": _coerce_bool(control_state.get("pump")),
        "direction": _clamp_int(control_state.get("direction"), 0, 0, 4),
        "inferred_fields": list(derived.get("inferred_fields", [])),
    }
