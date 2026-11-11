"""Turn buildings + sun position into shadow polygons, then measure how much of
each sidewalk segment is in the sun.

Geometry is done in a metric projection (UTM), so all lengths are metres.
"""

import math

import numpy as np
import shapely
from shapely.affinity import translate
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.ops import unary_union

import config


def shadow_offset(height: float, altitude: float, azimuth: float) -> tuple[float, float]:
    """Vector (dx east, dy north) from a roof point to where its shadow lands.

    Shadow length = height / tan(altitude). The shadow points away from the sun,
    i.e. towards azimuth + 180 deg.
    """
    length = min(height / math.tan(math.radians(altitude)), config.MAX_SHADOW_LENGTH)
    away = math.radians(azimuth + 180)
    return length * math.sin(away), length * math.cos(away)


def building_shadow(footprint, height: float, altitude: float, azimuth: float):
    """Shadow of a vertical prism: the footprint swept along the shadow vector.

    For every wall (edge of the footprint) the wall's shadow is the convex hull
    of the edge and the same edge moved by the offset. Union of all wall shadows
    plus the footprint itself is exact for any polygon shape, convex or not.
    """
    if altitude <= 0:
        return None
    dx, dy = shadow_offset(height, altitude, azimuth)
    parts = footprint.geoms if isinstance(footprint, MultiPolygon) else [footprint]
    pieces = []
    for polygon in parts:
        pieces.append(polygon)
        coords = list(polygon.exterior.coords)
        for a, b in zip(coords, coords[1:]):
            wall = LineString([a, b])
            pieces.append(shapely.convex_hull(shapely.union(wall, translate(wall, dx, dy))))
    return unary_union(pieces)


def shade_map(buildings_m, trees_m, altitude: float, azimuth: float):
    """Union of all shade: building shadows (depend on the sun) + tree crowns (always)."""
    shapes = []
    if altitude > 0:
        for geometry, height in zip(buildings_m.geometry, buildings_m["height"]):
            shadow = building_shadow(geometry, float(height), altitude, azimuth)
            if shadow is not None:
                shapes.append(shadow)
    for geometry, kind in zip(trees_m.geometry, trees_m["kind"]):
        shapes.append(geometry if kind == "wood" else geometry.buffer(config.TREE_CROWN_RADIUS_M))
    return unary_union(shapes) if shapes else Polygon()


def sun_fractions(edge_lines, shade, altitude: float) -> np.ndarray:
    """Share of each line (0..1) that lies in the sun. At night everything is shade."""
    lines = np.asarray(edge_lines, dtype=object)
    if altitude <= 0:
        return np.zeros(len(lines))
    shapely.prepare(shade)
    lengths = shapely.length(lines)
    shaded = shapely.length(shapely.intersection(lines, shade))
    with np.errstate(divide="ignore", invalid="ignore"):
        frac = np.where(lengths > 0, 1 - shaded / lengths, 0.0)
    return np.clip(frac, 0.0, 1.0)
