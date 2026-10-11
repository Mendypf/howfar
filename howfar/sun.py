"""Where the sun is, from the time and place (NOAA solar calculator equations, about 0.02 degrees).
Also: finding the sun's column in a 360-degree strip, which gives the strip's compass direction with no AI."""
import datetime as dt, math
import numpy as np


def position(utc, lat, lon):
    """-> (azimuth deg from true north, elevation deg). utc is a naive datetime in UTC."""
    r, dg = math.radians, math.degrees
    jd = 2440587.5 + utc.replace(tzinfo=dt.timezone.utc).timestamp() / 86400.0
    jc = (jd - 2451545.0) / 36525.0
    gmls = (280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360
    gmas = 357.52911 + jc * (35999.05029 - 0.0001537 * jc)
    eeo = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)
    seoc = (math.sin(r(gmas)) * (1.914602 - jc * (0.004817 + 0.000014 * jc)) + math.sin(r(2 * gmas)) * (0.019993 - 0.000101 * jc)
            + math.sin(r(3 * gmas)) * 0.000289)
    sal = gmls + seoc - 0.00569 - 0.00478 * math.sin(r(125.04 - 1934.136 * jc))
    moe = 23 + (26 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60) / 60
    oc = moe + 0.00256 * math.cos(r(125.04 - 1934.136 * jc))
    decl = dg(math.asin(math.sin(r(oc)) * math.sin(r(sal))))
    y = math.tan(r(oc / 2)) ** 2
    eqt = 4 * dg(y * math.sin(2 * r(gmls)) - 2 * eeo * math.sin(r(gmas)) + 4 * eeo * y * math.sin(r(gmas)) * math.cos(2 * r(gmls))
                 - 0.5 * y * y * math.sin(4 * r(gmls)) - 1.25 * eeo * eeo * math.sin(2 * r(gmas)))
    mins = utc.hour * 60 + utc.minute + utc.second / 60
    tst = (mins + eqt + 4 * lon) % 1440
    ha = tst / 4 - 180
    if ha < -180:
        ha += 360
    zen = dg(math.acos(max(-1, min(1, math.sin(r(lat)) * math.sin(r(decl)) + math.cos(r(lat)) * math.cos(r(decl)) * math.cos(r(ha))))))
    el = 90 - zen
    x = (math.sin(r(lat)) * math.cos(r(zen)) - math.sin(r(decl))) / (math.cos(r(lat)) * math.sin(r(zen)) + 1e-12)
    a = dg(math.acos(max(-1, min(1, x))))
    az = (a + 180) % 360 if ha > 0 else (540 - a) % 360
    return az, el


def column_in_strip(img, el_top, el_bottom, sun_el):
    """In a 360-degree strip (equirectangular band covering el_top..el_bottom degrees), find the column
    where the sun blows out the picture. -> (fraction across 0..1, strength) or None."""
    a = np.asarray(img.convert("RGB")).astype(int)
    H, W = a.shape[:2]
    def row(e):
        return int(min(max((el_top - e) / (el_top - el_bottom), 0), 1) * (H - 1))
    r0, r1 = row(min(el_top, sun_el + 25)), row(max(el_bottom, sun_el - 25))
    if r1 - r0 < 4:
        return None
    band = a[r0:r1]
    white = (band.min(axis=2) > 245).sum(axis=0).astype(float)
    k = max(5, W // 100)
    sm = np.convolve(white, np.ones(k) / k, mode="same")
    col = int(sm.argmax()); strength = float(sm.max())
    if strength < 8:
        return None
    return col / W, strength
