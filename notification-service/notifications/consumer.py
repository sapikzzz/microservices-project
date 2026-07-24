import json
import logging

import pika
import requests
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction

from .models import NotificationLog, ProcessedEvent
from .validation import validate_event

logger = logging.getLogger(__name__)


class NotificationEventConsumer:
    def __init__(self):
        self.connection = None
        self.channel = None

    def connect(self):
        self.connection = pika.BlockingConnection(pika.URLParameters(settings.RABBITMQ_URL))
        self.channel = self.connection.channel()
        self.channel.exchange_declare(exchange="notification.events", exchange_type="topic", durable=True)
        self.channel.queue_declare(queue="notification_service_queue", durable=True)
        self.channel.queue_bind(
            exchange="notification.events",
            queue="notification_service_queue",
            routing_key="notification.#",
        )

    def _get_user_email(self, user_id: int) -> str:
        url = f"{settings.USER_SERVICE_URL}/api/users/internal/{user_id}/"
        response = requests.get(
            url,
            headers={"X-Internal-Secret": settings.INTERNAL_SECRET},
            timeout=5,
        )
        response.raise_for_status()
        return response.json().get("email", "")

    def _handle_payload(self, payload: dict):
        validate_event(payload, "notification_event.json")

        event_id = payload["event_id"]
        event_type = payload["event_type"]
        recipient_user_id = payload["recipient_user_id"]
        subject = payload["subject"]
        message = payload["message"]

        if ProcessedEvent.objects.filter(event_id=event_id).exists():
            logger.info("Notification event %s already processed", event_id)
            return

        recipient_email = self._get_user_email(recipient_user_id)
        if not recipient_email:
            NotificationLog.objects.create(
                event_id=event_id,
                event_type=event_type,
                recipient_user_id=recipient_user_id,
                subject=subject,
                status="skipped",
                error="Recipient has no email",
            )
            ProcessedEvent.objects.create(event_id=event_id, event_type=event_type)
            logger.warning("Notification event %s skipped: user has no email", event_id)
            return

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            fail_silently=False,
        )

        with transaction.atomic():
            NotificationLog.objects.create(
                event_id=event_id,
                event_type=event_type,
                recipient_user_id=recipient_user_id,
                recipient_email=recipient_email,
                subject=subject,
                status="sent",
            )
            ProcessedEvent.objects.create(event_id=event_id, event_type=event_type)

        logger.info("Notification event %s sent to %s", event_id, recipient_email)

    def _on_message(self, ch, method, properties, body):
        try:
            payload = json.loads(body)
            self._handle_payload(payload)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            logger.error("Failed to process notification event: %s", e)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def start(self):
        self.connect()
        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(
            queue="notification_service_queue",
            on_message_callback=self._on_message,
        )
        logger.info("Notification consumer started")
        self.channel.start_consuming()
