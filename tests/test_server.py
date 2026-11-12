"""The web API runs the same pipeline as the CLI. feels_like is passed so no test needs the internet."""

from fastapi.testclient import TestClient

import config
from server import app

client = TestClient(app)
AITU = list(config.PLACES["aitu"][1:])
MEGA = list(config.PLACES["megasilkway"][1:])


def test_meta_lists_places_profiles_and_barriers():
    meta = client.get("/api/meta").json()
    assert meta["profiles"] == {"disabled": "Person with disabilities", "standard": "Person without disabilities"}
    assert meta["defaults"]["start"] == "qairu" and "nu" in meta["places"]
    assert len(meta["barriers"]) >= 5


def test_shadows_move_with_the_time_of_day():
    morning = client.get("/api/shade", params={"date": "2026-07-15", "time": "07:00"}).json()
    evening = client.get("/api/shade", params={"date": "2026-07-15", "time": "19:00"}).json()
    assert morning["sun"]["compass"] in {"NE", "E"} and morning["sun"]["shadow_compass"] in {"SW", "W"}
    assert evening["sun"]["compass"] == "W" and evening["sun"]["shadow_compass"] == "E"
    assert evening["shade"]["features"]


def test_night_has_no_sun():
    night = client.get("/api/shade", params={"date": "2026-07-15", "time": "23:30"}).json()
    assert night["sun"]["is_night"]


def test_route_for_points_picked_by_the_user_matches_the_cli_pipeline():
    from datetime import datetime
    import planner
    from server import area
    body = {"start": AITU, "end": MEGA, "date": "2026-07-15", "time": "16:00",
            "profile": "disabled", "feels_like": 31.0}
    trip = client.post("/api/route", json=body).json()
    cli = planner.plan_trip(area, AITU, MEGA, datetime(2026, 7, 15, 16, 0, tzinfo=config.ASTANA_TZ), "disabled", 31.0)
    assert trip["decision"] == cli["decision"]
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
    assert names[0].startswith("QAIRU") and "Nazarbayev University" in names and len(names) > 20


QAIRU = list(config.PLACES["qairu"][1:])
NU = list(config.PLACES["nu"][1:])


def trip(start, end, profile, time="16:00"):
    body = {"start": start, "end": end, "date": "2026-07-15", "time": time, "profile": profile, "feels_like": 31.0}
    return client.post("/api/route", json=body).json()


def test_nazarbayev_university_is_reached_by_its_main_entrance():
    # OSM breaks the crossing of Qabanbay Batyr Avenue into pieces; data/map_fixes.json joins them.
    # Without that fix this walk was 3.8 km around the campus.
    result = trip(QAIRU, NU, "standard")
    assert result["end_point"]["entrance"] == "Nazarbayev University, main entrance"
    assert result["routes"]["Shortest"]["stats"]["length_m"] < 1600


def test_mega_silk_way_uses_the_entrance_facing_the_start():
    result = trip(QAIRU, MEGA, "standard")
    assert result["end_point"]["entrance"] == "main entrance E"     # the east side, towards QAIRU


def test_person_with_disabilities_goes_around_barriers():
    disabled, standard = trip(QAIRU, MEGA, "disabled"), trip(QAIRU, MEGA, "standard")
    names = [b["name"] for b in disabled["direct"]["barriers"]]
    assert "Broken kerb ramp at the crossing to Mega Silk Way" in names           # on the direct way
    assert disabled["routes"]["Shortest"]["barriers"] == []                        # not on theirs
    assert disabled["routes"]["Shortest"]["coords"] != standard["routes"]["Shortest"]["coords"]
    assert disabled["direct"]["coords"] == standard["routes"]["Shortest"]["coords"]
    assert standard["direct"] is None


def test_without_disabilities_both_options_come_back():
    result = trip(QAIRU, NU, "standard", time="18:00")
    shortest, shaded = result["routes"]["Shortest"]["stats"], result["routes"]["Shaded"]["stats"]
    assert not result["same_route"] and shaded["sun_share"] < shortest["sun_share"]
    assert result["decision"] in {"Shortest", "Shaded"}                           # SAYA's suggestion
