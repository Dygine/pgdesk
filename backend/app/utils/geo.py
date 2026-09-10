"""
Distance between two points on the earth.

Used by the resident self check-in geofence. Kept here rather than in the
service so it can be tested on its own - a geofence that is wrong by a factor
is the kind of bug that only shows up as "attendance sometimes fails" months
later, and a pure function is the only part of this feature that can be pinned
down exactly.
"""
import math

# Mean earth radius in metres (WGS-84 mean). Good to ~0.5% anywhere, which is
# far inside the GPS error a phone reports, so a more elaborate ellipsoidal
# formula would be false precision.
EARTH_RADIUS_M = 6_371_008.8


def haversine_metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Great-circle distance in metres.

    Haversine rather than the simpler equirectangular approximation because the
    latter degrades badly near the poles, and "our geofence works in Bengaluru
    but not in Srinagar" is not a defect anyone would find quickly.
    """
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_phi = p2 - p1
    d_lambda = math.radians(lon2 - lon1)

    a = (math.sin(d_phi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(d_lambda / 2) ** 2)
    # asin of a clamped value: floating point can push `a` a hair above 1 for
    # antipodal points, and math.sqrt of a negative would raise.
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, a)))


def is_valid_coordinate(latitude: float | None, longitude: float | None) -> bool:
    """
    Both present and inside the real range.

    Note that (0, 0) is a valid point in the Gulf of Guinea but is almost always
    a client that sent uninitialised values, so callers treat it as absent. It
    is 6,000 km from the nearest PG we will ever serve; refusing it costs
    nothing and catches a common bug.
    """
    if latitude is None or longitude is None:
        return False
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        return False
    if abs(latitude) < 1e-7 and abs(longitude) < 1e-7:
        return False
    return True
