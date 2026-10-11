"""Ground heights from the free AWS terrain tiles (Terrarium PNGs, no key), and lines of sight over them.
Data: Mapzen / AWS Open Data terrain tiles (see README for credits)."""
import io, math, os, time
import numpy as np
import requests
from PIL import Image
from .cache import CACHE, UA
from .geo import dest, drop

_tiles = {}


def _tile(z, x, y):
    key = (z, x, y)
    if key in _tiles:
        return _tiles[key]
    fn = os.path.join(CACHE, f"terr_{z}_{x}_{y}.npy")
    if os.path.exists(fn):
        arr = np.load(fn)
    else:
        u = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
        for attempt in range(4):
            try:
                r = requests.get(u, headers=UA, timeout=40)
                if r.status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(1.5 * (attempt + 1))
        else:
            raise RuntimeError(f"terrain tile failed {u}")
        px = np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB"), dtype=np.float32)
        arr = px[..., 0] * 256 + px[..., 1] + px[..., 2] / 256 - 32768
        np.save(fn, arr)
    _tiles[key] = arr
    return arr


def elev(lat, lon, z=12):
    """Ground height (m above sea level) at a point, bilinear from a tile. z=13 near, 12 mid, 10 far."""
    n = 2 ** z
    xf = (lon + 180) / 360 * n
    yf = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    x0, y0 = int(math.floor(xf)), int(math.floor(yf))
    t = _tile(z, x0 % n, y0)
    px, py = (xf - x0) * 256 - 0.5, (yf - y0) * 256 - 0.5
    i, j = min(max(int(math.floor(px)), 0), 254), min(max(int(math.floor(py)), 0), 254)
    fx, fy = min(max(px - i, 0), 1), min(max(py - j, 0), 1)
    return float(t[j, i] * (1 - fx) * (1 - fy) + t[j, i + 1] * fx * (1 - fy) + t[j + 1, i] * (1 - fx) * fy + t[j + 1, i + 1] * fx * fy)


def zoom_for(d):
    return 13 if d < 6000 else 12 if d < 25000 else 10


def steps(dmax):
    s, out = 30.0, []
    while s < dmax:
        out.append(s)
        s += max(25.0, s * 0.006)
    return out


def profile(lat, lon, brg, dmax, h_eye):
    """Along one bearing: distances, ground heights, and the angle above/below level at which that ground appears."""
    S = steps(dmax)
    H = [elev(*dest(lat, lon, brg, s), z=zoom_for(s)) for s in S]
    A = [math.degrees(math.atan2(h - h_eye - drop(s), s)) for s, h in zip(S, H)]
    return np.array(S), np.array(H), np.array(A)


def terrain_hit(lat, lon, brg, pitch, dmax, h_eye):
    """First ground the line of sight touches. (distance m, lat, lon, ground height) or None (sky)."""
    S, H, A = profile(lat, lon, brg, dmax, h_eye)
    idx = np.nonzero(A >= pitch)[0]
    if len(idx) == 0:
        return None
    i = int(idx[0])
    s = S[i]
    if i > 0 and A[i] != A[i - 1]:
        t = (pitch - A[i - 1]) / (A[i] - A[i - 1])
        s = S[i - 1] + t * (S[i] - S[i - 1])
    la, lo = dest(lat, lon, brg, s)
    return float(s), la, lo, float(H[i])


def eye_height(lat, lon, alt_hint=None):
    """Height of the camera above sea level: ground + 1.6 m, or the photo's own altitude when it says the
    photographer stood well above the ground (upper floor, viewpoint)."""
    g = elev(lat, lon, 13)
    h = g + 1.6
    if alt_hint is not None and alt_hint - g > 6:
        h = alt_hint + 1.0
    return h, g
