"""
clutter: the small gear on a warship's roofs and open decks, drawn only (render side; the design never sees it).

Ventilators, skylights, hatches, boats on their chocks, Carley floats, ready-use lockers, searchlights, coal
scuttles, paravanes and so on, picked by era: a look's shapes key "clutter" names a kit in KITS (looks.shapes
defaults it to the look's era). Placement is repeatable (seeded by the design's id) and keeps to open roof and
deck: never under a higher block, a funnel, a mast, a turret, an AA mount or another item. Most items come in
mirrored pairs, as on real ships, so the result reads as fitted out rather than strewn about.

Nothing here changes the layout, hitboxes, sprite.json or the report. Each item also gives the height map a low
column (render.py), so it casts its own small shadow.

Shapes keys read here (README "Looks"):
    clutter          a KITS name, or None / "" for none
    clutter_density  a factor on every kit's counts (1)
    roof_planks      0 = steel roofs; otherwise the smallest block area (m^2) whose roof is planked like a deck
                     (the kit's default)
    roof_rails       guardrails round open roofs (the kit's default)
"""
from __future__ import annotations

import math
import random

from geometry import block_outline, point_in_polygon, polygon_area, polygon_y_span

# Item sizes (l along the ship, w across, h tall, all m) and how each is placed:
#   pair    mirrored about the centreline, anywhere across (a lone one on the centreline when the roof is narrow)
#   centre  on the centreline
# centre_p: a pair item's chance of one on the centreline instead; ends / deck_ends: kept beyond that fraction of
# L from amidships (everywhere / on the open deck only)
#   edge    mirrored, just inboard of the roof's or deck's edge
#   row     2-4 side by side, along the edge or (half the time) anywhere across like pair
# near: "funnel" keeps the item within NEAR_FUNNEL m (along the ship) of a funnel, where the boiler rooms breathe
ITEMS = {
    "cowl":       dict(l=1.3, w=1.3, h=1.8, place="pair"),
    "cowl_small": dict(l=0.9, w=0.9, h=1.2, place="pair"),
    "mushroom":   dict(l=0.9, w=0.9, h=0.8, place="pair"),
    "vent_box":   dict(l=1.8, w=1.1, h=1.1, place="pair"),
    "skylight":   dict(l=3.0, w=1.5, h=0.7, place="pair", centre_p=0.35, deck_ends=0.15),
    "hatch":      dict(l=1.4, w=1.0, h=1.0, place="pair"),
    "capstan":    dict(l=1.3, w=1.3, h=0.7, place="centre", ends=0.3),   # forecastle and quarterdeck only
    "reel":       dict(l=1.2, w=0.9, h=1.0, place="pair"),
    "locker":     dict(l=1.2, w=0.8, h=0.9, place="row"),
    "float":      dict(l=2.2, w=1.0, h=0.5, place="row"),
    "raft":       dict(l=0.7, w=1.5, h=0.7, place="row"),
    "searchlight": dict(l=1.7, w=1.7, h=1.6, place="pair"),
    "scuttle":    dict(l=0.5, w=0.5, h=0.0, place="edge"),
    "paravane":   dict(l=3.2, w=0.7, h=0.4, place="edge"),
    "dc_rack":    dict(l=4.0, w=1.2, h=1.0, place="edge"),
    # big gear, for the big roofs (kit "big")
    "boiler_cowl": dict(l=2.4, w=2.4, h=3.2, place="pair", near="funnel"),
    "engine_skylight": dict(l=6.5, w=3.4, h=1.0, place="pair", centre_p=0.7),
    "searchlight_tower": dict(l=3.4, w=3.4, h=2.6, place="pair"),
    "fan_house":  dict(l=4.2, w=2.6, h=2.0, place="pair", centre_p=0.4, near="funnel"),
}

# Boats: (kind, length m, beam m); nested boats ride inside a bigger one (Victorian and Great War practice)
BOATS = {
    "cutter":   (8.5, 2.2),
    "whaler":   (7.5, 1.9),
    "gig":      (9.0, 1.8),
    "pinnace":  (11.0, 2.8),   # steam pinnace: a cabin and a little funnel
    "launch":   (10.5, 2.8),   # motor launch: a cabin forward
    "dinghy":   (4.5, 1.5),
    "whaleboat": (8.0, 2.4),   # motor whaleboat with a canopy forward
}

