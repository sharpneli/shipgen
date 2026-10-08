"""
carrier: aircraft carriers, from seaplane carriers to angled-deck fleet carriers.

    "aviation": {
        "flight_deck": "axial" | "angled" | "none",   none = seaplane carrier: hangar aft, cranes, catapults
        "aircraft": 90, "aircraft_t": 6.0,             air group size and typical aircraft mass (t)
        "hangar_decks": 1,                             flight deck height = hangar decks x 5.6 m + 2 m gallery
        "elevators": 2, "deck_edge_elevators": 1, "catapults": 2, "cranes": 0
    }
    "armour": {"belt_mm", "decks" (deck 0 is the hangar deck), "flight_deck_mm"}

The main deck is the hangar deck; heights in hitboxes are above it, like every other style. A carrier has no
main battery: its guns are secondaries fitted where they suit, "ends" on the flight deck in line with the
island (Lexington, Essex) and "sides" on sponsons outboard of the deck edges, with torpedo mounts and AA.

Aircraft capacity = (hangar area x 0.85 x decks + flight deck area x 0.30) / spot, where spot (m^2 per
aircraft) = SPOT_K x aircraft_t^(2/3): about 66 m^2 for a 6 t WWII aircraft, 150 m^2 for a 20 t jet.
"""
from __future__ import annotations

import math

import armament
import firecontrol
import hullweight
import ordnance
from geometry import polygon_area, polygon_y_span
from layout import (LEVEL_H, Layout, _fp_circle, _fp_rect, add_block, add_funnel_weights, add_machinery_rooms,
                    add_steering, clamp, finish_layout, funnel_seg, hull_spec, mast_weight, plan_funnels, plan_machinery, roof_spots,
                    set_citadel, stack_machinery, tower_levels)
from weights import STEEL, Weight
from geometry import AA_CFG, Hull
from styles.base import Style

HANGAR_H = 5.6      # clear height of one hangar deck, metres
GALLERY_H = 2.0     # gallery deck between the hangar roof and the flight deck
SPOT_K = 20.0       # deck area per aircraft = SPOT_K * aircraft_t^(2/3) m^2
ANGLE_DEG = 9.0     # angled landing area, degrees to port

DEFAULTS = {"axial": dict(elevators=2, deck_edge_elevators=1, catapults=1, cranes=0),
            "angled": dict(elevators=0, deck_edge_elevators=4, catapults=4, cranes=0),
            "none": dict(elevators=0, deck_edge_elevators=0, catapults=1, cranes=2)}


def aviation(design):
    a = design.get("aviation") or {}
    kind = a.get("flight_deck", "axial")
    return {"flight_deck": kind, "aircraft": 0, "aircraft_t": 5.0, "hangar_decks": 1, "hangar": "open",
            **DEFAULTS.get(kind, {}), **a}


def closed(design):
    """A closed hangar: the flight deck is the hull's strength deck, and the hangar sides are its shell."""
    return aviation(design)["hangar"] == "closed" and aviation(design)["flight_deck"] != "none"


def spot_m2(av):
    return SPOT_K * av["aircraft_t"] ** (2 / 3)


def _vdc(n):
    """0, 1/2, 1/4, 3/4, 1/8, ...: positions that spread evenly however many get used."""
    out = []
    for i in range(n):
        k, d, v = i, 2, 0.0
        while k:
            v += (k & 1) / d
            k >>= 1
            d *= 2
        out.append(v)
    return out


def deck_plan(design):
    """Flight deck and hangar geometry, from the design alone (so navarch and the layout agree)."""
    av = aviation(design)
    L, B = design["hull"]["length"], design["hull"]["beam"]
    kind = av["flight_deck"]
    if kind == "none":
        hx0, hx1, hhw = -0.30 * L, -0.02 * L, 0.36 * B
        deck_x0 = -L / 2 + 0.03 * L
        hangar_area = (hx1 - hx0) * 2 * hhw
        park_area = (hx0 - deck_x0) * 0.7 * B
        return dict(kind=kind, fd_h=0.0, hangar=(hx0, hx1, hhw), hangar_area=hangar_area, fd_area=0.0,
                    park=(deck_x0, hx0), capacity=int((hangar_area * 0.85 + park_area * 0.5) / spot_m2(av)))
    fd_h = HANGAR_H * av["hangar_decks"] + GALLERY_H
    x0, x1 = -L / 2 - 0.02 * L, L / 2 - 0.03 * L
    tap, hw = 0.06 * L, 0.6 * B
    port = [(x0, -0.9 * hw), (x0 + 3, -hw)]
    land = None
    if kind == "angled":
        th = math.radians(ANGLE_DEG)
        c, s = math.cos(th), math.sin(th)
        wl = 1.4 * hw                       # landing area width
        p0 = (x0, 0.1 * hw)                 # landing centreline at the round-down
        ll = 0.62 * (x1 - x0)               # landing area length
        d, n = (c, -s), (-s, -c)            # along the landing area; its port normal

        def q(t, off=wl / 2):
            return (p0[0] + off * n[0] + t * d[0], p0[1] + off * n[1] + t * d[1])
        t1 = (p0[1] - c * wl / 2 + hw) / s
        e = q(ll)
        f = (e[0] + (abs(e[1]) - hw) * 0.8, -hw)
        port += [q(t1), e, f]
        land = dict(p0=p0, d=d, n=n, length=ll, width=wl, end=e, corner=f)
    port += [(x1 - tap, -hw), (x1, -0.45 * hw)]
    stbd = [(x1, 0.45 * hw), (x1 - tap, hw), (x0 + 3, hw), (x0, 0.9 * hw)]
    pts = port + stbd
    hx0, hx1, hhw = -0.40 * L, 0.32 * L, 0.4 * B
    hangar_area = (hx1 - hx0) * 2 * hhw
    fd_area = polygon_area(pts)
    cap = int((hangar_area * 0.85 * av["hangar_decks"] + fd_area * 0.30) / spot_m2(av))
    return dict(kind=kind, fd_h=fd_h, x0=x0, x1=x1, tap=tap, hw=hw, points=pts, land=land,
                hangar=(hx0, hx1, hhw), hangar_area=hangar_area, fd_area=fd_area, capacity=cap)


