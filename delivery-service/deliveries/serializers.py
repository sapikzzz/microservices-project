from rest_framework import serializers
from .models import Delivery, DeliveryEvent, DeliveryStatus


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------

class DeliveryEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryEvent
        fields = ['id', 'status', 'note', 'occurred_at']


# ---------------------------------------------------------------------------
# Delivery — read
# ---------------------------------------------------------------------------

class DeliverySerializer(serializers.ModelSerializer):
    events = DeliveryEventSerializer(many=True, read_only=True)
    total_distance_m = serializers.FloatField(read_only=True)
    total_duration_s = serializers.FloatField(read_only=True)

    class Meta:
        model = Delivery
        fields = [
            'id',
            'order_id',
            'customer_id',
            'status',
            'driver_location',
            'restaurant_location',
            'client_location',
            'distance_to_restaurant_m', 'duration_to_restaurant_s',
            'distance_to_client_m',     'duration_to_client_s',
            'total_distance_m',         'total_duration_s',
            'started_at', 'picked_up_at', 'ready_for_dropoff_at',
            'delivered_at', 'cancelled_at', 'updated_at',
            'events',
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Delivery — start (create)
# ---------------------------------------------------------------------------

class StartDeliverySerializer(serializers.Serializer):
    order_id = serializers.CharField(
        max_length=255,
        help_text='Unique identifier of the order from the Order Service.',
    )
    customer_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        default=None,
        help_text='User ID from User Service. Used to send delivery notifications to the customer.',
    )
    driver_location = serializers.CharField(
        help_text='Current address of the driver. e.g. "ul. Kowalska 5, Warszawa"',
    )
    restaurant_location = serializers.CharField(
        help_text='Full street address of the restaurant. e.g. "ul. Nowy Swiat 6/12, Warszawa"',
    )
    client_location = serializers.CharField(
        required=False,
        allow_blank=True,
        default='',
        help_text='Delivery destination address. Optional — can be provided at /pickup/ instead.',
    )

    def validate_order_id(self, value):
        if Delivery.objects.filter(order_id=value).exists():
            raise serializers.ValidationError(
                f'A delivery for order_id "{value}" already exists.'
            )
        return value


# ---------------------------------------------------------------------------
# Pickup
# ---------------------------------------------------------------------------

class PickupSerializer(serializers.Serializer):
    client_location = serializers.CharField(
        required=False,
        allow_blank=True,
        default='',
        help_text='Delivery destination address. Required if not set at delivery start.',
    )


# ---------------------------------------------------------------------------
# Update client location
# ---------------------------------------------------------------------------

class UpdateClientLocationSerializer(serializers.Serializer):
    client_location = serializers.CharField(
        help_text='New delivery destination address. e.g. "ul. Nowy Świat 15, Warszawa"',
    )


# ---------------------------------------------------------------------------
# Route response
# ---------------------------------------------------------------------------

class RouteSerializer(serializers.Serializer):
    leg        = serializers.ChoiceField(choices=['to_restaurant', 'to_client'])
    distance_m = serializers.FloatField(allow_null=True)
    duration_s = serializers.FloatField(allow_null=True)
    geojson    = serializers.JSONField(allow_null=True)


# ---------------------------------------------------------------------------
# Simple message response
# ---------------------------------------------------------------------------

class MessageSerializer(serializers.Serializer):
    detail = serializers.CharField()
