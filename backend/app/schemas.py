from datetime import datetime
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field


class StationProfile(BaseModel):
    station_id: str
    station_name: str
    region: str
    timezone: str
    latitude: float
    longitude: float
    source: Literal["simulated", "mqtt", "csv", "api", "device"] = "simulated"


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
    incident_status: Literal["open", "acknowledged", "resolved"] | None = None
    incident_note: str | None = None
    incident_updated_at: datetime | None = None
    review_label: Literal["true_anomaly", "false_positive"] | None = None
    review_note: str | None = None
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None


class IncidentStatusUpdate(BaseModel):
    note: str = ""


class AlertReviewUpdate(BaseModel):
    label: Literal["true_anomaly", "false_positive"]
    note: str = ""


class LabeledAlertExportResponse(BaseModel):
    exported_at: datetime
    count: int
    label_filter: Literal["true_anomaly", "false_positive"] | None = None
    station_id: str | None = None
    since_minutes: int | None = None
    items: List[AnomalyAlert] = Field(default_factory=list)


class RetrainingManifestResponse(BaseModel):
    generated_at: datetime
    manifest_id: str
    fingerprint: str
    count: int
    label_filter: Literal["true_anomaly", "false_positive"] | None = None
    station_id: str | None = None
    since_minutes: int | None = None
    label_counts: Dict[str, int] = Field(default_factory=dict)
    station_counts: Dict[str, int] = Field(default_factory=dict)
    earliest_reviewed_at: datetime | None = None
    latest_reviewed_at: datetime | None = None
    suggested_split: Dict[str, int] = Field(default_factory=dict)
    ready_for_training: bool = False
    warnings: List[str] = Field(default_factory=list)
    export_urls: Dict[str, str] = Field(default_factory=dict)


class SeverityEvaluationBreakdown(BaseModel):
    reviewed_count: int = 0
    true_anomaly: int = 0
    false_positive: int = 0
    precision: float | None = None


class ThresholdEvaluationPoint(BaseModel):
    threshold: float
    predicted_positive_count: int = 0
    true_positive: int = 0
    false_positive: int = 0
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None


class ReviewedAlertEvaluationResponse(BaseModel):
    generated_at: datetime
    count: int
    station_id: str | None = None
    since_minutes: int | None = None
    current_alert_threshold: float
    current_precision: float | None = None
    label_counts: Dict[str, int] = Field(default_factory=dict)
    severity_breakdown: Dict[str, SeverityEvaluationBreakdown] = Field(default_factory=dict)
    recommended_threshold: float | None = None
    recommended_threshold_metrics: ThresholdEvaluationPoint | None = None
    threshold_sweep: List[ThresholdEvaluationPoint] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class AlertHistoryEntry(BaseModel):
    id: int
    alert_id: str
    station_id: str
    event_type: Literal["detected", "incident_status", "review_label"]
    event_value: str
    note: str = ""
    changed_by: str = ""
    created_at: datetime


class DriftMetric(BaseModel):
    reference: float | None = None
    candidate: float | None = None
    absolute_delta: float | None = None


class ReadinessCheck(BaseModel):
    key: str
    passed: bool = False
    detail: str = ""


class ReviewedAlertReadinessResponse(BaseModel):
    generated_at: datetime
    count: int
    station_id: str | None = None
    since_minutes: int | None = None
    recent_window_count: int = 0
    reference_window_count: int = 0
    ready_for_training: bool = False
    recommendation: Literal["hold", "monitor", "ready"] = "hold"
    readiness_score: int = 0
    current_precision: float | None = None
    recommended_threshold: float | None = None
    label_counts: Dict[str, int] = Field(default_factory=dict)
    station_counts: Dict[str, int] = Field(default_factory=dict)
    checks: List[ReadinessCheck] = Field(default_factory=list)
    label_distribution_shift: Dict[str, DriftMetric] = Field(default_factory=dict)
    mean_score_shift: DriftMetric | None = None
    station_concentration_shift: DriftMetric | None = None
    warnings: List[str] = Field(default_factory=list)


class PromotionGateCheck(BaseModel):
    key: str
    passed: bool = False
    severity: Literal["blocker", "warning"] = "warning"
    detail: str = ""


class ReviewedAlertPromotionGateResponse(BaseModel):
    generated_at: datetime
    station_id: str | None = None
    since_minutes: int | None = None
    promotion_decision: Literal["blocked", "shadow", "canary"] = "blocked"
    approve_for_shadow: bool = False
    approve_for_canary: bool = False
    checks: List[PromotionGateCheck] = Field(default_factory=list)
    blockers: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    required_actions: List[str] = Field(default_factory=list)
    rollback_triggers: List[str] = Field(default_factory=list)


class ModelRegistryEntrySummary(BaseModel):
    manifest_id: str
    job_id: str = ""
    state: Literal["prepared", "shadow", "canary", "rolled_back"]
    promotion_decision: Literal["blocked", "shadow", "canary"] = "blocked"
    approve_for_shadow: bool = False
    approve_for_canary: bool = False
    station_id: str | None = None
    since_minutes: int | None = None
    recommendation: Literal["hold", "monitor", "ready"] = "hold"
    readiness_score: int = 0
    current_precision: float | None = None
    recommended_threshold: float | None = None
    reviewed_count: int = 0
    blocker_count: int = 0
    warning_count: int = 0
    mlflow_run_id: str = ""
    run_name: str = ""
    status_note: str = ""
    last_changed_by: str = ""
    created_at: datetime
    updated_at: datetime
    promoted_at: datetime | None = None
    rolled_back_at: datetime | None = None
    bundle_payload: Dict[str, Any] = Field(default_factory=dict)


