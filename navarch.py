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

from armour import armour_checks, armour_geometry, armour_weights
from decks import MIN_TIER
from geometry import DECK_PITCH, cwp, has_barbette, superfire_step
import hullweight
import powerplant
from weights import SEAWATER, STEEL, Weight

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
                            # averages this x the battery's armour_mm over the gunhouse
    shell_k=1.83e-5,        # shell kg = shell_k * cal_mm^3
    ammo_mult=1.6,          # shell + propellant + handling gear
    rounds=((127, 350), (152, 200), (203, 100)),   # rounds per gun at these calibres (mm): one curve through them,
                            # log-log between them and flat beyond (rounds_per_gun)
    mount_fixed_t=4.0,      # a mount's fixed gear (training gear, shield, platform) at 76 mm and up, falling with
                            # the cube below: light mounts weigh more than mount_k x their guns
    torp_mount_t=5.0, torp_tube_t=3.0, torp_t=1.6, torp_fixed_tube_t=1.0,
    aa_t={"quad40": 15.0, "twin40": 7.0, "single20": 1.0},
    lcb_frac=-0.012,        # longitudinal centre of buoyancy, fraction of L (negative = aft)
    planing_rw=0.13,        # planing placeholder: resistance/weight once planing ...
    planing_rw_disp=0.06,   # ... and at Fn∇ = 1
    planing_eta=0.5,        # propulsive efficiency
)


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
    """Rounds carried per gun: TUNING["rounds"] joined in log-log (a power law between neighbouring points), flat
    beyond the ends. One curve, so a gun 1 mm heavier carries about as many rounds (no calibre classes)."""
    pts = TUNING["rounds"]
    if cal_mm <= pts[0][0]:
        return pts[0][1]
    for (c0, r0), (c1, r1) in zip(pts, pts[1:]):
        if cal_mm <= c1:
            return r0 * (r1 / r0) ** (math.log(cal_mm / c0) / math.log(c1 / c0))
    return pts[-1][1]


def gun_rounds(t):
    """Rounds per gun in the magazines for turret type t: the battery's rounds_per_gun input (geometry.battery_type),
    else the curve (rounds_per_gun). The player's trade of combat endurance against magazine weight and volume."""
    return t["rounds_per_gun"] if "rounds_per_gun" in t else rounds_per_gun(t["calibre_mm"])


def mount_weights(t: dict, armour_mm: float, depth: float, level: int, deck: float = 0.0):
    """(turret incl. guns+armour, barbette armour, magazine/ammo) for one mount of type t. deck: the height of the
    weather deck it stands on above the main deck (a raised stretch: its barbette runs up through it)."""
    cal, cl, n, r = t["calibre_mm"], t["calibre_length"], t["barrels"], t["r"]
    guns = n * gun_tube_t(cal, cl)
    mech = TUNING["mount_k"] * guns + TUNING["mount_fixed_t"] * min(1.0, (cal / 76.0) ** 3)
    th = 0.42 * r
    area = 2 * math.pi * 0.9 * r * th + 0.85 * math.pi * r * r
    t_avg = TUNING["turret_t_avg"] * armour_mm / 1000.0
    turret = guns + mech + area * t_avg * STEEL
    # barbette: from the armour deck up to the turret base (superfiring turrets are taller)
    bh = 0.45 * depth + deck + level * superfire_step(th)
    barbette = 2 * math.pi * 0.95 * r * bh * (0.8 * armour_mm / 1000.0) * STEEL if has_barbette(t) else 0.0
    ammo = n * gun_rounds(t) * TUNING["shell_k"] * cal ** 3 / 1000.0 * TUNING["ammo_mult"]
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
            # a box-model hull (planing craft) has no plate model: its own gauge is the style's (plate_own_mm)
            plank = tun.get("plate_own_mm", 0.0)
            shell_t = hullweight.extra_plate_t(2 * hullweight.SHELL_SIDE * D * L,
                                               hullweight.plating(design)["shell_mm"], plank)
            hull = dict(t=tun["hull_k"] * (L * B * D) ** tun["hull_exp"] + shell_t, shell_t=shell_t,
                        plate_own_mm=plank)
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
        wood = hullweight.plating(design)["deck_wood_mm"]
        if wood:    # planking on the weather deck: a fire load, and weight high up
            area, wx, wz = style.weather_deck(design, L, B)
            items.append(Weight("Deck planking", "hull", area * wood * hullweight.RHO_WOOD, x=wx,
                                z_rel=("deck", wz)))
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
    res.warnings += armour_checks(design, L, res, geo)
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


