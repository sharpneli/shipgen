"""
hitview: debug views of the hitbox model in 3D. Every hitbox is a footprint with a base and a top height, so it
extrudes to a prism; the prisms are drawn in an orthographic projection with a depth buffer, flat-shaded,
from a few angles. Render side: reads nothing but the ship dict (its "hitboxes").

    hitview.render_views(ship, out_dir)      ->  hitbox_bow.png, hitbox_quarter.png, hitbox_side.png,
                                                 hitbox_internal.png

    hitview.render_subdivision(ship, out_dir) ->  hitbox_cells.png: every tier in plan, keel tier at the bottom,
                                                 cells coloured by their room's kind, with the bulkheads

The hull is translucent in the outside views, so the rooms show through; the internal view draws only the rooms,
the armour and the hull's edges. The quarters, stores, double bottom and torpedo protection that fill the rest of
the hull are faint (FILLER), so the rooms show through them; the citadel's armoured ends are dark slabs.
"""
from __future__ import annotations

import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from geometry import rotate_translate, table_half_width

KIND = {   # fill RGB, alpha
    "hull": ((150, 160, 170), 90),
    "main": ((215, 70, 70), 255), "secondary": ((230, 150, 60), 255), "torpedo": ((80, 170, 230), 255),
    "barbette": ((200, 200, 205), 255), "superstructure": ((110, 200, 120), 255), "funnel": ((170, 110, 220), 255),
    "uptake": ((150, 100, 200), 200), "casing": ((120, 120, 140), 255), "aa": ((235, 220, 70), 255),
    "conning_tower": ((240, 110, 190), 255), "deck": ((150, 175, 150), 255), "sponson": ((140, 150, 160), 255),
    "flight_deck": ((130, 140, 150), 200),
    "belt": ((60, 70, 90), 255), "strake": ((135, 145, 165), 255), "armour_deck": ((60, 70, 90), 110),
    "boiler_room": ((240, 140, 40), 235), "engine_room": ((190, 70, 40), 235), "bunker": ((70, 60, 55), 235),
    "magazine": ((230, 40, 40), 240), "accommodation": ((110, 180, 235), 55), "steering": ((160, 90, 200), 235),
    "hold": ((200, 170, 110), 200), "cargo_tank": ((150, 120, 70), 200), "fuel_tank": ((90, 80, 60), 220),
    "hangar_bay": ((200, 200, 210), 120), "stores": ((150, 150, 120), 55), "double_bottom": ((80, 95, 110), 40),
    "tds": ((90, 140, 160), 45), "armoured_bulkhead": ((60, 70, 90), 255),
    "shaft": ((225, 225, 120), 255), "shaft_alley": ((200, 190, 120), 150), "propeller": ((215, 160, 60), 255),
    "rudder": ((240, 110, 190), 255),
}
PROPULSION = ("shaft", "shaft_alley", "propeller", "rudder")
OPAQUE = 200      # kinds above this alpha are solid: they hide what is behind them
FILLER = ("accommodation", "stores", "double_bottom", "tds")   # fill the hull: drawn faint, so the rooms show through
LIGHT = (-0.35, -0.45, 0.82)      # from forward, port and above
VIEWS = [   # file, camera bearing (clockwise from ahead), elevation, what
    ("hitbox_bow.png", 35.0, 28.0, "outside"),
    ("hitbox_quarter.png", 215.0, 24.0, "outside"),
    ("hitbox_side.png", 90.0, 0.0, "outside"),
    ("hitbox_internal.png", 55.0, 35.0, "internal"),
]
CIRCLE_N = 16


def _circle(x, y, r):
    return [(x + r * math.cos(2 * math.pi * k / CIRCLE_N), y + r * math.sin(2 * math.pi * k / CIRCLE_N))
            for k in range(CIRCLE_N)]


def _signed_area(pts):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1])) / 2


