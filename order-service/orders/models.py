from django.db import models


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING_PAYMENT = 'pending_payment', 'Oczekuje na płatność'
        PAID = 'paid', 'Opłacone'
        ACCEPTED = 'accepted', 'Przyjęte przez restaurację'
        IN_PREPARATION = 'in_preparation', 'W przygotowaniu'
        READY_FOR_PICKUP = 'ready_for_pickup', 'Gotowe do odbioru'
        PICKED_UP = 'picked_up', 'Odebrane przez kuriera'
        IN_DELIVERY = 'in_delivery', 'W dostawie'
        DELIVERED = 'delivered', 'Dostarczone'
        CANCELLED = 'cancelled', 'Anulowane'

    # ID użytkownika z User Service, brak FK, brak lokalnego modelu User
    customer_id = models.IntegerField()

    # Snapshot z Restaurant Service, brak FK
    restaurant_id = models.IntegerField()
    restaurant_name = models.CharField(max_length=200, blank=True)

    delivery_address = models.TextField()
    notes = models.TextField(blank=True)

    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING_PAYMENT)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    # Wypełniane przez PayU webhook
    payment_id = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Zamówienie #{self.pk} [{self.get_status_display()}]'


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)

    # Snapshot z momentu złożenia, nie trzymamy żywego FK do Restaurant Service
    menu_item_id = models.IntegerField()
    name = models.CharField(max_length=200)
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)
    quantity = models.PositiveIntegerField()

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f'{self.quantity}x {self.name} @ {self.unit_price}'
