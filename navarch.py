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

from geometry import DECK_PITCH, superfire_step
import hullweight
import powerplant

STEEL = 7.85  # t/m^3
SEAWATER = 1.025  # t/m^3
OVERLOAD_TB = 3.0  # solve() gives up once the draught passes this x beam and still grows (overloaded from 0.48)

TUNING = dict(
    hull_k=0.112,           # styles with hull_model "box" (planing craft): structure = hull_k * (L*B*D)^hull_exp;
    hull_exp=1.0,           # the rest weigh their plating (hull_structure)
    freeboard_a=0.018,      # design freeboard = a*L + b
    freeboard_b=1.5,
    admiralty_a=111.0,      # admiralty coefficient C = a * Fn^-b * (form corrections)
    admiralty_b=0.69,
    cruise_kn=15.0,         # range is at min(cruise_kn, 0.6 x speed); the plant (powerplant.py) sets weight and fuel
    misc_frac=0.055,        # equipment, outfit and electrics, as a fraction of std displacement (crew, provisions
                            # and water are weighed by crew.py)
    superstructure_t_per_m2=0.32,
    gun_k=1.9e-6,           # gun mass (with breech) t = gun_k * cal_mm^3 * (L/50): 38 cm/52 108 t (real 111 t)
    mount_k=2.2,            # turret machinery and structure = mount_k * guns. With turret_t_avg: Bismarck's twin
    turret_t_avg=0.65,      # 38 cm 994 t (real 1,056 t), Iowa's triple 16" 1,860 t (about 1,700 t); turret armour
                            # averages this x turret_mm over the gunhouse
    tds_mm_per_m=12.0,      # torpedo protection: longitudinal bulkheads totalling this many mm per metre of
                            # armour.tds_m, each side over the citadel, inner bottom to the roof deck (Bismarck
                            # 45 mm torpedo bulkhead plus thinner ones, 5.5 m deep; Iowa four bulkheads, 5.2 m)
    shell_k=1.83e-5,        # shell kg = shell_k * cal_mm^3
    ammo_mult=1.6,          # shell + propellant + handling gear
    rounds_heavy=100, rounds_medium=200, rounds_light=350,
    torp_mount_t=5.0, torp_tube_t=3.0, torp_t=1.6, torp_fixed_tube_t=1.0,
    aa_t={"quad40": 15.0, "twin40": 7.0, "single20": 1.0},
    belt_h_a=0.30, belt_h_b=2.4,   # belt height = a*T + b, half below the waterline (when the design gives none)
    lcb_frac=-0.012,        # longitudinal centre of buoyancy, fraction of L (negative = aft)
    planing_rw=0.13,        # planing placeholder: resistance/weight once planing ...
    planing_rw_disp=0.06,   # ... and at Fn∇ = 1
    planing_eta=0.5,        # propulsive efficiency
)


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
    cruise_kn: float = 0.0     # range is computed at this speed
    plant: dict = field(default_factory=dict)       # powerplant.spec of the design
    plant_rated: dict = field(default_factory=dict)  # powerplant.rated at power_shp
    hull: dict = field(default_factory=dict)         # hullweight.weight: the structure and its hull girder
    gm_full: float = 0.0
    gm_light: float = 0.0
    roll_s: float = 0.0        # natural roll period at full load
    wind: dict = field(default_factory=dict)   # beam-wind heel (wind_heel)
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


def mount_weights(t: dict, armour_mm: float, depth: float, level: int, deck: float = 0.0):
    """(turret incl. guns+armour, barbette armour, magazine/ammo) for one mount of type t. deck: the height of the
    weather deck it stands on above the main deck (a raised stretch: its barbette runs up through it)."""
    cal, cl, n, r = t["calibre_mm"], t["calibre_length"], t["barrels"], t["r"]
    guns = n * gun_tube_t(cal, cl)
    mech = TUNING["mount_k"] * guns + (4.0 * min(1.0, (cal / 76.0) ** 3) if cal < 150 else 0.0)
    th = 0.42 * r
    area = 2 * math.pi * 0.9 * r * th + 0.85 * math.pi * r * r
    t_avg = TUNING["turret_t_avg"] * armour_mm / 1000.0
    turret = guns + mech + area * t_avg * STEEL
    # barbette: from the armour deck up to the turret base (superfiring turrets are taller)
    bh = 0.45 * depth + deck + level * superfire_step(th)
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


