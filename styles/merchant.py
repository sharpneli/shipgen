"""
merchant: cargo ships and tankers.

    "cargo": {"kind": "dry" | "tanker", "deadweight_t": 8500}      cargo carried at full load
    "machinery": {"position": "amidships" | "aft", "tech": {...}, ...}
                 the plant (powerplant.py); default tech: 1940 oil-fired triple expansion (Liberty)

The hull is a "three-island" ship: a raised forecastle, a bridge deck carrying the midships house, and a poop.
Holds (dry cargo: hatches, masts and derricks) or tanks (tanker: tank hatches and a catwalk) fill the
wells between them. With machinery aft the engine house and funnel stand on a longer poop and the midships
house is just the bridge. Standard displacement is the lightship; full load adds fuel and cargo.

Merchants cruise at their service speed, so range is computed at speed_kn. Guns are secondaries fitted where
they suit (DEMS guns, Q-ships; no main battery): "ends" on the poop and forecastle, "sides" along the bulwarks,
then torpedo mounts along the sides and AA on the house and ends.
"""
from __future__ import annotations

import armament
import ordnance
from layout import (LEVEL_H, Layout, _fp_circle, _fp_rect, add_block, add_funnel_weights, add_machinery_rooms,
                    add_steering, boiler_seg, clamp, finish_layout, plan_funnels, plan_machinery,
                    set_citadel, stack_machinery)
from navarch import Weight
from geometry import AA_CFG, Hull
from styles.base import Style
from styles.carrier import SECONDARY_LIMITS, _vdc, guns_are_secondaries

RAISED_H = 2.4      # forecastle, bridge deck and poop stand this far above the main deck



STOWAGE = {"dry": 1.4, "tanker": 1.25}   # m3 of hold per tonne of cargo (dry: general cargo, bale; tanker: oil)
DOUBLE_BOTTOM = 1.2                       # m under the holds


def hold_volume(hull, holds, depth):
    """Volume of the holds below the main deck: plan area times depth above the double bottom, times 0.9 for the
    bilges."""
    area = sum((h1 - h0) / 8 * sum(2 * hull.half_width(h0 + (h1 - h0) * (k + 0.5) / 8) for k in range(8))
               for h0, h1 in holds)
    return 0.9 * area * max(0.0, depth - DOUBLE_BOTTOM)


def cargo(design):
    return {"kind": "dry", "deadweight_t": 0.0, **(design.get("cargo") or {})}


def machinery(design):
    return {"position": "amidships", **(design.get("machinery") or {})}


def stow(C, holds, ctx, fill=1.5):
    """Spread C tonnes of cargo over the holds so the loaded ship floats level, the way a cargo officer plans
    the stowage: start in proportion to hold length, then shift cargo toward the forward or the after holds
    (no hold over `fill` x its proportional share) until the centre of gravity sits over the centre of
    buoyancy, or as close as the holds allow."""
    lens = [x1 - x0 for x0, x1 in holds]
    xs = [(x0 + x1) / 2 for x0, x1 in holds]
    total = sum(lens)
    prop = [C * l / total for l in lens]
    caps = [fill * p for p in prop]
    w_light = sum(w.w for w in ctx["items"])
    m_light = sum(w.w * w.x for w in ctx["items"])
    full = w_light + ctx["fuel"] + C
    xc = (full * ctx["lcb"] - m_light - ctx["fuel"] * ctx["fuel_x"]) / C   # where the cargo's centre must be

    def packed(order):
        out, left = [0.0] * len(holds), C
        for i in order:
            out[i] = min(caps[i], left)
            left -= out[i]
        return out

    def centre(ws):
        return sum(w * x for w, x in zip(ws, xs)) / C
    x_p = centre(prop)
    end = packed(sorted(range(len(holds)), key=lambda i: -xs[i] if xc > x_p else xs[i]))
    x_e = centre(end)
    a = 0.0 if abs(x_e - x_p) < 1e-9 else max(0.0, min(1.0, (xc - x_p) / (x_e - x_p)))
    return [(1 - a) * p + a * e for p, e in zip(prop, end)]


def merchant_hull_spec(design):
    h = design["hull"]
    cb = h["block_coefficient"]
    return dict(length=h["length"], beam=h["beam"],
                bow=dict(taper=clamp(0.42 - 0.3 * cb, 0.15, 0.3), power=2.0),
                stern=dict(taper=0.15, transom=0.3))


