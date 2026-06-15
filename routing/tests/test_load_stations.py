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
