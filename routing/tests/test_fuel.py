import pytest
from routing.services.fuel import plan_fuel_stops, RouteInfeasible


def _st(mile, price, name="S"):
    return {"mile": float(mile), "price": float(price), "name": name,
            "city": "C", "state": "XX", "lat": 0.0, "lng": 0.0}


def test_short_route_single_fill():
    # 300 mi route, one station at the start, one tank (500 mi) covers it.
    stations = [_st(0, 3.0, "A")]
    stops, gallons, cost = plan_fuel_stops(stations, total_distance=300)
    assert gallons == 30.0
    assert cost == 90.0                       # 30 gal * 3.0
    assert len(stops) == 1


def test_prefill_at_nearest_when_no_station_at_origin():
    # Nearest station is 50 mi in; the pre-trip fill is attributed to it at mile 0.
    stations = [_st(50, 3.0, "A"), _st(300, 2.0, "B")]
    stops, gallons, cost = plan_fuel_stops(stations, total_distance=400)
    assert gallons == 40.0
    # 30 gal @3 covers 0->300 (only A available in that stretch) + 10 gal @2 to dest
    assert cost == 110.0
    assert stops[0].miles_from_start == 0.0


def test_prefers_cheaper_station_ahead():
    # 400 mi, both reachable. Optimal: minimal at start, bulk at the cheap one.
    stations = [_st(0, 4.0, "A"), _st(100, 2.0, "B")]
    stops, gallons, cost = plan_fuel_stops(stations, total_distance=400)
    assert gallons == 40.0
    # 10 gal @4 (reach B) + 30 gal @2 (reach dest) = 40 + 60
    assert cost == 100.0


def test_capacity_forces_stop_and_fills_cheap_first():
    # 1100 mi, range 500. Fill full at cheap start, minimize at the expensive middle.
    stations = [_st(0, 3.0, "A"), _st(450, 5.0, "B"), _st(900, 2.0, "C")]
    stops, gallons, cost = plan_fuel_stops(stations, total_distance=1100)
    assert gallons == 110.0
    # 50@3 (150) + 40@5 (200) + 20@2 (40) = 390
    assert cost == 390.0
    assert [round(s.miles_from_start) for s in stops] == [0, 450, 900]


def test_does_not_overshoot_to_expensive_station():
    # Regression: cheap station at 100, expensive at 400, dest 600, range 500.
    # Optimal stops cheaply at mile 100 and coasts the final 500 mi, never buying
    # the $4 fuel. A naive "fill up and drive to the farthest station" overshoots
    # to mile 400 and is forced to buy expensive fuel ($90 instead of $60).
    stations = [_st(100, 1.0, "A"), _st(400, 4.0, "B")]
    stops, gallons, cost = plan_fuel_stops(stations, total_distance=600)
    assert gallons == 60.0
    assert cost == 60.0
    assert all(s.price_per_gallon == 1.0 for s in stops)


def test_infeasible_when_gap_exceeds_range():
    stations = [_st(0, 3.0), _st(700, 3.0)]   # 700-mi gap > 500
    with pytest.raises(RouteInfeasible):
        plan_fuel_stops(stations, total_distance=900)


def test_infeasible_when_no_station_near_start():
    stations = [_st(600, 3.0)]
    with pytest.raises(RouteInfeasible):
        plan_fuel_stops(stations, total_distance=900)
