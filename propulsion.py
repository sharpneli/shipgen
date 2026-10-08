"""
propulsion — the propulsion train for the hitboxes: shafts, shaft alleys, propellers and rudders.

Design side, standard library only. Built once per ship from the finished layout (shipdesign.interior), like the
subdivision; the size search never runs it, and nothing here is weighed (the plant's weight includes its shafting,
and the hull's its rudders and stern gear). It gives the game the weak spots aft: a jammed rudder, a wrecked shaft
or propeller, a flooded shaft alley.

  shafts      machinery shafts (powerplant.rated): spread across the stern at SHAFT_Y x B x k / pairs each side (a
              centreline shaft when the count is odd). The outer pairs come from the forward engine rooms and the
              inner ones (and the centre shaft) from the aft ones. A shaft runs from its engine room's middle, just
              over the inner bottom, down to its propeller as one straight segment.
  propellers  just ahead of the rudders; each pair further out stands STAGGER x L further forward. The diameter
              grows with the power per shaft (DP_K x MW ** 0.4: Iowa's 5.2 m, a destroyer's 4 m before the
              draught cap) and is capped at DP_T x the draught, so the tips stay under water. Planing craft hang
              theirs under the hull bottom, smaller (fast-turning).
  rudders     machinery.rudders: one on the centreline, or spread behind the innermost propellers. The stock is
              under the steering gear (layout.add_steering), the blade balanced about it (RUDDER_BALANCE of the
              chord ahead of it), RUDDER_K x L x T of blade area in all.
  alleys      watertight tunnels round each shaft from the machinery's aft end to where the shaft leaves the hull
              (geometry.HullForm): a wing shaft leaves early, where the stern narrows, and runs on in the open on
              its brackets; a centreline shaft leaves at the stern tube by its propeller. None when the shaft leaves
              inside the machinery.
"""
from __future__ import annotations

import math

STEERING = (0.03, 0.08, 0.25)   # the steering gear: from 0.03 to 0.08 L forward of the stern, 0.25 B each side
SHAFT_Y = 0.28          # the outermost shafts, x B off the centreline
STAGGER = 0.05          # each pair of propellers further out, x L further forward
DP_K = 1.2              # propeller diameter (m) per MW per shaft ** 0.4
DP_K_PLANING = 0.7
DP_T = 0.75             # the largest propeller, x the draught
DP_MIN = 0.3
RUDDER_K = 0.017        # total rudder area, x L x T
RUDDER_H = 0.7          # a rudder's height, x the draught
RUDDER_BALANCE = 0.25   # the share of the chord ahead of the stock
RUDDER_THICK = 0.15     # a rudder's thickness, x its chord
STOCK_AT = 0.2          # the stock, this far along the steering gear from its aft end
ALLEY_W, ALLEY_H = 2.4, 2.6
SHAFT_ABOVE_IB = 1.2    # a shaft's centre over the inner bottom at its engine
SHAFT_R = 0.3           # shaft radius (the hitbox), m


def steering_span(L, geo=None):
    """The steering gear's stretch (x0, x1): the layout's (geo["steering"], layout.add_steering) or the rule's
    (STEERING)."""
    return (geo or {}).get("steering") or (-L / 2 + STEERING[0] * L, -L / 2 + STEERING[1] * L)


def spread(n, y_out):
    """n positions across: a centreline one when n is odd, pairs out to y_out. [(y, rank)], rank 0 innermost."""
    pairs = n // 2
    out = [(0.0, 0)] if n % 2 else []
    for k in range(1, pairs + 1):
        y = y_out * k / pairs
        out += [(y, k), (-y, k)]
    return sorted(out, key=lambda v: -v[0])      # starboard to port


def _engine_rooms(lay):
    rooms = [(c["x0"], c["x1"], c["id"]) for c in lay.compartments if c["kind"] == "engine_room"]
    if not rooms and lay.geo.get("machinery"):
        x0, x1 = lay.geo["machinery"]
        rooms = [(x0, x1, None)]
    return sorted(rooms, key=lambda r: -r[1])     # forward first