def design_freeboard(L, tun=TUNING):
    """The style's standard freeboard at full load for an ocean-going hull; hull.freeboard scales it."""
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
    plant = powerplant.spec(design, style.DEFAULT_TECH)
    L = design["hull"]["length"]
    B = design["hull"]["beam"]
    cb = design["hull"]["block_coefficient"]
    V = design["speed_kn"]
    rng = design.get("range_nm", 6000)
    geo = geo or {}
    res = Result()

    disp = 200.0 * L * B * cb * 0.04  # initial guess
    own = [Weight(**w.__dict__) for w in placed] if placed is not None else None   # z is set on these below
    for _ in range(60):
        T = disp / (SEAWATER * L * B * cb)
        D = T + design_freeboard(L, tun) * design["hull"].get("freeboard", 1.0)
        items: list[Weight] = []
        arm = armour_geometry(design, L, T, D, geo)
        if tun.get("hull_model") == "box":
            hull = dict(t=tun["hull_k"] * (L * B * D) ** tun["hull_exp"])
        else:
            hull = hull_structure(design, L, B, cb, D, disp, arm, style.strength_deck(design, D),
                                  geo.get("raised", ()))
        z_frac = tun.get("hull_z_frac", 0.58) * (hull.get("depth_m", D) / D)
        items.append(Weight("Hull structure", "hull", hull["t"], x=-0.01 * L, z_rel=("frac", z_frac)))
        shp = power_required(disp, V, L, B, cb, tun)
        items.append(Weight("Machinery", "machinery", powerplant.rated(plant, shp)["weight_t"],
                            x=geo.get("machinery_x", -0.02 * L), z_rel=("frac", 0.32)))
        if placed is None:
            items += rough_payload(design, D) + style.rough_payload(design, D)
        else:
            items += own
        # armour that depends on draught / depth
        items += armour_weights(design, L, B, D, arm)
        items += style.structure_weights(design, L, B, T, D, geo, tun)
        std_wo_misc = sum(w.w for w in items)
        std = std_wo_misc / (1 - tun["misc_frac"])
        items.append(Weight("Equipment, outfit, crew & stores", "misc", std - std_wo_misc, x=0.0,
                            z_rel=("frac", 0.5)))
        # fuel for the requested range at cruise speed (merchants cruise at their service speed)
        vc = V if tun.get("cruise_at_service") else min(tun["cruise_kn"], 0.6 * V)
        shp_c = power_required(disp, vc, L, B, cb, tun)
        fuel = powerplant.fuel_rate(plant, shp, shp_c) * (rng / vc) / 1000.0
        std_load, full_load = style.payload_weights(design, L, D, geo, tun, dict(
            items=items, fuel=fuel, fuel_x=geo.get("machinery_x", -0.02 * L), lcb=tun["lcb_frac"] * L))
        std += sum(w.w for w in std_load)
        full = std + fuel + sum(w.w for w in full_load)
        if abs(full - disp) < 0.5:
            disp = full
            break
        if not math.isfinite(full) or full > disp and full / (SEAWATER * L * B * cb) > OVERLOAD_TB * B:
            # Still growing past any ship: on a hull this narrow, each tonne sinks it deeper, which deepens the hull
            # and adds more than a tonne. Iterating on, the depth runs to kilometres (and the deck stack with it).
            res.errors.append(f"The weights never settle on a {B:.1f} m beam: the ship sinks deeper with every "
                              "tonne it carries. A wider hull, or less armour or armament, would help.")
            break
        disp = 0.5 * disp + 0.5 * full
    else:   # every tonne added needs more hull to float it, which adds more tonnes: no design exists
        res.errors.append(f"The weights never settle: the ship needs a bigger hull to carry its load, which "
                          f"needs a bigger hull again (still growing at {full:,.0f} t). Lighten the armour or "
                          "armament.")

    items += std_load
    items.append(Weight("Fuel", "fuel", fuel, x=geo.get("machinery_x", -0.02 * L), z_rel=("frac", 0.18)))
    items += full_load
    for w in items:
        kind, v = w.z_rel
        w.z = v * D if kind == "frac" else D + v

    res.std, res.full, res.fuel = std, full, fuel
    res.draught, res.depth, res.freeboard = full / (SEAWATER * L * B * cb), D, D - full / (SEAWATER * L * B * cb)
    res.power_shp = shp
    res.cruise_kn = vc
    res.plant, res.plant_rated = plant, powerplant.rated(plant, shp)
    res.hull = hull
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
    res.roll_s = roll_period(L, B, res.draught, res.gm_full)
    res.wind = wind_heel(L, B, D, cb, full, std, res.gm_full, res.gm_light, geo.get("windage"))

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
                          "Carry less.")
    elif TB > tb_max - 0.08:
        res.warnings.append(f"Deep draught ({res.draught:.1f} m, {TB:.2f} x beam): the hull is heavily loaded.")
    if L / B < tun.get("lb_warn", 4.5):
        res.warnings.append(f"Very beamy hull (L/B {L / B:.1f}): hard to drive, needs a lot of power.")
    if L / B > 12:
        res.warnings.append(f"Very slender hull (L/B {L / B:.1f}): weak structure and poor stability.")
    gmin = res.gm_full
    if gmin <= 0:
        res.errors.append(f"Unstable: GM {gmin:.2f} m. The ship would capsize. Lower the weight high up.")
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
    w = res.wind
    if w and w["heel_deg"] > min(WIND_HEEL_WARN, 0.8 * w["deck_edge_deg"]):
        res.warnings.append(f"Heels {w['heel_deg']:.0f}° in a beam gale ({WIND_REF_MS:.0f} m/s, {w['condition']}): too "
                            f"much windage for its stability. The deck edge goes under at {w['deck_edge_deg']:.0f}°, "
                            f"in a {w['deck_edge_wind_kn']:.0f} kn wind.")
    fn = froude(V, L)
    res.warnings += style.checks(design, res, tun)
    for d in armour_decks(design, res.depth, geo.get("raised", ())):
        if d["asked"] != d["deck"]:
            res.warnings.append(f"The hull has no {deck_name(d['asked']).lower()} ({res.depth:.1f} m deep): its "
                                f"{d['mm']} mm deck armour lies on the {deck_name(d['deck']).lower()}.")
    arm = design.get("armour") or {}
    if arm.get("belt_mm", 0) > 0 and arm.get("belt_depth_m", 1.0) < 1.0:
        res.warnings.append(f"The belt reaches only {arm['belt_depth_m']:.1f} m below the waterline: rolling or "
                            "flooding uncovers the side under it.")
    ub = (design.get("armour") or {}).get("upper_belt") or {}
    if ub.get("mm", 0) > 0 and not any(s["kind"] == "upper" for s in armour_geometry(
            design, L, res.draught, res.depth, geo)["strakes"]):
        res.warnings.append(f"The {ub['mm']} mm upper belt has no height: the belt below it already reaches the "
                            f"{deck_name(ub.get('to_deck', 0)).lower()}.")
    h = res.hull
    if h.get("strength_t", 0.0) > h.get("min_gauge_t", float("inf")):
        res.warnings.append(f"The hull is very long for its depth: {h['strength_t']:,.0f} t of its plating (strength "
                            f"deck and shell {h['t_str_mm']:.0f} mm, where {h['t_min_mm']:.0f} mm would do) only "
                            "keeps it from breaking in two. A shorter hull or an armour deck high in it would help.")
    if fn > tun.get("fn_warn", 0.62):
        res.warnings.append(f"Speed {V} kn is extreme for a {L:.0f} m hull (Froude {fn:.2f}); power is enormous.")
    return res


