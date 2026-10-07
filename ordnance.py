"""
ordnance — what a ship carries that burns or explodes, stowed low in the hull: the magazines for its guns'
ammunition, and a carrier's aviation ordnance and fuel.

Design side, standard library only. Every style places its guns its own way (armament.add_mount books each
mount's ammunition as a "Magazine <mount id>" weight); this is the one place that turns that ammunition into
rooms. A style only says where they may go: zones, each a box on the inner bottom along x0..x1, with the rooms it
holds and what goes in each (mounts, extra tonnes). stow() sizes the zone's height to its contents, splits its
length between the rooms by volume, links each mount to its magazine and moves the ammunition weights there.

Everything stands on the inner bottom, its top on a deck of the stack (navarch.deck_stack) and never above the
lowest armour deck, so a shell or bomb fused by the armour deck bursts in the decks above it.
"""
from __future__ import annotations

from navarch import mount_weights

T_PER_M3 = 0.6     # tonnes of ammunition per m3 of magazine (shell and powder rooms with their racks; the handling
                   # rooms and passages are in the deck space above)
TIERS = 2          # deck spaces a magazine planned before its contents are known is given (a shell and powder room)
MIN_ROOM = 1.5     # m: the shortest magazine
# At action stations (research/08 section 3.9: fragments reaching ready-use ammunition start a fire about half the
# time). Fitted (E) to about 4 rounds a gun in a 16-inch gunhouse (trays and hoists), 20 at a 5-inch mount's ready
# racks, 100 a barrel at a 40 mm tub and 260 at a 20 mm: one smooth curve, no calibre classes. It's drawn from the
# magazines, so it isn't weighed again.
READY_K, READY_P = 17000.0, 1.4      # ready rounds per barrel = READY_K x calibre_mm^-READY_P
WARHEAD_K = 2.0e-6                   # torpedo warhead kg = WARHEAD_K x diameter_mm^3 (533 mm: 300 kg; 610: 450) (E)
TORPEDO_MM = 533                     # every torpedo tube is 533 mm (geometry.make_torpedo_type)


def span(plan, need_h=None, tiers=TIERS):
    """(base, top) above the main deck of a room standing on the inner bottom, top on a deck of the stack and never
    above the plan's roof (the lowest armour deck): the lowest deck need_h above the inner bottom, else the
    tiers-th deck up. At least one deck space. plan is layout's lay.geo["plant"]."""
    D, ib, roof = plan["decks"][0], plan["inner_bottom"], plan["top"]
    ups = sorted(z for z in plan["decks"] if ib + 1e-6 < z <= roof + 1e-6) or [roof]
    if need_h is None:
        top = ups[min(tiers, len(ups)) - 1]
    else:
        top = next((z for z in ups if z >= ib + need_h - 1e-6), ups[-1])
    return ib - D, top - D


def height(plan, tiers=TIERS):
    """The height of a room given `tiers` deck spaces (span), for planning a zone's length before stowing."""
    b, t = span(plan, tiers=tiers)
    return t - b


def ammo_t(t):
    """Tonnes of ammunition for one mount of turret type t."""
    return mount_weights(t, 0.0, 0.0, 0)[2]


def ready_use(calibre_mm, barrels, cap=None):
    """Ready-use ammunition at a gun mount at action stations: (rounds, tonnes). A round weighs what the magazines
    book (navarch: shell_k x calibre^3 x ammo_mult, shell and propellant)."""
    from navarch import TUNING
    n = barrels * max(1, round(READY_K * calibre_mm ** -READY_P))
    n = n if cap is None else min(n, cap)      # cap: the rounds the mount has in all
    return n, n * TUNING["shell_k"] * calibre_mm ** 3 / 1000.0 * TUNING["ammo_mult"]


def warhead_kg(diameter_mm=TORPEDO_MM):
    return WARHEAD_K * diameter_mm ** 3


def ammo_m3(t):
    """Magazine volume for one mount of turret type t."""
    return ammo_t(t) / T_PER_M3


def guns(mounts):
    """The ids of the mounts that carry ammunition (guns, not torpedo tubes)."""
    return [m["id"] for m in mounts if m["kind"] in ("main", "secondary")]


def booked_m3(lay, mids):
    """The magazine volume the mounts' booked ammunition ("Magazine <id>" weights) needs."""
    names = {f"Magazine {mid}" for mid in mids}
    return sum(w.w for w in lay.weights if w.name in names) / T_PER_M3


def zone_length(volume_m3, width, plan, tiers=TIERS, least=MIN_ROOM):
    """The length a zone `width` across needs for volume_m3 at `tiers` deck spaces tall (at least `least`)."""
    return max(least, volume_m3 / max(width * height(plan, tiers), 1.0))


def stow(lay, mounts, zones):
    """Stow the ordnance in zones: [dict(x0, x1, half_width, rooms=[room])], a room being dict(id, mounts=[mount
    ids], tonnes=extra tonnes, kind="magazine", t_per_m3=T_PER_M3, plus fields copied to the compartment). Each
    zone stands on the inner bottom, as many decks tall as its contents need over its plan area (at most the
    roof); its rooms share its length by volume, forward first. Adds the compartments (with "tonnes", and "mount"
    or "mounts"), sets each mount's "magazine", and moves its "Magazine <id>" weight to its room. Returns
    {room id: (x0, x1, base, top)}."""
    plan = lay.geo["plant"]
    by_id = {m["id"]: m for m in mounts}
    ammo = {w.name: w for w in lay.weights if w.name.startswith("Magazine ")}
    out = {}
    for z in zones:
        rooms = []
        for r in z["rooms"]:
            ms = [by_id[mid] for mid in r.get("mounts", []) if f"Magazine {mid}" in ammo]
            t = r.get("tonnes", 0.0) + sum(ammo[f"Magazine {m['id']}"].w for m in ms)
            rooms.append((r, ms, t, t / r.get("t_per_m3", T_PER_M3)))
        vol = sum(v for *_, v in rooms)
        if vol <= 0:
            continue
        L = z["x1"] - z["x0"]
        base, top = span(plan, vol / max(1.0, L * 2 * z["half_width"]))
        x = z["x1"]
        for r, ms, t, v in rooms:
            if v <= 0:
                continue
            l = L * v / vol
            c = dict(id=r["id"], kind=r.get("kind", "magazine"), x0=x - l, x1=x, half_width=z["half_width"],
                     base=base, top=top, tonnes=round(t, 1),
                     **{k: v_ for k, v_ in r.items() if k not in ("id", "kind", "mounts", "tonnes", "t_per_m3")})
            if len(ms) == 1 and z.get("own"):
                c["mount"] = ms[0]["id"]
            elif ms:
                c["mounts"] = [m["id"] for m in ms]
            lay.compartments.append(c)
            for m in ms:
                m["magazine"] = r["id"]
                w = ammo[f"Magazine {m['id']}"]
                w.x, w.z_rel = x - l / 2, ("deck", (base + top) / 2)
            out[r["id"]] = (x - l, x, base, top)
            x -= l
    return out


def own_zone(m, inner_hw):
    """A zone for one mount's own magazine: under it on the centreline, its diameter long."""
    r = m["t"]["r"]
    return dict(x0=m["x"] - r, x1=m["x"] + r, half_width=min(r, inner_hw), own=True,
                rooms=[dict(id=f"Magazine {m['id']}", mounts=[m["id"]])])

