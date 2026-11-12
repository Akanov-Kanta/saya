"""Turn buildings + sun position into shadow polygons, then measure how much of
each sidewalk segment is in the sun.

Geometry is done in a metric projection (UTM), so all lengths are metres.

Every building (or OSM building:part) becomes one or more vertical prisms: a
footprint that fills the space from height z0 to z1. A flat-roofed block is one
prism from the ground (or from its min_height, if it stands on columns) to its
height. A dome, a pyramid roof or a sphere is cut into horizontal slices, each
slice a prism, so the same code casts all of their shadows.
"""

import math

import numpy as np
import shapely
from shapely.affinity import scale
from shapely.geometry import Point, Polygon

import config


def shadow_direction(altitude: float, azimuth: float) -> tuple[float, float]:
    """Ground shift (dx east, dy north) of the shadow of a point 1 m above the ground.

    The shadow points away from the sun (azimuth + 180 deg) and is 1 / tan(altitude) long.
    """
    length = 1 / math.tan(math.radians(altitude))
    away = math.radians(azimuth + 180)
    return length * math.sin(away), length * math.cos(away)


def shadow_offset(height: float, altitude: float, azimuth: float) -> tuple[float, float]:
    """Where the shadow of a roof point lands: height / tan(altitude), capped at MAX_SHADOW_LENGTH."""
    dx, dy = shadow_direction(altitude, azimuth)
    factor = min(height, config.MAX_SHADOW_LENGTH / math.hypot(dx, dy))
    return dx * factor, dy * factor


# ---------------------------------------------------------------- building -> prisms

def part_prisms(footprint, min_height: float, height: float, shape: str = "flat", roof_height=None):
    """Cut one building piece into prisms: [(footprint, z0, z1), ...] in metres."""
    n = config.CURVE_SLICES
    if shape == "sphere":
        return _sphere_prisms(footprint, min_height, height, n)
    roof = float(roof_height or 0.0) if shape in ("dome", "pyramidal") else 0.0
    roof = min(roof, height - min_height)
    prisms = []
    base = height - roof
    if base > min_height:
        prisms.append((footprint, min_height, base))
    if roof > 0:
        centre = footprint.centroid
        for i in range(n):
            s0, s1 = i / n, (i + 1) / n
            # the widest point of each slice is its bottom: a dome narrows as sqrt(1 - s^2), a pyramid as 1 - s
            factor = math.sqrt(1 - s0 * s0) if shape == "dome" else 1 - s0
            prisms.append((scale(footprint, factor, factor, origin=centre), base + s0 * roof, base + s1 * roof))
    return prisms


def sphere_params(footprint, min_height: float, height: float) -> dict:
    """A sphere that fills the footprint (same area) with its top at `height`, on a narrower neck."""
    radius = math.sqrt(footprint.area / math.pi)
    centre_z = height - radius
    neck_top = max(min_height, centre_z - 0.8 * radius)
    return {"cx": footprint.centroid.x, "cy": footprint.centroid.y, "r": radius, "zc": centre_z,
            "neck_r": 0.45 * radius, "neck_top": neck_top}


def _sphere_prisms(footprint, min_height: float, height: float, n: int):
    p = sphere_params(footprint, min_height, height)
    centre, r, zc = Point(p["cx"], p["cy"]), p["r"], p["zc"]
    prisms = []
    if p["neck_top"] > min_height:
        prisms.append((centre.buffer(p["neck_r"], quad_segs=8), min_height, p["neck_top"]))
    bottom = zc - r
    for i in range(2 * n):
        z0, z1 = bottom + i * r / n, bottom + (i + 1) * r / n
        nearest = min(max(zc, z0), z1)               # the widest height inside this slice
        radius = math.sqrt(max(r * r - (nearest - zc) ** 2, 0.0))
        if radius > 0.05:
            prisms.append((centre.buffer(radius, quad_segs=8), max(z0, 0.0), z1))
    return prisms


def building_prisms(buildings_m):
    """All prisms of all buildings, plus for each prism the top height of its building."""
    prisms, tops = [], []
    columns = buildings_m.columns
    for i, geometry in enumerate(buildings_m.geometry):
        height = float(buildings_m["height"].iat[i])
        min_height = float(buildings_m["min_height"].iat[i]) if "min_height" in columns else 0.0
        shape = buildings_m["shape"].iat[i] if "shape" in columns else "flat"
        roof = buildings_m["roof_height"].iat[i] if "roof_height" in columns else None
        roof = None if roof is None or (isinstance(roof, float) and math.isnan(roof)) else float(roof)
        for prism in part_prisms(geometry, min_height, height, shape or "flat", roof):
            prisms.append(prism)
            tops.append(height)
    return prisms, np.array(tops, dtype=float)


