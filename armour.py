"""
armour — everything about the ship's armour on the design side: the design's armour inputs and their validation
(armour_errors), where the armour is (armour_geometry: the one source for its weights, the subdivision and the
hitboxes), its weights (armour_weights), the materials named for each part, and the warnings on a solved ship
(armour_checks). Turret and barbette armour are weighed with their mounts (batteries.mount_weights).

A new armour piece goes here: its input check in armour_errors, its geometry in armour_geometry, its weight in
armour_weights. hitbox.py and subdivision.py only publish what armour_geometry returns.
Heights are metres above the keel. Design side, standard library only.
"""
from __future__ import annotations

from decks import deck_name, deck_stack, raised_pieces
from geometry import DECK_PITCH, cwp
import ordnance
import powerplant
from propulsion import steering_span
from weights import STEEL, Weight

TUNING = dict(
    tds_mm_per_m=12.0,      # torpedo protection: longitudinal bulkheads totalling this many mm per metre of
                            # armour.tds_m, each side over the citadel, inner bottom to the roof deck (Bismarck
                            # 45 mm torpedo bulkhead plus thinner ones, 5.5 m deep; Iowa four bulkheads, 5.2 m)
    belt_h_a=0.30, belt_h_b=2.4,   # belt height = a*T + b, half below the waterline (when the design gives none)
)

ARMOUR_EXTENTS = ("citadel", "full", "fore", "aft", "ends")
BELT_ENDS = ("fore", "aft")


ARMOUR_PARTS = ("belt", "upper_belt", "end_belts", "bulkheads", "decks", "turrets", "barbettes", "conning_tower",
                "secondary", "flight_deck")


# extents that may share one deck (different stretches of it)
SHARED_DECK = ({"citadel", "fore"}, {"citadel", "aft"}, {"citadel", "ends"}, {"fore", "aft"})


