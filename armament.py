"""
armament: style-neutral placement of guns, torpedo mounts and AA.

The warship layout (layout.py) places its batteries with its own rules, then books each mount with add_mount like
every style. Other styles describe where guns may go (a line of positions, or candidate slots along the sides) and
these helpers do the rest: footprint
collision checks, superfiring levels, weights, and the mount records that hitboxes, arcs and the renderer
read. Any style can therefore carry any armament (a Q-ship, a carrier with cruiser guns).
"""
from __future__ import annotations

import math

from geometry import make_torpedo_type, make_turret_type, rotate_translate, superfire_step, turret_height, turret_reach
from geometry import turret_shapes
from layout import _fp_circle, _fp_rect, _overlap, stepped_counts, turret_name
from navarch import TUNING, Weight, mount_weights, torpedo_weight
from geometry import AA_CFG


def body_reach(t):
    """Radius of the turret body and its ears (not the barrels): its footprint on deck."""
    return max(t["r"], turret_reach({**t, "barrel_len": 0}))


def stow_bearing(x, side, half):
    """Rest bearing of a side mount at x (m forward of amidships) on `side` (+1 starboard), whose arc is +-half about
    its own beam: trained toward the nearer end of the ship (amidships counts as forward), stopping at the edge of
    its arc. Deck secondaries (+-90) so lie fore-and-aft, like Iowa's 5in or Bismarck's 15 cm turrets in harbour;
    casemates (+-60) lie along the hull side, 30 degrees off the centreline. The arc doesn't move."""
    return 90.0 * side + (-1.0 if x >= 0 else 1.0) * side * half


