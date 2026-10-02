"""
hitbox: fixed firing arcs, and hitbox export.

Hitboxes use the layout's components: exact shapes in ship-local metres plus base and top heights
above the main deck.

Firing arcs are fixed by the kind of mount, not computed from what stands around it, so the player only
picks counts and calibres. Every arc is centred on the mount's rest bearing (degrees clockwise from ahead):
    centreline guns of a forward or after group (rest 0 or 180)   +-ARC_END
    centreline guns with a turret ahead of them: a flush turret
    behind a superfiring one, or an amidships turret               +-ARC_BEAM about each beam
    side mounts: secondaries, sponson guns, side torpedo mounts,
    wing turrets (which stow fore-and-aft, at the edge of the arc) +-ARC_SIDE   (bow to stern, own side)
    casemate guns, in the hull side                               +-ARC_CASEMATE about their beam
    centreline trainable torpedo mounts                           +-ARC_TORPEDO about each beam
    fixed tubes (MTBs; the boat aims them)                        +-ARC_FIXED about their bearing
"""
from __future__ import annotations

from geometry import rrect_polygon, turret_shapes, turret_reach, _wrap180, angle_allowed, nearest_allowed  # noqa: F401
from geometry import AA_CFG

ARC_END = 135.0
ARC_SIDE = 90.0
ARC_BEAM = 65.0
ARC_CASEMATE = 60.0
ARC_TORPEDO = 60.0
ARC_FIXED = 1.0


def _arc(centre, half):
    """[start, end] clockwise with 0 <= start < 360; end may exceed 360."""
    start = (centre - half) % 360.0
    return [round(start, 1), round(start + 2 * half, 1)]


def mount_arcs(m):
    if m.get("fixed") is not None:
        return [_arc(m["fixed"], ARC_FIXED)]
    if m.get("casemate"):
        return [_arc(m["rest"], ARC_CASEMATE)]
    if m.get("wing"):
        return [_arc(90.0 if m["y"] > 0 else 270.0, ARC_SIDE)]
    if m.get("arc_role") == "beam":
        return [_arc(90.0, ARC_BEAM), _arc(270.0, ARC_BEAM)]
    if m["kind"] == "torpedo" and abs(m["y"]) < 0.5:
        return [_arc(90.0, ARC_TORPEDO), _arc(270.0, ARC_TORPEDO)]
    if abs(abs(_wrap180(m["rest"])) - 90.0) < 1e-6:
        return [_arc(m["rest"], ARC_SIDE)]
    return [_arc(m["rest"], ARC_END)]


def assign_arcs(lay):
    """Give every mount its fixed arcs (see the module docstring) and wrap its rest bearing to -180..180. The
    layout sets the rest bearing: inside the arcs, except side-firing centreline turrets, which stow
    fore-and-aft (pointing away from the turret they stand behind) and train out before firing."""
    for m in lay.mounts:
        m["arcs"] = mount_arcs(m)
        m["rest"] = _wrap180(m["fixed"] if m.get("fixed") is not None else m["rest"])
    by_id = {m["id"]: m for m in lay.mounts}
    for sm in lay.spec["turrets"]:
        sm["rest"] = by_id[sm["id"]]["rest"]


def export_hitboxes(lay, design):
    from layout import block_base, block_top
    armour = design.get("armour", {})
    sec = design.get("secondary") or {}
    sec_arm = sec.get("armour_mm", 25) if isinstance(sec, dict) else 25
    comps = []
    for m in lay.mounts:
        t = m["t"]
        sh = turret_shapes(t)
        r3 = lambda pts: [[round(x, 3), round(y, 3)] for x, y in pts]
        arm = m["armour_mm"] if "armour_mm" in m else (
            armour.get("turret_mm", 0) if m["kind"] == "main" else (sec_arm if m["kind"] == "secondary" else 0))
        comps.append(dict(
            id=m["id"], kind=m["kind"], type=m["type"], x=round(m["x"], 3), y=round(m["y"], 3),
            base=round(m["base"], 2), top=round(m["top"], 2), armour_mm=arm,
            broadphase_r=round(max(t["r"], turret_reach({**t, "barrel_len": 0})), 3),
            rotating=m.get("fixed") is None, rest_deg=m["rest"], arcs_deg=m["arcs"],
            local={"body": r3(sh["body"]), "parts": [r3(p) for p in sh["parts"]],
                   "barrels": [r3(p) for p in sh["barrels"]]}))
        if m.get("casemate"):   # in the hull side, below the main deck
            comps[-1]["mount"] = "casemate"
        if t.get("barbette", True):
            comps.append(dict(id=f"{m['id']} barbette", kind="barbette", shape="circle",
                              x=round(m["x"], 3), y=round(m["y"], 3), r=round(t["r"] * 0.95, 3),
                              base=-3.0, top=round(m["base"], 2),
                              armour_mm=round(0.8 * arm)))
    for b in lay.blocks:
        pts = rrect_polygon(b["x0"], b["y"] - b["w"] / 2, b["x1"], b["y"] + b["w"] / 2, b["rf"], b["rb"])
        comps.append(dict(id=b["id"], kind="superstructure", shape="polygon",
                          points=[[round(x, 3), round(y, 3)] for x, y in pts],
                          rrect=dict(x0=round(b["x0"], 3), x1=round(b["x1"], 3), y0=round(b["y"] - b["w"] / 2, 3),
                                     y1=round(b["y"] + b["w"] / 2, 3), rf=round(b["rf"], 3), rb=round(b["rb"], 3)),
                          base=round(block_base(b), 2), top=round(block_top(b), 2)))
    for f in lay.funnels:
        pts = rrect_polygon(f["x"] - f["l"] / 2, f["y"] - f["w"] / 2, f["x"] + f["l"] / 2, f["y"] + f["w"] / 2,
                            f["w"] / 2, f["w"] / 2)
        comps.append(dict(id=f["id"], kind="funnel", shape="polygon",
                          points=[[round(x, 3), round(y, 3)] for x, y in pts], base=f.get("z0", 0.0),
                          top=round(lay.fun_top, 2)))
    for dk in lay.decks + [{**sp, "kind": "sponson"} for sp in lay.sponsons]:
        comps.append(dict(id=dk["id"], kind=dk["kind"], shape="polygon",
                          points=[[round(x, 3), round(y, 3)] for x, y in dk["points"]],
                          base=round(dk["base"], 2), top=round(dk["top"], 2)))
    for a in lay.aa:
        comps.append(dict(id=a["id"], kind="aa", type=a["type"], shape="circle", x=round(a["x"], 3),
                          y=round(a["y"], 3), r=AA_CFG[a["type"]][0], base=a["base"], top=a["base"] + 2.0))
    return dict(
        units="metres",
        frame="ship-local: origin = ship centre = sprite centre, +x toward bow, +y toward starboard; "
              "angles clockwise from dead ahead",
        heights="base/top are metres above the main deck",
        turret_local="turret 'local' polygons are in turret space (pivot at 0,0, barrels along +x); "
                     "rotate by the current turret angle, then add (x, y)",
        length=lay.hull.L, beam=lay.hull.B,
        hull=[[round(x, 3), round(y, 3)] for x, y in lay.hull.points()],
        components=comps,
        compartments=[{k: (round(v, 3) if isinstance(v, float) else v) for k, v in c.items()}
                      for c in lay.compartments],
    )
