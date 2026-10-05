"""
lookgrid: contact sheets of designs drawn in each navy's look for one era, to compare how the navies differ.

    python lookgrid.py designs/dreadnought.json designs/seydlitz.json ... --era great_war [--out out_lookgrid]

Each design is built once (the look never changes the design), then drawn in every navy's look for the era.
Writes to --out:
    <navy>.png      one sheet per navy: every design in that navy's look, at the same scale, in a grid
    compare.png     every design in a row, one column per navy (smaller scale), for spotting looks that are
                    too alike
With --falloff, instead: falloff_<id>.png per design, every navy (rows) in every era (columns), to judge how the
looks quieten over time (looks.ERA_MUTE).
Like design.py this joins the two sides; neither imports it.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from concurrent.futures import ProcessPoolExecutor

from PIL import Image, ImageDraw

import looks
import render
import shipdesign

SEA = (46, 72, 94, 255)
INK = (232, 236, 240, 255)
DIM = (160, 176, 190, 255)
GAP = 24


def draw_one(job):
    """The rest preview of one built ship in one look, trimmed to the ship and its shadow."""
    ship, navy, era, S = job
    with tempfile.TemporaryDirectory() as tmp:
        meta = render.render_ship(ship, tmp, S, mips=0, look={"navy": navy, "era": era}, previews=False)
        turret_pngs = {tid: os.path.join(tmp, t["file"]) for tid, t in meta["turret_types"].items()}
        pad = math.ceil(meta["shadow"]["max_height_m"] / math.tan(math.radians(render.PREVIEW_SUN[1])) * S)
        img = render.composite(os.path.join(tmp, "hull.png"), turret_pngs, meta, lambda m: m["rest_deg"],
                               render.PREVIEW_SUN, os.path.join(tmp, "height.png"), pad)
    return img.crop(img.getbbox())


def caption(ship):
    r = ship["report"]["results"]
    d = ship["design"]
    return d.get("name", d["id"]), f'{d.get("type", "")}  {r["length_m"]:.0f} x {r["beam_m"]:.1f} m'


def on_sea(w, h):
    return Image.new("RGBA", (w, h), SEA)


def navy_sheet(navy, era, ships, imgs, cols):
    """A grid of the navy's ships, longest first, every one at the same scale."""
    order = sorted(range(len(ships)), key=lambda i: -imgs[i].width)
    title_f, name_f, sub_f = render._font(30, True), render._font(18, True), render._font(15)
    cell_w = max(im.width for im in imgs) + GAP
    rows = [order[k:k + cols] for k in range(0, len(order), cols)]
    row_h = [max(imgs[i].height for i in row) + 50 + GAP for row in rows]
    head = 80
    sheet = on_sea(cell_w * min(cols, len(order)) + GAP, head + sum(row_h))
    dr = ImageDraw.Draw(sheet)
    dr.text((GAP, 18), f'{navy}  /  {era}', font=title_f, fill=INK)
    dr.text((GAP, 54), looks.get({"look": {"navy": navy, "era": era}}).get("desc", ""), font=sub_f, fill=DIM)
    y = head
    for row, h in zip(rows, row_h):
        for c, i in enumerate(row):
            x = GAP + c * cell_w
            name, sub = caption(ships[i])
            dr.text((x, y), name, font=name_f, fill=INK)
            dr.text((x, y + 22), sub, font=sub_f, fill=DIM)
            sheet.alpha_composite(imgs[i], (x, y + 46))
        y += h
    return sheet