# Kits by era. roof / deck: (item, items per 100 m^2 of open surface); big: (item, items per 100 m^2 of a roof's
# area beyond what the small items count, ROOF_SAT); boats: the boats on big roofs, biggest
# first; nest: a dinghy rides in each cutter; scuttles: coal scuttles along the deck edges amidships
KITS = {
    "victorian": dict(
        roof=[("cowl", 1.6), ("skylight", 0.7), ("hatch", 0.6), ("cowl_small", 1.0)],
        big=[("boiler_cowl", 0.3), ("engine_skylight", 0.2)],
        deck=[("cowl", 0.35), ("skylight", 0.25), ("capstan", 0.15), ("hatch", 0.2), ("reel", 0.15)],
        boats=["cutter", "pinnace", "gig", "whaler"], nest=True, scuttles=True,
        roof_planks=60.0, roof_rails=True),
    "great_war": dict(
        roof=[("cowl", 1.2), ("searchlight", 0.5), ("skylight", 0.4), ("hatch", 0.5), ("cowl_small", 0.9)],
        big=[("boiler_cowl", 0.25), ("engine_skylight", 0.15), ("searchlight_tower", 0.1)],
        deck=[("cowl", 0.3), ("skylight", 0.15), ("capstan", 0.12), ("hatch", 0.2), ("reel", 0.2),
              ("paravane", 0.05)],
        boats=["pinnace", "cutter", "whaler", "pinnace", "gig"], nest=True, scuttles=True,
        roof_planks=60.0, roof_rails=True),
    "treaty": dict(
        roof=[("mushroom", 1.2), ("searchlight", 0.45), ("vent_box", 0.5), ("hatch", 0.5), ("float", 0.4)],
        big=[("fan_house", 0.25), ("searchlight_tower", 0.12), ("engine_skylight", 0.08)],
        deck=[("mushroom", 0.3), ("capstan", 0.1), ("hatch", 0.2), ("reel", 0.2), ("paravane", 0.06)],
        boats=["launch", "cutter", "pinnace", "whaler"], max_boats=6, nest=False, scuttles=False,
        roof_planks=0.0, roof_rails=True),
    "wwii": dict(
        roof=[("locker", 1.3), ("float", 1.0), ("vent_box", 0.8), ("mushroom", 0.8), ("hatch", 0.4)],
        big=[("fan_house", 0.3), ("searchlight_tower", 0.08)],
        deck=[("locker", 0.25), ("float", 0.25), ("mushroom", 0.25), ("hatch", 0.2), ("reel", 0.2),
              ("paravane", 0.04), ("dc_rack", 0.0)],
        boats=["launch", "whaler"], max_boats=4, nest=False, scuttles=False, roof_planks=0.0, roof_rails=True),
    "cold_war": dict(
        roof=[("raft", 1.4), ("vent_box", 1.0), ("mushroom", 0.6), ("hatch", 0.5)],
        big=[("fan_house", 0.3)],
        deck=[("raft", 0.08), ("vent_box", 0.2), ("hatch", 0.25), ("reel", 0.25), ("dc_rack", 0.0)],
        boats=["whaleboat"], max_boats=2, nest=False, scuttles=False, roof_planks=0.0, roof_rails=True),
}

MARGIN = 0.45      # clear space round every item and from a roof's edge, m
BOAT_ROOF_W = 8.0  # a roof this wide (and wider) carries boats
# Roof counts grow with area only up to about ROOF_SAT m^2, then with its square root: a long boat deck between
# the funnels (Kongo, Dante) held boats and a few vents, not gear strewn end to end at the small-roof density.
# Roofs at level 3 and up (bridge and fire-control platforms) carry HIGH_ROOF of the count. Decks keep the
# plain per-area count.
ROOF_SAT = 600.0
HIGH_ROOF = 0.6
# The rest of a big roof's area goes to the kit's big gear, and each m^2 the big gear covers takes BIG_SHARE m^2
# from the area the small items count (the clear space round a fan house or a skylight is part of it).
BIG_SHARE = 5.0
NEAR_FUNNEL = 7.0


# ----------------------------------------------------------------------------
# geometry
# ----------------------------------------------------------------------------
def _rect(x, y, l, w):
    return (x - l / 2, y - w / 2, x + l / 2, y + w / 2)


def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _samples(r, step=0.6):
    """Points over the rectangle r, its corners and edges included."""
    nx = max(1, math.ceil((r[2] - r[0]) / step))
    ny = max(1, math.ceil((r[3] - r[1]) / step))
    return [(r[0] + (r[2] - r[0]) * i / nx, r[1] + (r[3] - r[1]) * j / ny) for i in range(nx + 1) for j in range(ny + 1)]


def inset_polygon(pts, d):
    """The polygon moved inward by d (each edge offset, neighbours intersected); fine for the gentle outlines of
    superstructure blocks."""
    n = len(pts)
    area2 = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))
    sgn = 1 if area2 > 0 else -1
    lines = []
    for i in range(n):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
        dx, dy = x1 - x0, y1 - y0
        ln = math.hypot(dx, dy) or 1e-9
        nx, ny = -dy / ln * sgn, dx / ln * sgn     # inward normal
        lines.append(((x0 + nx * d, y0 + ny * d), (dx, dy)))
    out = []
    for i in range(n):
        (p, r), (q, s) = lines[i - 1], lines[i]
        den = r[0] * s[1] - r[1] * s[0]
        if abs(den) < 1e-9:
            out.append(q)
            continue
        t = ((q[0] - p[0]) * s[1] - (q[1] - p[1]) * s[0]) / den
        out.append((p[0] + t * r[0], p[1] + t * r[1]))
    return out


class _Surface:
    """An open roof (a superstructure block) or the deck, as a polygon plus what stands higher on it."""

    def __init__(self, pts, level, kind, block=None):
        self.pts, self.level, self.kind, self.block = pts, level, kind, block
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        self.bbox = (min(xs), min(ys), max(xs), max(ys))
        self.area = polygon_area(pts)
        self.inner = inset_polygon(pts, MARGIN) if len(pts) >= 3 else pts

    def holds(self, r):
        return all(point_in_polygon(x, y, self.inner) for x, y in _samples(r))