WIND_REF_MS = 26.0      # the beam gale for the heel check: the IMO weather criterion's 504 Pa
WIND_PA_K = 0.746       # wind pressure Pa = WIND_PA_K x (m/s)^2 on a ship's profile (504 Pa at 26 m/s)
WIND_HEEL_WARN = 16.0   # warn above this steady heel (degrees, IMO), or 0.8 of the deck-edge angle if that is less


def roll_period(L, B, T, gm):
    """Natural roll period, s (IMO: T = 2 C B / sqrt(GM), C = 0.373 + 0.023 B/T - 0.043 L/100). A stiff ship rolls
    quickly and snappily, a tender one slowly; the game decides what that does to its gunnery."""
    if gm <= 0 or T <= 0:
        return 0.0
    c = 0.373 + 0.023 * B / T - 0.043 * L / 100.0
    return 2.0 * c * B / math.sqrt(gm)


def wind_heel(L, B, D, cb, full, std, gm_full, gm_light, windage):
    """The steady heel a beam gale gives, at full load and light (fuel burnt: more freeboard, less weight), the worse
    of the two: the wind's heeling lever P A Z / (g disp) over GM, with A the side profile (the hull's freeboard plus
    the layout's windage) and Z from the middle of the draught to its centre. Also the deck-edge immersion angle and
    the wind that heels the ship that far. Only ever a warning: a player may build a ship that capsizes on a windy
    day."""
    if windage is None:
        return {}
    out = None
    for cond, disp, gm in (("full load", full, gm_full), ("light", std, gm_light)):
        T = disp / (SEAWATER * L * B * cb)
        fb = max(0.0, D - T)
        a_hull = 0.95 * L * fb
        area = a_hull + windage["area_m2"]
        z = (a_hull * (T + fb / 2) + windage["area_m2"] * (D + windage["z_m"])) / area if area else T
        arm = area * (z - T / 2) / (9.81 * disp * 1000.0)     # heeling lever, m per Pa of wind
        edge = math.degrees(math.atan2(fb, B / 2))
        heel = math.degrees(math.atan(WIND_PA_K * WIND_REF_MS ** 2 * arm / gm)) if gm > 0 else 90.0
        p_edge = math.tan(math.radians(edge)) * gm / arm if gm > 0 and arm > 0 else 0.0
        r = dict(condition=cond, heel_deg=heel, deck_edge_deg=edge,
                 deck_edge_wind_kn=math.sqrt(p_edge / WIND_PA_K) / 0.5144, area_m2=area)
        if out is None or heel > out["heel_deg"]:
            out = r
    return out


