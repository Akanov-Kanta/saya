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


def test_buildings_carry_3d_shape_for_the_browser():
    features = client.get("/api/buildings").json()["features"]
    sphere = [f["properties"] for f in features if f["properties"]["shape"] == "sphere"]
    assert len(sphere) == 1 and sphere[0]["height"] == 100       # the EXPO sphere, Nur Alem
    assert 35 < sphere[0]["r"] < 45 and sphere[0]["zc"] == sphere[0]["height"] - sphere[0]["r"]
    assert any(f["properties"]["min_height"] > 0 for f in features)   # parts that stand on columns
    assert all(f["properties"]["height"] > f["properties"]["min_height"] for f in features)


def test_trees_and_search_places():
    trees = client.get("/api/trees").json()
    assert trees["crown_radius_m"] == config.TREE_CROWN_RADIUS_M and len(trees["points"]) > 100
    names = [p["name"] for p in client.get("/api/meta").json()["search"]]
    assert names[:2] == ["Astana IT University", "Mega Silk Way"] and len(names) > 20
