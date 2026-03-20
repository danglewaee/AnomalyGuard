import base64
import json
import logging
import smtplib
import ssl
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Iterable
from urllib import error, parse, request

from app.schemas import AlertNotification, AnomalyAlert, NotificationEndpoint, StationProfile

logger = logging.getLogger(__name__)

RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass
class NotificationDispatchResult:
    id: str
    delivery_status: str
    delivery_detail: str
    delivered_at: datetime | None


@dataclass
class NotificationDeliveryConfig:
    enable_webhook: bool = False
    default_webhook_url: str = ""
    smtp_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    twilio_enabled: bool = False
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_phone: str = ""
    twilio_api_base: str = "https://api.twilio.com/2010-04-01"
    request_timeout_seconds: float = 5.0


def build_notification_plan(alert: AnomalyAlert, station: StationProfile) -> list[AlertNotification]:
    created_at = datetime.now(timezone.utc)
    title = _title(alert, station)
    body = _body(alert, station)

    notifications = [
        AlertNotification(
            id=str(uuid.uuid4()),
            alert_id=alert.id,
            station_id=alert.station_id,
            channel="ops-log",
            target_role="system-log",
            recipient=f"{station.community_name or station.region} incident log",
            title=title,
            body=body,
            created_at=created_at,
        )
    ]

    routed = False
    for endpoint in _eligible_endpoints(alert, station):
        routed = True
        notifications.append(
            AlertNotification(
                id=str(uuid.uuid4()),
                alert_id=alert.id,
                station_id=alert.station_id,
                channel=endpoint.channel,
                target_role=endpoint.role,
                recipient=endpoint.address,
                title=title,
                body=body,
                created_at=created_at,
            )
        )

    if routed:
        return notifications

    contacts = station.escalation_contacts or ["duty water operator"]
    notifications.append(
        AlertNotification(
            id=str(uuid.uuid4()),
            alert_id=alert.id,
            station_id=alert.station_id,
            channel="ops-log",
            target_role="duty-operator",
            recipient=contacts[0],
            title=title,
            body=body + " Manual outreach required because no real notification endpoint is configured.",
            created_at=created_at,
        )
    )
    if alert.community_risk_level in {"high", "critical"} and len(contacts) > 1:
        notifications.append(
            AlertNotification(
                id=str(uuid.uuid4()),
                alert_id=alert.id,
                station_id=alert.station_id,
                channel="ops-log",
                target_role="public-health",
                recipient=contacts[1],
                title=title,
                body=body + " Manual outreach required because no real notification endpoint is configured.",
                created_at=created_at,
            )
        )

    return notifications


def dispatch_notification_plan(
    notifications: Iterable[AlertNotification],
    config: NotificationDeliveryConfig,
) -> list[NotificationDispatchResult]:
    results: list[NotificationDispatchResult] = []

    for item in notifications:
        logger.info(
            "notification channel=%s target_role=%s recipient=%s alert_id=%s",
            item.channel,
            item.target_role,
            item.recipient,
            item.alert_id,
        )
        if item.channel == "email":
            results.append(_dispatch_email(item, config))
        elif item.channel == "sms":
            results.append(_dispatch_sms(item, config))
        elif item.channel == "webhook":
            results.append(_dispatch_webhook(item, config))
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


def _eligible_endpoints(alert: AnomalyAlert, station: StationProfile) -> list[NotificationEndpoint]:
    endpoints: list[NotificationEndpoint] = []
    seen: set[tuple[str, str, str]] = set()

    for raw_endpoint in station.notification_endpoints:
        endpoint = raw_endpoint if isinstance(raw_endpoint, NotificationEndpoint) else NotificationEndpoint.model_validate(raw_endpoint)
        key = (endpoint.role, endpoint.channel, endpoint.address)
        if key in seen or not endpoint.active:
            continue
        if RISK_ORDER[alert.community_risk_level] < RISK_ORDER[endpoint.min_risk_level]:
            continue
        seen.add(key)
        endpoints.append(endpoint)

    return endpoints


