"""Named mountains from Wikidata (no key), with the two traps already handled: heights come back in
metres (normalised), and the summit point of a big mountain can differ by 100-200 m between sources."""
import math, time
import requests
from .cache import UA
from .geo import dest, inv, angdiff, drop
from . import terrain

SPARQL = "https://query.wikidata.org/sparql"
HDR = {**UA, "Accept": "application/sparql-results+json"}
Q_BOX = """SELECT ?m ?mLabel ?lat ?lon ?ele ?links WHERE {
  SERVICE wikibase:box { ?m wdt:P625 ?loc . bd:serviceParam wikibase:cornerSouthWest "Point(%f %f)"^^geo:wktLiteral ; wikibase:cornerNorthEast "Point(%f %f)"^^geo:wktLiteral . }
  ?m wdt:P31/wdt:P279* wd:Q8502 . ?m p:P625/psv:P625 [ wikibase:geoLatitude ?lat ; wikibase:geoLongitude ?lon ] .
  OPTIONAL { ?m p:P2044/psn:P2044/wikibase:quantityAmount ?ele } ?m wikibase:sitelinks ?links .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" } } ORDER BY DESC(?links) LIMIT 400"""


def _query(q):
    for attempt in range(3):
        try:
            r = requests.get(SPARQL, params={"query": q}, headers=HDR, timeout=70)
            if r.status_code == 200:
                return r.json()["results"]["bindings"]
        except (requests.RequestException, ValueError):
            pass
        time.sleep(2 + 3 * attempt)
    raise RuntimeError("Wikidata did not answer (mountain list unavailable right now)")


def in_wedge(lat, lon, az, half, dmax):
    """Named mountains within +-half degrees of bearing az, out to dmax metres, best known first."""
    pts = [(lat, lon)] + [dest(lat, lon, az + a, dmax) for a in (-half, -half / 2, 0, half / 2, half)]
    s, w = min(a for a, _ in pts), min(b for _, b in pts); n, e = max(a for a, _ in pts), max(b for _, b in pts)
    seen, out = set(), []
    for b in _query(Q_BOX % (w, s, e, n)):
        if b["m"]["value"] in seen:
            continue
        seen.add(b["m"]["value"])
        la, lo = float(b["lat"]["value"]), float(b["lon"]["value"])
        d, bb = inv(lat, lon, la, lo)
        if d > 300 and abs(angdiff(bb, az)) <= half and d <= dmax:
            out.append({"name": b["mLabel"]["value"], "lat": la, "lon": lo, "dist": d, "brg": bb, "links": int(b["links"]["value"]),
                        "ele": float(b["ele"]["value"]) if "ele" in b else None, "wikidata": b["m"]["value"].rsplit("/", 1)[-1]})
    out.sort(key=lambda p: -p["links"])
    return out


def around(lat, lon, dmax, limit=40):
    """Best-known named mountains in every direction (for the agent's landmark list)."""
    pts = [dest(lat, lon, a, dmax) for a in range(0, 360, 45)]
    s, w = min(a for a, _ in pts), min(b for _, b in pts); n, e = max(a for a, _ in pts), max(b for _, b in pts)
    seen, out = set(), []
    for b in _query(Q_BOX % (w, s, e, n)):
        if b["m"]["value"] in seen:
            continue
        seen.add(b["m"]["value"])
        la, lo = float(b["lat"]["value"]), float(b["lon"]["value"])
        d, bb = inv(lat, lon, la, lo)
        if 300 < d <= dmax:
            out.append({"name": b["mLabel"]["value"], "lat": la, "lon": lo, "dist": d, "brg": bb, "links": int(b["links"]["value"]),
                        "ele": float(b["ele"]["value"]) if "ele" in b else None, "wikidata": b["m"]["value"].rsplit("/", 1)[-1]})
    out.sort(key=lambda p: -p["links"])
    return out[:limit]


def with_view_angles(ps, lat, lon, h_eye, check_hidden=True, max_check=25):
    """Add the angle each summit stands above level from the eye, and whether nearer ground hides it."""
    for p in ps:
        if p["ele"] is None:
            p["ele"] = terrain.elev(p["lat"], p["lon"], terrain.zoom_for(p["dist"]))
        p["ang"] = math.degrees(math.atan2(p["ele"] - h_eye - drop(p["dist"]), p["dist"]))
    if check_hidden:
        for p in ps[:max_check]:
            S, H, A = terrain.profile(lat, lon, p["brg"], p["dist"] * 0.97, h_eye)
            block = float(A.max()) if len(A) else -90
            p["clear"] = p["ang"] - block
            p["hidden"] = p["clear"] <= -0.5
    return ps


def find_named(name, lat, lon, radius_m=300000):
    """One named mountain by name, nearest to the user. -> dict or None."""
    try:
        r = requests.get("https://www.wikidata.org/w/api.php", params={"action": "wbsearchentities", "search": name, "language": "en",
                                                                         "format": "json", "limit": 8}, headers=UA, timeout=30).json()
    except Exception:
        return None
    ids = [s["id"] for s in r.get("search", [])]
    if not ids:
        return None
    q = """SELECT ?m ?mLabel ?lat ?lon ?ele ?links WHERE { VALUES ?m { %s }
      ?m p:P625/psv:P625 [ wikibase:geoLatitude ?lat ; wikibase:geoLongitude ?lon ] .
      OPTIONAL { ?m p:P2044/psn:P2044/wikibase:quantityAmount ?ele } ?m wikibase:sitelinks ?links .
      SERVICE wikibase:label { bd:serviceParam wikibase:language "en" } }""" % " ".join("wd:" + i for i in ids)
    best = None
    for b in _query(q):
        la, lo = float(b["lat"]["value"]), float(b["lon"]["value"])
        d, bb = inv(lat, lon, la, lo)
        if d <= radius_m and (best is None or d < best["dist"]):
            best = {"name": b["mLabel"]["value"], "lat": la, "lon": lo, "dist": d, "brg": bb, "links": int(b["links"]["value"]),
                    "ele": float(b["ele"]["value"]) if "ele" in b else None, "wikidata": b["m"]["value"].rsplit("/", 1)[-1]}
    return best
