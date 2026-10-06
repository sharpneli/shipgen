"""
Shared geometry: the SAME functions produce the sprite outlines and the hitboxes,
so a shell that hits a polygon here hits the same pixels in the sprite.

All coordinates are metres. Turret shapes are in turret-local space: pivot at (0, 0),
barrels pointing +x. To place a turret shape in ship space, rotate it by the turret's current
angle (clockwise, 0 = ahead) and translate it to the mount position.
"""
from __future__ import annotations

import math


# ---------------------------------------------------------------------------
# primitives
# ---------------------------------------------------------------------------
def rrect_clamped(x0, y0, x1, y1, rf=0.0, rb=0.0):
    """Clamp corner radii exactly the way the SVG renderer does."""
    h = (y1 - y0) / 2
    half_len = (x1 - x0) / 2
    return min(rf, h, half_len), min(rb, h, half_len)


def rrect_polygon(x0, y0, x1, y1, rf=0.0, rb=0.0, seg=8):
    """Rounded rectangle (front corners radius rf at +x, back corners rb at -x) as a polygon."""
    rf, rb = rrect_clamped(x0, y0, x1, y1, rf, rb)
    pts = []

    def arc(cx, cy, r, a0, a1):
        if r <= 1e-9:
            pts.append((cx, cy))
            return
        for i in range(seg + 1):
            a = math.radians(a0 + (a1 - a0) * i / seg)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))

    # clockwise on screen (y down): top edge -> front -> bottom edge -> back
    arc(x1 - rf, y0 + rf, rf, -90, 0)
    arc(x1 - rf, y1 - rf, rf, 0, 90)
    arc(x0 + rb, y1 - rb, rb, 90, 180)
    arc(x0 + rb, y0 + rb, rb, 180, 270)
    return pts


def block_outline(b):
    """A superstructure block's outline: its own polygon ("points") when it has one, else its rounded rectangle."""
    if b.get("points"):
        return [tuple(p) for p in b["points"]]
    y = b.get("y", 0.0)
    return rrect_polygon(b["x0"], y - b["w"] / 2, b["x1"], y + b["w"] / 2, b.get("rf", 0.0), b.get("rb", 0.0))


def polygon_centroid(pts):
    """Area and centroid x of a simple polygon."""
    a = cx = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        c = x0 * y1 - x1 * y0
        a += c
        cx += (x0 + x1) * c
    return abs(a) / 2, (cx / (3 * a) if a else sum(x for x, _ in pts) / len(pts))


def clip_convex(pts, clip):
    """Sutherland-Hodgman: the part of polygon pts inside the convex polygon clip (either winding)."""
    sgn = 1.0 if sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(clip, clip[1:] + clip[:1])) > 0 else -1.0
    out = list(pts)
    for (ax, ay), (bx, by) in zip(clip, clip[1:] + clip[:1]):
        if not out:
            break
        def side(p):
            return sgn * ((bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax))
        src, out = out, []
        for p, q in zip(src, src[1:] + src[:1]):
            sp, sq = side(p), side(q)
            if sp >= 0:
                out.append(p)
            if (sp >= 0) != (sq >= 0):
                t = sp / (sp - sq)
                out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return simplify_polygon(out)


def simplify_polygon(pts, tol=1e-3):
    """Drop repeated and collinear vertices."""
    out = []
    for p in pts:
        if not out or abs(p[0] - out[-1][0]) > tol or abs(p[1] - out[-1][1]) > tol:
            out.append(p)
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) <= tol and abs(out[0][1] - out[-1][1]) <= tol:
        out.pop()
    changed = True
    while changed and len(out) > 3:
        changed = False
        for i in range(len(out)):
            a, b, c = out[i - 1], out[i], out[(i + 1) % len(out)]
            if abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) <= tol * max(
                    1.0, math.hypot(c[0] - a[0], c[1] - a[1])):
                out.pop(i)
                changed = True
                break
    return out


