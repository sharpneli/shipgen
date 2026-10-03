"""
planing: planing-hull fast craft (motor torpedo boats, PT boats, motor gunboats).

Light wooden hard-chine hulls with a fine entry and a broad transom, high-speed petrol (or diesel) engines
exhausting through the transom (no funnels), a small charthouse with the open bridge, and fixed torpedo
tubes along the deck edges, toed out a few degrees, aimed by steering the boat.

    "torpedoes": {"mounts": 2, "tubes": 1}     fixed tubes, in port/starboard pairs (mounts rounded up to even)
    "machinery": {"tech": {...}}             default: 1940 petrol engines (plant-templates.md)

POWER IS A PLACEHOLDER: navarch.planing_power (a flat resistance/weight ratio once planing). It is the one
function to replace with a researched planing model; TUNING planing_rw / planing_rw_disp / planing_eta tune
it meanwhile.
"""
from __future__ import annotations

import armament
import ordnance
from layout import LEVEL_H, Layout, _fp_circle, _fp_rect, add_block, clamp, plan_machinery
from navarch import Weight, volumetric_froude
from geometry import AA_CFG, Hull
from styles.base import Style
from styles.carrier import _vdc

WOOD_T_PER_M2 = 0.10    # charthouse weight per m^2 of footprint


def planing_hull_spec(design):
    h = design["hull"]
    return dict(length=h["length"], beam=h["beam"], deck_inset=0.15, plank_spacing=0.55,
                bow=dict(taper=0.45, power=1.25, shape="pointed"),
                stern=dict(taper=0.04, transom=0.92, power=2.0, shape="round"))


class Planing(Style):
    name = "planing"
    DEFAULT_TECH = {"name": "Petrol engines (1940)", "fuel": "petrol", "weight_kg_per_kw": 6.5, "stress_floor": 0.7,
                   "sfc_g_per_kwh": 291, "density_t_per_m3": 0.4, "unit_max_mw": 1.1,
                   "unit": {"mw": 1, "height_m": 1.2, "width_m": 1.1, "length_m": 2.5}, "boiler_fraction": 0.0,
                   "crew_k": 3, "part_load": "DSL",
                   "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620,
                               "air_fuel_ratio": 38}}
    DEFAULT_CB = 0.45
    SIZE = dict(length=(8.0, 60.0), beam_max=12.0, gm_frac=0.06, tb=1.0, lb_max=4.5, slender=False)
    LIMITS = {("hull", "block_coefficient"): (0.35, 0.6),
              ("speed_kn",): (15, 60), ("range_nm",): (100, 3000)}

    def tuning(self, design):
        return dict(super().tuning(design), power_model="planing", hull_k=0.06, freeboard_a=0.04,
                    freeboard_b=0.8, misc_frac=0.07, cruise_kn=25.0, lcb_frac=-0.11, gm_stiff_frac=0.5,
                    fn_warn=99.0, lb_warn=2.8, trim_tol_frac=0.025, trim_warn_frac=0.01)

    def build_layout(self, design, res, shift=0.0):
        return _layout(design, res, shift)

    def checks(self, design, r, tun):
        fnv = volumetric_froude(r.full, design["speed_kn"])
        if fnv < 2.0:
            return [f"Not fully planing at {design['speed_kn']} kn (Fn∇ {fnv:.1f}, want 2+): the hull is too heavy "
                    "or too slow to rise onto the plane, so the power is spent pushing water."]
        return []

    CREW_STANDARD = "H0"     # sleep at station

    def results(self, design, lay, r):
        return dict(volumetric_froude=round(volumetric_froude(r.full, design["speed_kn"]), 2),
                    power_to_weight_hp_per_t=round(r.power_shp / r.full, 1), power_model="planing placeholder")

    def summary(self, design, lay, r):
        return [f"planing: Fn∇ {volumetric_froude(r.full, design['speed_kn']):.2f}   "
                f"{r.power_shp / r.full:.0f} hp/t   (placeholder power model)"]