class Merchant(Style):
    name = "merchant"
    SECONDARY_LIST = True
    LIMITS = {**SECONDARY_LIMITS, ("hull", "block_coefficient"): (0.55, 0.85), ("speed_kn",): (6, 30),
              ("cargo", "deadweight_t"): (0, 80000)}

    DEFAULT_TECH = {   # 1940 oil-fired triple expansion (Liberty), plant-templates.md
        "name": "Triple expansion, large-tube water-tube boilers, oil-fired (1940)",
        "fuel": "oil",
        "weight_kg_per_kw": 103.5,
        "stress_floor": 0.45,
        "sfc_g_per_kwh": 660,
        "density_t_per_m3": 0.28,
        "unit_max_mw": 12.0,
        "unit": {"mw": 5, "height_m": 7.5, "width_m": 4.5, "length_m": 9},
        "boiler_fraction": 0.55,
        "crew_k": 15.3,
        "part_load": "REC",
        "draught": {"system": "forced", "velocity_m_s": 14.0, "reach_m": 20.0, "gas_temp_k": 570, "air_fuel_ratio": 15},
    }
    DEFAULT_CB = 0.72
    SIZE = {**Style.SIZE, "gm_frac": 0.04, "tb": 0.46, "lb_max": 8.0}

    def validate(self, design):
        errs = super().validate(design) + guns_are_secondaries(self, design)
        if cargo(design)["kind"] not in ("dry", "tanker"):
            errs.append(f"cargo.kind = {cargo(design)['kind']!r}: use dry or tanker")
        m = machinery(design)
        if m["position"] not in ("amidships", "aft"):
            errs.append(f"machinery.position = {m['position']!r}: use amidships or aft")
        return errs

    def tuning(self, design):
        return dict(super().tuning(design), hull_k=0.10, freeboard_a=0.011, freeboard_b=1.0, misc_frac=0.03,
                    cruise_at_service=True, tb_max=0.62, lcb_frac=0.012,
                    gm_stiff_frac=0.2)

    def build_layout(self, design, res, shift=0.0):
        return _layout(design, res, shift)

    def rough_payload(self, design, D):
        L = design["hull"]["length"]
        return [Weight("Cargo gear", "superstructure", 0.01 * L ** 2, z_rel=("deck", 3))]

    def payload_weights(self, design, L, D, geo, tun, ctx):
        cg = cargo(design)
        holds = geo.get("holds") or [(-0.3 * L, 0.3 * L)]
        if not cg["deadweight_t"]:
            return [], []
        loads = stow(cg["deadweight_t"], holds, ctx)
        return [], [Weight(f"Cargo, {'tank' if cg['kind'] == 'tanker' else 'hold'} {i + 1}", "cargo",
                           w, x=(x0 + x1) / 2, z_rel=("frac", 0.45))
                    for i, ((x0, x1), w) in enumerate(zip(holds, loads)) if w > 0]

    CREW_STANDARD = "H3"     # cabins for two to four, messrooms
    CREW_DECK_K = 0.3        # merchant manning: a small deck department

    def results(self, design, lay, r):
        cg, m = cargo(design), machinery(design)
        return dict(cargo_t=round(cg["deadweight_t"]), deadweight_t=round(r.full - r.std),
                    cargo_kind=cg["kind"], holds=len(lay.geo.get("holds", [])), machinery_position=m["position"])

    def summary(self, design, lay, r):
        cg, m = cargo(design), machinery(design)
        return [f"cargo: {cg['deadweight_t']:,.0f} t {cg['kind']} in {len(lay.geo.get('holds', []))} "
                f"{'tanks' if cg['kind'] == 'tanker' else 'holds'}   deadweight {r.full - r.std:,.0f} t   "
                f"machinery {m['position']}"]