def director_parts(x, y, l, w, rangefinder_m):
    """A fire-control director facing ahead, l long and w across (firecontrol.size: the rangefinder sets w): its
    outline (the hitbox, a simple polygon) and the parts it is drawn from, whose union is that outline. With a
    rangefinder: a hood with a cut front, the tube across it, a little aft of its middle, and an end hood at each
    tip, standing out past the hood's sides. A rangefinder no wider than the hood stays inside it. Without one
    (a gyro sight, Mk 51 style): a round tub. Returns dict(outline, hood, tube, ends); tube is None and ends empty
    when nothing stands out."""
    if not rangefinder_m:
        hood = circle_polygon(x, y, min(l, w) / 2, 16)
        return dict(outline=hood, hood=hood, tube=None, ends=[])
    x0, x1 = x - l / 2, x + l / 2
    hh = min(w, l * 1.15) / 2                           # the hood, a little wider than long
    cf, cb = 0.35 * hh, 0.1 * hh                        # its front and back corners cut
    rx, tw = x - 0.12 * l, max(0.4, 0.14 * l)           # the tube: where and how thick (fore and aft)
    el, ew = min(0.9, 0.3 * l), 1.7 * tw                # the end hoods: fore and aft, across
    ye = w / 2 - ew                                     # the end hoods' inner face
    if ye <= hh:                                        # nothing stands out: the hood is the director
        hh = w / 2
        hood = [(x1, y - hh + cf), (x1, y + hh - cf), (x1 - cf, y + hh), (x0 + cb, y + hh), (x0, y + hh - cb),
                (x0, y - hh + cb), (x0 + cb, y - hh), (x1 - cf, y - hh)]
        return dict(outline=hood, hood=hood, tube=None, ends=[])
    half = [(x1, hh - cf), (x1 - cf, hh), (rx + tw / 2, hh), (rx + tw / 2, ye), (rx + el / 2, ye),
            (rx + el / 2, w / 2), (rx - el / 2, w / 2), (rx - el / 2, ye), (rx - tw / 2, ye), (rx - tw / 2, hh),
            (x0 + cb, hh), (x0, hh - cb)]
    outline = [(px, y + py) for px, py in half] + [(px, y - py) for px, py in reversed(half)]
    hood = [(x1, y - hh + cf), (x1, y + hh - cf), (x1 - cf, y + hh), (x0 + cb, y + hh), (x0, y + hh - cb),
            (x0, y - hh + cb), (x0 + cb, y - hh), (x1 - cf, y - hh)]
    tube = [(rx - tw / 2, y - ye), (rx + tw / 2, y - ye), (rx + tw / 2, y + ye), (rx - tw / 2, y + ye)]
    ends = [[(rx - el / 2, y + s * ye), (rx + el / 2, y + s * ye), (rx + el / 2, y + s * w / 2),
             (rx - el / 2, y + s * w / 2)] for s in (1, -1)]
    return dict(outline=outline, hood=hood, tube=tube, ends=ends)


def circle_polygon(cx, cy, r, seg=32):
    return [(cx + r * math.cos(2 * math.pi * i / seg), cy + r * math.sin(2 * math.pi * i / seg)) for i in range(seg)]


def rotate_translate(pts, deg, tx, ty):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [(tx + x * c - y * s, ty + x * s + y * c) for x, y in pts]


def point_in_polygon(x, y, pts):
    inside = False
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            if x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
    return inside


# AA mounts: (tub radius, barrels, barrel length, barrel width, barrel spacing) in metres.
# The tub radius is also the AA hitbox radius.
AA_CFG = {"quad40": (2.0, 4, 2.8, 0.17, 0.42),
          "twin40": (1.5, 2, 2.6, 0.17, 0.5),
          "single20": (0.75, 1, 1.7, 0.12, 0.0)}


