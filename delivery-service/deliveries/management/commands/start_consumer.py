from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Start the RabbitMQ order event consumer (order.cancelled)"

    def handle(self, *args, **options):
        from deliveries.consumer import OrderEventConsumer
        OrderEventConsumer().start()