STACK_DECK = 0.6       # a level of the deck stack weighs this much of a full internal deck: many are platforms and
                       # flats (fitted so the stack reproduces the hull-weight research's calibration)
INNER_BOTTOM_T = (4000.0, 10000.0)  # full displacement (t) over which the inner bottom's weight comes in: escorts
                                    # are calibrated without one, cruisers and capital ships with one


GIRDER_MID = 0.2       # x L each side of amidships: raised hull over this midbody works in the girder (the classification
                       # societies' 0.4 L midship region), by its mean height over it


def raised_girder_h(raised, L):
    """The mean height of raised stretches of hull (dicts x0, x1, levels) over the midbody, |x| <= GIRDER_MID L:
    what they deepen the girder by. A long forecastle reaching well aft of amidships counts fully, a short one
    near the bow not at all, and it phases in smoothly as the break moves (the size search needs no steps)."""
    a, b = -GIRDER_MID * L, GIRDER_MID * L
    tot = 0.0
    for s in raised:   # raised_profile's stretches don't overlap
        tot += max(0.0, min(b, s["x1"]) - max(a, s["x0"])) * s["levels"] * DECK_PITCH
    return tot / (b - a)


def hull_structure(design, L, B, cb, D, full, arm, above=None, raised=()):
    """The hull's structure weight and girder (hullweight.weight). Internal decks come from the deck stack's depth
    and the inner bottom from the displacement, both smoothly (a step would make the solver and the size search
    jump); the armour-deck plates over amidships (arm: armour_geometry) count in the girder.
    above: the style's strength deck above the main deck (Style.strength_deck: a closed hangar's flight deck),
    dict(h, decks, plates), or None. The hull's sides then run up to it, the decks between count as full internal
    decks, and the plates on it count in the girder; the transverse bulkheads still stop at the main deck.
    raised: raised stretches of hull (lay.raised): over the midbody they deepen the girder (raised_girder_h)."""
    n_int = STACK_DECK * max(0.0, (D - powerplant.double_bottom(D) - MIN_TIER) / DECK_PITCH)
    lo, hi = INNER_BOTTOM_T
    inner = min(1.0, max(0.0, (full - lo) / (hi - lo)))
    plates = [(d["mm"], d["z"]) for d in arm["decks"] if d["x0"] <= 0.0 <= d["x1"]]
    depth = D
    if above:
        depth, n_int, plates = D + above["h"], n_int + above["decks"], plates + above["plates"]
    rh = raised_girder_h(raised, L) if raised else 0.0
    out = hullweight.weight(L, B, depth, cb, full, hullweight.construction(design), n_int, inner, plates,
                            bulkhead_depth=D, girder_depth=depth + rh if rh else None)
    return {**out, "depth_m": depth}


MIN_TIER = 1.0         # a deck closer than this (m) to the inner bottom (the keel on a planing craft) is left out
MAX_DECKS = 60         # a backstop, far past any ship (156 m deep): a runaway depth must not build decks without end
DECK_NAMES = ["Main deck", "Second deck", "Third deck", "Fourth deck", "Fifth deck", "Sixth deck", "Seventh deck",
              "Eighth deck", "Ninth deck", "Tenth deck"]
ARMOUR_EXTENTS = ("citadel", "full", "fore", "aft", "ends")
BELT_ENDS = ("fore", "aft")
STEERING = (0.03, 0.08, 0.25)   # the steering gear: from 0.03 to 0.08 L forward of the stern, 0.25 B each side


def steering_span(L, geo=None):
    """The steering gear's stretch (x0, x1): the layout's (geo["steering"]) or the rule's (STEERING)."""
    return (geo or {}).get("steering") or (-L / 2 + STEERING[0] * L, -L / 2 + STEERING[1] * L)


def deck_name(n):
    """A deck's name by its number: 0 the main deck, 1, 2, ... down the stack; -1, -2, ... the decks of raised
    stretches of hull above it (forecastle, poop). The game's designer may give them period names."""
    if n < 0:
        return f"Raised deck {-n}"
    return DECK_NAMES[n] if n < len(DECK_NAMES) else f"Deck {n + 1}"