# ---------------------------------------------------------------------------
# hull profile
# ---------------------------------------------------------------------------
class Hull:
    def __init__(self, spec):
        self.L = spec["length"]
        self.B = spec["beam"]
        self.bow = {"taper": 0.33, "power": 1.6, "shape": "pointed", **spec.get("bow", {})}
        self.stern = {"taper": 0.18, "power": 2.0, "shape": "round", "transom": 0.45,
                      **spec.get("stern", {})}

    @staticmethod
    def _end(t, power, shape):
        # t: 0 at the start of the taper, 1 at the very tip
        base = max(0.0, 1.0 - t ** power)
        return math.sqrt(base) if shape == "round" else base

    @staticmethod
    def end_fill(power, shape):
        """The mean of _end over a taper (0..1): the share of the taper's L x B box its end fills."""
        if shape == "round":   # integral of sqrt(1 - t^p): a Beta function
            return math.gamma(1 + 1 / power) * math.gamma(1.5) / math.gamma(1 / power + 1.5)
        return power / (power + 1)

    def half_width(self, x: float) -> float:
        u = (x + self.L / 2) / self.L
        b, s = self.bow, self.stern
        if u >= 1 - b["taper"]:
            t = min(1.0, (u - (1 - b["taper"])) / b["taper"])
            w = self._end(t, b["power"], b["shape"])
            if b.get("flare"):   # a flared shoulder: fuller through the middle of the taper, the same tip
                w = min(1.0, w + b["flare"] * math.sin(math.pi * t) * (1 - t))
        elif u <= s["taper"]:
            t = min(1.0, max(0.0, 1 - u / s["taper"]))
            w = s["transom"] + (1 - s["transom"]) * self._end(t, s["power"], s["shape"])
        else:
            w = 1.0
        return self.B / 2 * w

    def points(self, inset=0.0, max_hw=None, x_min=None, x_max=None, n=260):
        """Closed outline as a point list (port side stern->bow, then starboard bow->stern)."""
        lo = -self.L / 2 if x_min is None else x_min
        hi = self.L / 2 if x_max is None else x_max
        xs = [lo + (hi - lo) * (1 - math.cos(math.pi * i / n)) / 2 for i in range(n + 1)]
        pts = []
        for x in xs:
            w = self.half_width(x) - inset
            if max_hw is not None:
                w = min(w, max_hw)
            if w > 0.01:
                pts.append((x, w))
        return [(x, -w) for x, w in pts] + [(x, w) for x, w in reversed(pts)]


def midship_coefficient(cb):
    """The midship section's fullness for a block coefficient (Kerlen's fit), kept to a sane range."""
    return min(0.995, max(0.6, 1.006 - 0.0056 * cb ** -3.56))


