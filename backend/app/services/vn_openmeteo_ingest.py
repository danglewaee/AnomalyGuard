from datetime import datetime
from typing import Any

import httpx

from app.schemas import StationProfile, WaterReading
from app.services.stations import get_station

FLOOD_URL = "https://flood-api.open-meteo.com/v1/flood"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_api_station(station_id: str) -> StationProfile:
    base = get_station(station_id)
    return StationProfile(
        station_id=base.station_id,
        station_name=base.station_name,
        region=base.region,
        timezone="Asia/Ho_Chi_Minh",
        latitude=base.latitude,
        longitude=base.longitude,
        source="api",
    )


def fetch_vn_openmeteo_readings(station_id: str, days: int = 30) -> tuple[StationProfile, list[WaterReading]]:
    station = _build_api_station(station_id)

    flood_params = {
        "latitude": station.latitude,
        "longitude": station.longitude,
        "daily": "river_discharge",
        "past_days": max(1, min(days, 92)),
        "forecast_days": 0,
        "timezone": "UTC",
    }

    weather_params = {
        "latitude": station.latitude,
        "longitude": station.longitude,
        "daily": "temperature_2m_mean",
        "past_days": max(1, min(days, 92)),
        "forecast_days": 0,
        "timezone": "UTC",
    }

    with httpx.Client(timeout=20.0) as client:
        flood_resp = client.get(FLOOD_URL, params=flood_params)
        flood_resp.raise_for_status()
        flood_body = flood_resp.json()

        weather_resp = client.get(WEATHER_URL, params=weather_params)
        weather_resp.raise_for_status()
        weather_body = weather_resp.json()

    times = flood_body.get("daily", {}).get("time", [])
    flows = flood_body.get("daily", {}).get("river_discharge", [])

    wt_times = weather_body.get("daily", {}).get("time", [])
    wt_values = weather_body.get("daily", {}).get("temperature_2m_mean", [])
    temp_map = {t: _to_float(v, 27.0) for t, v in zip(wt_times, wt_values)}

    if not times or not flows:
        raise ValueError("No VN flood data returned from Open-Meteo.")

    flow_values = [_to_float(v, 0.0) for v in flows]
    min_flow = min(flow_values)
    max_flow = max(flow_values)
    span = max(max_flow - min_flow, 1e-6)

    readings: list[WaterReading] = []
    for day, flow_m3s in zip(times, flow_values):
        norm = (flow_m3s - min_flow) / span
        temp_c = temp_map.get(day, 27.0)

        # Derived proxy fields from real river discharge + temperature.
        turbidity = 1.5 + norm * 12.0
        tds = 220.0 + (1.0 - norm) * 180.0
        ph = 7.4 - (norm - 0.5) * 0.5
        do = 9.8 - 0.12 * temp_c + norm * 1.2

        readings.append(
            WaterReading(
                timestamp=datetime.fromisoformat(f"{day}T00:00:00+00:00"),
                station_id=station.station_id,
                ph=round(ph, 3),
                tds=round(tds, 2),
                turbidity=round(max(0.0, turbidity), 3),
                temperature_c=round(temp_c, 2),
                do_mg_l=round(max(0.0, do), 2),
                flow_l_min=round(flow_m3s * 1000.0 * 60.0, 2),
            )
        )

    return station, readings
