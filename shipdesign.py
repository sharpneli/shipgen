"""
shipdesign: the design side. A player's design (JSON) in, the designed ship out as plain data. No drawing.

    import shipdesign
    errors = shipdesign.validate(design)          # input errors; [] means build() can run
    ship = shipdesign.build(design)               # plain, JSON-serialisable dict

ship = {
  "design":   the input design, unchanged (its "look" is passed through for the renderer, never read here)
  "report":   validity, errors, warnings, displacement, power, stability, hull structure and girder, weights (report.json)
  "hitboxes": hull, components with heights and firing arcs, subdivision cells and rooms (hitboxes.json)
  "render":   what the renderer needs to draw the ship, all in ship-local metres:
      spec      the drawing spec: hull form, turret types and mounts, superstructure, funnels, masts, boats,
                AA, fittings, decks
      deck_m    main deck height above the waterline
      mounts    per mount: id, kind, rest bearing, arcs, roof height above the main deck, and "mount": "casemate"
                for a casemate gun (in the hull side)
      columns   the static height-map columns, lowest first: {top (m above the waterline), shape, ...} with
                shape "hull" (the hull as drawn), "polygon" (points), "rect" (x, y, w, h), "circle" (cx, cy, r)
                or "ellipse" (cx, cy, rx, ry)
      summary   extra text lines about the design (carrier aviation, merchant cargo, ...)
}

This module and everything it imports (navarch, layout, armament, hitbox, styles, geometry) need nothing beyond
the standard library. The renderer (render.py) consumes only the dict above.
"""
from __future__ import annotations

import copy

import crew
import firecontrol
import hullweight
import navarch
import styles
from geometry import AA_CFG, HullForm, cwp, has_barbette, rrect_polygon, block_outline
from arcs import assign_arcs
from firecontrol import assign_smoke
from hitbox import export_hitboxes
import powerplant
from weights import SEAWATER
import propulsion
import stability
import subdivision
from layout import LEVEL_H, block_top, own_plate_mm

MAST_ABOVE_FUNNEL = 6.0   # mast tops sit this far above the funnel tops


def validate(design, limits=True):
    """Input errors. limits=False skips the numeric ranges (--no-limits); structural checks stay."""
    try:
        style = styles.get(design)
    except KeyError as e:
        return [str(e.args[0])]
    errs = []
    for path, (lo, hi) in (style.limits() if limits else {}).items():
        ds = [design]
        for k in path[:-1]:       # a list (several secondary batteries) checks every entry
            ds = [e for d in ds for e in (lambda v: v if isinstance(v, list) else [v or {}])(d.get(k))]
        for d in ds:
            if path[-1] not in d:
                continue
            v = d[path[-1]]
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                errs.append(f"{'.'.join(path)} = {v!r}: give a number, {lo}..{hi}")
            elif not lo <= v <= hi:
                errs.append(f"{'.'.join(path)} = {v} is outside {lo}..{hi}")
    if "id" not in design:
        errs.append("design needs an 'id'")
    return errs + style.validate(design)


def min_length(disp_t, v_kn):
    """The shortest hull a displacement ship of disp_t tonnes gets for v_kn knots: slenderness L / volume^(1/3)
    rises with the volumetric Froude number Fn∇, from 5.25 for slow ships (Liberty, Mikasa) to 8.2 for
    destroyers (Fletcher). Fitted to 16 real ships 1900-1945; within about 5% of most."""
    root = (disp_t / SEAWATER) ** (1 / 3)
    fnv = navarch.volumetric_froude(disp_t, v_kn)
    return max(5.25, min(8.2, 5.25 + 5.0 * (fnv - 0.55))) * root


def with_hull(design, L, B):
    """The design with a hull of L x B metres (and the style's block coefficient if it gives none)."""
    hull = design.get("hull") or {}
    cb = hull.get("block_coefficient", styles.get(design).DEFAULT_CB)
    return {**design, "hull": {**hull, "length": L, "beam": B, "block_coefficient": cb}}


def beam_needed(design, L, B, weights, geo):
    """The narrowest beam (at least B) for a hull of length L carrying `weights` (placed, from a layout): GM at
    least SIZE gm_frac x beam, draught at most tb x beam, and length at most lb_max x beam."""
    size = styles.get(design).SIZE
    b_max = size["beam_max"]
    lo = max(B, L / size["lb_max"])

    def ok(b):
        r = navarch.solve(with_hull(design, L, b), weights, geo)
        return r.gm_full >= size["gm_frac"] * b and r.draught <= size["tb"] * b

    if ok(lo):
        return lo
    hi = lo
    while hi < b_max:          # bracket: widen by steps of 15%
        lo, hi = hi, min(b_max, hi * 1.15)
        if ok(hi):
            break
    else:
        return b_max
    while hi - lo > 0.05 * max(1.0, lo / 10):     # to about half a percent
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if ok(mid) else (mid, hi)
    return hi


