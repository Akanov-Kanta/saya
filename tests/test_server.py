"""The web API runs the same pipeline as the CLI. feels_like is passed so no test needs the internet."""

from fastapi.testclient import TestClient

import config
from server import app

client = TestClient(app)
AITU = list(config.PLACES["aitu"][1:])
MEGA = list(config.PLACES["megasilkway"][1:])


def test_meta_lists_places_profiles_and_barriers():
    meta = client.get("/api/meta").json()
    assert set(meta["profiles"]) == {"wheelchair", "elderly", "standard"}
    assert "aitu" in meta["places"]
    assert len(meta["barriers"]) == 2


def test_shadows_move_with_the_time_of_day():
    morning = client.get("/api/shade", params={"date": "2026-07-15", "time": "07:00"}).json()
    evening = client.get("/api/shade", params={"date": "2026-07-15", "time": "19:00"}).json()
    assert morning["sun"]["compass"] in {"NE", "E"} and morning["sun"]["shadow_compass"] in {"SW", "W"}
    assert evening["sun"]["compass"] == "W" and evening["sun"]["shadow_compass"] == "E"
    assert evening["shade"]["features"]


def test_night_has_no_sun():
    night = client.get("/api/shade", params={"date": "2026-07-15", "time": "23:30"}).json()
    assert night["sun"]["is_night"]


def test_route_for_points_picked_by_the_user():
    body = {"start": AITU, "end": MEGA, "date": "2026-07-15", "time": "16:00",
            "profile": "wheelchair", "feels_like": 31.0}
    trip = client.post("/api/route", json=body).json()
    assert trip["decision"] == "Shaded"
    assert trip["bayes"]["posterior"] == 0.75
    assert len(trip["routes"]["Shaded"]["coords"]) > 10
    assert len(trip["mdp"]["rows"]) == 4


def test_point_outside_the_map_is_rejected():
    body = {"start": AITU, "end": [51.12, 71.46], "feels_like": 25}
    response = client.post("/api/route", json=body)
    assert response.status_code == 400
    assert "inside the mapped area" in response.json()["detail"]
