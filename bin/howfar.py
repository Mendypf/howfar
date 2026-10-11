#!/usr/bin/env python3
"""howfar: the tools an AI agent runs to answer "how far is that?" from a phone photo or a slow spin on video.
Every command prints one JSON object. Pictures for the agent's eyes go to --out (default ./howfar_out).

  look    PHOTO            what the file says + what is around that spot (map.png, around.png, photo_ruled.jpg)
  anchor                   camera heading + tilt from one recognised thing and its spot in the picture
  aim                      what a line of sight hits and how far (buildings, ground, named peaks)
  spin    VIDEO            a slow full turn -> 360 strip, skyline match, sun check
  peak                     trail distance and time to a named mountain (or a point)
  drive                    road distance and minutes to a point
  sunpos                   where the sun is for a time and place
  clear-cache              delete downloaded map pieces
"""
import argparse, datetime as dt, json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from howfar import photo as P, terrain, mapdata, peaks, camera, sun, draw, solve, route, sweep, cache  # noqa: E402

CREDIT = "map data (c) Overture Maps Foundation / OpenStreetMap contributors (ODbL); terrain: Mapzen / AWS Open Data; mountains: Wikidata"


def out_json(d):
    print(json.dumps(d, indent=1, ensure_ascii=False, default=str))


def parse_utc(s):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y:%m:%d %H:%M:%S"):
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            pass
    raise SystemExit("time must look like 2026-10-11 14:02:33 (UTC)")


