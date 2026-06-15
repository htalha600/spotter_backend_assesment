# Fuel Route API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Django REST API that takes a US start and finish, returns the driving route geometry, the cost-optimal fuel stops for a 500-mile-range / 10-mpg vehicle, and total fuel cost — using a single external routing call.

**Architecture:** Fuel stations are pre-geocoded offline by joining the fuel CSV's City+State against a bundled free US-cities coordinate dataset, then stored in SQLite. At request time we make **one** OpenRouteService directions call, project stored stations onto the returned polyline (pure Python), and run the classic "gas station problem" greedy to choose cost-optimal fill-ups. Start/finish are resolved against the local cities table first, so the common case is exactly one external call.

**Tech Stack:** Python 3.12, Django 5.2 (latest stable), Django REST Framework, `requests`, SQLite. OpenRouteService for routing (+ geocoding fallback).

---

## File Structure

```
fuel-route-api/
├── manage.py
├── requirements.txt
├── .env.example
├── README.md
├── data/
│   ├── fuel-prices-for-be-assessment.csv      # provided (copied in)
│   └── uscities.csv                            # bundled free SimpleMaps dataset
├── config/                                     # Django project
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
└── routing/                                    # the app
    ├── models.py                               # City, Station
    ├── serializers.py                          # request/response serialization
    ├── views.py                                # RouteView (the endpoint)
    ├── urls.py
    ├── services/
    │   ├── corridor.py                         # haversine, cumulative dist, station projection
    │   ├── fuel.py                             # gas-station optimal greedy
    │   ├── ors_client.py                       # OpenRouteService HTTP calls
    │   └── geocoding.py                        # resolve start/finish (local DB -> ORS)
    ├── management/commands/
    │   ├── load_cities.py                      # uscities.csv -> City table
    │   └── load_stations.py                    # fuel CSV join cities -> Station table
    └── tests/
        ├── test_corridor.py
        ├── test_fuel.py
        ├── test_geocoding.py
        └── test_view.py
```

**Responsibilities (one job each):**
- `services/fuel.py` — pure algorithm, no Django, no IO. Easiest thing to test in isolation.
- `services/corridor.py` — pure geometry, no Django, no IO.
- `services/ors_client.py` — the only module that talks to the network.
- `services/geocoding.py` — resolve a location string to coordinates.
- `views.py` — orchestration only; no business logic beyond wiring.

---

## Task 0: Project scaffold

**Files:**
- Create: `requirements.txt`, `.env.example`, `manage.py`, `config/settings.py`, `config/urls.py`, `config/wsgi.py`, `config/__init__.py`, `routing/__init__.py`, `routing/apps.py`

- [ ] **Step 1: Create `requirements.txt`**

```
Django==5.2.*
djangorestframework==3.15.*
requests==2.32.*
python-dotenv==1.0.*
pytest==8.*
pytest-django==4.*
```

- [ ] **Step 2: Create and activate a venv, install deps**

