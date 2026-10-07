"""
hitbox: fixed firing arcs, and hitbox export.

Hitboxes use the layout's components: exact shapes in ship-local metres plus base and top heights
above the main deck. They describe the ship only (where things are, what armours them, what links to what);
what a hit does is the game's business.

Firing arcs are fixed by the kind of mount, not computed from what stands around it, so the player only
picks counts and calibres. Every arc is centred on the mount's rest bearing (degrees clockwise from ahead), except
side guns, whose arcs are centred on their own beam while they stow toward the nearer end of the ship, at the edge
of the arc (armament.stow_bearing):
    centreline guns of a forward or after group (rest 0 or 180)   +-ARC_END
    centreline guns with a turret ahead of them: a flush turret
    behind a superfiring one, or an amidships turret               +-ARC_BEAM about each beam
    side mounts: secondaries and sponson guns (stowed fore-and-aft),
    side torpedo mounts (stowed on the beam), wing turrets
    (stowed fore-and-aft)                                         +-ARC_SIDE   (bow to stern, own side)
    cross-deck echelon wing turrets: that, and across the deck      +-ARC_CROSS about the far beam
    casemate guns, in the hull side (stowed along it, at the arc's
    edge toward the nearer end)                                   +-ARC_CASEMATE about their beam
    centreline trainable torpedo mounts                           +-ARC_TORPEDO about each beam
    fixed tubes (MTBs; the boat aims them)                        +-ARC_FIXED about their bearing
"""
from __future__ import annotations

import math
import re

from geometry import rrect_polygon, block_outline, turret_shapes, turret_reach, _wrap180, angle_allowed, nearest_allowed  # noqa: F401
from geometry import AA_CFG, HullForm
import powerplant
import ordnance
import propulsion
import subdivision

ARC_END = 135.0
ARC_SIDE = 90.0
ARC_BEAM = 65.0
# Cross-deck fire (main.cross_deck, echelon pairs only): a second, narrower arc about the far beam. Real ships got
# anything from a blast-limited few tens of degrees (Invincible) to over 100 degrees (German ships with a long
# stagger); +-30 is a gameplay pick: useful on the beam, never toward the ends, and the layout keeps the partner
# turret out of it with an ordinary stagger. The turret trains across through the nearer end of the ship
# (cross_turn), so the layout keeps that turn clear too.
ARC_CROSS = 30.0
ARC_CASEMATE = 60.0
ARC_TORPEDO = 60.0
ARC_FIXED = 1.0

# Turret armour other than the face (the design's turret_mm), as fractions of the face. Roughly Iowa, KGV and
# Bismarck: sides 0.56-0.69, rear 0.5-0.9, roof 0.4-0.43.
TURRET_SIDE, TURRET_REAR, TURRET_ROOF = 0.55, 0.5, 0.4
BARBETTE = 0.8   # barbette armour, fraction of the turret face (as navarch weighs it)

# What a superstructure block is for, by its id with any trailing number and side letter removed.
BLOCK_ROLES = {
    "Bridge": "bridge", "Bridge upper": "bridge", "Bridge base": "bridge", "Charthouse": "bridge",
    "Main director": "director", "Aft director": "director", "Director": "director",
    "Secondary director": "director", "AA director": "director",
    "Tower": "bridge", "Island tower": "island",
    "Aft control": "aft_control", "Aft control upper": "aft_control", "Aft control base": "aft_control",
    "Island": "island", "Island upper": "island",
    "Hangar": "hangar", "Hangar roof": "hangar",
    "Casemate housing": "casemate",
}


def _arc(centre, half):
    """[start, end] clockwise with 0 <= start < 360; end may exceed 360."""
    start = (centre - half) % 360.0
    return [round(start, 1), round(start + 2 * half, 1)]


