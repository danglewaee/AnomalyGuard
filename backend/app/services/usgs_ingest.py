from collections import defaultdict
from datetime import datetime
from typing import Any

import httpx

from app.schemas import StationProfile, WaterReading

USGS_URL = "https://waterservices.usgs.gov/nwis/iv/"

PARAM_CODES = {
    "00010": "temperature_c",
    "00300": "do_mg_l",
    "00400": "ph",
    "63680": "turbidity",
    "00095": "specific_conductance",
    "00060": "flow_cfs",
}


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_station(site_no: str, ts_item: dict[str, Any]) -> StationProfile:
    info = ts_item.get("sourceInfo", {})
    coords = info.get("geoLocation", {}).get("geogLocation", {})
    site_name = info.get("siteName", f"USGS Site {site_no}")
    lat = _to_float(coords.get("latitude")) or 0.0
    lon = _to_float(coords.get("longitude")) or 0.0

    return StationProfile(
        station_id=f"usgs-{site_no}",
        station_name=site_name,
        region="USGS Water Services",
        timezone="America/New_York",
        latitude=lat,
        longitude=lon,
        source="api",
    )


def fetch_usgs_readings(site_no: str, hours: int = 24) -> tuple[StationProfile, list[WaterReading]]:
    params = {
        "format": "json",
        "sites": site_no,
        "period": f"PT{max(1, min(hours, 168))}H",
        "parameterCd": "00010,00300,00400,63680,00095,00060",
    }

    with httpx.Client(timeout=20.0) as client:
        response = client.get(USGS_URL, params=params)
        response.raise_for_status()
        body = response.json()

    ts_list = body.get("value", {}).get("timeSeries", [])
    if not ts_list:
        raise ValueError("No timeSeries returned from USGS for this site.")

    station = _build_station(site_no, ts_list[0])

    points: dict[str, dict[str, float]] = defaultdict(dict)

    for series in ts_list:
        variable_code = (
            series.get("variable", {})
            .get("variableCode", [{}])[0]
            .get("value", "")
        )
        mapped = PARAM_CODES.get(variable_code)
        if not mapped:
            continue

        values = series.get("values", [])
        if not values:
            continue

        for item in values[0].get("value", []):
            ts = item.get("dateTime")
            value = _to_float(item.get("value"))
            if not ts or value is None:
                continue
            points[ts][mapped] = value

    readings: list[WaterReading] = []
    for ts, values in sorted(points.items()):
        specific_conductance = values.get("specific_conductance", 0.0)
        tds = specific_conductance * 0.65 if specific_conductance else 0.0
        flow_l_min = values.get("flow_cfs", 0.0) * 28.3168 * 60.0

        if "ph" not in values:
            continue

        readings.append(
            WaterReading(
                timestamp=datetime.fromisoformat(ts.replace("Z", "+00:00")),
                station_id=station.station_id,
                ph=round(values.get("ph", 7.0), 3),
                tds=round(tds, 2),
                turbidity=round(values.get("turbidity", 0.0), 3),
                temperature_c=round(values.get("temperature_c", 0.0), 2),
                do_mg_l=round(values.get("do_mg_l", 0.0), 2),
                flow_l_min=round(flow_l_min, 2),
            )
        )

    return station, readings
