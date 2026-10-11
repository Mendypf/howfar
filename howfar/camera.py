"""Lens maths: a spot in the picture <-> a direction in the world."""
import math


def half_fov(w, h, f35):
    """Half field of view (deg) across and down, from the 35 mm-equivalent focal length."""
    diag = math.hypot(w, h)
    return (math.degrees(math.atan(21.633 * w / diag / f35)), math.degrees(math.atan(21.633 * h / diag / f35)))


def cam(w, h, f35, x, y):
    """Picture spot (x, y as fractions from the top-left) -> normalised camera-plane coordinates."""
    hh, vh = half_fov(w, h, f35)
    return (2 * x - 1) * math.tan(math.radians(hh)), (1 - 2 * y) * math.tan(math.radians(vh))


def look(xn, yn, th):
    """Where a camera-plane spot points for a camera tilted up by th (radians):
    (degrees right of the camera heading, degrees above level)."""
    c, s = math.cos(th), math.sin(th)
    f = c - yn * s
    return math.degrees(math.atan2(xn, f)), math.degrees(math.atan2(yn * c + s, math.hypot(xn, f)))


def solve_pose(w, h, f35, ax, ay, a_brg, a_el):
    """Camera heading and tilt from ONE known thing: its spot in the picture (ax, ay), its true bearing
    and its true angle above level. -> (heading deg, tilt radians)."""
    xn, yn = cam(w, h, f35, ax, ay)
    lo, hi = math.radians(-70), math.radians(70)
    for _ in range(60):
        mid = (lo + hi) / 2
        if look(xn, yn, mid)[1] < a_el:
            lo = mid
        else:
            hi = mid
    th = (lo + hi) / 2
    return (a_brg - look(xn, yn, th)[0]) % 360, th


def aim(w, h, f35, heading, tilt_deg, x, y):
    """Bearing and elevation of a picture spot, given the camera heading and tilt (deg)."""
    off, el = look(*cam(w, h, f35, x, y), math.radians(tilt_deg))
    return (heading + off) % 360, el