class HullForm:
    """The hull's cross-sections: its half-breadth at x and height z (metres above the keel). The planform (Hull)
    is the main deck, deliberately fuller than the waterplane (it carries the flare). Here:
      waterplane  the deck outline fined toward the ends, B / 2 x w(x) ** p with w the deck's share of the beam,
                  p in 1..P_MAX solved so it fills cwp of its L x B box (the midbody keeps the full beam). A
                  straight-sided deck with a wide transom (destroyers, planing craft) is far fuller than
                  navarch.cwp, a fit for cruiser sterns; fining it that far would leave only the midbody, so p
                  stops at P_MAX and that waterplane comes out fuller than cwp (the volume still matches)
      below it    each section narrows to the keel, y = hw_wl(x) (1 - (1 - z / T) ** m): full amidships (the
                  midship coefficient for cb) and sharp at the ends, its fullness c(x) = cm u(x) ** a (u: the
                  waterline's share of the beam, m = c / (1 - c)) with a in 0..A_MAX solved so the underwater body
                  holds cb L B T; a long full-width midbody that still holds too much gets a leaner cm (a planing
                  craft's vee)
      above it    the side flares straight up from the waterline to the deck edge; raised decks keep the deck's
                  outline
    Standard library only: the design side builds it for the hitboxes, the render side reads its table."""
    N = 400
    P_MAX = 2.0
    A_MAX = 4.0
    C_MIN = 0.35        # the finest section, a little hollower than a vee (c 0.5)

    @staticmethod
    def _solve(f, lo, hi, target):
        """x in lo..hi where the decreasing f(x) meets target (an end when it doesn't)."""
        if f(lo) <= target:
            return lo
        if f(hi) >= target:
            return hi
        for _ in range(50):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if f(mid) > target else (lo, mid)
        return (lo + hi) / 2

    def __init__(self, hull, cb, cwp, T, D):
        self.hull, self.cb, self.T, self.D = hull, cb, T, D
        L = hull.L
        ws = [min(1.0, hull.half_width(-L / 2 + L * (k + 0.5) / self.N) / (hull.B / 2)) for k in range(self.N)]
        self.p = self._solve(lambda p: sum(w ** p for w in ws) / len(ws), 1.0, self.P_MAX, cwp)
        us = [w ** self.p for w in ws]
        self.cwp = sum(us) / len(us)
        fill = lambda cm, a: sum(u * max(self.C_MIN, cm * u ** a) for u in us) / len(us)   # underwater, of LBT
        self.cm = midship_coefficient(cb)
        self.a = self._solve(lambda a: fill(self.cm, a), 0.0, self.A_MAX, cb)
        # the ends alone can't make it: a leaner (or fuller) midship section takes up the rest
        if abs(fill(self.cm, self.a) - cb) > 1e-4:      # fill rises with cm: solve on 1 - cm
            self.cm = 1.0 - self._solve(lambda k: fill(1.0 - k, self.a), 0.005, 1.0 - self.C_MIN, cb)

    def waterline(self, x):
        """The waterplane's half-breadth at x."""
        w = min(1.0, self.hull.half_width(x) / (self.hull.B / 2))
        return self.hull.B / 2 * w ** self.p

    def fullness(self, x):
        """The section's fullness below the waterline at x: its area over its box's (2 hw_wl x T)."""
        u = self.waterline(x) / (self.hull.B / 2)
        return max(self.C_MIN, self.cm * u ** self.a)

    def half_width(self, x, z):
        """The half-breadth at x and z metres above the keel."""
        deck = self.hull.half_width(x)
        if z >= self.D:
            return deck
        wl = self.waterline(x)
        if z >= self.T:
            return wl + (deck - wl) * (z - self.T) / (self.D - self.T) if self.D > self.T else deck
        if z <= 0:
            return 0.0
        c = self.fullness(x)
        m = c / (1.0 - c)
        return min(deck, wl * (1.0 - (1.0 - z / self.T) ** m))

    HEIGHTS = (0.0, 0.03, 0.08, 0.15, 0.25, 0.4, 0.55, 0.7, 0.85, 1.0)     # sampled heights, fractions of T

    def table(self, stations=48):
        """Sampled sections for the hitboxes: [dict(x, z, y)], z on the keel scale, from the keel up to the
        main deck (and the waterline among them)."""
        L = self.hull.L
        zs = sorted({min(self.T, self.D) * f for f in self.HEIGHTS} | {self.D})
        out = []
        for k in range(stations + 1):
            x = -L / 2 + L * (1 - math.cos(math.pi * k / stations)) / 2
            out.append(dict(x=x, z=zs, y=[self.half_width(x, z) for z in zs]))
        return out


def table_half_width(table, x, z):
    """A sampled hull form's (HullForm.table, as exported) half-breadth at x and z: bilinear between stations
    and heights; above the top height, the top's."""
    xs = [s["x"] for s in table]
    if x <= xs[0] or x >= xs[-1]:
        return 0.0
    i = max(0, min(len(xs) - 2, next(k for k in range(len(xs) - 1) if xs[k + 1] >= x)))

    def at(s):
        zs, ys = s["z"], s["y"]
        if z >= zs[-1]:
            return ys[-1]
        if z <= zs[0]:
            return ys[0]
        j = next(k for k in range(len(zs) - 1) if zs[k + 1] >= z)
        f = (z - zs[j]) / (zs[j + 1] - zs[j]) if zs[j + 1] > zs[j] else 0.0
        return ys[j] + (ys[j + 1] - ys[j]) * f
    a, b = table[i], table[i + 1]
    f = (x - a["x"]) / (b["x"] - a["x"]) if b["x"] > a["x"] else 0.0
    return at(a) + (at(b) - at(a)) * f