def _layout(design, res, shift):
    shp, depth = res.power_shp, res.depth
    lay = Layout()
    hs = planing_hull_spec(design)
    hull = Hull(hs)
    lay.hull = hull
    L, B = hull.L, hull.B
    lay.shift_range = (-0.04 * L, 0.04 * L)
    shift = clamp(shift, *lay.shift_range)
    lay.geo["shift"] = shift

    # charthouse with the open bridge at its after end, a short radar mast
    blocks = []
    cx0, cx1 = 0.0 + shift, 0.22 * L + shift
    wc = 0.42 * B
    add_block(lay, blocks, "Charthouse", cx0, cx1, wc, 1, 0.45 * wc, 0.2, t_per_m2=WOOD_T_PER_M2)
    masts = [dict(x=cx0 + 0.25 * (cx1 - cx0), yard=min(0.5 * B, 2.4), tripod=False, top=LEVEL_H + 3.5)]

    m0, m1 = -0.42 * L, -0.08 * L
    L_mach = plan_machinery(lay, design, res, hull, (m0 + m1) / 2)
    if L_mach > m1 - m0:
        lay.fail("length", f"The engines need {L_mach:.1f} m, but the engine room has {m1 - m0:.1f} m.")
    lay.geo["machinery"] = (m0, m1)
    lay.geo["machinery_x"] = (m0 + m1) / 2
    lay.geo["citadel"] = (m0, m1)

    mounts, turret_types = [], {}
    # fixed torpedo tubes on the deck edges, toed out; first pair beside the charthouse
    tp = design.get("torpedoes") or {}
    if tp.get("mounts"):
        xs = [cx0 + 0.3 * (cx1 - cx0) - k * 0.5 for k in range(int(0.6 * L / 0.5))]

        def y_of_x(x, t):
            w = ((t["barrels"] - 1) * t["spacing"] + t["barrel_w"]) / 2
            return min(hull.half_width(x + t["barrel_len"] / 2), hull.half_width(x - t["barrel_len"] / 2)) - w - 0.15
        armament.fixed_tube_pairs(lay, mounts, turret_types, tp, xs, y_of_x, toe_deg=5.0)

    # guns: on the foredeck and the after deck, on the centreline
    fore, aft = armament.gun_groups(design)
    if fore:
        armament.gun_line(lay, mounts, turret_types, fore, "main", "ABC", L / 2 - 0.16 * L, -1, 0.0, 0,
                          lambda x: 0.2, armour_mm=(design.get("armour") or {}).get("turret_mm", 0), depth=depth)
        armament.gun_line(lay, mounts, turret_types, aft, "main", "YXW", -L / 2 + 1.6, +1, 0.0, 180,
                          lambda x: 0.2, armour_mm=(design.get("armour") or {}).get("turret_mm", 0), depth=depth)

    xs = [-L / 2 + 0.1 * L + v * 0.7 * L for v in _vdc(48)]
    sec = design.get("secondary") or {}
    if sec.get("per_side"):
        ts_id, ts = armament.gun_type(sec)
        r = armament.body_reach(ts)
        armament.side_pairs(lay, mounts, turret_types, "secondary", ts_id, ts, sec["per_side"],
                            [(x, hull.half_width(x) - r - 0.3, 0.2) for x in xs], "S")
    # AA (machine guns, 20 mm): a pair just aft of the bridge first, then along the deck
    aa_out = []
    aa_req = design.get("aa") or {}
    for kind, count in (("quad40", aa_req.get("heavy", 0)), ("single20", aa_req.get("light", 0))):
        rr = AA_CFG[kind][0]
        cands = [(cx0 - rr - 0.3, rr + 0.15, 0.2), (cx0 - rr - 0.3, 0.0, 0.2)]
        cands += [(x, hull.half_width(x) - rr - 0.3, 0.2) for x in xs] + [(x, 0.0, 0.2) for x in xs]
        armament.place_aa(lay, aa_out, kind, count, cands, spacing=0.6)

    # engine room hatches where the guns leave room, the smoke generator on the transom
    fittings = []
    for k in range(3):
        hx, hl = m0 + (k + 0.5) * (m1 - m0) / 3, 0.18 * (m1 - m0)
        fp = _fp_rect(hx - hl / 2, -0.16 * B, hx + hl / 2, 0.16 * B)
        if lay.free(fp, 0.2):
            fittings.append(dict(x=hx, y=0.0, l=hl, w=0.32 * B, color="hatch_coaming"))
            lay.occupy(fp, 0, 0.5, f"Engine hatch {k + 1}")
    fp = _fp_rect(-L / 2 + 0.2, -0.18 * B, -L / 2 + 1.0, 0.18 * B)
    if lay.free(fp, 0.1):
        fittings.append(dict(x=-L / 2 + 0.6, y=0.0, l=0.7, w=0.35 * B, color="fitting"))
        lay.occupy(fp, 0, 1.0, "Smoke generator")
    # a life raft on the engine room roof
    boats = []
    rl, rw_ = clamp(0.1 * L, 1.8, 3.0), clamp(0.22 * B, 1.0, 1.6)
    for x in [m1 - rl / 2 - k * 0.5 for k in range(int((m1 - m0) / 0.5))]:
        fp = _fp_rect(x - rl / 2, -rw_ / 2, x + rl / 2, rw_ / 2)
        if lay.free(fp, 0.2):
            boats.append(dict(x=x, y=0.0, l=rl, w=rw_, top=1.0))
            lay.occupy(fp, 0.5, 1.0, "Raft")
            break

    inner_hw = 0.8 * B / 2
    lay.compartments += [
        dict(id="Crew space", kind="accommodation", x0=cx1, x1=L / 2 - 0.08 * L, half_width=inner_hw),
        dict(id="Fuel tanks", kind="fuel_tank", x0=m1, x1=cx0 + 0.05 * L, half_width=inner_hw),
        dict(id="Engine room", kind="engine_room", x0=m0, x1=m1, half_width=inner_hw),
        dict(id="Tiller flat", kind="steering", x0=-L / 2, x1=m0, half_width=0.6 * B / 2)]
    # the guns' ammunition in a locker at the forward end of the crew space (ordnance.stow)
    guns = ordnance.guns(mounts)
    if guns:
        lx1, lw = L / 2 - 0.08 * L, 0.5 * inner_hw
        ordnance.stow(lay, mounts, [dict(x0=lx1 - ordnance.zone_length(ordnance.booked_m3(lay, guns), 2 * lw,
                                                                       lay.geo["plant"], tiers=1, least=0.5),
                                         x1=lx1, half_width=lw, rooms=[dict(id="Ammunition locker", mounts=guns)])])
    lay.spec = dict(
        id=design["id"], name=design.get("name", design["id"]), **{"class": design.get("type", "")},
        length=L, beam=B, bow=hs["bow"], stern=hs["stern"], deck="steel",
        deck_inset=hs["deck_inset"], plank_spacing=hs["plank_spacing"],
        turret_types=turret_types,
        turrets=[dict(id=m["id"], type=m["type"], x=m["x"], y=m["y"], z=m["z"], rest=m["rest"]) for m in mounts],
        superstructure=[{k: v for k, v in b.items() if k not in ("id", "kind")} for b in blocks],
        funnels=[], masts=masts, aa=[{k: v for k, v in a.items() if k not in ("id", "base")} for a in aa_out],
        boats=boats, fittings=fittings)   # no bollards: a small craft's cleats are too small to draw
    lay.mounts, lay.blocks, lay.funnels, lay.aa, lay.fun_top = mounts, blocks, [], aa_out, 0.0
    return lay


STYLE = Planing()
