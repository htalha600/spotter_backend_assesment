"""Resolve a location string to (lng, lat, label). Local City table first,
OpenRouteService geocoding as a fallback."""
import re
from routing.models import City
from routing.services import ors_client


class LocationNotFound(Exception):
    pass


_CITY_STATE = re.compile(r"^\s*(.+?)\s*,\s*([A-Za-z]{2})\s*$")


def resolve(text):
    """Return (lng, lat, label). Raises LocationNotFound if it can't be resolved."""
    m = _CITY_STATE.match(text or "")
    if m:
        name, state = m.group(1), m.group(2).upper()
        city = City.objects.filter(name__iexact=name, state__iexact=state).first()
        if city:
            return city.lng, city.lat, f"{city.name}, {city.state}"

    result = ors_client.geocode(text)
    if result is None:
        raise LocationNotFound(f"Could not resolve location: {text!r}")
    return result
