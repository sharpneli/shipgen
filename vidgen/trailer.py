#!/usr/bin/env python3
"""
trailer: the Fleetwright faux trailer, cut from vidgen clips plus the pieces drawn here (the design-bureau sheets,
title cards and the animated end card from stylecard.html). The look is the stylecard's: night sea, bone, brass,
Bodoni Moda for display and IBM Plex Mono for everything else (vidgen/fonts, OFL).

The footage comes from vidgen.py with --clean (no HUD) at 1920x1080 into vidgen/out/trailer/; see TRAILER_CLIPS for
the command lines. Then:

    ~/.venv/bin/python vidgen/trailer.py                  # -> vidgen/out/fleetwright_trailer.mp4
    ~/.venv/bin/python vidgen/trailer.py --still 14.2     # one PNG of the cut at that time
    ~/.venv/bin/python vidgen/trailer.py --only sheets    # just the design-bureau montage (or: end, cards)

The swing from the zoom into the battle is footage too, rendered from the battle's sim through a moving camera:

    ~/.venv/bin/python vidgen/trailer.py --render-swing --chunks 4   # -> vidgen/out/trailer/swing.mp4
    ~/.venv/bin/python vidgen/trailer.py --render-swing 50           # one frame of it as a PNG

Everything is drawing with numpy and pillow; imageio-ffmpeg reads the clips and writes the MP4.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DESIGNS = ROOT / "out_designs"
CLIPS = HERE / "out" / "trailer"
FONTS = HERE / "fonts"
W, H, FPS = 1920, 1080, 30

# the stylecard's palette
NIGHT = (16, 22, 27)
HAZE = (138, 154, 163)
BONE = (232, 228, 218)
BRASS = (201, 165, 92)
SIGNAL = (178, 58, 46)

# vidgen command lines for the footage (all with --size 1920x1080 --clean --out vidgen/out/trailer)
LINE, ENEMY = "lion+lion+lion+tiger_1914", "seydlitz+seydlitz+seydlitz+seydlitz"
TRAILER_CLIPS = {
    "lion_s6.mp4": "lion --scale 6 --seconds 9 --fire 3",
    "lion_explode_A_B_fit0.45.mp4": "lion --fit 0.45 --explode A,B --seconds 30",
    f"{LINE}_zoom.mp4": f"{LINE} --zoom",
    f"{LINE}_vs_{ENEMY}.mp4": f"{LINE} --vs {ENEMY} --fire 26 --seconds 34",
    f"{LINE}_vs_{ENEMY}_s2_f1.mp4": f"{LINE} --vs {ENEMY} --fire 26 --seconds 34 --focus 1 --scale 2",
    f"{LINE}_vs_{ENEMY}_s1.6_f4.mp4": f"{LINE} --vs {ENEMY} --fire 26 --seconds 34 --focus 4 --scale 1.6",
}


# ---------------------------------------------------------------------------------------------------------- type
@lru_cache(None)
def mono(size, medium=False):
    return ImageFont.truetype(str(FONTS / ("IBMPlexMono-Medium.ttf" if medium else "IBMPlexMono-Regular.ttf")), size)


@lru_cache(None)
def serif(size, weight=800):
    f = ImageFont.truetype(str(FONTS / "BodoniModa.ttf"), size)
    # a low optical size: at the display opsz (96) Bodoni Moda's hairlines go under a pixel and x264 eats them
    f.set_variation_by_axes([weight, min(20, max(6, size * 0.75))])
    return f


def tracked(d, xy, text, font, fill, track=0.0, anchor="l"):
    """Text with letter spacing (CSS letter-spacing in ems), as the stylecard sets it. anchor l / m / r on x;
    returns the drawn width."""
    sp = track * font.size
    widths = [d.textlength(c, font=font) for c in text]
    total = sum(widths) + sp * max(0, len(text) - 1)
    x, y = xy
    x -= {"l": 0, "m": total / 2, "r": total}[anchor]
    for c, w in zip(text, widths):
        d.text((x, y), c, font=font, fill=fill)
        x += w + sp
    return total


def ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def ease_out(x):
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


# ------------------------------------------------------------------------------------------- design bureau sheets
# (id, display title, subtitle). Order is the montage's; the last one goes to sea.
MONTAGE = [
    ("devastation", "DEVASTATION", "BREASTWORK TURRET SHIP · 1873"),
    ("bouvet", "BOUVET", "PRE-DREADNOUGHT · “FLOATING HOTEL”"),
    ("dreadnought", "DREADNOUGHT", "ALL-BIG-GUN BATTLESHIP · 1906"),
    ("doom", "DOOM", "COASTAL BATTLESHIP OF DOOM · 1900"),
    ("babel", "TOUR DE BABEL", "TEN CALIBRES · NO TWO SHELLS ALIKE"),
    ("yamato", "YAMATO", "BATTLESHIP · 1941"),
    ("overloaded", "TOO MUCH SHIP", "HEAVY CRUISER (ALLEGEDLY)"),
    ("supercarrier", "SUPERCARRIER", "CONVENTIONAL · 1960S"),
    ("lion", "LION", "BATTLECRUISER · 1912"),
]
# each sheet's time on screen, s: speeding up, then Lion holds for the stamp and the drop into the sea
MONTAGE_S = [1.5, 1.3, 1.1, 0.95, 0.8, 0.7, 0.6, 0.55]
LION_HOLD_S = 2.6

PLAN_BOX = (64, 128, 1300, 548)        # x0, y0, x1, y1
CUT_BOX = (64, 610, 1300, 1012)
SPEC_X = (1388, 1856)
TYPES = {"BB": "BATTLESHIP", "BC": "BATTLECRUISER", "CA": "HEAVY CRUISER", "CVA": "ATTACK CARRIER"}


class Design:
    """One exported design as the sheet shows it: plan view at rest (shipgen's preview_rest.png), the internal
    cutaway (hitbox_internal.png), stats and arcs from report.json and sprite.json."""

    def __init__(self, did, title, sub):
        self.id, self.title, self.sub = did, title, sub
        d = DESIGNS / did
        self.report = json.load(open(d / "report.json"))
        self.sprite = json.load(open(d / "sprite.json"))
        r, inp = self.report["results"], self.report["inputs"]
        self.stats = dict(length=r["length_m"], beam=r["beam_m"], draught=r["draught_m"],
                          disp=r["standard_displacement_t"], speed=inp.get("speed_kn", 0), power=r["power_shp"],
                          range=inp.get("range_nm", 0), crew=r["crew"])
        self.type = TYPES.get(inp.get("type"), inp.get("type", ""))
        guns = Counter()
        tt = self.sprite["turret_types"]
        for m in self.sprite["mounts"]:
            desc = tt[m["type"]]["desc"]                       # "2 x 343mm/45"
            n, cal = desc.split(" x ")
            guns[(m["kind"] == "main", cal)] += int(n)
        def calib(c):
            return float(c.split("mm")[0])
        self.arm = [f"{n} × {c.replace('mm', ' mm')}" for (main, c), n in
                    sorted(guns.items(), key=lambda kv: (not kv[0][0], -calib(kv[0][1])))]
        self.note = (self.report["warnings"] or ["None. Suspicious."])[0]

        prev = Image.open(d / "preview_rest.png").convert("RGBA")
        self.pad = (prev.width - self.sprite["size_px"][0]) / 2
        x0, y0, x1, y1 = PLAN_BOX
        bw, bh = x1 - x0 - 90, y1 - y0 - 130
        hull_w = self.sprite["size_px"][0]
        self.k = min(bw / hull_w, bh / self.sprite["size_px"][1] * 0.55)   # plan px per sprite px
        pw, ph = round(prev.width * self.k), round(prev.height * self.k)
        self.plan = prev.resize((pw, ph), Image.LANCZOS)
        self.plan_xy = ((x0 + x1) / 2 - pw / 2, (y0 + y1) / 2 - ph / 2 - 14)
        self.plan_full = prev

        cut = np.asarray(Image.open(d / "hitbox_internal.png").convert("RGB")).astype(np.float32)
        cut = cut[76:]                                        # the title and legend rows
        bg = np.median(cut[:8, :8].reshape(-1, 3), axis=0)
        a = np.clip(np.abs(cut - bg).max(axis=2) / 22.0, 0, 1)
        grey = cut.mean(axis=2, keepdims=True)
        cut = grey + (cut - grey) * 0.75                      # a touch muted, to sit with the palette
        rgba = np.dstack([np.clip(cut, 0, 255), a * 255]).astype(np.uint8)
        im = Image.fromarray(rgba, "RGBA")
        bb = im.getbbox()
        im = im.crop(bb)
        cx0, cy0, cx1, cy1 = CUT_BOX
        kk = min((cx1 - cx0 - 40) / im.width, (cy1 - cy0 - 60) / im.height)
        self.cut = im.resize((round(im.width * kk), round(im.height * kk)), Image.LANCZOS)
        self.cut_xy = ((cx0 + cx1) / 2 - self.cut.width / 2, cy0 + 40 + (cy1 - cy0 - 40) / 2 - self.cut.height / 2)

        self.arcs = self._arcs()

    def _arcs(self):
        """The main mounts' arcs of fire as brass fans on the plan, drawn at 2x and brought down."""
        S = 2
        x0, y0, x1, y1 = PLAN_BOX
        im = Image.new("RGBA", ((x1 - x0) * S, (y1 - y0) * S), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        px, py = self.plan_xy
        mains = [m for m in self.sprite["mounts"] if m["kind"] == "main"] or self.sprite["mounts"][:4]
        R = 0.13 * (x1 - x0)
        for m in mains:
            mx = (px + (m["px"][0] + self.pad) * self.k - x0) * S
            my = (py + (m["px"][1] + self.pad) * self.k - y0) * S
            for a0, a1 in m["arcs_deg"]:
                box = [mx - R * S, my - R * S, mx + R * S, my + R * S]
                d.pieslice(box, a0, a1, fill=BRASS + (16,))
                d.arc(box, a0, a1, fill=BRASS + (120,), width=S)
                for a in (a0, a1):
                    ar = math.radians(a)
                    d.line([(mx, my), (mx + R * S * math.cos(ar), my + R * S * math.sin(ar))],
                           fill=BRASS + (70,), width=S)
        return im.resize((x1 - x0, y1 - y0), Image.LANCZOS)


SPEC_ROWS = [
    ("LENGTH", "length", lambda v: f"{v:.1f} m"),
    ("BEAM", "beam", lambda v: f"{v:.1f} m"),
    ("DRAUGHT", "draught", lambda v: f"{v:.2f} m"),
    ("DISPLACEMENT", "disp", lambda v: f"{v:,.0f} t"),
    ("SPEED", "speed", lambda v: f"{v:.1f} kn"),
    ("POWER", "power", lambda v: f"{v:,.0f} shp"),
    ("RANGE", "range", lambda v: f"{v:,.0f} nm"),
    ("CREW", "crew", lambda v: f"{v:,.0f}"),
]


@lru_cache(None)
def sheet_base():
    """The drafting sheet without a design: grid, frame, rules, box captions."""
    im = Image.new("RGB", (W, H), NIGHT)
    d = ImageDraw.Draw(im, "RGBA")
    for x in range(64, W - 63, 32):
        d.line([(x, 104), (x, H - 56)], fill=HAZE + (14 if (x - 64) % 160 else 26,))
    for y in range(104, H - 55, 32):
        d.line([(64, y), (W - 64, y)], fill=HAZE + (14 if (y - 104) % 160 else 26,))
    d.line([(64, 96), (W - 64, 96)], fill=BRASS, width=2)
    d.line([(64, H - 48), (W - 64, H - 48)], fill=HAZE + (90,), width=1)
    for (x0, y0, x1, y1), cap in ((PLAN_BOX, "PLAN  ·  ARCS OF FIRE"), (CUT_BOX, "INTERNAL ARRANGEMENT")):
        d.rectangle([x0, y0, x1, y1], fill=NIGHT + (200,), outline=HAZE + (70,))
        for cx, cy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
            sx, sy = (1 if cx == x0 else -1), (1 if cy == y0 else -1)
            d.line([(cx, cy), (cx + 18 * sx, cy)], fill=BRASS, width=2)
            d.line([(cx, cy), (cx, cy + 18 * sy)], fill=BRASS, width=2)
        tracked(d, (x0 + 16, y0 + 12), cap, mono(15, True), BRASS, 0.25)
    sx0, sx1 = SPEC_X
    d.rectangle([sx0 - 28, PLAN_BOX[1], sx1, CUT_BOX[3]], fill=NIGHT + (200,), outline=HAZE + (70,))
    tracked(d, (64, 50), "FLEETWRIGHT  ·  DESIGN BUREAU", mono(17, True), HAZE, 0.2)
    tracked(d, (64, H - 38), "ALL DIMENSIONS MOULDED  ·  DO NOT SCALE FROM DRAWING  ·  NO WARRANTY EXPRESSED OR "
            "IMPLIED", mono(13), HAZE + (150,), 0.18)
    return im


def wrap(d, text, font, width):
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if d.textlength(t, font=font) > width and cur:
            lines.append(cur)
            cur = w_
        else:
            cur = t
    return lines + ([cur] if cur else [])


def sheet_frame(designs, i, t, dur, prev_stats=None, stamp=None, ui=1.0, plan=True):
    """Design i's sheet t s after it came up (dur s on screen). The plan view and cutaway are revealed by a brass
    scan line, the title types in and the numbers roll from the previous design's. stamp: seconds since the
    APPROVED stamp landed (None: no stamp). ui < 1 fades everything but the plan view toward the night sea (the
    drop into the water); plan=False leaves the plan view out (the edit draws it moving)."""
    dsg = designs[i]
    base = sheet_base().copy()
    im = base
    d = ImageDraw.Draw(im, "RGBA")
    n = len(designs)
    tracked(d, (W - 64, 50), f"DESIGN No. {i + 1:03d}  ·  SHEET {i + 1} OF {n}", mono(17, True), HAZE, 0.2,
            anchor="r")

    rev = min(0.4, dur * 0.35)
    scan = ease_out(t / rev)                                 # 0..1 across the boxes

    def reveal(layer, xy, box):
        x0, _, x1, _ = box
        edge = x0 + (x1 - x0) * scan
        lx = int(round(edge - xy[0]))
        if lx <= 0:
            return
        crop = layer.crop((0, 0, min(layer.width, lx), layer.height))
        im.paste(crop, (int(round(xy[0])), int(round(xy[1]))), crop)

    if plan:
        reveal(dsg.arcs, PLAN_BOX[:2], PLAN_BOX)
        reveal(dsg.plan, dsg.plan_xy, PLAN_BOX)
    reveal(dsg.cut, dsg.cut_xy, CUT_BOX)
    if scan < 1:
        for x0, y0, x1, y1 in (PLAN_BOX, CUT_BOX):
            ex = x0 + (x1 - x0) * scan
            d.rectangle([ex - 1, y0 + 1, ex + 1, y1 - 1], fill=BRASS + (230,))
            d.rectangle([ex - 14, y0 + 1, ex - 2, y1 - 1], fill=BRASS + (28,))

    # dimension line under the plan
    px, py = dsg.plan_xy
    hx0 = px + dsg.pad * dsg.k
    hx1 = hx0 + dsg.sprite["size_px"][0] * dsg.k
    yy = PLAN_BOX[3] - 34
    a = int(200 * ease(t / rev))
    d.line([(hx0, yy), (hx1, yy)], fill=HAZE + (a,), width=1)
    for x in (hx0, hx1):
        d.line([(x, yy - 8), (x, yy + 8)], fill=HAZE + (a,), width=1)
    lab = f"{dsg.stats['length']:.1f} m  O.A."
    tw = d.textlength(lab, font=mono(15))
    d.rectangle([(hx0 + hx1) / 2 - tw / 2 - 10, yy - 10, (hx0 + hx1) / 2 + tw / 2 + 10, yy + 10], fill=NIGHT)
    d.text(((hx0 + hx1) / 2 - tw / 2, yy - 10), lab, font=mono(15), fill=HAZE + (a,))

    # spec column
    sx0, sx1 = SPEC_X
    y = PLAN_BOX[1] + 26
    title = dsg.title[:max(1, math.ceil(len(dsg.title) * min(1.0, t / max(0.12, rev * 0.8))))]
    size = 76
    while size > 30 and d.textlength(dsg.title, font=serif(size)) > sx1 - sx0:
        size -= 2
    d.text((sx0, y), title, font=serif(size), fill=BONE)
    y += size + 18
    tracked(d, (sx0, y), dsg.sub, mono(15, True), BRASS, 0.12)
    y += 34
    d.line([(sx0, y), (sx1, y)], fill=BRASS + (160,), width=1)
    y += 18
    roll = ease_out(t / (rev * 1.1))
    rows = [("TYPE", None, dsg.type)] + SPEC_ROWS
    for label, key, fmt in rows:
        if key is None:
            val = fmt
        else:
            v1 = dsg.stats[key]
            v0 = prev_stats[key] if prev_stats else 0.0
            val = fmt(v0 + (v1 - v0) * roll)
        tracked(d, (sx0, y), label, mono(17), HAZE, 0.12)
        d.text((sx1 - d.textlength(val, font=mono(21, True)), y - 3), val, font=mono(21, True), fill=BONE)
        y += 36
    y += 6
    d.line([(sx0, y), (sx1, y)], fill=BRASS + (160,), width=1)
    y += 16
    tracked(d, (sx0, y), "ARMAMENT", mono(17), HAZE, 0.12)
    y += 32
    for line in (dsg.arm[:4] + (["+ MORE. MANY MORE."] if len(dsg.arm) > 4 else [])) or ["NONE (AIRCRAFT)"]:
        d.text((sx0, y), line, font=mono(19, True), fill=BONE)
        y += 28
    y += 10
    d.line([(sx0, y), (sx1, y)], fill=BRASS + (160,), width=1)
    y += 16
    tracked(d, (sx0, y), "BUREAU NOTES", mono(17), HAZE, 0.12)
    y += 30
    for line in wrap(d, dsg.note, mono(16), sx1 - sx0)[:4]:
        d.text((sx0, y), line, font=mono(16), fill=HAZE)
        y += 23

    if stamp is not None:
        _stamp(im, stamp)

    if ui < 1:
        a = np.asarray(im).astype(np.float32)
        a = np.array(NIGHT, np.float32) + (a - np.array(NIGHT, np.float32)) * ui
        im = Image.fromarray(a.astype(np.uint8))
    return im


@lru_cache(None)
def stamp_image():
    """APPROVED, a brass rubber stamp (the stylecard keeps signal red for flashes and hits): double border, slightly worn."""
    S = 2
    w, h = 470 * S, 150 * S
    im = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([4 * S, 4 * S, w - 4 * S, h - 4 * S], radius=10 * S, outline=255, width=6 * S)
    d.rounded_rectangle([16 * S, 16 * S, w - 16 * S, h - 16 * S], radius=6 * S, outline=255, width=2 * S)
    t = "APPROVED"
    size = 84
    while True:
        f = serif(size * S)
        sp = 0.06 * f.size
        tw = sum(d.textlength(c, font=f) for c in t) + sp * (len(t) - 1)
        if tw < w - 64 * S:
            break
        size -= 2
    x = w / 2 - tw / 2
    bb = d.textbbox((0, 0), t, font=f)
    for c in t:
        d.text((x, h / 2 - (bb[1] + bb[3]) / 2), c, font=f, fill=255)
        x += d.textlength(c, font=f) + sp
    rng = np.random.default_rng(7)
    a = np.asarray(im).astype(np.float32) / 255
    wear = rng.random((h // 6, w // 6))
    wear = np.asarray(Image.fromarray((wear * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR)) / 255
    a *= np.clip((wear - 0.12) * 3, 0.25, 1)
    im = Image.fromarray((a * 255).astype(np.uint8)).resize((w // S, h // S), Image.LANCZOS)
    rgba = Image.new("RGBA", im.size, BRASS)
    rgba.putalpha(im)
    return rgba.rotate(8, resample=Image.BICUBIC, expand=True)


def _stamp(im, ts):
    """The stamp slams down: from 1.6x and transparent to 1x in 0.12 s, a dark ring of ink pressed out."""
    if ts < 0:
        return
    st = stamp_image()
    k = 1 + 0.6 * (1 - ease_out(ts / 0.12))
    a = min(1.0, ts / 0.08) * 0.92
    s2 = st.resize((round(st.width * k), round(st.height * k)), Image.LANCZOS)
    alpha = np.asarray(s2.getchannel("A")).astype(np.float32) * a
    s2.putalpha(Image.fromarray(alpha.astype(np.uint8)))
    cx, cy = 1060, 470
    im.paste(s2, (round(cx - s2.width / 2), round(cy - s2.height / 2)), s2)


# ------------------------------------------------------------------------------------------------ the end card
# stylecard.html's #ship SVG (viewBox 600 x 120), part by part in the order they're drawn in
END_SHIP = [
    ("hull", "poly", [(8, 70), (596, 63), (578, 92), (34, 92)]),
    ("barbettes", "rect", [(410, 57, 24, 10), (134, 57, 24, 13)]),
    ("turrets", "rrect", [(455, 58, 36, 11), (404, 49, 36, 11), (128, 49, 36, 11), (78, 58, 36, 11)]),
    ("guns", "line3", [(490, 62, 536, 60), (439, 53, 490, 50), (129, 53, 84, 50), (79, 62, 36, 60)]),
    ("superstructure", "poly2", [[(336, 64), (336, 40), (352, 40), (352, 32), (384, 32), (388, 64)],
                                 [(190, 46), (220, 46), (220, 66), (190, 66)]]),
    ("funnels", "poly2", [[(282, 64), (286, 22), (306, 22), (304, 64)], [(236, 64), (240, 26), (258, 26), (256, 64)]]),
    ("tops", "rrect", [(355, 2, 16, 9), (197, 12, 12, 7)]),
    ("masts", "line2", [(363, 32, 363, 11), (363, 32, 352, 11), (363, 32, 374, 11), (203, 46, 203, 19)]),
]
END_S = 8.5
END_SCALE = W / 1600                  # the card is laid out at 1600 x 900


def end_frame(t, ss=2):
    """stylecard.html's end card at time t of its animation: the waterline runs out in brass, the ship builds up
    part by part, the wordmark closes its tracking in, the rules grow, the release line types on and the guns fire
    once (signal red is for muzzle flashes)."""
    k = END_SCALE * ss
    im = Image.new("RGB", (W * ss, H * ss), NIGHT)
    d = ImageDraw.Draw(im, "RGBA")

    def al(t0, dur=0.35):
        return ease((t - t0) / dur)

    # corners
    a = al(0.2, 0.6)
    for txt, x, anc in (("SHIPGEN · DESIGN No. 001", 64, "l"), ("SHEET 1 OF 1", 1600 - 64, "r")):
        tracked(d, (x * k, 48 * k), txt, mono(round(14 * k)), HAZE + (int(255 * a),), 0.2, anchor=anc)

    # the ship: 640 x 128 px for the 600 x 120 viewBox, centred, its top at 259 px (the flex column's)
    sk = 640 / 600 * k
    ox, oy = (800 - 320) * k, 259 * k

    def P(x, y):
        return (ox + x * sk, oy + y * sk)

    # waterline first, drawn out from the stern
    wl = ease_out((t - 0.3) / 0.9)
    if wl > 0:
        d.line([P(0, 96), P(600 * wl, 96)], fill=BRASS + (255,), width=round(1.5 * sk))
    for n, (name, kind, items) in enumerate(END_SHIP):
        t0 = 0.6 + n * 0.14
        a = al(t0, 0.3)
        if a <= 0:
            continue
        rise = (1 - ease_out((t - t0) / 0.3)) * 6          # parts settle down onto the hull
        c = HAZE + (int(255 * a),)
        for it in items:
            if kind == "poly":
                d.polygon([P(x, y - rise) for x, y in items], fill=c)
                break
            if kind == "poly2":
                d.polygon([P(x, y - rise) for x, y in it], fill=c)
            elif kind == "rect":
                x, y, w_, h_ = it
                d.rectangle([P(x, y - rise), P(x + w_, y + h_ - rise)], fill=c)
            elif kind == "rrect":
                x, y, w_, h_ = it
                d.rounded_rectangle([P(x, y - rise), P(x + w_, y + h_ - rise)], radius=2 * sk, fill=c)
            elif kind in ("line3", "line2"):
                x0, y0, x1, y1 = it
                g = ease_out((t - t0) / 0.3)               # guns run out, masts go up
                d.line([P(x0, y0), P(x0 + (x1 - x0) * g, y0 + (y1 - y0) * g)], fill=c,
                       width=round((3 if kind == "line3" else 2) * sk))
    # wake
    a = al(0.6 + len(END_SHIP) * 0.14, 0.5) * 0.45
    for x0, x1, y in ((40, 300, 104), (90, 250, 112)):
        d.line([P(x0, y), P(x1, y)], fill=HAZE + (int(255 * a),), width=max(1, round(sk)))

    # one salvo from the forward guns, late: a signal-red flash and a puff of haze at each muzzle
    for tf, (x, y) in ((5.6, (536, 60)), (5.75, (490, 50))):
        ft = t - tf
        if 0 <= ft < 1.6:
            fl = max(0.0, 1 - ft / 0.12)
            if fl > 0:
                r = 9 * sk
                d.ellipse([P(x + 2, y)[0] - r, P(x, y)[1] - r * 0.6, P(x + 2, y)[0] + r, P(x, y)[1] + r * 0.6],
                          fill=SIGNAL + (int(255 * fl),))
            pa = max(0.0, 1 - ft / 1.6) * min(1.0, ft / 0.1) * 0.5
            pr = (4 + 14 * ease_out(ft / 1.6)) * sk
            cx, cy = P(x + 8 + 10 * ease_out(ft / 1.6), y - 4 * ft)
            d.ellipse([cx - pr, cy - pr * 0.7, cx + pr, cy + pr * 0.7], fill=HAZE + (int(255 * pa * 0.6),))

    # wordmark: tracking closes from 0.45 to 0.1 em as it fades in
    wt = ease_out((t - 1.7) / 1.4)
    if t > 1.7:
        f = serif(round(148 * k))
        tr = 0.1 + 0.35 * (1 - wt)
        y = 427 * k
        bb = d.textbbox((0, 0), "F", font=f)
        tracked(d, (800 * k + 0.5 * tr * f.size, y + (148 * k - (bb[3] - bb[1])) / 2 - bb[1]), "FLEETWRIGHT", f,
                BONE + (int(255 * min(1.0, (t - 1.7) / 0.8)),), tr, anchor="m")
    # rules grow outward from the subtitle, then the subtitle
    g = ease_out((t - 2.9) / 0.6)
    if g > 0:
        f = mono(round(26 * k), True)
        tw = sum(d.textlength(c, font=f) for c in "NAVAL BATTLES") + 0.55 * f.size * 12
        cy = 624 * k
        x_in = 800 * k - tw / 2 - 32 * k
        d.rectangle([x_in - 140 * k * g, cy - k, x_in, cy + k], fill=BRASS)
        x_in2 = 800 * k + tw / 2 + 32 * k
        d.rectangle([x_in2, cy - k, x_in2 + 140 * k * g, cy + k], fill=BRASS)
        a = al(3.2, 0.5)
        bb = d.textbbox((0, 0), "N", font=f)
        tracked(d, (800 * k, cy - (bb[1] + bb[3]) / 2), "NAVAL BATTLES", f, BRASS + (int(255 * a),), 0.55,
                anchor="m")
    # the release line types on, and the aside comes after a beat
    f = mono(round(16 * k))
    main_, aside = "FREE · PC · COMING AT SOME POINT", " [HAH, AS IF]"
    n = int(max(0.0, t - 3.8) / 0.045)
    txt = main_[:n]
    if t > 5.1:
        txt = main_ + aside[:int((t - 5.1) / 0.06) + 1]
    full = main_ + aside
    if txt:
        tw = sum(d.textlength(c, font=f) for c in full) + 0.3 * f.size * (len(full) - 1)
        x0 = 800 * k - tw / 2
        tracked(d, (x0, (900 - 56 - 16) * k), txt, f, HAZE, 0.3)
        if int(t * 2.2) % 2 == 0 and t < 6.6:            # a cursor while it types
            cx = x0 + sum(d.textlength(c, font=f) for c in txt) + 0.3 * f.size * len(txt)
            d.rectangle([cx, (900 - 56 - 14) * k, cx + 9 * k, (900 - 56 + 2) * k], fill=HAZE + (200,))
    return im.resize((W, H), Image.LANCZOS)


def end_frames():
    for i in range(int(END_S * FPS)):
        yield np.asarray(end_frame(i / FPS))


# ----------------------------------------------------------------------------------------------- title cards
def card_frame(text, t, dur, over=None):
    """A title card: Bodoni over the night sea (or over a footage frame, darkened behind the words), a brass rule
    under it, in and out in 0.3 s, pushing in slowly."""
    a = ease(t / 0.3) * ease((dur - t) / 0.3)
    if over is None:
        im = Image.new("RGB", (W, H), NIGHT)
        cy, base = H / 2, 84
    else:                                          # over footage: the lower third, so the action stays clear
        cy, base = H * 0.8, 64
        f = over.astype(np.float32)
        yy = (np.arange(H)[:, None, None] - cy) / H
        f *= 1 - 0.5 * a * np.exp(-(yy / 0.12) ** 2)
        im = Image.fromarray(f.astype(np.uint8))
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    size = round(base * (1 + 0.04 * t / dur))
    fnt = serif(size)
    bb = d.textbbox((0, 0), text, font=fnt)
    tracked(d, (W / 2, cy - (bb[1] + bb[3]) / 2 - 10), text, fnt, BONE + (int(255 * a),), 0.08, anchor="m")
    rw = 120 * ease_out(t / 0.6)
    d.rectangle([W / 2 - rw, cy + size * 0.55, W / 2 + rw, cy + size * 0.55 + 2], fill=BRASS + (int(255 * a),))
    im.paste(lay, (0, 0), lay)
    return np.asarray(im)


def card_frames(text, dur):
    for i in range(int(round(dur * FPS))):
        yield card_frame(text, i / FPS, dur)


# --------------------------------------------------------------------------------------------- clips and the cut
def ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


class Clip:
    """A clip in vidgen/out/trailer read forward only: at(t) is the frame at source time t (s), blended between
    the two nearest frames, so slow motion doesn't stutter. Times must not go backward."""

    def __init__(self, name, start=0.0):
        import imageio_ffmpeg
        self.name = name
        self.t0 = max(0.0, start - 0.5)
        self.gen = imageio_ffmpeg.read_frames(str(CLIPS / name), input_params=["-ss", f"{self.t0:.3f}"])
        meta = self.gen.__next__()
        self.size = meta["size"]
        self.fps = meta["fps"]
        self.i = -1                                   # index (from t0) of self.cur
        self.prev = self.cur = None

    def _advance(self):
        w, h = self.size
        raw = next(self.gen, None)
        if raw is None:                               # past the end: hold the last frame
            self.prev = self.cur
            self.i += 1
            return
        self.prev, self.cur = self.cur, np.frombuffer(raw, np.uint8).reshape(h, w, 3)
        self.i += 1

    def at(self, t):
        x = (t - self.t0) * self.fps
        j = int(math.floor(x))
        while self.i < j + 1:
            self._advance()
        if self.prev is None:
            return self.cur
        f = x - j
        if f < 0.02 or self.i != j + 1:
            return self.prev if f < 0.5 or self.i != j + 1 else self.cur
        return (self.prev.astype(np.float32) * (1 - f) + self.cur.astype(np.float32) * f).astype(np.uint8)

    def close(self):
        self.gen.close()


def ramp(name, pieces):
    """Frames from one clip through speed pieces [(src_from, src_to, speed), ...] played back to back (each
    piece's output lasts (src_to - src_from) / speed s)."""
    c = Clip(name, pieces[0][0])
    for s0, s1, sp in pieces:
        n = int(round((s1 - s0) / sp * FPS))
        for k in range(n):
            yield c.at(s0 + k * sp / FPS)
    c.close()


def sheets_frames(designs):
    prev = None
    for i, dsg in enumerate(designs[:-1]):
        dur = MONTAGE_S[i]
        for k in range(int(round(dur * FPS))):
            yield np.asarray(sheet_frame(designs, i, k / FPS, dur, prev))
        prev = dsg.stats
    i = len(designs) - 1
    for k in range(int(round(LION_HOLD_S * FPS))):
        t = k / FPS
        yield np.asarray(sheet_frame(designs, i, t, 1.2, prev, stamp=t - STAMP_AT))


STAMP_AT = 1.2            # s into Lion's sheet
TO_SEA = (0.5, (0.15, 1.25), (0.95, 1.6))   # s: the sheet fades out over, the plan view moves over, footage fades in
ZOOM_START = dict(scale=4.0, heading=-12.0)  # vidgen's ZOOM_S[0] and default heading: the lead centred on frame 0


def to_sea_frames(designs, clip):
    """The drop into the water: the sheet fades to the night sea while Lion's plan view turns, shrinks and slides
    onto the lead ship of the zoom clip's first frames (the same sprite, so it lands exactly), then the footage
    fades up under it."""
    dsg = designs[-1]
    full = dsg.plan_full
    org = np.array(dsg.sprite["origin_px"]) + dsg.pad              # the ship's centre in preview_rest pixels
    p0 = np.array(dsg.plan_xy) + org * dsg.k
    p1 = np.array([W / 2, H / 2])
    s0, s1 = dsg.k, ZOOM_START["scale"] / dsg.sprite["scale_px_per_m"]
    a1 = -ZOOM_START["heading"]                                     # PIL turns counter-clockwise
    fade, (m0, m1), (f0, f1) = TO_SEA
    c = Clip(clip, 0.0)
    n = int(round(f1 * FPS))
    sheet_last = None
    for i in range(n):
        t = i / FPS
        ui = 1 - ease(t / fade)
        if ui > 0 or sheet_last is None:
            sheet_last = np.asarray(sheet_frame(designs, len(designs) - 1, 5.0, 1.2, None, stamp=5.0, ui=ui,
                                                plan=False))
        frame = Image.fromarray(sheet_last if ui > 0 else np.full((H, W, 3), NIGHT, np.uint8))
        e = ease((t - m0) / (m1 - m0))
        sc = math.exp(math.log(s0) + (math.log(s1) - math.log(s0)) * e)
        ang = a1 * e
        pos = p0 + (p1 - p0) * e
        im = full.resize((max(1, round(full.width * sc)), max(1, round(full.height * sc))), Image.LANCZOS)
        im = im.rotate(ang, resample=Image.BICUBIC, expand=True)
        # where the ship's centre went: rotate org (scaled, about the image centre) by ang
        cx, cy = (org[0] - full.width / 2) * sc, (org[1] - full.height / 2) * sc
        r = math.radians(ang)
        rx, ry = cx * math.cos(r) + cy * math.sin(r), -cx * math.sin(r) + cy * math.cos(r)
        tl = pos - np.array([im.width / 2 + rx, im.height / 2 + ry])
        frame.paste(im, (round(tl[0]), round(tl[1])), im)
        fa = ease((t - f0) / (f1 - f0))
        if fa > 0:
            foot = c.at(max(0.0, t - f0)).astype(np.float32)
            out = np.asarray(frame).astype(np.float32) * (1 - fa) + foot * fa
            yield out.astype(np.uint8)
        else:
            yield np.asarray(frame)
    c.close()


# the swing from the zoom into the battle (user, 2026-10-08: the hard cut turned the ships from the zoom's heading,
# -12, to the battle's, -78, in one frame). swing.mp4 is the battle's own sim (same seed and ships as the wide shot)
# drawn through a moving camera: it starts on the zoom's camera, turned 66 deg so the ships run at -12 on screen, and
# follows the zoom's path while the zoom clip dissolves into it (that hides what differs between the two sims: the
# zoom's gun smoke); then it pulls back, swings round and pans from our line to the middle of both, and comes to rest
# on the wide shot's framing. It holds there while it dissolves into the wide shot itself: the sims match, but the
# wake's foam noise is laid out by the canvas, so the two differ a little in texture. The sea's virtual eye moves
# with the camera and the sun turns with it, so the glint stays put on screen as in both clips
SWING_XF = 0.5           # s: the dissolve from the zoom (playing on at 2x, as its last piece)
SWING_MOVE = 3.0         # s: the swing itself
SWING_HOLD = 0.4         # s: at rest on the wide shot's framing, dissolving into it
SWING_ZOOM_AT = 22.0     # the zoom clip's time where its last piece ends and the dissolve begins
SWING_CLIP = "swing.mp4"


def swing_n():
    return int(round((SWING_XF + SWING_MOVE + SWING_HOLD) * FPS))


def swing_path():
    """The swing's camera per frame: (s px/m, P world m from the battle scene's centre at the frame's centre,
    theta deg the frame is turned clockwise), plus the scale the battle scene is drawn at."""
    import vidgen as V
    lion = [DESIGNS / x for x in LINE.split("+")]
    probe = V.Scene(lion, 320, 180, FPS, -12.0, None, 1, scale=0.1)
    z = V.Zoom(W, H, FPS, -12.0, probe.ships[0].off)
    sk = V.Scene(lion, W, H, FPS, V.BATTLE_HEADING, None, 1,
                 enemy=[DESIGNS / x for x in ENEMY.split("+")]).s
    del probe
    turn = -12.0 - V.BATTLE_HEADING                    # 66: zoom-world -> screen of the battle's world
    ours = V.unit(V.BATTLE_HEADING + 90) * (-0.5 * V.BATTLE_RANGE)    # our line's centre (port of the middle)

    def zoom_cam(t):                                   # the zoom clip's camera at output time t of the swing
        s = z.s(SWING_ZOOM_AT + 2 * t)
        return np.array([math.log(s), *(ours + V.rot(z.cam(s), -turn))])

    n, i0, i1 = swing_n(), int(round(SWING_XF * FPS)), int(round((SWING_XF + SWING_MOVE) * FPS))
    end = np.array([math.log(sk), *(-V.unit(V.BATTLE_HEADING) * 0.07 * W / sk)])   # vidgen's line-ahead offset
    a = zoom_cam(i0 / FPS)
    v = (zoom_cam(i0 / FPS + 1e-3) - zoom_cam(i0 / FPS - 1e-3)) / 2e-3
    D = (i1 - i0) / FPS
    out = []
    for i in range(n):
        if i < i0:
            q, th = zoom_cam(i / FPS), turn
        elif i >= i1:
            q, th = end, 0.0
        else:                                          # cubic Hermite from the zoom's motion to rest on the wide shot
            x = (i - i0) / (i1 - i0)
            h00, h10, h01 = 2 * x**3 - 3 * x**2 + 1, x**3 - 2 * x**2 + x, -2 * x**3 + 3 * x**2
            q = a * h00 + v * D * h10 + end * h01
            th = turn * (1 - V.smootherstep(x))
        out.append((math.exp(q[0]), q[1:], th))
    return out, sk


def _swing_canvas(path, sk):
    """The battle scene's canvas: covering every frame of the path, and where the scene's centre is on it."""
    lo, hi = np.full(2, np.inf), np.full(2, -np.inf)
    for s, P, th in path:
        for cx, cy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            r = math.radians(-th)
            vx, vy = cx * W / 2 * sk / s, cy * H / 2 * sk / s
            p = sk * P + (vx * math.cos(r) - vy * math.sin(r), vx * math.sin(r) + vy * math.cos(r))
            lo, hi = np.minimum(lo, p), np.maximum(hi, p)
    lo, hi = np.floor(lo) - 8, np.ceil(hi) + 8
    Wc, Hc = (int(v) + int(v) % 2 for v in hi - lo)
    C = -lo
    v = C + sk * path[-1][1]                           # the last frame's corner on whole pixels, as the wide shot's
    return Wc, Hc, C + np.round(v) - v


def _swing_part(a, b, out):
    """Frames a..b-1 of swing.mp4 (the battle scene stepped from its start, as vidgen's chunks)."""
    import argparse as ap_
    import imageio_ffmpeg
    import vidgen as V
    path, sk = swing_path()
    Wc, Hc, C = _swing_canvas(path, sk)
    sc = V.Scene([DESIGNS / x for x in LINE.split("+")], W, H, FPS, V.BATTLE_HEADING, None, 1, seconds=34,
                 sea=V.sea_args(ap_.Namespace(beaufort=None, swell=None)), fire_s=26, scale=sk,
                 view=(Wc, Hc, C, W, H), enemy=[DESIGNS / x for x in ENEMY.split("+")])
    sc.bare = True
    sea = sc.water.sea
    sun = sea.L.copy()
    dt = 1.0 / FPS
    for _ in range(int(V.WARM_S * FPS)):
        sc.step(dt)
    sc.t = 0.0
    sc.next_ev = 0
    f0 = int(round(BATTLE_WIDE[0][0] * FPS)) - len(path)          # the battle's frame at the swing's first
    for _ in range(f0 + a):
        sc.step(dt)
    w = imageio_ffmpeg.write_frames(str(out), (W, H), fps=FPS, codec="libx264", pix_fmt_out="yuv420p",
                                    macro_block_size=1, output_params=["-crf", "16", "-preset", "medium"])
    w.send(None)
    for i in range(a, b):
        s, P, th = path[i]
        sc.set_look(s)
        k = sk / s
        X = C + sk * P
        # the eye above the frame's centre, as high as the frame's width asks; the sun turned with the camera
        sea.ex = ((np.arange(Wc) - X[0]) / sk).astype(np.float32)
        sea.ey = ((np.arange(Hc) - X[1]) / sk).astype(np.float32)
        sea.eye_h = (W / s / 2) / math.tan(math.radians(20.0))
        sea.L = np.array([*V.rot(sun[:2], -th), sun[2]], np.float32)
        sea._light_setup()
        canvas = Image.fromarray(sc.render())
        if th == 0.0 and s == sk:                      # at rest on the wide shot: the plain window, no resampling
            x0, y0 = np.round(X - (W / 2, H / 2)).astype(int)
            fr = canvas.crop((x0, y0, x0 + W, y0 + H))
        else:
            if k > 1:                                  # going out: soften first, so the bicubic doesn't alias
                canvas = canvas.filter(ImageFilter.GaussianBlur(0.5 * math.sqrt(k * k - 1)))
            r = math.radians(th)
            ca, sa = k * math.cos(r), k * math.sin(r)
            data = (ca, sa, X[0] - ca * W / 2 - sa * H / 2, -sa, ca, X[1] + sa * W / 2 - ca * H / 2)
            fr = canvas.transform((W, H), Image.AFFINE, data, resample=Image.BICUBIC)
        w.send(np.ascontiguousarray(np.asarray(fr)).tobytes())
        sc.step(dt)
        print(f"\r  {out.name}: frame {i + 1}/{b}", end="", flush=True)
    w.close()
    return out


def render_swing(chunks=2, only=None):
    """swing.mp4 into vidgen/out/trailer, in `chunks` parallel parts joined without re-encoding. only: one frame
    index, written as a PNG instead."""
    from concurrent.futures import ProcessPoolExecutor
    n = swing_n()
    if only is not None:
        p = _swing_part(only, only + 1, CLIPS / f"swing_test{only}.mp4")
        c = Clip(p.name)
        Image.fromarray(c.at(0.0)).save(HERE / "out" / f"swing_{only}.png")
        c.close()
        p.unlink()
        print("\n  wrote", HERE / "out" / f"swing_{only}.png")
        return
    tmp = CLIPS / ".swing_parts"
    tmp.mkdir(exist_ok=True)
    cuts = [round(n * j / chunks) for j in range(chunks + 1)]
    parts = [tmp / f"part{j:02d}.mp4" for j in range(chunks)]
    with ProcessPoolExecutor(chunks) as pool:
        list(pool.map(_swing_part, cuts[:-1], cuts[1:], parts))
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts))
    subprocess.run([ffmpeg(), "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                    str(CLIPS / SWING_CLIP)], check=True)
    for p in parts + [lst]:
        p.unlink()
    tmp.rmdir()
    print(f"\n  wrote {CLIPS / SWING_CLIP} ({n} frames)")


def swing_frames(zoom):
    """The dissolve from the zoom (playing on at 2x) into swing.mp4, the swing, and its dissolve at rest into the
    wide shot (up to the wide shot's first frame)."""
    n, xf, xh = swing_n(), int(round(SWING_XF * FPS)), int(round(SWING_HOLD * FPS))
    t0 = BATTLE_WIDE[0][0] - n / FPS                   # the battle's time at the swing's first frame
    zc, sw, bc = Clip(zoom, SWING_ZOOM_AT), Clip(SWING_CLIP), Clip(f"{LINE_CLIP}.mp4", t0 + (n - xh) / FPS)
    for i in range(n):
        f = sw.at(i / FPS)
        if i < xf:
            a = ease((i + 1) / (xf + 1))
            f = (zc.at(SWING_ZOOM_AT + 2 * i / FPS).astype(np.float32) * (1 - a) + f * a).astype(np.uint8)
        elif i >= n - xh:
            a = ease((i - (n - xh) + 1) / (xh + 1))
            f = (f * (1 - a) + bc.at(t0 + i / FPS).astype(np.float32) * a).astype(np.uint8)
        yield f
    for c in (zc, sw, bc):
        c.close()


def fade(frames, t_in=0.0, t_out=0.0, color=(0, 0, 0), n=None):
    """Fade a run of frames in from and/or out to a colour (n: its length in frames, needed for t_out)."""
    col = np.array(color, np.float32)
    for i, f in enumerate(frames):
        a = 1.0
        if t_in:
            a = min(a, ease(i / FPS / t_in))
        if t_out and n:
            a = min(a, ease((n - 1 - i) / FPS / t_out))
        yield f if a >= 1 else (col + (f.astype(np.float32) - col) * a).astype(np.uint8)


def caption(frames, text, t0, t1):
    """A typed-on caption at the bottom left, mono brass, like a log entry."""
    for i, f in enumerate(frames):
        t = i / FPS
        if t < t0 or t > t1 + 0.4:
            yield f
            continue
        im = Image.fromarray(f)
        n = int((t - t0) / 0.04)
        a = min(1.0, (t1 + 0.4 - t) / 0.4)
        sh = Image.new("L", (W, 200), 0)                  # a soft dark shadow, so it reads over the wake
        tracked(ImageDraw.Draw(sh), (72, 108), text[:n], mono(22, True), 255, 0.25)
        sh = sh.filter(ImageFilter.GaussianBlur(6)).point(lambda v: int(min(255, v * 2.2) * 0.75 * a))
        im.paste(Image.new("RGB", (W, 200), (0, 0, 0)), (0, H - 200), sh)
        d = ImageDraw.Draw(im, "RGBA")
        tracked(d, (72, H - 92), text[:n], mono(22, True), BRASS + (int(255 * a),), 0.25)
        yield np.asarray(im)


def overlay_card(frames, text, t0, dur):
    for i, f in enumerate(frames):
        t = i / FPS - t0
        yield card_frame(text, t, dur, over=f) if 0 <= t < dur else f


LINE_CLIP = f"{LINE}_vs_{ENEMY}"


def cut():
    """The trailer, shot by shot (times are the clips' own)."""
    designs = [Design(*m) for m in MONTAGE]
    zoom = f"{LINE}_zoom.mp4"
    # 1. cold open: Lion alone, her turrets swinging out
    yield from fade(caption(ramp("lion_s6.mp4", [(1.0, 7.0, 1.0)]), "NORTH SEA  ·  31 MAY 1916", 1.2, 4.8),
                    t_in=1.0)
    # 2. card, 3. the design bureau, 4. into the water
    yield from card_frames("DESIGN EVERY RIVET.", 1.7)
    yield from sheets_frames(designs)
    yield from to_sea_frames(designs, zoom)
    # 5. the zoom: close while she trains and fires, then out to the squadron
    f0 = TO_SEA[2][1] - TO_SEA[2][0]
    yield from overlay_card(ramp(zoom, [(f0, 4.0, 1.0), (4.0, 7.5, 2.0), (7.5, 12.0, 1.0), (12.0, 22.0, 2.0)]),
                            "COMMAND THE LINE.", 10.4, 2.2)
    # 6. the battle: the swing round to it, wide, our salvos on the enemy lead, then the second Lion straddled and hit
    yield from swing_frames(zoom)
    yield from ramp(f"{LINE_CLIP}.mp4", BATTLE_WIDE)
    yield from ramp(f"{LINE_CLIP}_s1.6_f4.mp4", BATTLE_ENEMY)
    yield from ramp(f"{LINE_CLIP}_s2_f1.mp4", BATTLE_OURS)
    # 7. the money shot, to white, 8. the end card out of the white
    n = int(round(sum((b - a) / sp for a, b, sp in EXPLOSION) * FPS))
    yield from fade(overlay_card(ramp("lion_explode_A_B_fit0.45.mp4", EXPLOSION), "LIVE WITH THE CONSEQUENCES.",
                                 EXPLOSION_CARD, 2.4), t_out=0.5, color=(255, 255, 255), n=n)
    yield from fade(fade(end_frames(), t_in=0.9, color=(255, 255, 255)), t_out=0.7,
                    n=int(END_S * FPS))


# battle and explosion pieces (src_from, src_to, speed), picked from the renders
BATTLE_WIDE = [(7.6, 13.6, 1.0)]       # our line opens fire, theirs replies, the first fall of shot
BATTLE_ENEMY = [(14.8, 19.2, 1.0)]     # our salvos walk onto the enemy lead: short, over, straddle
BATTLE_OURS = [(20.0, 24.76, 1.0)]     # their salvos straddle the second Lion; cut on the hit's first frame (24.73)
EXPLOSION = [(11.30, 12.0, 1.0), (12.0, 14.0, 0.5), (14.0, 19.0, 1.0)]  # the hit (11.30), slow-mo jets and fireball
EXPLOSION_CARD = 5.6      # s into the explosion shot


def write(frames, out, n=None):
    import imageio_ffmpeg
    w = imageio_ffmpeg.write_frames(str(out), (W, H), fps=FPS, codec="libx264", pix_fmt_out="yuv420p",
                                    output_params=["-crf", "18", "-preset", "slow"], macro_block_size=8)
    w.send(None)
    c = 0
    for f in frames:
        w.send(np.ascontiguousarray(f))
        c += 1
        if c % 30 == 0:
            print(f"\r  {out.name}: {c / FPS:5.1f} s", end="", flush=True)
    w.close()
    print(f"\r  wrote {out} ({c / FPS:.1f} s)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--only", choices=("sheets", "end", "cards"), default=None)
    ap.add_argument("--still", type=float, default=None, help="one PNG at this time (of --only's piece)")
    ap.add_argument("--out", default=str(HERE / "out"))
    ap.add_argument("--render-swing", nargs="?", const=-1, type=int, default=None, metavar="FRAME",
                    help="render swing.mp4 (the zoom-to-battle camera move) from the battle's sim; with a frame "
                         "index, just that frame as a PNG")
    ap.add_argument("--chunks", type=int, default=2, help="--render-swing's parallel parts")
    args = ap.parse_args()
    out = Path(args.out)
    if args.render_swing is not None:
        render_swing(args.chunks, None if args.render_swing < 0 else args.render_swing)
        return
    if args.only == "sheets":
        frames = sheets_frames([Design(*m) for m in MONTAGE])
        if args.still is not None:
            k = int(round(args.still * FPS))
            for j, f in enumerate(frames):
                if j == k:
                    p = out / f"trailer_sheets_{args.still:g}.png"
                    Image.fromarray(f).save(p)
                    print("wrote", p)
                    return
        write(frames, out / "trailer_sheets.mp4")
        return
    if args.only == "end":
        if args.still is not None:
            p = out / f"trailer_end_{args.still:g}.png"
            end_frame(args.still).save(p)
            print("wrote", p)
            return
        write(end_frames(), out / "trailer_end.mp4")
        return
    if args.only == "cards":
        p = out / "trailer_card.png"
        Image.fromarray(card_frame("DESIGN EVERY RIVET.", args.still or 0.8, 1.6)).save(p)
        print("wrote", p)
        return
    if args.still is not None:
        k = int(round(args.still * FPS))
        for j, f in enumerate(cut()):
            if j == k:
                p = out / f"trailer_{args.still:g}.png"
                Image.fromarray(f).save(p)
                print("wrote", p)
                return
        sys.exit("past the end")
    write(cut(), out / "fleetwright_trailer.mp4")


if __name__ == "__main__":
    main()
