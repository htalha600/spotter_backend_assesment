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
