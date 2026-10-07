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
  breaking    Break: a total loss, the ship parted at a station (a main magazine, or amidships) into two rigid
              bodies, each with large-angle buoyancy from hull_form, its own weight from report.json, its torn
              end open to the sea and shocked bulkheads that give way under head (vidgen/sinkvid.py draws it)
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


# --- breaking in two ------------------------------------------------------------------------------------------
# A total loss: the ship breaks at a station (a magazine going up, or the girder failing) and the two pieces sink on
# their own. Each piece is a rigid body: its buoyancy comes from the hull form at any attitude, not from
# hydrostatics' small-angle coefficients, and its cells flood through the torn end with heads from the real pose.

BREAK_DT = 0.05          # s per step
BREAK_LEAK = 25.0        # the shock that broke her strains every bulkhead: leaks x this
TORN_OPEN = 0.5          # share of a torn cell's end open to the sea; wreckage fills the rest
SPLIT_V = 0.4            # m/s the break throws each piece away from it
ZETA = 0.4               # linear damping, share of critical (radiation and viscous, lumped)
CD_BODY = 1.0            # drag coefficient of a piece moving broadside through the water
ADDED = (1.0, 1.0, 0.2)  # added mass in heave, pitch and roll, x the piece's own
BREAK_HOURS = 0.75       # gives up after this, a piece still afloat
SETTLED_S = 120.0        # done once every piece left afloat has lain still (and stopped taking water) this long
# a shocked bulkhead (or deck) gives way when the head across it passes its strength, then is open over this share
# of its face. Each one's strength head is drawn evenly from BULKHEAD_HEAD (m): the blast has strained them all,
# some far worse than others
BULKHEAD_HEAD = (1.5, 7.0)
BULKHEAD_TORN = 0.3


def hull_bottom(hb):
    """z of the hull's bottom (over the design waterline) at ship (x, y), and its deck half-breadth at x."""
    wl = hb["vertical"]["waterline"]
    st = hb["hull_form"]["stations"]
    sx = np.array([s["x"] for s in st])
    ys = [np.maximum.accumulate(s["y"]) for s in st]
    ymax = np.array([y[-1] for y in ys])

    def bottom(x, y):
        x, y = np.asarray(x, float), np.asarray(y, float)
        i = np.clip(np.searchsorted(sx, x) - 1, 0, len(st) - 2)
        out = np.empty_like(x)
        for j in np.unique(i):
            sel = i == j
            za = np.interp(np.abs(y[sel]), ys[j], st[j]["z"])
            zb = np.interp(np.abs(y[sel]), ys[j + 1], st[j + 1]["z"])
            u = np.clip((x[sel] - sx[j]) / max(sx[j + 1] - sx[j], 1e-6), 0, 1)
            out[sel] = za + (zb - za) * u - wl
        return out
    return bottom, lambda x: np.interp(x, sx, ymax)


def hull_samples(hb, nx=160, ny=22, nz=22):
    """Points filling the hull up to the main deck (x, y, z over the design waterline) and the volume each stands
    for, scaled so the hull under the waterline holds hydrostatics' volume."""
    L, B, v = hb["length"], hb["beam"], hb["vertical"]
    bottom, half = hull_bottom(hb)
    dx, dy, dz = L / nx, B / ny, v["depth"] / nz
    gx = -L / 2 + dx * (np.arange(nx) + 0.5)
    gy = -B / 2 + dy * (np.arange(ny) + 0.5)
    gz = v["keel"] - v["waterline"] + dz * (np.arange(nz) + 0.5)
    X, Y, Z = (a.ravel() for a in np.meshgrid(gx, gy, gz, indexing="ij"))
    keep = (np.abs(Y) <= half(X)) & (Z >= bottom(X, Y))
    X, Y, Z = X[keep], Y[keep], Z[keep]
    dv = hb["hydrostatics"]["volume_m3"] / max(1, int((Z < 0).sum()))
    return X, Y, Z, dv, dz


