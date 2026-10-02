"""
powerplant: the propulsion plant from its technology and the design's choices (research/powerplant-model.md).

The design gives the plant's researched technology as numbers (design["machinery"]["tech"]; plant-templates.md
has examples by year to copy), plus its design choices. Nothing here depends on the ship's
type or style: the trade-offs come from the plant.

    "machinery": {
      "tech": {
        "name": "...",                    label only
        "fuel": "coal",                   coal | oil | diesel | petrol
        "weight_kg_per_kw": 150,          whole plant without fuel, at design stress 0 (conservative)
        "stress_floor": 0.75,             weight multiplier at design stress 1: how far the tech can be pushed
        "sfc_g_per_kwh": 1050,            fuel at rated power
        "density_t_per_m3": 0.26,         plant weight per m3 of gross machinery space, at stress 0
        "unit_max_mw": 9,                 largest prime-mover unit (an engine, or a turbine set on a shaft)
        "unit": {"mw": 5, "height_m": 7.5, "width_m": 4.5, "length_m": 9},   a reference unit's size
        "boiler_fraction": 0.6,           share of the machinery length in boiler rooms (0: engines only)
        "crew_k": 38,                     engineering crew = crew_k x MW^0.75
        "part_load": "REC",               part-load fuel curve: REC, DT, GTB, DSL, GTS or ICR
        "draught": {                      how the boilers get air and lose their gas (funnels)
          "system": "forced_boost",       natural | forced_boost | forced | exhaust (diesel, petrol)
          "velocity_m_s": 8,              funnel gas velocity on fans (forced, forced_boost)
          "reach_m": 6,                   how far an uptake can lead from its boilers
          "natural_fraction": 0.6,        share of rated power on natural draught (forced_boost)
          "gas_temp_k": 600, "air_fuel_ratio": 16}},
      "stress": 0.0,                      design stress, 0 conservative .. 1 max: lighter, thirstier, less margin
      "shafts": 2,                        default: as few as the units allow (1..4)
      "units_per_shaft": 1,               raised automatically if a unit would exceed unit_max_mw
      "transmission": "mechanical",       mechanical | electric (turbo-/diesel-electric: x1.3 weight)
      "arrangement": "grouped",           grouped (boilers, then engines) | unit (alternating; x1.1 length)
      "centreline_bulkhead": false,       splits the rooms port and starboard (rows count per side)
      "bunkers": "wing",                  coal: wing (beside the machinery) | ends (fore and aft of it)
      "wing_bunker_m": 2.0                width of each wing bunker
    }

Units: shaft power in kW inside this module (the rest of shipgen uses shp), weights in tonnes, metres.
"""
from __future__ import annotations

import math

KW_PER_SHP = 0.7457
CASING = 3.0               # a funnel casing's plan area over its gas area (air casing, several uptakes)
STEEL_FRAME = 0.92          # usable width of the hull at the machinery, as a fraction of the beam (frames, sides)
DOUBLE_BOTTOM_FRAC = 0.07   # double bottom height, fraction of the hull depth (at least DOUBLE_BOTTOM_MIN)
DOUBLE_BOTTOM_MIN = 1.0

FUELS = {   # lower heating value MJ/kg, stowage m3/t
    "coal": dict(lhv=30.0, stowage=1.30),
    "oil": dict(lhv=41.0, stowage=1.07),
    "diesel": dict(lhv=42.8, stowage=1.19),
    "petrol": dict(lhv=44.0, stowage=1.37),
}

# part-load fuel multipliers by load fraction, and the rise per 0.1 of overload
CURVES = {
    "REC": ([1.45, 1.20, 1.07, 1.02, 1.00], 0.5),
    "DT": ([2.60, 1.90, 1.40, 1.12, 1.00], 0.3),
    "GTB": ([1.90, 1.45, 1.18, 1.05, 1.00], 0.3),
    "DSL": ([1.25, 1.10, 1.03, 1.00, 1.01], 0.4),
    "GTS": ([2.80, 1.85, 1.35, 1.12, 1.00], 0.2),
    "ICR": ([1.35, 1.12, 1.03, 1.00, 1.00], 0.2),
}
CURVE_LOADS = [0.10, 0.25, 0.50, 0.75, 1.00]
STEAM_CURVES = ("REC", "DT", "GTB")       # boilers and turbines are shared: the curve applies to plant load

