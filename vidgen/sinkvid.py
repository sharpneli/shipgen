#!/usr/bin/env python3
"""
sinkvid: a top-down clip of an exported ship sinking by the stern or the bow, in vidgen's style, to judge the
sinking surface effects of sinking_foam.md (reference: sinking_foam_ref.py) before a realtime version.

The ship is breached at one end (a hit at the waterline: a boil, a ring and a splash), floods in shipgen's
flooding model (sinking.py, time-compressed), then plunges. The plunge is scripted (the model's small-angle
attitude stops holding past the deck edge): the low end goes down, the high end rises, sinks, and the wreck keeps
descending. Everything on the surface comes from how that rigid 3D hull crosses the plane z = 0 (sinking_foam.md 2):
  crossing foam   hull surface passing down through the surface leaves foam where it crosses, rising surface a
                  weaker cascade; a contact collar rings the waterline cut, brighter where the hull moves fast
  air boils       the hitbox cells' air comes out as boils once a cell's vent is under water; a trapped share
                  burps up after the ship is gone, later, wider and fainter
  the slam        when the last part goes under: a big boil and a ring wave (lighting only)
  oil and debris  leak puddles (Fay spreading, Bonn colours, damped ripples) and floating wreckage
Foam is drawn with vidgen's lace (ridged noise, coverage cap * d^gamma), so it's the same material as the wake.

The ship is a point cloud from the sprite and height map (sinking.Points' recipe, plus normals): every pixel at its
height, walls down every step, the bottom from hull_form. It's z-buffered at twice the frame's resolution, lit by
its rotated normals and shadowed by a sun shadow map, so a rising end casts a long shadow. Parts under the surface
fade into the water with depth.

    ~/.venv/bin/python vidgen/sinkvid.py bismarck                    # stern and bow -> vidgen/out/bismarck_sink_*.mp4
    ~/.venv/bin/python vidgen/sinkvid.py bismarck --end bow --still 30
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):   # one thread each: frames are drawn in
    os.environ.setdefault(_v, "1")                                           # many processes at once
import numpy as np
from PIL import Image, ImageDraw

import vidgen as V  # noqa: E402  (puts shipgen's root on sys.path)
from vidgen import FOAM, CHURN, SUN_AZ, SUN_EL, SHADE, WIND, box_blur, lace, unit, upscale

import render     # noqa: E402  (shipgen)
import sinking    # noqa: E402  (shipgen's flooding model, game side)

# timeline, seconds of clip
HIT_S = 1.0               # the breach
APPROACH_S = 16.0         # the flooding model's hour or two, compressed (time and flooded weight share the clip)
# the plunge, after the model says the ship founders: (s, |pitch| deg, share of the final extra sinkage). The extra
# sinkage D puts the rising end's tip at the surface by the last key: D = (pivot to that end) sin(pitch) + ...
PLUNGE = [(0, 0, 0.0), (5, 5, 0.03), (10, 11, 0.09), (15, 22, 0.24), (20, 35, 0.48), (24, 44, 0.76), (27, 48, 1.0)]
V_DESC = 8.0              # m/s the wreck keeps going down at (Titanic bow estimates are 7-8)
TAIL_S = 26.0             # after the last part goes under: the slam, trapped air, oil

TAU_FRESH, TAU_RESID = 3.0, 25.0     # the wake's two foam tiers (wake.md 3), so it's the same material
CULL_M = 12.0             # points deeper than this are invisible
DRIFT = 0.03 * WIND + np.array([0.08, 0.0])   # oil and debris: ~3 % of the wind plus a little current, m/s
SUN = unit(SUN_AZ)        # screen direction toward the sun
TAN_E = math.tan(math.radians(SUN_EL))
LIGHT = np.array([SUN[0] * math.cos(math.radians(SUN_EL)), SUN[1] * math.cos(math.radians(SUN_EL)),
                  math.sin(math.radians(SUN_EL))], np.float32)
ANTIFOULING = np.array([0.47, 0.18, 0.15], np.float32)
BOOT_TOP = np.array([0.13, 0.13, 0.14], np.float32)
DEBRIS = np.array([[0.62, 0.52, 0.38], [0.55, 0.47, 0.36], [0.72, 0.66, 0.55], [0.80, 0.42, 0.25]], np.float32)
STEAM = (0.86, 0.88, 0.89)


def smooth(a, lo, hi):
    t = np.clip((np.asarray(a, np.float32) - lo) / (hi - lo), 0, 1)
    return t * t * (3 - 2 * t)


def gblur(a, sigma_px):
    """Gaussian-ish blur by three box passes (sigma^2 = r(r + 1))."""
    if sigma_px < 0.7:
        return a
    r = max(1, int(round((math.sqrt(1 + 4 * sigma_px * sigma_px) - 1) / 2)))
    return box_blur(a.astype(np.float32), r)


def nonzero_box(m, also=None):
    """(x0, y0, x1, y1) round a mask's true cells, grown to hold box `also`; None if both are empty."""
    rows, cols = np.flatnonzero(m.any(axis=1)), np.flatnonzero(m.any(axis=0))
    box = [int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1] if len(rows) else None
    if also:
        box = list(also) if box is None else [min(box[0], also[0]), min(box[1], also[1]),
                                              max(box[2], also[2]), max(box[3], also[3])]
    return box


def pchip(x, y):
    """Monotone cubic through (x, y) (Fritsch-Carlson): no overshoot, no stop at every key like smoothstep."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    h, d = np.diff(x), np.diff(y) / np.diff(x)
    m = np.empty_like(y)
    m[0], m[-1] = d[0], d[-1]
    for k in range(1, len(y) - 1):
        if d[k - 1] * d[k] <= 0:
            m[k] = 0.0
        else:
            w1, w2 = 2 * h[k] + h[k - 1], h[k] + 2 * h[k - 1]
            m[k] = (w1 + w2) / (w1 / d[k - 1] + w2 / d[k])

    def f(t):
        i = int(np.clip(np.searchsorted(x, t) - 1, 0, len(x) - 2))
        u = (t - x[i]) / h[i]
        h00, h10, h01, h11 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u, -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
        return h00 * y[i] + h10 * h[i] * m[i] + h01 * y[i + 1] + h11 * h[i] * m[i + 1]
    return f


def uniform_noise(rng, W, H, feat_px):
    """Smooth gaussian noise rank-mapped to uniform 0..1 (a threshold then means coverage)."""
    n = rng.standard_normal((H, W))
    fy, fx = np.meshgrid(np.fft.fftfreq(H), np.fft.fftfreq(W), indexing="ij")
    f = np.real(np.fft.ifft2(np.fft.fft2(n) * np.exp(-(fx * fx + fy * fy) * (2 * math.pi * feat_px) ** 2 / 2)))
    out = np.empty(f.size, np.float32)
    out[np.argsort(f.ravel())] = np.linspace(0, 1, f.size, dtype=np.float32)
    return out.reshape(H, W)


# ---------------------------------------------------------------- the pose
class Timeline:
    """The ship's attitude over the clip: zero until the hit, then the flooding model's history (game time and
    flooded weight sharing the approach, as sinking.simulate picks its frames), then the scripted plunge."""

    def __init__(self, hb, end):
        sc = sinking.scenarios(hb)
        self.breach, side = sc[end]
        hole = 0.1 * math.sqrt(hb["hydrostatics"]["displacement_t"])
        f = sinking.Flood(hb, self.breach, hole, 1.0, side)
        hist = [(0.0, 0.0, 0.0, 0.0, 0.0)]
        fills = [f.w / f.cap]
        fate = None
        while f.t < sinking.MAX_HOURS * 3600:
            f.step()
            hist.append((f.t, f.s, f.theta, f.phi, sinking.RHO * f.w.sum()))
            fills.append(np.clip(f.w / f.cap, 0, 1))
            fate = f.fate()
            if fate:
                break
        if fate not in ("plunges", "founders"):
            raise SystemExit(f"{end}: the ship {fate or 'stays afloat'}; sinkvid only draws plunges")
        self.flood, self.fate = f, fate
        h = np.array(hist)
        self.hist, self.fills = h, np.array(fills, np.float32)
        tg, w = h[:, 0], h[:, 4]
        prog = tg / tg[-1] + w / max(w.max(), 1e-6)
        self.t_f = HIT_S + APPROACH_S                 # clip time the model says it founders
        self.game_f = tg[-1]
        u = np.linspace(0, 1, 97)
        game = np.interp(u * prog[-1], prog, tg)
        self.clip_game = (HIT_S + u * APPROACH_S, game)   # clip time -> game time over the approach
        kt = [0.0] + list(HIT_S + u * APPROACH_S)
        ks = [0.0] + list(np.interp(game, tg, h[:, 1]))
        kth = [0.0] + list(np.interp(game, tg, h[:, 2]))
        kph = [0.0] + list(np.interp(game, tg, h[:, 3]))
        s_f, th_f, ph_f = ks[-1], kth[-1], kph[-1]
        # pivot (lcf) to the rising end, then the extra sinkage that brings that end's tip to the surface
        lcf, L = hb["hydrostatics"]["lcf"], hb["length"]
        self.sign = math.copysign(1.0, th_f)          # sinking.py: theta > 0 is bow down
        d_end = L / 2 - lcf if self.sign < 0 else L / 2 + lcf
        fb = hb["vertical"]["freeboard"]
        th_max = math.radians(PLUNGE[-1][1]) if fate == "plunges" else abs(th_f)
        D = d_end * math.sin(th_max) + fb * math.cos(th_max) - s_f
        for dt, deg, share in PLUNGE[1:]:
            kt.append(self.t_f + dt)
            pitch = max(abs(th_f), math.radians(deg)) if fate == "plunges" else abs(th_f)
            kth.append(self.sign * pitch)
            ks.append(s_f + share * D)
            kph.append(ph_f)
        self.t_last = kt[-1]
        self.f_s, self.f_th, self.f_ph = pchip(kt, ks), pchip(kt, kth), pchip(kt, kph)
        self.end = end

    def pose(self, t):
        if t >= self.t_last:
            return (self.f_s(self.t_last) + V_DESC * (t - self.t_last), self.f_th(self.t_last), self.f_ph(self.t_last))
        return (float(self.f_s(t)), float(self.f_th(t)), float(self.f_ph(t)))

    def game_time(self, t):
        if t <= HIT_S:
            return 0.0
        if t <= self.t_f:
            return float(np.interp(t, *self.clip_game))
        return self.game_f + (t - self.t_f)

    def fill(self, t):
        """The flooding model's per-cell fill at clip time t (already flooded cells hold no air to give up)."""
        g = self.game_time(t)
        i = int(np.clip(np.searchsorted(self.hist[:, 0], g), 0, len(self.hist) - 1))
        return self.fills[i]

    def weight(self, t):
        return float(np.interp(self.game_time(t), self.hist[:, 0], self.hist[:, 4]))


