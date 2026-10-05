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
* Each ship becomes a static hull image and turret sprites, drawn in this order:
    1. hull     - everything that doesn't rotate: hull, deck, superstructure, funnels, masts, boats, AA
    2. turrets  - separate sprites, pivot at the image centre, sorted by mount "z"
  Turrets draw over the whole hull image: what stands taller than a turret's guns keeps out of its sweep,
  and shadows come from the height map, so nothing needs to draw over a turret.
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
import zlib

import cairosvg
from PIL import Image, ImageDraw, ImageFont

from fleet import FLEET, TURRET_TYPES
from looks import DEFAULT_PALETTE
import clutter
from geometry import turret_shapes, turret_reach, barrel_shown, BARREL_ROOT, CASEMATE_SHIELD, rrect_polygon, Hull, AA_CFG, point_in_polygon, \
    director_parts

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
        self.dazzle = []        # dazzle camouflage panels [(points, colour)], set by build_hull
        self._clip_n = 0
        # keep outlines at least ~0.6 px wide whatever the scale
        self.sw = max(0.12, 0.6 / scale)

    def dazzled(self, d, opacity=1.0):
        """The dazzle panels clipped to the outline d (an SVG path), or "" with no dazzle."""
        if not self.dazzle or opacity <= 0:
            return ""
        self._clip_n += 1
        cid = f"dz{self._clip_n}"
        op = f' opacity="{f(opacity)}"' if opacity < 1 else ""
        return (f'<clipPath id="{cid}"><path d="{d}"/></clipPath><g clip-path="url(#{cid})"{op}>'
                + "".join(f'<path d="{poly(pts)}" fill="{col}"/>' for pts, col in self.dazzle) + "</g>")

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
        if b.get("director"):
            return self.director(b, shadow, clip)
        lvl = b.get("level", 1)
        x0, x1 = b["x0"], b["x1"]
        y = b.get("y", 0)
        w = b["w"]
        rf, rb = b.get("rf", 0.8), b.get("rb", 0.8)
        mode = self.shapes.get("blocks")
        if b.get("points"):       # the layout's own outline, sharp-cornered
            d = poly(b["points"])
        elif mode == "chamfer":     # cut corners instead of round ones
            h = w / 2
            cf, cb = min(rf, h, (x1 - x0) / 2), min(rb, h, (x1 - x0) / 2)
            d = poly([(x0 + cb, y - h), (x1 - cf, y - h), (x1, y - h + cf), (x1, y + h - cf), (x1 - cf, y + h),
                      (x0 + cb, y + h), (x0, y + h - cb), (x0, y - h + cb)])
        elif mode == "tower" and lvl >= self.shapes.get("tower_level", 3):   # a round-fronted tower bridge
            d = rrect_path(x0, y - w / 2, x1, y + w / 2, min(w / 2, (x1 - x0) * 0.6), rb * 0.4)
        else:
            kf, kb = self.shapes.get("block_round") or \
                {"boxy": (0.35, 0.35), "soft": (1.6, 1.4), "bowfront": (1.5, 0.4), "tower": (1.2, 0.5)}.get(mode, (1.0, 1.0))
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
        s.append(self.dazzled(d))
        # a thin lighter rim on the port/fwd edge suggests light from the upper-left
        s.append(f'<path d="{d}" fill="none" stroke="{shade(col, 1.25)}" stroke-width="{f(self.sw * 0.9)}" '
                 f'transform="translate({f(-self.sw * 0.6)},{f(-self.sw * 0.6)})" stroke-opacity="0.7"/>')
        return "".join(s)

    def director(self, b, shadow=True, clip=None):
        """A fire-control director on its roof, facing ahead (layout block with "director"), drawn from
        geometry.director_parts, the same shape as its hitbox: the hood, the rangefinder's tube and end hoods
        sticking out each side, and a radar aerial on the hood's roof when it has one. Without a rangefinder (a
        gyro sight, Mk 51 style): a round tub with the sight in it."""
        dr = b["director"]
        x0, x1, y, w = b["x0"], b["x1"], b.get("y", 0), b["w"]
        l, xc = x1 - x0, (x0 + x1) / 2
        rf = dr.get("rangefinder_m", 0)
        parts = director_parts(xc, y, l, w, rf)
        p = self.p
        cols = p["levels"]
        col = cols[min(dr.get("on", 0) + 1, len(cols)) - 1]    # a shade lighter than the roof it stands on
        hood = poly(parts["hood"])
        s = []
        if shadow and self.shadows:     # one hood's height above its roof, like a level-1 block
            cl = f' clip-path="url(#{clip})"' if clip else ""
            s.append(f'<g{cl}><path d="{poly(parts["outline"])}" transform="translate({f(0.42)},{f(0.7)})" '
                     f'fill="#000" fill-opacity="0.28"/></g>')
        if rf:
            if parts["tube"]:
                s.append(f'<path d="{poly(parts["tube"])}" fill="{shade(col, 0.7)}" {self.stroke()}/>')
            s += [f'<path d="{poly(e)}" fill="{shade(col, 0.85)}" {self.stroke()}/>' for e in parts["ends"]]
            s.append(f'<path d="{hood}" fill="{col}" {self.stroke()}/>')
            s.append(self.dazzled(hood))
            # the hood's roof: a sighting hatch aft, and the radar aerial (a flat dish seen edge-on) forward
            hw = max(py for _, py in parts["hood"]) - y
            s.append(f'<path d="{rrect_path(x0 + 0.12 * l, y - 0.4 * hw, x0 + 0.32 * l, y + 0.4 * hw, 0.1, 0.1)}" '
                     f'fill="{shade(col, 0.88)}" {self.stroke(0.6)}/>')
            if dr.get("radar"):
                ax, aw = xc + 0.22 * l, 1.5 * hw
                s.append(f'<line x1="{f(xc)}" y1="{f(y)}" x2="{f(ax)}" y2="{f(y)}" stroke="{p["mast"]}" '
                         f'stroke-width="{f(max(self.sw * 1.2, 0.18))}"/>')
                s.append(f'<path d="{rrect_path(ax - 0.18, y - aw / 2, ax + 0.18, y + aw / 2, 0.12, 0.12)}" '
                         f'fill="{p["mast"]}" {self.stroke(0.6)}/>')
        else:
            r = min(l, w) / 2
            s.append(f'<path d="{hood}" fill="{p["tub"]}" {self.stroke()}/>')
            s.append(f'<circle cx="{f(xc)}" cy="{f(y)}" r="{f(r * 0.72)}" fill="{shade(p["tub"], 0.8)}"/>')
            s.append(f'<path d="{rrect_path(xc - 0.3 * r, y - 0.35 * r, xc + 0.25 * r, y + 0.35 * r, 0.08, 0.08)}" '
                     f'fill="{col}" {self.stroke(0.6)}/>')
            s.append(f'<line x1="{f(xc + 0.25 * r)}" y1="{f(y)}" x2="{f(xc + 0.6 * r)}" y2="{f(y)}" '
                     f'stroke="{p["barrel"]}" stroke-width="{f(max(self.sw * 1.2, 0.15))}"/>')
        s.append(f'<path d="{hood}" fill="none" stroke="{shade(col, 1.25)}" stroke-width="{f(self.sw * 0.9)}" '
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
        rake = self.shapes.get("funnel_rake", 0.0)   # a raked funnel: the top seen displaced aft of its foot
        s = [f'<g{cl}><path d="{d}" transform="translate({f(w * 0.3)},{f(w * 0.5)})" fill="#000" fill-opacity="0.25"/></g>'
             if self.shadows else ""]
        if rake:   # the foot, then the casing's forward face sloping back to the top
            s.append(f'<path d="{d}" fill="{shade(p["funnel"], 0.9)}" {self.stroke()}/>'
                     f'<rect x="{f(x - rake)}" y="{f(y - w / 2)}" width="{f(rake)}" height="{f(w)}" '
                     f'fill="{shade(p["funnel"], 0.9)}"/>'
                     f'<line x1="{f(x - rake)}" y1="{f(y - w / 2)}" x2="{f(x)}" y2="{f(y - w / 2)}" {self.stroke()}/>'
                     f'<line x1="{f(x - rake)}" y1="{f(y + w / 2)}" x2="{f(x)}" y2="{f(y + w / 2)}" {self.stroke()}/>')
            s.append(f'<g transform="translate({f(-rake)},0)">')
        s += [f'<path d="{d}" fill="{p["funnel"]}" {self.stroke()}/>', self.dazzled(d),
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
        cap = self.shapes.get("funnel_cap")
        if cap == "pan":         # an Italian "frying pan": a flat plate over the top, overhanging aft, open forward
            pl, pw = l * 0.8, w * 1.08
            px = x - l * 0.22
            s.append(f'<path d="{rrect_path(px - pl / 2, y - pw / 2, px + pl / 2, y + pw / 2, pw * 0.3, pw / 2)}" '
                     f'fill="{shade(p["funnel"], 0.8)}" {self.stroke(0.9)}/>')
            for i in range(1, 4):   # the plate's stiffeners
                gx = px - pl / 2 + pl * i / 4
                s.append(f'<line x1="{f(gx)}" y1="{f(y - pw / 2 + 0.3)}" x2="{f(gx)}" y2="{f(y + pw / 2 - 0.3)}" '
                         f'stroke="{shade(p["funnel"], 0.6)}" stroke-width="{f(self.sw * 0.8)}"/>')
        elif cap == "hat":       # a French "chapeau": a broad black cap with smoke vanes all round
            hl, hw_ = l + 1.2, w + 1.2
            hd = rrect_path(x - hl / 2, y - hw_ / 2, x + hl / 2, y + hw_ / 2, min(hw_ / 2, r + 0.6), min(hw_ / 2, r + 0.6))
            s.append(f'<path d="{hd}" fill="{p["funnel_cap"]}" {self.stroke()}/>')
            s.append(f'<path d="{inner}" fill="{shade(p["funnel_cap"], 1.25)}" transform="translate({f(x * 0.12)},'
                     f'{f(y * 0.12)}) scale(0.88)"/>')
            for i in range(max(2, int(l / 1.5))):   # vanes across the cap
                vx = x - l / 2 + 0.3 + (l - 0.6) * (i + 0.5) / max(2, int(l / 1.5))
                s.append(f'<line x1="{f(vx)}" y1="{f(y - w / 2 - 0.4)}" x2="{f(vx)}" y2="{f(y + w / 2 + 0.4)}" '
                         f'stroke="{shade(p["funnel_cap"], 2.2)}" stroke-width="{f(self.sw * 0.7)}" stroke-opacity="0.7"/>')
        # cap grating highlight
        s.append(f'<path d="{d}" fill="none" stroke="{shade(p["funnel"], 1.3)}" stroke-width="{f(self.sw)}" '
                 f'transform="translate({f(-self.sw * 0.6)},{f(-self.sw * 0.6)})" stroke-opacity="0.6"/>')
        if rake:
            s.append("</g>")
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
        legs = self.shapes.get("tripod", 0.0 if mode in ("pole", "fighting_top", "cage", "lattice") else 1.0)   # 0: every mast a pole
        if m.get("tripod", True) and legs:
            for ang in (150, 210):
                lx = x + 4.0 * legs * math.cos(math.radians(ang))
                ly = y + 3.0 * legs * (1 if ang == 150 else -1)
                s.append(f'<line x1="{f(x)}" y1="{f(y)}" x2="{f(lx)}" y2="{f(ly)}" '
                         f'stroke="{p["mast"]}" stroke-width="{f(max(self.sw * 1.3, 0.3))}" stroke-linecap="round"/>')
        cage = self.shapes.get("cage_r", 3.0 if mode == "cage" else 0.0)
        if cage and m.get("tripod", True):   # a US cage (lattice) mast from above, where a big ship has a tripod: twisted struts from a wide foot to a narrow head
            for i in range(12):
                a0, a1 = math.radians(i * 30), math.radians(i * 30 + 75)
                s.append(f'<line x1="{f(x + cage * math.cos(a0))}" y1="{f(y + cage * math.sin(a0))}" '
                         f'x2="{f(x + 0.4 * cage * math.cos(a1))}" y2="{f(y + 0.4 * cage * math.sin(a1))}" '
                         f'stroke="{p["mast"]}" stroke-width="{f(max(self.sw * 0.8, 0.15))}"/>')
            s.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(cage)}" fill="none" stroke="{p["mast"]}" '
                     f'stroke-width="{f(max(self.sw * 0.8, 0.15))}"/>'
                     f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(0.45 * cage)}" fill="{shade(p["mast"], 0.85)}" {self.stroke(0.6)}/>')
        lat = self.shapes.get("lattice_r", 2.2 if mode == "lattice" else 0.0)
        if lat and m.get("tripod", True):   # a lattice mast: a square braced truss narrowing to a radar platform
            for k in (1.0, 0.55):
                q = lat * k
                s.append(f'<rect x="{f(x - q)}" y="{f(y - q)}" width="{f(2 * q)}" height="{f(2 * q)}" fill="none" '
                         f'stroke="{p["mast"]}" stroke-width="{f(max(self.sw * 0.9, 0.18))}"/>')
            for sx, sy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                s.append(f'<line x1="{f(x + sx * lat)}" y1="{f(y + sy * lat)}" x2="{f(x - sx * 0.55 * lat)}" '
                         f'y2="{f(y + sy * 0.55 * lat)}" stroke="{p["mast"]}" stroke-width="{f(max(self.sw * 0.7, 0.14))}"/>')
            s.append(f'<rect x="{f(x - 0.4 * lat)}" y="{f(y - 0.4 * lat)}" width="{f(0.8 * lat)}" height="{f(0.8 * lat)}" '
                     f'fill="{shade(p["mast"], 1.3)}" {self.stroke(0.6)}/>'
                     f'<line x1="{f(x)}" y1="{f(y - 1.3 * lat)}" x2="{f(x)}" y2="{f(y + 1.3 * lat)}" '
                     f'stroke="{shade(p["mast"], 0.8)}" stroke-width="{f(max(self.sw * 1.6, 0.35))}"/>')
        top = self.shapes.get("top_r", 1.6 if mode == "fighting_top" else 0.0)
        for i in range(self.shapes.get("top_tiers", 1) if top else 0):   # a fighting top; tiers stack a pagoda
            r = top * (1 - 0.3 * i)
            s.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" fill="{shade(p["mast"], 0.75 + 0.2 * i)}" '
                     f'{self.stroke(0.8)}/>'
                     f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r - 0.35)}" fill="none" stroke="{shade(p["mast"], 1.2 + 0.2 * i)}" '
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
            if blk.get("points") and not all(point_in_polygon(x + dx, y + dy, blk["points"])
                                             for dx in (-1.2, 1.2) for dy in (-1.2, 1.2)):
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


