#!/usr/bin/env python3
"""
vidgen: a short top-down gameplay-style video of one exported ship, to judge how the sprites look in motion.

It reads only what the game would: out_designs/<id>/ (sprite.json, hitboxes.json, report.json, hull.png,
height.png, turrets/*.png). The camera looks straight down and follows the ship as it steams through procedural
water at its design speed, with funnel smoke drifting on the wind. The wake (bow-wave sheet, the crest peeling off
the shoulder, divergent waves and the propulsor wash) is baked once per clip by wake.py and only its foam texture
animates, anchored to the water.
The weapons start at rest and then train on a target bearing: by default the starboard bearing the most main mounts
reach (then the most mounts of any kind, then nearest 55 degrees), so cross-deck and end turrets join in. Each mount turns only inside its traverse_deg, as
the game must, and only mounts whose arcs hold the bearing train. Then they fire; torpedo mounts launch fish. Each
gun shot is a muzzle.Shot (muzzle_flash_research.md): a three-part flash in physical units, splatted with analytic
normalisation and averaged over the frame, then a smoke puff whose optical depth is both its opacity and its
shadow, a blast ring on the water that fades as the muzzle stands higher than the blast's length, and the shell on
its ballistic arc (on a slowed clock) with its shadow on the sea.

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
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from shadow import HEIGHT_STEP_M, shadow_mask, sun_offset_px  # noqa: E402

import muzzle  # noqa: E402  (vidgen/muzzle.py)
import wake  # noqa: E402  (vidgen/wake.py)

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
# foam drawing: ridged noise is high along its zero lines, so covering a fraction c of it (noise > 1 - c) draws
# filaments at small c and a sheet with open cells near 1. Lace needs c well under a half; the coverage is
# cap * d^gamma of the density d (LACE), so the densest foam is still lace with holes, never a flat slab, and
# medium densities stay thin. LACE_SOFT is the edge width in noise units.
LACE = {"fresh": (0.55, 1.5), "resid": (0.45, 1.0), "wash": (0.7, 1.0)}
LACE_SOFT = 0.2
LACE_RESID = 0.5          # residual foam's opacity (wake.md 3)


def lace(d, noise, kind):
    cap, gamma = LACE[kind]
    c = cap * np.clip(d, 0, 1) ** gamma
    return np.clip((noise - (1 - c)) / LACE_SOFT + 0.5, 0, 1) * np.clip(1.6 * d, 0, 0.9)


CHURN = np.array([0.26, 0.45, 0.49], np.float32)
FOAM = np.array([0.93, 0.96, 0.97], np.float32)

# guns (muzzle.py, from muzzle_flash_research.md). The flash is drawn in physical units: luminance over the sunlit
# sea's (L_BG, research 4.1) times EXPOSE puts the sea at about the water's own value here.
L_BG = 1500.0             # cd/m^2, sunlit open sea
EXPOSE = 0.18
RH = 0.7                  # relative humidity: hygroscopic smoke and water fog
TARGET_RANGE_M = 12000.0  # sets each gun's elevation (vacuum ballistics; out of reach -> 45 degrees)
# propellant by navy until shipgen exports the ammunition: cordite and RPC/12 are double-base, the rest
# single-base (research 3.1); --propellant overrides it (black_powder for the 1870s ships)
NAVY_PROPELLANT = {"portsmouth": "double_base", "kiel": "double_base"}
SMOKE_NEUTRAL = np.array([0.90, 0.89, 0.86], np.float32)
SMOKE_GAIN = 0.85         # sunlit white smoke against this scene's water and decks
SHELL = np.array([0.25, 0.24, 0.22], np.float32)   # dark painted steel
# shells fly their real path on a slowed clock: at 800-900 m/s they leave the frame in two or three frames, hidden
# by their own flash. Like TRAIN_RATE, readability over fidelity
SHELL_TIME = 0.12
SHELL_SMEAR = 0.5         # the speed smear behind a shell, in frames of its (slowed) motion

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


def auto_target(mounts, prefer=55.0):
    """The starboard bearing most guns can reach: most main mounts, then most mounts of any kind, then nearest
    `prefer`. Arc ends are candidates too, so a cross-deck arc that just reaches past the beam counts at its edge."""
    cands = {float(b) for b in range(1, 180)}
    cands |= {e % 360.0 for m in mounts for a in m["arcs_deg"] for e in a if 0 < e % 360.0 < 180}
    def score(b):
        hit = [m for m in mounts if any(in_arc(b, a) for a in m["arcs_deg"])]
        return (sum(m["kind"] == "main" for m in hit), len(hit), -abs(b - prefer))
    return max(sorted(cands), key=score)


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
            if axis == 0:
                a = (c[2 * r + 1:2 * r + 1 + n] - c[:n]) / (2 * r + 1)
            else:
                a = (c[:, 2 * r + 1:2 * r + 1 + n] - c[:, :n]) / (2 * r + 1)
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


def overlaps(x0, y0, w, h, W, H):
    return x0 < W and y0 < H and x0 + w > 0 and y0 + h > 0


def add_patch(buf, patch, x0, y0):
    """buf += patch with the patch's top-left at (x0, y0), clipped to buf."""
    h, w = patch.shape[:2]
    H, W = buf.shape[:2]
    fx0, fy0, fx1, fy1 = max(0, x0), max(0, y0), min(W, x0 + w), min(H, y0 + h)
    if fx0 < fx1 and fy0 < fy1:
        buf[fy0:fy1, fx0:fx1] += patch[fy0 - y0:fy1 - y0, fx0 - x0:fx1 - x0]


