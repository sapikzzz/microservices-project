"""RabbitMQ consumer — nasłuchuje zdarzeń z order.events.

Obsługuje:
  - `delivery.requested` — auto-tworzy dostawę gdy zamówienie jest gotowe do odbioru
  - `order.cancelled`    — oznacza powiązaną dostawę jako CANCELLED

Dodatkowo uruchamia wątek watchdog, który co 60 sekund sprawdza czy jakieś dostawy
w statusie READY_FOR_DROPOFF nie zostały nieskompletowane przez >10 minut i je anuluje.

Działa jako osobny proces (`python manage.py start_consumer`).
"""
import json
import logging
import threading
import time

import pika
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

DRIVER_PLACEHOLDER = "Centrum dystrybucji, Warszawa"

# Ile minut po dropoff delivery jest automatycznie anulowane
DROPOFF_AUTO_CANCEL_MINUTES = 10

# Co ile sekund watchdog sprawdza bazę
WATCHDOG_INTERVAL_SECONDS = 60


class OrderEventConsumer:
    EXCHANGE = "order.events"
    QUEUE = "delivery_service_queue"
    ROUTING_KEYS = ("order.cancelled", "delivery.requested")

    def __init__(self):
        self.connection = None
        self.channel = None

    def connect(self):
        params = pika.URLParameters(settings.RABBITMQ_URL)
        self.connection = pika.BlockingConnection(params)
        self.channel = self.connection.channel()
        self.channel.exchange_declare(exchange=self.EXCHANGE, exchange_type="topic", durable=True)
        self.channel.queue_declare(queue=self.QUEUE, durable=True)
        for routing_key in self.ROUTING_KEYS:
            self.channel.queue_bind(exchange=self.EXCHANGE, queue=self.QUEUE, routing_key=routing_key)

    def handle_delivery_requested(self, payload: dict):
        from deliveries.models import Delivery, DeliveryEvent, DeliveryStatus

        order_id = str(payload.get("order_id"))
        if Delivery.objects.filter(order_id=order_id).exists():
            logger.info("delivery.requested: dostawa dla order_id=%s już istnieje — pomijam", order_id)
            return

        client_location = (payload.get("delivery_address") or "").strip()
        lat = payload.get("restaurant_lat")
        lng = payload.get("restaurant_lng")
        restaurant_location = f"{lat},{lng}" if lat is not None and lng is not None else ""

        if not client_location or not restaurant_location:
            logger.warning(
                "delivery.requested: brak adresu klienta lub współrzędnych restauracji (order_id=%s)",
                order_id,
            )
            return

        # customer_id is passed by order-service in the delivery.requested event
        customer_id = payload.get("customer_id")

        delivery = Delivery.objects.create(
            order_id=order_id,
            customer_id=customer_id,
            driver_location=DRIVER_PLACEHOLDER,
            restaurant_location=restaurant_location,
            client_location=client_location,
            status=DeliveryStatus.PENDING,
        )
        DeliveryEvent.objects.create(
            delivery=delivery,
            status=DeliveryStatus.PENDING,
            note="Auto-utworzona z delivery.requested (kurier = placeholder).",
        )
        logger.info(
            "Auto-utworzono dostawę dla order_id=%s customer_id=%s",
            order_id, customer_id,
        )

    def handle_order_cancelled(self, payload: dict):
        from deliveries.models import Delivery, DeliveryEvent, DeliveryStatus
        from deliveries.rabbitmq import publish_delivery_notification

        order_id = str(payload.get("order_id"))
        delivery = Delivery.objects.filter(order_id=order_id).first()
        if not delivery:
            logger.warning("order.cancelled: brak dostawy dla order_id=%s", order_id)
            return
        if delivery.status in (DeliveryStatus.DELIVERED, DeliveryStatus.CANCELLED):
            logger.info("order.cancelled: dostawa %s już %s — pomijam", order_id, delivery.status)
            return

        delivery.status = DeliveryStatus.CANCELLED
        delivery.cancelled_at = timezone.now()
        delivery.save()
        DeliveryEvent.objects.create(
            delivery=delivery,
            status=DeliveryStatus.CANCELLED,
            note="Anulowane przez klienta (order.cancelled)",
        )
        if delivery.customer_id:
            publish_delivery_notification(order_id, DeliveryStatus.CANCELLED, delivery.customer_id)
        logger.info("Dostawa dla order_id=%s oznaczona jako CANCELLED", order_id)

    def _on_message(self, ch, method, properties, body):
        try:
            payload = json.loads(body)
            if method.routing_key == "delivery.requested":
                self.handle_delivery_requested(payload)
            elif method.routing_key == "order.cancelled":
                self.handle_order_cancelled(payload)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            logger.error("Błąd przetwarzania wiadomości: %s", e)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def start(self):
        # Uruchom watchdog w osobnym wątku
        watchdog = threading.Thread(
            target=_dropoff_watchdog,
            daemon=True,
            name="dropoff-watchdog",
        )
        watchdog.start()
        logger.info("Watchdog auto-cancel uruchomiony (interwał=%ds, limit=%dmin)",
                    WATCHDOG_INTERVAL_SECONDS, DROPOFF_AUTO_CANCEL_MINUTES)

        self.connect()
        self.channel.basic_consume(queue=self.QUEUE, on_message_callback=self._on_message)
        logger.info("Uruchomiono consumer zdarzeń order.events...")
        self.channel.start_consuming()