def deck_obstacles(spec, hull, small=False):
    """Footprints (x0, x1, y0, y1) of what stands on deck: turrets, superstructure and funnels; with small, also
    AA, boats, masts and fittings. The look features that paint the open deck (stripes, awnings, numbers) keep
    clear of them."""
    out = []
    for m in expand(spec.get("turrets"), hull):
        r = turret_types(spec)[m["type"]]["r"] * 1.15
        out.append((m["x"] - r, m["x"] + r, m.get("y", 0) - r, m.get("y", 0) + r))
    for b in expand(spec.get("superstructure"), hull):
        out.append((b["x0"], b["x1"], b.get("y", 0) - b["w"] / 2, b.get("y", 0) + b["w"] / 2))
    for fn in expand(spec.get("funnels"), hull):
        out.append((fn["x"] - fn["l"] / 2, fn["x"] + fn["l"] / 2, fn.get("y", 0) - fn["w"] / 2, fn.get("y", 0) + fn["w"] / 2))
    if small:
        for a in expand(spec.get("aa"), hull):
            out.append((a["x"] - 2.0, a["x"] + 2.0, a["y"] - 2.0, a["y"] + 2.0))
        for it in expand(spec.get("boats"), hull) + expand(spec.get("fittings"), hull):
            l, w = it.get("l", 7), it.get("w", 2.2)
            out.append((it["x"] - l / 2, it["x"] + l / 2, it["y"] - w / 2, it["y"] + w / 2))
        for m in expand(spec.get("masts"), hull):
            out.append((m["x"] - 1.0, m["x"] + 1.0, m.get("y", 0) - 1.0, m.get("y", 0) + 1.0))
    return out