# ---------------------------------------------------------------------------
# turret types generated from gun parameters
# ---------------------------------------------------------------------------
def make_turret_type(calibre_mm: float, calibre_length: float, barrels: int, kind: str = "auto") -> tuple[str, dict]:
    """Size a turret from its guns. Returns (type_id, type_dict) usable by the renderer."""
    cal = calibre_mm / 1000.0
    spacing = max(cal * 6.5, 0.9 + cal * 3.0) if barrels > 1 else 0.0
    width = (barrels - 1) * spacing + cal * 15.0 + 1.5
    r = width / 1.7
    if kind == "auto":   # light guns (under 76 mm) are open mounts
        kind = "bb" if calibre_mm >= 150 else "dp" if calibre_mm >= 76 else "open"
    tid = f"t{barrels}x{round(calibre_mm)}L{round(calibre_length)}{'' if kind in ('bb', 'dp') else '_' + kind}"
    # a casemate gun in the hull side: r is the casemate's half-width (spacing, weights), as for a turret of the same
    # guns; only a round port shield and the barrels show outboard of the hull (turret_shapes)
    return tid, dict(desc=f"{barrels} x {calibre_mm:g}mm/{calibre_length:g}", shape=kind, r=round(r, 3),
                     barrels=barrels, barrel_len=round(cal * calibre_length, 3),
                     barrel_w=round(max(cal * 2.3, 0.18), 3), spacing=round(spacing, 3),
                     calibre_mm=calibre_mm, calibre_length=calibre_length,
                     **({"centered": True, "barbette": False} if kind == "torp" else {}),
                     **({"barbette": False} if kind in ("open", "casemate") else {}))


def make_torpedo_type(tubes: int, fixed: bool = False) -> tuple[str, dict]:
    if fixed:   # fixed deck tubes (MTBs): aimed by steering the boat; the body is the cradle
        return f"tube{tubes}x533", dict(desc=f"{tubes} x 533mm fixed torpedo tube{'s' if tubes > 1 else ''}",
                                        shape="tube", r=0.55, barrels=tubes, barrel_len=7.2, barrel_w=0.55,
                                        spacing=0.75, centered=True, barbette=False, fixed_tube=True)
    return f"torp{tubes}x533", dict(desc=f"{tubes} x 533mm torpedo tubes", shape="torp", r=1.9,
                                     barrels=tubes, barrel_len=7.6, barrel_w=0.55, spacing=0.66,
                                     centered=True, barbette=False)


BARREL_ROOT = {"bb": 0.5, "dp": 0.3, "open": -0.3, "casemate": 0.0}
CASEMATE_SHIELD = 0.55  # a casemate gun's round port shield, in units of its casemate half-width r
# the fraction of a gun's barrel_len that shows (and is hit) outside its turret or casemate; the rest is taken as
# inside it and simply not modelled. Ballistics still use the full length in calibres.
BARREL_SHOWN = {"bb": 0.8, "dp": 0.8, "casemate": 0.5}


def barrel_shown(t: dict) -> float:
    """The drawn and hitbox length of a gun's barrels, from their root (BARREL_SHOWN)."""
    return t["barrel_len"] * BARREL_SHOWN.get(t.get("shape", "bb"), 1.0)


