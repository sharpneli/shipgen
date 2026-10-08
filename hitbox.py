"""
hitbox: hitbox export.

Hitboxes use the layout's components: exact shapes in ship-local metres plus base and top heights
above the main deck. They describe the ship only (where things are, what armours them, what links to what);
what a hit does is the game's business.
"""
from __future__ import annotations

from geometry import rrect_polygon, block_outline, turret_shapes, turret_reach
from geometry import AA_CFG, has_barbette
from layout import block_base, block_role, block_top
import ordnance
from batteries import gun_rounds
import propulsion

# Turret armour other than the face (the battery's armour_mm), as fractions of the face. Roughly Iowa, KGV and
# Bismarck: sides 0.56-0.69, rear 0.5-0.9, roof 0.4-0.43.
TURRET_SIDE, TURRET_REAR, TURRET_ROOF = 0.55, 0.5, 0.4
BARBETTE = 0.8   # barbette armour, fraction of the turret face (as navarch weighs it)


def propulsion_components(tr, D):
    """The propulsion train (propulsion.build) as components: shafts (segments from the engine room to the
    propeller), shaft alleys, propellers and rudders, linked to the engine rooms and the steering gear (the rooms
    link back: propulsion.link)."""
    z = lambda v: round(v - D, 2)
    rect = lambda x0, x1, y, hw: [[round(x0, 3), round(y - hw, 3)], [round(x1, 3), round(y - hw, 3)],
                                  [round(x1, 3), round(y + hw, 3)], [round(x0, 3), round(y + hw, 3)]]
    out = []
    steering = tr["steering"]
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
    return out


def export_hitboxes(lay, design, res, inner):
    """hitboxes.json. Heights are metres above the main deck; res (navarch.Result) places the keel, the
    waterline and the armour. inner: the ship's interior (shipdesign.interior): armour, hull form, subdivision,
    plating, hydrostatics, propulsion and battle stations."""
    from decks import deck_name
    from geometry import DECK_PITCH
    from armour import armour_material
    D, T = res.depth, res.draught
    rz = lambda z: round(z - D, 2)        # metres above the keel -> above the main deck
    ag = inner["armour"]
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
        arm = m["armour_mm"] if "armour_mm" in m else (sec_arm if m["kind"] == "secondary" else 0)
        comps.append(dict(
            id=m["id"], kind=m["kind"], type=m["type"], x=round(m["x"], 3), y=round(m["y"], 3),
            base=round(m["base"], 2), top=round(m["top"], 2), armour_mm=arm,
            broadphase_r=round(max(t["r"], turret_reach({**t, "barrel_len": 0})), 3),
            rotating=m.get("fixed") is None, rest_deg=m["rest"], arcs_deg=m["arcs"],
            traverse_deg=m["traverse"],
            local={"body": r3(sh["body"]), "parts": [r3(p) for p in sh["parts"]],
                   "barrels": [r3(p) for p in sh["barrels"]]}))
        mat = (m.get("material") or armour_material(design, "turrets") if m["kind"] == "main" else
               m.get("material") or armour_material(design, "secondary") if m["kind"] == "secondary" else None)
        if m["kind"] in ("main", "secondary"):
            comps[-1]["armour"] = dict(face=arm, side=round(TURRET_SIDE * arm), rear=round(TURRET_REAR * arm),
                                       roof=round(TURRET_ROOF * arm))
            with_material(comps[-1], mat)
        if m["kind"] == "torpedo":      # the torpedoes in the tubes, with their warheads
            comps[-1].update(torpedoes=t["barrels"], warhead_kg=round(ordnance.warhead_kg()))
        else:   # the rounds stowed for the mount (its battery's rounds_per_gun x barrels, in its magazine) and the
                # ready-use ammunition at the mount (ordnance.ready_use), drawn from them: never more than they hold
            rounds = round(gun_rounds(t) * t["barrels"])
            n, w = ordnance.ready_use(t["calibre_mm"], t["barrels"], cap=rounds)
            comps[-1].update(rounds=rounds, ready_rounds=n, ready_t=round(w, 2))
        if m.get("magazine"):
            comps[-1]["magazine"] = m["magazine"]
        if m.get("casemate"):   # in the hull side, below the main deck
            comps[-1]["mount"] = "casemate"
        if has_barbette(t):
            # from the main armour deck up to the turret, for a mount standing in the hull; a mount on a sponson or a
            # flight deck has only a pedestal on its platform
            in_hull = abs(m["y"]) + 0.95 * t["r"] <= lay.hull.half_width(m["x"]) and m["base"] < fd_base
            comps[-1]["barbette"] = f"{m['id']} barbette"
            comps.append(dict(id=f"{m['id']} barbette", kind="barbette", mount=m["id"], shape="circle",
                              x=round(m["x"], 3), y=round(m["y"], 3), r=round(t["r"] * 0.95, 3),
                              base=(min(rz(barbette_z), round(m["base"], 2)) if in_hull
                                    else round(m["base"] - 1.0, 2)),
                              top=round(m["base"], 2), armour_mm=round(BARBETTE * arm)))
            with_material(comps[-1], m.get("material") or armour_material(design, "barbettes") if m["kind"] == "main"
                          else mat)
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
        if dk["id"] in inner["planked"]:    # its deck planking (subdivision.deck_plates)
            comps[-1]["wood_mm"] = inner["plating"]["deck_wood_mm"]
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
    comps += propulsion_components(inner["propulsion"], D)
    for x in comps:     # where the complement stands at battle stations (crew.assign_battle_crew)
        if inner["battle_crew"].get((x["kind"], x["id"])):
            x["battle_crew"] = inner["battle_crew"][(x["kind"], x["id"])]
    form, sub = inner["form"], inner["subdivision"]
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
        hydrostatics=inner["hydrostatics"],
        hull_form=dict(midship_coefficient=round(form.cm, 3), waterplane_coefficient=round(form.cwp, 3),
                       stations=[dict(x=round(s["x"], 3), z=[round(z - D, 2) for z in s["z"]],
                                      y=[round(y, 3) for y in s["y"]]) for s in form.table()]),
        armour=arm_out,
        plating=inner["plating"],
        components=comps,
        **sub,
    )