def mount_arcs(m):
    if m.get("fixed") is not None:
        return [_arc(m["fixed"], ARC_FIXED)]
    own = 90.0 if m["y"] > 0 else 270.0     # a side mount's own beam
    if m.get("casemate"):
        return [_arc(own, ARC_CASEMATE)]
    if m.get("side_mount"):
        return [_arc(own, ARC_SIDE)]
    if m.get("wing"):
        if m.get("cross_deck"):     # own side first, then the cross-deck arc
            return [_arc(own, ARC_SIDE), _arc(own + 180.0, ARC_CROSS)]
        return [_arc(own, ARC_SIDE)]
    if m.get("arc_role") == "beam":
        return [_arc(90.0, ARC_BEAM), _arc(270.0, ARC_BEAM)]
    if m["kind"] == "torpedo" and abs(m["y"]) < 0.5:
        return [_arc(90.0, ARC_TORPEDO), _arc(270.0, ARC_TORPEDO)]
    if abs(abs(_wrap180(m["rest"])) - 90.0) < 1e-6:
        return [_arc(m["rest"], ARC_SIDE)]
    return [_arc(m["rest"], ARC_END)]


def cross_turn(m):
    """A cross-deck wing turret's whole swing [start, end] (end may exceed 360): its own side, the turn across
    the nearer end of the ship (the end it stows toward; the partner turret usually blocks the other way, which
    is never reserved), and the cross-deck arc."""
    own, cross = mount_arcs(m)
    if (m["rest"] % 360.0 < 90.0) == (m["y"] < 0):    # port turning through ahead, starboard through astern
        return [own[0], cross[1] + 360.0 if cross[1] < own[0] else cross[1]]
    return [cross[0], own[1] if own[1] > cross[0] else own[1] + 360.0]


def mount_traverse(m):
    """The one interval [start, end] (end may exceed 360) a mount turns within: its rest bearing and every arc,
    joined the way that's clear. It never passes through the rest of the circle, so the game can train by moving
    the bearing inside it, never wrapping. One arc: the arc (the rest is inside it, or at its edge for a wing
    turret). Two arcs about the beams (side-firing centreline turrets, centreline torpedo mounts): the way through
    the rest bearing, which faces away from the turret ahead or the bridge. Cross-deck wing turrets: cross_turn.
    The layout reserves exactly this (Layout.reserve_sweep)."""
    arcs = mount_arcs(m)
    if m.get("cross_deck"):
        return cross_turn(m)
    if len(arcs) == 1:
        return list(arcs[0])
    rest = (m["fixed"] if m.get("fixed") is not None else m["rest"]) % 360.0
    best = None
    for p, q in ((arcs[0], arcs[1]), (arcs[1], arcs[0])):
        lo, hi = p[0], q[1]
        while hi < lo:
            hi += 360.0
        if hi - lo < 360.0 and (lo <= rest <= hi or lo <= rest + 360.0 <= hi) and (best is None or hi - lo < best[1] - best[0]):
            best = [lo, hi]
    return best


def assign_arcs(lay):
    """Give every mount its fixed arcs (see the module docstring) and wrap its rest bearing to -180..180. The
    layout sets the rest bearing: inside the arcs, except side-firing centreline turrets, which stow
    fore-and-aft (pointing away from the turret they stand behind) and train out before firing, and side guns
    (secondaries, casemates, wing turrets), which stow at the edge of their arc toward the nearer end."""
    for m in lay.mounts:
        m["arcs"] = mount_arcs(m)
        m["traverse"] = mount_traverse(m)
        m["rest"] = _wrap180(m["fixed"] if m.get("fixed") is not None else m["rest"])
    by_id = {m["id"]: m for m in lay.mounts}
    for sm in lay.spec["turrets"]:
        sm["rest"] = by_id[sm["id"]]["rest"]


CONTROL_ROLES = ("bridge", "director", "aft_control")
BASE_BLOCKS = ("Bridge base", "Aft control base")   # offices and cabins under a control position: no view needed


