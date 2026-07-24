from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from restaurants.models import Menu, MenuItem, Restaurant
from restaurants.permissions import IsAuthenticated, IsRestaurantOwner
from restaurants.serializers import MenuItemSerializer, MenuItemWriteSerializer, MenuSerializer


def _get_restaurant_or_404(pk):
    return get_object_or_404(Restaurant, pk=pk)


class MenuListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema(
        summary="Utwórz nowe menu restauracji",
        description="Wymaga roli `restaurant` i własności restauracji.",
        request=MenuSerializer,
        responses={201: MenuSerializer},
    )
    def post(self, request, pk):
        restaurant = _get_restaurant_or_404(pk)
        self.check_object_permissions(request, restaurant)
        serializer = MenuSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            menu = Menu.objects.create(restaurant=restaurant, **serializer.validated_data)
        return Response(MenuSerializer(menu).data, status=status.HTTP_201_CREATED)


class MenuDetailView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    def _get_menu(self, pk, menu_id):
        restaurant = _get_restaurant_or_404(pk)
        menu = get_object_or_404(Menu, pk=menu_id, restaurant=restaurant)
        return restaurant, menu

    @extend_schema(
        summary="Edytuj menu",
        description="Wymaga roli `restaurant` i własności restauracji.",
        request=MenuSerializer,
        responses=MenuSerializer,
    )
    def put(self, request, pk, menu_id):
        restaurant, menu = self._get_menu(pk, menu_id)
        self.check_object_permissions(request, restaurant)
        serializer = MenuSerializer(menu, data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            serializer.save()
        return Response(MenuSerializer(menu).data)

    @extend_schema(
        summary="Usuń menu (kaskadowo usuwa pozycje)",
        description="Wymaga roli `restaurant` i własności restauracji.",
        responses={204: None},
    )
    def delete(self, request, pk, menu_id):
        restaurant, menu = self._get_menu(pk, menu_id)
        self.check_object_permissions(request, restaurant)
        with transaction.atomic():
            menu.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MenuItemCreateView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema(
        summary="Dodaj pozycję do menu",
        description="Wymaga roli `restaurant` i własności restauracji.",
        request=MenuItemWriteSerializer,
        responses={201: MenuItemSerializer},
    )
    def post(self, request, pk, menu_id):
        restaurant = _get_restaurant_or_404(pk)
        self.check_object_permissions(request, restaurant)
        menu = get_object_or_404(Menu, pk=menu_id, restaurant=restaurant)
        serializer = MenuItemWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            item = MenuItem.objects.create(menu=menu, **serializer.validated_data)
        return Response(MenuItemSerializer(item).data, status=status.HTTP_201_CREATED)


class MenuItemDetailView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    def _get_item(self, pk, menu_id, item_id):
        restaurant = _get_restaurant_or_404(pk)
        menu = get_object_or_404(Menu, pk=menu_id, restaurant=restaurant)
        item = get_object_or_404(MenuItem, pk=item_id, menu=menu)
        return restaurant, menu, item

    @extend_schema(
        summary="Edytuj pozycję menu",
        description="Wymaga roli `restaurant` i własności restauracji.",
        request=MenuItemWriteSerializer,
        responses=MenuItemSerializer,
    )
    def put(self, request, pk, menu_id, item_id):
        restaurant, menu, item = self._get_item(pk, menu_id, item_id)
        self.check_object_permissions(request, restaurant)
        serializer = MenuItemWriteSerializer(item, data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            serializer.save()
        return Response(MenuItemSerializer(item).data)

    @extend_schema(
        summary="Usuń pozycję menu",
        description="Wymaga roli `restaurant` i własności restauracji.",
        responses={204: None},
    )
    def delete(self, request, pk, menu_id, item_id):
        restaurant, menu, item = self._get_item(pk, menu_id, item_id)
        self.check_object_permissions(request, restaurant)
        with transaction.atomic():
            item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
