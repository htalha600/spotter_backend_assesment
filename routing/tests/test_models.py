import pytest
from routing.models import City


@pytest.mark.django_db
def test_city_lookup_is_case_insensitive():
    City.objects.create(name="Gila Bend", state="AZ", lat=32.9, lng=-112.7)
    found = City.objects.get(name__iexact="gila bend", state__iexact="az")
    assert round(found.lat, 1) == 32.9
