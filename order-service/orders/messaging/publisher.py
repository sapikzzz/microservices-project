import json
import logging

import pika
from django.conf import settings

logger = logging.getLogger(__name__)

EXCHANGE = 'order.events'


def _publish(routing_key: str, message: dict) -> None:
    try:
        connection = pika.BlockingConnection(pika.URLParameters(settings.RABBITMQ_URL))
        channel = connection.channel()
        channel.exchange_declare(exchange=EXCHANGE, exchange_type='topic', durable=True)
        channel.basic_publish(
            exchange=EXCHANGE,
            routing_key=routing_key,
            body=json.dumps(message),
            properties=pika.BasicProperties(delivery_mode=2),
        )
        connection.close()
        logger.info(f'Published {routing_key} for order {message.get("order_id")}')
    except Exception as e:
        logger.error(f'Failed to publish {routing_key} for order {message.get("order_id")}: {e}')


def publish_order_created(order) -> None:
    _publish('order.created', {
        'order_id': order.id,
        'restaurant_id': order.restaurant_id,
        'items': [
            {
                'menu_item_id': item.menu_item_id,
                'name': item.name,
                'quantity': item.quantity,
                'unit_price': str(item.unit_price),
                'notes': '',
            }
            for item in order.items.all()
        ],
        'total_price': str(order.total_price),
    })


def publish_order_cancelled(order) -> None:
    """Powiadamia restaurację i delivery, że zamówienie zostało anulowane."""
    _publish('order.cancelled', {
        'order_id': order.id,
        'restaurant_id': order.restaurant_id,
    })


def publish_delivery_requested(order, restaurant_lat=None, restaurant_lng=None) -> None:
    """Prosi delivery-service o utworzenie dostawy — po osiągnięciu ready_for_pickup.

    Niesie adres dostawy (zna go tylko order-service) oraz współrzędne restauracji
    przekazane w zdarzeniu order.ready_for_pickup.
    """
    _publish('delivery.requested', {
        'order_id': order.id,
        'delivery_address': order.delivery_address,
        'restaurant_lat': restaurant_lat,
        'restaurant_lng': restaurant_lng,
    })