def lay_out(design, r, shift=0.0, spread=0.0):
    """The style's layout for the solved weights r, then crewed (crew.apply: complement, space, weights)."""
    style = styles.get(design)
    lay = style.build_layout(design, r, shift, spread)
    crew.apply(lay, design, r, style)
    return lay


def fit(design, L, B=0.0):
    """Does everything fit on a hull of length L? Returns (fits, beam): the beam is the narrowest that carries
    the load (beam_needed) and has room across for what the layout places."""
    b_max = styles.get(design).SIZE["beam_max"]
    B = max(B, L / styles.get(design).SIZE["lb_max"])
    slender = styles.get(design).SIZE["slender"]
    for _ in range(12):
        d = with_hull(design, L, B)
        r = navarch.solve(d)
        lay = lay_out(d, r, 0.0)
        B2 = beam_needed(design, L, B, lay.weights, lay.geo)
        if "beam" in lay.short and B < b_max:
            B2 = max(B2, B * 1.05)
        if B2 <= B * 1.005:
            break
        B = min(B2, b_max)
    long_enough = not slender or L >= min_length(r.full, design["speed_kn"])
    return "length" not in lay.short and long_enough, B


def size(design, hint=None):
    """The hull for a design that gives none: the shortest that fits everything at the layout's comfortable
    clearances (searched on a half-metre grid), and the narrowest beam that carries it (fit). Returns (L, B).
    hint: the length of a similar design (the same one before a small change) to start the search from."""
    l_min, l_max = styles.get(design).SIZE["length"]
    snap = lambda v: max(l_min, min(l_max, round(v * 2) / 2))
    if hint:
        L, step = snap(hint), 1.03
    else:   # first guess from the displacement of the contents on a hull of typical proportions
        L, step = 100.0, 1.15
        for _ in range(3):
            r = navarch.solve(with_hull(design, L, L / 7.5))
            L = snap(5.0 * r.full ** (1 / 3))
    cache = {}

    def ok(L):
        if L not in cache:
            cache[L] = fit(design, L)
        return cache[L][0]

    lo = hi = None   # longest that fails, shortest that fits
    if ok(L):
        hi = L
        while hi > l_min:
            L = snap(min(hi - 0.5, hi / step))
            if not ok(L):
                lo = L
                break
            hi = L
    else:
        lo = L
        while lo < l_max:
            L = snap(max(lo + 0.5, lo * step))
            if ok(L):
                hi = L
                break
            lo = L
    if hi is None:            # nothing fits even the longest hull: take it, its errors say what doesn't fit
        hi = l_max
    while lo is not None and hi - lo > max(0.5, 0.004 * hi):
        mid = snap((lo + hi) / 2)
        if mid in (lo, hi):
            break
        if ok(mid):
            hi = mid
        else:
            lo = mid
    return hi, round((cache.get(hi) or fit(design, hi))[1], 2)


def solve(design, iterations=6, hint=None):
    """Size the hull (size), then lay it out and balance it (balance). Returns the internal (layout, navarch.Result,
    sized design); build() turns them into the published dict."""
    L, B = size(design, hint)
    l_max, b_max = styles.get(design).SIZE["length"][1], styles.get(design).SIZE["beam_max"]
    for _ in range(6):   # the balanced layout may still come up short of what the search found: grow a step
        lay, r, sized = balance(with_hull(design, L, B), iterations)
        if not lay.short or (L >= l_max and B >= b_max):
            break
        if "beam" in lay.short:
            B = min(b_max, round(B * 1.03, 2))
        if "length" in lay.short:
            L = min(l_max, max(L + 0.5, round(L * 1.01 * 2) / 2))
    if "length" in lay.short and L >= l_max and not lay.errors:
        lay.errors.append(f"Not everything fits even on the longest hull ({l_max:,.0f} m). Carry less.")
    if not lay.short:
        lay, r, sized = spread_ends(sized, lay, r, iterations)
    return lay, r, sized


