import math
from datetime import datetime

import numpy as np
import pytest
import shapely
from shapely.geometry import LineString, Point, box

import config
from shade import building_shadow, part_prisms, prism_shadow_pieces, sun_fractions
from sun import sun_position

ASTANA = (51.0909, 71.4184)


def test_summer_solstice_noon_in_astana():
    # Solar noon in Astana on 21 June is about 12:16 local time (UTC+5).
    # Expected altitude = 90 - latitude + 23.44 = 62.35 deg, sun due south.
    altitude, azimuth = sun_position(datetime(2026, 6, 21, 12, 16, tzinfo=config.ASTANA_TZ), *ASTANA)
    assert altitude == pytest.approx(62.35, abs=0.5)
    assert azimuth == pytest.approx(180, abs=3)


def test_sun_is_west_in_the_evening_and_down_at_night():
    _, evening_azimuth = sun_position(datetime(2026, 7, 15, 19, 0, tzinfo=config.ASTANA_TZ), *ASTANA)
    night_altitude, _ = sun_position(datetime(2026, 7, 15, 1, 0, tzinfo=config.ASTANA_TZ), *ASTANA)
    assert 250 < evening_azimuth < 310
    assert night_altitude < 0


def test_shadow_of_a_cube_points_away_from_the_sun():
    cube = box(0, 0, 10, 10)  # 10 x 10 m footprint, 10 m tall
    # Sun in the south at 45 deg -> shadow is 10 m long and goes north.
    north = building_shadow(cube, 10, altitude=45, azimuth=180)
    assert north.bounds == pytest.approx((0, 0, 10, 20))
    assert north.area == pytest.approx(200)
    # Sun in the west -> shadow goes east.
    east = building_shadow(cube, 10, altitude=45, azimuth=270)
    assert east.bounds == pytest.approx((0, 0, 20, 10))


def test_no_shadow_when_sun_is_down():
    assert building_shadow(box(0, 0, 10, 10), 10, altitude=-5, azimuth=0) is None


def test_sun_fraction_of_lines():
    shade = box(0, 0, 10, 10)
    lines = [LineString([(0, 5), (10, 5)]),    # fully inside the shade
             LineString([(5, 5), (15, 5)]),    # half inside
             LineString([(20, 0), (30, 0)])]   # fully in the sun
    assert list(sun_fractions(lines, shade, altitude=30)) == pytest.approx([0.0, 0.5, 1.0])
    assert list(sun_fractions(lines, shade, altitude=-1)) == [0, 0, 0]  # night: no sun anywhere


def test_building_on_columns_casts_a_shadow_that_starts_away_from_it():
    # A 10 x 10 m block from 5 m to 10 m above the ground, sun in the south at 45 deg.
    # Its shadow starts 5 m north of the footprint and ends 10 m north of it.
    raised = building_shadow(box(0, 0, 10, 10), 10, altitude=45, azimuth=180, min_height=5)
    assert raised.bounds == pytest.approx((0, 5, 10, 20))
    assert raised.area == pytest.approx(150)


def test_sphere_shadow_is_an_ellipse_away_from_the_sun():
    # A sphere of radius 10 m with its top at 20 m. Under a 45 deg sun in the south its
    # shadow is an ellipse centred 10 m north (the height of its centre), with semi-axes
    # 10 m across and 10 / sin(45 deg) = 14.1 m along the shadow.
    footprint = Point(0, 0).buffer(10, quad_segs=32)
    prisms = part_prisms(footprint, 0, 20, "sphere")
    pieces = prism_shadow_pieces(prisms, np.array([20.0] * len(prisms)), altitude=45, azimuth=180)
    shadow = shapely.union_all(pieces)
    assert shadow.centroid.x == pytest.approx(0, abs=0.5)
    assert shadow.centroid.y == pytest.approx(10, abs=1.5)
    assert shadow.area == pytest.approx(math.pi * 10 * 10 / math.sin(math.radians(45)), rel=0.15)


def test_dome_is_cut_into_slices_that_narrow_to_the_top():
    footprint = box(-10, -10, 10, 10)
    prisms = part_prisms(footprint, 0, 15, "dome", roof_height=5)
    assert prisms[0][1:] == (0, 10)                      # walls up to where the dome starts
    tops = [z1 for _, _, z1 in prisms]
    assert tops == sorted(tops) and tops[-1] == pytest.approx(15)
    areas = [f.area for f, _, _ in prisms[1:]]
    assert areas == sorted(areas, reverse=True)
