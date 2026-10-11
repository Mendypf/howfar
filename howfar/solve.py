"""From a line of sight (bearing + angle above level) to what it hits and how far: buildings, ground, named peaks.
Never trusts one ray: a small fan of lines around the asked direction votes."""
import math
from . import mapdata, peaks, terrain
from .geo import ray_poly, angdiff, dest, vincenty

DEFAULT_H = 9.0          # metres assumed for a building with no height on the map


def buildings_hit(bs, az, el, eye_above_ground, spread=1.5, n=13, pitches=(-0.4, -0.2, 0.0)):
    """Which footprints the fan of lines lands on. -> ranked [{name, id, dist_m, height_m, votes, bearing}]."""
    votes = {}
    total = 0
    for k in range(n):
        da = -spread + 2 * spread * k / (n - 1) if n > 1 else 0
        a = az + da
        hits = sorted(((ray_poly(b["xy"], a), b) for b in bs), key=lambda h: (h[0] is None, h[0] or 0))
        hits = [(t, b) for t, b in hits if t is not None]
        for dp in pitches:
            total += 1
            for t, b in hits:
                if eye_above_ground + t * math.tan(math.radians(el + dp)) <= (b["h"] or DEFAULT_H):
                    key = b["id"]
                    v = votes.setdefault(key, {"name": b["name"], "id": key, "dist_m": t, "height_m": b["h"], "votes": 0,
                                                "bearing": b["brg"], "floors": b.get("floors"), "colour": b.get("colour"),
                                                "material": b.get("material"), "roof": b.get("roof"), "class": b.get("class"),
                                                "dists": []})
                    v["votes"] += 1; v["dists"].append(t); v["dist_m"] = min(v["dist_m"], t)
                    break
    out = []
    for v in votes.values():
        ds = sorted(v["dists"]); v["dist_m"] = round(ds[len(ds) // 2]); v["dist_min_m"] = round(ds[0]); v["dist_max_m"] = round(ds[-1])
        v["share"] = round(v["votes"] / total, 2); del v["dists"]
        v["bearing"] = round(v["bearing"], 1)
        out.append(v)
    out.sort(key=lambda v: -v["votes"])
    return out


def shortlist_wide(bs, az, el, eye_above_ground, half=15.0, pitches=(-1.5, 0.0, 1.5)):
    """For a ROUGH heading (phone compass): sweep +-half degrees in 1-degree steps and rank the footprints whose
    roof rises above the line, nearest to the asked direction first. Proven on the tower set: right one in the
    top 3 with the compass up to 13 degrees off. -> [{name, id, dist_m, height_m, bearing, off_deg}]"""
    cand, show = {}, {}
    for da in range(-int(half), int(half) + 1):
        a = az + da
        hits = sorted(((ray_poly(b["xy"], a), b) for b in bs), key=lambda h: (h[0] is None, h[0] or 0))
        hits = [(t, b) for t, b in hits if t is not None]
        # skyline mode: which roofs show above everything in front of them along this line
        runmax = -90.0
        for t, b in hits:
            e_top = math.degrees(math.atan2((b["h"] or DEFAULT_H) - eye_above_ground, t))
            if e_top > runmax:
                v = show.setdefault(b["id"], [0.0, t, b])
                v[0] += (e_top - max(runmax, 0)) * math.exp(-(da / 10) ** 2); v[1] = min(v[1], t)
                runmax = e_top
        # tilt mode: the first roof the line itself cannot pass over
        for dp in pitches:
            for t, b in hits:
                if eye_above_ground + t * math.tan(math.radians(el + dp)) <= (b["h"] or DEFAULT_H):
                    s = math.hypot(da, 3 * dp)
                    if b["id"] not in cand or s < cand[b["id"]][0]:
                        cand[b["id"]] = (s, t, b)
                    break
    rank = {}
    for i, (s, t, b) in enumerate(sorted(cand.values(), key=lambda v: v[0])):
        rank[b["id"]] = [i + 1, None, s, t, b]
    for i, (sc, t, b) in enumerate(sorted(show.values(), key=lambda v: -v[0])):
        r = rank.setdefault(b["id"], [None, None, None, t, b])
        r[1] = i + 1; r[3] = min(r[3], t)
    out = []
    for rt, rs, s, t, b in sorted(rank.values(), key=lambda r: min(x for x in (r[0], r[1]) if x is not None)):
        out.append({"name": b["name"], "id": b["id"], "dist_m": round(t), "height_m": b["h"], "height_known": b["h_known"], "floors": b.get("floors"),
                    "bearing": round(b["brg"], 1), "off_deg": round(s, 1) if s is not None else None, "rank_by_line": rt, "rank_by_skyline": rs,
                    "colour": b.get("colour"), "material": b.get("material"), "class": b.get("class")})
    return out


def ground_hit(lat, lon, az, el, h_eye, dmax=250000):
    hits = []
    for da in (-0.6, -0.3, 0, 0.3, 0.6):
        for dp in (-0.35, -0.2, -0.1):
            h = terrain.terrain_hit(lat, lon, az + da, el + dp, dmax, h_eye)
            if h:
                hits.append(h)
    if not hits:
        return None
    hits.sort(key=lambda h: h[0])
    m = hits[len(hits) // 2]
    return {"dist_m": round(m[0]), "range_m": [round(hits[0][0]), round(hits[-1][0])], "lines_hit": f"{len(hits)} of 15",
            "lat": round(m[1], 5), "lon": round(m[2], 5), "ground_m": round(m[3])}


def peaks_near_line(lat, lon, az, el, h_eye, half=3.0, dmax=230000, el_tol=1.5):
    ps = peaks.in_wedge(lat, lon, az, half, dmax)
    ps = peaks.with_view_angles(ps, lat, lon, h_eye, check_hidden=False)
    short = [p for p in ps if abs(p["ang"] - el) <= el_tol]
    short = peaks.with_view_angles(short, lat, lon, h_eye, check_hidden=True, max_check=12)
    seen = [p for p in short if not p.get("hidden")]
    seen.sort(key=lambda p: -p["links"])
    hidden = [p for p in short if p.get("hidden")]
    fmt = lambda p: {"name": p["name"], "dist_km": round(p["dist"] / 1000, 2), "bearing": round(p["brg"], 1), "summit_m": round(p["ele"]) if p["ele"] else None,
                     "angle_above_level": round(p["ang"], 2), "wiki_pages": p["links"], "wikidata": p["wikidata"], "lat": p["lat"], "lon": p["lon"]}
    return {"candidates": [fmt(p) for p in seen[:6]], "hidden_behind_nearer_ground": [fmt(p)["name"] for p in hidden[:6]],
            "named_mountains_in_wedge": len(ps)}


def aim(lat, lon, bearing, elevation, kind="any", alt_hint=None, gps_err_m=None, dmax_buildings=3000, wide_half=15.0):
    """The whole lookup for one line of sight. kind: building | mountain | ground | any."""
    h_eye, ground = terrain.eye_height(lat, lon, alt_hint)
    eye_above = h_eye - ground
    out = {"line": {"bearing": round(bearing, 2), "elevation": round(elevation, 2)}, "eye_m_above_sea": round(h_eye, 1), "eye_m_above_ground": round(eye_above, 1)}
    gps = gps_err_m if gps_err_m else 10.0
    if kind in ("building", "any"):
        bs = [b for b in mapdata.buildings(lat, lon, dmax_buildings) if not b["part"]]
        bb = buildings_hit(bs, bearing, elevation, eye_above)
        out["buildings"] = bb[:6]
        out["buildings_in_area"] = len(bs)
        out["shortlist_if_heading_is_rough"] = shortlist_wide(bs, bearing, elevation, eye_above, half=wide_half)[:8]
    if kind in ("ground", "mountain", "any"):
        out["ground"] = ground_hit(lat, lon, bearing, elevation, h_eye)
    if kind in ("mountain", "any") and elevation > -2:
        try:
            out["peaks"] = peaks_near_line(lat, lon, bearing, elevation, h_eye)
        except Exception as ex:
            out["peaks"] = {"error": str(ex)[:120]}
    # a plain-words verdict the agent can lean on
    verdict = None
    b = out.get("buildings") or []
    if b and b[0]["share"] >= 0.5:
        top = b[0]
        lo = max(5, top["dist_min_m"] - gps); hi = top["dist_max_m"] + gps
        verdict = {"what": top["name"] or "unnamed building", "dist_m": top["dist_m"], "range_m": [round(lo), round(hi)], "basis": "map footprint the lines land on"}
        if len(b) > 1 and b[1]["share"] >= 0.25 and abs(b[1]["dist_m"] - top["dist_m"]) > 0.25 * top["dist_m"]:
            verdict["ambiguous_with"] = {"what": b[1]["name"] or "unnamed building", "dist_m": b[1]["dist_m"]}
    elif b and sum(v["share"] for v in b[:3]) >= 0.5:
        ds = [v["dist_m"] for v in b[:3]]
        verdict = {"what": "one of several buildings", "dist_m": round(sum(ds) / len(ds)), "range_m": [round(min(ds) - gps), round(max(ds) + gps)],
                   "basis": "lines split between neighbouring footprints", "ambiguous": True}
    pk = (out.get("peaks") or {}).get("candidates") or []
    if pk and kind in ("mountain", "any") and (verdict is None or kind == "mountain"):
        p = pk[0]
        verdict = {"what": p["name"], "dist_km": p["dist_km"], "range_km": [round(p["dist_km"] * 0.98, 1), round(p["dist_km"] * 1.02, 1)],
                   "basis": "named summit nearest the line, best known first" + (f"; also possible: {pk[1]['name']} {pk[1]['dist_km']} km" if len(pk) > 1 else "")}
    g = out.get("ground")
    if verdict is None and g:
        verdict = {"what": "the ground the line touches (no mapped building or named peak there)", "dist_m": g["dist_m"], "range_m": g["range_m"], "basis": "terrain"}
    if verdict is None:
        verdict = {"what": None, "abstain": True, "basis": "the line hits nothing on the map (sky, or a thing the map does not have); say so instead of guessing"}
    out["verdict"] = verdict
    return out
