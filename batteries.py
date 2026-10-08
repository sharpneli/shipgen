"""
batteries — the ship's guns as data: reading the design's batteries (main_batteries, secondary_batteries), what a
gun, mount, its magazine load and a torpedo mount weigh (mount_weights, torpedo_weight), rounds per gun, and the
first-pass armament estimate before anything is laid out (rough_armament). Where the mounts go is armament.py and
the styles' layouts; their magazines are ordnance.py.

A change to how a battery is read or weighed belongs here; every style and module reads batteries through these.
Design side, standard library only.
"""
from __future__ import annotations

import math

from geometry import battery_type, has_barbette, superfire_step
from weights import STEEL, Weight

TUNING = dict(
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
)


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


def rough_armament(design, D):
    """First-pass armament estimate before the layout exists (all at x=0): navarch.rough_payload."""
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
    return out
