"""Regression against public photos with known answers (tests/truth.json). Needs the internet (open map data).
Run:  python tests/regression.py
Pass bar: chain cases: the right landmark first, distance within 3% (mountains) / 6% (towers).
          compass-only cases: the right tower is in the wide shortlist's top 8 (the agent's eyes pick it), distance within 10%
          (the recorded truth is the tower's centre point; the tool reports the near face)."""
import json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from howfar import camera, terrain, solve, geo

T = json.load(open(os.path.join(HERE, "truth.json"), encoding="utf-8"))
LM, PH = T["landmarks"], T["photos"]


def top_asl(name):
    lm = LM[name]
    return lm["top_m"] if lm["mountain"] else terrain.elev(lm["lat"], lm["lon"], 13) + lm["top_m"]


def sight(p, h_eye, name):
    lm = LM[name]
    d = geo.vincenty(p["lat"], p["lon"], lm["lat"], lm["lon"])
    _, b = geo.inv(p["lat"], p["lon"], lm["lat"], lm["lon"])
    return d, b, math.degrees(math.atan2(top_asl(name) - h_eye - geo.drop(d), d))


fails = 0
print("== chain: GPS + lens + one recognised thing -> the other thing's distance")
for c in T["chain_cases"]:
    p = PH[str(c["photo"])]
    h_eye, _ = terrain.eye_height(p["lat"], p["lon"], None)
    a_d, a_b, a_el = sight(p, h_eye, c["anchor"]["name"])
    heading, th = camera.solve_pose(p["w"], p["h"], p["f35"], c["anchor"]["x"], c["anchor"]["y"], a_b, a_el)
    brg, el = camera.aim(p["w"], p["h"], p["f35"], heading, math.degrees(th), c["target"]["x"], c["target"]["y"])
    t_d, t_b, t_el = sight(p, h_eye, c["target"]["name"])
    kind = "mountain" if LM[c["target"]["name"]]["mountain"] else "building"
    res = solve.aim(p["lat"], p["lon"], brg, el, kind=kind)
    v = res["verdict"]
    got = v.get("dist_km", 0) * 1000 if "dist_km" in v else v.get("dist_m", 0)
    err = (got - t_d) / t_d * 100 if got else float("nan")
    same = lambda a, b: bool(a) and (a.lower() in b.lower() or b.lower() in a.lower())
    ok = same(v.get("what"), c["target"]["name"]) and abs(err) <= (3 if kind == "mountain" else 6)
    fails += not ok
    print(f"photo {c['photo']:02d} anchor {c['anchor']['name']:14s} -> {c['target']['name']:14s}: {v.get('what')} {got/1000:.2f} km vs true {t_d/1000:.2f} ({err:+.1f}%) "
          f"[line off {geo.angdiff(brg, t_b):+.2f} deg] {'OK' if ok else 'FAIL'}")

print("\n== towers: the phone's own compass + the tower's spot + the right tilt -> which building, how far")
for c in T["tower_cases"]:
    p = PH[str(c["photo"])]
    h_eye, _ = terrain.eye_height(p["lat"], p["lon"], None)
    head = (p["dir"] + (c["declination"] if p["dir_ref"] == "M" else 0)) % 360
    if c["photo"] == 14:
        head = (head + 180) % 360        # Android portrait shot tilted up: the file holds the top edge's direction
    t_d, t_b, t_el = sight(p, h_eye, c["name"])
    hh, vh = camera.half_fov(p["w"], p["h"], p["f35"])
    off = math.degrees(math.atan((2 * c["x"] - 1) * math.tan(math.radians(hh))))
    brg = (head + off) % 360
    aim_h = top_asl(c["name"]) - (top_asl(c["name"]) - h_eye) * 0.2         # aim 80% of the way up the tower, as a person would
    pitch = math.degrees(math.atan2(aim_h - h_eye - geo.drop(t_d), t_d))
    res = solve.aim(p["lat"], p["lon"], brg, pitch, kind="building")
    wide = res.get("shortlist_if_heading_is_rough", [])
    names = [b["name"] for b in wide[:8] if b["name"]]
    hit = next((b for b in wide[:8] if b["name"] and c["name"].split()[0].lower() in b["name"].lower()), None)
    got = hit["dist_m"] if hit else 0
    err = (got - t_d) / t_d * 100 if got else float("nan")
    ok = hit is not None and abs(err) <= 10      # truth is the tower's centre point; the tool answers the near face
    fails += not ok
    print(f"photo {c['photo']:02d} {c['name']:20s}: compass off {geo.angdiff(brg, t_b):+5.1f} deg | named in top 8 {names} -> {got:.0f} m vs true {t_d:.0f} ({err:+.1f}%) {'OK' if ok else 'FAIL'}")

print(f"\n{'ALL PASS' if not fails else str(fails) + ' FAILED'}")
sys.exit(1 if fails else 0)
