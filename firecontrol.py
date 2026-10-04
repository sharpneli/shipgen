"""
firecontrol: directors, the plotting rooms that turn their readings into gun orders, and the search radar. Shared by
every style: each style lays out its superstructure, then place() stands the directors on its roofs.

The design gives raw numbers (the game's designer UI keeps the templates, like a design bureau's director that many
ships use):

    "fire_control": {
      "main":      {"directors": 2, "rangefinder_m": 7.9, "armour_mm": 38, "radar_t": 2.0, "computer_t": 8.0},
      "secondary": {"directors": 4, "rangefinder_m": 4.6, "armour_mm": 19, "radar_t": 2.5, "computer_t": 3.0},
      "aa":        {"directors": 8, "rangefinder_m": 0.0, "armour_mm": 0, "radar_t": 0.0, "computer_t": 0.2},
      "search_radar_t": 4.0
    }

  directors      how many directors the battery has. Main directors stand on the highest roofs, as far apart as the
                 ship allows (fore and aft); secondary directors in pairs, one each side, on the highest roofs that
                 take a pair, and AA directors likewise on the lowest, beside their guns. An odd one, or all of them
                 where no pair fits (a narrow tower, a carrier's island), stand singly on a roof's line
  rangefinder_m  the rangefinder's base (0 for a gyro sight: a Mk 51 has none). Its arms stick out athwartships, so it
                 sets the director's width, and its weight grows with base squared
  armour_mm      the director's hood, all round and on the roof (splinter plating is about 15-25 mm)
  radar_t        the fire-control radar aerial on each director
  computer_t     each director's share of the plotting room (the transmitting station: range clock, Dreyer table,
                 rangekeeper or computer, stable element, switchboards). It stands low, under the armour
  search_radar_t the search radar on the foremast top (or the highest roof without a mast)

The weights are estimates (E), not from a weight statement; the point is where they are. A tall director sees farther
(the report gives each one's eye height and horizon), but every tonne up there costs stability: the beam the sizing
needs for GM, and the heel in a beam wind.
"""
from __future__ import annotations

import math

BATTERIES = ("main", "secondary", "aa")
FIELDS = ("directors", "rangefinder_m", "armour_mm", "radar_t", "computer_t")
LABEL = {"main": "Main director", "secondary": "Secondary director", "aa": "AA director"}
HOOD_H = 2.2              # director hood height, m: the eyepieces stand EYE_H above its floor
EYE_H = 1.5
HOOD_PLATE_T = 0.047      # t/m2 of unarmoured hood (6 mm plate)
RF_T_K = 0.03             # rangefinder t = RF_T_K x base^2: 4.6 m 0.6 t, 10.5 m 3.3 t, 15 m 6.8 t (E)
GEAR_T = (1.0, 1.2)       # training gear, sights, seats: a + b x base t (E). With its hood, 19 mm of armour and its radar
                          # a Mk 37 (4.6 m) comes out at about 20 t, a Mk 51 (no rangefinder) at 1.7 t
COMPUTER_Z = 0.3          # the plotting room's height, fraction of the hull's depth (under the armour deck)
MAIN_SPREAD = 0.25        # main directors stand at least this fraction of the length apart
REFRACTION = 1.17         # the visual horizon km = 3.57 x sqrt(REFRACTION x eye height m)


def spec(design):
    """The design's fire control, every battery with every field (0 where it gives none)."""
    fc = design.get("fire_control") or {}
    out = {b: {k: (fc.get(b) or {}).get(k, 0) for k in FIELDS} for b in BATTERIES}
    out["search_radar_t"] = fc.get("search_radar_t", 0.0)
    return out