def armour_errors(design) -> list[str]:
    """armour.decks: a list of {"deck": n (0 the main deck, 1 the second, ..., -1 the first raised deck), "mm",
    "extent"}, top down."""
    a = design.get("armour") or {}
    errs = []
    if "deck_mm" in a:
        errs.append("armour.deck_mm is gone: list the armour decks top down in armour.decks, e.g. "
                    "[{\"deck\": 1, \"mm\": 152, \"extent\": \"citadel\"}]")
    if "turret_mm" in a:
        errs.append("armour.turret_mm is gone: give each main battery its turrets' armour_mm (main[k].armour_mm)")
    decks = a.get("decks", [])
    if not isinstance(decks, list):
        return errs + ["armour.decks: use a list of armour decks, top down"]
    last, prev = None, None
    for k, d in enumerate(decks):
        if not isinstance(d, dict) or not isinstance(d.get("deck"), int):
            errs.append(f"armour.decks[{k}].deck: use a deck number (0 the main deck, 1 the second deck, ..., -1 "
                        "the first raised deck)")
            continue
        if not isinstance(d.get("mm"), (int, float)) or d["mm"] < 0:
            errs.append(f"armour.decks[{k}].mm: use a thickness of 0 or more")
        if d.get("extent") not in ARMOUR_EXTENTS:
            errs.append(f"armour.decks[{k}].extent = {d.get('extent')!r}: use {' or '.join(ARMOUR_EXTENTS)}")
        if last is not None and d["deck"] < last:
            errs.append(f"armour.decks[{k}]: list the armour decks top down")
        elif d["deck"] == last and {d.get("extent"), prev} not in SHARED_DECK:
            errs.append(f"armour.decks[{k}]: a deck may appear twice only over different stretches (the citadel "
                        "and its ends)")
        last, prev = d["deck"] if last is None else max(last, d["deck"]), d.get("extent")
    ub = a.get("upper_belt")
    if ub is not None:
        if not isinstance(ub, dict):
            errs.append("armour.upper_belt: use {\"mm\", \"to_deck\", \"extent\"}")
        else:
            if not isinstance(ub.get("to_deck", 0), int):
                errs.append("armour.upper_belt.to_deck: use a deck number (0 the main deck, 1 the second deck, ..., "
                            "-1 the first raised deck)")
            if ub.get("extent", "citadel") not in ARMOUR_EXTENTS:
                errs.append(f"armour.upper_belt.extent = {ub.get('extent')!r}: use {' or '.join(ARMOUR_EXTENTS)}")
    mats = a.get("materials")
    if mats is not None:
        if not isinstance(mats, dict):
            errs.append("armour.materials: name a material per part, e.g. {\"belt\": \"Krupp cemented\", ...}")
        else:
            errs += [f"armour.materials.{k}: not an armour part ({', '.join(ARMOUR_PARTS)})" for k in mats
                     if k not in ARMOUR_PARTS]
            errs += [f"armour.materials.{k}: name the material as a string" for k, v in mats.items()
                     if not isinstance(v, str) or not v]
    owns = [(f"armour.decks[{k}]", d) for k, d in enumerate(decks) if isinstance(d, dict)]
    owns += [("armour.upper_belt", a["upper_belt"])] if isinstance(a.get("upper_belt"), dict) else []
    owns += [(f"armour.end_belts.{e}", v) for e, v in (a.get("end_belts") or {}).items() if isinstance(v, dict)] \
        if isinstance(a.get("end_belts"), dict) else []
    owns += [("armour.steering_box", a["steering_box"])] if isinstance(a.get("steering_box"), dict) else []
    owns += [("armour.steering_box.deck", {"material": a["steering_box"]["deck_material"]})] \
        if isinstance(a.get("steering_box"), dict) and "deck_material" in a["steering_box"] else []
    sec = design.get("secondary") or []
    owns += [(f"secondary[{k}]", b) for k, b in enumerate(sec if isinstance(sec, list) else [sec]) if isinstance(b, dict)]
    mb = design.get("main") or []
    owns += [(f"main[{k}]", b) for k, b in enumerate(mb if isinstance(mb, list) else [mb]) if isinstance(b, dict)]
    errs += [f"{where}.material: name the material as a string" for where, d in owns
             if "material" in d and (not isinstance(d["material"], str) or not d["material"])]
    eb = a.get("end_belts")
    if eb is not None:
        if not isinstance(eb, dict) or set(eb) - {"fore", "aft"}:
            errs.append("armour.end_belts: use {\"fore\": {\"mm\", \"tip_mm\", \"reach\", \"bulkhead_mm\"}, "
                        "\"aft\": {...}}")
        else:
            errs += [f"armour.end_belts.{end}: use {{\"mm\", \"tip_mm\", \"reach\", \"bulkhead_mm\"}}"
                     for end, e in eb.items() if not isinstance(e, dict)]
    sb = a.get("steering_box")
    if sb is not None and (not isinstance(sb, dict) or set(sb) - {"mm", "deck_mm", "bulkhead_mm", "material",
                                                                  "deck_material"}):
        errs.append("armour.steering_box: use {\"mm\", \"deck_mm\", \"bulkhead_mm\"} (0 for none)")
    return errs


def armour_material(design, part, own=None):
    """The armour material named for a part (armour.materials[part]; a deck or battery may give its own): a
    plain string passed through to the hitboxes for the game's ballistics, or None if the design names none."""
    return own.get("material") if own and own.get("material") else (
        ((design.get("armour") or {}).get("materials") or {}).get(part))


def armour_decks(design, D, raised=()):
    """The design's armour decks (armour.decks, top down), placed on the deck stack: [dict(deck, mm, extent, z,
    asked, material)]. A deck the hull is too shallow for lies on its lowest deck, and a raised deck (-1, -2, ...)
    higher than any raised stretch (raised: lay.raised) on the highest there is, or the main deck (asked keeps what
    the design said). A raised deck's plates exist only over its stretches (armour_geometry)."""
    stack = deck_stack(design, D)
    top = -max((s["levels"] for s in raised), default=0)
    out = []
    for d in (design.get("armour") or {}).get("decks") or []:
        n = max(top, min(int(d.get("deck", 0)), stack[-1][0]))
        out.append(dict(deck=n, mm=d.get("mm", 0), extent=d.get("extent", "citadel"),
                        z=stack[n][1] if n >= 0 else D - n * DECK_PITCH,
                        asked=int(d.get("deck", 0)), material=armour_material(design, "decks", d)))
    return out