# ---------------------------------------------------------------- prisms -> shadows

def prism_shadow_pieces(prisms, tops, altitude: float, azimuth: float) -> np.ndarray:
    """Shadow pieces of prisms, all computed at once with shapely's vectorised functions.

    A point at height z casts its shadow at z * u, where u = shadow_direction(). So a
    prism from z0 to z1 casts its footprint moved by z0 * u, swept along to z1 * u.
    That sweep is the union of the two moved footprints and, for every wall, the
    parallelogram between the wall's two moved copies. It is exact for any polygon,
    convex or not, with or without courtyards.
    """
    if altitude <= 0 or not prisms:
        return np.array([], dtype=object)
    ux, uy = shadow_direction(altitude, azimuth)
    unit = math.hypot(ux, uy)
    k = np.minimum(1.0, config.MAX_SHADOW_LENGTH / (np.maximum(tops, 1e-6) * unit))   # shadow length cap
    footprints = np.array([p[0] for p in prisms], dtype=object)
    z0 = np.array([p[1] for p in prisms]) * k
    z1 = np.array([p[2] for p in prisms]) * k
    d0 = np.column_stack([z0 * ux, z0 * uy])
    d1 = np.column_stack([z1 * ux, z1 * uy])

    def moved(offsets):
        coords, index = shapely.get_coordinates(footprints, return_index=True)
        return shapely.set_coordinates(footprints.copy(), coords + offsets[index])

    parts, part_of = shapely.get_parts(footprints, return_index=True)
    rings, ring_of = shapely.get_rings(parts, return_index=True)
    coords, coord_of = shapely.get_coordinates(rings, return_index=True)
    same_ring = coord_of[:-1] == coord_of[1:]
    a, b = coords[:-1][same_ring], coords[1:][same_ring]
    prism_of = part_of[ring_of[coord_of[:-1][same_ring]]]
    e0, e1 = d0[prism_of], d1[prism_of]
    walls = shapely.polygons(np.stack([a + e0, b + e0, b + e1, a + e1, a + e0], axis=1))
    walls = walls[shapely.area(walls) > 1e-6]                 # walls parallel to the sun cast no area
    return np.concatenate([moved(d0), moved(d1), walls])


def building_shadow(footprint, height: float, altitude: float, azimuth: float, min_height: float = 0.0):
    """Shadow of one flat-roofed building (a vertical prism), or None at night."""
    if altitude <= 0:
        return None
    pieces = prism_shadow_pieces([(footprint, min_height, height)], np.array([height]), altitude, azimuth)
    return shapely.union_all(pieces)


def tree_shade(trees_m) -> np.ndarray:
    """Woods and forests shade their whole area. Single trees and tree rows shade a 3 m crown."""
    shapes = [geometry if kind == "wood" else geometry.buffer(config.TREE_CROWN_RADIUS_M, quad_segs=4)
              for geometry, kind in zip(trees_m.geometry, trees_m["kind"])]
    return np.array(shapes, dtype=object)


def shade_map(buildings_m, trees_m, altitude: float, azimuth: float, prisms=None):
    """Union of all shade: building shadows (depend on the sun) + tree crowns (always)."""
    if prisms is None:
        prisms = building_prisms(buildings_m)
    pieces = prism_shadow_pieces(*prisms, altitude, azimuth)
    shapes = np.concatenate([pieces, tree_shade(trees_m)])
    shapes = shapes[~shapely.is_empty(shapes)]
    return shapely.union_all(shapely.make_valid(shapes)) if len(shapes) else Polygon()


def sun_fractions(edge_lines, shade, altitude: float) -> np.ndarray:
    """Share of each line (0..1) that lies in the sun. At night everything is shade."""
    lines = np.asarray(edge_lines, dtype=object)
    if altitude <= 0:
        return np.zeros(len(lines))
    lengths = shapely.length(lines)
    shaded = np.zeros(len(lines))
    # Intersect each line only with the shade polygons near it, not with the whole union.
    pieces = shapely.get_parts(shade)
    tree = shapely.STRtree(pieces)
    line_index, piece_index = tree.query(lines, predicate="intersects")
    if len(line_index):
        parts = shapely.intersection(lines[line_index], pieces[piece_index])
        np.add.at(shaded, line_index, shapely.length(parts))
    with np.errstate(divide="ignore", invalid="ignore"):
        frac = np.where(lengths > 0, 1 - shaded / lengths, 0.0)
    return np.clip(frac, 0.0, 1.0)
