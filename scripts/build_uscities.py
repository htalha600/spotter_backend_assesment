"""Build data/uscities.csv from the public-domain GeoNames US dataset.

The fuel-station geocoder (`load_cities` / `load_stations`) needs a table of US
city coordinates. We derive it from GeoNames (https://www.geonames.org/,
CC BY 4.0), which is directly downloadable and has excellent small-town coverage
(important because many truck-stop towns are tiny).

Output columns match what `load_cities` expects: city, state_id, lat, lng.
One row per (city, state), keeping the most populous when a name repeats.

Usage (from the project root, with the venv active):
    python scripts/build_uscities.py

Re-run only when you want to refresh the dataset; the generated
data/uscities.csv is committed so the app runs out of the box.
"""
import csv
import io
import os
import sys
import urllib.request
import zipfile

GEONAMES_URL = "https://download.geonames.org/export/dump/US.zip"
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "uscities.csv")


def build():
    print(f"Downloading {GEONAMES_URL} ...")
    with urllib.request.urlopen(GEONAMES_URL) as resp:
        raw = resp.read()
    print(f"Downloaded {len(raw) // (1024 * 1024)} MB; extracting US.txt ...")
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        text = zf.read("US.txt").decode("utf-8")

    best = {}  # (NAME, ST) -> (population, name, state, lat, lng)
    for row in csv.reader(io.StringIO(text), delimiter="\t"):
        if len(row) < 15:
            continue
        name, lat, lng, fclass, ccode, admin1, pop = (
            row[1], row[4], row[5], row[6], row[8], row[10], row[14]
        )
        # feature class 'P' = populated place; admin1 is the 2-letter state for US
        if fclass != "P" or ccode != "US" or not (len(admin1) == 2 and admin1.isalpha()):
            continue
        try:
            population = int(pop) if pop else 0
            latf, lngf = float(lat), float(lng)
        except ValueError:
            continue
        key = (name.upper(), admin1)
        if key not in best or population > best[key][0]:
            best[key] = (population, name, admin1, latf, lngf)

    out_path = os.path.abspath(OUT_PATH)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["city", "state_id", "lat", "lng"])
        for _population, name, state, latf, lngf in best.values():
            writer.writerow([name, state, latf, lngf])
    print(f"Wrote {len(best)} unique city/state rows to {out_path}")


if __name__ == "__main__":
    try:
        build()
    except Exception as exc:  # pragma: no cover - operational script
        print(f"Failed: {exc}", file=sys.stderr)
        sys.exit(1)
