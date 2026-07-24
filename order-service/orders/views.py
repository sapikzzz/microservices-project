import logging

from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .messaging.publisher import publish_order_cancelled, publish_order_created
from .messaging.notifications import publish_order_status_notification
from .models import Order
from .payments import payu
from .serializers import OrderCreateSerializer, OrderSerializer
from .validation import validate_or_raise

logger = logging.getLogger(__name__)

_ORDER_EXAMPLE = {
    "restaurant_id": 1,
    "restaurant_name": "Pizza Roma",
    "delivery_address": "ul. Marszałkowska 1, Warszawa",
    "notes": "Bez cebuli",
    "items": [
        {
            "menu_item_id": 1,
            "name": "Pizza Margherita",
            "unit_price": "25.00",
            "quantity": 2,
        }
    ],
}

_ORDER_RESPONSE_EXAMPLE = {
    "id": 1,
    "customer_id": 3,
    "restaurant_id": 1,
    "restaurant_name": "Pizza Roma",
    "delivery_address": "ul. Marszałkowska 1, Warszawa",
    "notes": "Bez cebuli",
    "status": "pending_payment",
    "status_display": "Oczekuje na płatność",
    "total_price": "50.00",
    "payment_id": "",
    "created_at": "2026-01-15T12:00:00Z",
    "updated_at": "2026-01-15T12:00:00Z",
    "delivered_at": None,
    "cancelled_at": None,
    "items": [
        {
            "id": 1,
            "menu_item_id": 1,
            "name": "Pizza Margherita",
            "unit_price": "25.00",
            "quantity": 2,
            "subtotal": "50.00",
        }
    ],
}


class OrderViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Order.objects.prefetch_related('items').filter(customer_id=self.request.user.id)

    def get_serializer_class(self):
        if self.action == 'create':
            return OrderCreateSerializer
        return OrderSerializer

    def perform_create(self, serializer):
        serializer.save(customer_id=self.request.user.id)

    @extend_schema(
        summary="Lista zamówień zalogowanego użytkownika",
        responses={200: OrderSerializer(many=True)},
        examples=[
            OpenApiExample("Przykład odpowiedzi", value=[_ORDER_RESPONSE_EXAMPLE], response_only=True),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Szczegóły zamówienia",
        responses={200: OrderSerializer},
        examples=[
            OpenApiExample("Przykład odpowiedzi", value=_ORDER_RESPONSE_EXAMPLE, response_only=True),
        ],
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        summary="Złóż nowe zamówienie",
        description=(
            "Tworzy zamówienie ze statusem `pending_payment`. Dane wejściowe są "
            "walidowane względem JSON Schema (`schemas/order_create.json`) przed "
            "zapisem. Aby opłacić, użyj `pay/` (PayU) lub `simulate-payment/` (dev)."
        ),
        request=OrderCreateSerializer,
        responses={201: OrderSerializer},
        examples=[
            OpenApiExample("Przykład zapytania", value=_ORDER_EXAMPLE, request_only=True),
            OpenApiExample("Przykład odpowiedzi", value=_ORDER_RESPONSE_EXAMPLE, response_only=True),
        ],
    )
    def create(self, request, *args, **kwargs):
        validate_or_raise(request.data, 'order_create.json')
        return super().create(request, *args, **kwargs)

    @extend_schema(
        summary="[DEV] Symuluj płatność",
        description="Ustawia status zamówienia na `paid` i wysyła zdarzenie `order.created` do RabbitMQ, co powiadamia restaurację. Zastępuje integrację z PayU podczas developmentu.",
        request=None,
        responses={200: OrderSerializer},
        examples=[
            OpenApiExample(
                "Przykład odpowiedzi",
                value={**_ORDER_RESPONSE_EXAMPLE, "status": "paid", "status_display": "Opłacone"},
                response_only=True,
            ),
        ],
    )
    @action(detail=True, methods=['post'], url_path='simulate-payment')
    def simulate_payment(self, request, pk=None):
        order = self.get_object()
        if order.status != Order.Status.PENDING_PAYMENT:
            return Response(
                {'detail': 'Zamówienie nie oczekuje na płatność.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.status = Order.Status.PAID
        order.save()
        publish_order_status_notification(order)
        publish_order_created(order)
        return Response(OrderSerializer(order).data)

    @extend_schema(
        summary="Rozpocznij płatność PayU",
        description=(
            "Tworzy płatność w PayU dla zamówienia i zwraca `redirectUri` — link do "
            "strony płatności PayU. Po opłaceniu PayU wysyła powiadomienie na webhook "
            "(`payu-webhook/`), który zmienia status na `paid` i powiadamia restaurację."
        ),
        request=None,
        responses={
            200: inline_serializer(
                'PayUInitResponse',
                fields={
                    'redirectUri': serializers.URLField(),
                    'payu_order_id': serializers.CharField(),
                },
            )
        },
        examples=[
            OpenApiExample(
                "Przykład odpowiedzi",
                value={
                    'redirectUri': 'https://secure.snd.payu.com/pay/?orderId=ABC123',
                    'payu_order_id': 'ABC123',
                },
                response_only=True,
            ),
        ],
    )
    @action(detail=True, methods=['post'])
    def pay(self, request, pk=None):
        order = self.get_object()
        if order.status != Order.Status.PENDING_PAYMENT:
            return Response(
                {'detail': 'Zamówienie nie oczekuje na płatność.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        customer_ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
        try:
            result = payu.create_order(order, customer_ip=customer_ip)
        except payu.PayUError as e:
            logger.error(f'PayU init failed for order {order.id}: {e}')
            return Response(
                {'detail': 'Nie udało się rozpocząć płatności PayU.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        order.payment_id = result.get('orderId', '')
        order.save(update_fields=['payment_id'])
        return Response({
            'redirectUri': result.get('redirectUri'),
            'payu_order_id': result.get('orderId'),
        })

    # Statusy, z których klient może jeszcze anulować zamówienie.
    # delivered/cancelled — już za późno; pending_payment — anulowane bez zwrotu.
    CANCELLABLE_STATUSES = {
        Order.Status.PENDING_PAYMENT,
        Order.Status.PAID,
        Order.Status.ACCEPTED,
        Order.Status.IN_PREPARATION,
        Order.Status.READY_FOR_PICKUP,
        Order.Status.PICKED_UP,
        Order.Status.IN_DELIVERY,
    }

    @extend_schema(
        summary="Anuluj zamówienie (proces orkiestracji)",
        description=(
            "Anuluje zamówienie i — jeśli było opłacone — zleca zwrot w PayU. "
            "order-service działa tu jako koordynator (orkiestracja): walidacja statusu → "
            "zwrot PayU → zmiana statusu na `cancelled` → powiadomienie restauracji i "
            "delivery przez `order.cancelled`. Jeśli zwrot się nie powiedzie, anulowanie "
            "jest przerywane (zamówienie zostaje w dotychczasowym statusie)."
        ),
        request=None,
        responses={200: OrderSerializer},
        examples=[
            OpenApiExample(
                "Przykład odpowiedzi",
                value={**_ORDER_RESPONSE_EXAMPLE, "status": "cancelled", "status_display": "Anulowane"},
                response_only=True,
            ),
        ],
    )
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        order = self.get_object()

        if order.status not in self.CANCELLABLE_STATUSES:
            return Response(
                {'detail': f'Nie można anulować zamówienia w statusie "{order.get_status_display()}".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Krok orkiestracji: zwrot pieniędzy (tylko jeśli płatność faktycznie nastąpiła).
        if order.status != Order.Status.PENDING_PAYMENT and order.payment_id:
            try:
                result = payu.refund_order(order.payment_id, description=f'Anulowanie zamówienia #{order.id}')
            except payu.PayUError as e:
                logger.error(f'Refund failed for order {order.id}: {e}')
                return Response(
                    {'detail': 'Nie udało się wykonać zwrotu — anulowanie przerwane.'},
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            order.refund_id = result.get('refund', {}).get('refundId', '')

        order.status = Order.Status.CANCELLED
        order.cancelled_at = timezone.now()
        order.save()

        # Powiadom klienta oraz restaurację/delivery żeby przerwały realizację.
        publish_order_status_notification(order)
        publish_order_cancelled(order)
        logger.info(f'Order {order.id} cancelled by customer')

        return Response(OrderSerializer(order).data)


@extend_schema(
    summary="Webhook PayU (powiadomienie o statusie płatności)",
    description=(
        "Endpoint wywoływany przez serwery PayU (server-to-server) po zmianie statusu "
        "płatności. Weryfikuje podpis z nagłówka `OpenPayu-Signature`. Po statusie "
        "`COMPLETED` ustawia zamówienie na `paid` i publikuje `order.created`. "
        "Nie wymaga autoryzacji JWT."
    ),
    request=None,
    responses={200: None},
)
class PayUWebhookView(APIView):
    """Odbiera powiadomienia PayU. Bez JWT — PayU nie zna naszych tokenów."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        signature = request.headers.get('OpenPayu-Signature', '')
        if not payu.verify_notification_signature(request.body, signature):
            logger.warning('PayU webhook: nieprawidłowy podpis')
            return Response(status=status.HTTP_403_FORBIDDEN)

        order_data = request.data.get('order', {})
        ext_order_id = order_data.get('extOrderId')
        payu_status = order_data.get('status')

        order = Order.objects.filter(id=ext_order_id).first()
        if not order:
            logger.warning(f'PayU webhook: zamówienie {ext_order_id} nie istnieje')
            # Zwracamy 200, żeby PayU przestał ponawiać powiadomienie.
            return Response(status=status.HTTP_200_OK)

        if payu_status == 'COMPLETED' and order.status == Order.Status.PENDING_PAYMENT:
            order.status = Order.Status.PAID
            order.payment_id = order_data.get('orderId', order.payment_id)
            order.save()
            publish_order_status_notification(order)
            publish_order_created(order)
            logger.info(f'PayU webhook: zamówienie {order.id} opłacone')

        return Response(status=status.HTTP_200_OK)