def _edges(dp, x):
    """(port edge y, starboard edge y) of the flight deck at x."""
    span = polygon_y_span(dp["points"], x)
    return span if span else (-dp["hw"], dp["hw"])


def _flight_deck_drawing(dp, av, L):
    """Renderer spec for the flight deck (see shipgen.flight_deck_spec)."""
    x0, x1, tap, hw = dp["x0"], dp["x1"], dp["tap"], dp["hw"]
    marks, wires = [], []
    ys = [y for _, y in dp["points"]]
    lc = clamp(12 + 2.8 * av["aircraft_t"], 20, 85)     # catapult length grows with aircraft mass
    land = dp["land"]
    if land:
        (px, py), (dx, dy), (nx, ny), ll, wl = land["p0"], land["d"], land["n"], land["length"], land["width"]

        def at(t, off=0.0):
            return px + off * nx + t * dx, py + off * ny + t * dy
        a, b = at(8), at(ll - 5)
        marks.append(dict(x1=a[0], y1=a[1], x2=b[0], y2=b[1], color="marking", width=0.5, dash="5 5"))
        for off in (wl / 2 - 1.0, -wl / 2 + 1.0):
            a, b = at(2, off), at(ll - 2, off)
            marks.append(dict(x1=a[0], y1=a[1], x2=b[0], y2=b[1], color="marking", width=0.35, opacity=0.85))
        for k in range(4):
            t = ll * (0.10 + 0.04 * k)
            a, b = at(t, wl / 2 - 2), at(t, -wl / 2 + 2)
            wires.append((a[0], a[1], b[0], b[1]))
        marks.append(dict(x1=land["corner"][0], y1=0, x2=x1 - 4, y2=0, color="marking", width=0.5, dash="5 5"))
        marks.append(dict(x1=x0 + 1.5, y1=hw - 1.0, x2=x1 - tap, y2=hw - 1.0, color="marking", width=0.35,
                          opacity=0.85))
    else:
        marks.append(dict(x1=x0 + 4, y1=0, x2=x1 - 4, y2=0, color="marking", width=0.5, dash="5 5"))
        for side in (-1, 1):
            marks.append(dict(x1=x0 + 1.5, y1=side * (hw - 1.0), x2=x1 - tap, y2=side * (hw - 1.0),
                              color="marking", width=0.35, opacity=0.85))
        for k in range(8):
            wx = x0 + (x1 - x0) * (0.06 + 0.02 * k)
            wires.append((wx, -hw + 2, wx, hw - 2))
    for i in range(6):   # round-down stripes
        sx = x0 + 0.8 + i * 1.6
        marks.append(dict(x1=sx, y1=-0.9 * hw + 1.5, x2=sx, y2=0.9 * hw - 1.5, color="stripe", width=0.7,
                          opacity=0.9 if i % 2 == 0 else 0))
    for k in range(min(av["catapults"], 4 if land else 2)):
        if k < 2:   # bow catapults
            y = (-0.22 if k == 0 else 0.22) * hw
            marks.append(dict(x1=x1 - 0.6 * tap, y1=y, x2=x1 - 0.6 * tap - lc, y2=y, color="track", width=0.6))
        else:       # waist catapults on the angled deck
            off = wl / 2 - 6 - 7 * (k - 2)
            a, b = at(ll - 10, off), at(ll - 10 - lc, off)
            marks.append(dict(x1=a[0], y1=a[1], x2=b[0], y2=b[1], color="track", width=0.6))
    return dict(points=dp["points"], planks=dict(x0=x0, x1=x1, y0=min(ys), y1=max(ys), step=1.4),
                elevators=[], edge_elevators=[], wires=wires, marks=marks,
                number=dict(x=x1 - 0.6 * tap - lc - 0.04 * L, y=0, text=str(av.get("number", "")), size=0.035 * L)
                if av.get("number") else None)


