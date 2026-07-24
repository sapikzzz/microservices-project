import json
import logging
from uuid import uuid4

import pika
from django.conf import settings

logger = logging.getLogger(__name__)


def publish_notification_event(routing_key: str, payload: dict):
    message = {
        "event_id": str(uuid4()),
        **payload,
    }
    try:
        connection = pika.BlockingConnection(pika.URLParameters(settings.RABBITMQ_URL))
        channel = connection.channel()
        channel.exchange_declare(exchange="notification.events", exchange_type="topic", durable=True)
        channel.basic_publish(
            exchange="notification.events",
            routing_key=routing_key,
            body=json.dumps(message),
            properties=pika.BasicProperties(delivery_mode=2),
        )
        connection.close()
        logger.info("Published notification event %s", routing_key)
    except Exception as e:
        logger.error("Failed to publish notification event %s: %s", routing_key, e)


def publish_order_status_notification(order):
    publish_notification_event(
        "notification.order_status_changed",
        {
            "event_type": "order.status_changed",
            "recipient_user_id": order.customer_id,
            "subject": f"Status zamówienia #{order.id}: {order.get_status_display()}",
            "message": (
                f"Status Twojego zamówienia #{order.id} w restauracji "
                f"{order.restaurant_name or order.restaurant_id} zmienił się na: "
                f"{order.get_status_display()}."
            ),
            "order_id": order.id,
            "restaurant_id": order.restaurant_id,
            "status": order.status,
        },
    )
