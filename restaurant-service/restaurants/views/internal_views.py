from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from restaurants.models import MenuItem, Restaurant
from restaurants.permissions import IsInternal
from restaurants.serializers import MenuItemSerializer

_INTERNAL_HEADERS = [
    OpenApiParameter("X-Internal-Secret", str, OpenApiParameter.HEADER, required=True, description="Shared secret między serwisami"),
]


class IsOpenView(APIView):
    permission_classes = [IsInternal]

    @extend_schema(
        summary="Czy restauracja jest teraz otwarta?",
        parameters=_INTERNAL_HEADERS,
        responses=inline_serializer(
            "IsOpenResponse",
            fields={
                "is_open": serializers.BooleanField(),
                "restaurant_id": serializers.IntegerField(),
            },
        ),
    )
    def get(self, request, pk):
        restaurant = get_object_or_404(Restaurant, pk=pk)
        return Response({"is_open": restaurant.is_open(), "restaurant_id": pk})


class CoversAddressView(APIView):
    permission_classes = [IsInternal]

    @extend_schema(
        summary="Czy restauracja obsługuje podany adres?",
        parameters=_INTERNAL_HEADERS + [
            OpenApiParameter("lat", float, OpenApiParameter.QUERY, required=True),
            OpenApiParameter("lng", float, OpenApiParameter.QUERY, required=True),
        ],
        responses=inline_serializer(
            "CoversAddressResponse",
            fields={
                "covers": serializers.BooleanField(),
                "restaurant_id": serializers.IntegerField(),
            },
        ),
    )
    def get(self, request, pk):
        restaurant = get_object_or_404(Restaurant, pk=pk)
        lat = request.query_params.get("lat")
        lng = request.query_params.get("lng")
        if lat is None or lng is None:
            return Response({"error": "'lat' and 'lng' are required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            lat = float(lat)
            lng = float(lng)
        except ValueError:
            return Response({"error": "'lat' and 'lng' must be numeric."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"covers": restaurant.covers_address(lat, lng), "restaurant_id": pk})


class MenuItemsView(APIView):
    permission_classes = [IsInternal]

    @extend_schema(
        summary="Pobierz pozycje menu po ID (walidacja dla Order Service)",
        parameters=_INTERNAL_HEADERS + [
            OpenApiParameter("ids", str, OpenApiParameter.QUERY, required=True, description="ID pozycji menu po przecinku, np. 1,2,3"),
        ],
        responses=MenuItemSerializer(many=True),
    )
    def get(self, request, pk):
        restaurant = get_object_or_404(Restaurant, pk=pk)
        ids_param = request.query_params.get("ids")
        if not ids_param:
            return Response({"error": "'ids' parameter is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            ids = [int(i) for i in ids_param.split(",") if i.strip()]
        except ValueError:
            return Response({"error": "'ids' must be comma-separated integers."}, status=status.HTTP_400_BAD_REQUEST)
        items = MenuItem.objects.filter(
            pk__in=ids,
            menu__restaurant=restaurant,
            available=True,
        )
        return Response(MenuItemSerializer(items, many=True).data)