def guns_are_secondaries(style, design):
    """Carriers and merchants are built around something else; guns are fitted where they suit."""
    errs = []
    if design.get("main"):
        errs.append(f"The {style.name} style has no main battery: its guns are secondaries fitted where they suit. "
                "Give them as \"secondary\": a battery or a list of batteries, each with \"count\" (or "
                "\"per_side\") and \"where\": \"ends\" or \"sides\".")
    return errs + [f"secondary.where = {b['where']!r}: use ends or sides" for b in armament.batteries(design)
            if b["where"] not in ("ends", "sides")]


SECONDARY_LIMITS = {}   # carriers and merchants take the common (wide) secondary limits


class Carrier(Style):
    name = "carrier"
    SECONDARY_LIST = True
    MIN_TOWER = 3            # the island (or the seaplane carrier's bridge) up to its bridge level
    LIMITS = {**SECONDARY_LIMITS,("hull", "block_coefficient"): (0.45, 0.76),
              ("aviation", "aircraft"): (0, 160), ("aviation", "aircraft_t"): (0.5, 35),
              ("aviation", "hangar_decks"): (1, 2), ("aviation", "elevators"): (0, 4),
              ("aviation", "deck_edge_elevators"): (0, 4), ("aviation", "catapults"): (0, 4),
              ("aviation", "cranes"): (0, 4), ("armour", "flight_deck_mm"): (0, 100)}

    SIZE = {**Style.SIZE, "lb_max": 9.5}

    def validate(self, design):
        kind = aviation(design)["flight_deck"]
        hangar = aviation(design)["hangar"]
        return super().validate(design) + guns_are_secondaries(self, design) + (
            [] if kind in DEFAULTS else [f"aviation.flight_deck = {kind!r}: use axial, angled or none"]) + (
            [] if hangar in ("open", "closed") else [f"aviation.hangar = {hangar!r}: use open or closed"])

    def strength_deck(self, design, D):
        if not closed(design):
            return None
        fd_h, mm = deck_plan(design)["fd_h"], (design.get("armour") or {}).get("flight_deck_mm", 0)
        return dict(h=fd_h, decks=aviation(design)["hangar_decks"], plates=[(mm, D + fd_h)] if mm else [])

    def tuning(self, design):
        # the main deck is the hangar deck, well above a warship's main deck, so the hull's own centre of
        # gravity sits lower in that depth
        return dict(super().tuning(design), freeboard_a=0.024, freeboard_b=2.5, misc_frac=0.075, hull_z_frac=0.5,
                    flight_deck_t_per_m2=0.34, hangar_t_per_m2=0.32)

    def build_layout(self, design, res, shift=0.0, spread=0.0):
        if aviation(design)["flight_deck"] == "none":
            return _seaplane_layout(design, res, shift)
        return _flight_deck_layout(design, res, shift)

    def rough_payload(self, design, D):
        L = design["hull"]["length"]
        return [Weight("Island", "superstructure", 0.006 * L ** 2, z_rel=("deck", deck_plan(design)["fd_h"] + 4))]

    def weather_deck(self, design, L, B):
        """A carrier's weather deck is its flight deck (Essex and the escort carriers: wooden ones)."""
        dp = deck_plan(design)
        if dp["kind"] == "none":
            return super().weather_deck(design, L, B)
        return dp["fd_area"], (dp["x0"] + dp["x1"]) / 2, dp["fd_h"]

    def structure_weights(self, design, L, B, T, D, geo, tun):
        dp, av = deck_plan(design), aviation(design)
        m = av["aircraft_t"]
        hx0, hx1, _ = dp["hangar"]
        out = []
        if dp["kind"] != "none":
            fdx = (dp["x0"] + dp["x1"]) / 2
            # a closed hangar's flight deck is the hull's strength deck (hullweight.hull_structure), whose plating the
            # hull already weighs: here only the rest (the beams that span the hangar, the overhang). Its sides are
            # the hull's shell; the hangar's own structure (gallery deck, pillars, fire curtains) stays.
            fd_t = dp["fd_area"] * tun["flight_deck_t_per_m2"]
            if closed(design):
                fd_t = max(0.0, fd_t - hullweight.deck_area(L, B, design["hull"]["block_coefficient"])
                           * hullweight.deck_t_per_m2(L, hullweight.construction(design)))
            out.append(Weight("Flight deck", "hull", fd_t, x=fdx, z_rel=("deck", dp["fd_h"])))
            mm = (design.get("armour") or {}).get("flight_deck_mm", 0)
            if mm:
                out.append(Weight("Flight deck armour", "armour", dp["fd_area"] * 0.85 * mm / 1000 * STEEL, x=fdx,
                                  z_rel=("deck", dp["fd_h"])))
            out.append(Weight("Hangar structure", "hull",
                              dp["hangar_area"] * av["hangar_decks"] * tun["hangar_t_per_m2"], x=(hx0 + hx1) / 2,
                              z_rel=("deck", dp["fd_h"] / 2)))
            n_el = av["elevators"] + av["deck_edge_elevators"]
            if n_el:
                out.append(Weight("Elevators", "aviation", n_el * (8 + 3 * m), x=(hx0 + hx1) / 2,
                                  z_rel=("deck", dp["fd_h"] - 1)))
            out.append(Weight("Arresting gear", "aviation", 30 + 2 * m, x=dp["x0"] + 0.15 * (dp["x1"] - dp["x0"]),
                              z_rel=("deck", dp["fd_h"] - 1)))
            if av["catapults"]:
                out.append(Weight("Catapults", "aviation", av["catapults"] * (15 + 3 * m), x=0.3 * L,
                                  z_rel=("deck", dp["fd_h"] - 1)))
        else:
            if av["cranes"]:
                out.append(Weight("Aircraft cranes", "aviation", av["cranes"] * (15 + 2 * m), x=hx0,
                                  z_rel=("deck", 4)))
            if av["catapults"]:
                out.append(Weight("Catapults", "aviation", av["catapults"] * (10 + 2 * m), x=(dp["park"][0] + hx0) / 2,
                                  z_rel=("deck", 1)))
        return out

    def payload_weights(self, design, L, D, geo, tun, ctx):
        av, dp = aviation(design), deck_plan(design)
        n, m = av["aircraft"], av["aircraft_t"]
        if not n:
            return [], []
        hx0, hx1, _ = dp["hangar"]
        return ([Weight("Air group", "aviation", n * m, x=(hx0 + hx1) / 2, z_rel=("deck", max(dp["fd_h"] - 3, 2))),
                 Weight("Aviation ordnance", "aviation", ORDNANCE_K * n * m, x=geo.get("magazine_x", 0.2 * L),
                        z_rel=("deck", geo["magazine_z"]) if "magazine_z" in geo else ("frac", 0.25))],
                [Weight("Aviation fuel", "fuel", AVGAS_K * n * m, x=geo.get("avgas_x", -0.25 * L),
                        z_rel=("deck", geo["avgas_z"]) if "avgas_z" in geo else ("frac", 0.15))])

    def crew_extra(self, design):
        av = aviation(design)
        return {"air_group": round(av["aircraft"] * (6 + 0.75 * av["aircraft_t"]))}

    def results(self, design, lay, r):
        av, dp = aviation(design), deck_plan(design)
        out = dict(aircraft=av["aircraft"], aircraft_capacity=dp["capacity"], hangar_area_m2=round(dp["hangar_area"]),
                   flight_deck=dp["kind"])
        if dp["kind"] != "none":
            ys = [y for _, y in dp["points"]]
            out.update(flight_deck_m=[round(dp["x1"] - dp["x0"], 1), round(max(ys) - min(ys), 1)],
                       flight_deck_height_m=round(r.freeboard + dp["fd_h"], 2))
        return out

    def summary(self, design, lay, r):
        av, dp = aviation(design), deck_plan(design)
        line = f"aviation: {av['aircraft']} aircraft of {av['aircraft_t']:g} t (capacity {dp['capacity']})   "
        if dp["kind"] == "none":
            return [line + f"seaplane carrier, {av['cranes']} cranes, {av['catapults']} catapults"]
        ys = [y for _, y in dp["points"]]
        return [line + f"{dp['kind']} flight deck {dp['x1'] - dp['x0']:.0f} x {max(ys) - min(ys):.0f} m, "
                       f"{av['elevators']} + {av['deck_edge_elevators']} deck-edge elevators, {av['catapults']} catapults"]


