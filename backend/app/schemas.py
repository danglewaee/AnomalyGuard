from datetime import datetime
from typing import Dict, List, Literal

from pydantic import BaseModel, Field


class StationProfile(BaseModel):
    station_id: str
    station_name: str
    region: str
    timezone: str
    latitude: float
    longitude: float
    source: Literal["simulated", "mqtt", "csv", "api"] = "simulated"


class WaterReading(BaseModel):
    timestamp: datetime
    station_id: str = Field(default="mekong-can-tho")
    ph: float
    tds: float
    turbidity: float
    temperature_c: float
    do_mg_l: float
    flow_l_min: float


class AnomalyAlert(BaseModel):
    id: str
    timestamp: datetime
    station_id: str
    severity: Literal["low", "medium", "high"]
    score: float
    reasons: List[str]
    feature_contributions: Dict[str, float]