def spread_ends(design, lay, r, iterations=6):
    """The hull is sized with the spare length (a hull longer than its middle needs: crew space, fuel, the speed
    rule) amidships. Give the ends as much of it as they take (the layout's spread) without the layout faring worse:
    nothing short, no new errors or layout warnings (a director moved into the smoke, a torpedo mount that no longer
    fits beside the funnels: the middle's length need doesn't count everything standing there). The citadel then
    covers the end groups and machinery and no more, and the heavy middle stays compact. Returns the balanced
    (layout, result, design) with the largest such spread found (bisected), else the ones given."""
    shift = lay.geo.get("shift", 0.0)

    def outcome(s):
        l_ = lay_out(design, r, shift, s)
        r_ = navarch.solve(design, l_.weights, l_.geo)
        assign_smoke(l_, r_)
        return bool(l_.short), set(l_.errors) | set(r_.errors), set(l_.warnings)

    _, errs0, warns0 = outcome(0.0)

    def ok(o):
        return not o[0] and o[1] <= errs0 and o[2] <= warns0

    if ok(outcome(1.0)):
        s = 1.0
    else:
        lo, hi = 0.0, 1.0
        for _ in range(5):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if ok(outcome(mid)) else (lo, mid)
        s = lo
    if s <= 0.0:
        return lay, r, design
    lay2, r2, _ = balance(design, iterations, s)
    if lay2.short or not set(lay2.errors) | set(r2.errors) <= errs0 or not set(lay2.warnings) <= set(lay.warnings):
        return lay, r, design      # the balance moved it somewhere worse: keep the middle's spare
    return lay2, r2, design


def balance(design, iterations=6, spread=0.0):
    """Rough solve -> layout -> solve -> shift to balance; repeat until stable. The layout can jump as things
    move (a gun takes another slot), so once the moment changes sign the shift is bisected between the last two,
    and the best balanced shift seen is used."""
    r = navarch.solve(design)
    shift = 0.0
    lay = None
    best = None                # (|moment|, shift)
    bracket = []               # (shift, moment) on each side of balance
    for _ in range(iterations + 4):
        lay = lay_out(design, r, shift, spread)
        r = navarch.solve(design, lay.weights, lay.geo)
        shift = lay.geo["shift"]
        moment = sum(w.w * (w.x - r.lcb) for w in r.weights)
        movable = sum(w.w for w in r.weights if w.group not in ("hull", "misc"))
        if best is None or abs(moment) < best[0]:
            best = (abs(moment), shift)
        bracket = [b for b in bracket if (b[1] > 0) != (moment > 0)][-1:] + [(shift, moment)]
        if len(bracket) == 2:        # balance lies between two shifts: bisect
            new_shift = (bracket[0][0] + bracket[1][0]) / 2
        else:
            new_shift = max(lay.shift_range[0], min(lay.shift_range[1], shift - moment / movable))
        if abs(new_shift - shift) < 0.05:
            break
        shift = new_shift
    shift = best[1]
    lay = lay_out(design, r, shift, spread)
    r = navarch.solve(design, lay.weights, lay.geo)
    assign_arcs(lay)
    assign_smoke(lay, r)
    return lay, r, design


def plant_report(lay, r):
    """The plant's static numbers for the game (powerplant.published) and how it sits in the hull."""
    plan = lay.geo.get("plant") or {}
    sp = plan.get("space", {})
    fp = lay.geo.get("funnel_plan") or {}
    extra = dict(
        machinery_length_m=round(sum(seg_l for _, seg_l in plan.get("segments", [])), 1),
        boiler_rooms=sum(1 for c in lay.compartments if c["kind"] == "boiler_room"),
        engine_rooms=sum(1 for c in lay.compartments if c["kind"] == "engine_room"),
        rows=sp.get("rows"), protrusion_m=round(sp.get("protrusion", 0.0), 2),
        space_m=dict(width=round(plan.get("width", 0.0), 2), height=round(plan.get("height", 0.0), 2)),
        wing_bunkers_t=round(plan.get("wing_t", 0.0)), end_bunkers_m=round(plan.get("end_m", 0.0), 1),
        funnels=len(lay.funnels), funnel_gas_area_m2=round(fp.get("area", 0.0), 1),
        funnel_gas_velocity_m_s=round(fp.get("velocity", 0.0), 1),
        smoke_reach_m=round(powerplant.smoke_reach(r.plant, r.power_shp), 1) if lay.funnels else 0.0)
    return powerplant.published(r.plant, r.power_shp, extra)


