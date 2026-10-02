"""
navarch — "naval architecture lite" weight, power and stability model.

The player never enters tonnage. Displacement is whatever the ship needs to carry its hull,
machinery, fuel, armour and armament. Some of those depend on displacement themselves
(power ~ displacement^2/3, hull depth ~ draught), so solve() iterates to a fixed point.

All constants live in TUNING so the game designer can rebalance without touching the code.
The model is calibrated loosely against WWII ships (see calibrate() at the bottom). Treat it as
plausible game physics, not a design tool.

Units: metres, tonnes (metric), knots, shp, mm of armour.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

STEEL = 7.85  # t/m^3
SEAWATER = 1.025  # t/m^3

TUNING = dict(
    hull_k=0.112,           # structure weight = hull_k * (L*B*D)^hull_exp
    hull_exp=1.0,
    freeboard_a=0.018,      # design freeboard = a*L + b
    freeboard_b=1.5,
    admiralty_a=111.0,      # admiralty coefficient C = a * Fn^-b * (form corrections)
    admiralty_b=0.69,
    shp_per_t_ref=41.0,     # machinery specific power at 212,000 shp ...
    shp_per_t_exp=0.66,     # ... rising for smaller plants: (212000/P)^exp
    shp_per_t_max=105.0,
    sfc=0.42,               # kg fuel per shp per hour at cruise (incl. hotel load)
    cruise_kn=15.0,
    misc_frac=0.08,         # equipment, outfit, electrics, stores, crew, as a fraction of std displacement
    superstructure_t_per_m2=0.32,
    gun_k=1.6e-6,           # gun tube mass t = gun_k * cal_mm^3 * (L/50)
    mount_k=2.0,            # turret machinery mass = mount_k * guns
    shell_k=1.83e-5,        # shell kg = shell_k * cal_mm^3
    ammo_mult=1.6,          # shell + propellant + handling gear
    rounds_heavy=100, rounds_medium=200, rounds_light=350,
    torp_mount_t=5.0, torp_tube_t=3.0, torp_t=1.6, torp_fixed_tube_t=1.0,
    aa_t={"quad40": 15.0, "twin40": 7.0, "single20": 1.0},
    belt_h_a=0.30, belt_h_b=2.4,   # belt height = a*T + b
    lcb_frac=-0.012,        # longitudinal centre of buoyancy, fraction of L (negative = aft)
    planing_rw=0.13,        # planing placeholder: resistance/weight once planing ...
    planing_rw_disp=0.06,   # ... and at Fn∇ = 1
    planing_eta=0.5,        # propulsive efficiency
)


# Machinery other than the default lightweight naval turbines (TUNING shp_per_t_*): fixed shp per tonne,
# fuel kg per shp-hour (incl. hotel load), and an engine room length factor (styles.merchant).
MACHINERY = {
    "naval_turbine": None,
    "coal_turbine": dict(spt=13.0, sfc=0.75, len_k=1.4),   # pre-1920 naval turbines with coal-fired boilers
    "steam_recip": dict(spt=6.0, sfc=0.62, len_k=1.6),
    "steam_turbine": dict(spt=10.0, sfc=0.42, len_k=1.3),
    "diesel": dict(spt=8.0, sfc=0.20, len_k=1.2),
    "petrol": dict(spt=450.0, sfc=0.28, len_k=0.5),        # high-speed petrol engines (MTBs, PT boats)
    "fast_diesel": dict(spt=180.0, sfc=0.22, len_k=0.6),   # high-speed diesels (fast attack craft)
}


def machinery_tuning(mtype):
    """TUNING overrides for a machinery type."""
    mc = MACHINERY[mtype]
    if mc is None:
        return {}
    return dict(shp_per_t_ref=mc["spt"], shp_per_t_exp=0.0, shp_per_t_max=mc["spt"], sfc=mc["sfc"])


@dataclass
class Weight:
    name: str
    group: str
    w: float
    x: float = 0.0
    z: float | None = None              # absolute height above keel, set once D is known
    z_rel: tuple = ("frac", 0.5)         # ("frac", k) -> k*D ; ("deck", h) -> D + h


@dataclass
class Result:
    std: float = 0.0
    full: float = 0.0
    draught: float = 0.0
    depth: float = 0.0
    freeboard: float = 0.0
    power_shp: float = 0.0
    fuel: float = 0.0
    crew: int = 0
    gm_full: float = 0.0
    gm_light: float = 0.0
    lcg: float = 0.0
    lcb: float = 0.0
    trim_m: float = 0.0
    weights: list = field(default_factory=list)
    groups: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# component weights
# ---------------------------------------------------------------------------
def gun_tube_t(cal_mm, cal_len):
    return TUNING["gun_k"] * cal_mm ** 3 * (cal_len / 50.0)


def rounds_per_gun(cal_mm):
    if cal_mm >= 200:
        return TUNING["rounds_heavy"]
    if cal_mm >= 150:
        return TUNING["rounds_medium"]
    return TUNING["rounds_light"]


def mount_weights(t: dict, armour_mm: float, depth: float, level: int):
    """(turret incl. guns+armour, barbette armour, magazine/ammo) for one mount of type t."""
    cal, cl, n, r = t["calibre_mm"], t["calibre_length"], t["barrels"], t["r"]
    guns = n * gun_tube_t(cal, cl)
    mech = TUNING["mount_k"] * guns + (4.0 * min(1.0, (cal / 76.0) ** 3) if cal < 150 else 0.0)
    th = 0.42 * r
    area = 2 * math.pi * 0.9 * r * th + 0.85 * math.pi * r * r
    t_avg = 0.55 * armour_mm / 1000.0
    turret = guns + mech + area * t_avg * STEEL
    # barbette: from the armour deck up to the turret base (superfiring turrets are taller)
    bh = 0.45 * depth + level * (th + 1.0)
    barbette = 2 * math.pi * 0.95 * r * bh * (0.8 * armour_mm / 1000.0) * STEEL if t.get("barbette", True) else 0.0
    ammo = n * rounds_per_gun(cal) * TUNING["shell_k"] * cal ** 3 / 1000.0 * TUNING["ammo_mult"]
    return turret, barbette, ammo


def torpedo_weight(tubes, fixed=False):
    if fixed:   # fixed deck tubes: no training gear, light tubes
        return tubes * (TUNING["torp_fixed_tube_t"] + TUNING["torp_t"])
    return TUNING["torp_mount_t"] + tubes * (TUNING["torp_tube_t"] + TUNING["torp_t"])


# ---------------------------------------------------------------------------
# hydrodynamics
# ---------------------------------------------------------------------------
def froude(v_kn, L):
    return v_kn * 0.5144 / math.sqrt(9.81 * L)


def admiralty_c(v_kn, L, B, cb, tun=TUNING):
    fn = max(froude(v_kn, L), 0.08)
    c = tun["admiralty_a"] * fn ** -tun["admiralty_b"]
    c *= (L / B / 8.0) ** 0.25          # slender hulls are easier to drive
    c *= (0.55 / cb) ** 0.5             # fuller hulls are harder to drive
    return c


def power_required(disp, v_kn, L, B, cb, tun=TUNING):
    if tun.get("power_model") == "planing":
        return planing_power(disp, v_kn, tun)
    return disp ** (2 / 3) * v_kn ** 3 / admiralty_c(v_kn, L, B, cb, tun)


def volumetric_froude(disp, v_kn):
    """Fn∇ = V / sqrt(g ∇^(1/3)): about 1 at the hump, 2+ when a hull is fully planing."""
    return v_kn * 0.5144 / math.sqrt(9.81 * (disp / SEAWATER) ** (1 / 3))


def planing_power(disp, v_kn, tun=TUNING):
    """PLACEHOLDER planing-hull power model, to be replaced by a researched one.
    Resistance/weight ratio rises as V^2 in displacement mode, ramps to the planing plateau between
    Fn∇ 1 and 2, then stays flat; shp = R V / propulsive efficiency."""
    fnv = volumetric_froude(disp, v_kn)
    hi, lo = tun["planing_rw"], tun["planing_rw_disp"]
    rw = lo * fnv ** 2 if fnv < 1 else lo + (hi - lo) * min(1.0, fnv - 1)
    r_kn = rw * disp * 9.81                      # kN (disp in t)
    return r_kn * v_kn * 0.5144 / tun["planing_eta"] / 0.7457


def machinery_weight(shp, tun=TUNING):
    spt = tun["shp_per_t_ref"] * (212000.0 / max(shp, 1.0)) ** tun["shp_per_t_exp"]
    spt = min(spt, tun["shp_per_t_max"])
    return shp / spt


def machinery_length(shp):
    """Length of boiler + engine rooms, metres."""
    return 0.14 * math.sqrt(shp)


def funnel_count(shp):
    return 1 if shp < 25000 else 2


def design_freeboard(L, tun=TUNING):
    return tun["freeboard_a"] * L + tun["freeboard_b"]


def cwp(cb):
    return 0.18 + 0.86 * cb


# ---------------------------------------------------------------------------
# solver
# ---------------------------------------------------------------------------
def solve(design: dict, placed: list[Weight] | None = None, geo: dict | None = None) -> Result:
    """
    design : player input (see designs/*.json)
    placed : weights with x positions supplied by the layout (armament, armour, superstructure).
             If None, a rough estimate is used (first pass, before anything is laid out).
    geo    : layout facts: machinery x, citadel span, ...
    The design's style (styles/) adds its own tuning, structure (counted in standard displacement)
    and payload (cargo, aircraft, aviation fuel).
    """
    import styles
    style = styles.get(design)
    tun = {**TUNING, **style.tuning(design)}
    L = design["hull"]["length"]
    B = design["hull"]["beam"]
    cb = design["hull"].get("block_coefficient", 0.55)
    V = design["speed_kn"]
    rng = design.get("range_nm", 6000)
    geo = geo or {}
    res = Result()

    disp = 200.0 * L * B * cb * 0.04  # initial guess
    for _ in range(60):
        T = disp / (SEAWATER * L * B * cb)
        D = T + design_freeboard(L, tun)
        items: list[Weight] = []
        items.append(Weight("Hull structure", "hull", tun["hull_k"] * (L * B * D) ** tun["hull_exp"],
                            x=-0.01 * L, z_rel=("frac", tun.get("hull_z_frac", 0.58))))
        shp = power_required(disp, V, L, B, cb, tun)
        items.append(Weight("Machinery", "machinery", machinery_weight(shp, tun), x=geo.get("machinery_x", -0.02 * L),
                            z_rel=("frac", 0.32)))
        if placed is None:
            items += rough_payload(design, D) + style.rough_payload(design, D)
        else:
            items += [Weight(**{**w.__dict__}) for w in placed]
        # armour that depends on draught / depth
        items += armour_weights(design, L, B, T, D, geo)
        items += style.structure_weights(design, L, B, T, D, geo, tun)
        std_wo_misc = sum(w.w for w in items)
        std = std_wo_misc / (1 - tun["misc_frac"])
        items.append(Weight("Equipment, outfit, crew & stores", "misc", std - std_wo_misc, x=0.0,
                            z_rel=("frac", 0.5)))
        # fuel for the requested range at cruise speed (merchants cruise at their service speed)
        vc = V if tun.get("cruise_at_service") else min(tun["cruise_kn"], 0.6 * V)
        shp_c = power_required(disp, vc, L, B, cb, tun)
        fuel = shp_c * tun["sfc"] * (rng / vc) / 1000.0
        std_load, full_load = style.payload_weights(design, L, D, geo, tun, dict(
            items=items, fuel=fuel, fuel_x=geo.get("machinery_x", -0.02 * L), lcb=tun["lcb_frac"] * L))
        std += sum(w.w for w in std_load)
        full = std + fuel + sum(w.w for w in full_load)
        if abs(full - disp) < 0.5:
            disp = full
            break
        disp = 0.5 * disp + 0.5 * full
    else:   # every tonne added needs more hull to float it, which adds more tonnes: no design exists
        res.errors.append(f"The weights never settle: the ship needs a bigger hull to carry its load, which "
                          f"needs a bigger hull again (still growing at {full:,.0f} t). Lighten the armour or "
                          "armament, or enlarge the hull.")

    items += std_load
    items.append(Weight("Fuel", "fuel", fuel, x=geo.get("machinery_x", -0.02 * L), z_rel=("frac", 0.18)))
    items += full_load
    for w in items:
        kind, v = w.z_rel
        w.z = v * D if kind == "frac" else D + v

    res.std, res.full, res.fuel = std, full, fuel
    res.draught, res.depth, res.freeboard = full / (SEAWATER * L * B * cb), D, D - full / (SEAWATER * L * B * cb)
    res.power_shp = shp
    res.crew = style.crew(design, std)
    res.weights = items
    groups = {}
    for w in items:
        groups[w.group] = groups.get(w.group, 0.0) + w.w
    res.groups = groups

    # --- stability (transverse) at full load and with fuel burnt ---
    def gm(disp_case, include_fuel):
        T_ = disp_case / (SEAWATER * L * B * cb)
        ws = [w for w in items if include_fuel or w.group not in ("fuel", "cargo")]
        kg = sum(w.w * w.z for w in ws) / sum(w.w for w in ws)
        kb = 0.53 * T_
        cw = cwp(cb)
        it = 0.0372 * (2 * cw + 1) ** 3 * L * B ** 3 / 12
        bm = it / (disp_case / SEAWATER)
        return kb + bm - kg

    res.gm_full = gm(full, True)
    res.gm_light = gm(std, False)       # fuel burnt (and cargo out), no ballast

    # --- longitudinal balance ---
    res.lcg = sum(w.w * w.x for w in items) / full
    res.lcb = tun["lcb_frac"] * L
    cw = cwp(cb)
    bml = 0.0743 * cw ** 2 * L ** 2 / (cb * res.draught)
    res.trim_m = (res.lcg - res.lcb) * L / bml  # + = down by the bow

    # --- checks ---
    TB = res.draught / B
    tb_max = tun.get("tb_max", 0.48)
    if TB > tb_max:
        res.errors.append(f"Hull overloaded: draught {res.draught:.1f} m is {TB:.2f} x beam (max {tb_max}). "
                          "Widen or lengthen the hull, or carry less.")
    elif TB > tb_max - 0.08:
        res.warnings.append(f"Deep draught ({res.draught:.1f} m, {TB:.2f} x beam): the hull is heavily loaded.")
    if L / B < tun.get("lb_warn", 4.5):
        res.warnings.append(f"Very beamy hull (L/B {L / B:.1f}): hard to drive, needs a lot of power.")
    if L / B > 12:
        res.warnings.append(f"Very slender hull (L/B {L / B:.1f}): weak structure and poor stability.")
    gmin = res.gm_full
    if gmin <= 0:
        res.errors.append(f"Unstable: GM {gmin:.2f} m. The ship would capsize. Lower the weight high up or widen the hull.")
    elif gmin < 0.035 * B:
        res.warnings.append(f"Top-heavy: GM {gmin:.2f} m (want at least {0.035 * B:.2f} m).")
    if res.gm_light <= 0 < gmin:
        res.warnings.append(f"Needs water ballast when low on fuel (light-condition GM {res.gm_light:.2f} m).")
    if res.gm_full > tun.get("gm_stiff_frac", 0.15) * B:
        res.warnings.append(f"Very stiff: GM {res.gm_full:.2f} m. Snappy roll, poor gun platform.")
    trim_tol = tun.get("trim_tol_frac", 0.01)
    if abs(res.trim_m) > trim_tol * L:
        res.errors.append(f"Badly out of trim: {abs(res.trim_m):.1f} m by the {'bow' if res.trim_m > 0 else 'stern'}.")
    elif abs(res.trim_m) > tun.get("trim_warn_frac", 0.004) * L:
        res.warnings.append(f"Trimmed {abs(res.trim_m):.1f} m by the {'bow' if res.trim_m > 0 else 'stern'}.")
    fn = froude(V, L)
    res.warnings += style.checks(design, res, tun)
    if fn > tun.get("fn_warn", 0.62):
        res.warnings.append(f"Speed {V} kn is extreme for a {L:.0f} m hull (Froude {fn:.2f}); power is enormous.")
    return res


def armour_weights(design, L, B, T, D, geo):
    a = design.get("armour", {})
    belt, deck = a.get("belt_mm", 0), a.get("deck_mm", 0)
    cx0, cx1 = geo.get("citadel", (-0.3 * L, 0.3 * L))
    lc = cx1 - cx0
    xc = (cx0 + cx1) / 2
    out = []
    if belt > 0:
        h = TUNING["belt_h_a"] * T + TUNING["belt_h_b"]
        out.append(Weight("Belt armour", "armour", 2 * lc * h * belt / 1000 * STEEL, x=xc,
                          z_rel=("frac", T / D if D else 0.5)))
        out.append(Weight("Bulkheads", "armour", 2 * B * h * 1.4 * 0.6 * belt / 1000 * STEEL, x=xc,
                          z_rel=("frac", 0.5)))
    if deck > 0:
        out.append(Weight("Deck armour", "armour", lc * B * 0.9 * deck / 1000 * STEEL, x=xc,
                          z_rel=("deck", -2.5)))
    return out


def rough_payload(design, D):
    """First-pass armament estimate before the layout exists (all at x=0)."""
    from geometry import make_turret_type, make_torpedo_type
    out = []
    a = design.get("armour", {})
    m = design.get("main")
    if m:
        _, t = make_turret_type(m["calibre_mm"], m["calibre_length"], m["barrels"])
        n = m.get("fore", 0) + m.get("aft", 0) + m.get("mid", 0) + 2 * m.get("wing", 0)
        tw, bw, aw = mount_weights(t, a.get("turret_mm", 0), D, 0)
        out.append(Weight("Main battery", "armament", n * tw, z_rel=("deck", 2)))
        out.append(Weight("Main barbettes", "armour", n * bw, z_rel=("frac", 0.75)))
        out.append(Weight("Main magazines", "armament", n * aw, z_rel=("frac", 0.25)))
    secs = design.get("secondary") or []
    for s in (secs if isinstance(secs, list) else [secs]):   # one battery, or a list (carriers, merchants)
        n = s.get("count", 2 * s.get("per_side", 0))
        if not n:
            continue
        _, t = make_turret_type(s["calibre_mm"], s["calibre_length"], s["barrels"])
        tw, bw, aw = mount_weights(t, s.get("armour_mm", 25), D, 0)
        out.append(Weight("Secondary battery", "armament", n * (tw + aw), z_rel=("deck", 2)))
    tp = design.get("torpedoes")
    if tp and tp.get("mounts", 0):
        out.append(Weight("Torpedoes", "armament", tp["mounts"] * torpedo_weight(tp["tubes"]), z_rel=("deck", 1)))
    aa = design.get("aa", {})
    w = aa.get("heavy", 0) * TUNING["aa_t"]["quad40"] + aa.get("light", 0) * TUNING["aa_t"]["single20"]
    if w:
        out.append(Weight("AA guns", "armament", w, z_rel=("deck", 2)))
    out.append(Weight("Superstructure", "superstructure", 0.012 * design["hull"]["length"] ** 2, z_rel=("deck", 4)))
    return out