def prisms(hb, what):
    """[(kind, footprint polygon, base, top)] for the view: components, compartments, armour, hull."""
    out = []
    vert = hb.get("vertical", {})
    keel = vert.get("keel", -5.0)
    hull = [tuple(p) for p in hb["hull"]]
    if what == "outside":     # the hull in slices, each its outline at the slice's middle: it narrows to the keel
        wl = vert.get("waterline", 0.0)
        zs = [keel + (min(wl, 0.0) - keel) * f for f in (0.0, 0.06, 0.15, 0.3, 0.5, 0.75, 1.0)]
        zs += [0.0] if wl < 0.0 else []
        for z0, z1 in zip(zs, zs[1:]):
            out.append(("hull", form_outline(hb, (z0 + z1) / 2), z0, z1))
    for c in hb["components"]:
        kind = c["kind"]
        if what == "internal" and kind not in ("barbette", "uptake", "casing") + PROPULSION:
            continue
        if "local" in c:
            polys = [c["local"]["body"]] + c["local"]["parts"]
            for p in polys:
                out.append((kind, rotate_translate(p, c["rest_deg"], c["x"], c["y"]), c["base"], c["top"]))
            mid = c["base"] + 0.55 * (c["top"] - c["base"])
            for p in c["local"]["barrels"]:
                out.append((kind, rotate_translate(p, c["rest_deg"], c["x"], c["y"]), mid - 0.25, mid + 0.25))
        elif c.get("shape") == "segment":       # a shaft: short boxes along it
            (x0, y, z0), (x1, _, z1), r = c["p0"], c["p1"], c["r"]
            n = max(1, int(abs(x1 - x0) / 3.0))
            for k in range(n):
                a, b = x0 + (x1 - x0) * k / n, x0 + (x1 - x0) * (k + 1) / n
                zm = z0 + (z1 - z0) * (k + 0.5) / n
                out.append((kind, [(a, y - r), (b, y - r), (b, y + r), (a, y + r)], zm - r, zm + r))
        elif c.get("shape") == "circle":
            out.append((kind, _circle(c["x"], c["y"], c["r"]), c["base"], c["top"]))
        elif "points" in c:
            out.append((kind, [tuple(p) for p in c["points"]], c["base"], c["top"]))
    kinds = {r["id"]: r["kind"] for r in hb.get("rooms", [])}
    for c in hb.get("cells", []):
        out.append((kinds[c["room"]], cell_outline(hb, c), c["base"], c["top"]))
    arm = hb.get("armour", {})
    slabs = ([("belt", arm["belt"])] if "belt" in arm else []) + [("strake", b) for b in arm.get("strakes", [])]
    wl = vert.get("waterline", 0.0)
    for kind, b in slabs:
        # a thin slab just outside the hull side over its stretch, split at the waterline: it follows the flare
        zs = [b["bottom"]] + ([wl] if b["bottom"] < wl < b["top"] else []) + [b["top"]]
        for z0, z1 in zip(zs, zs[1:]):
            for side in (1, -1):
                xs = [b["x0"] + (b["x1"] - b["x0"]) * k / 12 for k in range(13)]
                hw = [form_half_width(hb, x, (z0 + z1) / 2) for x in xs]
                outer = [(x, side * (w + 0.15)) for x, w in zip(xs, hw)]
                inner = [(x, side * (w - 0.25)) for x, w in zip(xs, hw)][::-1]
                out.append((kind, outer + inner, z0, z1))
    for bh in hb.get("bulkheads", []):       # the citadel's armoured ends, across the hull
        if bh.get("kind") == "armoured":
            hw = form_half_width(hb, bh["x"], (bh["armour_bottom"] + bh["armour_top"]) / 2) - 0.2
            out.append(("armoured_bulkhead", [(bh["x"] - 0.15, -hw), (bh["x"] + 0.15, -hw), (bh["x"] + 0.15, hw),
                                              (bh["x"] - 0.15, hw)], bh["armour_bottom"], bh["armour_top"]))
    for d in (arm.get("decks", []) if what == "internal" else []):
        xs = [d["x0"] + (d["x1"] - d["x0"]) * k / 12 for k in range(13)]
        pts = ([(x, form_half_width(hb, x, d["z"]) - 0.2) for x in xs] +
               [(x, -form_half_width(hb, x, d["z"]) + 0.2) for x in xs[::-1]])
        out.append(("armour_deck", pts, d["z"] - 0.15, d["z"]))
    return out


def form_half_width(hb, x, z):
    """The hull's half-breadth at x and height z (above the main deck): its exported cross-sections
    (hull_form), or the deck outline's where there are none."""
    if hb.get("hull_form"):
        return table_half_width(hb["hull_form"]["stations"], x, z)
    return _half_width([tuple(p) for p in hb["hull"]], x)