DRAUGHT_SYSTEMS = ("natural", "forced_boost", "forced", "exhaust")
SMOKE_K = {"coal_natural": 4.0, "coal": 3.0, "oil": 1.5, "oil_heated": 1.0, "diesel": 0.5, "petrol": 0.5}

# a mature-ish 1940 high-pressure geared turbine plant (plant-templates.md, ST7 1940): the default tech
DEFAULT_TECH = {
    "name": "High-pressure geared turbines (1940)", "fuel": "oil", "weight_kg_per_kw": 35.2, "stress_floor": 0.5,
    "sfc_g_per_kwh": 349, "density_t_per_m3": 0.42, "unit_max_mw": 42.8,
    "unit": {"mw": 30, "height_m": 5.0, "width_m": 5.0, "length_m": 8},
    "boiler_fraction": 0.5, "crew_k": 10, "part_load": "GTB",
    "draught": {"system": "forced", "velocity_m_s": 14.0, "reach_m": 27.0, "gas_temp_k": 450, "air_fuel_ratio": 15},
}
CHOICES = dict(stress=0.0, shafts=None, units_per_shaft=1, transmission="mechanical", arrangement="grouped",
               centreline_bulkhead=False, bunkers=None, wing_bunker_m=2.0)


def spec(design, default_tech=None):
    """The design's plant: its tech over the default tech, and its choices over the defaults."""
    m = design.get("machinery") or {}
    base = default_tech or DEFAULT_TECH
    tech = {**base, **(m.get("tech") or {})}
    tech["unit"] = {**base["unit"], **((m.get("tech") or {}).get("unit") or {})}
    tech["draught"] = {**base["draught"], **((m.get("tech") or {}).get("draught") or {})}
    p = {**CHOICES, **{k: v for k, v in m.items() if k in CHOICES}, "tech": tech}
    if p["bunkers"] is None:
        p["bunkers"] = "wing" if tech["fuel"] == "coal" else "ends"
    return p


def validate(design, default_tech=None):
    p = spec(design, default_tech)
    t = p["tech"]
    errs = []
    if t["fuel"] not in FUELS:
        errs.append(f"machinery.tech.fuel = {t['fuel']!r}: use {', '.join(FUELS)}")
    if t["part_load"] not in CURVES:
        errs.append(f"machinery.tech.part_load = {t['part_load']!r}: use {', '.join(CURVES)}")
    if t["draught"]["system"] not in DRAUGHT_SYSTEMS:
        errs.append(f"machinery.tech.draught.system = {t['draught']['system']!r}: use {', '.join(DRAUGHT_SYSTEMS)}")
    for k in ("weight_kg_per_kw", "sfc_g_per_kwh", "density_t_per_m3", "unit_max_mw", "crew_k"):
        if not t[k] > 0:
            errs.append(f"machinery.tech.{k} must be above 0")
    for k in ("mw", "height_m", "width_m", "length_m"):
        if not t["unit"][k] > 0:
            errs.append(f"machinery.tech.unit.{k} must be above 0")
    if not 0 <= t["boiler_fraction"] < 1:
        errs.append("machinery.tech.boiler_fraction must be 0..1")
    if not 0 <= p["stress"] <= 1:
        errs.append("machinery.stress must be 0..1")
    if p["transmission"] not in ("mechanical", "electric"):
        errs.append(f"machinery.transmission = {p['transmission']!r}: use mechanical or electric")
    if p["arrangement"] not in ("grouped", "unit"):
        errs.append(f"machinery.arrangement = {p['arrangement']!r}: use grouped or unit")
    if p["bunkers"] not in ("wing", "ends"):
        errs.append(f"machinery.bunkers = {p['bunkers']!r}: use wing or ends")
    if p["shafts"] is not None and not (isinstance(p["shafts"], int) and 1 <= p["shafts"] <= 8):
        errs.append("machinery.shafts must be 1..8")
    return errs


