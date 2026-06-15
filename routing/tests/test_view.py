import pytest
from django.urls import reverse
from routing.models import Station
from routing.services import ors_client, geocoding


@pytest.fixture
def seeded(db):
    for mile_city in [("A", 32.0, -110.0, 3.0), ("B", 32.0, -103.0, 2.5),
                      ("C", 32.0, -96.0, 3.2)]:
        name, lat, lng, price = mile_city
        Station.objects.create(opis_id="1", name=name, city=name, state="XX",
                               price=price, lat=lat, lng=lng, address="")


@pytest.mark.django_db
def test_route_endpoint_returns_stops_and_cost(client, seeded, monkeypatch):
    # ~ east-west line at lat 32 from lng -110 to -96 (~820 mi)
    monkeypatch.setattr(geocoding, "resolve",
                        lambda t: (-110.0, 32.0, "Start") if "start" in t.lower()
                        else (-96.0, 32.0, "Finish"))
    monkeypatch.setattr(ors_client, "directions", lambda s, e: {
        "coords": [[-110.0, 32.0], [-103.0, 32.0], [-96.0, 32.0]],
        "distance_miles": 820.0,
    })

    resp = client.get(reverse("route"), {"start": "start city, XX",
                                         "finish": "finish city, XX"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["route"]["type"] == "LineString"
    assert data["total_distance_miles"] == 820.0
    assert data["total_fuel_cost"] > 0
    assert len(data["fuel_stops"]) >= 1
    # gallons consumed == distance / 10
    assert round(data["total_gallons"], 1) == 82.0


@pytest.mark.django_db
def test_route_endpoint_validates_missing_params(client):
    resp = client.get(reverse("route"), {"start": "x"})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_route_endpoint_returns_422_when_no_stations_near_route(client, monkeypatch):
    # No Station rows seeded -> corridor filtering yields no candidates ->
    # plan_fuel_stops raises RouteInfeasible -> the view must return 422, not 500.
    monkeypatch.setattr(geocoding, "resolve",
                        lambda t: (-110.0, 32.0, "Start") if "start" in t.lower()
                        else (-96.0, 32.0, "Finish"))
    monkeypatch.setattr(ors_client, "directions", lambda s, e: {
        "coords": [[-110.0, 32.0], [-103.0, 32.0], [-96.0, 32.0]],
        "distance_miles": 820.0,
    })

    resp = client.get(reverse("route"), {"start": "start city, XX",
                                         "finish": "finish city, XX"})
    assert resp.status_code == 422
    assert "error" in resp.json()
