from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Start RabbitMQ notification consumer"

    def handle(self, *args, **options):
        from notifications.consumer import NotificationEventConsumer

        self.stdout.write("Starting notification consumer...")
        NotificationEventConsumer().start()