def validate(design):
    fc = design.get("fire_control")
    if fc is None:
        return []
    if not isinstance(fc, dict):
        return ["fire_control: use {\"main\": {...}, \"secondary\": {...}, \"aa\": {...}, \"search_radar_t\": t}"]
    errs = [f"fire_control.{k}: not a battery ({', '.join(BATTERIES)}) or search_radar_t" for k in fc
            if k not in BATTERIES + ("search_radar_t",)]
    for b in BATTERIES:
        v = fc.get(b)
        if v is None:
            continue
        if not isinstance(v, dict):
            errs.append(f"fire_control.{b}: use {{{', '.join(FIELDS)}}}")
            continue
        errs += [f"fire_control.{b}.{k}: not a director setting ({', '.join(FIELDS)})" for k in v if k not in FIELDS]
        errs += [f"fire_control.{b}.{k} must be a number, 0 or more" for k in FIELDS
                 if k in v and not (isinstance(v[k], (int, float)) and v[k] >= 0)]
        if not isinstance(v.get("directors", 0), int):
            errs.append(f"fire_control.{b}.directors: use a whole number")
    s = fc.get("search_radar_t", 0)
    if not (isinstance(s, (int, float)) and s >= 0):
        errs.append("fire_control.search_radar_t must be a number, 0 or more")
    return errs


def size(d):
    """A director's footprint: (fore-and-aft, athwartships) m. The rangefinder's arms set its width."""
    base = d["rangefinder_m"]
    return 0.25 * base + 1.8, max(base + 1.0, 1.8)


def weights(d):
    """One director's weights, t: hood, gear, rangefinder, armour, radar (and its share of the plotting room)."""
    base = d["rangefinder_m"]
    l, w = size(d)
    area = 2 * (l + w) * HOOD_H + l * w
    return dict(hood=area * HOOD_PLATE_T, gear=GEAR_T[0] + GEAR_T[1] * base, rangefinder=RF_T_K * base ** 2,
                armour=area * d["armour_mm"] / 1000.0 * 7.85, radar=d["radar_t"], computer=d["computer_t"])


def horizon_km(eye_m):
    return 3.57 * math.sqrt(REFRACTION * max(0.0, eye_m))