def hydrostatics(form, res):
    """The full-load hydrostatics a game needs to settle, trim and heel a flooded ship by added weight: sinkage
    = w / (100 tpc_t) m, trim = w (x - lcf) / (100 mct_tm) cm (+ down by the bow), heel = w y / (Δ gm_t) rad.
    Heights above the main deck. gm_t is the report's (navarch's estimate); gm_l comes from the hull form's
    waterplane with navarch's kb and kg."""
    L, D, T, disp = form.hull.L, res.depth, res.draught, res.full
    area, lcf, i_l, i_t = form.waterplane()
    vol = disp / SEAWATER
    kg = sum(w.w * w.z for w in res.weights) / sum(w.w for w in res.weights)
    kb = 0.53 * T
    gm_l = kb + i_l / vol - kg
    return dict(displacement_t=round(disp), volume_m3=round(vol), waterplane_m2=round(area, 1),
                lcf=round(lcf, 3), lcg=round(res.lcg, 3), lcb=round(res.lcb, 3), kg=round(kg - D, 2),
                kb=round(kb - D, 2), gm_t=round(res.gm_full, 3), gm_l=round(gm_l, 1),
                i_t_m4=round(i_t), i_l_m4=round(i_l), tpc_t=round(SEAWATER * area / 100, 2),
                mct_tm=round(disp * gm_l / (100 * L), 1))


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
    # side armour stands in for the shell's extra plating (hull.plating.shell_mm) where it covers the side
    side_arm = sum((s["x1"] - s["x0"]) * (s["top"] - s["bottom"]) for s in arm["strakes"] if s["kind"] != "box")
    if arm["belt_mm"] > 0:
        side_arm += (arm["x1"] - arm["x0"]) * (arm["belt_top"] - arm["belt_bottom"])
    out = hullweight.weight(L, B, depth, cb, full, hullweight.construction(design), n_int, inner, plates,
                            bulkhead_depth=D, girder_depth=depth + rh if rh else None,
                            shell_mm=hullweight.plating(design)["shell_mm"], armoured_side_m2=2 * max(0.0, side_arm))
    return {**out, "depth_m": depth}


def main_batteries(design):
    """The main batteries, in the design's order: "main" is a list of batteries (one object is taken as a list of
    one). Each has its turret (calibre_mm, calibre_length, barrels, armour_mm, optional material) and where its
    turrets stand: fore, aft, mid, wing (pairs) and the placement choices (superfire, echelon, cross_deck,
    amidships_stands_on). The layout puts every battery's turrets in the same groups, in list order (layout.py)."""
    m = design.get("main")
    return [b for b in (m if isinstance(m, list) else [m] if m else []) if isinstance(b, dict) and b]


def secondary_batteries(design):
    """The secondary batteries, in the design's order: "secondary" is one battery or a list (a lone object is a list
    of one). Each gives its mounts as "count" (total) or "per_side" (validation rejects both); both come back filled
    in: count = 2 x per_side, or per_side = count // 2 (a style that mounts its secondaries in pairs leaves an odd one
    out, with a warning: armament.warn_unpaired). Batteries without mounts stay, so list positions name them
    (layout.battery_prefix)."""
    s = design.get("secondary")
    out = []
    for b in (s if isinstance(s, list) else [s] if s else []):
        n = b["count"] if "count" in b else 2 * b.get("per_side", 0)
        out.append({**b, "count": n, "per_side": b.get("per_side", n // 2)})
    return out


def battery_turrets(b):
    """How many turrets a main battery has: its end, midships and wing turrets (two to a pair)."""
    return b.get("fore", 0) + b.get("aft", 0) + b.get("mid", 0) + 2 * b.get("wing", 0)


def rough_payload(design, D):
    """First-pass armament estimate before the layout exists (all at x=0)."""
    from geometry import battery_type, make_torpedo_type
    out = []
    for k, m in enumerate(main_batteries(design)):
        _, t = battery_type(m)
        n = battery_turrets(m)
        tw, bw, aw = mount_weights(t, m.get("armour_mm", 0), D, 0)
        sfx = f" {k + 1}" if k else ""
        out.append(Weight("Main battery" + sfx, "armament", n * tw, z_rel=("deck", 2)))
        out.append(Weight("Main barbettes" + sfx, "armour", n * bw, z_rel=("frac", 0.75)))
        out.append(Weight("Main magazines" + sfx, "armament", n * aw, z_rel=("frac", 0.25)))
    for s in secondary_batteries(design):
        n = s["count"]
        if not n:
            continue
        _, t = battery_type(s)
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