def sample_tile(tile, u, v):
    """Bilinear lookup of a square tile at u (columns, 1-D) and v (rows, 1-D), both in tile widths, wrapping."""
    n = tile.shape[0]
    fu, fv = u * n, v * n
    iu, iv = np.floor(fu).astype(np.int32), np.floor(fv).astype(np.int32)
    wu, wv = (fu - iu).astype(np.float32)[None, :], (fv - iv).astype(np.float32)[:, None]
    iu0, iv0, iu1, iv1 = iu % n, iv % n, (iu + 1) % n, (iv + 1) % n
    r0, r1 = tile[iv0], tile[iv1]
    return ((r0[:, iu0] * (1 - wu) + r0[:, iu1] * wu) * (1 - wv) + (r1[:, iu0] * (1 - wu) + r1[:, iu1] * wu) * wv)


def sample_points(tile, u, v):
    """Bilinear lookup of a square tile at matching arrays u, v (in tile widths, wrapping)."""
    n = tile.shape[0]
    fu, fv = u * n, v * n
    iu, iv = np.floor(fu).astype(np.int32), np.floor(fv).astype(np.int32)
    wu, wv = (fu - iu).astype(np.float32), (fv - iv).astype(np.float32)
    iu0, iv0, iu1, iv1 = iu % n, iv % n, (iu + 1) % n, (iv + 1) % n
    return ((tile[iv0, iu0] * (1 - wu) + tile[iv0, iu1] * wu) * (1 - wv)
            + (tile[iv1, iu0] * (1 - wu) + tile[iv1, iu1] * wu) * wv)


def tonemap(x, knee=0.7):
    """Display values below the knee pass unchanged; above it the luminance rolls off toward 1 and the colour
    partly toward white (at most 75 %, reached 32x over the knee), so a flash never clips per channel to flat yellow (research 8.3)."""
    Y = np.maximum(x @ muzzle.LUM.astype(np.float32), 1e-6)
    Yt = np.where(Y > knee, knee + (1 - knee) * (1 - np.exp(-(Y - knee) / (1 - knee))), Y)
    rgb = x * (Yt / Y)[..., None]
    over = 0.75 * np.clip(np.log2(Y / knee) / 5, 0, 1)[..., None]
    return rgb * (1 - over) + Yt[..., None] * over


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
        # each swell component's phase over the half-res grid is fixed relative to the frame; the camera and time
        # only add a constant, so cos(a + b) = cos a cos b - sin a sin b with cos a, sin a computed once
        Xh, Yh = self.mx[::2, ::2].astype(np.float64), self.my[::2, ::2].astype(np.float64)
        self.swell = []
        for kx, ky, steep, w, ph in self.waves:
            a = kx * Xh + ky * Yh
            k = math.hypot(kx, ky)
            self.swell.append((np.cos(a).astype(np.float32), np.sin(a).astype(np.float32),
                               steep * kx / k, steep * ky / k, kx, ky, w, ph))

    def ripple(self, X, Y, scale, ox, oy):
        """X: the frame's columns, Y: its rows (1-D: the frame is axis-aligned and the camera only shifts it), so
        the lookup is a gather of tile rows, then of columns."""
        n = self.rx.shape[0]
        k = n / (self.ripple_m * scale)
        ix = ((X + ox) * k).astype(np.int32) % n
        iy = ((Y + oy) * k).astype(np.int32) % n
        return self.rx.take(iy, axis=0).take(ix, axis=1), self.ry.take(iy, axis=0).take(ix, axis=1)

    def shade(self, cam, t, wake=None, half=None):
        """wake: (hx, hy, calm) full-frame: the baked wake's slopes, added, and how much its slick flattens the
        ripples (0..1). half: (hx, hy) more slopes on the half-res swell grid (smooth ones; cheaper to add there)."""
        # the swell is smooth, so it's summed at half resolution and upsampled; ripples stay full resolution
        hx = np.zeros(self.swell[0][0].shape, np.float32) if self.swell else np.zeros(self.mx[::2, ::2].shape, np.float32)
        hy = np.zeros_like(hx)
        for ca, sa, ax, ay, kx, ky, w, ph in self.swell:
            b = kx * cam[0] + ky * cam[1] - w * t + ph
            c = ca * np.float32(math.cos(b))
            c -= sa * np.float32(math.sin(b))
            hx += c * np.float32(ax)
            hy += c * np.float32(ay)
        if half is not None:
            hx += half[0]
            hy += half[1]
        hx, hy = upscale(hx, self.W, self.H), upscale(hy, self.W, self.H)
        calm = 1.0
        if wake is not None:
            hx += wake[0]
            hy += wake[1]
            calm = 1 - wake[2]
        X, Y = self.mx[0] + np.float32(cam[0]), self.my[:, 0] + np.float32(cam[1])
        for scale, vel, amp in ((1.0, (1.1, 1.6), 0.10), (0.45, (-0.7, 1.2), 0.07)):
            if self.ripple_m * scale * self.s < 40:
                continue
            rx, ry = self.ripple(X, Y, scale, np.float32(-vel[0] * t), np.float32(-vel[1] * t))
            a = amp * calm
            hx += rx * a
            hy += ry * a
        inv = 1 / np.sqrt(hx * hx + hy * hy + 1)
        L, Hh = self.L.astype(np.float32), self.Hh.astype(np.float32)
        # n = (-hx, -hy, 1) * inv
        diff = np.clip((L[2] - hx * L[0] - hy * L[1]) * inv, 0, 1)
        sky = np.clip((1 - inv) * 6, 0, 0.35)       # tilted facets reflect more sky
        spec = np.clip((Hh[2] - hx * Hh[0] - hy * Hh[1]) * inv, 0, 1) ** 400 * np.float32(0.9)
        d = np.clip((diff - 0.6) / 0.4, 0, 1)
        col = np.empty((self.H, self.W, 3), np.float32)
        for c in range(3):
            v = WATER_DEEP[c] + (WATER_LIT[c] - WATER_DEEP[c]) * d
            v += (WATER_SKY[c] - v) * sky
            v += spec
            col[..., c] = v
        return col


