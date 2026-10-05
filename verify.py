#!/usr/bin/env python3
"""
verify: checks that hitboxes and sprites agree, pixel for pixel.

    python verify.py out_designs/battleship [more dirs ...]

For every rotating mount, the turret sprite is rotated to several angles and pasted at its mount,
then compared with the hitbox polygons (body + parts + barrels), rotated and placed the same way.
Reports IoU (intersection over union) per mount and angle. Fixed parts are checked too: raised
blocks and funnels must be fully opaque inside their hitbox polygon, and the hull outline is
compared against the hull image.

The subdivision is checked too (check_subdivision): every cell has one owning room, points inside the hull below
the main deck each fall in exactly one cell, neighbours are mutual, and every mount's magazine is a room.
"""
import json
import math
import os
import random
import sys

from PIL import Image, ImageDraw

Image.MAX_IMAGE_PIXELS = None   # our own output: a 1 km ship makes very large sheets

from geometry import rotate_translate, point_in_polygon


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


def check_subdivision(hb, samples=3000):
    """Problems with the subdivision ([] if none)."""
    from hitview import _half_width
    probs = []
    cells = {c["id"]: c for c in hb["cells"]}
    rooms = {r["id"]: r for r in hb["rooms"]}
    for r in rooms.values():
        if not r["cells"]:
            probs.append(f"room {r['id']} has no cell")
        for cid in r["cells"]:
            if cid not in cells:
                probs.append(f"room {r['id']} lists unknown cell {cid}")
    for c in cells.values():
        if c["room"] not in rooms or c["id"] not in rooms[c["room"]]["cells"]:
            probs.append(f"cell {c['id']}: owner {c['room']} doesn't list it")
        for nid, _ in c["neighbours"]:
            if nid not in cells or c["id"] not in [n for n, _ in cells[nid]["neighbours"]]:
                probs.append(f"cell {c['id']}: neighbour {nid} isn't mutual")
    for comp in hb["components"]:
        if comp.get("magazine") and comp["magazine"] not in rooms:
            probs.append(f"{comp['id']}: magazine {comp['magazine']} isn't a room")
    hull = [tuple(p) for p in hb["hull"]]
    L, keel = hb["length"], hb["vertical"]["keel"]
    rng = random.Random(1)
    bad = 0
    for _ in range(samples):
        x = rng.uniform(-L / 2, L / 2)
        hw = _half_width(hull, x)
        y, z = rng.uniform(-hw, hw), rng.uniform(keel, 0.0)
        n = sum(1 for c in cells.values()
                if c["x0"] <= x < c["x1"] and c["y0"] <= y < c["y1"] and c["base"] <= z < c["top"])
        bad += n != 1
    if bad > samples * 0.002:      # points right at the bow tip may miss a zero-volume cell
        probs.append(f"{bad} of {samples} points inside the hull fall in no cell or several")
    return probs


def check_traverse(hb, sp):
    """traverse_deg: one interval under a full turn holding the rest bearing and every arc, the same in
    sprite.json; and a main turret's barrels, swung through all of it, meet nothing taller than their axis
    (superstructure, funnels, other turrets)."""
    inside = lambda lo, hi, a: lo - 1e-6 <= a <= hi + 1e-6 or lo - 1e-6 <= a + 360 <= hi + 1e-6
    sp_tr = {m["id"]: m.get("traverse_deg") for m in sp["mounts"]}
    probs = []
    for c in hb["components"]:
        if "arcs_deg" not in c:
            continue
        lo, hi = c.get("traverse_deg") or (0.0, -1.0)
        if not (0 <= hi - lo < 360 and inside(lo, hi, c["rest_deg"] % 360)
                and all(inside(lo, hi, a0 % 360) and inside(lo, hi, a1 % 360) and (a1 - a0) <= hi - lo
                        for a0, a1 in c["arcs_deg"])):
            probs.append(f"{c['id']}: traverse {c.get('traverse_deg')} doesn't hold rest {c['rest_deg']} "
                         f"and arcs {c['arcs_deg']}")
        if sp_tr.get(c["id"]) != c.get("traverse_deg"):
            probs.append(f"{c['id']}: sprite.json traverse {sp_tr.get(c['id'])} differs")
        if c["kind"] != "main":
            continue
        R = max(p[0] for b in c["local"]["barrels"] for p in b)
        axis = c["base"] + 0.55 * (c["top"] - c["base"])
        tall = [o for o in hb["components"] if o is not c and o.get("top", 0) > axis + 1e-6
                and o.get("base", 0) < axis and (o.get("points") or "local" in o)]
        hits = set()
        for k in range(int(hi - lo) + 1):
            a = math.radians(lo + k)
            for f in (0.5, 0.75, 1.0):
                px, py = c["x"] + f * R * math.cos(a), c["y"] + f * R * math.sin(a)
                for o in tall:
                    if (point_in_polygon(px, py, o["points"]) if o.get("points") else
                            point_in_polygon(px, py, rotate_translate(o["local"]["body"], o["rest_deg"], o["x"], o["y"]))):
                        hits.add(o["id"])
        if hits:
            probs.append(f"{c['id']}: barrels swung through {c['traverse_deg']} hit {', '.join(sorted(hits))}")
    return probs


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

    hull_a = Image.open(os.path.join(d, "hull.png")).getchannel("A")
    opaque = hull_a.load()
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
                        ok += opaque[x, y] > 127
            cov = ok / n if n else 1.0
            fixed_worst = min(fixed_worst, cov)
            rows.append((c["id"], c["kind"], cov))
    # the hull image is the hull plus whatever overhangs it: flight decks, sponsons, deck-edge elevators
    outline = [hb["hull"]] + [c["points"] for c in hb["components"] if c.get("kind") in ("flight_deck", "sponson")]
    hull_iou = iou(hull_a.point(lambda v: 255 if v > 127 else 0), mask_from_polys((W, H), outline, S, ox, oy))
    print(f"\n{os.path.basename(d)} @ {S} px/m   hull IoU {hull_iou:.3f}   "
          f"worst turret IoU {worst:.3f}   worst fixed coverage {fixed_worst:.3f}")
    for rid, kind, v in rows:
        flag = "" if v > 0.85 else "   <-- check"
        print(f"   {rid:>16} {kind:>15}  {v:.3f}{flag}")
    probs = check_subdivision(hb) + check_traverse(hb, sp)
    shared = [r["id"] for r in hb["rooms"] if r.get("shared")]
    print(f"   subdivision: {len(hb['sections'])} sections, {len(hb['cells'])} cells, {len(hb['rooms'])} rooms"
          + (f", sharing a cell: {', '.join(shared)}" if shared else ""))
    for p in probs[:20]:
        print(f"   <-- {p}")
    return min(worst, fixed_worst, hull_iou, 0.0 if probs else 1.0)


if __name__ == "__main__":
    res = [check(d) for d in sys.argv[1:]]
    print("\nALL OK" if min(res) > 0.85 else "\nSOME MISMATCH")
