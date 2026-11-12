"""Glue code shared by the CLI (main.py) and the web app (server.py).

Area       loads and projects the map once, repairs known gaps in the OSM path
           network, marks barriers, finds building entrances, and computes shade
           for any date/time (cached).
plan_trip  runs the full pipeline for one trip: A* -> Bayes -> MDP.
"""

import threading
from collections import OrderedDict
from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import osmnx as ox
import shapely
from shapely.geometry import LineString, Point, mapping

import bayes
import config
import mdp
import osm_data
import search
import shade
import weather
from sun import sun_position


@dataclass
class Network:
    graph: object          # projected graph (metres); edges carry sun_fraction / barrier_type
    shade: object          # shapely geometry of all shade, projected
    altitude: float
    azimuth: float
    shaded_share: float    # share of all path length that is in shade
    barriers: list


def to_metres(lat: float, lon: float) -> Point:
    return gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(config.PROJECTED_CRS).iloc[0]


WALKWAYS = {"footway", "path", "pedestrian", "steps", "cycleway", "living_street"}
FAST_ROADS = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link"}


def repair_gaps(graph, fixes: dict):
    """Join known gaps in the OSM path network (returns a repaired copy and the list of joins).

    1. Every link listed in data/map_fixes.json, each with a note on why it is there.
    2. A footpath that dead-ends within `auto_join_m` (6 m) of another walkway is joined to it.
       Gaps that small are mapping slips, not fences.
    """
    graph = graph.copy()
    joins = []

    def link(a, b, note, crossing=None):
        ya, xa, yb, xb = graph.nodes[a]["y"], graph.nodes[a]["x"], graph.nodes[b]["y"], graph.nodes[b]["x"]
        attrs = {"highway": "footway", "geometry": LineString([(xa, ya), (xb, yb)]),
                 "length": ox.distance.great_circle(ya, xa, yb, xb), "map_fix": note}
        if crossing:
            attrs.update(footway="crossing", crossing=crossing)
        for u, v in ((a, b), (b, a)):
            graph.add_edge(u, v, **attrs)
        joins.append({"from": a, "to": b, "lat": (ya + yb) / 2, "lon": (xa + xb) / 2,
                      "length_m": round(attrs["length"], 1), "note": note})

    for fix in fixes.get("connections", []):
        if fix["from"] in graph and fix["to"] in graph:
            link(fix["from"], fix["to"], fix["note"], fix.get("crossing"))

    limit = fixes.get("auto_join_m", 0)
    if limit:
        ids = np.array(list(graph.nodes))
        points = gpd.GeoSeries.from_xy([graph.nodes[n]["x"] for n in ids], [graph.nodes[n]["y"] for n in ids],
                                       crs="EPSG:4326").to_crs(config.PROJECTED_CRS).values
        tree = shapely.STRtree(points)
        undirected = graph.to_undirected(as_view=True)

        def kinds(n):
            return {osm_data.first(d.get("highway")) for _, _, d in graph.edges(n, data=True)}

        for i, n in enumerate(ids):
            if undirected.degree(n) != 1 or not kinds(n) & WALKWAYS:
                continue
            near = [j for j in tree.query(points[i], predicate="dwithin", distance=limit)
                    if ids[j] != n and not undirected.has_edge(n, ids[j]) and kinds(ids[j]) - FAST_ROADS]
            if near:
                j = min(near, key=lambda j: points[i].distance(points[j]))
                link(n, ids[j], f"footpath ends {points[i].distance(points[j]):.1f} m from another walkway")
    return graph, joins