def extent_spans(extent, L, x0, x1):
    """An armour extent as [(extent, x0, x1)] pieces: the citadel, the whole hull, or the hull beyond either
    end of the citadel ("ends" is both)."""
    return {"citadel": [("citadel", x0, x1)], "full": [("full", -L / 2, L / 2)],
            "fore": [("fore", x1, L / 2)], "aft": [("aft", -L / 2, x0)],
            "ends": [("fore", x1, L / 2), ("aft", -L / 2, x0)]}[extent]


def belt_mm_at(s, x, z=None):
    """A belt's thickness at x (and height z, on the same scale as its bottom): mm at its root (the citadel end),
    tapering linearly to tip_mm at the hull's end. A belt with bottom_mm (the main belt) keeps its thickness down
    to the waterline (wl), then tapers linearly to bottom_mm at its lower edge."""
    mm = s["mm"]
    if s["tip_mm"] != mm and s["x1"] - s["x0"] > 0:
        f = (x - s["x0"]) / (s["x1"] - s["x0"])
        if s["extent"] == "aft":
            f = 1.0 - f
        mm += (s["tip_mm"] - mm) * min(1.0, max(0.0, f))
    if z is not None and s.get("bottom_mm", mm) != mm and z < s["wl"] and s["wl"] > s["bottom"]:
        f = max(0.0, (z - s["bottom"]) / (s["wl"] - s["bottom"]))
        mm = s["bottom_mm"] + (mm - s["bottom_mm"]) * f
    return mm


