from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from restaurants.models import IncomingOrder, Restaurant
from restaurants.permissions import IsAuthenticated, IsRestaurantOwner
from restaurants.serializers import IncomingOrderSerializer


class OrderListView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurantOwner]

    @extend_schema(
        summary="Lista zamówień restauracji",
        description="Wymaga roli `restaurant` i własności restauracji.",
        parameters=[
            OpenApiParameter(
                "status", str, OpenApiParameter.QUERY, required=False,
                enum=["pending", "accepted", "preparing", "ready_for_pickup", "rejected"],
            ),
        ],
        responses=IncomingOrderSerializer(many=True),
    )
    def get(self, request, pk):
        restaurant = get_object_or_404(Restaurant, pk=pk)
        self.check_object_permissions(request, restaurant)
        orders = restaurant.orders.all()
        status_filter = request.query_params.get("status")
        if status_filter:
            orders = orders.filter(status=status_filter)
        paginator = PageNumberPagination()
        paginator.page_size = 20
        page = paginator.paginate_queryset(orders, request)
        serializer = IncomingOrderSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class _OrderStatusView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurantOwner]
    target_status = None
    event_routing_key = None
    # Stany terminalne — z nich nie wolno już zmieniać statusu zamówienia.
    TERMINAL_STATUSES = {IncomingOrder.STATUS_CANCELLED, IncomingOrder.STATUS_REJECTED}

    def patch(self, request, pk, order_id):
        restaurant = get_object_or_404(Restaurant, pk=pk)
        self.check_object_permissions(request, restaurant)
        order = get_object_or_404(IncomingOrder, order_id=order_id, restaurant=restaurant)
        if order.status in self.TERMINAL_STATUSES:
            return Response(
                {"detail": f"Zamówienie jest w stanie terminalnym ({order.status}) — nie można zmienić statusu."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        self._pre_check(order)
        with transaction.atomic():
            order.status = self.target_status
            order.save(update_fields=["status", "updated_at"])
        self._publish_event(order, restaurant)
        return Response(IncomingOrderSerializer(order).data)

    def _pre_check(self, order):
        pass

    def _publish_event(self, order, restaurant):
        if self.event_routing_key:
            from restaurants.messaging.publisher import publisher
            payload = {"order_id": order.order_id, "restaurant_id": restaurant.pk}
            publisher.publish("order.events", self.event_routing_key, payload)


class OrderAcceptView(_OrderStatusView):
    target_status = IncomingOrder.STATUS_ACCEPTED
    event_routing_key = "order.accepted_by_restaurant"

    @extend_schema(
        summary="Zaakceptuj zamówienie",
        description="Wymaga roli `restaurant` i własności restauracji. Zamówienia trafiające do Restaurant Service są już opłacone.",
        request=None,
        responses=IncomingOrderSerializer,
    )
    def patch(self, request, pk, order_id):
        return super().patch(request, pk, order_id)


class OrderRejectView(_OrderStatusView):
    target_status = IncomingOrder.STATUS_REJECTED
    event_routing_key = "order.rejected_by_restaurant"

    @extend_schema(
        summary="Odrzuć zamówienie",
        description="Wymaga roli `restaurant` i własności restauracji.",
        request=None,
        responses=IncomingOrderSerializer,
    )
    def patch(self, request, pk, order_id):
        return super().patch(request, pk, order_id)


class OrderPreparingView(_OrderStatusView):
    target_status = IncomingOrder.STATUS_PREPARING
    event_routing_key = "order.preparing"

    @extend_schema(
        summary="Ustaw zamówienie jako 'w przygotowaniu'",
        description="Wymaga roli `restaurant` i własności restauracji.",
        request=None,
        responses=IncomingOrderSerializer,
    )
    def patch(self, request, pk, order_id):
        return super().patch(request, pk, order_id)


class OrderReadyView(_OrderStatusView):
    target_status = IncomingOrder.STATUS_READY
    event_routing_key = "order.ready_for_pickup"

    @extend_schema(
        summary="Ustaw zamówienie jako gotowe do odbioru",
        description="Wymaga roli `restaurant` i własności restauracji.",
        request=None,
        responses=IncomingOrderSerializer,
    )
    def patch(self, request, pk, order_id):
        return super().patch(request, pk, order_id)

    def _publish_event(self, order, restaurant):
        from restaurants.messaging.publisher import publisher
        payload = {
            "order_id": order.order_id,
            "restaurant_id": restaurant.pk,
            "lat": restaurant.lat,
            "lng": restaurant.lng,
        }
        publisher.publish("order.events", self.event_routing_key, payload)
