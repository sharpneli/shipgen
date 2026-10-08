"""
crew: the complement and the volume it needs (research/crew-space-model.md).

The complement is built from what the ship carries: engineering (the plant, powerplant.rated crew), the crews of
its guns and torpedo mounts, deck and command (by size), an air group (carriers), then the hotel crew (cooks,
stewards, medics, supply) as a fraction of the whole. The habitability standard is numbers in the design (copy a
block from crew-templates.md); the game rates comfort from them smoothly, so there are no hard tiers here.

    "crew": {
      "standard": {                      habitability: net deck areas per head, shared spaces, water, provisions
        "name": "...",
        "sleep_rating_m2": 1.3, "sleep_cpo_m2": 2.5, "sleep_officer_m2": 6.0,
        "mess_seats_per_man": 0.33, "galley_k": 0.30, "galley_min_m2": 5, "sanitary_m2": 0.20,
        "sickbay_beds_per_man": 0.010, "welfare_m2": 0.03, "services_k": 0.05, "passage_factor": 1.20,
        "deck_height_m": 2.4, "provisions_m3_per_day": 0.009, "water_l_per_day": 60, "hotel_fraction": 0.06,
        "cpo_fraction": 0.08, "tolerance_days": 60},
      "endurance_days": 45,              provisions carried; default: the fuel's range at cruise speed
      "distiller": true,                 makes fresh water: tanks then hold only buffer_days
      "buffer_days": 5,
      "water_l_per_day": 60,             default: the standard's
      "berth_ratio": 1.0,                below 1 hot-bunking, above 1 surge berths
      "officer_fraction": null           default 0.15 under 30 men, else 0.08
    }

The crew lives wherever the ship has empty volume (crew_space): the hull to the main deck and the superstructure,
less what the machinery, magazines, bunkers, holds, tanks and torpedo protection take, of which USABLE is left
for crew (the rest is passages, stores, workshops, fan rooms, offices). Too little room makes the hull grow.
"""
from __future__ import annotations

import math

USABLE = 0.65            # of the ship's empty volume, what living space, provisions and water may take
CREW_T = 0.12            # tonnes per man with his effects
PROVISIONS_T_PER_M3 = 0.6

STANDARDS = {   # research/crew-space-model.md section 4, as design numbers (crew-templates.md)
    "H0": dict(name="Sleep at station (MTB, PT boat)", sleep_rating_m2=0.6, sleep_cpo_m2=0.8, sleep_officer_m2=1.5,
               mess_seats_per_man=0.0, galley_k=0.25, galley_min_m2=1.0, sanitary_m2=0.06, sickbay_beds_per_man=0.0,
               welfare_m2=0.0, services_k=0.0, passage_factor=1.10, deck_height_m=1.9, provisions_m3_per_day=0.006,
               water_l_per_day=8, hotel_fraction=0.0, cpo_fraction=0.0, tolerance_days=2),
    "H1": dict(name="Hammocks over mess tables", sleep_rating_m2=1.1, sleep_cpo_m2=1.8, sleep_officer_m2=5.0,
               mess_seats_per_man=0.0, galley_k=0.30, galley_min_m2=4.0, sanitary_m2=0.10, sickbay_beds_per_man=0.010,
               welfare_m2=0.0, services_k=0.03, passage_factor=1.15, deck_height_m=2.3, provisions_m3_per_day=0.007,
               water_l_per_day=15, hotel_fraction=0.05, cpo_fraction=0.08, tolerance_days=30),
    "H2": dict(name="Tiered bunks and separate messdecks", sleep_rating_m2=1.3, sleep_cpo_m2=2.5, sleep_officer_m2=6.0,
               mess_seats_per_man=0.33, galley_k=0.30, galley_min_m2=5.0, sanitary_m2=0.20,
               sickbay_beds_per_man=0.010, welfare_m2=0.03, services_k=0.05, passage_factor=1.20, deck_height_m=2.4,
               provisions_m3_per_day=0.009, water_l_per_day=60, hotel_fraction=0.06, cpo_fraction=0.08,
               tolerance_days=60),
    "H3": dict(name="Cold-war bunks with lockers and lounges", sleep_rating_m2=1.9, sleep_cpo_m2=3.5,
               sleep_officer_m2=7.5, mess_seats_per_man=0.30, galley_k=0.35, galley_min_m2=6.0, sanitary_m2=0.35,
               sickbay_beds_per_man=0.012, welfare_m2=0.15, services_k=0.08, passage_factor=1.25, deck_height_m=2.6,
               provisions_m3_per_day=0.010, water_l_per_day=120, hotel_fraction=0.07, cpo_fraction=0.08,
               tolerance_days=120),
    "H4": dict(name="Modern small messes", sleep_rating_m2=2.8, sleep_cpo_m2=5.0, sleep_officer_m2=9.0,
               mess_seats_per_man=0.30, galley_k=0.40, galley_min_m2=8.0, sanitary_m2=0.45, sickbay_beds_per_man=0.015,
               welfare_m2=0.30, services_k=0.10, passage_factor=1.28, deck_height_m=2.8, provisions_m3_per_day=0.011,
               water_l_per_day=180, hotel_fraction=0.07, cpo_fraction=0.08, tolerance_days=180),
    "H5": dict(name="Single cabins (merchant)", sleep_rating_m2=5.0, sleep_cpo_m2=7.0, sleep_officer_m2=10.0,
               mess_seats_per_man=0.50, galley_k=0.40, galley_min_m2=8.0, sanitary_m2=0.60, sickbay_beds_per_man=0.015,
               welfare_m2=0.50, services_k=0.12, passage_factor=1.30, deck_height_m=2.8, provisions_m3_per_day=0.011,
               water_l_per_day=200, hotel_fraction=0.08, cpo_fraction=0.08, tolerance_days=365),
}
CHOICES = dict(endurance_days=None, distiller=True, buffer_days=5, water_l_per_day=None, berth_ratio=1.0,
               officer_fraction=None)


