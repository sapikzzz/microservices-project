import logging

from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Delivery, DeliveryEvent, DeliveryStatus
from .ors_client import calculate_route, geocode_address, ORSError
from .rabbitmq import publish_delivery_event, publish_delivery_notification
from .serializers import (
    DeliverySerializer,
    StartDeliverySerializer,
    PickupSerializer,
    UpdateClientLocationSerializer,
    RouteSerializer,
    MessageSerializer,
)

logger = logging.getLogger(__name__)

ORDER_ID_PARAM = OpenApiParameter(
    name='order_id',
    location=OpenApiParameter.PATH,
    description='Order ID supplied by the Order Service.',
    type=OpenApiTypes.STR,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log_event(delivery: Delivery, note: str = '') -> None:
    DeliveryEvent.objects.create(
        delivery=delivery,
        status=delivery.status,
        note=note,
    )


def _geocode(address: str, field_name: str):
    try:
        return geocode_address(address)
    except ORSError as exc:
        raise _GeocodingError(field_name, address, exc)


class _GeocodingError(Exception):
    def __init__(self, field: str, address: str, cause: Exception):
        self.response_data = {field: [f'Could not geocode "{address}": {cause}']}


def _safe_route(from_lat, from_lon, to_lat, to_lon, label: str) -> dict:
    try:
        return calculate_route(from_lat, from_lon, to_lat, to_lon)
    except ORSError as exc:
        logger.error('ORS route calculation failed (%s): %s', label, exc)
        return {'geojson': None, 'distance_m': None, 'duration_s': None}


# ---------------------------------------------------------------------------
# List + Create
# ---------------------------------------------------------------------------

class DeliveryListCreateView(APIView):

    @extend_schema(
        tags=['Deliveries'],
        summary='List all deliveries',
        responses={200: DeliverySerializer(many=True)},
    )
    def get(self, request):
        qs = Delivery.objects.prefetch_related('events').all()
        order_id      = request.query_params.get('order_id')
        status_filter = request.query_params.get('status')
        if order_id:
            qs = qs.filter(order_id__icontains=order_id)
        if status_filter:
            qs = qs.filter(status=status_filter.upper())
        return Response(DeliverySerializer(qs, many=True).data)

    @extend_schema(
        tags=['Deliveries'],
        summary='Start a new delivery',
        description=(
            'Creates a delivery record. `driver_location` and `restaurant_location` are '
            'geocoded via OpenRouteService and the driver → restaurant route is calculated '
            'immediately. `client_location` is optional here — provide it at /pickup/ if unknown. '
            '`customer_id` (User Service ID) enables automatic delivery notifications to the customer.'
        ),
        request=StartDeliverySerializer,
        responses={
            201: DeliverySerializer,
            400: OpenApiResponse(description='Validation error or address cannot be geocoded'),
        },
    )
    def post(self, request):
        serializer = StartDeliverySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            driver_lat, driver_lon         = _geocode(data['driver_location'],     'driver_location')
            restaurant_lat, restaurant_lon = _geocode(data['restaurant_location'], 'restaurant_location')
        except _GeocodingError as exc:
            return Response(exc.response_data, status=status.HTTP_400_BAD_REQUEST)

        client_location = data.get('client_location', '')
        if client_location:
            try:
                _geocode(client_location, 'client_location')
            except _GeocodingError:
                logger.warning(
                    'Could not geocode client_location "%s" — stored as empty, '
                    'provide it again at /pickup/', client_location,
                )
                client_location = ''

        route = _safe_route(
            driver_lat, driver_lon,
            restaurant_lat, restaurant_lon,
            label='driver→restaurant',
        )

        delivery = Delivery.objects.create(
            order_id=data['order_id'],
            customer_id=data.get('customer_id'),
            status=DeliveryStatus.PENDING,
            driver_location=data['driver_location'],
            restaurant_location=data['restaurant_location'],
            client_location=client_location,
            route_to_restaurant=route['geojson'],
            distance_to_restaurant_m=route['distance_m'],
            duration_to_restaurant_s=route['duration_s'],
        )
        _log_event(delivery, note=(
            f'Delivery started. '
            f'Driver: "{data["driver_location"]}" → Restaurant: "{data["restaurant_location"]}".'
        ))
        publish_delivery_event(delivery.order_id, delivery.status)

        return Response(DeliverySerializer(delivery).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

class DeliveryDetailView(APIView):

    @extend_schema(
        tags=['Deliveries'],
        summary='Get delivery details',
        parameters=[ORDER_ID_PARAM],
        responses={
            200: DeliverySerializer,
            404: OpenApiResponse(description='Not found'),
        },
    )
    def get(self, request, order_id):
        try:
            delivery = Delivery.objects.prefetch_related('events').get(order_id=order_id)
        except Delivery.DoesNotExist:
            return Response({'detail': 'Delivery not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(DeliverySerializer(delivery).data)


# ---------------------------------------------------------------------------
# Update client location
# ---------------------------------------------------------------------------

class UpdateClientLocationView(APIView):

    @extend_schema(
        tags=['Deliveries'],
        summary='Update customer delivery address',
        description=(
            'Updates the client (delivery) location mid-delivery. '
            'Allowed at any active status (PENDING, PICKED_UP, READY_FOR_DROPOFF). '
            'If the delivery is already PICKED_UP or READY_FOR_DROPOFF, the '
            'restaurant → client route is automatically recalculated.'
        ),
        parameters=[ORDER_ID_PARAM],
        request=UpdateClientLocationSerializer,
        responses={
            200: DeliverySerializer,
            400: OpenApiResponse(description='Validation / state error or address cannot be geocoded'),
            404: OpenApiResponse(description='Not found'),
        },
    )
    def patch(self, request, order_id):
        try:
            delivery = Delivery.objects.prefetch_related('events').get(order_id=order_id)
        except Delivery.DoesNotExist:
            return Response({'detail': 'Delivery not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not delivery.is_active:
            return Response(
                {'detail': f'Cannot update location — delivery is already {delivery.status}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = UpdateClientLocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_location = serializer.validated_data['client_location'].strip()

        try:
            client_lat, client_lon = _geocode(new_location, 'client_location')
        except _GeocodingError as exc:
            return Response(exc.response_data, status=status.HTTP_400_BAD_REQUEST)

        delivery.client_location = new_location
        update_fields = ['client_location', 'updated_at']

        # Recalculate route to client if the driver is already on their way
        if delivery.status in (DeliveryStatus.PICKED_UP, DeliveryStatus.READY_FOR_DROPOFF):
            try:
                restaurant_lat, restaurant_lon = _geocode(
                    delivery.restaurant_location, 'restaurant_location'
                )
            except _GeocodingError as exc:
                return Response(exc.response_data, status=status.HTTP_400_BAD_REQUEST)

            route = _safe_route(
                restaurant_lat, restaurant_lon,
                client_lat, client_lon,
                label='restaurant→client (location update)',
            )
            delivery.route_to_client      = route['geojson']
            delivery.distance_to_client_m = route['distance_m']
            delivery.duration_to_client_s = route['duration_s']
            update_fields += [
                'route_to_client', 'distance_to_client_m', 'duration_to_client_s',
            ]
            _log_event(delivery, note=f'Client location updated to "{new_location}" — route recalculated.')
        else:
            _log_event(delivery, note=f'Client location updated to "{new_location}".')

        delivery.save(update_fields=update_fields)
        return Response(DeliverySerializer(delivery).data)


# ---------------------------------------------------------------------------
# Pickup
# ---------------------------------------------------------------------------

class DeliveryPickupView(APIView):

    @extend_schema(
        tags=['Deliveries'],
        summary='Mark order as picked up',
        description=(
            'Transitions status to PICKED_UP and calculates the restaurant → client route. '
            'Supply `client_location` here if it was not provided at delivery creation. '
            'Sends a push notification to the customer if `customer_id` is set on the delivery.'
        ),
        parameters=[ORDER_ID_PARAM],
        request=PickupSerializer,
        responses={
            200: DeliverySerializer,
            400: OpenApiResponse(description='Validation / state error or address cannot be geocoded'),
            404: OpenApiResponse(description='Not found'),
        },
    )
    def post(self, request, order_id):
        try:
            delivery = Delivery.objects.prefetch_related('events').get(order_id=order_id)
        except Delivery.DoesNotExist:
            return Response({'detail': 'Delivery not found.'}, status=status.HTTP_404_NOT_FOUND)

        if delivery.status != DeliveryStatus.PENDING:
            return Response(
                {'detail': f'Cannot pick up — current status is {delivery.status}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = PickupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        client_location = serializer.validated_data.get('client_location', '').strip() \
                          or delivery.client_location

        if not client_location:
            return Response(
                {'client_location': [
                    'client_location is required at pickup because it was not set at delivery start.'
                ]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            restaurant_lat, restaurant_lon = _geocode(delivery.restaurant_location, 'restaurant_location')
            client_lat, client_lon         = _geocode(client_location, 'client_location')
        except _GeocodingError as exc:
            return Response(exc.response_data, status=status.HTTP_400_BAD_REQUEST)

        route = _safe_route(
            restaurant_lat, restaurant_lon,
            client_lat, client_lon,
            label='restaurant→client',
        )

        delivery.client_location      = client_location
        delivery.route_to_client      = route['geojson']
        delivery.distance_to_client_m = route['distance_m']
        delivery.duration_to_client_s = route['duration_s']
        delivery.status               = DeliveryStatus.PICKED_UP
        delivery.picked_up_at         = timezone.now()
        delivery.save()

        _log_event(delivery, note=(
            f'Order picked up. '
            f'Restaurant: "{delivery.restaurant_location}" → Client: "{client_location}".'
        ))
        publish_delivery_event(delivery.order_id, delivery.status)
        if delivery.customer_id:
            publish_delivery_notification(delivery.order_id, delivery.status, delivery.customer_id)

        return Response(DeliverySerializer(delivery).data)


# ---------------------------------------------------------------------------
# Dropoff
# ---------------------------------------------------------------------------

class DeliveryDropoffView(APIView):

    @extend_schema(
        tags=['Deliveries'],
        summary='Mark order as ready for drop-off',
        description=(
            'Transitions status from PICKED_UP to READY_FOR_DROPOFF. '
            'Sends a notification to the customer if `customer_id` is set. '
            'The delivery will be automatically cancelled after 10 minutes '
            'if not completed (handled by the consumer watchdog process).'
        ),
        parameters=[ORDER_ID_PARAM],
        responses={
            200: DeliverySerializer,
            400: OpenApiResponse(description='State error'),
            404: OpenApiResponse(description='Not found'),
        },
    )
    def post(self, request, order_id):
        try:
            delivery = Delivery.objects.prefetch_related('events').get(order_id=order_id)
        except Delivery.DoesNotExist:
            return Response({'detail': 'Delivery not found.'}, status=status.HTTP_404_NOT_FOUND)

        if delivery.status != DeliveryStatus.PICKED_UP:
            return Response(
                {'detail': f'Cannot mark as ready for drop-off — current status is {delivery.status}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        delivery.status               = DeliveryStatus.READY_FOR_DROPOFF
        delivery.ready_for_dropoff_at = timezone.now()
        delivery.save()

        _log_event(delivery, note='Order ready for drop-off. Auto-cancel scheduled in 10 minutes.')
        publish_delivery_event(delivery.order_id, delivery.status)
        if delivery.customer_id:
            publish_delivery_notification(delivery.order_id, delivery.status, delivery.customer_id)

        return Response(DeliverySerializer(delivery).data)


# ---------------------------------------------------------------------------
# Complete
# ---------------------------------------------------------------------------

class DeliveryCompleteView(APIView):

    @extend_schema(
        tags=['Deliveries'],
        summary='Complete the delivery',
        description='Transitions status to DELIVERED. Final step in the lifecycle.',
        parameters=[ORDER_ID_PARAM],
        responses={
            200: DeliverySerializer,
            400: OpenApiResponse(description='State error'),
            404: OpenApiResponse(description='Not found'),
        },
    )
    def post(self, request, order_id):
        try:
            delivery = Delivery.objects.prefetch_related('events').get(order_id=order_id)
        except Delivery.DoesNotExist:
            return Response({'detail': 'Delivery not found.'}, status=status.HTTP_404_NOT_FOUND)

        if delivery.status not in (DeliveryStatus.PICKED_UP, DeliveryStatus.READY_FOR_DROPOFF):
            return Response(
                {'detail': f'Cannot complete — current status is {delivery.status}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        delivery.status       = DeliveryStatus.DELIVERED
        delivery.delivered_at = timezone.now()
        delivery.save()

        _log_event(delivery, note='Order delivered successfully.')
        publish_delivery_event(delivery.order_id, delivery.status)
        if delivery.customer_id:
            publish_delivery_notification(delivery.order_id, delivery.status, delivery.customer_id)

        return Response(DeliverySerializer(delivery).data)


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

class DeliveryCancelView(APIView):

    @extend_schema(
        tags=['Deliveries'],
        summary='Cancel an active delivery',
        parameters=[ORDER_ID_PARAM],
        responses={
            200: DeliverySerializer,
            400: OpenApiResponse(description='State error'),
            404: OpenApiResponse(description='Not found'),
        },
    )
    def post(self, request, order_id):
        try:
            delivery = Delivery.objects.prefetch_related('events').get(order_id=order_id)
        except Delivery.DoesNotExist:
            return Response({'detail': 'Delivery not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not delivery.is_active:
            return Response(
                {'detail': f'Cannot cancel — current status is {delivery.status}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        delivery.status      = DeliveryStatus.CANCELLED
        delivery.cancelled_at = timezone.now()
        delivery.save()

        _log_event(delivery, note='Delivery cancelled.')
        publish_delivery_event(delivery.order_id, delivery.status)
        if delivery.customer_id:
            publish_delivery_notification(delivery.order_id, delivery.status, delivery.customer_id)

        return Response(DeliverySerializer(delivery).data)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

class DeliveryRouteView(APIView):

    @extend_schema(
        tags=['Routes'],
        summary='Get route GeoJSON for a delivery leg',
        description=(
            'Returns the stored ORS GeoJSON for the requested leg:\n'
            '- `to_restaurant` — driver → restaurant (available immediately after creation)\n'
            '- `to_client` — restaurant → client (available after /pickup/)\n'
        ),
        parameters=[
            ORDER_ID_PARAM,
            OpenApiParameter(
                name='leg',
                location=OpenApiParameter.QUERY,
                description='Which route leg to return.',
                enum=['to_restaurant', 'to_client'],
                default='to_restaurant',
            ),
        ],
        responses={
            200: RouteSerializer,
            404: OpenApiResponse(description='Not found or route not yet calculated'),
            400: OpenApiResponse(description='Invalid leg parameter'),
        },
    )
    def get(self, request, order_id):
        try:
            delivery = Delivery.objects.get(order_id=order_id)
        except Delivery.DoesNotExist:
            return Response({'detail': 'Delivery not found.'}, status=status.HTTP_404_NOT_FOUND)

        leg = request.query_params.get('leg', 'to_restaurant')

        if leg == 'to_restaurant':
            return Response({
                'leg':        leg,
                'distance_m': delivery.distance_to_restaurant_m,
                'duration_s': delivery.duration_to_restaurant_s,
                'geojson':    delivery.route_to_restaurant,
            })

        elif leg == 'to_client':
            if delivery.route_to_client is None:
                required_status = (
                    DeliveryStatus.PICKED_UP,
                    DeliveryStatus.READY_FOR_DROPOFF,
                    DeliveryStatus.DELIVERED,
                )
                if delivery.status not in required_status:
                    return Response(
                        {
                            'detail': (
                                'Route to client is not available yet. '
                                f'Current status: {delivery.status}. '
                                'Call POST /pickup/ first to calculate this route.'
                            )
                        },
                        status=status.HTTP_404_NOT_FOUND,
                    )
            return Response({
                'leg':        leg,
                'distance_m': delivery.distance_to_client_m,
                'duration_s': delivery.duration_to_client_s,
                'geojson':    delivery.route_to_client,
            })

        else:
            return Response(
                {'detail': 'leg must be "to_restaurant" or "to_client".'},
                status=status.HTTP_400_BAD_REQUEST,
            )
