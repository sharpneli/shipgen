"""
layout — turns a player's design (counts and calibres) into exact positions.

The player says "2 turrets forward, 1 aft, 5 secondaries per side". This module decides where
everything goes using simple naval-architecture rules:

  bow | forecastle | fwd turret group | MIDDLE (bridge, funnels over machinery, aft control) | aft group | quarterdeck | stern

* Turret groups sit as far toward the ends as the hull allows: preferred bow/stern clearances,
  the hull width at the mount, and the minimum clearances.
* The middle must be long enough for the boiler and engine rooms (length grows with sqrt(power)).
* The whole arrangement is then shifted fore/aft so the centre of gravity sits over the centre of
  buoyancy (design.py runs that loop, using shift_range from here).
* Secondaries, torpedo mounts and AA go into free slots, symmetric port/starboard,
  preferring amidships.

Everything placed becomes a component with an exact shape and height. The same components feed
the renderer spec, the hitboxes and the weight model.
"""
from __future__ import annotations

import bisect
import functools
import math
import re

from geometry import (make_turret_type, make_torpedo_type, rrect_polygon, rrect_clamped, circle_polygon,
                      turret_shapes, turret_height, turret_reach, point_in_polygon, polygons_intersect,
                      sector_polygon, superfire_step, polygon_centroid, polygon_y_span, clip_convex, simplify_polygon)
import ordnance
import powerplant
from navarch import Weight, mount_weights, torpedo_weight, TUNING
from hitbox import ARC_BEAM
from geometry import Hull, AA_CFG

LEVEL_H = 2.6  # height of one superstructure level, metres
CASEMATE_BEAM = 0.7    # casemates stand where the hull is at least this fraction of its full beam


# ---------------------------------------------------------------------------
# small collision helpers (circles, axis-aligned rects and polygons)
# ---------------------------------------------------------------------------
def _fp_circle(x, y, r):
    return ("c", x, y, r)


def _fp_rect(x0, y0, x1, y1):
    return ("r", x0, y0, x1, y1)


def _fp_poly(pts):
    pts = [tuple(p) for p in pts]
    return ("p", pts, min(x for x, _ in pts), min(y for _, y in pts), max(x for x, _ in pts), max(y for _, y in pts))


def _bbox(fp):
    """Bounding box (x0, y0, x1, y1) of a circle, rect or polygon footprint."""
    if fp[0] == "c":
        return fp[1] - fp[3], fp[2] - fp[3], fp[1] + fp[3], fp[2] + fp[3]
    if fp[0] == "p":
        return fp[2:]
    return fp[1], fp[2], fp[3], fp[4]


def _fp_points(fp, margin=0.0):
    """A rect or polygon footprint as a polygon (a rect grown by margin)."""
    if fp[0] == "p":
        return fp[1]
    return [(fp[1] - margin, fp[2] - margin), (fp[3] + margin, fp[2] - margin), (fp[3] + margin, fp[4] + margin),
            (fp[1] - margin, fp[4] + margin)]


def _overlap(a, b, margin=0.0):
    if a[0] == "p" or b[0] == "p":     # polygons: a circle by its distance, rects grown by the margin
        p, o = (a, b) if a[0] == "p" else (b, a)
        if o[0] == "c":
            pts = p[1]
            return point_in_polygon(o[1], o[2], pts) or min(
                _seg_dist(o[1], o[2], *pts[i - 1], *pts[i]) for i in range(len(pts))) < o[3] + margin
        return polygons_intersect(p[1], _fp_points(o, margin))
    if a[0] == "c" and b[0] == "c":
        return math.hypot(a[1] - b[1], a[2] - b[2]) < a[3] + b[3] + margin
    if a[0] == "r" and b[0] == "r":
        return not (a[3] + margin <= b[1] or b[3] + margin <= a[1] or a[4] + margin <= b[2] or b[4] + margin <= a[2])
    c, r = (a, b) if a[0] == "c" else (b, a)
    nx = min(max(c[1], r[1]), r[3])
    ny = min(max(c[2], r[2]), r[4])
    return math.hypot(c[1] - nx, c[2] - ny) < c[3] + margin


class Layout:
    def __init__(self, design=None, sup_t=None):
        sup = (design or {}).get("superstructure") or {}
        # superstructure structure weight per m2 of each level's footprint (steel about 0.32, aluminium about 0.2)
        self.sup_t = sup.get("t_per_m2", TUNING["superstructure_t_per_m2"] if sup_t is None else sup_t)
        self.directors = []     # fire-control directors (firecontrol.place)
        self.components = []    # exact geometry + heights (hitboxes)
        self.footprints = []    # (fp, base, top, owner_id) for collision tests
        self.weights = []       # navarch.Weight with x positions
        self.errors, self.warnings = [], []
        self.spec = {}
        self.geo = {}
        self.shift_range = (0.0, 0.0)
        self.compartments = []
        self.decks = []         # raised decks and flight decks: dict(id, kind, points, base, top)
        self.sponsons = []      # platforms outboard of a flight deck: dict(id, points, base, top)
        self.sweeps = []        # main turrets' barrel sweep zones: dict(owner, polys, axis)
        self.funnels_planned = []    # funnels with their machinery segment ("seg"); add_machinery_rooms adds "serves"
        self.casings = []       # casings over machinery taller than its space: dict(id, x0, x1, w, base, top, ...)
        self.conning_tower = None   # armoured warships: dict(x, y, r, top), inside the bridge (not drawn)
        self.short = set()      # what the hull lacks for everything to fit: "length" and/or "beam" (sizing)

    def fail(self, need, msg):
        """Something doesn't fit: an error, and what more of (need: "length", "beam" or None) would fix it."""
        self.errors.append(msg)
        if need:
            self.short.add(need)

    def free(self, fp, margin=0.4, ignore=()):
        x0, y0, x1, y1 = _bbox(fp)
        x0, y0, x1, y1 = x0 - margin, y0 - margin, x1 + margin, y1 + margin
        for o in self.footprints:
            b = _bbox(o[0])
            if b[0] < x1 and x0 < b[2] and b[1] < y1 and y0 < b[3] and o[3] not in ignore \
                    and _overlap(fp, o[0], margin):
                return False
        return True

    def free_at(self, fp, base, top, margin=0.4, ignore=()):
        """Is a footprint standing from base to top (m above the main deck) clear of everything placed whose height
        overlaps it? (free() ignores heights.)"""
        x0, y0, x1, y1 = _bbox(fp)
        x0, y0, x1, y1 = x0 - margin, y0 - margin, x1 + margin, y1 + margin
        for o in self.footprints:
            if o[2] <= base + 1e-6 or o[1] >= top - 1e-6 or o[3] in ignore:
                continue
            b = _bbox(o[0])
            if b[0] < x1 and x0 < b[2] and b[1] < y1 and y0 < b[3] and _overlap(fp, o[0], margin):
                return False
        return True

    def occupy(self, fp, base, top, owner):
        self.footprints.append((fp, base, top, owner))

    def reserve_sweep(self, m):
        """A main turret claims the area its barrels sweep: its firing arcs plus the turn from its stowed
        bearing to the starboard arc (one side free to switch sides), out to the muzzles. Anything placed
        later that stands taller than the guns must keep out (see clear())."""
        from hitbox import mount_arcs
        arcs = mount_arcs(m)
        rest = m["rest"] % 360.0
        intervals = list(arcs)
        if not any(lo <= rest <= hi or lo <= rest + 360 <= hi for lo, hi in arcs):
            lo, hi = next(((lo, hi) for lo, hi in arcs if lo <= 90 <= hi), arcs[0])
            intervals.append([rest, lo] if rest < lo else [hi, rest])
        R = turret_reach(m["t"]) + 0.5
        polys = []
        for lo, hi in intervals:
            polys.append(sector_polygon(m["x"], m["y"], R, lo, hi))
        sectors = [(m["x"], m["y"], R, lo, hi) for lo, hi in intervals]
        boxes = [(min(x for x, _ in p), min(y for _, y in p), max(x for x, _ in p), max(y for _, y in p)) for p in polys]
        self.sweeps.append(dict(owner=m["id"], polys=polys, boxes=boxes, sectors=sectors,
                                axis=m["base"] + 0.55 * (m["top"] - m["base"])))

    def clear(self, poly, top):
        """Is a footprint (polygon or circle/rect footprint) standing `top` metres above the deck clear of every
        gun sweep lower than it?"""
        circle = poly[1:] if isinstance(poly, tuple) and poly[0] == "c" else None
        if isinstance(poly, tuple):
            poly = circle_polygon(poly[1], poly[2], poly[3], 16) if poly[0] == "c" else _fp_points(poly)
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        for sw in self.sweeps:
            if sw["axis"] >= top:
                continue
            for p, (a0, b0, a1, b1), sec in zip(sw["polys"], sw["boxes"], sw["sectors"]):    # quick rejects first:
                # bounding boxes, then a circle's true distance from the true sector (both polygons lie inside
                # their true shapes, so a miss there is a miss for the polygons too)
                if not (a0 <= x1 and x0 <= a1 and b0 <= y1 and y0 <= b1):
                    continue
                if circle is not None:
                    d = _sector_dist(sec, circle[0], circle[1])
                    if d >= circle[2]:
                        continue
                    if d < circle[2] - 0.2 - 0.005 * sec[2]:    # deep inside: the polygons overlap too
                        return False
                if polygons_intersect(poly, p):
                    return False
        return True

    def on_deck(self, x, y):
        """Is (x, y) on a deck that overhangs the hull (a flight deck)?"""
        return any(point_in_polygon(x, y, dk["points"]) for dk in self.decks if dk["kind"] == "flight_deck")


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy or 1.0)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def _sector_dist(sec, px, py):
    """Distance from (px, py) to a pie slice (cx, cy, R, a0, a1) (bearings as geometry.sector_polygon), 0 inside."""
    cx, cy, R, a0, a1 = sec
    d = math.hypot(px - cx, py - cy)
    a = math.degrees(math.atan2(py - cy, px - cx))
    inside = a1 - a0 >= 360 or (a - a0) % 360.0 <= a1 - a0
    if inside:
        return max(0.0, d - R)
    ends = [(cx + R * math.cos(math.radians(b)), cy + R * math.sin(math.radians(b))) for b in (a0, a1)]
    return min(_seg_dist(px, py, cx, cy, ex, ey) for ex, ey in ends)


def add_block(lay, blocks, bid, x0, x1, w, level, rf, rb, y=0.0, z0=0.0, layer=None, kind="superstructure",
              t_per_m2=None, points=None):
    """Superstructure block standing on z0 (metres above the main deck): footprint, weight, record.
    Blocks above the main deck go on the upper sprite layer. points: an outline polygon instead of the rounded
    rectangle; x0, x1, y and w then become its bounding box, and rf, rb are 0 (its corners are sharp)."""
    if points:
        points = [(round(px, 3), round(py, 3)) for px, py in points]
        x0, x1 = min(p[0] for p in points), max(p[0] for p in points)
        y0, y1 = min(p[1] for p in points), max(p[1] for p in points)
        y, w, rf, rb = (y0 + y1) / 2, y1 - y0, 0.0, 0.0
    rf_, rb_ = rrect_clamped(x0, y - w / 2, x1, y + w / 2, rf, rb)
    b = dict(id=bid, kind=kind, x0=x0, x1=x1, y=y, w=w, level=level, rf=rf_, rb=rb_)
    if points:
        area, xc = polygon_centroid(points)
        b.update(points=[list(p) for p in points], area=round(area, 2))
    else:
        area, xc = (x1 - x0) * w, (x0 + x1) / 2
    if z0:
        b["z0"] = z0
    if layer or z0:
        b["layer"] = layer or "upper"
    blocks.append(b)
    lay.occupy(_fp_poly(points) if points else _fp_rect(x0, y - w / 2, x1, y + w / 2), block_base(b), block_top(b), bid)
    t_per_m2 = lay.sup_t if t_per_m2 is None else t_per_m2
    lay.weights.append(Weight(bid, "superstructure", area * t_per_m2,
                              x=xc, z_rel=("deck", (block_base(b) + block_top(b)) / 2)))
    return b


def roof_spots(blocks, l, w, step=0.5):
    """Where something l long (fore and aft) and w wide could stand on the blocks' roofs: (x, y, z0, pair) candidates.
    pair: one each side at +-y (on a block centred on the centreline), else a single one at y. Along each roof every
    step metres, inside its length; across, on its centreline and at its edges (a director's rangefinder arms or an AA
    tub may overhang the edge a little). Directors' own roofs are left out."""
    out = []
    for b in blocks:
        if b.get("kind") == "director":
            continue
        z0 = block_top(b)
        if b["x1"] - b["x0"] < l:
            xs = [(b["x0"] + b["x1"]) / 2]
        else:
            n = int((b["x1"] - b["x0"] - l) / step)
            xs = [b["x0"] + l / 2 + k * step for k in range(n + 1)]
        ye = b["w"] / 2 - w / 2
        if b.get("points") and "_slabs" not in b:      # cached on the block (finish_layout leaves it out)
            b["_slabs"] = _Slabs(b["points"])
        slabs = b.get("_slabs")
        for x in xs:
            # a polygon roof: the spot (both of a pair) inside it across its length
            spans = [slabs.at(x + dx) for dx in (-l / 2, l / 2)] if slabs else None

            def on_roof(y):
                if not spans:
                    return True
                hw_ = w / 2 - 0.3 if w < b["w"] else 0.0     # wider than the roof: its arms overhang, as before
                for s in ((1, -1) if y else (1,)):
                    a, b_ = s * y - hw_, s * y + hw_
                    for sp in spans:
                        for lo, hi in sp:
                            if lo <= a and b_ <= hi:
                                break
                        else:
                            return False
                return True
            if on_roof(b["y"]):
                out.append((x, b["y"], z0, False))
            if abs(b["y"]) < 1e-6 and ye > w / 2 + 0.1 and on_roof(ye):
                out.append((x, ye, z0, True))
    return out


def _thin(line, tol):
    """Douglas-Peucker: the polyline's points that keep it within tol of the original."""
    if len(line) < 3:
        return list(line)
    (ax, ay), (bx, by) = line[0], line[-1]
    i, dmax = max(((i, _seg_dist(*line[i], ax, ay, bx, by)) for i in range(1, len(line) - 1)), key=lambda t: t[1])
    if dmax <= tol:
        return [line[0], line[-1]]
    return _thin(line[:i + 1], tol)[:-1] + _thin(line[i:], tol)


class _Slabs:
    """A polygon cut into slabs between its vertices' x: where a line across the ship is inside it, quickly."""
    def __init__(self, pts):
        self.xs = sorted({x for x, _ in pts})
        edges = [(x0, y0, x1, y1) for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]) if x0 != x1]
        self.slabs = []
        for a, b in zip(self.xs, self.xs[1:]):
            m = (a + b) / 2
            self.slabs.append(sorted((e for e in edges if (e[0] > m) != (e[2] > m)),
                                     key=lambda e: e[1] + (m - e[0]) * (e[3] - e[1]) / (e[2] - e[0])))

    def at(self, x):
        """The stretches of y inside the polygon at x."""
        i = bisect.bisect_right(self.xs, x) - 1
        if i < 0 or i >= len(self.slabs):
            return []
        ys = [y0 + (x - x0) * (y1 - y0) / (x1 - x0) for x0, y0, x1, y1 in self.slabs[i]]
        return [(ys[k], ys[k + 1]) for k in range(0, len(ys) - 1, 2)]