def deck_stack(design, D):
    """The hull's decks, every DECK_PITCH down from the main deck, as heights above the keel, top down:
    [(n, z)] with n = 0 the main deck, 1 the second deck, ... Stops MIN_TIER above the inner bottom (the keel on
    a planing craft); the main deck is always there."""
    floor = 0.0 if design.get("style") == "planing" else powerplant.double_bottom(D)
    out = [(0, D)]
    while D - len(out) * DECK_PITCH >= floor + MIN_TIER - 1e-9 and len(out) <= MAX_DECKS:
        out.append((len(out), D - len(out) * DECK_PITCH))
    return out


ARMOUR_PARTS = ("belt", "upper_belt", "end_belts", "bulkheads", "decks", "turrets", "barbettes", "conning_tower",
                "secondary", "flight_deck")


def armour_material(design, part, own=None):
    """The armour material named for a part (armour.materials[part]; a deck or battery may give its own): a
    plain string passed through to the hitboxes for the game's ballistics, or None if the design names none."""
    return own.get("material") if own and own.get("material") else (
        ((design.get("armour") or {}).get("materials") or {}).get(part))


def armour_decks(design, D, raised=()):
    """The design's armour decks (armour.decks, top down), placed on the deck stack: [dict(deck, mm, extent, z,
    asked, material)]. A deck the hull is too shallow for lies on its lowest deck, and a raised deck (-1, -2, ...)
    higher than any raised stretch (raised: lay.raised) on the highest there is, or the main deck (asked keeps what
    the design said). A raised deck's plates exist only over its stretches (armour_geometry)."""
    stack = deck_stack(design, D)
    top = -max((s["levels"] for s in raised), default=0)
    out = []
    for d in (design.get("armour") or {}).get("decks") or []:
        n = max(top, min(int(d.get("deck", 0)), stack[-1][0]))
        out.append(dict(deck=n, mm=d.get("mm", 0), extent=d.get("extent", "citadel"),
                        z=stack[n][1] if n >= 0 else D - n * DECK_PITCH,
                        asked=int(d.get("deck", 0)), material=armour_material(design, "decks", d)))
    return out


def raised_pieces(raised, s0, s1, k):
    """The stretch s0..s1 split where raised stretches (dicts x0, x1, levels) step: [(x0, x1, levels)], each with
    the raised decks over it, at most k."""
    xs = sorted({s0, s1} | {x for r in raised for x in (r["x0"], r["x1"]) if s0 < x < s1})
    out = []
    for a, b in zip(xs, xs[1:]):
        m = (a + b) / 2
        lv = min(k, max((r["levels"] for r in raised if r["x0"] <= m <= r["x1"]), default=0))
        if out and out[-1][2] == lv:
            out[-1] = (out[-1][0], b, lv)
        else:
            out.append((a, b, lv))
    return out


def extent_spans(extent, L, x0, x1):
    """An armour extent as [(extent, x0, x1)] pieces: the citadel, the whole hull, or the hull beyond either
    end of the citadel ("ends" is both)."""
    return {"citadel": [("citadel", x0, x1)], "full": [("full", -L / 2, L / 2)],
            "fore": [("fore", x1, L / 2)], "aft": [("aft", -L / 2, x0)],
            "ends": [("fore", x1, L / 2), ("aft", -L / 2, x0)]}[extent]


def belt_mm_at(s, x, z=None):
    """A belt's thickness at x (and height z, on the same scale as its bottom): mm at its root (the citadel end),
    tapering linearly to tip_mm at the hull's end. A belt with bottom_mm (the main belt) keeps its thickness down
    to the waterline (wl), then tapers linearly to bottom_mm at its lower edge."""
    mm = s["mm"]
    if s["tip_mm"] != mm and s["x1"] - s["x0"] > 0:
        f = (x - s["x0"]) / (s["x1"] - s["x0"])
        if s["extent"] == "aft":
            f = 1.0 - f
        mm += (s["tip_mm"] - mm) * min(1.0, max(0.0, f))
    if z is not None and s.get("bottom_mm", mm) != mm and z < s["wl"] and s["wl"] > s["bottom"]:
        f = max(0.0, (z - s["bottom"]) / (s["wl"] - s["bottom"]))
        mm = s["bottom_mm"] + (mm - s["bottom_mm"]) * f
    return mm


