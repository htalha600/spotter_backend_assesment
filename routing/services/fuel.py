"""Cost-optimal fuel-stop selection: the classic 'gas station problem'.

Model: all fuel for the trip is purchased at corridor stations. A pre-trip fill
happens at the station nearest the start (a virtual mile-0 node priced at that
station), unless a station already sits at mile 0. At each station the greedy
decides, in order: if a strictly cheaper station is reachable within range, buy
just enough to coast there; else if the destination is reachable, buy just
enough to finish; else fill the tank (current price is the cheapest reachable)
and advance to the next station to re-evaluate. This greedy is optimal for the
gas station problem.
"""
from dataclasses import dataclass, asdict


class RouteInfeasible(Exception):
    pass


@dataclass
class Stop:
    name: str
    city: str
    state: str
    lat: float
    lng: float
    price_per_gallon: float
    miles_from_start: float
    gallons: float
    cost: float

    def to_dict(self):
        return asdict(self)


def plan_fuel_stops(stations, total_distance, range_miles=500.0, mpg=10.0):
    """stations: list of dicts with 'mile','price','name','city','state','lat','lng',
    sorted ascending by 'mile' (one cheapest entry per location).
    Returns (stops: list[Stop], total_gallons: float, total_cost: float).
    Raises RouteInfeasible if any required leg exceeds range_miles.
    """
    stations = sorted(stations, key=lambda s: s["mile"])
    if not stations or stations[0]["mile"] > range_miles:
        raise RouteInfeasible(f"No fuel station within {range_miles:.0f} miles of the start.")

    # Ensure a fueling point exists at mile 0: a pre-trip fill at the station
    # nearest the start (you top up before departing). If a station already sits
    # at mile 0, it serves as the origin directly.
    if stations[0]["mile"] > 0.0:
        nodes = [{**stations[0], "mile": 0.0}] + stations
    else:
        nodes = stations

    # Feasibility: every gap, and last-stop -> destination, must be within range.
    prev = nodes[0]["mile"]
    for s in nodes[1:]:
        if s["mile"] - prev > range_miles:
            raise RouteInfeasible(
                f"No station between mile {prev:.0f} and {s['mile']:.0f} "
                f"(gap exceeds {range_miles:.0f} mi range)."
            )
        prev = s["mile"]
    if total_distance - prev > range_miles:
        raise RouteInfeasible(
            f"Final {total_distance - prev:.0f} mi to destination exceeds range."
        )

    n = len(nodes)
    tank = 0.0            # miles of fuel currently in the tank
    total_gallons = 0.0
    total_cost = 0.0
    bought = {}          # node index -> gallons purchased there

    def buy(i, miles_needed):
        nonlocal tank, total_gallons, total_cost
        if miles_needed <= 1e-9:
            return
        gallons = miles_needed / mpg
        bought[i] = bought.get(i, 0.0) + gallons
        total_gallons += gallons
        total_cost += gallons * nodes[i]["price"]
        tank += miles_needed

    i = 0
    while i < n:
        here = nodes[i]["mile"]
        price = nodes[i]["price"]
        # Find the nearest strictly-cheaper station within range.
        next_cheaper = None
        j = i + 1
        while j < n and nodes[j]["mile"] - here <= range_miles:
            if nodes[j]["price"] < price:
                next_cheaper = j
                break
            j += 1
        if next_cheaper is not None:
            # A cheaper station is reachable: buy just enough to coast there.
            dist = nodes[next_cheaper]["mile"] - here
            buy(i, dist - tank)
            tank -= dist
            i = next_cheaper
        elif here + range_miles >= total_distance:
            # No cheaper station ahead and the destination is reachable: buy just
            # enough to finish.
            buy(i, (total_distance - here) - tank)
            tank -= (total_distance - here)
            break
        else:
            # No cheaper station ahead: this is the cheapest fuel within range, so
            # fill the tank, then advance to the NEXT station and re-evaluate.
            # (Advancing to the next station rather than the farthest reachable one
            # avoids overshooting a cheaper-or-equal refuel point closer to the
            # destination.)
            nxt = i + 1
            buy(i, range_miles - tank)
            tank -= (nodes[nxt]["mile"] - here)
            i = nxt

    stops = []
    for idx, gallons in sorted(bought.items()):
        node = nodes[idx]
        stops.append(Stop(
            name=node["name"], city=node["city"], state=node["state"],
            lat=node["lat"], lng=node["lng"],
            price_per_gallon=round(node["price"], 4),
            miles_from_start=round(node["mile"], 1),
            gallons=round(gallons, 2),
            cost=round(gallons * node["price"], 2),
        ))
    return stops, round(total_gallons, 2), round(total_cost, 2)