def mast_weight(lay, m, top, name):
    """A mast's weight at half its height: tripod legs or a pole, tubes that get stouter the taller they are
    (MAST_T_K x top^2 per leg: a 20 m pole 4.8 t, a battleship's tripod about 14 t)."""
    legs = 3 if m.get("tripod") else 1
    lay.weights.append(Weight(name, "superstructure", legs * MAST_T_K * top ** 2, x=m["x"],
                              z_rel=("deck", top / 2)))


MAST_T_K = 0.012

# warship AA preference, added to the distance from amidships (fraction of L): by the roof's level (index: 1 the
# deckhouse, 2-3 the bridge and aft control, 4+ the tower), single mounts on a roof's line, the deck edges
AA_ROOF_PEN = (0.05, 0.05, 0.0, 0.0, 0.03)
AA_SINGLE_PEN = 0.1
AA_PLATFORM_PEN = 0.15   # on a raised platform (a pedestal block AA_PLATFORM_H tall) at the deck edge
AA_PLATFORM_H = LEVEL_H
AA_DECK_PEN = 0.3        # on the bare deck: only where a raised tub would stand in a turret's sweep


def battery_of(mid):
    """A grouped mount's battery: its id less the number and side ("SB3P" -> "SB", "W1S" -> "W1")."""
    pre, num = re.match(r"^([A-Z]+?)(\d+)[SP]$", mid).groups()
    return pre + num if pre == "W" else pre


