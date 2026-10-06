"""A lightweight sinking demo on an export directory: floods the subdivision's cells from a breach, settles the
ship by added weight with the exported hydrostatics, and draws it top down from the sprite and height map.

    python sinking.py out_designs/battleship                    # stern, bow, starboard -> sinking/*.gif
    python sinking.py out_designs/destroyer --scenario port --hole 6

What it shows the game needs, all from hitboxes.json and sprite.json (nothing here reads the design side):
  flooding    water enters a breached cell through the hole (Q = 0.6 A sqrt(2 g head)), and a main-deck cell
              through its hatches once the deck at it is awash. Cells pass water through decks and inside a room
              ("open"), never through a bulkhead or the inner bottom. A full cell lets the sea on up into the
              cells over it
  attitude    added weight: sinkage w / (100 tpc), trim w (x - lcf) / mct, heel w y / (Δ' GM'), GM' from the
              added weight's height and the partly filled cells' free surface (a loll when it goes negative)
  the end     the ship founders when a third of its deck is awash (a plunge by the lower end, or settling
              level) or it heels past its deck edge (capsize); that part is a canned animation, as the
              small-angle model doesn't hold there
  drawing     every sprite pixel is a point at its height-map height (turrets at their roof), plus the hull's
              bottom from hull_form and walls down every height step, rolled, pitched and sunk, then shaded by
              how deep under the surface it is
"""
import argparse
import json
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import render

G, RHO = 9.81, 1.025
CD = 0.6                # discharge coefficient of a hole
DT = 5.0                # seconds per flooding step
HATCH = 0.02            # a deck's openings, x the plan area between two cells
DECK_OPEN = 0.03        # a main-deck cell's openings to the sea once awash, x its plan area
LEAK = 0.0006           # a watertight bulkhead's or deck's leaks (doors, vents, strained seams), x its area
AWASH_FOUNDER = 0.33    # founders when this share of the deck's length is under water
CAPSIZE_MARGIN = 8.0    # degrees past the deck edge's immersion: capsizes
MAX_HOURS = 8.0
SEA = np.array([28, 62, 92], np.float32)
FOAM = np.array([215, 230, 235], np.float32)
ANTIFOULING = np.array([120, 46, 38], np.float32)


def load(export_dir):
    hb = json.load(open(os.path.join(export_dir, "hitboxes.json")))
    sp = json.load(open(os.path.join(export_dir, "sprite.json")))
    if "hydrostatics" not in hb:
        raise SystemExit(f"{export_dir}: no hydrostatics in hitboxes.json; re-export with design.py")
    return hb, sp


# --- flooding -------------------------------------------------------------------------------------------------

