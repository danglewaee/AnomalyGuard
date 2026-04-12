from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import WaterQualityForecastResponse
from app.services.alert_pipeline import ensure_valid_station
from app.services.forecasting import build_water_quality_forecast
from app.services.stations import default_station_id
from app.services.store_pg import PostgresStore


router = APIRouter()


def _validated_horizons(values: list[int]) -> list[int]:
    if not values:
        return [6, 12, 24]
    invalid = [value for value in values if value < 1 or value > 168]
    if invalid:
        raise HTTPException(status_code=422, detail="horizon_hours must be between 1 and 168")
    return sorted(set(values))


@router.get("/api/forecasts/water-quality", response_model=WaterQualityForecastResponse)
def water_quality_forecast(
    station_id: str | None = Query(default=None),
    since_minutes: int | None = Query(default=10080, ge=30, le=43200),
    limit: int = Query(default=1000, ge=2, le=5000),
    horizon_hours: list[int] = Query(default=[6, 12, 24]),
    method: Literal["auto", "persistence", "moving_average", "lag_linear", "lstm"] = Query(default="auto"),
    db: Session = Depends(get_db),
) -> dict:
    station_id = station_id or default_station_id()
    ensure_valid_station(station_id)
    readings = PostgresStore(db).latest_readings(
        limit=limit,
        station_id=station_id,
        since_minutes=since_minutes,
    )
    forecast = build_water_quality_forecast(
        readings,
        station_id=station_id,
        horizon_hours=_validated_horizons(horizon_hours),
        method=method,
    )
    return forecast.model_dump(mode="json")