# ---------------------------------------------------------------------------
# layouts
# ---------------------------------------------------------------------------
def _common(design, shp, shift):
    lay = Layout(design)
    hs = hull_spec(design)
    hull = Hull(hs)
    lay.hull = hull
    lay.shift_range = (-0.04 * hull.L, 0.04 * hull.L)
    shift = clamp(shift, *lay.shift_range)
    lay.geo["shift"] = shift
    return lay, hs, hull, shift


def _check_capacity(lay, av, dp):
    if av["aircraft"] > dp["capacity"]:
        lay.fail("length", f"Air group of {av['aircraft']} does not fit: the hangar and deck park hold about "
                           f"{dp['capacity']} aircraft of {av['aircraft_t']:g} t. Add a hangar deck, or carry fewer or "
                           "smaller aircraft.")



def _machinery(lay, design, res, hull, mc):
    """Plan the machinery block centred at mc. It has to fit in the middle half of the hull."""
    L_mach = plan_machinery(lay, design, res, hull, mc)
    if L_mach > 0.5 * hull.L:
        lay.fail("length", f"The machinery needs {L_mach:.0f} m, more than half the hull. Use less power or a more "
                           "compact plant.")
    lay.geo["machinery"] = (mc - L_mach / 2, mc + L_mach / 2)
    lay.geo["machinery_x"] = mc
    return L_mach