def assign_smoke(lay, res):
    """Control positions in a funnel's smoke (powerplant model, section 6b): a bridge, director or aft control
    standing aft of a funnel, closer than its smoke reach (powerplant.smoke_reach) and lower than the funnel top
    plus 0.3 x the distance. Sets lay.smoke {block id: [funnel ids]} and warns about each."""
    from layout import block_top
    lay.smoke = {}
    if not lay.funnels:
        return
    reach = powerplant.smoke_reach(res.plant, res.power_shp)
    for b in lay.blocks:
        if block_role(b["id"]) not in CONTROL_ROLES or re.sub(r"\s*\d+$", "", b["id"]) in BASE_BLOCKS:
            continue
        hit = smoke_from(lay.funnels, lay.fun_top, reach, b["x1"], block_top(b), b["y"], b["w"])
        if hit:
            lay.smoke[b["id"]] = hit
            lay.warnings.append(f"{b['id']} stands in the smoke of {', '.join(hit)}: poor visibility from it.")


def smoke_from(funnels, fun_top, reach, x1, top, y, w):
    """Ids of the funnels whose smoke blinds a control position whose forward end is at x1, its roof at top and
    its centre at y, w wide: one standing aft of the funnel, closer than reach and lower than the funnel top plus
    0.3 x the distance."""
    hit = []
    for f in funnels:
        d = (f["x"] - f["l"] / 2) - x1
        if 0 <= d < reach and top < fun_top + 0.3 * d and abs(f["y"] - y) < w / 2 + f["w"]:
            hit.append(f["id"])
    return hit


def block_role(bid):
    """A superstructure block's role (BLOCK_ROLES); anything else is a deckhouse."""
    return BLOCK_ROLES.get(re.sub(r"\s*\d+[SP]?$", "", bid), "deckhouse")


def propulsion_components(lay, design, res, form, sub, gear=None):
    """The propulsion train (propulsion.build) as components: shafts (segments from the engine room to the
    propeller), shaft alleys, propellers and rudders, linked both ways to the engine rooms and the steering gear.
    The cells they pass through list them in "through"."""
    D = res.depth
    tr = propulsion.build(lay, design, res, form, gear)
    z = lambda v: round(v - D, 2)
    rect = lambda x0, x1, y, hw: [[round(x0, 3), round(y - hw, 3)], [round(x1, 3), round(y - hw, 3)],
                                  [round(x1, 3), round(y + hw, 3)], [round(x0, 3), round(y + hw, 3)]]
    out = []
    steering = next((c["id"] for c in lay.compartments if c["kind"] == "steering"), None)
    for sh in tr["shafts"]:
        (x0, y, z0), (x1, _, z1) = sh["p0"], sh["p1"]
        out.append(dict(id=sh["id"], kind="shaft", shape="segment", position=sh["position"],
                        p0=[round(x0, 3), round(y, 3), z(z0)], p1=[round(x1, 3), round(y, 3), z(z1)], r=propulsion.SHAFT_R,
                        points=rect(x1, x0, y, propulsion.SHAFT_R),      # its plan, for a broad phase
                        base=z(min(z0, z1) - propulsion.SHAFT_R), top=z(max(z0, z1) + propulsion.SHAFT_R),
                        leaves_hull_x=round(sh["exit_x"], 3), propeller=sh["propeller"],
                        **({"engine_room": sh["engine_room"]} if sh["engine_room"] else {}),
                        **({"alley": sh["alley"]} if sh.get("alley") else {})))
    for a in tr["alleys"]:
        out.append(dict(id=a["id"], kind="shaft_alley", shape="polygon", shaft=a["shaft"],
                        points=rect(a["x0"], a["x1"], a["y"], propulsion.ALLEY_W / 2), base=z(a["base"]),
                        top=z(a["top"])))
    for p in tr["propellers"]:
        r = p["diameter"] / 2
        out.append(dict(id=p["id"], kind="propeller", shape="disc", x=round(p["x"], 3), y=round(p["y"], 3),
                        z=z(p["z"]), diameter_m=round(p["diameter"], 2), position=p["position"], shaft=p["shaft"],
                        points=rect(p["x"] - 0.25 * r, p["x"] + 0.25 * r, p["y"], r), base=z(p["z"] - r),
                        top=z(p["z"] + r)))
    for rd in tr["rudders"]:
        out.append(dict(id=rd["id"], kind="rudder", shape="polygon", x=round(rd["x"], 3), y=round(rd["y"], 3),
                        area_m2=round(rd["area_m2"], 1), points=rect(rd["x0"], rd["x1"], rd["y"], rd["thick"] / 2),
                        base=z(rd["base"]), top=z(rd["top"]), **({"steering": steering} if steering else {})))
    # the links back, and the cells each shaft and alley passes through
    rooms = {r["id"]: r for r in sub["rooms"]}
    for sh in tr["shafts"]:
        if sh["engine_room"] in rooms:
            rooms[sh["engine_room"]].setdefault("shafts", []).append(sh["id"])
    if steering in rooms:
        rooms[steering]["rudders"] = [rd["id"] for rd in tr["rudders"]]
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
            hw = propulsion.ALLEY_W / 2
            if (min(c["x1"], a["x1"]) - max(c["x0"], a["x0"]) > 0.05 and
                    min(c["y1"], a["y"] + hw) - max(c["y0"], a["y"] - hw) > 0.05 and
                    min(c["top"], a["top"] - D) - max(c["base"], a["base"] - D) > 0.05):
                c.setdefault("through", []).append(a["id"])
    return out


