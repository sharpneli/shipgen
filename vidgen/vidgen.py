#!/usr/bin/env python3
"""
vidgen: a short top-down gameplay-style video of one exported ship, to judge how the sprites look in motion.

It reads only what the game would: out_designs/<id>/ (sprite.json, hitboxes.json, report.json, hull.png,
height.png, turrets/*.png). The camera looks straight down and follows the ship as it steams through procedural
water at its design speed, with a bow wave, Kelvin wake, stern wash and funnel smoke drifting on the wind.
The weapons start at rest and then train on a target bearing. Each mount turns only inside its traverse_deg, as
the game must, and only mounts whose arcs hold the bearing train. Then they fire: muzzle flash, gun smoke, a
blast ring on the water for big guns and tracers; torpedo mounts launch fish.

Shadows follow README "Shadows": the height map is marched toward the sun (shadow.shadow_mask, the reference
implementation), and turret shadows are the turret sprites in black, offset by (top_m - deck_m) / tan(elevation)
and kept where the height map is below top_m.

Everything is drawing; nothing here feeds back into the design. Particle and wave numbers are tuned by eye.

    ~/.venv/bin/python vidgen/vidgen.py bismarck                  # -> vidgen/out/bismarck.mp4
    ~/.venv/bin/python vidgen/vidgen.py all --size 1920x1080
    ~/.venv/bin/python vidgen/vidgen.py kongo --target 300 --still 9.5   # one PNG frame instead of a video

Needs numpy, pillow and imageio-ffmpeg (pip install imageio-ffmpeg; it bundles an ffmpeg binary).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from shadow import HEIGHT_STEP_M, shadow_mask, sun_offset_px  # noqa: E402

KN = 0.514444             # m/s per knot
G = 9.81

# timeline (seconds)
REST_S = 2.5              # weapons stowed before training starts
SETTLE_S = 0.6            # pause between the last mount on target and the first salvo
FIRE_S = 7.0              # firing phase
WARM_S = 10.0             # particles simulated before frame 0, so the wake and smoke already trail
# training rates in degrees per second: faster than real (2-4 deg/s for big turrets) to keep the clip short
TRAIN_RATE = {"main": 30.0, "secondary": 40.0, "torpedo": 30.0}

SUN_AZ = 225.0            # screen bearing toward the sun (clockwise from +x screen): upper left
SUN_EL = 45.0
WIND = np.array([0.0, -6.0])  # m/s in screen-world axes: from the south (screen bottom), carrying smoke away from
                              # the starboard (lower) side the guns fire to by default
SHADE = 0.5              # how much a full shadow darkens

WATER_DEEP = np.array([0.075, 0.175, 0.235], np.float32)
WATER_LIT = np.array([0.13, 0.26, 0.32], np.float32)
WATER_SKY = np.array([0.55, 0.66, 0.72], np.float32)
CHURN = np.array([0.26, 0.45, 0.49], np.float32)
FOAM = np.array([0.93, 0.96, 0.97], np.float32)
FLASH = np.array([1.0, 0.72, 0.30], np.float32)
FLASH_CORE = np.array([1.0, 0.97, 0.85], np.float32)

BUCKETS = [1, 2, 4, 8, 16, 32]   # blur radii (half-res px) the particle splats are sorted into
PAD = 3 * BUCKETS[-1]            # density buffers extend this far past the frame so off-screen blobs bleed in


# ---------------------------------------------------------------- small helpers
def rot(v, deg):
    """Rotate (x, y) by deg clockwise on screen (y down)."""
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([v[0] * c - v[1] * s, v[0] * s + v[1] * c])


def unit(deg):
    a = math.radians(deg)
    return np.array([math.cos(a), math.sin(a)])


def in_arc(a, arc):
    return (a - arc[0]) % 360.0 <= arc[1] - arc[0] + 1e-6


def unwrap(a, trav):
    """a as a value inside traverse [start, end], or None if the mount can't point there."""
    v = trav[0] + (a - trav[0]) % 360.0
    return v if v <= trav[1] + 1e-6 else None