class Flood:
    def __init__(self, hb, breach, hole_m2, leak=1.0, side=0):
        """breach: the cell ids holed; side: the hole's side, +1 starboard, -1 port, 0 both (a loll falls
        toward it)."""
        v = hb["vertical"]
        self.wl = v["waterline"]                # cell heights are above the main deck; the model's above the WL
        self.fb = v["freeboard"]
        self.L, self.B = hb["length"], hb["beam"]
        self.h = hb["hydrostatics"]
        cells = [c for c in hb["cells"] if c["volume_m3"] * c.get("permeability", 1) > 0.5]
        self.ids = [c["id"] for c in cells]
        idx = {c: i for i, c in enumerate(self.ids)}
        f = lambda k: np.array([c[k] for c in cells], float)
        self.x0, self.x1, self.y0, self.y1 = f("x0"), f("x1"), f("y0"), f("y1")
        self.base, self.top = f("base") - self.wl, f("top") - self.wl
        self.cap = f("volume_m3") * np.array([c.get("permeability", 1) for c in cells])
        self.xc, self.yc = (self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2
        self.plan = (self.x1 - self.x0) * (self.y1 - self.y0)
        self.on_deck = f("top") > -0.05         # under the main deck: open to the sea once it's awash
        self.w = np.zeros(len(cells))
        self.hole = np.zeros(len(cells))
        b = [idx[c] for c in breach if c in idx]
        self.hole[b] = hole_m2 / max(1, len(b))
        self.side = side
        # links: (lower or either, upper or other, area, vertical). Watertight ones (bulkheads, the inner bottom)
        # only leak
        self.links = []
        for c in cells:
            i = idx[c["id"]]
            for nid, bnd in c["neighbours"]:
                j = idx.get(nid)
                if j is None or j < i:
                    continue
                if abs(self.top[i] - self.base[j]) < 0.05:
                    lo, hi, vert = i, j, True
                elif abs(self.top[j] - self.base[i]) < 0.05:
                    lo, hi, vert = j, i, True
                else:
                    lo, hi, vert = i, j, False
                ox = max(0.0, min(self.x1[i], self.x1[j]) - max(self.x0[i], self.x0[j]))
                oy = max(0.0, min(self.y1[i], self.y1[j]) - max(self.y0[i], self.y0[j]))
                oz = max(0.0, min(self.top[i], self.top[j]) - max(self.base[i], self.base[j]))
                face = ox * oy if vert else max(ox, oy) * oz
                if "ulkhead" in bnd or bnd == "Inner bottom":
                    area = LEAK * leak * face
                elif bnd == "open":
                    area = max(1.0, 0.3 * face)
                else:
                    area = HATCH * face         # a deck's hatches
                if area > 1e-4:
                    self.links.append((lo, hi, area, vert))
        self.s = self.theta = self.phi = self.phi_eq = 0.0
        self.gm = self.h["gm_t"]
        self.t = 0.0

    def level(self):
        return self.base + (self.top - self.base) * np.clip(self.w / self.cap, 0, 1)

    def sea(self, x, y):
        """The sea surface over the design waterline at ship (x, y)."""
        return self.s + self.theta * (x - self.h["lcf"]) + self.phi * y

    def step(self):
        lvl = self.level()
        ylow = np.where(self.phi >= 0, self.y1, self.y0)
        sea = self.sea(self.xc, ylow)
        room = self.cap - self.w
        q = np.zeros_like(self.w)
        # through the breach, from the hole (a third of the way up the cell) or the water inside, whichever's higher
        hz = self.base + 0.33 * (self.top - self.base)
        q += CD * self.hole * np.sqrt(2 * G * np.clip(sea - np.maximum(lvl, hz), 0, None))
        # down the hatches of an awash deck
        q += np.where(self.on_deck, CD * DECK_OPEN * self.plan * np.sqrt(2 * G * np.clip(sea - self.top, 0, None)), 0)
        # the sea on up through a full cell that's open to it: up to the sea's own level
        open_ = (self.hole > 0) | (self.on_deck & (sea > self.top))
        full = self.w >= self.cap * 0.999
        for _ in range(4):
            for lo, hi, a, vert in self.links:
                for p, r in ((lo, hi), (hi, lo)):
                    if open_[p] and full[p] and not open_[r] and sea[r] > self.base[r]:
                        open_[r] = True
                        q[r] += CD * a * math.sqrt(2 * G * max(0.0, sea[r] - lvl[r]))
        dw = np.minimum(q * DT, room)
        self.w += dw
        # inside: water falls through the decks and levels out inside a room
        lvl = self.level()
        for lo, hi, a, vert in self.links:
            if vert:
                if self.w[hi] > 0 and self.w[lo] < self.cap[lo]:
                    rate = CD * a * math.sqrt(2 * G * (lvl[hi] - self.base[hi] + 0.1)) * DT
                    m = min(self.w[hi], self.cap[lo] - self.w[lo], rate)
                    self.w[hi] -= m
                    self.w[lo] += m
            else:
                d = lvl[lo] - lvl[hi]
                src, dst = (lo, hi) if d > 0 else (hi, lo)
                if abs(d) > 0.01 and self.w[src] > 0:
                    rate = CD * a * math.sqrt(2 * G * abs(d)) * DT
                    m = min(self.w[src], self.cap[dst] - self.w[dst], rate, abs(d) * 0.5 * min(
                        self.cap[src] / max(self.top[src] - self.base[src], 0.1),
                        self.cap[dst] / max(self.top[dst] - self.base[dst], 0.1)))
                    self.w[src] -= m
                    self.w[dst] += m
        self.t += DT
        self.settle()

    def settle(self):
        h = self.h
        wt = RHO * self.w
        W = wt.sum()
        if W <= 0:
            return
        disp = h["displacement_t"] + W
        xw, yw = (wt * self.xc).sum() / W, (wt * self.yc).sum() / W
        lvl = self.level()
        zw = (wt * (self.base + lvl) / 2).sum() / W            # the water's centre, above the design WL
        self.s = W / (100 * h["tpc_t"])
        self.theta = W * (xw - h["lcf"]) / (100 * h["mct_tm"]) / self.L
        # added weight at zw: GM' = GM + w / Δ' (s / 2 - GM - zw) (heights from the design waterline)
        # free surface, weighted 4 f (1 - f) by the fill f: a shallow pool or a pressed-up cell barely moves
        fill = np.clip(self.w / self.cap, 0, 1)
        fs = (4 * fill * (1 - fill) * RHO * self.cap / np.maximum(self.plan * (self.top - self.base), 1e-6)
              * (self.x1 - self.x0) * (self.y1 - self.y0) ** 3 / 12).sum() / disp
        self.gm = h["gm_t"] + W / disp * (self.s / 2 - h["gm_t"] - zw) - fs
        # the wall-sided GZ = sin φ (GM + BM tan² φ / 2) against the heeling arm w y cos φ / Δ': in tan φ,
        # Δ' (GM t + BM t³ / 2) = w y. Past a negative GM's loll it has one root, toward the list (or the breach)
        bmt = h["i_t_m4"] / (disp / RHO)
        m = abs(W * yw)
        side = math.copysign(1.0, yw) if m > 1e-3 * disp else (self.side or math.copysign(1.0, self.phi or 1.0))
        g = lambda t: disp * (self.gm * t + 0.5 * bmt * t ** 3) - m
        lo, hi = 0.0, 60.0
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if g(mid) < 0 else (lo, mid)
        self.phi_eq = side * math.atan(lo)
        self.phi += (self.phi_eq - self.phi) * min(1.0, DT / 40.0)  # rolls over in its own time

    def awash(self):
        xs = np.linspace(-self.L / 2, self.L / 2, 101)
        return float(np.mean(self.sea(xs, 0.0) > self.fb))

    def fate(self):
        edge = math.degrees(math.atan2(self.fb, self.B / 2))
        if abs(math.degrees(self.phi)) > edge + CAPSIZE_MARGIN:
            return "capsizes"
        if self.awash() > AWASH_FOUNDER:
            # by the end only when the trim, not the sinkage, put the deck under
            return "plunges" if abs(self.theta) * self.L / 2 > 0.5 * self.fb else "founders"
        return None


def scenarios(hb):
    """name -> (breached cell ids, side): every cell under the waterline in the stern's or bow's last quarter (a
    smaller end hit just settles the ship by the end), or a torpedo's hole on one side: the outer cells within
    0.06 L of amidships, from 4 m under the waterline up."""
    L, wl = hb["length"], hb["vertical"]["waterline"]
    cells = [c for c in hb["cells"] if c["base"] < wl - 0.5]
    mid = [c for c in cells if abs((c["x0"] + c["x1"]) / 2) < 0.06 * L and c["top"] > wl - 4]
    def outer(sel, side):
        out = []
        for sec in {c["section"] for c in sel}:
            cs = [c for c in sel if c["section"] == sec]
            for tier in {c["tier"] for c in cs}:
                ts = [c for c in cs if c["tier"] == tier]
                if side and any(c["band"] != "C" for c in ts):
                    ts = [c for c in ts if c["band"] != "C"]
                elif side and tier == "bottom":
                    continue
                if side >= 0:
                    out.append(max(ts, key=lambda c: c["y1"])["id"])
                if side <= 0:
                    out.append(min(ts, key=lambda c: c["y0"])["id"])
        return sorted(set(out))
    return {
        "stern": ([c["id"] for c in cells if c["x1"] < -0.25 * L], 0),
        "bow": ([c["id"] for c in cells if c["x0"] > 0.25 * L], 0),
        "starboard": (outer(mid, 1), 1),
        "port": (outer(mid, -1), -1),
    }


def simulate(hb, breach, hole_m2, leak=1.0, side=0, frames=48, end_frames=28):
    f = Flood(hb, breach, hole_m2, leak, side)
    hist = []
    fate = None
    while f.t < MAX_HOURS * 3600:
        f.step()
        hist.append((f.t, f.s, f.theta, f.phi, RHO * f.w.sum(), f.gm))
        fate = f.fate()
        if fate:
            break
    # frames even in time and flooded weight together, so the last minutes' runaway gets its share
    t, w = np.array([h[0] for h in hist]), np.array([h[4] for h in hist])
    prog = t / t[-1] + w / max(w.max(), 1e-6)
    pick = np.searchsorted(prog, np.linspace(0, prog[-1], frames)).clip(0, len(hist) - 1)
    states = [dict(t=hist[i][0], s=hist[i][1], theta=hist[i][2], phi=hist[i][3], w=hist[i][4], gm=hist[i][5],
                   phase="flooding") for i in pick]
    last = dict(states[-1])
    hmax = 40.0 + hb["vertical"]["draught"]
    for k in range(1, end_frames + 1):
        u = k / end_frames
        e = dict(last, phase=fate or "afloat")
        if fate == "plunges":
            sgn = math.copysign(1, last["theta"])
            e["theta"] = last["theta"] + (sgn * math.radians(38) - last["theta"]) * min(1, 1.6 * u) ** 2
            e["s"] = last["s"] + max(0, u - 0.25) / 0.75 * (hb["length"] / 2 * math.sin(math.radians(38)) + hmax)
        elif fate == "capsizes":
            sgn = math.copysign(1, last["phi"] or 1)
            e["phi"] = last["phi"] + (sgn * math.radians(170) - last["phi"]) * min(1, 1.4 * u) ** 1.5
            e["s"] = last["s"] + max(0, u - 0.45) / 0.55 * (hb["beam"] + hmax)
        elif fate == "founders":
            e["s"] = last["s"] + u ** 1.5 * hmax
        else:
            break
        e["t"] = last["t"] + u * 120
        states.append(e)
    return states, fate or "stays afloat", f


# --- drawing --------------------------------------------------------------------------------------------------

class Points:
    """The ship as points: (x, y, z over the design waterline, rgb), its deck from the sprite and height map, its
    bottom from hull_form, and walls down every step in height, at `ppm` px per metre."""
    def __init__(self, export_dir, hb, sp, ppm):
        S = sp["scale_px_per_m"]
        meta = dict(sp, mounts=sp["mounts"])
        tp = {t: os.path.join(export_dir, v["file"]) for t, v in sp["turret_types"].items()}
        args = (os.path.join(export_dir, "hull.png"), tp, meta, lambda m: m["rest_deg"])
        img = render.composite(*args, sun=(240, 50), height_p=os.path.join(export_dir, "height.png"))
        solid = render.composite(*args).getchannel("A")       # the ship itself, not the shadow it casts
        hmap = np.asarray(Image.open(os.path.join(export_dir, "height.png")).convert("L"), np.float32) \
            * sp["shadow"]["height_step_m"]
        # turrets at their roofs (the height map is the hull's)
        for m in sp["mounts"]:
            t = Image.open(tp[m["type"]]).convert("RGBA").rotate(-m["rest_deg"], resample=Image.BICUBIC)
            a = np.zeros(hmap.shape, np.float32)
            cx, cy = round(m["px"][0] - t.width / 2), round(m["px"][1] - t.height / 2)
            lay = Image.new("L", (hmap.shape[1], hmap.shape[0]), 0)
            lay.paste(t.getchannel("A"), (cx, cy))
            a = np.asarray(lay) > 128
            hmap = np.where(a, np.maximum(hmap, m["top_m"]), hmap)
        k = ppm / S
        size = (max(1, round(img.width * k)), max(1, round(img.height * k)))
        img = img.resize(size, Image.LANCZOS)
        solid = np.asarray(solid.resize(size, Image.LANCZOS))
        hmap = np.asarray(Image.fromarray(hmap, "F").resize(size, Image.NEAREST))
        rgba = np.asarray(img, np.float32)
        ox, oy = sp["origin_px"][0] * k, sp["origin_px"][1] * k
        mask = solid > 100
        yy, xx = np.nonzero(mask)
        X = (xx + 0.5 - ox) / ppm
        Y = (yy + 0.5 - oy) / ppm
        Z = hmap[yy, xx]
        C = rgba[yy, xx, :3]
        # the bottom, from hull_form: the lowest height where the section is at least |y| wide
        wl = hb["vertical"]["waterline"]
        st = hb["hull_form"]["stations"]
        sx = np.array([s["x"] for s in st])
        def bottom(x, y):
            i = np.clip(np.searchsorted(sx, x) - 1, 0, len(st) - 2)
            out = np.empty_like(x)
            for j in np.unique(i):
                sel = i == j
                a, b = st[j], st[j + 1]
                za = np.interp(np.abs(y[sel]), np.maximum.accumulate(a["y"]), a["z"])
                zb = np.interp(np.abs(y[sel]), np.maximum.accumulate(b["y"]), b["z"])
                u = np.clip((x[sel] - a["x"]) / max(b["x"] - a["x"], 1e-6), 0, 1)
                out[sel] = za + (zb - za) * u - wl
            return out
        Zb = np.minimum(bottom(X, Y), Z - 0.5)
        # walls: from each point down to its lowest 4-neighbour (outside the ship: its own bottom)
        H = np.full(mask.shape, np.nan, np.float32)
        H[yy, xx] = Z
        low = Z.copy()
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            ny, nx = np.clip(yy + dy, 0, mask.shape[0] - 1), np.clip(xx + dx, 0, mask.shape[1] - 1)
            n = H[ny, nx]
            edge = ~mask[ny, nx] | (ny != yy + dy) | (nx != xx + dx)
            low = np.minimum(low, np.where(edge, Zb, np.nan_to_num(n, nan=1e9)))
        n_wall = np.clip(np.ceil((Z - low) * ppm * 1.5), 0, 400).astype(int)
        rep = np.repeat(np.arange(len(Z)), n_wall)
        frac = (np.arange(len(rep)) - np.repeat(np.cumsum(n_wall) - n_wall, n_wall) + 0.5) / np.repeat(n_wall, n_wall)
        WZ = Z[rep] - (Z[rep] - low[rep]) * frac
        WC = np.where((WZ < 0)[:, None], ANTIFOULING, C[rep] * 0.62)
        self.x = np.concatenate([X, X, X[rep]])
        self.y = np.concatenate([Y, Y, Y[rep]])
        self.z = np.concatenate([Z, Zb, WZ])
        self.c = np.concatenate([C, np.broadcast_to(ANTIFOULING * 0.85, C.shape), WC]).astype(np.float32)
        self.ppm = ppm
        self.lcf = hb["hydrostatics"]["lcf"]
        L, B = hb["length"], hb["beam"]
        hmax = float(Z.max())
        self.w = round((L + 30) * ppm)
        self.h = round((B + 2 * hmax * 0.8 + 10) * ppm)

    def frame(self, s, theta, phi):
        # roll (starboard down for phi > 0), then pitch (bow down for theta > 0) about the lcf, then sink
        cp, sp_ = math.cos(phi), math.sin(phi)
        y1 = self.y * cp + self.z * sp_
        z1 = self.z * cp - self.y * sp_
        x0 = self.x - self.lcf
        ct, st = math.cos(theta), math.sin(theta)
        x2 = x0 * ct + z1 * st + self.lcf
        z2 = z1 * ct - x0 * st - s
        px = np.round(x2 * self.ppm + self.w / 2).astype(int)
        py = np.round(y1 * self.ppm + self.h / 2).astype(int)
        ok = (px >= 0) & (px < self.w) & (py >= 0) & (py < self.h)
        order = np.argsort(z2[ok], kind="stable")           # the highest point at a pixel is the one seen
        px, py, z2, col = px[ok][order], py[ok][order], z2[ok][order], self.c[ok][order]
        rgb = np.broadcast_to(SEA, (self.h, self.w, 3)).copy()
        zb = np.full((self.h, self.w), -np.inf, np.float32)
        rgb[py, px] = col
        zb[py, px] = z2
        # close the pinholes a roll or a pitch opens between the points: an empty pixel takes its highest
        # neighbour's point when most of its neighbours have one
        hit = np.isfinite(zb)
        pad = lambda a, v: np.pad(a, 1, constant_values=v)
        zp, hp = pad(zb, -np.inf), pad(hit, False)
        cp_ = np.pad(rgb, ((1, 1), (1, 1), (0, 0)), mode="edge")
        nb = [(dy, dx) for dy in (0, 1, 2) for dx in (0, 1, 2) if (dy, dx) != (1, 1)]
        count = sum(hp[dy:dy + self.h, dx:dx + self.w].astype(int) for dy, dx in nb)
        fill = ~hit & (count >= 5)
        best = np.full((self.h, self.w), -np.inf, np.float32)
        for dy, dx in nb:
            z = zp[dy:dy + self.h, dx:dx + self.w]
            take = fill & (z > best)
            best = np.where(take, z, best)
            rgb[take] = cp_[dy:dy + self.h, dx:dx + self.w][take]
        zb = np.where(fill, best, zb)
        # under the surface: fading into the sea with depth; at it, a thin line of foam
        depth = np.where(np.isfinite(zb), -zb, -1.0)
        a = np.where(depth > 0, np.clip(0.35 + depth / 3.0, 0, 1), 0.0)[..., None]
        out = rgb * (1 - a) + SEA * a
        foam = np.isfinite(zb) & (np.abs(zb) < 0.15)
        out[foam] = out[foam] * 0.55 + FOAM * 0.45
        return Image.fromarray(out.clip(0, 255).astype(np.uint8), "RGB")


def caption(img, text):
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
    d.text((8, 6), text, fill=(235, 240, 240), font=font)
    return img


def label(name, st, fate):
    t = st["t"] / 60
    if st["phase"] == "flooding":
        return (f"{name}: {t:5.1f} min  flooded {st['w']:,.0f} t  sinkage {st['s']:.2f} m  "
                f"trim {math.degrees(st['theta']):+.2f}°  heel {math.degrees(st['phi']):+.1f}°  GM {st['gm']:.2f} m")
    return f"{name}: {fate} after {t:.0f} min"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export_dir")
    ap.add_argument("--scenario", choices=["stern", "bow", "starboard", "port", "all"], default=None,
                    help="default: stern, bow and starboard")
    ap.add_argument("--hole", type=float, help="total hole area, m² (default 0.1 √Δ)")
    ap.add_argument("--leak", type=float, default=1.0, help="scales the bulkheads' leaks (0: watertight)")
    ap.add_argument("--ppm", type=float, help="px per metre (default: 1000 px over the length, at most 8)")
    ap.add_argument("--out", help="default: <export_dir>/sinking")
    a = ap.parse_args()
    hb, sp = load(a.export_dir)
    out = a.out or os.path.join(a.export_dir, "sinking")
    os.makedirs(out, exist_ok=True)
    hole = a.hole or 0.1 * math.sqrt(hb["hydrostatics"]["displacement_t"])
    ppm = a.ppm or min(8.0, 1000 / hb["length"])
    pts = Points(a.export_dir, hb, sp, ppm)
    names = {None: ["stern", "bow", "starboard"], "all": ["stern", "bow", "starboard", "port"]}.get(
        a.scenario, [a.scenario])
    sc = scenarios(hb)
    strips = []
    for name in names:
        states, fate, f = simulate(hb, sc[name][0], hole, a.leak, sc[name][1])
        frames = [caption(pts.frame(st["s"], st["theta"], st["phi"]), label(name, st, fate)) for st in states]
        frames += [frames[-1]] * 6
        gif = os.path.join(out, f"sink_{name}.gif")
        frames[0].save(gif, save_all=True, append_images=frames[1:], duration=90, loop=0)
        keys = [frames[i] for i in np.linspace(0, len(states) - 1, 6).round().astype(int)]
        strips.append(keys)
        print(f"{name:>10}: {len(sc[name][0])} cells breached, {hole:.1f} m²; {fate} after {states[-1]['t'] / 60:.0f} min "
              f"-> {gif}")
    w, h = strips[0][0].size
    sheet = Image.new("RGB", (w * len(strips), h * 6), tuple(int(v) for v in SEA))
    for i, keys in enumerate(strips):
        for j, im in enumerate(keys):
            sheet.paste(im, (i * w, j * h))
    sheet.save(os.path.join(out, "sinking_sheet.png"))
    print(f"sheet -> {os.path.join(out, 'sinking_sheet.png')}")


if __name__ == "__main__":
    main()
