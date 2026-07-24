from django.core.management.base import BaseCommand
from rest_framework_simplejwt.tokens import AccessToken


ROLES = ['customer', 'restaurant', 'driver', 'admin']


class Command(BaseCommand):
    help = 'Generuje testowy token JWT (tylko do lokalnego developmentu)'

    def add_arguments(self, parser):
        parser.add_argument('--user-id', type=int, default=1)
        parser.add_argument('--role', choices=ROLES, default='customer')
        parser.add_argument('--username', default=None)

    def handle(self, *args, **options):
        user_id = options['user_id']
        role = options['role']
        username = options['username'] or f'test_{role}_{user_id}'

        token = AccessToken()
        token['user_id'] = user_id
        token['role'] = role
        token['username'] = username

        self.stdout.write(self.style.SUCCESS('\n=== TOKEN TESTOWY ==='))
        self.stdout.write(f'user_id:  {user_id}')
        self.stdout.write(f'role:     {role}')
        self.stdout.write(f'username: {username}')
        self.stdout.write('\nDo Swaggera (Authorize) — wklej SAM token, bez słowa "Bearer":')
        self.stdout.write(self.style.WARNING(str(token)))
        self.stdout.write('\nDo curl/Bruno (nagłówek):')
        self.stdout.write(f'Authorization: Bearer {token}')
        self.stdout.write('')
