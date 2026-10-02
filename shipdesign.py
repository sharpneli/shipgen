"""
shipdesign: the design side. A player's design (JSON) in, the designed ship out as plain data. No drawing.

    import shipdesign
    errors = shipdesign.validate(design)          # input errors; [] means build() can run
    ship = shipdesign.build(design)               # plain, JSON-serialisable dict

ship = {
  "design":   the input design, unchanged (its "look" is passed through for the renderer, never read here)
  "report":   validity, errors, warnings, displacement, power, stability, weights (report.json)
  "hitboxes": hull, components with heights and firing arcs, compartments (hitboxes.json)
  "render":   what the renderer needs to draw the ship, all in ship-local metres:
      spec      the drawing spec: hull form, turret types and mounts, superstructure, funnels, masts, boats,
                AA, fittings, decks
      deck_m    main deck height above the waterline
      mounts    per mount: id, kind, rest bearing, arcs, roof height above the main deck
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

import navarch
import styles
from geometry import AA_CFG, rrect_polygon
from hitbox import assign_arcs, export_hitboxes
from layout import LEVEL_H, block_top

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
            if path[-1] in d and not (lo <= d[path[-1]] <= hi):
                errs.append(f"{'.'.join(path)} = {d[path[-1]]} is outside {lo}..{hi}")
    if "id" not in design:
        errs.append("design needs an 'id'")
    return errs + style.validate(design)


def solve(design, iterations=6):
    """Rough solve -> layout -> solve -> shift to balance; repeat until stable. Returns the internal
    (layout, navarch.Result); build() turns them into the published dict."""
    build_layout = styles.get(design).build_layout
    r = navarch.solve(design)
    shift = 0.0
    lay = None
    for _ in range(iterations):
        lay = build_layout(design, r.power_shp, r.depth, shift)
        r = navarch.solve(design, lay.weights, lay.geo)
        moment = sum(w.w * (w.x - r.lcb) for w in r.weights)
        movable = sum(w.w for w in r.weights if w.group not in ("hull", "misc"))
        new_shift = max(lay.shift_range[0], min(lay.shift_range[1], lay.geo["shift"] - moment / movable))
        if abs(new_shift - shift) < 0.05:
            shift = new_shift
            break
        shift = new_shift
    lay = build_layout(design, r.power_shp, r.depth, shift)
    r = navarch.solve(design, lay.weights, lay.geo)
    assign_arcs(lay)
    return lay, r


def report_dict(design, lay, r):
    return dict(
        id=design["id"], name=design.get("name", design["id"]), valid=not (lay.errors or r.errors),
        errors=lay.errors + r.errors, warnings=lay.warnings + r.warnings,
        inputs=design,
        results=dict(
            standard_displacement_t=round(r.std), full_displacement_t=round(r.full),
            draught_m=round(r.draught, 2), depth_m=round(r.depth, 2), freeboard_m=round(r.freeboard, 2),
            power_shp=round(r.power_shp, -2), fuel_t=round(r.fuel), crew=r.crew,
            gm_full_m=round(r.gm_full, 2), gm_light_m=round(r.gm_light, 2),
            trim_m=round(r.trim_m, 2), lcg_m=round(r.lcg, 2), lcb_m=round(r.lcb, 2),
            layout_shift_m=round(lay.geo["shift"], 2),
            **styles.get(design).results(design, lay, r),
        ),
        weight_groups_t={k: round(v) for k, v in sorted(r.groups.items(), key=lambda kv: -kv[1])},
        weights=[dict(name=w.name, group=w.group, t=round(w.w, 1), x=round(w.x, 2), z=round(w.z, 2))
                 for w in r.weights],
    )


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
        if t.get("barbette", True) and m["base"] > 0.5:
            items.append(dict(top=deck_m + m["base"], shape="circle", cx=m["x"], cy=m["y"], r=t["r"] * 0.95))
    for b in lay.blocks:
        pts = rrect_polygon(b["x0"], b["y"] - b["w"] / 2, b["x1"], b["y"] + b["w"] / 2, b["rf"], b["rb"])
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


def build(design):
    """Design the ship: the published, plain-data result (see the module docstring). Call validate() first."""
    lay, r = solve(design)
    deck_m = max(r.freeboard, 0.1)    # an unsolvable design can come out with no freeboard at all
    hitboxes = export_hitboxes(lay, design)
    return dict(
        design=design,
        report=report_dict(design, lay, r),
        hitboxes=hitboxes,
        render=dict(
            spec=copy.deepcopy(lay.spec),
            deck_m=deck_m,
            mounts=[dict(id=m["id"], kind=m["kind"], rest=m["rest"], arcs=m["arcs"], top=m["top"])
                    for m in lay.mounts],
            columns=height_columns(lay, deck_m),
            summary=styles.get(design).summary(design, lay, r),
        ),
    )
