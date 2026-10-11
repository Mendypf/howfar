"""Map tiles straight out of Overture Maps' public open-data files (PMTiles on S3) with plain HTTP range
requests, plus a small decoder for the vector tiles inside. No key, no account.
Data: (c) Overture Maps Foundation and contributors, ODbL / CDLA-Permissive; see README for credits."""
import gzip, math, os, struct, time
import requests
from .cache import CACHE, UA

S3 = "https://overturemaps-extras-us-west-2.s3.us-west-2.amazonaws.com/tiles/{release}/{theme}.pmtiles"
STAC = "https://stac.overturemaps.org/catalog.json"
_release = None
_ranges = {}
STATS = {"tiles": 0, "bytes": 0, "secs": 0.0}


# ---------- PMTiles ----------
def release():
    global _release
    if _release is None:
        _release = os.environ.get("HOWFAR_OVERTURE_RELEASE")
    if _release is None:
        fn = os.path.join(CACHE, "overture_release.txt")
        if os.path.exists(fn) and time.time() - os.path.getmtime(fn) < 7 * 86400:
            _release = open(fn).read().strip()
        else:
            _release = requests.get(STAC, headers=UA, timeout=30).json()["latest"]
            open(fn, "w").write(_release)
    return _release


def url(theme):
    return S3.format(release=release(), theme=theme)


def _rng(u, off, ln):
    key = (u, off, ln)
    if key not in _ranges:
        for attempt in range(4):
            try:
                r = requests.get(u, headers={**UA, "Range": f"bytes={off}-{off + ln - 1}"}, timeout=60)
                if r.status_code in (200, 206):
                    _ranges[key] = r.content
                    break
            except requests.RequestException:
                pass
            time.sleep(1.5 * (attempt + 1))
        else:
            raise RuntimeError(f"range read failed for {u}")
    return _ranges[key]


def _header(u):
    b = _rng(u, 0, 127)
    if b[:7] != b"PMTiles" or b[7] != 3:
        raise RuntimeError("not a PMTiles v3 file: " + u)
    f = struct.unpack("<11Q", b[8:96])
    return dict(root=(f[0], f[1]), leaf_off=f[4], data_off=f[6], internal=b[97], tilecomp=b[98], minz=b[100], maxz=b[101])


def _unz(b, comp):
    return gzip.decompress(b) if comp == 2 else b


def _varint(b, i):
    r = s = 0
    while True:
        c = b[i]; i += 1
        r |= (c & 0x7F) << s
        if c < 0x80:
            return r, i
        s += 7


def _directory(b):
    n, i = _varint(b, 0)
    ids, runs, lens, offs = [], [], [], []
    last = 0
    for _ in range(n):
        v, i = _varint(b, i); last += v; ids.append(last)
    for _ in range(n):
        v, i = _varint(b, i); runs.append(v)
    for _ in range(n):
        v, i = _varint(b, i); lens.append(v)
    for k in range(n):
        v, i = _varint(b, i)
        offs.append(offs[k - 1] + lens[k - 1] if (v == 0 and k > 0) else v - 1)
    return ids, runs, lens, offs


def tile_id(z, x, y):
    acc = sum((1 << t) * (1 << t) for t in range(z))
    xy, d, s = [x, y], 0, (1 << z) >> 1
    while s > 0:
        rx, ry = (1 if xy[0] & s else 0), (1 if xy[1] & s else 0)
        d += s * s * ((3 * rx) ^ ry)
        if ry == 0:
            if rx == 1:
                xy[0], xy[1] = s - 1 - xy[0], s - 1 - xy[1]
            xy[0], xy[1] = xy[1], xy[0]
        s >>= 1
    return acc + d


def raw_tile(theme, z, x, y):
    """Bytes of one vector tile (decompressed), or None where the file has no tile."""
    u = url(theme)
    h = _header(u)
    tid = tile_id(z, x, y)
    off, ln = h["root"]
    base = 0
    for _ in range(4):
        ids, runs, lens, offs = _directory(_unz(_rng(u, base + off, ln), h["internal"]))
        lo, hi, k = 0, len(ids) - 1, -1
        while lo <= hi:
            mid = (lo + hi) // 2
            if ids[mid] <= tid:
                k = mid; lo = mid + 1
            else:
                hi = mid - 1
        if k < 0:
            return None
        if runs[k] == 0:
            base, off, ln = h["leaf_off"], offs[k], lens[k]
            continue
        if tid < ids[k] + runs[k]:
            return _unz(_rng(u, h["data_off"] + offs[k], lens[k]), h["tilecomp"])
        return None
    return None