def spec(design, default_standard="H2"):
    """The design's crew settings over the defaults (the standard over the style's default standard block)."""
    c = design.get("crew") or {}
    base = STANDARDS[default_standard]
    std = {**base, **(c.get("standard") or {})}
    out = {**CHOICES, **{k: v for k, v in c.items() if k in CHOICES}, "standard": std}
    if out["water_l_per_day"] is None:
        out["water_l_per_day"] = std["water_l_per_day"]
    return out


def validate(design, default_standard="H2"):
    s = spec(design, default_standard)
    errs = []
    for k, v in s["standard"].items():
        if k != "name" and not (isinstance(v, (int, float)) and v >= 0):
            errs.append(f"crew.standard.{k} must be a number, 0 or more")
    if not 0 <= s["standard"]["hotel_fraction"] < 0.9:
        errs.append("crew.standard.hotel_fraction must be 0..0.9")
    if s["endurance_days"] is not None and not s["endurance_days"] > 0:
        errs.append("crew.endurance_days must be above 0")
    if not s["berth_ratio"] > 0:
        errs.append("crew.berth_ratio must be above 0")
    return errs


# ---------------------------------------------------------------------------
# complement
# ---------------------------------------------------------------------------
def gun_crew(calibre_mm, barrels):
    """Crew of one gun mount, handling rooms included: per barrel 0.5 + 0.09 per mm of calibre, plus 0.02 per mm
    for the mount (Iowa's 16-inch triple about 120, a 5-inch twin about 26, a 40 mm quad about 17, a 20 mm 3)."""
    return barrels * (0.5 + 0.09 * calibre_mm) + 0.02 * calibre_mm


def torpedo_crew(t):
    return 0.5 * t["barrels"] if t.get("fixed_tube") else 2 + 0.6 * t["barrels"]


def deck_crew(std_t, k=0.8):
    """Deck, command, signals, control and damage control: k x standard displacement^0.5, tapering below 1,000 t
    (a PT boat has a skipper, an exec and a quartermaster, not a deck division)."""
    return k * max(std_t, 1.0) ** 0.5 * min(1.0, std_t / 1000.0) ** 0.3


def complement(lay, res, extra=None, deck_k=0.8, officer_fraction=None, hotel_fraction=0.06):
    """The complement by department: {department: men}, with totals."""
    from geometry import AA_CFG
    guns = 0.0
    torps = 0.0
    for m in lay.mounts:
        t = m["t"]
        if m["kind"] == "torpedo":
            torps += torpedo_crew(t)
        else:
            guns += gun_crew(t["calibre_mm"], t["barrels"])
    for a in lay.aa:
        guns += gun_crew(40.0 if "40" in a["type"] else 20.0, AA_CFG[a["type"]][1])
    deps = dict(engineering=res.plant_rated.get("crew", 0), weapons=round(guns + torps),
                deck_and_command=round(deck_crew(res.std, deck_k)))
    deps.update(extra or {})
    ops = sum(deps.values())
    total = math.ceil(ops / (1 - hotel_fraction))
    deps["hotel"] = total - ops
    fo = officer_fraction if officer_fraction is not None else (0.15 if total < 30 else 0.08)
    return dict(departments=deps, total=total, officers=max(1, round(fo * total)))


