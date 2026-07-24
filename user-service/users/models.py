from django.db import models
from django.contrib.auth.models import AbstractUser
import uuid


class User(AbstractUser):
    ROLE_CUSTOMER = 'customer'
    ROLE_DRIVER = 'driver'
    ROLE_ADMIN = 'admin'
    ROLE_RESTAURANT = 'restaurant'

    ROLE_CHOICES = (
        (ROLE_CUSTOMER, 'Customer'),
        (ROLE_DRIVER, 'Driver'),
        (ROLE_ADMIN, 'Admin'),
        (ROLE_RESTAURANT, 'Restaurant'),
    )

    phone_number = models.CharField(max_length=15, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_CUSTOMER)

    def __str__(self):
        return self.username


class DeliveryAddress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    street = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=10)
    is_default = models.BooleanField(default=False)


class UserPreference(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='preferences')
    is_vegan = models.BooleanField(default=False)
    is_gluten_free = models.BooleanField(default=False)
    newsletter_agreed = models.BooleanField(default=True)


class FavoriteRestaurant(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorites')
    # Storing only ID from other microservices
    restaurant_id = models.UUIDField()

    class Meta:
        unique_together = ('user', 'restaurant_id')
