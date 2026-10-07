"""
Shared geometry: the SAME functions produce the sprite outlines and the hitboxes,
so a shell that hits a polygon here hits the same pixels in the sprite.

All coordinates are metres. Turret shapes are in turret-local space: pivot at (0, 0),
barrels pointing +x. To place a turret shape in ship space, rotate it by the turret's current
angle (clockwise, 0 = ahead) and translate it to the mount position.
"""
from __future__ import annotations

import functools
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


def superellipse_fill(p, q):
    """The share of its box that a quadrant (y / b) ** p + s ** q = 1 fills."""
    return math.gamma(1 + 1 / p) * math.gamma(1 + 1 / q) / math.gamma(1 + 1 / p + 1 / q)


@functools.lru_cache(maxsize=8192)
def section_exponents(c, k):
    """(p, q) of the superellipse section of fullness c and character k (-1 V .. 1 U): p sets the bottom (over 1
    flat at the keel, under 1 a hollow fin), q the side (over 1 upright at the waterline); k pulls them apart, U
    upright sides over a round bottom, V sloping sides over a flat floor. q stays at least 1: under it the side
    turns flat at the waterline and the hull loses half its breadth just under it."""
    e = math.exp(k * HullForm.KAPPA)
    lo, hi = 0.1, 500.0
    for _ in range(60):
        n = math.sqrt(lo * hi)
        lo, hi = (lo, n) if superellipse_fill(n / e, max(1.0, n * e)) > c else (n, hi)
    n = math.sqrt(lo * hi)
    return n / e, max(1.0, n * e)