# ---------------------------------------------------------------------------
# space
# ---------------------------------------------------------------------------
def needs(c, n, officers, h_avail):
    """Volumes the crew needs (crew-space-model section 3): living space, provisions, water tankage and the
    distiller, and the comfort inputs."""
    s = c["standard"]
    nc = round(s["cpo_fraction"] * n)
    nr = max(0, n - officers - nc)
    b = c["berth_ratio"]
    t_end = c["endurance_days"]
    a_sleep = nr * b * s["sleep_rating_m2"] + nc * s["sleep_cpo_m2"] + officers * s["sleep_officer_m2"]
    a_mess = s["mess_seats_per_man"] * (nr + nc) * 1.1 + (0.8 * officers * 1.6 if s["mess_seats_per_man"] else 0.0)
    a_galley = max(s["galley_min_m2"], s["galley_k"] * n ** 0.8)
    a_san = max(1.0, s["sanitary_m2"] * n)
    beds = math.ceil(s["sickbay_beds_per_man"] * n) if (n >= 15 and t_end > 3) else 0
    a_med = (6 + 4 * beds if beds else 0) + (40 if n > 1000 and s["sickbay_beds_per_man"] >= 0.01 else 0)
    a_welfare = s["welfare_m2"] * n
    a_serv = s["services_k"] * n ** 0.85 * (1 if t_end > 7 else 0.5)
    a_net = a_sleep + a_mess + a_galley + a_san + a_med + a_welfare + a_serv
    h_eff = min(s["deck_height_m"], h_avail)
    live = a_net * s["passage_factor"] * h_eff
    prov = n * t_end * s["provisions_m3_per_day"] * 1.4
    w_day = c["water_l_per_day"]
    water = n * w_day * (min(c["buffer_days"], t_end) if c["distiller"] else t_end) / 1000.0
    q_dist = 1.2 * n * w_day / 1000.0 if c["distiller"] else 0.0
    return dict(living_m3=live, provisions_m3=prov, water_m3=water, distiller_m3_per_day=q_dist,
                distiller_volume_m3=0.06 * q_dist, net_area_m2=a_net, sleep_m2_per_man=a_sleep / max(1, n),
                headroom_m=h_eff, sickbay_beds=beds, ratings=nr, cpos=nc)


TAKEN = ("magazine", "boiler_room", "engine_room", "bunker", "hold", "cargo_tank", "fuel_tank", "steering")


def crew_space(lay, design, res):
    """The ship's empty volume, m3: the hull from the inner bottom to the main deck, less the spaces the machinery,
    magazines, bunkers, holds, tanks, steering gear and torpedo protection take, with the raised stretches of hull
    (forecastle, poop), plus the superstructure (blocks)."""
    import powerplant
    from layout import LEVEL_H
    from layout import block_role
    from geometry import cwp
    hull = lay.hull
    L, B = hull.L, hull.B
    cb = design["hull"]["block_coefficient"]
    D, T = res.depth, res.draught
    db = powerplant.double_bottom(D)
    plan = lay.geo.plant or {}
    low = (plan.get("top", D) if plan.get("armoured") else D) - db      # default compartment height
    hull_v = L * B * (T * cb + max(0.0, D - T) * cwp(cb)) - db * L * B * cwp(cb) * 0.9
    # raised stretches of hull (forecastle, poop) are hull: the subdivision quarters men in their cells
    raised = sum(_area(dk["points"]) * (dk["top"] - dk["base"]) for dk in lay.decks if dk["kind"] == "deck")
    taken = 0.0
    for c in lay.compartments:
        if c["kind"] not in TAKEN:
            continue
        h = (c["top"] - c["base"]) if "top" in c and "base" in c else (D - db if c["kind"] in ("hold", "cargo_tank")
                                                                       else low)
        taken += (c["x1"] - c["x0"]) * 2 * c["half_width"] * h
    cit = lay.geo.citadel
    if plan.get("tds") and cit:
        taken += 2 * plan["tds"] * (cit[1] - cit[0]) * low
    rooms = {b["id"]: b.get("area", (b["x1"] - b["x0"]) * b["w"]) * LEVEL_H * 0.9 for b in lay.blocks if b["kind"] != "director"
             and block_role(b["id"]) not in ("hangar", "director", "casemate")}
    sup = sum(rooms.values())
    free = max(0.0, hull_v - taken) + raised + sup
    return dict(hull_m3=hull_v + raised, taken_m3=taken, superstructure_m3=sup, free_m3=free, usable_m3=USABLE * free,
                hull_usable_m3=USABLE * (max(0.0, hull_v - taken) + raised), blocks_m3=rooms)