Run (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
Expected: installs without error. Confirm Django version:
```powershell
python -c "import django; print(django.get_version())"
```
Expected: `5.2.x`

- [ ] **Step 3: Scaffold the Django project and app**

Run:
```powershell
django-admin startproject config .
python manage.py startapp routing
```
Expected: creates `config/` and `routing/` packages, `manage.py` at root.

- [ ] **Step 4: Configure `config/settings.py`**

Replace the `INSTALLED_APPS`, and add config block. Add to `INSTALLED_APPS`:
```python
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "routing",
]
```
Append at the bottom of `settings.py`:
```python
import os
from dotenv import load_dotenv

load_dotenv(BASE_DIR / ".env")

# OpenRouteService
ORS_API_KEY = os.getenv("ORS_API_KEY", "")
ORS_BASE_URL = os.getenv("ORS_BASE_URL", "https://api.openrouteservice.org")

# Vehicle constants (assignment-fixed)
VEHICLE_RANGE_MILES = 500.0
VEHICLE_MPG = 10.0
# How far off the route a station may be (city-centroid coords are coarse)
CORRIDOR_MAX_DETOUR_MILES = 25.0

DATA_DIR = BASE_DIR / "data"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}
```

- [ ] **Step 5: Create `.env.example`**

```
ORS_API_KEY=your-openrouteservice-api-key-here
ORS_BASE_URL=https://api.openrouteservice.org
```

- [ ] **Step 6: Add `pytest.ini` for pytest-django**

Create `pytest.ini`:
```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings
python_files = tests.py test_*.py *_tests.py
```

- [ ] **Step 7: Verify the project boots**

Run:
```powershell
python manage.py check
```
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 8: Commit**

```powershell
git add .
git commit -m "chore: scaffold Django project, app, and dependencies"
```

---

## Task 1: City model + `load_cities` command

The `City` table provides coordinates for (a) geocoding station City+State and (b) resolving start/finish inputs — both with zero API calls.

**Get the dataset:** Download the free SimpleMaps "US Cities" Basic CSV (CC BY 4.0) from https://simplemaps.com/data/us-cities and place the extracted `uscities.csv` at `data/uscities.csv`. Relevant columns: `city`, `state_id` (2-letter), `lat`, `lng`.

**Files:**
- Modify: `routing/models.py`
- Create: `routing/management/__init__.py`, `routing/management/commands/__init__.py`, `routing/management/commands/load_cities.py`
- Test: `routing/tests/test_models.py`

- [ ] **Step 1: Define the `City` model in `routing/models.py`**

```python
from django.db import models


class City(models.Model):
    name = models.CharField(max_length=120)
    state = models.CharField(max_length=2)
    lat = models.FloatField()
    lng = models.FloatField()

    class Meta:
        indexes = [models.Index(fields=["name", "state"])]
        unique_together = [("name", "state")]

    def __str__(self):
        return f"{self.name}, {self.state}"
```

- [ ] **Step 2: Make and run migrations**

Run:
```powershell
python manage.py makemigrations routing
python manage.py migrate
```
Expected: creates `routing/migrations/0001_initial.py`, applies cleanly.

- [ ] **Step 3: Write the failing test**

Create `routing/tests/__init__.py` (empty) and `routing/tests/test_models.py`:
```python
import pytest
from routing.models import City


@pytest.mark.django_db
def test_city_lookup_is_case_insensitive():
    City.objects.create(name="Gila Bend", state="AZ", lat=32.9, lng=-112.7)
    found = City.objects.get(name__iexact="gila bend", state__iexact="az")
    assert round(found.lat, 1) == 32.9
```

- [ ] **Step 4: Run it to confirm it passes (model already exists)**

Run:
```powershell
pytest routing/tests/test_models.py -v
```
Expected: PASS. (This test pins the lookup contract used later.)

- [ ] **Step 5: Write `load_cities.py`**

```python
import csv
from django.conf import settings
from django.core.management.base import BaseCommand
from routing.models import City


class Command(BaseCommand):
    help = "Load US city coordinates from data/uscities.csv into the City table."

    def handle(self, *args, **options):
        path = settings.DATA_DIR / "uscities.csv"
        if not path.exists():
            self.stderr.write(f"Missing {path}. Download from simplemaps.com/data/us-cities.")
            return
        City.objects.all().delete()
        objs = {}
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                name = row["city"].strip()
                state = row["state_id"].strip().upper()
                key = (name.upper(), state)
                if key in objs:
                    continue  # keep first (SimpleMaps lists largest first)
                try:
                    objs[key] = City(name=name, state=state,
                                     lat=float(row["lat"]), lng=float(row["lng"]))
                except (KeyError, ValueError):
                    continue
        City.objects.bulk_create(objs.values(), batch_size=2000)
        self.stdout.write(self.style.SUCCESS(f"Loaded {len(objs)} cities."))
```

- [ ] **Step 6: Run the loader and verify**

Run:
```powershell
python manage.py load_cities
python manage.py shell -c "from routing.models import City; print(City.objects.count())"
```
Expected: prints a count in the tens of thousands (~31,000).

- [ ] **Step 7: Commit**

```powershell
git add routing config data/uscities.csv
git commit -m "feat: City model and load_cities command"
```

---

## Task 2: Station model + `load_stations` command

**Files:**
- Modify: `routing/models.py`
- Create: `routing/management/commands/load_stations.py`
- Test: `routing/tests/test_load_stations.py`

- [ ] **Step 1: Add the `Station` model to `routing/models.py`**

```python
class Station(models.Model):
    opis_id = models.CharField(max_length=20)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=300, blank=True)
    city = models.CharField(max_length=120)
    state = models.CharField(max_length=2)
    price = models.FloatField()
    lat = models.FloatField()
    lng = models.FloatField()

    class Meta:
        indexes = [
            models.Index(fields=["lat", "lng"]),
            models.Index(fields=["state"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state})"
```

- [ ] **Step 2: Make and run migrations**

Run:
```powershell
python manage.py makemigrations routing
python manage.py migrate
```
Expected: new migration applied.

- [ ] **Step 3: Write the failing test**

Create `routing/tests/test_load_stations.py`:
```python
import pytest
from django.core.management import call_command
from routing.models import City, Station


@pytest.mark.django_db
def test_load_stations_joins_city_coords_and_dedupes(tmp_path, settings):
    settings.DATA_DIR = tmp_path
    (tmp_path / "fuel-prices-for-be-assessment.csv").write_text(
        "OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\n"
        "20,PILOT TRAVEL CENTER #1243,\"I-8\",Gila Bend,AZ,930,3.899\n"
        "20,PILOT #1243,\"I-8\",Gila Bend,AZ,930,3.899\n"          # dup id, same loc
        "7,WOODSHED,\"I-44\",Big Cabin,OK,307,3.00\n"
        "99,NOWHERE,\"X\",Atlantis,ZZ,1,9.99\n",                    # unresolvable city
        encoding="utf-8",
    )
    City.objects.create(name="Gila Bend", state="AZ", lat=32.9, lng=-112.7)
    City.objects.create(name="Big Cabin", state="OK", lat=36.5, lng=-95.2)

    call_command("load_stations")

    assert Station.objects.count() == 2          # dup collapsed, unresolvable dropped
    gila = Station.objects.get(city="Gila Bend")
    assert round(gila.lat, 1) == 32.9
    assert round(gila.price, 3) == 3.899
```

- [ ] **Step 4: Run it to verify it fails**

Run:
```powershell
pytest routing/tests/test_load_stations.py -v
```
Expected: FAIL — `load_stations` command does not exist.

- [ ] **Step 5: Write `load_stations.py`**

```python
import csv
from django.conf import settings
from django.core.management.base import BaseCommand
from routing.models import City, Station


class Command(BaseCommand):
    help = "Load fuel stations, geocoding each by joining City+State to the City table."

    def handle(self, *args, **options):
        path = settings.DATA_DIR / "fuel-prices-for-be-assessment.csv"
        cities = {(c.name.upper(), c.state): (c.lat, c.lng)
                  for c in City.objects.all()}

        best = {}        # (city_upper, state) -> chosen row (cheapest), keeps one per location
        unresolved = set()
        total = 0
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                total += 1
                city = row["City"].strip()
                state = row["State"].strip().upper()
                key = (city.upper(), state)
                coords = cities.get(key)
                if coords is None:
                    unresolved.add(key)
                    continue
                try:
                    price = float(row["Retail Price"])
                except (KeyError, ValueError):
                    continue
                # keep the cheapest station per location (cost-effective choice)
                if key not in best or price < best[key]["price"]:
                    best[key] = {
                        "opis_id": row["OPIS Truckstop ID"].strip(),
                        "name": row["Truckstop Name"].strip(),
                        "address": row.get("Address", "").strip(),
                        "city": city, "state": state, "price": price,
                        "lat": coords[0], "lng": coords[1],
                    }

        Station.objects.all().delete()
        Station.objects.bulk_create(
            [Station(**v) for v in best.values()], batch_size=2000
        )
        resolved = len(best)
        self.stdout.write(self.style.SUCCESS(
            f"Loaded {resolved} stations from {total} rows. "
            f"Unresolved locations: {len(unresolved)}."
        ))
```

- [ ] **Step 6: Run the test to verify it passes**

Run:
```powershell
pytest routing/tests/test_load_stations.py -v
```
Expected: PASS.

- [ ] **Step 7: Run against real data, sanity-check coverage**

Run (after copying the provided CSV to `data/`):
```powershell
python manage.py load_stations
```
Expected: prints e.g. "Loaded ~3,5xx stations ... Unresolved locations: <few hundred>". A high resolve rate confirms the city join works.

- [ ] **Step 8: Commit**

```powershell
git add routing
git commit -m "feat: Station model and load_stations command with city-join geocoding"
```

---

## Task 3: Corridor geometry (`services/corridor.py`)

Pure functions: distance, cumulative distance along the route, and projecting stations onto the route to get "miles from start" + detour, with a bbox prefilter for speed.

**Files:**
- Create: `routing/services/__init__.py`, `routing/services/corridor.py`
- Test: `routing/tests/test_corridor.py`

- [ ] **Step 1: Write the failing tests**

Create `routing/tests/test_corridor.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run:
```powershell
pytest routing/tests/test_corridor.py -v
```
Expected: FAIL — module/functions not defined.

- [ ] **Step 3: Implement `services/corridor.py`**

```python
"""Pure geometry helpers for matching stations to a route polyline.

Route coordinates are (lng, lat) pairs, matching GeoJSON / ORS output.
"""
from math import radians, sin, cos, asin, sqrt

EARTH_RADIUS_MI = 3958.8


def haversine_miles(lat1, lng1, lat2, lng2):
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = (sin(dlat / 2) ** 2
         + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2)
    return 2 * EARTH_RADIUS_MI * asin(sqrt(a))


def cumulative_miles(coords):
    """coords: list of (lng, lat). Returns cumulative miles, [0] == 0.0."""
    cum = [0.0]
    for (lng1, lat1), (lng2, lat2) in zip(coords, coords[1:]):
        cum.append(cum[-1] + haversine_miles(lat1, lng1, lat2, lng2))
    return cum


def _downsample(coords, cum, step_miles=5.0):
    """Thin the polyline to ~one vertex per step_miles to bound projection cost.
    Always keeps first and last vertex. Returns (coords2, cum2)."""
    if len(coords) <= 2:
        return coords, cum
    keep = [0]
    last = 0.0
    for i in range(1, len(coords) - 1):
        if cum[i] - last >= step_miles:
            keep.append(i)
            last = cum[i]
    keep.append(len(coords) - 1)
    return [coords[i] for i in keep], [cum[i] for i in keep]


def stations_along_route(coords, stations, max_detour_miles=25.0):
    """Project each station onto the route; keep those within max_detour_miles.

    Returns a new list of station dicts (copies) with an added 'mile' key
    (distance from start along the route), sorted ascending by 'mile', and
    deduplicated per coordinate keeping the cheapest price.
    """
    cum = cumulative_miles(coords)
    dcoords, dcum = _downsample(coords, cum)

    lats = [lat for _, lat in dcoords]
    lngs = [lng for lng, _ in dcoords]
    # bbox + ~max_detour buffer in degrees (1 deg lat ~= 69 mi)
    buf = max_detour_miles / 69.0 + 0.5
    min_lat, max_lat = min(lats) - buf, max(lats) + buf
    min_lng, max_lng = min(lngs) - buf, max(lngs) + buf

    best = {}  # (round lat, round lng) -> chosen dict (cheapest)
    for s in stations:
        lat, lng = s["lat"], s["lng"]
        if not (min_lat <= lat <= max_lat and min_lng <= lng <= max_lng):
            continue
        # nearest downsampled vertex
        best_d, best_i = None, None
        for i, (vlng, vlat) in enumerate(dcoords):
            d = haversine_miles(lat, lng, vlat, vlng)
            if best_d is None or d < best_d:
                best_d, best_i = d, i
        if best_d > max_detour_miles:
            continue
        key = (round(lat, 3), round(lng, 3))
        cand = {**s, "mile": dcum[best_i], "detour": best_d}
        if key not in best or cand["price"] < best[key]["price"]:
            best[key] = cand

    return sorted(best.values(), key=lambda s: s["mile"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```powershell
pytest routing/tests/test_corridor.py -v
```
Expected: PASS (all 3).

- [ ] **Step 5: Commit**

```powershell
git add routing
git commit -m "feat: corridor geometry — haversine, cumulative distance, station projection"
```

---

## Task 4: Fuel algorithm (`services/fuel.py`)

The "gas station problem" optimal greedy. Start with a full tank whose cost is attributed to the cheapest station within range of the start (the pre-trip fill, shown at mile 0); then at each station, if a cheaper station is reachable buy just enough to reach it, else fill up and drive to the farthest reachable station.

**Files:**
- Create: `routing/services/fuel.py`
- Test: `routing/tests/test_fuel.py`

- [ ] **Step 1: Write the failing tests (hand-computed optima)**

Create `routing/tests/test_fuel.py`:
```python
import pytest
from routing.services.fuel import plan_fuel_stops, RouteInfeasible


def _st(mile, price, name="S"):
    return {"mile": float(mile), "price": float(price), "name": name,
            "city": "C", "state": "XX", "lat": 0.0, "lng": 0.0}


def test_short_route_one_fill_at_cheapest_near_start():
    # 300 mi route, one tank covers it. Buy 30 gal at cheapest reachable station.
    stations = [_st(0, 3.0, "A"), _st(100, 2.5, "B")]
    stops, gallons, cost = plan_fuel_stops(stations, total_distance=300)
    assert gallons == 30.0
    assert cost == 75.0                      # 30 gal * 2.5 (cheapest within 500 of start)
    assert len(stops) == 1


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


def test_infeasible_when_gap_exceeds_range():
    stations = [_st(0, 3.0), _st(700, 3.0)]   # 700-mi gap > 500
    with pytest.raises(RouteInfeasible):
        plan_fuel_stops(stations, total_distance=900)


def test_infeasible_when_no_station_near_start():
    stations = [_st(600, 3.0)]
    with pytest.raises(RouteInfeasible):
        plan_fuel_stops(stations, total_distance=900)
```

- [ ] **Step 2: Run to verify failure**

Run:
```powershell
pytest routing/tests/test_fuel.py -v
```
Expected: FAIL — module not defined.

- [ ] **Step 3: Implement `services/fuel.py`**

```python
"""Cost-optimal fuel-stop selection: the classic 'gas station problem'.

Model: the vehicle starts with a full tank, whose cost is attributed to the
cheapest station within range of the start (shown as the mile-0 pre-trip fill).
At each station: if a strictly cheaper station is reachable within range, buy
just enough to coast there; otherwise fill the tank and drive to the farthest
reachable station. This greedy is optimal for the gas station problem.
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
    near_start = [s for s in stations if s["mile"] <= range_miles]
    if not near_start:
        raise RouteInfeasible(f"No fuel station within {range_miles:.0f} miles of the start.")

    # Virtual origin fill priced/identified by the cheapest near-start station.
    origin = min(near_start, key=lambda s: s["price"])
    nodes = [{**origin, "mile": 0.0}] + [s for s in stations if s["mile"] > 0.0]

    # Feasibility: every gap, and last-stop -> destination, must be within range.
    prev = 0.0
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
        # Can we reach the destination from here? Buy only what's needed, then stop.
        if here + range_miles >= total_distance:
            buy(i, (total_distance - here) - tank)
            tank -= (total_distance - here)
            break
        # Find the first strictly-cheaper station within range; track the farthest reachable.
        j = i + 1
        next_cheaper = None
        farthest = i
        while j < n and nodes[j]["mile"] - here <= range_miles:
            farthest = j
            if nodes[j]["price"] < nodes[i]["price"]:
                next_cheaper = j
                break
            j += 1
        if next_cheaper is not None:
            dist = nodes[next_cheaper]["mile"] - here
            buy(i, dist - tank)        # just enough to coast to the cheaper station
            tank -= dist
            i = next_cheaper
        else:
            dist = nodes[farthest]["mile"] - here
            buy(i, range_miles - tank)  # no cheaper ahead: fill the tank
            tank -= dist
            i = farthest

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```powershell
pytest routing/tests/test_fuel.py -v
```
Expected: PASS (all 5). If a cost assertion is off, the bug is in `buy`/tank accounting — fix until the hand-computed values match.

- [ ] **Step 5: Commit**

```powershell
git add routing
git commit -m "feat: optimal gas-station-problem fuel planner"
```

---

## Task 5: OpenRouteService client (`services/ors_client.py`)

The only module that hits the network. One directions call returns geometry + distance; a geocode helper is used only as a fallback for start/finish.

**Files:**
- Create: `routing/services/ors_client.py`
- Test: `routing/tests/test_ors_client.py`

- [ ] **Step 1: Write the failing tests (HTTP mocked via monkeypatch)**

Create `routing/tests/test_ors_client.py`:
```python
from routing.services import ors_client


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError("http error")


def test_directions_parses_geometry_and_miles(monkeypatch):
    payload = {
        "features": [{
            "geometry": {"type": "LineString",
                         "coordinates": [[-100.0, 40.0], [-96.0, 40.0]]},
            "properties": {"summary": {"distance": 160934.0}},  # meters = 100 mi
        }]
    }
    monkeypatch.setattr(ors_client.requests, "post",
                        lambda *a, **k: _FakeResp(payload))
    result = ors_client.directions((-100.0, 40.0), (-96.0, 40.0))
    assert result["coords"][0] == [-100.0, 40.0]
    assert round(result["distance_miles"]) == 100


def test_geocode_returns_first_feature(monkeypatch):
    payload = {"features": [
        {"geometry": {"coordinates": [-112.7, 32.9]},
         "properties": {"label": "Gila Bend, AZ"}}
    ]}
    monkeypatch.setattr(ors_client.requests, "get",
                        lambda *a, **k: _FakeResp(payload))
    lng, lat, label = ors_client.geocode("Gila Bend, AZ")
    assert (round(lng, 1), round(lat, 1)) == (-112.7, 32.9)
    assert "Gila Bend" in label
```

- [ ] **Step 2: Run to verify failure**

Run:
```powershell
pytest routing/tests/test_ors_client.py -v
```
Expected: FAIL — module not defined.

- [ ] **Step 3: Implement `services/ors_client.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```powershell
pytest routing/tests/test_ors_client.py -v
```
Expected: PASS (both).

- [ ] **Step 5: Commit**

```powershell
git add routing
git commit -m "feat: OpenRouteService client (directions + geocode)"
```

---

## Task 6: Location resolver (`services/geocoding.py`)

Resolve start/finish to coordinates. Try the local `City` table first (0 API calls); fall back to ORS geocoding only when the local lookup misses.

**Files:**
- Create: `routing/services/geocoding.py`
- Test: `routing/tests/test_geocoding.py`

- [ ] **Step 1: Write the failing tests**

Create `routing/tests/test_geocoding.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run:
```powershell
pytest routing/tests/test_geocoding.py -v
```
Expected: FAIL — module not defined.

- [ ] **Step 3: Implement `services/geocoding.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```powershell
pytest routing/tests/test_geocoding.py -v
```
Expected: PASS (all 3).

- [ ] **Step 5: Commit**

```powershell
git add routing
git commit -m "feat: location resolver (local City table with ORS fallback)"
```

---

## Task 7: Route API endpoint (`views.py`, `serializers.py`, URLs)

Wire it together: validate input, resolve endpoints, one directions call, project stations, plan fuel, return JSON.

**Files:**
- Create: `routing/views.py`, `routing/serializers.py`, `routing/urls.py`
- Modify: `config/urls.py`
- Test: `routing/tests/test_view.py`

- [ ] **Step 1: Write `routing/serializers.py`**

```python
from rest_framework import serializers


class RouteQuerySerializer(serializers.Serializer):
    start = serializers.CharField(max_length=200)
    finish = serializers.CharField(max_length=200)
```

- [ ] **Step 2: Write the failing integration test**

Create `routing/tests/test_view.py`:
```python
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
```

- [ ] **Step 3: Run to verify failure**

Run:
```powershell
pytest routing/tests/test_view.py -v
```
Expected: FAIL — view/url not defined.

- [ ] **Step 4: Implement `routing/views.py`**

```python
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from routing.models import Station
from routing.serializers import RouteQuerySerializer
from routing.services import ors_client, geocoding
from routing.services.corridor import stations_along_route
from routing.services.fuel import plan_fuel_stops, RouteInfeasible


class RouteView(APIView):
    def get(self, request):
        query = RouteQuerySerializer(data=request.query_params)
        if not query.is_valid():
            return Response(query.errors, status=status.HTTP_400_BAD_REQUEST)
        start_text = query.validated_data["start"]
        finish_text = query.validated_data["finish"]

        # 1. Resolve endpoints (local City table first; ORS fallback)
        try:
            s_lng, s_lat, s_label = geocoding.resolve(start_text)
            f_lng, f_lat, f_label = geocoding.resolve(finish_text)
        except geocoding.LocationNotFound as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # 2. One external routing call
        try:
            route = ors_client.directions((s_lng, s_lat), (f_lng, f_lat))
        except ors_client.ORSError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        # 3. Pure-Python fuel planning
        all_stations = list(
            Station.objects.values("name", "city", "state", "lat", "lng", "price")
        )
        candidates = stations_along_route(
            route["coords"], all_stations,
            max_detour_miles=settings.CORRIDOR_MAX_DETOUR_MILES,
        )
        try:
            stops, total_gallons, total_cost = plan_fuel_stops(
                candidates, route["distance_miles"],
                range_miles=settings.VEHICLE_RANGE_MILES, mpg=settings.VEHICLE_MPG,
            )
        except RouteInfeasible as exc:
            return Response({"error": str(exc)},
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        return Response({
            "start": s_label,
            "finish": f_label,
            "route": {"type": "LineString", "coordinates": route["coords"]},
            "total_distance_miles": round(route["distance_miles"], 1),
            "total_gallons": total_gallons,
            "total_fuel_cost": total_cost,
            "fuel_stops": [s.to_dict() for s in stops],
        })
```

- [ ] **Step 5: Implement URLs**

Create `routing/urls.py`:
```python
from django.urls import path
from routing.views import RouteView

urlpatterns = [path("route", RouteView.as_view(), name="route")]
```

Modify `config/urls.py`:
```python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("routing.urls")),
]
```

- [ ] **Step 6: Run tests to verify they pass**

Run:
```powershell
pytest routing/tests/test_view.py -v
```
Expected: PASS (both).

- [ ] **Step 7: Run the full suite**

Run:
```powershell
pytest -v
```
Expected: all tests PASS.

- [ ] **Step 8: Commit**

```powershell
git add routing config
git commit -m "feat: /api/route endpoint wiring resolver, routing, and fuel planner"
```

---

## Task 8: Manual end-to-end + README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Get an ORS API key and configure**

Sign up at https://openrouteservice.org/dev/#/signup, create a free token, copy `.env.example` to `.env`, and paste the key into `ORS_API_KEY`.

- [ ] **Step 2: Load data (once)**

Run:
```powershell
python manage.py migrate
python manage.py load_cities
python manage.py load_stations
```
Expected: cities + stations loaded, coverage line printed.

- [ ] **Step 3: Run the server and hit a real route**

Run:
```powershell
python manage.py runserver
```
In another terminal (or Postman):
```powershell
curl "http://127.0.0.1:8000/api/route?start=New%20York,%20NY&finish=Los%20Angeles,%20CA"
```
Expected: JSON with a `route` LineString, several `fuel_stops`, and a `total_fuel_cost`. Confirm `total_gallons` ≈ distance/10, and that stops are <500 mi apart. Verify in the server log that **exactly one** ORS request was made.

- [ ] **Step 4: Write `README.md`**

Cover: what it does; the one-external-call design; setup (venv, install, ORS key, `load_cities`/`load_stations`, where to get `uscities.csv`); the `GET /api/route?start=&finish=` contract with a sample response; documented assumptions (city-centroid coords, cheapest-per-location, start-with-full-tank cost model, 10 mpg / 500 mi); how to run tests (`pytest`). Add SimpleMaps CC BY 4.0 attribution.

- [ ] **Step 5: Commit**

```powershell
git add README.md
git commit -m "docs: setup, API contract, and design notes"
```

---

## Self-Review Notes (addressed)

- **Spec coverage:** route map (LineString in response) ✓; optimal cost-effective stops (Task 4) ✓; 500-mi multi-stop (Task 4 feasibility + greedy) ✓; total fuel cost @10 mpg (Task 4) ✓; uses provided CSV (Task 2) ✓; free routing API (Task 5) ✓; latest Django (Task 0) ✓; fast + ≤3 external calls (local resolver + single directions call, Tasks 5–7) ✓.
- **Call budget:** common case = 1 (directions); worst case = 3 (2 geocode fallbacks + 1 directions). Within "2–3 acceptable."
- **Type consistency:** `plan_fuel_stops` returns `(list[Stop], float, float)`; `Stop.to_dict()` used in the view; station dicts carry `name/city/state/lat/lng/price` from Task 7's `.values(...)` and gain `mile` in `stations_along_route`. Consistent across tasks.
