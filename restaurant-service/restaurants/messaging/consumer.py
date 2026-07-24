import json
import logging

import pika
from django.conf import settings

logger = logging.getLogger(__name__)


class OrderEventConsumer:
    def __init__(self):
        self.connection = None
        self.channel = None

    def connect(self):
        params = pika.URLParameters(settings.RABBITMQ_URL)
        self.connection = pika.BlockingConnection(params)
        self.channel = self.connection.channel()
        self.channel.exchange_declare(exchange="order.events", exchange_type="topic", durable=True)
        self.channel.queue_declare(queue="restaurant_service_queue", durable=True)
        self.channel.queue_bind(
            exchange="order.events",
            queue="restaurant_service_queue",
            routing_key="order.created",
        )
        self.channel.queue_bind(
            exchange="order.events",
            queue="restaurant_service_queue",
            routing_key="order.cancelled",
        )

    def handle_order_created(self, payload: dict):
        from django.db import transaction
        from restaurants.models import IncomingOrder, Restaurant
        from restaurants.validation import get_errors

        try:
            errors = get_errors(payload, "order_created_event.json")
            if errors:
                logger.warning("Invalid order.created payload: %s", errors)
                return

            restaurant = Restaurant.objects.get(pk=payload["restaurant_id"])
            with transaction.atomic():
                IncomingOrder.objects.create(
                    order_id=payload["order_id"],
                    restaurant=restaurant,
                    items_snapshot=payload["items"],
                    total_price=payload["total_price"],
                )
            logger.info("Created IncomingOrder for order_id=%s", payload["order_id"])
        except Exception as e:
            logger.error("Failed to handle order.created: %s", e)

    def handle_order_cancelled(self, payload: dict):
        from restaurants.models import IncomingOrder

        try:
            updated = IncomingOrder.objects.filter(
                order_id=payload["order_id"],
            ).update(status=IncomingOrder.STATUS_CANCELLED)
            if updated:
                logger.info("IncomingOrder %s marked CANCELLED", payload["order_id"])
            else:
                logger.warning("order.cancelled: IncomingOrder %s not found", payload.get("order_id"))
        except Exception as e:
            logger.error("Failed to handle order.cancelled: %s", e)

    def _on_message(self, ch, method, properties, body):
        try:
            payload = json.loads(body)
            if method.routing_key == "order.cancelled":
                self.handle_order_cancelled(payload)
            else:
                self.handle_order_created(payload)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            logger.error("Error processing message: %s", e)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def start(self):
        self.connect()
        self.channel.basic_consume(
            queue="restaurant_service_queue",
            on_message_callback=self._on_message,
        )
        logger.info("Starting order event consumer...")
        self.channel.start_consuming()
