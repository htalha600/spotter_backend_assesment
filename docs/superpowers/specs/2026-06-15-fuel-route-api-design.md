# Fuel Route API — Design Spec

**Date:** 2026-06-15
**Goal:** A Django REST API that, given a US start and finish location, returns the driving route plus the cost-optimal sequence of fuel stops (500-mile tank, 10 mpg) and the total fuel cost — using minimal external API calls.

## Requirements (from assignment)

- Inputs: start and finish location, both within the USA.
- Output: the route geometry + optimal fuel-up locations along it ("optimal" = cost-effective based on fuel prices).
- Vehicle max range 500 miles → multiple fuel-ups possible; display all of them.
- Return total money spent on fuel, assuming 10 miles per gallon.
- Use the provided fuel-prices CSV for prices.
- Use a free map/routing API (chosen: OpenRouteService).
- Latest stable Django.
- Fast responses.
- Minimal calls to the routing API: 1 ideal, 2–3 acceptable.

## Data reality (from `fuel-prices-for-be-assessment.csv`)

- Columns: `OPIS Truckstop ID, Truckstop Name, Address, City, State, Rack ID, Retail Price`.
- 8,151 rows; 6,738 unique truck-stop IDs (duplicate rows exist); 3,893 unique City+State pairs; 57 states/territories.
- Price range $2.69–$6.40, avg $3.50.
- **No coordinates.** Addresses are highway-exit descriptions (e.g. `"I-44, EXIT 283 & US-69"`), not clean street addresses. Only City + State are reliably geocodable.

## Decisions

- **Output:** pure JSON API (no rendered map / HTML). Easiest backend demo via Postman.
- **Routing/geocoding API:** OpenRouteService (free key; one directions call returns geometry + distance; geocoding available as fallback).
- **Station geocoding:** offline join of the fuel CSV's City+State against a bundled free **SimpleMaps US-cities** dataset (~31k cities, includes small towns). **Zero geocoding API calls at request time.**

## Architecture

### Part 1 — Offline build (Django management command `load_stations`)
Not in the request path. Run once at setup / when data changes.

```
read fuel CSV ─┐
               ├─ join on (City, State) → attach lat/lng → Station table (SQLite)
US-cities.csv ─┘
- dedupe 8,151 rows → unique stations; keep cheapest price per location
- drop + log stations whose city cannot be resolved (report coverage %)
```
Result: stations pre-indexed in DB with coordinates; no per-request CSV parsing or geocoding.

### Part 2 — Request path: `GET /api/route?start=<City, ST>&finish=<City, ST>`
```
1. Resolve start & finish → coords
     - try local cities DB first (0 calls)
     - ORS geocode only if not found locally
2. ONE ORS /v2/directions call → route polyline + total distance   ← only guaranteed external call
3. Pure-Python fuel logic (no API):
     a. bbox prefilter stations to the route corridor (+ buffer)
     b. project each candidate onto the polyline → (miles-along-route, detour-miles)
     c. keep stations within ~N miles of the path; order by miles-along-route
     d. optimal fuel-stop selection (see below)
4. Serialize JSON response
```
**External calls: 1 common case, ≤3 worst case.**

## Fuel-stop selection — the "gas station problem"

Minimize total fuel cost given a 500-mile tank (not merely "fill at the cheapest stop"). Provably-optimal greedy:

> At each stop, look ahead at all stations reachable within remaining range. If a **cheaper** station is reachable, buy just enough fuel to coast there. If none is cheaper, **fill the tank** here and advance to the cheapest reachable station.

- O(n) with a monotonic deque over stations ordered along the route.
- Range in miles = tank distance (500). gallons = leg_miles / 10 mpg. cost = Σ (gallons_bought × stop_price).
- Assumes tank starts effectively at start point; first fill chosen by the same rule.

## Output shape
```json
{
  "route": { "type": "LineString", "coordinates": [[lng, lat], ...] },
  "total_distance_miles": 1342.5,
  "total_gallons": 134.25,
  "total_fuel_cost": 421.88,
  "fuel_stops": [
    {
      "name": "PILOT #1243", "city": "Gila Bend", "state": "AZ",
      "price_per_gallon": 3.899, "gallons": 50.0, "cost": 194.95,
      "lat": 32.9, "lng": -112.7, "miles_from_start": 480
    }
  ]
}
```

## Error handling
- Unresolvable start/finish → 400 with a clear message.
- Route longer than range with no reachable station in some 500-mi window → 422 with the gap described.
- ORS failure/timeout → 502.
- Route shorter than 500 mi → empty `fuel_stops`, cost 0.

## Testing
- Unit tests for the fuel algorithm: handcrafted station sets with known optimal costs; edge cases (route < 500mi, single stop forced, no reachable station, ties).
- Unit tests for polyline projection / corridor filtering on simple geometries.
- Integration test of the endpoint with ORS **mocked** (fast, offline, deterministic).

## Documented assumptions / trade-offs
- City-centroid coordinates are coarse (~up to ~10 mi off the real exit). Acceptable for corridor membership + cheapest-in-window selection; the data supports nothing finer without a paid geocoder.
- Stations in cities not present in the US-cities dataset are excluded (coverage logged at build time).
- 10 mpg and 500-mi range are fixed constants per the assignment.

## Tech stack
- Django 5.2 (latest stable), Django REST Framework, SQLite, `requests` for ORS.
- ORS API key via environment variable.
