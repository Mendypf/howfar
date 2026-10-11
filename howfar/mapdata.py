"""Buildings, streets and named places around a point, from Overture Maps open data (read tile by tile)."""
import math
from . import tiles as T
from .geo import metres_per_degree, inv, angdiff

ROAD_SKIP = ("footway", "steps", "cycleway", "path", "pedestrian", "track", "bridleway")


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def buildings(lat, lon, radius_m):
    """Footprints in local metres (x east, y north) with heights. Parts are kept apart (flag `part`)."""
    mlat, mlon = metres_per_degree(lat)
    out, n = [], 0
    for tx, ty in T.tiles_around(lat, lon, radius_m, 14):
        t = T.tile("buildings", 14, tx, ty)
        parents = {f["props"].get("id"): f["props"] for f in t.get("building", [])}
        for layer in ("building", "building_part"):
            for f in t.get(layer, []):
                pr = f["props"]
                par = parents.get(pr.get("building_id"), {}) if layer == "building_part" else {}
                h = _num(pr.get("height"))
                floors = _num(pr.get("num_floors"))
                est = h if h and h > 1 else (3.2 * floors if floors and floors > 0 else None)
                for ring in f["rings"]:
                    if len(ring) < 3:
                        continue
                    ll = [T.to_ll(14, tx, ty, px, py, f["extent"]) for px, py in ring]
                    xy = [((b - lon) * mlon, (a - lat) * mlat) for a, b in ll]
                    cx, cy = sum(p[0] for p in xy) / len(xy), sum(p[1] for p in xy) / len(xy)
                    d = math.hypot(cx, cy)
                    if d > radius_m * 1.3:
                        continue
                    n += 1
                    out.append({"id": f"b{n}", "name": pr.get("@name") or par.get("@name"), "xy": xy, "cx": cx, "cy": cy,
                                "dist": d, "brg": math.degrees(math.atan2(cx, cy)) % 360,
                                "h": est, "h_known": bool(h and h > 1), "floors": floors,
                                "colour": pr.get("facade_color") or par.get("facade_color"),
                                "material": pr.get("facade_material") or par.get("facade_material"),
                                "roof": pr.get("roof_shape") or par.get("roof_shape"),
                                "class": pr.get("class") or pr.get("subtype") or par.get("class"), "part": layer == "building_part"})
    return out


def streets(lat, lon, radius_m):
    """Road segments in local metres: [{name, class, xy}]."""
    mlat, mlon = metres_per_degree(lat)
    out = []
    for tx, ty in T.tiles_around(lat, lon, radius_m, 14):
        for f in T.tile("transportation", 14, tx, ty).get("segment", []):
            pr = f["props"]
            cl = pr.get("class")
            if pr.get("subtype") != "road" or cl in ROAD_SKIP:
                continue
            for ring in f["rings"]:
                pts = [T.to_ll(14, tx, ty, px, py, f["extent"]) for px, py in ring]
                xy = [((b - lon) * mlon, (a - lat) * mlat) for a, b in pts]
                if len(xy) >= 2:
                    out.append({"name": pr.get("@name"), "class": cl, "xy": xy})
    return out


def places(lat, lon, radius_m):
    """Named places (shops, venues) as points in local metres: [{name, category, x, y, dist, brg}]."""
    mlat, mlon = metres_per_degree(lat)
    out = []
    for tx, ty in T.tiles_around(lat, lon, radius_m, 14):
        t = T.tile("places", 14, tx, ty)
        for layer, feats in t.items():
            for f in feats:
                pr = f["props"]
                nm = pr.get("@name") or pr.get("name")
                if not nm or not f["rings"] or not f["rings"][0]:
                    continue
                a, b = T.to_ll(14, tx, ty, f["rings"][0][0][0], f["rings"][0][0][1], f["extent"])
                x, y = (b - lon) * mlon, (a - lat) * mlat
                d = math.hypot(x, y)
                if d > radius_m:
                    continue
                cat = pr.get("@category") or pr.get("category") or pr.get("categories") or pr.get("primary")
                out.append({"name": nm, "category": cat, "x": x, "y": y, "dist": d, "brg": math.degrees(math.atan2(x, y)) % 360})
    out.sort(key=lambda p: p["dist"])
    return out


def nearest_roads(lat, lon, radius_m=120, limit=3):
    """Roads closest to the user, each with its two directions. The first one is almost always the road
    the user stands on; its bearings are exact where a compass is not."""
    found = []
    for s in streets(lat, lon, radius_m):
        best = None
        for (x0, y0), (x1, y1) in zip(s["xy"], s["xy"][1:]):
            ex, ey = x1 - x0, y1 - y0
            L2 = ex * ex + ey * ey
            if L2 < 1e-6:
                continue
            u = max(0.0, min(1.0, -(x0 * ex + y0 * ey) / L2))
            px, py = x0 + u * ex, y0 + u * ey
            d = math.hypot(px, py)
            if best is None or d < best[0]:
                b = math.degrees(math.atan2(ex, ey)) % 360
                best = (d, b)
        if best:
            found.append({"name": s["name"], "class": s["class"], "distance_m": round(best[0], 1),
                          "bearings": [round(best[1], 1), round((best[1] + 180) % 360, 1)]})
    found.sort(key=lambda r: r["distance_m"])
    merged = []
    for r in found:
        if any(m["name"] == r["name"] and abs(angdiff(m["bearings"][0], r["bearings"][0])) % 180 < 8 for m in merged):
            continue
        merged.append(r)
        if len(merged) >= limit:
            break
    return merged


def snap_to_road(lat, lon, max_move_m=60):
    """GPS drift puts people inside buildings. If the point sits inside a footprint, move it to the closest point on
    the nearest road (people stand on streets and squares). -> (lat, lon, moved_m, road name or None)."""
    from .geo import inside
    bs = buildings(lat, lon, 80)
    if not any(inside(b["xy"], 0.0, 0.0) for b in bs if not b["part"]):
        return lat, lon, 0.0, None
    best = None
    for s in streets(lat, lon, 150):
        for (x0, y0), (x1, y1) in zip(s["xy"], s["xy"][1:]):
            ex, ey = x1 - x0, y1 - y0
            L2 = ex * ex + ey * ey
            if L2 < 1e-6:
                continue
            u = max(0.0, min(1.0, -(x0 * ex + y0 * ey) / L2))
            px, py = x0 + u * ex, y0 + u * ey
            d = math.hypot(px, py)
            if best is None or d < best[0]:
                best = (d, px, py, s["name"])
    if best is None or best[0] > max_move_m:
        return lat, lon, 0.0, None
    mlat, mlon = metres_per_degree(lat)
    return lat + best[2] / mlat, lon + best[1] / mlon, round(best[0], 1), best[3]


def named_buildings(lat, lon, radius_m, min_height=None):
    """Named (or tall) buildings around the user, as landmark candidates with bearings."""
    out = []
    for b in buildings(lat, lon, radius_m):
        if b["part"]:
            continue
        if b["name"] or (min_height and b["h"] and b["h"] >= min_height):
            out.append({"name": b["name"], "dist_m": round(b["dist"]), "bearing": round(b["brg"], 1), "height_m": b["h"], "id": b["id"]})
    out.sort(key=lambda b: (-(b["height_m"] or 0), b["dist_m"]))
    return out