def _machinery_rooms(lay, hull, res):
    m0, m1 = lay.geo["machinery"]
    add_machinery_rooms(lay, stack_machinery(lay.geo["plant"]["segments"], m1), 0.8 * hull.B / 2, res.depth)


ORDNANCE_K = 0.6    # aviation ordnance (bombs, torpedoes, rockets), tonnes per tonne of air group
AVGAS_K = 1.2       # aviation fuel, tonnes per tonne of air group
AVGAS_T_PER_M3 = 0.5   # avgas tanks: petrol at 0.72 t/m3 with the void and water-filled spaces around the tanks


def _compartments(lay, design, hull, mach, hangar, mounts, extra=()):
    av = aviation(design)
    L, B = hull.L, hull.B
    m0, m1 = mach
    cit = (m0 - 0.06 * L, m1 + 0.08 * L)
    set_citadel(lay, *cit)
    inner_hw = 0.8 * B / 2
    hx0, hx1, hhw = hangar
    # what burns or blows up stands low (ordnance.stow), under the hangar and the armour deck: the aviation
    # ordnance and the guns' ammunition forward of the machinery, the avgas abaft it
    air_t = av["aircraft"] * av["aircraft_t"]
    st = ordnance.stow(lay, mounts, [
        dict(x0=m1, x1=cit[1], half_width=inner_hw,
             rooms=[dict(id="Aviation magazines", tonnes=ORDNANCE_K * air_t),
                    dict(id="Gun magazines", mounts=ordnance.guns(mounts))]),
        dict(x0=cit[0], x1=m0, half_width=inner_hw,
             rooms=[dict(id="Aviation fuel", kind="fuel_tank", tonnes=AVGAS_K * air_t, t_per_m3=AVGAS_T_PER_M3)])])
    for key, rid in (("magazine", "Aviation magazines"), ("avgas", "Aviation fuel")):
        if rid in st:
            x0, x1, base, top = st[rid]
            lay.geo[f"{key}_x"], lay.geo[f"{key}_z"] = (x0 + x1) / 2, (base + top) / 2
    lay.compartments += [
        dict(id="Hangar", kind="hangar", x0=hx0, x1=hx1, half_width=hhw, base=0.0,
             top=2 * LEVEL_H if av["flight_deck"] == "none" else HANGAR_H * av["hangar_decks"]),
        *extra]
    add_steering(lay)


