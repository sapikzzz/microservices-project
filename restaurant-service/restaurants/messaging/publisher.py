import json
import logging

import pika
from django.conf import settings

logger = logging.getLogger(__name__)


class EventPublisher:
    _instance = None
    _connection = None
    _channel = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _connect(self):
        params = pika.URLParameters(settings.RABBITMQ_URL)
        self._connection = pika.BlockingConnection(params)
        self._channel = self._connection.channel()

    def _ensure_connected(self):
        try:
            if self._channel is None or self._channel.is_closed:
                self._connect()
        except Exception:
            self._connect()

    def publish(self, exchange: str, routing_key: str, payload: dict):
        try:
            if exchange == "order.events":
                from restaurants.validation import get_errors
                errors = get_errors(payload, "order_status_event.json")
                if errors:
                    logger.error("Invalid RabbitMQ event %s payload: %s", routing_key, errors)
                    return

            self._ensure_connected()
            self._channel.exchange_declare(exchange=exchange, exchange_type="topic", durable=True)
            self._channel.basic_publish(
                exchange=exchange,
                routing_key=routing_key,
                body=json.dumps(payload),
                properties=pika.BasicProperties(delivery_mode=2),
            )
        except Exception as e:
            logger.error("Failed to publish RabbitMQ event %s: %s", routing_key, e)


publisher = EventPublisher()


def publish_kafka_event(restaurant_id: int, status: str, name: str, event_type: str):
    try:
        from confluent_kafka import Producer
        conf = {"bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS}
        producer = Producer(conf)
        payload = json.dumps({
            "restaurant_id": restaurant_id,
            "status": status,
            "name": name,
            "event_type": event_type,
        })
        producer.produce("restaurant.events", key=str(restaurant_id), value=payload)
        producer.flush(timeout=5)
    except Exception as e:
        logger.warning("Kafka event publish failed (%s): %s", event_type, e)