def hydrostatics(form, res):
    """The full-load hydrostatics a game needs to settle, trim and heel a flooded ship by added weight: sinkage
    = w / (100 tpc_t) m, trim = w (x - lcf) / (100 mct_tm) cm (+ down by the bow), heel = w y / (Δ gm_t) rad.
    Heights above the main deck. gm_t is the report's (navarch's estimate); gm_l comes from the hull form's
    waterplane with navarch's kb and kg."""
    from navarch import SEAWATER
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


def hull_plating(lay, design, res):
    """The unarmoured plating (hullweight.plates): the hull's from its structure, the superstructure's from the
    design (superstructure.plating_mm, control_mm) over the structure's own gauge."""
    import hullweight
    from layout import own_plate_mm
    sup = design.get("superstructure") or {}
    hp = hullweight.plating(design)
    h = res.hull if "t_min_mm" in res.hull else {**res.hull, "plate_own_mm": own_plate_mm(lay)}
    return hullweight.plates(h, lay.hull.L, hp["shell_mm"], hp["material"], sup.get("plating_mm", 0.0),
                             sup.get("control_mm", 0.0), hp["deck_wood_mm"])


def deck_plates(sub, plating, design, comps):
    """plate_mm on the subdivision's decks and unarmoured bulkheads: the main deck is the strength deck (thicker over
    the middle: plate_end_mm toward the ends), the inner bottom and raised decks at the hull's own gauge, the other
    decks and the watertight bulkheads lighter. A torpedo bulkhead gives the protection's plating, all its
    bulkheads together. Deck planking (wood_mm) lies on the weather deck: the flight deck when there is one, else
    the main and raised decks."""
    from navarch import TUNING
    tds = (design.get("armour") or {}).get("tds_m", 0.0) or 0.0
    for d in sub["decks"]:
        if d["kind"] == "inner_bottom":
            d["plate_mm"] = plating["inner_bottom_mm"]
        elif d["kind"] == "main":
            d["plate_mm"], d["plate_end_mm"] = plating["strength_deck_mm"], plating["strength_deck_end_mm"]
        elif d["kind"] == "raised":     # a raised stretch's weather deck, at the hull's own gauge
            d["plate_mm"] = plating["strength_deck_end_mm"]
        else:
            d["plate_mm"] = plating["deck_mm"]
    wood = plating["deck_wood_mm"]
    if wood:
        weather = [c for c in comps if c["kind"] == "flight_deck"] or [
            d for d in sub["decks"] if d["kind"] in ("main", "raised")]
        for d in weather:
            d["wood_mm"] = wood
    for b in sub["bulkheads"]:
        b["plate_mm"] = (round(TUNING["tds_mm_per_m"] * tds, 1) if b.get("kind") == "tds"
                         else plating["bulkhead_mm"])