class Placer:
    def __init__(self, spec, hull, turret_types):
        self.spec, self.hull = spec, hull
        self.blocks = [b for b in spec.get("superstructure") or [] if not b.get("director")]
        self.block_polys = [(b.get("level", 1), block_outline(b)) for b in self.blocks]
        self.directors = [block_outline(b) for b in spec.get("superstructure") or [] if b.get("director")]
        self.circles, self.rects = [], []
        for m in spec.get("turrets") or []:
            t = turret_types[m["type"]]
            self.circles.append((m["x"], m.get("y", 0), t["r"] * 1.2))
        for a in spec.get("aa") or []:
            self.circles.append((a["x"], a["y"], 2.4))
        self.funnels = [(fn["x"], fn["l"]) for fn in spec.get("funnels") or []]
        for fn in spec.get("funnels") or []:
            self.rects.append(_rect(fn["x"], fn.get("y", 0), fn["l"] + 1.6, fn["w"] + 1.6))
        for m in spec.get("masts") or []:
            self.circles.append((m["x"], m.get("y", 0), 1.4))
            if m.get("tripod", True):   # the legs run aft; keep them clear whichever look draws them
                self.rects.append((m["x"] - 5.5, m.get("y", 0) - 4.0, m["x"] + 0.5, m.get("y", 0) + 4.0))
        for b in (spec.get("boats") or []) + (spec.get("fittings") or []) + (spec.get("hatches") or []):
            self.rects.append(_rect(b["x"], b["y"], b.get("l", 7) + 0.8, b.get("w", 2.2) + 0.8))
        for c in spec.get("cranes") or []:
            self.circles.append((c["x"], c.get("y", 0), 2.0))
        for bx in spec.get("bollards") or []:   # a pair of bitts each side by the deck edge
            by = hull.half_width(bx) - 1.1
            self.rects += [(bx - 0.6, s * by - 0.6, bx + 1.5, s * by + 0.6) for s in (-1, 1)]
        if spec.get("chain_x"):
            self.rects.append((spec["chain_x"] - 1.5, -hull.B, hull.L, hull.B))
        if spec.get("breakwater_x"):
            self.rects.append((spec["breakwater_x"] - hull.B * 0.4, -hull.B, spec["breakwater_x"] + 1.0, hull.B))
        self.taken = []

    def free(self, surf, r):
        if not surf.holds(r):
            return False
        g = (r[0] - MARGIN, r[1] - MARGIN, r[2] + MARGIN, r[3] + MARGIN)
        if any(_overlap(g, t) for t in self.taken) or any(_overlap(g, t) for t in self.rects):
            return False
        for cx, cy, cr in self.circles:
            dx = max(g[0] - cx, 0, cx - g[2])
            dy = max(g[1] - cy, 0, cy - g[3])
            if dx * dx + dy * dy < cr * cr:
                return False
        pts = _samples(g, 0.5)
        for lvl, poly in self.block_polys:
            if (surf.kind == "deck" or lvl > surf.level) and any(point_in_polygon(x, y, poly) for x, y in pts):
                return False
        if any(point_in_polygon(x, y, poly) for poly in self.directors for x, y in pts):
            return False
        if surf.kind == "deck":
            lv = {self.deck_level(x) for x, _ in ((g[0], 0), (g[2], 0))}
            if len(lv) > 1:          # astride a break in the deck
                return False
        return True

    def deck_level(self, x):
        return max([rd.get("levels", 1) for rd in self.spec.get("raised_decks") or [] if rd["x0"] <= x <= rd["x1"]],
                   default=0)


# ----------------------------------------------------------------------------
# placement
# ----------------------------------------------------------------------------
def surfaces(spec, hull):
    out = []
    for b in spec.get("superstructure") or []:
        if b.get("director") or b.get("vents") is False:
            continue
        out.append(_Surface(block_outline(b), b.get("level", 1), "roof", b))
    # the deck as a polygon a little inside its edge
    n = 80
    xs = [-hull.L / 2 + hull.L * (i + 0.5) / n for i in range(n)]
    top = [(x, -max(0.0, hull.half_width(x) - 0.6)) for x in xs]
    bot = [(x, max(0.0, hull.half_width(x) - 0.6)) for x in reversed(xs)]
    out.append(_Surface(top + bot, 0, "deck"))
    return out


def _mirror_ys(surf, x, l, w, place, rng, centre_p=0.0):
    """Candidate y positions (each a tuple placed together) for an item at x."""
    lo = hi = None
    for xx in (x - l / 2, x, x + l / 2):
        sp = polygon_y_span(surf.inner, xx)
        if sp is None:
            return []
        lo, hi = (sp[0], sp[1]) if lo is None else (max(lo, sp[0]), min(hi, sp[1]))
    if hi - lo < w:
        return []
    on_centre = lo + w / 2 <= 0 <= hi - w / 2
    if place == "centre" or (on_centre and rng.random() < centre_p):
        return [(0.0,)] if on_centre else []
    edge = min(-lo, hi) - w / 2 - 0.05
    if place == "edge" or (place == "row" and rng.random() < 0.5):
        return [(-edge, edge)] if edge > w / 2 else []
    if edge > w / 2 + MARGIN:   # anywhere across, mirrored
        y = rng.uniform(w / 2 + MARGIN, edge)
        return [(-y, y)]
    return [(0.0,)] if on_centre else []   # too narrow for a pair: one on the centreline


def _spread(P, surf, xs, ys):
    """How far a candidate stands from what's already placed, the obstacles, its mirror twin and the surface's
    edge (counted double, so items don't all run to the sides). Bigger is emptier."""
    best = 1e9
    for x in xs:
        for y in ys:
            for r in P.taken:
                best = min(best, math.hypot(x - (r[0] + r[2]) / 2, y - (r[1] + r[3]) / 2))
            for cx, cy, cr in P.circles:
                best = min(best, math.hypot(x - cx, y - cy) - cr)
            if len(ys) == 2:
                best = min(best, 2 * abs(y))
            sp = polygon_y_span(surf.inner, x)
            if sp:
                best = min(best, 2 * min(y - sp[0], sp[1] - y) + 1.0)
    return best


