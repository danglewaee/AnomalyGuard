from collections import Counter
from datetime import datetime, timezone
import re

from app.schemas import (
    AnomalyAlert,
    CommunityOverview,
    CommunityOverviewSummary,
    CommunityZoneOverview,
    CommunityZoneStation,
    StationProfile,
    WaterReading,
)
from app.services.community_impact_profile import load_community_impact_profile


_OPERATOR_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}
_COMMUNITY_RISK_ORDER = {"stable": 0, "watch": 1, "warning": 2, "critical": 3}
_COMMUNITY_RISK_LABELS = {
    "stable": "Conditions look stable across monitored water signals.",
    "watch": "Some early warning signs need closer attention.",
    "warning": "Repeated anomaly signals suggest elevated water risk.",
    "critical": "High-priority water risk signals need immediate response.",
}
_COMMUNITY_MESSAGES = {
    "stable": "Normal precautions are still recommended, but no urgent community action is indicated right now.",
    "watch": "Prefer treated water for direct household use until the next operator update if local conditions look unusual.",
    "warning": "Avoid untreated water intake for direct use until the next verified update from local operators.",
    "critical": "Do not use untreated water from this monitored area until operators verify that conditions are safe again.",
}
_RECOMMENDED_ACTIONS = {
    "stable": "Keep monitoring official updates and continue normal treatment practices.",
    "watch": "Ask local operators to verify field conditions and use treated or stored water where possible.",
    "warning": "Pause untreated intake, confirm field conditions quickly, and share the next update with nearby households and farms.",
    "critical": "Escalate to immediate verification, notify nearby communities, and avoid untreated intake until cleared.",
}


def _centroid_for_stations(stations: list[StationProfile]) -> tuple[float | None, float | None]:
    if not stations:
        return None, None

    latitude = sum(station.latitude for station in stations) / len(stations)
    longitude = sum(station.longitude for station in stations) / len(stations)
    return round(latitude, 5), round(longitude, 5)


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "unknown-zone"


def _community_risk_for_zone(alert_count: int, highest_severity: str | None) -> str:
    if highest_severity == "high" and alert_count >= 2:
        return "critical"
    if highest_severity == "high" or alert_count >= 3:
        return "warning"
    if highest_severity == "medium" or alert_count >= 1:
        return "watch"
    return "stable"


def _zone_headline(region: str, risk_level: str, top_signals: list[str]) -> str:
    base = _COMMUNITY_RISK_LABELS[risk_level]
    if top_signals:
        return f"{base} Primary signals near {region}: {', '.join(top_signals)}."
    return f"{base} Latest monitored area: {region}."


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped


def _zone_context(region: str, top_signals: list[str], impact_profile: dict[str, object]) -> dict[str, str | list[str]]:
    profile = impact_profile
    normalized = " ".join(signal.lower() for signal in top_signals)
    impacted_groups = list(profile["base_impacted_groups"])
    priority_sites = list(profile["base_priority_sites"])
    impact_copy = str(profile["default_impact_copy"])

    for rule in profile["signal_rules"]:
        match_any = [str(item).lower() for item in rule.get("match_any", [])]
        if not match_any or not any(token in normalized for token in match_any):
            continue

        impacted_groups.extend(str(item) for item in rule.get("impacted_groups", []))
        priority_sites.extend(str(item) for item in rule.get("priority_sites", []))
        if impact_copy == str(profile["default_impact_copy"]) and rule.get("impact_copy"):
            impact_copy = str(rule["impact_copy"])

    return {
        "downstream_corridor": str(profile["corridor_template"]).format(region=region),
        "impacted_groups": _dedupe_preserve_order(impacted_groups),
        "priority_sites": _dedupe_preserve_order(priority_sites),
        "impact_copy": impact_copy,
    }


def _join_labels(values: list[str], limit: int = 3) -> str:
    trimmed = values[:limit]
    if not trimmed:
        return "downstream communities"
    if len(trimmed) == 1:
        return trimmed[0]
    if len(trimmed) == 2:
        return f"{trimmed[0]} and {trimmed[1]}"
    return f"{', '.join(trimmed[:-1])}, and {trimmed[-1]}"


def _impact_statement(risk_level: str, corridor: str, impacted_groups: list[str], impact_copy: str) -> str:
    audience = _join_labels(impacted_groups, limit=2)
    if risk_level == "stable":
        return (
            f"No broad downstream disruption is indicated for {audience} along {corridor}. "
            "Routine updates are enough unless readings drift again."
        )
    if risk_level == "watch":
        return f"If conditions continue to drift, {audience} along {corridor} should hear the next update first. {impact_copy}"
    if risk_level == "warning":
        return f"Downstream exposure is rising for {audience} along {corridor}. {impact_copy}"
    return f"Immediate public-safe messaging should reach {audience} along {corridor}. {impact_copy}"