class Area:
    """The map, loaded once. set_time() puts the shade of a given moment on every edge."""

    CACHE_SIZE = 96  # a whole day in 15-minute steps

    def __init__(self, graph, buildings, trees, barriers, entrances=None, fixes=None):
        fixes = osm_data.load_fixes() if fixes is None else fixes
        self.graph_latlon, self.map_fixes = repair_gaps(graph, fixes)
        self.graph = ox.project_graph(self.graph_latlon, to_crs=config.PROJECTED_CRS)
        self.buildings = buildings
        self.trees = trees
        self.buildings_m = buildings.to_crs(config.PROJECTED_CRS)
        self.trees_m = trees.to_crs(config.PROJECTED_CRS)
        self.edges = ox.graph_to_gdfs(self.graph, nodes=False, fill_edge_geometry=True)
        # Measure every edge in the same projection as the A* heuristic. osmnx's lengths are
        # great-circle distances on a sphere, up to 0.3 % shorter than UTM metres at Astana's
        # latitude, and then a straight line in UTM could overestimate the remaining cost.
        # A polyline is never shorter than the straight line between its ends, so with these
        # lengths the heuristic is admissible exactly.
        self.edges["length"] = self.edges.geometry.length
        for (u, v, key), length in zip(self.edges.index, self.edges["length"]):
            self.graph.edges[u, v, key]["length"] = float(length)
        self.edge_keys = list(self.edges.index)
        self.lengths = self.edges["length"].to_numpy()
        self.node_ids = list(self.graph.nodes)
        self.node_xy = np.array([(self.graph.nodes[n]["x"], self.graph.nodes[n]["y"]) for n in self.node_ids])
        self.barriers = self._mark_barriers(barriers)
        entrances = osm_data.load_entrances(fixes) if entrances is None else entrances
        self.entrances_m = entrances.to_crs(config.PROJECTED_CRS) if len(entrances) else entrances
        self.prisms = shade.building_prisms(self.buildings_m)   # cut once, reused for every sun position
        self.lock = threading.Lock()   # the web server may call from several threads
        self._cache = OrderedDict()
        self._cache_lock = threading.Lock()

    def _mark_barriers(self, barriers):
        marked = []
        for report in barriers:
            point = to_metres(report["lat"], report["lon"])
            near = self.edges[self.edges.geometry.distance(point) <= report["radius_m"]]
            for u, v, key in near.index:
                self.graph.edges[u, v, key]["barrier_type"] = report["type"]
                self.graph.edges[u, v, key]["barrier_name"] = report["name"]
                self.graph.edges[u, v, key]["barrier_id"] = report["id"]
            marked.append({**report, "edges_marked": len(near)})
        return marked

    def shade_at(self, when):
        """(altitude, azimuth, shade geometry, sun fraction per edge, shaded share), cached per minute."""
        key = when.isoformat(timespec="minutes")
        with self._cache_lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        lat, lon = config.AREA_CENTER
        altitude, azimuth = sun_position(when, lat, lon)
        geometry = shade.shade_map(self.buildings_m, self.trees_m, altitude, azimuth, prisms=self.prisms)
        fractions = shade.sun_fractions(self.edges.geometry.values, geometry, altitude)
        total = self.lengths.sum()
        shaded_share = float(1 - (self.lengths * fractions).sum() / total) if total else 0.0
        result = (altitude, azimuth, geometry, fractions, shaded_share)
        with self._cache_lock:
            self._cache[key] = result
            while len(self._cache) > self.CACHE_SIZE:
                self._cache.popitem(last=False)
        return result

    def warm_up(self, times):
        """Compute the shade for these moments ahead of time (the web server does it in the background)."""
        for when in times:
            self.shade_at(when)

    def set_time(self, when) -> Network:
        """Write the sun fraction of this moment onto the graph edges. Call under self.lock."""
        altitude, azimuth, geometry, fractions, shaded_share = self.shade_at(when)
        for (u, v, key), fraction in zip(self.edge_keys, fractions):
            self.graph.edges[u, v, key]["sun_fraction"] = float(fraction)
        return Network(self.graph, geometry, altitude, azimuth, shaded_share, self.barriers)

    def snap_to_entrance(self, lat: float, lon: float, toward=None, profile_key: str = "standard"):
        """A point inside a building goes to that building's entrance: the main one if it has one,
        the one facing the other end of the trip if it has several, and not one marked
        wheelchair=no for a person with disabilities. Returns (lat, lon, label or None)."""
        if not len(self.entrances_m):
            return lat, lon, None
        point = to_metres(lat, lon)
        inside = self.buildings_m[self.buildings_m.geometry.buffer(1.0).contains(point)]
        if inside.empty:
            return lat, lon, None
        footprint = inside.geometry.union_all()
        ids = set(inside["osm_id"]) if "osm_id" in inside else set()
        linked = self.entrances_m["building"].fillna("").map(lambda b: bool(ids & set(b.split(","))))
        doors = self.entrances_m[(self.entrances_m.geometry.distance(footprint) <= 3.0) | linked]
        doors = doors[~doors["entrance"].isin(["parking", "service", "emergency", "exit", "garage"])]
        if profile_key == "disabled":
            doors = doors[doors["wheelchair"].fillna("") != "no"]
        if doors.empty:
            return lat, lon, None
        if (doors["entrance"] == "main").any():
            doors = doors[doors["entrance"] == "main"]
        target = to_metres(*toward) if toward else point
        door = doors.iloc[int(np.argmin(doors.geometry.distance(target).to_numpy()))]
        door_ll = gpd.GeoSeries([door.geometry], crs=config.PROJECTED_CRS).to_crs("EPSG:4326").iloc[0]
        kind = "main entrance" if door["entrance"] == "main" else "entrance"
        text = lambda value: value if isinstance(value, str) and value else None   # NaN / None -> None
        label = text(door.get("name")) or (f"{kind} {door['ref']}" if text(door.get("ref")) else kind)
        return door_ll.y, door_ll.x, label

    def nearest_node(self, lat: float, lon: float):
        """Closest graph node and its distance in metres."""
        point = to_metres(lat, lon)
        distances = np.hypot(self.node_xy[:, 0] - point.x, self.node_xy[:, 1] - point.y)
        index = int(np.argmin(distances))
        return self.node_ids[index], float(distances[index])

    def route_latlon(self, edges):
        """[(lat, lon), ...] along the edges a route actually uses."""
        points = []
        for u, v, key in edges:
            data = self.graph_latlon.edges[u, v, key]
            line = data.get("geometry") or LineString([
                (self.graph_latlon.nodes[u]["x"], self.graph_latlon.nodes[u]["y"]),
                (self.graph_latlon.nodes[v]["x"], self.graph_latlon.nodes[v]["y"]),
            ])
            coords = [(lat, lon) for lon, lat in line.coords]
            points.extend(coords if not points else coords[1:])
        return points

    def shade_geojson(self, when):
        """Shade polygons in lat/lon for the web map."""
        geometry = self.shade_at(when)[2]
        if geometry.is_empty:
            return {"type": "FeatureCollection", "features": []}
        latlon = gpd.GeoSeries([geometry.simplify(0.4)], crs=config.PROJECTED_CRS).to_crs("EPSG:4326").iloc[0]
        return {"type": "FeatureCollection",
                "features": [{"type": "Feature", "properties": {}, "geometry": mapping(latlon)}]}


