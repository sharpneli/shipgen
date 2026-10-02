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

The columns come from the design side (shipdesign.height_columns); build_height_svg only rasterises them.
shadow_mask() below is the reference implementation (numpy); render.py uses it for the previews.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image

from shipgen import f, hull_path, poly, svg_doc

HEIGHT_STEP_M = 0.25      # one grey level = 0.25 m; 255 = 63.75 m above the waterline


def _grey(h_m):
    v = max(0, min(255, round(h_m / HEIGHT_STEP_M)))
    return f"rgb({v},{v},{v})"


def build_height_svg(columns, vb, scale, hull):
    """SVG of the static height map from the design's columns (shipdesign.height_columns, lowest first, so the
    taller one wins where they overlap). hull: the hull as drawn (a look may fill it out)."""
    def element(c):
        sh = c["shape"]
        if sh == "hull":
            return f'<path d="{hull_path(hull)}"/>'
        if sh == "polygon":
            return f'<path d="{poly(c["points"])}"/>'
        if sh == "rect":
            return f'<rect x="{f(c["x"])}" y="{f(c["y"])}" width="{f(c["w"])}" height="{f(c["h"])}"/>'
        if sh == "circle":
            return f'<circle cx="{f(c["cx"])}" cy="{f(c["cy"])}" r="{f(c["r"])}"/>'
        if sh == "ellipse":
            return f'<ellipse cx="{f(c["cx"])}" cy="{f(c["cy"])}" rx="{f(c["rx"])}" ry="{f(c["ry"])}"/>'
        raise ValueError(f"unknown column shape {sh!r}")
    x, y, w, h = vb
    body = f'<rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}" fill="#000"/>'
    body += "".join(element(c).replace("/>", f' fill="{_grey(c["top"])}"/>', 1) for c in columns)
    return svg_doc(body, vb, scale), max(c["top"] for c in columns)


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
