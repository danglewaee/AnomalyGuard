import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from urllib import error, request

from app.schemas import AlertNotification, AnomalyAlert, StationProfile

logger = logging.getLogger(__name__)


@dataclass
class NotificationDispatchResult:
    id: str
    delivery_status: str
    delivery_detail: str
    delivered_at: datetime | None


def build_notification_plan(alert: AnomalyAlert, station: StationProfile) -> list[AlertNotification]:
    created_at = datetime.now(timezone.utc)
    messages = [
        AlertNotification(
            id=str(uuid.uuid4()),
            alert_id=alert.id,
            station_id=alert.station_id,
            channel="ops-log",
            recipient=f"{station.community_name or station.region} incident log",
            title=_title(alert, station),
            body=_body(alert, station),
            created_at=created_at,
        )
    ]

    contacts = station.escalation_contacts or ["duty water operator"]
    messages.append(
        AlertNotification(
            id=str(uuid.uuid4()),
            alert_id=alert.id,
            station_id=alert.station_id,
            channel="duty-operator",
            recipient=contacts[0],
            title=_title(alert, station),
            body=_body(alert, station),
            created_at=created_at,
        )
    )

    if alert.community_risk_level in {"high", "critical"} and len(contacts) > 1:
        messages.append(
            AlertNotification(
                id=str(uuid.uuid4()),
                alert_id=alert.id,
                station_id=alert.station_id,
                channel="public-health",
                recipient=contacts[1],
                title=_title(alert, station),
                body=_body(alert, station),
                created_at=created_at,
            )
        )

    return messages


def dispatch_notification_plan(
    notifications: Iterable[AlertNotification],
    webhook_url: str = "",
    enable_webhook: bool = False,
) -> list[NotificationDispatchResult]:
    results: list[NotificationDispatchResult] = []

    for item in notifications:
        logger.info(
            "notification channel=%s recipient=%s alert_id=%s risk=%s",
            item.channel,
            item.recipient,
            item.alert_id,
            item.title,
        )
        if enable_webhook and webhook_url:
            results.append(_dispatch_webhook(item, webhook_url))
        else:
            results.append(
                NotificationDispatchResult(
                    id=item.id,
                    delivery_status="delivered",
                    delivery_detail="Logged for operator workflow",
                    delivered_at=datetime.now(timezone.utc),
                )
            )

    return results


def _dispatch_webhook(item: AlertNotification, webhook_url: str) -> NotificationDispatchResult:
    payload = {
        "notification_id": item.id,
        "alert_id": item.alert_id,
        "station_id": item.station_id,
        "channel": item.channel,
        "recipient": item.recipient,
        "title": item.title,
        "body": item.body,
        "created_at": item.created_at.isoformat(),
    }

    req = request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=5) as resp:
            detail = f"Webhook delivered with status {resp.status}"
            return NotificationDispatchResult(
                id=item.id,
                delivery_status="delivered",
                delivery_detail=detail,
                delivered_at=datetime.now(timezone.utc),
            )
    except error.URLError as exc:
        return NotificationDispatchResult(
            id=item.id,
            delivery_status="failed",
            delivery_detail=str(exc),
            delivered_at=None,
        )


def _title(alert: AnomalyAlert, station: StationProfile) -> str:
    return f"{alert.community_risk_level.upper()} water risk at {station.station_name}"


def _body(alert: AnomalyAlert, station: StationProfile) -> str:
    actions = "; ".join(alert.recommended_actions) if alert.recommended_actions else "Verify field conditions."
    groups = ", ".join(alert.affected_groups) if alert.affected_groups else "downstream users"
    return (
        f"Community: {station.community_name or station.region}. "
        f"Affected groups: {groups}. "
        f"Potential impact: {alert.potential_impact} "
        f"Recommended actions: {actions} "
        f"Acknowledge within {alert.time_to_acknowledge_minutes} minutes and intervene within "
        f"{alert.time_to_intervene_minutes} minutes."
    )