def _flight_deck_layout(design, res, shift):
    shp, depth = res.power_shp, res.depth
    lay, hs, hull, shift = _common(design, shp, shift)
    L, B = hull.L, hull.B
    av, dp = aviation(design), deck_plan(design)
    fd_h, hw = dp["fd_h"], dp["hw"]
    armour = design.get("armour") or {}
    _check_capacity(lay, av, dp)
    lay.decks.append(dict(id="Flight deck", kind="flight_deck", points=dp["points"], base=fd_h - 1.0, top=fd_h))
    fd = _flight_deck_drawing(dp, av, L)

    # ---------------- island: on the starboard deck edge, funnel uptakes at its after end ----------------
    mc = -0.04 * L + shift
    _machinery(lay, design, res, hull, mc)
    li = clamp(0.11 * L, 8, 36)
    wi = clamp(0.3 * B, 4, 10)
    nfun, fw, fl = plan_funnels(lay, design, res, B, fd_h + LEVEL_H * 4 + 3.0)
    fw = min(fw, wi - 1.0)
    fl = min(fl, 0.45 * li / nfun)
    wi = max(wi, fw + 1.2)
    xi = 0.05 * L + shift
    yi = hw - wi / 2 - 0.3
    blocks, funnels = [], []
    ix0, ix1 = xi - li / 2, xi + li / 2
    add_block(lay, blocks, "Island", ix0, ix1, wi, 1, 1.5, 1.0, y=yi, z0=fd_h)
    fwd0 = ix0 + nfun * (fl + 1.0) + 1.0          # the tower stands ahead of the funnel(s)
    add_block(lay, blocks, "Island upper", fwd0, ix1 - 0.5, 0.85 * wi, 2, 1.2, 0.8, y=yi, z0=fd_h)
    add_block(lay, blocks, "Bridge", fwd0 + 0.2 * (ix1 - fwd0), ix1 - 0.3, 0.9 * wi, 3, 0.4 * wi, 0.6, y=yi, z0=fd_h)
    top_level = tower_levels(design, 4 if L >= 200 else 3)    # the old built-in rule as the default
    for k in range(4, top_level + 1):     # the island's tower narrows as it rises
        f = min(0.12, 0.03 * (k - 4))
        add_block(lay, blocks, f"Island tower {k}", fwd0 + (0.4 + f) * (ix1 - fwd0),
                  max(fwd0 + (0.4 + f) * (ix1 - fwd0) + 3.0, ix1 - (0.25 + f) * (ix1 - fwd0)),
                  max(3.0, 0.45 * wi * 0.9 ** (k - 4)), k, 0.2 * wi, 0.2 * wi, y=yi, z0=fd_h)
    fun_top = fd_h + LEVEL_H * min(top_level, 4) + 3.0
    for i in range(nfun):
        fx = ix0 + 1.0 + (i + 0.5) * (fl + 1.0)
        funnels.append(dict(id=f"Funnel {i + 1}", x=fx, y=yi, l=fl, w=fw, pipes=2 if fw > 4 else 1, z0=fd_h,
                            seg=funnel_seg(lay, i)))
        lay.occupy(_fp_rect(fx - fl / 2, yi - fw / 2, fx + fl / 2, yi + fw / 2), fd_h, fun_top, f"Funnel {i + 1}")
        add_funnel_weights(lay, funnels[-1], fun_top, mc, res.depth)
    masts = [dict(x=fwd0 - 0.5, y=yi, yard=min(0.6 * wi, 6), tripod=False,
                  top=max(fun_top + 5.0, fd_h + LEVEL_H * top_level + firecontrol.HOOD_H + 2.0))]
    mast_weight(lay, masts[0], masts[0]["top"], "Mast")

    mounts, turret_types = [], {}
    island_guns = any(b["where"] == "ends" or b["count"] % 2 for b in armament.batteries(design))

    # ---------------- elevators ----------------
    hx0, hx1, hhw = dp["hangar"]
    le, ew = clamp(0.055 * L, 10, 18), min(clamp(0.45 * 2 * hw, 10, 18), 0.9 * hw)
    for k in range(av["elevators"]):
        ex = hx1 - le / 2 - 2 - k * (hx1 - hx0 - le - 4) / max(av["elevators"] - 1, 1)
        fd["elevators"].append(dict(x=ex, y=-0.1 * hw, l=le, w=ew))
    lee, wee = clamp(0.06 * L, 10, 20), clamp(0.045 * L, 6, 16)
    land = dp["land"]
    slots = [(ix1 + lee / 2 + 3, 1), (ix0 - lee / 2 - 3, 1),
             ((land["end"][0] - lee / 2 - 3) if land else xi, -1), (ix0 - 1.5 * lee - 8, 1)]
    if island_guns:   # guns fore and aft of the island: keep the starboard deck edge there free
        slots = [slots[2], slots[1], slots[3], slots[0]]
    placed = 0
    for ex, side in slots:
        if placed >= av["deck_edge_elevators"]:
            break
        edge = _edges(dp, ex)[0 if side < 0 else 1]
        y_in, y_out = edge - side * 0.5, edge + side * (wee - 0.5)
        fp = _fp_rect(ex - lee / 2, min(y_in, y_out), ex + lee / 2, max(y_in, y_out))
        if not lay.free(fp, 0.5):
            continue
        eid = f"Deck-edge elevator {placed + 1}"
        lay.occupy(fp, fd_h - 1.0, fd_h, eid)
        yc = (y_in + y_out) / 2
        fd["edge_elevators"].append(dict(x=ex, y=yc, l=lee, w=wee))
        lay.sponsons.append(dict(id=eid, points=[(ex - lee / 2, y_in), (ex + lee / 2, y_in), (ex + lee / 2, y_out),
                                                 (ex - lee / 2, y_out)], base=fd_h - 1.0, top=fd_h))
        placed += 1
    if placed < av["deck_edge_elevators"]:
        lay.fail("length", f"Only {placed} of {av['deck_edge_elevators']} deck-edge elevators fit.")

    # ---------------- sponsons: secondaries, torpedo mounts and AA outboard of the deck edges ----------------
    xs = [dp["x0"] + 6 + v * (dp["x1"] - dp["tap"] - 10 - dp["x0"]) for v in _vdc(64)]

    def sponson_slots(reach, base):
        out = []
        for x in xs:
            pe, se = _edges(dp, x)
            out.append((x, se + reach + 0.3, base, pe - reach - 0.3))
        return out

    # guns: "ends" on the flight deck in line with the island (fore, aft), "sides" on sponsons
    on_fd = lambda x: fd_h
    armament.place_batteries(
        lay, mounts, turret_types, design,
        [(ix1 + 1.0, +1, yi, 0, on_fd, ()), (ix0 - 1.0, -1, yi, 180, on_fd, ())],
        lambda t: sponson_slots(armament.body_reach(t), fd_h - armament.turret_height(t) - 0.3), depth=depth)
    tp = design.get("torpedoes") or {}
    if tp.get("mounts"):
        tt_id, tt = armament.torpedo_type(tp)
        n = (tp["mounts"] + 1) // 2
        armament.side_pairs(lay, mounts, turret_types, "torpedo", tt_id, tt, n,
                            sponson_slots(tt["barrel_len"] / 2 + 0.3, fd_h - 2.5), "T", label="Torpedo")
    firecontrol.place(lay, design, blocks)
    aa_out = []
    aa_req = design.get("aa") or {}
    for kind, count in (("quad40", aa_req.get("heavy", 0)), ("single20", aa_req.get("light", 0))):
        rr = AA_CFG[kind][0]      # tubs on the island's roofs first (Essex), then sponsons along the deck edges
        island = [(x, y, z0, None) for x, y, z0, pair in sorted(roof_spots(blocks, 2 * rr, 2 * rr),
                                                                key=lambda s: (s[2], abs(s[0] - xi))) if not pair]
        armament.place_aa(lay, aa_out, kind, count, island + sponson_slots(rr, fd_h - 2.4),
                          layer_of=lambda base: "upper" if base > fd_h + 0.01 else "base")
    sponsons = []
    for it in [m for m in mounts if m["base"] < fd_h - 0.5] + aa_out:
        reach = AA_CFG[it["type"]][0] if "dir" in it else (
            armament.body_reach(it["t"]) if it["kind"] != "torpedo" else it["t"]["barrel_len"] / 2 + 0.3)
        pe, se = _edges(dp, it["x"])
        side = 1 if it["y"] > 0 else -1
        edge = se if side > 0 else pe
        y_in, y_out = edge - side * 0.8, it["y"] + side * (reach + 0.5)
        l = 2 * reach + 1.0
        sponsons.append(dict(x=it["x"], y=(y_in + y_out) / 2, l=l, w=abs(y_out - y_in)))
        lay.sponsons.append(dict(id=f"Sponson {it['id']}", points=[
            (it["x"] - l / 2, y_in), (it["x"] + l / 2, y_in), (it["x"] + l / 2, y_out), (it["x"] - l / 2, y_out)],
            base=it["base"] - 0.5, top=it["base"]))

    # ---------------- machinery and compartments ----------------
    _machinery_rooms(lay, hull, res)
    _compartments(lay, design, hull, lay.geo["machinery"], dp["hangar"], mounts)
    return finish_layout(lay, design, hs, mounts, turret_types, blocks, funnels, masts, aa_out, fun_top,
                   flight_deck=fd, sponsons=sponsons, boats=[])