def open_ends(spec, hull, half_y=None, small=False):
    """The open foredeck and quarterdeck: (front of the foremost obstacle, back of the aftmost), counting only
    obstacles within half_y of the centreline when given."""
    obs = [o for o in deck_obstacles(spec, hull, small) if half_y is None or (o[2] < half_y and o[3] > -half_y)]
    if not obs:
        return 0.0, 0.0
    return max(o[1] for o in obs), min(o[0] for o in obs)


def dazzle_panels(spec, hull, colours):
    """Dazzle camouflage: slanted panels cut across the whole ship, in a repeatable pattern per design (seeded by
    its id). Panels are clipped to the hull band, the superstructure and the funnels as they're drawn."""
    rng = random.Random(f'{spec["id"]}/dazzle')
    L, Y = hull.L, hull.B / 2 + 2.0
    n = max(5, round(L / 18))
    step = L / n
    cuts = [(-L / 2 - 2.0, 0.0)] + [(-L / 2 + step * i + rng.uniform(-0.2, 0.2) * step,
                                     rng.uniform(-0.45, 0.45) * step / Y) for i in range(1, n)] + [(L / 2 + 2.0, 0.0)]
    out, last = [], None
    for (c0, k0), (c1, k1) in zip(cuts, cuts[1:]):
        col = rng.choice([c for c in [None] + list(colours) if c != last])
        last = col
        if col:
            out.append(([(c0 - k0 * Y, -Y), (c1 - k1 * Y, -Y), (c1 + k1 * Y, Y), (c0 + k0 * Y, Y)], col))
        if rng.random() < 0.5:   # a wedge from one side into the panel, in another colour
            side = rng.choice((-1, 1))
            mid = (c0 + c1) / 2
            wcol = rng.choice([c for c in colours if c != col])
            out.append(([(mid - 0.35 * step, side * Y), (mid + 0.35 * step, side * Y),
                         (mid + rng.uniform(-0.3, 0.3) * step, side * Y * rng.uniform(-0.2, 0.4))], wcol))
    return out


