from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from restaurants.models import Restaurant
from restaurants.permissions import IsAdmin
from restaurants.serializers import RestaurantAdminSerializer
from restaurants.messaging.notifications import publish_notification_event


class PendingRestaurantsView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(
        summary="Lista restauracji oczekujących na weryfikację",
        description="Wymaga roli `admin`.",
        responses=RestaurantAdminSerializer(many=True),
    )
    def get(self, request):
        restaurants = Restaurant.objects.filter(status=Restaurant.STATUS_PENDING)
        return Response(RestaurantAdminSerializer(restaurants, many=True).data)


class AdminRestaurantDetailView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(
        summary="Szczegóły restauracji (niezależnie od statusu)",
        description="Wymaga roli `admin`.",
        responses=RestaurantAdminSerializer,
    )
    def get(self, request, pk):
        restaurant = get_object_or_404(Restaurant, pk=pk)
        return Response(RestaurantAdminSerializer(restaurant).data)


class AdminRestaurantVerifyView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(
        summary="Zweryfikuj restaurację (zatwierdź lub odrzuć)",
        description="Wymaga roli `admin`.",
        request=inline_serializer(
            "VerifyAction",
            fields={"action": serializers.ChoiceField(choices=["accept", "reject"])},
        ),
        responses=RestaurantAdminSerializer,
        examples=[
            OpenApiExample("Zatwierdź", value={"action": "accept"}, request_only=True),
            OpenApiExample("Odrzuć", value={"action": "reject"}, request_only=True),
        ],
    )
    def patch(self, request, pk):
        restaurant = get_object_or_404(Restaurant, pk=pk)
        action = request.data.get("action")
        if action not in ("accept", "reject"):
            return Response(
                {"error": "action must be 'accept' or 'reject'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if action == "accept":
            new_status = Restaurant.STATUS_ACTIVE
            event_type = "restaurant.verified"
        else:
            new_status = Restaurant.STATUS_REJECTED
            event_type = "restaurant.rejected"

        with transaction.atomic():
            restaurant.status = new_status
            restaurant.save(update_fields=["status", "updated_at"])

        from restaurants.messaging.publisher import publish_kafka_event
        publish_kafka_event(
            restaurant_id=restaurant.pk,
            status=new_status,
            name=restaurant.name,
            event_type=event_type,
        )
        if action == "accept":
            publish_notification_event(
                "notification.restaurant_verified",
                {
                    "event_type": "restaurant.verified",
                    "recipient_user_id": restaurant.owner_id,
                    "subject": f"Restauracja {restaurant.name} została zaakceptowana",
                    "message": f"Twoja restauracja {restaurant.name} została zaakceptowana i jest aktywna.",
                    "restaurant_id": restaurant.id,
                    "restaurant_name": restaurant.name,
                },
            )
        else:
            publish_notification_event(
                "notification.restaurant_rejected",
                {
                    "event_type": "restaurant.rejected",
                    "recipient_user_id": restaurant.owner_id,
                    "subject": f"Restauracja {restaurant.name} została odrzucona",
                    "message": f"Twój wniosek dla restauracji {restaurant.name} został odrzucony.",
                    "restaurant_id": restaurant.id,
                    "restaurant_name": restaurant.name,
                },
            )

        return Response(RestaurantAdminSerializer(restaurant).data)
