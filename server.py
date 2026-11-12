"""SAYA web app: a 3D map where you pick the time of day and the start/end points.

    python server.py          # then open http://127.0.0.1:8765

The browser only draws. All the AI (shadows, A*, Bayes, MDP) runs here in
Python through the same planner.plan_trip() the CLI uses.
"""

import json
import math
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

import geopandas as gpd
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
import mdp
import osm_data
import planner
import shade
from sun import compass

WEB_DIR = Path(__file__).parent / "web"
PORT = 8765

area = planner.Area(*osm_data.load_area())


def buildings_for_web() -> str:
    """Every 3D piece with what the browser needs to draw it exactly like the shadow model sees it."""
    b = area.buildings.copy()
    metric = area.buildings_m
    centres = gpd.GeoSeries(metric.geometry.centroid, crs=config.PROJECTED_CRS).to_crs("EPSG:4326")
    b["cx"], b["cy"] = centres.x.round(7), centres.y.round(7)
    for column in ("r", "zc", "neck_r", "neck_top"):
        b[column] = None
    for i in b.index[b["shape"] == "sphere"]:
        params = shade.sphere_params(metric.geometry[i], b.loc[i, "min_height"], b.loc[i, "height"])
        for column in ("r", "zc", "neck_r", "neck_top"):
            b.loc[i, column] = round(params[column], 2)
    b["geometry"] = b.geometry.simplify(0.000003)   # about 0.3 m, keeps curved walls smooth
    return b.to_json(drop_id=True)


def places_in_area() -> list:
    """The named places of config.py first, then named OSM buildings and parks inside the area."""
    centre = planner.to_metres(*config.AREA_CENTER)
    places = [{"name": name, "lat": lat, "lon": lon, "type": "landmark"} for name, lat, lon in config.PLACES.values()]
    if osm_data.PLACES_FILE.exists():
        names = {p["name"] for p in places}
        for place in json.loads(osm_data.PLACES_FILE.read_text()):
            if place["name"] not in names and planner.to_metres(place["lat"], place["lon"]).distance(centre) < config.AREA_RADIUS_M:
                places.append(place)
                names.add(place["name"])
    return places


def tree_points(spacing_row=7.0, spacing_wood=9.0) -> list:
    """Where to draw 3D trees: each tree, a tree every 7 m along tree rows, a 9 m grid inside woods."""
    import numpy as np
    import shapely
    xs, ys = [], []
    for geometry, kind in zip(area.trees_m.geometry, area.trees_m["kind"]):
        if kind == "wood" and geometry.geom_type in ("Polygon", "MultiPolygon"):
            x0, y0, x1, y1 = geometry.bounds
            gx, gy = np.meshgrid(np.arange(x0, x1, spacing_wood), np.arange(y0, y1, spacing_wood))
            gx = gx.ravel() + (np.sin(gy.ravel() * 0.37) * 2.5)      # a little irregular, like a real wood
            gy = gy.ravel() + (np.cos(gx * 0.29) * 2.5)
            inside = shapely.contains_xy(geometry, gx, gy)
            xs += list(gx[inside]); ys += list(gy[inside])
        elif geometry.geom_type in ("LineString", "MultiLineString"):
            for line in getattr(geometry, "geoms", [geometry]):
                for d in np.arange(0, line.length + 0.1, spacing_row):
                    point = line.interpolate(d)
                    xs.append(point.x); ys.append(point.y)
        else:
            point = geometry.representative_point()
            xs.append(point.x); ys.append(point.y)
    points = gpd.GeoSeries.from_xy(xs, ys, crs=config.PROJECTED_CRS).to_crs("EPSG:4326")
    return [[round(p.x, 7), round(p.y, 7)] for p in points]


buildings_geojson = buildings_for_web()
places = places_in_area()
trees = tree_points()


def warm_up():
    """Shade for the whole default day, every 15 minutes, nearest to the default time first."""
    start = datetime.fromisoformat(f"{config.DEFAULT_DATE}T{config.DEFAULT_TIME}").replace(tzinfo=config.ASTANA_TZ)
    day = start.replace(hour=5, minute=0)
    times = [day + timedelta(minutes=15 * i) for i in range(69)]   # 05:00 ... 22:00
    times.sort(key=lambda t: abs(t - start))
    area.warm_up(times)


@asynccontextmanager
async def lifespan(app):
    threading.Thread(target=warm_up, daemon=True).start()
    yield