def weight_curve(hb, rep, n=400):
    """(bin centres, t per bin, t m of height per bin; heights over the design waterline). The report gives each
    weight as a point, so the spread is assumed: armour at the belt's centre over the belt, a strake over itself,
    machinery and fuel over the machinery rooms, hull and misc weights along the hull's section areas (tilted to
    keep their centre), anything else (a turret, a deckhouse) over 2 % of the length either side. Then the whole
    hull's share is tilted so the curve's centre is hydrostatics' lcg. A stand-in until shipgen exports extents."""
    L, v = hb["length"], hb["vertical"]
    xs = -L / 2 + L / n * (np.arange(n) + 0.5)
    X, _, _, dv, _ = hull_samples(hb, nx=n, ny=12, nz=12)
    area = np.bincount(np.clip(((X + L / 2) / L * n).astype(int), 0, n - 1), minlength=n).astype(float)
    area = 0.5 * area / area.sum() + 0.5 / n                       # section areas, blended with even
    spans = {}
    belt = hb.get("armour", {}).get("belt")
    if belt:
        spans["belt"] = (belt["x0"], belt["x1"])
    for s in hb.get("armour", {}).get("strakes", []):
        spans[s["id"]] = (s["x0"], s["x1"])
    mach = [r for r in hb["rooms"] if r["kind"] in ("boiler_room", "engine_room")]
    if mach:
        spans["machinery"] = (min(r["x0"] for r in mach), max(r["x1"] for r in mach))
    near = lambda x, sp: abs(x - (sp[0] + sp[1]) / 2) < 1.0
    t = np.zeros(n)
    tz = np.zeros(n)
    hull_t = np.zeros(n)
    for w in rep["weights"]:
        if w["t"] <= 0:
            continue
        z = w["z"] - v["draught"]
        if w["name"] in spans:
            sp = spans[w["name"]]
        elif w["group"] == "armour" and "belt" in spans and near(w["x"], spans["belt"]):
            sp = spans["belt"]
        elif w["group"] in ("machinery", "fuel") and "machinery" in spans and near(w["x"], spans["machinery"]):
            sp = spans["machinery"]
        elif w["group"] in ("hull", "misc"):
            # the hull's distribution, tilted (linearly in x) to put its centre at the weight's x
            d = area * (1 + _tilt(xs, area, w["x"]) * xs)
            d = np.maximum(d, 0)
            d /= d.sum()
            t += w["t"] * d
            tz += w["t"] * z * d
            hull_t += w["t"] * d
            continue
        else:
            sp = (w["x"] - 0.02 * L, w["x"] + 0.02 * L)
        lo, hi = max(sp[0], -L / 2), min(sp[1], L / 2)
        d = np.clip((np.minimum(xs + L / n / 2, hi) - np.maximum(xs - L / n / 2, lo)) / (L / n), 0, 1)
        d = d / d.sum() if d.sum() > 0 else (np.abs(xs - w["x"]) == np.abs(xs - w["x"]).min()).astype(float)
        t += w["t"] * d
        tz += w["t"] * z * d
    # the whole hull's share tilted so the curve's centre is the ship's lcg
    lcg = hb["hydrostatics"]["lcg"]
    if hull_t.sum() > 0:
        shift = (lcg * t.sum() - (t * xs).sum())
        h = hull_t / hull_t.sum()
        k = shift / max(hull_t.sum() * ((h * xs * xs).sum() - (h * xs).sum() ** 2), 1e-9)
        adj = hull_t * k * (xs - (h * xs).sum())
        adj = np.maximum(adj, -0.9 * hull_t)
        zh = tz / np.maximum(t, 1e-9)
        t = t + adj
        tz = tz + adj * zh
    return xs, t, tz


def _tilt(xs, d, x_want):
    """k so that d (1 + k x) has its centre at x_want (first order)."""
    d = d / d.sum()
    m1, m2 = (d * xs).sum(), (d * xs * xs).sum()
    return (x_want - m1) / max(m2 - x_want * m1, 1e-9)