def turret_shapes(t: dict) -> dict:
    """Polygons (turret-local) for the turret body, extra parts and each barrel."""
    r = t["r"]
    n, bl, bw, sp = t["barrels"], t["barrel_len"], t["barrel_w"], t["spacing"]
    shape = t.get("shape", "bb")
    out = {"body": [], "parts": [], "barrels": []}

    def barrel_polys(x0):
        res = []
        for i in range(n):
            y = (i - (n - 1) / 2) * sp
            xe = x0 + barrel_shown(t)
            res.append([(x0, y - bw * 0.62), (xe, y - bw / 2), (xe, y + bw / 2), (x0, y + bw * 0.62)])
        return res

    if shape == "bb":
        R = 1.1 * r
        half = 0.85 * r
        cx = -0.55 * r + math.sqrt(R * R - half * half)
        a0 = math.degrees(math.atan2(half, -0.55 * r - cx))
        pts = [(0.85 * r, -0.5 * r), (0.85 * r, 0.5 * r), (0.4 * r, 0.85 * r)]
        seg = 16
        for i in range(seg + 1):
            a = math.radians(a0 + (360 - 2 * a0) * i / seg)
            pts.append((cx + R * math.cos(a), R * math.sin(a)))
        pts.append((0.4 * r, -0.85 * r))
        out["body"] = pts
        out["parts"] = [[(-0.66 * r, -1.02 * r), (-0.48 * r, -1.02 * r), (-0.48 * r, 1.02 * r), (-0.66 * r, 1.02 * r)]]
        out["barrels"] = barrel_polys(BARREL_ROOT["bb"] * r)
    elif shape == "dp":
        out["body"] = rrect_polygon(-0.95 * r, -0.72 * r, 0.75 * r, 0.72 * r, 0.42 * r, 0.6 * r)
        out["barrels"] = barrel_polys(BARREL_ROOT["dp"] * r)
    elif shape == "open":
        out["body"] = circle_polygon(0, 0, r)
        out["barrels"] = barrel_polys(BARREL_ROOT["open"] * r)
    elif shape == "casemate":   # pivot at the hull side: the shield bulges out of it, the barrels point outboard
        out["body"] = circle_polygon(0, 0, CASEMATE_SHIELD * r)
        out["barrels"] = barrel_polys(BARREL_ROOT["casemate"] * r)
    elif shape == "torp":
        out["body"] = circle_polygon(0, 0, r)
        for i in range(n):
            y = (i - (n - 1) / 2) * sp
            out["barrels"].append(rrect_polygon(-bl / 2, y - bw / 2, bl / 2, y + bw / 2, bw / 2, bw / 2, seg=4))
        ty = (n - 1) / 2 * sp + bw / 2
        out["parts"] = [
            [(-bl / 2 - 0.2, -ty - 0.2), (-bl / 2 + 0.7, -ty - 0.2), (-bl / 2 + 0.7, ty + 0.2), (-bl / 2 - 0.2, ty + 0.2)],
            rrect_polygon(-r * 0.4, -ty - 0.9, r * 0.4, -ty + 0.1, 0.25, 0.25, seg=3),  # trainer's cab
        ]
    elif shape == "tube":
        w = (n - 1) * sp + bw
        out["body"] = rrect_polygon(-bl / 2 + 0.6, -w / 2 - 0.15, bl / 2 - 1.2, w / 2 + 0.15, 0.1, 0.1, seg=2)
        for i in range(n):
            y = (i - (n - 1) / 2) * sp
            out["barrels"].append(rrect_polygon(-bl / 2, y - bw / 2, bl / 2, y + bw / 2, bw / 2, 0.05, seg=4))
    else:
        raise ValueError(shape)
    return out


def turret_reach(t: dict) -> float:
    """Max distance of any part of the turret from its pivot (for sprite canvas sizing)."""
    sh = turret_shapes(t)
    pts = sh["body"] + [p for poly in sh["parts"] + sh["barrels"] for p in poly]
    return max(math.hypot(x, y) for x, y in pts)


