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
LANDMARKS_FILE = DATA_DIR / "landmarks.json"   # hand-set shapes OSM cannot express
PLACES_FILE = DATA_DIR / "places.json"
ENTRANCES_FILE = DATA_DIR / "entrances.geojson"
FIXES_FILE = DATA_DIR / "map_fixes.json"         # hand-checked repairs of the OSM path network

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


def _tag(row, key):
    value = first(row.get(key))
    return None if value is None or (isinstance(value, float) and math.isnan(value)) else value


SHAPES = {"dome": "dome", "round": "dome", "onion": "dome", "pyramidal": "pyramidal", "hipped": "pyramidal"}


def _buildings_3d(features: gpd.GeoDataFrame, landmarks: dict) -> gpd.GeoDataFrame:
    """One row per 3D piece: a whole building, or one building:part of it.

    Follows OSM's Simple 3D Buildings scheme: when a building outline has parts
    inside it, only the parts are drawn (each with its own height, min_height
    and roof), and the outline gives them its name and type.
    """
    features = features[features.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    features["geometry"] = features.geometry.make_valid()
    features = features[features.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    is_part = features["building:part"].notna() if "building:part" in features else pd.Series(False, features.index)
    parts, outlines = features[is_part], features[~is_part]

    owner = {}  # part index -> outline index
    if len(parts):
        points = gpd.GeoDataFrame(geometry=parts.geometry.representative_point().values, crs=features.crs)
        shapes = gpd.GeoDataFrame(geometry=outlines.geometry.values, crs=features.crs)
        hits = gpd.sjoin(points, shapes, predicate="within")
        owner = {parts.index[i]: outlines.index[j] for i, j in zip(hits.index, hits["index_right"])}
        outlines = outlines.drop(index=set(owner.values()))

    rows = []
    for index, row in pd.concat([outlines, parts]).iterrows():
        parent = features.loc[owner[index]] if index in owner else row
        kind = str(_tag(parent, "building") or "yes")
        levels = _number(_tag(row, "building:levels"))
        roof_levels = _number(_tag(row, "roof:levels")) or 0.0
        height = _number(_tag(row, "height"))
        if height:
            source = "height tag"
        elif levels:
            height = (levels + roof_levels) * config.METERS_PER_LEVEL
            source = f"{levels:g} levels x {config.METERS_PER_LEVEL} m"
        else:
            height = config.DEFAULT_HEIGHT_BY_TYPE.get(kind, config.DEFAULT_BUILDING_HEIGHT)
            source = f"default {height:g} m for '{kind}'"

        min_height = _number(_tag(row, "min_height"))
        if min_height is None and _number(_tag(row, "building:min_level")):
            min_height = _number(_tag(row, "building:min_level")) * config.METERS_PER_LEVEL
        if min_height is None:
            min_height = height - 1.0 if kind == "roof" else 0.0   # a canopy floats above the ground
        min_height = max(0.0, min(min_height, height - 0.5))

        osm_id = f"{index[0]}/{index[1]}"
        landmark = landmarks.get(osm_id, {})
        shape = landmark.get("shape") or SHAPES.get(str(_tag(row, "roof:shape") or "flat"), "flat")
        roof_height = _number(_tag(row, "roof:height"))
        if roof_height is None and roof_levels:
            roof_height = roof_levels * config.METERS_PER_LEVEL
        body = height - min_height
        if shape == "pyramidal" and roof_height is None:
            roof_height = min(3.0, 0.4 * body)
        rows.append({
            "osm_id": osm_id,
            "name": landmark.get("name") or _tag(row, "name") or _tag(parent, "name"),
            "kind": kind,
            "height": round(float(height), 2),
            "min_height": round(float(min_height), 2),
            "shape": shape,
            "roof_height": None if roof_height is None else round(float(min(roof_height, body)), 2),
            "colour": _tag(row, "building:colour") or _tag(parent, "building:colour"),
            "roof_colour": _tag(row, "roof:colour") or _tag(parent, "roof:colour"),
            "material": _tag(row, "building:material") or _tag(parent, "building:material"),
            "height_source": source + (" (shape set by hand: see data/landmarks.json)" if landmark else ""),
            "geometry": row.geometry,
        })
    out = gpd.GeoDataFrame(rows, geometry="geometry", crs=features.crs)

    # A dome without roof:height gets half its footprint width, measured in metres.
    metric = out.to_crs(config.PROJECTED_CRS)
    for i in out.index[(out["shape"] == "dome") & out["roof_height"].isna()]:
        radius = math.sqrt(metric.geometry[i].area / math.pi)
        out.loc[i, "roof_height"] = round(min(radius, out.loc[i, "height"] - out.loc[i, "min_height"]), 2)
    return out


def _named_places(features: gpd.GeoDataFrame) -> list:
    """Named buildings and parks, for the search box of the web app."""
    places, seen = [], set()
    for _, row in features.iterrows():
        name = _tag(row, "name")
        if not name or name in seen:
            continue
        seen.add(name)
        point = row.geometry.representative_point()
        places.append({"name": str(name), "lat": round(point.y, 6), "lon": round(point.x, 6),
                       "type": str(_tag(row, "leisure") or _tag(row, "building") or _tag(row, "amenity") or "")})
    return places


def download_area() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    lat, lon = config.AREA_CENTER
    reach = config.AREA_RADIUS_M + 150   # buildings and trees just outside still cast shade inside
    print("Downloading the walk network from OpenStreetMap...")
    graph = _from_overpass(lambda: ox.graph_from_point(
        (lat, lon), dist=config.AREA_RADIUS_M, network_type="walk", simplify=True))
    ox.save_graphml(graph, GRAPH_FILE)

    print("Downloading buildings and building parts...")
    features = _from_overpass(lambda: ox.features_from_point(
        (lat, lon), tags={"building": True, "building:part": True}, dist=reach))
    landmarks = json.loads(LANDMARKS_FILE.read_text()) if LANDMARKS_FILE.exists() else {}
    buildings = _buildings_3d(features, landmarks)
    buildings.to_file(BUILDINGS_FILE, driver="GeoJSON")

    print("Downloading trees, woods and parks...")
    green = _from_overpass(lambda: ox.features_from_point(
        (lat, lon), tags={"natural": ["tree", "tree_row", "wood"], "landuse": ["forest"],
                          "leisure": ["park", "garden"]}, dist=reach))
    natural = green["natural"] if "natural" in green else pd.Series(None, green.index)
    landuse = green["landuse"] if "landuse" in green else pd.Series(None, green.index)
    is_tree = natural.notna() | (landuse == "forest")
    trees = gpd.GeoDataFrame({"kind": [first(n) if isinstance(n, str) else "wood"
                                       for n in natural[is_tree]]},
                             geometry=green.geometry[is_tree].values, crs=green.crs)
    trees.to_file(TREES_FILE, driver="GeoJSON")

    print("Downloading building entrances...")
    doors = _from_overpass(lambda: ox.features_from_point((lat, lon), tags={"entrance": True}, dist=reach))
    doors = doors[doors.geometry.geom_type == "Point"]
    gpd.GeoDataFrame({
        "osm_id": [f"{i[0]}/{i[1]}" for i in doors.index],
        "entrance": [first(v) for v in doors["entrance"]],
        "ref": [first(v) if isinstance(first(v), str) else None for v in doors.get("ref", pd.Series(None, doors.index))],
        "wheelchair": [first(v) if isinstance(first(v), str) else None
                       for v in doors.get("wheelchair", pd.Series(None, doors.index))],
    }, geometry=doors.geometry.values, crs=doors.crs).to_file(ENTRANCES_FILE, driver="GeoJSON")

    places = _named_places(pd.concat([features[features.get("building:part").isna()]
                                      if "building:part" in features else features,
                                      green[green.get("leisure").notna()] if "leisure" in green else green.iloc[:0]]))
    PLACES_FILE.write_text(json.dumps(places, ensure_ascii=False, indent=0))
    print(f"Saved {graph.number_of_nodes()} nodes, {len(buildings)} 3D pieces, {len(trees)} trees, {len(places)} places")


def load_fixes() -> dict:
    return json.loads(FIXES_FILE.read_text()) if FIXES_FILE.exists() else {}


def load_entrances(fixes=None) -> gpd.GeoDataFrame:
    """Building entrances from OSM, plus the ones data/map_fixes.json adds where OSM has none."""
    columns = ["osm_id", "entrance", "ref", "wheelchair", "name", "building"]
    entrances = gpd.read_file(ENTRANCES_FILE) if ENTRANCES_FILE.exists() else \
        gpd.GeoDataFrame(columns=columns, geometry=[], crs="EPSG:4326")
    added = (fixes if fixes is not None else load_fixes()).get("entrances", [])
    if added:
        extra = gpd.GeoDataFrame(
            [{"osm_id": None, "entrance": e.get("entrance", "main"), "ref": None,
              "wheelchair": e.get("wheelchair"), "name": e["name"],
              "building": ",".join(e.get("building", []))} for e in added],
            geometry=gpd.points_from_xy([e["lon"] for e in added], [e["lat"] for e in added]), crs="EPSG:4326")
        entrances = pd.concat([entrances, extra], ignore_index=True)
    for column in columns:
        if column not in entrances:
            entrances[column] = None
    return entrances


def load_area(refresh: bool = False):
    """Return (walk graph, buildings, trees, barriers) in lat/lon (EPSG:4326)."""
    if refresh or not (GRAPH_FILE.exists() and BUILDINGS_FILE.exists() and TREES_FILE.exists()):
        download_area()
    graph = ox.load_graphml(GRAPH_FILE)
    buildings = gpd.read_file(BUILDINGS_FILE)
    trees = gpd.read_file(TREES_FILE)
    barriers = json.loads(BARRIERS_FILE.read_text()) if BARRIERS_FILE.exists() else []
    return graph, buildings, trees, barriers
