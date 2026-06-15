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

        best = {}        # (city_upper, state) -> chosen row (cheapest), one per location
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