def _seaplane_layout(design, res, shift):
    shp, depth = res.power_shp, res.depth
    """Seaplane carrier: guns forward, bridge, funnels over the machinery, a hangar aft opening onto an
    aircraft deck over the stern with catapults, and cranes that lift the seaplanes in and out."""
    lay, hs, hull, shift = _common(design, shp, shift)
    L, B = hull.L, hull.B
    av, dp = aviation(design), deck_plan(design)
    armour = design.get("armour") or {}
    _check_capacity(lay, av, dp)
    blocks, funnels, mounts, turret_types = [], [], [], {}
    hx0, hx1, hhw = dp["hangar"]
    hx0, hx1 = hx0 + shift, hx1 + shift
    add_block(lay, blocks, "Hangar", hx0, hx1, 2 * hhw, 1, 1.0, 0.5)
    add_block(lay, blocks, "Hangar roof", hx0, hx1, 2 * hhw, 2, 1.0, 0.5)
    hangar_ids = ("Hangar", "Hangar roof")
    roof = 2 * LEVEL_H

    # bridge and funnels between the hangar and the forward guns
    bx1 = 0.24 * L + shift
    lb = clamp(0.07 * L, 7, 16)
    bx0 = bx1 - lb
    wb = clamp(0.5 * B, 4.5, 12)
    add_block(lay, blocks, "Bridge base", bx0, bx1, wb, 1, 0.3 * wb, 1.0)
    add_block(lay, blocks, "Bridge", bx0 + 0.15 * lb, bx1, 0.85 * wb, 2, 0.4 * wb, 1.0)
    add_block(lay, blocks, "Bridge upper", bx0 + 0.35 * lb, bx1 - 0.05 * lb, 0.7 * wb, 3, 0.3 * wb, 0.8)
    n_tower = tower_levels(design, 3)
    for k in range(4, n_tower + 1):      # a taller tower narrows as it rises
        f, tw = min(0.12, 0.03 * (k - 4)), max(3.0, 0.5 * wb * 0.9 ** (k - 4))
        add_block(lay, blocks, f"Tower {k}", bx0 + (0.45 + f) * lb, max(bx0 + (0.45 + f) * lb + 3.0,
                                                                      bx1 - (0.15 + f) * lb), tw, k, 0.5 * tw, 0.5 * tw)
    fun_top = LEVEL_H * min(n_tower, 4) + 3.0
    mc = (hx1 + bx0) / 2
    _machinery(lay, design, res, hull, mc)
    nfun, fw, fl = plan_funnels(lay, design, res, B, fun_top)
    fw = min(fw, 0.3 * B)
    room = bx0 - hx1 - 2.0
    if room < nfun * (fl + 1.0):
        lay.fail("length", f"No room for {nfun} funnel(s) between the bridge and the hangar.")
    for i in range(nfun):
        fx = hx1 + 1.0 + (i + 0.5) * room / nfun
        funnels.append(dict(id=f"Funnel {i + 1}", x=fx, y=0.0, l=fl, w=fw, pipes=2 if fw > 4 else 1,
                            seg=funnel_seg(lay, i)))
        lay.occupy(_fp_rect(fx - fl / 2, -fw / 2, fx + fl / 2, fw / 2), 0, fun_top, f"Funnel {i + 1}")
        add_funnel_weights(lay, funnels[-1], fun_top, mc, res.depth)
    masts = [dict(x=bx0 - 1.0, yard=min(0.3 * B, 8), tripod=False)]
    if LEVEL_H * n_tower + firecontrol.HOOD_H + 2.0 > fun_top + 6.0:    # a tall tower: the mast tops it
        masts[0]["top"] = LEVEL_H * n_tower + firecontrol.HOOD_H + 2.0
    mast_weight(lay, masts[0], masts[0].get("top", fun_top + 6.0), "Mast")

    # aircraft deck: catapults and cranes
    park0, _ = dp["park"]
    fittings, cranes = [], []
    lc = clamp(0.5 * (hx0 - park0), 8, 25)
    ncat = av["catapults"]
    for k in range(ncat):
        y = 0.0 if ncat == 1 else (k / (ncat - 1) - 0.5) * 0.5 * B
        cx = (park0 + hx0) / 2
        fittings.append(dict(x=cx, y=y, l=lc, w=1.0, color="track"))
        lay.occupy(_fp_rect(cx - lc / 2, y - 0.8, cx + lc / 2, y + 0.8), 0, 1.5, f"Catapult {k + 1}")
    jib = clamp(0.09 * L, 8, 16)
    crane_slots = [(hx0 - 2.5, hhw - 1.0, 135), (hx0 - 2.5, -(hhw - 1.0), -135), (park0 + 3, 0.0, 180),
                   (hx1 + 2.0, hhw, 45)]
    for k in range(min(av["cranes"], 4)):
        cx, cy, d = crane_slots[k]
        cranes.append(dict(x=cx, y=cy, r=1.4, dir=d, jib=jib, top=roof + 6.0))
        lay.occupy(_fp_circle(cx, cy, 1.6), 0, roof + 6.0, f"Crane {k + 1}")

    # guns: "ends" on the forecastle and the hangar roof, "sides" along the main deck
    xs = [hx0 + v * (bx1 - hx0) for v in _vdc(48)]
    armament.place_batteries(
        lay, mounts, turret_types, design,
        [(L / 2 - 0.08 * L, -1, 0.0, 0, lambda x: 0.3, ()), (hx0 + 0.5, +1, 0.0, 180, lambda x: roof, hangar_ids)],
        lambda t: [(x, hull.half_width(x) - armament.body_reach(t) - 0.6, 0.0) for x in xs], depth=depth)
    tp = design.get("torpedoes") or {}
    if tp.get("mounts"):
        tt_id, tt = armament.torpedo_type(tp)
        r = tt["barrel_len"] / 2 + 0.3
        armament.side_pairs(lay, mounts, turret_types, "torpedo", tt_id, tt, (tp["mounts"] + 1) // 2,
                            [(x, hull.half_width(x) - r - 0.4, 0.3) for x in xs], "T", label="Torpedo")
    firecontrol.place(lay, design, blocks)
    aa_out = []
    aa_req = design.get("aa") or {}
    for kind, count in (("quad40", aa_req.get("heavy", 0)), ("single20", aa_req.get("light", 0))):
        rr = AA_CFG[kind][0]
        cands = [(hx0 + v * (hx1 - hx0), hhw - rr - 0.3, roof) for v in _vdc(24)]
        cands += [(x, hull.half_width(x) - rr - 0.5, 0.0) for x in xs]
        armament.place_aa(lay, aa_out, kind, count, cands, ignore=hangar_ids)

    boats = []
    bl_ = clamp(0.03 * L, 4, 8)
    for x in [(hx1 + bx0) / 2 + k * 2.0 for k in range(-4, 5)]:
        y = 0.5 * B - 0.35 * bl_ - 1.0
        fps = [_fp_rect(x - bl_ / 2, s * y - 0.15 * bl_, x + bl_ / 2, s * y + 0.15 * bl_) for s in (1, -1)]
        if y > fw / 2 + 0.3 * bl_ and all(lay.free(fp, 0.3) for fp in fps):
            for s, fp in zip((1, -1), fps):
                boats.append(dict(x=x, y=s * y, l=bl_, w=0.3 * bl_))
                lay.occupy(fp, LEVEL_H, LEVEL_H + 1.5, f"Boat{len(boats)}")
            break

    _machinery_rooms(lay, hull, res)
    _compartments(lay, design, hull, lay.geo["machinery"], (hx0, hx1, hhw), mounts)
    return finish_layout(lay, design, hs, mounts, turret_types, blocks, funnels, masts, aa_out, fun_top,
                   fittings=fittings, cranes=cranes, boats=boats,
                   bollards=[L / 2 - 0.05 * L, -L / 2 + 0.06 * L], chain_x=L / 2 - 0.06 * L, hawse_back=0.03 * L + 1.0)


STYLE = Carrier()