def build_community_overview(
    *,
    alerts: list[AnomalyAlert],
    readings: list[WaterReading],
    stations: list[StationProfile],
    since_minutes: int,
    impact_profile_key: str | None = None,
) -> CommunityOverview:
    resolved_profile_key, impact_profile = load_community_impact_profile(impact_profile_key)
    active_alerts = [alert for alert in alerts if alert.incident_status != "resolved"]
    station_lookup = {station.station_id: station for station in stations}
    zones: dict[str, dict] = {}

    for station in stations:
        zone = zones.setdefault(
            station.region,
            {
                "station_names": [],
                "station_profiles": [],
                "recent_alert_count": 0,
                "highest_operator_severity": None,
                "latest_update_at": None,
                "top_signals": [],
            },
        )
        zone["station_names"].append(station.station_name)
        zone["station_profiles"].append(station)

    for reading in readings:
        station = station_lookup.get(reading.station_id)
        region = station.region if station is not None else reading.station_id
        zone = zones.setdefault(
            region,
            {
                "station_names": [],
                "station_profiles": [],
                "recent_alert_count": 0,
                "highest_operator_severity": None,
                "latest_update_at": None,
                "top_signals": [],
            },
        )
        current = zone.get("latest_update_at")
        if current is None or reading.timestamp > current:
            zone["latest_update_at"] = reading.timestamp

    reason_counters: dict[str, Counter[str]] = {region: Counter() for region in zones}
    for alert in active_alerts:
        station = station_lookup.get(alert.station_id)
        region = station.region if station is not None else alert.station_id
        zone = zones.setdefault(
            region,
            {
                "station_names": [],
                "station_profiles": [],
                "recent_alert_count": 0,
                "highest_operator_severity": None,
                "latest_update_at": None,
                "top_signals": [],
            },
        )
        zone["recent_alert_count"] += 1
        zone["highest_operator_severity"] = max(
            zone.get("highest_operator_severity"),
            alert.severity,
            key=lambda value: _OPERATOR_SEVERITY_ORDER.get(value or "low", 0),
        )
        current = zone.get("latest_update_at")
        if current is None or alert.timestamp > current:
            zone["latest_update_at"] = alert.timestamp
        reason_counters.setdefault(region, Counter()).update(alert.reasons or [])

    zone_models: list[CommunityZoneOverview] = []
    risk_counts = Counter()
    for region, zone in zones.items():
        top_signals = [signal for signal, _ in reason_counters.get(region, Counter()).most_common(2)]
        risk_level = _community_risk_for_zone(zone["recent_alert_count"], zone.get("highest_operator_severity"))
        risk_counts[risk_level] += 1
        station_profiles = sorted(zone["station_profiles"], key=lambda station: station.station_name)
        centroid_latitude, centroid_longitude = _centroid_for_stations(station_profiles)
        context = _zone_context(region, top_signals, impact_profile)
        zone_models.append(
            CommunityZoneOverview(
                zone_id=_slugify(region),
                name=region,
                risk_level=risk_level,
                headline=_zone_headline(region, risk_level, top_signals),
                community_message=_COMMUNITY_MESSAGES[risk_level],
                recommended_action=_RECOMMENDED_ACTIONS[risk_level],
                impact_statement=_impact_statement(
                    risk_level,
                    str(context["downstream_corridor"]),
                    list(context["impacted_groups"]),
                    str(context["impact_copy"]),
                ),
                downstream_corridor=str(context["downstream_corridor"]),
                recent_alert_count=zone["recent_alert_count"],
                station_count=len(zone["station_names"]),
                top_signals=top_signals,
                station_names=sorted(zone["station_names"]),
                impacted_groups=list(context["impacted_groups"]),
                priority_sites=list(context["priority_sites"]),
                centroid_latitude=centroid_latitude,
                centroid_longitude=centroid_longitude,
                stations=[
                    CommunityZoneStation(
                        station_id=station.station_id,
                        station_name=station.station_name,
                        latitude=station.latitude,
                        longitude=station.longitude,
                        source=station.source,
                    )
                    for station in station_profiles
                ],
                latest_update_at=zone.get("latest_update_at"),
            )
        )

    zone_models.sort(
        key=lambda zone: (
            _COMMUNITY_RISK_ORDER[zone.risk_level],
            zone.recent_alert_count,
            zone.latest_update_at or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )

    highest_risk = zone_models[0].risk_level if zone_models else "stable"
    headline = _COMMUNITY_RISK_LABELS[highest_risk]
    summary = CommunityOverviewSummary(
        stable=risk_counts["stable"],
        watch=risk_counts["watch"],
        warning=risk_counts["warning"],
        critical=risk_counts["critical"],
        monitored_zones=len(zone_models),
        zones_at_risk=risk_counts["watch"] + risk_counts["warning"] + risk_counts["critical"],
        recent_alerts=len(active_alerts),
    )
    return CommunityOverview(
        generated_at=datetime.now(timezone.utc),
        since_minutes=since_minutes,
        headline=headline,
        impact_profile=resolved_profile_key,
        impact_profile_name=str(impact_profile.get("display_name") or resolved_profile_key.replace("-", " ").title()),
        summary=summary,
        zones=zone_models,
    )