def hull_report(design, r):
    """The hull structure (hullweight.hull_structure) and its girder amidships, for the damage model: the girder
    holds while its moment of inertia (plating plus armour decks; losing either takes its part away) stays above
    required_m4."""
    h = r.hull
    if "t_min_mm" not in h:     # a style that keeps the volume law (planing craft)
        return dict(structure_t=round(h["t"]))
    return dict(
        construction=hullweight.construction(design).get("name"), structure_t=round(h["t"]),
        min_gauge_t=round(h["min_gauge_t"]), strength_t=round(h["strength_t"]),
        plate_min_mm=round(h["t_min_mm"], 1), plate_strength_mm=round(h["t_str_mm"], 1),
        shell_plating_t=round(h["shell_t"]),
        girder=dict(allowable_stress_mpa=round(h["stress_mpa"], 1), required_m4=round(h["i_req_m4"], 2),
                    plating_m4=round(h["i_plating_m4"], 2), armour_decks_m4=round(h["i_armour_m4"], 2)))


def report_dict(design, lay, r, sized):
    """design: the player's input (echoed in "inputs"); sized: the same with the hull the designer chose."""
    h = sized["hull"]
    return dict(
        id=design["id"], name=design.get("name", design["id"]), valid=not (lay.errors or r.errors),
        errors=lay.errors + r.errors, warnings=lay.warnings + r.warnings,
        inputs=design,
        results=dict(
            length_m=h["length"], beam_m=h["beam"], block_coefficient=h["block_coefficient"],
            standard_displacement_t=round(r.std), full_displacement_t=round(r.full),
            draught_m=round(r.draught, 2), depth_m=round(r.depth, 2), freeboard_m=round(r.freeboard, 2),
            power_shp=round(r.power_shp, -2), fuel_t=round(r.fuel), crew=lay.crew["complement"],
            gm_full_m=round(r.gm_full, 2), gm_light_m=round(r.gm_light, 2), roll_period_s=round(r.roll_s, 1),
            **({} if not r.wind else dict(
                windage_m2=round(r.wind["area_m2"]), gale_heel_deg=round(r.wind["heel_deg"], 1),
                gale_heel_condition=r.wind["condition"], deck_edge_deg=round(r.wind["deck_edge_deg"], 1),
                deck_edge_wind_kn=round(r.wind["deck_edge_wind_kn"]))),
            trim_m=round(r.trim_m, 2), lcg_m=round(r.lcg, 2), lcb_m=round(r.lcb, 2),
            layout_shift_m=round(lay.geo["shift"], 2),
            **styles.get(design).results(sized, lay, r),
        ),
        plant=plant_report(lay, r),
        hull=hull_report(design, r),
        crew=lay.crew,
        fire_control=firecontrol.report(lay, r.freeboard),
        **({"bridge": bridge_report(lay, r.freeboard)} if "bridge" in lay.geo else {}),
        weight_groups_t={k: round(v) for k, v in sorted(r.groups.items(), key=lambda kv: -kv[1])},
        weights=[dict(name=w.name, group=w.group, t=round(w.w, 1), x=round(w.x, 2), z=round(w.z, 2))
                 for w in r.weights],
    )


def hull_plating(lay, design, res):
    """The unarmoured plating (hullweight.plates): the hull's from its structure, the superstructure's from the
    design (superstructure.plating_mm, control_mm) over the structure's own gauge."""
    sup = design.get("superstructure") or {}
    hp = hullweight.plating(design)
    h = res.hull if "t_min_mm" in res.hull else {**res.hull, "plate_own_mm": own_plate_mm(lay)}
    return hullweight.plates(h, lay.hull.L, hp["shell_mm"], hp["material"], sup.get("plating_mm", 0.0),
                             sup.get("control_mm", 0.0), hp["deck_wood_mm"])


def interior(lay, design, r):
    """What the solved, laid-out ship is inside, beyond the layout: its armour (r.armour), hull form
    (round the stern gear), subdivision with its plating, hydrostatics, propulsion train linked into the
    subdivision, and battle stations (which also go in the report's crew). export_hitboxes publishes it."""
    D, T = r.depth, r.draught
    ag = r.armour
    cb = design["hull"]["block_coefficient"]
    gear = propulsion.gear(lay, design, r)        # the stern's lines make room for it
    form = HullForm(lay.hull, cb, cwp(cb), T, D, navarch.froude(design["speed_kn"], lay.hull.L), gear, r.lcb)
    sub = subdivision.build(lay, design, r, ag, ag["armoured"], form)
    plating = hull_plating(lay, design, r)
    planked = subdivision.deck_plates(sub, plating, design, lay)
    hydro = stability.hydrostatics(form, r)
    train = propulsion.build(lay, design, r, form, gear)
    propulsion.link(train, sub, D)
    return dict(armour=ag, form=form, subdivision=sub, plating=plating, planked=planked, hydrostatics=hydro,
                propulsion=train, battle_crew=crew.assign_battle_crew(lay, sub))