def compare_sheet(era, navies, ships, imgs, factor):
    """Rows are designs, columns navies, scaled down by factor."""
    small = {k: im.resize((max(1, round(im.width * factor)), max(1, round(im.height * factor))), Image.LANCZOS)
             for k, im in imgs.items()}
    name_f, head_f = render._font(15, True), render._font(20, True)
    col_w = [max(small[(d, n)].width for d in range(len(ships))) + GAP for n in navies]
    row_h = [max(small[(d, n)].height for n in navies) + 26 + GAP for d in range(len(ships))]
    head = 50
    sheet = on_sea(sum(col_w) + GAP, head + sum(row_h))
    dr = ImageDraw.Draw(sheet)
    x = GAP
    for n, w in zip(navies, col_w):
        dr.text((x, 14), n, font=head_f, fill=INK)
        x += w
    y = head
    for d, h in enumerate(row_h):
        dr.text((GAP, y), caption(ships[d])[0], font=name_f, fill=DIM)
        x = GAP
        for n, w in zip(navies, col_w):
            sheet.alpha_composite(small[(d, n)], (x, y + 22))
            x += w
        y += h
    return sheet


def falloff_sheet(ship, navies, imgs):
    """One design: rows are navies, columns eras."""
    head_f = render._font(18, True)
    w = max(im.width for im in imgs.values()) + GAP
    h = max(im.height for im in imgs.values()) + GAP // 2
    sheet = on_sea(130 + w * len(looks.ERAS), 44 + h * len(navies))
    dr = ImageDraw.Draw(sheet)
    for c, e in enumerate(looks.ERAS):
        dr.text((130 + c * w, 12), e, font=head_f, fill=INK)
    for r, n in enumerate(navies):
        dr.text((GAP, 44 + r * h + h // 3), n, font=head_f, fill=INK)
        for c, e in enumerate(looks.ERAS):
            sheet.alpha_composite(imgs[(n, e)], (130 + c * w, 44 + r * h))
    return sheet


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("designs", nargs="+")
    ap.add_argument("--era", default="great_war", choices=looks.ERAS)
    ap.add_argument("--navies", default=",".join(looks.NAVIES), help="comma-separated (default: all)")
    ap.add_argument("--scale", type=float, default=5.0, help="pixels per metre on the navy sheets (default 5)")
    ap.add_argument("--cols", type=int, default=3, help="columns on the navy sheets (default 3)")
    ap.add_argument("--compare-scale", type=float, default=0.5, help="the compare sheet's size against the navy sheets")
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    ap.add_argument("--falloff", action="store_true", help="one sheet per design: every navy in every era")
    ap.add_argument("--out", default="out_lookgrid")
    args = ap.parse_args()

    navies = args.navies.split(",")
    ships = [shipdesign.build(json.load(open(p))) for p in args.designs]
    if args.falloff:
        os.makedirs(args.out, exist_ok=True)
        for ship in ships:
            jobs = [(n, e) for n in navies for e in looks.ERAS]
            with ProcessPoolExecutor(args.jobs) as ex:
                imgs = dict(zip(jobs, ex.map(draw_one, [(ship, n, e, args.scale * 0.6) for n, e in jobs])))
            path = os.path.join(args.out, f'falloff_{ship["design"]["id"]}.png')
            falloff_sheet(ship, navies, imgs).convert("RGB").save(path)
            print("wrote", path)
        return
    jobs = [(d, n) for d in range(len(ships)) for n in navies]
    with ProcessPoolExecutor(args.jobs) as ex:
        done = ex.map(draw_one, [(ships[d], n, args.era, args.scale) for d, n in jobs])
        imgs = dict(zip(jobs, done))
    os.makedirs(args.out, exist_ok=True)
    for n in navies:
        sheet = navy_sheet(n, args.era, ships, [imgs[(d, n)] for d in range(len(ships))], args.cols)
        sheet.convert("RGB").save(os.path.join(args.out, f"{n}.png"))
        print("wrote", os.path.join(args.out, f"{n}.png"), sheet.size)
    sheet = compare_sheet(args.era, navies, ships, imgs, args.compare_scale)
    sheet.convert("RGB").save(os.path.join(args.out, "compare.png"))
    print("wrote", os.path.join(args.out, "compare.png"), sheet.size)


if __name__ == "__main__":
    main()
