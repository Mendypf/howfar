"""What a phone photo file says about where and how it was taken."""
import datetime as dt, math
from PIL import Image, ExifTags


def _rat(v):
    try:
        return float(v)
    except Exception:
        return None


def _dms(v, ref):
    try:
        d = float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
    except Exception:
        return None
    return -d if ref in ("S", "W") else d


def read(path):
    """-> dict: w, h, make, model, lat, lon, alt, gps_err_m, dir_deg, dir_ref ('T' true / 'M' magnetic),
    taken_local, taken_utc (from the GPS time stamps or the time-zone offset tag), f35, focal_mm, orientation, notes."""
    im = Image.open(path)
    w, h = im.size
    ex = im.getexif()
    out = {"w": w, "h": h, "notes": []}
    out["make"] = str(ex.get(0x010F, "")).strip() or None
    out["model"] = str(ex.get(0x0110, "")).strip() or None
    out["orientation"] = int(ex.get(0x0112, 1) or 1)
    if out["orientation"] in (5, 6, 7, 8):          # stored sideways: the picture as seen is rotated
        out["w"], out["h"] = h, w
    try:
        exif = ex.get_ifd(0x8769)
    except Exception:
        exif = {}
    try:
        gps = ex.get_ifd(0x8825)
    except Exception:
        gps = {}
    out["lat"] = _dms(gps.get(2), gps.get(1)) if gps.get(2) else None
    out["lon"] = _dms(gps.get(4), gps.get(3)) if gps.get(4) else None
    alt = _rat(gps.get(6))
    if alt is not None and gps.get(5) == 1:
        alt = -alt
    out["alt"] = alt
    out["gps_err_m"] = _rat(gps.get(0x1F))
    out["dir_deg"] = _rat(gps.get(0x11))
    out["dir_ref"] = str(gps.get(0x10) or "") or None
    out["speed"] = _rat(gps.get(0x0D)); out["speed_ref"] = str(gps.get(0x0C) or "") or None     # K km/h, M mph, N knots
    out["track"] = _rat(gps.get(0x0F))                                                           # direction of movement
    # time
    local = exif.get(0x9003) or ex.get(0x0132)
    out["taken_local"] = str(local) if local else None
    utc = None
    if gps.get(0x1D) and gps.get(0x07):
        try:
            hh, mm, ss = [float(v) for v in gps[0x07]]
            utc = dt.datetime.strptime(str(gps[0x1D]).strip("\x00 "), "%Y:%m:%d") + dt.timedelta(hours=hh, minutes=mm, seconds=ss)
        except Exception:
            utc = None
    if utc is None and local and exif.get(0x9011):
        try:
            off = str(exif[0x9011]).strip()
            sign = -1 if off.startswith("-") else 1
            oh, om = off.lstrip("+-").split(":")
            utc = dt.datetime.strptime(str(local), "%Y:%m:%d %H:%M:%S") - sign * dt.timedelta(hours=int(oh), minutes=int(om))
        except Exception:
            utc = None
    out["taken_utc"] = utc.strftime("%Y-%m-%d %H:%M:%S") if utc else None
    if not utc and local:
        out["notes"].append("time of day is local with no time zone in the file; sun-based checks are off until a zone is known")
    # lens
    f35 = _rat(exif.get(0xA405))
    focal = _rat(exif.get(0x920A))
    zoom = _rat(exif.get(0xA404))
    if f35 and zoom and zoom > 1.05:
        out["notes"].append(f"digital zoom {zoom:.1f}x recorded; field of view scaled accordingly")
        f35 = f35 * zoom
    out["f35"] = f35
    out["focal_mm"] = focal
    if not f35:
        out["f35"] = 26.0
        out["notes"].append("no 35 mm-equivalent focal length in the file; assuming a 26 mm main camera (ask the user if they zoomed)")
    # compass hint, with the known phone quirks
    if out["dir_deg"] is not None:
        mk = (out["make"] or "").lower()
        if "apple" in mk:
            out["compass_note"] = "iPhone: true north, typically 5-10 degrees off, worse indoors or behind glass"
        elif "google" in mk or "pixel" in (out["model"] or "").lower():
            out["compass_note"] = ("Pixel: magnetic, whole degrees, and it is the direction of the phone's TOP EDGE, "
                                   "so a landscape photo is 90 degrees off (either way) and a photo tilted far up can be 180 off")
        else:
            out["compass_note"] = "phone compass: treat as a rough hint only (+-10 degrees at best)"
    else:
        out["compass_note"] = "no compass direction in the file"
    return out


def half_fov(p):
    from .camera import half_fov as hf
    return hf(p["w"], p["h"], p["f35"])
