"""
RabbitMQ event publisher for delivery status changes.

Designed to fail gracefully — if RABBITMQ_URL is not set or the broker
is unreachable, events are logged and dropped rather than crashing the request.

Delivery statuses are published to the shared `order.events` exchange so
that order-service consumer can pick them up with its existing STATUS_MAP.
Statuses that have no corresponding order routing key (PENDING) are skipped
for order.events but logged locally.

Exchange: order.events  (topic, durable)
Routing keys published by this service:
  order.picked_up           ← delivery PICKED_UP
  order.in_delivery         ← delivery READY_FOR_DROPOFF
  order.delivered           ← delivery DELIVERED
  order.cancelled           ← delivery CANCELLED

Exchange: notification.events  (topic, durable)
Routing keys published by this service:
  notification.delivery_status  ← any pickup/dropoff/cancel with customer_id
"""

import json
import logging
from uuid import uuid4

logger = logging.getLogger(__name__)

# Mapping: DeliveryStatus value (lowercase) → routing key on order.events.
# None means "don't publish to order.events" (no order-level transition).
_DELIVERY_TO_ORDER_ROUTING_KEY = {
    'pending':           None,              # order already knows about the delivery start
    'picked_up':         'order.picked_up',
    'ready_for_dropoff': 'order.in_delivery',
    'delivered':         'order.delivered',
    'cancelled':         'order.cancelled',
}

_DELIVERY_STATUS_LABELS = {
    'picked_up':         'Kurier odebrał zamówienie',
    'ready_for_dropoff': 'Zamówienie w drodze do Ciebie',
    'delivered':         'Zamówienie dostarczone',
    'cancelled':         'Dostawa anulowana',
}


def _get_pika_channel():
    """Return a fresh pika connection+channel or raise ImportError/Exception."""
    import pika
    from django.conf import settings
    url: str = getattr(settings, 'RABBITMQ_URL', '') or ''
    if not url:
        raise ValueError('RABBITMQ_URL not configured')
    params = pika.URLParameters(url)
    params.socket_timeout = 3
    params.connection_attempts = 1
    connection = pika.BlockingConnection(params)
    return connection, connection.channel()


def publish_delivery_event(order_id: str, status: str, extra: dict | None = None) -> None:
    """
    Publish a delivery status-change event to RabbitMQ → order.events exchange.

    Safe to call unconditionally — silently skips if:
      - RABBITMQ_URL is not configured
      - pika is not installed
      - The broker is unreachable
      - The delivery status has no corresponding order routing key
    """
    from django.conf import settings
    url: str = getattr(settings, 'RABBITMQ_URL', '') or ''
    if not url:
        logger.debug(
            'RABBITMQ_URL not configured — skipping event publish '
            '(order_id=%s status=%s)', order_id, status,
        )
        return

    routing_key = _DELIVERY_TO_ORDER_ROUTING_KEY.get(status.lower())
    if routing_key is None:
        logger.debug(
            'Delivery status %r has no order.events routing key — skipping publish '
            '(order_id=%s)', status, order_id,
        )
        return

    try:
        import pika
    except ImportError:
        logger.warning('pika is not installed — RabbitMQ publishing unavailable.')
        return

    payload = json.dumps({
        'order_id': order_id,
        'status': status,
        **(extra or {}),
    })

    try:
        connection, channel = _get_pika_channel()
        channel.exchange_declare(exchange='order.events', exchange_type='topic', durable=True)
        channel.basic_publish(
            exchange='order.events',
            routing_key=routing_key,
            body=payload.encode(),
            properties=pika.BasicProperties(
                content_type='application/json',
                delivery_mode=2,
            ),
        )
        connection.close()
        logger.info(
            'Published delivery event to order.events: order_id=%s status=%s routing_key=%s',
            order_id, status, routing_key,
        )
    except Exception as exc:
        logger.warning(
            'Failed to publish RabbitMQ event (order_id=%s status=%s): %s',
            order_id, status, exc,
        )


def publish_delivery_notification(order_id: str, status: str, customer_id: int) -> None:
    """
    Publish a customer-facing notification to notification.events exchange.

    Called on PICKED_UP, READY_FOR_DROPOFF, DELIVERED, CANCELLED.
    Skips gracefully if customer_id is None or RABBITMQ_URL is not configured.
    """
    if not customer_id:
        return

    label = _DELIVERY_STATUS_LABELS.get(status.lower())
    if not label:
        return

    try:
        import pika
    except ImportError:
        logger.warning('pika is not installed — notification publishing unavailable.')
        return

    payload = json.dumps({
        'event_id': str(uuid4()),
        'event_type': 'order.status_changed',
        'recipient_user_id': customer_id,
        'subject': f'Aktualizacja dostawy zamówienia #{order_id}',
        'message': f'{label}. Numer zamówienia: #{order_id}.',
        'order_id': order_id,
        'status': status,
    })

    try:
        connection, channel = _get_pika_channel()
        channel.exchange_declare(exchange='notification.events', exchange_type='topic', durable=True)
        channel.basic_publish(
            exchange='notification.events',
            routing_key='notification.delivery_status',
            body=payload.encode(),
            properties=pika.BasicProperties(
                content_type='application/json',
                delivery_mode=2,
            ),
        )
        connection.close()
        logger.info(
            'Published delivery notification: order_id=%s status=%s customer_id=%s',
            order_id, status, customer_id,
        )
    except Exception as exc:
        logger.warning(
            'Failed to publish notification (order_id=%s customer_id=%s): %s',
            order_id, customer_id, exc,
        )
