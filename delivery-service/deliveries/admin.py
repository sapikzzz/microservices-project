from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
import json

from .models import Delivery, DeliveryEvent, DeliveryStatus

STATUS_COLORS = {
    DeliveryStatus.PENDING: '#f59e0b',          # amber
    DeliveryStatus.PICKED_UP: '#3b82f6',        # blue
    DeliveryStatus.READY_FOR_DROPOFF: '#8b5cf6',# violet
    DeliveryStatus.DELIVERED: '#10b981',        # green
    DeliveryStatus.CANCELLED: '#ef4444',        # red
}


class DeliveryEventInline(admin.TabularInline):
    model = DeliveryEvent
    extra = 0
    readonly_fields = ['status', 'note', 'occurred_at']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = [
        'order_id', 'status_badge', 'distance_summary',
        'started_at', 'delivered_at',
    ]
    list_filter = ['status', 'started_at']
    search_fields = ['order_id']
    readonly_fields = [
        'id', 'order_id', 'status_badge',
        'driver_location',
        'restaurant_location',
        'client_location',
        'distance_to_restaurant_m', 'duration_to_restaurant_s',
        'distance_to_client_m', 'duration_to_client_s',
        'route_to_restaurant_pretty', 'route_to_client_pretty',
        'started_at', 'picked_up_at', 'ready_for_dropoff_at', 'delivered_at', 'updated_at',
    ]
    fieldsets = [
        ('Identity', {
            'fields': ['id', 'order_id', 'status_badge'],
        }),
        ('Locations', {
            'fields': [
                ('driver_latitude', 'driver_longitude'),
                ('restaurant_latitude', 'restaurant_longitude'),
                ('client_latitude', 'client_longitude'),
            ],
        }),
        ('Route — Driver → Restaurant', {
            'fields': [
                ('distance_to_restaurant_m', 'duration_to_restaurant_s'),
                'route_to_restaurant_pretty',
            ],
            'classes': ['collapse'],
        }),
        ('Route — Restaurant → Client', {
            'fields': [
                ('distance_to_client_m', 'duration_to_client_s'),
                'route_to_client_pretty',
            ],
            'classes': ['collapse'],
        }),
        ('Timestamps', {
            'fields': [
                'started_at', 'picked_up_at',
                'ready_for_dropoff_at', 'delivered_at', 'updated_at',
            ],
        }),
    ]
    inlines = [DeliveryEventInline]
    ordering = ['-started_at']

    # ------------------------------------------------------------------

    @admin.display(description='Status')
    def status_badge(self, obj):
        color = STATUS_COLORS.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:3px 10px;'
            'border-radius:12px;font-size:12px;font-weight:600;">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description='Distance summary')
    def distance_summary(self, obj):
        parts = []
        if obj.distance_to_restaurant_m:
            parts.append(f'→🍴 {obj.distance_to_restaurant_m / 1000:.1f} km')
        if obj.distance_to_client_m:
            parts.append(f'→📦 {obj.distance_to_client_m / 1000:.1f} km')
        return ' | '.join(parts) or '—'

    def _json_pretty(self, data):
        if not data:
            return mark_safe('<em>not available</em>')
        formatted = json.dumps(data, indent=2)
        return format_html(
            '<pre style="max-height:300px;overflow:auto;background:#1e1e1e;'
            'color:#d4d4d4;padding:10px;border-radius:6px;font-size:11px;">{}</pre>',
            formatted,
        )

    @admin.display(description='Route GeoJSON (driver → restaurant)')
    def route_to_restaurant_pretty(self, obj):
        return self._json_pretty(obj.route_to_restaurant)

    @admin.display(description='Route GeoJSON (restaurant → client)')
    def route_to_client_pretty(self, obj):
        return self._json_pretty(obj.route_to_client)


@admin.register(DeliveryEvent)
class DeliveryEventAdmin(admin.ModelAdmin):
    list_display = ['delivery', 'status', 'note', 'occurred_at']
    list_filter = ['status', 'occurred_at']
    search_fields = ['delivery__order_id', 'note']
    readonly_fields = ['delivery', 'status', 'note', 'occurred_at']
    ordering = ['-occurred_at']
