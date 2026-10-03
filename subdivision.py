"""
subdivision — the hull below the main deck as a grid of watertight cells, and the rooms that own them.

Design side, standard library only. Built once per ship from the finished layout (hitbox.export_hitboxes); the
size search never runs it.

  sections  the hull between transverse bulkheads (stations). The stations snap to what matters: the ends of
            the layout's rooms (machinery rooms, magazines, holds, steering), the citadel's ends and the
            collision bulkhead. Stations closer than MIN_SECTION merge (the more important one stays), and gaps
            longer than MAX_SECTION fill in, except inside one room. Numbered from the bow.
  tiers     between the decks, keel up: the inner bottom (not on planing craft), then the deck stack every
            navarch.DECK_PITCH up to the main deck (navarch.deck_stack). Armour decks (armour.decks) lie on the
            stack. Each tier is named after the deck it stands on: "bottom", "hold", then ..., "third", "second"
            under the main deck. A tier the waterline crosses gives its submerged fraction.
  bands     across the ship: port wing | centre | starboard wing where a longitudinal bulkhead stands (inboard of
            the machinery's wing bunkers, or of the torpedo protection inside the citadel, up to the lowest
            armour deck), else the centre alone. A centreline machinery bulkhead splits the centre into CP | CS.
  cells     section x tier x band boxes. Their y extent reaches the hull's widest point over the section, so the
            boxes tile the hull: a point inside the hull below the main deck is in exactly one cell.
  rooms     the layout's compartments, snapped to whole cells: a room owns a cell when it overlaps the cell by at
            least half the shorter of the two along every axis; conflicts go by ROOM_PRIORITY, then overlap. A
            room too small for any cell of its own shares the cell it overlaps most ("also"). Cells no room
            claims become a section's double bottom, stores (at least half under water), quarters (above) or
            torpedo protection (a wing cell inside the citadel). Every cell has exactly one owning room.

Each cell gives its volume (the hull's plan inside the box, times its height; the part below the waterline scaled
so all underwater parts add up to the displacement volume), its permeability (PERMEABILITY by its room's kind), the
armour over it (every armour deck above it, top down) and beside it, its crew (the complement spread over the quarters by volume) and its neighbours, each
with the boundary between them: a bulkhead or deck id, or "open" inside one room.
"""
from __future__ import annotations

import math

MIN_SECTION = 0.03      # stations closer than this x L merge, within MIN_SECTION_M..MIN_SECTION_MAX_M (rooms don't
MIN_SECTION_M = 1.0     # grow with a silly hull's length)
MIN_SECTION_MAX_M = 8.0
MAX_SECTION = 0.07      # longer gaps get more bulkheads (the research's 0.05-0.07 L); a single room spans freely
MAX_SECTION_M = 2.5
COLLISION = 0.05        # the collision bulkhead, x L abaft the bow
STEEL_FRAME = 0.92      # usable half-width of the hull, as in powerplant (frames, side plating)

# who keeps a contested cell, and whose ends make the stations
ROOM_PRIORITY = {"magazine": 9, "steering": 6, "boiler_room": 7, "engine_room": 7, "fuel_tank": 7, "bunker": 6,
                 "cargo_tank": 5, "hold": 5, "accommodation": 2}
# fraction of a cell's volume that floodwater can fill, by its room's kind (research §8.4)
PERMEABILITY = {"magazine": 0.6, "steering": 0.85, "boiler_room": 0.85, "engine_room": 0.85, "fuel_tank": 0.95,
                "bunker": 0.95, "cargo_tank": 0.95, "hold": 0.6, "accommodation": 0.95, "stores": 0.6,
                "double_bottom": 0.95, "tds": 0.95}
COAL_PERMEABILITY = 0.4   # a full coal bunker


def _overlap(a0, a1, b0, b1):
    return min(a1, b1) - max(a0, b0)


def _claims(room, cell):
    """Does the room's box take the cell: on every axis an overlap of at least half the shorter of the two?"""
    for k0, k1 in (("x0", "x1"), ("y0", "y1"), ("base", "top")):
        o = _overlap(room[k0], room[k1], cell[k0], cell[k1])
        if o <= 1e-6 or o < 0.5 * min(room[k1] - room[k0], cell[k1] - cell[k0]) - 1e-6:
            return False
    return True


def _box_overlap(room, cell):
    v = 1.0
    for k0, k1 in (("x0", "x1"), ("y0", "y1"), ("base", "top")):
        v *= max(0.0, _overlap(room[k0], room[k1], cell[k0], cell[k1]))
    return v


