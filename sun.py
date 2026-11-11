"""Where is the sun? NOAA's general solar position formulas (accurate to about 0.5 deg)."""

import math
from datetime import datetime, timezone


def sun_position(when: datetime, lat: float, lon: float) -> tuple[float, float]:
    """Return (altitude, azimuth) in degrees for a timezone-aware datetime.

    altitude: angle above the horizon (negative at night).
    azimuth: compass direction of the sun, clockwise from north (180 = due south).
    """
    utc = when.astimezone(timezone.utc)
    day_of_year = utc.timetuple().tm_yday
    hour = utc.hour + utc.minute / 60 + utc.second / 3600

    # Fractional year in radians
    g = 2 * math.pi / 365 * (day_of_year - 1 + (hour - 12) / 24)

    # Equation of time (minutes) and solar declination (radians)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                       - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
            - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
            - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))

    # True solar time (minutes) and hour angle (radians). 0 at solar noon, positive in the afternoon.
    true_solar_time = hour * 60 + eqtime + 4 * lon
    hour_angle = math.radians(true_solar_time / 4 - 180)

    phi = math.radians(lat)
    cos_zenith = (math.sin(phi) * math.sin(decl)
                  + math.cos(phi) * math.cos(decl) * math.cos(hour_angle))
    altitude = 90 - math.degrees(math.acos(max(-1.0, min(1.0, cos_zenith))))

    azimuth = math.degrees(math.atan2(
        math.sin(hour_angle),
        math.cos(hour_angle) * math.sin(phi) - math.tan(decl) * math.cos(phi),
    )) + 180
    return altitude, azimuth % 360


def compass(azimuth: float) -> str:
    names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return names[int((azimuth + 22.5) // 45) % 8]
