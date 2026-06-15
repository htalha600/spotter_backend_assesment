from routing.services.corridor import (
    haversine_miles, cumulative_miles, stations_along_route,
)


def test_haversine_known_distance():
    # NYC -> LA is ~2450 miles; allow tolerance
    d = haversine_miles(40.71, -74.01, 34.05, -118.24)
    assert 2400 < d < 2500


def test_cumulative_miles_monotonic_from_zero():
    coords = [(-100.0, 40.0), (-99.0, 40.0), (-98.0, 40.0)]  # (lng, lat) heading east
    cum = cumulative_miles(coords)
    assert cum[0] == 0.0
    assert cum[1] > 0 and cum[2] > cum[1]


def test_stations_along_route_filters_and_orders():
    # straight east-west route along lat 40 from lng -100 to -96
    coords = [(-100.0, 40.0), (-98.0, 40.0), (-96.0, 40.0)]
    stations = [
        {"name": "near-mid", "city": "A", "state": "XX", "lat": 40.05, "lng": -98.0, "price": 3.0},
        {"name": "near-start", "city": "B", "state": "XX", "lat": 40.0, "lng": -100.0, "price": 4.0},
        {"name": "far-off", "city": "C", "state": "XX", "lat": 30.0, "lng": -98.0, "price": 1.0},
    ]
    out = stations_along_route(coords, stations, max_detour_miles=25.0)
    names = [s["name"] for s in out]
    assert "far-off" not in names            # too far off route
    assert names == ["near-start", "near-mid"]   # ordered by miles-from-start
    assert out[0]["mile"] < out[1]["mile"]
