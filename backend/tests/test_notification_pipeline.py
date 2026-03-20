import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.schemas import AnomalyAlert, StationProfile
from app.services.notification_pipeline import (
    NotificationDeliveryConfig,
    NotificationDispatchResult,
    build_notification_plan,
    dispatch_notification_plan,
)


class NotificationPipelineTests(unittest.TestCase):
    def test_builds_real_channel_plan_for_high_risk(self) -> None:
        station = StationProfile(
            station_id="ang-giang-intake",
            station_name="An Giang Intake",
            region="An Giang",
            timezone="Asia/Ho_Chi_Minh",
            latitude=10.5,
            longitude=105.1,
            source="mqtt",
            community_name="An Giang Riverside Households",
            province="An Giang",
            water_use_type="drinking",
            population_served=120000,
            households_served=25000,
            schools_nearby=9,
            critical_assets=["school cluster", "intake gate"],
            escalation_contacts=["district water operator", "community health lead"],
            notification_endpoints=[
                {
                    "role": "duty-operator",
                    "channel": "email",
                    "address": "ops@example.org",
                    "label": "Duty operator",
                    "min_risk_level": "low",
                },
                {
                    "role": "public-health",
                    "channel": "sms",
                    "address": "+84900000001",
                    "label": "Health lead",
                    "min_risk_level": "high",
                },
                {
                    "role": "community-response",
                    "channel": "webhook",
                    "address": "https://example.org/hooks/community",
                    "label": "Response automation",
                    "min_risk_level": "critical",
                },
            ],
            exposure_notes="Families rely on intake-fed treated water.",
        )
        alert = AnomalyAlert(
            id="alert-1",
            timestamp=datetime.now(timezone.utc),
            station_id=station.station_id,
            severity="high",
            score=0.82,
            reasons=["ph outside safe range", "turbidity outside safe range"],
            feature_contributions={"turbidity": 3.1, "ph": 2.3},
            community_name=station.community_name,
            water_use_type=station.water_use_type,
            community_risk_level="critical",
            affected_groups=["households", "schoolchildren"],
            potential_impact="Nearby children may be exposed if unsafe water is used before operators intervene.",
            recommended_actions=["Inspect intake conditions and hold untreated water release until manual verification is complete."],
            time_to_acknowledge_minutes=5,
            time_to_intervene_minutes=30,
            escalation_target="district water operator + community health lead",
            status="new",
            status_note="",
            risk_confidence=0.91,
            data_quality_flag="sensor",
        )

        plan = build_notification_plan(alert, station)

        channels = [item.channel for item in plan]
        roles = [item.target_role for item in plan]
        self.assertEqual(channels[0], "ops-log")
        self.assertEqual(roles[0], "system-log")
        self.assertIn("email", channels)
        self.assertIn("sms", channels)
        self.assertIn("webhook", channels)
        self.assertIn("public-health", roles)

    def test_low_risk_plan_filters_high_threshold_routes(self) -> None:
        station = StationProfile(
            station_id="field-station",
            station_name="Field Station",
            region="Can Tho",
            timezone="Asia/Ho_Chi_Minh",
            latitude=10.0,
            longitude=105.8,
            source="simulated",
            community_name="Field Users",
            province="Can Tho",
            water_use_type="irrigation",
            population_served=1500,
            households_served=250,
            schools_nearby=0,
            critical_assets=[],
            escalation_contacts=["canal operator"],
            notification_endpoints=[
                {
                    "role": "duty-operator",
                    "channel": "email",
                    "address": "canal@example.org",
                    "label": "Canal operator",
                    "min_risk_level": "low",
                },
                {
                    "role": "public-health",
                    "channel": "sms",
                    "address": "+84900000009",
                    "label": "Health desk",
                    "min_risk_level": "high",
                },
            ],
            exposure_notes="Irrigation only.",
        )
        alert = AnomalyAlert(
            id="alert-2",
            timestamp=datetime.now(timezone.utc),
            station_id=station.station_id,
            severity="low",
            score=0.49,
            reasons=["statistical deviation from recent baseline"],
            feature_contributions={"flow_l_min": 1.3},
            community_name=station.community_name,
            water_use_type=station.water_use_type,
            community_risk_level="medium",
            affected_groups=["farmers"],
            potential_impact="Irrigation quality may become unreliable for farms depending on untreated river water.",
            recommended_actions=["Verify sensor integrity and collect a confirmatory field sample."],
            time_to_acknowledge_minutes=60,
            time_to_intervene_minutes=240,
            escalation_target="canal operator",
            status="new",
            status_note="",
            risk_confidence=0.44,
            data_quality_flag="simulated",
        )

        plan = build_notification_plan(alert, station)

        channels = [item.channel for item in plan]
        self.assertEqual(channels, ["ops-log", "email"])

    def test_dispatch_routes_email_sms_and_webhook(self) -> None:
        station = StationProfile(
            station_id="route-test",
            station_name="Route Test",
            region="Can Tho",
            timezone="Asia/Ho_Chi_Minh",
            latitude=10.0,
            longitude=105.8,
            source="mqtt",
        )
        alert = AnomalyAlert(
            id="alert-3",
            timestamp=datetime.now(timezone.utc),
            station_id=station.station_id,
            severity="high",
            score=0.77,
            reasons=["tds outside safe range"],
            feature_contributions={"tds": 2.8},
        )
        plan = [
            *build_notification_plan(alert, station)[:1],
            *[
                item
                for item in build_notification_plan(
                    alert.model_copy(update={"community_risk_level": "critical"}),
                    station.model_copy(
                        update={
                            "community_name": "Test community",
                            "notification_endpoints": [
                                {
                                    "role": "duty-operator",
                                    "channel": "email",
                                    "address": "ops@example.org",
                                },
                                {
                                    "role": "public-health",
                                    "channel": "sms",
                                    "address": "+84900000088",
                                    "min_risk_level": "high",
                                },
                                {
                                    "role": "community-response",
                                    "channel": "webhook",
                                    "address": "https://example.org/hooks/route-test",
                                    "min_risk_level": "critical",
                                },
                            ],
                        }
                    ),
                )[1:]
            ],
        ]

        config = NotificationDeliveryConfig(
            enable_webhook=True,
            default_webhook_url="https://example.org/hooks/default",
            smtp_enabled=True,
            smtp_host="smtp.example.org",
            smtp_port=587,
            smtp_from_email="alerts@example.org",
            twilio_enabled=True,
            twilio_account_sid="sid",
            twilio_auth_token="token",
            twilio_from_phone="+12025550100",
        )

        with (
            patch(
                "app.services.notification_pipeline._dispatch_email",
                return_value=NotificationDispatchResult(
                    id=plan[1].id,
                    delivery_status="delivered",
                    delivery_detail="email ok",
                    delivered_at=datetime.now(timezone.utc),
                ),
            ) as email_mock,
            patch(
                "app.services.notification_pipeline._dispatch_sms",
                return_value=NotificationDispatchResult(
                    id=plan[2].id,
                    delivery_status="delivered",
                    delivery_detail="sms ok",
                    delivered_at=datetime.now(timezone.utc),
                ),
            ) as sms_mock,
            patch(
                "app.services.notification_pipeline._dispatch_webhook",
                return_value=NotificationDispatchResult(
                    id=plan[3].id,
                    delivery_status="delivered",
                    delivery_detail="webhook ok",
                    delivered_at=datetime.now(timezone.utc),
                ),
            ) as webhook_mock,
        ):
            results = dispatch_notification_plan(plan, config)

        self.assertEqual(len(results), 4)
        email_mock.assert_called_once()
        sms_mock.assert_called_once()
        webhook_mock.assert_called_once()
        self.assertEqual(results[0].delivery_status, "delivered")


if __name__ == "__main__":
    unittest.main()