def is_steam(p):
    return p["tech"]["boiler_fraction"] > 0


def rated(p, shp):
    """The plant at its rated power: units, weight, fuel rate, crew, continuous and overload power."""
    t, s = p["tech"], p["stress"]
    kw = max(shp, 1.0) * KW_PER_SHP
    mw = kw / 1000.0
    shafts = p["shafts"] or max(1, min(4, math.ceil(mw / t["unit_max_mw"])))
    per_shaft = max(p["units_per_shaft"], math.ceil(mw / shafts / t["unit_max_mw"]))
    elec = p["transmission"] == "electric"
    w_spec = t["weight_kg_per_kw"] * (1 - (1 - t["stress_floor"]) * s) * (1.3 if elec else 1.0)
    sfc = t["sfc_g_per_kwh"] * (1 + 0.08 * s) * (1.06 if elec else 1.0)
    return dict(kw=kw, shafts=shafts, units_per_shaft=per_shaft, units=shafts * per_shaft,
                unit_mw=mw / (shafts * per_shaft), weight_t=kw * w_spec / 1000.0, sfc=sfc,
                density=t["density_t_per_m3"] * (0.85 + 0.15 * s),
                continuous_kw=kw * (1 - 0.15 * s), overload=1 + 0.15 * (1 - s),
                crew=round(t["crew_k"] * mw ** 0.75), raised_units=per_shaft > p["units_per_shaft"])


def curve_mult(name, f):
    pts, over = CURVES[name]
    if f >= 1.0:
        return pts[-1] + over * (f - 1.0) / 0.1
    if f <= CURVE_LOADS[0]:
        return pts[0] * (CURVE_LOADS[0] / max(f, 0.02)) ** 0.25   # below the table: keeps rising, gently
    for (f0, m0), (f1, m1) in zip(zip(CURVE_LOADS, pts), zip(CURVE_LOADS[1:], pts[1:])):
        if f <= f1:
            return m0 + (m1 - m0) * (f - f0) / (f1 - f0)
    return pts[-1]


def fuel_rate(p, shp_rated, shp_load):
    """Fuel burnt at shp_load, kg per hour. Steam plants apply their curve to the plant's load; engine plants
    shut units down so the running ones sit near full load."""
    r = rated(p, shp_rated)
    kw = shp_load * KW_PER_SHP
    curve = p["tech"]["part_load"]
    if curve in STEAM_CURVES:
        f = kw / r["kw"]
    else:
        unit_kw = r["kw"] / r["units"]
        running = max(1, min(r["units"], math.ceil(kw / unit_kw - 1e-9)))
        f = kw / (running * unit_kw)
    return kw * r["sfc"] * curve_mult(curve, f) / 1000.0


def double_bottom(depth):
    return max(DOUBLE_BOTTOM_MIN, DOUBLE_BOTTOM_FRAC * depth)


