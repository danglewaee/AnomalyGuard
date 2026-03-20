from app.config import settings
from app.celery_app import celery_app
from app.db import SessionLocal
from app.schemas import AnomalyAlert, StationProfile
from app.services.metrics import NOTIFICATIONS_DELIVERED, NOTIFICATIONS_FAILED, NOTIFICATIONS_QUEUED
from app.services.notification_pipeline import (
    NotificationDeliveryConfig,
    build_notification_plan,
    dispatch_notification_plan,
)
from app.services.store_pg import PostgresStore
from app.services.usgs_ingest import fetch_usgs_readings
from app.services.vn_openmeteo_ingest import fetch_vn_openmeteo_readings


@celery_app.task(name="tasks.fetch_vn_data")
def fetch_vn_data_task(station_id: str, days: int) -> dict:
    station, readings = fetch_vn_openmeteo_readings(station_id, days)
    return {"station": station.model_dump(mode="json"), "readings": [r.model_dump(mode="json") for r in readings]}


@celery_app.task(name="tasks.fetch_usgs_data")
def fetch_usgs_data_task(site_no: str, hours: int) -> dict:
    station, readings = fetch_usgs_readings(site_no, hours)
    return {"station": station.model_dump(mode="json"), "readings": [r.model_dump(mode="json") for r in readings]}


@celery_app.task(name="tasks.notify_alert")
def notify_alert_task(alert_payload: dict, station_payload: dict) -> dict:
    alert = AnomalyAlert(**alert_payload)
    station = StationProfile(**station_payload)
    notifications = build_notification_plan(alert, station)

    with SessionLocal() as db:
        store = PostgresStore(db)
        for item in notifications:
            NOTIFICATIONS_QUEUED.labels(channel=item.channel).inc()
            store.upsert_notification(item)

        results = dispatch_notification_plan(
            notifications,
            config=NotificationDeliveryConfig(
                enable_webhook=settings.enable_webhook_notifications,
                default_webhook_url=settings.notification_webhook_url,
                smtp_enabled=settings.smtp_notifications_enabled,
                smtp_host=settings.smtp_host,
                smtp_port=settings.smtp_port,
                smtp_username=settings.smtp_username,
                smtp_password=settings.smtp_password,
                smtp_from_email=settings.smtp_from_email,
                smtp_use_tls=settings.smtp_use_tls,
                smtp_use_ssl=settings.smtp_use_ssl,
                twilio_enabled=settings.twilio_sms_enabled,
                twilio_account_sid=settings.twilio_account_sid,
                twilio_auth_token=settings.twilio_auth_token,
                twilio_from_phone=settings.twilio_from_phone,
                twilio_api_base=settings.twilio_api_base,
                request_timeout_seconds=settings.notification_request_timeout_seconds,
            ),
        )

        for result in results:
            row = store.update_notification_delivery(
                notification_id=result.id,
                delivery_status=result.delivery_status,
                delivery_detail=result.delivery_detail,
                delivered_at=result.delivered_at,
            )
            channel = row.channel if row is not None else "webhook"
            if result.delivery_status == "delivered":
                NOTIFICATIONS_DELIVERED.labels(channel=channel).inc()
            else:
                NOTIFICATIONS_FAILED.labels(channel=channel).inc()

    return {"alert_id": alert.id, "notifications": len(notifications)}
