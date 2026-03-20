import unittest
from datetime import datetime, timezone

from app.schemas import StationProfile, WaterReading
from app.services.detector import DetectionResult
from app.services.risk_policy import build_community_alert, validate_status_transition


class RiskPolicyTests(unittest.TestCase):
    def test_builds_critical_drinking_water_alert(self) -> None:
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
        reading = WaterReading(
            timestamp=datetime.now(timezone.utc),
            station_id=station.station_id,
            ph=5.8,
            tds=680.0,
            turbidity=14.2,
            temperature_c=29.0,
            do_mg_l=6.0,
            flow_l_min=1100.0,
        )
        result = DetectionResult(
            is_anomaly=True,
            score=0.84,
            severity="high",
            reasons=["ph outside safe range", "turbidity outside safe range"],
            contributions={"turbidity": 3.2, "ph": 2.1, "tds": 1.7},
        )

        alert = build_community_alert(reading, station, result, alert_id="a1")

        self.assertEqual(alert.community_risk_level, "critical")
        self.assertIn("households", alert.affected_groups)
        self.assertIn("schoolchildren", alert.affected_groups)
        self.assertIn("Inspect intake conditions", " ".join(alert.recommended_actions))
        self.assertEqual(alert.escalation_target, "district water operator + community health lead")
        self.assertEqual(alert.data_quality_flag, "sensor")

    def test_proxy_source_reduces_confidence(self) -> None:
        station = StationProfile(
            station_id="mekong-can-tho",
            station_name="Can Tho River Gate",
            region="Can Tho, Mekong Delta",
            timezone="Asia/Ho_Chi_Minh",
            latitude=10.0,
            longitude=105.7,
            source="api",
            community_name="Can Tho Riverside Communities",
            province="Can Tho",
            water_use_type="mixed",
            population_served=95000,
            households_served=22000,
            schools_nearby=3,
            critical_assets=[],
            escalation_contacts=["district water operator"],
            exposure_notes="Proxy-fed station profile.",
        )
        reading = WaterReading(
            timestamp=datetime.now(timezone.utc),
            station_id=station.station_id,
            ph=7.2,
            tds=440.0,
            turbidity=9.5,
            temperature_c=30.0,
            do_mg_l=4.0,
            flow_l_min=900.0,
        )
        result = DetectionResult(
            is_anomaly=True,
            score=0.61,
            severity="medium",
            reasons=["do_mg_l outside safe range"],
            contributions={"do_mg_l": 2.7, "turbidity": 1.4},
        )

        alert = build_community_alert(reading, station, result, alert_id="a2")

        self.assertEqual(alert.data_quality_flag, "proxy-derived")
        self.assertLess(alert.risk_confidence, 0.8)
        self.assertGreaterEqual(alert.time_to_acknowledge_minutes, 15)

    def test_status_transition_rules(self) -> None:
        self.assertTrue(validate_status_transition("new", "acknowledged"))
        self.assertTrue(validate_status_transition("investigating", "resolved"))
        self.assertFalse(validate_status_transition("resolved", "investigating"))
        self.assertFalse(validate_status_transition("false_positive", "acknowledged"))


if __name__ == "__main__":
    unittest.main()