def _dispatch_email(item: AlertNotification, config: NotificationDeliveryConfig) -> NotificationDispatchResult:
    if not config.smtp_enabled:
        return _failed(item.id, "SMTP notifications are disabled")
    if not config.smtp_host or not config.smtp_from_email:
        return _failed(item.id, "SMTP host/from address are not configured")

    message = EmailMessage()
    message["From"] = config.smtp_from_email
    message["To"] = item.recipient
    message["Subject"] = item.title
    message.set_content(item.body)

    try:
        if config.smtp_use_ssl:
            with smtplib.SMTP_SSL(
                config.smtp_host,
                config.smtp_port,
                timeout=config.request_timeout_seconds,
            ) as server:
                _smtp_login(server, config)
                server.send_message(message)
        else:
            with smtplib.SMTP(
                config.smtp_host,
                config.smtp_port,
                timeout=config.request_timeout_seconds,
            ) as server:
                if config.smtp_use_tls:
                    server.starttls(context=ssl.create_default_context())
                _smtp_login(server, config)
                server.send_message(message)
    except Exception as exc:
        return _failed(item.id, f"SMTP delivery failed: {exc}")

    return NotificationDispatchResult(
        id=item.id,
        delivery_status="delivered",
        delivery_detail=f"Email delivered to {item.recipient}",
        delivered_at=datetime.now(timezone.utc),
    )


def _smtp_login(server: smtplib.SMTP, config: NotificationDeliveryConfig) -> None:
    if config.smtp_username:
        server.login(config.smtp_username, config.smtp_password)


def _dispatch_sms(item: AlertNotification, config: NotificationDeliveryConfig) -> NotificationDispatchResult:
    if not config.twilio_enabled:
        return _failed(item.id, "Twilio SMS notifications are disabled")
    if not config.twilio_account_sid or not config.twilio_auth_token or not config.twilio_from_phone:
        return _failed(item.id, "Twilio credentials are incomplete")

    url = (
        f"{config.twilio_api_base.rstrip('/')}/Accounts/"
        f"{config.twilio_account_sid}/Messages.json"
    )
    body = _truncate_sms_body(item)
    payload = parse.urlencode(
        {
            "To": item.recipient,
            "From": config.twilio_from_phone,
            "Body": body,
        }
    ).encode("utf-8")
    auth = base64.b64encode(
        f"{config.twilio_account_sid}:{config.twilio_auth_token}".encode("utf-8")
    ).decode("ascii")
    req = request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=config.request_timeout_seconds) as resp:
            detail = f"SMS delivered with status {resp.status}"
            return NotificationDispatchResult(
                id=item.id,
                delivery_status="delivered",
                delivery_detail=detail,
                delivered_at=datetime.now(timezone.utc),
            )
    except error.URLError as exc:
        return _failed(item.id, f"SMS delivery failed: {exc}")


def _dispatch_webhook(item: AlertNotification, config: NotificationDeliveryConfig) -> NotificationDispatchResult:
    if not config.enable_webhook:
        return _failed(item.id, "Webhook notifications are disabled")

    webhook_url = item.recipient or config.default_webhook_url
    if not webhook_url:
        return _failed(item.id, "Webhook URL is not configured")

    payload = {
        "notification_id": item.id,
        "alert_id": item.alert_id,
        "station_id": item.station_id,
        "channel": item.channel,
        "target_role": item.target_role,
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
        with request.urlopen(req, timeout=config.request_timeout_seconds) as resp:
            detail = f"Webhook delivered with status {resp.status}"
            return NotificationDispatchResult(
                id=item.id,
                delivery_status="delivered",
                delivery_detail=detail,
                delivered_at=datetime.now(timezone.utc),
            )
    except error.URLError as exc:
        return _failed(item.id, f"Webhook delivery failed: {exc}")


def _failed(notification_id: str, detail: str) -> NotificationDispatchResult:
    return NotificationDispatchResult(
        id=notification_id,
        delivery_status="failed",
        delivery_detail=detail,
        delivered_at=None,
    )


def _truncate_sms_body(item: AlertNotification) -> str:
    body = f"{item.title}. {item.body}"
    if len(body) <= 320:
        return body
    return body[:317] + "..."


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
