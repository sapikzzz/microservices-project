from rest_framework import serializers

from .models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.ReadOnlyField()

    class Meta:
        model = OrderItem
        fields = ['id', 'menu_item_id', 'name', 'unit_price', 'quantity', 'subtotal']


class OrderItemCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['menu_item_id', 'name', 'unit_price', 'quantity']

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError('Ilość musi być większa od zera.')
        return value

    def validate_unit_price(self, value):
        if value <= 0:
            raise serializers.ValidationError('Cena musi być większa od zera.')
        return value


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'customer_id',
            'restaurant_id', 'restaurant_name',
            'delivery_address', 'notes',
            'status', 'status_display', 'total_price',
            'payment_id',
            'created_at', 'updated_at', 'delivered_at', 'cancelled_at',
            'items',
        ]
        read_only_fields = [
            'id', 'customer_id', 'status', 'total_price',
            'payment_id', 'created_at', 'updated_at', 'delivered_at', 'cancelled_at',
        ]


class OrderCreateSerializer(serializers.ModelSerializer):
    items = OrderItemCreateSerializer(many=True)

    class Meta:
        model = Order
        fields = ['restaurant_id', 'restaurant_name', 'delivery_address', 'notes', 'items']

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError('Zamówienie musi zawierać co najmniej jeden produkt.')
        return items

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        total = sum(item['unit_price'] * item['quantity'] for item in items_data)
        order = Order.objects.create(total_price=total, **validated_data)
        OrderItem.objects.bulk_create([
            OrderItem(order=order, **item) for item in items_data
        ])
        return order
