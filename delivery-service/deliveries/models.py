import uuid
from django.db import models
from django.utils import timezone


class DeliveryStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending — driver assigned, heading to restaurant'
    PICKED_UP = 'PICKED_UP', 'Picked Up — driver heading to client'
    READY_FOR_DROPOFF = 'READY_FOR_DROPOFF', 'Ready for Drop-off'
    DELIVERED = 'DELIVERED', 'Delivered'
    CANCELLED = 'CANCELLED', 'Cancelled'


class Delivery(models.Model):
    # Identity
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_id = models.CharField(max_length=255, unique=True, db_index=True)

    # Customer (from Order Service — no FK, just an int ID)
    customer_id = models.IntegerField(null=True, blank=True, help_text='User ID from User Service')

    # Status
    status = models.CharField(
        max_length=30,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.PENDING,
    )

    driver_location = models.CharField(max_length=500)
    restaurant_location = models.CharField(max_length=500)
    client_location = models.CharField(max_length=500)

    # Route data (GeoJSON from OpenRouteService)
    route_to_restaurant = models.JSONField(null=True, blank=True)
    route_to_client = models.JSONField(null=True, blank=True)

    # Route metadata
    distance_to_restaurant_m = models.FloatField(null=True, blank=True, help_text='metres')
    duration_to_restaurant_s = models.FloatField(null=True, blank=True, help_text='seconds')
    distance_to_client_m = models.FloatField(null=True, blank=True, help_text='metres')
    duration_to_client_s = models.FloatField(null=True, blank=True, help_text='seconds')

    # Timestamps
    started_at = models.DateTimeField(default=timezone.now)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    ready_for_dropoff_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Delivery'
        verbose_name_plural = 'Deliveries'
        ordering = ['-started_at']

    def __str__(self):
        return f'Delivery #{self.order_id} [{self.status}]'

    @property
    def is_active(self):
        return self.status not in (DeliveryStatus.DELIVERED, DeliveryStatus.CANCELLED)

    @property
    def total_distance_m(self):
        d1 = self.distance_to_restaurant_m or 0
        d2 = self.distance_to_client_m or 0
        return d1 + d2

    @property
    def total_duration_s(self):
        d1 = self.duration_to_restaurant_s or 0
        d2 = self.duration_to_client_s or 0
        return d1 + d2


class DeliveryEvent(models.Model):
    """Audit log for every status transition."""
    delivery = models.ForeignKey(Delivery, on_delete=models.CASCADE, related_name='events')
    status = models.CharField(max_length=30, choices=DeliveryStatus.choices)
    note = models.TextField(blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['occurred_at']
        verbose_name = 'Delivery Event'
        verbose_name_plural = 'Delivery Events'

    def __str__(self):
        return f'{self.delivery.order_id} → {self.status} at {self.occurred_at:%Y-%m-%d %H:%M:%S}'