def armour_geometry(design, L, T, D, geo):
    """Where the armour is: the one source for its weights and its hitboxes. Heights in metres above the keel.
      decks     the armour decks (armour_decks) as plates over their x extents: the citadel, the whole hull
                ("full"), or the hull beyond the citadel's fore or aft end ("ends" is a plate at each end)
      main      the main armour deck: the thickest over the citadel (the higher of equals), or None
      roof      the lowest armour deck over the citadel: the machinery and magazines stand under it (None if none)
      belt      the main belt over the citadel, armour.belt_mm thick down to the waterline, then tapering to
                armour.belt_bottom_mm at its lower edge: from armour.belt_depth_m below the full-load waterline to
                armour.belt_height_m above it, or up to the main armour deck when that is higher (kept between
                keel and main deck; TUNING belt_h, half below and half above, when the design gives none)
      strakes   the rest of the side armour, each dict(id, kind, extent, mm, tip_mm, x0, x1, bottom, top,
                material):
                  end    armour.end_belts: the waterline belt carried on from the citadel toward the stem ("fore")
                         or stern ("aft"), reach of the way there (1: all the way), at the main belt's depth, up
                         to the thickest armour deck over that end when that is higher; mm at the citadel
                         tapering to tip_mm at its far end
                  upper  armour.upper_belt: from the top of the belt below it up to armour.upper_belt.to_deck,
                         over its extent (one strake per stretch: the citadel, fore and aft)
                  box    armour.steering_box: the sides of a separate box round the steering gear (steering_span),
                         from the inner bottom (the gear stands low) up to its roof, the deck over the gear
      bulkheads the citadel's transverse bulkheads (armour.bulkhead_mm, 0.6 of the belt if not given) close the
                belts' ends, from the top of the main or upper belt over the citadel down to 0.4 belt heights
                below the belt.
      end_bulkheads  the other armoured transverse bulkheads, each dict(id, x, mm, bottom, top, material): one
                closing an end belt that stops short of the hull's end (its bulkhead_mm), from the citadel
                bulkheads' lower edge up to the belt's top, and the steering box's two ends
                (steering_box.bulkhead_mm), as tall as its sides. The box's roof is a deck plate (extent
                "steering") on the deck over the steering gear (ordnance.span, as layout.add_steering stands it). The
                box's roof and bulkheads span the hull's width there (geo["steering_beam"]; the beam without one).
      materials armour.materials, by part (armour_material): belt_material, bulkhead_material, roof_material,
                and material on each deck plate and strake. Strings only, for the game's ballistics."""
    a = design.get("armour") or {}
    belt = a.get("belt_mm", 0)
    x0, x1 = geo.get("citadel", (-0.3 * L, 0.3 * L))
    raised = geo.get("raised", ())
    decks = []
    for d in armour_decks(design, D, raised):
        if d["mm"] <= 0:
            continue
        spans = extent_spans(d["extent"], L, x0, x1)
        if d["deck"] < 0:     # a raised deck: only over its stretches
            spans = [(ext, a_, b_) for ext, s0, s1 in spans for a_, b_, lv in raised_pieces(raised, s0, s1, -d["deck"])
                     if lv >= -d["deck"]]
        for ext, p0, p1 in spans:
            # pushed onto one deck by a shallow hull: overlapping plates make one
            p = next((p for p in decks if p["deck"] == d["deck"] and min(p["x1"], p1) - max(p["x0"], p0) > 1e-6),
                     None)
            if p:
                p.update(mm=p["mm"] + d["mm"], x0=min(p["x0"], p0), x1=max(p["x1"], p1),
                         extent="full" if "full" in (p["extent"], ext) else p["extent"],
                         material=p["material"] if d["material"] in (None, p["material"]) else
                         d["material"] if p["material"] is None else f"{p['material']} + {d['material']}")
                continue
            decks.append({**d, "extent": ext, "x0": p0, "x1": p1})
    over = [d for d in decks if d["extent"] in ("citadel", "full") and d["deck"] >= 0]  # the stack's plates over the
                                                                                        # citadel
    main = max(over, key=lambda d: (d["mm"], d["z"]), default=None)
    roof = min(over, key=lambda d: d["z"], default=None)
    h0 = TUNING["belt_h_a"] * T + TUNING["belt_h_b"]
    below, above = a.get("belt_depth_m", h0 / 2), a.get("belt_height_m", h0 / 2)
    h = below + above
    bot = max(0.0, T - below)
    band = min(D, max(bot, T + above))
    top = min(D, max(band, main["z"] if main else 0.0))

    strakes, end_bhs = [], []
    bh_bot = max(0.0, bot - 0.4 * h)
    tops = {"citadel": top if belt > 0 else band}         # where an upper belt starts over each stretch
    for end in BELT_ENDS:
        e = (a.get("end_belts") or {}).get(end) or {}
        tops[end] = band
        if e.get("mm", 0) <= 0:
            continue
        _, s0, s1 = extent_spans(end, L, x0, x1)[0]
        reach = min(1.0, max(0.0, e.get("reach", 1.0)))
        if end == "fore":       # reach of the way from the citadel to the stem (stern)
            s1 = s0 + (s1 - s0) * reach
        else:
            s0 = s1 - (s1 - s0) * reach
        cover = [d for d in decks if d["x0"] <= (s0 + s1) / 2 <= d["x1"] and d["extent"] in (end, "full")]
        dk = max(cover, key=lambda d: (d["mm"], d["z"]), default=None)
        et = min(D, max(band, dk["z"] if dk else 0.0))
        tops[end] = et
        if s1 - s0 > 1e-6:
            strakes.append(dict(id=f"{end.capitalize()} end belt", kind="end", extent=end, mm=e["mm"],
                                tip_mm=e.get("tip_mm", e["mm"]), x0=s0, x1=s1, bottom=bot, top=et,
                                material=armour_material(design, "end_belts", e)))
            if reach < 1.0 and e.get("bulkhead_mm", 0) > 0:     # closing the belt where it stops short
                end_bhs.append(dict(id=f"{end.capitalize()} end belt bulkhead", x=s1 if end == "fore" else s0,
                                    mm=e["bulkhead_mm"], bottom=bh_bot, top=et,
                                    material=armour_material(design, "bulkheads")))
    sb = a.get("steering_box") or {}
    if max(sb.get("mm", 0), sb.get("deck_mm", 0), sb.get("bulkhead_mm", 0)) > 0:
        # a compact box round the steering gear, which stands low (layout.add_steering: ordnance.span over the inner
        # bottom): sides from the inner bottom to the deck over the gear, a roof on that deck, bulkheads at both ends
        import ordnance
        b0, b1 = steering_span(L, geo)
        stack = deck_stack(design, D)
        wbox = geo.get("steering_beam")
        rz_ = ordnance.span(dict(decks=[z for _, z in stack], inner_bottom=powerplant.double_bottom(D),
                                 top=roof["z"] if roof else D))[1] + D
        n = min(stack, key=lambda v: abs(v[1] - rz_))[0]
        if sb.get("deck_mm", 0) > 0:
            decks.append(dict(deck=n, mm=sb["deck_mm"], extent="steering", z=rz_, asked=n, x0=b0, x1=b1, w=wbox,
                              material=armour_material(design, "decks", sb.get("deck_material") and
                                                       {"material": sb["deck_material"]})))
        floor = min(powerplant.double_bottom(D), rz_)
        if sb.get("mm", 0) > 0:
            strakes.append(dict(id="Steering gear box", kind="box", extent="aft", mm=sb["mm"], tip_mm=sb["mm"],
                                x0=b0, x1=b1, bottom=floor, top=rz_,
                                material=armour_material(design, "end_belts", sb)))
        if sb.get("bulkhead_mm", 0) > 0:
            end_bhs += [dict(id=f"Steering gear box {w} bulkhead", x=x, mm=sb["bulkhead_mm"], bottom=floor,
                             top=rz_, w=wbox, material=armour_material(design, "bulkheads"))
                        for w, x in (("forward", b1), ("aft", b0))]
    ub = a.get("upper_belt") or {}
    if ub.get("mm", 0) > 0:
        stack = deck_stack(design, D)
        to = int(ub.get("to_deck", 0))
        ut = stack[min(max(to, 0), stack[-1][0])][1]
        pieces = extent_spans(ub.get("extent", "citadel"), L, x0, x1)
        if ub.get("extent") == "full":
            pieces = [("citadel", x0, x1), ("fore", x1, L / 2), ("aft", -L / 2, x0)]
        for ext, s0, s1 in pieces:
            # up to a raised deck (to_deck -1, -2, ...): to it over its stretches, to the main deck elsewhere
            parts = raised_pieces(raised, s0, s1, -to) if to < 0 else [(s0, s1, 0)]
            for k, (p0, p1, lv) in enumerate(parts):
                top_ = ut + lv * DECK_PITCH
                if top_ > tops[ext] + 0.05 and p1 - p0 > 1e-6:
                    sid = "Upper belt" if ext == "citadel" else f"Upper belt ({ext})"
                    strakes.append(dict(id=sid + (f" {k + 1}" if len(parts) > 1 else ""), kind="upper",
                                        extent=ext, mm=ub["mm"], tip_mm=ub["mm"], x0=p0, x1=p1, bottom=tops[ext],
                                        top=top_, material=armour_material(design, "upper_belt", ub)))
    bh_top = max([top] + [s["top"] for s in strakes if s["kind"] == "upper" and s["extent"] == "citadel"])
    return dict(x0=x0, x1=x1, belt_mm=belt, belt_bottom_mm=a.get("belt_bottom_mm", belt), waterline=T,
                belt_bottom=bot, belt_top=top, decks=decks, strakes=strakes,
                main_z=main["z"] if main else None, roof_z=roof["z"] if roof else None,
                roof_mm=roof["mm"] if roof else 0, roof_material=roof["material"] if roof else None,
                belt_material=armour_material(design, "belt"), bulkhead_material=armour_material(design, "bulkheads"),
                armoured=belt > 0 or bool(over),
                bulkhead_mm=a.get("bulkhead_mm", 0.6 * belt), bulkhead_bottom=bh_bot,
                bulkhead_top=bh_top, end_bulkheads=end_bhs)


