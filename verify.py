#!/usr/bin/env python3
"""
verify: checks that hitboxes and sprites agree, pixel for pixel.

    python verify.py out_designs/battleship [more dirs ...]

For every rotating mount, the turret sprite is rotated to several angles and pasted at its mount,
then compared with the hitbox polygons (body + parts + barrels), rotated and placed the same way.
Reports IoU (intersection over union) per mount and angle. Fixed parts are checked too: upper-layer
blocks and funnels must be fully opaque inside their hitbox polygon, and the hull outline is
compared against the base layer.
"""
import json
import os
import sys

from PIL import Image, ImageDraw

Image.MAX_IMAGE_PIXELS = None   # our own output: a 1 km ship makes very large sheets

from geometry import rotate_translate


def mask_from_polys(size, polys, S, ox, oy):
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    for p in polys:
        d.polygon([(ox + x * S, oy + y * S) for x, y in p], fill=255)
    return m


def iou(a, b):
    pa, pb = a.load(), b.load()
    inter = uni = 0
    for y in range(a.height):
        for x in range(a.width):
            A, Bv = pa[x, y] > 127, pb[x, y] > 127
            inter += A and Bv
            uni += A or Bv
    return inter / uni if uni else 1.0


def check(d):
    hb = json.load(open(os.path.join(d, "hitboxes.json")))
    sp = json.load(open(os.path.join(d, "sprite.json")))
    S = sp["scale_px_per_m"]
    W, H = sp["size_px"]
    ox, oy = sp["origin_px"]
    worst = 1.0
    rows = []
    for c in hb["components"]:
        if "local" not in c:
            continue
        tm = sp["turret_types"][c["type"]]
        timg = Image.open(os.path.join(d, tm["file"])).convert("RGBA")
        scores = []
        for ang in (c["rest_deg"], c["rest_deg"] + 37, c["rest_deg"] + 90, c["rest_deg"] + 180):
            rot = timg.rotate(-ang, resample=Image.BICUBIC)
            canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            cx, cy = ox + c["x"] * S, oy + c["y"] * S
            canvas.alpha_composite(rot, (round(cx - rot.width / 2), round(cy - rot.height / 2)))
            sprite_mask = canvas.getchannel("A")
            polys = [rotate_translate(p, ang, c["x"], c["y"])
                     for p in [c["local"]["body"]] + c["local"]["parts"] + c["local"]["barrels"]]
            hit_mask = mask_from_polys((W, H), polys, S, ox, oy)
            # crop to the region of interest for speed
            r = int(max(rot.width, rot.height) / 2) + 2
            box = (max(0, int(cx) - r), max(0, int(cy) - r), min(W, int(cx) + r), min(H, int(cy) + r))
            if box[2] <= box[0] or box[3] <= box[1]:   # off the canvas (an invalid layout): a mismatch
                scores.append(0.0)
                continue
            scores.append(iou(sprite_mask.crop(box), hit_mask.crop(box)))
        rows.append((c["id"], c["kind"], min(scores)))
        worst = min(worst, min(scores))

    upper = Image.open(os.path.join(d, "hull_upper.png")).getchannel("A").load()
    fixed_worst = 1.0
    for c in hb["components"]:
        if c.get("kind") in ("funnel",) or (c.get("kind") == "superstructure" and c["base"] > 0):
            m = mask_from_polys((W, H), [c["points"]], S, ox, oy)
            pm = m.load()
            n = ok = 0
            for y in range(H):
                for x in range(W):
                    if pm[x, y] > 127:
                        n += 1
                        ok += upper[x, y] > 127
            cov = ok / n if n else 1.0
            fixed_worst = min(fixed_worst, cov)
            rows.append((c["id"], c["kind"], cov))
    base_a = Image.open(os.path.join(d, "hull_base.png")).getchannel("A")
    # the base layer is the hull plus whatever overhangs it: flight decks, sponsons, deck-edge elevators
    outline = [hb["hull"]] + [c["points"] for c in hb["components"] if c.get("kind") in ("flight_deck", "sponson")]
    hull_iou = iou(base_a.point(lambda v: 255 if v > 127 else 0), mask_from_polys((W, H), outline, S, ox, oy))
    print(f"\n{os.path.basename(d)} @ {S} px/m   hull IoU {hull_iou:.3f}   "
          f"worst turret IoU {worst:.3f}   worst fixed coverage {fixed_worst:.3f}")
    for rid, kind, v in rows:
        flag = "" if v > 0.85 else "   <-- check"
        print(f"   {rid:>16} {kind:>15}  {v:.3f}{flag}")
    return min(worst, fixed_worst, hull_iou)


if __name__ == "__main__":
    res = [check(d) for d in sys.argv[1:]]
    print("\nALL OK" if min(res) > 0.85 else "\nSOME MISMATCH")
