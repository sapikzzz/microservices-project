import requests
from django.conf import settings
from rest_framework import serializers

from .models import IncomingOrder, Menu, MenuItem, Restaurant

VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
REQUIRED_ADDRESS_KEYS = {"street", "city", "postal_code", "country"}


def _validate_address_format(address):
    if not isinstance(address, dict):
        raise serializers.ValidationError("address must be a JSON object.")
    missing = REQUIRED_ADDRESS_KEYS - address.keys()
    if missing:
        raise serializers.ValidationError(f"address is missing keys: {missing}")


def _validate_opening_hours_format(hours):
    if not isinstance(hours, dict):
        raise serializers.ValidationError("opening_hours must be a JSON object.")
    missing = VALID_DAYS - hours.keys()
    if missing:
        raise serializers.ValidationError(f"opening_hours is missing day keys: {missing}")
    for day, value in hours.items():
        if day not in VALID_DAYS:
            raise serializers.ValidationError(f"Unknown day key: {day}")
        if value is None:
            continue
        if not isinstance(value, list) or len(value) != 2:
            raise serializers.ValidationError(f"opening_hours[{day}] must be null or a list of two time strings.")


def _validate_address_nominatim(address: dict):
    url = settings.OSM_NOMINATIM_URL + "/search"
    params = {
        "street": address.get("street", ""),
        "city": address.get("city", ""),
        "postalcode": address.get("postal_code", ""),
        "country": address.get("country", ""),
        "format": "json",
        "limit": 1,
    }
    headers = {"User-Agent": "FoodOrderingPlatform/1.0"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=5)
        results = response.json()
        if not results:
            raise serializers.ValidationError({"address": "Address not found via geocoding service."})
    except requests.RequestException:
        raise serializers.ValidationError({"address": "Could not validate address (geocoding service unavailable)."})


class MenuItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuItem
        fields = ["id", "name", "description", "price", "category", "image_url", "available"]
        read_only_fields = ["id"]


class MenuItemWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuItem
        fields = ["name", "description", "price", "category", "image_url", "available"]

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than 0.")
        return value


class MenuSerializer(serializers.ModelSerializer):
    class Meta:
        model = Menu
        fields = ["id", "name", "active", "created_at"]
        read_only_fields = ["id", "created_at"]


class MenuWithItemsSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()

    class Meta:
        model = Menu
        fields = ["id", "name", "active", "items"]

    def get_items(self, obj):
        available_items = obj.items.filter(available=True)
        return MenuItemSerializer(available_items, many=True).data


class RestaurantPublicSerializer(serializers.ModelSerializer):
    average_rating = serializers.SerializerMethodField()

    class Meta:
        model = Restaurant
        fields = ["id", "name", "address", "delivery_radius_km", "opening_hours", "average_rating"]

    def get_average_rating(self, obj):
        return 0.0


class RestaurantAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = Restaurant
        fields = [
            "id", "name", "owner_id", "address", "delivery_radius_km",
            "opening_hours", "status", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class RestaurantWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    address = serializers.JSONField()
    delivery_radius_km = serializers.FloatField(min_value=0.01)
    opening_hours = serializers.JSONField()
    lat = serializers.FloatField()
    lng = serializers.FloatField()

    def validate_address(self, value):
        _validate_address_format(value)
        return value

    def validate_opening_hours(self, value):
        _validate_opening_hours_format(value)
        return value

    def validate(self, attrs):
        _validate_address_nominatim(attrs["address"])
        return attrs

    def create(self, validated_data):
        return Restaurant.objects.create(**validated_data)

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class IncomingOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = IncomingOrder
        fields = [
            "id", "order_id", "items_snapshot", "total_price",
            "status", "received_at", "updated_at",
        ]
        read_only_fields = fields