def gear(lay, design, res):
    """The stern gear, which the hull's lines must make room for (geometry.HullForm): dict(screws, planing,
    propellers, rudders, shafts), heights above the keel. The shafts have no exit yet (build)."""
    L, B = lay.hull.L, lay.hull.B
    D, T = res.depth, res.draught
    rated = res.plant_rated or {}
    n = max(1, int(rated.get("shafts", 1)))
    n_r = max(1, int(((design.get("machinery") or {}).get("rudders", 1))))
    planing = design.get("style") == "planing"
    ib = 0.0 if planing else __import__("powerplant").double_bottom(D)
    mw = res.power_shp * 0.7457 / 1000.0 / n
    dp = max(DP_MIN, (DP_K_PLANING if planing else DP_K) * mw ** 0.4)
    if not planing:
        dp = min(dp, DP_T * T)
    st0, st1 = lay.geo.get("steering") or (-L / 2 + 0.03 * L, -L / 2 + 0.08 * L)
    x_r = st0 + STOCK_AT * (st1 - st0)

    # rudders, behind the innermost propellers
    area = RUDDER_K * L * T / n_r
    h_r = RUDDER_H * T
    chord = area / h_r
    shaft_ys = spread(n, SHAFT_Y * B)
    inner = min((abs(y) for y, _ in shaft_ys if abs(y) > 1e-6), default=0.1 * B)
    r_ys = [y for y, _ in spread(n_r, inner)]
    r_top = (0.15 if planing else 0.85) * T
    rudders = []
    for k, y in enumerate(r_ys):
        rid = "Rudder" if n_r == 1 else f"Rudder {k + 1}"
        rudders.append(dict(id=rid, x=x_r, y=y, chord=chord, x0=x_r - (1 - RUDDER_BALANCE) * chord,
                            x1=x_r + RUDDER_BALANCE * chord, thick=max(0.1, RUDDER_THICK * chord),
                            base=r_top - h_r - (0.3 * T if planing else 0.0), top=r_top, area_m2=area))

    # propellers, ahead of the rudders; pairs further out, further forward
    x_p0 = x_r + RUDDER_BALANCE * chord + 0.25 * dp + 0.3
    z_p = (-0.55 * dp) if planing else min(0.05 * T + 0.5 * dp, T - 0.6 * dp)
    rooms = _engine_rooms(lay)
    pairs = n // 2
    groups = pairs + n % 2          # the outer pair first, forward ... the centre shaft (or inner pair) last, aft
    shafts, props = [], []
    mach = lay.geo.get("machinery")
    for k, (y, rank) in enumerate(shaft_ys):
        sid, pid = f"Shaft {k + 1}", f"Propeller {k + 1}"
        g = pairs - rank
        room = rooms[min(len(rooms) - 1, g * len(rooms) // groups)] if rooms else None
        xs = (room[0] + room[1]) / 2 if room else (mach[0] if mach else -0.2 * L)
        zs = ib + SHAFT_ABOVE_IB
        xp = x_p0 + STAGGER * L * (rank - (1 if n % 2 == 0 else 0))
        xp = min(xp, xs - 1.0)
        pos = "centre" if abs(y) < 1e-6 else "wing" if pairs == 1 else "outer" if rank == pairs else "inner"
        shafts.append(dict(id=sid, y=y, position=pos, engine_room=room[2] if room else None, propeller=pid,
                           p0=(xs, y, zs), p1=(xp, y, z_p)))
        props.append(dict(id=pid, x=xp, y=y, z=z_p, diameter=dp, shaft=sid, position=pos))
    return dict(screws=n, planing=planing, ib=ib, shafts=shafts, propellers=props, rudders=rudders,
                rated_mw_per_shaft=mw)


def build(lay, design, res, form, gr=None):
    """The propulsion train: dict(shafts, propellers, rudders, alleys), each a list of dicts with heights above the
    keel (hitbox.export_hitboxes turns them into components), and the steering gear's room id. gr: gear(), when the
    hull form was built round it."""
    gr = gr or gear(lay, design, res)
    mach = lay.geo.get("machinery")
    shafts, alleys = [], []
    for k, sh in enumerate(gr["shafts"]):
        (xs, y, zs), (xp, _, z_p) = sh["p0"], sh["p1"]
        z_at = lambda x: zs + (z_p - zs) * (xs - x) / (xs - xp) if xs != xp else zs
        # where the shaft leaves the hull: aft from the engine, the first point the hull no longer holds it
        exit_x = xp + 0.3
        steps = max(2, int((xs - xp) / 0.5))
        for j in range(steps + 1):
            x = xs - (xs - xp) * j / steps
            if abs(y) + SHAFT_R + 0.2 > form.half_width(x, z_at(x)):
                exit_x = x
                break
        shafts.append({**sh, "exit_x": exit_x})
        a0 = mach[0] if mach else xs
        if exit_x < a0 - 0.5:
            zt = [z_at(a0), z_at(exit_x)]
            alleys.append(dict(id=f"Shaft alley {k + 1}", shaft=sh["id"], x0=exit_x, x1=a0, y=y,
                               base=max(gr["ib"], min(zt) - ALLEY_H / 2), top=max(zt) + ALLEY_H / 2))
            shafts[-1]["alley"] = alleys[-1]["id"]
    steering = next((c["id"] for c in lay.compartments if c["kind"] == "steering"), None)
    return dict(shafts=shafts, propellers=gr["propellers"], rudders=gr["rudders"], alleys=alleys,
                rated_mw_per_shaft=gr["rated_mw_per_shaft"], steering=steering)


def link(tr, sub, D):
    """Link the train (build) into the subdivision: each engine room lists its shafts, the steering gear its rudders,
    and every cell a shaft or alley passes through lists it in "through". D: the hull's depth (the subdivision's
    heights are above the main deck, the train's above the keel)."""
    rooms = {r["id"]: r for r in sub["rooms"]}
    for sh in tr["shafts"]:
        if sh["engine_room"] in rooms:
            rooms[sh["engine_room"]].setdefault("shafts", []).append(sh["id"])
    if tr["steering"] in rooms:
        rooms[tr["steering"]]["rudders"] = [rd["id"] for rd in tr["rudders"]]
    for c in sub["cells"]:
        inside = lambda x, y, zz: (c["x0"] <= x < c["x1"] and c["y0"] <= y < c["y1"] and c["base"] <= zz < c["top"])
        for sh in tr["shafts"]:
            (x0, y, z0), (x1, _, z1) = sh["p0"], sh["p1"]
            if not (c["y0"] <= y < c["y1"] and c["x0"] < x0 and c["x1"] > sh["exit_x"]):
                continue
            n = max(2, int((x0 - sh["exit_x"]) / 0.5))
            if any(inside(x, y, z0 + (z1 - z0) * (x0 - x) / (x0 - x1) - D)
                   for x in (x0 - (x0 - sh["exit_x"]) * k / n for k in range(n + 1))):
                c.setdefault("through", []).append(sh["id"])
        for a in tr["alleys"]:
            hw = ALLEY_W / 2
            if (min(c["x1"], a["x1"]) - max(c["x0"], a["x0"]) > 0.05 and
                    min(c["y1"], a["y"] + hw) - max(c["y0"], a["y"] - hw) > 0.05 and
                    min(c["top"], a["top"] - D) - max(c["base"], a["base"] - D) > 0.05):
                c.setdefault("through", []).append(a["id"])

