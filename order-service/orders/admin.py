from django.contrib import admin

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['subtotal']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer_id', 'restaurant_id', 'status', 'total_price', 'created_at']
    list_filter = ['status']
    search_fields = ['delivery_address']
    readonly_fields = ['created_at', 'updated_at', 'delivered_at', 'cancelled_at']
    inlines = [OrderItemInline]
