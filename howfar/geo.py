"""Geodesy helpers: points along a bearing, distance and bearing between points, local metre grids."""
import math

R = 6371008.8          # mean earth radius, metres
K = 0.13               # standard atmospheric refraction coefficient


def dest(lat, lon, brg, d):
    """Point reached from (lat, lon) going d metres on compass bearing brg (sphere)."""
    p1, l1, b, a = math.radians(lat), math.radians(lon), math.radians(brg), d / R
    p2 = math.asin(math.sin(p1) * math.cos(a) + math.cos(p1) * math.sin(a) * math.cos(b))
    l2 = l1 + math.atan2(math.sin(b) * math.sin(a) * math.cos(p1), math.cos(a) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), (math.degrees(l2) + 540) % 360 - 180


def inv(lat1, lon1, lat2, lon2):
    """(distance m, initial bearing deg) on the sphere."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    d = 2 * R * math.asin(math.sqrt(a))
    b = math.degrees(math.atan2(math.sin(dl) * math.cos(p2),
                                math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)))
    return d, b % 360


def vincenty(lat1, lon1, lat2, lon2):
    """WGS84 ellipsoid distance (m). Used for the final number; the sphere maths is used for search."""
    a, f = 6378137.0, 1 / 298.257223563
    b = (1 - f) * a
    U1, U2 = math.atan((1 - f) * math.tan(math.radians(lat1))), math.atan((1 - f) * math.tan(math.radians(lat2)))
    L = math.radians(lon2 - lon1); lam = L
    sU1, cU1, sU2, cU2 = math.sin(U1), math.cos(U1), math.sin(U2), math.cos(U2)
    ss = cs = sig = sa = c2a = c2m = 0.0
    for _ in range(200):
        sl, cl = math.sin(lam), math.cos(lam)
        ss = math.hypot(cU2 * sl, cU1 * sU2 - sU1 * cU2 * cl)
        if ss == 0:
            return 0.0
        cs = sU1 * sU2 + cU1 * cU2 * cl
        sig = math.atan2(ss, cs)
        sa = cU1 * cU2 * sl / ss
        c2a = 1 - sa * sa
        c2m = cs - 2 * sU1 * sU2 / c2a if c2a else 0
        C = f / 16 * c2a * (4 + f * (4 - 3 * c2a))
        lam2 = L + (1 - C) * f * sa * (sig + C * ss * (c2m + C * cs * (-1 + 2 * c2m * c2m)))
        if abs(lam2 - lam) < 1e-12:
            lam = lam2; break
        lam = lam2
    u2 = c2a * (a * a - b * b) / (b * b)
    A = 1 + u2 / 16384 * (4096 + u2 * (-768 + u2 * (320 - 175 * u2)))
    B = u2 / 1024 * (256 + u2 * (-128 + u2 * (74 - 47 * u2)))
    ds = B * ss * (c2m + B / 4 * (cs * (-1 + 2 * c2m * c2m) - B / 6 * c2m * (-3 + 4 * ss * ss) * (-3 + 4 * c2m * c2m)))
    return b * A * (sig - ds)


def angdiff(a, b):
    """Signed difference a - b in degrees, in -180..180."""
    return (a - b + 180) % 360 - 180


def metres_per_degree(lat):
    """(metres per degree of latitude, metres per degree of longitude) at this latitude."""
    mlat = 111132.92 - 559.82 * math.cos(2 * math.radians(lat))
    mlon = 111412.84 * math.cos(math.radians(lat)) - 93.5 * math.cos(3 * math.radians(lat))
    return mlat, mlon


def drop(d):
    """How far the ground falls away at distance d: earth curve, eased by air bending the light."""
    return d * d * (1 - K) / (2 * R)


def ray_poly(xy, az):
    """Distance along a flat compass direction from the origin to where it first enters a footprint
    given in local metres (x east, y north). None if it misses."""
    dx, dy = math.sin(math.radians(az)), math.cos(math.radians(az))
    best = None
    for (x1, y1), (x2, y2) in zip(xy, xy[1:] + xy[:1]):
        ex, ey = x2 - x1, y2 - y1
        den = dx * ey - dy * ex
        if abs(den) < 1e-12:
            continue
        t = (x1 * ey - y1 * ex) / den
        u = (x1 * dy - y1 * dx) / den
        if t > 0.5 and -1e-9 <= u <= 1 + 1e-9:
            best = t if best is None else min(best, t)
    return best


def inside(xy_ring, x, y):
    c = False
    for (x1, y1), (x2, y2) in zip(xy_ring, xy_ring[1:] + xy_ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c