class HullForm:
    """The hull's cross-sections: its half-breadth at x and height z (metres above the keel). The planform (Hull)
    is the main deck, deliberately fuller than the waterplane (it carries the flare). Here:
      keel        the keel's height over the baseline, keel(x). Forward a rounded forefoot over FOREFOOT of the
                  length, cut away more on fast ships. Departure: real forefeet run 3-6% of the length; at that a
                  low waterline ran on to within a few metres of the stem and its sections there were thin blades,
                  so the forefoot is cut away further and the bottom tiers end where the hull still has room.
                  Aft by the stern gear (propulsion.gear): one screw keeps the keel to the sternpost at the
                  rudder, with the counter above the water abaft it; several screws get a cut-up, the bottom
                  rising so it clears the propellers' tips and running on up, smoothly to the stern, to
                  TRANSOM_DEEP x T x the stern's share of the beam under the waterline (a long flat counter just
                  under the water had drawn a sliver of hull in every slice above it). A planing hull keeps a
                  straight keel to its transom and rises in a long rocker forward
      area        the sectional area curve, A(x) over the midship section's (cm B T): a parallel midbody of
                  PMB_K (Cp - PMB_CP) L (next to none on a destroyer's Cp 0.53, an eighth of the length on a
                  battleship's 0.61, two fifths on a tanker's 0.77) round the centre of buoyancy, then
                  e + (1 - e)(1 - r ** 2) ** (1 / n) out to each end (r 0 at the shoulder, 1 at the end; e the
                  immersed transom's area, nil at the bow and over a counter): rounded at the shoulder however
                  fine, where 1 - r ** n came to a point and drew a diamond of flat bottom. n is solved so the
                  underwater body holds cb L B T, and the split between entrance and run (n e ** +-d) so its
                  centre sits at the ship's lcb (navarch: the layout trims the weights to it)
      waterplane  each station meets its area with its waterline and its section's fullness together: of the
                  share rho of the midship's breadth x fullness it needs, the waterline takes rho ** lambda and
                  the section the rest (lambda solved so the waterplane fills navarch.cwp, more on the
                  waterline under U ends, less under V), the waterline never past the deck edge nor narrower
                  than the station nearer the end (a shallow run over a cut-up wants it wider toward the
                  transom: the stations ahead are filled out to it, then smoothed), the fullness
                  from C_MIN up to cm at the shoulders, C_END at the ends (a section fuller than amidships turns
                  into a box), falling off as r ** C_END_POW: flat at the shoulder, where a linear fall had put a
                  corner in the flat of bottom and run it out to the stem in straight sides, a needle nose.
                  Departure: lambda stays in LAM_MIN..LAM_MAX so the section always takes part of the fining.
                  navarch.cwp (0.18 + 0.86 cb) is lean for warships: reaching it took lambda ~1, a fine
                  waterline over box-full sections, where a battleship's lines give ~0.6. So warships' waterplanes
                  come out ~0.70-0.73 (Schneekluth & Bertram's regressions give about that), fuller than cwp
      sections    below the waterline each section is a superellipse (y / b) ** p + s ** q = 1 over its own depth
                  (s: the depth below the waterline over the keel's): flat at the keel wherever it is fuller than
                  a vee, and hollow under c 0.5 at the fine ends. Its character (section_exponents) grows from
                  nil amidships: forward a U near Fn 0.225 and a V either side (Schneekluth & Bertram's tests: U
                  best around Fn 0.23, V under 0.18 and over 0.25), aft a U on a single screw (an even wake into
                  it) and a flat-floored V run on several; it fades out as the section thins toward a vee.
                  Every section stands on a flat keel of KEEL_K B (half-breadth; the keel plate and the flat of
                  the floor beside it), the curve above re-solved so the section keeps its area, and never more
                  than KEEL_SHARE of that area: the low waterlines end blunt where the forefoot cuts them off,
                  where a curve from a point at the keel had drawn a needle. Departure: real keel plates are
                  narrower (1.5-2.5 m on a battleship); this is wider for a roomier, sturdier-looking bottom.
                  Planing hulls take a hard chine instead: a straight deadrise from the keel to a chine, an
                  upright side above it
      above it    the side flares straight up from the waterline to the deck edge; raised decks keep the deck's
                  outline
    Standard library only: the design side builds it for the hitboxes, the render side reads its table."""
    N = 400
    C_MIN = 0.35        # the finest section, a little hollower than a vee (c 0.5)
    C_MAX = 0.995
    KAPPA = 1.2         # how far a full U or V character pulls the section's exponents apart
    FOREFOOT = 0.10     # the forefoot's run, x L, up to Fn FOREFOOT_FN; then FOREFOOT_K more per unit Fn
    FOREFOOT_FN = 0.2
    FOREFOOT_K = 0.25
    FOREFOOT_MAX = 0.16
    ROCKER = 0.45       # a planing keel's rocker, x L from the stem
    PLANING_CM = 0.6    # a planing midship section's fullness to start from (a chine at 0.8 of the draught)
    CUT_CLEAR = 0.1     # the cut-up's bottom over the propellers' tips, x their diameter
    CUT_RUN = 7.0       # the cut-up's run, x its rise (where it is steepest it climbs at 2 / CUT_RUN)
    TRANSOM_DEEP = 0.2  # the stern's underside below the waterline, x T x its share of the beam (a wide transom
                        # stays immersed; a narrow cruiser stern fades out at the waterline)
    FORE_V, FORE_U = -0.6, 0.8      # forward character: V away from Fn FORE_FN, U at it
    FORE_FN, FORE_FN_W = 0.225, 0.04
    AFT_K = 0.8         # aft character: U with one screw, V (flat floored) with several
    CHAR_RUN = 0.3      # the character grows from nil amidships to full this far from it, x L
    PMB_K, PMB_CP, PMB_MAX = 1.8, 0.54, 0.5     # the parallel midbody, x L, from the prismatic coefficient
    LAMBDA, LAMBDA_K = 0.5, 0.2     # the waterline's share of an end's fining, and how far character moves it
    LAM_MIN, LAM_MAX = 0.35, 0.75   # the share's range: the section always takes part of the fining
    ROUNDS = 3          # area curve and waterline share, solved in turn
    TRANSOM_C = 0.75    # an immersed transom's fullness
    SMOOTH = 6          # the end waterlines' smoothing, stations either side (of N)
    C_END = 0.75        # the fullest a section gets at the ends: from cm at the shoulders down to this
    C_END_POW = 2.0     # how that cap falls off toward the ends (of r): 1 had cornered the bottom at the shoulders
    KEEL_K = 0.06       # the flat keel's half-breadth, x B
    KEEL_SHARE = 0.5    # the most of a section's area the flat keel may take (fine ends keep a curve)

    @staticmethod
    def _solve(f, lo, hi, target):
        """x in lo..hi where the increasing f(x) meets target (an end when it doesn't)."""
        if f(lo) >= target:
            return lo
        if f(hi) <= target:
            return hi
        for _ in range(40):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if f(mid) < target else (lo, mid)
        return (lo + hi) / 2

    def __init__(self, hull, cb, cwp, T, D, fn=0.0, gear=None, lcb=0.0):
        """cwp: the waterplane coefficient to aim for (navarch.cwp); fn: the Froude number at the design speed;
        gear: propulsion.gear (None: a flat keel aft); lcb: the centre of buoyancy's x (navarch.Result.lcb)."""
        self.hull, self.cb, self.T, self.D, self.fn, self.cwp_target = hull, cb, T, D, fn, cwp
        L, B = hull.L, hull.B
        gear = gear or {}
        self.planing = bool(gear.get("planing"))
        self.screws = gear.get("screws", 0)
        self.k_fore = self.FORE_V + (self.FORE_U - self.FORE_V) * math.exp(-((fn - self.FORE_FN) / self.FORE_FN_W) ** 2)
        self.k_aft = self.AFT_K if self.screws == 1 else -self.AFT_K if self.screws else 0.0
        self.forefoot = L * (self.ROCKER if self.planing else
                             min(self.FOREFOOT_MAX, self.FOREFOOT + self.FOREFOOT_K * max(0.0, fn - self.FOREFOOT_FN)))
        self.post = self.cut = None
        props = gear.get("propellers") or []
        if not self.planing and self.screws == 1 and gear.get("rudders"):
            self.post = min(r["x0"] for r in gear["rudders"])     # the sternpost: the rudder's heel, aft
        elif not self.planing and props:
            rise = min(0.95 * T, max(p["z"] + p["diameter"] * (0.5 + self.CUT_CLEAR) for p in props))
            x_c = max(p["x"] + 0.5 * p["diameter"] for p in props)
            end = max(rise, T * (1.0 - self.TRANSOM_DEEP * min(1.0, hull.half_width(-L / 2) / (B / 2))))
            self.cut = (x_c, x_c + self.CUT_RUN * rise, rise, end)

        self.xs = [-L / 2 + L * (k + 0.5) / self.N for k in range(self.N)]
        self._ws = [min(1.0, hull.half_width(x) / (B / 2)) for x in self.xs]
        self._ds = [max(0.0, T - self.keel(x)) / T for x in self.xs]
        self.cm = self.PLANING_CM if self.planing else midship_coefficient(cb)
        self.lcb = max(-0.2 * L, min(0.2 * L, lcb))
        lo_end = min(0.99, self._ws[0] * self._ds[0] * self.TRANSOM_C / self.cm)    # the transom's share
        self._ends = (lo_end, 0.0)
        self.lam = self.LAMBDA
        for _ in range(self.ROUNDS):            # the area curve, then the waterline's share for the waterplane
            self._fit()
            self.lam = self._solve(lambda lam: -self._waterplane(lam), self.LAM_MIN, self.LAM_MAX, -cwp)
        self._fit()
        if abs(self.volume - cb) > 1e-4:        # the curve alone can't: a leaner (or fuller) midship section
            self.cm = self._solve(lambda cm: self._fit(cm) or self.volume, self.C_MIN, self.C_MAX, cb)
            self._fit(self.cm)
        self.cwp = self._waterplane(self.lam)

    def _waterplane(self, lam):
        """The waterplane coefficient with the waterline's share lam and the area curve as fitted."""
        us = self._stations(self.n, self.split, lam)[0]
        return sum(u for u, d in zip(us, self._ds) if d > 0) / self.N

    def _fit(self, cm=None):
        """Solve the area curve for the current cm: n for the volume inside a bisection on the entrance/run split
        for the lcb. Sets the stations' waterlines (_us) and fullness (_cs), the volume and lcb it reached."""
        cm = self.cm if cm is None else cm
        L = self.hull.L
        self.pmb = max(0.0, min(self.PMB_MAX, self.PMB_K * (self.cb / cm - self.PMB_CP))) * L
        xa, xf = self.lcb - self.pmb / 2, self.lcb + self.pmb / 2
        xa, xf = max(xa, -0.45 * L), min(xf, 0.45 * L)
        self._mid = (xa, xf)

        stations = lambda n, d: self._stations(n, d, self.lam, cm, xa, xf)

        def volume(n, d):
            return sum(stations(n, d)[2]) / self.N

        def centre(d):
            n = self._solve(lambda n: volume(n, d), 0.3, 20.0, self.cb)
            a = stations(n, d)[2]
            tot = sum(a)
            return (sum(x * v for x, v in zip(self.xs, a)) / tot if tot > 0 else 0.0), n
        self.split = self._solve(lambda d: centre(d)[0], -2.0, 2.0, self.lcb)
        self.reached_lcb, self.n = centre(self.split)
        self._us, self._cs, area = stations(self.n, self.split)
        self.volume = sum(area) / self.N

    def _stations(self, n, d, lam0, cm=None, xa=None, xf=None):
        """The stations' waterlines, fullness and areas (of B T) for the area curve's n and split d, and the
        waterline's share lam0."""
        L = self.hull.L
        cm = self.cm if cm is None else cm
        if xa is None:
            xa, xf = self._mid
        n_f, n_r = n * math.exp(d), n * math.exp(-d)
        rows = []           # (s, w, dk, c_hi, raw waterline) per station, stern to bow
        for x, w, dk in zip(self.xs, self._ws, self._ds):
            if x > xf:
                r, nn, e, k = (x - xf) / (L / 2 - xf), n_f, self._ends[1], self.k_fore
            elif x < xa:
                r, nn, e, k = (xa - x) / (xa + L / 2), n_r, self._ends[0], self.k_aft
            else:
                r, nn, e, k = 0.0, 1.0, 1.0, 0.0
            r = min(1.0, r)
            s = e + (1 - e) * (1 - r * r) ** (1 / nn)
            c_hi = min(self.C_MAX, cm - max(0.0, cm - self.C_END) * r ** self.C_END_POW)
            rho = s / dk if dk > 0 else 0.0
            u = min(w, rho ** max(0.05, lam0 + self.LAMBDA_K * k)) if rho > 0 else 0.0
            rows.append([s, w, dk, c_hi, u])
        # the waterline only narrows from the shoulders out to the ends: a shallow run over a cut-up wants it
        # wide again toward the transom, so the stations ahead of it are filled out to it (never cut down to a
        # plateau, which met the deck edge in a corner), then smoothed; the sections take up the rest
        fore = [i for i in reversed(range(self.N)) if self.xs[i] > xf and rows[i][2] > 0]
        aft = [i for i in range(self.N) if self.xs[i] < xa and rows[i][2] > 0]
        for end in (fore, aft):         # from the end inward
            u_max = 0.0
            for i in end:
                u_max = rows[i][4] = min(rows[i][1], max(u_max, rows[i][4]))
            raw = [rows[i][4] for i in end]
            h = self.SMOOTH
            for j, i in enumerate(end):
                win = raw[max(0, j - h):j + h + 1]
                rows[i][4] = min(rows[i][1], sum(win) / len(win))
        us, cs, area = [], [], []
        for s, w, dk, c_hi, u in rows:
            if dk <= 0 or w <= 0:           # over a counter, or past the deck's tip
                us.append(w); cs.append(cm); area.append(0.0)
                continue
            c = cm * s / (u * dk) if u > 0 else self.C_MIN
            if c > c_hi:
                c, u = c_hi, min(u, cm * s / (dk * c_hi))
            elif c < self.C_MIN:
                c, u = self.C_MIN, min(u, cm * s / (dk * self.C_MIN))
            us.append(u); cs.append(c); area.append(u * dk * c)
        return us, cs, area

    def _at(self, vals, x):
        """A station table's value at x, linear between the stations' centres."""
        f = (x + self.hull.L / 2) / self.hull.L * self.N - 0.5
        i = max(0, min(self.N - 2, int(math.floor(f))))
        t = max(0.0, min(1.0, f - i))
        return vals[i] + (vals[i + 1] - vals[i]) * t

    def keel(self, x):
        """The keel's height over the baseline at x."""
        L, T = self.hull.L, self.T
        z = 0.0
        run = L / 2 - x                 # from the stem
        if run < self.forefoot:
            r = 1.0 - run / self.forefoot
            z = T * r * r if self.planing else T * (1.0 - math.sqrt(max(0.0, 1.0 - r * r)))
        if self.post is not None and x < self.post:
            z = T                       # abaft the sternpost: the counter, out of the water
        elif self.cut:
            x_c, x_s, rise, end = self.cut
            if x_c <= x < x_s:
                z = max(z, rise * ((x_s - x) / (x_s - x_c)) ** 2)
            elif x < x_c:                   # on up to the stern, the cut-up's slope where they meet
                run = x_c + L / 2
                k = max(1.0, 2.0 * rise / (x_s - x_c) * run / (end - rise)) if end > rise + 1e-6 else 1.0
                z = max(z, rise + (end - rise) * (1.0 - (1.0 - min(1.0, (x_c - x) / run)) ** k))
        return min(T, z)

    def waterline(self, x):
        """The waterplane's half-breadth at x."""
        return min(self.hull.half_width(x), self.hull.B / 2 * self._at(self._us, x))

    def fullness(self, x):
        """The section's fullness below the waterline at x: its area over its box's (2 hw_wl x its depth)."""
        return max(self.C_MIN, min(self.C_MAX, self._at(self._cs, x)))

    def character(self, x, c):
        """The section's character, -1 (V) .. 1 (U), at x for its fullness c."""
        k = self.k_fore if x > 0 else self.k_aft
        return k * min(1.0, abs(x) / (self.CHAR_RUN * self.hull.L)) * max(0.0, min(1.0, (c - 0.5) / 0.15))

    def half_width(self, x, z):
        """The half-breadth at x and z metres above the keel."""
        deck = self.hull.half_width(x)
        if z >= self.D:
            return deck
        wl = self.waterline(x)
        if z >= self.T:
            return wl + (deck - wl) * (z - self.T) / (self.D - self.T) if self.D > self.T else deck
        zk = self.keel(x)
        if z <= zk:
            return 0.0
        d = self.T - zk
        c = self.fullness(x)
        if self.planing and c >= 0.5:      # hard chine: a straight deadrise to the chine, upright above it
            chine = 2.0 * d * (1.0 - c)
            return min(deck, wl * min(1.0, (z - zk) / chine) if chine > 1e-9 else wl)
        kw = 0.0 if self.planing else min(self.KEEL_K * self.hull.B, self.KEEL_SHARE * wl * c)
        if wl - kw < 1e-6:
            return min(deck, wl)
        c_curve = max(0.2, min(self.C_MAX, (wl * c - kw) / (wl - kw)))     # the curve's share beside the keel
        p, q = section_exponents(round(c_curve, 3), round(0.0 if self.planing else self.character(x, c), 3))
        return min(deck, kw + (wl - kw) * max(0.0, 1.0 - ((self.T - z) / d) ** q) ** (1.0 / p))

    def waterplane(self, n=400):
        """The design waterplane: (area m², its centre's x (lcf), its second moments about the lcf
        athwartships (i_l, for trim) and about the centreline (i_t, for heel), m⁴), by the midpoint rule."""
        L = self.hull.L
        dx = L / n
        xs = [-L / 2 + (i + 0.5) * dx for i in range(n)]
        hw = [self.waterline(x) for x in xs]
        area = sum(2 * y for y in hw) * dx
        lcf = sum(2 * y * x for x, y in zip(xs, hw)) * dx / area
        i_l = sum(2 * y * (x - lcf) ** 2 for x, y in zip(xs, hw)) * dx
        i_t = sum(2 / 3 * y ** 3 for y in hw) * dx
        return area, lcf, i_l, i_t

    HEIGHTS = (0.0, 0.01, 0.03, 0.08, 0.15, 0.25, 0.4, 0.55, 0.7, 0.85, 1.0)  # sampled, fractions of the depth

    def table(self, stations=48):
        """Sampled sections for the hitboxes: [dict(x, z, y)], z on the keel scale, from the section's keel (its
        first height) up to the main deck (and the waterline among them). A station abaft a sternpost starts
        at the waterline: nothing of it is under water."""
        L = self.hull.L
        top = min(self.T, self.D)
        out = []
        for k in range(stations + 1):
            x = -L / 2 + L * (1 - math.cos(math.pi * k / stations)) / 2
            zk = min(self.keel(x), top)
            zs = sorted({zk + (top - zk) * f for f in self.HEIGHTS} | {self.D})
            out.append(dict(x=x, z=zs, y=[self.half_width(x, z) for z in zs]))
        return out


def table_half_width(table, x, z):
    """A sampled hull form's (HullForm.table, as exported) half-breadth at x and z: bilinear between stations
    and heights; under a station's first height (its keel) nothing, above the top height, the top's."""
    xs = [s["x"] for s in table]
    if x <= xs[0] or x >= xs[-1]:
        return 0.0
    i = max(0, min(len(xs) - 2, next(k for k in range(len(xs) - 1) if xs[k + 1] >= x)))

    def at(s):
        zs, ys = s["z"], s["y"]
        if z >= zs[-1]:
            return ys[-1]
        if z < zs[0]:
            return 0.0
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
