from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Start the RabbitMQ order event consumer"

    def handle(self, *args, **options):
        from restaurants.messaging.consumer import OrderEventConsumer
        consumer = OrderEventConsumer()
        consumer.start()
