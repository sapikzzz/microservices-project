from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("restaurants", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="incomingorder",
            name="payment_confirmed",
        ),
    ]
