"""The spin: a slow full turn on video becomes a 360-degree strip, which is matched to the drawn map view
(no AI) and checked against the sun (no AI). The agent then does its own visual match on top."""
import json, math, os, shutil, subprocess
import numpy as np
from PIL import Image
from . import draw, sun as sunmod

W360 = 360 * draw.PPD


def ffmpeg():
    return shutil.which("ffmpeg")


def duration(video):
    fp = shutil.which("ffprobe")
    if fp:
        try:
            j = json.loads(subprocess.run([fp, "-v", "error", "-show_entries", "format=duration:format_tags=creation_time", "-of", "json", video],
                                          capture_output=True, text=True, timeout=60).stdout)
            return float(j["format"]["duration"]), (j["format"].get("tags") or {}).get("creation_time")
        except Exception:
            pass
    return None, None


def frames(video, out_dir, n=36, width=960):
    """Extract n evenly spaced frames. -> list of file paths."""
    os.makedirs(out_dir, exist_ok=True)
    ff = ffmpeg()
    if not ff:
        raise RuntimeError("ffmpeg is not installed; install it (apt/brew/winget) or send 8-12 photos of the turn instead")
    dur, _ = duration(video)
    dur = dur or 10.0
    for f in os.listdir(out_dir):
        if f.startswith("frame_"):
            os.remove(os.path.join(out_dir, f))
    subprocess.run([ff, "-v", "error", "-y", "-i", video, "-vf", f"fps={n / dur:.6f},scale={width}:-2", os.path.join(out_dir, "frame_%03d.jpg")],
                   check=True, timeout=600)
    fs = sorted(os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.startswith("frame_"))
    return fs


def _small_gray(path, size=(48, 36)):
    return np.asarray(Image.open(path).convert("L").resize(size, Image.BILINEAR), dtype=np.float32)