def _open_area(surf):
    """The area the kit's small counts scale with (ROOF_SAT, HIGH_ROOF)."""
    if surf.kind == "deck":
        return surf.area
    a = surf.area if surf.area <= ROOF_SAT else math.sqrt(surf.area * ROOF_SAT)
    return a * (HIGH_ROOF if surf.level >= 3 else 1.0)


def _big_area(surf):
    """The area the kit's big counts scale with: what ROOF_SAT left out of the small count."""
    if surf.kind == "deck" or surf.area <= ROOF_SAT:
        return 0.0
    return (surf.area - math.sqrt(surf.area * ROOF_SAT)) * (HIGH_ROOF if surf.level >= 3 else 1.0)


CANDIDATES = 8   # valid spots tried per item; the emptiest wins (best-candidate sampling: an even spread)


def place_items(P, surf, kit_items, density, rng, area):
    """Scatter the kit's items over one surface: (kind, x, y) tuples, spread evenly over the open area. Counts are
    per 100 m^2 of area."""
    out = []
    x0, _, x1, _ = surf.bbox
    L = P.hull.L
    for kind, per100 in kit_items:
        it = ITEMS[kind]
        near = [(fx - fl / 2 - NEAR_FUNNEL, fx + fl / 2 + NEAR_FUNNEL) for fx, fl in P.funnels
                if fx + fl / 2 + NEAR_FUNNEL > x0 and fx - fl / 2 - NEAR_FUNNEL < x1] if it.get("near") else []
        if it.get("near") and not near:
            continue
        want = area / 100.0 * per100 * density
        n = int(want) + (1 if rng.random() < want - int(want) else 0)
        fails = 0
        while n > 0 and fails < 3:
            cands = []
            for _ in range(40):
                if len(cands) >= CANDIDATES:
                    break
                if near:
                    a, b = rng.choice(near)
                    x = rng.uniform(max(a, x0), min(b, x1))
                else:
                    x = rng.uniform(x0, x1)
                ends = it.get("ends", 0.0) or (it.get("deck_ends", 0.0) if surf.kind == "deck" else 0.0)
                if abs(x) < ends * L:
                    continue
                yss = _mirror_ys(surf, x, it["l"], it["w"], it["place"], rng, it.get("centre_p", 0.0))
                if not yss:
                    continue
                ys = yss[0]
                count = rng.choice((2, 3, 3, 4)) if it["place"] == "row" else 1
                xs = [x + (k - (count - 1) / 2) * (it["l"] + 0.25) for k in range(count)]
                rs = [_rect(xx, y, it["l"], it["w"]) for xx in xs for y in ys]
                if all(P.free(surf, r) for r in rs):
                    cands.append((_spread(P, surf, xs, ys), xs, ys, rs))
            if not cands:
                fails += 1
                continue
            _, xs, ys, rs = max(cands, key=lambda c: c[0])
            P.taken.extend(rs)
            out.extend((kind, xx, y) for xx in xs for y in ys)
            n -= len(rs)   # every item counts, a row of four as four
    return out


def place_boats(P, surf, kit, rng):
    """Boats in rows along a wide roof (the boat deck): an outboard pair of rows, then the centreline, each
    filled from aft to fore with the kit's boats in turn, as many as fit (up to kit "max_boats")."""
    out = []
    x0, _, x1, _ = surf.bbox
    pool = list(kit["boats"])
    k = rng.randrange(len(pool))
    for row in ("outboard", "centre"):
        x = x0
        while x < x1 and len(out) < kit.get("max_boats", 8):
            for j in range(len(pool)):
                name = pool[(k + j) % len(pool)]
                l, w = BOATS[name]
                cx = x + l / 2
                sp = [polygon_y_span(surf.inner, xx) for xx in (cx - l / 2, cx, cx + l / 2)]
                if any(s_ is None for s_ in sp):
                    continue
                edge = min(min(-s_[0], s_[1]) for s_ in sp) - w / 2 - 0.2
                if row == "outboard":
                    if edge < w / 2 + 0.6:
                        continue
                    ys = (-edge, edge)
                else:
                    ys = (0.0,)
                rs = [_rect(cx, y, l + 0.2, w + 0.2) for y in ys]
                if all(P.free(surf, r) for r in rs):
                    P.taken.extend(rs)
                    out += [(name, cx, y) for y in ys]
                    k += j + 1
                    x += l + 0.6
                    break
            else:
                x += 0.5
    return out