app = FastAPI(title="SAYA", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def revalidate_page_files(request, call_next):
    """Browsers must re-check index.html, app.js and style.css, so an update never shows an old page."""
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


def parse_when(date: str, time: str) -> datetime:
    try:
        return datetime.fromisoformat(f"{date}T{time}").replace(tzinfo=config.ASTANA_TZ)
    except ValueError:
        raise HTTPException(400, "Use date YYYY-MM-DD and time HH:MM.")


def sun_info(altitude: float, azimuth: float) -> dict:
    up = altitude > 0
    return {
        "altitude": round(altitude, 1),
        "azimuth": round(azimuth, 1),
        "compass": compass(azimuth),
        "shadow_compass": compass(azimuth + 180),
        "shadow_of_10m": round(min(10 / math.tan(math.radians(altitude)), config.MAX_SHADOW_LENGTH), 1) if up else None,
        "is_night": not up,
    }


@app.get("/api/meta")
def meta():
    return {
        "center": config.AREA_CENTER,
        "radius_m": config.AREA_RADIUS_M,
        "places": {key: {"name": name, "lat": lat, "lon": lon} for key, (name, lat, lon) in config.PLACES.items()},
        "search": places,
        "profiles": {key: profile["label"] for key, profile in config.PROFILES.items()},
        "defaults": {"date": config.DEFAULT_DATE, "time": config.DEFAULT_TIME, "profile": "disabled",
                     "start": config.DEFAULT_START, "end": config.DEFAULT_END},
        "barriers": [{**{k: r[k] for k in ("id", "type", "name", "lat", "lon")},
                      "source": r.get("source", "simulated"), "note": r.get("note", "")}
                     for r in area.barriers],
        "map_fixes": [j for j in area.map_fixes if not j["note"].startswith("footpath ends")],
    }


@app.get("/api/buildings")
def buildings():
    return Response(buildings_geojson, media_type="application/geo+json")


@app.get("/api/trees")
def tree_positions():
    return {"crown_radius_m": config.TREE_CROWN_RADIUS_M, "points": trees}


@app.get("/api/shade")
def shade(date: str = config.DEFAULT_DATE, time: str = config.DEFAULT_TIME):
    when = parse_when(date, time)
    altitude, azimuth, _, _, shaded_share = area.shade_at(when)
    return {"sun": sun_info(altitude, azimuth), "shaded_share": round(shaded_share, 3),
            "shade": area.shade_geojson(when)}


class TripRequest(BaseModel):
    start: tuple[float, float]  # (lat, lon)
    end: tuple[float, float]
    date: str = config.DEFAULT_DATE
    time: str = config.DEFAULT_TIME
    profile: str = "disabled"
    feels_like: float | None = None


@app.post("/api/route")
def route(trip_request: TripRequest):
    if trip_request.profile not in config.PROFILES:
        raise HTTPException(400, f"Unknown profile {trip_request.profile}")
    when = parse_when(trip_request.date, trip_request.time)
    try:
        trip = planner.plan_trip(area, trip_request.start, trip_request.end, when,
                                 trip_request.profile, trip_request.feels_like)
    except ValueError as error:
        raise HTTPException(400, str(error))
    except Exception as error:  # weather API down or date too far ahead
        raise HTTPException(424, f"No weather reading for this date ({type(error).__name__}). "
                                 "Type a feels-like temperature instead.")

    network = trip["network"]

    def describe(route_data):
        stats = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in route_data["stats"].items()}
        coords = [[lon, lat] for lat, lon in area.route_latlon(route_data["result"].edges)]
        return {"stats": stats, "coords": coords, "barriers": route_data.get("barriers", [])}

    routes = {action: describe(route_data) for action, route_data in trip["routes"].items()}
    same = routes["Shortest"]["coords"] == routes["Shaded"]["coords"]
    point = lambda p: {"lat": round(p[0], 7), "lon": round(p[1], 7), "entrance": p[2]}
    mdp_rows = [
        {"state": s, "action": a,
         "p_comfortable": round(trip["transitions"][(s, a)]["Comfortable"], 3),
         "p_stressed": round(trip["transitions"][(s, a)]["HeatStressed"], 3),
         "reward": round(trip["rewards"][(s, a)], 2),
         "q": round(trip["q"][(s, a)], 2)}
        for s in mdp.STATES for a in mdp.ACTIONS
    ]
    return {
        "sun": sun_info(network.altitude, network.azimuth),
        "profile": trip["profile_key"],
        "start_node": trip["start_node"], "goal_node": trip["goal_node"],
        "start_point": point(trip["start_point"]), "end_point": point(trip["end_point"]),
        "routes": routes, "same_route": same,
        "direct": describe(trip["direct"]) if trip["direct"] else None,
        "weather": {"feels_like": trip["feels_like"], "source": trip["weather_source"]},
        "bayes": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in trip["belief"].items()},
        "mdp": {"rows": mdp_rows, "gamma": config.MDP_GAMMA, "values": trip["values"],
                "vulnerability": trip["profile"]["heat_vulnerability"]},
        "decision": trip["decision"],
    }


# The page itself (index.html, app.js, style.css)
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


if __name__ == "__main__":
    print(f"SAYA is running: open http://127.0.0.1:{PORT}")
    uvicorn.run(app, host="127.0.0.1", port=PORT)
