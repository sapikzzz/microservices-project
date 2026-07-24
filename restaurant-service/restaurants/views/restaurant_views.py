from django.db import transaction
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from restaurants.models import Restaurant
from restaurants.permissions import IsAuthenticated, IsRestaurantOwner
from restaurants.serializers import (
    MenuWithItemsSerializer,
    RestaurantAdminSerializer,
    RestaurantPublicSerializer,
    RestaurantWriteSerializer,
)
from restaurants.messaging.notifications import publish_notification_event

_RESTAURANT_WRITE_EXAMPLE = {
    "name": "Burger House",
    "address": {
        "street": "Nowy Świat 15",
        "city": "Warszawa",
        "postal_code": "00-029",
        "country": "Poland",
    },
    "lat": 52.2297,
    "lng": 21.0122,
    "delivery_radius_km": 5.0,
    "opening_hours": {
        "mon": ["10:00", "22:00"],
        "tue": ["10:00", "22:00"],
        "wed": ["10:00", "22:00"],
        "thu": ["10:00", "22:00"],
        "fri": ["10:00", "23:00"],
        "sat": ["11:00", "23:00"],
        "sun": None,
    },
}


class RestaurantListView(APIView):
    @extend_schema(
        summary="Lista aktywnych restauracji w pobliżu",
        parameters=[
            OpenApiParameter("lat", float, OpenApiParameter.QUERY, required=True, description="Szerokość geograficzna klienta, np. 52.2297"),
            OpenApiParameter("lng", float, OpenApiParameter.QUERY, required=True, description="Długość geograficzna klienta, np. 21.0122"),
        ],
        responses=RestaurantPublicSerializer(many=True),
    )
    def get(self, request):
        lat = request.query_params.get("lat")
        lng = request.query_params.get("lng")
        if lat is None or lng is None:
            return Response({"error": "Query params 'lat' and 'lng' are required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            lat = float(lat)
            lng = float(lng)
        except ValueError:
            return Response({"error": "'lat' and 'lng' must be numeric."}, status=status.HTTP_400_BAD_REQUEST)

        qs = Restaurant.objects.filter(status=Restaurant.STATUS_ACTIVE)
        result = [r for r in qs if r.covers_address(lat, lng) and r.is_open()]
        return Response(RestaurantPublicSerializer(result, many=True).data)


class RestaurantApplyView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema(
        summary="Złóż wniosek o dodanie restauracji",
        description="Tworzy restaurację ze statusem `pending`. Wymaga roli `restaurant`. Adres jest walidowany przez Nominatim (OSM).",
        request=RestaurantWriteSerializer,
        responses={201: RestaurantAdminSerializer},
        examples=[OpenApiExample("Przykład", value=_RESTAURANT_WRITE_EXAMPLE, request_only=True)],
    )
    def post(self, request):
        serializer = RestaurantWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            restaurant = serializer.save(owner_id=request.user.id)
        publish_notification_event(
            "notification.restaurant_application_submitted",
            {
                "event_type": "restaurant.application_submitted",
                "recipient_user_id": restaurant.owner_id,
                "subject": f"Wniosek restauracji {restaurant.name} został przyjęty",
                "message": (
                    f"Twój wniosek o dodanie restauracji {restaurant.name} został zapisany "
                    "i oczekuje na weryfikację administratora."
                ),
                "restaurant_id": restaurant.id,
                "restaurant_name": restaurant.name,
            },
        )
        return Response(RestaurantAdminSerializer(restaurant).data, status=status.HTTP_201_CREATED)


class RestaurantDetailView(APIView):
    def get_permissions(self):
        if self.request.method == "PUT":
            return [IsAuthenticated(), IsRestaurantOwner()]
        return []

    @extend_schema(
        summary="Szczegóły aktywnej restauracji",
        responses=RestaurantPublicSerializer,
    )
    def get(self, request, pk):
        try:
            restaurant = Restaurant.objects.get(pk=pk, status=Restaurant.STATUS_ACTIVE)
        except Restaurant.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(RestaurantPublicSerializer(restaurant).data)

    @extend_schema(
        summary="Edytuj dane restauracji",
        description="Wymaga roli `restaurant` i własności restauracji.",
        request=RestaurantWriteSerializer,
        responses=RestaurantAdminSerializer,
        examples=[OpenApiExample("Przykład", value=_RESTAURANT_WRITE_EXAMPLE, request_only=True)],
    )
    def put(self, request, pk):
        try:
            restaurant = Restaurant.objects.get(pk=pk)
        except Restaurant.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        self.check_object_permissions(request, restaurant)
        serializer = RestaurantWriteSerializer(restaurant, data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            serializer.save()
        restaurant.refresh_from_db()
        return Response(RestaurantAdminSerializer(restaurant).data)


class RestaurantMenuView(APIView):
    @extend_schema(
        summary="Menu aktywnej restauracji (tylko aktywne pozycje)",
        responses=MenuWithItemsSerializer(many=True),
    )
    def get(self, request, pk):
        try:
            restaurant = Restaurant.objects.get(pk=pk, status=Restaurant.STATUS_ACTIVE)
        except Restaurant.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        menus = restaurant.menus.filter(active=True)
        return Response(MenuWithItemsSerializer(list(menus), many=True).data)