def place(lay, design, blocks):
    """Stand the design's directors on the superstructure's roofs (layout.roof_spots) as blocks of their own (kind
    "director": drawn and hit like superstructure, appended to blocks), with their weights: the director at its
    height, its plotting room low in the hull. Main directors take the highest roofs, the first two at least
    MAIN_SPREAD of the length apart when they can; secondary and AA directors go in pairs, highest first. Sets
    lay.directors. A director with nowhere to stand is an error (more length rarely helps: it needs a roof)."""
    from layout import _fp_rect, add_block, roof_spots
    from navarch import Weight
    fc = spec(design)
    L = lay.hull.L
    for bat in BATTERIES:
        d = fc[bat]
        n = d["directors"]
        if not n:
            continue
        l, w = size(d)
        hl, hw = l / 2, w / 2
        wt = weights(d)
        mine = []

        def ok(x, y, z0):
            fp = _fp_rect(x - hl, y - hw, x + hl, y + hw)
            return lay.free_at(fp, z0, z0 + HOOD_H, 0.2) and lay.clear(fp, z0 + HOOD_H)

        def put(x, y, z0, pair=False, unit=None):
            k = len(mine)
            if bat == "main":
                bid = LABEL[bat] + ("" if k == 0 else f" {k + 1}")
            else:       # numbered by station: a pair (1S, 1P) or a single director (2)
                bid = f"{LABEL[bat]} {unit}" + (("S" if y > 0 else "P") if pair else "")
            add_block(lay, blocks, bid, x - hl, x + hl, w, 1, 0.45 * min(l, w), 0.45 * min(l, w), y=y, z0=z0,
                      kind="director", t_per_m2=0.0)
            lay.weights.append(Weight(bid, "fire_control", sum(v for k_, v in wt.items() if k_ != "computer"), x=x,
                                      z_rel=("deck", z0 + 0.5 * HOOD_H)))
            if wt["computer"]:
                lay.weights.append(Weight(f"Plotting room ({bid})", "fire_control", wt["computer"], x=x,
                                          z_rel=("frac", COMPUTER_Z)))
            rec = dict(id=bid, battery=bat, x=x, y=y, base=z0, top=z0 + HOOD_H, eye=z0 + EYE_H, **d,
                       weight_t=sum(wt.values()), unit=unit)
            lay.directors.append(rec)
            mine.append(rec)

        spots = roof_spots(blocks, l, w)
        if bat == "main":       # the highest roofs, spread fore and aft; single directors, on the roof's line
            cands = sorted(((x, y, z0) for x, y, z0, pair in spots if not pair), key=lambda s: (-s[2], -s[0]))
            for spread in (MAIN_SPREAD * L, 0.0):
                for x, y, z0 in cands:
                    if len(mine) >= n:
                        break
                    if any(abs(x - m["x"]) < max(spread if len(mine) < 2 else 0.0, l + 0.4) for m in mine):
                        continue
                    if ok(x, y, z0):
                        put(x, y, z0)
        else:                   # pairs, one each side, highest first; an odd one (or all, where no pair fits: a
                                # narrow tower, a carrier's island) singly on a roof's line
            for singles in (False, True):
                # secondary directors take the highest roofs; AA directors the lowest, beside the AA they direct
                for x, y, z0, pair in sorted(spots, key=lambda s: ((s[2] if bat == "aa" else -s[2]), not s[3],
                                                                   abs(s[0]))):
                    left = n - len(mine)
                    if left <= 0:
                        break
                    if pair != (left >= 2 and not singles) or (pair and singles):
                        continue
                    pts = [(x, y), (x, -y)] if pair else [(x, y)]
                    if all(ok(px, py, z0) for px, py in pts):
                        unit = len({m["unit"] for m in mine}) + 1
                        for px, py in pts:
                            put(px, py, z0, pair, unit)
        if len(mine) < n:
            lay.fail(None, f"Only {len(mine)} of {n} {'AA' if bat == 'aa' else bat} directors find a roof to stand on "
                           f"({w:.1f} m across with the rangefinder).")
    main = design.get("main") or {}
    if (main.get("fore", 0) + main.get("aft", 0) + main.get("mid", 0) + main.get("wing", 0)) and \
            not fc["main"]["directors"]:
        lay.warnings.append("The main battery has no director: each turret fires under local control.")


def search_radar(lay, design, blocks, masts, fun_top):
    """The search radar's weight on the foremast's top (masts[0]; its top defaults to fun_top + 6 m, as drawn), or
    1 m over the highest roof on a ship without masts."""
    from layout import block_top
    from navarch import Weight
    t = spec(design)["search_radar_t"]
    if not t:
        return
    if masts:
        m = masts[0]
        lay.weights.append(Weight("Search radar", "fire_control", t, x=m["x"], z_rel=("deck", m.get("top", fun_top + 6.0))))
        return
    top = max(blocks, key=block_top, default=None)
    lay.weights.append(Weight("Search radar", "fire_control", t, x=(top["x0"] + top["x1"]) / 2 if top else 0.0,
                              z_rel=("deck", (block_top(top) if top else 0.0) + 1.0)))


def report(lay, deck_m):
    """The directors for the report: where they stand, how high their eyes are above the waterline (deck_m: the main
    deck's height above it), how far they see, and what they weigh."""
    out = []
    for d in getattr(lay, "directors", []):
        eye = deck_m + d["eye"]
        out.append(dict(id=d["id"], battery=d["battery"], x=round(d["x"], 2), y=round(d["y"], 2),
                        eye_height_m=round(eye, 2), horizon_km=round(horizon_km(eye), 1),
                        rangefinder_m=d["rangefinder_m"], armour_mm=d["armour_mm"], radar_t=d["radar_t"],
                        weight_t=round(d["weight_t"], 1)))
    return out