# ---------------------------------------------------------------- the ship as points
class Ship3D:
    """sinking.Points' recipe with normals: tops (the sprite at its height-map height, turrets at their roofs),
    walls down every height step (outward normals) and, apart, a coarser bottom from hull_form, which only takes
    part in the waterline cut and the crossing foam (a plunge never shows it)."""

    def __init__(self, src, hb, sp, ppm):
        S = sp["scale_px_per_m"]
        tp = {t: str(src / v["file"]) for t, v in sp["turret_types"].items()}
        img = render.composite(str(src / "hull.png"), tp, sp, lambda m: m["rest_deg"])
        hmap = np.asarray(Image.open(src / "height.png").convert("L"), np.float32) * sp["shadow"]["height_step_m"]
        for m in sp["mounts"]:
            t = Image.open(tp[m["type"]]).convert("RGBA").rotate(-m["rest_deg"], resample=Image.BICUBIC)
            lay = Image.new("L", (hmap.shape[1], hmap.shape[0]), 0)
            lay.paste(t.getchannel("A"), (round(m["px"][0] - t.width / 2), round(m["px"][1] - t.height / 2)))
            hmap = np.where(np.asarray(lay) > 128, np.maximum(hmap, m["top_m"]), hmap)
        k = ppm / S
        size = (max(1, round(img.width * k)), max(1, round(img.height * k)))
        rgba = np.asarray(img.resize(size, Image.LANCZOS), np.float32) / 255
        hmap = np.asarray(Image.fromarray(hmap, "F").resize(size, Image.NEAREST))
        ox, oy = sp["origin_px"][0] * k, sp["origin_px"][1] * k
        mask = rgba[..., 3] > 0.4
        yy, xx = np.nonzero(mask)
        X, Y, Z = (xx + 0.5 - ox) / ppm, (yy + 0.5 - oy) / ppm, hmap[yy, xx]
        C = rgba[yy, xx, :3]
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
        # walls: from each point down to its lowest 4-neighbour (outside the ship: its own bottom), facing it
        Hm = np.full(mask.shape, np.nan, np.float32)
        Hm[yy, xx] = Z
        low, nx_, ny_ = Z.copy(), np.zeros_like(Z), np.zeros_like(Z)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            py, px = np.clip(yy + dy, 0, mask.shape[0] - 1), np.clip(xx + dx, 0, mask.shape[1] - 1)
            edge = ~mask[py, px] | (py != yy + dy) | (px != xx + dx)
            nb = np.where(edge, Zb, np.nan_to_num(Hm[py, px], nan=1e9))
            lower = nb < low - 1e-3
            low = np.where(lower, nb, low)
            nx_ = np.where(lower, dx, nx_)
            ny_ = np.where(lower, dy, ny_)
        n_wall = np.clip(np.ceil((Z - low) * ppm), 0, 400).astype(int)
        rep = np.repeat(np.arange(len(Z)), n_wall)
        frac = (np.arange(len(rep)) - np.repeat(np.cumsum(n_wall) - n_wall, n_wall) + 0.5) / np.repeat(n_wall, n_wall)
        WZ = Z[rep] - (Z[rep] - low[rep]) * frac
        WC = C[rep] * 0.75
        WC = np.where((WZ < 0)[:, None], ANTIFOULING, np.where((WZ < 0.9)[:, None], BOOT_TOP, WC))
        n = len(Z)
        self.x = np.concatenate([X, X[rep]]).astype(np.float32)
        self.y = np.concatenate([Y, Y[rep]]).astype(np.float32)
        self.z = np.concatenate([Z, WZ]).astype(np.float32)
        self.c = np.concatenate([C, WC]).astype(np.float32)
        self.n = np.concatenate([np.tile(np.float32([0, 0, 1]), (n, 1)),
                                 np.stack([nx_[rep], ny_[rep], np.zeros(len(rep))], 1)]).astype(np.float32)
        self.top = np.concatenate([np.ones(n, bool), np.zeros(len(rep), bool)])
        # normals come in a few kinds (deck up, walls facing +-x or +-y): shading looks a kind up, colours are
        # bytes, so the per-pixel gathers stay small. Points are grouped by kind, so the drawing can take only the
        # kinds facing the camera as slices: a wall is edge-on at rest and hidden under its top, and only shows
        # once a pitch or a roll tips it up
        self.normals, kind = np.unique(self.n, axis=0, return_inverse=True)
        o = np.argsort(kind.ravel(), kind="stable")
        self.x, self.y, self.z, self.c, self.n, self.top = (a[o] for a in (self.x, self.y, self.z, self.c, self.n,
                                                                             self.top))
        self.nkind = kind.ravel()[o].astype(np.int8)
        ends = np.searchsorted(self.nkind, np.arange(len(self.normals) + 1))
        self.kslice = [(int(ends[k]), int(ends[k + 1])) for k in range(len(self.normals))]
        self.c8 = np.clip(np.rint(self.c * 255), 0, 255).astype(np.uint8)
        sub = (yy % 2 == 0) & (xx % 2 == 0)                  # bottom at half the density
        self.bx, self.by, self.bz = X[sub].astype(np.float32), Y[sub].astype(np.float32), Zb[sub].astype(np.float32)
        self.lcf = hb["hydrostatics"]["lcf"]
        self.ppm = ppm
        # every third point, contiguous: the sim's waterline cut, collar and footprint use only these
        self.xs, self.ys, self.zs = self.x[::3].copy(), self.y[::3].copy(), self.z[::3].copy()
        self.tops = self.top[::3].copy()


def transform(x, y, z, pose, lcf, heading, n=None):
    """sinking.Points.frame's attitude: roll (starboard down for phi > 0), then pitch (bow down for theta > 0)
    about the lcf, then sink; then the heading on screen. Returns screen-aligned world metres (y down)."""
    s, th, ph = pose
    cp, sp_ = math.cos(ph), math.sin(ph)
    ct, st = math.cos(th), math.sin(th)
    ch, sh = math.cos(math.radians(heading)), math.sin(math.radians(heading))
    y1 = y * cp + z * sp_
    z1 = z * cp - y * sp_
    x0 = x - lcf
    x2 = x0 * ct + z1 * st + lcf
    Z = z1 * ct - x0 * st - s
    X, Y = x2 * ch - y1 * sh, x2 * sh + y1 * ch
    if n is None:
        return X, Y, Z
    ny1 = n[:, 1] * cp + n[:, 2] * sp_
    nz1 = n[:, 2] * cp - n[:, 1] * sp_
    nx2 = n[:, 0] * ct + nz1 * st
    nz2 = nz1 * ct - n[:, 0] * st
    return X, Y, Z, np.stack([nx2 * ch - ny1 * sh, nx2 * sh + ny1 * ch, nz2], 1)


def rotate_normals(n, pose, heading):
    """transform()'s rotation alone, for normals."""
    _, th, ph = pose
    cp, sp_ = math.cos(ph), math.sin(ph)
    ct, st = math.cos(th), math.sin(th)
    ch, sh = math.cos(math.radians(heading)), math.sin(math.radians(heading))
    ny1 = n[:, 1] * cp + n[:, 2] * sp_
    nz1 = n[:, 2] * cp - n[:, 1] * sp_
    nx2 = n[:, 0] * ct + nz1 * st
    nz2 = nz1 * ct - n[:, 0] * st
    return np.stack([nx2 * ch - ny1 * sh, nx2 * sh + ny1 * ch, nz2], 1)