def plan(spec, hull, turret_types, shapes):
    """Every clutter item for the ship: a list of dicts {kind, x, y, l, w, h, level, boat?}. Repeatable."""
    kit = KITS.get(shapes.get("clutter") or "")
    if not kit:
        return []
    density = shapes.get("clutter_density", 1.0)
    rng = random.Random(f'{spec["id"]}/clutter/{shapes.get("clutter")}')
    P = Placer(spec, hull, turret_types)
    items = []
    surfs = surfaces(spec, hull)
    for s in surfs:   # what's left open once the blocks above are drawn over it
        x0, y0, x1, y1 = s.bbox
        pts = [(x0 + 0.5 + i, y0 + 0.5 + j) for i in range(int(x1 - x0)) for j in range(int(y1 - y0))]
        pts = [q for q in pts if point_in_polygon(*q, s.pts)]
        above = [poly for lvl, poly in P.block_polys if s.kind == "deck" or lvl > s.level]
        s.area = sum(1 for q in pts if not any(point_in_polygon(*q, poly) for poly in above))
    # boats first, on the widest open roofs (the boat deck)
    if kit["boats"] and not spec.get("flight_deck"):
        roofs = sorted((s for s in surfs if s.kind == "roof" and s.bbox[3] - s.bbox[1] >= BOAT_ROOF_W
                        and s.area >= 60), key=lambda s: -s.area)
        for s in roofs[:1]:
            for name, x, y in place_boats(P, s, kit, rng):
                l, w = BOATS[name]
                items.append(dict(kind="boat", boat=name, x=x, y=y, l=l, w=w, h=1.4, level=s.level, nest=kit["nest"]))
    for s in surfs:
        if spec.get("flight_deck") and s.kind == "deck":
            continue
        area = _open_area(s)
        if s.kind == "roof" and kit.get("big") and _big_area(s) > 0:   # the big gear first, then less small gear
            big = place_items(P, s, kit["big"], density, rng, _big_area(s))
            area = max(0.0, area - BIG_SHARE * sum(ITEMS[k]["l"] * ITEMS[k]["w"] for k, _, _ in big))
        else:
            big = []
        small = place_items(P, s, kit["roof"] if s.kind == "roof" else kit["deck"], density, rng, area)
        for kind, x, y in big + small:
            it = ITEMS[kind]
            items.append(dict(kind=kind, x=x, y=y, l=it["l"], w=it["w"], h=it["h"], level=s.level,
                              face=rng.choice((1, 1, -1, 0))))
    deck = surfs[-1]
    if kit.get("scuttles") and not spec.get("flight_deck"):   # coal scuttles in pairs along the sides amidships
        L = hull.L
        x = -0.2 * L
        while x < 0.2 * L:
            hw = hull.half_width(x) - 1.3
            rs = [_rect(x, s * hw, 0.5, 0.5) for s in (-1, 1)]
            if hw > 2 and all(P.free(deck, r) for r in rs):
                P.taken.extend(rs)
                items += [dict(kind="scuttle", x=x, y=s * hw, l=0.5, w=0.5, h=0.0, level=0) for s in (-1, 1)]
            x += 4.5
    if "dc_rack" in dict(kit["deck"]) and hull.L < 140 and not spec.get("flight_deck"):   # depth charges at the stern
        for x in (-hull.L / 2 + 3.0, -hull.L / 2 + 4.5, -hull.L / 2 + 6.0):
            hw = min(hull.half_width(x - 2.0), hull.half_width(x + 2.0)) - 1.3
            rs = [_rect(x, s * (hw - 0.6), 4.0, 1.2) for s in (-1, 1)]
            if hw > 2 and all(P.free(deck, r) for r in rs):
                P.taken.extend(rs)
                items += [dict(kind="dc_rack", x=x, y=s * (hw - 0.6), l=4.0, w=1.2, h=1.0, level=0) for s in (-1, 1)]
                break
    return items


