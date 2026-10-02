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

import math

from geometry import (make_turret_type, make_torpedo_type, rrect_polygon, rrect_clamped, circle_polygon,
                      turret_shapes, turret_height, turret_reach, point_in_polygon, polygons_intersect,
                      sector_polygon)
from navarch import Weight, mount_weights, torpedo_weight, machinery_length, funnel_count, TUNING
from hitbox import ARC_BEAM
from shipgen import Hull, AA_CFG

LEVEL_H = 2.6  # height of one superstructure level, metres


# ---------------------------------------------------------------------------
# small collision helpers (circles and axis-aligned rects)
# ---------------------------------------------------------------------------
def _fp_circle(x, y, r):
    return ("c", x, y, r)


def _fp_rect(x0, y0, x1, y1):
    return ("r", x0, y0, x1, y1)


def _overlap(a, b, margin=0.0):
    if a[0] == "c" and b[0] == "c":
        return math.hypot(a[1] - b[1], a[2] - b[2]) < a[3] + b[3] + margin
    if a[0] == "r" and b[0] == "r":
        return not (a[3] + margin <= b[1] or b[3] + margin <= a[1] or a[4] + margin <= b[2] or b[4] + margin <= a[2])
    c, r = (a, b) if a[0] == "c" else (b, a)
    nx = min(max(c[1], r[1]), r[3])
    ny = min(max(c[2], r[2]), r[4])
    return math.hypot(c[1] - nx, c[2] - ny) < c[3] + margin


class Layout:
    def __init__(self):
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

    def free(self, fp, margin=0.4, ignore=()):
        return not any(_overlap(fp, o[0], margin) for o in self.footprints if o[3] not in ignore)

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
        self.sweeps.append(dict(owner=m["id"], polys=polys, axis=m["base"] + 0.55 * (m["top"] - m["base"])))

    def clear(self, poly, top):
        """Is a footprint (polygon or circle/rect footprint) standing `top` metres above the deck clear of every
        gun sweep lower than it?"""
        if isinstance(poly, tuple):
            poly = (circle_polygon(poly[1], poly[2], poly[3], 16) if poly[0] == "c" else
                    [(poly[1], poly[2]), (poly[3], poly[2]), (poly[3], poly[4]), (poly[1], poly[4])])
        return not any(sw["axis"] < top and any(polygons_intersect(poly, p) for p in sw["polys"])
                       for sw in self.sweeps)

    def on_deck(self, x, y):
        """Is (x, y) on a deck that overhangs the hull (a flight deck)?"""
        return any(point_in_polygon(x, y, dk["points"]) for dk in self.decks if dk["kind"] == "flight_deck")


def add_block(lay, blocks, bid, x0, x1, w, level, rf, rb, y=0.0, z0=0.0, layer=None, kind="superstructure",
              t_per_m2=None):
    """Superstructure block standing on z0 (metres above the main deck): footprint, weight, record.
    Blocks above the main deck go on the upper sprite layer."""
    rf_, rb_ = rrect_clamped(x0, y - w / 2, x1, y + w / 2, rf, rb)
    b = dict(id=bid, kind=kind, x0=x0, x1=x1, y=y, w=w, level=level, rf=rf_, rb=rb_)
    if z0:
        b["z0"] = z0
    if layer or z0:
        b["layer"] = layer or "upper"
    blocks.append(b)
    lay.occupy(_fp_rect(x0, y - w / 2, x1, y + w / 2), block_base(b), block_top(b), bid)
    t_per_m2 = TUNING["superstructure_t_per_m2"] if t_per_m2 is None else t_per_m2
    lay.weights.append(Weight(bid, "superstructure", (x1 - x0) * w * t_per_m2,
                              x=(x0 + x1) / 2, z_rel=("deck", (block_base(b) + block_top(b)) / 2)))
    return b


# ---------------------------------------------------------------------------
def block_base(b):
    """Height of a superstructure block's floor above the main deck (z0 = what it stands on)."""
    return b.get("z0", 0.0) + LEVEL_H * (b["level"] - 1)


def block_top(b):
    return b.get("z0", 0.0) + LEVEL_H * b["level"]