def decks(design, D, ag):
    """The decks, keel up, as heights above the main deck: [dict(id, kind, z, armour_mm?, x0?, x1?)]. The keel,
    the inner bottom (not on planing craft), then the deck stack (navarch.deck_stack) up to the main deck. An
    armoured deck carries its armour (navarch.armour_geometry) and the stretch it covers."""
    from navarch import deck_stack, deck_name
    from powerplant import double_bottom
    out = [dict(id="Keel", kind="keel", z=-D)]
    if design.get("style") != "planing":
        out.append(dict(id="Inner bottom", kind="inner_bottom", z=-D + double_bottom(D)))
    arm = {}
    for d in ag["decks"]:
        arm[d["deck"]] = dict(armour_mm=d["mm"], x0=d["x0"], x1=d["x1"])
    for n, z in reversed(deck_stack(design, D)):
        out.append(dict(id=deck_name(n), kind="main" if n == 0 else "deck", deck=n, z=z - D, **arm.get(n, {})))
    return out


def tier_name(floor):
    """A tier is named after the deck it stands on: bottom (the double bottom), hold (on the inner bottom), then
    second, third, ... (the space on that deck)."""
    if floor["kind"] in ("keel", "inner_bottom"):
        return "bottom" if floor["kind"] == "keel" else "hold"
    return floor["id"].lower().removesuffix(" deck")


def stations(L, rooms, cit, min_gap, max_gap):
    """Transverse bulkhead positions, bow to stern: [dict(x, kind)], with the hull's ends."""
    cands = [(L / 2 - COLLISION * L, 9, "collision")]
    if cit:
        cands += [(cit[0], 10, cit[2]), (cit[1], 10, cit[2])]
    for r in rooms:
        p = ROOM_PRIORITY.get(r["kind"], 4)
        cands += [(r["x0"], p, "main"), (r["x1"], p, "main")]
    cands = [c for c in cands if -L / 2 + min_gap <= c[0] <= L / 2 - min_gap]
    cands.sort(key=lambda c: -c[0])
    merged = []      # one station where several rooms end: its importance adds up
    for c in cands:
        if merged and merged[-1][0] - c[0] < 0.05:
            m = merged[-1]
            merged[-1] = (m[0], m[1] + c[1], m[2] if m[2] != "main" else c[2])
        else:
            merged.append(c)
    cands = merged
    pts = [(L / 2, 99, "end")] + cands + [(-L / 2, 99, "end")]
    while len(pts) > 2:      # merge the closest pair under the minimum, dropping the less important station
        g, i = min((pts[i][0] - pts[i + 1][0], i) for i in range(len(pts) - 1))
        if g >= min_gap:
            break
        a, b = pts[i], pts[i + 1]
        if a[2] == "end" or (b[2] != "end" and b[1] <= a[1]):
            pts.pop(i + 1)       # a tie keeps the forward one
        else:
            pts.pop(i)
    out = [dict(x=pts[0][0], kind="end")]
    for (xa, _, _), (xb, pb, kb) in zip(pts, pts[1:]):
        gap = xa - xb
        inside = any(r["x0"] <= xb + 1e-6 and r["x1"] >= xa - 1e-6 for r in rooms)
        if gap > max_gap and not inside:
            k = math.ceil(gap / max_gap - 1e-9)
            out += [dict(x=xa - gap * j / k, kind="main") for j in range(1, k)]
        out.append(dict(x=xb, kind=kb))
    return out


