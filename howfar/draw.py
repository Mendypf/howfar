"""Pictures for the agent's eyes: a north-up block map, a 360-degree eye-level view drawn from map data,
and a percent grid over the photo so positions can be read off reliably."""
import math
from PIL import Image, ImageDraw, ImageFont
from . import mapdata
from .geo import dest

PPD = 10                 # pixels per degree in the 360 view
E_LO, E_HI = -20, 40     # elevation band drawn in the 360 view
EYE = 1.6


def font(sz, bold=True):
    for f in (("arialbd.ttf" if bold else "arial.ttf"), "arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, sz)
        except Exception:
            pass
    return ImageFont.load_default()


def block_map(lat, lon, radius=320.0, px=1024):
    """North-up map: streets with names, building outlines (darker = taller, tall ones labelled), red dot = you."""
    s = px / 2 / radius
    to = lambda x, y: (px / 2 + x * s, px / 2 - y * s)
    im = Image.new("RGB", (px, px), (246, 244, 238)); dr = ImageDraw.Draw(im)
    names = {}
    for st in mapdata.streets(lat, lon, radius * 1.45):
        cl = st["class"]
        w = {"motorway": 9, "trunk": 9, "primary": 8, "secondary": 7, "tertiary": 6}.get(cl, 4 if cl != "service" else 2)
        xy = [to(x, y) for x, y in st["xy"]]
        dr.line(xy, fill=(255, 255, 255), width=w + 2); dr.line(xy, fill=(250, 226, 150) if w >= 6 else (255, 255, 255), width=w)
        if st["name"] and w >= 4 and len(xy) >= 2:
            mid = xy[len(xy) // 2]
            if 30 < mid[0] < px - 30 and 30 < mid[1] < px - 30:
                names.setdefault(st["name"], []).append(mid)
    labels = []
    for b in sorted(mapdata.buildings(lat, lon, radius * 1.45), key=lambda b: b["h"] or 0):
        if b["part"]:
            continue
        h = b["h"]
        g = 222 if not h else int(max(95, 212 - min(h, 160) * 0.75))
        xy = [to(x, y) for x, y in b["xy"]]
        dr.polygon(xy, fill=(g, g, g + 6 if g < 240 else g), outline=(120, 120, 128))
        cx, cy = to(b["cx"], b["cy"])
        if 20 < cx < px - 20 and 20 < cy < px - 20 and ((h and h >= 45) or b["name"]):
            labels.append(((h or 0), cx, cy, (b["name"] or "") + (f" {h:.0f} m" if h and h >= 45 else "")))
    f_s, f_n, f_b = font(13), font(15), font(22)
    placed = []
    for h, cx, cy, t in sorted(labels, reverse=True):
        if len(placed) >= 24 or any(math.hypot(cx - a, cy - b) < 70 for a, b in placed):
            continue
        placed.append((cx, cy))
        dr.text((cx, cy), t.strip(), fill=(20, 20, 60), font=f_s, anchor="mm", stroke_width=2, stroke_fill=(255, 255, 255))
    for nm, mids in names.items():
        done = []
        for mx, my in sorted(mids, key=lambda m: abs(m[0] - px / 2) + abs(m[1] - px / 2)):
            if all(math.hypot(mx - a, my - b) > 260 for a, b in done) and len(done) < 2:
                dr.text((mx, my), nm, fill=(150, 60, 0), font=f_n, anchor="mm", stroke_width=3, stroke_fill=(255, 255, 255)); done.append((mx, my))
    c = px / 2
    for deg, lab in ((0, "N 0"), (45, "45"), (90, "E 90"), (135, "135"), (180, "S 180"), (225, "225"), (270, "W 270"), (315, "315")):
        a = math.radians(deg); r = px / 2 - 26
        dr.text((c + r * math.sin(a), c - r * math.cos(a)), lab, fill=(0, 90, 200), font=f_b, anchor="mm", stroke_width=3, stroke_fill=(255, 255, 255))
    dr.ellipse([c - 9, c - 9, c + 9, c + 9], fill=(230, 0, 0), outline=(255, 255, 255), width=3)
    dr.line([(30, px - 30), (30 + 100 * s, px - 30)], fill=(0, 0, 0), width=4); dr.text((30, px - 54), "100 m", fill=(0, 0, 0), font=f_n)
    return im


def around_view(lat, lon, radius=450.0):
    """360-degree view from the user's spot at eye height, drawn from map data. Columns = compass bearing (PPD px/deg)."""
    W, H = 360 * PPD, (E_HI - E_LO) * PPD
    im = Image.new("RGB", (W, H), (236, 242, 252)); dr = ImageDraw.Draw(im)
    row = lambda e: (E_HI - e) * PPD
    dr.rectangle([0, row(0), W, H], fill=(228, 224, 216))

    def proj(x, y, z):
        d = math.hypot(x, y)
        if d < 0.5:
            return None
        return math.degrees(math.atan2(x, y)) % 360, math.degrees(math.atan2(z - EYE, d)), d

    def poly(pts, fill, outline, width=1, line=False):
        out, prev = [], pts[0][0]
        for az, el in pts:
            while az - prev > 180: az -= 360
            while az - prev < -180: az += 360
            out.append((az, el)); prev = az
        for shift in (-360, 0, 360):
            xy = [((az + shift) * PPD, row(el)) for az, el in out]
            if max(p[0] for p in xy) < 0 or min(p[0] for p in xy) > W:
                continue
            if line:
                dr.line(xy, fill=fill, width=width)
            else:
                dr.polygon(xy, fill=fill, outline=outline)

    for st in mapdata.streets(lat, lon, radius * 1.45):
        if st["class"] == "service":
            continue
        for (x0, y0), (x1, y1) in zip(st["xy"], st["xy"][1:]):
            n = max(2, int(math.hypot(x1 - x0, y1 - y0) / 4))
            seg = []
            for i in range(n + 1):
                p = proj(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n, 0)
                if p and p[2] <= radius:
                    seg.append((p[0], p[1]))
                else:
                    if len(seg) >= 2: poly(seg, (235, 190, 60), None, 3, line=True)
                    seg = []
            if len(seg) >= 2: poly(seg, (235, 190, 60), None, 3, line=True)
    walls = []
    near = mapdata.buildings(lat, lon, radius * 1.45)
    seen_ids = {b["id"] for b in near}
    # tall things further out still show above the roofline: towers up to 3 km (landmarks the agent can match)
    far = [b for b in mapdata.buildings(lat, lon, 3000) if b["h"] and b["h"] >= 40 and b["dist"] > radius]
    for b in list(near) + far:
        if b["part"]:
            continue
        h = b["h"] or 9.0
        xy = b["xy"]
        for (x0, y0), (x1, y1) in zip(xy, xy[1:] + xy[:1]):
            d = math.hypot((x0 + x1) / 2, (y0 + y1) / 2)
            if d <= radius or (b["h"] and b["h"] >= 40 and d <= 3000):
                walls.append((d, (x0, y0), (x1, y1), h, b))
    labels = []
    for d, p0, p1, h, b in sorted(walls, key=lambda w: -w[0]):
        a = proj(p0[0], p0[1], 0); c = proj(p1[0], p1[1], 0)
        if not a or not c:
            continue
        top0 = proj(p0[0], p0[1], h)[1]; top1 = proj(p1[0], p1[1], h)[1]
        g = int(max(70, 205 - min(h, 150) * 0.9)) if b["h"] else 200
        nearness = max(0, min(1, (radius - d) / radius))
        v = g * (0.75 + 0.25 * nearness)
        poly([(a[0], top0), (c[0], top1), (c[0], c[1]), (a[0], a[1])], (int(v), int(v), int(min(255, v + 8))), (60, 60, 70))
        if b["name"] or (b["h"] and b["h"] >= 40):
            labels.append((d, (a[0] + (((c[0] - a[0] + 180) % 360) - 180) / 2) % 360, max(top0, top1), b["name"], b["h"]))
    f_s, f_b = font(18), font(24)
    seen, placed = set(), []
    order = sorted(labels, key=lambda l: (-(l[4] or 0) if (l[4] or 0) >= 40 else 0, l[0]))
    for d, az, top, nm, h in order:
        k = nm or round(az)
        if k in seen or (not nm and not (h and h >= 40)) or len(placed) >= 14:
            continue
        if any(abs(((az - a + 180) % 360) - 180) < 25 for a in placed):
            continue
        seen.add(k); placed.append(az)
        t = ((nm or "") + (f" {h:.0f} m" if h else "")).strip()
        for shift in (-360, 0, 360):
            x = (az + shift) * PPD
            if 0 <= x <= W:
                dr.text((x, row(top) - 12), t, fill=(20, 20, 70), font=f_s, anchor="mb", stroke_width=2, stroke_fill=(255, 255, 255))
    for deg in range(0, 360, 5):
        x = deg * PPD; big = deg % 30 == 0
        dr.line([(x, H - (26 if big else 12)), (x, H)], fill=(0, 70, 200), width=3 if big else 1)
        dr.line([(x, 0), (x, 26 if big else 12)], fill=(0, 70, 200), width=3 if big else 1)
        if big:
            lab = {0: "N 0", 90: "E 90", 180: "S 180", 270: "W 270"}.get(deg, str(deg))
            dr.text((x, H - 30), lab, fill=(0, 70, 200), font=f_b, anchor="mb", stroke_width=3, stroke_fill=(255, 255, 255))
            dr.text((x, 30), lab, fill=(0, 70, 200), font=f_b, anchor="mt", stroke_width=3, stroke_fill=(255, 255, 255))
    dr.line([(0, row(0)), (W, row(0))], fill=(120, 120, 120), width=1)
    return im


def ruled_photo(path, max_side=1600):
    """The photo with a percent grid (0-100 across and down) so a spot can be named as numbers."""
    im = Image.open(path)
    try:
        from PIL import ImageOps
        im = ImageOps.exif_transpose(im)
    except Exception:
        pass
    im = im.convert("RGB"); im.thumbnail((max_side, max_side), Image.LANCZOS)
    W, H = im.size; dr = ImageDraw.Draw(im); f = font(max(14, W // 70))
    for pct in range(0, 101, 10):
        x, y = pct / 100 * (W - 1), pct / 100 * (H - 1)
        dr.line([(x, 0), (x, H)], fill=(255, 40, 40), width=1)
        dr.line([(0, y), (W, y)], fill=(255, 40, 40), width=1)
        for ty in (4, H - 4):
            dr.text((min(max(x, 14), W - 14), ty), str(pct), fill=(255, 40, 40), font=f, anchor="mt" if ty == 4 else "mb", stroke_width=2, stroke_fill=(255, 255, 255))
        for tx in (4, W - 4):
            dr.text((tx, min(max(y, 10), H - 10)), str(pct), fill=(255, 40, 40), font=f, anchor="lm" if tx == 4 else "rm", stroke_width=2, stroke_fill=(255, 255, 255))
    return im


def ruled_strip(strip):
    """A 360 strip with a percent ruler top and bottom (0% = left edge)."""
    im = strip.convert("RGB").copy(); W, H = im.size; dr = ImageDraw.Draw(im); f = font(24)
    for pct in range(0, 100, 5):
        x = pct / 100 * W; big = pct % 10 == 0
        dr.line([(x, H - (26 if big else 12)), (x, H)], fill=(255, 40, 40), width=3 if big else 1)
        dr.line([(x, 0), (x, 26 if big else 12)], fill=(255, 40, 40), width=3 if big else 1)
        if big:
            dr.text((x, H - 30), f"{pct}%", fill=(255, 40, 40), font=f, anchor="mb", stroke_width=3, stroke_fill=(255, 255, 255))
            dr.text((x, 30), f"{pct}%", fill=(255, 40, 40), font=f, anchor="mt", stroke_width=3, stroke_fill=(255, 255, 255))
    return im
