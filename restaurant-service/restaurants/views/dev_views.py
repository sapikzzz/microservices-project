from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from restaurants.models import IncomingOrder, Restaurant


class SimulateOrderReceivedView(APIView):
    @extend_schema(
        summary="[DEV] Symuluj zdarzenie order.created z Order Service",
        request=inline_serializer(
            "SimulateOrderReceived",
            fields={
                "order_id": serializers.IntegerField(),
                "restaurant_id": serializers.IntegerField(),
                "total_price": serializers.DecimalField(max_digits=10, decimal_places=2),
                "items": serializers.ListField(
                    child=serializers.DictField(),
                    help_text='Lista pozycji, np. [{"menu_item_id": 1, "name": "Burger", "quantity": 2, "unit_price": "19.99", "notes": ""}]',
                ),
            },
        ),
        responses=inline_serializer(
            "SimulateOrderReceivedResponse",
            fields={
                "incoming_order_id": serializers.IntegerField(),
                "order_id": serializers.IntegerField(),
            },
        ),
        examples=[
            OpenApiExample(
                "Przykład",
                value={
                    "order_id": 123,
                    "restaurant_id": 1,
                    "total_price": "48.97",
                    "items": [
                        {"menu_item_id": 1, "name": "Burger klasyczny", "quantity": 2, "unit_price": "19.99", "notes": "bez cebuli"},
                    ],
                },
                request_only=True,
            )
        ],
    )
    def post(self, request):
        data = request.data
        required = ("order_id", "restaurant_id", "items", "total_price")
        missing = [f for f in required if f not in data]
        if missing:
            return Response({"error": f"Missing fields: {missing}"}, status=status.HTTP_400_BAD_REQUEST)

        restaurant = get_object_or_404(Restaurant, pk=data["restaurant_id"])
        with transaction.atomic():
            order = IncomingOrder.objects.create(
                order_id=data["order_id"],
                restaurant=restaurant,
                items_snapshot=data["items"],
                total_price=data["total_price"],
            )
        return Response({"incoming_order_id": order.pk, "order_id": order.order_id}, status=status.HTTP_201_CREATED)