def barrel_footprint(t, x, y, bearing):
    """Axis-aligned box around a mount's barrels (as shown) trained to `bearing`."""
    pts = [p for poly in turret_shapes(t)["barrels"] for p in rotate_translate(poly, bearing, x, y)]
    return _fp_rect(min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def barrel_band(base, top, t):
    """The heights (lo, hi) above the main deck that a mount's barrels take, about their axis."""
    axis = base + 0.55 * (top - base)
    hw = t["barrel_w"] / 2 + 0.1
    return axis - hw, axis + hw


def gun_type(gun):
    return make_turret_type(gun["calibre_mm"], gun["calibre_length"], gun["barrels"])


def tube_footprint(t, x, y, bearing):
    """Axis-aligned box around a fixed tube laid along `bearing` (a few degrees off the centreline)."""
    a = math.radians(bearing)
    hl, hw = t["barrel_len"] / 2 + 0.2, ((t["barrels"] - 1) * t["spacing"] + t["barrel_w"]) / 2 + 0.2
    ex, ey = abs(hl * math.cos(a)) + abs(hw * math.sin(a)), abs(hl * math.sin(a)) + abs(hw * math.cos(a))
    return _fp_rect(x - ex, y - ey, x + ex, y + ey)


def add_mount(lay, mounts, kind, t_id, t, mid, x, y, base, rest, level=0, armour_mm=0, depth=10.0, top=None,
              footprint_r=None, label="Mount", deck=0.0, **extra):
    """One mount: footprint, weights and the mount record, for every style. A fixed tube (t["fixed_tube"]) keeps
    `rest` as its fixed bearing. top defaults to base + the turret's height; footprint_r to its body and ears.
    The weights: the mount ("<label> <id>"), its barbette if it stands above the deck, and its ammunition
    ("Magazine <id>", which ordnance.stow moves into its magazine). deck: the weather deck under it (m above the main
    deck; navarch.mount_weights). extra goes into the mount record."""
    th = turret_height(t) if kind != "torpedo" or t.get("fixed_tube") else 1.1
    top = base + th if top is None else top
    mounts.append(dict(id=mid, kind=kind, type=t_id, t=t, x=x, y=y, level=level, base=base, top=top,
                       rest=rest, armour_mm=armour_mm, **extra))
    if t.get("fixed_tube"):
        mounts[-1]["fixed"] = rest
        lay.occupy(tube_footprint(t, x, y, rest), base, top, mid)
    else:
        r = footprint_r if footprint_r is not None else (body_reach(t) if kind != "torpedo"
                                                          else t["barrel_len"] / 2 + 0.3)
        lay.occupy(_fp_circle(x, y, r), base, top, mid)
        if extra.get("side_mount"):     # stowed fore-and-aft: the barrels lie along the deck (stow_bearing)
            lay.occupy(barrel_footprint(t, x, y, rest), *barrel_band(base, top, t), mid)
    if kind == "torpedo":
        lay.weights.append(Weight(mid, "armament", torpedo_weight(t["barrels"], t.get("fixed_tube", False)), x=x,
                                  z_rel=("deck", base + 0.5)))
        return mounts[-1]
    tw, bw, aw = mount_weights(t, armour_mm, depth, level, deck)
    lay.weights += [Weight(f"{label} {mid}", "armament", tw, x=x, z_rel=("deck", (base + top) / 2)),
                    Weight(f"Magazine {mid}", "armament", aw, x=x, z_rel=("frac", 0.25))]
    if bw and base > 0.5:
        lay.weights.append(Weight(f"Barbette {mid}", "armour", bw, x=x, z_rel=("frac", 0.75)))
    return mounts[-1]


def gun_line(lay, mounts, turret_types, gun, kind, names, x_start, step_dir, y, rest, deck_h,
             raise_inner=False, armour_mm=0.0, depth=10.0, label="Main", ignore=()):
    """n mounts in a line from x_start (the edge of the first mount) in direction step_dir (+1 forward,
    -1 aft). deck_h(x) gives the deck height under a mount. Each further mount superfires over the one
    before it; with raise_inner the first one is the highest instead (guns stepping down away from an island)."""
    n = gun["count"]
    if not n:
        return
    t_id, t = gun_type(gun)
    turret_types[t_id] = t
    r, th = t["r"], turret_height(t)
    reach = body_reach(t)
    s = 2.2 * r + 3.0
    k = max(gun.get("stepped", n), 1)
    flat = gun.get("flat", False)   # guns fitted where they suit: all on deck, each with its own end arc
    for i in range(n):
        x = x_start + step_dir * (reach + i * s)
        flush = i >= k and not flat     # behind the stepped turrets: flush on deck, firing to the sides
        level = 0 if (flush or flat) else ((k - 1 - i) if raise_inner else i)
        base = deck_h(x) + level * superfire_step(th)
        mid = turret_name(names, i)
        if not lay.free(_fp_circle(x, y, reach), 0.4, ignore):
            lay.fail("length", f"{label} mount {mid} ({gun['calibre_mm']:g} mm) does not fit at {x:.0f} m: "
                               "the deck is taken there. Use fewer or smaller guns.")
            continue
        if abs(y) + reach > lay.hull.half_width(x) + 0.2 and not lay.on_deck(x, y):
            lay.fail("beam", f"{label} mount {mid} ({gun['calibre_mm']:g} mm) is too wide for the hull at {x:.0f} m.")
            continue
        stow = (rest + 180) % 360     # flush: stowed pointing away from the stepped turret ahead of it
        add_mount(lay, mounts, kind, t_id, t, mid, x, y, base, stow if flush else rest, level=level,
                  armour_mm=armour_mm, depth=depth)
        if flush:
            mounts[-1]["arc_role"] = "beam"


def side_pairs(lay, mounts, turret_types, kind, t_id, t, per_side, cands, prefix, pitch=None,
               armour_mm=25.0, depth=10.0, label="Secondary", ignore=()):
    """per_side mounts on each side. cands: (x, y, base) for the starboard side (y > 0), in order of
    preference, mirrored to -y; or (x, y, base, y_port) when the sides differ (an angled flight deck).
    A candidate is used when both sides are free and it keeps pitch from the others already placed. Guns stow
    fore-and-aft (stow_bearing), so their barrels must be free too, and a mount keeps its barrels' length from the
    next one in the direction they point; torpedo mounts stow on the beam."""
    if not per_side:
        return 0
    turret_types[t_id] = t
    reach = body_reach(t) if kind != "torpedo" else t["barrel_len"] / 2 + 0.3
    pitch = pitch or 2.1 * reach + 1.0
    guns = kind != "torpedo"
    pitch_stowed = turret_reach(t) + reach + 0.4      # barrels lying toward the next mount
    placed = []
    for c in cands:
        x, y, base = c[:3]
        y_port = c[3] if len(c) > 3 else -y
        if len(placed) >= per_side:
            break
        if any(abs(x - px) < pitch or (guns and (x >= 0) == (px >= 0) and abs(x - px) < pitch_stowed)
               for px in placed):
            continue
        fps = [_fp_circle(x, y, reach), _fp_circle(x, y_port, reach)]
        if _overlap(fps[0], fps[1], 0.4) or not all(lay.free(fp, 0.4, ignore) for fp in fps):
            continue
        if guns:
            band = barrel_band(base, base + turret_height(t), t)
            if not all(lay.free_at(barrel_footprint(t, x, yy, stow_bearing(x, side, 90.0)), *band, 0.2, ignore)
                       for side, yy in ((1, y), (-1, y_port))):
                continue
        k = len(placed) + 1
        for side, yy in ((1, y), (-1, y_port)):
            mid = f"{prefix}{k}{'S' if side > 0 else 'P'}"
            if guns:
                add_mount(lay, mounts, kind, t_id, t, mid, x, yy, base, stow_bearing(x, side, 90.0),
                          armour_mm=armour_mm, depth=depth, side_mount=True)
            else:
                add_mount(lay, mounts, kind, t_id, t, mid, x, yy, base, 90 * side, armour_mm=armour_mm, depth=depth)
        placed.append(x)
    if len(placed) < per_side:
        lay.fail("length", f"Only {len(placed)} of {per_side} {label.lower()} mounts per side fit.")
    return len(placed)


def batteries(design):
    """The secondary armament as a list of batteries (styles whose guns are fitted where they suit: carriers,
    merchants). "secondary" is one battery or a list; each has "count" (total mounts) or "per_side", and
    "where": "sides" (pairs along the sides, the default; an odd mount goes to an end) or "ends" (on the
    centreline / island line, fore and aft alternately)."""
    sec = design.get("secondary") or []
    out = []
    for b in (sec if isinstance(sec, list) else [sec]):
        n = b.get("count", 2 * b.get("per_side", 0))
        if n:
            out.append({**b, "count": n, "where": b.get("where", "sides")})
    return out


def place_batteries(lay, mounts, turret_types, design, end_lines, side_slots, depth=10.0, armour_mm=0):
    """Fit every secondary battery. end_lines: (x_start, step_dir, y, rest, deck_h, ignore) per end, in the
    order they fill; side_slots(t) -> starboard candidates for side_pairs. All mounts are kind "secondary",
    flat on deck (no superfiring). armour_mm: the mounts' armour unless a battery gives its own."""
    cursor = [ln[0] for ln in end_lines]
    for k, b in enumerate(batteries(design)):
        first = len(mounts)
        prefix = "S" if k == 0 else "S" + "BCDEFG"[k - 1]
        t_id, t = gun_type(b)
        turret_types[t_id] = t
        n_end = b["count"] if b["where"] == "ends" else b["count"] % 2
        n_side = 0 if b["where"] == "ends" else b["count"] // 2
        if n_end and not end_lines:
            lay.fail(None, f"No end positions for {n_end} {b['calibre_mm']:g} mm mount(s): give them in pairs.")
            n_end = 0
        made = 0
        for i, (_, d, y, rest, deck_h, ign) in enumerate(end_lines):
            n = n_end // len(end_lines) + (i < n_end % len(end_lines))
            if not n:
                continue
            gun_line(lay, mounts, turret_types, {**b, "count": n, "flat": True}, "secondary",
                     [f"{prefix}{made + j + 1}" for j in range(n)], cursor[i], d, y, rest, deck_h,
                     armour_mm=b.get("armour_mm", armour_mm), depth=depth, label="Secondary", ignore=ign)
            cursor[i] += d * (2 * body_reach(t) + (n - 1) * (2.2 * t["r"] + 3.0) + 1.0)
            made += n
        if n_side:
            side_pairs(lay, mounts, turret_types, "secondary", t_id, t, n_side, side_slots(t), prefix,
                       armour_mm=b.get("armour_mm", armour_mm), depth=depth)
        for m in mounts[first:]:
            m["material"] = b.get("material")      # the battery's own armour material, if it names one


def torpedo_type(tp, fixed=False):
    return make_torpedo_type(tp.get("tubes", 4), fixed)


def fixed_tube_pairs(lay, mounts, turret_types, tp, xs, y_of_x, base=0.2, toe_deg=8.0):
    """Fixed torpedo tubes in port/starboard pairs, toed out by toe_deg from dead ahead. xs: candidate tube
    centres in order of preference; y_of_x(x, t): the starboard tube centre y there."""
    t_id, t = torpedo_type(tp, fixed=True)
    turret_types[t_id] = t
    want = (tp["mounts"] + 1) // 2
    placed = 0
    for x in xs:
        if placed >= want:
            break
        y = y_of_x(x, t)
        fps = [tube_footprint(t, x, y, toe_deg), tube_footprint(t, x, -y, -toe_deg)]
        if y <= 0 or not all(lay.free(fp, 0.2) for fp in fps):
            continue
        placed += 1
        for side in (1, -1):
            add_mount(lay, mounts, "torpedo", t_id, t, f"T{placed}{'S' if side > 0 else 'P'}", x, side * y, base,
                      side * toe_deg)
    if placed < want:
        lay.fail("length", f"Only {placed} of {want} pairs of torpedo tubes fit along the sides.")
    return placed


AA_TUB_T = {"quad40": 3.0, "twin40": 1.5, "single20": 0.3}   # a raised mount's tub and splinter shield (E)


def place_aa(lay, aa_out, kind, count, cands, spacing=None, ignore=(), layer_of=None):
    """AA mounts in pairs from cands (x, y, base[, y_port]) with y >= 0, in order of preference, mirrored to
    -y unless y_port is given; y == 0, or y_port None, means a single mount at y (on the centreline, or on an
    off-centre island). Single slots are taken two at a time while the count left is even, so they never leave an
    odd mount that only a pair slot could take; a lone single slot fills an odd count (offer one last to keep it for
    the leftover). A slot must be free of what's placed at its height (ignore: ids to disregard, or a function of the
    slot's base giving them) and clear of the guns' sweeps. A mount above the main deck stands in a tub (AA_TUB_T, weighed with it). layer_of(base):
    the sprite layer ("base" by default)."""
    rr = AA_CFG[kind][0]
    spacing = spacing if spacing is not None else (3.0 if kind == "quad40" else 2.2)
    aa_fps = [_fp_circle(a["x"], a["y"], AA_CFG[a["type"]][0]) for a in aa_out]   # spaced from each other

    def single(c):
        return c[1] == 0 or (len(c) > 3 and c[3] is None)

    def fits(c, also=()):
        """The slot's mounts [(footprint, base, foot)] if it is free (and clear of the footprints also), else None."""
        cx, cy, base = c[:3]
        use = [(cx, cy)] if single(c) else [(cx, cy), (cx, c[3] if len(c) > 3 else -cy)]
        fps = [_fp_circle(x, y, rr) for x, y in use]
        if len(fps) == 2 and _overlap(fps[0], fps[1], spacing):   # a slot too near the centreline to mirror
            return None
        if any(abs(fp[1] - o[1]) < fp[3] + o[3] + spacing and _overlap(fp, o, spacing)   # x distance first
               for fp in fps for o in list(aa_fps) + list(also)):
            return None
        ign = ignore(base) if callable(ignore) else ignore
        if not all(lay.free_at(fp, base, base + 2.0, 0.4, ign) for fp in fps) or \
                not all(lay.clear(fp, base + 2.0) for fp in fps):
            return None
        return [(fp, base, cx) for fp in fps]

    def put(mounts):
        for fp, base, cx in mounts:
            aa_fps.append(fp)
            y = fp[2]
            aid = f"AA{len(aa_out) + 1}"
            d = 180 if (y == 0 and cx < 0) else (90 if y > 0 else -90 if y < 0 else 0)
            aa_out.append(dict(id=aid, type=kind, x=fp[1], y=y, dir=d, base=base,
                               layer=layer_of(base) if layer_of else "base"))
            lay.occupy(fp, base, base + 2.0, aid)
            lay.weights.append(Weight(aid, "armament", TUNING["aa_t"][kind] + (AA_TUB_T[kind] if base > 0.5 else 0.0),
                                      x=fp[1], z_rel=("deck", base + 1.0)))

    placed = 0
    lonely = False      # a search for a partner single found none, and nothing has been placed since
    for i, c in enumerate(cands):
        left = count - placed
        if left <= 0:
            break
        if not single(c) and left < 2:
            continue
        if single(c) and left % 2 == 0 and lonely:
            continue
        got = fits(c)
        if not got:
            continue
        if single(c) and left % 2 == 0:     # a single while the count is even: only with a partner single
            mate = next((m for m in (fits(c2, [g[0] for g in got]) for c2 in cands[i + 1:] if single(c2)) if m), None)
            if not mate:
                lonely = True
                continue
            got += mate
        put(got)
        lonely = False
        placed += len(got)
    if placed < count:
        lay.fail("length", f"Only {placed} of {count} {'heavy' if kind == 'quad40' else 'light'} AA mounts fit.")
    return placed


def gun_groups(design):
    """The main battery as two lines: (fore spec, aft spec), each with 'count' and 'stepped' (how many
    superfire; see layout.stepped_counts)."""
    main = design.get("main") or {}
    if not (main.get("fore", 0) + main.get("aft", 0)):
        return None, None
    sf, sa = stepped_counts(main)
    return {**main, "count": main.get("fore", 0), "stepped": sf}, {**main, "count": main.get("aft", 0), "stepped": sa}