def form_outline(hb, z, n=120):
    """The hull's outline at height z (above the main deck) as a polygon."""
    L = hb["length"]
    xs = [-L / 2 + L * (1 - math.cos(math.pi * k / n)) / 2 for k in range(n + 1)]
    pts = [(x, form_half_width(hb, x, z)) for x in xs]
    pts = [(x, w) for x, w in pts if w > 0.01]
    return [(x, -w) for x, w in pts] + [(x, w) for x, w in reversed(pts)]


def cell_outline(hb, c, n=8):
    """A cell's footprint: its box clipped to the hull's outline at the cell's middle height (sampled along x)."""
    xs = [c["x0"] + (c["x1"] - c["x0"]) * k / n for k in range(n + 1)]
    hw = [form_half_width(hb, x, (c["base"] + c["top"]) / 2) for x in xs]
    lo = [(x, max(c["y0"], -w)) for x, w in zip(xs, hw)]
    hi = [(x, min(c["y1"], w)) for x, w in zip(xs, hw)]
    pts = [(x, y) for (x, y), (_, y2) in zip(lo, hi) if y < y2] + \
          [(x, y2) for (x, y), (_, y2) in reversed(list(zip(lo, hi))) if y < y2]
    return pts


def _half_width(hull, x):
    """The hull outline's half-width at x (its widest starboard crossing)."""
    best = 0.0
    for (x0, y0), (x1, y1) in zip(hull, hull[1:] + hull[:1]):
        if (x0 - x) * (x1 - x) <= 0 and x0 != x1:
            y = y0 + (y1 - y0) * (x - x0) / (x1 - x0)
            best = max(best, abs(y))
    return best