def hull_spec(design):
    h = design["hull"]
    cb = h.get("block_coefficient", 0.55)
    return dict(length=h["length"], beam=h["beam"],
                bow=dict(taper=min(0.42, max(0.25, 0.30 + (0.58 - cb) * 0.6)), power=1.6),
                stern=dict(taper=0.18, transom=min(0.6, max(0.35, 0.45 + (0.55 - cb) * 0.6))))


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def turret_name(letters, i):
    """A, B, C, then A4, A5, ... (letters[0] plus the turret's number in its group)."""
    return letters[i] if i < len(letters) else f"{letters[0]}{i + 1}"


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


def build_layout(design: dict, shp: float, depth: float, shift: float = 0.0) -> Layout:
    lay = Layout()
    hs = hull_spec(design)
    hull = Hull(hs)
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

    L_mach = machinery_length(shp)
    nfun = design.get("funnels") or funnel_count(shp)
    fw = clamp(0.6 * math.sqrt(shp / nfun / 1000.0), 2.2, 0.3 * B)
    fl = 1.45 * fw
    lb = clamp(0.05 * L + 2, 7, 18)                 # bridge length
    la = 0.045 * L + 2 if L >= 130 else 0.0         # aft control position length
    # a midships turret's slot among the funnels: barrels stowed along the centreline one way, and on the other
    # side enough room that its neighbour stays out of the beam arcs
    beam_tan = math.tan(math.radians(90.0 - ARC_BEAM))
    s_mid = max(reach + 1.0, 0.55 * fw / beam_tan + 0.5) + R_main + 1.5

    # the middle's plan, forward to aft: funnels (F), midships turrets (T) and wing turret pairs (W). Abreast
    # pairs go to the ends of the middle (Dreadnought, Nassau), echelon pairs among the funnels (Invincible)
    seq = ["F"] * nfun
    for k in range(nm):
        seq.insert(round((k + 1) * (nfun + nm) / (nm + 1) - 0.5), "T")
    n0 = len(seq)
    for k in range(nw):
        if echelon:
            seq.insert(round((k + 1) * (n0 + nw) / (nw + 1) - 0.5), "W")
        else:
            seq.insert(k // 2 if k % 2 == 0 else len(seq) - k // 2, "W")
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
        while 0 <= j < len(seq) and seq[j] == "F":
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

    M_req = max(L_mach + 2, lb + nfun * (fl + 2.0) + la + 3) + nm * s_mid + \
        sum(wing_widths(B / 2 - reach - 0.6).values())

    need_hw = reach + 0.6
    if tm and need_hw > B / 2:
        lay.errors.append(f"Main turrets are {2 * reach:.1f} m across; the {B:g} m beam cannot carry them "
                          f"(needs about {2 * need_hw:.1f} m). Widen the hull or use fewer or smaller guns.")

    def fits(x):
        if need_hw > B / 2:      # cannot fit anywhere: already reported, don't push the guns inward
            return True
        return hull.half_width(x) >= need_hw

    # preferred / minimum clearances from the hull ends to the outer edge of each group
    if nf:
        bow_pref, bow_min = 0.12 * L + 2.5 * r, 0.08 * L + 1.5 * r
    else:
        bow_pref, bow_min = 0.18 * L, 0.10 * L
    if na:
        st_pref, st_min = 0.14 * L + 2.0 * r, 0.07 * L + 1.0 * r
    else:
        st_pref, st_min = 0.15 * L, 0.08 * L

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
        sb, ss = bow_pref - bow_min, st_pref - st_min
        take = min(deficit, sb + ss)
        if sb + ss > 0:
            bow_c -= take * sb / (sb + ss)
            st_c -= take * ss / (sb + ss)
        fore, aft, mid_fwd, mid_aft = arrangement(bow_c, st_c, 0.0)
        deficit = M_req - (mid_fwd - mid_aft)
        if deficit > 0.5:
            lay.errors.append(
                f"Not enough length amidships: boilers and engines for {shp / 1000:.0f}k shp need about "
                f"{M_req:.0f} m between the turret groups, but only {mid_fwd - mid_aft:.0f} m is free. "
                f"Lengthen the hull by about {deficit:.0f} m, reduce speed, or remove a turret.")

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
                base = 1.2 + level * (th + 1.0)
                mid = turret_name(names[gname], i)
                # a flush turret stows pointing away from the stepped turret ahead of it
                mounts.append(dict(id=mid, kind="main", type=tm_id, t=tm, x=x, y=0.0, level=level,
                                   base=base, top=base + th, rest=(180 if gname == "A" else 0) if flush else rest,
                                   z=1 + level))
                if flush:
                    mounts[-1]["arc_role"] = "beam"
                lay.reserve_sweep(mounts[-1])
                lay.occupy(_fp_circle(x, 0, reach), base, base + th, mid)
                tw, bw, aw = mount_weights(tm, armour.get("turret_mm", 0), depth, level)
                lay.weights += [Weight(f"Turret {mid}", "armament", tw, x=x, z_rel=("deck", base + th / 2)),
                                Weight(f"Barbette {mid}", "armour", bw, x=x, z_rel=("frac", 0.75)),
                                Weight(f"Magazine {mid}", "armament", aw, x=x, z_rel=("frac", 0.22))]

    # ---------------- middle: bridge, deckhouse, funnels, aft control ----------------
    blocks = []

    def add_block(bid, x0, x1, w, level, rf, rb, y=0.0, kind="superstructure", layer=None):
        rf_, rb_ = rrect_clamped(x0, y - w / 2, x1, y + w / 2, rf, rb)
        b = dict(id=bid, kind=kind, x0=x0, x1=x1, y=y, w=w, level=level, rf=rf_, rb=rb_)
        if layer:
            b["layer"] = layer
        blocks.append(b)
        top = LEVEL_H * level
        lay.occupy(_fp_rect(x0, y - w / 2, x1, y + w / 2), top - LEVEL_H, top, bid)
        lay.weights.append(Weight(bid, "superstructure",
                                  (x1 - x0) * w * TUNING["superstructure_t_per_m2"], x=(x0 + x1) / 2,
                                  z_rel=("deck", LEVEL_H * (level - 0.5))))
        return b

    tower_levels = [2, 3] + ([4] if L >= 180 else [])
    bx1 = mid_fwd
    bx0 = bx1 - lb
    wide = B >= 15
    fun_top = LEVEL_H * max(tower_levels) + 3.0

    # ---------------- midships turrets: placed with the funnels' plan, before any superstructure ----------------
    fz0 = mid_aft + (la + 1.5 if la else 1.0)
    fz1 = bx0 - 1.5
    mach_c = (fz0 + fz1) / 2
    lay.geo["machinery"] = (mach_c - L_mach / 2, mach_c + L_mach / 2)
    lay.geo["machinery_x"] = mach_c
    # wing turrets stand as far outboard as the narrowest hull section of the middle allows
    y_w = min(hull.half_width(fz0 + (fz1 - fz0) * k / 20) for k in range(21)) - reach - 0.6
    wings_w = wing_widths(y_w) if nw else {}
    if nw and not echelon and y_w < reach + 0.25:
        lay.errors.append(f"Wing turrets are {2 * reach:.1f} m across: a pair cannot stand abreast on this beam "
                          f"(needs about {4 * reach + 1.7:.1f} m). Widen the hull or set \"echelon\": true.")
    elif nw and y_w <= 0.5:
        lay.errors.append(f"Hull too narrow for wing turrets even in echelon: they need about "
                          f"{2 * reach + 2.2:.1f} m of beam amidships.")
    if fz1 - fz0 < nfun * (fl + 1.0) + nm * s_mid + sum(wings_w.values()):
        what = [f"{nm} midships turret(s)"] * bool(nm) + [f"{nw} wing turret pair(s)"] * bool(nw)
        lay.errors.append(f"No room for {nfun} funnel(s){' and ' + ' and '.join(what) if what else ''} between "
                          "the bridge and the aft control position.")
    pitch = (fz1 - fz0 - nm * s_mid - sum(wings_w.values())) / nfun
    tp_ = design.get("torpedoes") or {}
    pitch_cap = fl + 4.0
    if tp_.get("mounts", 0) and not B >= 15:   # centreline torpedo mounts go between the funnels
        pitch_cap = fl + 7.6 + 2.0
    span = min(pitch, pitch_cap) * nfun
    if nm or nw:
        # midships turrets among the funnels (F T F, F T T F, ...), flush, firing to the sides. Each stows aft
        # unless another turret is aft of it; its slot holds the stowed barrels on one side and, on the other,
        # keeps the neighbour (funnel, bridge or aft control) out of its beam arcs.
        # Wing turret pairs (W) stand outboard, firing to their own side; their slot keeps the centreline
        # neighbours clear of their bodies (and of their barrels, if a neighbour is as wide as the turret stands)
        fpitch = span / nfun
        widths, stows = [], []
        for i, it in enumerate(seq):
            if it == "F":
                widths.append(fpitch)
                stows.append(None)
                continue
            if it == "W":
                widths.append(wings_w[i])
                stows.append(wing_side(i, -1, y_w))
                continue
            stow = 0 if (i + 1 < len(seq) and seq[i + 1] == "T") else 180
            j = i - 1 if stow == 180 else i + 1                  # the neighbour on the open side
            half = half_of(j, y_w)
            margin = max(reach + 1.0, half / beam_tan + 0.5)
            widths.append(margin + R_main + 1.5)
            stows.append((stow, margin))
        xx = mach_c + sum(widths) / 2
        fxs, mids, wings = [], [], []
        for it, w_, st in zip(seq, widths, stows):
            if it == "F":
                fxs.append(xx - w_ / 2)
            elif it == "W":
                # abreast: both at one x; echelon: port forward, starboard aft
                x = xx - st
                wings.append([(x, -1), (x - wing_stagger(y_w), 1)] if echelon else [(x, -1), (x, 1)])
            else:
                stow, margin = st
                mids.append((xx - margin if stow == 180 else xx - w_ + margin, stow))
            xx -= w_
        fxs.reverse()
        mid_base = (LEVEL_H if wide else 0.0) + 1.2

        def main_mount(mid, x, y, rest, **kw):
            mounts.append(dict(id=mid, kind="main", type=tm_id, t=tm, x=x, y=y, level=0, base=mid_base,
                               top=mid_base + th, rest=rest, z=1, **kw))
            lay.occupy(_fp_circle(x, y, reach), mid_base, mid_base + th, mid)
            lay.reserve_sweep(mounts[-1])
            tw, bw, aw = mount_weights(tm, armour.get("turret_mm", 0), depth, 0)
            lay.weights += [Weight(f"Turret {mid}", "armament", tw, x=x, z_rel=("deck", mid_base + th / 2)),
                            Weight(f"Barbette {mid}", "armour", bw, x=x, z_rel=("frac", 0.75)),
                            Weight(f"Magazine {mid}", "armament", aw, x=x, z_rel=("frac", 0.22))]

        for k, (x, stow) in enumerate(mids):
            main_mount(turret_name("QPRS", k), x, 0.0, stow, arc_role="beam", midships=True)
        # wing turrets fire bow to stern on their own side, and stow fore-and-aft (the edge of that arc) toward
        # the nearer end: an echelon pair's forward turret forward and its aft one aft
        for k, pair in enumerate(wings):
            for x, side in pair:
                fwd = (x == pair[0][0]) if echelon else x >= mach_c
                main_mount(f"W{k + 1}{'S' if side > 0 else 'P'}", x, side * y_w, 0 if fwd else 180, wing=True)
    else:
        start = mach_c - span / 2
        fxs = [start + (i + 0.5) * span / nfun for i in range(nfun)]

    # ---------------- superstructure, kept out of the guns' sweeps ----------------
    blocks = []

    def add_block(bid, x0, x1, w, level, rf, rb, y=0.0, kind="superstructure", layer=None):
        rf_, rb_ = rrect_clamped(x0, y - w / 2, x1, y + w / 2, rf, rb)
        b = dict(id=bid, kind=kind, x0=x0, x1=x1, y=y, w=w, level=level, rf=rf_, rb=rb_)
        if layer:
            b["layer"] = layer
        blocks.append(b)
        top = LEVEL_H * level
        lay.occupy(_fp_rect(x0, y - w / 2, x1, y + w / 2), top - LEVEL_H, top, bid)
        lay.weights.append(Weight(bid, "superstructure",
                                  (x1 - x0) * w * TUNING["superstructure_t_per_m2"], x=(x0 + x1) / 2,
                                  z_rel=("deck", LEVEL_H * (level - 0.5))))
        return b

    # the bridge tower steps aft, and the aft control forward, until no turret's barrels can reach them
    tower_top = LEVEL_H * max(tower_levels)
    while not lay.clear(_fp_rect(bx0, -w2 / 2, bx1, w2 / 2), tower_top) and bx0 > mid_aft:
        bx1 -= 0.5
        bx0 -= 0.5
    ax0 = mid_aft
    while la and not lay.clear(_fp_rect(ax0, -0.14 * B, ax0 + la, 0.14 * B), LEVEL_H * 3) and ax0 + la < bx0:
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
    # bridge tower
    add_block("Bridge", bx0, bx1, w2, 2, 0.42 * w2, 1.0)
    add_block("Bridge upper", bx0 + 0.1 * lb, bx1 - 0.06 * lb, 0.78 * w2, 3, 0.36 * w2, 1.0)
    if 4 in tower_levels:
        add_block("Main director", bx0 + 0.35 * lb, bx1 - 0.2 * lb, 0.5 * w2, 4, 0.25 * w2, 0.25 * w2)
    # aft control
    if la:
        add_block("Aft control", ax0, ax0 + la, 0.28 * B, 2, 1.0, 0.1 * B)
        add_block("Aft director", ax0 + 0.25 * la, ax0 + 0.75 * la, 0.17 * B, 3, 0.085 * B, 0.085 * B)

    funnels = []
    for i, fx in enumerate(fxs):
        fid = f"Funnel {i + 1}"
        fp = _fp_rect(fx - fl / 2, -fw / 2, fx + fl / 2, fw / 2)
        if not lay.clear(fp, fun_top) or not lay.free(fp, 0.0):
            lay.errors.append(f"{fid} would stand in a turret's sweep or against the bridge: lengthen the hull or "
                              "use fewer funnels or midships turrets.")
        funnels.append(dict(id=fid, x=fx, y=0.0, l=fl, w=fw, pipes=2 if fw > 4 else 1))
        lay.occupy(fp, 0, fun_top, fid)
        lay.weights.append(Weight(fid, "superstructure", fl * fw * 0.9, x=fx, z_rel=("deck", fun_top / 2)))

    # ---------------- secondaries ----------------
    sec = design.get("secondary") or {}
    nsec = sec.get("per_side", 0)
    dh_w = 0.62 * B
    sec_base = LEVEL_H if wide else 0.0
    if nsec:
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
        xs_probe = [x_lo + (x_hi - x_lo) * k / 20 for k in range(21)]
        outer = min(hull.half_width(x) for x in xs_probe) - rs_reach - 0.6
        if outer < inner:
            lay.errors.append(f"Hull too narrow for {sec['calibre_mm']:g} mm secondary mounts: they need about "
                              f"{2 * (inner + rs_reach + 0.6):.1f} m of beam amidships.")
        y_s = max(inner, inner + 0.55 * (outer - inner))
        pitch_s = 2.1 * rs_reach + 1.0
        if x_hi <= x_lo:
            lay.errors.append("No room amidships for the secondary battery.")
        elif nsec > 1 and (x_hi - x_lo) / (nsec - 1) < pitch_s:
            lay.errors.append(f"{nsec} secondary mounts per side do not fit in {x_hi - x_lo:.0f} m amidships "
                              f"(max {int((x_hi - x_lo) / pitch_s) + 1}).")
        step = min((x_hi - x_lo) / max(nsec - 1, 1), 2.2 * rs + 4.0)
        c = (x_lo + x_hi) / 2
        sxs = [c + (i - (nsec - 1) / 2) * step if nsec > 1 else c for i in range(nsec)]
        if nw:
            # wing turrets break up the middle: take the free spots nearest amidships, at the preferred pitch if
            # they fit, else the minimum
            def spot_ok(x):
                fps = [_fp_circle(x, s * y_s, rs_reach) for s in (1, -1)]
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
                lay.errors.append(f"Only {len(sxs)} of {nsec} secondary mounts per side fit beside the wing turrets.")
            sxs.sort()
        for i, sx in enumerate(sxs):
            if not lay.clear(_fp_circle(sx, y_s, rs_reach), sec_base + ths):
                lay.errors.append(f"Secondary mounts S{i + 1} would stand in a main turret's sweep: lengthen the "
                                  "hull or use fewer secondaries.")
            for side in (1, -1):
                mid = f"S{i + 1}{'S' if side > 0 else 'P'}"
                mounts.append(dict(id=mid, kind="secondary", type=ts_id, t=ts, x=sx, y=side * y_s, level=0,
                                   base=sec_base, top=sec_base + ths,
                                   rest=90 * side, z=3))
                lay.occupy(_fp_circle(sx, side * y_s, rs_reach), sec_base, sec_base + ths, mid)
                tw, _, aw = mount_weights(ts, sec.get("armour_mm", 25), depth, 0)
                lay.weights += [Weight(f"Mount {mid}", "armament", tw, x=sx, z_rel=("deck", sec_base + ths / 2)),
                                Weight(f"Magazine {mid}", "armament", aw, x=sx, z_rel=("frac", 0.3))]
        if wide:
            dh_w = 2 * (y_s + rs_reach + 0.6)
    if wide:
        if nw:   # wing turrets stand on the deckhouse
            dh_w = max(dh_w, 2 * (y_w + reach + 0.6))
        hw_min = min(hull.half_width(dh["x0"]), hull.half_width(dh["x1"]))
        dh_w = min(dh_w, 2 * (hw_min - 0.6))
    deckhouse = add_block("Deckhouse", dh["x0"], dh["x1"], dh_w, 1, 0.12 * dh_w if wide else 2.0, 0.1 * dh_w if wide else 1.0)
    blocks.insert(0, blocks.pop())  # draw the deckhouse first, under the bridge
    # the deckhouse is under everything else in the middle; secondaries stand on it
    lay.footprints = [fp for fp in lay.footprints if fp[3] != "Deckhouse"] + \
                     [(_fp_rect(dh["x0"], -dh_w / 2, dh["x1"], dh_w / 2), 0, LEVEL_H, "Deckhouse")]

    # ---------------- torpedo mounts ----------------
    tp = design.get("torpedoes") or {}
    ntp = tp.get("mounts", 0)
    if ntp:
        tt_id, tt = make_torpedo_type(tp.get("tubes", 4))
        turret_types[tt_id] = tt
        sweep = tt["barrel_len"] / 2 + 0.3
        placed = 0
        if not wide:
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
        else:
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
        if placed < ntp:
            lay.errors.append(f"Only {placed} of {ntp} torpedo mounts fit on deck.")

    # ---------------- AA ----------------
    aa_out = []
    aa_req = design.get("aa", {})

    def place_aa(kind, count):
        rr = AA_CFG[kind][0]
        spacing = 3.0 if kind == "quad40" else 2.2   # extra gap between AA mounts so they spread out
        placed = 0
        cands = []
        if wide and kind == "quad40":  # heavy AA: on the deckhouse roof, along its edges
            yy = dh_w / 2 - rr - 0.3
            for k in range(int((dh["x1"] - dh["x0"]) * 2)):
                cands.append((dh["x0"] + 0.5 * k, yy, LEVEL_H))
        x = L / 2 - 0.06 * L
        while x > -L / 2 + 2:
            yy = hull.half_width(x) - rr - 0.5
            if yy > rr + 0.5:
                cands.append((x, yy, 0.0))
            x -= 0.5
        cands.sort(key=lambda c: (abs(c[0] - mach_c) / L + (0.0 if c[2] else 0.15)))
        for cx, cy, base in cands:
            if placed >= count:
                break
            fps = [_fp_circle(cx, cy, rr), _fp_circle(cx, -cy, rr)]
            pair = count - placed >= 2
            use = fps if pair else [fps[0]]
            # a single leftover AA mount goes on the centreline at the stern
            if not pair:
                sx = -L / 2 + rr + 2.5
                if hull.half_width(sx) > rr + 0.6 and lay.free(_fp_circle(sx, 0, rr), 0.4):
                    use, cx, cy, base = [_fp_circle(sx, 0, rr)], sx, 0.0, 0.0
            if not all(lay.free(fp, 0.4, ignore=("Deckhouse",) if base else ()) and lay.clear(fp, base + 2.0)
                       for fp in use):
                continue
            aa_ids = {a["id"] for a in aa_out}
            if not all(not _overlap(fp, o[0], spacing) for fp in use for o in lay.footprints if o[3] in aa_ids):
                continue
            for k, fp in enumerate(use):
                y = fp[2]
                aid = f"AA{len(aa_out) + 1}"
                d = 180 if (y == 0 and cx < 0) else (90 if y > 0 else -90 if y < 0 else 0)
                aa_out.append(dict(id=aid, type=kind, x=fp[1], y=y, dir=d, base=base,
                                   layer="base"))
                lay.occupy(fp, base, base + 2.0, aid)
                lay.weights.append(Weight(aid, "armament", TUNING["aa_t"][kind], x=fp[1],
                                          z_rel=("deck", base + 1.0)))
                placed += 1
        if placed < count:
            lay.errors.append(f"Only {placed} of {count} {'heavy' if kind == 'quad40' else 'light'} AA mounts fit.")

    place_aa("quad40", aa_req.get("heavy", 0))
    place_aa("single20", aa_req.get("light", 0))

    # ---------------- masts and boats (decorative but drawn) ----------------
    mast_top = fun_top + 6.0
    fx_ = bx0 - 1.2 if lay.clear(_fp_circle(bx0 - 1.2, 0, 0.7), mast_top) else bx0 + 0.3 * lb   # else on the bridge
    masts = [dict(x=fx_, yard=min(0.3 * B, 10), tripod=L >= 150)]
    if la:
        masts.append(dict(x=ax0 + la * 0.5, yard=min(0.22 * B, 8), tripod=False))
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
    main_x = [m["x"] for m in mounts if m["kind"] == "main"]
    if main_x:
        cit = (min(main_x) - r - 2.0, max(main_x) + r + 2.0)
    else:
        cit = lay.geo["machinery"]
    lay.geo["citadel"] = cit
    inner_hw = 0.8 * B / 2
    lay.compartments.append(dict(id="Citadel", kind="citadel", x0=cit[0], x1=cit[1], half_width=inner_hw,
                                 belt_mm=armour.get("belt_mm", 0), deck_mm=armour.get("deck_mm", 0)))
    mid_xs = [m["x"] for m in mounts if m.get("midships")]
    wing_xs = [m["x"] for m in mounts if m.get("wing")]
    for gname, xs in (("Forward magazines", fore), ("Midships magazines", mid_xs), ("Wing magazines", wing_xs),
                      ("Aft magazines", aft)):
        if xs:
            lay.compartments.append(dict(id=gname, kind="magazine", x0=min(xs) - r, x1=max(xs) + r,
                                         half_width=inner_hw))
    m0, m1 = lay.geo["machinery"]
    lay.compartments.append(dict(id="Machinery", kind="machinery", x0=m0, x1=m1, half_width=inner_hw))
    lay.compartments.append(dict(id="Steering gear", kind="steering", x0=-L / 2 + 0.03 * L, x1=-L / 2 + 0.08 * L,
                                 half_width=0.5 * B / 2))

    # ---------------- renderer spec ----------------
    front_edge = (fore[0] + r) if fore else mid_fwd
    spec = dict(
        id=design["id"], name=design.get("name", design["id"]), **{"class": design.get("type", "")},
        length=L, beam=B, bow=hs["bow"], stern=hs["stern"], deck=deck,
        turret_types=turret_types,
        turrets=[dict(id=m["id"], type=m["type"], x=m["x"], y=m["y"], z=m["z"], rest=m["rest"]) for m in mounts],
        superstructure=[{k: v for k, v in b.items() if k not in ("id", "kind")} for b in blocks],
        funnels=[{k: v for k, v in f_.items() if k != "id"} for f_ in funnels],
        masts=masts,
        aa=[{k: v for k, v in a.items() if k not in ("id", "base")} for a in aa_out],
        boats=boats,
        bollards=[L / 2 - 0.05 * L, -L / 2 + 0.06 * L],
    )
    if L / 2 - front_edge > 0.08 * L + 6:
        spec["chain_x"] = front_edge + 0.35 * (L / 2 - front_edge)
        spec["hawse_back"] = 0.03 * L + 1.0
    if L >= 150 and fore and (L / 2 - front_edge) > 12:
        spec["breakwater_x"] = front_edge + 3.0
    lay.spec = spec
    lay.mounts = mounts
    lay.blocks = blocks
    lay.funnels = funnels
    lay.aa = aa_out
    lay.hull = hull
    lay.fun_top = fun_top
    return lay
