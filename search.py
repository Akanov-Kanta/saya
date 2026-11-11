"""A* search over the walk network, with an accessibility- and sun-aware edge cost."""

import heapq
import itertools
import math
from dataclasses import dataclass

import config
from osm_data import first

ROUGH_SURFACES = {"paving_stones", "sett", "cobblestone", "unhewn_cobblestone", "gravel", "fine_gravel", "compacted"}


@dataclass
class SearchResult:
    found: bool
    path: list    # node ids, start ... goal
    edges: list   # (u, v, key) actually used
    cost: float
    expanded: int  # nodes taken off the frontier


def astar(graph, start, goal, edge_cost, use_heuristic: bool = True) -> SearchResult:
    """Classic A*: always expand the frontier node with the smallest f = g + h.

    g(n) = cheapest known cost from start to n
    h(n) = straight-line distance from n to the goal (metres). It is admissible
           and consistent because every edge costs at least its own length.
    With use_heuristic=False this is exactly Dijkstra / uniform-cost search,
    which we use only to show how many nodes A* saves.
    """
    goal_x, goal_y = graph.nodes[goal]["x"], graph.nodes[goal]["y"]

    def h(node):
        if not use_heuristic:
            return 0.0
        return math.hypot(graph.nodes[node]["x"] - goal_x, graph.nodes[node]["y"] - goal_y)

    tie = itertools.count()                 # breaks ties in the heap without comparing nodes
    frontier = [(h(start), next(tie), start)]
    g = {start: 0.0}
    came_from = {start: None}               # node -> (previous node, edge key)
    closed = set()

    while frontier:
        _, _, node = heapq.heappop(frontier)
        if node in closed:
            continue                        # stale heap entry, a cheaper one was already expanded
        closed.add(node)
        if node == goal:
            break
        for neighbour, parallel_edges in graph[node].items():
            # Two nodes can be joined by several OSM ways: take the cheapest passable one.
            options = [(edge_cost(node, neighbour, key, data), key) for key, data in parallel_edges.items()]
            options = [(cost, key) for cost, key in options if cost is not None]
            if not options:
                continue                    # impassable for this profile
            step_cost, key = min(options)
            new_g = g[node] + step_cost
            if new_g < g.get(neighbour, math.inf):
                g[neighbour] = new_g
                came_from[neighbour] = (node, key)
                heapq.heappush(frontier, (new_g + h(neighbour), next(tie), neighbour))

    if goal not in closed:
        return SearchResult(False, [], [], math.inf, len(closed))

    path, edges, node = [goal], [], goal
    while came_from[node] is not None:
        previous, key = came_from[node]
        edges.append((previous, node, key))
        path.append(previous)
        node = previous
    path.reverse()
    edges.reverse()
    return SearchResult(True, path, edges, g[goal], len(closed))


# ---------------------------------------------------------------- edge cost

def _is_uncontrolled_crossing(graph, u, v, data) -> bool:
    if first(data.get("footway")) != "crossing" and first(data.get("highway")) != "crossing":
        return False
    tags = [first(data.get("crossing"))]
    for node in (u, v):
        tags += [first(graph.nodes[node].get("crossing")), first(graph.nodes[node].get("highway"))]
    return "traffic_signals" not in tags


def access(graph, u, v, data, profile):
    """How hard is this edge for the profile? Returns (multiplier, extra metres) or None if impassable."""
    multiplier, extra = 1.0, 0.0
    highway = first(data.get("highway"))
    barrier = data.get("barrier_type") or ("steps" if highway == "steps" else None)
    if barrier:
        factor = profile["barrier"].get(barrier, 1.0)
        if factor is None:
            return None
        multiplier *= factor
    if highway in config.BUSY_ROADS:
        multiplier *= profile["busy_road"]
    elif highway not in config.FOOT_HIGHWAYS and highway != "steps":
        multiplier *= profile["road_no_sidewalk"]
    if first(data.get("surface")) in ROUGH_SURFACES:
        multiplier *= profile["paving_stones"]
    if _is_uncontrolled_crossing(graph, u, v, data):
        extra += profile["uncontrolled_crossing_m"]
    return multiplier, extra


def make_edge_cost(graph, profile, sun_weight: float):
    """cost = length * access multiplier * (1 + sun_weight * sun_fraction) + extra metres"""
    def edge_cost(u, v, key, data):
        result = access(graph, u, v, data, profile)
        if result is None:
            return None
        multiplier, extra = result
        return data["length"] * multiplier * (1 + sun_weight * data.get("sun_fraction", 0.0)) + extra
    return edge_cost


def route_stats(graph, result: SearchResult, profile) -> dict:
    length = sun = 0.0
    uncontrolled = 0
    barriers = []
    for u, v, key in result.edges:
        data = graph.edges[u, v, key]
        length += data["length"]
        sun += data["length"] * data.get("sun_fraction", 0.0)
        uncontrolled += _is_uncontrolled_crossing(graph, u, v, data)
        if data.get("barrier_type"):
            barriers.append(data.get("barrier_name"))
    speed = profile["speed_mps"]
    return {
        "length_m": length,
        "sun_m": sun,
        "sun_share": sun / length if length else 0.0,
        "walk_min": length / speed / 60,
        "sun_min": sun / speed / 60,
        "uncontrolled_crossings": uncontrolled,
        "barriers": sorted(set(b for b in barriers if b)),
        "cost": result.cost,
        "expanded": result.expanded,
    }
