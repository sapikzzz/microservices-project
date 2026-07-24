import json
import logging

import pika
from django.conf import settings
from django.utils import timezone

from orders.validation import get_errors
from orders.messaging.notifications import publish_order_status_notification
from orders.messaging.publisher import publish_delivery_requested

logger = logging.getLogger(__name__)

STATUS_MAP = {
    'order.accepted_by_restaurant': 'accepted',
    'order.rejected_by_restaurant': 'cancelled',
    'order.preparing': 'in_preparation',
    'order.ready_for_pickup': 'ready_for_pickup',
    'order.picked_up': 'picked_up',
    'order.in_delivery': 'in_delivery',
    'order.delivered': 'delivered',
    'order.cancelled': 'cancelled',
}


def handle_message(ch, method, properties, body):
    from orders.models import Order

    try:
        data = json.loads(body)

        # Walidacja danych wejściowych z innego serwisu względem JSON Schema.
        errors = get_errors(data, 'order_event.json')
        if errors:
            logger.warning(f'Niepoprawna wiadomość ({method.routing_key}): {errors}')
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        order_id = data['order_id']
        routing_key = method.routing_key
        new_status = STATUS_MAP.get(routing_key)

        if not new_status:
            logger.warning(f'Unknown routing key: {routing_key}')
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        update_fields = {'status': new_status}
        if new_status == 'cancelled':
            update_fields['cancelled_at'] = timezone.now()
        elif new_status == 'delivered':
            update_fields['delivered_at'] = timezone.now()

        order = Order.objects.filter(id=order_id).first()
        if not order:
            logger.warning(f'Order {order_id} not found')
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        # Stany terminalne — spóźnione zdarzenie nie może ich nadpisać.
        if order.status in (Order.Status.CANCELLED, Order.Status.DELIVERED):
            logger.info(
                f'Order {order_id} w stanie terminalnym ({order.status}) — ignoruję {routing_key}'
            )
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        for field, value in update_fields.items():
            setattr(order, field, value)
        order.save(update_fields=[*update_fields.keys(), 'updated_at'])
        logger.info(f'Order {order_id} status → {new_status}')
        publish_order_status_notification(order)

        # Po osiągnięciu ready_for_pickup prosimy delivery-service o utworzenie dostawy.
        if routing_key == 'order.ready_for_pickup':
            publish_delivery_requested(order, data.get('lat'), data.get('lng'))

        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        logger.error(f'Error handling message: {e}')
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def start_consuming():
    connection = pika.BlockingConnection(pika.URLParameters(settings.RABBITMQ_URL))
    channel = connection.channel()
    channel.exchange_declare(exchange='order.events', exchange_type='topic', durable=True)
    channel.queue_declare(queue='order_service_queue', durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='order_service_queue', on_message_callback=handle_message)
    logger.info('Consumer started, waiting for messages...')
    channel.start_consuming()