# ---------------------------------------------------------------- the scene
class Mount:
    pass


class Scene:
    def __init__(self, src: Path, W, H, fps, heading, target, seed, seconds=None, propellant=None):
        self.src, self.W, self.H, self.fps = src, W, H, fps
        self.rng = np.random.default_rng(seed)
        self.sprite = json.loads((src / "sprite.json").read_text())
        self.hit = json.loads((src / "hitboxes.json").read_text())
        self.report = json.loads((src / "report.json").read_text())
        navy = self.report["inputs"].get("look", {}).get("navy")
        self.propellant = propellant or NAVY_PROPELLANT.get(navy, "single_base")
        res = self.report["results"]
        self.heading = heading
        if target is None:
            target = auto_target(self.sprite["mounts"])
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
        self._mounts(S0, self.target_bearing)
        self._funnels()
        self.duration = seconds or (self.t_fire + FIRE_S if self.has_guns else 10.0)

        self.water = Water(self.rng, W, H, s, self.C)
        self.dens = Density(W, H)
        self._wake()
        self.foam = Particles((0, 0), 2.5)       # water at rest; the push from the hull dies away
        self.spray = Particles((0, 0), 0.6)      # thrown off the stem, falls back within a second
        self.smoke = Particles(WIND, 1.2)
        self.shots = []                           # muzzle.Shot: flash, smoke puff and shell, all analytic in time
        self.fish = []                            # torpedoes [x, y, vx, vy, t0]
        self.puff_noise = self._noise_tile(128, 0.05)
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
            # calibres can be fractional ("1 x 164.7mm/45"); the type id rounds them ("t1x165L45")
            nums = re.search(r"(\d+)\s*x\s*([\d.]+)\s*mm", desc) or re.search(r"(\d+)x(\d+)", mt.type)
            mt.calibre = float(nums.group(2)) if nums else 100.0
            # a main battery is one gun: several batteries (pre-dreadnought mixed calibres) each fire their own
            # salvos. The type id names the gun and its barrels; batteries differing only in barrels share a beat
            gun = re.search(r"x([\d.]+)(?:L(\d+))?", mt.type)
            mt.gun = (gun.group(1), gun.group(2)) if gun else (mt.calibre, None)
            # the flash, smoke and shell model of this gun (muzzle.py); the bore is a little under the roof
            mt.fx = muzzle.Gun(mt.calibre / 1000, float(mt.gun[1] or 45), self.propellant)
            mt.fxD = muzzle.derive(mt.fx, RH)
            mt.el = muzzle.elevation(mt.fxD["v0"], TARGET_RANGE_M)
            mt.muzzle_h = max(self.freeboard, mt.top_m - 1.5)
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
        # firing schedule: each main battery in full salvos on its own beat (bigger guns load slower), secondaries
        # rippling on their own beat, torpedoes once. The biggest battery opens fire; the others follow within half
        # a second, so mixed batteries don't all flash on one frame
        ev = []
        rng = self.rng
        salvo, first = {}, {}
        mains = sorted({(mt.calibre, mt.gun) for mt in bearing if mt.kind == "main"}, key=lambda g: -g[0])
        for i, (cal, gun) in enumerate(mains):
            salvo[gun] = 1.6 + cal / 250          # smooth: 381 mm -> 3.1 s, 305 -> 2.8, 203 -> 2.4, 120 -> 2.1
            first[gun] = self.t_fire + (rng.uniform(0.2, 0.5) if i else 0.0)
        for mt in bearing:
            n = len(mt.muzzles)
            if mt.kind == "torpedo":
                for i in range(n):
                    ev.append((self.t_fire + 1.0 + 0.3 * i + rng.uniform(0, 0.1), mt, i))
            elif mt.kind == "main":
                t = first[mt.gun]
                while t < self.t_fire + FIRE_S - 0.5:
                    for i in range(n):
                        ev.append((t + rng.uniform(0, 0.12) + 0.04 * i, mt, i))
                    t += salvo[mt.gun]
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

    def _wake(self):
        """Bake the steady wake once (wake.py) and warp it to the frame: the heading is fixed and the camera follows
        the ship, so the wake's envelope stands still on screen. Only the foam's texture moves, anchored to the
        water, so the ship steams through it."""
        t0 = time.perf_counter()
        res, style = self.report["results"], self.report["inputs"].get("style")
        deck = np.array(self.hit["hull"]["points"] if isinstance(self.hit["hull"], dict) else self.hit["hull"])
        L, B = res["length_m"], res["beam_m"]
        self.wl = wl = wake.waterline(deck, style, L)
        self.stem = np.array([deck[:, 0].max(), 0.0])
        W, H, s = self.W, self.H, self.s
        h = math.radians(self.heading)
        c, sn = math.cos(h), math.sin(h)
        # every pixel in ship-local metres
        u, v = np.meshgrid(np.arange(W, dtype=np.float32) + 0.5, np.arange(H, dtype=np.float32) + 0.5)
        dX, dY = u - self.C[0], v - self.C[1]
        self.lx, self.ly = (c * dX + sn * dY) / s, (-sn * dX + c * dY) / s
        pad = 4 / s + 5
        extent = (float(self.lx.min()) - pad, float(self.lx.max()) + pad,
                  float(max(-self.ly.min(), self.ly.max())) + pad)
        dx = max(1.5 / s, L / 400)
        shafts = int(self.report.get("plant", {}).get("shafts", 2) or 2)
        wash = (2.0 if style == "planing" else 1.0) * (0.85 + 0.075 * min(shafts, 4))
        bk = wake.bake(wl, B, res.get("draught_m", self.deck_m), self.speed, extent, dx,
                       cb=res.get("block_coefficient", 0.55), wash=wash)
        self.wake_info = bk.info
        gx, gy = bk.gx, bk.gy
        k = 1 / (s * bk.dx)
        data = (c * k, sn * k, (-c * self.C[0] - sn * self.C[1]) * k - bk.x0 / bk.dx + 0.5,   # + 0.5: PIL samples
                -sn * k, c * k, (sn * self.C[0] - c * self.C[1]) * k - bk.y0 / bk.dx + 0.5)  # at pixel centres

        def warp(a):
            return np.asarray(Image.fromarray(np.ascontiguousarray(a, np.float32), "F").transform(
                (W, H), Image.AFFINE, data, resample=Image.BILINEAR))
        gain = 1.0                       # wake.md suggests 2-3x; the swell here already carries the light
        sx, sy = warp(gx) * gain, warp(gy) * gain
        hx, hy = c * sx - sn * sy, sn * sx + c * sy                     # ship axes -> screen axes
        lim = 0.3 / np.maximum(np.hypot(hx, hy), 0.3)                    # the linear field's steepest bits are a glare
        self.wake_hx, self.wake_hy = hx * lim, hy * lim
        self.wake_fresh, self.wake_resid, self.wake_wash = warp(bk.fresh), warp(bk.resid), warp(bk.wash)
        self.wake_calm = np.clip(self.wake_wash * 0.9, 0, 0.75)

        # foam tiles in ship axes, anchored to the water: streaky along the track for the wash, rounder for crests
        feat = max(0.6, 2.5 / s)         # foam clump size, m: never finer than about two and a half pixels
        n = 512
        self.tile_k = 4 / feat           # tile px per metre
        rng = self.rng

        def tile(lu, lv):
            f = np.fft.fftfreq(n)
            fu, fv = np.meshgrid(f, f)
            out = 0
            for oct_, amp in ((1, 1.0), (2.5, 0.45)):
                spec = np.fft.fft2(rng.standard_normal((n, n))) * np.exp(
                    -((fu * lu * oct_) ** 2 + (fv * lv * oct_) ** 2) * 2 * math.pi ** 2)
                fld = np.real(np.fft.ifft2(spec))
                out = out + amp * fld / fld.std()
            return (out / out.std()).astype(np.float32)     # unit gaussian
        self.tiles_wash = (tile(7, 1.6), tile(7, 1.6))
        self.tiles_crest = (tile(2.5, 1.8), tile(2.5, 1.8))
        self.spray_rate = self.speed * max(0.0, bk.info["Zb"] - 1.0) * 4
        self.wake_info["t_setup"] = time.perf_counter() - t0

    def foam_tex(self, tiles, t, ridged=False):
        """Two water-anchored gaussian tiles crossfaded slowly (cos/sin weights keep it unit gaussian), so foam
        clumps re-form as well as scroll past, mapped to uniform 0..1 so a threshold means coverage. Ridged, it
        peaks along the noise's zero lines: a lacy net of filaments."""
        n = tiles[0].shape[0]
        a = math.radians(self.heading)
        du, dv = self.pos[0] * math.cos(a) + self.pos[1] * math.sin(a), -self.pos[0] * math.sin(a) + self.pos[1] * math.cos(a)
        # bilinear: zoomed in (a destroyer fills the frame), one tile px spans two screen px and nearest sampling
        # showed as stair-stepped clumps
        fu, fv = (self.lx + du) * self.tile_k, (self.ly + dv) * self.tile_k
        iu, iv = np.floor(fu), np.floor(fv)
        wu, wv = (fu - iu).astype(np.float32), (fv - iv).astype(np.float32)
        iu, iv = iu.astype(np.int32) % n, iv.astype(np.int32) % n
        ju, jv = (iu + 1) % n, (iv + 1) % n
        ph = 2 * math.pi * t / 14.0
        tl = tiles[0] * math.cos(ph) + tiles[1] * math.sin(ph)
        g = ((tl[iv, iu] * (1 - wu) + tl[iv, ju] * wu) * (1 - wv) + (tl[jv, iu] * (1 - wu) + tl[jv, ju] * wu) * wv)
        th = np.tanh(0.7978845 * (g + 0.044715 * g * g * g))     # 2 Phi(g) - 1
        return 1 - np.abs(th) if ridged else 0.5 + 0.5 * th

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

    def spawn_spray(self, dt):
        """Spray thrown off the stem when the bow wave stands high (wake.md 3.2 item 5); the wake itself is baked."""
        rng = self.rng
        n = int(rng.poisson(dt * self.spray_rate))
        if not n:
            return
        B = self.report["results"]["beam_m"]
        # thrown from where the bow crest leaves the hull, along the waterline's first stretch: spawned on the
        # centreline with big soft blobs, it read as a fuzzy block ahead of the stem, apart from the crest
        xw = self.wl[:, 0].max() - rng.uniform(0, 0.12, n) ** 1.5 * self.wake_info["L"]
        side = np.where(rng.random(n) < 0.5, 1.0, -1.0)
        p = np.stack([xw, side * (wake.half_breadth(self.wl, xw) + rng.uniform(0, 0.04, n) * B)], 1)
        out = np.stack([rng.uniform(-0.1, 0.25, n), side * rng.uniform(0.2, 0.5, n)], 1) * self.speed
        w, v = self.world_of(p), self.dir_of(out)
        fs = min(1.0, max(0.3, self.wake_info["L"] / 150))
        self.spray.add(x=w[:, 0], y=w[:, 1], vx=v[:, 0], vy=v[:, 1], life=rng.uniform(0.3, 0.8, n),
                       r0=0.3 * fs, r1=rng.uniform(0.6, 1.3, n) * fs, a0=rng.uniform(0.15, 0.35, n))

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
        if mt.kind == "torpedo":
            self.fish.append([muz[0], muz[1], *(self.vel + d * 22.0), self.t])
            self.foam.add(x=muz[0] + rng.normal(0, 1, 12), y=muz[1] + rng.normal(0, 1, 12),
                          vx=d[0] * 4, vy=d[1] * 4, life=2.0, r0=0.5, r1=2.5, a0=0.7)
            return
        D = mt.fxD
        self.shots.append(muzzle.Shot(mt.fx, D, muz, mt.muzzle_h, math.radians(ang), mt.el, self.t, self.vel, WIND,
                                      rng))
        # the blast flattens the sea under the muzzle: a ring of churned water about 2 lam_b across, fading
        # smoothly as the muzzle stands higher above the water than the blast's own length
        lb = D["lam_b"]
        k = int(rng.poisson(math.exp(-(mt.muzzle_h / lb) ** 2) * (16 + 2.5 * lb)))
        if k:
            a = rng.uniform(0, 2 * math.pi, k)
            rv = np.stack([np.cos(a), np.sin(a)], 1) * 2 * lb * rng.uniform(0.6, 1.0, (k, 1)) + d * 1.2 * lb
            self.foam.add(x=muz[0] + d[0] * 0.4 * lb, y=muz[1] + d[1] * 0.4 * lb, vx=rv[:, 0], vy=rv[:, 1],
                          life=rng.uniform(0.8, 1.6, k), r0=1.0, r1=lb / 4 + 1, a0=0.55)

    def step(self, dt):
        self.pos = self.pos + self.vel * dt
        self.t += dt
        self.spawn_spray(dt)
        self.spawn_smoke(dt)
        while self.next_ev < len(self.events) and self.events[self.next_ev][0] <= self.t:
            _, mt, i = self.events[self.next_ev]
            self.fire(mt, i)
            self.next_ev += 1
        for ps in (self.foam, self.spray, self.smoke):
            ps.step(dt)
        for f in self.fish:
            f[0] += f[2] * dt
            f[1] += f[3] * dt
            self.foam.add(x=f[0] + self.rng.normal(0, 0.3, 2), y=f[1] + self.rng.normal(0, 0.3, 2),
                          life=self.rng.uniform(2, 5, 2), r0=0.3, r1=1.0, a0=0.22)
        far = 3 * max(self.W, self.H) / self.s
        self.shots = [sh for sh in self.shots if self._shot_alive(sh, far)]
        self.fish = [f for f in self.fish if np.hypot(f[0] - self.pos[0], f[1] - self.pos[1]) < far]

    def _shot_alive(self, sh, far):
        """A shot lives while its shell is in the air near the frame, or its smoke still shows (research 7.1: until
        the puff's peak optical depth is under 0.01) and hasn't drifted far off."""
        if self.t < sh.flash_end + 0.1:
            return True
        xy, z, _ = sh.shell(sh.t0 + (self.t - sh.t0) * SHELL_TIME)
        if z > 0 and np.hypot(*(xy - self.pos)) < far:
            return True
        p = sh.puff(self.t)
        return p["A"] / (2 * math.pi * p["sh"] ** 2) > 0.01 and np.hypot(*(p["xy"] - self.pos)) < far

    # ----- drawing
    def _noise_tile(self, n, k):
        """Tileable gaussian noise, unit variance, features about 1/k px wide (k in cycles per px)."""
        f = np.fft.fftfreq(n)
        kk = np.hypot(*np.meshgrid(f, f))
        out = 0
        for oct_, amp in ((1, 1.0), (2.3, 0.3)):
            spec = np.fft.fft2(self.rng.standard_normal((n, n))) * np.exp(-(kk / (k * oct_)) ** 2)
            fld = np.real(np.fft.ifft2(spec))
            out = out + amp * fld / fld.std()
        return (out / out.std()).astype(np.float32)

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
        frame = self.water.shade(self.pos, self.t, (self.wake_hx, self.wake_hy, self.wake_calm))

        # baked wake: the wash tints the water to a pale churned slick, then the three foam densities are broken up
        # by water-anchored noise (wake.md 6, shader note), the residual foam at half opacity
        frame += (CHURN - frame) * np.clip(self.wake_wash * 0.9, 0, 0.7)[..., None]
        tw = self.foam_tex(self.tiles_wash, self.t, ridged=True)
        tc = self.foam_tex(self.tiles_crest, self.t, ridged=True)
        f = np.maximum(np.maximum(lace(self.wake_wash, tw, "wash"), lace(self.wake_fresh, tc, "fresh")),
                       LACE_RESID * lace(self.wake_resid, tw, "resid"))
        frame += (FOAM - frame) * f[..., None]
        foam = upscale(self.field(self.foam) + self.field(self.spray), W, H) * self.water.foam_noise
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

        # smoke: shadows on the sea and ship, then the smoke itself, lit from the sun side. Gun smoke is one analytic
        # puff per shot (muzzle.py); its optical depth sets both its opacity and its shadow
        sd = unit(SUN_AZ)
        smoke_d = np.zeros((self.dens.hh, self.dens.hw), np.float32)
        sh = np.zeros_like(smoke_d)
        if len(self.smoke):
            smoke_d = self.field(self.smoke)
            h = float(np.mean(self.smoke.d["h"]))
            o = sun_offset_px(s, SUN_AZ, SUN_EL, h + 4)
            sh += self.field(self.smoke, offset=o)
        gun_tau, gun_col, gun_sh = self._gun_smoke()
        if sh.any() or gun_sh.any():
            dark = 0.35 * (1 - np.exp(-sh)) + 0.45 * (1 - np.exp(-gun_sh))
            frame *= (1 - np.clip(upscale(dark, W, H), 0, 0.6))[..., None]
        self._shells(frame, shadow=True)
        if smoke_d.any():
            base = (0.16, 0.15, 0.15) if self.coal else (0.36, 0.36, 0.37)
            gy, gx = np.gradient(smoke_d)
            light = np.clip(1.0 + 3.0 * (gx * sd[0] + gy * sd[1]) * -1, 0.55, 1.35)
            col = np.array(base, np.float32)[None, None, :] * upscale(light, W, H)[..., None]
            al = np.clip(1 - np.exp(-1.4 * upscale(smoke_d, W, H)), 0, 0.92)[..., None]
            frame = frame * (1 - al) + col * al
        if gun_tau.any():
            al = np.clip(1 - np.exp(-gun_tau), 0, 0.97)
            # lit as a surface whose height goes with log thickness: billows show inside the opaque core too
            gy, gx = np.gradient(box_blur(np.log1p(gun_tau), 2))
            light = np.clip(1.0 - 0.6 * (gx * sd[0] + gy * sd[1]), 0.6, 1.12)
            col = gun_col / np.maximum(gun_tau, 1e-6)[..., None] * (SMOKE_GAIN * light)[..., None]
            col = np.stack([upscale(col[..., c], W, H) for c in range(3)], -1)
            al = upscale(al, W, H)[..., None]
            frame = frame * (1 - al) + col * al

        # the flashes over the smoke (research 7.6: the fireball is in front of its own smoke), and the shells over
        # the flashes: on the slowed clock they're still inside the fireball they really outran, so they show as
        # silhouettes against it, as in high-speed photographs of a shell leaving the muzzle
        self._flashes(frame)
        self._shells(frame)

        # target marker and captions
        frame = np.clip(frame, 0, 1)
        out = (frame * 255).astype(np.uint8)
        hud = self.hud.astype(np.float32) / 255
        ha = hud[..., 3:4]
        out = (out * (1 - ha) + hud[..., :3] * 255 * ha).astype(np.uint8)
        return self._overlay(out)

    def _gun_smoke(self):
        """Every shot's smoke puff splatted at half resolution: optical depth tau (research 5.4's vertical form,
        A / (2 pi sh^2) at the centre), the tau-weighted colour, and the same tau shifted along the sun by the
        puff's height for its shadow. The puff is one gaussian; noise in the puff's own frame, scaled with it,
        breaks it into billows that grow as it spreads (a mean-1 factor, so the puff keeps its A)."""
        hh, hw = self.dens.hh, self.dens.hw
        tau = np.zeros((hh, hw), np.float32)
        col = np.zeros((hh, hw, 3), np.float32)
        shd = np.zeros_like(tau)
        s = self.s
        for shot in self.shots:
            p = shot.puff(self.t)
            if p is None or p["A"] <= 0:
                continue
            cx, cy = self.scr(*p["xy"])
            sig = max(p["sh"], 1.2 / s)                  # at least 0.6 half-res px
            peak = p["A"] / (2 * math.pi * sig * sig)
            # out to where even the billows' bright spots fall under tau 0.003, or the window's edge shows
            r = sig * math.sqrt(2 * math.log(max(3 * peak / 0.003, 2.0))) * s / 2
            hx, hy = (cx - 1) / 2, (cy - 1) / 2
            x0, y0 = int(math.floor(hx - r)), int(math.floor(hy - r))
            xs, ys = np.arange(x0, int(math.ceil(hx + r)) + 1), np.arange(y0, int(math.ceil(hy + r)) + 1)
            off = sun_offset_px(s, SUN_AZ, SUN_EL, p["z"])
            sx0, sy0 = x0 + int(round(off[0] / 2)), y0 + int(round(off[1] / 2))
            if not (overlaps(x0, y0, len(xs), len(ys), hw, hh) or overlaps(sx0, sy0, len(xs), len(ys), hw, hh)):
                continue
            dx = ((xs * 2 + 1 - cx) / s).astype(np.float32)
            dy = ((ys * 2 + 1 - cy) / s).astype(np.float32)
            g = np.float32(peak) * np.exp(
                -(dx[None, :] ** 2 + dy[:, None] ** 2) / np.float32(2 * sig * sig))
            u, v = dx / sig * 0.2 + shot.noise_off[0], dy / sig * 0.2 + shot.noise_off[1]
            g *= np.exp(0.9 * sample_tile(self.puff_noise, u, v) - 0.405)
            # warm near the muzzle for NC powders, fading over about 5 s (research 7.4); water fog is pure white
            tint = SMOKE_NEUTRAL + (shot.D["tint"] - SMOKE_NEUTRAL) * math.exp(-p["age"] / 5.0)
            c = (tint * p["A_p"] + 0.97 * p["A_w"]) / p["A"]
            add_patch(tau, g, x0, y0)
            add_patch(col, g[..., None] * c.astype(np.float32), x0, y0)
            add_patch(shd, g, sx0, sy0)
        return tau, col, shd

    def _shells(self, frame, shadow=False):
        """Each shell in flight: an ogive body (4.5 calibres, the nose's first 40 % tapering) lit by the sun as a
        cylinder, with a short speed smear behind it. Shells under about a pixel wide are drawn at a pixel and
        fainter (opacity by the root of the true over the drawn area). shadow: the shell's shadow on the sea instead,
        moved away from the sun by its height and fading as the sun's disc (0.53 degrees) blurs it past its width."""
        s, H, W = self.s, frame.shape[0], frame.shape[1]
        sd = unit(SUN_AZ)
        cel, sel = math.cos(math.radians(SUN_EL)), math.sin(math.radians(SUN_EL))
        for shot in self.shots:
            tt = (self.t - shot.t0) * SHELL_TIME
            if tt <= 0:
                continue
            xy, z, vel = shot.shell(shot.t0 + tt)
            vel = vel * SHELL_TIME
            if z <= 0:
                continue
            d = shot.gun.d
            strength = 1.0
            if shadow:
                xy = xy + np.array(sun_offset_px(1.0, SUN_AZ, SUN_EL, z))
                strength = 0.5 * d / (d + z * 0.0093)
            cx, cy = self.scr(*xy)
            sp = float(np.hypot(*vel))
            dirv = vel / sp
            R, L = d / 2 * s, 4.5 * d * s
            R_ = max(R, 0.9)
            L_ = max(L, 7 * R_)
            op = math.sqrt(min(1.0, R * L / (R_ * L_))) * strength
            smear = sp * s * min(SHELL_SMEAR / self.fps, self.t - shot.t0)
            back = L_ + smear
            pad = R_ + 2
            tx, ty = cx - dirv[0] * back, cy - dirv[1] * back
            x0, x1 = int(math.floor(min(cx, tx) - pad)), int(math.ceil(max(cx, tx) + pad))
            y0, y1 = int(math.floor(min(cy, ty) - pad)), int(math.ceil(max(cy, ty) + pad))
            x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
            if x0 >= x1 or y0 >= y1:
                continue
            X = np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5 - np.float32(cx)
            Y = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5 - np.float32(cy)
            b0 = -(X * dirv[0] + Y * dirv[1])            # distance behind the nose
            pe = -X * dirv[1] + Y * dirv[0]
            K = min(12, 1 + int(math.ceil(smear / (0.5 * L_))))
            cov = np.zeros_like(b0)
            for k in range(K):
                f = k / (K - 1) if K > 1 else 0.0
                b = b0 - smear * f
                uu = np.clip(b / L_, 0, 1)
                rr = R_ * np.sqrt(np.clip(1 - np.clip((0.4 - uu) / 0.4, 0, 1) ** 2, 0, 1))
                c = np.clip(rr - np.abs(pe) + 0.5, 0, 1) * np.clip(b + 0.5, 0, 1) * np.clip(L_ - b + 0.5, 0, 1)
                np.maximum(cov, c * (1 - 0.85 * f), out=cov)
            a = (cov * op)[..., None]
            win = frame[y0:y1, x0:x1]
            if shadow:
                win *= 1 - a
                continue
            q = np.clip(pe / R_, -1, 1)
            nl = q * (-dirv[1] * sd[0] + dirv[0] * sd[1]) * cel + np.sqrt(1 - q * q) * sel
            lit = 0.35 + 0.9 * np.clip(nl, 0, 1) + 0.2 * np.clip(nl, 0, 1) ** 12
            win *= 1 - a
            win += (SHELL[None, None, :] * lit[..., None]) * a

    def _flashes(self, frame):
        """Muzzle flashes in physical units (research 7.2): each emitter's luminous intensity, averaged over the
        frame interval (4 samples, so a flash shorter than a frame is dimmed, not missed), splatted as an oriented
        gaussian with ANALYTIC normalisation (sigma at least 0.6 px), so the flash keeps its total light at any
        zoom. Then bloom on a compressed copy and a luminance roll-off to white, applied only to what the flash adds."""
        dt = 1.0 / self.fps
        subs = [self.t - dt * (i + 0.5) / 4 for i in range(4)]
        ems = []
        for shot in self.shots:
            if shot.t0 > self.t or shot.flash_end < self.t - dt:
                continue
            acc = {}
            for ts in subs:                              # latest first: its geometry is the one drawn
                for e in shot.emitters(ts):
                    a = acc.setdefault(e["kind"], [0.0, e])
                    a[0] += e["I"] / 4
            ems += [(shot, I, e) for I, e in acc.values() if I > 0]
        if not ems:
            return
        s, H, W = self.s, frame.shape[0], frame.shape[1]
        wins = []
        for shot, I, e in ems:
            su = max(e["a"] * math.cos(shot.el) / 1.5, 0.6 / s)
            sv = max(e["b"] / 1.5, 0.6 / s)
            cx, cy = self.scr(e["c"][0], e["c"][1])
            ext = 3.5 * 1.3 * max(su, sv) * s
            wins.append((shot, I, e, su, sv, cx, cy, ext))
        M = 60                                           # bloom reach (box blur r=17, 3 passes)
        bx0 = max(0, int(min(w[5] - w[7] for w in wins)) - M)
        by0 = max(0, int(min(w[6] - w[7] for w in wins)) - M)
        bx1 = min(W, int(max(w[5] + w[7] for w in wins)) + M + 1)
        by1 = min(H, int(max(w[6] + w[7] for w in wins)) + M + 1)
        if bx0 >= bx1 or by0 >= by1:
            return
        F = np.zeros((by1 - by0, bx1 - bx0, 3), np.float32)
        for shot, I, e, su, sv, cx, cy, ext in wins:
            x0, x1 = max(bx0, int(cx - ext)), min(bx1, int(cx + ext) + 1)
            y0, y1 = max(by0, int(cy - ext)), min(by1, int(cy + ext) + 1)
            if x0 >= x1 or y0 >= y1:
                continue
            dx = (np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5 - np.float32(cx)) / s
            dy = (np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5 - np.float32(cy)) / s
            ca, sa = math.cos(shot.az), math.sin(shot.az)
            u, v = dx * ca + dy * sa, -dx * sa + dy * ca
            if e["kind"] == "secondary":
                # the ragged fireball: the reference's lobes at per-shot phases, plus noise on the edge, and
                # DEPARTURE: a flat-topped profile exp(-q^2 / 2), not a gaussian. Over the sunlit sea a gaussian's
                # tail stays above the display's floor out to about twice the fireball's size, a glowing halo
                ang = np.arctan2(v, u)
                rm = 1 + 0.18 * np.sin(3 * ang + shot.lobes[0]) + 0.12 * np.sin(5 * ang + shot.lobes[1])
                rm = rm * (1 + 0.15 * sample_points(self.puff_noise, u / e["a"] * 0.25 + shot.noise_off[0],
                                                    v / e["b"] * 0.25 + shot.noise_off[1]))
                ra = max(0.8 * e["a"] * math.cos(shot.el), 0.6 / s)
                rb = max(0.8 * e["b"], 0.6 / s)
                q = (u / (rm * ra)) ** 2 + (v / (rm * rb)) ** 2
                w = np.exp(-0.5 * q * q)
                area = 1.2533 * math.pi * ra * rb * 1.03   # integral of exp(-q^2/2) is sqrt(pi/2) pi ra rb
            else:
                w = np.exp(-0.5 * ((u / su) ** 2 + (v / sv) ** 2))
                area = 2 * math.pi * su * sv
            Lpx = w * np.float32(I / area / L_BG * EXPOSE)
            rgb = e["rgb"] / max(float(e["rgb"] @ muzzle.LUM), 1e-3)
            F[y0 - by0:y1 - by0, x0 - bx0:x1 - bx0] += Lpx[..., None] * rgb.astype(np.float32)
        # bloom on a compressed source, or a big flash paints the whole frame (research 7.2 item 6)
        src = F / (1 + F / 6)
        for frac, r in ((0.20, 1), (0.10, 6), (0.05, 17)):
            for c in range(3):
                F[..., c] += frac * box_blur(src[..., c], r)
        sub = frame[by0:by1, bx0:bx1]
        sub += tonemap(sub + F) - tonemap(sub)

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
    sc = Scene(src, args.w, args.h, args.fps, args.heading, args.target, args.seed, args.seconds, args.propellant)
    if not args.quiet:
        i = sc.wake_info
        print(f"  {src.name} wake: Fr_L {i['FrL']:.2f}, Zb {i['Zb']:.1f} m, solve {i['solve'][0]}x{i['solve'][1]}, "
              f"grid {i['grid'][0]}x{i['grid'][1]}, bake {i['t_total'] * 1000:.0f} ms, "
              f"setup {i['t_setup'] * 1000:.0f} ms")
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
    ap.add_argument("--target", type=float, default=None,
                    help="target bearing relative to the bow, deg clockwise (90 = starboard beam); default: the "
                         "starboard bearing the most main guns reach, nearest 55")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--propellant", choices=sorted(muzzle.PROPELLANTS), default=None,
                    help="gun propellant family (default: double_base for portsmouth and kiel looks, else single_base)")
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