def prepare_network(graph, buildings, trees, barriers, when) -> Network:
    """One-shot helper: load an Area and set its time."""
    area = Area(graph, buildings, trees, barriers)
    return area.set_time(when)


def plan_routes(network: Network, start, goal, profile) -> dict:
    """Run A* twice: sun_weight 0 (shortest accessible) and sun_weight > 0 (shaded).
    Dijkstra runs as well, only to report how many nodes A* saved."""
    routes = {}
    for action, weight_key in (("Shortest", "shortest"), ("Shaded", "shaded")):
        cost = search.make_edge_cost(network.graph, profile, config.SUN_WEIGHT[weight_key])
        result = search.astar(network.graph, start, goal, cost)
        if not result.found:
            raise ValueError("No accessible route for this profile: every way is blocked by a barrier.")
        dijkstra = search.astar(network.graph, start, goal, cost, use_heuristic=False)
        stats = search.route_stats(network.graph, result, profile)
        stats["dijkstra_expanded"] = dijkstra.expanded
        stats["sun_weight"] = config.SUN_WEIGHT[weight_key]
        routes[action] = {"result": result, "stats": stats}
    return routes


MAX_SNAP_DISTANCE_M = 120


def barriers_on(graph, edges) -> list:
    """The barriers a route passes, in order: resident reports, raised kerbs, and steps from OSM."""
    found = []
    for u, v, key in edges:
        data = graph.edges[u, v, key]
        kind = data.get("barrier_type") or ("steps" if osm_data.first(data.get("highway")) == "steps" else None)
        if kind:
            ident = data.get("barrier_id", f"osm-steps-{u}-{v}")
            if all(b["id"] != ident and {u, v} != b["_edge"] for b in found):
                found.append({"id": ident, "type": kind, "_edge": {u, v},
                              "name": data.get("barrier_name") or "Steps (mapped in OpenStreetMap)"})
    for b in found:
        b.pop("_edge")
    return found