def magazine_plan(design, tm):
    """The magazines grouped fore and aft of the machinery (warships): the secondaries' (deck and casemate) and
    the abreast wing turrets'. Each battery sends the forward half of its pairs (rounded up) to the fore group;
    wing pair k goes to the end of the middle it stands at (even k forward). Returns {"fore"|"aft": [(battery,
    mounts, magazine m3 per mount)]}."""
    out = {"fore": [], "aft": []}
    main = design.get("main") or {}
    if tm and not main.get("echelon"):
        for k in range(main.get("wing", 0)):
            out["fore" if k % 2 == 0 else "aft"].append((f"W{k + 1}", 2, ordnance.ammo_m3(tm)))
    secs = design.get("secondary") or []
    for k, s in enumerate(secs if isinstance(secs, list) else [secs]):
        n = s.get("per_side", s.get("count", 0) // 2)
        if not n:
            continue
        kind = "casemate" if s.get("mount") == "casemate" else "auto"
        t = make_turret_type(s["calibre_mm"], s["calibre_length"], s["barrels"], kind=kind)[1]
        for grp, pairs in (("fore", (n + 1) // 2), ("aft", n // 2)):
            if pairs:
                out[grp].append((battery_prefix(k), 2 * pairs, ordnance.ammo_m3(t)))
    return out


def add_magazines(lay, mounts, inner_hw, groups=None):
    """The warship's magazines (ordnance.stow), linked both ways (m["magazine"], the magazine's "mount" or
    "mounts"). End, midships and echelon wing turrets: one per mount, below it on the centreline, spanning its
    diameter (ordnance.own_zone). Grouped mounts (magazine_plan) share one magazine per battery and group, in the
    machinery block's magazine segments: groups = {"fore"|"aft": (x0, x1)}. Each battery's forward pairs fill the
    fore group as planned."""
    groups = groups or {}
    plan = lay.geo.get("plant") or {}
    ghw = plan["width"] / 2 if plan.get("wing_m") else min(inner_hw, plan.get("width", 2 * inner_hw) / 2)
    zones, batteries = [], {}
    for m in mounts:
        if m["kind"] not in ("main", "secondary"):
            continue
        if groups and (m["kind"] == "secondary" or (m.get("wing") and not m.get("echelon"))):
            batteries.setdefault(battery_of(m["id"]), []).append(m)
            continue
        zones.append(ordnance.own_zone(m, inner_hw))
    rooms = {"fore": [], "aft": []}
    for bat, ms in batteries.items():
        pairs = sorted({m["x"] for m in ms}, reverse=True)
        n_fore = len(pairs) if not bat.startswith("W") else 0
        if bat.startswith("W"):            # wing pair k stands at the fore end of the middle for even k
            n_fore = len(pairs) if int(bat[1:]) % 2 == 1 else 0
        elif "fore" in groups and "aft" in groups:
            n_fore = (len(pairs) + 1) // 2
        n_fore = len(pairs) if "aft" not in groups else 0 if "fore" not in groups else n_fore
        for grp, xs in (("fore", pairs[:n_fore]), ("aft", pairs[n_fore:])):
            sel = [m["id"] for m in ms if m["x"] in xs]
            if sel:
                rooms[grp].append(dict(id=f"Magazine {bat} {grp}", mounts=sel))
    for grp, rs in rooms.items():
        if rs:
            zones.append(dict(x0=groups[grp][0], x1=groups[grp][1], half_width=ghw, rooms=rs))
    ordnance.stow(lay, mounts, zones)


def plan_machinery(lay, design, res, hull, x=0.0):
    """The machinery space for the solved ship res (navarch.Result: its plant, power, depth, draught, fuel), centred
    near x. The room the plant gets: across, the hull inside its frames, less torpedo protection (armour.tds_m) and
    wing bunkers on each side; up, from the inner bottom to the lowest armour deck over the citadel (the main deck
    without deck armour). Fuel the
    wing bunkers and double bottom can't take goes into end bunkers or tanks, which lengthen the block. Stores the
    plan in lay.geo["plant"] and returns the block's length (powerplant.segments)."""
    from navarch import armour_geometry, deck_stack
    p = res.plant
    armour = design.get("armour") or {}
    D, T = res.depth, res.draught
    tds = armour.get("tds_m", 0.0)
    wing = p["wing_bunker_m"] if (p["tech"]["fuel"] == "coal" and p["bunkers"] == "wing") else 0.0
    w = powerplant.STEEL_FRAME * 2 * hull.half_width(x) - 2 * tds - 2 * wing
    ag = armour_geometry(design, hull.L, T, D, lay.geo)
    armoured = ag["armoured"]
    top = ag["roof_z"] if ag["roof_z"] is not None else D
    db = powerplant.double_bottom(D)
    h = max(1.0, top - db)
    sp = powerplant.space(p, res.power_shp, w, h)
    cb = design["hull"]["block_coefficient"]
    wing_t, end = powerplant.bunkers(p, res.fuel, sp["length"], w, h, hull.L, hull.B, cb, D, T, tds)
    segs = powerplant.segments(p, sp, end)
    if not sp["fits"]:
        lay.fail("beam", f"The plant's units are {sp['unit'][1]:.1f} m wide, but the machinery space is only "
                         f"{max(w, 0.0):.1f} m across. Use more shafts (smaller units) or less side protection.")
    lay.geo["plant"] = dict(fuel=p["tech"]["fuel"], space=sp, segments=segs, wing_t=wing_t, wing_m=wing, end_m=end,
                            width=w, height=h, inner_bottom=db, top=top, armoured=armoured, deck_mm=ag["roof_mm"],
                            tds=tds, decks=[z for _, z in deck_stack(design, D)])
    return sum(seg_l for _, seg_l in segs)


def stack_machinery(segs, x_front):
    """Place machinery segments one after another, aft from x_front: [(kind, x0, x1)]."""
    out, x = [], x_front
    for kind, seg_l in segs:
        out.append((kind, x - seg_l, x))
        x -= seg_l
    return out


def add_machinery_rooms(lay, placed, inner_hw, depth):
    """Compartments for the placed machinery segments [(kind, x0, x1)]: boiler rooms, engine rooms and bunkers
    (each cut into rooms no longer than about 0.07 L), wing bunkers beside the machinery, and the casing over a
    plant that stands taller than its space. Sets lay.geo machinery (the block's span), machinery_x and
    machinery_rooms."""
    plan = lay.geo["plant"]
    fuel = plan["fuel"]
    names = {"boiler": "Boiler room", "engine": "Engine room", "bunker": "Bunker"}
    count = {k: 0 for k in names}
    rooms = []
    max_room = max(6.0, 0.07 * lay.hull.L)
    seg_rooms = {}
    for si, (kind, x0, x1) in enumerate(placed):
        n = max(1, math.ceil((x1 - x0) / max_room - 1e-9))
        for k in range(n):
            count[kind] += 1
            a, b = x1 - (k + 1) * (x1 - x0) / n, x1 - k * (x1 - x0) / n
            c = dict(id=f"{names[kind]} {count[kind]}", kind=f"{kind}_room" if kind != "bunker" else "bunker",
                     x0=a, x1=b, half_width=plan["width"] / 2 if plan["wing_m"] else min(inner_hw, plan["width"] / 2))
            if kind == "bunker":
                c["fuel"] = fuel
            rooms.append(c)
            seg_rooms.setdefault(si, []).append(c["id"])
    lay.compartments += rooms
    x0, x1 = min(s[1] for s in placed), max(s[2] for s in placed)
    if plan["wing_m"] > 0:
        y = plan["width"] / 2 + plan["wing_m"] / 2
        for side in (1, -1):
            lay.compartments.append(dict(id=f"Wing bunker {'S' if side > 0 else 'P'}", kind="bunker", fuel=fuel,
                                         x0=x0, x1=x1, y=side * y, half_width=plan["wing_m"] / 2,
                                         base=plan["inner_bottom"] - depth, top=0.0,     # up to the main deck
                                         tonnes=round(plan["wing_t"] / 2, 1)))
    sp = plan["space"]
    if sp["protrusion"] > 0:     # the units stand above the bounding deck: a casing (glacis if armoured) over them
        engines = [s for s in placed if s[0] == "engine"] or placed
        cw = min(plan["width"], sp["rows"] * (sp["unit"][1] + 0.8)) if sp["rows"] else plan["width"]
        top = plan["inner_bottom"] + sp["unit"][2] - depth
        lay.casings = [dict(id=f"Machinery casing {i + 1}", x0=a, x1=b, w=cw, base=plan["top"] - depth, top=top,
                            armour_mm=plan["deck_mm"] if plan["armoured"] else 0)
                       for i, (_, a, b) in enumerate(engines)]
        if plan["armoured"]:
            for c in lay.casings:
                area = 2 * ((c["x1"] - c["x0"]) + c["w"]) * (c["top"] - c["base"]) + (c["x1"] - c["x0"]) * c["w"]
                lay.weights.append(Weight(c["id"], "armour", area * plan["deck_mm"] / 1000 * 7.85,
                                          x=(c["x0"] + c["x1"]) / 2, z_rel=("deck", (c["base"] + c["top"]) / 2)))
    lay.geo["machinery"] = (x0, x1)
    lay.geo["machinery_x"] = (x0 + x1) / 2
    lay.geo["machinery_rooms"] = [(r["kind"], r["id"], r["x0"], r["x1"]) for r in rooms]
    for f in lay.funnels_planned:     # each funnel's uptakes lead from the boiler rooms of its segment
        f["serves"] = seg_rooms.get(f.get("seg"), [])


FUNNEL_ABOVE = 3.0      # m a funnel top stands over the tower's 4th level, and over any roof it passes through
STACK_NATURAL = 25.0    # m from the grates to the funnel top that natural and boost draught plants want
BRIDGE_OVER_BOILERS = 0.85   # how much of the bridge (and its gap) the forward boiler group may run on under
# the navigating bridge's deck stands at least this far over the roof of the highest turret ahead of it, so the
# eye (about 1.7 m up) clears the roof by about 2.7 m and sees the sea ahead. Real ships stand 2-4 m clear
# (research/superstructure-research.md section 6); whole levels of LEVEL_H put a Fletcher-like destroyer's bridge at
# level 4 and a battleship's at level 5
BRIDGE_CLEAR = 1.0


# a really tall tower tapers: base levels above TOWER_TAPER_FROM lose TOWER_TAPER_W of their width and
# TOWER_TAPER_L of their length per level, down to the floors (every design up to now stays below it)
TOWER_TAPER_FROM = 6
TOWER_TAPER_W, TOWER_TAPER_L = 0.07, 0.04
TOWER_MIN_W, TOWER_MIN_L = 0.45, 0.6


def tower_taper(k):
    """(width, length) of the bridge tower's level k as fractions of the bridge's footprint."""
    n = max(0, k - TOWER_TAPER_FROM)
    if not n:
        return 1.0, 1.0
    return max(TOWER_MIN_W, (1 - TOWER_TAPER_W) ** n), max(TOWER_MIN_L, (1 - TOWER_TAPER_L) ** n)


def bridge_level(roof):
    """The lowest level the navigating bridge can stand at (2 at least) to see over a turret roof this high above
    the main deck (None: nothing ahead)."""
    if roof is None:
        return 2
    return max(2, math.ceil((roof + BRIDGE_CLEAR) / LEVEL_H - 1e-9) + 1)


def plan_funnels(lay, design, res, beam, top, groups=None):
    """Funnel count and size for the planned machinery (plan_machinery), with funnel tops `top` above the main
    deck: powerplant.funnel_plan over the boiler groups (default: the plan's boiler segments), and at least the
    design's "funnels". Returns (count, width, length)."""
    plant = lay.geo["plant"]
    if groups is None:
        groups = [seg_l for kind, seg_l in plant["segments"] if kind == "boiler"]
    stack = res.depth - plant["inner_bottom"] - 1.0 + top
    fp = powerplant.funnel_plan(res.plant, res.power_shp, groups, beam, stack)
    if design.get("funnels") and design["funnels"] > sum(fp["counts"]):    # the player may add more, not fewer
        fp = powerplant.funnel_plan(res.plant, res.power_shp, groups, beam, stack,
                                    extra=design["funnels"] - sum(fp["counts"]))
    lay.geo["funnel_plan"] = fp
    lay.geo["smoke_reach"] = powerplant.smoke_reach(res.plant, res.power_shp)   # directors keep out of it
    return sum(fp["counts"]), fp["width"], fp["length"]


def boiler_seg(lay):
    """Index of the plan's (first, largest) boiler segment, or its engines for an engines-only plant."""
    segs = lay.geo["plant"]["segments"]
    best = max(range(len(segs)), key=lambda i: (segs[i][0] == "boiler", segs[i][0] == "engine", segs[i][1]))
    return best


def add_funnel_weights(lay, f, top, served_x, depth):
    """Weights of funnel f (dict: x, l, w, z0) standing to `top` above the main deck, and of its uptakes from the
    boilers it serves (centred at served_x) up to the deck, with armoured gratings where they pierce an armoured
    deck. Records the funnel for add_machinery_rooms."""
    plant = lay.geo["plant"]
    sp = plant["space"]
    z0 = f.get("z0", 0.0)
    vert = max(1.0, depth - (plant["inner_bottom"] + sp["unit"][2])) + z0
    horiz = abs(f["x"] - served_x)
    w_f, w_u = powerplant.funnel_weight(f["w"], f["l"], top - z0, vert, horiz)
    lay.weights.append(Weight(f["id"], "superstructure", w_f, x=f["x"], z_rel=("deck", (z0 + top) / 2)))
    lay.weights.append(Weight(f"Uptakes {f['id']}", "machinery", w_u, x=(f["x"] + served_x) / 2,
                              z_rel=("deck", z0 - vert / 2)))
    fp = lay.geo.get("funnel_plan")
    if plant["armoured"] and fp:
        lay.weights.append(Weight(f"Gratings {f['id']}", "armour", 0.6 * fp["area"] / max(1, sum(fp["counts"])),
                                  x=served_x, z_rel=("deck", plant["top"] - depth)))
    f["top"] = top
    lay.funnels_planned.append(f)


def raise_funnels(lay, funnels, blocks, top):
    """The funnel top (m above the main deck) raised to FUNNEL_ABOVE over the highest block any funnel passes
    through (deckhouse levels wrap round the funnels), with the funnels' footprints and weights updated to match."""
    new = top
    for f in funnels:
        pts = _fp_points(_fp_rect(f["x"] - f["l"] / 2, f["y"] - f["w"] / 2, f["x"] + f["l"] / 2, f["y"] + f["w"] / 2))
        for b in blocks:
            if b.get("points") and polygons_intersect(b["points"], pts):
                new = max(new, block_top(b) + FUNNEL_ABOVE)
    if new <= top + 1e-6:
        return top
    by_id = {f["id"]: f for f in funnels}
    for f in funnels:
        f["top"] = new
    lay.footprints = [(fp, b, new if o in by_id else t, o) for fp, b, t, o in lay.footprints]
    for wt in lay.weights:
        f = by_id.get(wt.name)
        if f and wt.group == "superstructure":
            z0 = f.get("z0", 0.0)
            wt.w = powerplant.funnel_weight(f["w"], f["l"], new - z0, 0.0, 0.0)[0]
            wt.z_rel = ("deck", (z0 + new) / 2)
    return new


# ---------------------------------------------------------------------------
def block_base(b):
    """Height of a superstructure block's floor above the main deck (z0 = what it stands on)."""
    return b.get("z0", 0.0) + LEVEL_H * (b["level"] - 1)


def block_top(b):
    return b.get("z0", 0.0) + LEVEL_H * b["level"]


# Warship and carrier planform. The main deck fills more of its L x B box than the waterplane (navarch.cwp), since
# the sides flare out above water: a parallel midbody, then the rest as bow and stern tapers with one power solved
# for that fill. Big ships are oval (LARGE: at Cb 0.6 close to Dreadnought's deck, fill 0.78 against her 0.76);
# small ones keep straight sides and a wide transom (SMALL: Fletcher, fill 0.83 at Cb 0.5), blended by the deck's
# L x B across PLAN_SIZE m². Small ships are short of deck space anyway.
#   flare: fill above cwp; mid: parallel midbody share of L (LARGE: MIDBODY_K x (Cb - 0.5)); bow_share: the bow's
#   share of the tapers; transom: the stern's end width over the beam
LARGE = dict(flare=0.08, bow_share=0.5, transom=0.1)
SMALL = dict(flare=0.22, mid=0.25, bow_share=0.53, transom=0.75)
MIDBODY_K = 1.5
PLAN_SIZE = (1500.0, 4000.0)


def planform(cb, size_m2):
    """Bow and stern tapers for a deck of size_m2 (L x B) whose plan fills cwp(cb) + flare of its box."""
    from navarch import cwp
    s = min(1.0, max(0.0, (size_m2 - PLAN_SIZE[0]) / (PLAN_SIZE[1] - PLAN_SIZE[0])))
    large = {**LARGE, "mid": min(0.4, max(0.0, (cb - 0.5) * MIDBODY_K))}
    k = {key: SMALL[key] + (large[key] - SMALL[key]) * s for key in SMALL}
    mid, transom = k["mid"], k["transom"]
    bt, st = (1 - mid) * k["bow_share"], (1 - mid) * (1 - k["bow_share"])
    target = min(0.97, cwp(cb) + k["flare"])

    def fill(p):
        return mid + bt * Hull.end_fill(p, "pointed") + st * (transom + (1 - transom) * Hull.end_fill(p, "round"))
    lo, hi = 1.05, 12.0
    for _ in range(30):
        p = (lo + hi) / 2
        lo, hi = (p, hi) if fill(p) < target else (lo, p)
    p = (lo + hi) / 2
    return dict(bow=dict(taper=bt, power=p), stern=dict(taper=st, power=p, transom=transom, shape="round"))


def hull_spec(design):
    h = design["hull"]
    return dict(length=h["length"], beam=h["beam"], **planform(h["block_coefficient"], h["length"] * h["beam"]))


STEERING = (0.03, 0.08, 0.25)   # the steering gear: from 0.03 to 0.08 L forward of the stern, 0.25 B each side


def set_citadel(lay, x0, x1):
    """The citadel: the stretch the vital spaces, belt and citadel armour decks cover (lay.geo["citadel"])."""
    lay.geo["citadel"] = (x0, x1)


def add_steering(lay, x0=None, x1=None, half_width=None, name="Steering gear"):
    """The steering gear over the rudders, for every style: by default STEERING's stretch forward of the stern.
    It stands low, on the inner bottom ordnance.TIERS deck spaces tall, under the armour. Returns the room."""
    L, B = lay.hull.L, lay.hull.B
    x0 = -L / 2 + STEERING[0] * L if x0 is None else x0
    x1 = -L / 2 + STEERING[1] * L if x1 is None else x1
    base, top = ordnance.span(lay.geo["plant"])
    room = dict(id=name, kind="steering", x0=x0, x1=x1, base=base, top=top,
                half_width=STEERING[2] * B if half_width is None else half_width)
    lay.compartments.append(room)
    return room


def finish_layout(lay, design, hs, mounts, turret_types, blocks, funnels, masts, aa_out, fun_top, deck="steel",
                  **extra):
    """The laid-out ship's renderer spec (lay.spec) and its parts on lay, for every style. extra: style-specific
    spec keys (boats, bollards, flight deck, fittings, ...)."""
    lay.spec = dict(
        id=design["id"], name=design.get("name", design["id"]), **{"class": design.get("type", "")},
        length=lay.hull.L, beam=lay.hull.B, bow=hs["bow"], stern=hs["stern"], deck=deck,
        turret_types=turret_types,
        turrets=[dict(id=m["id"], type=m["type"], x=m["x"], y=m["y"], z=m["z"], rest=m["rest"]) for m in mounts],
        superstructure=[{k: v for k, v in b.items() if k not in ("id", "kind") and not k.startswith("_")}
                        for b in blocks],
        funnels=[{k: v for k, v in f_.items() if k not in ("id", "seg", "serves")} for f_ in funnels],
        masts=masts, aa=[{k: v for k, v in a.items() if k not in ("id", "base")} for a in aa_out],
        **extra)
    lay.mounts, lay.blocks, lay.funnels, lay.aa, lay.fun_top = mounts, blocks, funnels, aa_out, fun_top
    import firecontrol
    firecontrol.search_radar(lay, design, blocks, masts, fun_top)
    lay.geo["windage"] = lateral_profile(lay, blocks, funnels, masts, mounts, aa_out, fun_top)
    return lay


WIND_COL = 1.0      # the side profile is summed in columns this long (m)


def lateral_profile(lay, blocks, funnels, masts, mounts, aa, fun_top):
    """What the wind sees from abeam above the main deck: the union of the side views of the superstructure, raised
    decks (a carrier's hangar and flight deck, a merchant's forecastle and poop), funnels, masts, gun mounts and AA,
    so things side by side across the ship count once. Returns dict(area_m2, z_m: the area's centre above the main
    deck), for navarch's wind heel (the hull's own freeboard is added there)."""
    cols = {}

    def add(x0, x1, z0, z1):
        if z1 <= z0 or x1 <= x0:
            return
        for i in range(int(math.floor(x0 / WIND_COL)), int(math.ceil(x1 / WIND_COL))):
            f = (min(x1, (i + 1) * WIND_COL) - max(x0, i * WIND_COL)) / WIND_COL      # share of the column covered
            cols.setdefault(i, []).append((z0, z1, f))

    for b in blocks:
        add(b["x0"], b["x1"], block_base(b), block_top(b))
    for dk in lay.decks:
        xs = [p[0] for p in dk["points"]]
        add(min(xs), max(xs), 0.0, dk["top"])
    for f in funnels:
        add(f["x"] - f["l"] / 2, f["x"] + f["l"] / 2, f.get("z0", 0.0), fun_top)
    for m in masts:
        w = 1.5 if m.get("tripod") else 0.7
        add(m["x"] - w / 2, m["x"] + w / 2, 0.0, m.get("top", fun_top + 6.0))
    for m in mounts:
        if m.get("casemate") or m["top"] <= 0:
            continue
        r = m["t"]["r"]
        add(m["x"] - r, m["x"] + r, 0.0, m["top"])
    for a in aa:
        r = AA_CFG[a["type"]][0]
        add(a["x"] - r, a["x"] + r, a["base"], a["base"] + 2.0)
    area = mom = 0.0
    for spans in cols.values():      # per column: the union of its spans (overlaps count once)
        spans.sort()
        cur = None
        for z0, z1, f in spans:
            if cur and z0 <= cur[1]:
                if z1 > cur[1]:
                    area += (z1 - cur[1]) * f * WIND_COL
                    mom += (z1 - cur[1]) * f * WIND_COL * (cur[1] + z1) / 2
                    cur = (cur[0], z1)
                continue
            cur = (z0, z1)
            area += (z1 - z0) * f * WIND_COL
            mom += (z1 - z0) * f * WIND_COL * (z0 + z1) / 2
    return dict(area_m2=area, z_m=mom / area if area else 0.0)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def turret_name(letters, i):
    """A, B, C, then A4, A5, ... (letters[0] plus the turret's number in its group)."""
    return letters[i] if i < len(letters) else f"{letters[0]}{i + 1}"


def battery_prefix(k):
    """Mount id prefix of the k-th secondary battery: S, SB, SC, ..."""
    return "S" if k == 0 else f"S{chr(ord('A') + k)}" if k < 26 else f"S{k + 1}-"


def place_casemates(lay, mounts, turret_types, blocks, secs, hull, depth):
    """The casemate batteries (secs entries with "mount": "casemate"): single guns at the hull side, each pivoting on
    it, so only its round port shield and barrels show, outboard. Two tiers ("tier"):
      lower (default)  in the hull side, one level below the main deck. Nothing on deck stands in their way: only the
                       hull's shape (they stay where the hull is at least CASEMATE_BEAM of its full width), the main
                       barbettes going down through the hull, and each other.
      upper            on the main deck, each in an armoured housing (a level-1 block) against the deck edge; housings
                       close together join into one gallery. They keep clear of what stands on the main deck, of the
                       main turrets' sweeps, and of the lower tier's shields: the tiers stagger, so every gun shows.
    The lower tier fills first, then the upper. Within a tier the batteries fill in list order, each taking the free
    places nearest amidships: all at a comfortable pitch if every gun fits so, else with the lower guns just far
    enough apart for an upper gun between each pair, else closer."""
    import armament     # armament imports layout
    from geometry import CASEMATE_SHIELD
    bats = []
    for sec in secs:
        n = sec.get("per_side", sec.get("count", 0) // 2)
        if sec.get("mount") == "casemate" and n:
            t_id, t = make_turret_type(sec["calibre_mm"], sec["calibre_length"], sec["barrels"], kind="casemate")
            turret_types[t_id] = t
            bats.append((sec, n, t_id, t, sec.get("tier", "lower") == "upper"))
    if not bats:
        return
    bats.sort(key=lambda bt: bt[4])     # the lower tier first (a stable sort keeps the list order within a tier)
    B = hull.B
    barbettes = [m for m in mounts if m["kind"] == "main" and m["t"].get("barbette", True)]

    def lower_ok(x, rc):
        hw = hull.half_width(x)
        if hw < CASEMATE_BEAM * B / 2 or hw - 2 * rc < 0.5:
            return False
        boxes = [_fp_rect(x - rc, hw - 2 * rc, x + rc, hw), _fp_rect(x - rc, -hw, x + rc, -hw + 2 * rc)]
        return not any(_overlap(bx, _fp_circle(m["x"], m["y"], 0.95 * m["t"]["r"]), 0.3)
                       for bx in boxes for m in barbettes)

    def housing(x0, x1, rc):
        """(outer y, depth) of an upper-tier housing from x0 to x1: against the deck edge, inside the hull."""
        yo = min(hull.half_width(x0 + (x1 - x0) * k / 8) for k in range(9)) - 0.3
        return yo, 1.6 * rc

    def upper_ok(x, rc):
        if hull.half_width(x) < CASEMATE_BEAM * B / 2:
            return False
        x0, x1 = x - 1.05 * rc, x + 1.05 * rc
        yo, d = housing(x0, x1, rc)
        if yo - d < 0.5:
            return False
        for side in (1, -1):
            fp = _fp_rect(x0, yo - d, x1, yo) if side > 0 else _fp_rect(x0, -yo, x1, -yo + d)
            # what stands on the main deck below the housing's roof blocks it; the deckhouse doesn't (the housing
            # joins it) and nor does anything below the deck
            if any(_overlap(fp, o[0], 0.3) for o in lay.footprints
                   if o[3] != "Deckhouse" and o[1] < LEVEL_H - 0.01 and o[2] > 0.01):
                return False
            if not lay.clear(fp, LEVEL_H):
                return False
        return True

    xs = [0.5 * k for k in range(int(-hull.L), int(hull.L) + 1)]
    elig = [x for x in xs if hull.half_width(x) >= CASEMATE_BEAM * B / 2]
    # centred on the hull's full-width part, moved with the arrangement's balancing shift
    c = ((min(elig) + max(elig)) / 2 if elig else 0.0) + lay.geo.get("shift", 0.0)
    xs.sort(key=lambda x: abs(x - c))
    ok_cache = {}

    r_up = max([t["r"] for _, _, _, t, up in bats if up], default=0.0)

    def attempt(mode):
        def half(r, upper):   # half the pitch
            if mode == "pref":
                return 1.1 * r + 2.0
            if mode == "stagger" and not upper:   # room between lower guns for one upper gun's housing
                return max(1.05 * r + 0.5, 1.05 * r_up + CASEMATE_SHIELD * r + 0.3)
            return 1.05 * r + 0.5
        taken = {False: [], True: []}    # per tier: (x, half pitch)
        shields = []                     # the lower tier's shields: (x, radius)
        out = []
        for sec, n, t_id, t, upper in bats:
            rc = t["r"]
            h = half(rc, upper)
            got = []
            for x in xs:
                if len(got) >= n:
                    break
                if not all(abs(x - xo) >= h + ho for xo, ho in taken[upper]):
                    continue
                if upper and not all(abs(x - xs_) >= 1.05 * rc + rs_ + 0.3 for xs_, rs_ in shields):
                    continue
                key = (x, rc, upper)
                if key not in ok_cache:
                    ok_cache[key] = (upper_ok if upper else lower_ok)(x, rc)
                if ok_cache[key]:
                    got.append(x)
                    taken[upper].append((x, h))
            if not upper:
                shields += [(x, CASEMATE_SHIELD * rc) for x in got]
            out.append(sorted(got))
        return out

    # comfortable pitch; else lower guns spaced to stagger with the upper tier; else close. Failing all, the most guns
    best = None
    for mode in ("pref", "stagger", "min") if r_up else ("pref", "min"):
        placed = attempt(mode)
        if all(len(got) >= bt[1] for got, bt in zip(placed, bats)):
            break
        if best is None or sum(map(len, placed)) > sum(map(len, best)):
            best = placed
    else:
        placed = best
    galleries = []    # upper-tier housings: [x0, x1, yo, depth, ids]
    lower_x = [x for got, bt in zip(placed, bats) if not bt[4] for x in got]
    for got, (sec, n, t_id, t, upper) in zip(placed, bats):
        if len(got) < n:
            lay.fail("length", f"Only {len(got)} of {n} {sec['calibre_mm']:g} mm {'upper ' if upper else ''}casemates "
                               f"per side fit {'on deck' if upper else 'in the hull sides'}. "
                               "Use fewer or smaller guns.")
        arm, rc = sec.get("armour_mm", 25), t["r"]
        for i, x in enumerate(got):
            if upper:
                yo, d = housing(x - 1.05 * rc, x + 1.05 * rc, rc)
                galleries.append([x - 1.05 * rc, x + 1.05 * rc, yo, d])
            else:
                yo = hull.half_width(x)
            base, top = (0.0, LEVEL_H) if upper else (-LEVEL_H, 0.0)
            for side in (1, -1):
                mid = f"{sec['prefix']}{i + 1}{'S' if side > 0 else 'P'}"
                armament.add_mount(lay, mounts, "secondary", t_id, t, mid, x, side * yo, base, 90 * side, 0,
                                   armour_mm=arm, depth=depth, top=top, footprint_r=CASEMATE_SHIELD * rc,
                                   casemate=True, material=sec.get("material"))
    # housings close together (no lower shield between them) join into one gallery, its outer face the innermost
    galleries.sort()
    merged = []
    for g in galleries:
        if merged and g[0] - merged[-1][1] < 1.5 and not any(merged[-1][1] <= x <= g[0] for x in lower_x):
            m = merged[-1]
            m[1], m[2], m[3] = max(m[1], g[1]), min(m[2], g[2]), max(m[3], g[3])
        else:
            merged.append(list(g))
    for k, (x0, x1, yo, d) in enumerate(merged):
        for side in (1, -1):
            add_block(lay, blocks, f"Casemate housing {k + 1}{'S' if side > 0 else 'P'}", x0, x1, d, 1,
                      0.3, 0.3, y=side * (yo - d / 2))


def stepped_counts(main):
    """How many turrets of the fore and aft groups step up (superfire); the rest of a group sits flush on
    deck behind them and fires to the sides only. main["superfire"]: true (default, all), false (none: a
    single flush end turret per group), or {"fore": k, "aft": k}."""
    sf = main.get("superfire", True)
    nf, na = main.get("fore", 0), main.get("aft", 0)
    if sf is True:
        return nf, na
    if sf is False:
        return min(nf, 1), min(na, 1)
    return sf.get("fore", nf), sf.get("aft", na)


def deckhouse_levels(design):
    """superstructure.deckhouse_levels: how many levels the deckhouse amidships has (1 when the design gives none)."""
    return int((design.get("superstructure") or {}).get("deckhouse_levels", 1))


# Superstructure levels. Every warship level (the 01 deckhouse, the deckhouse levels over it, the bridge tower and the
# aft control) is one block made by add_level from the same rules: the caller gives its intent (a core x0..x1, w
# wide, on the centreline, and which ends may grow toward the end turrets), level_outline shapes it.
DH_INSET = 0.6         # level 1 stands on the deck: its sides follow the deck edge this far in
DH_TURRET_CLEAR = 1.0  # every level's ends keep this far from an end turret's body (its swing zone is kept out too)
DH_FIT = 0.375         # an end's shape is fitted on stations this far apart across the ship
DH_STEP_COST = 3.0     # m2 (on one side) a swept end must win over a flat one to be worth its corners
DH_MIN_FACE = 1.5      # m: the narrowest face a swept end has (else it comes to a point)
DH_MIN_DROP = 0.75     # m: a sweep falls back at least this far, or the end is flat
FP_MARGIN = 0.3        # what stands at a level's height is kept this far from its ends


def deck_band(lay):
    """The main deck less DH_INSET at the sides, as a convex polygon: what level 1 stands on (cached on the layout)."""
    if getattr(lay, "_deck_band", None) is None:
        hull = lay.hull
        xa, xb = -hull.L / 2, hull.L / 2
        k = max(2, int(xb - xa))
        xs = [xa + (xb - xa) * i / k for i in range(k + 1)]
        band = _thin([(x, hull.half_width(x) - DH_INSET) for x in xs if hull.half_width(x) - DH_INSET > 0.1], 0.05)
        lay._deck_band = _convex_hull(band + [(x, -y) for x, y in band[::-1]])
    return lay._deck_band


def _convex_hull(pts):
    """Andrew's monotone chain: the convex hull of the points, counter-clockwise."""
    pts = sorted(set(pts))
    if len(pts) < 3:
        return pts

    def half(seq):
        out = []
        for p in seq:
            while len(out) >= 2 and ((out[-1][0] - out[-2][0]) * (p[1] - out[-2][1]) -
                                     (out[-1][1] - out[-2][1]) * (p[0] - out[-2][0])) <= 0:
                out.pop()
            out.append(p)
        return out
    lower, upper = half(pts), half(pts[::-1])
    return lower[:-1] + upper[:-1]


def _fp_intervals(fp, y, margin):
    """Where the line across the ship at y crosses a footprint grown by margin: [(x0, x1)]."""
    if fp[0] == "c":
        dy = y - fp[2]
        r = fp[3] + margin
        if abs(dy) >= r:
            return []
        h = math.sqrt(r * r - dy * dy)
        return [(fp[1] - h, fp[1] + h)]
    if fp[0] == "r":
        return [(fp[1] - margin, fp[3] + margin)] if fp[2] - margin < y < fp[4] + margin else []
    if not fp[3] - margin < y < fp[5] + margin:
        return []
    pts = fp[1]
    xs = [x0 + (y - y0) * (x1 - x0) / (y1 - y0) for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1])
          if (y0 > y) != (y1 > y)]
    return [(min(xs) - margin, max(xs) + margin)] if xs else []


def level_outline(lay, x0, x1, w, base, top, support=None, grow=(False, False), keep=(), ignore=(), notches=()):
    """A superstructure level's outline: a room laid out like a deck, not a slab. It stands on its support (a convex
    polygon: the level below, or the deck band for level 1) and is clipped to it, so its sides follow the level below
    and, at the bottom, the deck edge. Its ends start at x0 / x1 and are shaped by what lies beyond them:
      - the end turrets' bodies (plus DH_TURRET_CLEAR) and their barrels' swing, at any height (blast and swing),
      - every other turret's sweep lower than its roof (top),
      - whatever stands at its height (lay.footprints overlapping base .. top, FP_MARGIN clear; ignore: ids it may
        enclose, such as funnels).
    Inside a turret's blind arc that makes a nose pointing at the turret. An end may grow outward (grow: (aft, fwd))
    only toward an end turret, as far as its body allows on the centreline; it always reaches far enough to carry the
    bounding boxes in keep (what stands on its roof). Each end is convex and symmetric: flat, or a face across the
    ship (at least DH_MIN_FACE wide, or none: a point) with one straight sweep from each edge back to the side, as
    shallow as the obstacles allow. A sweep must fall back DH_MIN_DROP and add DH_STEP_COST m2 a side over the flat
    end. What lies in a notch's bite (notches: (x0, x1, half-width), cut by notch_outline) doesn't shape the ends.
    Returns the polygon (empty if the support leaves nothing)."""
    import armament     # armament imports layout
    support = support or deck_band(lay)
    sup = _Slabs(support)
    H = w / 2
    st = DH_FIT
    n = max(1, int(math.ceil(H / st - 1e-6)))
    ys = [min(H, j * st) for j in range(n + 1)]
    floor = -0.3 * (x1 - x0)
    ends = getattr(lay, "end_mounts", [])
    scan = lay.__dict__.setdefault("_scan", {})
    end_ids = {m["id"] for m in ends}
    fps = [o[0] for o in lay.footprints if o[2] > base + 1e-6 and o[1] < top - 1e-6 and o[3] not in ignore
           and o[3] not in end_ids]
    prof = {}
    for e, xc, may_grow in ((1, x1, grow[1]), (-1, x0, grow[0])):
        uc = e * xc
        ms = [m for m in ends if e * (m["x"] - xc) > 0]
        rad = {m["id"]: armament.body_reach(m["t"]) + DH_TURRET_CLEAR for m in ms}
        cap = max(0.0, min((e * (m["x"] - xc) - rad[m["id"]] for m in ms), default=0.0)) if may_grow else 0.0
        req = [floor] * (n + 1)
        for bx0, by0, bx1, by1 in keep:     # what stands on the roof must stay on it
            far = max(e * bx0, e * bx1) - uc + 0.3
            for j, y in enumerate(ys):
                if any(lo - st <= s * y <= hi + st for s in (1, -1) for lo, hi in ((by0, by1),)):
                    req[j] = max(req[j], far)
        cap = max(cap, max(req))
        lo_u, hi_u = uc + floor, uc + cap + FP_MARGIN

        def near(xa, xb):     # an obstacle reaching into the end's zone (u from uc + floor to uc + cap)
            ua, ub = sorted((e * xa, e * xb))
            return ub > lo_u and ua < hi_u
        owners = {m["id"] for m in ms}
        polys = [(p, bx) for sw in lay.sweeps if sw["owner"] in owners or (sw["axis"] < top and sw["owner"] not in end_ids)
                 for p, bx in zip(sw["polys"], sw["boxes"]) if near(bx[0], bx[2])]
        circles = [(m["x"], m["y"], rad[m["id"]]) for m in ms if near(m["x"] - rad[m["id"]], m["x"] + rad[m["id"]])]
        near_fps = [fp for fp in fps if near(_bbox(fp)[0] - FP_MARGIN, _bbox(fp)[2] + FP_MARGIN)]
        if not (polys or circles or near_fps) and max(req) <= cap:    # nothing near: flat, as far out as it may
            prof[e] = [(e * (uc + cap), 0.0), (e * (uc + cap), H)]
            continue

        def raw(y):
            """How far the end may move out (negative: in) along the line at y."""
            ivs = []
            for p, (a0, b0, a1, b1) in polys:
                if b0 <= y <= b1:
                    key = (id(p), y)      # sweeps stay put through the layout: their scanlines are shared
                    if key not in scan:
                        xs = sorted(px + (y - py) * (qx - px) / (qy - py)
                                    for (px, py), (qx, qy) in zip(p, p[1:] + p[:1]) if (py > y) != (qy > y))
                        scan[key] = [(xs[i], xs[i + 1]) for i in range(0, len(xs) - 1, 2)]
                    ivs += scan[key]
            for cx, cy, r in circles:
                if abs(y - cy) < r:
                    h = math.sqrt(r * r - (y - cy) ** 2)
                    ivs.append((cx - h, cx + h))
            for fp in near_fps:
                ivs += _fp_intervals(fp, y, FP_MARGIN)
            d = cap
            for xa, xb in ivs:
                if any(xa < n1 and n0 < xb and abs(y) > h - 1e-6 for n0, n1, h in notches):
                    continue      # in a notch's bite (found cell by cell, so exactly): notch_outline cuts it out
                ua, ub = sorted((e * xa, e * xb))
                if ub > uc + floor:
                    d = min(d, ua - uc - 0.3)
            return max(floor, d)
        A = [max(min(raw(y), raw(-y)), r) for y, r in zip(ys, req)]
        # where the support already cuts the station off, the end is free (the clip trims it); looked for from the
        # end's innermost limit out (farther in, a station cut off counts as cut off there)
        d_in = max(floor, min(A) - st)
        dgrid = [d_in + st * i for i in range(int((cap - d_in) / st) + 1)] + [cap]
        hws = []
        for d in dgrid:
            spans = sup.at(e * (uc + d))
            hws.append(min((min(-a, b) for a, b in spans if a <= 0 <= b), default=-1.0))
        E = [next((d for d, hw in zip(dgrid, hws) if hw < y - 1e-9), cap) for y in ys]
        Aeff = [min(cap, cap if Ej <= Aj else Aj) for Aj, Ej in zip(A, E)]
        # a face across the ship out to y_a, then one straight sweep back to the side: the end is convex, with
        # at most two corners a side (a flat end has none, a pointed one only the sweep)
        best = None
        face_min = int(math.ceil(DH_MIN_FACE / 2 / st - 1e-9))
        for i in [0] + list(range(max(1, face_min), n + 1)):
            d0 = min(Aeff[:i + 1])
            if any(r > d0 + 1e-9 for r in req[:i + 1]):
                continue
            ya, d1, lo = ys[i], d0, -math.inf
            for k in range(i + 1, n + 1):   # the shallowest sweep that keeps clear, and deep enough for keep
                t = (ys[k] - ya) / (H - ya)
                if Aeff[k] < d0:
                    d1 = min(d1, d0 - (d0 - Aeff[k]) / t)
                if req[k] > floor:
                    lo = max(lo, d0 - (d0 - req[k]) / t)
            if d1 < lo - 1e-9 or d1 < floor:
                continue
            if d0 - d1 < DH_MIN_DROP and i < n:   # hardly a sweep: the flat end (i == n) covers it
                continue
            f = [d0 if k <= i else d0 - (d0 - d1) * (ys[k] - ya) / (H - ya) for k in range(n + 1)]
            area = sum(min(fk, Ek) * (st if 0 < k < n else st / 2) for k, (fk, Ek) in enumerate(zip(f, E)))
            score = area - (DH_STEP_COST if i < n else 0.0)
            if best is None or score > best[0] + 1e-6:
                best = (score, [(0.0, d0), (H, d0)] if i == n else ([(0.0, d0)] if i else []) + [(ya, d0), (H, d1)])
        if best is None:      # nothing fits: square, as far out as what stands on it needs
            best = (0.0, [(0.0, max(req)), (H, max(req))])
        prof[e] = [(e * (uc + d), y) for y, d in best[1]]
    half = prof[1] + prof[-1][::-1]          # starboard: the forward end out to the side, then the aft end back in
    pts = half + [(x, -y) for x, y in half[::-1]]
    return clip_convex(simplify_polygon(pts), support)


BEVEL_OUTER = (3.0, 0.22)   # m, share of the level's width: the facets on the end facing the nearer end of the ship
BEVEL_INNER = (0.8, 0.07)   # and the small cuts on the other corners


def bevel_outline(pts, keep=(), flush=()):
    """Chamfers a level's near-square corners (interior angle 60-120 deg; swept ends and points are left alone), so
    no level is a plain box: a big facet on the end facing the nearer end of the ship (the bridge front, the aft
    control's back), a small cut elsewhere. A corner is kept where something in keep (bounding boxes of what stands
    on the roof) comes within the cut, and on an end that butts flush against another block (flush: its x)."""
    if len(pts) < 3:
        return pts
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    w, xm = max(ys) - min(ys), (min(xs) + max(xs)) / 2
    out = []
    for i, b in enumerate(pts):
        a, c = pts[i - 1], pts[(i + 1) % len(pts)]
        ua, uc = (a[0] - b[0], a[1] - b[1]), (c[0] - b[0], c[1] - b[1])
        la, lc = math.hypot(*ua), math.hypot(*uc)
        if la < 1e-6 or lc < 1e-6 or abs(ua[0] * uc[0] + ua[1] * uc[1]) > 0.5 * la * lc or \
                any(abs(b[0] - xf) < 1e-3 for xf in flush):
            out.append(b)
            continue
        outer = (b[0] - xm) * (1 if xm >= 0 else -1) > 0
        cap, frac = BEVEL_OUTER if outer else BEVEL_INNER
        size = min(cap, frac * w, 0.4 * la, 0.4 * lc)
        if size < 0.25 or any(bx0 - size < b[0] < bx1 + size and by0 - size < b[1] < by1 + size
                              for bx0, by0, bx1, by1 in keep):
            out.append(b)
            continue
        out += [(b[0] + ua[0] / la * size, b[1] + ua[1] / la * size),
                (b[0] + uc[0] / lc * size, b[1] + uc[1] / lc * size)]
    return out


def add_level(lay, blocks, bid, level, x0, x1, w, support=None, grow=(False, False), keep=(), ignore=(),
              notches=(), joins=(None, None)):
    """One superstructure level as a block, shaped by level_outline (support: the polygon it stands on, the deck band
    by default), bevelled (bevel_outline) and narrowed at its notches (notch_outline). Returns the block, or None if
    nothing of it stands on its support. A notched block keeps its convex outline (_support) for the level above to
    stand on, and its notches (_notches) for that level to keep. joins: (aft, fwd) ids of the blocks an end butts
    flush against (that end stays flat at x0 / x1, unbevelled, and doesn't keep clear of the block)."""
    base, top = LEVEL_H * (level - 1), LEVEL_H * level
    joined = [j for j in joins if j]
    pts = level_outline(lay, x0, x1, w, base, top, support, grow, keep, list(ignore) + joined, notches)
    pts = bevel_outline(pts, keep, flush=[x for x, j in zip((x0, x1), joins) if j])
    if len(pts) < 3 or polygon_centroid(pts)[0] < 1.0:
        return None
    convex = pts
    if notches:
        pts = notch_outline(pts, notches)
    b = add_block(lay, blocks, bid, x0, x1, w, level, 0.0, 0.0, points=pts)
    if notches:
        b["_support"], b["_notches"] = [list(p) for p in convex], list(notches)
    return b


def notch_outline(pts, notches):
    """A convex outline narrowed to half-width h along x0 .. x1 for each notch (x0, x1, h), symmetric about the
    centreline, with 45-degree shoulders outside that stretch: a bite out of each side where something on the roof
    below stands in the way, so the level runs on in one piece."""
    sl = _Slabs(pts)
    xs_v = sorted({x for x, _ in pts})
    xa, xb = xs_v[0], xs_v[-1]

    def cap(x):
        return min((h + max(0.0, n0 - x, x - n1) for n0, n1, h in notches), default=math.inf)

    def span(x):
        sp = sl.at(min(max(x, xa + 1e-6), xb - 1e-6))
        return (min(a for a, _ in sp), max(b for _, b in sp)) if sp else (0.0, 0.0)
    brk = set(xs_v)
    for n0, n1, h in notches:
        lo_, hi_ = span((n0 + n1) / 2)
        reach = max(hi_, -lo_) - h
        brk |= {n0, n1, n0 - reach, n1 + reach}
    brk = sorted(x for x in brk if xa <= x <= xb)
    up = lambda x: min(span(x)[1], cap(x))
    dn = lambda x: max(span(x)[0], -cap(x))
    xs = []
    for a, b in zip(brk, brk[1:]):     # both sides are piecewise linear between breaks: add where they cross
        xs.append(a)
        for f, g in ((lambda x: span(x)[1], cap), (lambda x: -span(x)[0], cap)):
            da, db = f(a) - g(a), f(b) - g(b)
            if da * db < 0:
                xs.append(a + (b - a) * da / (da - db))
    xs = sorted(set(xs + [brk[-1]]))
    top = [(x, up(x)) for x in xs]
    bot = [(x, dn(x)) for x in xs[::-1]]
    return simplify_polygon(bot[-1:] + top + bot[:-1]) if top else pts


DH_CELL = 0.5          # deckhouse levels are found in cells this long
DH_MIN_RUN = 3.0       # and kept where at least this long
DH_MIN_W = 3.0         # nor narrower than this
DH_NOTCH_MIN = 0.5     # a break in a level narrows it (a notch) to no less than this share of its width,
DH_NOTCH_STEP = 0.25   # found in steps this fine; else the level stops there and goes on as another block
DH_JOIN = 1.5          # m: a level's end this close to a tower block at its height runs on to butt flush against it
DH_KEEP = 0.7          # a level is as wide as it can be while keeping this share of the length it has at
                       # DH_MIN_W: nearly all, so it runs on in one piece between the secondaries


def add_deckhouse_levels(lay, blocks, n, x0, x1, dh, dh_w, through=(), base_block=None):
    """The deckhouse's levels above the first, up to level n, over the middle (x0 .. x1): room for the crew above the
    hull, at the price of topweight and windage. Each level stands on the one below, keeps out of what stands on that
    roof (secondaries, wing and midships turrets, the bridge and aft control) and of the guns' sweeps, and wraps
    around the funnels (through: ids it may enclose). It is as wide as it can be while keeping most of its length
    (DH_KEEP), and never wider than the level below. A narrow ship whose deckhouse is only under the bridge first
    carries it on along the middle where the deck is free. Each run of cells is the core of a level (add_level) on
    the block below it (base_block: the level-1 deckhouse), Deckhouse k[-i]."""
    if n <= 1:
        return []
    hull = lay.hull
    cells = [x0 + DH_CELL * i for i in range(int((x1 - x0) / DH_CELL))]
    made = []

    def ok(x, w, base, top, support):
        if support is not None and not support(x):
            return False
        hw = min(hull.half_width(x), hull.half_width(x + DH_CELL)) - 0.6
        if w / 2 > hw:
            return False
        fp = _fp_rect(x, -w / 2, x + DH_CELL, w / 2)
        return lay.free_at(fp, base, top, 0.3, through) and lay.clear(fp, top)

    def runs(w, base, top, support):
        out, start = [], None
        for x in cells + [None]:
            if x is not None and ok(x, w, base, top, support):
                start = x if start is None else start
                continue
            if start is not None:
                end = (x if x is not None else cells[-1] + DH_CELL)
                if end - start >= DH_MIN_RUN - 1e-6:
                    out.append((start, end))
                start = None
        return out

    def level(k, w_max, support, skip=None, under=()):
        base, top = LEVEL_H * (k - 1), LEVEL_H * k
        sup = (lambda x: support(x) and not skip(x)) if skip else support
        if w_max < DH_MIN_W:
            return [], 0.0
        total = lambda rr: sum(b - a for a, b in rr)
        floor = total(runs(DH_MIN_W, base, top, sup))
        if floor <= 0:
            return [], 0.0
        lo, hi = DH_MIN_W, w_max          # the widest that keeps DH_KEEP of the length
        if total(runs(hi, base, top, sup)) >= DH_KEEP * floor:
            lo = hi
        while hi - lo > 0.25:
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if total(runs(mid, base, top, sup)) >= DH_KEEP * floor else (lo, mid)
        out = []

        def pieced(lo):
            """The level's runs at width lo, a break bridged by a notch where a narrower width clears it."""
            pieces, notches = [], []
            for a, b in runs(lo, base, top, sup):
                if pieces:
                    g0 = pieces[-1][1]
                    gap = [x for x in cells if g0 - 1e-6 <= x < a - 1e-6]
                    wn = lo - DH_NOTCH_STEP
                    while wn >= max(DH_MIN_W, DH_NOTCH_MIN * lo) and not all(ok(x, wn, base, top, sup) for x in gap):
                        wn -= DH_NOTCH_STEP
                    if wn >= max(DH_MIN_W, DH_NOTCH_MIN * lo):
                        pieces[-1][1] = b
                        notches.append((g0, a, wn / 2))
                        continue
                pieces.append([a, b])
            return pieces, notches
        pieces, notches = pieced(lo)
        for _ in range(8):      # a bite too shallow to show: the whole level that much narrower instead
            shallow = [2 * h for _, _, h in notches if lo / 2 - h < DH_MIN_DROP]
            if not shallow:
                break
            lo = min(shallow)
            pieces, notches = pieced(lo)
        # what a level's end may butt flush against: the bridge tower's and aft control's blocks at its level,
        # across the centreline, within DH_JOIN
        towers = [t for t in blocks if abs(block_base(t) - base) < 1e-6 and t.get("kind") == "superstructure"
                  and not t["id"].startswith("Deckhouse") and abs(t["y"]) < t["w"] / 2]
        for a, b in pieces:     # each run a level (add_level) on the block it stands on
            j_aft = next((t for t in towers if a - DH_JOIN <= t["x1"] <= a + 1e-6), None)
            j_fwd = next((t for t in towers if b - 1e-6 <= t["x0"] <= b + DH_JOIN), None)
            a, b = (j_aft["x1"] if j_aft else a), (j_fwd["x0"] if j_fwd else b)
            on_ = max(under, key=lambda u: min(b, u["x1"]) - max(a, u["x0"]), default=None)
            mine = [n for n in notches if a <= n[0] and n[1] <= b] + \
                   [n for u in under for n in u.get("_notches", []) if n[1] > a and n[0] < b]   # kept from below
            blk = add_level(lay, blocks, f"Deckhouse {k}" + ("" if not out else f"-{len(out) + 1}"), k, a, b, lo,
                            support=on_ and on_.get("_support", on_["points"]), ignore=through, notches=mine,
                            joins=(j_aft and j_aft["id"], j_fwd and j_fwd["id"]))
            if blk:
                made.append(blk)
                out.append(blk)
        return out, lo

    on = lambda bb: (lambda x: any(b["x0"] <= x and x + DH_CELL <= b["x1"] + 1e-6 for b in bb))
    below = [base_block]
    w = dh_w
    if dh["x1"] - dh["x0"] < 0.5 * (x1 - x0):      # a narrow ship: the deckhouse goes on along the middle first
        ext, w1 = level(1, dh_w, lambda x: True, skip=on(below))
        below += ext
    for k in range(2, n + 1):
        below, w = level(k, w, on(below), under=below)
        if not below:
            lay.warnings.append(f"Only {k - 1} of {n} deckhouse levels fit amidships.")
            break
    return made


def tower_levels(design, default):
    """superstructure.tower_levels: the bridge tower's (or island's) top level; default when the design gives none."""
    return int((design.get("superstructure") or {}).get("tower_levels", default))


def build_layout(design: dict, res, shift: float = 0.0) -> Layout:
    import armament     # armament imports layout
    import firecontrol
    shp, depth = res.power_shp, res.depth
    lay = Layout(design)
    hs = hull_spec(design)
    hull = Hull(hs)
    lay.hull = hull
    L, B = hull.L, hull.B
    armour = design.get("armour", {})
    deck = design.get("deck", "wood" if L >= 150 else "steel")

    # ---------------- main battery groups ----------------
    main = design.get("main") or {}
    nf, na, nm = main.get("fore", 0), main.get("aft", 0), main.get("mid", 0)
    nw, echelon = main.get("wing", 0), bool(main.get("echelon", False))   # wing turret pairs
    tm_id, tm = (make_turret_type(main["calibre_mm"], main["calibre_length"], main["barrels"])
                 if (nf + na + nm + nw) else (None, None))
    r = tm["r"] if tm else 0.0
    reach = max(r, turret_reach({**tm, "barrel_len": 0}) if tm else 0.0)  # body+ears, not barrels
    th = turret_height(tm) if tm else 0.0
    s_main = 2.2 * r + 3.0
    gap = 2.0 + 0.5 * r
    R_main = turret_reach(tm) + 0.5 if tm else 0.0        # muzzle reach: what a stowed turret's barrels cover
    n_step_f, n_step_a = stepped_counts(main)
    flush_f, flush_a = nf > max(n_step_f, 1), na > max(n_step_a, 1)   # a flush turret ends the group

    plan_machinery(lay, design, res, hull)
    plant = lay.geo["plant"]
    lb = clamp(0.05 * L + 2, 7, 18)                 # bridge length
    la = 0.045 * L + 2 if L >= 130 else 0.0         # aft control position length
    # the bridge tower: base levels from level 2, the navigating bridge, then each level up to
    # superstructure.tower_levels, the main director on top; funnels stand as tall as a tower of up to 4 levels.
    # nb_need: the first level that sees over the highest forward turret's roof (bridge_level)
    fwd_tier = min(nf, max(n_step_f, 1)) - 1 if (tm and nf) else None    # the forward group's top tier
    fwd_roof = 1.2 + fwd_tier * superfire_step(th) + th if fwd_tier is not None else None
    nb_need = bridge_level(fwd_roof)
    # the aft control looks aft over the aft group the same way: its level by the same rule, an upper level over it
    aft_tier = min(na, max(n_step_a, 1)) - 1 if (tm and na) else None
    na_lvl = bridge_level(1.2 + aft_tier * superfire_step(th) + th if aft_tier is not None else None)
    # superstructure.tower_levels is the tower's height, a slider: the bridge stands as high in it as leaves the levels
    # over it (Bridge upper, Tower n: the compass platform and director tower, 1 level, 2 from 180 m), and never below
    # nb_need. A tall tower makes a tall tower bridge over its base levels (Nelson: about level 8 of 10); a tower too
    # low for the view puts the bridge on its top level, with a warning
    over = 2 if L >= 180 else 1
    n_tower = tower_levels(design, nb_need + over)
    nb = min(n_tower, max(nb_need, n_tower - over))
    if nb < nb_need:
        lay.warnings.append(
            f"The bridge (level {nb}, its deck {LEVEL_H * (nb - 1):.1f} m above the main deck) cannot see over "
            f"turret {turret_name('ABC', fwd_tier)}'s roof ({fwd_roof:.1f} m): superstructure.tower_levels "
            f"{nb_need} or more lifts it clear.")
    lay.geo["bridge"] = dict(level=nb, floor=LEVEL_H * (nb - 1), need=nb_need, tower=n_tower,
                             turret_roof=fwd_roof)
    hood = firecontrol.HOOD_H if firecontrol.spec(design)["main"]["directors"] else 0.0
    wide = B >= 15

    # ---------------- the middle's plan: machinery, funnels, midships and wing turrets ----------------
    # The machinery block (boiler rooms, engine rooms, bunkers; powerplant.segments) runs forward to aft under the
    # middle. Midships turrets (T) and echelon wing pairs (W) stand in gaps between its segments, over their
    # magazines: more of them than gaps splits the longest boiler group, which then needs its own funnels.
    segs = [list(s) for s in plant["segments"]]
    n_gaps = nm + (nw if echelon else 0)
    main_kind = "boiler" if any(k == "boiler" for k, _ in segs) else "engine"

    def candidates():
        """Gaps next to the boilers (engines-only plants: engine rooms): between boiler groups, or between the
        boilers and the engine rooms or bunkers (Lion's and Kongo's Q turret)."""
        return [i for i in range(1, len(segs)) if main_kind in (segs[i - 1][0], segs[i][0])]

    while len(candidates()) < n_gaps:
        i = max((i for i, (k, _) in enumerate(segs) if k == main_kind), key=lambda i: segs[i][1])
        segs[i:i + 1] = [[main_kind, segs[i][1] / 2], [main_kind, segs[i][1] / 2]]
    cands = candidates()
    gaps = sorted({cands[min(len(cands) - 1, int((k + 0.5) * len(cands) / n_gaps))] for k in range(n_gaps)})
    for c in cands:                # rounding collided: take the free candidates in order
        if len(gaps) >= n_gaps:
            break
        if c not in gaps:
            gaps = sorted(gaps + [c])
    gap_kind = {}
    t_gaps = [gaps[round((k + 0.5) * len(gaps) / nm - 0.5)] for k in range(nm)] if nm else []
    for g in gaps:
        gap_kind[g] = "T" if g in t_gaps else "W"
    # the grouped magazines (magazine_plan) stand at the ends of the machinery block, as wide as its space
    mag_plan = magazine_plan(design, tm)
    mag_l = {g: ordnance.zone_length(sum(n * v_ for _, n, v_ in v), plant["width"], plant) if v else 0.0
             for g, v in mag_plan.items()}
    if mag_l["fore"] > 0:
        segs.insert(0, ["magazine", mag_l["fore"]])
        gap_kind = {g + 1: k for g, k in gap_kind.items()}
    if mag_l["aft"] > 0:
        segs.append(["magazine", mag_l["aft"]])
    # funnels: enough for the gas, each within reach of its boilers (powerplant.funnel_plan). Natural and boost
    # draught want a tall stack: at least STACK_NATURAL from the grates to the funnel top.
    fun_top = LEVEL_H * min(n_tower, 4) + FUNNEL_ABOVE
    below = depth - plant["inner_bottom"] - 1.0          # grates to the main deck
    if res.plant["tech"]["draught"]["system"] in ("natural", "forced_boost"):
        fun_top = max(fun_top, STACK_NATURAL - below)
    groups = [s[1] for s in segs if s[0] == "boiler"]
    nfun, fw, fl = plan_funnels(lay, design, res, B, fun_top, groups)
    fplan = lay.geo["funnel_plan"]
    fw = min(fw, 0.3 * B)
    # a midships turret's slot among the funnels: barrels stowed along the centreline one way, and on the other
    # side enough room that its neighbour stays out of the beam arcs
    beam_tan = math.tan(math.radians(90.0 - ARC_BEAM))
    s_mid = max(reach + 1.0, 0.55 * fw / beam_tan + 0.5) + R_main + 1.5
    # torpedo mounts on narrow hulls stand on the centreline between the funnels
    f_min = fl + (9.6 if ((design.get("torpedoes") or {}).get("mounts", 0) and not wide) else 2.0)

    # the plan, forward to aft: funnels (F, over a boiler group), open machinery (E: engine rooms, bunkers),
    # midships turrets (T) and wing turret pairs (W). Abreast pairs go to the ends of the middle (Dreadnought,
    # Nassau), echelon pairs into gaps among the machinery (Invincible)
    seq, seg_of, widths0 = [], [], []
    g_i = 0
    for si, (kind, seg_l) in enumerate(segs):
        if si in gap_kind:
            seq.append(gap_kind[si])
            seg_of.append(None)
            widths0.append(None)
        if kind == "boiler":
            n_g = fplan["counts"][g_i]
            g_i += 1
            for _ in range(n_g):
                seq.append("F")
                seg_of.append(si)
                widths0.append(max(seg_l / n_g, f_min))
        else:
            seq.append("E")
            seg_of.append(si)
            widths0.append(seg_l)
    if not groups and nfun:        # engines only: the exhaust funnel(s) stand over the engine rooms
        e_items = [i for i, it in enumerate(seq) if it == "E" and segs[seg_of[i]][0] == "engine"] or [0]
        for _ in range(nfun):
            seq.insert(e_items[0], "F")
            seg_of.insert(e_items[0], None)
            widths0.insert(e_items[0], f_min)
    # engine rooms and bunkers at the ends of the block have nothing on deck: they leave the deck plan and run on
    # under whatever stands above them (bridge, wing turrets, aft control). An engines-only plant keeps its engine
    # rooms in the plan, under its exhaust funnels.
    lead, trail = [], []
    if groups:
        while seq and seq[0] == "E":
            lead.append(seg_of.pop(0))
            seq.pop(0)
            widths0.pop(0)
        while seq and seq[-1] == "E":
            trail.insert(0, seg_of.pop())
            seq.pop()
            widths0.pop()
    if not echelon:
        for k in range(nw):
            at = 0 if k % 2 == 0 else len(seq)
            seq.insert(at, "W")
            seg_of.insert(at, None)
            widths0.insert(at, None)
    core = [i for i, it in enumerate(seq) if not (it == "W" and not echelon)]   # the plan over the machinery
    # the forward boiler group may run on under the bridge: most of it, as its funnels must still come up through
    # open deck aft of the bridge, each with its room (f_min)
    under_bridge, ub_seg = 0.0, None
    if core and seq[core[0]] == "F":
        ub_seg = seg_of[core[0]]
        f_items = [i for i in range(len(seq)) if seq[i] == "F" and seg_of[i] == ub_seg]
        ub_l = segs[ub_seg][1]
        under_bridge = max(0.0, min(ub_l - len(f_items) * f_min, BRIDGE_OVER_BOILERS * (lb + 1.5)))
        for i in f_items:
            widths0[i] = max(f_min, (ub_l - under_bridge) / len(f_items))
    lead_l = sum(segs[si][1] for si in lead) + under_bridge
    trail_l = sum(segs[si][1] for si in trail)
    w2 = clamp(0.36 * B, 4.5, 12)                   # bridge width
    ends = {-1: w2 / 2, len(seq): 0.14 * B if la else 0.0}

    def half_of(j, y):
        """Half-width of what stands on the centreline at seq[j] (a W counts as its turrets' outer edge)."""
        if j in ends:
            return ends[j]
        return fw / 2 if seq[j] == "F" else (y + reach if seq[j] == "W" else 0.0)

    def wing_gap(y, half):
        """Fore-and-aft room from a wing turret at y to the edge of its neighbour's slot: clear of the body,
        or of the barrels' reach if the neighbour stands as far out as the turret's sweep."""
        if half >= y - 0.2:
            return R_main + 0.5
        return max(0.5, math.sqrt(max(0.0, (reach + 0.5) ** 2 - (y - half) ** 2)))

    def wing_stagger(y):
        """Fore-and-aft offset between an echelon pair: bodies clear, and if the partner reaches across a
        turret's barrel line, clear of its barrels too."""
        if reach - y > y - 0.3:
            return R_main + reach + 0.5
        return max(2 * reach + 1.0, math.sqrt(max(0.0, (2 * reach + 0.5) ** 2 - 4 * y * y)))

    def wing_side(i, step, y):
        """Room from the wing pair at seq[i] toward one end (step -1 forward, +1 aft): clear of the neighbour, and
        of the next bridge, turret or aft control beyond any funnels, which may stand wider than the funnels and
        reach into the barrels' sweep."""
        j = i + step
        g = wing_gap(y, half_of(j, y))
        while 0 <= j < len(seq) and seq[j] in ("F", "E"):
            j += step
        g = max(g, wing_gap(y, half_of(j, y)))
        # past the bridge (or aft control) stands the end group's inner turret, whose body may cross the
        # barrels' line when they point ahead (or astern): keep the muzzles short of it
        if (step < 0 and nf) or (step > 0 and na):
            flush = flush_f if step < 0 else flush_a
            beyond = (R_main + 1.0 if flush else r + gap) + (lb + 1.5 if step < 0 else (la + 1.5 if la else 1.0))
            need = R_main + reach + 0.5 if reach > y - 0.3 else math.sqrt(max(0.0, (2 * reach + 0.5) ** 2 - y * y))
            g = max(g, need - beyond)
        return g

    def wing_widths(y):
        return {i: wing_side(i, -1, y) + wing_side(i, 1, y) + (wing_stagger(y) if echelon else 0.0)
                for i, it in enumerate(seq) if it == "W"}

    def plan_widths(y):
        """Fore-and-aft length of each item of the plan, with the wing pairs standing at y."""
        ww = wing_widths(y)
        out = []
        for i, it in enumerate(seq):
            if it == "W":
                out.append(ww[i])
            elif it == "T":
                stow = 0 if (i + 1 < len(seq) and seq[i + 1] == "T") else 180
                j = i - 1 if stow == 180 else i + 1                  # the neighbour on the open side
                margin = max(reach + 1.0, half_of(j, y) / beam_tan + 0.5)
                out.append(margin + R_main + 1.5)
            else:
                out.append(widths0[i])
        return out

    # the middle holds, on deck, the bridge, the plan and the aft control; below it, the machinery (the plan's
    # core with the end segments run on beyond it): whichever is longer
    aft_l = la + 1.5 if la else 1.0

    def middle_needs(ws):
        """Length the middle needs: the deck plan with the bridge and aft control, the machinery, and the two
        mixes (bridge, the plan through its core, then the trailing machinery; the leading machinery, then the plan
        from its core to the aft control)."""
        before = sum(ws[:core[0]]) if core else 0.0
        c_l = sum(ws[i] for i in core)
        return max(lb + 1.5 + sum(ws) + aft_l, lead_l + c_l + trail_l + 2.0,
                   lb + 1.5 + before + c_l + trail_l + 1.0, lead_l + 1.0 + sum(ws) - before + aft_l)

    M_req = middle_needs(plan_widths(B / 2 - reach - 0.6))

    need_hw = reach + 0.6
    if tm and need_hw > B / 2:
        lay.fail("beam", f"Main turrets are {2 * reach:.1f} m across; the {B:g} m beam cannot carry them "
                         f"(needs about {2 * need_hw:.1f} m). Use fewer or smaller guns.")

    def fits(x):
        if need_hw > B / 2:      # cannot fit anywhere: already reported, don't push the guns inward
            return True
        return hull.half_width(x) >= need_hw

    # preferred / minimum clearances from the hull ends to the outer edge of each group
    if nf:
        bow_pref, bow_min = 0.09 * L + 2.5 * r, 0.06 * L + 1.5 * r
    else:
        bow_pref, bow_min = 0.14 * L, 0.06 * L
    if na:
        st_pref, st_min = 0.08 * L + 2.0 * r, 0.05 * L + 1.0 * r
    else:
        st_pref, st_min = 0.12 * L, 0.05 * L

    def arrangement(bow_c, st_c, sh):
        """Positions for the given clearances and shift."""
        fore = [L / 2 - bow_c - r + sh - i * s_main for i in range(nf)]
        aft = [-L / 2 + st_c + r + sh + i * s_main for i in range(na)]
        # push groups inward until the hull is wide enough for the outermost turret
        guard = 0
        while fore and not fits(fore[0]) and fore[0] > 0 and guard < 4000:
            fore = [x - 0.25 for x in fore]
            guard += 1
        guard = 0
        while aft and not fits(aft[0]) and aft[0] < 0 and guard < 4000:
            aft = [x + 0.25 for x in aft]
            guard += 1
        # a flush turret at the inner end of a group stows its barrels toward the middle: keep them clear
        mid_fwd = (fore[-1] - R_main - 1.0 if flush_f else fore[-1] - r - gap) if fore else L / 2 - bow_c + sh
        mid_aft = (aft[-1] + R_main + 1.0 if flush_a else aft[-1] + r + gap) if aft else -L / 2 + st_c + sh
        return fore, aft, mid_fwd, mid_aft

    fore, aft, mid_fwd, mid_aft = arrangement(bow_pref, st_pref, 0.0)
    deficit = M_req - (mid_fwd - mid_aft)
    bow_c, st_c = bow_pref, st_pref
    if deficit > 0:
        lay.short.add("length")   # sizing wants the preferred clearances: room to shift for balance
        sb, ss = bow_pref - bow_min, st_pref - st_min
        take = min(deficit, sb + ss)
        if sb + ss > 0:
            bow_c -= take * sb / (sb + ss)
            st_c -= take * ss / (sb + ss)
        fore, aft, mid_fwd, mid_aft = arrangement(bow_c, st_c, 0.0)
        deficit = M_req - (mid_fwd - mid_aft)
        if deficit > 0.5:
            lay.fail(
                "length", f"Not enough length amidships: the machinery, funnels and midships turrets need about "
                f"{M_req:.0f} m between the turret groups, but only {mid_fwd - mid_aft:.0f} m is free. "
                "Reduce speed, use a more compact plant, or remove a turret.")

    # how far the whole arrangement may shift for balance
    def shift_ok(sh):
        f_, a_, mf, ma = arrangement(bow_c, st_c, sh)
        if f_ and (f_[0] != L / 2 - bow_c - r + sh):   # had to be pushed in: hull too narrow there
            return False
        if a_ and (a_[0] != -L / 2 + st_c + r + sh):
            return False
        front_edge = (f_[0] + r) if f_ else mf
        back_edge = (a_[0] - r) if a_ else ma
        return L / 2 - front_edge >= bow_min - 1e-6 and back_edge + L / 2 >= st_min - 1e-6

    lo = hi = 0.0
    while lo > -0.3 * L and shift_ok(lo - 0.25):
        lo -= 0.25
    while hi < 0.3 * L and shift_ok(hi + 0.25):
        hi += 0.25
    lay.shift_range = (lo, hi)
    shift = clamp(shift, lo, hi)
    fore, aft, mid_fwd, mid_aft = arrangement(bow_c, st_c, shift)
    lay.geo["shift"] = shift

    # ---------------- main turrets ----------------
    turret_types = {}
    mounts = []
    if tm:
        turret_types[tm_id] = tm
        groups = [("A", fore, 0), ("Y", aft, 180)]
        names = {"A": "ABC", "Y": "YXW"}
        stepped = dict(zip("AY", (n_step_f, n_step_a)))
        for gname, xs, rest in groups:
            for i, x in enumerate(xs):
                # each further turret superfires over the one outboard of it, up to the stepped count;
                # the rest stand flush behind and fire to the sides only
                flush = i >= max(stepped[gname], 1)
                level = 0 if flush else i
                base = 1.2 + level * superfire_step(th)
                mid = turret_name(names[gname], i)
                # a flush turret stows pointing away from the stepped turret ahead of it
                m = armament.add_mount(lay, mounts, "main", tm_id, tm, mid, x, 0.0, base,
                                       (180 if gname == "A" else 0) if flush else rest, 1 + level, level=level,
                                       armour_mm=armour.get("turret_mm", 0), depth=depth, footprint_r=reach,
                                       label="Turret")
                if flush:
                    m["arc_role"] = "beam"
                lay.reserve_sweep(m)

    # ---------------- middle: bridge, deckhouse, funnels, aft control ----------------
    bx1 = mid_fwd
    bx0 = bx1 - lb

    # ---------------- the plan placed: machinery, funnels, midships and wing turrets ----------------
    fz0 = mid_aft + (la + 1.5 if la else 1.0)
    fz1 = bx0 - 1.5
    # wing turrets stand as far outboard as the narrowest hull section of the middle allows, then as far as the
    # hull allows where they end up: a hull narrowing to its ends is wider where the pairs stand
    y_w = min(hull.half_width(fz0 + (fz1 - fz0) * k / 20) for k in range(21)) - reach - 0.6

    def plan_front(widths):
        """Where the plan's front stands for these item lengths: (lo_x, hi_x, x)."""
        before_core = sum(widths[:core[0]]) if core else 0.0
        core_l = sum(widths[i] for i in core)
        lo_x = max(fz0 + sum(widths), mid_aft + 1.0 + trail_l + core_l + before_core)
        hi_x = min(fz1, mid_fwd - 1.0 - lead_l + before_core)
        return lo_x, hi_x, (lo_x + hi_x) / 2 if hi_x >= lo_x else hi_x

    def wing_room(y):
        """How far out the wing turrets could stand where a plan with them at y puts them."""
        widths = plan_widths(y)
        xx, room = plan_front(widths)[2], B
        for i, (it, w_) in enumerate(zip(seq, widths)):
            if it == "W":
                x = xx - wing_side(i, -1, y)
                for xw in ((x, x - wing_stagger(y)) if echelon else (x,)):
                    room = min(room, *(hull.half_width(xw + d) for d in (-reach, 0.0, reach)))
            xx -= w_
        return room - reach - 0.6
    if nw:
        lo_y, hi_y = y_w, min(wing_room(y_w), B / 2 - reach - 0.6)
        for _ in range(8):     # the farthest out that still fits where it puts them
            if hi_y - lo_y < 0.05:
                break
            mid_y = (lo_y + hi_y) / 2
            lo_y, hi_y = (mid_y, hi_y) if wing_room(mid_y) >= mid_y else (lo_y, mid_y)
        y_w = lo_y
    if nw and not echelon and y_w < reach + 0.25:
        lay.fail("beam", f"Wing turrets are {2 * reach:.1f} m across: a pair cannot stand abreast on this beam "
                         f"(needs about {4 * reach + 1.7:.1f} m). Set \"echelon\": true or use smaller guns.")
    elif nw and y_w <= 0.5:
        lay.fail("beam", f"Hull too narrow for wing turrets even in echelon: they need about "
                         f"{2 * reach + 2.2:.1f} m of beam amidships.")
    widths = plan_widths(y_w)
    # where the plan's front may stand: the deck plan between the bridge and the aft control, and the machinery
    # (core plus end segments) between the end turret groups
    before_core = sum(widths[:core[0]]) if core else 0.0
    core_l = sum(widths[i] for i in core)
    lo_x, hi_x, xx = plan_front(widths)
    if hi_x < lo_x - 0.5:
        what = [f"{nm} midships turret(s)"] * bool(nm) + [f"{nw} wing turret pair(s)"] * bool(nw)
        lay.fail("length", f"No room for the machinery, {nfun} funnel(s){' and ' + ' and '.join(what) if what else ''}"
                           " between the end turret groups.")
    core_front = xx - before_core
    fxs, f_seg, mids, wings, seg_span = [], [], [], [], {}
    for i, (it, w_) in enumerate(zip(seq, widths)):
        if it == "F":
            fxs.append(xx - w_ / 2)
            f_seg.append(seg_of[i])
        elif it == "W":
            # abreast: both at one x; echelon: port forward, starboard aft
            x = xx - wing_side(i, -1, y_w)
            wings.append([(x, -1), (x - wing_stagger(y_w), 1)] if echelon else [(x, -1), (x, 1)])
        elif it == "T":
            # flush, firing to the sides. Each stows aft unless another turret is aft of it; its slot holds the
            # stowed barrels on one side and, on the other, keeps the neighbour out of its beam arcs
            stow = 0 if (i + 1 < len(seq) and seq[i + 1] == "T") else 180
            j = i - 1 if stow == 180 else i + 1
            margin = max(reach + 1.0, half_of(j, y_w) / beam_tan + 0.5)
            mids.append((xx - margin if stow == 180 else xx - w_ + margin, stow))
        if seg_of[i] is not None:
            seg_span.setdefault(seg_of[i], [xx, xx - w_])[1] = xx - w_
        xx -= w_
    # the machinery: each segment of the plan centred under its items (a funnel group may be spaced wider than its
    # boilers), the end segments run on fore and aft of the plan's core
    pos = {si: ((a_ + b_) / 2 - segs[si][1] / 2, (a_ + b_) / 2 + segs[si][1] / 2) for si, (a_, b_) in seg_span.items()}
    if ub_seg is not None:     # the forward boiler group runs on from the back of its funnels' span under the bridge
        back = seg_span[ub_seg][1]
        pos[ub_seg] = (back, back + segs[ub_seg][1])
    x = max([core_front] + [v[1] for v in pos.values()])
    for si in reversed(lead):
        pos[si] = (x, x + segs[si][1])
        x += segs[si][1]
    x = min([core_front - core_l] + [v[0] for v in pos.values()])
    for si in trail:
        pos[si] = (x - segs[si][1], x)
        x -= segs[si][1]
    mach_placed = [(segs[si][0], pos[si][0], pos[si][1]) for si in range(len(segs))]
    f_seg = [si if si is not None else next((k for k, s in enumerate(segs) if s[0] == "engine"), 0) for si in f_seg]
    plant_placed = [p_ for p_ in mach_placed if p_[0] != "magazine"]     # the block less its magazines
    mach_c = (min(p_[1] for p_ in plant_placed) + max(p_[2] for p_ in plant_placed)) / 2
    lay.geo["machinery"] = (min(p_[1] for p_ in plant_placed), max(p_[2] for p_ in plant_placed))
    lay.geo["machinery_x"] = mach_c
    if nm or nw:
        mid_base = (LEVEL_H if wide else 0.0) + 1.2

        def main_mount(mid, x, y, rest, **kw):
            lay.reserve_sweep(armament.add_mount(lay, mounts, "main", tm_id, tm, mid, x, y, mid_base, rest, 1,
                                                 armour_mm=armour.get("turret_mm", 0), depth=depth,
                                                 footprint_r=reach, label="Turret", **kw))

        for k, (x, stow) in enumerate(mids):
            main_mount(turret_name("QPRS", k), x, 0.0, stow, arc_role="beam", midships=True)
        # wing turrets fire bow to stern on their own side, and stow fore-and-aft (the edge of that arc) toward
        # the nearer end: an echelon pair's forward turret forward and its aft one aft
        for k, pair in enumerate(wings):
            for x, side in pair:
                fwd = (x == pair[0][0]) if echelon else x >= mach_c
                main_mount(f"W{k + 1}{'S' if side > 0 else 'P'}", x, side * y_w, 0 if fwd else 180, wing=True,
                           **({"echelon": True} if echelon else {}))

    # ---------------- superstructure, kept out of the guns' sweeps ----------------
    # every level keeps clear of the end groups' turrets (level_outline): all but wing and midships turrets
    lay.end_mounts = [m for m in mounts if m["kind"] == "main" and not (m.get("wing") or m.get("midships"))]
    blocks = []
    block = functools.partial(add_block, lay, blocks)      # the shared add_block, on this ship's list

    # the bridge tower steps aft, and the aft control forward, until no turret's barrels can reach them
    tower_top = LEVEL_H * n_tower + hood
    while not lay.clear(_fp_rect(bx0, -w2 / 2, bx1, w2 / 2), tower_top) and bx0 > mid_aft:
        bx1 -= 0.5
        bx0 -= 0.5
    ax0 = mid_aft
    while la and not lay.clear(_fp_rect(ax0, -0.14 * B, ax0 + la, 0.14 * B), LEVEL_H * (na_lvl + 1)) and \
            ax0 + la < bx0:
        ax0 += 0.5
    # level-1 deckhouse: the full middle on big ships, only under the bridge on small ones
    if wide:
        dh = dict(x0=mid_aft, x1=mid_fwd + 1.0)
    else:
        dh = dict(x0=bx0 - 3.0, x1=bx1 + 1.0)
    # trim the deckhouse ends out of low turrets' sweeps, at the widest the deckhouse can get (the hull's)
    def dh_rect(x0, x1):
        hw = min(hull.half_width(dh["x0"]), hull.half_width(dh["x1"])) - 0.6
        return _fp_rect(x0, -hw, x1, hw)
    while not lay.clear(dh_rect(dh["x0"], dh["x1"]), LEVEL_H) and dh["x1"] - dh["x0"] > 4:
        if lay.clear(dh_rect(dh["x0"], (dh["x0"] + dh["x1"]) / 2), LEVEL_H):
            dh["x1"] -= 0.5
        else:
            dh["x0"] += 0.5
    # bridge tower: base levels (chart house, offices, sea cabins) as wide as the bridge up to it, then the bridge
    # and the levels over it as before (a bridge at level 2 builds the tower it always did). A really tall tower
    # tapers above TOWER_TAPER_FROM (tower_taper), like a pagoda or a tall tower bridge; the bridge keeps its full
    # width there, its wings over the narrower column, and the levels over it follow its length
    def tower_fp(k):
        """(x0, x1, w) of the tower's base level k: the bridge's footprint, narrower and shorter (mostly from aft)
        above TOWER_TAPER_FROM."""
        fw, fl = tower_taper(k)
        if fl == 1.0:
            return bx0, bx1, w2 * fw
        l = lb * fl
        x1 = bx1 - 0.25 * (lb - l)
        return x1 - l, x1, w2 * fw

    def stack(bid, k, x0_, x1_, w_, below):
        """One level of a tower standing on the level below (below: its block, or None for the deck band). Upper
        levels never grow past their core (only level 1 does), so a tower keeps its setbacks."""
        b_ = add_level(lay, blocks, bid, k, x0_, x1_, w_, support=below and below["points"])
        return b_ or below

    below = None
    for k in range(2, nb):
        x0_, x1_, w_ = tower_fp(k)
        below = stack(f"Bridge base {k}", k, x0_, x1_, w_, below)
    tower_foot = blocks[0] if blocks else None
    tx0, tx1, _ = tower_fp(nb - 1) if nb > 2 else (bx0, bx1, w2)
    tl = tx1 - tx0
    below = stack("Bridge", nb, tx0, tx1, w2, None)    # full width over a tapered column: its wings overhang
    tower_foot = tower_foot or below
    if n_tower > nb:
        below = stack("Bridge upper", nb + 1, tx0 + 0.1 * tl, tx1 - 0.06 * tl, 0.78 * w2, below)
    if armour.get("belt_mm", 0) > 0:   # inside the bridge tower's front, as tall as its first level
        ct_r = min(max(0.1 * B, 1.25), 4.0, 0.4 * w2)
        ct_x = max(bx1 - 0.42 * w2, bx0 + ct_r)
        if tower_foot:          # as far forward as the tower's foot holds it
            pts_ = tower_foot["points"]
            ct_x = tower_foot["x1"] - ct_r - 0.3
            while ct_x > tower_foot["x0"] + ct_r and min(
                    _seg_dist(ct_x, 0.0, *pts_[i - 1], *pts_[i]) for i in range(len(pts_))) < ct_r + 0.3:
                ct_x -= 0.25
        lay.conning_tower = dict(x=ct_x, y=0.0, r=ct_r, top=2 * LEVEL_H)
        mm = armour["belt_mm"] / 1000      # the hitbox's armour: walls as thick as the belt, a roof half that
        area = 2 * math.pi * ct_r * 2 * LEVEL_H + 0.5 * math.pi * ct_r ** 2
        lay.weights.append(Weight("Conning tower", "armour", area * mm * 7.85, x=lay.conning_tower["x"],
                                  z_rel=("deck", LEVEL_H)))
    for k in range(nb + 2, n_tower + 1):      # the tower narrows as it rises
        f, tw = min(0.12, 0.03 * (k - nb - 2)), max(3.0, 0.5 * w2 * 0.9 ** (k - nb - 2))
        below = stack(f"Tower {k}", k, tx0 + (0.35 + f) * tl, max(tx0 + (0.35 + f) * tl + 3.0, tx1 - (0.2 + f) * tl),
                      tw, below)
    # aft control: the same
    if la:
        below = None
        for k in range(2, na_lvl):     # base levels under it, as under the bridge
            below = stack(f"Aft control base {k}", k, ax0, ax0 + la, 0.28 * B, below)
        below = stack("Aft control", na_lvl, ax0, ax0 + la, 0.28 * B, below)
        stack("Aft control upper", na_lvl + 1, ax0 + 0.25 * la, ax0 + 0.75 * la, 0.17 * B, below)

    # each boiler group's funnels are trunked aft, toward the boundary with what lies aft of the boilers (the
    # engine rooms), so the funnels don't all crowd the forward end of the machinery: the group's middle goes to the
    # boundary, or as far toward it as the uptakes' reach (each end of the group within reach of a funnel, or no
    # farther than planned), the turrets' sweeps, the aft control and the funnels behind allow
    def fun_fp(x):
        return _fp_rect(x - fl / 2, -fw / 2, x + fl / 2, fw / 2)

    reach_lim = fplan["reach"] + fl / 2

    def in_reach(si, xs, off):
        ends = mach_placed[si][1:]
        return all(min(abs(e - x - off) for x in xs) <= max(reach_lim, min(abs(e - x) for x in xs)) + 1e-6
                   for e in ends)

    by_seg = {}
    for i, si in enumerate(f_seg):
        by_seg.setdefault(si, []).append(i)
    fx_final = list(fxs)
    for si in sorted(by_seg, key=lambda s: mach_placed[s][1]):     # aft-most group first
        idx = by_seg[si]
        want = 0.0
        if mach_placed[si][0] == "boiler":
            want = min(0.0, mach_placed[si][1] - (fxs[idx[0]] + fxs[idx[-1]]) / 2)
        off = want
        while off < 0.0 and not (in_reach(si, [fxs[i] for i in idx], off) and all(
                lay.clear(fun_fp(fxs[i] + off), fun_top) and lay.free(fun_fp(fxs[i] + off), 0.0) for i in idx)):
            off = min(0.0, off + 0.25)
        for i in idx:
            fx_final[i] = fxs[i] + off
            lay.occupy(fun_fp(fx_final[i]), 0, fun_top, f"Funnel {i + 1}")

    funnels = []
    for i, fx in enumerate(fx_final):
        fid = f"Funnel {i + 1}"
        fp = fun_fp(fx)     # already occupied above
        if not lay.clear(fp, fun_top) or not lay.free(fp, 0.0, ignore=(fid,)):
            lay.fail("length", f"{fid} would stand in a turret's sweep or against the bridge: use fewer funnels "
                               "or midships turrets.")
        funnels.append(dict(id=fid, x=fx, y=0.0, l=fl, w=fw, pipes=2 if fw > 4 else 1, seg=f_seg[i]))
        seg = mach_placed[f_seg[i]]
        add_funnel_weights(lay, funnels[-1], fun_top, (seg[1] + seg[2]) / 2, depth)

    # ---------------- secondaries on deck ----------------
    # one battery or a list; deck batteries stand on the deckhouse amidships (the first spread evenly, the rest in
    # the free spots nearest amidships), casemate batteries go in the hull sides once the deckhouse is laid out
    secs = design.get("secondary") or []
    secs = [{**b, "prefix": battery_prefix(k)} for k, b in enumerate(secs if isinstance(secs, list) else [secs])]
    dh_w = 0.62 * B
    sec_base = LEVEL_H if wide else 0.0
    first = True
    for sec in secs:
        nsec = sec.get("per_side", sec.get("count", 0) // 2)
        if sec.get("mount", "deck") != "deck" or not nsec:
            continue
        pre, cal = sec["prefix"], f"{sec['calibre_mm']:g} mm"
        ts_id, ts = make_turret_type(sec["calibre_mm"], sec["calibre_length"], sec["barrels"])
        turret_types[ts_id] = ts
        rs = ts["r"]
        rs_reach = max(rs, turret_reach({**ts, "barrel_len": 0}))
        ths = turret_height(ts)
        x_lo, x_hi = mid_aft + rs_reach + 0.5, mid_fwd - rs_reach - 0.5
        if wide:   # they stand on the deckhouse: stay on what is left of it after trimming
            x_lo = max(mid_aft, dh["x0"]) + rs_reach + 0.5
            x_hi = min(mid_fwd, dh["x1"]) - rs_reach - 0.5
        inner = max([b["w"] / 2 for b in blocks if b["level"] >= 2] + [fw / 2] + ([reach] if nm else [])) \
            + rs_reach + 0.4

        def outer_at(x):   # how far out a mount at x may stand: inside the deck edge over its whole footprint
            return min(hull.half_width(x + d) for d in (-rs_reach, 0.0, rs_reach)) - rs_reach - 0.6

        def y_at(x):       # mounts follow the deck edge, 0.55 of the way out from the inner limit
            return max(inner, inner + 0.55 * (outer_at(x) - inner))
        xs_probe = [x_lo + (x_hi - x_lo) * k / 40 for k in range(41)]
        if max(outer_at(x) for x in xs_probe) < inner:
            lay.fail("beam", f"Hull too narrow for {cal} secondary mounts: they need about "
                             f"{2 * (inner + rs_reach + 0.6):.1f} m of beam amidships.")
        else:   # keep to the stretch where they fit across; a hull narrowing to its ends asks for length instead
            fits = [x for x in xs_probe if outer_at(x) >= inner]
            x_lo, x_hi = min(fits), max(fits)
        pitch_s = 2.1 * rs_reach + 1.0
        if x_hi <= x_lo:
            lay.fail("length", "No room amidships for the secondary battery.")
        elif first and nsec > 1 and (x_hi - x_lo) / (nsec - 1) < pitch_s:
            lay.fail("length", f"{nsec} secondary mounts per side do not fit in {x_hi - x_lo:.0f} m amidships "
                               f"(max {int((x_hi - x_lo) / pitch_s) + 1}).")
        step = min((x_hi - x_lo) / max(nsec - 1, 1), 2.2 * rs + 4.0)
        c = (x_lo + x_hi) / 2
        sxs = [c + (i - (nsec - 1) / 2) * step if nsec > 1 else c for i in range(nsec)]
        if nw or not first:
            # wing turrets (or the batteries placed before) break up the middle: take the free spots nearest
            # amidships, at the preferred pitch if they fit, else the minimum
            def spot_ok(x):
                fps = [_fp_circle(x, s * y_at(x), rs_reach) for s in (1, -1)]
                return all(lay.free(fp, 0.4) and lay.clear(fp, sec_base + ths) for fp in fps)
            spots = sorted((x for x in (x_lo + 0.5 * k for k in range(int(max(0.0, x_hi - x_lo) * 2) + 1))
                            if spot_ok(x)), key=lambda x: abs(x - c))
            for sp in (2.2 * rs + 4.0, pitch_s):
                sxs = []
                for x in spots:
                    if len(sxs) < nsec and all(abs(x - o) >= sp for o in sxs):
                        sxs.append(x)
                if len(sxs) == nsec:
                    break
            if len(sxs) < nsec:
                where = "beside the wing turrets" if first else "amidships beside the other secondaries"
                lay.fail("length", f"Only {len(sxs)} of {nsec} {'' if first else cal + ' '}secondary mounts per side "
                                   f"fit {where}.")
            sxs.sort()
        for i, sx in enumerate(sxs):
            y_s = y_at(sx)
            if not lay.clear(_fp_circle(sx, y_s, rs_reach), sec_base + ths):
                lay.fail("length", f"Secondary mounts {pre}{i + 1} would stand in a main turret's sweep: use fewer "
                                   "secondaries.")
            for side in (1, -1):
                mid = f"{pre}{i + 1}{'S' if side > 0 else 'P'}"
                armament.add_mount(lay, mounts, "secondary", ts_id, ts, mid, sx, side * y_s, sec_base, 90 * side, 3,
                                   armour_mm=sec.get("armour_mm", 25), depth=depth, top=sec_base + ths,
                                   footprint_r=rs_reach, material=sec.get("material"))
        if wide and sxs:
            y_s = max(y_at(sx) for sx in sxs)
            dh_w = max(dh_w, 2 * (y_s + rs_reach + 0.6)) if not first else 2 * (y_s + rs_reach + 0.6)
        first = False
    if wide:
        if nw:   # wing turrets stand on the deckhouse
            dh_w = max(dh_w, 2 * (y_w + reach + 0.6))
        hw_max = max(hull.half_width(dh["x0"] + (dh["x1"] - dh["x0"]) * k / 20) for k in range(21))
        dh_w = min(dh_w, 2 * (hw_max - DH_INSET))     # the sides follow the deck edge (level_outline)
    # level 1 (add_level): on the deck, its ends grown toward the end turrets on big ships, under all that stands
    # on it, wrapped round the funnels
    keep = [_bbox(o[0]) for o in lay.footprints if o[1] >= LEVEL_H - 0.01
            and dh["x0"] <= (_bbox(o[0])[0] + _bbox(o[0])[2]) / 2 <= dh["x1"]]
    deckhouse = add_level(lay, blocks, "Deckhouse", 1, dh["x0"], dh["x1"], dh_w, grow=(wide, wide), keep=keep,
                          ignore=[f["id"] for f in funnels])
    dh_pts = deckhouse["points"]
    blocks.insert(0, blocks.pop())  # draw the deckhouse first, under the bridge
    # the deckhouse is under everything else in the middle; secondaries stand on it
    lay.footprints = [fp for fp in lay.footprints if fp[3] != "Deckhouse"] + \
                     [(_fp_poly(dh_pts), 0, LEVEL_H, "Deckhouse")]

    # ---------------- casemates: guns in the hull side, below the main deck ----------------
    place_casemates(lay, mounts, turret_types, blocks, secs, hull, depth)

    # ---------------- torpedo mounts ----------------
    tp = design.get("torpedoes") or {}
    ntp = tp.get("mounts", 0)
    if ntp:
        tt_id, tt = make_torpedo_type(tp.get("tubes", 4))
        turret_types[tt_id] = tt
        sweep = tt["barrel_len"] / 2 + 0.3
        placed = 0
        if wide:
            if ntp % 2:
                lay.warnings.append("Wide hulls carry torpedo mounts in pairs; rounded up to an even number.")
                ntp += 1
            xs = sorted([x * 0.5 for x in range(int(-L), int(L))], key=lambda x: abs(x - mach_c))
            for x in xs:
                if placed >= ntp:
                    break
                y = hull.half_width(x) - tt["r"] - 0.8
                if y < sweep:
                    continue
                fps = [_fp_circle(x, y, sweep), _fp_circle(x, -y, sweep)]
                if all(lay.free(fp, 0.3) and lay.clear(fp, 1.4) for fp in fps):
                    for side, fp in zip((1, -1), fps):
                        mid = f"T{placed // 2 + 1}{'S' if side > 0 else 'P'}"
                        mounts.append(dict(id=mid, kind="torpedo", type=tt_id, t=tt, x=x, y=side * y, level=0,
                                           base=0.3, top=1.4, rest=90 * side, z=1))
                        lay.occupy(fp, 0, 1.4, mid)
                        lay.weights.append(Weight(mid, "armament", torpedo_weight(tt["barrels"]), x=x,
                                                  z_rel=("deck", 1)))
                        placed += 1
        if placed < ntp:     # narrow hulls, and wide ones whose deck edges are taken: on the centreline
            cands = sorted([mid_aft + 0.5 * k for k in range(int((mid_fwd - mid_aft) * 2) + 1)],
                           key=lambda x: abs(x - mach_c))
            for x in cands:
                if placed >= ntp:
                    break
                fp = _fp_circle(x, 0, sweep)
                if lay.free(fp, 0.3) and lay.clear(fp, 1.4) and hull.half_width(x) > tt["r"] + 0.5:
                    mid = f"T{placed + 1}"
                    mounts.append(dict(id=mid, kind="torpedo", type=tt_id, t=tt, x=x, y=0.0, level=0, base=0.3,
                                       top=1.4, rest=90, z=1))
                    lay.occupy(fp, 0, 1.4, mid)
                    lay.weights.append(Weight(mid, "armament", torpedo_weight(tt["barrels"]), x=x, z_rel=("deck", 1)))
                    placed += 1
        if placed < ntp and wide:   # the deck is taken: on the deckhouse roof, on its centreline
            cands = sorted([dh["x0"] + sweep + 0.5 * k for k in range(int((dh["x1"] - dh["x0"] - 2 * sweep) * 2) + 1)],
                           key=lambda x: abs(x - mach_c))
            for x in cands:
                if placed >= ntp:
                    break
                fp = _fp_circle(x, 0, sweep)
                if lay.free(fp, 0.3, ignore=("Deckhouse",)) and lay.clear(fp, LEVEL_H + 1.4):
                    mid = f"T{placed + 1}"
                    mounts.append(dict(id=mid, kind="torpedo", type=tt_id, t=tt, x=x, y=0.0, level=1,
                                       base=LEVEL_H + 0.3, top=LEVEL_H + 1.4, rest=90, z=1))
                    lay.occupy(fp, LEVEL_H, LEVEL_H + 1.4, mid)
                    lay.weights.append(Weight(mid, "armament", torpedo_weight(tt["barrels"]), x=x,
                                              z_rel=("deck", LEVEL_H + 1)))
                    placed += 1
        if placed < ntp:
            lay.fail("length", f"Only {placed} of {ntp} torpedo mounts fit on deck.")

    # ---------------- deckhouse levels (superstructure.deckhouse_levels): room for the crew up top ----------------
    add_deckhouse_levels(lay, blocks, deckhouse_levels(design), mid_aft, mid_fwd, dh, dh_w,
                         [f["id"] for f in funnels], base_block=deckhouse)
    fun_top = raise_funnels(lay, funnels, blocks, fun_top)

    # ---------------- fire control: directors on the roofs ----------------
    firecontrol.place(lay, design, blocks)

    # ---------------- AA ----------------
    aa_out = []
    aa_req = design.get("aa", {})

    def aa_slots(kind):
        """AA stands high, as on real ships: in tubs on the superstructure's roofs (the bridge, tower and aft control
        levels first, then the tower's top, then the deckhouse), with the deck edges along the hull as the last
        resort; nearest amidships first within each. Pairs come before single mounts on a roof's centreline, and
        a single leftover mount goes on the centreline at the stern."""
        rr = AA_CFG[kind][0]
        scored = []
        for x, y, z0, pair in roof_spots(blocks, 2 * rr, 2 * rr):
            lvl = round(z0 / LEVEL_H)
            pen = AA_ROOF_PEN[min(lvl, len(AA_ROOF_PEN) - 1)]
            if pair:
                scored.append((abs(x - mach_c) / L + pen, (x, y, z0)))
            elif abs(y) < 1e-6:
                scored.append((abs(x - mach_c) / L + pen + AA_SINGLE_PEN, (x, 0.0, z0)))
        x = L / 2 - 0.06 * L
        while x > -L / 2 + 2:       # along the deck edges: on a raised platform, else on the deck
            yy = hull.half_width(x) - rr - 0.5
            if yy > rr + 0.5:
                scored.append((abs(x - mach_c) / L + AA_PLATFORM_PEN, (x, yy, AA_PLATFORM_H, -yy, 0.0)))
                scored.append((abs(x - mach_c) / L + AA_DECK_PEN, (x, yy, 0.0)))
            x -= 0.5
        cands = [c for _, c in sorted(scored, key=lambda s: s[0])]
        sx = -L / 2 + rr + 2.5
        if hull.half_width(sx) > rr + 0.6:
            cands.append((sx, 0.0, 0.0))
        return cands

    def place_aa(kind, count):
        armament.place_aa(lay, aa_out, kind, count, aa_slots(kind),
                          layer_of=lambda base: "upper" if base > LEVEL_H + 0.01 else "base")

    place_aa("quad40", aa_req.get("heavy", 0))
    place_aa("single20", aa_req.get("light", 0))
    for a in aa_out:      # the raised platforms under deck-edge AA: a pedestal block as wide as the tub
        if "platform" in a:
            rr = AA_CFG[a["type"]][0]
            block(f"AA platform {a['id'][2:]}", a["x"] - rr, a["x"] + rr, 2 * rr, 1, rr, rr, y=a["y"])
            lay.footprints.pop()      # the AA mount's own footprint already claims the column

    # ---------------- masts and boats (decorative but drawn) ----------------
    mast_top = fun_top + 6.0
    fx_ = bx0 - 1.2 if lay.clear(_fp_circle(bx0 - 1.2, 0, 0.7), mast_top) else bx0 + 0.3 * lb   # else on the bridge
    masts = [dict(x=fx_, yard=min(0.3 * B, 10), tripod=L >= 150)]
    if LEVEL_H * n_tower + hood + 2.0 > mast_top:     # a tall tower: the foremast tops it
        masts[0]["top"] = LEVEL_H * n_tower + hood + 2.0
    if la:
        masts.append(dict(x=ax0 + la * 0.5, yard=min(0.22 * B, 8), tripod=False))
    for k, m in enumerate(masts):
        mast_weight(lay, m, m.get("top", mast_top), "Foremast" if k == 0 else "Mainmast")
    boats = []
    bl_ = clamp(0.03 * L, 4, 8)
    for x in [mach_c + k * 2.0 for k in range(-6, 7)]:
        if len(boats) >= 2:
            break
        y = (dh_w / 2 - 0.35 * bl_ - 0.6) if wide else (B / 2 - 0.35 * bl_ - 1.0)
        fps = [_fp_rect(x - bl_ / 2, s * y - 0.15 * bl_, x + bl_ / 2, s * y + 0.15 * bl_) for s in (1, -1)]
        if y > fw / 2 + 0.3 * bl_ and all(lay.free(fp, 0.3, ignore=("Deckhouse",)) and lay.clear(fp, LEVEL_H + 1.5)
                                          for fp in fps):
            for s, fp in zip((1, -1), fps):
                boats.append(dict(x=x, y=s * y, l=bl_, w=0.3 * bl_))
                lay.occupy(fp, LEVEL_H, LEVEL_H + 1.5, f"Boat{len(boats)}")

    # ---------------- citadel & compartments ----------------
    # the citadel covers the main turrets and the whole machinery block with its grouped magazines (an all-forward
    # ship's machinery lies aft of every turret)
    main_x = [m["x"] for m in mounts if m["kind"] == "main"]
    block = (min(p_[1] for p_ in mach_placed), max(p_[2] for p_ in mach_placed))
    if main_x:
        cit = (min(min(main_x) - r - 2.0, block[0]), max(max(main_x) + r + 2.0, block[1]))
    else:
        cit = block
    set_citadel(lay, *cit)
    inner_hw = 0.8 * B / 2
    mag_x = [(x0, x1) for kind, x0, x1 in mach_placed if kind == "magazine"]
    mag_groups = {}
    if mag_l["fore"] > 0:
        mag_groups["fore"] = mag_x[0]
    if mag_l["aft"] > 0:
        mag_groups["aft"] = mag_x[-1]
    add_magazines(lay, mounts, inner_hw, mag_groups)
    # the funnels' segments count the magazines (mach_placed); the rooms are made from the block less them
    to_plant = {i: k for k, i in enumerate(i for i, p_ in enumerate(mach_placed) if p_[0] != "magazine")}
    for f in lay.funnels_planned:
        f["seg"] = to_plant.get(f.get("seg"))
    add_machinery_rooms(lay, plant_placed, inner_hw, depth)
    add_steering(lay)

    # ---------------- renderer spec ----------------
    front_edge = (fore[0] + r) if fore else mid_fwd
    extra = dict(boats=boats, bollards=[L / 2 - 0.05 * L, -L / 2 + 0.06 * L])
    if L / 2 - front_edge > 0.08 * L + 6:
        extra.update(chain_x=front_edge + 0.35 * (L / 2 - front_edge), hawse_back=0.03 * L + 1.0)
    if L >= 150 and fore and (L / 2 - front_edge) > 12:
        extra["breakwater_x"] = front_edge + 3.0
    return finish_layout(lay, design, hs, mounts, turret_types, blocks, funnels, masts, aa_out, fun_top, deck=deck,
                         **extra)