# ----------------------------------------------------------------------------
# drawing
# ----------------------------------------------------------------------------
def draw(it, P, surface_col):
    """SVG for one item. P is the Painter (palette, stroke); surface_col the colour it stands on."""
    from shipgen import f, shade, poly, rrect_path
    p = P.p
    x, y, l, w = it["x"], it["y"], it["l"], it["w"]
    k = it["kind"]
    metal = shade(surface_col, 0.8)
    dark = "#1d2125"
    st = P.stroke(0.6)
    if k in ("cowl", "cowl_small", "boiler_cowl"):   # a cowl ventilator: the round trunk and its bell mouth turned to the wind
        r = l / 2
        fx = it.get("face", 1)
        mx, my = (x + fx * r * 0.25, y) if fx else (x, y + (r * 0.25 if y >= 0 else -r * 0.25))
        return (f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" fill="{shade(surface_col, 0.92)}" {st}/>'
                f'<ellipse cx="{f(mx)}" cy="{f(my)}" rx="{f(r * (0.45 if fx else 0.62))}" ry="{f(r * (0.62 if fx else 0.45))}" '
                f'fill="{dark}"/>')
    if k == "mushroom":
        r = l / 2
        return (f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" fill="{metal}" {st}/>'
                f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r * 0.45)}" fill="{shade(surface_col, 1.08)}"/>')
    if k == "vent_box":
        s = [f'<rect x="{f(x - l / 2)}" y="{f(y - w / 2)}" width="{f(l)}" height="{f(w)}" rx="0.1" fill="{metal}" {st}/>']
        for i in range(1, 4):
            xx = x - l / 2 + l * i / 4
            s.append(f'<line x1="{f(xx)}" y1="{f(y - w / 2 + 0.15)}" x2="{f(xx)}" y2="{f(y + w / 2 - 0.15)}" '
                     f'stroke="{shade(metal, 0.7)}" stroke-width="{f(P.sw * 0.8)}"/>')
        return "".join(s)
    if k in ("skylight", "engine_skylight"):   # a pitched glazed skylight: frame, two glass slopes and the glazing bars
        glass = p.get("glass", "#5f7782")
        s = [f'<rect x="{f(x - l / 2)}" y="{f(y - w / 2)}" width="{f(l)}" height="{f(w)}" rx="0.1" '
             f'fill="{p["fitting"]}" {st}/>',
             f'<rect x="{f(x - l / 2 + 0.2)}" y="{f(y - w / 2 + 0.2)}" width="{f(l - 0.4)}" height="{f(w / 2 - 0.2)}" '
             f'fill="{shade(glass, 1.15)}"/>',
             f'<rect x="{f(x - l / 2 + 0.2)}" y="{f(y)}" width="{f(l - 0.4)}" height="{f(w / 2 - 0.2)}" fill="{glass}"/>']
        n = max(2, int(l / 0.6))
        for i in range(1, n):
            xx = x - l / 2 + l * i / n
            s.append(f'<line x1="{f(xx)}" y1="{f(y - w / 2 + 0.2)}" x2="{f(xx)}" y2="{f(y + w / 2 - 0.2)}" '
                     f'stroke="{p["fitting"]}" stroke-width="{f(P.sw * 0.7)}"/>')
        return "".join(s)
    if k == "hatch":   # a companionway: a box with its sliding hood
        return (f'<rect x="{f(x - l / 2)}" y="{f(y - w / 2)}" width="{f(l)}" height="{f(w)}" rx="0.1" '
                f'fill="{shade(surface_col, 0.88)}" {st}/>'
                f'<path d="{rrect_path(x - l / 2 + 0.15, y - w / 2 + 0.15, x + 0.1, y + w / 2 - 0.15, 0.0, 0.35)}" '
                f'fill="{shade(surface_col, 1.08)}" {P.stroke(0.4)}/>')
    if k == "capstan":
        r = l / 2
        s = [f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" fill="{p["fitting"]}" {st}/>',
             f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r * 0.55)}" fill="{shade(p["fitting"], 1.3)}"/>']
        for a in range(0, 360, 45):
            s.append(f'<line x1="{f(x)}" y1="{f(y)}" x2="{f(x + r * math.cos(math.radians(a)))}" '
                     f'y2="{f(y + r * math.sin(math.radians(a)))}" stroke="{shade(p["fitting"], 0.6)}" '
                     f'stroke-width="{f(P.sw * 0.7)}"/>')
        return "".join(s)
    if k == "reel":   # a hose or wire reel on its frame
        return (f'<rect x="{f(x - l / 2)}" y="{f(y - w / 2)}" width="{f(l)}" height="{f(w)}" fill="{p["fitting"]}" {st}/>'
                f'<rect x="{f(x - l / 2 + 0.2)}" y="{f(y - w / 2 + 0.1)}" width="{f(l - 0.4)}" height="{f(w - 0.2)}" '
                f'fill="{shade(p["fitting"], 0.65)}"/>'
                + "".join(f'<line x1="{f(x - l / 2 + 0.2)}" y1="{f(y - w / 2 + w * i / 5)}" x2="{f(x + l / 2 - 0.2)}" '
                          f'y2="{f(y - w / 2 + w * i / 5)}" stroke="{shade(p["fitting"], 1.2)}" stroke-width="{f(P.sw * 0.6)}"/>'
                          for i in range(1, 5)))
    if k == "locker":   # a ready-use ammunition locker
        return (f'<rect x="{f(x - l / 2)}" y="{f(y - w / 2)}" width="{f(l)}" height="{f(w)}" rx="0.08" '
                f'fill="{shade(surface_col, 0.9)}" {st}/>'
                f'<line x1="{f(x)}" y1="{f(y - w / 2)}" x2="{f(x)}" y2="{f(y + w / 2)}" stroke="{shade(surface_col, 0.65)}" '
                f'stroke-width="{f(P.sw * 0.7)}"/>')
    if k == "float":   # a Carley float: an oval ring round its net
        col = p.get("float", "#b7a87e")
        return (f'<path d="{rrect_path(x - l / 2, y - w / 2, x + l / 2, y + w / 2, w / 2, w / 2)}" fill="{col}" {st}/>'
                f'<path d="{rrect_path(x - l / 2 + 0.25, y - w / 2 + 0.25, x + l / 2 - 0.25, y + w / 2 - 0.25, w / 2 - 0.25, w / 2 - 0.25)}" '
                f'fill="{shade(col, 0.55)}"/>')
    if k == "raft":   # an inflatable liferaft canister lying across its cradle
        col = p.get("raft", "#e9e7e0")
        return (f'<path d="{rrect_path(x - l / 2, y - w / 2, x + l / 2, y + w / 2, l / 2, l / 2)}" fill="{col}" {st}/>'
                f'<line x1="{f(x - l / 2)}" y1="{f(y)}" x2="{f(x + l / 2)}" y2="{f(y)}" stroke="{shade(col, 0.7)}" '
                f'stroke-width="{f(P.sw * 0.7)}"/>')
    if k == "searchlight":   # a round platform with its lamp
        r = l / 2
        return (f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" fill="{shade(surface_col, 0.85)}" {st}/>'
                f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r * 0.5)}" fill="{p["fitting"]}" {P.stroke(0.5)}/>'
                f'<circle cx="{f(x + r * 0.28)}" cy="{f(y)}" r="{f(r * 0.3)}" fill="#d9dccf"/>')
    if k == "searchlight_tower":   # a raised platform with its rail, the lamp on it
        r = l / 2
        return (f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" fill="{shade(surface_col, 0.8)}" {st}/>'
                f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r - 0.2)}" fill="none" stroke="{p["mast"]}" '
                f'stroke-width="{f(max(0.1, P.sw * 0.8))}" stroke-dasharray="0.12 0.9" stroke-opacity="0.8"/>'
                f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r * 0.4)}" fill="{p["fitting"]}" {P.stroke(0.5)}/>'
                f'<circle cx="{f(x + r * 0.2)}" cy="{f(y)}" r="{f(r * 0.24)}" fill="#d9dccf"/>')
    if k == "fan_house":   # a boiler-room fan house: a steel box, louvres down both sides, a cap on top
        s = [f'<rect x="{f(x - l / 2)}" y="{f(y - w / 2)}" width="{f(l)}" height="{f(w)}" rx="0.15" fill="{metal}" {st}/>',
             f'<rect x="{f(x - l / 2 + 0.5)}" y="{f(y - w / 2 + 0.55)}" width="{f(l - 1.0)}" height="{f(w - 1.1)}" rx="0.1" '
             f'fill="{shade(metal, 1.12)}" {P.stroke(0.5)}/>']
        for i in range(1, 9):
            xx = x - l / 2 + l * i / 9
            for y0_, y1_ in ((y - w / 2 + 0.1, y - w / 2 + 0.45), (y + w / 2 - 0.45, y + w / 2 - 0.1)):
                s.append(f'<line x1="{f(xx)}" y1="{f(y0_)}" x2="{f(xx)}" y2="{f(y1_)}" stroke="{dark}" '
                         f'stroke-width="{f(P.sw * 0.8)}" stroke-opacity="0.7"/>')
        return "".join(s)
    if k == "scuttle":
        return (f'<circle cx="{f(x)}" cy="{f(y)}" r="0.25" fill="{p["fitting"]}" {P.stroke(0.5)}/>'
                f'<circle cx="{f(x)}" cy="{f(y)}" r="0.13" fill="{dark}"/>')
    if k == "paravane":   # a paravane on the deck edge: a stubby torpedo with its fins
        col = p.get("paravane", shade(p["fitting"], 1.35))
        return (f'<path d="{rrect_path(x - l / 2, y - 0.2, x + l / 2, y + 0.2, 0.2, 0.2)}" fill="{col}" {st}/>'
                f'<path d="M{f(x - l / 2 + 0.3)},{f(y - w / 2)} L{f(x - l / 2 + 0.9)},{f(y)} L{f(x - l / 2 + 0.3)},{f(y + w / 2)} Z" '
                f'fill="{col}" {P.stroke(0.5)}/>')
    if k == "dc_rack":   # a depth-charge rack: two rails and the drums between them
        s = [f'<rect x="{f(x - l / 2)}" y="{f(y - w / 2)}" width="{f(l)}" height="{f(w)}" fill="none" '
             f'stroke="{p["fitting"]}" stroke-width="{f(P.sw * 1.2)}"/>']
        for i in range(5):
            s.append(f'<circle cx="{f(x - l / 2 + 0.4 + i * (l - 0.8) / 4)}" cy="{f(y)}" r="0.38" '
                     f'fill="{shade(p["fitting"], 0.8)}" {P.stroke(0.5)}/>')
        return "".join(s)
    if k == "boat":
        return draw_boat(it, P)
    return ""