def armour_geometry(design, L, T, D, geo):
    """Where the armour is: the one source for its weights and its hitboxes. Heights in metres above the keel.
      decks     the armour decks (armour_decks) as plates over their x extents: the citadel, the whole hull
                ("full"), or the hull beyond the citadel's fore or aft end ("ends" is a plate at each end)
      main      the main armour deck: the thickest over the citadel (the higher of equals), or None
      roof      the lowest armour deck over the citadel: the machinery and magazines stand under it (None if none)
      belt      the main belt over the citadel, armour.belt_mm thick down to the waterline, then tapering to
                armour.belt_bottom_mm at its lower edge: from armour.belt_depth_m below the full-load waterline to
                armour.belt_height_m above it, or up to the main armour deck when that is higher (kept between
                keel and main deck; TUNING belt_h, half below and half above, when the design gives none)
      strakes   the rest of the side armour, each dict(id, kind, extent, mm, tip_mm, x0, x1, bottom, top,
                material):
                  end    armour.end_belts: the waterline belt carried on from the citadel toward the stem ("fore")
                         or stern ("aft"), reach of the way there (1: all the way), at the main belt's depth, up
                         to the thickest armour deck over that end when that is higher; mm at the citadel
                         tapering to tip_mm at its far end
                  upper  armour.upper_belt: from the top of the belt below it up to armour.upper_belt.to_deck,
                         over its extent (one strake per stretch: the citadel, fore and aft)
                  box    armour.steering_box: the sides of a separate box round the steering gear (steering_span),
                         from the inner bottom (the gear stands low) up to its roof, the deck over the gear
      bulkheads the citadel's transverse bulkheads (armour.bulkhead_mm, 0.6 of the belt if not given) close the
                belts' ends, from the top of the main or upper belt over the citadel down to 0.4 belt heights
                below the belt.
      end_bulkheads  the other armoured transverse bulkheads, each dict(id, x, mm, bottom, top, material): one
                closing an end belt that stops short of the hull's end (its bulkhead_mm), from the citadel
                bulkheads' lower edge up to the belt's top, and the steering box's two ends
                (steering_box.bulkhead_mm), as tall as its sides. The box's roof is a deck plate (extent
                "steering") on the deck over the steering gear (ordnance.span, as layout.add_steering stands it). The
                box's roof and bulkheads span the hull's width there (geo["steering_beam"]; the beam without one).
      materials armour.materials, by part (armour_material): belt_material, bulkhead_material, roof_material,
                and material on each deck plate and strake. Strings only, for the game's ballistics."""
    a = design.get("armour") or {}
    belt = a.get("belt_mm", 0)
    x0, x1 = geo.get("citadel", (-0.3 * L, 0.3 * L))
    raised = geo.get("raised", ())
    decks = []
    for d in armour_decks(design, D, raised):
        if d["mm"] <= 0:
            continue
        spans = extent_spans(d["extent"], L, x0, x1)
        if d["deck"] < 0:     # a raised deck: only over its stretches
            spans = [(ext, a_, b_) for ext, s0, s1 in spans for a_, b_, lv in raised_pieces(raised, s0, s1, -d["deck"])
                     if lv >= -d["deck"]]
        for ext, p0, p1 in spans:
            # pushed onto one deck by a shallow hull: overlapping plates make one
            p = next((p for p in decks if p["deck"] == d["deck"] and min(p["x1"], p1) - max(p["x0"], p0) > 1e-6),
                     None)
            if p:
                p.update(mm=p["mm"] + d["mm"], x0=min(p["x0"], p0), x1=max(p["x1"], p1),
                         extent="full" if "full" in (p["extent"], ext) else p["extent"],
                         material=p["material"] if d["material"] in (None, p["material"]) else
                         d["material"] if p["material"] is None else f"{p['material']} + {d['material']}")
                continue
            decks.append({**d, "extent": ext, "x0": p0, "x1": p1})
    over = [d for d in decks if d["extent"] in ("citadel", "full") and d["deck"] >= 0]  # the stack's plates over the
                                                                                        # citadel
    main = max(over, key=lambda d: (d["mm"], d["z"]), default=None)
    roof = min(over, key=lambda d: d["z"], default=None)
    h0 = TUNING["belt_h_a"] * T + TUNING["belt_h_b"]
    below, above = a.get("belt_depth_m", h0 / 2), a.get("belt_height_m", h0 / 2)
    h = below + above
    bot = max(0.0, T - below)
    band = min(D, max(bot, T + above))
    top = min(D, max(band, main["z"] if main else 0.0))

    strakes, end_bhs = [], []
    bh_bot = max(0.0, bot - 0.4 * h)
    tops = {"citadel": top if belt > 0 else band}         # where an upper belt starts over each stretch
    for end in BELT_ENDS:
        e = (a.get("end_belts") or {}).get(end) or {}
        tops[end] = band
        if e.get("mm", 0) <= 0:
            continue
        _, s0, s1 = extent_spans(end, L, x0, x1)[0]
        reach = min(1.0, max(0.0, e.get("reach", 1.0)))
        if end == "fore":       # reach of the way from the citadel to the stem (stern)
            s1 = s0 + (s1 - s0) * reach
        else:
            s0 = s1 - (s1 - s0) * reach
        cover = [d for d in decks if d["x0"] <= (s0 + s1) / 2 <= d["x1"] and d["extent"] in (end, "full")]
        dk = max(cover, key=lambda d: (d["mm"], d["z"]), default=None)
        et = min(D, max(band, dk["z"] if dk else 0.0))
        tops[end] = et
        if s1 - s0 > 1e-6:
            strakes.append(dict(id=f"{end.capitalize()} end belt", kind="end", extent=end, mm=e["mm"],
                                tip_mm=e.get("tip_mm", e["mm"]), x0=s0, x1=s1, bottom=bot, top=et,
                                material=armour_material(design, "end_belts", e)))
            if reach < 1.0 and e.get("bulkhead_mm", 0) > 0:     # closing the belt where it stops short
                end_bhs.append(dict(id=f"{end.capitalize()} end belt bulkhead", x=s1 if end == "fore" else s0,
                                    mm=e["bulkhead_mm"], bottom=bh_bot, top=et,
                                    material=armour_material(design, "bulkheads")))
    sb = a.get("steering_box") or {}
    if max(sb.get("mm", 0), sb.get("deck_mm", 0), sb.get("bulkhead_mm", 0)) > 0:
        # a compact box round the steering gear, which stands low (layout.add_steering: ordnance.span over the inner
        # bottom): sides from the inner bottom to the deck over the gear, a roof on that deck, bulkheads at both ends
        b0, b1 = steering_span(L, geo)
        stack = deck_stack(design, D)
        wbox = geo.get("steering_beam")
        rz_ = ordnance.span(dict(decks=[z for _, z in stack], inner_bottom=powerplant.double_bottom(D),
                                 top=roof["z"] if roof else D))[1] + D
        n = min(stack, key=lambda v: abs(v[1] - rz_))[0]
        if sb.get("deck_mm", 0) > 0:
            decks.append(dict(deck=n, mm=sb["deck_mm"], extent="steering", z=rz_, asked=n, x0=b0, x1=b1, w=wbox,
                              material=armour_material(design, "decks", sb.get("deck_material") and
                                                       {"material": sb["deck_material"]})))
        floor = min(powerplant.double_bottom(D), rz_)
        if sb.get("mm", 0) > 0:
            strakes.append(dict(id="Steering gear box", kind="box", extent="aft", mm=sb["mm"], tip_mm=sb["mm"],
                                x0=b0, x1=b1, bottom=floor, top=rz_,
                                material=armour_material(design, "end_belts", sb)))
        if sb.get("bulkhead_mm", 0) > 0:
            end_bhs += [dict(id=f"Steering gear box {w} bulkhead", x=x, mm=sb["bulkhead_mm"], bottom=floor,
                             top=rz_, w=wbox, material=armour_material(design, "bulkheads"))
                        for w, x in (("forward", b1), ("aft", b0))]
    ub = a.get("upper_belt") or {}
    if ub.get("mm", 0) > 0:
        stack = deck_stack(design, D)
        to = int(ub.get("to_deck", 0))
        ut = stack[min(max(to, 0), stack[-1][0])][1]
        pieces = extent_spans(ub.get("extent", "citadel"), L, x0, x1)
        if ub.get("extent") == "full":
            pieces = [("citadel", x0, x1), ("fore", x1, L / 2), ("aft", -L / 2, x0)]
        for ext, s0, s1 in pieces:
            # up to a raised deck (to_deck -1, -2, ...): to it over its stretches, to the main deck elsewhere
            parts = raised_pieces(raised, s0, s1, -to) if to < 0 else [(s0, s1, 0)]
            for k, (p0, p1, lv) in enumerate(parts):
                top_ = ut + lv * DECK_PITCH
                if top_ > tops[ext] + 0.05 and p1 - p0 > 1e-6:
                    sid = "Upper belt" if ext == "citadel" else f"Upper belt ({ext})"
                    strakes.append(dict(id=sid + (f" {k + 1}" if len(parts) > 1 else ""), kind="upper",
                                        extent=ext, mm=ub["mm"], tip_mm=ub["mm"], x0=p0, x1=p1, bottom=tops[ext],
                                        top=top_, material=armour_material(design, "upper_belt", ub)))
    bh_top = max([top] + [s["top"] for s in strakes if s["kind"] == "upper" and s["extent"] == "citadel"])
    return dict(x0=x0, x1=x1, belt_mm=belt, belt_bottom_mm=a.get("belt_bottom_mm", belt), waterline=T,
                belt_bottom=bot, belt_top=top, decks=decks, strakes=strakes,
                main_z=main["z"] if main else None, roof_z=roof["z"] if roof else None,
                roof_mm=roof["mm"] if roof else 0, roof_material=roof["material"] if roof else None,
                belt_material=armour_material(design, "belt"), bulkhead_material=armour_material(design, "bulkheads"),
                armoured=belt > 0 or bool(over),
                bulkhead_mm=a.get("bulkhead_mm", 0.6 * belt), bulkhead_bottom=bh_bot,
                bulkhead_top=bh_top, end_bulkheads=end_bhs)


