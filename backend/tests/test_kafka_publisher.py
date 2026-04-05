from pathlib import Path
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("ALLOW_INSECURE_DEFAULTS", "false")
os.environ.setdefault("JWT_SECRET_KEY", "anomalyguard-test-jwt-0123456789abcdef0123456789")
os.environ.setdefault("ADMIN_USERNAME", "test-admin")
os.environ.setdefault("ADMIN_PASSWORD", "AnomalyGuardTestAdmin!2026")
os.environ.setdefault("DEVICE_API_KEY", "anomalyguard-test-device-key-0123456789")
os.environ.setdefault("CORS_ALLOW_ORIGINS", "http://testserver")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEPS_ROOT = BACKEND_ROOT / ".deps"
if DEPS_ROOT.exists() and str(DEPS_ROOT) not in sys.path:
    sys.path.insert(0, str(DEPS_ROOT))

from app.services import kafka_publisher


class KafkaPublisherTests(unittest.TestCase):
    def test_publish_alert_skips_when_disabled(self) -> None:
        with patch.object(kafka_publisher.settings, "enable_kafka_publish", False), patch(
            "app.services.kafka_publisher.KafkaProducer"
        ) as producer_cls:
            publisher = kafka_publisher.AlertKafkaPublisher()
            publisher.publish_alert({"id": "alert-1"})

        producer_cls.assert_not_called()

    def test_publish_alert_sends_to_configured_topic_when_enabled(self) -> None:
        producer = MagicMock()

        with patch.object(kafka_publisher.settings, "enable_kafka_publish", True), patch.object(
            kafka_publisher.settings,
            "kafka_topic_alerts",
            "anomaly-alerts",
        ), patch("app.services.kafka_publisher.KafkaProducer", return_value=producer) as producer_cls:
            publisher = kafka_publisher.AlertKafkaPublisher()
            publisher.publish_alert({"id": "alert-2"})

        producer_cls.assert_called_once()
        producer.send.assert_called_once_with("anomaly-alerts", {"id": "alert-2"})
        producer.flush.assert_called_once_with(2)
