from datetime import datetime

import pytest
from shapely.geometry import LineString, box

import config
from shade import building_shadow, sun_fractions
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