def _boat_path(x, y, l, w, double=False):
    from shipgen import f
    x0, x1 = x - l / 2, x + l / 2
    if double:   # a whaler: pointed both ends
        return (f'M{f(x0)},{f(y)} C{f(x0 + 0.25 * l)},{f(y - 0.55 * w)} {f(x1 - 0.25 * l)},{f(y - 0.55 * w)} {f(x1)},{f(y)} '
                f'C{f(x1 - 0.25 * l)},{f(y + 0.55 * w)} {f(x0 + 0.25 * l)},{f(y + 0.55 * w)} {f(x0)},{f(y)} Z')
    return (f'M{f(x0)},{f(y - 0.36 * w)} C{f(x0 + 0.5 * l)},{f(y - 0.56 * w)} {f(x0 + 0.85 * l)},{f(y - 0.42 * w)} {f(x1)},{f(y)} '
            f'C{f(x0 + 0.85 * l)},{f(y + 0.42 * w)} {f(x0 + 0.5 * l)},{f(y + 0.56 * w)} {f(x0)},{f(y + 0.36 * w)} Z')


def draw_boat(it, P):
    """A ship's boat on its chocks, bow forward: the hull, the inside, thwarts, and per kind a cabin, funnel or
    canopy. Victorian and Great War cutters carry a dinghy nested inside."""
    from shipgen import f, shade
    p = P.p
    x, y, l, w, kind = it["x"], it["y"], it["l"], it["w"], it["boat"]
    col = p["boat"]
    double = kind in ("whaler", "gig")
    s = []
    for cx in (x - 0.28 * l, x + 0.22 * l):   # chocks
        s.append(f'<rect x="{f(cx - 0.2)}" y="{f(y - w / 2 - 0.25)}" width="0.4" height="{f(w + 0.5)}" '
                 f'fill="{p["fitting"]}" {P.stroke(0.5)}/>')
    s.append(f'<path d="{_boat_path(x, y, l, w, double)}" fill="{col}" {P.stroke()}/>')
    if kind in ("pinnace", "launch", "whaleboat"):   # decked boats
        s.append(f'<path d="{_boat_path(x, y, l - 0.6, w - 0.5)}" fill="{shade(col, 0.9)}"/>')
        if kind == "pinnace":
            s.append(f'<rect x="{f(x - 0.35 * l)}" y="{f(y - 0.3 * w)}" width="{f(0.3 * l)}" height="{f(0.6 * w)}" rx="0.2" '
                     f'fill="{shade(col, 1.05)}" {P.stroke(0.6)}/>'
                     f'<circle cx="{f(x + 0.05 * l)}" cy="{f(y)}" r="{f(0.16 * w)}" fill="{p["funnel"]}" {P.stroke(0.6)}/>'
                     f'<circle cx="{f(x + 0.05 * l)}" cy="{f(y)}" r="{f(0.09 * w)}" fill="{p.get("funnel_cap", "#222")}"/>')
        elif kind == "launch":
            s.append(f'<rect x="{f(x - 0.05 * l)}" y="{f(y - 0.3 * w)}" width="{f(0.32 * l)}" height="{f(0.6 * w)}" rx="0.25" '
                     f'fill="{shade(col, 1.06)}" {P.stroke(0.6)}/>')
        else:
            s.append(f'<path d="{_boat_path(x + 0.12 * l, y, 0.62 * l, w - 0.4)}" fill="{shade(col, 0.78)}" {P.stroke(0.5)}/>')
        return "".join(s)
    s.append(f'<path d="{_boat_path(x, y, l - 0.5, w - 0.45, double)}" fill="{shade(col, 0.72)}"/>')
    for i in range(1, 5):   # thwarts
        tx = x - l / 2 + l * i / 5
        s.append(f'<line x1="{f(tx)}" y1="{f(y - 0.38 * w)}" x2="{f(tx)}" y2="{f(y + 0.38 * w)}" stroke="{shade(col, 0.9)}" '
                 f'stroke-width="{f(max(0.15, P.sw))}"/>')
    if it.get("nest") and kind == "cutter":   # a dinghy stowed inside
        dl, dw = 0.5 * l, 0.62 * w
        s.append(f'<path d="{_boat_path(x - 0.05 * l, y, dl, dw)}" fill="{shade(col, 1.04)}" {P.stroke(0.6)}/>'
                 f'<path d="{_boat_path(x - 0.05 * l, y, dl - 0.35, dw - 0.3)}" fill="{shade(col, 0.8)}"/>')
    return "".join(s)


