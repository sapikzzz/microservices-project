#!/bin/sh
set -e

echo "==> Waiting for PostgreSQL..."
until python -c "
import psycopg2, os
psycopg2.connect(
    dbname=os.environ.get('POSTGRES_DB','deliveries'),
    user=os.environ.get('POSTGRES_USER','postgres'),
    password=os.environ.get('POSTGRES_PASSWORD','postgres'),
    host=os.environ.get('POSTGRES_HOST','db'),
    port=os.environ.get('POSTGRES_PORT','5432'),
)
" 2>/dev/null; do
  sleep 1
done
echo "==> PostgreSQL is ready."

echo "==> Running migrations..."
python manage.py makemigrations deliveries --noinput
python manage.py migrate --noinput

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

echo "==> Creating superuser (if not exists)..."
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
username = '${DJANGO_SUPERUSER_USERNAME:-admin}'
email = '${DJANGO_SUPERUSER_EMAIL:-admin@example.com}'
password = '${DJANGO_SUPERUSER_PASSWORD:-admin}'
if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username, email, password)
    print(f'Superuser \"{username}\" created.')
else:
    print(f'Superuser \"{username}\" already exists.')
"

echo "==> Starting Gunicorn..."
exec gunicorn delivery_service.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-2}" \
    --threads "${GUNICORN_THREADS:-4}" \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
