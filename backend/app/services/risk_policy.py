from typing import Iterable

from app.schemas import AnomalyAlert, StationProfile, WaterReading
from app.services.detector import DetectionResult

ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "new": {"acknowledged", "investigating", "escalated", "resolved", "false_positive"},
    "acknowledged": {"investigating", "escalated", "resolved", "false_positive"},
    "investigating": {"escalated", "resolved", "false_positive"},
    "escalated": {"resolved", "false_positive"},
    "resolved": {"resolved"},
    "false_positive": {"false_positive"},
}


def validate_status_transition(current_status: str, next_status: str) -> bool:
    if current_status == next_status:
        return True
    return next_status in ALLOWED_STATUS_TRANSITIONS.get(current_status, set())


def build_community_alert(
    reading: WaterReading,
    station: StationProfile,
    result: DetectionResult,
    alert_id: str,
) -> AnomalyAlert:
    primary_signals = _primary_signals(result)
    affected_groups = _affected_groups(station)
    community_risk_level = _community_risk_level(station, result, primary_signals)
    community_risk_level = _apply_source_cap(community_risk_level, station)
    ack_minutes, intervene_minutes = _response_windows(community_risk_level)
    recommended_actions = _recommended_actions(station, community_risk_level, primary_signals)

    return AnomalyAlert(
        id=alert_id,
        timestamp=reading.timestamp,
        station_id=reading.station_id,
        severity=result.severity,
        score=round(result.score, 3),
        reasons=result.reasons,
        feature_contributions=result.contributions,
        community_name=station.community_name or station.region,
        water_use_type=station.water_use_type,
        community_risk_level=community_risk_level,
        affected_groups=affected_groups,
        potential_impact=_potential_impact(station, affected_groups, primary_signals, community_risk_level),
        recommended_actions=recommended_actions,
        time_to_acknowledge_minutes=ack_minutes,
        time_to_intervene_minutes=intervene_minutes,
        escalation_target=_escalation_target(station, community_risk_level),
        status="new",
        status_note="",
        risk_confidence=_risk_confidence(station, result),
        data_quality_flag=_data_quality_flag(station),
    )


def _primary_signals(result: DetectionResult) -> set[str]:
    signals = set(result.contributions.keys())
    joined_reasons = " ".join(result.reasons).lower()
    for feature in ("ph", "tds", "turbidity", "temperature_c", "do_mg_l", "flow_l_min"):
        if feature in joined_reasons:
            signals.add(feature)
    return signals


def _affected_groups(station: StationProfile) -> list[str]:
    groups: list[str] = []
    if station.water_use_type in {"drinking", "mixed"}:
        groups.append("households")
    if station.water_use_type in {"irrigation", "mixed"}:
        groups.append("farmers")
    if station.water_use_type in {"aquaculture", "mixed"}:
        groups.append("aquaculture operators")
    if station.schools_nearby > 0:
        groups.append("schoolchildren")
    return groups


def _community_risk_level(station: StationProfile, result: DetectionResult, signals: set[str]) -> str:
    score = {"low": 1, "medium": 2, "high": 3}[result.severity]
    drinking_signals = {"ph", "tds", "turbidity"}
    ecological_signals = {"do_mg_l", "turbidity", "flow_l_min"}

    if station.water_use_type in {"drinking", "mixed"} and signals & drinking_signals:
        score += 1
    if station.schools_nearby > 0 and signals & drinking_signals:
        score += 1
    if station.population_served >= 100000:
        score += 1
    if station.water_use_type in {"aquaculture", "mixed"} and signals & ecological_signals:
        score += 1

    if score >= 5:
        return "critical"
    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def _apply_source_cap(risk_level: str, station: StationProfile) -> str:
    if station.source == "api" and risk_level == "critical":
        return "high"
    if station.source == "simulated" and risk_level in {"high", "critical"}:
        return "medium"
    return risk_level


def _response_windows(risk_level: str) -> tuple[int, int]:
    if risk_level == "critical":
        return 5, 30
    if risk_level == "high":
        return 15, 60
    if risk_level == "medium":
        return 60, 240
    return 180, 720


def _recommended_actions(station: StationProfile, risk_level: str, signals: set[str]) -> list[str]:
    actions = ["Verify sensor integrity and collect a confirmatory field sample."]
    if station.water_use_type in {"drinking", "mixed"} and signals & {"ph", "tds", "turbidity"}:
        actions.append("Inspect intake conditions and hold untreated water release until manual verification is complete.")
    if station.water_use_type in {"aquaculture", "mixed"} and signals & {"do_mg_l", "turbidity", "flow_l_min"}:
        actions.append("Notify downstream aquaculture operators to reduce intake and monitor dissolved oxygen stress.")
    if station.water_use_type in {"irrigation", "mixed"} and signals & {"ph", "tds", "turbidity"}:
        actions.append("Alert irrigation managers to inspect canal gates and avoid sensitive irrigation cycles until the signal stabilizes.")
    if risk_level in {"high", "critical"}:
        actions.append("Escalate to the responsible operator and public health contact before the response window expires.")
    return actions


def _potential_impact(
    station: StationProfile,
    affected_groups: Iterable[str],
    signals: set[str],
    risk_level: str,
) -> str:
    impacts: list[str] = []
    if "households" in affected_groups and signals & {"ph", "tds", "turbidity"}:
        impacts.append(
            f"Household water safety may degrade for roughly {station.population_served or station.households_served} people if intake quality continues to worsen."
        )
    if "schoolchildren" in affected_groups and risk_level in {"high", "critical"}:
        impacts.append("Nearby children may be exposed if unsafe water is used before operators intervene.")
    if "aquaculture operators" in affected_groups and signals & {"do_mg_l", "flow_l_min", "turbidity"}:
        impacts.append("Aquaculture ponds downstream may experience oxygen stress, sediment shock, or short-term intake disruption.")
    if "farmers" in affected_groups and signals & {"ph", "tds", "turbidity"}:
        impacts.append("Irrigation quality may become unreliable for farms depending on untreated river water.")
    if not impacts:
        impacts.append("Anomalous water behavior could affect downstream users if the signal persists without investigation.")
    return " ".join(impacts)


def _escalation_target(station: StationProfile, risk_level: str) -> str:
    if station.escalation_contacts:
        primary = station.escalation_contacts[0]
        if risk_level == "critical" and len(station.escalation_contacts) > 1:
            return f"{primary} + {station.escalation_contacts[1]}"
        return primary
    return "duty water operator"


def _risk_confidence(station: StationProfile, result: DetectionResult) -> float:
    confidence = 0.55 + result.score * 0.35
    if station.source == "api":
        confidence -= 0.12
    elif station.source == "simulated":
        confidence -= 0.18
    confidence = max(0.2, min(confidence, 0.98))
    return round(confidence, 3)


def _data_quality_flag(station: StationProfile) -> str:
    if station.source == "api":
        return "proxy-derived"
    if station.source == "simulated":
        return "simulated"
    if station.source in {"mqtt", "csv"}:
        return "sensor"
    return "uncertain"
