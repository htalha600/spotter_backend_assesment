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