def deck_paint(spec, hull, P):
    """A look's paint and canvas on the open deck (P.shapes): recognition stripes on the forecastle (and
    quarterdeck) and peacetime awnings over the quarterdeck; then, separately (drawn over the anchor chains),
    a hull number on the foredeck."""
    sh, pal, L = P.shapes, P.p, hull.L
    out = []
    tip = L / 2 - 0.04 * L
    st = sh.get("deck_stripes")
    if st and not spec.get("flight_deck"):   # alternating bands, chevrons pointing ahead by default
        fwd, aft = open_ends(spec, hull)
        n, k = st.get("n", 5), (st.get("slope", 0.8) if st.get("pattern", "chevron") == "chevron" else 0.0)
        cols = [pal.get(c, c) for c in st.get("colours", ("recog_a", "recog_b"))]
        Y = hull.B / 2
        spans = [(fwd + 1.0, tip + 0.04 * L, 1)] + ([(-L / 2, aft - 1.0, -1)] if st.get("ends") == "both" else [])
        for i, (x0, x1, dirn) in enumerate(spans):
            if x1 - x0 < 4.0:
                continue
            band = (x1 - x0) / (2 * n)
            g = [f'<clipPath id="stripe{i}"><rect x="{f(x0)}" y="{f(-Y)}" width="{f(x1 - x0)}" height="{f(2 * Y)}"/></clipPath>'
                 f'<g clip-path="url(#deckclip)"><g clip-path="url(#stripe{i})">']
            for j in range(int((x1 - x0 + k * Y) / band) + 4):
                u0 = (x0 if dirn > 0 else x1) + dirn * band * (j - 1)
                u1 = u0 + dirn * band
                pts = [(u0, 0), (u0 - dirn * k * Y, -Y), (u1 - dirn * k * Y, -Y), (u1, 0), (u1 - dirn * k * Y, Y),
                       (u0 - dirn * k * Y, Y)] if k else [(u0 - 0.6 * Y, -Y), (u1 - 0.6 * Y, -Y), (u1 + 0.6 * Y, Y),
                                                          (u0 + 0.6 * Y, Y)]
                out_col = cols[j % len(cols)]
                g.append(f'<path d="{poly(pts)}" fill="{out_col}"/>')
            out.append("".join(g) + "</g></g>")
    aw = sh.get("awnings")
    if aw and not spec.get("flight_deck"):   # canvas on stanchions over the quarterdeck, ridged along the centreline
        _, aft = open_ends(spec, hull)
        x0, x1 = -L / 2 + 0.03 * L, aft - 1.2
        if x1 - x0 > 6.0:
            d = hull_path(hull, inset=1.1, x_min=x0, x_max=x1)
            col = pal.get("awning", "#ece7d6")
            ribs = "".join(f'<line x1="{f(x)}" y1="{f(-hull.B)}" x2="{f(x)}" y2="{f(hull.B)}"/>'
                           for x in [x0 + 2.5 * i for i in range(1, int((x1 - x0) / 2.5) + 1)])
            out.append(f'<clipPath id="awning"><path d="{d}"/></clipPath>'
                       f'<path d="{d}" fill="{col}" {P.stroke(0.9)}/>'
                       f'<g clip-path="url(#awning)"><rect x="{f(x0)}" y="0" width="{f(x1 - x0)}" height="{f(hull.B)}" '
                       f'fill="#000" fill-opacity="0.1"/>'
                       f'<g stroke="{shade(col, 0.72)}" stroke-width="{f(P.sw * 0.8)}">{ribs}</g>'
                       f'<line x1="{f(x0)}" y1="0" x2="{f(x1)}" y2="0" stroke="{shade(col, 0.65)}" '
                       f'stroke-width="{f(P.sw * 1.2)}"/></g>')
    num = []
    if sh.get("hull_number") and not spec.get("flight_deck"):   # painted big across the foredeck
        text = str(sh.get("number") or 100 + zlib.crc32(spec["id"].encode()) % 900)
        hw = hull.half_width(L / 2 - 0.15 * L)
        size = 0.75 * 2 * hw / (0.62 * len(text))
        fwd, _ = open_ends(spec, hull, half_y=0.62 * len(text) * size / 2, small=True)
        x1 = L / 2 - 0.12 * L
        size = min(size, (x1 - fwd) * 0.8, 0.05 * L)
        if size > 1.2:
            nx = x1 - size * 0.6
            num.append(f'<text x="{f(nx)}" y="0" font-family="DejaVu Sans" font-weight="bold" font-size="{f(size)}" '
                       f'fill="{pal.get("number", pal["marking"])}" fill-opacity="0.92" text-anchor="middle" '
                       f'dominant-baseline="central" transform="rotate(90 {f(nx)} 0)">{text}</text>')
    return "".join(out), "".join(num)


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