# ---------------------------------------------------------------- the scene
class SinkScene:
    def __init__(self, src: Path, W, H, fps, heading, end, seed):
        import json
        self.src, self.W, self.H, self.fps, self.heading = src, W, H, fps, heading
        self.rng = np.random.default_rng(seed)
        self.sprite = json.loads((src / "sprite.json").read_text())
        self.hb = json.loads((src / "hitboxes.json").read_text())
        self.report = json.loads((src / "report.json").read_text())
        if "hydrostatics" not in self.hb:
            raise SystemExit(f"{src}: no hydrostatics in hitboxes.json; re-export with design.py")
        res = self.report["results"]
        self.L, self.B = res["length_m"], res["beam_m"]
        ch, sh = abs(math.cos(math.radians(heading))), abs(math.sin(math.radians(heading)))
        S0 = self.sprite["scale_px_per_m"]
        self.s = s = min(S0, 0.72 * W / (self.L * ch + self.B * sh), 0.55 * H / (self.L * sh + self.B * ch))
        self.C = np.array([W / 2, H / 2], np.float32)    # float32: a float64 centre promoted every to_px
        t0 = time.perf_counter()
        self.tl = Timeline(self.hb, end)
        self.ship = Ship3D(src, self.hb, self.sprite, 2 * s)
        self.setup_s = time.perf_counter() - t0
        self.water = V.Water(self.rng, W, H, s, self.C)
        self.dens = V.Density(W, H)
        self.fb = self.hb["vertical"]["freeboard"]

        # foam canvas (world = screen, the ship is stopped), and the lace textures, anchored to the water
        self.fresh = np.zeros((H, W), np.float32)
        self.resid = np.zeros((H, W), np.float32)
        feat = max(0.6, 2.5 / s)
        self.tiles = []
        for lu, lv in ((2.3, 2.0), (3.5, 3.0)):
            pair = []
            for _ in range(2):
                pair.append(self._tile_sample(self._tile(lu, lv), 4 / feat))
            self.tiles.append(pair)
        self.noise_f = uniform_noise(self.rng, W, H, 1.2 * s)
        self.noise_w = uniform_noise(self.rng, W, H, 0.9 * s)

        # cells: sample points per cell for the submerged fraction, and a vent over each (the main deck above it,
        # or its own top if higher: a hold breathes up its trunks to the weather deck)
        f = self.tl.flood
        g = np.linspace(0.15, 0.85, 3)
        a, b, c = np.meshgrid(g, g, g, indexing="ij")
        a, b, c = a.ravel(), b.ravel(), c.ravel()
        self.cx = (f.x0[:, None] + (f.x1 - f.x0)[:, None] * a).ravel().astype(np.float32)
        self.cy = (f.y0[:, None] + (f.y1 - f.y0)[:, None] * b).ravel().astype(np.float32)
        self.cz = (f.base[:, None] + (f.top - f.base)[:, None] * c).ravel().astype(np.float32)
        self.ncell = len(f.cap)
        self.cell_of = np.repeat(np.arange(self.ncell), len(a))
        self.cap = f.cap
        self.vent = np.stack([f.xc, f.yc, np.maximum(f.top, self.fb)], 1).astype(np.float32)
        self.released = np.zeros(self.ncell)
        self.held = np.zeros(self.ncell)
        self.acc = np.zeros(self.ncell)
        self.trapped = 0.0
        self.p_hold, self.p_trap = 0.5, 0.35

        bi = [f.ids.index(c) for c in self.tl.breach if c in f.ids]
        self.breach_pt = np.array([f.xc[bi].mean(), self.B / 2 * 0.95, -3.0], np.float32)
        self.funnels = []
        for comp in self.hb["components"]:
            if comp["kind"] == "funnel":
                p = np.array(comp["points"])
                area = 0.5 * abs(np.dot(p[:, 0], np.roll(p[:, 1], 1)) - np.dot(p[:, 1], np.roll(p[:, 0], 1)))
                self.funnels.append([p.mean(axis=0), math.sqrt(max(area, 1.0) / math.pi),
                                     comp["top"] + self.fb, False])
        fuel = float(self.report["results"].get("fuel_t", 0.05 * self.hb["hydrostatics"]["displacement_t"]))
        self.fuel_m3 = fuel / 0.95
        # m3/s from the torn tanks: the reference's 0.03-0.3, kept low, as a slick that swamps the frame hides
        # the foam (its own first try did that too)
        self.leak_rate = 0.06 * min(1.0, fuel / 6000)

        self.boils, self.rings, self.puddles = [], [], []
        self.debris = np.zeros((0, 2), np.float32)
        self.debris_c = np.zeros(0, int)
        self.smoke = V.Particles(WIND, 1.2)
        self.steam = V.Particles(WIND, 1.0)
        self.spray = V.Particles((0, 0), 0.8)
        self.t = 0.0
        self.t_gone = None
        self.last_xy, self.last_area = np.zeros(2), 0.0
        self.hit_done = False
        self.duration = None
        self.Zprev = None
        self.zcell_prev = None
        self.Zsprev, self.Bprev = self._sim_pts(0.0)[:2]
        self.fbox = None          # the box the foam canvases have been written in (it only grows)
        self.hud = self._hud()
        hb_ = nonzero_box(self.hud[..., 3] > 0)
        self.hud_box = (hb_[1], hb_[0], self.hud[hb_[1]:hb_[3], hb_[0]:hb_[2]].astype(np.float32) / 255)

    # ----- setup helpers
    def _tile(self, lu, lv, n=512):
        f = np.fft.fftfreq(n)
        fu, fv = np.meshgrid(f, f)
        out = 0
        for oct_, amp in ((1, 1.0), (2.5, 0.45)):
            spec = np.fft.fft2(self.rng.standard_normal((n, n))) * np.exp(
                -((fu * lu * oct_) ** 2 + (fv * lv * oct_) ** 2) * 2 * math.pi ** 2)
            fld = np.real(np.fft.ifft2(spec))
            out = out + amp * fld / fld.std()
        return (out / out.std()).astype(np.float32)

    def _tile_sample(self, tile, k):
        """The tile over the frame (world metres, bilinear): the camera is fixed, so it's sampled once."""
        n = tile.shape[0]
        u, v = np.meshgrid(np.arange(self.W, dtype=np.float32) + 0.5, np.arange(self.H, dtype=np.float32) + 0.5)
        fu, fv = (u - self.C[0]) / self.s * k, (v - self.C[1]) / self.s * k
        iu, iv = np.floor(fu), np.floor(fv)
        wu, wv = fu - iu, fv - iv
        iu, iv = iu.astype(np.int32) % n, iv.astype(np.int32) % n
        ju, jv = (iu + 1) % n, (iv + 1) % n
        return ((tile[iv, iu] * (1 - wu) + tile[iv, ju] * wu) * (1 - wv)
                + (tile[jv, iu] * (1 - wu) + tile[jv, ju] * wu) * wv).astype(np.float32)

    def tex(self, i, t, win=np.s_[:, :], ridged=True):
        """vidgen's foam texture: two tiles crossfaded over 14 s (stays unit gaussian), mapped to uniform 0..1,
        ridged = high along the zero lines (lace)."""
        ph = 2 * math.pi * t / 14.0
        g = self.tiles[i][0][win] * math.cos(ph) + self.tiles[i][1][win] * math.sin(ph)
        th = np.tanh(0.7978845 * (g + 0.044715 * g * g * g))
        return 1 - np.abs(th) if ridged else 0.5 + 0.5 * th

    def _hud(self):
        im = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        res = self.report["results"]
        big, small = V.font(max(14, self.H // 30)), V.font(max(11, self.H // 50))
        x, y = self.H // 36, self.H - self.H // 36
        name = self.sprite.get("name", self.sprite["id"])
        stats = (f"{res['length_m']:.0f} m  ·  {res['standard_displacement_t']:,} t std  ·  "
                 f"breached {'aft' if self.tl.end == 'stern' else 'forward'}, sinks {self.tl.fate.replace('plunges', 'by the ' + ('stern' if self.tl.sign < 0 else 'bow'))}")
        d.text((x + 1, y - big.size - small.size - 5), name, font=big, fill=(0, 0, 0, 140))
        d.text((x, y - big.size - small.size - 6), name, font=big, fill=(240, 244, 246, 235))
        d.text((x, y - small.size), stats, font=small, fill=(220, 228, 232, 210))
        self.font_small = small
        return np.asarray(im)

    # ----- geometry per frame
    def to_px(self, X, Y):
        return X * self.s + self.C[0], Y * self.s + self.C[1]

    def world_pt(self, p, t):
        X, Y, Z = transform(np.float32([p[0]]), np.float32([p[1]]), np.float32([p[2]]), self.tl.pose(t),
                            self.ship.lcf, self.heading)
        return float(X[0]), float(Y[0]), float(Z[0])

    def _sim_pts(self, t):
        """What the step needs: the every-third-point subset and the bottom, and the pose. The sim works on the
        subset only (each point counting three): the foam it feeds is blurred over a few pixels anyway, and memory
        traffic, not arithmetic, is what limits drawing in many processes at once."""
        sh, pose = self.ship, self.tl.pose(t)
        Xs, Ys, Zs = transform(sh.xs, sh.ys, sh.zs, pose, sh.lcf, self.heading)
        BX, BY, BZ = transform(sh.bx, sh.by, sh.bz, pose, sh.lcf, self.heading)
        return Zs, BZ, Xs, Ys, BX, BY, pose

    def splat(self, X, Y, w, roi, f=1):
        """Sum w into the frame pixels of window roi = (x0, y0, x1, y1), in cells of f x f pixels."""
        x0, y0, x1, y1 = roi
        px, py = self.to_px(X, Y)
        ix, iy = (np.floor(px).astype(np.int32) - x0) // f, (np.floor(py).astype(np.int32) - y0) // f
        w_, h_ = (x1 - x0) // f, (y1 - y0) // f
        ok = (ix >= 0) & (ix < w_) & (iy >= 0) & (iy < h_)
        return np.bincount(iy[ok] * w_ + ix[ok], weights=w[ok], minlength=w_ * h_).reshape(h_, w_).astype(np.float32)

    # ----- simulation step
    def step(self, dt):
        t = self.t + dt
        Zs, BZ, Xs, Ys, BX, BY, pose = self._sim_pts(t)
        s = self.s
        rng = self.rng
        # 1. crossing foam: surface passing down through z = 0 (water pouring over the deck and edge), up (cascade).
        # Only the points that changed side are worked on; each subset point stands for three
        dens = (s / self.ship.ppm) ** 2
        cz = np.flatnonzero((self.Zsprev > 0) != (Zs > 0))
        zp = self.Zsprev[cz]
        v = (Zs[cz] - zp) / dt
        down = zp > 0
        w = 3 * np.where(down, 0.25 + 0.75 * smooth(-v, 0.03, 0.8), 0.55 * smooth(v, 0.05, 1.0)).astype(np.float32)
        X, Y = Xs[cz], Ys[cz]
        bc = np.flatnonzero((self.Bprev > 0) != (BZ > 0))
        bv = (BZ[bc] - self.Bprev[bc]) / dt
        bw = 4.0 * np.where(self.Bprev[bc] > 0, 0.25 + 0.75 * smooth(-bv, 0.03, 0.8), 0.55 * smooth(bv, 0.05, 1.0))
        vzs = (Zs - self.Zsprev) / dt
        # the foam source is worked out in a window round the ship's footprint, not the whole frame
        px, py = self.to_px(Xs, Ys)
        pad = int(5 * s) + 8
        roi = (max(0, int(px.min()) - pad), max(0, int(py.min()) - pad),
               min(self.W, int(px.max()) + pad), min(self.H, int(py.max()) + pad))
        zmax = float(Zs.max())
        roi = (roi[0], roi[1], roi[0] + (roi[2] - roi[0]) // 4 * 4, roi[1] + (roi[3] - roi[1]) // 4 * 4)
        if roi[2] > roi[0] and roi[3] > roi[1] and zmax > -2:
            rw, rh = roi[2] - roi[0], roi[3] - roi[1]
            # the crossing line is thin: full resolution, blurred only over the box it covers
            src = np.minimum((self.splat(X, Y, w, roi) + self.splat(BX[bc], BY[bc], bw.astype(np.float32), roi))
                             * dens * 3.0, 0.8)
            cb = nonzero_box(src > 0)
            if cb:
                g = int(2 * s) + 3
                cb = (max(0, cb[0] - g), max(0, cb[1] - g), min(rw, cb[2] + g), min(rh, cb[3] + g))
                c_ = np.s_[cb[1]:cb[3], cb[0]:cb[2]]
                src[c_] = gblur(src[c_], 0.5 * s)
            # 2. contact collar round the waterline cut: columns with hull both above and below the surface. It's
            # smooth (1.3 m wide), so worked out at half resolution, the agitation at a quarter
            ab = self.splat(Xs, Ys, (Zs > 0).astype(np.float32), roi, 2)
            be = self.splat(Xs, Ys, (Zs < 0).astype(np.float32), roi, 2) + self.splat(BX, BY, (BZ < 0).astype(np.float32), roi, 2)
            Wc = ((ab > 0) & (be > 0)).astype(np.float32)
            Wc = (box_blur(Wc, 1, passes=1) > 0.3).astype(np.float32)    # close sampling pinholes
            if Wc.any():
                near = np.abs(Zs) < 1.5
                agit = self.splat(Xs[near], Ys[near], np.abs(vzs[near]), roi, 4)
                cnt = self.splat(Xs[near], Ys[near], np.ones(int(near.sum()), np.float32), roi, 4)
                agit = gblur(agit / np.maximum(cnt, 1), 0.5 * s) / np.maximum(gblur((cnt > 0).astype(np.float32), 0.5 * s), 0.05)
                agit = upscale(agit, rw // 2, rh // 2)
                ring = np.clip(2.0 * gblur(Wc, 0.45 * s), 0, 1) * (1 - Wc) * (0.18 + 0.82 * smooth(agit, 0.05, 1.2))
                src += upscale(gblur(ring, 0.25 * s), rw, rh)
            src = np.clip(src, 0, 1)
        else:
            src = None
        # the canvases only change inside the box foam has been written in, so they're updated there alone
        if src is not None:
            g = 8                                     # room for the residual's slow spreading
            r_ = (max(0, roi[0] - g), max(0, roi[1] - g), min(self.W, roi[2] + g), min(self.H, roi[3] + g))
            fb = self.fbox
            self.fbox = r_ if fb is None else (min(fb[0], r_[0]), min(fb[1], r_[1]), max(fb[2], r_[2]), max(fb[3], r_[3]))
        if self.fbox is not None:
            b_ = np.s_[self.fbox[1]:self.fbox[3], self.fbox[0]:self.fbox[2]]
            df, dr = math.exp(-dt / TAU_FRESH), math.exp(-dt / TAU_RESID)
            fr, re = self.fresh[b_], self.resid[b_]
            re *= dr
            re += fr * (0.5 * (1 - df))
            fr *= df
            if src is not None:
                x0, y0, x1, y1 = roi
                np.maximum(self.fresh[y0:y1, x0:x1], src, out=self.fresh[y0:y1, x0:x1])
            if int(round(t * self.fps)) % 10 == 0:
                self.resid[b_] = gblur(self.resid[b_], 0.35 * s)
        # debris off the deck as it goes under
        dd = np.flatnonzero(down & self.ship.tops[cz])
        if len(dd):
            pick = dd[rng.random(len(dd)) < 0.0018]
            self._add_debris(np.stack([X[pick], Y[pick]], 1))

        # 3. air: water in = air out, per cell; boils once the vent's under
        CX, CY, CZ = transform(self.cx, self.cy, self.cz, pose, self.ship.lcf, self.heading)
        f_geo = np.bincount(self.cell_of, weights=(CZ < 0).astype(float), minlength=self.ncell) / 27
        if self.zcell_prev is None:
            self.released = np.maximum(f_geo, self.tl.fill(0.0))
        self.zcell_prev = True
        f_new = np.maximum(self.released, np.maximum(f_geo, self.tl.fill(t)))
        dV = (f_new - self.released) * self.cap
        self.released = f_new
        VX, VY, VZ = transform(self.vent[:, 0], self.vent[:, 1], self.vent[:, 2], pose, self.ship.lcf, self.heading)
        for c in np.nonzero((dV > 0) | (self.held > 0.5))[0]:
            if VZ[c] >= 0:                 # vent above water: the air goes up the trunks, some is held below
                self.held[c] += self.p_hold * dV[c]
                continue
            rel = dV[c] + self.held[c] * min(1.0, dt / 3.0)
            self.held[c] -= self.held[c] * min(1.0, dt / 3.0)
            self.trapped += self.p_trap * rel
            self.acc[c] += (1 - self.p_trap) * rel
            q = max(15.0, self.cap[c] / 25)
            while self.acc[c] > q:
                Vr = q * rng.uniform(0.6, 1.4)
                self.acc[c] -= Vr
                depth = -float(VZ[c])
                jx, jy = rng.normal(0, 0.25 * self.B, 2)
                self._boil(dict(t=t + depth / 2.0, x=VX[c] + jx, y=VY[c] + jy,
                                       S=0.9 * Vr ** (1 / 3) + 0.10 * depth, I=float(np.clip(1.15 - 0.008 * depth, 0.35, 1))))
        # the hit
        if not self.hit_done and t >= HIT_S:
            self.hit_done = True
            hx, hy, _ = self.world_pt(self.breach_pt, t)
            self._boil(dict(t=t, x=hx, y=hy, S=0.05 * self.L, I=1.0))
            self.rings.append(dict(t=t, x=hx, y=hy, A=0.6))
            n = 70
            a = rng.uniform(0, 2 * math.pi, n)
            sp = rng.uniform(2, 14, n)
            self.spray.add(x=hx + rng.normal(0, 2, n), y=hy + rng.normal(0, 2, n), vx=np.cos(a) * sp,
                           vy=np.sin(a) * sp, life=rng.uniform(1.5, 3.5, n), r0=2.0, r1=rng.uniform(4, 9, n), a0=0.55)
        # gone? the slam, the ring, the tanks
        if self.t_gone is None and t > HIT_S:
            if zmax > 0:
                above = Zs > 0
                if above.any():          # the subset is every third point
                    self.last_area = 3 * float(above.sum()) / self.ship.ppm ** 2 * 0.5
                    self.last_xy = np.array([Xs[above].mean(), Ys[above].mean()])
            else:
                self.t_gone = t
                cx, cy = self.last_xy
                S_ = 3.0 + 0.9 * math.sqrt(max(self.last_area, 1.0))
                self._boil(dict(t=t + 0.3, x=cx, y=cy, S=S_, I=1.0))
                self.rings.append(dict(t=t, x=cx, y=cy, A=0.6 + 0.02 * S_))
                for k in range(8):     # the tanks give way one by one, over a stretch of the wreck
                    jx, jy = rng.normal(0, [0.12 * self.L, 0.4 * self.B])
                    self.puddles.append((t + 2.0 + 1.5 * k, cx + jx, cy + jy, 0.004 * self.fuel_m3 / 8))
                r = rng.random((25, 2)) - 0.5
                self._add_debris(np.stack([cx + r[:, 0] * 0.3 * self.L, cy + r[:, 1] * 0.15 * self.L], 1))
        # trapped air burps: slowly while afloat (bulkheads failing), faster once under, from the wreck's top
        rate = 1 / 40.0 if self.t_gone is None else 1 / 14.0
        if self.trapped > 1 and rng.random() < dt * 3.0:
            top = int(np.argmax(Zs))
            depth = max(-float(Zs[top]), 0.0)
            tx, ty = Xs[top:top + 1], Ys[top:top + 1]
            if 2.0 < depth < 200:
                Vr = self.trapped * rate / 3.0 * rng.uniform(0.3, 1.7)
                if rng.random() < 0.04:            # a bulkhead lets go
                    Vr = 0.15 * self.trapped
                self.trapped -= Vr
                jx, jy = rng.normal(0, 0.15 * self.B + 0.05 * depth, 2)
                self._boil(dict(t=t + depth / 2.0, x=float(tx[0]) + jx, y=float(ty[0]) + jy,
                                       S=0.9 * Vr ** (1 / 3) + 0.10 * depth, I=float(np.clip(1.1 - 0.006 * depth, 0.3, 1))))
        # 5. oil from the torn tanks, once a second, rising from the breach
        if self.hit_done and self.t_gone is None and int(round(t * self.fps)) % self.fps == 0:
            lx, ly, lz = self.world_pt(self.breach_pt, t)
            for _ in range(3):         # oil comes up in several places, so the puddles merge into a slick
                jx, jy = rng.normal(0, 0.35 * self.B, 2)
                self.puddles.append((t + max(-lz, 0) / 1.0 + rng.uniform(0, 1), lx + jx, ly + jy, self.leak_rate / 3))
        # 6. debris: drift plus the boils' outflow
        if len(self.debris):
            v = np.tile(DRIFT.astype(np.float32), (len(self.debris), 1))
            for b in self.boils:
                a = t - b["t"]
                if a < 0 or a > 12:
                    continue
                d = self.debris - np.float32([b["x"], b["y"]])
                r = np.linalg.norm(d, axis=1) + 1e-6
                R = b["S"] * (0.5 + 1.5 * (1 - math.exp(-a / 1.5)))
                sp = 2.0 * b["I"] * math.exp(-a / 3.0) * (r / R) * np.exp(-(r / R) ** 2)
                v += d / r[:, None] * sp[:, None]
            self.debris = self.debris + v * dt
        # funnels: smoke while they're out, a steam burst as cold water reaches the boilers
        for fn in self.funnels:
            c, r, top, quenched = fn
            fx, fy, fz = self.world_pt((c[0], c[1], top), t)
            if fz > 1.0:
                n = int(rng.poisson(dt * (6 + 1.5 * r)))
                if n:
                    self.smoke.add(x=fx + rng.normal(0, r * 0.25, n), y=fy + rng.normal(0, r * 0.25, n),
                                   vx=rng.normal(0, 0.6, n), vy=rng.normal(0, 0.6, n), life=rng.uniform(5, 9, n),
                                   r0=r * 0.6, r1=r * 1.6 + 3, a0=rng.uniform(0.12, 0.22, n), h=fz)
            elif not quenched:
                fn[3] = True
                n = 90             # puffs thrown out of the funnel and the vents round it, not one ball
                a = rng.uniform(0, 2 * math.pi, n)
                sp = rng.uniform(2, 12, n)
                self.steam.add(x=fx + rng.normal(0, 2 * r, n), y=fy + rng.normal(0, 2 * r, n), vx=np.cos(a) * sp,
                               vy=np.sin(a) * sp, life=rng.uniform(2, 4.5, n), r0=0.3 * r,
                               r1=rng.uniform(0.6, 1.4, n) * r, a0=rng.uniform(0.12, 0.25, n), h=4.0)
        for ps in (self.smoke, self.steam, self.spray):
            ps.step(dt)
        self.boils = [b for b in self.boils if t - b["t"] <= 21 * math.sqrt(b["S"] / 4)]   # 6 lifetimes
        self.Zsprev, self.Bprev = Zs, BZ
        self.t = t

    # the state a frame is drawn from: the sim steps in one process, frames are drawn in a pool of workers that
    # each hold the same scene (built from the same seed). Copies, as the step changes the foam arrays in place
    # and the pool pickles a snapshot later, on its own thread.
    SNAP = ("t", "t_gone", "boils", "rings", "puddles", "debris", "debris_c", "fbox")

    def snapshot(self, fresh=None, resid=None):
        """The frame's state. With fresh and resid (shared-memory arrays), the foam canvases are copied there and
        left out: pickling 7 MB a frame held the GIL long enough to halve the stepping process's speed."""
        d = {k: getattr(self, k) for k in self.SNAP}
        d["rings"], d["puddles"] = list(self.rings), list(self.puddles)
        if fresh is None:
            d["fresh"], d["resid"] = self.fresh.copy(), self.resid.copy()
        elif self.fbox is not None:       # the box only grows, so a slot is zero outside it
            b_ = np.s_[self.fbox[1]:self.fbox[3], self.fbox[0]:self.fbox[2]]
            fresh[b_], resid[b_] = self.fresh[b_], self.resid[b_]
        for name in ("smoke", "steam", "spray"):
            d[name] = {k: v.copy() for k, v in getattr(self, name).d.items()}
        return d

    def load(self, d, fresh=None, resid=None):
        for k in self.SNAP:
            setattr(self, k, d[k])
        self.fresh, self.resid = (d["fresh"], d["resid"]) if fresh is None else (fresh, resid)
        for name in ("smoke", "steam", "spray"):
            getattr(self, name).d = d[name]

    def _boil(self, b):
        b["k"], b["ph"] = int(self.rng.integers(11, 19)), float(self.rng.random() * 6.283)
        self.boils.append(b)

    def _add_debris(self, p):
        self.debris = np.concatenate([self.debris, p.astype(np.float32)])
        self.debris_c = np.concatenate([self.debris_c, self.rng.integers(0, len(DEBRIS), len(p))])

    # ----- analytic layers
    def boil_fields(self, t):
        """(foam density, churn, eta) of the boils active at t (sinking_foam.md 2.3), on the half-resolution grid
        (they're smooth; the lace's detail comes from the noise), plus the box they cover there, or None."""
        H, W, s = self.H // 2, self.W // 2, self.s / 2
        dens = np.zeros((H, W), np.float32)
        churn_f = np.zeros((H, W), np.float32)
        eta = np.zeros((H, W), np.float32)
        box = [W, H, 0, 0]
        for b in self.boils:
            a = t - b["t"]
            if a < 0:
                continue
            ts, tb = 1.5 * math.sqrt(b["S"] / 4), 3.5 * math.sqrt(b["S"] / 4)
            R = b["S"] * (0.5 + 1.5 * (1 - math.exp(-a / ts)))
            cx, cy = self.to_px(b["x"], b["y"])
            cx, cy = cx / 2, cy / 2
            rr = 2.4 * R * s
            i0, i1 = max(0, int(cx - rr)), min(W, int(cx + rr) + 1)
            j0, j1 = max(0, int(cy - rr)), min(H, int(cy + rr) + 1)
            if i1 <= i0 or j1 <= j0:
                continue
            box = [min(box[0], i0), min(box[1], j0), max(box[2], i1), max(box[3], j1)]
            dx = (np.arange(i0, i1, dtype=np.float32) + 0.5 - cx)[None, :] / s
            dy = (np.arange(j0, j1, dtype=np.float32) + 0.5 - cy)[:, None] / s
            q = np.hypot(dx, dy) / R
            ang = np.arctan2(dy, dx)
            q = q * (1 + 0.12 * np.sin(3 * ang + b["S"]) + 0.08 * np.sin(5 * ang + 2 * b["x"]))
            I = b["I"] * math.exp(-a / tb)
            streak = 0.75 + 0.25 * np.cos(b["k"] * ang + b["ph"] + 3.0 * q)
            churn = 0.75 * smooth(1 - q, 0.0, 0.6) * math.exp(-a / (0.6 * tb))
            rim = np.exp(-((q - 0.95) / 0.20) ** 2) * streak
            tail = 0.25 * b["I"] * math.exp(-a / (5 * tb)) * smooth(1.15 - q, 0, 0.35) * smooth(q, 0.2, 0.9) * streak
            new = I * (churn + rim) + tail
            cur = dens[j0:j1, i0:i1]
            dens[j0:j1, i0:i1] = np.maximum(cur, new) + 0.35 * np.minimum(cur, new)
            np.maximum(churn_f[j0:j1, i0:i1], I * churn / 0.75, out=churn_f[j0:j1, i0:i1])
            eta[j0:j1, i0:i1] += 0.08 * b["S"] * I * np.exp(-2.5 * q * q)
        return np.clip(dens, 0, 1.2), churn_f, eta, (box if box[2] > box[0] else None)

    def ring_eta(self, t, eta):
        """Adds the ring waves to the half-resolution eta, inside each ring's live annulus."""
        H, W, s = eta.shape[0], eta.shape[1], self.s / 2
        for r in self.rings:
            a = t - r["t"]
            if not 0 <= a <= 40:
                continue
            cx, cy = self.to_px(r["x"], r["y"])
            cx, cy = cx / 2, cy / 2
            R, wd = 5.0 * a, 6 + 0.6 * a
            rr = (R + 3 * wd) * s
            i0, i1 = max(0, int(cx - rr)), min(W, int(cx + rr) + 1)
            j0, j1 = max(0, int(cy - rr)), min(H, int(cy + rr) + 1)
            if i1 <= i0 or j1 <= j0:
                continue
            dx = (np.arange(i0, i1, dtype=np.float32) + 0.5 - cx)[None, :]
            dy = (np.arange(j0, j1, dtype=np.float32) + 0.5 - cy)[:, None]
            d = np.hypot(dx, dy) / s
            env = np.exp(-((d - R) / wd) ** 2) * (r["A"] * math.exp(-a / 15) / math.sqrt(1 + R / 20))
            eta[j0:j1, i0:i1] += env * np.cos((d - R) / 3.0)
        return eta

    def oil_thickness(self, t):
        """Oil film thickness, m: Fay gravity-inertial puddles (x1.5 time, real slicks spread faster), drifting."""
        h = np.zeros((self.H, self.W), np.float32)
        D, s = 0.07, self.s
        box = [self.W, self.H, 0, 0]
        for (t0, x, y, Vol) in self.puddles:
            a = t - t0
            if a <= 0:
                continue
            ae = a * 1.5
            R = 1.14 * (D * V.G * Vol * ae * ae) ** 0.25 + 0.5
            cx, cy = self.to_px(x + DRIFT[0] * a, y + DRIFT[1] * a)
            rr = 3.2 * R * s
            i0, i1 = max(0, int(cx - rr)), min(self.W, int(cx + rr) + 1)
            j0, j1 = max(0, int(cy - rr)), min(self.H, int(cy + rr) + 1)
            if i1 <= i0 or j1 <= j0:
                continue
            dx = (np.arange(i0, i1, dtype=np.float32) + 0.5 - cx)[None, :] / s
            dy = (np.arange(j0, j1, dtype=np.float32) + 0.5 - cy)[:, None] / s
            d = np.hypot(dx, dy) / R * (1 + 0.8 * (self.noise_w[j0:j1, i0:i1] - 0.5))
            box = [min(box[0], i0), min(box[1], j0), max(box[2], i1), max(box[3], j1)]
            core = Vol / (math.pi * R * R) * smooth(1.25 - d, 0, 0.7)
            halo = 1.5e-6 * smooth(2.2 - d, 0, 1.0)
            h[j0:j1, i0:i1] += core + halo
        return h, (box if box[2] > box[0] else None)

    def oil_colour(self, img, h, o):
        """Bonn Agreement codes (um): sheen .04-.3, rainbow .3-5, metallic 5-50, true colour 50-200 / > 200."""
        lg = np.log10(np.maximum(h * 1e6, 1e-4))
        sheen = smooth(lg, math.log10(0.04), math.log10(0.3)) * (1 - smooth(lg, 0.0, math.log10(5)))
        out = img + 0.07 * sheen[..., None]
        rb = smooth(lg, math.log10(0.3), 0.0) * (1 - smooth(lg, math.log10(3), math.log10(8)))
        ph = 2 * math.pi * (1.3 * lg + 0.6 * self.noise_w[o])
        rain = 0.5 + 0.5 * np.stack([np.cos(ph), np.cos(ph - 2.1), np.cos(ph + 2.1)], -1)
        out = out * (1 - 0.15 * rb[..., None]) + (0.15 * rb)[..., None] * (0.25 + 0.5 * rain)
        met = smooth(lg, math.log10(5), math.log10(30)) * (1 - smooth(lg, math.log10(60), math.log10(200)))
        out = out * (1 - 0.35 * met[..., None]) + 0.35 * met[..., None] * np.float32([0.20, 0.17, 0.24])
        true = smooth(lg + 0.6 * (self.noise_f[o] - 0.5), math.log10(50), math.log10(2000))
        return out * (1 - 0.45 * true[..., None]) + 0.45 * true[..., None] * np.float32([0.06, 0.055, 0.05])

    # ----- the hull, z-buffered at 2x with a sun shadow map
    def hull_layers(self, t):
        """Returns (x0, y0, sub_pm, sub_a, sh, top_pm, top_a) on a 1x frame window: the submerged hull
        (premultiplied, faded with depth), the shadow on the surface, the hull above water (premultiplied).
        Works on flat pixel indices: the z-buffer and the shadow map are max-reductions (np.maximum.at, far
        cheaper than sorting the points by height), and only the ship's own pixels are shaded, then summed 2x2
        into the 1x window by bincount."""
        sh = self.ship
        pose = self.tl.pose(t)
        # the kinds facing the camera (tops always), as one index array into the grouped points
        nz = rotate_normals(sh.normals, pose, self.heading)[:, 2]
        segs = [sh.kslice[k] for k in range(len(sh.normals)) if nz[k] > 0.05]
        sel = np.concatenate([np.arange(a, b, dtype=np.int32) for a, b in segs])
        X, Y, Z = transform(sh.x[sel], sh.y[sel], sh.z[sel], pose, sh.lcf, self.heading)
        keep = np.flatnonzero(Z > -CULL_M)
        if not len(keep):
            return None
        keep = sel[keep]                            # indices into the ship's points
        X, Y, Z = X[Z > -CULL_M], Y[Z > -CULL_M], Z[Z > -CULL_M]
        # shadow casters: every third point, walls and all (a column's walls carry its shadow down to the deck),
        # above water, into a 1x shadow map
        CX, CY, CZ = transform(sh.xs, sh.ys, sh.zs, pose, sh.lcf, self.heading)
        up = CZ > 0
        CX, CY, CZ = CX[up], CY[up], CZ[up]
        s2 = 2 * self.s
        px, py = (X * self.s + self.C[0]) * 2, (Y * self.s + self.C[1]) * 2
        cgx = (CX * self.s + self.C[0] - CZ * (self.s / TAN_E) * SUN[0]) * 2
        cgy = (CY * self.s + self.C[1] - CZ * (self.s / TAN_E) * SUN[1]) * 2
        lo_x, hi_x = float(px.min()), float(px.max())
        lo_y, hi_y = float(py.min()), float(py.max())
        if len(CZ):
            lo_x, hi_x = min(lo_x, float(cgx.min())), max(hi_x, float(cgx.max()))
            lo_y, hi_y = min(lo_y, float(cgy.min())), max(hi_y, float(cgy.max()))
        x0 = max(0, int(lo_x) - 4) & ~1
        y0 = max(0, int(lo_y) - 4) & ~1
        x1 = min(2 * self.W, int(hi_x) + 6) & ~1
        y1 = min(2 * self.H, int(hi_y) + 6) & ~1
        if x1 <= x0 or y1 <= y0:
            return None
        w2, h2 = x1 - x0, y1 - y0
        n2 = w2 * h2
        ix, iy = px.astype(np.int32) - x0, py.astype(np.int32) - y0
        ok = np.flatnonzero((ix >= 0) & (ix < w2) & (iy >= 0) & (iy < h2))
        pix = iy[ok] * w2 + ix[ok]
        zo = Z[ok]
        zb = np.full(n2, -np.inf, np.float32)
        np.maximum.at(zb, pix, zo)                  # the highest point at a pixel is the one seen
        win = zo == zb[pix]
        idx = np.full(n2, -1, np.int32)
        idx[pix[win]] = ok[win]
        idx, zb = idx.reshape(h2, w2), zb.reshape(h2, w2)
        # pinholes a rotation opens: an empty pixel with most neighbours filled takes its highest neighbour
        zp = np.pad(zb, 1, constant_values=-np.inf)
        ip = np.pad(idx, 1, constant_values=-1)
        nb = [(dy, dx) for dy in (0, 1, 2) for dx in (0, 1, 2) if (dy, dx) != (1, 1)]
        filled = ip >= 0
        count = sum(filled[dy:dy + h2, dx:dx + w2].view(np.int8) for dy, dx in nb)
        fy, fx = np.nonzero((idx < 0) & (count >= 5))
        best = np.full(len(fy), -np.inf, np.float32)
        bidx = np.full(len(fy), -1, np.int32)
        for dy, dx in nb:
            z = zp[fy + dy, fx + dx]
            take = z > best
            best = np.where(take, z, best)
            bidx = np.where(take, ip[fy + dy, fx + dx], bidx)
        idx[fy, fx] = bidx
        flat = idx.ravel()
        hp = np.flatnonzero(flat >= 0)              # the ship's pixels
        pi = flat[hp]
        tz = Z[pi]
        # sun shadow map at 1x: each caster at its ground projection away from the sun keeps the highest; dilated
        # a pixel (separably) to close pinholes
        w1, h1 = w2 // 2, h2 // 2
        smap = np.full(w1 * h1, -np.inf, np.float32)
        if len(CZ):
            jx, jy = (cgx - x0).astype(np.int32) // 2, (cgy - y0).astype(np.int32) // 2
            okc = (jx >= 0) & (jx < w1) & (jy >= 0) & (jy < h1)
            np.maximum.at(smap, jy[okc] * w1 + jx[okc], CZ[okc])
            smap = smap.reshape(h1, w1)
            m = smap.copy()
            np.maximum(m[:, 1:], smap[:, :-1], out=m[:, 1:])
            np.maximum(m[:, :-1], smap[:, 1:], out=m[:, :-1])
            smap = m.copy()
            np.maximum(smap[1:], m[:-1], out=smap[1:])
            np.maximum(smap[:-1], m[1:], out=smap[:-1])
            smap = smap.ravel()
        # receivers: the sea (and everything under it) at z = 0 looks up its own pixel; the hull above water
        # looks up its projection
        zr = np.maximum(tz, 0)
        hy_, hx_ = np.divmod(hp, w2)
        ru = (hx_ + 0.5 - zr * (s2 / TAN_E) * SUN[0]).astype(np.int32) // 2
        rv = (hy_ + 0.5 - zr * (s2 / TAN_E) * SUN[1]).astype(np.int32) // 2
        inb = (ru >= 0) & (ru < w1) & (rv >= 0) & (rv < h1)
        ship_sh = np.where(inb, smap[np.where(inb, rv * w1 + ru, 0)] > zr + 0.4, False)
        # the ship's pixels: lit above water (lambert on the rotated normal, a flat deck at rest stays as drawn,
        # wet near the sea), faded with depth below it
        orig = keep[pi]
        Ct = sh.c8[orig].astype(np.float32) * (1 / 255)
        lam = np.clip(rotate_normals(sh.normals, pose, self.heading) @ LIGHT, 0, 1)
        fac = np.clip(0.45 + 0.55 * lam / LIGHT[2], 0.35, 1.3).astype(np.float32)[sh.nkind[orig]]
        above = tz >= 0
        wet = 1 - 0.25 * smooth(1.2 - tz, 0, 1.2)
        vis = np.where(above, 0, 0.85 * np.exp(np.minimum(tz, 0) / 3.0)).astype(np.float32)
        # 2x2 sums into the 1x window
        q = (hy_ // 2) * w1 + hx_ // 2

        def acc(wt):
            return np.bincount(q, weights=wt, minlength=w1 * h1).reshape(h1, w1).astype(np.float32) * 0.25
        top_a = acc(above)
        litw = (fac * wet * above).astype(np.float32)
        top_pm = np.stack([acc(Ct[:, k] * litw) for k in range(3)], -1)
        if vis.any():
            sub_a = acc(vis)
            sub_pm = np.stack([acc((Ct[:, k] * 0.75 + 0.25 * V.WATER_LIT[k]) * vis) for k in range(3)], -1)
        else:
            sub_a, sub_pm = np.zeros((h1, w1), np.float32), np.zeros((h1, w1, 3), np.float32)
        cover = acc(np.ones(len(hp), np.float32))
        sh1 = (smap.reshape(h1, w1) > 0.4) * (1 - cover) + acc(ship_sh.astype(np.float32))
        sh1 = box_blur(sh1.astype(np.float32), 1, passes=1)
        top_pm *= (1 - SHADE * sh1)[..., None]
        return x0 // 2, y0 // 2, sub_pm, sub_a, sh1 * (1 - top_a), top_pm, top_a

    # ----- drawing
    def field(self, ps, offset=(0.0, 0.0)):
        if not len(ps):
            return np.zeros((self.dens.hh, self.dens.hw), np.float32)
        px, py = self.to_px(ps.d["x"], ps.d["y"])
        return self.dens.render(px + offset[0], py + offset[1], ps.radius() * self.s, ps.opacity())

    def render(self):
        t, W, H, s = self.t, self.W, self.H, self.s
        bd_h, churn_h, eta_h, bb = self.boil_fields(t)
        eta_h = self.ring_eta(t, eta_h)
        gy, gx = np.gradient(eta_h)
        hx, hy = gx * (s / 2), gy * (s / 2)          # half-res pixels are 2 / s metres
        lim = 0.3 / np.maximum(np.hypot(hx, hy), 0.3)
        oil, ob = self.oil_thickness(t)
        wake = None
        if ob:
            o = np.s_[ob[1]:ob[3], ob[0]:ob[2]]
            slick = np.zeros((H, W), np.float32)
            slick[o] = smooth(np.log10(np.maximum(oil[o], 1e-9)), -7.6, -6.6)
            oily_o = smooth(oil[o] * 1e6, 50, 600)
            wake = (0.0, 0.0, 0.85 * slick)
        frame = self.water.shade((0.0, 0.0), t, wake, half=(hx * lim, hy * lim))
        if ob:
            frame[o] = self.oil_colour(frame[o] * (1 - 0.10 * slick[o])[..., None], oil[o], o)

        hl = self.hull_layers(t)
        if hl is not None:
            x0, y0, sub_pm, sub_a, shw, top_pm, top_a = hl
            h_, w_ = sub_a.shape
            win = frame[y0:y0 + h_, x0:x0 + w_]
            h_, w_ = win.shape[:2]
            win *= 1 - sub_a[:h_, :w_, None]
            win += sub_pm[:h_, :w_]

        # foam, vidgen's lace: boils churn the water like the propulsor wash, the crossing and collar foam is the
        # wake's fresh foam, the residual its half-opacity residual. Worked out only over the box the foam covers.
        bd = np.zeros((H, W), np.float32)
        if bb:
            i0, j0, i1, j1 = bb
            fb = np.s_[2 * j0:2 * j1, 2 * i0:2 * i1]
            bd[fb] = upscale(bd_h[j0:j1, i0:i1], 2 * (i1 - i0), 2 * (j1 - j0))
            churn = upscale(churn_h[j0:j1, i0:i1], 2 * (i1 - i0), 2 * (j1 - j0))
            frame[fb] += (CHURN - frame[fb]) * np.clip(churn * 0.8, 0, 0.7)[..., None]
        box = nonzero_box(np.zeros((1, 1), bool), self.fbox)
        if bb:
            box = nonzero_box(np.zeros((1, 1), bool), (2 * bb[0], 2 * bb[1], 2 * bb[2], 2 * bb[3]) if box is None else
                              (min(box[0], 2 * bb[0]), min(box[1], 2 * bb[1]), max(box[2], 2 * bb[2]), max(box[3], 2 * bb[3])))
        if box:
            f = np.s_[box[1]:box[3], box[0]:box[2]]
            ta, tb = self.tex(0, t, f), self.tex(1, t, f)
            fm = np.maximum(np.maximum(lace(bd[f], tb, "wash"), lace(self.fresh[f], ta, "fresh")),
                            V.LACE_RESID * lace(np.clip(self.resid[f], 0, 1), tb, "resid"))
            if ob:
                oily = np.zeros((H, W), np.float32)
                oily[o] = oily_o
                oily = oily[f][..., None]
                fm *= 1 - 0.3 * oily[..., 0]
                foam_c = FOAM * (1 - oily) + np.float32([0.50, 0.41, 0.30]) * oily
            else:
                foam_c = FOAM
            frame[f] += (foam_c - frame[f]) * fm[..., None]
        if len(self.spray):
            sp = upscale(self.field(self.spray), W, H) * self.water.foam_noise
            frame += (FOAM - frame) * np.clip(1 - np.exp(-1.6 * sp), 0, 0.95)[..., None]

        # debris: small pale bits
        if len(self.debris):
            px, py = self.to_px(self.debris[:, 0], self.debris[:, 1])
            ix, iy = px.astype(int), py.astype(int)
            ok = (ix >= 0) & (ix < W - 2) & (iy >= 0) & (iy < H - 2)
            col = DEBRIS[self.debris_c[ok]]
            for ox, oy in ((0, 0), (1, 0), (0, 1)):
                frame[iy[ok] + oy, ix[ok] + ox] = col * (1.0 if ox == oy == 0 else 0.85)

        # shadow on the surface, then the hull above it
        if hl is not None:
            win = frame[y0:y0 + h_, x0:x0 + w_]
            win *= (1 - SHADE * shw[:h_, :w_])[..., None]
            win *= 1 - top_a[:h_, :w_, None]
            win += top_pm[:h_, :w_]

        # smoke and steam, with their shadows (vidgen's recipe)
        sd = SUN
        sh = np.zeros((self.dens.hh, self.dens.hw), np.float32)
        layers = []
        for ps, base, k in ((self.smoke, (0.36, 0.36, 0.37), 1.0), (self.steam, STEAM, 0.3)):
            if not len(ps):
                continue
            d = self.field(ps)
            h = float(np.mean(ps.d["h"]))
            o = (-SUN * (h + 4) / TAN_E * s)
            sh += k * self.field(ps, offset=(o[0], o[1]))
            layers.append((d, base, ps is self.smoke))
        if sh.any():
            frame *= (1 - 0.35 * np.clip(1 - np.exp(-upscale(sh, W, H)), 0, 1))[..., None]
        for d, base, lit in layers:          # steam unlit: lit, a thin puff showed a hard dark half
            hb_ = nonzero_box(d > 0.002)
            if not hb_:
                continue
            i0, j0, i1, j1 = hb_
            dd = d[j0:j1, i0:i1]
            f = np.s_[2 * j0:2 * j1, 2 * i0:2 * i1]
            ww, hh = 2 * (i1 - i0), 2 * (j1 - j0)
            col = np.float32(base)[None, None, :]
            if lit:
                gy_, gx_ = np.gradient(dd)
                col = col * upscale(np.clip(1.0 - 3.0 * (gx_ * sd[0] + gy_ * sd[1]), 0.55, 1.35), ww, hh)[..., None]
            al = np.clip(1 - np.exp(-1.4 * upscale(dd, ww, hh)), 0, 0.92)[..., None]
            frame[f] = frame[f] * (1 - al) + col * al

        out = (np.clip(frame, 0, 1) * 255).astype(np.uint8)
        hy0, hx0, hud = self.hud_box
        hh, hw = hud.shape[:2]
        ha = hud[..., 3:4]
        o_ = out[hy0:hy0 + hh, hx0:hx0 + hw]
        o_[:] = (o_ * (1 - ha) + hud[..., :3] * 255 * ha).astype(np.uint8)
        im = Image.fromarray(out)
        d = ImageDraw.Draw(im, "RGBA")
        d.text((H // 36, H // 36), self.phase(), font=self.font_small, fill=(235, 240, 242, 220))
        return np.asarray(im)

    def phase(self):
        t, tl = self.t, self.tl
        g = tl.game_time(t) / 60
        end = "stern" if tl.sign < 0 else "bow"
        if t < HIT_S:
            return "Afloat"
        if t < tl.t_f:
            th = math.degrees(tl.pose(t)[1])
            return (f"Flooding: {tl.weight(t):,.0f} t in, trim {abs(th):.1f}° by the {end}   "
                    f"T+{g:.0f} min (time compressed)")
        if self.t_gone is None:
            return f"Plunging by the {end}   T+{g:.0f} min"
        return f"Gone {t - self.t_gone:.0f} s ago: trapped air, oil, wreckage"


# ---------------------------------------------------------------- driver
_SC = None   # a drawing worker's scene and its view of the shared ring


class Ring:
    """Shared-memory slots, one per frame in flight: the foam canvases in, the drawn frame out."""

    def __init__(self, n, W, H, name=None):
        from multiprocessing import shared_memory
        self.n, self.W, self.H = n, W, H
        self.per = 2 * W * H * 4 + W * H * 3
        self.shm = shared_memory.SharedMemory(name=name, create=name is None, size=n * self.per)
        self.name = self.shm.name

    def slot(self, i):
        buf, o, W, H = self.shm.buf, i * self.per, self.W, self.H
        fresh = np.ndarray((H, W), np.float32, buf, o)
        resid = np.ndarray((H, W), np.float32, buf, o + W * H * 4)
        frame = np.ndarray((H, W, 3), np.uint8, buf, o + 2 * W * H * 4)
        return fresh, resid, frame


def _worker_init(ring_args, *a):
    global _SC
    _SC = SinkScene(*a)
    _SC.ring = Ring(*ring_args)


def _draw(snap, i):
    fresh, resid, frame = _SC.ring.slot(i)
    _SC.load(snap, fresh, resid)
    frame[:] = _SC.render()
    return i


def make(src: Path, end: str, out: Path, args, still=None, workers=1):
    """One clip. With workers > 1 the frames are drawn in a pool while this process steps the sim and encodes."""
    t0 = time.perf_counter()
    scene_args = (src, args.w, args.h, args.fps, args.heading, end, args.seed)
    sc = SinkScene(*scene_args)
    dur = args.seconds or (sc.tl.t_last + 4 + TAIL_S)
    if not args.quiet:
        print(f"  {src.name} {end}: {sc.tl.fate} at T+{sc.tl.game_f / 60:.0f} min; {len(sc.ship.x):,} points, "
              f"setup {sc.setup_s:.1f} s, {workers} drawing workers")
    dt = 1.0 / args.fps
    if still is not None:
        for _ in range(int(round(still * args.fps))):
            sc.step(dt)
        Image.fromarray(sc.render()).save(out)
        return out
    import collections
    import imageio_ffmpeg
    w = imageio_ffmpeg.write_frames(str(out), (args.w, args.h), fps=args.fps, codec="libx264",
                                    pix_fmt_out="yuv420p", macro_block_size=1,
                                    output_params=["-crf", str(args.crf), "-preset", "medium",
                                                   "-movflags", "+faststart"])
    w.send(None)
    n = int(round(dur * args.fps))
    pool = None
    if workers > 1:
        from concurrent.futures import ProcessPoolExecutor
        depth = 2 * workers                     # frames in flight; one ring slot each, plus one being refilled
        ring = Ring(depth + 1, args.w, args.h)
        pool = ProcessPoolExecutor(workers, initializer=_worker_init,
                                   initargs=((depth + 1, args.w, args.h, ring.name),) + scene_args)
    pending = collections.deque()

    def emit():
        k = pending.popleft().result()
        w.send(ring.slot(k)[2].tobytes())
    for i in range(n):
        if pool is None:
            w.send(np.ascontiguousarray(sc.render()).tobytes())
        else:
            while len(pending) >= depth or (pending and pending[0].done()):
                emit()
            k = i % (depth + 1)
            fresh, resid, _ = ring.slot(k)
            pending.append(pool.submit(_draw, sc.snapshot(fresh, resid), k))
        sc.step(dt)
        if i % args.fps == 0 and not args.quiet:
            print(f"\r  {out.name}: {i / args.fps:4.1f}/{dur:.1f} s", end="", flush=True)
    while pending:
        emit()
    if pool is not None:
        pool.shutdown()
        ring.shm.close()
        ring.shm.unlink()
    w.close()
    print(f"\r  {out.name}: {dur:.1f} s, {n} frames, {(time.perf_counter() - t0) / 60:.1f} min", flush=True)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ships", nargs="+", help="out_designs/<id> folders or ids")
    ap.add_argument("--end", choices=["stern", "bow", "both"], default="both", help="which end is breached")
    ap.add_argument("--designs", default=str(V.ROOT / "out_designs"))
    ap.add_argument("--out", default=str(V.ROOT / "vidgen" / "out"))
    ap.add_argument("--size", default="1280x720")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--seconds", type=float, default=None)
    ap.add_argument("--heading", type=float, default=-12.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--still", type=float, nargs="*", default=None, help="write PNGs at these times instead")
    ap.add_argument("--jobs", type=int, default=0, help="cores to use (default: all)")
    args = ap.parse_args()
    args.w, args.h = (int(v) for v in args.size.lower().split("x"))
    base = Path(args.designs)
    srcs = [Path(s) if (Path(s) / "sprite.json").exists() else base / s for s in args.ships]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ends = ["stern", "bow"] if args.end == "both" else [args.end]
    todo = []
    for src in srcs:
        for end in ends:
            if args.still is not None:
                for ts in args.still:
                    todo.append((src, end, out / f"{src.name}_sink_{end}_{ts:05.1f}.png", ts))
            else:
                todo.append((src, end, out / f"{src.name}_sink_{end}.mp4", None))
    cores = args.jobs or os.cpu_count() or 1
    if args.still is None:
        # videos: every clip at once, each stepping its sim in its own process (the step is sequential) and
        # sharing out the remaining cores as drawing workers
        args.quiet = len(todo) > 1
        # drawing is limited by memory bandwidth, not cores: past about 6 workers a clip, more only contend
        workers = max(1, min(6, (cores - len(todo)) // len(todo)))
        if len(todo) == 1:
            make(*todo[0][:3], args, None, workers)
            return
        import multiprocessing as mp
        procs = [mp.Process(target=make, args=(src, end, path, args, None, workers)) for src, end, path, _ in todo]
        for p in procs:
            p.start()
        for p in procs:
            p.join()
        return
    jobs = max(1, min(cores, len(todo)))
    args.quiet = jobs > 1
    if jobs == 1:
        for src, end, path, ts in todo:
            print(f"wrote {make(src, end, path, args, ts)}")
        return
    from concurrent.futures import ProcessPoolExecutor, as_completed
    with ProcessPoolExecutor(jobs) as pool:
        futs = [pool.submit(make, src, end, path, args, ts) for src, end, path, ts in todo]
        for f in as_completed(futs):
            print(f"wrote {f.result()}", flush=True)


if __name__ == "__main__":
    main()
