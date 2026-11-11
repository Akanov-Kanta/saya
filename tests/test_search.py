import math
import random

import networkx as nx
import pytest

import config
from search import astar, make_edge_cost, route_stats

WHEELCHAIR = config.PROFILES["wheelchair"]
STANDARD = config.PROFILES["standard"]


def add_path(graph, u, v, sun, **tags):
    """Add a footway in both directions, length = straight-line distance."""
    length = math.dist((graph.nodes[u]["x"], graph.nodes[u]["y"]), (graph.nodes[v]["x"], graph.nodes[v]["y"]))
    for a, b in ((u, v), (v, u)):
        graph.add_edge(a, b, length=length, sun_fraction=sun, highway="footway", **tags)


def toy_map():
    """  A --- B --- D   sunny straight street, 200 m
          \\       /
             C        shaded side street, about 224 m"""
    graph = nx.MultiDiGraph()
    for node, (x, y) in {"A": (0, 0), "B": (100, 0), "C": (100, 50), "D": (200, 0)}.items():
        graph.add_node(node, x=x, y=y)
    add_path(graph, "A", "B", sun=1.0)
    add_path(graph, "B", "D", sun=1.0)
    add_path(graph, "A", "C", sun=0.0)
    add_path(graph, "C", "D", sun=0.0)
    return graph


def test_shortest_route_ignores_sun():
    result = astar(toy_map(), "A", "D", make_edge_cost(toy_map(), STANDARD, sun_weight=0))
    assert result.path == ["A", "B", "D"]
    assert result.cost == pytest.approx(200)


def test_shaded_route_avoids_sun():
    graph = toy_map()
    result = astar(graph, "A", "D", make_edge_cost(graph, STANDARD, sun_weight=3))
    assert result.path == ["A", "C", "D"]
    stats = route_stats(graph, result, STANDARD)
    assert stats["sun_m"] == 0
    assert stats["length_m"] == pytest.approx(2 * math.hypot(100, 50))


def test_barrier_blocks_wheelchair_but_not_pedestrian():
    graph = toy_map()
    for u, v in (("A", "C"), ("C", "A")):
        graph.edges[u, v, 0]["barrier_type"] = "broken_ramp"
    shaded_wheelchair = astar(graph, "A", "D", make_edge_cost(graph, WHEELCHAIR, sun_weight=3))
    shaded_walker = astar(graph, "A", "D", make_edge_cost(graph, STANDARD, sun_weight=3))
    assert shaded_wheelchair.path == ["A", "B", "D"]   # forced back into the sun
    assert shaded_walker.path == ["A", "C", "D"]


def test_no_route_when_every_way_is_blocked():
    graph = toy_map()
    for u, v, key in list(graph.edges(keys=True)):
        graph.edges[u, v, key]["barrier_type"] = "steps"
    assert not astar(graph, "A", "D", make_edge_cost(graph, WHEELCHAIR, 0)).found


def test_astar_matches_dijkstra_and_expands_fewer_nodes():
    """On a random 15 x 15 grid A* must return the same optimal cost as Dijkstra."""
    rng = random.Random(7)
    grid = nx.MultiDiGraph()
    size, step = 15, 20
    for i in range(size):
        for j in range(size):
            grid.add_node((i, j), x=i * step, y=j * step)
    for i in range(size):
        for j in range(size):
            for di, dj in ((1, 0), (0, 1)):
                if i + di < size and j + dj < size:
                    add_path(grid, (i, j), (i + di, j + dj), sun=rng.random())
    cost = make_edge_cost(grid, WHEELCHAIR, sun_weight=3)
    a_star = astar(grid, (0, 0), (size - 1, size - 1), cost)
    dijkstra = astar(grid, (0, 0), (size - 1, size - 1), cost, use_heuristic=False)
    assert a_star.cost == pytest.approx(dijkstra.cost)
    assert a_star.expanded <= dijkstra.expanded
