#!/usr/bin/env python3
"""
design: command line. Player design (JSON) -> designed ship (shipdesign.py) -> sprites (render.py).
The design's "style" (warship, carrier, merchant; see styles/) picks the layout and the extra weights; its
"look" (looks.py) only how it is drawn.

    python design.py designs/battleship.json [more.json ...] [--scale 10] [--mips 5] [--out out_designs] [--no-limits]

For each design it writes out_designs/<id>/:
    report.json        inputs, displacement, power, stability, weight breakdown, errors and warnings
    hitboxes.json      hull polygon, components (turrets with local polygons + firing arcs), subdivision
    sprite.json        sprite metadata: layers, origin, mount pixel positions, rest angles, arcs, z
    hull_base.png/svg, hull_upper.png/svg, turrets/<type>.png/svg   (no baked shadows)
    height.png         height map for sun shadows (see shadow.py)
    <layer>_mips.png   next to each layer PNG: level 0 plus every lower mip level packed in one image
    preview_rest.png, preview_starboard.png
    debug_hitboxes.png (hitboxes drawn over the sprite), sheet.png (summary card)
"""
from __future__ import annotations

import argparse
import json
import os

import looks
import render
import shipdesign


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("designs", nargs="+")
    ap.add_argument("--scale", type=float, default=10.0, help="pixels per metre at mip level 0 (default 10)")
    ap.add_argument("--mips", type=int, default=5, help="mip levels below level 0 (default 5: down to 1/32)")
    ap.add_argument("--out", default="out_designs")
    ap.add_argument("--no-limits", action="store_true",
                    help="skip the input ranges: anything goes (the physics may then make no sense)")
    ap.add_argument("--no-previews", action="store_true",
                    help="game assets only: skip the shaded previews, debug overlay and sheet (much faster)")
    args = ap.parse_args()
    crashed = 0
    for p in args.designs:
        with open(p) as fh:
            design = json.load(fh)
        errs = shipdesign.validate(design, limits=not args.no_limits) + looks.validate(design)
        if errs:
            print(f"{p}: invalid input:\n  " + "\n  ".join(errs))
            continue
        try:   # a silly design may break the generator; report it and carry on with the rest
            ship = shipdesign.build(design)
            out_dir = os.path.join(args.out, design["id"])
            os.makedirs(out_dir, exist_ok=True)
            render.render_ship(ship, out_dir, args.scale, args.mips, previews=not args.no_previews)
        except Exception as e:
            print(f"{p}: the generator broke on this design: {type(e).__name__}: {e}")
            crashed += 1
            continue
        rep = ship["report"]
        with open(os.path.join(out_dir, "report.json"), "w") as fh:
            json.dump(rep, fh, indent=2)
        with open(os.path.join(out_dir, "hitboxes.json"), "w") as fh:
            json.dump(ship["hitboxes"], fh, indent=1)
        res = rep["results"]
        print(f"{design['id']:>14}: {'OK ' if rep['valid'] else 'BAD'} {res['length_m']:>5.1f} x {res['beam_m']:>4.1f} m  "
              f"std {res['standard_displacement_t']:>6,} t "
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
