"""Shared geographic primitives. Every detector takes its constants and its grid from here.

One place on purpose. These same few things - the Earth's radius, the nautical mile, a bearing, the
degree grid - were written out separately in seven modules. They agreed, which is exactly what makes
that arrangement dangerous: nothing would have caught the day one copy was corrected and the others
were not. The grid was already two functions with different arithmetic, and at 1.0 deg with a 0.1
deg cell they disagreed about which square a point belongs to.
"""
from math import asin, atan2, cos, degrees, floor, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0
KM_PER_NM = 1.852
# Poludnik: 111 km na stopien, z dokladnoscia wystarczajaca do dobrania promienia przeszukiwania.
KM_PER_DEG_LAT = 111.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def km_per_deg_lon(lat: float) -> float:
    """Width of one degree of longitude at this latitude, floored at 1 km.

    It shrinks towards the poles - 59 km at 58N, 29 km at 75N - so a search ring measured in cells
    has to be wider east-west than north-south, or pairs simply fall out of the grid.
    """
    return max(1.0, KM_PER_DEG_LAT * cos(radians(lat)))


def cell_of(lat: float, lon: float, size: float) -> tuple[int, int]:
    """Degree-grid square a position falls into. The one definition of a cell boundary."""
    return (floor(lat / size), floor(lon / size))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from the first point to the second, 0-360 clockwise from north."""
    phi1, phi2 = radians(lat1), radians(lat2)
    d_lon = radians(lon2 - lon1)
    y = sin(d_lon) * cos(phi2)
    x = cos(phi1) * sin(phi2) - sin(phi1) * cos(phi2) * cos(d_lon)
    return degrees(atan2(y, x)) % 360.0


def implied_kt(km: float, hours: float, same_instant_km: float = 0.0) -> float:
    """Speed in knots a distance and a duration imply, with a stated answer for a bad duration.

    The bad duration is the whole reason this is a function. Two positions stamped the same second
    imply an infinite speed, and every caller used to decide that for itself: one returned 0 to dodge
    the division, one returned infinity, one skipped the pair entirely. The same data therefore meant
    "stood still", "impossible" and "unknown" depending on which detector was asked.

    Infinity is the honest answer, and same_instant_km says how far apart two fixes must be before it
    is claimed - below that the gap is the clock's rounding, not a hull in two places.
    """
    if hours > 0:
        return km / KM_PER_NM / hours
    return float("inf") if km > same_instant_km else 0.0