def spread(n, vols):
    """n men over rooms by volume ({id: m3}): whole men, the remainders to the largest fractions, {id: men} for the
    rooms that get any."""
    total = sum(vols.values())
    if n <= 0 or total <= 0:
        return {}
    shares = {k: n * v / total for k, v in vols.items()}
    men = {k: int(s) for k, s in shares.items()}
    for k in sorted(shares, key=lambda k: men[k] - shares[k])[:n - sum(men.values())]:
        men[k] += 1
    return {k: m for k, m in men.items() if m}


def _area(pts):
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))) / 2


def tank_room(lay, design, res):
    """Double-bottom tankage left for fresh water after the fuel (as powerplant.bunkers fills it), m3."""
    import powerplant
    p = res.plant
    if p["tech"]["fuel"] == "coal":
        oil = 0.0
    else:
        oil = res.fuel * powerplant.FUELS[p["tech"]["fuel"]]["stowage"]
    D = res.depth
    tank = powerplant.double_bottom(D) * lay.hull.L * lay.hull.B * design["hull"]["block_coefficient"] * 0.6
    return max(0.0, tank - oil)


def apply(lay, design, res, style):
    """Crew the laid-out ship: its complement, the volume the crew needs against the volume the ship has (too
    little: the hull is short of length), and the weights of crew, provisions and water.
    Sets lay.crew (report "crew"); subdivision.build quarters the complement in the hull's free cells."""
    from weights import Weight
    import powerplant
    c = spec(design, style.CREW_STANDARD)
    range_days = math.ceil(design.get("range_nm", 6000) / max(res.cruise_kn, 1.0) / 24.0 - 1e-9)
    if c["endurance_days"] is None:
        c["endurance_days"] = max(1, range_days)
    s = c["standard"]
    comp = complement(lay, res, style.crew_extra(design), style.CREW_DECK_K, c["officer_fraction"],
                      s["hotel_fraction"])
    n = comp["total"]
    h_avail = res.depth - powerplant.double_bottom(res.depth)
    nd = needs(c, n, comp["officers"], h_avail)
    room = crew_space(lay, design, res)
    water_tanks = tank_room(lay, design, res)
    water_free = max(0.0, nd["water_m3"] - water_tanks)        # water the double bottom can't take
    need = nd["living_m3"] + nd["provisions_m3"] + water_free + nd["distiller_volume_m3"]
    if need > room["usable_m3"]:
        lay.fail("length", f"No room for the crew: {n} men need about {need:,.0f} m3 for quarters, provisions and "
                           f"water, but the ship has about {room['usable_m3']:,.0f} m3 to spare. Use a lower "
                           "habitability standard, a shorter endurance, a distiller, or fewer men (guns, power).")
    if c["endurance_days"] < range_days:
        lay.warnings.append(f"Provisions for {c['endurance_days']} days, but the fuel lasts {range_days} days at "
                            "cruising speed.")
    # the crew lives in the hull first (research/superstructure-research.md: the hull fills first, the overflow goes
    # up); whoever doesn't fit there is quartered in the superstructure, spread over its blocks by volume (not
    # directors, casemate housings or hangars)
    frac = min(1.0, max(0.0, (need - room["hull_usable_m3"]) / need)) if need > 0 else 0.0
    up = round(n * frac)
    up_blocks = spread(up, room["blocks_m3"])
    # weights: crew and effects between decks (those quartered up top at their blocks' mid-height), provisions low,
    # water in the double bottom (or above it)
    from layout import block_base
    x_mid = lay.geo.machinery_mid(lay.hull.L)
    by_id = {b["id"]: b for b in lay.blocks}
    for bid, m in up_blocks.items():
        b = by_id[bid]
        lay.weights.append(Weight(f"Crew and effects ({bid})", "misc", m * CREW_T, x=(b["x0"] + b["x1"]) / 2,
                                  z_rel=("deck", block_base(b) + 1.3)))
    lay.weights += [Weight("Crew and effects", "misc", (n - up) * CREW_T, x=0.0, z_rel=("deck", -1.5)),
                    Weight("Provisions", "misc", nd["provisions_m3"] * PROVISIONS_T_PER_M3, x=0.0,
                           z_rel=("frac", 0.4)),
                    Weight("Fresh water", "misc", nd["water_m3"], x=x_mid, z_rel=("frac", 0.05))]
    lay.crew = dict(complement=n, quartered_in_superstructure=up, superstructure_quarters=up_blocks,
                    officers=comp["officers"], cpos=nd["cpos"], ratings=nd["ratings"],
                    departments=comp["departments"], standard=s.get("name", ""),
                    endurance_days=c["endurance_days"], range_days=range_days, distiller=c["distiller"],
                    berth_ratio=c["berth_ratio"],
                    living_m3=round(nd["living_m3"]), provisions_m3=round(nd["provisions_m3"]),
                    water_m3=round(nd["water_m3"]), water_in_double_bottom_m3=round(nd["water_m3"] - water_free),
                    distiller_m3_per_day=round(nd["distiller_m3_per_day"], 1),
                    space_needed_m3=round(need), space_usable_m3=round(room["usable_m3"]),
                    space_free_m3=round(room["free_m3"]), sleep_m2_per_man=round(nd["sleep_m2_per_man"], 2),
                    sleep_standard_m2=s["sleep_rating_m2"], headroom_m=round(nd["headroom_m"], 2),
                    deck_height_m=s["deck_height_m"], sickbay_beds=nd["sickbay_beds"],
                    tolerance_days=s["tolerance_days"])