def battle_crew(lay, sub, comps):
    """battle_crew on the components, rooms and cells where the complement stands at battle stations
    (crew.battle_stations; a room's men are spread over the cells it owns by volume), and its summary in the
    report's crew (battle_stations)."""
    import crew
    st = crew.battle_stations(lay, sub, comps)
    for x in comps:
        if st["components"].get((x["kind"], x["id"])):
            x["battle_crew"] = st["components"][(x["kind"], x["id"])]
    cells = {c["id"]: c for c in sub["cells"]}
    for r in sub["rooms"]:
        men = st["rooms"].get(r["id"])
        if men:
            r["battle_crew"] = men
            own = {cid: cells[cid]["volume_m3"] for cid in r["cells"] if cells[cid]["room"] == r["id"]}
            for cid, m in crew.spread(men, own).items():
                cells[cid]["battle_crew"] = m
    if getattr(lay, "crew", None) is not None and st["summary"]:
        lay.crew["battle_stations"] = st["summary"]


def export_hitboxes(lay, design, res):
    """hitboxes.json. Heights are metres above the main deck; res (navarch.Result) places the keel, the
    waterline and the armour."""
    from layout import block_base, block_top
    from navarch import armour_geometry, armour_material, cwp, deck_name, froude, DECK_PITCH
    D, T = res.depth, res.draught
    rz = lambda z: round(z - D, 2)        # metres above the keel -> above the main deck
    ag = armour_geometry(design, lay.hull.L, T, D, lay.geo)
    armoured = ag["armoured"]
    armour = design.get("armour", {})
    # barbettes reach the main armour deck (the belt top without deck armour; the second deck, never under the
    # waterline, when unarmoured)
    barbette_z = (ag["main_z"] if ag["main_z"] is not None else ag["belt_top"] if ag["belt_mm"] > 0
                  else max(T, D - DECK_PITCH))
    sec = design.get("secondary") or {}
    sec_arm = sec.get("armour_mm", 25) if isinstance(sec, dict) else 25
    r3 = lambda pts: [[round(x, 3), round(y, 3)] for x, y in pts]
    fd_base = min([dk["base"] for dk in lay.decks if dk["kind"] == "flight_deck"] + [1e9])
    comps = []
    def with_material(d, m):    # the armour.materials string, passed through as given (none: no key)
        if m:
            d["material"] = m
        return d
    for m in lay.mounts:
        t = m["t"]
        sh = turret_shapes(t)
        arm = m["armour_mm"] if "armour_mm" in m else (
            armour.get("turret_mm", 0) if m["kind"] == "main" else (sec_arm if m["kind"] == "secondary" else 0))
        comps.append(dict(
            id=m["id"], kind=m["kind"], type=m["type"], x=round(m["x"], 3), y=round(m["y"], 3),
            base=round(m["base"], 2), top=round(m["top"], 2), armour_mm=arm,
            broadphase_r=round(max(t["r"], turret_reach({**t, "barrel_len": 0})), 3),
            rotating=m.get("fixed") is None, rest_deg=m["rest"], arcs_deg=m["arcs"],
            traverse_deg=m["traverse"],
            local={"body": r3(sh["body"]), "parts": [r3(p) for p in sh["parts"]],
                   "barrels": [r3(p) for p in sh["barrels"]]}))
        mat = (armour_material(design, "turrets") if m["kind"] == "main" else
               m.get("material") or armour_material(design, "secondary") if m["kind"] == "secondary" else None)
        if m["kind"] in ("main", "secondary"):
            comps[-1]["armour"] = dict(face=arm, side=round(TURRET_SIDE * arm), rear=round(TURRET_REAR * arm),
                                       roof=round(TURRET_ROOF * arm))
            with_material(comps[-1], mat)
        if m["kind"] == "torpedo":      # the torpedoes in the tubes, with their warheads
            comps[-1].update(torpedoes=t["barrels"], warhead_kg=round(ordnance.warhead_kg()))
        else:                           # ready-use ammunition at the mount (ordnance.ready_use)
            n, w = ordnance.ready_use(t["calibre_mm"], t["barrels"])
            comps[-1].update(ready_rounds=n, ready_t=round(w, 2))
        if m.get("magazine"):
            comps[-1]["magazine"] = m["magazine"]
        if m.get("casemate"):   # in the hull side, below the main deck
            comps[-1]["mount"] = "casemate"
        if t.get("barbette", True):
            # from the main armour deck up to the turret, for a mount standing in the hull; a mount on a sponson or a
            # flight deck has only a pedestal on its platform
            in_hull = abs(m["y"]) + 0.95 * t["r"] <= lay.hull.half_width(m["x"]) and m["base"] < fd_base
            comps[-1]["barbette"] = f"{m['id']} barbette"
            comps.append(dict(id=f"{m['id']} barbette", kind="barbette", mount=m["id"], shape="circle",
                              x=round(m["x"], 3), y=round(m["y"], 3), r=round(t["r"] * 0.95, 3),
                              base=(min(rz(barbette_z), round(m["base"], 2)) if in_hull
                                    else round(m["base"] - 1.0, 2)),
                              top=round(m["base"], 2), armour_mm=round(BARBETTE * arm)))
            with_material(comps[-1], armour_material(design, "barbettes") if m["kind"] == "main" else mat)
    directors = {d["id"]: d for d in lay.directors}
    sup_material = (design.get("superstructure") or {}).get("material")
    quarters = (getattr(lay, "crew", None) or {}).get("superstructure_quarters", {})
    for b in lay.blocks:
        pts = block_outline(b)
        smoke = getattr(lay, "smoke", {}).get(b["id"])
        # a rounded rectangle also gives its parameters; a polygon block only its points
        rr = {} if b.get("points") else dict(rrect=dict(
            x0=round(b["x0"], 3), x1=round(b["x1"], 3), y0=round(b["y"] - b["w"] / 2, 3),
            y1=round(b["y"] + b["w"] / 2, 3), rf=round(b["rf"], 3), rb=round(b["rb"], 3)))
        comps.append(dict(id=b["id"], kind="superstructure", role=block_role(b["id"]), shape="polygon",
                          points=[[round(x, 3), round(y, 3)] for x, y in pts], **rr,
                          base=round(block_base(b), 2), top=round(block_top(b), 2)))
        d = directors.get(b["id"])
        if d:       # a fire-control director: which battery it serves, its rangefinder and its hood's armour
            comps[-1].update(battery=d["battery"], rangefinder_m=d["rangefinder_m"], armour_mm=d["armour_mm"],
                             radar=d["radar_t"] > 0)
        else:
            with_material(comps[-1], sup_material)
        if "_plate_mm" in b:        # its walls' plating (layout.block_plating)
            comps[-1]["plate_mm"] = b["_plate_mm"]
        if quarters.get(b["id"]):     # off-watch men quartered here (crew.apply): a hit here can kill them
            comps[-1]["crew"] = quarters[b["id"]]
        if smoke:
            comps[-1]["smoke"] = smoke
    ct = lay.conning_tower
    if ct:
        comps.append(dict(id="Conning tower", kind="conning_tower", shape="circle", x=round(ct["x"], 3),
                          y=round(ct["y"], 3), r=round(ct["r"], 3), base=0.0, top=round(ct["top"], 2),
                          armour_mm=ag["belt_mm"]))
        with_material(comps[-1], armour_material(design, "conning_tower"))
    plan = lay.geo.get("plant")
    for f in lay.funnels:
        pts = rrect_polygon(f["x"] - f["l"] / 2, f["y"] - f["w"] / 2, f["x"] + f["l"] / 2, f["y"] + f["w"] / 2,
                            f["w"] / 2, f["w"] / 2)
        pts = [[round(x, 3), round(y, 3)] for x, y in pts]
        comps.append(dict(id=f["id"], kind="funnel", shape="polygon", points=pts, base=f.get("z0", 0.0),
                          top=round(lay.fun_top, 2), boiler_rooms=f.get("serves", [])))
        if plan and f.get("serves") is not None:   # the uptakes: from the top of the boilers up to the funnel
            comps.append(dict(id=f"{f['id']} uptakes", kind="uptake", funnel=f["id"], shape="polygon", points=pts,
                              base=round(plan["inner_bottom"] + plan["space"]["unit"][2] - D, 2),
                              top=f.get("z0", 0.0), boiler_rooms=f.get("serves", [])))
    for c in lay.casings:      # over machinery that stands taller than its space; armoured as the deck it pierces
        pts = rrect_polygon(c["x0"], -c["w"] / 2, c["x1"], c["w"] / 2, 0.5, 0.5)
        comps.append(dict(id=c["id"], kind="casing", shape="polygon",
                          points=[[round(x, 3), round(y, 3)] for x, y in pts], base=round(c["base"], 2),
                          top=round(c["top"], 2), armour_mm=c["armour_mm"]))
        if c["armour_mm"]:
            with_material(comps[-1], ag["roof_material"])
    for dk in [d for d in lay.decks if d["kind"] != "deck"] + [{**sp, "kind": "sponson"} for sp in lay.sponsons]:
        # (raised stretches of hull are cells of the subdivision, and their extent is in vertical.raised)
        comps.append(dict(id=dk["id"], kind=dk["kind"], shape="polygon",
                          points=[[round(x, 3), round(y, 3)] for x, y in dk["points"]],
                          base=round(dk["base"], 2), top=round(dk["top"], 2)))
        fd_mm = (design.get("armour") or {}).get("flight_deck_mm", 0)
        if dk["kind"] == "flight_deck" and fd_mm:
            comps[-1]["armour_mm"] = fd_mm
            with_material(comps[-1], armour_material(design, "flight_deck"))
    for a in lay.aa:
        n, w = ordnance.ready_use(40.0 if "40" in a["type"] else 20.0, AA_CFG[a["type"]][1])
        comps.append(dict(id=a["id"], kind="aa", type=a["type"], shape="circle", x=round(a["x"], 3),
                          y=round(a["y"], 3), r=AA_CFG[a["type"]][0], base=a["base"], top=a["base"] + 2.0,
                          ready_rounds=n, ready_t=round(w, 2)))
    for c in lay.compartments:     # a carrier's hangar stands above the hangar deck, outside the subdivision
        if c["kind"] == "hangar":
            pts = rrect_polygon(c["x0"], -c["half_width"], c["x1"], c["half_width"], 0.0, 0.0)
            comps.append(dict(id=c["id"], kind="hangar_bay", shape="polygon",
                              points=[[round(x, 3), round(y, 3)] for x, y in pts], base=round(c["base"], 2),
                              top=round(c["top"], 2)))
    cb = design["hull"]["block_coefficient"]
    gear = propulsion.gear(lay, design, res)        # the stern's lines make room for it
    form = HullForm(lay.hull, cb, cwp(cb), T, D, froude(design["speed_kn"], lay.hull.L), gear, res.lcb)
    sub = subdivision.build(lay, design, res, ag, armoured, form)
    plating = hull_plating(lay, design, res)
    deck_plates(sub, plating, design, comps)
    hydro = hydrostatics(form, res)
    comps += propulsion_components(lay, design, res, form, sub, gear)
    battle_crew(lay, sub, comps)
    arm_out = {}
    if ag["belt_mm"] > 0:
        arm_out["belt"] = with_material(dict(thickness_mm=ag["belt_mm"], x0=round(ag["x0"], 3), x1=round(ag["x1"], 3),
                                             bottom=rz(ag["belt_bottom"]), top=rz(ag["belt_top"])), ag["belt_material"])
        if ag["belt_bottom_mm"] != ag["belt_mm"]:    # tapers below the waterline to this at its lower edge
            arm_out["belt"].update(bottom_mm=ag["belt_bottom_mm"], taper_from=rz(min(ag["belt_top"], ag["waterline"])))
    if ag["strakes"]:
        arm_out["strakes"] = [with_material(dict(id=st["id"], kind=st["kind"], extent=st["extent"], thickness_mm=st["mm"],
                                   **({"tip_mm": st["tip_mm"]} if st["tip_mm"] != st["mm"] else {}),
                                   x0=round(st["x0"], 3), x1=round(st["x1"], 3), bottom=rz(st["bottom"]),
                                   top=rz(st["top"])), st["material"]) for st in ag["strakes"]]
    if armoured and ag["bulkhead_mm"] > 0:
        arm_out["bulkheads"] = [with_material(dict(id=f"{end} bulkhead", x=round(x, 3), thickness_mm=round(ag["bulkhead_mm"]),
                                                   bottom=rz(ag["bulkhead_bottom"]), top=rz(ag["bulkhead_top"])),
                                              ag["bulkhead_material"])
                                for end, x in (("Forward", ag["x1"]), ("Aft", ag["x0"]))]
    if ag["end_bulkheads"]:      # an end belt's closing bulkhead, the steering box's ends
        arm_out.setdefault("bulkheads", []).extend(
            with_material(dict(id=b["id"], x=round(b["x"], 3), thickness_mm=round(b["mm"]), bottom=rz(b["bottom"]),
                               top=rz(b["top"])), b["material"]) for b in ag["end_bulkheads"])
    if ag["decks"]:
        arm_out["decks"] = [with_material(dict(deck=deck_name(d["deck"]), thickness_mm=d["mm"], extent=d["extent"],
                                               x0=round(d["x0"], 3), x1=round(d["x1"], 3), z=rz(d["z"]),
                                               main=d["z"] == ag["main_z"], roof=d["z"] == ag["roof_z"]),
                                          d["material"]) for d in ag["decks"]]
    return dict(
        units="metres",
        frame="ship-local: origin = ship centre = sprite centre, +x toward bow, +y toward starboard; "
              "angles clockwise from dead ahead",
        heights="base/top/z are metres above the main deck (negative = below it)",
        turret_local="turret 'local' polygons are in turret space (pivot at 0,0, barrels along +x); "
                     "rotate by the current turret angle, then add (x, y)",
        length=lay.hull.L, beam=lay.hull.B,
        vertical=dict(keel=-round(D, 2), waterline=-round(D - T, 2),
                      armour_deck=rz(ag["main_z"]) if ag["main_z"] is not None else None,
                      draught=round(T, 2), depth=round(D, 2), freeboard=round(D - T, 2),
                      **({"raised": [dict(id=st["id"], x0=round(st["x0"], 3), x1=round(st["x1"], 3),
                                          top=round(st["levels"] * DECK_PITCH, 2)) for st in lay.raised]}
                         if lay.raised else {})),
        hull=[[round(x, 3), round(y, 3)] for x, y in lay.hull.points()],
        hydrostatics=hydro,
        hull_form=dict(midship_coefficient=round(form.cm, 3), waterplane_coefficient=round(form.cwp, 3),
                       stations=[dict(x=round(s["x"], 3), z=[round(z - D, 2) for z in s["z"]],
                                      y=[round(y, 3) for y in s["y"]]) for s in form.table()]),
        armour=arm_out,
        plating=plating,
        components=comps,
        **sub,
    )