def faces(prs, cam):
    """Visible faces [(depth, kind, 3D points, normal)] of the prisms seen from direction cam."""
    out = []
    for kind, poly, base, top in prs:
        if len(poly) < 3 or top <= base:
            continue
        ccw = _signed_area(poly) > 0
        if cam[2] > 1e-6:
            out.append((kind, [(x, y, top) for x, y in poly], (0.0, 0.0, 1.0)))
        n = len(poly)
        for i in range(n):
            (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
            dx, dy = x1 - x0, y1 - y0
            ln = math.hypot(dx, dy)
            if ln < 1e-6:
                continue
            nx, ny = (dy / ln, -dx / ln) if ccw else (-dy / ln, dx / ln)
            if nx * cam[0] + ny * cam[1] <= 1e-6:
                continue
            out.append((kind, [(x0, y0, base), (x1, y1, base), (x1, y1, top), (x0, y0, top)], (nx, ny, 0.0)))
    return out


def render_view(hb, az, el, what, width=1800, title=""):
    a, e = math.radians(az), math.radians(el)
    cam = (math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e))   # towards the camera
    f = (-cam[0], -cam[1], -cam[2])
    r = (math.sin(a), -math.cos(a), 0.0)            # screen right (up x f, normalised)
    s = (f[1] * r[2] - f[2] * r[1], f[2] * r[0] - f[0] * r[2], f[0] * r[1] - f[1] * r[0])   # screen up = f x r
    prs = prisms(hb, what)
    fs = faces(prs, cam)
    dot = lambda p, v: p[0] * v[0] + p[1] * v[1] + p[2] * v[2]
    pts_all = [p for _, pts, _ in fs for p in pts]
    if not pts_all:
        return None
    us = [dot(p, r) for p in pts_all]
    vs = [dot(p, s) for p in pts_all]
    margin = 60
    scale = (width - 2 * margin) / max(1.0, max(us) - min(us))
    height = int((max(vs) - min(vs)) * scale) + 2 * margin + 40
    u0, v1 = min(us), max(vs)
    proj = lambda p: (margin + (dot(p, r) - u0) * scale, margin + 40 + (v1 - dot(p, s)) * scale)
    lx, ly, lz = LIGHT
    ln = math.sqrt(lx * lx + ly * ly + lz * lz)
    # a depth buffer, not a painter's sort: a centroid sort put big faces (a deckhouse roof, a barbette's wall) over
    # small ones in front of them (a turret roof). The solid faces go first and write depth; the translucent ones
    # (the hull, the filler rooms) are then blended far to near wherever nothing solid is in front of them
    rgb_buf = np.empty((height, width, 3), np.float32)
    rgb_buf[:] = (34, 40, 48)
    zbuf = np.full((height, width), np.inf, np.float32)
    bias = 1.0 / scale       # edges win ties with the faces they border, so the outlines stay visible
    solid = [t for t in fs if KIND.get(t[0], (None, 255))[1] > OPAQUE]
    clear = [t for t in fs if 0 < KIND.get(t[0], (None, 255))[1] <= OPAQUE]
    clear.sort(key=lambda t: -sum(dot(p, f) for p in t[1]) / len(t[1]))
    for group, write in ((solid, True), (clear, False)):
        for kind, pts, nrm in group:
            rgb, alpha = KIND.get(kind, ((200, 200, 200), 255))
            shade = 0.5 + 0.5 * max(0.0, (nrm[0] * lx + nrm[1] * ly + nrm[2] * lz) / ln)
            fill = np.array([c * shade for c in rgb], np.float32)
            edge = None if kind == "hull" else fill * 0.6
            ea = min(255, alpha + (20 if kind in FILLER else 60))
            sp = [proj(p) for p in pts]
            x0, y0 = max(0, int(min(x for x, _ in sp)) - 1), max(0, int(min(y for _, y in sp)) - 1)
            x1, y1 = min(width, int(max(x for x, _ in sp)) + 2), min(height, int(max(y for _, y in sp)) + 2)
            if x1 <= x0 or y1 <= y0:
                continue
            m = Image.new("L", (x1 - x0, y1 - y0), 0)
            ImageDraw.Draw(m).polygon([(x - x0, y - y0) for x, y in sp], fill=1, outline=1 if edge is None else 2)
            mask = np.asarray(m)
            if not mask.any():
                continue
            # the face's plane gives each pixel its depth: n . (u r + v s + t f) = n . p0, solved for t
            nf = dot(nrm, f)
            ys, xs = np.mgrid[y0:y1, x0:x1].astype(np.float32)
            u = (xs - margin) / scale + u0
            v = v1 - (ys - margin - 40) / scale
            depth = (dot(nrm, pts[0]) - u * dot(nrm, r) - v * dot(nrm, s)) / nf
            ds = [dot(p, f) for p in pts]
            depth = np.clip(depth, min(ds), max(ds))     # grazing faces: no wild depths on their edge pixels
            depth[mask == 2] -= bias
            zs = zbuf[y0:y1, x0:x1]
            ok = (mask > 0) & (depth <= zs)
            px = rgb_buf[y0:y1, x0:x1]
            for val, col, a in ((1, fill, alpha), (2, edge, ea)):
                sel = ok & (mask == val)
                if col is None or not sel.any():
                    continue
                if write:
                    px[sel] = col
                else:
                    px[sel] += (col - px[sel]) * (a / 255.0)
            if write:
                zs[ok] = depth[ok]
    img = Image.fromarray(np.clip(rgb_buf + 0.5, 0, 255).astype(np.uint8), "RGB")
    d = ImageDraw.Draw(img, "RGBA")
    if what == "internal":     # the hull's edges: the deck outline, the keel, the stem and stern posts and a few
        keel = hb.get("vertical", {}).get("keel", -5.0)            # sections
        hull = [tuple(p) for p in hb["hull"]]
        d.line([proj((x, y, 0.0)) for x, y in hull + hull[:1]], fill=(200, 210, 220, 160), width=1)
        stations = (hb.get("hull_form") or {}).get("stations")
        if stations:         # the keel line: each section's lowest point, up the stem and the stern
            d.line([proj((st["x"], 0.0, st["z"][0])) for st in stations], fill=(200, 210, 220, 160), width=1)
            for st in (stations[0], stations[-1]):
                d.line([proj((st["x"], 0.0, st["z"][0])), proj((st["x"], 0.0, 0.0))], fill=(200, 210, 220, 160), width=1)
        else:
            x0, x1 = min(x for x, _ in hull), max(x for x, _ in hull)
            d.line([proj((x0, 0.0, keel)), proj((x1, 0.0, keel))], fill=(200, 210, 220, 160), width=1)
            for x, y in (max(hull), min(hull)):
                d.line([proj((x, y, keel)), proj((x, y, 0.0))], fill=(200, 210, 220, 160), width=1)
        for st in (hb.get("hull_form") or {}).get("stations", [])[4:-4:4]:
            sec = [(y, z) for y, z in zip(st["y"], st["z"])]
            pts = [(st["x"], -y, z) for y, z in reversed(sec)] + [(st["x"], y, z) for y, z in sec]
            d.line([proj(p) for p in pts], fill=(200, 210, 220, 90), width=1)
    wl = hb.get("vertical", {}).get("waterline")
    if wl is not None:
        d.line([proj((x, y, wl)) for x, y in form_outline(hb, wl) + form_outline(hb, wl)[:1]],
               fill=(80, 170, 255, 200), width=1)
    _legend(d, title, sorted({k for k, _, _ in fs}), width)
    return img


