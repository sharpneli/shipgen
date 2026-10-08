"""
navarch — "naval architecture lite" weight, power and stability model.

The player never enters tonnage. Displacement is whatever the ship needs to carry its hull,
machinery, fuel, armour and armament. Some of those depend on displacement themselves
(power ~ displacement^2/3, hull depth ~ draught), so solve() iterates to a fixed point.

This module is the solver and the power model only. Each weight comes from the module that owns its subject, and
each keeps its own constants in its own TUNING:
    hullweight   hull structure (plate model, girder, deck stack and inner bottom)
    armour       armour geometry, weights, materials, input checks and warnings
    batteries    guns, mounts, magazines' loads, torpedoes, AA; the battery readers
    powerplant   machinery weight and fuel rate
    styles/      style-specific structure and payload (Style.structure_weights, payload_weights)
    stability    GM, roll, wind heel, trim, hydrostatics and their warnings, once the weights are settled
TUNING here holds the hull form, power, misc and limit constants; a style overrides them with Style.tuning().
Calibrated loosely against real ships (calibrate.py). Treat it as plausible game physics, not a design tool.

Units: metres, tonnes (metric), knots, shp, mm of armour.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from armour import armour_checks, armour_geometry, armour_weights
from batteries import rough_armament
import hullweight
import powerplant
import stability
from weights import SEAWATER, Weight

OVERLOAD_TB = 3.0  # solve() gives up once the draught passes this x beam and still grows (overloaded from 0.48)

TUNING = dict(
    hull_k=0.112,           # styles with hull_model "box" (planing craft): structure = hull_k * (L*B*D)^hull_exp;
    hull_exp=1.0,           # the rest weigh their plating (hullweight.hull_structure)
    freeboard_a=0.018,      # design freeboard = a*L + b
    freeboard_b=1.5,
    admiralty_a=111.0,      # admiralty coefficient C = a * Fn^-b * (form corrections)
    admiralty_b=0.69,
    cruise_kn=15.0,         # range is at min(cruise_kn, 0.6 x speed); the plant (powerplant.py) sets weight and fuel
    misc_frac=0.055,        # equipment, outfit and electrics, as a fraction of std displacement (crew, provisions
                            # and water are weighed by crew.py)
    superstructure_t_per_m2=0.32,
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
    armour: dict = field(default_factory=dict)       # armour.armour_geometry at the solved draught and depth
    gm_full: float = 0.0
    gm_light: float = 0.0
    roll_s: float = 0.0        # natural roll period at full load
    wind: dict = field(default_factory=dict)   # beam-wind heel (stability.wind_heel)
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
            hull = hullweight.box_structure(design, L, B, D, tun)
        else:
            hull = hullweight.hull_structure(design, L, B, cb, D, disp, arm, style.strength_deck(design, D),
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
    res.armour = armour_geometry(design, L, res.draught, res.depth, geo)
    res.weights = items
    groups = {}
    for w in items:
        groups[w.group] = groups.get(w.group, 0.0) + w.w
    res.groups = groups

    stability.evaluate(res, L, B, cb, tun, geo.get("windage"))

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
    stability.checks(res, L, B, tun)
    fn = froude(V, L)
    res.warnings += style.checks(design, res, tun)
    res.warnings += armour_checks(design, res, geo)
    res.warnings += hullweight.structure_checks(res.hull)
    if fn > tun.get("fn_warn", 0.62):
        res.warnings.append(f"Speed {V} kn is extreme for a {L:.0f} m hull (Froude {fn:.2f}); power is enormous.")
    return res


def rough_payload(design, D):
    """First-pass armament and superstructure estimate before the layout exists (all at x=0)."""
    out = rough_armament(design, D)
    out.append(Weight("Superstructure", "superstructure", 0.012 * design["hull"]["length"] ** 2, z_rel=("deck", 4)))
    return out