def turn_estimate(paths):
    """How far the phone turned, from the video closing the loop (last frames looking like the first).
    -> (turn degrees, confidence 0..1)."""
    if len(paths) < 8:
        return 360.0, 0.0
    a = _small_gray(paths[0]); a = (a - a.mean()) / (a.std() + 1e-6)
    best, bi = -1, None
    for i in range(len(paths) // 2, len(paths)):
        b = _small_gray(paths[i]); b = (b - b.mean()) / (b.std() + 1e-6)
        c = float((a * b).mean())
        if c > best:
            best, bi = c, i
    if best >= 0.75 and bi is not None:
        n = len(paths)
        return 360.0 * (n - 1) / bi, min(1.0, (best - 0.75) / 0.2)
    return 360.0, 0.0


def strip(paths, hfov_deg, turn_deg=360.0, height=600):
    """Slit-scan strip: the middle slice of every frame, laid side by side, assuming a steady turn.
    Returns an image whose width maps to turn_deg (left edge = start of the video)."""
    n = len(paths)
    per = turn_deg / n                       # degrees of turn per frame
    tiles = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        w, h = im.size
        sw = max(8, int(w * per / hfov_deg))
        x0 = (w - sw) // 2
        t = im.crop((x0, 0, x0 + sw, h))
        t = t.resize((max(1, int(per * draw.PPD)), height), Image.LANCZOS)
        tiles.append(t)
    W = sum(t.size[0] for t in tiles)
    out = Image.new("RGB", (W, height))
    x = 0
    for t in tiles:
        out.paste(t, (x, 0)); x += t.size[0]
    return out


def skyline_real(img, el_top, el_bottom):
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    H, W = a.shape[:2]
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx = a.max(axis=2); mn = a.min(axis=2)
    sky = ((mx > 150) & ((mx - mn) < 60)) | ((b > r + 12) & (b > g + 4) & (b > 90))
    notsky = ~sky
    run = np.zeros_like(notsky, dtype=np.int16)
    run[0] = notsky[0]
    for y in range(1, H):
        run[y] = (run[y - 1] + 1) * notsky[y]
    hit = run >= 8
    first = np.full(W, H - 1)
    anyhit = hit.any(axis=0)
    first[anyhit] = hit.argmax(axis=0)[anyhit] - 7
    return el_top - first / (H - 1) * (el_top - el_bottom)


def skyline_drawn(pn):
    a = np.asarray(pn).astype(np.int16)
    sky = (abs(a[..., 0] - 236) < 6) & (abs(a[..., 1] - 242) < 6) & (abs(a[..., 2] - 252) < 6)
    notsky = ~sky
    first = notsky.argmax(axis=0)
    first[~notsky.any(axis=0)] = a.shape[0] - 1
    return draw.E_HI - first / draw.PPD


def match_skyline(real_profile, drawn_profile):
    """Circular cross-correlation. -> (bearing of the real strip's LEFT edge, score, gap to the runner-up)."""
    W = len(drawn_profile)
    rr = np.interp(np.linspace(0, 1, W, endpoint=False), np.linspace(0, 1, len(real_profile), endpoint=False), real_profile)
    rr = rr - rr.mean(); dd = drawn_profile - drawn_profile.mean()
    rr = rr / (np.linalg.norm(rr) + 1e-9); dd = dd / (np.linalg.norm(dd) + 1e-9)
    c = np.fft.irfft(np.fft.rfft(dd) * np.conj(np.fft.rfft(rr)), n=W)
    s = int(np.argmax(c)); best = float(c[s])
    mask = np.ones(W, bool)
    for k in range(-200, 201):
        mask[(s + k) % W] = False
    second = float(c[mask].max()) if mask.any() else 0.0
    return (s / draw.PPD) % 360, best, best - second


def analyse(video, lat, lon, out_dir, hfov_deg=65.0, n=36, turn=None, utc=None, vfov_deg=None):
    """Everything the spin gives: strip, skyline match, sun check. -> dict (and files in out_dir)."""
    from . import mapdata
    lat, lon, moved, road = mapdata.snap_to_road(lat, lon)
    paths = frames(video, os.path.join(out_dir, "frames"), n=n)
    est_turn, conf = turn_estimate(paths)
    turn_used = turn or (est_turn if conf > 0 else 360.0)
    st = strip(paths, hfov_deg, turn_used)
    st.save(os.path.join(out_dir, "strip.jpg"), quality=88)
    draw.ruled_strip(st).save(os.path.join(out_dir, "strip_ruled.jpg"), quality=88)
    out = {"frames": len(paths), "turn_deg_used": round(turn_used, 1), "turn_from_loop_closure": {"deg": round(est_turn, 1), "confidence": round(conf, 2)},
           "strip": os.path.join(out_dir, "strip_ruled.jpg"), "position_used": {"lat": round(lat, 6), "lon": round(lon, 6)}}
    if moved:
        out["position_note"] = f"the given position was inside a building (GPS drift); moved {moved} m onto {road or 'the nearest road'}"
    im = Image.open(paths[0]); w, h = im.size
    vf = vfov_deg or 2 * math.degrees(math.atan(math.tan(math.radians(hfov_deg / 2)) * h / w))
    el_top, el_bot = vf / 2, -vf / 2
    # skyline match (only meaningful for a full turn)
    try:
        pn = draw.around_view(lat, lon)
        pn.save(os.path.join(out_dir, "around.png"))
        if abs(turn_used - 360) < 25:
            real = skyline_real(st, el_top, el_bot)
            left, score, gap = match_skyline(real, skyline_drawn(pn))
            out["skyline_match"] = {"left_edge_bearing": round(left, 1), "last_frame_bearing": round((left + turn_used * (len(paths) - 1) / len(paths)) % 360, 1),
                                    "score": round(score, 3), "gap_to_runner_up": round(gap, 3),
                                    "trust": "good" if gap > 0.08 else "weak" if gap > 0.04 else "poor"}
        else:
            out["skyline_match"] = {"skipped": "not a full turn"}
    except Exception as ex:
        out["skyline_match"] = {"error": str(ex)[:120]}
    # sun check: which frame has the sun blowing out the top of the picture
    if utc is not None:
        az, el = sunmod.position(utc, lat, lon)
        out["sun"] = {"azimuth": round(az, 1), "elevation": round(el, 1)}
        if el > el_top + 3:
            out["sun"]["note"] = f"sun stands {el:.0f} degrees high, above what a level phone sees ({el_top:.0f}); no sun check from this video"
        elif el > 2:
            scores = []
            for i, p in enumerate(paths):
                a = np.asarray(Image.open(p).convert("RGB")).astype(int)
                Hf = a.shape[0]
                # the sun's row for a level phone: perspective, not linear
                fpx = (Hf / 2) / math.tan(math.radians(vf / 2))
                r_sun = Hf / 2 - fpx * math.tan(math.radians(el))
                r0, r1 = int(max(0, r_sun - 0.12 * Hf)), int(min(Hf, r_sun + 0.12 * Hf))
                if r1 - r0 < 4:
                    scores.append((0.0, 0.5)); continue
                band = a[r0:r1]
                white = (band.min(axis=2) > 245)
                col = white.sum(axis=0).astype(float)
                k = max(5, a.shape[1] // 40); sm = np.convolve(col, np.ones(k) / k, mode="same")
                scores.append((float(sm.max()), int(sm.argmax()) / a.shape[1]))
            best = max(range(len(scores)), key=lambda i: scores[i][0])
            strength, frac = scores[best]
            if strength >= 8 and el < 75:
                heading0 = (az - (best / len(paths) * turn_used + (frac - 0.5) * hfov_deg)) % 360
                out["sun"].update(frame_with_sun=best, strength=round(strength), first_frame_bearing=round(heading0, 1),
                                  last_frame_bearing=round((heading0 + turn_used * (len(paths) - 1) / len(paths)) % 360, 1))
            else:
                out["sun"]["note"] = "no frame shows the sun clearly (overcast, or sun too high / behind buildings)"
    return out
