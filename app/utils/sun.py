"""Sun position for rule conditions (``sun_elevation()``, ``is_daylight()``).

NOAA "General Solar Position Calculations" (the fractional-year series):
accurate to a fraction of a degree, which puts sunrise / sunset within a
couple of minutes — plenty for "is it daytime" rules, and no dependency.
Pure functions: the caller passes the instant and the place.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime

# Elevation of the sun's centre at the standard sunrise / sunset: the upper
# limb touches the horizon, refraction included.
SUNRISE_ELEVATION = -0.833


def sun_elevation(lat: float, lon: float, when: datetime) -> float:
    """Elevation of the sun above the horizon, in degrees, at ``lat`` / ``lon``
    (degrees, east positive) and the aware instant ``when``."""
    t = when.astimezone(UTC)
    days_in_year = 366 if t.year % 4 == 0 and (t.year % 100 != 0 or t.year % 400 == 0) else 365
    hours = t.hour + t.minute / 60 + t.second / 3600
    g = 2 * math.pi / days_in_year * (t.timetuple().tm_yday - 1 + (hours - 12) / 24)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                       - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
            - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
            - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    true_solar_min = hours * 60 + eqtime + 4 * lon
    hour_angle = math.radians(true_solar_min / 4 - 180)
    phi = math.radians(lat)
    cos_zenith = math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl) * math.cos(hour_angle)
    return 90 - math.degrees(math.acos(max(-1.0, min(1.0, cos_zenith))))
