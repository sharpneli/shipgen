#!/usr/bin/env python3
"""
design: player design (JSON) -> balanced layout, weights and performance, sprites, hitboxes.
The design's "style" (warship, carrier, merchant; see styles/) picks the layout and the extra weights.

    python design.py designs/battleship.json [more.json ...] [--scale 10] [--mips 5] [--out out_designs] [--no-limits]

For each design it writes out_designs/<id>/:
    report.json        inputs, displacement, power, stability, weight breakdown, errors and warnings
    hitboxes.json      hull polygon, components (turrets with local polygons + firing arcs), compartments
    sprite.json        sprite metadata: layers, origin, mount pixel positions, rest angles, arcs, z
    hull_base.png/svg, hull_upper.png/svg, turrets/<type>.png/svg   (no baked shadows)
    height.png         height map for sun shadows (see shadow.py)
    <layer>_mips.png   next to each layer PNG: level 0 plus every lower mip level packed in one image
    preview_rest.png, preview_starboard.png
    debug_hitboxes.png (hitboxes drawn over the sprite), sheet.png (summary card)
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os

from PIL import Image, ImageChops, ImageDraw, ImageFont

import looks
import navarch
import styles
from hitbox import assign_arcs, export_hitboxes, nearest_allowed
from geometry import rotate_translate, turret_shapes
from shipgen import build_hull_layers, build_turret, render, DEFAULT_PALETTE
import shadow

Image.MAX_IMAGE_PIXELS = None   # our own output: a 1 km ship makes very large sheets
PREVIEW_SUN = (240.0, 50.0)   # ship-local bearing and elevation of the sun in the previews, degrees
SHADOW_OPACITY = 0.4

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
    return errs + style.validate(design) + looks.validate(design)


def solve_design(design, iterations=6):
    """Rough solve -> layout -> solve -> shift to balance; repeat until stable."""
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


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------
def mip_rects(w, h, levels):
    """[x, y, w, h] of each level in the packed image: level 0 on the left, level 1 to its right at the top,
    then each next level alternately below and to the right of the previous one. The whole chain fits in
    1.5w x h. Canvases are multiples of 2^(levels+1) px, so every rect is whole pixels with an even size."""
    rects = [[0, 0, w, h]]
    x, y = w, 0
    for k in range(1, levels + 1):
        lw, lh = w >> k, h >> k
        rects.append([x, y, lw, lh])
        if k % 2:
            y += lh
        else:
            x += lw
    return rects


def write_mips(out_dir, rel, levels, height=False):
    """<rel stem>_mips.png: the level-0 image and its halvings, packed as in mip_rects. Colour layers use a
    2x2 box filter on premultiplied alpha (no dark fringes); the height map a 2x2 max (see shadow.py)."""
    im = Image.open(os.path.join(out_dir, rel))
    im = im.convert("L") if height else im.convert("RGBa")
    rects = mip_rects(im.width, im.height, levels)
    atlas = Image.new(im.mode, (rects[1][0] + rects[1][2] if levels else im.width, im.height), 0)
    for k, (x, y, w, h) in enumerate(rects):
        if k:
            assert im.width % 2 == 0 and im.height % 2 == 0, (rel, im.size)
            im = shadow.reduce_max(im) if height else im.reduce(2)
        assert im.size == (w, h), (rel, k, im.size)
        atlas.paste(im, (x, y))
    out = rel[:-len(".png")] + "_mips.png"
    (atlas if height else atlas.convert("RGBA")).save(os.path.join(out_dir, out), optimize=True)
    return dict(file=out, rects=rects)


def composite(base_p, upper_p, turret_pngs, meta, angle_fn, sun=None, height_p=None, pad=0):
    """Layers in draw order. With a sun (bearing, elevation), cast shadows the way the game should: turret
    silhouettes offset away from the sun, under the turrets, plus the height-map shadow over everything."""
    S = meta["scale_px_per_m"]
    base = Image.open(base_p).convert("RGBA")
    canvas = Image.new("RGBA", (base.width + 2 * pad, base.height + 2 * pad), (0, 0, 0, 0))
    canvas.alpha_composite(base, (pad, pad))
    turrets = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    t_shadow = Image.new("L", canvas.size, 0)
    for m in sorted(meta["mounts"], key=lambda m: m["z"]):
        rot = Image.open(turret_pngs[m["type"]]).convert("RGBA").rotate(-angle_fn(m), resample=Image.BICUBIC)
        cx, cy = m["px"][0] + pad, m["px"][1] + pad
        turrets.alpha_composite(rot, (round(cx - rot.width / 2), round(cy - rot.height / 2)))
        if sun:
            dx, dy = shadow.sun_offset_px(S, *sun, m["top_m"] - meta["shadow"]["deck_m"])
            sil = Image.new("L", canvas.size, 0)
            sil.paste(rot.getchannel("A"), (round(cx + dx - rot.width / 2), round(cy + dy - rot.height / 2)))
            t_shadow = ImageChops.lighter(t_shadow, sil)
    canvas.alpha_composite(turrets)
    upper = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    upper.paste(Image.open(upper_p).convert("RGBA"), (pad, pad))
    canvas.alpha_composite(upper)
    if sun:
        # turrets don't shadow themselves, and their shadow stays under the taller upper layer
        covered = ImageChops.lighter(turrets.getchannel("A"), upper.getchannel("A"))
        mask = ImageChops.multiply(t_shadow, ImageChops.invert(covered))
        mask = ImageChops.lighter(mask, shadow.shadow_mask(Image.open(height_p), S, *sun, pad_px=pad))
        black = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        black.putalpha(mask.point(lambda v: round(v * SHADOW_OPACITY)))
        canvas.alpha_composite(black)
    return canvas


def render_design(design, lay, r, out_dir, S, mips=0):
    os.makedirs(os.path.join(out_dir, "turrets"), exist_ok=True)
    align = 2 ** (mips + 1)
    spec = copy.deepcopy(lay.spec)
    spec["palette"] = looks.palette(design, styles.get(design))   # visual only: nothing above depends on it
    pal = {**DEFAULT_PALETTE, **spec["palette"]}
    turret_look = looks.get(design)["turrets"]
    spec["shapes"] = looks.get(design)["shapes"]
    turret_pngs = {}
    tmeta = {}
    for tid, t in spec["turret_types"].items():
        png = os.path.join(out_dir, "turrets", f"{tid}.png")
        render(build_turret(t, pal, S, align, shadows=False, look=turret_look), png, png.replace(".png", ".svg"))
        turret_pngs[tid] = png
        w, h = Image.open(png).size
        tmeta[tid] = dict(file=f"turrets/{tid}.png", size_px=[w, h], pivot_px=[w / 2, h / 2], desc=t["desc"])

    base_svg, upper_svg, vb, mounts, hull = build_hull_layers(spec, S, align, shadows=False)
    render(base_svg, os.path.join(out_dir, "hull_base.png"), os.path.join(out_dir, "hull_base.svg"))
    render(upper_svg, os.path.join(out_dir, "hull_upper.png"), os.path.join(out_dir, "hull_upper.svg"))
    deck_m = max(r.freeboard, 0.1)    # an unsolvable design can come out with no freeboard at all
    height_svg, max_h = shadow.build_height_svg(lay, deck_m, vb, S, hull)
    height_p = os.path.join(out_dir, "height.png")
    render(height_svg, height_p)
    shadow.to_height_png(height_p)
    W, H = Image.open(os.path.join(out_dir, "hull_base.png")).size
    ox, oy = W / 2, H / 2
    by_id = {m["id"]: m for m in lay.mounts}
    meta = dict(id=design["id"], name=design.get("name", design["id"]), scale_px_per_m=S,
                size_px=[W, H], origin_px=[ox, oy],
                orientation="bow points +x (right); angles clockwise, 0 = ahead",
                layer_order=["hull_base", "turrets (ascending z)", "hull_upper"],
                layers=dict(base="hull_base.png", upper="hull_upper.png"), turret_types=tmeta,
                mips=dict(levels=mips, scale_px_per_m=[S / 2 ** k for k in range(mips + 1)],
                          rule="each layer has <name>_mips.png with level k at mip_rects[k] = [x, y, w, h]; "
                               "within level k, size, origin_px, pivot_px and mount px are the level-0 values / 2^k"),
                shadow=dict(height_map="height.png", height_step_m=shadow.HEIGHT_STEP_M,
                            deck_m=round(deck_m, 2), max_height_m=round(max_h, 2),
                            note="height map grey value x height_step_m = metres above the waterline (0 = sea); "
                                 "mount top_m is the turret roof above the waterline; see shadow.py"),
                mounts=[])
    for m in spec["turrets"]:
        lm = by_id[m["id"]]
        meta["mounts"].append(dict(id=m["id"], kind=lm["kind"], type=m["type"], pos_m=[m["x"], m["y"]],
                                   px=[ox + m["x"] * S, oy + m["y"] * S], rest_deg=lm["rest"],
                                   arcs_deg=lm["arcs"], z=m["z"], top_m=round(deck_m + lm["top"], 2)))
    meta["layers"]["base_mips"] = write_mips(out_dir, "hull_base.png", mips)["file"]
    meta["layers"]["upper_mips"] = write_mips(out_dir, "hull_upper.png", mips)["file"]
    meta["shadow"]["height_map_mips"] = write_mips(out_dir, "height.png", mips, height=True)["file"]
    meta["mip_rects"] = mip_rects(W, H, mips)
    for tm in tmeta.values():
        pk = write_mips(out_dir, tm["file"], mips)
        tm["mips_file"], tm["mip_rects"] = pk["file"], pk["rects"]
    with open(os.path.join(out_dir, "sprite.json"), "w") as fh:
        json.dump(meta, fh, indent=2)

    base_p, upper_p = os.path.join(out_dir, "hull_base.png"), os.path.join(out_dir, "hull_upper.png")
    rest_angle, stbd_angle = (lambda m: m["rest_deg"]), (lambda m: nearest_allowed(m["arcs_deg"], 90))
    pad = max(0, math.ceil(max_h / math.tan(math.radians(PREVIEW_SUN[1])) * S))   # room for the shadow on the sea
    rest = composite(base_p, upper_p, turret_pngs, meta, rest_angle, PREVIEW_SUN, height_p, pad)
    stbd = composite(base_p, upper_p, turret_pngs, meta, stbd_angle, PREVIEW_SUN, height_p, pad)
    rest.save(os.path.join(out_dir, "preview_rest.png"))
    stbd.save(os.path.join(out_dir, "preview_starboard.png"))
    hb = export_hitboxes(lay, design)
    debug = debug_overlay(composite(base_p, upper_p, turret_pngs, meta, rest_angle), hb, S, ox, oy)
    debug.save(os.path.join(out_dir, "debug_hitboxes.png"))
    sheet(design, lay, r, rest, stbd, hb, S, os.path.join(out_dir, "sheet.png"))
    return meta, hb


KIND_COL = {"main": (255, 80, 80), "secondary": (255, 170, 60), "torpedo": (90, 200, 255), "barbette": (255, 255, 255),
            "superstructure": (120, 255, 120), "funnel": (230, 120, 255), "aa": (255, 240, 80)}


def debug_overlay(img, hb, S, ox, oy):
    im = img.copy()
    d = ImageDraw.Draw(im)
    P = lambda pts: [(ox + x * S, oy + y * S) for x, y in pts]
    d.line(P(hb["hull"] + hb["hull"][:1]), fill=(0, 255, 255), width=1)
    for c in hb["components"]:
        col = KIND_COL.get(c["kind"], (255, 255, 255))
        if "local" in c:
            for poly in [c["local"]["body"]] + c["local"]["parts"]:
                pts = rotate_translate(poly, c["rest_deg"], c["x"], c["y"])
                d.line(P(pts + pts[:1]), fill=col, width=1)
        elif c.get("shape") == "circle":
            cx, cy, rr = ox + c["x"] * S, oy + c["y"] * S, c["r"] * S
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=col)
        else:
            d.line(P(c["points"] + c["points"][:1]), fill=col, width=1)
    for c in hb["compartments"]:
        x0, x1, hw = c["x0"], c["x1"], c["half_width"]
        d.rectangle([ox + x0 * S, oy - hw * S, ox + x1 * S, oy + hw * S], outline=(255, 255, 255, 90))
    return im


def _font(sz, bold=False):
    try:
        return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf", sz)
    except OSError:
        return ImageFont.load_default()


def arcs_image(rest, hb, S, ox, oy, L):
    R = 0.28 * L * S
    pad = int(R + 10)
    W, H = rest.width + 2 * pad, rest.height + 2 * pad
    im = Image.new("RGBA", (W, H), (45, 90, 115, 255))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cols = [(255, 90, 90), (255, 200, 60), (120, 230, 120), (120, 190, 255), (230, 140, 255), (255, 255, 255)]
    mains = [c for c in hb["components"] if c.get("kind") == "main"]
    for i, c in enumerate(mains):
        col = cols[i % len(cols)]
        cx, cy = pad + ox + c["x"] * S, pad + oy + c["y"] * S
        for a0, a1 in c["arcs_deg"]:
            d.pieslice([cx - R, cy - R, cx + R, cy + R], a0, a1, fill=col + (55,), outline=col + (200,))
    for c in hb["components"]:
        if c.get("kind") in ("secondary", "torpedo"):
            cx, cy = pad + ox + c["x"] * S, pad + oy + c["y"] * S
            rr = R * 0.45
            for a0, a1 in c["arcs_deg"]:
                d.arc([cx - rr, cy - rr, cx + rr, cy + rr], a0, a1, fill=(255, 255, 255, 120), width=1)
    im.alpha_composite(layer)
    im.alpha_composite(rest, (pad, pad))
    return im


def sheet(design, lay, r, rest, stbd, hb, S, path):
    L = lay.hull.L
    ox, oy = rest.width / 2, rest.height / 2
    arcs = arcs_image(rest, hb, S, ox, oy, L)
    rep = report_dict(design, lay, r)
    res = rep["results"]
    lines = [
        f"{rep['name']}  ({'VALID' if rep['valid'] else 'INVALID'})"
        + (f"   look: {looks.look_name(design)}" if looks.look_name(design) != looks.DEFAULT_LOOK else ""),
        f"{L:.0f} x {lay.hull.B:.1f} m, Cb {design['hull'].get('block_coefficient', 0.55)}   "
        f"std {res['standard_displacement_t']:,} t   full {res['full_displacement_t']:,} t",
        f"draught {res['draught_m']} m   freeboard {res['freeboard_m']} m   {design['speed_kn']} kn "
        f"needs {res['power_shp']:,.0f} shp   range {design.get('range_nm', 0):,} nm (fuel {res['fuel_t']:,} t)",
        f"GM {res['gm_full_m']} m full / {res['gm_light_m']} m light   trim {res['trim_m']:+} m   "
        f"layout shift {res['layout_shift_m']:+} m   crew {res['crew']:,}",
        "weights: " + "  ".join(f"{k} {v:,}" for k, v in rep["weight_groups_t"].items()),
    ] + styles.get(design).summary(design, lay, r)
    mains = [c for c in hb["components"] if c.get("kind") == "main"]
    if mains:
        lines.append("main arcs: " + "   ".join(f"{c['id']} {sum(b - a for a, b in c['arcs_deg']):.0f} deg"
                                              for c in mains))
    lines += [f"ERROR: {e}" for e in rep["errors"]] + [f"warning: {w}" for w in rep["warnings"]]
    f1, f2 = _font(18, True), _font(13)
    gap = 16
    text_h = 30 + 19 * (len(lines) - 1) + 10
    Wd = max(arcs.width, rest.width * 2 + gap) + 2 * gap
    Hd = gap + text_h + arcs.height + gap + rest.height + gap
    im = Image.new("RGBA", (Wd, Hd), (36, 72, 94, 255))
    d = ImageDraw.Draw(im)
    y = gap
    for i, ln in enumerate(lines):
        col = (255, 120, 120) if ln.startswith("ERROR") else (255, 215, 120) if ln.startswith("warning") else (232, 238, 242)
        d.text((gap, y), ln, font=f1 if i == 0 else f2, fill=col)
        y += 30 if i == 0 else 19
    y = gap + text_h
    im.alpha_composite(arcs, (gap, y))
    y += arcs.height + gap
    im.alpha_composite(rest, (gap, y))
    im.alpha_composite(stbd, (gap * 2 + rest.width, y))
    im.convert("RGB").save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("designs", nargs="+")
    ap.add_argument("--scale", type=float, default=10.0, help="pixels per metre at mip level 0 (default 10)")
    ap.add_argument("--mips", type=int, default=5, help="mip levels below level 0 (default 5: down to 1/32)")
    ap.add_argument("--out", default="out_designs")
    ap.add_argument("--no-limits", action="store_true",
                    help="skip the input ranges: anything goes (the physics may then make no sense)")
    args = ap.parse_args()
    crashed = 0
    for p in args.designs:
        with open(p) as fh:
            design = json.load(fh)
        errs = validate(design, limits=not args.no_limits)
        if errs:
            print(f"{p}: invalid input:\n  " + "\n  ".join(errs))
            continue
        try:   # a silly design may break the generator; report it and carry on with the rest
            lay, r = solve_design(design)
            out_dir = os.path.join(args.out, design["id"])
            os.makedirs(out_dir, exist_ok=True)
            meta, hb = render_design(design, lay, r, out_dir, args.scale, args.mips)
        except Exception as e:
            print(f"{p}: the generator broke on this design: {type(e).__name__}: {e}")
            crashed += 1
            continue
        rep = report_dict(design, lay, r)
        with open(os.path.join(out_dir, "report.json"), "w") as fh:
            json.dump(rep, fh, indent=2)
        with open(os.path.join(out_dir, "hitboxes.json"), "w") as fh:
            json.dump(hb, fh, indent=1)
        res = rep["results"]
        print(f"{design['id']:>14}: {'OK ' if rep['valid'] else 'BAD'} std {res['standard_displacement_t']:>6,} t "
              f"full {res['full_displacement_t']:>6,} t  T {res['draught_m']:>5} m  {res['power_shp']:>9,.0f} shp  "
              f"GM {res['gm_full_m']:>5}  trim {res['trim_m']:+.2f}  shift {res['layout_shift_m']:+.1f}")
        for e in rep["errors"]:
            print("      ERROR:", e)
        for w in rep["warnings"]:
            print("      warn: ", w)
    if crashed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
