"""
arcs: fixed firing arcs by mount kind, and the one interval each mount turns within (traverse).

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

from geometry import _wrap180


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
