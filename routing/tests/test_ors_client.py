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