# ---------- Mapbox Vector Tile decoder ----------
def _fields(b):
    i, n = 0, len(b)
    while i < n:
        key, i = _varint(b, i)
        f, w = key >> 3, key & 7
        if w == 0:
            v, i = _varint(b, i)
        elif w == 1:
            v = b[i:i + 8]; i += 8
        elif w == 2:
            ln, i = _varint(b, i); v = b[i:i + ln]; i += ln
        elif w == 5:
            v = b[i:i + 4]; i += 4
        else:
            raise ValueError("wire type %d" % w)
        yield f, w, v


def _zz(n):
    return (n >> 1) ^ -(n & 1)


def _value(b):
    for f, w, v in _fields(b):
        if f == 1: return v.decode("utf-8", "replace")
        if f == 2: return struct.unpack("<f", v)[0]
        if f == 3: return struct.unpack("<d", v)[0]
        if f in (4, 5): return v
        if f == 6: return _zz(v)
        if f == 7: return bool(v)
    return None


def _packed(b):
    out, i = [], 0
    while i < len(b):
        v, i = _varint(b, i); out.append(v)
    return out


def _geom(cmds):
    rings, cur, x, y, i = [], [], 0, 0, 0
    while i < len(cmds):
        c = cmds[i]; i += 1
        op, cnt = c & 7, c >> 3
        if op == 7:
            if cur: rings.append(cur); cur = []
            continue
        for _ in range(cnt):
            x += _zz(cmds[i]); y += _zz(cmds[i + 1]); i += 2
            if op == 1 and cur:
                rings.append(cur); cur = []
            cur.append((x, y))
    if cur: rings.append(cur)
    return rings


def decode(buf):
    """-> {layer: [ {type, props, rings (tile units), extent} ]}"""
    if buf[:2] == b"\x1f\x8b":
        buf = gzip.decompress(buf)
    out = {}
    for f, w, v in _fields(buf):
        if f != 3: continue
        name, keys, vals, feats, extent = None, [], [], [], 4096
        for f2, w2, v2 in _fields(v):
            if f2 == 1: name = v2.decode()
            elif f2 == 2: feats.append(v2)
            elif f2 == 3: keys.append(v2.decode())
            elif f2 == 4: vals.append(_value(v2))
            elif f2 == 5: extent = v2
        L = []
        for fb in feats:
            tags, typ, g = [], 0, []
            for f3, w3, v3 in _fields(fb):
                if f3 == 2: tags = _packed(v3)
                elif f3 == 3: typ = v3
                elif f3 == 4: g = _packed(v3)
            L.append({"type": typ, "props": {keys[tags[k]]: vals[tags[k + 1]] for k in range(0, len(tags) - 1, 2)},
                      "rings": _geom(g), "extent": extent})
        out[name] = L
    return out


# ---------- tile maths + cached access ----------
def xy(lat, lon, z):
    n = 2 ** z
    return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n


def to_ll(z, tx, ty, px, py, extent):
    n = 2 ** z
    lon = (tx + px / extent) / n * 360 - 180
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (ty + py / extent) / n))))
    return lat, lon


def tile(theme, z, x, y):
    """Decoded Overture tile, cached on disk under the cache folder."""
    fn = os.path.join(CACHE, f"ov_{release()}_{theme}_{z}_{x}_{y}.mvt")
    if os.path.exists(fn):
        raw = open(fn, "rb").read()
    else:
        t0 = time.time()
        raw = raw_tile(theme, z, x, y) or b""
        STATS["tiles"] += 1; STATS["bytes"] += len(raw); STATS["secs"] += time.time() - t0
        open(fn, "wb").write(raw)
    return decode(raw) if raw else {}


def tiles_around(lat, lon, radius_m, z):
    """Tile coordinates covering a circle of radius_m around a point."""
    from .geo import dest
    pts = [(lat, lon)] + [dest(lat, lon, b, radius_m) for b in range(0, 360, 45)]
    xs, ys = zip(*[xy(a, b, z) for a, b in pts])
    return [(x, y) for x in range(int(min(xs)), int(max(xs)) + 1) for y in range(int(min(ys)), int(max(ys)) + 1)]