def break_points(hb):
    """name -> (cut x, the torn zone (x0, x1), why): aft and fore at the aftmost and foremost main-battery
    magazines (the usual way a big ship is lost outright), mid at the section amidships (the girder failing). With
    no main magazine, the section at a quarter of the length from that end."""
    L = hb["length"]
    main = {c["id"] for c in hb["components"] if c["kind"] == "main"}
    mags = [r for r in hb["rooms"] if r["kind"] == "magazine"
            and ({r.get("mount")} | set(r.get("mounts", []))) & main]
    sec = lambda x: min(hb["sections"], key=lambda s: 0 if s["x0"] <= x <= s["x1"] else
                        min(abs(x - s["x0"]), abs(x - s["x1"])))
    out = {}
    s = sec(0.0)
    out["mid"] = (0.5 * (s["x0"] + s["x1"]), (s["x0"], s["x1"]), f"section {s['id']}")
    for name, pick, x_q in (("aft", min, -0.25 * L), ("fore", max, 0.25 * L)):
        if mags:
            r = pick(mags, key=lambda r: r["x0"] + r["x1"])
            out[name] = (0.5 * (r["x0"] + r["x1"]), (r["x0"], r["x1"]), r["id"])
        else:
            s = sec(x_q)
            out[name] = (0.5 * (s["x0"] + s["x1"]), (s["x0"], s["x1"]), f"section {s['id']}")
    return out


def cut_point(hb, x):
    """break_points' entry for a cut at x metres: the torn zone is the section holding it."""
    s = min(hb["sections"], key=lambda s: 0 if s["x0"] <= x <= s["x1"] else min(abs(x - s["x0"]), abs(x - s["x1"])))
    return x, (s["x0"], s["x1"]), f"section {s['id']}"


def apply_pose(x, y, z, pose):
    """A piece's attitude: roll (starboard down for phi > 0), then pitch (bow down for theta > 0), both about the
    pivot (px, 0, pz), then the pivot moved by (dx, dy) and sunk by s. With the pivot at (lcf, 0, 0) and no move,
    it's Points.frame's attitude."""
    s, th, ph, px, pz, dx, dy = pose
    cp, sp_ = math.cos(ph), math.sin(ph)
    ct, st = math.cos(th), math.sin(th)
    zr = z - pz
    y1 = y * cp + zr * sp_
    z1 = zr * cp - y * sp_
    x0 = x - px
    return x0 * ct + z1 * st + px + dx, y1 + dy, z1 * ct - x0 * st + pz - s


def orifice(ha, hb_, zlo, zhi, area):
    """Signed flow (m³/s) from the side at level ha to the one at hb_ through an opening spanning zlo..zhi: the
    part under the higher level, at the head down to the lower level (or the wet part's middle)."""
    hi, lo = np.maximum(ha, hb_), np.minimum(ha, hb_)
    span = np.maximum(zhi - zlo, 1e-6)
    wet = np.where(zhi - zlo > 1e-3, np.clip((hi - zlo) / span, 0, 1), (hi > zlo).astype(float))
    mid = (zlo + np.minimum(hi, zhi)) / 2
    head = np.clip(hi - np.maximum(lo, mid), 0, None)
    return np.sign(ha - hb_) * CD * area * wet * np.sqrt(2 * G * head)