def _layout(design, res, shift):
    shp, depth = res.power_shp, res.depth
    lay = Layout()
    hs = merchant_hull_spec(design)
    hull = Hull(hs)
    lay.hull = hull
    L, B = hull.L, hull.B
    cg, mach = cargo(design), machinery(design)
    tanker = cg["kind"] == "tanker"
    aft_engines = mach["position"] == "aft"
    lay.shift_range = (-0.05 * L, 0.05 * L)
    shift = clamp(shift, *lay.shift_range)
    lay.geo["shift"] = shift
    armour = design.get("armour") or {}
    L_mach = plan_machinery(lay, design, res, hull, -0.38 * L if aft_engines else 0.0)

    # ---------------- the three islands ----------------
    fc_len = clamp(0.09 * L, 6, 22)
    poop_len = max(0.08 * L, L_mach + 0.03 * L) if aft_engines else 0.08 * L
    if aft_engines:
        bd_len = clamp(0.10 * L, 10, 24)
        bxc = 0.08 * L + shift
    else:
        bd_len = max(clamp(0.16 * L, 12, 40), L_mach + 6)
        bxc = -0.02 * L + shift
    islands = [("Forecastle", L / 2 - fc_len, L / 2), ("Bridge deck", bxc - bd_len / 2, bxc + bd_len / 2),
               ("Poop", -L / 2, -L / 2 + poop_len)]
    raised = []
    for name, x0, x1 in islands:
        lay.decks.append(dict(id=name, kind="deck", points=hull.points(inset=0.3, x_min=x0, x_max=x1),
                              base=0.0, top=RAISED_H))
        raised.append(dict(x0=x0, x1=x1))

    def deck_h(x):
        return RAISED_H if any(x0 <= x <= x1 for _, x0, x1 in islands) else 0.0

    # ---------------- houses, funnel, boats ----------------
    blocks, funnels, boats = [], [], []
    bx0, bx1 = bxc - bd_len / 2, bxc + bd_len / 2
    hw_mid = hull.half_width(bxc)
    wh = min(0.62 * B, 2 * (hw_mid - 1.5))
    house_ids = []

    def house(bid, x0, x1, w, level, rf, rb, z0=RAISED_H):
        house_ids.append(bid)
        return add_block(lay, blocks, bid, x0, x1, w, level, rf, rb, z0=z0)

    house("House", bx0 + 0.08 * bd_len, bx1 - 0.06 * bd_len, wh, 1, 1.2, 1.0)
    if not aft_engines:
        house("Boat deck house", bx0 + 0.25 * bd_len, bx1 - 0.08 * bd_len, 0.5 * B, 2, 1.0, 0.8)
    house("Bridge", bx1 - 0.3 * bd_len, bx1 - 0.08 * bd_len, min(0.92 * B, 2 * (hw_mid - 0.4)), 3 if not aft_engines else 2,
          0.6, 0.6)
    fun_top = RAISED_H + LEVEL_H * 3 + 2.0
    if aft_engines:
        ex0, ex1 = -L / 2 + 0.03 * L, -L / 2 + poop_len - 1.0
        house("Engine house", ex0, ex1, min(0.7 * B, 2 * (hull.half_width((ex0 + ex1) / 2) - 1.5)), 1, 1.0, 1.0)
        house("Engine house upper", ex0 + 0.15 * (ex1 - ex0), ex1 - 0.1 * (ex1 - ex0), 0.45 * B, 2, 0.8, 0.8)
        fx = (ex0 + ex1) / 2 - 0.1 * (ex1 - ex0)
        mx = (-L / 2 + 0.02 * L + -L / 2 + poop_len) / 2
        boat_x, boat_y = ex0 + 0.35 * (ex1 - ex0), 0.35 * B
        fun_top = RAISED_H + LEVEL_H * 2 + 3.0
    else:
        fx = bx0 + 0.3 * bd_len
        mx = bx0 + L_mach / 2 + 1.0
        boat_x, boat_y = fx, 0.31 * B
    # funnels from the plant (powerplant.funnel_plan), in a row along the house from fx
    nfun, fw, fl = plan_funnels(lay, design, res, B, fun_top)
    fw = min(fw, 0.4 * B)
    for i in range(nfun):
        x = fx - i * (fl + 1.5) if aft_engines else fx + (i - (nfun - 1) / 2) * (fl + 1.5)
        funnels.append(dict(id=f"Funnel {i + 1}", x=x, y=0.0, l=fl, w=fw, pipes=1, z0=RAISED_H, seg=boiler_seg(lay)))
        lay.occupy(_fp_rect(x - fl / 2, -fw / 2, x + fl / 2, fw / 2), RAISED_H, fun_top, f"Funnel {i + 1}")
        add_funnel_weights(lay, funnels[-1], fun_top, mx, depth)
    bl_ = clamp(0.045 * L, 5, 9)
    for dx in (-0.6 * bl_, 0.6 * bl_) if L >= 110 else (0.0,):
        for s in (1, -1):
            x = boat_x + dx - 0.5 * fl - 1.0 if dx < 0 else boat_x + dx + 0.5 * fl + 1.0
            boats.append(dict(x=x, y=s * boat_y, l=bl_, w=0.3 * bl_, top=RAISED_H + LEVEL_H + 1.5))
            lay.occupy(_fp_rect(x - bl_ / 2, s * boat_y - 0.15 * bl_, x + bl_ / 2, s * boat_y + 0.15 * bl_),
                       RAISED_H + LEVEL_H, RAISED_H + LEVEL_H + 1.5, f"Boat{len(boats)}")
    lay.geo["machinery"] = (mx - L_mach / 2, mx + L_mach / 2)
    lay.geo["machinery_x"] = mx

    # ---------------- guns: "ends" on the poop and forecastle, "sides" along the bulwarks ----------------
    # (fitted before the cargo gear, which makes way)
    mounts, turret_types = [], {}
    xs = [-L / 2 + 0.06 * L + v * 0.88 * L for v in _vdc(64)]
    armament.place_batteries(
        lay, mounts, turret_types, design,
        [(-L / 2 + 0.025 * L, +1, 0.0, 180, lambda x: deck_h(x) + 0.3, tuple(house_ids)),
         (L / 2 - 0.035 * L, -1, 0.0, 0, lambda x: deck_h(x) + 0.3, ())],
        lambda t: [(x, hull.half_width(x) - armament.body_reach(t) - 0.6, deck_h(x) + 0.3) for x in xs], depth=depth)

    # ---------------- holds or tanks in the wells ----------------
    if aft_engines:
        zones = [(bx1 + 1.0, L / 2 - fc_len - 1.0, +1), (-L / 2 + poop_len + 1.0, bx0 - 1.0, -1)]
    else:
        zones = [(bx1 + 1.0, L / 2 - fc_len - 1.0, +1), (-L / 2 + poop_len + 1.0, bx0 - 1.0, -1)]
    pitch = clamp(0.12 * L, 10, 22) if not tanker else clamp(0.09 * L, 8, 16)
    holds, hatches, masts, fittings = [], [], [], []
    mast_top = clamp(0.12 * L + 4, 10, 24)
    for z0, z1, outward in zones:
        zl = z1 - z0
        if zl < 6:
            continue
        n = max(1, round(zl / pitch))
        hl = zl / n
        zone = [(z0 + i * hl, z0 + (i + 1) * hl) for i in range(n)]
        if outward < 0:      # aft zone: number from the house outward
            zone = zone[::-1]
        holds += zone
        if tanker:
            for h0, h1 in zone:
                for s in (1, -1):
                    fittings.append(dict(x=(h0 + h1) / 2, y=s * 0.22 * B, l=1.4, w=1.4, color="hatch_coaming"))
            continue
        hatch_w = 0.42 * B
        zone_hatches = []
        for h0, h1 in zone:
            hx, hl_ = (h0 + h1) / 2, 0.55 * (h1 - h0)
            while hl_ > 0.25 * (h1 - h0) and not lay.free(_fp_rect(hx - hl_ / 2, -hatch_w / 2, hx + hl_ / 2, hatch_w / 2), 0.4):
                hl_ -= 0.5    # a gun stands in the well: shorten the hatch
            if hl_ <= 0.25 * (h1 - h0):
                zone_hatches.append(None)
                continue
            ht = dict(x=hx, y=0.0, l=hl_, w=hatch_w)
            hatches.append(ht)
            zone_hatches.append(ht)
            lay.occupy(_fp_rect(hx - hl_ / 2, -hatch_w / 2, hx + hl_ / 2, hatch_w / 2), 0, 1.2,
                       f"Hatch {len(hatches)}")
        # masts at every other hold boundary from the house outward, the odd one at the well's outer end
        k = 0
        while k < n:
            if k + 1 < n:
                mxx = zone[k][1] if outward > 0 else zone[k][0]
                served = zone_hatches[k:k + 2]
            else:
                mxx = zone[k][1] - 0.5 if outward > 0 else zone[k][0] + 0.5
                served = zone_hatches[k:k + 1]
            spot = next((mxx + d for d in (0, 1, -1, 2, -2, 3, -3) if lay.free(_fp_circle(mxx + d, 0.0, 0.9), 0.3)), None)
            if spot is None:
                k += 2
                continue
            mxx = spot
            booms = [(h["x"], s * 0.18 * B) for h in served if h for s in (1, -1)]
            masts.append(dict(x=mxx, y=0.0, yard=min(0.25 * B, 6), tripod=False, booms=booms, top=mast_top))
            lay.occupy(_fp_circle(mxx, 0.0, 0.9), 0, mast_top, f"Mast {len(masts)}")
            lay.weights.append(Weight(f"Mast {len(masts)}", "superstructure", 8 + 0.2 * L, x=mxx,
                                      z_rel=("deck", mast_top / 3)))
            k += 2
    if tanker:
        masts.append(dict(x=L / 2 - fc_len - 0.5, y=0.0, yard=min(0.3 * B, 7), tripod=False, top=mast_top))
        for x0, x1 in ((-L / 2 + poop_len, bx0), (bx1, L / 2 - fc_len)):
            fittings.append(dict(x=(x0 + x1) / 2, y=0.0, l=x1 - x0, w=1.2, color="fitting", r=0.2))
    if not holds:
        lay.fail("length", "No room for cargo: the forecastle, midships house and poop fill the hull.")
    elif cg["deadweight_t"]:
        vol = hold_volume(hull, holds, depth)
        need = cg["deadweight_t"] * STOWAGE[cg["kind"]]
        lay.geo["hold_volume"] = vol
        if vol < need:
            lay.fail("length", f"The {'tanks' if tanker else 'holds'} take about {vol:,.0f} m3, but "
                               f"{cg['deadweight_t']:,.0f} t of cargo needs about {need:,.0f} m3. Carry less cargo.")
    hatch_t = sum(h["l"] * h["w"] for h in hatches) * 0.12
    if hatch_t:
        lay.weights.append(Weight("Hatch covers", "superstructure", hatch_t, x=0.0, z_rel=("deck", 1.0)))
    lay.geo["holds"] = holds

    # ---------------- torpedo mounts and AA ----------------

    tp = design.get("torpedoes") or {}
    if tp.get("mounts"):
        tt_id, tt = armament.torpedo_type(tp)
        r = tt["barrel_len"] / 2 + 0.3
        armament.side_pairs(lay, mounts, turret_types, "torpedo", tt_id, tt, (tp["mounts"] + 1) // 2,
                            [(x, hull.half_width(x) - r - 0.4, deck_h(x) + 0.3) for x in xs], "T", z=1,
                            label="Torpedo")
    aa_out = []
    aa_req = design.get("aa") or {}
    for kind, count in (("quad40", aa_req.get("heavy", 0)), ("single20", aa_req.get("light", 0))):
        rr = AA_CFG[kind][0]
        roof = RAISED_H + LEVEL_H
        cands = [(bx1 - 0.12 * bd_len, min(0.46 * B, hw_mid - 0.4) - rr - 0.2, RAISED_H + LEVEL_H * 2),
                 (bx0 + 0.1 * bd_len, wh / 2 - rr - 0.3, roof)]
        cands += [(x, hull.half_width(x) - rr - 0.6, deck_h(x)) for x in xs]
        armament.place_aa(lay, aa_out, kind, count, cands, ignore=tuple(house_ids))

    # ---------------- compartments ----------------
    inner_hw = 0.85 * B / 2
    m0, m1 = lay.geo["machinery"]
    for i, (h0, h1) in enumerate(holds):
        lay.compartments.append(dict(id=f"{'Tank' if tanker else 'Hold'} {i + 1}",
                                     kind="cargo_tank" if tanker else "hold", x0=h0, x1=h1, half_width=inner_hw))
    add_machinery_rooms(lay, stack_machinery(lay.geo["plant"]["segments"], m1), inner_hw, depth)
    steer = add_steering(lay)
    # the guns' magazine aft, just forward of the steering gear, low on the inner bottom (ordnance.stow)
    guns = ordnance.guns(mounts)
    if guns:
        mx0 = steer["x1"]
        mw = min(inner_hw, 0.5 * B / 2)
        ordnance.stow(lay, mounts, [dict(x0=mx0, x1=mx0 + ordnance.zone_length(
            ordnance.booked_m3(lay, guns), 2 * mw, lay.geo["plant"]), half_width=mw,
            rooms=[dict(id="Gun magazine", mounts=guns)])])
    set_citadel(lay, m0, m1)

    return finish_layout(lay, design, hs, mounts, turret_types, blocks, funnels, masts, aa_out, fun_top,
                         boats=boats, raised_decks=raised, hatches=hatches, fittings=fittings,
                         bollards=[L / 2 - 0.04 * L, -L / 2 + 0.04 * L],
                         chain_x=L / 2 - 0.05 * L, hawse_back=0.025 * L + 1.0)


STYLE = Merchant()