def armour_weights(design, L, B, D, g):
    """The armour's weights from its geometry (armour_geometry)."""
    lc = g["x1"] - g["x0"]
    xc = (g["x0"] + g["x1"]) / 2
    zf = lambda lo, hi: ("frac", (lo + hi) / 2 / D if D else 0.5)
    out = []
    if g["belt_mm"] > 0:
        # full thickness above the waterline (t0 .. top), tapering to belt_bottom_mm below it (bot .. t0)
        bot, top, mm, mb = g["belt_bottom"], g["belt_top"], g["belt_mm"], g["belt_bottom_mm"]
        t0 = min(top, max(bot, g["waterline"]))
        a_up, a_lo = (top - t0) * mm, (t0 - bot) * (mm + mb) / 2           # m x mm per side
        z_lo = bot + (t0 - bot) * (mb + 2 * mm) / (3 * (mb + mm)) if mb + mm > 0 else bot
        zc = ((top + t0) / 2 * a_up + z_lo * a_lo) / (a_up + a_lo) if a_up + a_lo > 0 else (top + bot) / 2
        out.append(Weight("Belt armour", "armour", 2 * lc * (a_up + a_lo) / 1000 * STEEL, x=xc,
                          z_rel=("frac", zc / D if D else 0.5)))
    if g["armoured"] and g["bulkhead_mm"] > 0:
        hb = g["bulkhead_top"] - g["bulkhead_bottom"]
        out.append(Weight("Bulkheads", "armour", 2 * B * hb * g["bulkhead_mm"] / 1000 * STEEL, x=xc,
                          z_rel=zf(g["bulkhead_top"], g["bulkhead_bottom"])))
    for b in g["end_bulkheads"]:      # across the hull there (an end belt's: the beam, a little heavy at the ends)
        out.append(Weight(b["id"], "armour", (b.get("w") or B) * (b["top"] - b["bottom"]) * b["mm"] / 1000 * STEEL,
                          x=b["x"],
                          z_rel=zf(b["top"], b["bottom"])))
    for s in g["strakes"]:
        a, b = (s["mm"], s["tip_mm"]) if s["extent"] != "aft" else (s["tip_mm"], s["mm"])   # thickness at x0, x1
        f = (a + 2 * b) / (3 * (a + b)) if a + b > 0 else 0.5                             # trapezoid centroid
        out.append(Weight(s["id"], "armour", 2 * (s["x1"] - s["x0"]) * (s["top"] - s["bottom"]) * (a + b) / 2
                          / 1000 * STEEL, x=s["x0"] + f * (s["x1"] - s["x0"]), z_rel=zf(s["top"], s["bottom"])))
    tds = (design.get("armour") or {}).get("tds_m", 0.0)
    if tds > 0 and lc > 0:
        floor = powerplant.double_bottom(D)
        top = g["roof_z"] if g["roof_z"] is not None else g["waterline"]
        mm = TUNING["tds_mm_per_m"] * tds
        out.append(Weight("Torpedo protection", "armour", 2 * lc * max(0.0, top - floor) * mm / 1000 * STEEL, x=xc,
                          z_rel=zf(top, floor)))
    cb = design["hull"]["block_coefficient"]
    for d in g["decks"]:
        area = (L * cwp(cb) if d["extent"] == "full" else d["x1"] - d["x0"]) * (d.get("w") or B) * 0.9
        name = f"Deck armour ({deck_name(d['deck']).lower()}" + (
            f", {d['extent']})" if d["extent"] in BELT_ENDS + ("steering",) else ")")
        out.append(Weight(name, "armour", area * d["mm"] / 1000 * STEEL,
                          x=0.0 if d["extent"] == "full" else (d["x0"] + d["x1"]) / 2, z_rel=("deck", d["z"] - D)))
    return out


def armour_checks(design, res, geo):
    """Warnings on the solved ship's armour (res: navarch.Result, with its armour geometry): an armour deck the hull
    is too shallow for, a belt too shallow under the waterline, an upper belt with no height."""
    out = []
    for d in armour_decks(design, res.depth, geo.get("raised", ())):
        if d["asked"] != d["deck"]:
            out.append(f"The hull has no {deck_name(d['asked']).lower()} ({res.depth:.1f} m deep): its "
                       f"{d['mm']} mm deck armour lies on the {deck_name(d['deck']).lower()}.")
    arm = design.get("armour") or {}
    if arm.get("belt_mm", 0) > 0 and arm.get("belt_depth_m", 1.0) < 1.0:
        out.append(f"The belt reaches only {arm['belt_depth_m']:.1f} m below the waterline: rolling or "
                   "flooding uncovers the side under it.")
    ub = (design.get("armour") or {}).get("upper_belt") or {}
    if ub.get("mm", 0) > 0 and not any(s["kind"] == "upper" for s in res.armour["strakes"]):
        out.append(f"The {ub['mm']} mm upper belt has no height: the belt below it already reaches the "
                   f"{deck_name(ub.get('to_deck', 0)).lower()}.")
    return out