def smoothstep(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def box_blur(a, r, passes=3):
    """Separable box blur (3 passes ~ gaussian, sigma^2 = r(r+1)), edges clamped."""
    for _ in range(passes):
        for axis in (0, 1):
            p = np.pad(a, [(r + 1, r) if ax == axis else (0, 0) for ax in (0, 1)], mode="edge")
            c = np.cumsum(p, axis=axis, dtype=np.float32)
            n = a.shape[axis]
            hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
            lo = np.take(c, np.arange(0, n), axis=axis)
            a = (hi - lo) / (2 * r + 1)
    return a


def blend(frame, rgba, x0, y0):
    """Alpha-blend an RGBA uint8 array into the float frame with its top-left at (x0, y0)."""
    h, w = rgba.shape[:2]
    H, W = frame.shape[:2]
    fx0, fy0, fx1, fy1 = max(0, x0), max(0, y0), min(W, x0 + w), min(H, y0 + h)
    if fx0 >= fx1 or fy0 >= fy1:
        return
    src = rgba[fy0 - y0:fy1 - y0, fx0 - x0:fx1 - x0].astype(np.float32) / 255.0
    a = src[..., 3:4]
    dst = frame[fy0:fy1, fx0:fx1]
    dst *= 1 - a
    dst += src[..., :3] * a


def stamp_max(buf, alpha, x0, y0, heights=None, below=None):
    """buf = max(buf, alpha) over the patch at (x0, y0). With heights (full-frame metres) and below, it lands only
    where heights < below: a shadow cast from height `below` can't climb anything taller."""
    h, w = alpha.shape
    H, W = buf.shape
    fx0, fy0, fx1, fy1 = max(0, x0), max(0, y0), min(W, x0 + w), min(H, y0 + h)
    if fx0 >= fx1 or fy0 >= fy1:
        return
    a = alpha[fy0 - y0:fy1 - y0, fx0 - x0:fx1 - x0]
    if heights is not None:
        a = a * (heights[fy0:fy1, fx0:fx1] < below)
    np.maximum(buf[fy0:fy1, fx0:fx1], a, out=buf[fy0:fy1, fx0:fx1])


def font(size):
    for name in ("DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


# ---------------------------------------------------------------- particles
class Particles:
    """World-space particles (metres). Each relaxes its velocity toward `drift` with time constant tau."""
    FIELDS = ("x", "y", "vx", "vy", "age", "life", "r0", "r1", "a0", "h")

    def __init__(self, drift, tau):
        self.d = {k: np.zeros(0, np.float32) for k in self.FIELDS}
        self.drift = np.asarray(drift, np.float32)
        self.tau = tau

    def add(self, **kw):
        sizes = [np.size(v) for v in kw.values()]
        if min(sizes) == 0:
            return
        n = max(sizes)
        for k in self.FIELDS:
            v = np.broadcast_to(np.asarray(kw.get(k, 0.0), np.float32), (n,))
            self.d[k] = np.concatenate([self.d[k], v])

    def step(self, dt):
        d = self.d
        k = 1 - math.exp(-dt / self.tau)
        d["vx"] += (self.drift[0] - d["vx"]) * k
        d["vy"] += (self.drift[1] - d["vy"]) * k
        d["x"] += d["vx"] * dt
        d["y"] += d["vy"] * dt
        d["age"] += dt
        keep = d["age"] < d["life"]
        if not keep.all():
            for f in self.FIELDS:
                d[f] = d[f][keep]

    def __len__(self):
        return len(self.d["x"])

    def radius(self):
        u = np.clip(self.d["age"] / self.d["life"], 0, 1)
        return self.d["r0"] + (self.d["r1"] - self.d["r0"]) * np.sqrt(u)

    def opacity(self, fade_in=0.08):
        d = self.d
        u = np.clip(d["age"] / d["life"], 0, 1)
        return d["a0"] * np.clip(d["age"] / fade_in, 0, 1) * (1 - u) ** 1.5


class Density:
    """Splats soft blobs into a half-resolution buffer: each blob lands in the blur bucket nearest its radius."""

    def __init__(self, W, H):
        self.hw, self.hh = W // 2, H // 2
        self.shape = (self.hh + 2 * PAD, self.hw + 2 * PAD)

    def render(self, px, py, r_px, w):
        """px, py: full-res screen px; r_px: full-res radius; w: peak opacity. Returns the half-res field.
        A bucket of blur radius R is splatted into a grid f = R/2 times coarser and blurred there with radius 2,
        then upsampled: the big soft buckets cost no more than the small ones."""
        out = np.zeros(self.shape, np.float32)
        if len(px) == 0:
            return out[PAD:-PAD, PAD:-PAD]
        hx, hy = px / 2 + PAD, py / 2 + PAD
        rb = np.clip(np.rint(np.log2(np.maximum(r_px / 2, 1))), 0, len(BUCKETS) - 1).astype(int)
        for b, R in enumerate(BUCKETS):
            m = (rb == b) & (hx >= 0) & (hy >= 0) & (hx < self.shape[1] - 1) & (hy < self.shape[0] - 1)
            if not m.any():
                continue
            f = max(1, R // 2)
            r = R // f
            shape = (-(-self.shape[0] // f), -(-self.shape[1] // f))
            buf = np.zeros((shape[0] + 1, shape[1] + 1), np.float32)
            x, y = (hx[m] + 0.5) / f - 0.5, (hy[m] + 0.5) / f - 0.5
            x, y = np.clip(x, 0, shape[1] - 1), np.clip(y, 0, shape[0] - 1)
            ix, iy = np.floor(x).astype(int), np.floor(y).astype(int)
            fx, fy = x - ix, y - iy
            wm = w[m] * (2 * math.pi * r * (r + 1))   # so the blurred peak comes out at about w
            for ox, oy, ww in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)),
                               (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
                np.add.at(buf, (iy + oy, ix + ox), wm * ww)
            blurred = box_blur(buf[:shape[0], :shape[1]], r)
            if f > 1:
                blurred = np.asarray(Image.fromarray(blurred, "F").resize(
                    (shape[1] * f, shape[0] * f), Image.BILINEAR))[:self.shape[0], :self.shape[1]]
            out += blurred
        return out[PAD:-PAD, PAD:-PAD]


def upscale(a, W, H):
    return np.array(Image.fromarray(a.astype(np.float32), "F").resize((W, H), Image.BILINEAR))


# ---------------------------------------------------------------- water
class Water:
    """Directional sine swell plus a scrolling ripple normal map, shaded for a viewer straight above."""

    def __init__(self, rng, W, H, s, C):
        self.W, self.H, self.s = W, H, s
        u, v = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
        self.mx, self.my = (u - C[0]) / s, (v - C[1]) / s       # metres from the ship's centre
        wind_dir = math.degrees(math.atan2(WIND[1], WIND[0]))
        self.waves = []
        # many short-crested components, no dominant pair (two strong crossing swells read as a lattice)
        for lam in np.geomspace(110, 6, 14):
            if lam * s < 10:      # finer than 10 px would only alias
                continue
            steep = rng.uniform(0.03, 0.06)
            k = 2 * math.pi / lam
            d = unit(wind_dir + rng.uniform(-75, 75))
            self.waves.append((k * d[0], k * d[1], steep, math.sqrt(G * k), rng.uniform(0, 2 * math.pi)))
        # ripple normal map: tileable filtered noise, 256 px over RIPPLE_M metres
        n = 256
        f = np.fft.fftfreq(n)
        kk = np.hypot(*np.meshgrid(f, f))
        spec = np.fft.fft2(rng.standard_normal((n, n))) * np.exp(-(kk / 0.06) ** 2) * (kk > 0.004)
        hgt = np.real(np.fft.ifft2(spec))
        hgt /= hgt.std()
        self.rx, self.ry = np.gradient(hgt)[1].astype(np.float32), np.gradient(hgt)[0].astype(np.float32)
        self.ripple_m = max(36.0, 200.0 / s)   # zoomed far out, a 36 m tile would alias
        L = np.array([math.cos(math.radians(SUN_EL)) * unit(SUN_AZ)[0],
                      math.cos(math.radians(SUN_EL)) * unit(SUN_AZ)[1], math.sin(math.radians(SUN_EL))])
        self.L = L
        Hh = L + np.array([0, 0, 1.0])
        self.Hh = Hh / np.linalg.norm(Hh)
        noise = rng.standard_normal((H // 8 + 2, W // 8 + 2)).astype(np.float32)
        self.foam_noise = np.clip(0.75 + 0.35 * upscale(box_blur(noise, 1), W, H), 0.3, 1.2)

    def ripple(self, X, Y, scale, ox, oy):
        n = self.rx.shape[0]
        k = n / (self.ripple_m * scale)
        ix = ((X + ox) * k).astype(np.int32) % n
        iy = ((Y + oy) * k).astype(np.int32) % n
        return self.rx[iy, ix], self.ry[iy, ix]

    def shade(self, cam, t):
        # the swell is smooth, so it's summed at half resolution and upsampled; ripples stay full resolution
        Xh, Yh = self.mx[::2, ::2] + cam[0], self.my[::2, ::2] + cam[1]
        hx = np.zeros_like(Xh)
        hy = np.zeros_like(Xh)
        for kx, ky, steep, w, ph in self.waves:
            c = np.cos(kx * Xh + ky * Yh - w * t + ph) * steep
            hx += c * kx / math.hypot(kx, ky)
            hy += c * ky / math.hypot(kx, ky)
        hx, hy = upscale(hx, self.W, self.H), upscale(hy, self.W, self.H)
        X, Y = self.mx + cam[0], self.my + cam[1]
        for scale, vel, amp in ((1.0, (1.1, 1.6), 0.10), (0.45, (-0.7, 1.2), 0.07)):
            if self.ripple_m * scale * self.s < 40:
                continue
            rx, ry = self.ripple(X, Y, scale, -vel[0] * t, -vel[1] * t)
            hx += rx * amp
            hy += ry * amp
        inv = 1 / np.sqrt(hx * hx + hy * hy + 1)
        nx, ny, nz = -hx * inv, -hy * inv, inv
        diff = np.clip(nx * self.L[0] + ny * self.L[1] + nz * self.L[2], 0, 1)
        sky = np.clip(1 - nz, 0, 1) * 6       # tilted facets reflect more sky
        spec = np.clip(nx * self.Hh[0] + ny * self.Hh[1] + nz * self.Hh[2], 0, 1) ** 400
        d = (diff - 0.6) / 0.4
        col = WATER_DEEP + (WATER_LIT - WATER_DEEP) * np.clip(d, 0, 1)[..., None]
        col = col + (WATER_SKY - col) * np.clip(sky, 0, 0.35)[..., None]
        return col + spec[..., None] * 0.9


# ---------------------------------------------------------------- the scene
class Mount:
    pass


class Scene:
    def __init__(self, src: Path, W, H, fps, heading, target, seed, seconds=None):
        self.src, self.W, self.H, self.fps = src, W, H, fps
        self.rng = np.random.default_rng(seed)
        self.sprite = json.loads((src / "sprite.json").read_text())
        self.hit = json.loads((src / "hitboxes.json").read_text())
        self.report = json.loads((src / "report.json").read_text())
        res = self.report["results"]
        self.heading = heading
        self.target_bearing = target % 360.0
        self.speed = float(self.report["inputs"].get("speed_kn", 20)) * KN
        self.vel = unit(heading) * self.speed
        self.deck_m = self.sprite["shadow"]["deck_m"]
        self.freeboard = self.hit["vertical"].get("freeboard", self.deck_m)

        # scale: fit the ship's canvas (rotated) into 80% x 62% of the frame, never above the sprites' own scale
        S0 = self.sprite["scale_px_per_m"]
        Lm, Bm = res["length_m"], res["beam_m"]
        ch, sh = abs(math.cos(math.radians(heading))), abs(math.sin(math.radians(heading)))
        self.s = s = min(S0, 0.80 * W / (Lm * ch + Bm * sh), 0.62 * H / (Lm * sh + Bm * ch))
        # the ship sits a little ahead of centre so the wake has room
        self.C = np.array([W / 2, H / 2]) + unit(heading) * (0.07 * W)

        self._static_layers(S0)
        self._mounts(S0, target)
        self._funnels()
        self.duration = seconds or (self.t_fire + FIRE_S if self.has_guns else 10.0)

        self.water = Water(self.rng, W, H, s, self.C)
        self.dens = Density(W, H)
        self.foam = Particles((0, 0), 2.5)       # water at rest; the push from the hull dies away
        self.churn = Particles((0, 0), 3.0)
        self.kelvin = Particles((0, 0), 12.0)   # bow-wave crests keep running out along the Kelvin arms
        self.smoke = Particles(WIND, 1.2)
        self.gsmoke = Particles(WIND, 1.6)      # the blast carries it out before the wind turns it
        self.glow = []                            # (x, y, r, intensity, t0, life, core)
        self.tracers = []                         # [x, y, vx, vy, t0]
        self.fish = []                            # torpedoes [x, y, vx, vy, t0]
        self.pos = np.zeros(2)
        self.t = -WARM_S
        self.hud = self._hud()

    # ----- setup
    def to_screen(self, m):
        """Ship-local metres (+x bow, +y starboard) -> screen px."""
        return self.C + rot(np.asarray(m, float), self.heading) * self.s

    def world_of(self, m):
        """Ship-local metres (one point or an (n, 2) array) -> world metres."""
        return self.pos + self.dir_of(m)

    def dir_of(self, m):
        """Rotate ship-local vectors (one or (n, 2)) into world axes."""
        a = math.radians(self.heading)
        R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
        return np.asarray(m, float) @ R.T

    def _affine(self, im, origin, resample):
        h = math.radians(self.heading)
        c, sn = math.cos(h), math.sin(h)
        Cx, Cy = self.C
        data = (c, sn, origin[0] - c * Cx - sn * Cy, -sn, c, origin[1] + sn * Cx - c * Cy)
        return im.transform((self.W, self.H), Image.AFFINE, data, resample=resample)

    def _static_layers(self, S0):
        k = self.s / S0
        hull = Image.open(self.src / self.sprite["layers"]["hull"]).convert("RGBA")
        height = Image.open(self.src / self.sprite["shadow"]["height_map"]).convert("L")
        size = (max(1, round(hull.width * k)), max(1, round(hull.height * k)))
        origin = np.array(self.sprite["origin_px"]) * k
        if k < 1:
            hull = hull.resize(size, Image.LANCZOS)
            height = height.resize(size, Image.BOX)
        self.hull = np.asarray(self._affine(hull, origin, Image.BICUBIC))
        hs = self._affine(height, origin, Image.BILINEAR)
        self.Hs = np.asarray(hs, np.float32) * HEIGHT_STEP_M
        self.hull_alpha = self.hull[..., 3].astype(np.float32) / 255
        self.hull_shadow = np.asarray(shadow_mask(hs, self.s, SUN_AZ, SUN_EL), np.float32) / 255

    def _mounts(self, S0, target):
        k = self.s / S0
        comps = {c["id"]: c for c in self.hit["components"]}
        types = {}
        for tid, t in self.sprite["turret_types"].items():
            im = Image.open(self.src / t["file"]).convert("RGBA")
            if k < 1:
                im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
            types[tid] = (im, t.get("desc", tid))
        self.mounts = []
        for m in sorted(self.sprite["mounts"], key=lambda m: m["z"]):
            mt = Mount()
            mt.id, mt.kind, mt.type = m["id"], m["kind"], m["type"]
            mt.img, desc = types[m["type"]]
            mt.pos_m = np.array(m["pos_m"], float)
            mt.screen = self.to_screen(mt.pos_m)
            mt.top_m = m["top_m"]
            # turret shadows are swept from the barbette top (the height map under the pivot) up to the roof, and
            # measured from the deck the mount stands on (a low percentile of the height map around it, sea left
            # out), not the main deck: a raised forecastle turret would otherwise cast too long
            px, py = int(round(mt.screen[0])), int(round(mt.screen[1]))
            Hh, Hw = self.Hs.shape
            inside = 0 <= px < Hw and 0 <= py < Hh
            mt.base_h = min(float(self.Hs[py, px]), mt.top_m) if inside else self.deck_m
            r = max(2, int(mt.img.width * 0.35))
            patch = self.Hs[max(0, py - r):py + r, max(0, px - r):px + r]
            patch = patch[patch > 0.3]
            mt.recv_h = min(float(np.percentile(patch, 20)), mt.base_h) if patch.size else self.deck_m
            mt.trav = m["traverse_deg"]
            mt.rest = unwrap(m["rest_deg"], mt.trav)
            if mt.rest is None:      # README promises the traverse holds the rest bearing; be permissive anyway
                mt.rest = m["rest_deg"]
            nums = re.search(r"(\d+)\s*x\s*(\d+)\s*mm", desc) or re.search(r"(\d+)x(\d+)", mt.type)
            mt.calibre = float(nums.group(2)) if nums else 100.0
            loc = comps.get(mt.id, {}).get("local", {})
            mt.muzzles = []
            for b in loc.get("barrels", []):
                p = np.array(b)
                xm = p[:, 0].max()
                mt.muzzles.append(np.array([xm, p[np.abs(p[:, 0] - xm) < 1e-3, 1].mean()]))
            if not mt.muzzles:
                mt.muzzles = [np.zeros(2)]
            aim = target % 360.0
            ok = any(in_arc(aim, a) for a in m["arcs_deg"])
            mt.aim = unwrap(aim, mt.trav) if ok else None
            if mt.aim is None:
                mt.train = (0.0, 0.0)
            else:
                mt.train = (REST_S, REST_S + abs(mt.aim - mt.rest) / TRAIN_RATE.get(mt.kind, 30.0))
            self.mounts.append(mt)
        bearing = [mt for mt in self.mounts if mt.aim is not None]
        self.has_guns = bool(bearing)
        self.t_fire = max((mt.train[1] for mt in bearing), default=REST_S) + SETTLE_S
        # firing schedule: main guns in full salvos, secondaries rippling on their own beat, torpedoes once
        ev = []
        rng = self.rng
        salvo = 2.8 if any(mt.calibre >= 280 for mt in bearing) else 2.2
        for mt in bearing:
            n = len(mt.muzzles)
            if mt.kind == "torpedo":
                for i in range(n):
                    ev.append((self.t_fire + 1.0 + 0.3 * i + rng.uniform(0, 0.1), mt, i))
            elif mt.kind == "main":
                t = self.t_fire
                while t < self.t_fire + FIRE_S - 0.5:
                    for i in range(n):
                        ev.append((t + rng.uniform(0, 0.12) + 0.04 * i, mt, i))
                    t += salvo
            else:
                period = 0.7 + mt.calibre / 180
                t = self.t_fire + 0.3 + rng.uniform(0, period)
                while t < self.t_fire + FIRE_S - 0.3:
                    for i in range(n):
                        ev.append((t + 0.05 * i, mt, i))
                    t += period * rng.uniform(0.85, 1.15)
        self.events = sorted(ev, key=lambda e: e[0])
        self.next_ev = 0

    def _funnels(self):
        plant = self.report.get("plant", {})
        fuel = str(plant.get("fuel", "oil"))
        self.coal = "coal" in fuel
        self.funnels = []
        for c in self.hit["components"]:
            if c["kind"] != "funnel":
                continue
            p = np.array(c["points"])
            area = 0.5 * abs(np.dot(p[:, 0], np.roll(p[:, 1], 1)) - np.dot(p[:, 1], np.roll(p[:, 0], 1)))
            r = math.sqrt(max(area, 1.0) / math.pi)
            self.funnels.append((p.mean(axis=0), r, c["top"] + self.freeboard))

    def _hud(self):
        im = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        res = self.report["results"]
        big, small = font(max(14, self.H // 30)), font(max(11, self.H // 50))
        x, y = self.H // 36, self.H - self.H // 36
        stats = (f"{res['length_m']:.0f} m  ·  {res['standard_displacement_t']:,} t std  ·  "
                 f"{self.report['inputs'].get('speed_kn', '?')} kn  ·  {len(self.mounts)} mounts")
        d.text((x + 1, y - big.size - small.size - 5), self.sprite.get("name", self.sprite["id"]),
               font=big, fill=(0, 0, 0, 140))
        d.text((x, y - big.size - small.size - 6), self.sprite.get("name", self.sprite["id"]),
               font=big, fill=(240, 244, 246, 235))
        d.text((x, y - small.size), stats, font=small, fill=(220, 228, 232, 210))
        self.font_small = small
        return np.asarray(im)

    # ----- simulation
    def bearing(self, mt, t):
        if mt.aim is None:
            return mt.rest
        t0, t1 = mt.train
        u = smoothstep((t - t0) / (t1 - t0)) if t1 > t0 else float(t >= t0)
        return mt.rest + (mt.aim - mt.rest) * u

    def spawn_wake(self, dt):
        rng = self.rng
        hull = np.array(self.hit["hull"]["points"] if isinstance(self.hit["hull"], dict) else self.hit["hull"])
        L = hull[:, 0].max() - hull[:, 0].min()
        xb = hull[:, 0].max()
        spd = self.speed
        fs = min(1.2, max(0.3, L / 150))     # foam size follows the ship: a PT boat's bow wave is small
        # bow wave: along the forward quarter of each side, pushed out at 0.36 v (the Kelvin angle's tangent)
        fwd = hull[hull[:, 0] > xb - 0.12 * L]
        n = int(rng.poisson(dt * (30 + 0.3 * L) * min(1.5, spd / 10) / fs))
        if n and len(fwd):
            p = fwd[rng.integers(0, len(fwd), n)] + rng.normal(0, 0.4, (n, 2))
            side = np.sign(p[:, 1] + 1e-6)
            out = np.stack([np.full(n, 0.1), side], 1) * spd * rng.uniform(0.25, 0.4, (n, 1))
            w = self.world_of(p)
            v = self.dir_of(out)
            self.kelvin.add(x=w[:, 0], y=w[:, 1], vx=v[:, 0], vy=v[:, 1], life=rng.uniform(6, 12, n),
                            r0=0.6 * fs, r1=rng.uniform(1.5, 3.5, n) * fs, a0=rng.uniform(0.12, 0.3, n))
        # side wash: thin foam along the waterline
        n = int(rng.poisson(dt * 0.25 * L * min(1.5, spd / 10)))
        if n:
            p = hull[rng.integers(0, len(hull), n)] + rng.normal(0, 0.3, (n, 2))
            w = self.world_of(p)
            out = np.stack([np.zeros(n), np.sign(p[:, 1] + 1e-6)], 1) * rng.uniform(0.5, 2, (n, 1))
            v = self.dir_of(out)
            self.foam.add(x=w[:, 0], y=w[:, 1], vx=v[:, 0], vy=v[:, 1], life=rng.uniform(1.0, 2.5, n),
                          r0=0.4 * fs, r1=rng.uniform(0.8, 1.6, n) * fs, a0=rng.uniform(0.15, 0.3, n))
        # stern wash: propeller churn dragged along behind
        xs = hull[:, 0].min()
        aft = hull[hull[:, 0] < xs + 0.06 * L]
        half_b = max(1.0, np.abs(aft[:, 1]).max() * 0.75) if len(aft) else 2.0
        n = int(rng.poisson(dt * (20 + 0.12 * L)))
        if n:
            p = np.stack([np.full(n, xs) + rng.uniform(-1.5, 2, n), rng.uniform(-half_b, half_b, n)], 1)
            w = self.world_of(p)
            v = np.tile(self.vel * 0.35, (n, 1)) + rng.normal(0, 1.2, (n, 2))
            self.churn.add(x=w[:, 0], y=w[:, 1], vx=v[:, 0], vy=v[:, 1], life=rng.uniform(10, 18, n),
                           r0=half_b * 0.4, r1=half_b * 0.9 + 4 * fs, a0=rng.uniform(0.10, 0.2, n))
            m = int(rng.poisson(dt * (10 + 0.06 * L) / fs))
            p = np.stack([np.full(m, xs) + rng.uniform(-1.5, 2, m), rng.uniform(-half_b, half_b, m)], 1)
            w = self.world_of(p)
            v = np.tile(self.vel * 0.35, (m, 1)) + rng.normal(0, 1.2, (m, 2))
            self.foam.add(x=w[:, 0], y=w[:, 1], vx=v[:, 0], vy=v[:, 1], life=rng.uniform(3, 7, m),
                          r0=0.8 * fs, r1=rng.uniform(1.5, 3.5, m) * fs, a0=rng.uniform(0.25, 0.5, m))

    def spawn_smoke(self, dt):
        rng = self.rng
        for c, r, top in self.funnels:
            n = int(rng.poisson(dt * (10 + 2 * r)))
            if not n:
                continue
            p = c + rng.normal(0, r * 0.25, (n, 2))
            w = self.world_of(p)
            v = np.tile(self.vel * 0.6, (n, 1)) + rng.normal(0, 0.6, (n, 2))
            self.smoke.add(x=w[:, 0], y=w[:, 1], vx=v[:, 0], vy=v[:, 1], life=rng.uniform(5, 9, n),
                           r0=r * 0.6, r1=r * 1.6 + 3, a0=rng.uniform(0.15, 0.3, n) * (1.6 if self.coal else 1.0),
                           h=top)

    def fire(self, mt, i):
        rng = self.rng
        ang = self.heading + self.bearing(mt, self.t)
        d = unit(ang)
        muz = self.pos + rot(mt.pos_m, self.heading) + rot(mt.muzzles[i], ang)
        c = mt.calibre
        if mt.kind == "torpedo":
            self.fish.append([muz[0], muz[1], *(self.vel + d * 22.0), self.t])
            self.foam.add(x=muz[0] + rng.normal(0, 1, 12), y=muz[1] + rng.normal(0, 1, 12),
                          vx=d[0] * 4, vy=d[1] * 4, life=2.0, r0=0.5, r1=2.5, a0=0.7)
            return
        size = 1.0 + c / 30          # flash radius, m: 380 mm -> ~19 m, 40 mm -> ~3 m
        self.glow.append((muz[0], muz[1], d[0], d[1], size, self.t))
        n = int(3 + c / 40)
        sp = rng.uniform(0.2, 1.0, n) * (10 + c / 12)
        jit = rng.normal(0, 0.25, (n, 2))
        vv = (d[None, :] + jit) * sp[:, None] + self.vel * 0.3
        self.gsmoke.add(x=muz[0] + d[0] * size * 0.3, y=muz[1] + d[1] * size * 0.3, vx=vv[:, 0], vy=vv[:, 1],
                        life=rng.uniform(2.0, 4.0, n), r0=size * 0.3, r1=size * rng.uniform(1.0, 1.8, n),
                        a0=rng.uniform(0.12, 0.25, n), h=self.deck_m + 3)
        if c >= 150:                  # blast flattens the sea under the muzzle
            k = int(16 + c / 10)
            a = rng.uniform(0, 2 * math.pi, k)
            rv = np.stack([np.cos(a), np.sin(a)], 1) * (c / 12) * rng.uniform(0.6, 1.0, (k, 1))
            rv += d * c / 20
            self.foam.add(x=muz[0] + d[0] * size * 0.5, y=muz[1] + d[1] * size * 0.5, vx=rv[:, 0], vy=rv[:, 1],
                          life=rng.uniform(0.8, 1.6, k), r0=1.0, r1=c / 90 + 1, a0=0.55)
        if c >= 75:
            self.tracers.append([muz[0], muz[1], *(self.vel + d * 450.0), self.t])

    def step(self, dt):
        self.pos = self.pos + self.vel * dt
        self.t += dt
        self.spawn_wake(dt)
        self.spawn_smoke(dt)
        while self.next_ev < len(self.events) and self.events[self.next_ev][0] <= self.t:
            _, mt, i = self.events[self.next_ev]
            self.fire(mt, i)
            self.next_ev += 1
        for ps in (self.foam, self.kelvin, self.churn, self.smoke, self.gsmoke):
            ps.step(dt)
        for f in self.fish:
            f[0] += f[2] * dt
            f[1] += f[3] * dt
            self.foam.add(x=f[0] + self.rng.normal(0, 0.3, 2), y=f[1] + self.rng.normal(0, 0.3, 2),
                          life=self.rng.uniform(2, 5, 2), r0=0.3, r1=1.0, a0=0.22)
        for tr in self.tracers:
            tr[0] += tr[2] * dt
            tr[1] += tr[3] * dt
        self.glow = [g for g in self.glow if self.t - g[5] < 0.25]
        far = 3 * max(self.W, self.H) / self.s
        self.tracers = [tr for tr in self.tracers if self.t - tr[4] < 1.2]
        self.fish = [f for f in self.fish if np.hypot(f[0] - self.pos[0], f[1] - self.pos[1]) < far]

    # ----- drawing
    def scr(self, wx, wy):
        return (wx - self.pos[0]) * self.s + self.C[0], (wy - self.pos[1]) * self.s + self.C[1]

    def field(self, ps, weight=None, offset=(0.0, 0.0)):
        if not len(ps):
            return np.zeros((self.dens.hh, self.dens.hw), np.float32)
        px, py = self.scr(ps.d["x"], ps.d["y"])
        w = ps.opacity() if weight is None else weight
        return self.dens.render(px + offset[0], py + offset[1], ps.radius() * self.s, w)

    def render(self):
        W, H, s = self.W, self.H, self.s
        frame = self.water.shade(self.pos, self.t)

        churn = upscale(self.field(self.churn), W, H)
        frame += (CHURN - frame) * np.clip(1 - np.exp(-churn), 0, 0.8)[..., None]
        foam = upscale(self.field(self.foam) + self.field(self.kelvin), W, H) * self.water.foam_noise
        frame += (FOAM - frame) * np.clip(1 - np.exp(-1.6 * foam), 0, 0.95)[..., None]

        # hull, then static and turret shadows on everything below the turrets
        a = self.hull_alpha[..., None]
        frame = frame * (1 - a) + self.hull[..., :3].astype(np.float32) / 255 * a
        shade = self.hull_shadow.copy()
        rots = []
        for mt in self.mounts:
            ang = self.heading + self.bearing(mt, self.t)
            im = mt.img.rotate(-ang, resample=Image.BICUBIC, expand=True)
            arr = np.asarray(im)
            x0 = int(round(mt.screen[0] - arr.shape[1] / 2))
            y0 = int(round(mt.screen[1] - arr.shape[0] / 2))
            rots.append((arr, x0, y0))
            # the turret's body from its barbette top to its roof, as slices about 1.5 px of shadow apart, so the
            # shadow runs unbroken from the barbette's (in the height map) to the roof's
            alpha = arr[..., 3].astype(np.float32) / 255
            span = (mt.top_m - mt.base_h) / math.tan(math.radians(SUN_EL)) * s
            n = max(1, min(24, int(math.ceil(span / 1.5))))
            for j in range(n + 1):
                h = mt.base_h + (mt.top_m - mt.base_h) * j / n
                off = sun_offset_px(s, SUN_AZ, SUN_EL, max(0.0, h - mt.recv_h))
                stamp_max(shade, alpha, x0 + int(round(off[0])), y0 + int(round(off[1])), self.Hs, h)
        self.last_shade = shade          # kept for debugging shadow issues
        frame *= (1 - SHADE * shade)[..., None]
        for arr, x0, y0 in rots:
            blend(frame, arr, x0, y0)

        # smoke: shadows on the sea and ship, then the smoke itself, lit from the sun side
        sd = unit(SUN_AZ)
        smoke_d = np.zeros((self.dens.hh, self.dens.hw), np.float32)
        gun_d = np.zeros_like(smoke_d)
        sh = np.zeros_like(smoke_d)
        if len(self.smoke):
            smoke_d = self.field(self.smoke)
            h = float(np.mean(self.smoke.d["h"]))
            o = sun_offset_px(s, SUN_AZ, SUN_EL, h + 4)
            sh += self.field(self.smoke, offset=o)
        if len(self.gsmoke):
            gun_d = self.field(self.gsmoke)
            o = sun_offset_px(s, SUN_AZ, SUN_EL, self.deck_m + 4)
            sh += self.field(self.gsmoke, offset=o)
        if sh.any():
            frame *= (1 - 0.35 * np.clip(1 - np.exp(-upscale(sh, W, H)), 0, 1))[..., None]
        for dens, base in ((smoke_d, (0.16, 0.15, 0.15) if self.coal else (0.36, 0.36, 0.37)),
                           (gun_d, (0.62, 0.59, 0.53))):
            if not dens.any():
                continue
            gy, gx = np.gradient(dens)
            light = np.clip(1.0 + 3.0 * (gx * sd[0] + gy * sd[1]) * -1, 0.55, 1.35)
            col = np.array(base, np.float32)[None, None, :] * upscale(light, W, H)[..., None]
            al = np.clip(1 - np.exp(-1.4 * upscale(dens, W, H)), 0, 0.92)[..., None]
            frame = frame * (1 - al) + col * al

        # light: muzzle flashes and tracers, added
        if self.glow or self.tracers:
            xs, ys, rs, ws, core = [], [], [], [], []
            for gx_, gy_, dx, dy, size, t0 in self.glow:
                u = (self.t - t0) / 0.25
                fade = (1 - u) ** 2
                for j, (along, rr, ww) in enumerate(((0.0, 0.25, 1.0), (0.45, 0.32, 0.9), (0.9, 0.35, 0.7),
                                                     (1.35, 0.3, 0.45), (1.8, 0.25, 0.25))):
                    x, y = self.scr(gx_ + dx * size * along, gy_ + dy * size * along)
                    xs.append(x), ys.append(y), rs.append(size * rr * (0.8 + 0.6 * u) * s), ws.append(ww * fade)
            for tx, ty, vx, vy, t0 in self.tracers:
                sp = math.hypot(vx, vy)
                for j in range(6):
                    k = j / 6 * 14 / sp
                    x, y = self.scr(tx - vx * k, ty - vy * k)
                    xs.append(x), ys.append(y), rs.append(max(1.0, 0.6 * s)), ws.append(0.5 * (1 - j / 6))
            g = upscale(self.dens.render(np.array(xs), np.array(ys), np.array(rs), np.array(ws)), W, H)
            a = (1 - np.exp(-1.5 * g))[..., None]           # saturates, so overlapping flashes don't blow out
            frame += (FLASH - frame) * a * 0.9
            frame += (FLASH_CORE - frame) * np.clip(1.5 * g - 1.2, 0, 1)[..., None] * 0.8

        # target marker and captions
        frame = np.clip(frame, 0, 1)
        out = (frame * 255).astype(np.uint8)
        hud = self.hud.astype(np.float32) / 255
        ha = hud[..., 3:4]
        out = (out * (1 - ha) + hud[..., :3] * 255 * ha).astype(np.uint8)
        return self._overlay(out)

    def _overlay(self, out):
        im = Image.fromarray(out)
        d = ImageDraw.Draw(im, "RGBA")
        t = self.t
        if not self.has_guns:
            phase = "Under way"
        elif t < REST_S:
            phase = "Weapons at rest"
        elif t < self.t_fire:
            phase = "Training on target"
        else:
            phase = "Firing"
        m = self.H // 36
        d.text((m, m), phase, font=self.font_small, fill=(235, 240, 242, 220))
        if self.has_guns and t >= REST_S - 0.5:
            b = self.target_bearing
            dvec = unit(self.heading + b)
            # where the ray from the ship's centre leaves the frame, pulled in by a margin
            ts = []
            for i, lim in ((0, self.W), (1, self.H)):
                if abs(dvec[i]) > 1e-6:
                    for edge in (m * 2, lim - m * 2):
                        tt = (edge - self.C[i]) / dvec[i]
                        if tt > 0:
                            ts.append(tt)
            tt = min(ts)
            p = self.C + dvec * tt
            n = rot(np.array([1.0, 0]), self.heading + b)
            q = rot(np.array([0, 1.0]), self.heading + b)
            sz = self.H / 50
            tri = [tuple(p), tuple(p - n * sz * 1.6 + q * sz * 0.8), tuple(p - n * sz * 1.6 - q * sz * 0.8)]
            alpha = int(200 * min(1.0, (t - REST_S + 0.5) / 0.5))
            d.polygon(tri, fill=(230, 60, 50, alpha))
            d.text(tuple(p - n * sz * 3.4 - np.array([sz, sz * 0.6])), "target", font=self.font_small,
                   fill=(235, 220, 215, alpha))
        return np.asarray(im)


# ---------------------------------------------------------------- driver
def make(src: Path, out: Path, args, still=None):
    sc = Scene(src, args.w, args.h, args.fps, args.heading, args.target, args.seed, args.seconds)
    dt = 1.0 / args.fps
    for _ in range(int(WARM_S * args.fps)):
        sc.step(dt)
    sc.t = 0.0
    sc.next_ev = 0
    n = int(round(sc.duration * args.fps))
    if still is not None:
        for _ in range(int(round(still * args.fps))):
            sc.step(dt)
        Image.fromarray(sc.render()).save(out)
        return out
    import imageio_ffmpeg
    w = imageio_ffmpeg.write_frames(str(out), (args.w, args.h), fps=args.fps, codec="libx264",
                                    pix_fmt_out="yuv420p", macro_block_size=1,
                                    output_params=["-crf", str(args.crf), "-preset", "medium",
                                                   "-movflags", "+faststart"])
    w.send(None)
    for i in range(n):
        w.send(np.ascontiguousarray(sc.render()).tobytes())
        sc.step(dt)
        if i % args.fps == 0 and not args.quiet:
            print(f"\r  {out.name}: {i / args.fps:4.1f}/{sc.duration:.1f} s", end="", flush=True)
    w.close()
    print(f"\r  {out.name}: {sc.duration:.1f} s, {n} frames")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ships", nargs="+", help="out_designs/<id> folders or ids, or 'all'")
    ap.add_argument("--designs", default=str(ROOT / "out_designs"), help="where ids are looked up")
    ap.add_argument("--out", default=str(ROOT / "vidgen" / "out"), help="output folder")
    ap.add_argument("--size", default="1280x720")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--seconds", type=float, default=None, help="clip length (default: fits the timeline)")
    ap.add_argument("--heading", type=float, default=-12.0, help="ship heading on screen, deg clockwise from right")
    ap.add_argument("--target", type=float, default=55.0,
                    help="target bearing relative to the bow, deg clockwise (90 = starboard beam)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--crf", type=int, default=20, help="x264 quality (lower = better, bigger)")
    ap.add_argument("--still", type=float, default=None, help="write one PNG at this time instead of a video")
    ap.add_argument("--jobs", type=int, default=0, help="ships rendered at once (default: one per core)")
    args = ap.parse_args()
    args.w, args.h = (int(v) for v in args.size.lower().split("x"))
    if args.w % 2 or args.h % 2:
        ap.error("--size must be even in both dimensions")
    base = Path(args.designs)
    srcs = sorted(p.parent for p in base.glob("*/sprite.json")) if args.ships == ["all"] else [
        Path(s) if (Path(s) / "sprite.json").exists() else base / s for s in args.ships]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ext = ".png" if args.still is not None else ".mp4"
    todo = []
    for src in srcs:
        if not (src / "sprite.json").exists():
            print(f"skip {src}: no sprite.json", file=sys.stderr)
            continue
        todo.append((src, out / f"{src.name}{ext}"))
    jobs = max(1, min(args.jobs or os.cpu_count() or 1, len(todo)))
    args.quiet = jobs > 1          # interleaved progress lines would be noise; report each ship as it finishes
    if jobs == 1:
        for src, path in todo:
            print(f"wrote {make(src, path, args, still=args.still)}")
        return
    # one ship per process: each render is single-threaded numpy, so ships scale across cores
    from concurrent.futures import ProcessPoolExecutor, as_completed
    with ProcessPoolExecutor(jobs) as pool:
        futs = {pool.submit(make, src, path, args, args.still): src for src, path in todo}
        for f in as_completed(futs):
            print(f"wrote {f.result()}", flush=True)


if __name__ == "__main__":
    main()