def build_hull(spec, scale, align=2, shadows=True):
    pal = {**DEFAULT_PALETTE, **spec.get("palette", {})}
    P = Painter(pal, scale, shadows, spec.get("shapes"))
    sh = P.shapes
    hull = Hull(look_hull_spec(spec))
    hx, hy = ship_extent(spec, hull, scale, align)
    vb = (-hx, -hy, 2 * hx, 2 * hy)
    # tumblehome: the hull's sides bulge out below a narrower deck, seen from above as a wide band round the deck
    outer = Hull({**look_hull_spec(spec), "beam": hull.B * (1 + sh["tumblehome"])}) if sh.get("tumblehome") else hull
    hull_d = hull_path(outer)
    defs = f'<clipPath id="hullclip"><path d="{hull_d}"/></clipPath>'
    if sh.get("dazzle") and pal.get("camo"):
        P.dazzle = dazzle_panels(spec, hull, pal["camo"])

    # two passes in one image: low (hull, deck, level 1, what stands on the deck), then high (what stands on
    # a roof, and the tall stuff), so a roof never draws over what stands on it
    low, high = [], []

    # --- hull and deck -------------------------------------------------------
    low.append(f'<path d="{hull_d}" fill="{pal["hull"]}" {P.stroke(1.4)}/>')
    low.append(P.dazzled(hull_d))
    inset = spec.get("deck_inset", 0.55)
    deck_d = hull_path(hull, inset=inset, max_hw=spec.get("deck_max_hw"),
                          x_min=spec.get("deck_x0"), x_max=spec.get("deck_x1"))
    deck_col = pal["wood"] if spec.get("deck") == "wood" else pal["deck"]
    low.append(f'<path d="{deck_d}" fill="{deck_col}"/>')
    low.append(P.dazzled(deck_d, sh.get("dazzle_decks", 0.0)))   # painted decks, under the planking lines
    defs += f'<clipPath id="deckclip"><path d="{deck_d}"/></clipPath>'

    # planking / plating lines
    spacing = spec.get("plank_spacing", 1.25)
    seam = 9.0 if spec.get("deck") == "wood" else 6.0

    def plank_lines(x0, x1, y_off=0.0, dash_off=0.0):
        """Planks (or plates) along the deck from x0 to x1, their seams across it from x0 on: y_off shifts the
        planks across, dash_off the butt joints along each seam."""
        out = []
        yy = -hull.B / 2 + y_off
        while yy < hull.B / 2:
            out.append(f'<line x1="{f(x0)}" y1="{f(yy)}" x2="{f(x1)}" y2="{f(yy)}"/>')
            yy += spacing
        xx = x0
        while xx < x1:
            out.append(f'<line x1="{f(xx)}" y1="{f(-hull.B / 2)}" x2="{f(xx)}" y2="{f(hull.B / 2)}" '
                       f'stroke-dasharray="{f(spacing)} {f(spacing * 2)}"'
                       + (f' stroke-dashoffset="{f(dash_off)}"' if dash_off else "") + '/>')
            xx += seam
        return out

    lines = plank_lines(-hull.L / 2, hull.L / 2)
    line_col = pal["deck_line"] if spec.get("deck") == "wood" else pal.get("steel_line", pal["deck_line"])
    # a margin plank round the deck's edge (every deck has one, the raised ones too): the planking stops at it
    margin = 2 * spacing / 3
    mhw = spec.get("deck_max_hw")
    main_margin_d = hull_path(hull, inset=inset + margin, max_hw=mhw - margin if mhw else None,
                              x_min=spec["deck_x0"] + margin if spec.get("deck_x0") is not None else None,
                              x_max=spec["deck_x1"] - margin if spec.get("deck_x1") is not None else None)
    defs += f'<clipPath id="deckmargin"><path d="{main_margin_d}"/></clipPath>'
    line_op = f(P.shapes.get("deck_line_opacity", 0.45))
    low.append(f'<path d="{main_margin_d}" fill="none" stroke="{line_col}" stroke-width="{f(P.sw * 0.7)}" '
               f'stroke-opacity="{line_op}"/>'
               f'<g clip-path="url(#deckmargin)" stroke="{line_col}" stroke-width="{f(P.sw * 0.7)}" '
               f'stroke-opacity="{line_op}">{"".join(lines)}</g>')

    # raised decks (forecastle, bridge deck, poop): the hull outline between x0 and x1, a step up, lighter per deck.
    # Each is laid as its own deck: planks shifted half a plank on alternate levels, butt seams from its own end,
    # and a margin plank round its edge, so the texture never runs on across a break
    for i, rd in enumerate(spec.get("raised_decks", [])):
        lv = rd.get("levels", 1)
        rd_in = rd.get("inset", 0.3)
        rd_d = hull_path(hull, inset=rd_in, x_min=rd["x0"], x_max=rd["x1"])
        margin_d = hull_path(hull, inset=rd_in + margin, x_min=rd["x0"] + margin,
                             x_max=rd["x1"] - (margin if rd["x1"] < hull.L / 2 - 0.5 else 0.0))
        defs += f'<clipPath id="rdclip{i}"><path d="{margin_d}"/></clipPath>'
        rd_lines = plank_lines(rd["x0"], rd["x1"], spacing / 2 if lv % 2 else 0.0, 1.5 * spacing * lv)
        low.append(f'<path d="{rd_d}" fill="{shade(deck_col, 1.07 ** lv)}" {P.stroke()}/>'
                   + P.dazzled(rd_d, sh.get("dazzle_decks", 0.0)) +
                   f'<path d="{margin_d}" fill="none" stroke="{line_col}" stroke-width="{f(P.sw * 0.7)}" '
                   f'stroke-opacity="0.45"/>'
                   f'<g clip-path="url(#rdclip{i})" stroke="{line_col}" stroke-width="{f(P.sw * 0.7)}" '
                   f'stroke-opacity="0.45">{"".join(rd_lines)}</g>')
    for ht in spec.get("hatches", []):
        low.append(P.hatch(ht))
    paint, number = deck_paint(spec, hull, P)
    low.append(paint)

    # bow details: anchor chains, breakwater, bollards
    bx = spec.get("chain_x")
    if bx:
        x_haw = hull.L / 2 - spec.get("hawse_back", 6.0)
        hw_haw = hull.half_width(x_haw) - 0.6
        for side in (-1, 1):
            low.append(f'<line x1="{f(bx)}" y1="{f(side * 1.6)}" x2="{f(x_haw)}" y2="{f(side * hw_haw)}" '
                        f'stroke="{pal["chain"]}" stroke-width="{f(max(0.45, P.sw * 2))}" stroke-dasharray="0.45 0.25"/>')
            low.append(f'<circle cx="{f(bx)}" cy="{f(side * 1.6)}" r="0.9" fill="{pal["fitting"]}" {P.stroke()}/>')
            low.append(f'<path d="M{f(x_haw - 1.2)},{f(side * (hw_haw + 0.2))} l1.6,{f(side * 0.6)} l0.6,{f(-side * 0.9)} Z" '
                        f'fill="{pal["chain"]}"/>')
    bw = spec.get("breakwater_x")
    if bw:
        hwb = hull.half_width(bw) - 1.2
        low.append(f'<path d="M{f(bw - hwb * 0.55)},{f(-hwb)} L{f(bw)},0 L{f(bw - hwb * 0.55)},{f(hwb)}" '
                    f'fill="none" stroke="{shade(deck_col, 0.6)}" stroke-width="{f(max(0.45, P.sw * 2.2))}"/>')
    for bxx in spec.get("bollards", []):
        for side in (-1, 1):
            by = side * (hull.half_width(bxx) - 1.1)
            low.append(f'<circle cx="{f(bxx)}" cy="{f(by)}" r="0.35" fill="{pal["fitting"]}" {P.stroke(0.6)}/>'
                        f'<circle cx="{f(bxx + 0.9)}" cy="{f(by)}" r="0.35" fill="{pal["fitting"]}" {P.stroke(0.6)}/>')

    low.append(number)   # over the chains, so it stays readable

    # --- aircraft carrier flight deck ---------------------------------------
    fd = spec.get("flight_deck")
    if fd:
        for sp in expand(spec.get("sponsons"), hull):
            low.append(P.fitting({**sp, "color": pal["deck"], "r": 0.8}))
        fd = flight_deck_spec(fd)
        for el in fd.get("edge_elevators", []):
            low.append(P.fitting({**el, "color": pal["flight_deck"], "r": 0.4}))
        fd_d = poly(fd["points"])
        defs += f'<clipPath id="fdclip"><path d="{fd_d}"/></clipPath>'
        # shadow of the flight deck on the hull/sea is implied by a dark rim
        low.append(f'<path d="{fd_d}" fill="{pal["flight_deck"]}" {P.stroke(1.3)}/>')
        pk = fd["planks"]
        fl = []
        yy = pk["y0"]
        while yy < pk["y1"]:
            fl.append(f'<line x1="{f(pk["x0"])}" y1="{f(yy)}" x2="{f(pk["x1"])}" y2="{f(yy)}"/>')
            yy += pk["step"]
        low.append(f'<g clip-path="url(#fdclip)" stroke="{shade(pal["flight_deck"], 0.75)}" '
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
        low.append("".join(g))
        defs = defs.replace('<clipPath id="hullclip">', '<clipPath id="hullclip_unused">')
        defs += f'<clipPath id="hullclip"><path d="{hull_d}"/><path d="{fd_d}"/></clipPath>'

    # --- superstructure, fittings, AA, boats --------------------------------
    # a look's clutter kit (clutter.py): roof finishes drawn with each block, the gear itself after all blocks
    kit = clutter.KITS.get(sh.get("clutter") or "")
    items = clutter.plan(spec, Hull(spec), turret_types(spec), sh) if kit else []
    spec["_clutter"] = items
    planks = sh.get("roof_planks", kit["roof_planks"]) if kit else 0
    rails = sh.get("roof_rails", kit["roof_rails"]) if kit else False
    for sb in expand(spec.get("superstructure"), hull):
        layer = sb.get("layer", "base" if sb.get("level", 1) <= 1 else "upper")
        out = low if layer == "base" else high
        out.append(P.block(sb, clip="hullclip"))
        if kit and not sb.get("director"):
            out.append(clutter.roof_finish(sb, P, kit, planks, rails, pal["wood"]))
    if kit:
        for it in items:
            lvl = it["level"]
            if lvl == 0:
                col = deck_col
            else:
                col = pal["levels"][min(lvl, len(pal["levels"])) - 1]
            (low if lvl <= 1 else high).append(clutter.draw(it, P, col))
    else:
        low.append(vents(spec, hull, P))
    for ft in expand(spec.get("fittings"), hull):
        (high if ft.get("layer") == "upper" else low).append(P.fitting(ft))
    for a in expand(spec.get("aa"), hull):
        (high if a.get("layer") == "upper" else low).append(P.aa(a))
    for b in expand(spec.get("boats"), hull):
        (low if b.get("layer") == "base" else high).append(P.boat(b))

    # --- turret barbettes (low pass) ------------------------------------------
    mounts = expand(spec.get("turrets"), hull)
    for m in mounts:
        t = turret_types(spec)[m["type"]]
        if t.get("barbette", True):
            low.append(P.barbette(m["x"], m["y"] if "y" in m else 0, t["r"] * t.get("barbette_k", 0.95)))

    # --- tall stuff ----------------------------------------------------------
    for fn in expand(spec.get("funnels"), hull):
        high.append(P.funnel(fn, clip="hullclip"))
    for m in expand(spec.get("masts"), hull):
        high.append(P.mast(m))
    for c in expand(spec.get("cranes"), hull):
        high.append(P.crane(c))

    return svg_doc("".join(low + high), vb, scale, defs), vb, mounts, hull


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
        body = rrect_polygon(-0.95 * r, -0.82 * r, 0.86 * r, 0.82 * r, 0.32 * r, 0.5 * r)
        return body, ears(-0.72, -0.5, -1.0, -0.7), 0.86 * r, 0.6 * r
    if look == "round":      # flat face, straight cheeks, a rounded rear; a long rangefinder right across
        rear = [(-0.05 - 0.92 * math.sin(math.radians(a)), -0.9 * math.cos(math.radians(a))) for a in range(0, 91, 10)]
        body = mirror([(0.84, -0.5), (0.45, -0.84)] + rear)
        return body, [rrect_polygon(-0.6 * r, -1.08 * r, -0.42 * r, 1.08 * r, 0.09 * r, 0.09 * r, seg=4)], 0.84 * r, 0.5 * r
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
    if look == "hooded":     # an open Victorian barbette ring, the guns under a pear-shaped hood on the turntable
        body = [((-0.05 + 0.93 * math.cos(math.radians(a))) * r, 0.93 * math.sin(math.radians(a)) * r)
                for a in range(0, 360, 10)]
        return body, [], 0.88 * r, 0.0
    if look == "lancia":     # long and narrow: a wedge prow of a face, flat sides, a rounded bustle; rangefinder across
        rear = [(-0.6 - 0.36 * math.sin(math.radians(a)), -0.82 * math.cos(math.radians(a))) for a in range(0, 91, 15)]
        body = mirror([(0.96, 0.0), (0.84, -0.42), (0.5, -0.82)] + rear)
        return body, [rrect_polygon(-0.64 * r, -1.04 * r, -0.46 * r, 1.04 * r, 0.07 * r, 0.07 * r, seg=4)], 0.9 * r, 0.0
    if look == "champignon":  # a French drum under an overhanging mushroom roof, a conical sighting hood on top
        body = [((-0.05 + 0.95 * math.cos(math.radians(a))) * r, 0.95 * math.sin(math.radians(a)) * r)
                for a in range(0, 360, 10)]
        return body, [], 0.9 * r, 0.0
    if look == "quadruple":  # a wide flat face, chamfered front corners, a tapering rear; two halves for four guns
        body = mirror([(0.86, -0.68), (0.7, -0.86), (-0.5, -0.86), (-0.95, -0.45), (-0.95, 0.0)])
        return body, ears(-0.62, -0.46, -1.02, -0.84), 0.86 * r, 0.68 * r
    raise ValueError(f"unknown turret look {look!r}")


def build_turret(t, palette, scale, align=2, shadows=True, look="standard", shapes=None):
    """Turret sprite. Outlines come from geometry.turret_shapes, the same polygons used for hitboxes; a look
    other than "standard" redraws armoured turrets in its own style (look_turret_body). shapes: the look's
    drawing variations (turret_bands: recognition bands painted across armoured turret roofs)."""
    P = Painter(palette, scale, shadows, shapes)
    defs = ""
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
            xe = x_start + barrel_shown(t)
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
        if P.shapes.get("turret_bands"):
            defs = f'<clipPath id="tbody"><path d="{body}"/></clipPath>'
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
        elif look == "hooded":   # the ring's dark well, then the light hood over the guns' breeches
            cx = -0.05 * r
            s.append(f'<circle cx="{f(cx)}" cy="0" r="{f(0.74 * r)}" fill="{shade(body_col, 0.5)}" {P.stroke(0.5)}/>')
            hw = min(0.6 * r, (n - 1) / 2 * sp + 0.35 * r)
            pear = [(0.62 * r, -hw * 0.8), (0.72 * r, 0.0), (0.62 * r, hw * 0.8), (0.2 * r, hw), (-0.45 * r, hw * 0.55),
                    (-0.6 * r, 0.0), (-0.45 * r, -hw * 0.55), (0.2 * r, -hw)]
            hood_col = p.get("turret_hood", shade(body_col, 1.35))
            s.append(f'<path d="{poly(pear)}" fill="{hood_col}" {P.stroke(0.8)}/>'
                     f'<path d="{poly(pear)}" fill="{shade(hood_col, 1.15)}" transform="translate({f(0.04 * r)},0) scale(0.7)"/>'
                     f'<circle cx="{f(-0.2 * r)}" cy="0" r="{f(0.1 * r)}" fill="{shade(hood_col, 0.85)}" {P.stroke(0.5)}/>')
        elif look == "lancia":   # the wedge's crease, two low cupolas forward, a hatch on the bustle
            s.append(f'<path d="M{f(0.96 * r)},0 L{f(-0.4 * r)},0" stroke="{shade(body_col, 0.7)}" '
                     f'stroke-width="{f(0.05 * r)}"/>')
            for yy in (-0.45 * r, 0.45 * r):
                s.append(f'<ellipse cx="{f(0.3 * r)}" cy="{f(yy)}" rx="{f(0.16 * r)}" ry="{f(0.09 * r)}" fill="{hood}" '
                         f'{P.stroke(0.5)}/>')
            s.append(f'<circle cx="{f(-0.8 * r)}" cy="0" r="{f(0.1 * r)}" fill="{hood}" {P.stroke(0.5)}/>')
        elif look == "champignon":  # the mushroom roof's lip, the cone rising to a sighting hood at the centre
            for k, rr in ((0.85, 0.78), (1.15, 0.52), (1.3, 0.3)):
                s.append(f'<circle cx="{f(-0.05 * r)}" cy="0" r="{f(rr * r)}" fill="{shade(body_col, k)}" '
                         f'{P.stroke(0.5)}/>')
            s.append(f'<rect x="{f(-0.05 * r)}" y="{f(-0.11 * r)}" width="{f(0.32 * r)}" height="{f(0.22 * r)}" '
                     f'rx="{f(0.06 * r)}" fill="{shade(body_col, 0.75)}" {P.stroke(0.5)}/>')
            for a in range(0, 360, 30):   # rivets round the lip
                s.append(f'<circle cx="{f((-0.05 + 0.87 * math.cos(math.radians(a))) * r)}" '
                         f'cy="{f(0.87 * math.sin(math.radians(a)) * r)}" r="{f(0.025 * r)}" fill="{shade(body_col, 0.6)}"/>')
        elif look == "quadruple":   # the wall between the two halves, a periscope hood over each gun pair
            if n >= 4:
                s.append(f'<rect x="{f(-0.95 * r)}" y="{f(-0.05 * r)}" width="{f(1.79 * r)}" height="{f(0.1 * r)}" '
                         f'fill="{shade(body_col, 0.65)}" {P.stroke(0.4)}/>')
            for yy in ((-0.48 * r, 0.48 * r) if n >= 2 else (0.0,)):
                s.append(f'<rect x="{f(0.18 * r)}" y="{f(yy - 0.1 * r)}" width="{f(0.32 * r)}" height="{f(0.2 * r)}" '
                         f'rx="{f(0.05 * r)}" fill="{hood}" {P.stroke(0.5)}/>')
            s.append(f'<rect x="{f(-0.85 * r)}" y="{f(-0.2 * r)}" width="{f(0.18 * r)}" height="{f(0.4 * r)}" '
                     f'rx="{f(0.04 * r)}" fill="{hood}" {P.stroke(0.5)}/>')
        for i, key in enumerate(P.shapes.get("turret_bands") or []):   # recognition bands across the roof
            bx = (-0.1 - 0.26 * i) * r
            s.append(f'<g clip-path="url(#tbody)"><rect x="{f(bx - 0.1 * r)}" y="{f(-1.2 * r)}" width="{f(0.2 * r)}" '
                     f'height="{f(2.4 * r)}" fill="{p.get(key, key)}" fill-opacity="0.92"/></g>')

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
    return svg_doc("".join(s), vb, scale, defs)


# ----------------------------------------------------------------------------
# preview compositing
# ----------------------------------------------------------------------------
def clamp_angle(target, rest, trav):
    d = (target - rest + 180) % 360 - 180
    d = max(-trav, min(trav, d))
    return rest + d


def composite(hull_png, turret_pngs, meta, angle_fn):
    canvas = Image.open(hull_png).convert("RGBA")
    for m in sorted(meta["mounts"], key=lambda m: m["z"]):
        timg = Image.open(turret_pngs[m["type"]]).convert("RGBA")
        ang = angle_fn(m)
        rot = timg.rotate(-ang, resample=Image.BICUBIC)
        cx, cy = m["px"]
        canvas.alpha_composite(rot, (round(cx - rot.width / 2), round(cy - rot.height / 2)))
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
                "layer_order": ["hull", "turrets (ascending z)"],
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
        hull_svg, vb, mounts, hull = build_hull(spec, S)
        hull_p = os.path.join(d, "hull.png")
        render(hull_svg, hull_p, os.path.join(d, "hull.svg"))
        W, H = Image.open(hull_p).size
        ox, oy = W / 2, H / 2
        meta = {"id": sid, "name": spec["name"], "class": spec["class"],
                "length_m": hull.L, "beam_m": hull.B, "scale_px_per_m": S,
                "size_px": [W, H], "origin_px": [ox, oy],
                "layers": {"hull": f"ships/{sid}/hull.png"},
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

        rest_img = composite(hull_p, turret_pngs, meta, lambda m: m["rest_deg"])
        bs_img = composite(hull_p, turret_pngs, meta, lambda m: clamp_angle(90, m["rest_deg"], m["traverse_deg"]))
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