def turret_height(t: dict) -> float:
    """Roof height of a turret above its base, metres."""
    return {"bb": 0.42, "dp": 0.55, "open": 0.9, "torp": 0.5, "tube": 1.6, "casemate": 0.42}[t.get("shape", "bb")] * t["r"]


DECK_PITCH = 2.6   # m between decks: the hull's deck stack below the main deck, raised stretches of hull above it
                  # and superstructure levels share it, so a raised deck one pitch up stands where level 1 would


def superfire_step(th: float) -> float:
    """How much higher each superfiring tier stands than the one it fires over, metres, for a turret th tall.
    About one deck, a little more for big turrets: Iowa's 16in turret II stands 2.6 m over turret I, and
    Atlanta's 5in twins step up a deck (about 2.4 m) each. The guns (at 0.55 th) clear the roof below by 1.1-1.6 m."""
    return 2.0 + 0.2 * th


def polygon_area(pts):
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))) / 2


def polygon_y_span(pts, x):
    """(min y, max y) where the vertical line at x crosses the polygon, or None if it misses."""
    ys = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        if (x0 <= x <= x1 or x1 <= x <= x0) and x0 != x1:
            ys.append(y0 + (x - x0) * (y1 - y0) / (x1 - x0))
    return (min(ys), max(ys)) if ys else None


def sector_polygon(cx, cy, R, a0, a1, step=10.0):
    """Pie slice of radius R from bearing a0 to a1 (degrees clockwise from +x; a1 > a0, ship-local)."""
    n = max(2, int(math.ceil((a1 - a0) / step)) + 1)
    pts = [(cx, cy)] if a1 - a0 < 360 else []
    for i in range(n):
        a = math.radians(a0 + (a1 - a0) * i / (n - 1))
        pts.append((cx + R * math.cos(a), cy + R * math.sin(a)))
    return pts


def _segments_cross(p, q, r, s):
    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    d1, d2, d3, d4 = orient(r, s, p), orient(r, s, q), orient(p, q, r), orient(p, q, s)
    return (d1 > 0) != (d2 > 0) and (d3 > 0) != (d4 > 0)


def polygons_intersect(a, b):
    """True if two simple polygons overlap (edges cross, or one lies inside the other)."""
    xa, ya = [x for x, _ in a], [y for _, y in a]
    xb, yb = [x for x, _ in b], [y for _, y in b]
    x0, x1 = max(min(xa), min(xb)), min(max(xa), max(xb))
    y0, y1 = max(min(ya), min(yb)), min(max(ya), max(yb))
    if x1 < x0 or y1 < y0:
        return False   # bounding boxes apart: cannot touch
    # edges can only cross inside both bounding boxes: test just the edges reaching into their overlap (a long hull
    # outline against a small rect has a handful)
    def near(p):
        out, s = [], p[-1]
        for e in p:
            if (s[0] <= x1 or e[0] <= x1) and (s[0] >= x0 or e[0] >= x0) and \
                    (s[1] <= y1 or e[1] <= y1) and (s[1] >= y0 or e[1] >= y0):
                out.append((s, e))
            s = e
        return out
    eb = near(b)
    if eb:
        for p, q in near(a):
            for r, s in eb:
                if _segments_cross(p, q, r, s):
                    return True
    return point_in_polygon(*a[0], b) or point_in_polygon(*b[0], a)


# ---------------------------------------------------------------------------
# firing arcs: [start, end] clockwise from ahead, end may exceed 360
# ---------------------------------------------------------------------------
def _wrap180(a):
    return (a + 180.0) % 360.0 - 180.0


def angle_allowed(arcs, a):
    a %= 360.0
    return any(lo <= a <= hi or lo <= a + 360.0 <= hi for lo, hi in arcs)


def nearest_allowed(arcs, a):
    if not arcs or angle_allowed(arcs, a):
        return a
    best, bd = a, 1e9
    for lo, hi in arcs:
        for e in (lo, hi):
            d = abs(_wrap180(e - a))
            if d < bd:
                best, bd = e, d
    return best
