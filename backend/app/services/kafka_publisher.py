import json

from kafka import KafkaProducer

from app.config import settings


class AlertKafkaPublisher:
    def __init__(self) -> None:
        self.enabled = settings.enable_kafka_publish
        self.topic = settings.kafka_topic_alerts
        self._producer: KafkaProducer | None = None

    def _get_producer(self) -> KafkaProducer:
        if self._producer is None:
            self._producer = KafkaProducer(
                bootstrap_servers=settings.kafka_bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                retries=2,
            )
        return self._producer

    def publish_alert(self, alert: dict) -> None:
        if not self.enabled:
            return
        producer = self._get_producer()
        producer.send(self.topic, alert)
        producer.flush(2)