class ModelRegistryEventEntry(BaseModel):
    id: int
    manifest_id: str
    from_state: str = ""
    to_state: str
    actor: str = ""
    note: str = ""
    metadata_payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ModelRegistryTransitionRequest(BaseModel):
    target_state: Literal["shadow", "canary", "rolled_back"]
    note: str = ""


class RetrainingJobRequest(BaseModel):
    station_id: str | None = None
    since_minutes: int | None = 10080
    limit: int = Field(default=1000, ge=1, le=5000)
    recent_count: int = Field(default=50, ge=1, le=500)


class DeviceTelemetry(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    station_id: str = Field(default="esp32-device-001")
    station_name: str | None = None
    region: str | None = None
    timezone: str = "Asia/Ho_Chi_Minh"
    latitude: float | None = None
    longitude: float | None = None
    timestamp: datetime | None = None
    time: str | None = None
    client_id: str | None = Field(default=None, alias="clientID")
    ph: float
    tds: float
    temperature_c: float | None = Field(default=None, alias="temp")
    humidity: float | None = Field(default=None, alias="hum")
    weight_g: float | None = Field(default=None, alias="weight")
    water_temp_c: float | None = Field(default=None, alias="waterTemp")
    is_feeding: bool = Field(default=False, alias="isFeeding")
    turbidity: float | None = None
    do_mg_l: float | None = None
    flow_l_min: float | None = None


class DeviceControlState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    direction: int = Field(default=0, ge=0, le=4)
    pump: bool = False
    isFeeding: bool = False
    weight: float = Field(default=100.0, ge=0.0)
    hour: int = Field(default=0, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)


class DeviceStatus(BaseModel):
    station_id: str
    station_name: str
    region: str
    source: Literal["device"] = "device"
    last_seen_at: datetime | None = None
    telemetry: Dict[str, Any] = Field(default_factory=dict)
    control: Dict[str, Any] = Field(default_factory=dict)
    reading_preview: Dict[str, Any] = Field(default_factory=dict)


class DeviceCredentialMutationRequest(BaseModel):
    note: str = ""


class DeviceCredentialSummary(BaseModel):
    station_id: str
    key_fingerprint: str
    last_event_type: str = ""
    last_rotated_at: datetime | None = None
    last_rotated_by: str = ""
    registry_managed: bool = True


class DeviceCredentialAuditEntry(BaseModel):
    id: int
    station_id: str
    event_type: Literal["provisioned", "rotated", "revoked"]
    actor: str = ""
    key_fingerprint: str = ""
    note: str = ""
    metadata_payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class DeviceCredentialRotateResponse(BaseModel):
    station_id: str
    issued_key: str
    key_fingerprint: str
    event_type: Literal["provisioned", "rotated"]
    rotated_at: datetime
    rotated_by: str
    note: str = ""


class CommunityOverviewSummary(BaseModel):
    stable: int = 0
    watch: int = 0
    warning: int = 0
    critical: int = 0
    monitored_zones: int = 0
    zones_at_risk: int = 0
    recent_alerts: int = 0


class CommunityZoneStation(BaseModel):
    station_id: str
    station_name: str
    latitude: float
    longitude: float
    source: Literal["simulated", "mqtt", "csv", "api", "device"] = "simulated"


class CommunityZoneOverview(BaseModel):
    zone_id: str
    name: str
    risk_level: Literal["stable", "watch", "warning", "critical"]
    headline: str
    community_message: str
    recommended_action: str
    impact_statement: str = ""
    downstream_corridor: str = ""
    recent_alert_count: int = 0
    station_count: int = 0
    top_signals: List[str] = Field(default_factory=list)
    station_names: List[str] = Field(default_factory=list)
    impacted_groups: List[str] = Field(default_factory=list)
    priority_sites: List[str] = Field(default_factory=list)
    centroid_latitude: float | None = None
    centroid_longitude: float | None = None
    stations: List[CommunityZoneStation] = Field(default_factory=list)
    latest_update_at: datetime | None = None


class CommunityImpactProfileOption(BaseModel):
    key: str
    display_name: str
    description: str = ""
    is_default: bool = False


class CommunityImpactProfilesResponse(BaseModel):
    active_profile: str
    profiles: List[CommunityImpactProfileOption] = Field(default_factory=list)


class CommunityOverview(BaseModel):
    generated_at: datetime
    since_minutes: int
    headline: str
    impact_profile: str = ""
    impact_profile_name: str = ""
    summary: CommunityOverviewSummary
    zones: List[CommunityZoneOverview] = Field(default_factory=list)


class JobStatus(BaseModel):
    id: str
    job_type: str
    status: Literal["queued", "running", "succeeded", "failed"]
    requested_by: str = ""
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    result_payload: Dict[str, Any] = Field(default_factory=dict)
    error_message: str = ""
