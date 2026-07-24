import hashlib
import hmac
import logging
from decimal import Decimal

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class PayUError(Exception):
    """Błąd komunikacji z PayU."""


def _to_grosze(amount: Decimal) -> str:
    """PayU oczekuje kwot w groszach jako string, np. 25.00 PLN -> "2500"."""
    return str(int((Decimal(amount) * 100).quantize(Decimal('1'))))


def get_access_token() -> str:
    """Pobiera token OAuth2 (grant_type=client_credentials)."""
    try:
        resp = requests.post(
            f'{settings.PAYU_BASE_URL}/pl/standard/user/oauth/authorize',
            data={
                'grant_type': 'client_credentials',
                'client_id': settings.PAYU_CLIENT_ID,
                'client_secret': settings.PAYU_CLIENT_SECRET,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()['access_token']
    except (requests.RequestException, KeyError, ValueError) as e:
        raise PayUError(f'Nie udało się pobrać tokenu PayU: {e}') from e


def create_order(order, customer_ip: str = '127.0.0.1') -> dict:
    """Tworzy płatność w PayU dla danego zamówienia.

    Zwraca dict z PayU zawierający m.in. ``redirectUri`` (link do strony
    płatności) oraz ``orderId`` (identyfikator płatności po stronie PayU).
    """
    token = get_access_token()

    products = [
        {
            'name': item.name,
            'unitPrice': _to_grosze(item.unit_price),
            'quantity': str(item.quantity),
        }
        for item in order.items.all()
    ]

    payload = {
        'notifyUrl': settings.PAYU_NOTIFY_URL,
        'continueUrl': settings.PAYU_CONTINUE_URL,
        'customerIp': customer_ip,
        'merchantPosId': settings.PAYU_POS_ID,
        'description': f'Zamówienie #{order.id}',
        'currencyCode': 'PLN',
        'totalAmount': _to_grosze(order.total_price),
        'extOrderId': str(order.id),
        'products': products,
        'buyer': {
            'email': 'buyer@example.com',
            'language': 'pl',
        },
    }

    try:
        # allow_redirects=False — PayU odpowiada 302 z ciałem JSON; bez tego
        # requests podążyłby za przekierowaniem i stracilibyśmy redirectUri.
        resp = requests.post(
            f'{settings.PAYU_BASE_URL}/api/v2_1/orders',
            json=payload,
            headers={'Authorization': f'Bearer {token}'},
            allow_redirects=False,
            timeout=10,
        )
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        raise PayUError(f'Błąd tworzenia płatności PayU: {e}') from e

    status_code = data.get('status', {}).get('statusCode')
    if status_code not in ('SUCCESS', 'WARNING_CONTINUE_3DS', 'WARNING_CONTINUE_CVV'):
        raise PayUError(f'PayU odrzucił płatność: {data}')

    return data


def refund_order(payu_order_id: str, description: str = 'Anulowanie zamówienia',
                 amount: Decimal | None = None) -> dict:
    """Zleca zwrot płatności w PayU.

    ``payu_order_id`` to identyfikator płatności z PayU (zapisany w
    ``order.payment_id``). Bez ``amount`` wykonywany jest zwrot pełny;
    podanie kwoty zwraca część (na przyszłość — np. zwrot z opłatą).
    """
    token = get_access_token()

    refund: dict = {'description': description}
    if amount is not None:
        refund['amount'] = _to_grosze(amount)

    try:
        resp = requests.post(
            f'{settings.PAYU_BASE_URL}/api/v2_1/orders/{payu_order_id}/refunds',
            json={'refund': refund},
            headers={'Authorization': f'Bearer {token}'},
            timeout=10,
        )
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        raise PayUError(f'Błąd zwrotu PayU: {e}') from e

    status_code = data.get('status', {}).get('statusCode')
    if status_code != 'SUCCESS':
        raise PayUError(f'PayU odrzucił zwrot: {data}')

    return data


def verify_notification_signature(raw_body: bytes, signature_header: str) -> bool:
    """Weryfikuje podpis powiadomienia z nagłówka ``OpenPayu-Signature``.

    Nagłówek ma postać: ``sender=...;signature=<hash>;algorithm=MD5;content=DOCUMENT``
    Podpis to hash(treść_body + drugi_klucz).
    """
    if not signature_header or not settings.PAYU_SECOND_KEY:
        return False

    parts = {}
    for chunk in signature_header.split(';'):
        if '=' in chunk:
            key, value = chunk.split('=', 1)
            parts[key.strip()] = value.strip()

    incoming = parts.get('signature')
    algorithm = parts.get('algorithm', 'MD5').upper()
    if not incoming:
        return False

    payload = raw_body + settings.PAYU_SECOND_KEY.encode()
    if algorithm == 'SHA-256':
        expected = hashlib.sha256(payload).hexdigest()
    else:
        expected = hashlib.md5(payload).hexdigest()

    return hmac.compare_digest(incoming, expected)
