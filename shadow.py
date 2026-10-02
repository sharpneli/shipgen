#!/usr/bin/env python3
"""
shadow: height map layer and the reference sun-shadow renderer.

The static part of the ship (hull, superstructure, funnels, masts, AA, boats, barbettes) is written as a
height map: an 8-bit greyscale PNG on the same canvas as hull_base/hull_upper, value = metres above the
waterline / HEIGHT_STEP_M (0 = sea). Every pixel is treated as a solid column from the sea up to its height.

Shadow of the height map (what the game shader does, per pixel p, in ship-local space):
    d   = unit vector from p toward the sun, ship-local (+x bow, +y starboard)
    k   = tan(sun elevation)
    shadowed(p) = exists t > 0 with  H(p + t*d) > H(p) + t*k
March t in steps of about one texel (or 0.5 m, whichever is longer) out to MAX_HEIGHT / k, sampling H with
clamp-to-border 0. Because H(p) is the receiver height, the same pass is right for the sea, the deck and the
superstructure roofs. Draw the shadow quad larger than the sprite by max_height_m / k on every side so the
shadow can fall on the sea beyond the canvas.

Turrets rotate, so they are not in the height map: draw each turret sprite in black, rotated like the turret,
offset away from the sun by (top_m - deck_m) / k, after hull_base and before the turrets themselves.

shadow_mask() below is the reference implementation (numpy); design.py uses it for the previews.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image

from geometry import rrect_polygon
from shipgen import AA_CFG, f, poly, svg_doc

HEIGHT_STEP_M = 0.25      # one grey level = 0.25 m; 255 = 63.75 m above the waterline
MAST_ABOVE_FUNNEL = 6.0   # mast tops sit this far above the funnel tops


def _grey(h_m):
    v = max(0, min(255, round(h_m / HEIGHT_STEP_M)))
    return f"rgb({v},{v},{v})"


def build_height_svg(lay, deck_m, vb, scale):
    """SVG of the static height map. Shapes are drawn lowest first so the taller one wins where they overlap.
    Only columns: a heightfield cannot overhang, so mast yards, derricks and turret barrels are left out.
    A flight deck overhang is drawn as a solid column, which casts the same shadow seen from above."""
    from layout import LEVEL_H, block_top
    items = [(deck_m, f'<path d="{lay.hull.outline()}"/>')]
    for dk in lay.decks + lay.sponsons:
        items.append((deck_m + dk["top"], f'<path d="{poly(dk["points"])}"/>'))
    for ht in lay.spec.get("hatches", []):
        items.append((deck_m + ht.get("top", 1.2), f'<rect x="{f(ht["x"] - ht["l"] / 2)}" y="{f(ht["y"] - ht["w"] / 2)}" '
                                                  f'width="{f(ht["l"])}" height="{f(ht["w"])}"/>'))
    for cr in lay.spec.get("cranes", []):
        items.append((deck_m + cr["top"], f'<circle cx="{f(cr["x"])}" cy="{f(cr["y"])}" r="{f(cr.get("r", 1.2))}"/>'))
    for m in lay.mounts:   # barbettes of raised mounts stand above the deck
        t = m["t"]
        if t.get("barbette", True) and m["base"] > 0.5:
            items.append((deck_m + m["base"], f'<circle cx="{f(m["x"])}" cy="{f(m["y"])}" r="{f(t["r"] * 0.95)}"/>'))
    for b in lay.blocks:
        pts = rrect_polygon(b["x0"], b["y"] - b["w"] / 2, b["x1"], b["y"] + b["w"] / 2, b["rf"], b["rb"])
        items.append((deck_m + block_top(b), f'<path d="{poly(pts)}"/>'))
    for a in lay.aa:
        items.append((deck_m + a["base"] + 2.0, f'<circle cx="{f(a["x"])}" cy="{f(a["y"])}" r="{f(AA_CFG[a["type"]][0] * 0.8)}"/>'))
    for bt in lay.spec.get("boats", []):
        items.append((deck_m + bt.get("top", LEVEL_H + 1.5), f'<ellipse cx="{f(bt["x"])}" cy="{f(bt["y"])}" rx="{f(bt["l"] / 2)}" ry="{f(bt["w"] / 2)}"/>'))
    for fn in lay.funnels:
        pts = rrect_polygon(fn["x"] - fn["l"] / 2, fn["y"] - fn["w"] / 2, fn["x"] + fn["l"] / 2, fn["y"] + fn["w"] / 2,
                            fn["w"] / 2, fn["w"] / 2)
        items.append((deck_m + lay.fun_top, f'<path d="{poly(pts)}"/>'))
    for m in lay.spec.get("masts", []):
        top = m.get("top", lay.fun_top + MAST_ABOVE_FUNNEL)
        items.append((deck_m + top, f'<circle cx="{f(m["x"])}" cy="{f(m.get("y", 0))}" r="0.7"/>'))
    items.sort(key=lambda it: it[0])
    x, y, w, h = vb
    body = f'<rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}" fill="#000"/>'
    body += "".join(el.replace("/>", f' fill="{_grey(hm)}"/>', 1) for hm, el in items)
    return svg_doc(body, vb, scale), max(hm for hm, _ in items)


def to_height_png(rgba_png):
    """cairosvg writes RGBA; keep one grey channel."""
    Image.open(rgba_png).convert("L").save(rgba_png, optimize=True)


def reduce_max(im: Image.Image) -> Image.Image:
    """2x2 max filter: a coarser level never lowers a column, so shadow lengths stay right."""
    a = np.asarray(im)
    return Image.fromarray(a.reshape(a.shape[0] // 2, 2, a.shape[1] // 2, 2).max(axis=(1, 3)))


def shadow_mask(height: Image.Image, S, sun_az_deg, sun_el_deg, pad_px=0, soft_m=0.3):
    """Reference shadow: returns an 'L' image (255 = full shadow), the height map's size plus pad_px per side.
    sun_az_deg is the sun's bearing in ship-local degrees (0 = dead ahead, 90 = starboard)."""
    H = np.pad(np.asarray(height, dtype=np.float32) * HEIGHT_STEP_M, pad_px)
    k = math.tan(math.radians(sun_el_deg))
    dx, dy = math.cos(math.radians(sun_az_deg)), math.sin(math.radians(sun_az_deg))
    rows, cols = H.shape
    shade = np.zeros_like(H)
    t_max = int(H.max() / k * S) + 1
    last = None
    for t in range(1, t_max + 1):
        ox, oy = round(t * dx), round(t * dy)
        if (ox, oy) == last:
            continue
        last = (ox, oy)
        occ = np.zeros_like(H)   # occ[p] = H[p + (ox, oy)], 0 off the canvas
        ys, yd = (slice(oy, rows), slice(0, rows - oy)) if oy >= 0 else (slice(0, rows + oy), slice(-oy, rows))
        xs, xd = (slice(ox, cols), slice(0, cols - ox)) if ox >= 0 else (slice(0, cols + ox), slice(-ox, cols))
        occ[yd, xd] = H[ys, xs]
        dist_m = math.hypot(ox, oy) / S
        np.maximum(shade, np.clip((occ - (H + dist_m * k)) / soft_m, 0, 1), out=shade)
    return Image.fromarray((shade * 255).astype(np.uint8))


def sun_offset_px(S, sun_az_deg, sun_el_deg, height_m):
    """Ship-local pixel offset of a shadow cast from height_m (away from the sun)."""
    L = height_m / math.tan(math.radians(sun_el_deg)) * S
    return -L * math.cos(math.radians(sun_az_deg)), -L * math.sin(math.radians(sun_az_deg))