def roof_finish(b, P, kit, area_min, rails, wood):
    """A block's roof: planked like a deck (Victorian boat decks and the like) inside a steel waterway, and a
    guardrail round its edge. Drawn over the block, under whatever stands on it."""
    from shipgen import f, shade, poly
    pts = block_outline(b)
    if len(pts) < 3:
        return ""
    s = []
    lvl = b.get("level", 1)
    if area_min and polygon_area(pts) >= area_min:
        inner = inset_polygon(pts, 0.7)
        col = shade(wood, 1.03 ** lvl)
        P._clip_n += 1
        cid = f"rp{P._clip_n}"
        xs = [q[0] for q in inner]
        ys = [q[1] for q in inner]
        lines = []
        yy = min(ys)
        while yy < max(ys):
            lines.append(f'<line x1="{f(min(xs))}" y1="{f(yy)}" x2="{f(max(xs))}" y2="{f(yy)}"/>')
            yy += 1.0
        xx = min(xs)
        while xx < max(xs):
            lines.append(f'<line x1="{f(xx)}" y1="{f(min(ys))}" x2="{f(xx)}" y2="{f(max(ys))}" stroke-dasharray="1 2"/>')
            xx += 7.0
        s.append(f'<clipPath id="{cid}"><path d="{poly(inner)}"/></clipPath>'
                 f'<path d="{poly(inner)}" fill="{col}"/>'
                 f'<g clip-path="url(#{cid})" stroke="{P.p["deck_line"]}" stroke-width="{f(P.sw * 0.6)}" '
                 f'stroke-opacity="0.4">{"".join(lines)}</g>')
    if rails and polygon_area(pts) >= 12.0:
        rl = inset_polygon(pts, 0.2)
        s.append(f'<path d="{poly(rl)}" fill="none" stroke="{P.p["mast"]}" stroke-width="{f(max(0.06, P.sw * 0.5))}" '
                 f'stroke-opacity="0.55"/>'
                 f'<path d="{poly(rl)}" fill="none" stroke="{P.p["mast"]}" stroke-width="{f(max(0.14, P.sw * 1.1))}" '
                 f'stroke-dasharray="0.12 1.4" stroke-opacity="0.7"/>')
    return "".join(s)


def height_columns(items, columns, hull):
    """Height-map columns for the items, each standing on whatever column is tallest under its centre."""
    def under(x, y):
        best = 0.0
        for c in columns:
            sh = c["shape"]
            if sh == "hull":
                inside = abs(y) <= hull.half_width(x)
            elif sh == "polygon":
                inside = point_in_polygon(x, y, c["points"])
            elif sh == "rect":
                inside = c["x"] <= x <= c["x"] + c["w"] and c["y"] <= y <= c["y"] + c["h"]
            elif sh == "circle":
                inside = (x - c["cx"]) ** 2 + (y - c["cy"]) ** 2 <= c["r"] ** 2
            elif sh == "ellipse":
                inside = ((x - c["cx"]) / c["rx"]) ** 2 + ((y - c["cy"]) / c["ry"]) ** 2 <= 1
            else:
                inside = False
            if inside:
                best = max(best, c["top"])
        return best
    out = []
    for it in items:
        if it["h"] <= 0:
            continue
        base = under(it["x"], it["y"])
        if it["kind"] in ("cowl", "cowl_small", "boiler_cowl", "mushroom", "searchlight", "searchlight_tower"):
            out.append(dict(top=base + it["h"], shape="circle", cx=it["x"], cy=it["y"], r=it["l"] / 2))
        elif it["kind"] == "boat":
            out.append(dict(top=base + it["h"], shape="ellipse", cx=it["x"], cy=it["y"], rx=it["l"] / 2, ry=it["w"] / 2))
        else:
            out.append(dict(top=base + it["h"], shape="rect", x=it["x"] - it["l"] / 2, y=it["y"] - it["w"] / 2,
                            w=it["l"], h=it["w"]))
    return out
