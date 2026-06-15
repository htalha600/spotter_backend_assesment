# Fuel Route API

A Django REST API that, given a **start** and **finish** in the USA, returns the
driving route plus the **cost-optimal sequence of fuel stops** for a vehicle with a
**500-mile range** at **10 miles/gallon**, and the **total fuel cost** for the trip.

It is built to hit the external routing/map API as little as possible: **one
OpenRouteService call per request** in the common case (≤3 worst case).

---

## How it works (the design in one minute)

The provided fuel-price CSV lists ~8,100 truck stops by **name/address/city/state +
price** — but with **no coordinates**, and the addresses are highway-exit
descriptions, not geocodable street addresses. The only reliable location signal is
**City + State**.

So geocoding is done **once, offline**, not per request:

1. **`load_cities`** loads a bundled free US-cities coordinate dataset into a `City`
   table.
2. **`load_stations`** reads the fuel CSV, **deduplicates to the cheapest station per
   city** (the cost-effective choice), joins City+State → lat/lng, and stores the
   result in a `Station` table. Stations whose city can't be matched are dropped (the
   count is logged).

At **request time** there is no CSV parsing and no geocoding of stations:

1. Resolve `start`/`finish` to coordinates — **local `City` table first** (0 API
   calls); ORS geocoding only if the input isn't a recognizable `City, ST`.
2. **One** ORS `directions` call → route polyline + total distance.
3. Pure-Python: project stored stations onto the route (bbox prefilter + nearest-
   vertex), keep those within a corridor, order them by distance along the route.
4. Run the **gas-station-problem greedy** to pick cost-optimal fill-ups.
5. Return JSON.

### The fuel algorithm

This is the classic *gas station problem*: minimize total fuel cost given a finite
tank — not merely "stop at the cheapest station." Greedy rule at each station:

> If a **strictly cheaper** station is reachable within the remaining range, buy just
> enough to coast there. Otherwise, if the destination is reachable, buy just enough
> to finish; else fill the tank and drive to the farthest reachable station.

A pre-trip fill is attributed to the station nearest the start (shown at mile 0). The
total fuel purchased equals `distance / 10` gallons; cost is the sum of
`gallons × price` across the chosen stops. See
[`routing/services/fuel.py`](routing/services/fuel.py) and its hand-computed tests in
[`routing/tests/test_fuel.py`](routing/tests/test_fuel.py).

---

## API

### `GET /api/route`

Query parameters:

| param    | example          | notes |
|----------|------------------|-------|
| `start`  | `New York, NY`   | `City, ST` resolves with no API call; other text falls back to ORS geocoding |
| `finish` | `Los Angeles, CA`| same |

Example:

```
GET /api/route?start=New York, NY&finish=Los Angeles, CA
```

Response (shape):

```json
{
  "start": "New York, NY",
  "finish": "Los Angeles, CA",
  "route": { "type": "LineString", "coordinates": [[-74.0, 40.7], ...] },
  "total_distance_miles": 2789.5,
  "total_gallons": 278.95,
  "total_fuel_cost": 812.34,
  "fuel_stops": [
    {
      "name": "PILOT #1243", "city": "Gila Bend", "state": "AZ",
      "lat": 32.9, "lng": -112.7,
      "price_per_gallon": 3.899,
      "miles_from_start": 0.0,
      "gallons": 50.0,
      "cost": 194.95
    }
  ]
}
```

Status codes:

| code | when |
|------|------|
| 200  | success |
| 400  | missing `start`/`finish`, or a location can't be resolved |
| 422  | route can't be completed within range (a gap > 500 mi has no station) |
| 502  | the routing provider failed |

---

## Setup

Requires Python 3.11+ (built and tested on 3.12) and a free OpenRouteService key.

```bash
# 1. Create a virtualenv and install dependencies
python -m venv .venv
# Windows:  .\.venv\Scripts\Activate.ps1
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure the API key
cp .env.example .env          # then edit .env and paste your ORS key
```

Get a free key at https://openrouteservice.org/dev/#/signup and put it in `.env` as
`ORS_API_KEY`.

```bash
# 3. Build the database (migrations + one-time data load)
#    data/uscities.csv (city coordinates) is already bundled, so no download needed.
python manage.py migrate
python manage.py load_cities
python manage.py load_stations     # prints how many stations resolved (~3,765/3,893)

# 5. Run
python manage.py runserver
```

Then:

```bash
curl "http://127.0.0.1:8000/api/route?start=New York, NY&finish=Los Angeles, CA"
```

> On Windows, if `python` isn't on PATH, call the venv interpreter directly, e.g.
> `.\.venv\Scripts\python.exe manage.py runserver`.

---

## Tests

```bash
pytest
```

All tests run **offline** — the OpenRouteService client is mocked — so no API key or
dataset is needed to run them. Coverage includes the fuel algorithm (hand-computed
optima and infeasibility cases), corridor geometry, the data loaders, the location
resolver, and an end-to-end view test.

---

## Assumptions & trade-offs

- **City-centroid coordinates** are used for stations (the data supports nothing
  finer without a paid geocoder). This is accurate enough to decide corridor
  membership and pick the cheapest station in each 500-mile window; a stop may sit up
  to ~10 mi from its true exit. ~3,765 of 3,893 unique station cities resolve.
- **Cost-optimal can mean many small stops.** The planner minimizes dollars, so it
  will make small top-ups at successively cheaper stations rather than fewer larger
  fills. This is intentional ("optimal = cost effective"); minimizing the *number* of
  stops would be a different objective.
- **Cheapest station per city** is kept; multiple truck stops in one city collapse to
  the lowest price (the cost-effective choice).
- The vehicle **starts with a full tank**, attributed to the station nearest the
  start; `10 mpg` and `500 mi` range are fixed constants.
- Stations in cities absent from the US-cities dataset are excluded (count logged at
  load time).

## Tech stack

Django 5.2, Django REST Framework, SQLite, `requests`. OpenRouteService for routing
and geocoding fallback.

## Attribution

City coordinates derived from [GeoNames](https://www.geonames.org/) (CC BY 4.0).
The bundled `data/uscities.csv` is generated by
[`scripts/build_uscities.py`](scripts/build_uscities.py); re-run it to refresh.
