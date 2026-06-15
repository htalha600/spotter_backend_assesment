import pytest
from routing.models import City
from routing.services import geocoding


@pytest.mark.django_db
def test_resolve_uses_local_city_table_without_api(monkeypatch):
    City.objects.create(name="Gila Bend", state="AZ", lat=32.9, lng=-112.7)

    def _boom(*a, **k):
        raise AssertionError("ORS should not be called when local hit exists")
    monkeypatch.setattr(geocoding.ors_client, "geocode", _boom)

    lng, lat, label = geocoding.resolve("Gila Bend, AZ")
    assert (round(lng, 1), round(lat, 1)) == (-112.7, 32.9)


@pytest.mark.django_db
def test_resolve_falls_back_to_ors(monkeypatch):
    monkeypatch.setattr(geocoding.ors_client, "geocode",
                        lambda text: (-71.06, 42.36, "Boston, MA"))
    lng, lat, label = geocoding.resolve("123 Some Address, Boston")
    assert label == "Boston, MA"


@pytest.mark.django_db
def test_resolve_raises_when_unresolvable(monkeypatch):
    monkeypatch.setattr(geocoding.ors_client, "geocode", lambda text: None)
    with pytest.raises(geocoding.LocationNotFound):
        geocoding.resolve("Nowhere Atlantis")
