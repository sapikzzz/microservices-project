from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('customer', 'Customer'),
                    ('driver', 'Driver'),
                    ('admin', 'Admin'),
                    ('restaurant', 'Restaurant'),
                ],
                default='customer',
                max_length=20,
            ),
        ),
    ]
