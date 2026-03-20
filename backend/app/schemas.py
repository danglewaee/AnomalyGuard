from datetime import datetime
from typing import Dict, List, Literal

from pydantic import BaseModel, Field

WaterDataSource = Literal["simulated", "mqtt", "csv", "api"]
WaterUseType = Literal["drinking", "irrigation", "aquaculture", "mixed"]
AlertSeverity = Literal["low", "medium", "high"]
CommunityRiskLevel = Literal["low", "medium", "high", "critical"]
AlertWorkflowStatus = Literal["new", "acknowledged", "investigating", "escalated", "resolved", "false_positive"]
DataQualityFlag = Literal["simulated", "proxy-derived", "sensor", "external-feed", "uncertain"]
NotificationChannel = Literal["ops-log", "duty-operator", "public-health", "webhook"]
NotificationDeliveryStatus = Literal["queued", "delivered", "failed"]


class StationProfile(BaseModel):
    station_id: str
    station_name: str
    region: str
    timezone: str
    latitude: float
    longitude: float
    source: WaterDataSource = "simulated"
    community_name: str = ""
    province: str = ""
    water_use_type: WaterUseType = "mixed"
    population_served: int = 0
    households_served: int = 0
    schools_nearby: int = 0
    critical_assets: List[str] = Field(default_factory=list)
    escalation_contacts: List[str] = Field(default_factory=list)
    exposure_notes: str = ""


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
    severity: AlertSeverity
    score: float
    reasons: List[str]
    feature_contributions: Dict[str, float]
    community_name: str = ""
    water_use_type: WaterUseType = "mixed"
    community_risk_level: CommunityRiskLevel = "low"
    affected_groups: List[str] = Field(default_factory=list)
    potential_impact: str = ""
    recommended_actions: List[str] = Field(default_factory=list)
    time_to_acknowledge_minutes: int = 60
    time_to_intervene_minutes: int = 240
    escalation_target: str = ""
    status: AlertWorkflowStatus = "new"
    status_note: str = ""
    risk_confidence: float = 0.0
    data_quality_flag: DataQualityFlag = "uncertain"


class AlertStatusUpdateRequest(BaseModel):
    status: AlertWorkflowStatus
    note: str = Field(default="", max_length=500)


class AlertNotification(BaseModel):
    id: str
    alert_id: str
    station_id: str
    channel: NotificationChannel
    recipient: str
    title: str
    body: str
    delivery_status: NotificationDeliveryStatus = "queued"
    delivery_detail: str = ""
    created_at: datetime
    delivered_at: datetime | None = None