def _legend(d, title, kinds, width):
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    d.text((12, 10), title, fill=(230, 235, 240, 255), font=font)
    x = 12
    y = 30
    for k in kinds:
        rgb, alpha = KIND.get(k, ((200, 200, 200), 255))
        if not alpha:
            continue
        w = d.textlength(k, font=font) + 30
        if x + w > width - 12:
            x, y = 12, y + 20
        d.rectangle([x, y + 3, x + 12, y + 15], fill=rgb + (255,))
        d.text((x + 17, y), k, fill=(210, 215, 220, 255), font=font)
        x += w
    return y


def render_subdivision(ship, out_dir, width=1800):
    """hitbox_cells.png: every tier of the subdivision in plan, keel tier at the bottom; cells coloured by their
    room's kind, outlined, with ids on the bigger ones, and the bulkheads between them."""
    hb = ship["hitboxes"]
    if not hb.get("cells"):
        return
    hull = [tuple(p) for p in hb["hull"]]
    L, B = hb["length"], hb["beam"]
    margin = 40
    S = (width - 2 * margin) / L
    row = B * S + 34
    tiers = list(reversed(hb["tiers"]))
    height = int(margin + 40 + row * len(tiers) + margin)
    img = Image.new("RGB", (width, height), (34, 40, 48))
    d = ImageDraw.Draw(img, "RGBA")
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
        big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except OSError:
        font = big = ImageFont.load_default()
    kinds = {r["id"]: r["kind"] for r in hb["rooms"]}
    used = set()
    for i, t in enumerate(tiers):
        cy = margin + 40 + row * i + 18 + B * S / 2
        P = lambda x, y: (margin + (x + L / 2) * S, cy + y * S)
        d.text((margin, cy - B * S / 2 - 17), f"{t['id']}: {t['base']:g} to {t['top']:g} m"
               + (" (below the waterline)" if t["below_waterline"] else
                  f" ({100 * t['submerged']:.0f}% below the waterline)" if t.get("submerged") else "")
               + "".join(f", under {d['thickness_mm']} mm on the {d['deck'].lower()}"
                         for d in hb.get("armour", {}).get("decks", []) if abs(d["z"] - t["top"]) < 1e-6),
               fill=(220, 225, 230, 255), font=big)
        d.polygon([P(x, y) for x, y in hull], outline=(200, 210, 220, 120))
        d.polygon([P(x, y) for x, y in form_outline(hb, (t["base"] + t["top"]) / 2)], outline=(200, 210, 220, 255))
        for c in hb["cells"]:
            if c["tier"] != t["id"]:
                continue
            kind = kinds[c["room"]]
            used.add(kind)
            rgb, _ = KIND.get(kind, ((200, 200, 200), 255))
            pts = cell_outline(hb, c)
            if len(pts) >= 3:
                d.polygon([P(x, y) for x, y in pts], fill=rgb + (215,), outline=(20, 24, 30, 255))
            if (c["x1"] - c["x0"]) * S > 34 and (c["y1"] - c["y0"]) * S > 14:
                lab = c["section"] + ("+" if c.get("also") else "") + (f" {c['crew']}" if c.get("crew") else "")
                d.text(P((c["x0"] + c["x1"]) / 2, (c["y0"] + c["y1"]) / 2), lab, fill=(10, 10, 10, 255),
                       font=font, anchor="mm")
    _legend(d, f"{ship['design'].get('name', '')}: subdivision, {len(hb['sections'])} sections, {len(hb['cells'])} "
               "cells (label: section, + shares a room, crew)", sorted(used), width)
    img.save(os.path.join(out_dir, "hitbox_cells.png"))


def render_views(ship, out_dir):
    hb = ship["hitboxes"]
    name = ship["design"].get("name", ship["design"].get("id", ""))
    for fname, az, el, what in VIEWS:
        img = render_view(hb, az, el, what, title=f"{name}: hitboxes, {what}, from {az:g} deg, elevation {el:g} deg")
        if img is not None:
            img.save(os.path.join(out_dir, fname))
    render_subdivision(ship, out_dir)