def build(lay, design, res, ag, armoured):
    """The subdivision of the laid-out ship: dict(decks, tiers, sections, bulkheads, cells, rooms) for
    hitboxes.json. ag is navarch.armour_geometry (heights above the keel)."""
    hull = lay.hull
    L, B = hull.L, hull.B
    D, T = res.depth, res.draught
    cb = design["hull"]["block_coefficient"]
    planing = design.get("style") == "planing"
    plan = lay.geo.get("plant") or {}
    mach = lay.geo.get("machinery")
    wl = -(D - T)
    rz = lambda z: z - D

    # ---------------- decks and tiers ----------------
    dks = decks(design, D, ag)
    has_bottom = dks[1]["kind"] == "inner_bottom"
    tiers = []
    for lo, hi in zip(dks, dks[1:]):
        name = "hold" if lo["kind"] == "keel" and not has_bottom else tier_name(lo)
        sub = min(1.0, max(0.0, (wl - lo["z"]) / (hi["z"] - lo["z"])))
        tiers.append(dict(id=name, base=lo["z"], top=hi["z"], below_waterline=sub >= 1.0 - 1e-6,
                          submerged=sub, floor=lo["id"], ceiling=hi["id"]))
    ib = dks[1]["z"] if has_bottom else -D
    under = (ag["roof_z"] - D) if ag["roof_z"] is not None else 0.0   # rooms' default top: the lowest armour deck
    adecks = [d for d in reversed(dks) if d.get("armour_mm")]         # armoured decks, top down

    # ---------------- rooms (the layout's compartments) as boxes ----------------
    rooms = []
    for c in lay.compartments:
        if c["kind"] in ("citadel", "hangar"):
            continue
        y, hw = c.get("y", 0.0), c["half_width"]
        rooms.append(dict(src=c, id=c["id"], kind=c["kind"], x0=c["x0"], x1=c["x1"], y0=y - hw, y1=y + hw,
                          base=c.get("base", ib), top=c.get("top", under)))

    # ---------------- sections ----------------
    cit = None
    if armoured:
        cit = (ag["x0"], ag["x1"], "armoured" if ag["belt_mm"] > 0 else "citadel")
    elif lay.geo.get("citadel") and design.get("style", "warship") in ("warship", "carrier"):
        cit = (*lay.geo["citadel"], "citadel")
    st = stations(L, rooms, cit, min(MIN_SECTION_MAX_M, max(MIN_SECTION_M, MIN_SECTION * L)), max(MAX_SECTION_M, MAX_SECTION * L))
    sections = []
    for i, (a, b) in enumerate(zip(st, st[1:])):
        sections.append(dict(id=str(i + 1), x0=b["x"], x1=a["x"]))
    nbh = len(st) - 2
    tb = []          # transverse bulkheads, bow to stern
    for k, s in enumerate(st[1:-1]):
        d = dict(id=f"Bulkhead {k + 1}", kind=s["kind"] if s["kind"] in ("collision", "armoured") else "main",
                 x=round(s["x"], 3), base=round(-D, 2), top=0.0)
        if s["kind"] == "armoured":
            d.update(armour_mm=round(ag["bulkhead_mm"]), armour_bottom=round(rz(ag["bulkhead_bottom"]), 2),
                     armour_top=round(rz(ag["belt_top"]), 2))
        tb.append(d)
    assert len(tb) == nbh

    # ---------------- bands and cells ----------------
    tds = plan.get("tds", 0.0) or 0.0
    wing_m = plan.get("wing_m", 0.0) or 0.0
    centreline = bool((design.get("machinery") or {}).get("centreline_bulkhead"))
    a_plan = sum(2 * hull.half_width(-L / 2 + L * (k + 0.5) / 400) * L / 400 for k in range(400))
    under_k = min(1.0, cb * L * B / a_plan) if a_plan else 1.0      # plan x height -> underwater volume

    def hw_samples(x0, x1, n=8):
        return [hull.half_width(x0 + (x1 - x0) * (j + 0.5) / n) for j in range(n)]

    cells, longi = [], []
    belt = (ag["x0"], ag["x1"], rz(ag["belt_bottom"]), rz(ag["belt_top"]), ag["belt_mm"]) if ag["belt_mm"] > 0 else None
    for si, sec in enumerate(sections):
        x0, x1 = sec["x0"], sec["x1"]
        xm = (x0 + x1) / 2
        hws = hw_samples(x0, x1)
        hwmax = max(hull.half_width(x0), hull.half_width(x1), *hws)
        in_mach = mach and mach[0] - 1e-6 <= xm <= mach[1] + 1e-6
        in_cit = cit and cit[0] - 1e-6 <= xm <= cit[1] + 1e-6
        split, s_kind, s_top = None, None, None
        if wing_m > 0 and in_mach:
            split, s_kind, s_top = plan["width"] / 2, "wing", 0.0
        elif tds > 0 and in_cit:
            split = max(0.5, STEEL_FRAME * min(hws) - tds)
            s_kind, s_top = "tds", under
        if split is not None and split >= hwmax - 0.3:
            split = None
        for side, sgn in (("S", 1), ("P", -1)):
            if split is not None:
                longi.append(dict(id=f"{'Wing' if s_kind == 'wing' else 'Torpedo'} bulkhead {sec['id']} {side}",
                                  kind=s_kind, section=sec["id"], side=side, y=round(sgn * split, 3), x0=round(x0, 3), x1=round(x1, 3),
                                  base=round(ib, 2), top=round(s_top, 2)))
        cl = centreline and in_mach
        if cl:
            longi.append(dict(id=f"Centreline bulkhead {sec['id']}", kind="centreline", section=sec["id"], side="C",
                              y=0.0,
                              x0=round(x0, 3), x1=round(x1, 3), base=round(ib, 2), top=round(under, 2)))
        for ti, tr in enumerate(tiers):
            bottom = has_bottom and ti == 0
            banded = split is not None and not bottom and tr["top"] <= s_top + 1e-6
            centre_split = cl and not bottom and tr["top"] <= under + 1e-6
            if banded:
                ys = [("P", -hwmax, -split)] + ([("CP", -split, 0.0), ("CS", 0.0, split)] if centre_split
                                                else [("C", -split, split)]) + [("S", split, hwmax)]
            else:
                ys = [("CP", -hwmax, 0.0), ("CS", 0.0, hwmax)] if centre_split else [("C", -hwmax, hwmax)]
            for band, y0, y1 in ys:
                area = sum(max(0.0, min(h, y1) - max(-h, y0)) for h in hws) * (x1 - x0) / len(hws)
                h = tr["top"] - tr["base"]
                vol = area * h * (tr["submerged"] * under_k + 1.0 - tr["submerged"])
                if vol < 0.01:
                    continue
                c = dict(id=f"{sec['id']} {tr['id']} {band}", section=sec["id"], tier=tr["id"], band=band,
                         x0=x0, x1=x1, y0=y0, y1=y1, base=tr["base"], top=tr["top"], volume_m3=vol,
                         below_waterline=tr["below_waterline"], si=si, ti=ti)
                if in_cit and armoured:
                    c["citadel"] = True
                above = [d["armour_mm"] for d in adecks if tr["top"] <= d["z"] + 1e-6 and d["x0"] <= xm <= d["x1"]]
                if above:
                    c["armour_above_mm"] = above
                outer = band in ("P", "S") or (band == "C") or (band in ("CP", "CS") and not banded)
                if belt and outer and belt[0] <= xm <= belt[1] and _overlap(belt[2], belt[3], tr["base"], tr["top"]) > 0:
                    c["belt_mm"] = belt[4]
                if banded and band in ("P", "S") and in_cit and tds > 0:
                    c["tds_m"] = tds
                cells.append(c)

    # ---------------- rooms take cells ----------------
    owner = {}
    for c in cells:
        best = None
        for r in rooms:
            if _claims(r, c):
                key = (ROOM_PRIORITY.get(r["kind"], 4), _box_overlap(r, c))
                if best is None or key > best[0]:
                    best = (key, r)
        if best:
            owner[c["id"]] = best[1]["id"]
    by_id = {c["id"]: c for c in cells}
    room_out = {r["id"]: dict(id=r["id"], kind=r["kind"], cells=[]) for r in rooms}
    for r in rooms:
        for k, v in r["src"].items():
            if k not in ("id", "kind", "x0", "x1", "y", "half_width", "base", "top"):
                room_out[r["id"]][k] = v
    for cid, rid in owner.items():
        room_out[rid]["cells"].append(cid)
    also = {}
    for r in rooms:     # a room with no cell of its own shares the one it overlaps most (or the nearest)
        if room_out[r["id"]]["cells"]:
            continue
        rc = ((r["x0"] + r["x1"]) / 2, (r["y0"] + r["y1"]) / 2, (r["base"] + r["top"]) / 2)
        cand = sorted(cells, key=lambda c: (-_box_overlap(r, c), math.dist(
            rc, ((c["x0"] + c["x1"]) / 2, (c["y0"] + c["y1"]) / 2, (c["base"] + c["top"]) / 2))))
        if cand:
            also.setdefault(cand[0]["id"], []).append(r["id"])
            room_out[r["id"]]["cells"].append(cand[0]["id"])
            room_out[r["id"]]["shared"] = True

    # the rest: double bottom, torpedo protection, stores, quarters (one room per section and use)
    for c in cells:
        if c["id"] in owner:
            continue
        if has_bottom and c["ti"] == 0:
            use, name = "double_bottom", "Double bottom"
        elif c.get("tds_m") and c["band"] in ("P", "S"):
            use, name = "tds", "Torpedo protection"
        elif tiers[c["ti"]]["submerged"] >= 0.5:
            use, name = "stores", "Stores"
        else:
            use, name = "accommodation", "Quarters"
        rid = f"{name} {c['section']}" + (f" {c['band']}" if use == "tds" else "")
        room_out.setdefault(rid, dict(id=rid, kind=use, cells=[]))["cells"].append(c["id"])
        owner[c["id"]] = rid

    # ---------------- crew: the complement over the quarters, by volume ----------------
    n = (getattr(lay, "crew", None) or {}).get("complement", 0)
    quarters = [c for c in cells if room_out[owner[c["id"]]]["kind"] == "accommodation"]
    qv = sum(c["volume_m3"] for c in quarters)
    if n and qv > 0:
        shares = [n * c["volume_m3"] / qv for c in quarters]
        men = [int(s) for s in shares]
        for k in sorted(range(len(quarters)), key=lambda k: men[k] - shares[k])[:n - sum(men)]:
            men[k] += 1
        for c, m in zip(quarters, men):
            if m:
                c["crew"] = m
    for r in room_out.values():
        r.pop("crew", None)
        crew = sum(by_id[cid].get("crew", 0) for cid in r["cells"] if owner[cid] == r["id"])
        if crew:
            r["crew"] = crew

    # ---------------- per-cell finish: room, permeability, neighbours ----------------
    fuel = plan.get("fuel")
    for c in cells:
        r = room_out[owner[c["id"]]]
        c["room"] = r["id"]
        if c["id"] in also:
            c["also"] = also[c["id"]]
        p = PERMEABILITY.get(r["kind"], 0.9)
        if r["kind"] == "bunker" and r.get("fuel", fuel) == "coal":
            p = COAL_PERMEABILITY
        c["permeability"] = p
    grid = {(c["si"], c["ti"]): [] for c in cells}
    for c in cells:
        grid[(c["si"], c["ti"])].append(c)
    lon = {(l_["section"], l_["side"]): l_["id"] for l_ in longi}
    for c in cells:
        nb = []
        for d in grid[(c["si"], c["ti"])]:        # across: the next band, through a longitudinal bulkhead
            if d is c:
                continue
            if abs(d["y0"] - c["y1"]) < 1e-6:
                y = c["y1"]
            elif abs(d["y1"] - c["y0"]) < 1e-6:
                y = c["y0"]
            else:
                continue
            nb.append((d, lon[(c["section"], "C" if abs(y) < 1e-6 else "S" if y > 0 else "P")]))
        for dt, deck in ((-1, tiers[c["ti"]]["floor"]), (1, tiers[c["ti"]]["ceiling"])):   # up and down
            for d in grid.get((c["si"], c["ti"] + dt), []):
                if _overlap(c["y0"], c["y1"], d["y0"], d["y1"]) > 1e-6:
                    nb.append((d, deck))
        for ds in (-1, 1):                         # fore and aft, through the transverse bulkhead
            for d in grid.get((c["si"] + ds, c["ti"]), []):
                if _overlap(c["y0"], c["y1"], d["y0"], d["y1"]) > 1e-6:
                    nb.append((d, tb[min(c["si"], d["si"])]["id"]))
        c["neighbours"] = [[d["id"], "open" if d["room"] == c["room"] else via] for d, via in nb]

    # ---------------- rooms: extent and volume ----------------
    for r in room_out.values():
        own = [by_id[cid] for cid in r["cells"]]
        r["volume_m3"] = round(sum(c["volume_m3"] for c in own if owner[c["id"]] == r["id"]), 1)
        r["x0"], r["x1"] = round(min(c["x0"] for c in own), 3), round(max(c["x1"] for c in own), 3)
        r["base"], r["top"] = round(min(c["base"] for c in own), 2), round(max(c["top"] for c in own), 2)

    def rnd(c):
        out = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in c.items() if k not in ("si", "ti")}
        out["volume_m3"] = round(c["volume_m3"], 1)
        out["base"], out["top"] = round(c["base"], 2), round(c["top"], 2)
        return out

    return dict(
        decks=[{k: (round(v, 3) if isinstance(v, float) else v) for k, v in d.items()} for d in dks[1:]],
        tiers=[{k: (round(v, 2) if isinstance(v, float) else v) for k, v in t.items()} for t in tiers],
        sections=[dict(id=s["id"], x0=round(s["x0"], 3), x1=round(s["x1"], 3)) for s in sections],
        bulkheads=tb + longi,
        cells=[rnd(c) for c in cells],
        rooms=sorted(room_out.values(), key=lambda r: -r["x1"]),
    )