class Piece:
    """One part of a broken ship: its hull samples and dry weight on its side of the cut, its share of the cells
    (a cell the cut runs through is split by length), and a rigid body's state. Heights are over the design
    waterline, positions in the ship's frame at the moment of the break."""

    def __init__(self, brk, side):
        hb, xc = brk.hb, brk.x_cut
        self.side = side                                   # -1 aft of the cut, +1 forward of it
        on = (brk.hx > xc) if side > 0 else (brk.hx <= xc)
        self.hx, self.hy, self.hz = brk.hx[on], brk.hy[on], brk.hz[on]
        self.dv = brk.dv
        won = (brk.wx > xc) if side > 0 else (brk.wx <= xc)
        self.M0 = float(brk.wt[won].sum())
        self.G = np.array([(brk.wt[won] * brk.wx[won]).sum() / self.M0, 0.0,
                           brk.wtz[won].sum() / self.M0])
        self.x0, self.x1 = (xc, hb["length"] / 2) if side > 0 else (-hb["length"] / 2, xc)
        self.length = self.x1 - self.x0
        # cells, clipped to this side
        wl = hb["vertical"]["waterline"]
        ids, rows = [], []
        for c in hb["cells"]:
            cap = c["volume_m3"] * c.get("permeability", 1)
            if cap <= 0.5:
                continue
            a, b = max(c["x0"], self.x0), min(c["x1"], self.x1)
            if b - a < 0.05:
                continue
            share = (b - a) / max(c["x1"] - c["x0"], 1e-6)
            ids.append(c["id"])
            rows.append((a, b, c["y0"], c["y1"], c["base"] - wl, c["top"] - wl, cap * share, c["top"] > -0.05,
                         c["neighbours"]))
        self.ids = ids
        idx = {c: i for i, c in enumerate(ids)}
        f = lambda k: np.array([r[k] for r in rows], float)
        self.cx0, self.cx1, self.cy0, self.cy1, self.base, self.top, self.cap = (f(k) for k in range(7))
        self.on_deck = np.array([r[7] for r in rows], bool)
        self.w = np.zeros(len(rows))
        self.plan = (self.cx1 - self.cx0) * (self.cy1 - self.cy0)
        # the cells' corners, for their world height range
        cx = np.stack([self.cx0, self.cx1], 1)[:, [0, 1, 0, 1, 0, 1, 0, 1]]
        cy = np.stack([self.cy0, self.cy1], 1)[:, [0, 0, 1, 1, 0, 0, 1, 1]]
        cz = np.stack([self.base, self.top], 1)[:, [0, 0, 0, 0, 1, 1, 1, 1]]
        self.corners = (cx.ravel(), cy.ravel(), cz.ravel())
        # openings to the sea: (cell, area, low point, high point). The torn zone's cells are open across their
        # end at the cut (a little more on the side the blast came from, so the piece lists); a main-deck cell
        # through its hatches once its deck is under
        op = []
        z0, z1_ = brk.zone
        for i in range(len(rows)):
            yc = 0.5 * (self.cy0[i] + self.cy1[i])
            if self.cx1[i] > z0 and self.cx0[i] < z1_:
                xf = self.cx1[i] if side < 0 else self.cx0[i]
                bias = 0.8 + 0.2 * float(np.clip(yc / (hb["beam"] / 4), -1, 1)) * brk.blast_side
                op.append((i, TORN_OPEN * bias * (self.cy1[i] - self.cy0[i]) * (self.top[i] - self.base[i]),
                           (xf, yc, self.base[i]), (xf, yc, self.top[i])))
            if self.on_deck[i]:
                p = (0.5 * (self.cx0[i] + self.cx1[i]), yc, self.top[i])
                op.append((i, DECK_OPEN * self.plan[i], p, p))
        self.op_cell = np.array([o[0] for o in op], int)
        self.op_area = np.array([o[1] for o in op], float)
        self.op_lo = tuple(np.array([o[2][k] for o in op], float) for k in range(3))
        self.op_hi = tuple(np.array([o[3][k] for o in op], float) for k in range(3))
        # links between this piece's cells: (i, j, area, low point, high point)
        lk = []
        for i, r in enumerate(rows):
            for nid, bnd in r[8]:
                j = idx.get(nid)
                if j is None or j <= i:
                    continue
                ox0, ox1 = max(self.cx0[i], self.cx0[j]), min(self.cx1[i], self.cx1[j])
                oy0, oy1 = max(self.cy0[i], self.cy0[j]), min(self.cy1[i], self.cy1[j])
                oz0, oz1 = max(self.base[i], self.base[j]), min(self.top[i], self.top[j])
                vert = abs(self.top[i] - self.base[j]) < 0.05 or abs(self.top[j] - self.base[i]) < 0.05
                face = max(0.0, ox1 - ox0) * max(0.0, oy1 - oy0) if vert else \
                    max(max(0.0, ox1 - ox0), max(0.0, oy1 - oy0)) * max(0.0, oz1 - oz0)
                tight = "ulkhead" in bnd or bnd == "Inner bottom"
                if tight:
                    area = LEAK * brk.leak * face
                elif bnd == "open":
                    area = max(1.0, 0.3 * face)
                else:
                    area = HATCH * face
                if area <= 1e-4:
                    continue
                pc = (0.5 * (ox0 + ox1), 0.5 * (oy0 + oy1))
                zl, zh = (min(self.top[i], self.top[j]),) * 2 if vert else (oz0, oz1)
                lk.append((i, j, area, (pc[0], pc[1], zl), (pc[0], pc[1], zh), tight, BULKHEAD_TORN * face))
        self.lk_i = np.array([l[0] for l in lk], int)
        self.lk_j = np.array([l[1] for l in lk], int)
        self.lk_a = np.array([l[2] for l in lk], float)
        self.lk_lo = tuple(np.array([l[3][k] for l in lk], float) for k in range(3))
        self.lk_hi = tuple(np.array([l[4][k] for l in lk], float) for k in range(3))
        tight = np.array([l[5] for l in lk], bool)
        self.lk_torn = np.array([l[6] for l in lk], float)
        self.lk_fail = np.where(tight, brk.rng.uniform(*BULKHEAD_HEAD, len(lk)), np.inf)
        self.failed = 0
        # the body: G in the world, its velocity, pitch and roll and their rates
        self.Gw = self.G.copy()
        self.V = np.array([side * SPLIT_V, 0.0, 0.0])
        self.th = self.ph = self.wth = self.wph = 0.0
        # damping from the intact piece's own heave stiffness and roll period
        self.dz = brk.dz
        self.awp = float((np.abs(self.hz) < 0.5 * brk.dz).sum()) * self.dv / brk.dz
        B = hb["beam"]
        self.k_th, self.k_ph = 0.29 * self.length, 0.38 * B
        self.om_z = math.sqrt(RHO * G * max(self.awp, 1.0) / (self.M0 * (1 + ADDED[0])))
        self.om_ph = math.sqrt(G * max(hb["hydrostatics"]["gm_t"], 0.3)) / self.k_ph
        self.q_th = RHO * CD_BODY * B * self.length ** 4 / 64
        self.q_ph = RHO * CD_BODY * self.length * B ** 4 / 64
        self.t_gone = None
        self.zmax = float(self.hz.max())

    def pose(self):
        G = self.G
        return (float(G[2] - self.Gw[2]), self.th, self.ph, float(G[0]), float(G[2]),
                float(self.Gw[0] - G[0]), float(self.Gw[1]))

    def levels(self, pose):
        """World height of each cell's water surface: its fill over its world height range (a cell's water is
        taken to lie level across it, which is rough past a few tens of degrees, but it's the mass that matters)."""
        _, _, Z = apply_pose(*self.corners, pose)
        Z = Z.reshape(-1, 8)
        lo, hi = Z.min(1), Z.max(1)
        f = np.clip(self.w / self.cap, 0, 1)
        return lo + f * (hi - lo), lo, hi

    def step(self, dt):
        pose = self.pose()
        zw, lo, hi = self.levels(pose)
        harea = self.cap / np.maximum(hi - lo, 0.3)        # a cell's plan area at this attitude, roughly
        dw = np.zeros_like(self.w)
        if len(self.op_cell):
            _, _, ol = apply_pose(*self.op_lo, pose)
            _, _, oh = apply_pose(*self.op_hi, pose)
            ol, oh = np.minimum(ol, oh), np.maximum(ol, oh)
        if len(self.lk_i):
            _, _, ll = apply_pose(*self.lk_lo, pose)
            _, _, lh = apply_pose(*self.lk_hi, pose)
            ll, lh = np.minimum(ll, lh), np.maximum(ll, lh)
        # pressure levels: a filling cell rises toward the level of what feeds it, the sea through an opening under
        # it or a neighbour through a link under that one's level (sinking.Flood's sea on up through a full cell).
        # Blended in from 85 % full, as a cell's level from its fill is rough at an angle
        fill = np.clip(self.w / self.cap, 0, 1)
        k = np.clip((fill - 0.85) / 0.15, 0, 1)
        k = k * k * (3 - 2 * k)
        feed = np.full_like(zw, -np.inf)
        if len(self.op_cell):
            np.maximum.at(feed, self.op_cell[ol < 0], 0.0)
        P = np.maximum(zw, zw + (np.maximum(feed, zw) - zw) * k)
        if len(self.lk_i):
            i, j = self.lk_i, self.lk_j
            for _ in range(12):
                f2 = feed.copy()
                np.maximum.at(f2, j, np.where(ll < P[i], P[i], -np.inf))
                np.maximum.at(f2, i, np.where(ll < P[j], P[j], -np.inf))
                P2 = np.maximum(zw, zw + (np.maximum(f2, zw) - zw) * k)
                if np.allclose(P2, P, atol=1e-3):
                    break
                P = P2
        # the sea, through the openings (and back out, where a cell's water stands above the sea)
        if len(self.op_cell):
            c = self.op_cell
            q = orifice(0.0, P[c], ol, oh, self.op_area) * dt
            q = np.minimum(q, np.abs(zw[c]) * harea[c] + (self.cap[c] - self.w[c]))   # no further than the levels meeting
            q = np.maximum(q, -self.w[c])
            np.add.at(dw, c, q)
        # between cells
        if len(self.lk_i):
            zl, zh = ll, lh
            # bulkheads giving way: the head across one, at its foot
            head = np.abs(P[i] - P[j]) * (np.maximum(P[i], P[j]) > zl)
            gone = head > self.lk_fail
            if gone.any():
                self.lk_a[gone] = np.maximum(self.lk_a[gone], self.lk_torn[gone])
                self.lk_fail[gone] = np.inf
                self.failed += int(gone.sum())
            q = orifice(P[i], P[j], zl, zh, self.lk_a) * dt
            lim = 0.5 * np.abs(P[i] - P[j]) * np.minimum(harea[i], harea[j])
            q = np.clip(q, -lim, lim)
            q = np.clip(q, -0.5 * self.w[j], 0.5 * self.w[i])
            np.add.at(dw, i, -q)
            np.add.at(dw, j, q)
        self.w = np.clip(self.w + dw, 0, self.cap)
        # forces: buoyancy over the submerged samples, the dry weight at G, each cell's water at its centre
        X, Y, Z = apply_pose(self.hx, self.hy, self.hz, pose)
        self.zmax = float(Z.max())
        sub = Z < 0
        # the linear (wave-making) damping goes with the waterplane the piece still has
        wp = min(1.5, float((np.abs(Z) < 0.5 * self.dz).sum()) * self.dv / self.dz / max(self.awp, 1.0))
        Bf = RHO * G * self.dv * float(sub.sum())
        wt = RHO * self.w
        f = np.clip(self.w / self.cap, 0, 1)
        WX, WY, _ = apply_pose(0.5 * (self.cx0 + self.cx1), 0.5 * (self.cy0 + self.cy1),
                               self.base + 0.5 * f * (self.top - self.base), pose)
        M = self.M0 + float(wt.sum())
        gx, gy = self.Gw[0], self.Gw[1]
        # generalised moments of the vertical forces: dZ/dtheta = -(X - Gx), dZ/dphi = -(Y - Gy) cos(theta)
        if Bf > 0:
            bx, by = float(X[sub].mean()), float(Y[sub].mean())
        else:
            bx, by = gx, gy
        ww = wt * G
        q_th = -Bf * (bx - gx) + float((ww * (WX - gx)).sum())
        q_ph = math.cos(self.th) * (-Bf * (by - gy) + float((ww * (WY - gy)).sum()))
        Fz = Bf - M * G
        mz = M * (1 + ADDED[0])
        i_th = M * (1 + ADDED[1]) * self.k_th ** 2
        i_ph = M * (1 + ADDED[2]) * self.k_ph ** 2
        L_, B_ = self.length, self.k_ph / 0.38
        ct, cp = abs(math.cos(self.th)), abs(math.cos(self.ph))
        a_z = L_ * B_ * ct * cp + B_ * 8.0 * abs(math.sin(self.th)) + L_ * 8.0 * abs(math.sin(self.ph))
        vz = self.V[2]
        Fz -= 2 * ZETA * wp * self.om_z * mz * vz + 0.5 * RHO * CD_BODY * a_z * abs(vz) * vz
        q_th -= 2 * ZETA * wp * self.om_z * i_th * self.wth + self.q_th * abs(self.wth) * self.wth
        q_ph -= 2 * ZETA * wp * self.om_ph * i_ph * self.wph + self.q_ph * abs(self.wph) * self.wph
        self.V[2] += Fz / mz * dt
        self.V[:2] *= math.exp(-dt / 20.0)
        self.wth += q_th / i_th * dt
        self.wph += q_ph / i_ph * dt
        self.Gw += self.V * dt
        self.th += self.wth * dt
        self.ph += self.wph * dt
        self.Bf, self.M = Bf, M

    def activity(self):
        """How fast its far ends move, m/s: the clip's time warp follows it."""
        return abs(self.V[2]) + abs(self.wth) * self.length / 2 + abs(self.wph) * self.k_ph / 0.38 / 2


