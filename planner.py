"""Glue code: sun -> shade on every sidewalk -> resident barrier reports -> A* routes."""

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import osmnx as ox
from shapely.geometry import Point

import config
import search
import shade
from sun import sun_position


@dataclass
class Network:
    graph: object          # projected graph (metres), edges carry sun_fraction / barrier_type
    shade: object          # shapely geometry of all shade, projected
    altitude: float
    azimuth: float
    shaded_share: float    # share of all sidewalk length that is in shade
    barriers: list


def to_metres(lat: float, lon: float) -> Point:
    return gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(config.PROJECTED_CRS).iloc[0]


def prepare_network(graph, buildings, trees, barriers, when) -> Network:
    lat, lon = config.AREA_CENTER
    altitude, azimuth = sun_position(when, lat, lon)

    graph_m = ox.project_graph(graph, to_crs=config.PROJECTED_CRS)
    buildings_m = buildings.to_crs(config.PROJECTED_CRS)
    trees_m = trees.to_crs(config.PROJECTED_CRS)
    shade_geometry = shade.shade_map(buildings_m, trees_m, altitude, azimuth)

    # Sun fraction of every edge
    edges = ox.graph_to_gdfs(graph_m, nodes=False, fill_edge_geometry=True)
    fractions = shade.sun_fractions(edges.geometry.values, shade_geometry, altitude)
    for (u, v, key), fraction in zip(edges.index, fractions):
        graph_m.edges[u, v, key]["sun_fraction"] = float(fraction)

    # Resident reports (broken ramp, steps, construction) mark nearby edges
    marked = []
    for report in barriers:
        point = to_metres(report["lat"], report["lon"])
        near = edges[edges.geometry.distance(point) <= report["radius_m"]]
        for u, v, key in near.index:
            graph_m.edges[u, v, key]["barrier_type"] = report["type"]
            graph_m.edges[u, v, key]["barrier_name"] = report["name"]
        marked.append({**report, "edges_marked": len(near)})

    total = edges["length"].sum()
    shaded_share = float(1 - (edges["length"].values * fractions).sum() / total) if total else 0.0
    return Network(graph_m, shade_geometry, altitude, azimuth, shaded_share, marked)


def nearest_node(graph_m, lat: float, lon: float):
    point = to_metres(lat, lon)
    nodes = list(graph_m.nodes)
    xs = np.array([graph_m.nodes[n]["x"] for n in nodes])
    ys = np.array([graph_m.nodes[n]["y"] for n in nodes])
    return nodes[int(np.argmin((xs - point.x) ** 2 + (ys - point.y) ** 2))]


def plan_routes(network: Network, start, goal, profile) -> dict:
    """Run A* twice: sun_weight 0 (shortest accessible) and sun_weight > 0 (shaded).
    Dijkstra runs as well, only to report how many nodes A* saved."""
    routes = {}
    for action, weight_key in (("Shortest", "shortest"), ("Shaded", "shaded")):
        cost = search.make_edge_cost(network.graph, profile, config.SUN_WEIGHT[weight_key])
        result = search.astar(network.graph, start, goal, cost)
        if not result.found:
            raise RuntimeError(f"No accessible route for this profile ({action}).")
        dijkstra = search.astar(network.graph, start, goal, cost, use_heuristic=False)
        stats = search.route_stats(network.graph, result, profile)
        stats["dijkstra_expanded"] = dijkstra.expanded
        stats["sun_weight"] = config.SUN_WEIGHT[weight_key]
        routes[action] = {"result": result, "stats": stats}
    return routes