# ---------------------------------------------------------------------------
# battle stations (research/08_gunfire_effects.md: casualties are the men within a burst's reach)
# ---------------------------------------------------------------------------
HANDLING = 0.4           # of a turret's crew, below in its barbette (working chamber, hoists, handling room) (E)
COMMAND_K = (4, 0.2)     # the command party: 4 + 0.2 x deck_and_command, on the bridge (E)
AFT_CONTROL = 0.25       # of the command party, at the aft control when there is one (E)
DIRECTOR_K = 2           # a director's crew: 2 + its rangefinder's base in metres (E; a Mk 51 tub has 2)
STEERING_PARTY = 2       # men in the steering gear room


def battle_stations(lay, sub):
    """Where the complement stands at battle stations, for the game's casualty model (the quarters are empty then;
    crew weights stay lumped). Every man is placed once, so the counts add up to the complement:
      weapons     over the mounts (AA and torpedoes too) by their crews (gun_crew, torpedo_crew); a turret in the
                  hull keeps HANDLING of its crew in its barbette
      engineering over the boiler and engine rooms by volume
      the rest    (deck and command, hotel, an air group) in this order: the command party on the bridge blocks
                  (AFT_CONTROL of it aft), each director's crew, a steering party; an air group in the hangar (or on
                  the flight deck); whoever is left are the repair, first-aid and ammunition parties, in the hull's
                  free rooms (quarters and stores) by volume
    A place a ship lacks passes its men on to the next (to the repair parties last; with no free rooms, to the
    superstructure). Returns dict(components={(kind, id): men}, rooms={id: men}, summary={station: men}); components
    are keyed by kind too, since ids may repeat across kinds (a carrier's Hangar block and hangar bay)."""
    from geometry import AA_CFG, block_outline, has_barbette, polygon_centroid
    from layout import block_role
    from layout import block_base, block_top
    c = lay.crew or {}
    deps = dict(c.get("departments") or {})
    if not deps:
        return dict(components={}, rooms={}, summary={})
    barbettes = {m["id"] for m in lay.mounts if has_barbette(m["t"])}
    on_comp, on_room, summary = {}, {}, {}

    def put(where, men, station):
        for k, m in men.items():
            if m:
                where[k] = where.get(k, 0) + m
                summary[station] = summary.get(station, 0) + m

    def take(n, cap):
        return min(n, max(0, cap))

    # weapons
    need = {}
    for m in lay.mounts:
        t = m["t"]
        need[(m["kind"], m["id"])] = (torpedo_crew(t) if m["kind"] == "torpedo"
                                      else gun_crew(t["calibre_mm"], t["barrels"]))
    for a in lay.aa:
        need[("aa", a["id"])] = gun_crew(40.0 if "40" in a["type"] else 20.0, AA_CFG[a["type"]][1])
    for (kind, k), men in spread(deps.get("weapons", 0), need).items():
        below = round(HANDLING * men) if kind != "aa" and k in barbettes else 0
        put(on_comp, {(kind, k): men - below}, "aa" if kind == "aa" else "torpedoes" if kind == "torpedo" else "guns")
        put(on_comp, {("barbette", f"{k} barbette"): below}, "handling")
    rest = sum(n for d, n in deps.items() if d not in ("weapons", "engineering"))
    # engineering
    mach = {r["id"]: r["volume_m3"] for r in sub["rooms"] if r["kind"] in ("boiler_room", "engine_room")
            and not r.get("shared")}
    if mach:
        put(on_room, spread(deps.get("engineering", 0), mach), "machinery")
    else:
        rest += deps.get("engineering", 0)
    # command, directors, steering
    vol = {}
    for b in lay.blocks:
        area = abs(polygon_centroid(block_outline(b))[0])
        vol[("superstructure", b["id"])] = area * (block_top(b) - block_base(b))
    role = lambda k: block_role(k[1])
    bridge = {k: v for k, v in vol.items() if role(k) in ("bridge", "island")}
    aft = {k: v for k, v in vol.items() if role(k) == "aft_control"}
    if not bridge:
        bridge = {k: v for k, v in vol.items() if role(k) != "director"}
    if bridge:
        n = take(round(COMMAND_K[0] + COMMAND_K[1] * deps.get("deck_and_command", 0)), rest)
        n_aft = round(AFT_CONTROL * n) if aft else 0
        put(on_comp, spread(n - n_aft, bridge), "command")
        put(on_comp, spread(n_aft, aft), "command")
        rest -= n
    for d in lay.directors:
        n = take(DIRECTOR_K + round(d["rangefinder_m"]), rest)
        put(on_comp, {("superstructure", d["id"]): n}, "directors")
        rest -= n
    steer = [r["id"] for r in sub["rooms"] if r["kind"] == "steering" and not r.get("shared")]
    if steer:
        n = take(STEERING_PARTY, rest)
        put(on_room, {steer[0]: n}, "steering")
        rest -= n
    # an air group: in the hangar, else on the flight deck
    air = take(deps.get("air_group", 0), rest)
    if air:
        bays = ({("hangar_bay", c["id"]): 1.0 for c in lay.compartments if c["kind"] == "hangar"}
                or {("flight_deck", dk["id"]): 1.0 for dk in lay.decks if dk["kind"] == "flight_deck"})
        if bays:
            put(on_comp, spread(air, bays), "air")
            rest -= air
    # repair, first-aid and ammunition parties
    free = {r["id"]: r["volume_m3"] for r in sub["rooms"] if r["kind"] in ("accommodation", "stores")
            and not r.get("shared")}
    if free:
        put(on_room, spread(rest, free), "repair")
    elif vol:
        put(on_comp, spread(rest, {k: v for k, v in vol.items() if role(k) != "director"} or vol),
            "repair")
    return dict(components=on_comp, rooms=on_room, summary=summary)


def assign_battle_crew(lay, sub):
    """battle_crew on the rooms and cells where the complement stands at battle stations (battle_stations; a room's
    men are spread over the cells it owns by volume), and its summary in the report's crew (battle_stations).
    Returns the men on the components: {(kind, id): men}, for the hitboxes."""
    st = battle_stations(lay, sub)
    cells = {c["id"]: c for c in sub["cells"]}
    for r in sub["rooms"]:
        men = st["rooms"].get(r["id"])
        if men:
            r["battle_crew"] = men
            own = {cid: cells[cid]["volume_m3"] for cid in r["cells"] if cells[cid]["room"] == r["id"]}
            for cid, m in spread(men, own).items():
                cells[cid]["battle_crew"] = m
    if lay.crew is not None and st["summary"]:
        lay.crew["battle_stations"] = st["summary"]
    return st["components"]