def space(p, shp, w_avail, h_avail):
    """The machinery space for an inside width w_avail and a height h_avail (inner bottom to the bounding
    deck): its length, split into boiler and engine rooms, and how the units fit. A plant taller than h_avail
    protrudes above it (the layout covers that with a casing); one with no row of units across is infeasible."""
    t = p["tech"]
    r = rated(p, shp)
    k = (r["unit_mw"] / t["unit"]["mw"]) ** (1 / 3)        # units scale with the cube root of their power
    h_u, w_u, l_u = t["unit"]["height_m"] * k, t["unit"]["width_m"] * k, t["unit"]["length_m"] * k
    h_eff = max(1.0, min(h_avail, h_u + 2.5))
    pitch = w_u + 0.8
    split = p["centreline_bulkhead"]
    w_side = w_avail / 2 if split else w_avail
    rows = int(w_side // pitch) if w_side > 0 else 0
    used = rows * pitch
    w_eff = (used + 0.5 * (w_side - used)) * (2 if split else 1)
    volume = r["weight_t"] / r["density"]
    length = volume / max(w_eff, 0.5) / h_eff
    length *= 1.10 if p["arrangement"] == "unit" else 1.0
    length = max(length, l_u + 2.0)
    bf = t["boiler_fraction"]
    return dict(length=length, boilers=length * bf, engines=length * (1 - bf), rows=rows, unit=(l_u, w_u, h_u),
                protrusion=max(0.0, h_u - h_avail), volume=volume, w_eff=w_eff, h_eff=h_eff, fits=rows > 0)


def bunkers(p, fuel_t, length, w_avail, h_avail, ship_l, ship_b, cb, depth, draught=0.0, tds=0.0):
    """Where the fuel goes: (tonnes in wing bunkers, length of end bunkers or tanks). Coal fills wing bunkers
    beside the machinery (if chosen; they run from the inner bottom up to the main deck, the upper bunkers above
    the armour deck included), then end bunkers fore and aft of it. Liquid fuel fills the double bottom and
    the torpedo protection's liquid layers (half of a tds-deep system, over 0.6 of the length, up to the waterline)
    first, then end tanks."""
    stow = FUELS[p["tech"]["fuel"]]["stowage"]
    left, wing = fuel_t, 0.0
    if p["tech"]["fuel"] == "coal":
        if p["bunkers"] == "wing":
            wing = min(left, 2 * p["wing_bunker_m"] * length * (depth - double_bottom(depth)) * 0.9 / stow)
            left -= wing
        w_end = w_avail + (2 * p["wing_bunker_m"] if p["bunkers"] == "wing" else 0.0)
    else:
        db = double_bottom(depth) * ship_l * ship_b * cb * 0.6 / stow     # usable double-bottom tankage
        layers = 2 * 0.5 * tds * 0.6 * ship_l * draught / stow
        left = max(0.0, left - db - layers)
        w_end = w_avail
    end = left * stow / (max(w_end, 1.0) * max(h_avail, 1.0) * 0.9) if left > 0 else 0.0
    return wing, end


def segments(p, sp, end_len):
    """The machinery block, forward to aft: [(kind, length)], kind boiler, engine or bunker. Grouped: boilers,
    then engines; unit: two boiler-engine pairs. End bunkers go half ahead of the boilers and half between
    boilers and engines (a cross bunker)."""
    b, e = sp["boilers"], sp["engines"]
    half = end_len / 2
    out = []
    if half > 0.05:
        out.append(("bunker", half))
    if b <= 0.05:                    # engines only (diesel, petrol)
        out.append(("engine", e))
        if half > 0.05:
            out.append(("bunker", half))
        return out
    if p["arrangement"] == "unit":
        out += [("boiler", b / 2), ("engine", e / 2)]
        if half > 0.05:
            out.append(("bunker", half))
        out += [("boiler", b / 2), ("engine", e / 2)]
    else:
        out.append(("boiler", b))
        if half > 0.05:
            out.append(("bunker", half))
        out.append(("engine", e))
    return out


# ---------------------------------------------------------------------------
# funnels (spec section 6b)
# ---------------------------------------------------------------------------
def gas_flow(p):
    """Funnel gas, m3/s per MW of rated power."""
    t = p["tech"]
    d = t["draught"]
    sfc = rated(p, 1000.0)["sfc"]
    return sfc / 3600.0 * (1 + d.get("air_fuel_ratio", 15)) / (353.0 / d.get("gas_temp_k", 600))


def natural_velocity(p, stack_m, trunk_m=0.0):
    t = p["tech"]["draught"].get("gas_temp_k", 600)
    return 0.3 * math.sqrt(2 * 9.81 * max(stack_m, 1.0) * (1 - 288.0 / t)) * max(0.5, 1 - 0.02 * trunk_m)


def funnel_plan(p, shp, groups, beam, stack_m, extra=0):
    """Funnels for boiler groups of the given lengths: (count per group, width, length, gas velocity, area
    needed). Count: enough gas area (a funnel's gas area is at most that of a min(0.22 beam, 7 m) wide funnel)
    and each uptake within reach of its boilers; `extra` more if the design asks for more. The casing drawn is
    CASING times the gas area, up to that largest size. Engine-only plants get one small
    exhaust funnel per group."""
    d = p["tech"]["draught"]
    mw = rated(p, shp)["kw"] / 1000.0
    q = gas_flow(p)
    sysname = d["system"]
    v_nat = natural_velocity(p, stack_m)
    if sysname == "natural":
        area, v = mw * q / v_nat, v_nat
    elif sysname == "forced_boost":
        area = max(mw * q / d["velocity_m_s"], mw * d.get("natural_fraction", 0.6) * q / v_nat)
        v = d["velocity_m_s"]
    else:
        v = d.get("velocity_m_s", 14.0)
        area = mw * q / v
    w_max = min(0.22 * beam, 7.0)
    a_max = 0.785 * w_max * 1.5 * w_max
    n_area = math.ceil(area / a_max - 1e-9)
    reach = d.get("reach_m", 10.0)
    counts = []
    for g in groups:
        # first guess of the funnel length, then the reach rule
        l_f = 1.5 * min(w_max, math.sqrt(area / max(1, n_area) / (0.785 * 1.5)))
        counts.append(max(1, math.ceil(g / (2 * reach + l_f) - 1e-9)))
    if not counts:
        counts = [1]
    want = max(n_area, sum(counts)) + extra
    i = 0
    while sum(counts) < want:       # more funnels: on the longest groups per funnel
        j = max(range(len(counts)), key=lambda k: (groups[k] if groups else 1) / counts[k])
        counts[j] += 1
        i += 1
    n = sum(counts)
    w = min(w_max, math.sqrt(CASING * area / n / (0.785 * 1.5)))
    w = max(w, 2.2 if sysname != "exhaust" else 1.0)
    return dict(counts=counts, width=w, length=1.5 * w, velocity=v, area=area, gas=q, reach=reach)


def smoke_reach(p, shp):
    """How far aft of a funnel its smoke blinds a control position (spec 6b: k_smoke sqrt(P_MW q_gas))."""
    t = p["tech"]
    d = t["draught"]
    if t["fuel"] == "coal":
        k = SMOKE_K["coal_natural" if d["system"] == "natural" else "coal"]
    elif t["fuel"] == "oil":
        k = SMOKE_K["oil_heated" if d.get("gas_temp_k", 600) <= 480 else "oil"]
    else:
        k = SMOKE_K[t["fuel"]]
    return k * math.sqrt(rated(p, shp)["kw"] / 1000.0 * gas_flow(p))


def funnel_weight(w, l, height, uptake_vertical, uptake_horizontal):
    """(funnel, uptake) tonnes: 0.12 t per m of perimeter per m of height, uptakes 0.18 t with horizontal runs
    counting 1.5 times."""
    per = math.pi * w + 2 * max(0.0, l - w)
    return 0.12 * per * height, 0.18 * per * (uptake_vertical + 1.5 * uptake_horizontal)


def published(p, shp, extra=None):
    """The plant's static numbers for the game (report "plant")."""
    t = p["tech"]
    r = rated(p, shp)
    out = dict(
        name=t.get("name", ""), fuel=t["fuel"], rated_kw=round(r["kw"]), rated_shp=round(shp, -1),
        continuous_kw=round(r["continuous_kw"]), overload_max=round(r["overload"], 3),
        shafts=r["shafts"], units=r["units"], unit_mw=round(r["unit_mw"], 2), weight_t=round(r["weight_t"], 1),
        sfc_g_per_kwh=round(r["sfc"], 1), part_load=dict(curve=t["part_load"], loads=CURVE_LOADS,
                                                         multipliers=CURVES[t["part_load"]][0],
                                                         overload_per_tenth=CURVES[t["part_load"]][1]),
        draught=t["draught"]["system"], stress=p["stress"], transmission=p["transmission"],
        arrangement=p["arrangement"], crew=r["crew"])
    if t["draught"]["system"] == "forced_boost":
        out["natural_fraction"] = t["draught"].get("natural_fraction", 0.6)
    out.update(extra or {})
    return out
