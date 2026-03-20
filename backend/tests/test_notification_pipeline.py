import unittest
from datetime import datetime, timezone

from app.schemas import AnomalyAlert, StationProfile
from app.services.notification_pipeline import build_notification_plan


class NotificationPipelineTests(unittest.TestCase):
    def test_builds_operator_and_public_health_notifications_for_high_risk(self) -> None:
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
        self.assertEqual(channels[0], "ops-log")
        self.assertIn("duty-operator", channels)
        self.assertIn("public-health", channels)

    def test_low_risk_plan_keeps_single_operator_contact(self) -> None:
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

        self.assertEqual(len(plan), 2)
        self.assertEqual(plan[1].recipient, "canal operator")


if __name__ == "__main__":
    unittest.main()