class Break:
    """A ship broken in two at x_cut: the parts aft and forward of it, each sinking on its own. zone is the torn
    stretch (the magazine room or the section at the cut): its cells open to the sea across their ends."""

    def __init__(self, hb, rep, x_cut, zone, leak=BREAK_LEAK, blast_side=1, seed=0):
        self.hb, self.x_cut, self.zone, self.leak, self.blast_side = hb, x_cut, zone, leak, blast_side
        self.rng = np.random.default_rng(seed)
        self.hx, self.hy, self.hz, self.dv, self.dz = hull_samples(hb)
        self.wx, self.wt, self.wtz = weight_curve(hb, rep)
        self.pieces = [Piece(self, -1), Piece(self, 1)]
        self.t = 0.0
        self.still = 0.0
        self.w_hist = []          # (t, water in each piece), a sample a second, for the settled test

    def step(self, dt=BREAK_DT):
        for p in self.pieces:
            p.step(dt)
            if p.t_gone is None and p.zmax < 0:
                p.t_gone = self.t + dt
        self.t += dt
        # settled: the pieces afloat lie still and, over the last 30 s, took in under 0.5 t/s (a step's own
        # flows chatter in and out of a cell, so it's judged over a window)
        if not self.w_hist or self.t - self.w_hist[-1][0] >= 1.0:
            self.w_hist.append((self.t, [RHO * float(p.w.sum()) for p in self.pieces]))
            t0, w0 = next(h for h in self.w_hist if h[0] >= self.t - 30.0 - 1e-6)
            afloat = [k for k, p in enumerate(self.pieces) if p.zmax > -60.0]
            quiet = self.t - t0 >= 29.0 and all(
                self.pieces[k].activity() < 0.1 and
                RHO * float(self.pieces[k].w.sum()) - w0[k] < 0.5 * (self.t - t0) for k in afloat)
            self.still = self.still + (self.t - (self.w_hist[-2][0] if len(self.w_hist) > 1 else 0.0)) \
                if quiet else 0.0

    def done(self, depth=60.0):
        """Every piece deep, or the ones afloat settled (a broken-off end can float on its trapped air), or out of
        time."""
        return (all(p.zmax < -depth for p in self.pieces) or self.still > SETTLED_S
                or self.t > BREAK_HOURS * 3600)


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