def plan_trip(area: Area, start_latlon, end_latlon, when, profile_key: str, feels_like=None) -> dict:
    """Whole pipeline for one trip. Returns every intermediate number (for printing or the web)."""
    profile = config.PROFILES[profile_key]
    # A point inside a building starts or ends at that building's entrance.
    start_point = area.snap_to_entrance(*start_latlon, toward=end_latlon, profile_key=profile_key)
    end_point = area.snap_to_entrance(*end_latlon, toward=start_latlon, profile_key=profile_key)
    start, start_gap = area.nearest_node(*start_point[:2])
    goal, goal_gap = area.nearest_node(*end_point[:2])
    if max(start_gap, goal_gap) > MAX_SNAP_DISTANCE_M:
        raise ValueError("Pick points inside the mapped area (the dashed circle).")
    if start == goal:
        raise ValueError("Start and end are the same place.")

    # 1. A* (needs the shade of this moment on the graph)
    with area.lock:
        network = area.set_time(when)
        routes = plan_routes(network, start, goal, profile)
        for route in routes.values():
            route["barriers"] = barriers_on(network.graph, route["result"].edges)
        direct = None
        if profile_key != "standard":
            # The way a person without disabilities would take: it shows which barriers we avoid.
            standard = config.PROFILES["standard"]
            result = search.astar(network.graph, start, goal, search.make_edge_cost(network.graph, standard, 0.0))
            if result.found:
                direct = {"result": result, "stats": search.route_stats(network.graph, result, standard),
                          "barriers": barriers_on(network.graph, result.edges)}

    # 2. Bayes: sensor reading -> P(dangerous heat). The weather is read at one point for the whole area.
    if feels_like is None:
        feels_like, source = weather.feels_like_at(when, *config.WEATHER_POINT)
    else:
        source = "entered by hand"
    reading = bayes.reading_bucket(feels_like)
    prior = bayes.prior_for_month(when.month)
    belief = bayes.heat_posterior(prior, reading)

    # 3. MDP: Shortest or Shaded?
    stats = {action: routes[action]["stats"] for action in mdp.ACTIONS}
    transitions, rewards = mdp.build_model(stats, belief["posterior"], profile["heat_vulnerability"])
    values = mdp.terminal_values()
    q, new_values, policy = mdp.bellman_update(transitions, rewards, values)

    return {
        "network": network, "profile": profile, "profile_key": profile_key,
        "start_node": start, "goal_node": goal, "start_point": start_point, "end_point": end_point,
        "routes": routes, "direct": direct, "feels_like": feels_like, "weather_source": source,
        "belief": belief, "transitions": transitions, "rewards": rewards,
        "values": values, "q": q, "policy": policy, "decision": policy["Comfortable"],
    }
