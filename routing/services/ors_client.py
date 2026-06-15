"""OpenRouteService HTTP client. The directions call is the single external
request in the normal request path."""
import requests
from django.conf import settings

_METERS_PER_MILE = 1609.34


class ORSError(Exception):
    pass


def _headers():
    return {"Authorization": settings.ORS_API_KEY,
            "Content-Type": "application/json"}


def directions(start_lnglat, end_lnglat, timeout=15):
    """start/end: (lng, lat). Returns {'coords': [[lng,lat],...], 'distance_miles': float}."""
    url = f"{settings.ORS_BASE_URL}/v2/directions/driving-car/geojson"
    body = {"coordinates": [list(start_lnglat), list(end_lnglat)]}
    try:
        resp = requests.post(url, json=body, headers=_headers(), timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        feature = data["features"][0]
        coords = feature["geometry"]["coordinates"]
        meters = feature["properties"]["summary"]["distance"]
    except (requests.RequestException, KeyError, IndexError) as exc:
        raise ORSError(f"Routing failed: {exc}") from exc
    return {"coords": coords, "distance_miles": meters / _METERS_PER_MILE}


def geocode(text, timeout=10):
    """Resolve a free-text US location to (lng, lat, label). Returns None if not found."""
    url = f"{settings.ORS_BASE_URL}/geocode/search"
    params = {"api_key": settings.ORS_API_KEY, "text": text,
              "boundary.country": "US", "size": 1}
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        features = resp.json().get("features", [])
        if not features:
            return None
        lng, lat = features[0]["geometry"]["coordinates"]
        label = features[0]["properties"].get("label", text)
    except (requests.RequestException, KeyError, IndexError) as exc:
        raise ORSError(f"Geocoding failed: {exc}") from exc
    return lng, lat, label