def armour_weights(design, L, B, D, g):
    """The armour's weights from its geometry (armour_geometry)."""
    lc = g["x1"] - g["x0"]
    xc = (g["x0"] + g["x1"]) / 2
    zf = lambda lo, hi: ("frac", (lo + hi) / 2 / D if D else 0.5)
    out = []
    if g["belt_mm"] > 0:
        # full thickness above the waterline (t0 .. top), tapering to belt_bottom_mm below it (bot .. t0)
        bot, top, mm, mb = g["belt_bottom"], g["belt_top"], g["belt_mm"], g["belt_bottom_mm"]
        t0 = min(top, max(bot, g["waterline"]))
        a_up, a_lo = (top - t0) * mm, (t0 - bot) * (mm + mb) / 2           # m x mm per side
        z_lo = bot + (t0 - bot) * (mb + 2 * mm) / (3 * (mb + mm)) if mb + mm > 0 else bot
        zc = ((top + t0) / 2 * a_up + z_lo * a_lo) / (a_up + a_lo) if a_up + a_lo > 0 else (top + bot) / 2
        out.append(Weight("Belt armour", "armour", 2 * lc * (a_up + a_lo) / 1000 * STEEL, x=xc,
                          z_rel=("frac", zc / D if D else 0.5)))
    if g["armoured"] and g["bulkhead_mm"] > 0:
        hb = g["bulkhead_top"] - g["bulkhead_bottom"]
        out.append(Weight("Bulkheads", "armour", 2 * B * hb * g["bulkhead_mm"] / 1000 * STEEL, x=xc,
                          z_rel=zf(g["bulkhead_top"], g["bulkhead_bottom"])))
    for b in g["end_bulkheads"]:      # across the hull there (an end belt's: the beam, a little heavy at the ends)
        out.append(Weight(b["id"], "armour", (b.get("w") or B) * (b["top"] - b["bottom"]) * b["mm"] / 1000 * STEEL,
                          x=b["x"],
                          z_rel=zf(b["top"], b["bottom"])))
    for s in g["strakes"]:
        a, b = (s["mm"], s["tip_mm"]) if s["extent"] != "aft" else (s["tip_mm"], s["mm"])   # thickness at x0, x1
        f = (a + 2 * b) / (3 * (a + b)) if a + b > 0 else 0.5                             # trapezoid centroid
        out.append(Weight(s["id"], "armour", 2 * (s["x1"] - s["x0"]) * (s["top"] - s["bottom"]) * (a + b) / 2
                          / 1000 * STEEL, x=s["x0"] + f * (s["x1"] - s["x0"]), z_rel=zf(s["top"], s["bottom"])))
    tds = (design.get("armour") or {}).get("tds_m", 0.0)
    if tds > 0 and lc > 0:
        floor = powerplant.double_bottom(D)
        top = g["roof_z"] if g["roof_z"] is not None else g["waterline"]
        mm = TUNING["tds_mm_per_m"] * tds
        out.append(Weight("Torpedo protection", "armour", 2 * lc * max(0.0, top - floor) * mm / 1000 * STEEL, x=xc,
                          z_rel=zf(top, floor)))
    cb = design["hull"]["block_coefficient"]
    for d in g["decks"]:
        area = (L * cwp(cb) if d["extent"] == "full" else d["x1"] - d["x0"]) * (d.get("w") or B) * 0.9
        name = f"Deck armour ({deck_name(d['deck']).lower()}" + (
            f", {d['extent']})" if d["extent"] in BELT_ENDS + ("steering",) else ")")
        out.append(Weight(name, "armour", area * d["mm"] / 1000 * STEEL,
                          x=0.0 if d["extent"] == "full" else (d["x0"] + d["x1"]) / 2, z_rel=("deck", d["z"] - D)))
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