def _dropoff_watchdog():
    """
    Wątek działający w tle — co WATCHDOG_INTERVAL_SECONDS sprawdza dostawy
    w statusie READY_FOR_DROPOFF, których ready_for_dropoff_at minęło
    ponad DROPOFF_AUTO_CANCEL_MINUTES minut temu, i automatycznie je anuluje.

    Działa w osobnym procesie (consumer), więc nie interferuje z Gunicorn workers.
    """
    import django
    from django.db import connection as db_connection

    # Daj chwilę na startup Django
    time.sleep(5)

    while True:
        try:
            from deliveries.models import Delivery, DeliveryEvent, DeliveryStatus
            from deliveries.rabbitmq import publish_delivery_event, publish_delivery_notification

            cutoff = timezone.now() - timezone.timedelta(minutes=DROPOFF_AUTO_CANCEL_MINUTES)
            expired = Delivery.objects.filter(
                status=DeliveryStatus.READY_FOR_DROPOFF,
                ready_for_dropoff_at__lte=cutoff,
            )

            for delivery in expired:
                delivery.status = DeliveryStatus.CANCELLED
                delivery.cancelled_at = timezone.now()
                delivery.save(update_fields=['status', 'cancelled_at', 'updated_at'])

                DeliveryEvent.objects.create(
                    delivery=delivery,
                    status=DeliveryStatus.CANCELLED,
                    note=f"Auto-anulowana — brak potwierdzenia dostarczenia przez {DROPOFF_AUTO_CANCEL_MINUTES} minut od dropoff.",
                )

                publish_delivery_event(delivery.order_id, DeliveryStatus.CANCELLED)
                if delivery.customer_id:
                    publish_delivery_notification(
                        delivery.order_id,
                        DeliveryStatus.CANCELLED,
                        delivery.customer_id,
                    )
                logger.warning(
                    "Auto-cancelled delivery order_id=%s (READY_FOR_DROPOFF od %s)",
                    delivery.order_id, delivery.ready_for_dropoff_at,
                )

        except Exception as exc:
            logger.error("Watchdog błąd: %s", exc)
        finally:
            # Zwolnij połączenie z DB po każdej iteracji (threading + Django best practice)
            try:
                db_connection.close()
            except Exception:
                pass

        time.sleep(WATCHDOG_INTERVAL_SECONDS)
