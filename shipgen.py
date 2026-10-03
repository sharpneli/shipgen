#!/usr/bin/env python3
"""
shipgen — parametric top-down warship sprite generator.

Conventions
-----------
* All geometry is authored in METRES in ship-local space:
    +x = toward the bow, +y = toward starboard (screen-down when the bow points right).
  The origin (0, 0) is the ship's centre and is also the exact centre of every hull image.
* Sprites face RIGHT (bow at +x). Angle 0 = dead ahead; positive angles turn clockwise
  on screen (toward starboard), the same as most 2D engines whose y axis points down.
* Each ship becomes three layers, drawn in this order:
    1. hull_base   - hull, deck, low deckhouses, barbettes, low AA guns
    2. turrets     - separate sprites, pivot at the image centre, sorted by mount "z"
    3. hull_upper  - bridge, towers, funnels, masts, boats (drawn above the turrets)
* Rendering: an SVG with a viewBox in metres, rasterised at --scale px per metre.

Usage
-----
    python shipgen.py                  # all ships, 3 px/m, into ./out
    python shipgen.py --scale 4 --only destroyer battleship
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import random

import cairosvg
from PIL import Image, ImageDraw, ImageFont

from fleet import FLEET, TURRET_TYPES
from looks import DEFAULT_PALETTE
from geometry import turret_shapes, turret_reach, BARREL_ROOT, CASEMATE_SHIELD, rrect_polygon, Hull, AA_CFG

PAD_M = 3.0  # empty margin around each hull sprite, metres



# ----------------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------------
def f(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".")


def rrect_path(x0, y0, x1, y1, rf=0.0, rb=0.0) -> str:
    """Rectangle with separate corner radii for the front (+x) and back (-x) ends."""
    h = (y1 - y0) / 2
    rf, rb = min(rf, h, (x1 - x0) / 2), min(rb, h, (x1 - x0) / 2)
    p = [f"M{f(x0 + rb)},{f(y0)}", f"L{f(x1 - rf)},{f(y0)}"]
    if rf > 0:
        p.append(f"A{f(rf)},{f(rf)} 0 0 1 {f(x1)},{f(y0 + rf)}")
    p.append(f"L{f(x1)},{f(y1 - rf)}")
    if rf > 0:
        p.append(f"A{f(rf)},{f(rf)} 0 0 1 {f(x1 - rf)},{f(y1)}")
    p.append(f"L{f(x0 + rb)},{f(y1)}")
    if rb > 0:
        p.append(f"A{f(rb)},{f(rb)} 0 0 1 {f(x0)},{f(y1 - rb)}")
    p.append(f"L{f(x0)},{f(y0 + rb)}")
    if rb > 0:
        p.append(f"A{f(rb)},{f(rb)} 0 0 1 {f(x0 + rb)},{f(y0)}")
    return " ".join(p) + " Z"


def poly(points) -> str:
    return "M" + " L".join(f"{f(x)},{f(y)}" for x, y in points) + " Z"


def shade(hex_color: str, k: float) -> str:
    """k<1 darkens, k>1 lightens toward white."""
    c = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
    if k <= 1:
        c = [round(v * k) for v in c]
    else:
        c = [round(v + (255 - v) * (k - 1)) for v in c]
    return "#" + "".join(f"{max(0, min(255, v)):02x}" for v in c)


def hull_path(hull, inset=0.0, max_hw=None, x_min=None, x_max=None, n=260) -> str:
    """SVG path of the hull (or an inset deck) outline."""
    return poly(hull.points(inset, max_hw, x_min, x_max, n))


# ----------------------------------------------------------------------------
# spec expansion: mirroring, edge-relative placement
# ----------------------------------------------------------------------------
def expand(items, hull: Hull):
    out = []
    for it in items or []:
        it = dict(it)
        if "edge" in it:  # place 'edge' metres inboard from the hull side
            side = 1 if it.get("y", 1) >= 0 else -1
            it["y"] = side * (hull.half_width(it["x"]) - it["edge"])
        if it.get("mirror") and abs(it.get("y", 0)) > 1e-6:
            a = dict(it)
            b = dict(it)
            b["y"] = -a["y"]
            for k in ("dir", "rest"):
                if k in b:
                    b[k] = -b[k]
            if "id" in it:
                a["id"], b["id"] = it["id"] + ("S" if a["y"] > 0 else "P"), it["id"] + ("S" if b["y"] > 0 else "P")
            out += [a, b]
        else:
            out.append(it)
    return out


# ----------------------------------------------------------------------------
# drawing primitives (all return SVG fragments in metres)
# ----------------------------------------------------------------------------
class Painter:
    def __init__(self, palette, scale, shadows=True, shapes=None):
        self.p = palette
        self.shapes = shapes or {}   # a look's drawing variations (looks.py)
        self.shadows = shadows  # bake drop shadows in; off when the game casts them from a height map
        # keep outlines at least ~0.6 px wide whatever the scale
        self.sw = max(0.12, 0.6 / scale)

    def stroke(self, k=1.0):
        return f'stroke="{self.p["line"]}" stroke-width="{f(self.sw * k)}" stroke-linejoin="round"'

    # --- AA guns (baked into the hull layers; too small to rotate usefully) ---
    def aa(self, a):
        kind = a.get("type", "quad40")
        x, y, d = a["x"], a["y"], a.get("dir", 0)
        cfg = AA_CFG[kind]
        r, n, ln, bw, sp = cfg
        p = self.p
        s = [f'<g transform="translate({f(x)},{f(y)}) rotate({f(d)})">',
             f'<circle r="{f(r)}" fill="{p["tub"]}" {self.stroke()}/>',
             f'<circle r="{f(r * 0.72)}" fill="{shade(p["tub"], 0.8)}"/>']
        for i in range(n):
            yy = (i - (n - 1) / 2) * sp
            s.append(f'<rect x="0" y="{f(yy - bw / 2)}" width="{f(ln)}" height="{f(bw)}" fill="{p["barrel"]}"/>')
        s.append(f'<rect x="{f(-r * 0.45)}" y="{f(-r * 0.45)}" width="{f(r * 0.8)}" height="{f(r * 0.9)}" '
                 f'rx="{f(r * 0.15)}" fill="{p["turret"]}" {self.stroke(0.7)}/>')
        s.append("</g>")
        return "".join(s)

    def boat(self, b):
        x, y, l, w = b["x"], b["y"], b.get("l", 7), b.get("w", 2.2)
        p = self.p
        return (f'<ellipse cx="{f(x)}" cy="{f(y)}" rx="{f(l / 2)}" ry="{f(w / 2)}" fill="{p["boat"]}" {self.stroke()}/>'
                f'<ellipse cx="{f(x)}" cy="{f(y)}" rx="{f(l / 2 - 0.5)}" ry="{f(w / 2 - 0.35)}" fill="{shade(p["boat"], 0.82)}"/>')

    def fitting(self, ft):
        x, y, l, w = ft["x"], ft["y"], ft["l"], ft["w"]
        r = ft.get("r", min(l, w) * 0.2)
        col = self.p.get(ft.get("color", "fitting"), ft.get("color", self.p["fitting"]))
        return f'<path d="{rrect_path(x - l / 2, y - w / 2, x + l / 2, y + w / 2, r, r)}" fill="{col}" {self.stroke(0.8)}/>'

    def block(self, b, shadow=True, clip=None):
        """Superstructure block; higher 'level' => lighter and longer shadow."""
        lvl = b.get("level", 1)
        x0, x1 = b["x0"], b["x1"]
        y = b.get("y", 0)
        w = b["w"]
        rf, rb = b.get("rf", 0.8), b.get("rb", 0.8)
        mode = self.shapes.get("blocks")
        if mode == "chamfer":     # cut corners instead of round ones
            h = w / 2
            cf, cb = min(rf, h, (x1 - x0) / 2), min(rb, h, (x1 - x0) / 2)
            d = poly([(x0 + cb, y - h), (x1 - cf, y - h), (x1, y - h + cf), (x1, y + h - cf), (x1 - cf, y + h),
                      (x0 + cb, y + h), (x0, y + h - cb), (x0, y - h + cb)])
        else:
            kf, kb = self.shapes.get("block_round") or \
                {"boxy": (0.35, 0.35), "soft": (1.6, 1.4), "bowfront": (1.5, 0.4)}.get(mode, (1.0, 1.0))
            d = rrect_path(x0, y - w / 2, x1, y + w / 2, rf * kf, rb * kb)
        cols = self.p["levels"]
        col = cols[min(lvl, len(cols)) - 1]
        s = []
        if shadow and self.shadows:
            off = 0.35 + 0.35 * lvl
            cl = f' clip-path="url(#{clip})"' if clip else ""
            s.append(f'<g{cl}><path d="{d}" transform="translate({f(off * 0.6)},{f(off)})" '
                     f'fill="#000" fill-opacity="0.28"/></g>')
        s.append(f'<path d="{d}" fill="{col}" {self.stroke()}/>')
        # a thin lighter rim on the port/fwd edge suggests light from the upper-left
        s.append(f'<path d="{d}" fill="none" stroke="{shade(col, 1.25)}" stroke-width="{f(self.sw * 0.9)}" '
                 f'transform="translate({f(-self.sw * 0.6)},{f(-self.sw * 0.6)})" stroke-opacity="0.7"/>')
        return "".join(s)

    def funnel(self, fn, clip=None):
        x, y, l, w = fn["x"], fn.get("y", 0), fn["l"], fn["w"]
        p = self.p
        mode = self.shapes.get("funnel")
        r = w / 2 * self.shapes.get("funnel_round", 0.44 if mode == "box" else 1.0)
        d = rrect_path(x - l / 2, y - w / 2, x + l / 2, y + w / 2, r, r)
        inner = rrect_path(x - l / 2 + 0.6, y - w / 2 + 0.6, x + l / 2 - 0.6, y + w / 2 - 0.6, max(0.0, r - 0.6),
                           max(0.0, r - 0.6))
        if mode == "oval":       # a smooth superellipse, fuller than an ellipse
            def sup(a, b_, n=self.shapes.get("funnel_squareness", 2.6), k=48):
                return poly([(x + a * math.copysign(abs(math.cos(t)) ** (2 / n), math.cos(t)),
                              y + b_ * math.copysign(abs(math.sin(t)) ** (2 / n), math.sin(t)))
                             for t in (2 * math.pi * i / k for i in range(k))])
            d, inner = sup(l / 2, w / 2), sup(l / 2 - 0.6, w / 2 - 0.6)
        cl = f' clip-path="url(#{clip})"' if clip else ""
        s = [f'<g{cl}><path d="{d}" transform="translate({f(w * 0.3)},{f(w * 0.5)})" fill="#000" fill-opacity="0.25"/></g>'
             if self.shadows else "",
             f'<path d="{d}" fill="{p["funnel"]}" {self.stroke()}/>',
             f'<path d="{inner}" fill="{p["funnel_cap"]}"/>']
        if p.get("funnel_band"):   # a painted top band (a look's funnel marking), seen from above as a rim
            band = rrect_path(x - l / 2 + 0.2, y - w / 2 + 0.2, x + l / 2 - 0.2, y + w / 2 - 0.2, r - 0.2, r - 0.2)
            s.append(f'<path d="{band}" fill="none" stroke="{p["funnel_band"]}" '
                     f'stroke-width="{f(self.shapes.get("funnel_band_w", 0.25))}"/>')
        # uptake openings
        n = fn.get("pipes", 2)
        for i in range(n):
            cx = x - l / 2 + 0.6 + (l - 1.2) * (i + 0.5) / n
            s.append(f'<ellipse cx="{f(cx)}" cy="{f(y)}" rx="{f((l - 1.2) / n / 2 - 0.25)}" '
                     f'ry="{f(w / 2 - 1.0)}" fill="#0b0d0f"/>')
        if mode == "capped":     # a cowl cap: a lighter ring standing proud round the top
            cap = rrect_path(x - l / 2 + 0.35, y - w / 2 + 0.35, x + l / 2 - 0.35, y + w / 2 - 0.35, r - 0.35, r - 0.35)
            s.append(f'<path d="{cap}" fill="none" stroke="{shade(p["funnel"], 1.25)}" stroke-width="0.45"/>')
        # cap grating highlight
        s.append(f'<path d="{d}" fill="none" stroke="{shade(p["funnel"], 1.3)}" stroke-width="{f(self.sw)}" '
                 f'transform="translate({f(-self.sw * 0.6)},{f(-self.sw * 0.6)})" stroke-opacity="0.6"/>')
        return "".join(s)

    def mast(self, m):
        x, y = m["x"], m.get("y", 0)
        span = m.get("yard", 6)
        p = self.p
        s = [f'<line x1="{f(x)}" y1="{f(y - span / 2)}" x2="{f(x)}" y2="{f(y + span / 2)}" '
             f'stroke="{p["mast"]}" stroke-width="{f(max(self.sw * 1.6, 0.35))}" stroke-linecap="round"/>'] if span else []
        for bx, by in m.get("booms", []):   # cargo derricks, heel at the mast
            s.append(f'<line x1="{f(x)}" y1="{f(y)}" x2="{f(bx)}" y2="{f(by)}" stroke="{p["mast"]}" '
                     f'stroke-width="{f(max(self.sw * 1.4, 0.3))}" stroke-linecap="round"/>'
                     f'<circle cx="{f(bx)}" cy="{f(by)}" r="0.3" fill="{p["mast"]}"/>')
        mode = self.shapes.get("mast")
        legs = self.shapes.get("tripod", 0.0 if mode in ("pole", "fighting_top") else 1.0)   # 0: every mast a pole
        if m.get("tripod", True) and legs:
            for ang in (150, 210):
                lx = x + 4.0 * legs * math.cos(math.radians(ang))
                ly = y + 3.0 * legs * (1 if ang == 150 else -1)
                s.append(f'<line x1="{f(x)}" y1="{f(y)}" x2="{f(lx)}" y2="{f(ly)}" '
                         f'stroke="{p["mast"]}" stroke-width="{f(max(self.sw * 1.3, 0.3))}" stroke-linecap="round"/>')
        top = self.shapes.get("top_r", 1.6 if mode == "fighting_top" else 0.0)
        if top:   # a round fighting top on the mast
            s.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(top)}" fill="{shade(p["mast"], 0.75)}" {self.stroke(0.8)}/>'
                     f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(top - 0.35)}" fill="none" stroke="{shade(p["mast"], 1.2)}" '
                     f'stroke-width="0.2"/>')
        s.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="0.7" fill="{p["mast"]}" {self.stroke(0.6)}/>')
        return "".join(s)

    def crane(self, c):
        """Revolving crane: pedestal and cab, jib pointing along dir (degrees, 0 = ahead)."""
        x, y, r = c["x"], c["y"], c.get("r", 1.2)
        a = math.radians(c.get("dir", 0))
        jx, jy = x + c["jib"] * math.cos(a), y + c["jib"] * math.sin(a)
        col = self.p["crane"]
        return (f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" fill="{shade(col, 1.3)}" {self.stroke()}/>'
                f'<line x1="{f(x)}" y1="{f(y)}" x2="{f(jx)}" y2="{f(jy)}" stroke="{col}" '
                f'stroke-width="{f(max(0.45, r * 0.4))}" stroke-linecap="round"/>'
                f'<circle cx="{f(jx)}" cy="{f(jy)}" r="0.35" fill="{col}"/>'
                f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r * 0.55)}" fill="{shade(col, 1.6)}" {self.stroke(0.6)}/>')

    def hatch(self, h):
        """Cargo hatch: coaming, tarpaulin cover and the battens across it."""
        x, y, l, w = h["x"], h["y"], h["l"], h["w"]
        p = self.p
        s = [f'<rect x="{f(x - l / 2)}" y="{f(y - w / 2)}" width="{f(l)}" height="{f(w)}" rx="0.25" '
             f'fill="{p["hatch_coaming"]}" {self.stroke()}/>',
             f'<rect x="{f(x - l / 2 + 0.35)}" y="{f(y - w / 2 + 0.35)}" width="{f(l - 0.7)}" height="{f(w - 0.7)}" '
             f'fill="{p["hatch"]}"/>']
        n = max(1, int(l / 1.6))
        for i in range(1, n):
            bx = x - l / 2 + l * i / n
            s.append(f'<line x1="{f(bx)}" y1="{f(y - w / 2 + 0.35)}" x2="{f(bx)}" y2="{f(y + w / 2 - 0.35)}" '
                     f'stroke="{shade(p["hatch"], 0.7)}" stroke-width="{f(self.sw * 0.8)}"/>')
        return "".join(s)

    def barbette(self, x, y, r):
        p = self.p
        return (f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" fill="{p["barbette"]}" {self.stroke()}/>'
                f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r * 0.8)}" fill="{shade(p["barbette"], 0.75)}"/>')


# ----------------------------------------------------------------------------
# hull layers
# ----------------------------------------------------------------------------
def svg_doc(body: str, vb: tuple, scale: float, defs: str = "") -> str:
    x, y, w, h = vb
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{round(w * scale)}" height="{round(h * scale)}" '
            f'viewBox="{f(x)} {f(y)} {f(w)} {f(h)}" shape-rendering="geometricPrecision">'
            f'<defs>{defs}</defs>{body}</svg>')


def turret_types(spec):
    """Library turret types plus any generated on the fly by the design layout."""
    return {**TURRET_TYPES, **spec.get("turret_types", {})}


def flight_deck_spec(fd):
    """Flight deck as drawn: outline points, plank lines, elevators, wires (segments), painted marks and the
    hull number. Layouts give this directly; the hand-authored short form (x0, x1, half_width, bow_taper,
    wires as x positions) is expanded here into an axial deck."""
    if "points" in fd:
        return fd
    x0, x1, hw, tap = fd["x0"], fd["x1"], fd["half_width"], fd.get("bow_taper", 14)
    marks = [dict(x1=x0 + 4, y1=0, x2=x1 - 4, y2=0, color="marking", width=0.5, dash="5 5")]
    for side in (-1, 1):
        marks.append(dict(x1=x0 + 1.5, y1=side * (hw - 1.0), x2=x1 - tap, y2=side * (hw - 1.0),
                          color="marking", width=0.35, opacity=0.85))
    for i in range(6):   # stern ramp stripes
        sx = x0 + 0.8 + i * 1.6
        marks.append(dict(x1=sx, y1=-hw + 1.5, x2=sx, y2=hw - 1.5, color="stripe", width=0.7,
                          opacity=0.9 if i % 2 == 0 else 0))
    return dict(points=[(x0, -hw), (x1 - tap, -hw), (x1, -hw * 0.42), (x1, hw * 0.42), (x1 - tap, hw), (x0, hw)],
                planks=dict(x0=x0, x1=x1, y0=-hw, y1=hw, step=1.4),
                elevators=fd.get("elevators", []), edge_elevators=fd.get("edge_elevators", []),
                wires=[(wx, -hw + 2, wx, hw - 2) for wx in fd.get("wires", [])], marks=marks,
                number=dict(x=x1 - tap - 14, y=0, text=fd["number"]) if fd.get("number") else None)


def ship_extent(spec, hull, scale=None, align=2):
    hw = hull.B / 2
    fd = spec.get("flight_deck")
    if fd:
        hw = max(hw, max(abs(y) for _, y in flight_deck_spec(fd)["points"]))
    for key in ("sponsons", "superstructure", "fittings"):
        for it in expand(spec.get(key), hull):
            hw = max(hw, abs(it.get("y", 0)) + it.get("w", 0) / 2)
    for m in spec.get("turrets", []):   # casemate guns stand on the hull side: keep their barrels on the canvas
        t = turret_types(spec)[m["type"]]
        if t.get("shape") == "casemate":
            hw = max(hw, abs(m.get("y", 0)) + turret_reach(t))
    hx, hy = hull.L / 2 + PAD_M, hw + PAD_M
    if scale:  # snap the canvas to a multiple of `align` px (even at least): origin lands on an exact pixel
        a = align / 2
        hx, hy = math.ceil(hx * scale / a) * a / scale, math.ceil(hy * scale / a) * a / scale
    return hx, hy


def vents(spec, hull, P):
    """Scatter small ventilators/hatches on level-1 deckhouses, avoiding everything else."""
    rng = random.Random(spec["id"])
    obstacles = []  # (x, y, radius)
    for m in expand(spec.get("turrets"), hull):
        obstacles.append((m["x"], m.get("y", 0), turret_types(spec)[m["type"]]["r"] * 1.15))
    for a in expand(spec.get("aa"), hull):
        obstacles.append((a["x"], a["y"], 2.4))
    for b in expand(spec.get("boats"), hull):
        obstacles.append((b["x"], b["y"], b.get("l", 7) / 2 + 0.6))
    rects = [(fn["x"] - fn["l"] / 2 - 0.8, fn.get("y", 0) - fn["w"] / 2 - 0.8,
              fn["x"] + fn["l"] / 2 + 2.5, fn.get("y", 0) + fn["w"] / 2 + 2.5)
             for fn in expand(spec.get("funnels"), hull)]
    rects += [(b["x0"] - 0.8, b.get("y", 0) - b["w"] / 2 - 0.8, b["x1"] + 2.0, b.get("y", 0) + b["w"] / 2 + 2.0)
              for b in expand(spec.get("superstructure"), hull) if b.get("level", 1) > 1]
    out = []
    for blk in expand(spec.get("superstructure"), hull):
        if blk.get("level", 1) != 1 or not blk.get("vents", True):
            continue
        y0 = blk.get("y", 0) - blk["w"] / 2 + 1.2
        y1 = blk.get("y", 0) + blk["w"] / 2 - 1.2
        x0, x1 = blk["x0"] + max(1.2, blk.get("rb", 0)), blk["x1"] - max(1.2, blk.get("rf", 0))
        n = int((x1 - x0) * (y1 - y0) / 35)
        for _ in range(n * 4):
            if n <= 0:
                break
            x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
            if any(math.hypot(x - ox, y - oy) < orr for ox, oy, orr in obstacles):
                continue
            if any(a <= x <= c and b <= y <= d for a, b, c, d in rects):
                continue
            obstacles.append((x, y, 1.6))
            n -= 1
            col = shade(P.p["levels"][0], 0.78)
            if rng.random() < 0.5:
                out.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="0.55" fill="{col}" {P.stroke(0.6)}/>'
                           f'<circle cx="{f(x + 0.12)}" cy="{f(y + 0.15)}" r="0.3" fill="#1d2125"/>')
            else:
                l, w = rng.choice([(1.6, 1.0), (1.0, 1.4), (2.2, 1.2)])
                out.append(f'<rect x="{f(x - l / 2)}" y="{f(y - w / 2)}" width="{f(l)}" height="{f(w)}" rx="0.2" '
                           f'fill="{col}" {P.stroke(0.6)}/>')
    return "".join(out)


def look_hull_spec(spec):
    """The hull as a look draws it (spec["shapes"]: bow_power and transom added, bow_flare). Drawing only, and only
    ever fuller than the layout's hull, so deck-edge fittings stay on deck; the hitbox keeps the layout's hull."""
    sh = spec.get("shapes") or {}
    if not any(sh.get(k) for k in ("bow_power", "bow_flare", "transom")):
        return spec
    hull = Hull(spec)
    bow = {**hull.bow, "power": hull.bow["power"] + sh.get("bow_power", 0.0), "flare": sh.get("bow_flare", 0.0)}
    stern = {**hull.stern, "transom": min(0.9, hull.stern["transom"] + sh.get("transom", 0.0))}
    return {**spec, "bow": bow, "stern": stern}


def build_hull_layers(spec, scale, align=2, shadows=True):
    pal = {**DEFAULT_PALETTE, **spec.get("palette", {})}
    P = Painter(pal, scale, shadows, spec.get("shapes"))
    hull = Hull(look_hull_spec(spec))
    hx, hy = ship_extent(spec, hull, scale, align)
    vb = (-hx, -hy, 2 * hx, 2 * hy)
    hull_d = hull_path(hull)
    defs = f'<clipPath id="hullclip"><path d="{hull_d}"/></clipPath>'

    base, upper = [], []

    # --- hull and deck -------------------------------------------------------
    base.append(f'<path d="{hull_d}" fill="{pal["hull"]}" {P.stroke(1.4)}/>')
    inset = spec.get("deck_inset", 0.55)
    deck_d = hull_path(hull, inset=inset, max_hw=spec.get("deck_max_hw"),
                          x_min=spec.get("deck_x0"), x_max=spec.get("deck_x1"))
    deck_col = pal["wood"] if spec.get("deck") == "wood" else pal["deck"]
    base.append(f'<path d="{deck_d}" fill="{deck_col}"/>')
    defs += f'<clipPath id="deckclip"><path d="{deck_d}"/></clipPath>'

    # planking / plating lines
    spacing = spec.get("plank_spacing", 1.25)
    lines = []
    yy = -hull.B / 2
    while yy < hull.B / 2:
        lines.append(f'<line x1="{f(-hull.L / 2)}" y1="{f(yy)}" x2="{f(hull.L / 2)}" y2="{f(yy)}"/>')
        yy += spacing
    # butt joints / plate seams across the deck
    xx = -hull.L / 2
    seam = 9.0 if spec.get("deck") == "wood" else 6.0
    while xx < hull.L / 2:
        lines.append(f'<line x1="{f(xx)}" y1="{f(-hull.B / 2)}" x2="{f(xx)}" y2="{f(hull.B / 2)}" stroke-dasharray="{f(spacing)} {f(spacing * 2)}"/>')
        xx += seam
    line_col = pal["deck_line"] if spec.get("deck") == "wood" else pal.get("steel_line", pal["deck_line"])
    base.append(f'<g clip-path="url(#deckclip)" stroke="{line_col}" stroke-width="{f(P.sw * 0.7)}" '
                f'stroke-opacity="{f(P.shapes.get("deck_line_opacity", 0.45))}">{"".join(lines)}</g>')

    # raised decks (forecastle, bridge deck, poop): the hull outline between x0 and x1, a step up
    for i, rd in enumerate(spec.get("raised_decks", [])):
        rd_d = hull_path(hull, inset=rd.get("inset", 0.3), x_min=rd["x0"], x_max=rd["x1"])
        defs += f'<clipPath id="rdclip{i}"><path d="{rd_d}"/></clipPath>'
        base.append(f'<path d="{rd_d}" fill="{shade(deck_col, 1.07)}" {P.stroke()}/>'
                    f'<g clip-path="url(#rdclip{i})" stroke="{line_col}" stroke-width="{f(P.sw * 0.7)}" '
                    f'stroke-opacity="0.45">{"".join(lines)}</g>')
    for ht in spec.get("hatches", []):
        base.append(P.hatch(ht))

    # bow details: anchor chains, breakwater, bollards
    bx = spec.get("chain_x")
    if bx:
        x_haw = hull.L / 2 - spec.get("hawse_back", 6.0)
        hw_haw = hull.half_width(x_haw) - 0.6
        for side in (-1, 1):
            base.append(f'<line x1="{f(bx)}" y1="{f(side * 1.6)}" x2="{f(x_haw)}" y2="{f(side * hw_haw)}" '
                        f'stroke="{pal["chain"]}" stroke-width="{f(max(0.45, P.sw * 2))}" stroke-dasharray="0.45 0.25"/>')
            base.append(f'<circle cx="{f(bx)}" cy="{f(side * 1.6)}" r="0.9" fill="{pal["fitting"]}" {P.stroke()}/>')
            base.append(f'<path d="M{f(x_haw - 1.2)},{f(side * (hw_haw + 0.2))} l1.6,{f(side * 0.6)} l0.6,{f(-side * 0.9)} Z" '
                        f'fill="{pal["chain"]}"/>')
    bw = spec.get("breakwater_x")
    if bw:
        hwb = hull.half_width(bw) - 1.2
        base.append(f'<path d="M{f(bw - hwb * 0.55)},{f(-hwb)} L{f(bw)},0 L{f(bw - hwb * 0.55)},{f(hwb)}" '
                    f'fill="none" stroke="{shade(deck_col, 0.6)}" stroke-width="{f(max(0.45, P.sw * 2.2))}"/>')
    for bxx in spec.get("bollards", []):
        for side in (-1, 1):
            by = side * (hull.half_width(bxx) - 1.1)
            base.append(f'<circle cx="{f(bxx)}" cy="{f(by)}" r="0.35" fill="{pal["fitting"]}" {P.stroke(0.6)}/>'
                        f'<circle cx="{f(bxx + 0.9)}" cy="{f(by)}" r="0.35" fill="{pal["fitting"]}" {P.stroke(0.6)}/>')

    # --- aircraft carrier flight deck ---------------------------------------
    fd = spec.get("flight_deck")
    if fd:
        for sp in expand(spec.get("sponsons"), hull):
            base.append(P.fitting({**sp, "color": pal["deck"], "r": 0.8}))
        fd = flight_deck_spec(fd)
        for el in fd.get("edge_elevators", []):
            base.append(P.fitting({**el, "color": pal["flight_deck"], "r": 0.4}))
        fd_d = poly(fd["points"])
        defs += f'<clipPath id="fdclip"><path d="{fd_d}"/></clipPath>'
        # shadow of the flight deck on the hull/sea is implied by a dark rim
        base.append(f'<path d="{fd_d}" fill="{pal["flight_deck"]}" {P.stroke(1.3)}/>')
        pk = fd["planks"]
        fl = []
        yy = pk["y0"]
        while yy < pk["y1"]:
            fl.append(f'<line x1="{f(pk["x0"])}" y1="{f(yy)}" x2="{f(pk["x1"])}" y2="{f(yy)}"/>')
            yy += pk["step"]
        base.append(f'<g clip-path="url(#fdclip)" stroke="{shade(pal["flight_deck"], 0.75)}" '
                    f'stroke-width="{f(P.sw * 0.7)}" stroke-opacity="0.6">{"".join(fl)}</g>')
        mk = pal["marking"]
        g = [f'<g clip-path="url(#fdclip)">']
        # elevators
        for el in fd.get("elevators", []):
            ex, ey, el_l, el_w = el["x"], el.get("y", 0), el["l"], el["w"]
            g.append(f'<rect x="{f(ex - el_l / 2)}" y="{f(ey - el_w / 2)}" width="{f(el_l)}" height="{f(el_w)}" '
                     f'fill="{shade(pal["flight_deck"], 0.88)}" stroke="{shade(pal["flight_deck"], 0.55)}" stroke-width="{f(P.sw * 1.2)}"/>')
        # arresting wires
        for x1_, y1_, x2_, y2_ in fd.get("wires", []):
            g.append(f'<line x1="{f(x1_)}" y1="{f(y1_)}" x2="{f(x2_)}" y2="{f(y2_)}" stroke="{shade(mk, 0.75)}" '
                     f'stroke-width="{f(max(0.25, P.sw))}" stroke-opacity="0.8"/>')
        # painted lines: centreline dashes, deck-edge stripes, ramp stripes, catapult tracks
        for ln in fd.get("marks", []):
            g.append(f'<line x1="{f(ln["x1"])}" y1="{f(ln["y1"])}" x2="{f(ln["x2"])}" y2="{f(ln["y2"])}" '
                     f'stroke="{pal[ln["color"]]}" stroke-width="{f(ln["width"])}"'
                     + (f' stroke-dasharray="{ln["dash"]}"' if ln.get("dash") else "")
                     + (f' stroke-opacity="{ln["opacity"]}"' if "opacity" in ln else "") + "/>")
        num = fd.get("number")
        if num:
            nx, ny = num["x"], num["y"]
            g.append(f'<text x="{f(nx)}" y="{f(ny)}" font-family="DejaVu Sans" font-weight="bold" '
                     f'font-size="{f(num.get("size", 9))}" fill="{mk}" text-anchor="middle" dominant-baseline="central" '
                     f'transform="rotate(90 {f(nx)} {f(ny)})">{num["text"]}</text>')
        g.append("</g>")
        base.append("".join(g))
        defs = defs.replace('<clipPath id="hullclip">', '<clipPath id="hullclip_unused">')
        defs += f'<clipPath id="hullclip"><path d="{hull_d}"/><path d="{fd_d}"/></clipPath>'

    # --- superstructure, fittings, AA, boats --------------------------------
    for sb in expand(spec.get("superstructure"), hull):
        layer = sb.get("layer", "base" if sb.get("level", 1) <= 1 else "upper")
        (base if layer == "base" else upper).append(P.block(sb, clip="hullclip"))
    base.append(vents(spec, hull, P))
    for ft in expand(spec.get("fittings"), hull):
        (upper if ft.get("layer") == "upper" else base).append(P.fitting(ft))
    for a in expand(spec.get("aa"), hull):
        (upper if a.get("layer") == "upper" else base).append(P.aa(a))
    for b in expand(spec.get("boats"), hull):
        (base if b.get("layer") == "base" else upper).append(P.boat(b))

    # --- turret barbettes (base layer, under the rotating turrets) ----------
    mounts = expand(spec.get("turrets"), hull)
    for m in mounts:
        t = turret_types(spec)[m["type"]]
        if t.get("barbette", True):
            base.append(P.barbette(m["x"], m["y"] if "y" in m else 0, t["r"] * t.get("barbette_k", 0.95)))

    # --- tall stuff ----------------------------------------------------------
    for fn in expand(spec.get("funnels"), hull):
        upper.append(P.funnel(fn, clip="hullclip"))
    for m in expand(spec.get("masts"), hull):
        upper.append(P.mast(m))
    for c in expand(spec.get("cranes"), hull):
        upper.append(P.crane(c))

    return (svg_doc("".join(base), vb, scale, defs),
            svg_doc("".join(upper), vb, scale, defs),
            vb, mounts, hull)


# ----------------------------------------------------------------------------
# turrets
# ----------------------------------------------------------------------------
def turret_extent(t, scale=None, align=2):
    half = max(t["r"] * 1.15, turret_reach(t)) + 1.0
    if scale:  # canvas a multiple of `align` px (even at least) -> pivot exactly at the image centre
        a = align / 2
        half = math.ceil(half * scale / a) * a / scale
    return half


def look_turret_body(look, r):
    """A look's drawing of an armoured (bb) turret, in units of r: (body outline, rangefinder parts, front face x,
    front face half-width). Drawing only: the hitbox keeps geometry.turret_shapes, and each outline stays
    close to it (verify.py checks the sprite against the hitbox)."""
    def mirror(top):   # top: points from the front centreline round the port side (y < 0) to the rear
        return [(x * r, y * r) for x, y in top] + [(x * r, -y * r) for x, y in reversed(top)]

    def ears(x0, x1, y0, y1, rad=0.0):
        return [rrect_polygon(x0 * r, y0 * r, x1 * r, y1 * r, rad * r, rad * r, seg=4),
                rrect_polygon(x0 * r, -y1 * r, x1 * r, -y0 * r, rad * r, rad * r, seg=4)]

    if look == "slab":       # boxy, slab-sided, rangefinder hoods on the rear corners
        body = rrect_polygon(-0.95 * r, -0.84 * r, 0.86 * r, 0.84 * r, 0.1 * r, 0.28 * r)
        return body, ears(-0.8, -0.56, -1.0, -0.7), 0.86 * r, 0.74 * r
    if look == "round":      # flat face, straight cheeks, a rounded rear; a long rangefinder right across
        rear = [(-0.05 - 0.92 * math.sin(math.radians(a)), -0.9 * math.cos(math.radians(a))) for a in range(0, 91, 10)]
        body = mirror([(0.8, -0.48)] + rear)
        return body, [rrect_polygon(-0.42 * r, -1.14 * r, -0.24 * r, 1.14 * r, 0.09 * r, 0.09 * r, seg=4)], 0.8 * r, 0.48 * r
    if look == "classic":    # straight sides into a semicircular rear
        rear = [(-0.18 - 0.8 * math.sin(math.radians(a)), -0.8 * math.cos(math.radians(a))) for a in range(0, 91, 10)]
        body = mirror([(0.86, -0.62), (0.76, -0.8)] + rear)
        return body, ears(-0.64, -0.46, -1.0, 1.0)[:1], 0.86 * r, 0.62 * r
    if look == "faceted":    # angled cheeks and rear corners, flat sides
        body = mirror([(0.86, -0.52), (0.58, -0.86), (-0.78, -0.86), (-0.95, -0.62), (-0.95, 0.0)])
        return body, ears(-0.6, -0.44, -0.98, -0.8), 0.86 * r, 0.52 * r
    if look == "drum":       # a Victorian round turret: a drum with sighting hoods standing out at the rear sides
        body = [((-0.05 + 0.9 * math.cos(math.radians(a))) * r, 0.9 * math.sin(math.radians(a)) * r)
                for a in range(0, 360, 10)]
        return body, ears(-0.55, -0.35, -0.98, -0.72, 0.08), 0.85 * r, 0.0
    raise ValueError(f"unknown turret look {look!r}")


def build_turret(t, palette, scale, align=2, shadows=True, look="standard"):
    """Turret sprite. Outlines come from geometry.turret_shapes, the same polygons used for hitboxes; a look
    other than "standard" redraws armoured turrets in its own style (look_turret_body)."""
    P = Painter(palette, scale, shadows)
    p = palette
    r = t["r"]
    n, bl, bw, sp = t["barrels"], t["barrel_len"], t["barrel_w"], t["spacing"]
    half = turret_extent(t, scale, align)
    s = []
    body_col = t.get("color", p["turret"])
    G = turret_shapes(t)

    def barrels(x_start):
        out = []
        for i, bpoly in enumerate(G["barrels"]):
            y = (i - (n - 1) / 2) * sp
            xe = x_start + bl
            out.append(f'<path d="{poly(bpoly)}" '
                       f'fill="{p["barrel"]}" {P.stroke(0.8)}/>')
            out.append(f'<line x1="{f(x_start)}" y1="{f(y - bw * 0.18)}" x2="{f(xe - bw)}" y2="{f(y - bw * 0.18)}" '
                       f'stroke="{shade(p["barrel"], 1.6)}" stroke-width="{f(bw * 0.18)}" stroke-opacity="0.55"/>')
            out.append(f'<rect x="{f(xe - bw * 0.9)}" y="{f(y - bw * 0.58)}" width="{f(bw * 0.9)}" height="{f(bw * 1.16)}" '
                       f'fill="{shade(p["barrel"], 0.7)}" {P.stroke(0.6)}/>')
        return "".join(out)

    shape = t.get("shape", "bb")
    # soft rotation-invariant contact shadow
    if shadows:
        s.append(f'<circle r="{f(r * 1.08)}" fill="#000" fill-opacity="0.18"/>')

    if shape == "bb" and look != "standard":
        pts, parts, xf, hf = look_turret_body(look, r)
        body = poly(pts)
        s.append(barrels(BARREL_ROOT["bb"] * r))
        for i in range(n):   # gun ports
            y = (i - (n - 1) / 2) * sp
            s.append(f'<rect x="{f(xf - 0.1 * r)}" y="{f(y - bw * 0.85)}" width="{f(0.2 * r)}" height="{f(bw * 1.7)}" '
                     f'rx="{f(bw * 0.3)}" fill="{shade(body_col, 0.55)}" {P.stroke(0.6)}/>')
        s.append(f'<path d="{body}" fill="{body_col}" {P.stroke(1.2)}/>')
        s.append(f'<path d="{body}" fill="{shade(body_col, 1.12)}" transform="translate({f(0.02 * r)},0) scale(0.8)"/>')
        if hf:   # sloped face plate (a drum turret has none)
            s.append(f'<path d="M{f(xf)},{f(-hf)} L{f(xf)},{f(hf)} L{f(xf - 0.22 * r)},{f(hf - 0.08 * r)} '
                     f'L{f(xf - 0.22 * r)},{f(-hf + 0.08 * r)} Z" fill="{shade(body_col, 0.82)}"/>')
        for part in parts:
            s.append(f'<path d="{poly(part)}" fill="{shade(body_col, 0.85)}" {P.stroke(0.8)}/>')
        hood = shade(body_col, 0.8)
        if look == "slab":      # three periscope hoods forward, a vent box aft
            for yy in (-0.5 * r, 0.0, 0.5 * r):
                s.append(f'<rect x="{f(0.3 * r)}" y="{f(yy - 0.08 * r)}" width="{f(0.18 * r)}" height="{f(0.16 * r)}" '
                         f'rx="{f(0.03 * r)}" fill="{hood}" {P.stroke(0.5)}/>')
            s.append(f'<rect x="{f(-0.6 * r)}" y="{f(-0.25 * r)}" width="{f(0.28 * r)}" height="{f(0.5 * r)}" '
                     f'rx="{f(0.05 * r)}" fill="{hood}" {P.stroke(0.5)}/>')
        elif look == "round":   # two round cupolas forward, a hatch amidships
            for yy in (-0.32 * r, 0.32 * r):
                s.append(f'<circle cx="{f(0.3 * r)}" cy="{f(yy)}" r="{f(0.1 * r)}" fill="{hood}" {P.stroke(0.5)}/>')
            s.append(f'<circle cx="{f(-0.05 * r)}" cy="0" r="{f(0.12 * r)}" fill="{hood}" {P.stroke(0.5)}/>')
        elif look == "classic":  # sighting hoods on the roof sides, a hatch aft
            for yy in (-0.5 * r, 0.5 * r):
                s.append(f'<rect x="{f(0.15 * r)}" y="{f(yy - 0.1 * r)}" width="{f(0.3 * r)}" height="{f(0.2 * r)}" '
                         f'rx="{f(0.08 * r)}" fill="{hood}" {P.stroke(0.5)}/>')
            s.append(f'<rect x="{f(-0.3 * r)}" y="{f(-0.12 * r)}" width="{f(0.22 * r)}" height="{f(0.24 * r)}" '
                     f'rx="{f(0.04 * r)}" fill="{hood}" {P.stroke(0.5)}/>')
        elif look == "drum":    # two small sighting hoods at the front edge, a round roof hatch
            for yy in (-0.38 * r, 0.38 * r):
                s.append(f'<rect x="{f(0.42 * r)}" y="{f(yy - 0.08 * r)}" width="{f(0.2 * r)}" height="{f(0.16 * r)}" '
                         f'rx="{f(0.05 * r)}" fill="{shade(body_col, 1.5)}" {P.stroke(0.5)}/>')
            s.append(f'<circle cx="{f(-0.2 * r)}" cy="0" r="{f(0.14 * r)}" fill="{shade(body_col, 1.4)}" {P.stroke(0.5)}/>')
        elif look == "faceted":  # domed cupolas forward, a rangefinder hood across the rear
            for yy in (-0.42 * r, 0.42 * r):
                s.append(f'<circle cx="{f(0.25 * r)}" cy="{f(yy)}" r="{f(0.12 * r)}" fill="{hood}" {P.stroke(0.5)}/>'
                         f'<circle cx="{f(0.22 * r)}" cy="{f(yy - 0.03 * r)}" r="{f(0.05 * r)}" '
                         f'fill="{shade(body_col, 1.2)}"/>')
            s.append(f'<rect x="{f(-0.62 * r)}" y="{f(-0.68 * r)}" width="{f(0.2 * r)}" height="{f(1.36 * r)}" '
                     f'rx="{f(0.06 * r)}" fill="{hood}" {P.stroke(0.5)}/>')

    elif shape == "bb":
        body = poly(G["body"])
        s.append(barrels(BARREL_ROOT["bb"] * r))
        # blast bags / gun ports
        for i in range(n):
            y = (i - (n - 1) / 2) * sp
            s.append(f'<rect x="{f(0.75 * r)}" y="{f(y - bw * 0.85)}" width="{f(0.2 * r)}" height="{f(bw * 1.7)}" '
                     f'rx="{f(bw * 0.3)}" fill="{shade(body_col, 0.55)}" {P.stroke(0.6)}/>')
        s.append(f'<path d="{body}" fill="{body_col}" {P.stroke(1.2)}/>')
        s.append(f'<path d="{body}" fill="{shade(body_col, 1.12)}" transform="translate({f(0.02 * r)},0) scale(0.8)"/>')
        # sloped front face plate
        s.append(f'<path d="M{f(0.85 * r)},{f(-0.5 * r)} L{f(0.85 * r)},{f(0.5 * r)} L{f(0.62 * r)},{f(0.42 * r)} '
                 f'L{f(0.62 * r)},{f(-0.42 * r)} Z" fill="{shade(body_col, 0.82)}"/>')
        # rangefinder ears
        for part in G["parts"]:
            s.append(f'<path d="{poly(part)}" fill="{shade(body_col, 0.85)}" {P.stroke(0.8)}/>')
        # roof hatches / periscope hoods
        for yy in (-0.45 * r, 0.45 * r):
            s.append(f'<rect x="{f(0.2 * r)}" y="{f(yy - 0.09 * r)}" width="{f(0.22 * r)}" height="{f(0.18 * r)}" '
                     f'rx="{f(0.05 * r)}" fill="{shade(body_col, 0.8)}" {P.stroke(0.5)}/>')
        s.append(f'<circle cx="{f(-0.15 * r)}" cy="0" r="{f(0.1 * r)}" fill="{shade(body_col, 0.8)}" {P.stroke(0.5)}/>')

    elif shape == "dp":
        body = poly(G["body"])
        s.append(barrels(BARREL_ROOT["dp"] * r))
        s.append(f'<path d="{body}" fill="{body_col}" {P.stroke(1.1)}/>')
        s.append(f'<path d="{body}" fill="{shade(body_col, 1.12)}" transform="translate({f(-0.05 * r)},0) scale(0.78)"/>')
        s.append(f'<rect x="{f(-0.55 * r)}" y="{f(-0.18 * r)}" width="{f(0.3 * r)}" height="{f(0.36 * r)}" '
                 f'rx="{f(0.06 * r)}" fill="{shade(body_col, 0.8)}" {P.stroke(0.5)}/>')

    elif shape == "open":
        s.append(f'<circle r="{f(r)}" fill="{p["tub"]}" {P.stroke()}/>')
        s.append(barrels(BARREL_ROOT["open"] * r))
        s.append(f'<path d="M{f(0.25 * r)},{f(-0.85 * r)} A{f(0.9 * r)},{f(0.9 * r)} 0 0 1 {f(0.25 * r)},{f(0.85 * r)}" '
                 f'fill="none" stroke="{body_col}" stroke-width="{f(0.28 * r)}" stroke-linecap="round"/>')
        s.append(f'<rect x="{f(-0.5 * r)}" y="{f(-0.25 * r)}" width="{f(0.6 * r)}" height="{f(0.5 * r)}" '
                 f'fill="{body_col}" {P.stroke(0.6)}/>')

    elif shape == "casemate":   # the port shield on the hull side and the barrels run out through it
        rc = CASEMATE_SHIELD * r
        s.append(barrels(BARREL_ROOT["casemate"] * r))
        s.append(f'<circle r="{f(rc)}" fill="{p["hull"]}" {P.stroke(1.1)}/>')
        s.append(f'<circle r="{f(rc * 0.72)}" fill="{shade(p["hull"], 1.25)}"/>')
        s.append(f'<rect x="{f(0.2 * rc)}" y="{f(-(n - 1) / 2 * sp - bw * 0.8)}" width="{f(0.8 * rc)}" '
                 f'height="{f((n - 1) * sp + bw * 1.6)}" fill="{shade(p["hull"], 0.45)}"/>')
        for i in range(n):   # the barrels' roots in the gun port
            y = (i - (n - 1) / 2) * sp
            s.append(f'<rect x="{f(0.2 * rc)}" y="{f(y - bw * 0.62)}" width="{f(0.8 * rc)}" height="{f(bw * 1.24)}" '
                     f'fill="{p["barrel"]}"/>')

    elif shape == "torp":
        s.append(f'<circle r="{f(r)}" fill="{shade(body_col, 0.85)}" {P.stroke()}/>')
        for i, tube in enumerate(G["barrels"]):
            y = (i - (n - 1) / 2) * sp
            s.append(f'<path d="{poly(tube)}" fill="{p["tube"]}" {P.stroke(0.8)}/>')
            s.append(f'<circle cx="{f(bl / 2 - bw / 2)}" cy="{f(y)}" r="{f(bw * 0.3)}" fill="#111"/>')
        bar, cab = G["parts"]
        s.append(f'<path d="{poly(bar)}" fill="{shade(body_col, 0.9)}" {P.stroke(0.7)}/>')
        s.append(f'<path d="{poly(cab)}" fill="{body_col}" {P.stroke(0.7)}/>')
    elif shape == "tube":
        # thin outlines: at 0.55 m a normal outline would visibly fatten the tube
        s.append(f'<path d="{poly(G["body"])}" fill="{shade(body_col, 0.8)}" {P.stroke(0.4)}/>')
        for i, tube in enumerate(G["barrels"]):
            y = (i - (n - 1) / 2) * sp
            s.append(f'<path d="{poly(tube)}" fill="{p["tube"]}" {P.stroke(0.4)}/>')
            s.append(f'<line x1="{f(-bl / 2 + 0.6)}" y1="{f(y - bw * 0.2)}" x2="{f(bl / 2 - 0.6)}" y2="{f(y - bw * 0.2)}" '
                     f'stroke="{shade(p["tube"], 1.5)}" stroke-width="{f(bw * 0.15)}" stroke-opacity="0.6"/>')
            s.append(f'<circle cx="{f(bl / 2 - bw / 2)}" cy="{f(y)}" r="{f(bw * 0.3)}" fill="#111"/>')
    else:
        raise ValueError(f"unknown turret shape {shape}")

    vb = (-half, -half, 2 * half, 2 * half)
    return svg_doc("".join(s), vb, scale)


# ----------------------------------------------------------------------------
# preview compositing
# ----------------------------------------------------------------------------
def clamp_angle(target, rest, trav):
    d = (target - rest + 180) % 360 - 180
    d = max(-trav, min(trav, d))
    return rest + d


def composite(base_png, upper_png, turret_pngs, meta, angle_fn):
    base = Image.open(base_png).convert("RGBA")
    upper = Image.open(upper_png).convert("RGBA")
    canvas = base.copy()
    for m in sorted(meta["mounts"], key=lambda m: m["z"]):
        timg = Image.open(turret_pngs[m["type"]]).convert("RGBA")
        ang = angle_fn(m)
        rot = timg.rotate(-ang, resample=Image.BICUBIC)
        cx, cy = m["px"]
        canvas.alpha_composite(rot, (round(cx - rot.width / 2), round(cy - rot.height / 2)))
    canvas.alpha_composite(upper)
    return canvas


def contact_sheet(rows, path, scale, sea="#2d5a73"):
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
    except OSError:
        font = small = ImageFont.load_default()
    gap = 24
    colw = max(max(a.width, b.width) for _, _, a, b in rows)
    W = colw * 2 + gap * 3
    H = gap + sum(max(a.height, b.height) + 34 + gap for _, _, a, b in rows)
    sheet = Image.new("RGBA", (W, H), sea)
    d = ImageDraw.Draw(sheet)
    y = gap
    for title, sub, a, b in rows:
        d.text((gap, y), title, fill="#e8eef2", font=font)
        d.text((gap + d.textlength(title, font=font) + 12, y + 4), sub, fill="#b7c7d1", font=small)
        y += 30
        h = max(a.height, b.height)
        sheet.alpha_composite(a, (gap + (colw - a.width) // 2, y + (h - a.height) // 2))
        sheet.alpha_composite(b, (gap * 2 + colw + (colw - b.width) // 2, y + (h - b.height) // 2))
        y += h + gap + 4
    d.text((gap, H - 20), f"left: turrets at rest   |   right: trained to starboard (clamped to arcs)   |   {scale} px/m",
           fill="#9fb4c1", font=small)
    sheet.convert("RGB").save(path)


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------
def render(svg, png_path, svg_path=None):
    if svg_path:
        with open(svg_path, "w") as fh:
            fh.write(svg)
    cairosvg.svg2png(bytestring=svg.encode(), write_to=png_path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scale", type=float, default=3.0, help="pixels per metre (default 3)")
    ap.add_argument("--out", default="out")
    ap.add_argument("--only", nargs="*", help="ship ids to build")
    args = ap.parse_args()
    S = args.scale
    os.makedirs(os.path.join(args.out, "turrets"), exist_ok=True)
    os.makedirs(os.path.join(args.out, "preview"), exist_ok=True)

    ships = [s for s in FLEET if not args.only or s["id"] in args.only]
    manifest = {"scale_px_per_m": S, "orientation": "bow points +x (right); angles clockwise, 0 = ahead",
                "layer_order": ["hull_base", "turrets (ascending z)", "hull_upper"],
                "turrets": {}, "ships": []}

    # turret sprites (shared between ships)
    turret_pngs = {}
    used = {m["type"] for s in ships for m in s.get("turrets", [])}
    for tid in sorted(used):
        t = TURRET_TYPES[tid]
        pal = {**DEFAULT_PALETTE, **t.get("palette", {})}
        svg = build_turret(t, pal, S)
        png = os.path.join(args.out, "turrets", f"{tid}.png")
        render(svg, png, png.replace(".png", ".svg"))
        turret_pngs[tid] = png
        size = Image.open(png).size
        manifest["turrets"][tid] = {"file": f"turrets/{tid}.png", "size_px": size,
                                    "pivot_px": [size[0] / 2, size[1] / 2],
                                    "desc": t.get("desc", "")}

    rows = []
    for spec in ships:
        sid = spec["id"]
        d = os.path.join(args.out, "ships", sid)
        os.makedirs(d, exist_ok=True)
        base_svg, upper_svg, vb, mounts, hull = build_hull_layers(spec, S)
        render(base_svg, os.path.join(d, "hull_base.png"), os.path.join(d, "hull_base.svg"))
        render(upper_svg, os.path.join(d, "hull_upper.png"), os.path.join(d, "hull_upper.svg"))
        W, H = Image.open(os.path.join(d, "hull_base.png")).size
        ox, oy = W / 2, H / 2
        meta = {"id": sid, "name": spec["name"], "class": spec["class"],
                "length_m": hull.L, "beam_m": hull.B, "scale_px_per_m": S,
                "size_px": [W, H], "origin_px": [ox, oy],
                "layers": {"base": f"ships/{sid}/hull_base.png", "upper": f"ships/{sid}/hull_upper.png"},
                "mounts": []}
        for i, m in enumerate(mounts):
            y = m.get("y", 0)
            rest = m.get("rest", 180 if m["x"] < 0 else 0)
            meta["mounts"].append({
                "id": m.get("id", f"M{i}"), "type": m["type"],
                "pos_m": [m["x"], y], "px": [ox + m["x"] * S, oy + y * S],
                "rest_deg": rest, "traverse_deg": m.get("traverse", 150), "z": m.get("z", 1)})
        with open(os.path.join(d, f"{sid}.json"), "w") as fh:
            json.dump(meta, fh, indent=2)
        manifest["ships"].append({"id": sid, "meta": f"ships/{sid}/{sid}.json"})

        rest_img = composite(os.path.join(d, "hull_base.png"), os.path.join(d, "hull_upper.png"),
                             turret_pngs, meta, lambda m: m["rest_deg"])
        bs_img = composite(os.path.join(d, "hull_base.png"), os.path.join(d, "hull_upper.png"),
                           turret_pngs, meta, lambda m: clamp_angle(90, m["rest_deg"], m["traverse_deg"]))
        rest_img.save(os.path.join(args.out, "preview", f"{sid}_rest.png"))
        bs_img.save(os.path.join(args.out, "preview", f"{sid}_starboard.png"))
        rows.append((spec["name"], f'{spec["class"]} · {hull.L:.0f} × {hull.B:.0f} m', rest_img, bs_img))
        print(f"built {sid}: {W}x{H}px, {len(mounts)} mounts")

    with open(os.path.join(args.out, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    contact_sheet(rows, os.path.join(args.out, "preview", "fleet_sheet.png"), S)
    print("wrote", os.path.join(args.out, "preview", "fleet_sheet.png"))


if __name__ == "__main__":
    main()
