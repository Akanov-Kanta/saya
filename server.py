"""SAYA web app: a 3D map where you pick the time of day and the start/end points.

    python server.py          # then open http://127.0.0.1:8765

The browser only draws. All the AI (shadows, A*, Bayes, MDP) runs here in
Python through the same planner.plan_trip() the CLI uses.
"""

import json
import math
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
import mdp
import osm_data
import planner
from sun import compass

WEB_DIR = Path(__file__).parent / "web"
PORT = 8765

app = FastAPI(title="SAYA")
area = planner.Area(*osm_data.load_area())
buildings_geojson = area.buildings[["name", "height", "height_source", "geometry"]].to_json()


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
        "profiles": {key: profile["label"] for key, profile in config.PROFILES.items()},
        "defaults": {"date": config.DEFAULT_DATE, "time": config.DEFAULT_TIME, "profile": "wheelchair",
                     "start": config.DEFAULT_START, "end": config.DEFAULT_END},
        "barriers": [{k: r[k] for k in ("id", "type", "name", "lat", "lon")} for r in area.barriers],
    }


@app.get("/api/buildings")
def buildings():
    return Response(buildings_geojson, media_type="application/geo+json")


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
    profile: str = "wheelchair"
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
    routes = {}
    for action, route_data in trip["routes"].items():
        stats = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in route_data["stats"].items()}
        coords = [[lon, lat] for lat, lon in area.route_latlon(route_data["result"].edges)]
        routes[action] = {"stats": stats, "coords": coords}
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
        "start_node": trip["start_node"], "goal_node": trip["goal_node"],
        "routes": routes,
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
