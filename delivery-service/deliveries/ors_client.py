"""
OpenRouteService client.

Docs: https://openrouteservice.org/dev/#/api-docs
"""
import logging

import requests

logger = logging.getLogger(__name__)


class ORSError(Exception):
    """Raised when OpenRouteService returns an unexpected response."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _directions_url() -> str:
    # FIX: lazy access — nie wywołujemy settings na poziomie modułu,
    # żeby uniknąć ImproperlyConfigured przed django.setup().
    from django.conf import settings
    base = settings.OPENROUTESERVICE_BASE_URL.rstrip('/')
    return f'{base}/v2/directions/driving-car/geojson'


def _geocode_url() -> str:
    from django.conf import settings
    base = settings.OPENROUTESERVICE_BASE_URL.rstrip('/')
    return f'{base}/geocode/search'


# ---------------------------------------------------------------------------
# Geocoding  —  address string → (lat, lon)
# ---------------------------------------------------------------------------

def geocode_address(address: str):
    """
    Convert a free-text address to a (latitude, longitude) tuple.

    Uses the ORS Pelias geocoding endpoint. Returns the top result.
    Raises ORSError if the address cannot be resolved.

    Shortcut: if the input is already a "lat,lon" pair (e.g. from a
    delivery.requested event), parse it directly without calling ORS.
    """
    import re
    coords = re.fullmatch(r'\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*', address or '')
    if coords:
        return float(coords.group(1)), float(coords.group(2))

    from django.conf import settings
    api_key = settings.OPENROUTESERVICE_API_KEY
    if not api_key:
        raise ORSError('OPENROUTESERVICE_API_KEY is not set — cannot geocode.')

    try:
        response = requests.get(
            _geocode_url(),
            params={'api_key': api_key, 'text': address, 'size': 1},
            timeout=10,
        )
        response.raise_for_status()
    except requests.exceptions.Timeout:
        raise ORSError(f'ORS geocoding timed out for address: {address!r}')
    except requests.exceptions.HTTPError as exc:
        body = exc.response.text if exc.response is not None else ''
        raise ORSError(f'ORS geocoding HTTP {exc.response.status_code}: {body}') from exc
    except requests.exceptions.RequestException as exc:
        raise ORSError(f'ORS geocoding request failed: {exc}') from exc

    features = response.json().get('features', [])
    if not features:
        raise ORSError(f'No geocoding results for address: {address!r}')

    # GeoJSON coordinates are always [longitude, latitude]
    lon, lat = features[0]['geometry']['coordinates']
    return float(lat), float(lon)


# ---------------------------------------------------------------------------
# Directions  —  (lat, lon) pairs → route
# ---------------------------------------------------------------------------

def calculate_route(
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
) -> dict:
    """
    Call the ORS Directions API and return:
        {
            "geojson":     <GeoJSON FeatureCollection>,
            "distance_m":  float,   # metres
            "duration_s":  float,   # seconds
        }

    Raises ORSError on API / network failures.
    """
    from django.conf import settings
    api_key = settings.OPENROUTESERVICE_API_KEY
    if not api_key:
        logger.warning('OPENROUTESERVICE_API_KEY is not set — skipping route calculation.')
        return _empty_route()

    payload = {
        'coordinates': [
            [float(from_lon), float(from_lat)],   # ORS expects [lon, lat]
            [float(to_lon),   float(to_lat)],
        ],
        'instructions': False,
    }

    headers = {
        'Authorization': api_key,
        'Content-Type': 'application/json; charset=utf-8',
        'Accept': 'application/json, application/geo+json',
    }

    try:
        response = requests.post(
            _directions_url(), json=payload, headers=headers, timeout=10
        )
        response.raise_for_status()
    except requests.exceptions.Timeout:
        raise ORSError('OpenRouteService request timed out.')
    except requests.exceptions.HTTPError as exc:
        body = exc.response.text if exc.response is not None else ''
        raise ORSError(f'ORS HTTP {exc.response.status_code}: {body}') from exc
    except requests.exceptions.RequestException as exc:
        raise ORSError(f'ORS request failed: {exc}') from exc

    data = response.json()

    try:
        feature = data['features'][0]
        summary = feature['properties']['summary']
        return {
            'geojson':    data,
            'distance_m': summary['distance'],
            'duration_s': summary['duration'],
        }
    except (KeyError, IndexError) as exc:
        raise ORSError(f'Unexpected ORS response structure: {exc}') from exc


def _empty_route() -> dict:
    return {'geojson': None, 'distance_m': None, 'duration_s': None}