def cmd_look(a):
    p = P.read(a.photo)
    lat = a.lat if a.lat is not None else p["lat"]
    lon = a.lon if a.lon is not None else p["lon"]
    if lat is None or lon is None:
        out_json({"error": "no position: the file has no GPS and none was given; pass --lat --lon from the user's location"}); return
    os.makedirs(a.out, exist_ok=True)
    utc = parse_utc(a.utc) if a.utc else (dt.datetime.strptime(p["taken_utc"], "%Y-%m-%d %H:%M:%S") if p["taken_utc"] else None)
    lat, lon, moved, road = mapdata.snap_to_road(lat, lon)
    h_eye, ground = terrain.eye_height(lat, lon, p.get("alt"))
    hh, vh = camera.half_fov(p["w"], p["h"], p["f35"])
    res = {"photo": {k: p[k] for k in ("w", "h", "make", "model", "lat", "lon", "alt", "gps_err_m", "dir_deg", "dir_ref", "compass_note", "taken_local", "taken_utc", "f35", "notes")},
           "position_used": {"lat": round(lat, 6), "lon": round(lon, 6), "source": "file" if a.lat is None else "given",
                             "note": f"was inside a building (GPS drift); moved {moved} m onto {road or 'the nearest road'}" if moved else None},
           "field_of_view_deg": {"horizontal": round(2 * hh, 1), "vertical": round(2 * vh, 1)},
           "eye": {"m_above_sea": round(h_eye, 1), "ground_m": round(ground, 1)}}
    if p["dir_deg"] is not None:
        hint = [round(p["dir_deg"], 1)]
        if "top edge" in (p.get("compass_note") or "") and p["w"] > p["h"]:
            hint = [round((p["dir_deg"] - 90) % 360, 1), round((p["dir_deg"] + 90) % 360, 1)]
        res["compass_hint"] = {"bearings": hint, "reference": p["dir_ref"], "note": p["compass_note"]}
    try:
        res["roads_at_your_feet"] = mapdata.nearest_roads(lat, lon)
    except Exception as ex:
        res["roads_at_your_feet"] = {"error": str(ex)[:120]}
    try:
        res["named_buildings_near"] = mapdata.named_buildings(lat, lon, 1500, min_height=50)[:25]
    except Exception as ex:
        res["named_buildings_near"] = {"error": str(ex)[:120]}
    try:
        ps = peaks.with_view_angles(peaks.around(lat, lon, a.peak_km * 1000, limit=30), lat, lon, h_eye, check_hidden=True, max_check=10)
        res["named_mountains_around"] = [{"name": q["name"], "dist_km": round(q["dist"] / 1000, 1), "bearing": round(q["brg"]), "summit_m": round(q["ele"]) if q["ele"] else None,
                                         "angle_above_level": round(q["ang"], 2), "hidden": q.get("hidden"), "wiki_pages": q["links"]} for q in ps]
    except Exception as ex:
        res["named_mountains_around"] = {"error": str(ex)[:120]}
    if utc:
        az, el = sun.position(utc, lat, lon)
        res["sun"] = {"azimuth": round(az, 1), "elevation": round(el, 1), "utc": utc.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        draw.block_map(lat, lon).save(os.path.join(a.out, "map.png"))
        draw.around_view(lat, lon).save(os.path.join(a.out, "around.png"))
        draw.ruled_photo(a.photo).save(os.path.join(a.out, "photo_ruled.jpg"), quality=88)
        res["pictures"] = {"map": os.path.join(a.out, "map.png"), "around": os.path.join(a.out, "around.png"), "photo_ruled": os.path.join(a.out, "photo_ruled.jpg")}
    except Exception as ex:
        res["pictures"] = {"error": str(ex)[:120]}
    res["credit"] = CREDIT
    out_json(res)


def cmd_anchor(a):
    lat, lon = a.lat, a.lon
    h_eye, ground = terrain.eye_height(lat, lon, a.alt)
    found = None
    try:
        pk = peaks.find_named(a.name, lat, lon)
    except Exception:
        pk = None
    if pk and pk["ele"]:
        found = {"kind": "mountain", "name": pk["name"], "lat": pk["lat"], "lon": pk["lon"], "top_m": pk["ele"], "dist_m": pk["dist"], "bearing": pk["brg"]}
    if found is None:
        nm = a.name.lower()
        for b in mapdata.named_buildings(lat, lon, 5000):
            if b["name"] and (nm in b["name"].lower() or b["name"].lower() in nm):
                la, lo = lat, lon
                found = {"kind": "building", "name": b["name"], "dist_m": b["dist_m"], "bearing": b["bearing"], "height_m": b["height_m"]}
                break
    if found is None:
        out_json({"error": f"could not find '{a.name}' on the map near the user; try another name, or use the compass hint / map match instead"}); return
    from howfar.geo import drop, dest
    if found["kind"] == "mountain":
        top = found["top_m"]
    else:
        pt = dest(lat, lon, found["bearing"], found["dist_m"])
        top = terrain.elev(pt[0], pt[1], 13) + (found["height_m"] or 20)
        if not found["height_m"]:
            found["note"] = "building height unknown on the map; its top is a poor tilt reference, keep tilt loose"
    a_el = __import__("math").degrees(__import__("math").atan2(top - h_eye - drop(found["dist_m"]), found["dist_m"]))
    heading, th = camera.solve_pose(a.w, a.h, a.f35, a.x, a.y, found["bearing"], a_el)
    out_json({"anchor": found, "anchor_angle_above_level": round(a_el, 2), "camera_heading": round(heading, 2), "camera_tilt": round(__import__("math").degrees(th), 2),
              "note": "heading from an anchor is good to about 1 degree; tilt from a tall thing's top can be 1 degree off (antenna, spire)"})


def cmd_aim(a):
    if a.bearing is not None:
        brg, el = a.bearing, a.elevation or 0.0
    else:
        if None in (a.heading, a.x, a.y):
            out_json({"error": "give either --bearing/--elevation or --heading/--tilt with --x --y"}); return
        brg, el = camera.aim(a.w, a.h, a.f35, a.heading, a.tilt or 0.0, a.x, a.y)
    lat, lon, moved, road = mapdata.snap_to_road(a.lat, a.lon)
    res = solve.aim(lat, lon, brg, el, kind=a.kind, alt_hint=a.alt, gps_err_m=a.gps_err)
    if moved:
        res["position_note"] = f"the given position was inside a building (GPS drift); moved {moved} m onto {road or 'the nearest road'}"
    res["credit"] = CREDIT
    out_json(res)


def cmd_spin(a):
    os.makedirs(a.out, exist_ok=True)
    utc = parse_utc(a.utc) if a.utc else None
    if utc is None:
        _, ct = sweep.duration(a.video)
        if ct:
            try:
                utc = dt.datetime.strptime(ct[:19], "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                utc = None
    res = sweep.analyse(a.video, a.lat, a.lon, a.out, hfov_deg=a.hfov, n=a.frames, turn=a.turn, utc=utc)
    res["how_to_finish"] = ("Open strip_ruled.jpg and around.png. Match them yourself (streets leading away, gaps, tall buildings) and name the compass "
                            "bearing at the strip's LEFT edge. Compare with skyline_match and sun. When two sources agree within 20 degrees, trust it; "
                            "the target is what the video ENDS on, i.e. the last frame's bearing. Then run `aim` with that bearing.")
    res["credit"] = CREDIT
    out_json(res)


def cmd_peak(a):
    if a.name:
        pk = peaks.find_named(a.name, a.lat, a.lon)
        if not pk:
            out_json({"error": f"no mountain called '{a.name}' found near here"}); return
        to_lat, to_lon = pk["lat"], pk["lon"]
    else:
        to_lat, to_lon = a.to_lat, a.to_lon
        pk = None
    res = route.hike(a.lat, a.lon, to_lat, to_lon)
    if pk:
        res["mountain"] = {"name": pk["name"], "summit_m": pk["ele"], "lat": pk["lat"], "lon": pk["lon"]}
    res["credit"] = CREDIT + "; routing: FOSSGIS Valhalla, BRouter"
    out_json(res)


def cmd_drive(a):
    res = route.drive(a.lat, a.lon, a.to_lat, a.to_lon)
    res["credit"] = CREDIT + "; routing: FOSSGIS Valhalla"
    out_json(res)


def cmd_sunpos(a):
    az, el = sun.position(parse_utc(a.utc), a.lat, a.lon)
    out_json({"azimuth": round(az, 2), "elevation": round(el, 2)})


def main():
    ap = argparse.ArgumentParser(prog="howfar", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("look"); s.add_argument("photo"); s.add_argument("--lat", type=float); s.add_argument("--lon", type=float)
    s.add_argument("--utc", help="time the photo was taken, UTC, if the file has none"); s.add_argument("--out", default="howfar_out")
    s.add_argument("--peak-km", type=float, default=150); s.set_defaults(f=cmd_look)

    s = sp.add_parser("anchor"); s.add_argument("--lat", type=float, required=True); s.add_argument("--lon", type=float, required=True)
    s.add_argument("--name", required=True); s.add_argument("--x", type=float, required=True); s.add_argument("--y", type=float, required=True, help="spot of the anchor's TOP, fractions 0-1")
    s.add_argument("--w", type=int, required=True); s.add_argument("--h", type=int, required=True); s.add_argument("--f35", type=float, required=True)
    s.add_argument("--alt", type=float); s.set_defaults(f=cmd_anchor)

    s = sp.add_parser("aim"); s.add_argument("--lat", type=float, required=True); s.add_argument("--lon", type=float, required=True)
    s.add_argument("--bearing", type=float); s.add_argument("--elevation", type=float, help="degrees above level of the spot (0 if unknown)")
    s.add_argument("--heading", type=float); s.add_argument("--tilt", type=float, help="camera tilt up, degrees"); s.add_argument("--x", type=float); s.add_argument("--y", type=float)
    s.add_argument("--w", type=int, default=4032); s.add_argument("--h", type=int, default=3024); s.add_argument("--f35", type=float, default=26.0)
    s.add_argument("--kind", choices=["building", "mountain", "ground", "any"], default="any"); s.add_argument("--alt", type=float); s.add_argument("--gps-err", type=float)
    s.set_defaults(f=cmd_aim)

    s = sp.add_parser("spin"); s.add_argument("video"); s.add_argument("--lat", type=float, required=True); s.add_argument("--lon", type=float, required=True)
    s.add_argument("--utc"); s.add_argument("--hfov", type=float, default=65.0, help="horizontal field of view of the video, degrees (phone main camera ~65)")
    s.add_argument("--frames", type=int, default=36); s.add_argument("--turn", type=float, help="degrees turned if not a full circle"); s.add_argument("--out", default="howfar_out")
    s.set_defaults(f=cmd_spin)

    s = sp.add_parser("peak"); s.add_argument("--lat", type=float, required=True); s.add_argument("--lon", type=float, required=True)
    s.add_argument("--name"); s.add_argument("--to-lat", type=float); s.add_argument("--to-lon", type=float); s.set_defaults(f=cmd_peak)

    s = sp.add_parser("drive"); s.add_argument("--lat", type=float, required=True); s.add_argument("--lon", type=float, required=True)
    s.add_argument("--to-lat", type=float, required=True); s.add_argument("--to-lon", type=float, required=True); s.set_defaults(f=cmd_drive)

    s = sp.add_parser("sunpos"); s.add_argument("--lat", type=float, required=True); s.add_argument("--lon", type=float, required=True); s.add_argument("--utc", required=True)
    s.set_defaults(f=cmd_sunpos)

    s = sp.add_parser("clear-cache"); s.set_defaults(f=lambda a: out_json({"deleted_files": cache.clear(), "folder": cache.CACHE}))
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
