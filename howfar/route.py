"""How long to get there: trail routing (hiking) and road routing (driving) on public, keyless servers.
Fair use: one request per question, with attribution (see README). Servers: FOSSGIS Valhalla, BRouter."""
import math
import requests
from .cache import UA
from .geo import inv

VALHALLA = "https://valhalla1.openstreetmap.de/route"
BROUTER = "https://brouter.de/brouter"


def valhalla(lat1, lon1, lat2, lon2, costing):
    body = {"locations": [{"lat": lat1, "lon": lon1}, {"lat": lat2, "lon": lon2}], "costing": costing, "units": "kilometers"}
    r = requests.post(VALHALLA, json=body, headers=UA, timeout=60)
    if r.status_code != 200:
        return {"error": f"router answered HTTP {r.status_code}"}
    t = r.json()["trip"]
    names = []
    for m in t["legs"][0].get("maneuvers", []):
        for n in m.get("street_names", []):
            if n not in names:
                names.append(n)
    end = t["locations"][-1]
    return {"km": round(t["summary"]["length"], 2), "minutes": round(t["summary"]["time"] / 60),
            "via": names[:8], "snapped_end": {"lat": end.get("lat"), "lon": end.get("lon")}}


def brouter_hike(lat1, lon1, lat2, lon2, profile="hiking-mountain"):
    u = f"{BROUTER}?lonlats={lon1},{lat1}|{lon2},{lat2}&profile={profile}&alternativeidx=0&format=geojson"
    r = requests.get(u, headers=UA, timeout=90)
    if r.status_code != 200:
        return {"error": f"BRouter answered HTTP {r.status_code}"}
    p = r.json()["features"][0]["properties"]
    return {"km": round(float(p["track-length"]) / 1000, 2), "minutes": round(float(p["total-time"]) / 60),
            "ascent_m": round(float(p.get("filtered ascend") or p.get("plain-ascend") or 0))}


def naismith_minutes(km, ascent_m):
    """Naismith's rule: 1 h per 5 km plus 1 h per 600 m of climb."""
    return round(60 * (km / 5 + ascent_m / 600))


def hike(lat, lon, to_lat, to_lon):
    """Trail distance and time to a point, from two routers; straight-line for comparison."""
    straight, brg = inv(lat, lon, to_lat, to_lon)
    out = {"straight_km": round(straight / 1000, 2), "bearing": round(brg)}
    try:
        out["valhalla"] = valhalla(lat, lon, to_lat, to_lon, "pedestrian")
    except Exception as ex:
        out["valhalla"] = {"error": str(ex)[:100]}
    try:
        out["brouter"] = brouter_hike(lat, lon, to_lat, to_lon)
    except Exception as ex:
        out["brouter"] = {"error": str(ex)[:100]}
    v, b = out["valhalla"], out["brouter"]
    if "km" in b:
        out["estimate"] = {"km": b["km"], "minutes": max(b["minutes"], naismith_minutes(b["km"], b["ascent_m"])), "ascent_m": b["ascent_m"],
                           "how": "BRouter hiking route; time is the slower of BRouter and Naismith's rule"}
    elif "km" in v:
        out["estimate"] = {"km": v["km"], "minutes": v["minutes"], "how": "Valhalla pedestrian route"}
    else:
        out["estimate"] = None
    snapped = v.get("snapped_end") if isinstance(v, dict) else None
    if snapped and snapped.get("lat") is not None:
        gap, _ = inv(snapped["lat"], snapped["lon"], to_lat, to_lon)
        out["off_trail_at_end_m"] = round(gap)
        if gap > 150:
            out["note"] = f"the mapped trail ends about {round(gap)} m from the summit point; the last stretch is off-trail"
    return out


def drive(lat, lon, to_lat, to_lon):
    straight, brg = inv(lat, lon, to_lat, to_lon)
    out = {"straight_km": round(straight / 1000, 2), "bearing": round(brg)}
    try:
        out["road"] = valhalla(lat, lon, to_lat, to_lon, "auto")
    except Exception as ex:
        out["road"] = {"error": str(ex)[:100]}
    return out