BRIDGE_EYE = 1.7   # m: the officer of the watch's eye over the bridge deck


def bridge_report(lay, deck_m):
    """The navigating bridge's view (warships): its level, eye height above the waterline and horizon, and whether it
    sees over the highest forward turret. The tower's height (superstructure.tower_levels) trades this and the
    directors' horizons against topweight and windage (gm_*, gale_heel_deg, windage_m2)."""
    b = lay.geo["bridge"]
    eye = deck_m + b["floor"] + BRIDGE_EYE
    return dict(level=b["level"], tower_levels=b["tower"], eye_height_m=round(eye, 2),
                horizon_km=round(firecontrol.horizon_km(eye), 1), sees_over_turrets=b["level"] >= b["need"],
                level_to_see_over_turrets=b["need"])


def height_columns(lay, deck_m):
    """The static height-map columns, lowest first. Only columns: a heightfield cannot overhang, so mast yards,
    derricks and turret barrels are left out. A flight deck overhang is a solid column, which casts the same
    shadow seen from above."""
    items = [dict(top=deck_m, shape="hull")]
    for dk in lay.decks + lay.sponsons:
        items.append(dict(top=deck_m + dk["top"], shape="polygon", points=dk["points"]))
    for ht in lay.spec.get("hatches", []):
        items.append(dict(top=deck_m + ht.get("top", 1.2), shape="rect", x=ht["x"] - ht["l"] / 2,
                          y=ht["y"] - ht["w"] / 2, w=ht["l"], h=ht["w"]))
    for cr in lay.spec.get("cranes", []):
        items.append(dict(top=deck_m + cr["top"], shape="circle", cx=cr["x"], cy=cr["y"], r=cr.get("r", 1.2)))
    for m in lay.mounts:   # barbettes of raised mounts stand above the deck
        t = m["t"]
        if has_barbette(t) and m["base"] > 0.5:
            items.append(dict(top=deck_m + m["base"], shape="circle", cx=m["x"], cy=m["y"], r=t["r"] * 0.95))
    for b in lay.blocks:
        pts = block_outline(b)
        items.append(dict(top=deck_m + block_top(b), shape="polygon", points=pts))
    for a in lay.aa:
        items.append(dict(top=deck_m + a["base"] + 2.0, shape="circle", cx=a["x"], cy=a["y"],
                          r=AA_CFG[a["type"]][0] * 0.8))
    for bt in lay.spec.get("boats", []):
        items.append(dict(top=deck_m + bt.get("top", LEVEL_H + 1.5), shape="ellipse", cx=bt["x"], cy=bt["y"],
                          rx=bt["l"] / 2, ry=bt["w"] / 2))
    for fn in lay.funnels:
        pts = rrect_polygon(fn["x"] - fn["l"] / 2, fn["y"] - fn["w"] / 2, fn["x"] + fn["l"] / 2, fn["y"] + fn["w"] / 2,
                            fn["w"] / 2, fn["w"] / 2)
        items.append(dict(top=deck_m + lay.fun_top, shape="polygon", points=pts))
    for m in lay.spec.get("masts", []):
        top = m.get("top", lay.fun_top + MAST_ABOVE_FUNNEL)
        items.append(dict(top=deck_m + top, shape="circle", cx=m["x"], cy=m.get("y", 0), r=0.7))
    items.sort(key=lambda it: it["top"])
    return items


def build(design, hint=None):
    """Design the ship: the published, plain-data result (see the module docstring). Call validate() first.
    hint: the hull length (report results length_m) of the previous build when the player has changed one
    knob. The search starts there, which makes it several times faster; the result is the same either way, up
    to the search's half-percent tolerance."""
    lay, r, sized = solve(design, hint=hint)
    deck_m = max(r.freeboard, 0.1)    # an unsolvable design can come out with no freeboard at all
    inner = interior(lay, sized, r)   # before the report: it adds the battle stations to the crew
    hitboxes = export_hitboxes(lay, sized, r, inner)
    return dict(
        design=design,
        report=report_dict(design, lay, r, sized),
        hitboxes=hitboxes,
        render=dict(
            spec=copy.deepcopy(lay.spec),
            deck_m=deck_m,
            mounts=[dict(id=m["id"], kind=m["kind"], rest=m["rest"], arcs=m["arcs"],
                         traverse=m["traverse"], top=m["top"],
                         **({"mount": "casemate"} if m.get("casemate") else {})) for m in lay.mounts],
            columns=height_columns(lay, deck_m),
            summary=styles.get(design).summary(sized, lay, r),
        ),
    )
