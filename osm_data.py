"""Get the map data: walk network, buildings and trees from OpenStreetMap.

The first run downloads them and saves plain files in data/. Every later run
(including the live demo) reads those files and needs no internet.
"""

import ast
import json
import math
import re
from pathlib import Path

import geopandas as gpd
import osmnx as ox
import pandas as pd

import config

DATA_DIR = Path(__file__).parent / "data"
GRAPH_FILE = DATA_DIR / "walk_graph.graphml"
BUILDINGS_FILE = DATA_DIR / "buildings.geojson"
TREES_FILE = DATA_DIR / "trees.geojson"
BARRIERS_FILE = DATA_DIR / "barriers.json"

# The public Overpass server is often busy, so try mirrors in turn.
OVERPASS_SERVERS = [
    "https://overpass-api.de/api",
    "https://overpass.kumi.systems/api",
    "https://overpass.private.coffee/api",
]

ox.settings.use_cache = True
ox.settings.cache_folder = DATA_DIR / "osm_cache"
ox.settings.overpass_rate_limit = False
ox.settings.requests_timeout = 120
ox.settings.useful_tags_way = list(ox.settings.useful_tags_way) + ["surface", "footway", "crossing"]
ox.settings.useful_tags_node = list(ox.settings.useful_tags_node) + ["crossing"]


def first(value):
    """OSM tags can come back as a list, a stringified list, NaN or a plain value."""
    if isinstance(value, str) and value.startswith("["):
        try:
            value = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return value
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _number(value):
    match = re.search(r"\d+(\.\d+)?", str(value)) if value is not None else None
    return float(match.group()) if match else None


def _from_overpass(fetch):
    last_error = None
    for url in OVERPASS_SERVERS:
        ox.settings.overpass_url = url
        try:
            return fetch()
        except Exception as error:  # network errors, 429/502 from a busy server
            print(f"  {url} failed ({type(error).__name__}), trying the next server")
            last_error = error
    raise RuntimeError("Every Overpass server failed. Check the internet connection and retry.") from last_error


def _building_heights(buildings: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    heights, sources = [], []
    for _, row in buildings.iterrows():
        height = _number(first(row.get("height")))
        levels = _number(first(row.get("building:levels")))
        if height:
            heights.append(height); sources.append("height tag")
        elif levels:
            heights.append(levels * config.METERS_PER_LEVEL); sources.append("levels x 3.2 m")
        else:
            heights.append(config.DEFAULT_BUILDING_HEIGHT); sources.append("default 9 m")
    out = gpd.GeoDataFrame(
        {"name": [first(n) for n in buildings.get("name", pd.Series([None] * len(buildings)))],
         "height": heights, "height_source": sources},
        geometry=buildings.geometry.values, crs=buildings.crs,
    )
    return out


def download_area() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    lat, lon = config.AREA_CENTER
    print("Downloading the walk network from OpenStreetMap...")
    graph = _from_overpass(lambda: ox.graph_from_point(
        (lat, lon), dist=config.AREA_RADIUS_M, network_type="walk", simplify=True))
    ox.save_graphml(graph, GRAPH_FILE)

    # Buildings and trees a bit outside the network still cast shade onto it.
    print("Downloading buildings...")
    buildings = _from_overpass(lambda: ox.features_from_point(
        (lat, lon), tags={"building": True}, dist=config.AREA_RADIUS_M + 100))
    buildings = buildings[buildings.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    _building_heights(buildings).to_file(BUILDINGS_FILE, driver="GeoJSON")

    print("Downloading trees...")
    trees = _from_overpass(lambda: ox.features_from_point(
        (lat, lon), tags={"natural": ["tree", "tree_row", "wood"]}, dist=config.AREA_RADIUS_M + 100))
    trees = gpd.GeoDataFrame({"kind": [first(k) for k in trees["natural"]]},
                             geometry=trees.geometry.values, crs=trees.crs)
    trees.to_file(TREES_FILE, driver="GeoJSON")


def load_area(refresh: bool = False):
    """Return (walk graph, buildings, trees, barriers) in lat/lon (EPSG:4326)."""
    if refresh or not (GRAPH_FILE.exists() and BUILDINGS_FILE.exists() and TREES_FILE.exists()):
        download_area()
    graph = ox.load_graphml(GRAPH_FILE)
    buildings = gpd.read_file(BUILDINGS_FILE)
    trees = gpd.read_file(TREES_FILE)
    barriers = json.loads(BARRIERS_FILE.read_text()) if BARRIERS_FILE.exists() else []
    return graph, buildings, trees, barriers
