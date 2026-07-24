from django.core.management.base import BaseCommand

from orders.messaging.consumer import start_consuming


class Command(BaseCommand):
    help = 'Start RabbitMQ consumer for order service'

    def handle(self, *args, **options):
        self.stdout.write('Starting RabbitMQ consumer...')
        start_consuming()
