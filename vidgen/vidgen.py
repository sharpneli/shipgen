#!/usr/bin/env python3
"""
vidgen: a short top-down gameplay-style video of one exported ship, to judge how the sprites look in motion.

It reads only what the game would: out_designs/<id>/ (sprite.json, hitboxes.json, report.json, hull.png,
height.png, turrets/*.png). The camera looks straight down and follows the ship as it steams at its design speed
through a spectral sea (ocean.py, ocean-surface-research.md: wind sea and swell for --beaufort, shaded with sky
reflection and sun glint), with funnel smoke drifting on the wind. The wake (bow-wave sheet, the crest peeling off
the shoulder, divergent waves and the propulsor wash) is baked once per clip by wake.py and only its foam texture
animates, anchored to the water.
The weapons start at rest and then train on a target bearing: by default the starboard bearing the most main mounts
reach (then the most mounts of any kind, then nearest 55 degrees), so cross-deck and end turrets join in. Each mount turns only inside its traverse_deg, as
the game must, and only mounts whose arcs hold the bearing train. Then they fire; torpedo mounts launch fish. Each
gun shot is a muzzle.Shot (muzzle_flash_research.md): a three-part flash in physical units averaged over the frame
(the fireball a burning temperature field, the flash lighting the deck and smoke around it), then a smoke puff whose
optical depth is both its opacity and its shadow (sometimes with a smoke ring; a later shot's jet shoves older smoke
along its bore), and the shell on its ballistic arc (on a slowed clock) with its shadow on the sea. Each mount's
salvo is a muzzle.Blast on the water (muzzle_blast_water-vfx.md): a dark leading edge racing out at the speed of
sound, a frosted disc behind it, offset along the bore, and scour foam and spray near the muzzle.

With --explode a magazine goes up (magazine.py, magazine_explosion.md): a hit on the mount over it, the jet phase
(flame jets from the gun ports, hood, hatches, scuttles and the machinery rooms' vents beside it, then the
barbette), the fireball, debris, the thrown gunhouse, the blast on the water, stem fires and boiler steam, all sized
from the magazine's contents in hitboxes.json. The smoke goes into the same optical-depth field as the funnel and
gun smoke, lifted up the screen by its height (the research's oblique projection); the fire glows through it. The
ship stops firing and loses way. The stern breaking off and the sinking are for later.

Shadows follow README "Shadows": the height map is marched toward the sun (shadow.shadow_mask, the reference
implementation), and turret shadows are the turret sprites in black, offset by (top_m - deck_m) / tan(elevation)
and kept where the height map is below top_m.

Several ids joined by '+' are a line of battle in one clip (Ship per ship, Scene for the shared sea, smoke and
camera): line ahead on one course and speed, so every ship stands still on screen and their hulls, height maps,
shadows and wakes are merged once into the scene's layers.

Everything is drawing; nothing here feeds back into the design. Particle and wave numbers are tuned by eye.

    ~/.venv/bin/python vidgen/vidgen.py bismarck                  # -> vidgen/out/bismarck.mp4
    ~/.venv/bin/python vidgen/vidgen.py all --size 1920x1080
    ~/.venv/bin/python vidgen/vidgen.py kongo --target 300 --still 9.5   # one PNG frame instead of a video
    ~/.venv/bin/python vidgen/vidgen.py bismarck --explode Y             # -> vidgen/out/bismarck_explode_Y.mp4
    ~/.venv/bin/python vidgen/vidgen.py bismarck --explode B --tier column
    ~/.venv/bin/python vidgen/vidgen.py bismarck --beaufort 5 --swell 2,12,270   # rougher sea, westerly swell
    ~/.venv/bin/python vidgen/vidgen.py invincible+invincible --fire 20  # a line of battle -> invincible+invincible.mp4
    ~/.venv/bin/python vidgen/vidgen.py lion --size 1920x1080 --scale 0.25 --fire 20   # one ship at strategic scale
    ~/.venv/bin/python vidgen/vidgen.py lion+lion+lion+tiger_1914 --size 1920x1080 --zoom  # one ship -> squadron -> strategic

Needs numpy, pillow and imageio-ffmpeg (pip install imageio-ffmpeg; it bundles an ffmpeg binary).
"""
from __future__ import annotations

import os
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):   # one thread each: the sea's matmuls are
    os.environ.setdefault(_v, "1")                                           # small, and clips render in parallel

import argparse
import json
import math
import re
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from shadow import HEIGHT_STEP_M, shadow_mask, sun_offset_px  # noqa: E402

import magazine  # noqa: E402  (vidgen/magazine.py)
import muzzle  # noqa: E402  (vidgen/muzzle.py)
import ocean  # noqa: E402  (vidgen/ocean.py)
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
# a line of battle (several ships in one clip): ships in line ahead, centre to centre about two cables (400 yd, the
# usual close order), on one course at the slowest ship's speed. Each ship after the lead opens fire a random
# moment after it's on target, so sister ships don't flash in lockstep
LINE_SPACING = 366.0
LINE_LAG = (0.3, 1.5)

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
LACE_ZOOM = (0.4, 1.5)    # px/m: lace_k's ends (the line-of-battle clips, ~1.8, keep their full lace)


def lace(d, noise, kind, k=1.0):
    """Foam drawn as lace: noise (uniform 0..1) over 1 - c. k < 1 blends it toward its mean coverage c, for a zoom
    where the real foam texture is far under a pixel (lace_k); k = 0 never reads the noise."""
    cap, gamma = LACE[kind]
    c = cap * np.clip(d, 0, 1) ** gamma
    op = np.clip(1.6 * d, 0, 0.9)
    if k <= 0:
        return c * op
    f = np.clip((noise - (1 - c)) / LACE_SOFT + 0.5, 0, 1)
    return (f if k >= 1 else c + (f - c) * np.float32(k)) * op


def lace_k(s):
    """How much of the foam's lace texture shows at s px/m: all of it from LACE_ZOOM[1] in, none (its mean coverage,
    a smooth bright stripe, as a wake reads from altitude) from LACE_ZOOM[0] out; smoothstep in log s between. The
    texture is never drawn finer than ~2.5 px, so from high up it was coarse clumps, a dashed confetti ribbon."""
    a, b = (math.log(v) for v in LACE_ZOOM)
    return smoothstep((math.log(s) - a) / (b - a))


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
SMOKE_COAL = (0.16, 0.15, 0.15)
SMOKE_OIL = (0.36, 0.36, 0.37)
SMOKE_MAX = 0.9           # densest smoke still lets a little through, funnel and gun alike
GUN_SMOKE_VIS = 0.07      # gun smoke's drawn optical depth against the research's (the look, not visibility)
# zoomed out, a puff is a few pixels beside a ship a few pixels wide, and the puff is what says she's firing: its
# drawn share rises smoothly toward the research's as (S_REF / s)^GUN_SMOKE_ZOOM (never past it). Close up the
# deck must show through; that's the only reason for the cut
GUN_SMOKE_ZOOM = 0.5
SUB_PUFFS = 14            # clumps a shot's smoke puff is drawn as
SUB_SIGMA = 0.45          # each clump's spread against the puff's
RING_BLOBS = 10           # blobs a smoke ring is drawn as
RING_CORE = 0.3           # a ring's core spread against its radius
RING_VIS = 0.3            # a ring's drawn optical depth against the puff's GUN_SMOKE_VIS: a ring mixes out fast
                          # (DEPARTURE: at the research's share it drew as an opaque white pill)
SHELL = np.array([0.25, 0.24, 0.22], np.float32)   # dark painted steel
# shells fly their real path on a slowed clock: at 800-900 m/s they leave the frame in two or three frames, hidden
# by their own flash. Like TRAIN_RATE, readability over fidelity
SHELL_TIME = 0.132
SHELL_SMEAR = 0.5         # the speed smear behind a shell, in frames of its (slowed) motion
# the blast on the water (muzzle.Blast): ripple amplitude 1 + BLAST_FROST frost - BLAST_LEAD lead (research 3.2).
# DEPARTURE: the research's 2.5 made the frost glitter like whitecaps here (vidgen's ripples carry the sun glint);
# the silvery look comes mostly from the sheen instead
BLAST_FROST = 0.8
BLAST_LEAD = 0.7
TAU_FROST_VIS = muzzle.TAU_FROST
BLAST_FOAM = 0.6          # scour foam's density drawn (DEPARTURE: at full, the jet's lobe was a field of confetti)
BLAST_SHEEN = 0.35        # the frost's silvery sky sheen, at full frost
BLAST_DARK = 0.22         # how much the leading edge darkens the sea
# the secondary fireball as a temperature field (Scene._fireball; DEPARTURES there)
FIREBALL_CORE = 0.05      # the core's temperature over the emitter's
FIREBALL_FALL = 0.25      # temperature lost toward the edge (q = 1): luminance falls ~100x there
FIREBALL_STIR = 0.08      # +- share of T the turbulence stirs
FIREBALL_R = 1.4          # the gas reaches this far in units of the fireball's radius
# the flash as a light on the scene (Scene._flash_light)
E_SUN = 7.0e4             # lux on a level surface from the sun at SUN_EL (L_BG's sea at albedo ~0.07)
FLASH_WRAP = 0.3          # rough and vertical faces turned toward the flash, as a share of the ground distance
FLASH_LIGHT_MAX = 1.0     # at most this many times the sun's light
# zoomed out, a flash is a few pixels and only as wide as the hull: its bloom grows (the 6 and 17 px halos gain
# 0.6 and 0.3 of FLASH_GLARE) smoothly from S_REF out to GLARE_FULL_S px/m, so a salvo still flares from high up.
# A look, like the lens's own bloom; the light itself is unchanged
FLASH_GLARE = 1.0
GLARE_FULL_S = 0.25

# magazine explosions (magazine.py, from magazine_explosion.md)
EXPLODE_AFTER = 4.0       # default: the hit lands this long after the first salvo
EXPLODE_TAIL = 40.0       # the clip runs this long past the main event (the cap mushrooms by ~15 s, research 6)
EXPLODE_FIT = 0.34        # the ship's share of the frame width in an explosion clip, so the column and cap fit
STOP_TAU = 12.0           # s: the ship loses way after the main event (until the sinking clip takes over)
BREAK_STOP_TAU = 4.0      # s: with --sink, the halves coast to a stop this fast (an open section is a huge drag)
# an explosion clip's camera (user, 2026-10-08): the ship's centre on screen, as shares of the frame. Up and left
# while the guns fire, so their blasts have the right and the bottom of the frame; low and a little left for the
# explosion, so the column and the cap rise into the empty top; then a little toward the middle for the sinking.
# The pans are smootherstep, so the camera starts and stops without a jolt (my picks by eye)
CAM_GUNS = (0.30, 0.36)
CAM_BLAST = (0.43, 0.68)
CAM_SINK = (0.48, 0.58)
CAM_PAN_BLAST = (0.3, 3.0)  # s: the pan to the explosion ends this long before the main event, and how long it takes
CAM_PAN_SINK = (20.0, 10.0)  # s: the pan to the sinking starts this long after the main event, and how long it takes
CAM_MARGIN = 8            # px kept around the window, so the blast's camera shake moves it rather than smearing
# vertical effects are drawn in the research's oblique "3/4" projection (3.1): height above the source lifts a
# puff up the screen by K_OBL z', with the soft compression z' = H_C (1 - e^(-z/H_C)), while ships and water stay
# top-down and shadows use the true height. DEPARTURE: z is measured from the source's height (the deck), not the
# sea, so smoke still leaves from where it's made; funnel and gun smoke barely rise and stay unlifted
K_OBL = 0.6
H_C = 450.0
H_CAM = 800.0             # pseudo-perspective scale 1 + z / H_CAM for flying solids (sinking_foam.md's)
SMOKE_SOOT = (0.14, 0.12, 0.10)   # explosion smoke: soot from what the fire picks up (oil, paint, cork), research 1.2
STEAM = SMOKE_NEUTRAL * 0.97 * SMOKE_GAIN
FIRELIT = np.array([0.30, 0.12, 0.03], np.float32)   # smoke lit orange from inside and below (research 3.3)
I_REF = 3.0e4             # fire light normalisation (the reference's)
EXPLODE_VIS = 0.4         # explosion smoke's drawn optical depth against the reference's KAPPA (a look, as for guns)
CLUMPS = 4                # clumps an explosion puff is drawn as (like the gun smoke's SUB_PUFFS)
CLUMP_SIGMA = 0.5         # each clump's spread against the puff's
CLUMP_SPREAD = 0.75       # the clumps' scatter about the puff's centre, in its spread
EX_RELIEF = 6.0           # the explosion smoke's coarse relief lighting gain
FIRE_SKIN = 0.8           # how hard the cooled smoke over a pixel dims its fire (power of the hot share)
FIRE_STIR = 0.14          # +- share of the fire's temperature the noise stirs (luminance is steep in it)
FIRE_NOISE_M = 22.0       # m: the stirring noise's feature size
SPARK = muzzle.bb_rgb(1800) / float(muzzle.bb_rgb(1800) @ muzzle.LUM)
DEBRIS = np.array([0.06, 0.055, 0.05], np.float32)

# smoke's relief lighting in metres, so it doesn't change with the zoom: tuned on half-res pixels at S_REF px/m
# (Bismarck at 720p), a blur of 2 pixels and a light of 1 - 2 slope per pixel
S_REF = 4.0
LIGHT_BLUR_M = 4.0 / S_REF
LIGHT_SLOPE = 2.0 / S_REF

PLUME_LIFE = (80.0, 100.0)    # s: funnel smoke puffs' lives (Plume)
PLUME_GROW_S = 7.0
PLUME_SPREAD = 1.0        # m/s
# the soot's drawn share falls as e^(-age / fade), fade = PLUME_FADE_S (S_REF / s)^PLUME_FADE_ZOOM (8 s close up,
# ~80 s at 0.25 px/m). A look, like GUN_SMOKE_VIS: kept whole, the funnels' output (tuned for puffs gone in 7 s)
# laid a black slab over the sea astern close up, while from high up the long trail is what shows her course and
# the wind. The game's visibility should keep the soot whole
PLUME_FADE_S = 8.0
PLUME_FADE_ZOOM = 0.83

BUCKETS = [1, 2, 4, 8, 16, 32, 64]   # blur radii (half-res px) the particle splats are sorted into
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


def smootherstep(x):
    """Smoothstep with zero acceleration at both ends too: a camera pan that starts and stops without a jolt."""
    x = min(1.0, max(0.0, x))
    return x * x * x * (x * (6 * x - 15) + 10)


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
    FIELDS = ("x", "y", "vx", "vy", "age", "life", "r0", "r1", "a0", "h", "coal")

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


class Plume(Particles):
    fade_s = 8.0          # the scene sets it by its zoom (plume_fade)

    """Funnel smoke as a plume that keeps its soot: each puff's radius grows as r^2 = r0^2 + (r1^2 - r0^2) a /
    PLUME_GROW_S (eddy diffusion; the old puffs reached r1 at about that age) and keeps growing, and its peak falls
    as 1/r^2, so its optical depth is kept while it spreads (less a fade drawn by zoom, PLUME_FADE_S). Further out the spread is linear in age, PLUME_SPREAD m/s
    (Pasquill class D: sigma_y ~ 0.07 x, x the ~15 m/s she makes through the air), so the plume opens into a fan; it fades out only over its long life. A plume then
    trails downwind for a kilometre or so, as coal smoke did (the old puffs simply faded within 5-9 s, a short dark
    lump over the ship from high up). Near the funnels it's drawn about as before."""

    def _r2(self):
        d = self.d
        return d["r0"] ** 2 + (d["r1"] ** 2 - d["r0"] ** 2) * d["age"] / PLUME_GROW_S + (PLUME_SPREAD * d["age"]) ** 2

    def radius(self):
        return np.sqrt(self._r2())

    def opacity(self, fade_in=0.08):
        d = self.d
        u = np.clip(d["age"] / d["life"], 0, 1)
        r2 = self._r2()
        r2_1 = d["r0"] ** 2 + (d["r1"] ** 2 - d["r0"] ** 2) / PLUME_GROW_S      # at 1 s, where the peak was a0
        return (d["a0"] * np.clip(d["age"] / fade_in, 0, 1) * np.minimum(1.0, r2_1 / r2)
                * np.exp(-d["age"] / self.fade_s) * (1 - u) ** 1.5)


class Density:
    """Splats soft blobs into a buffer `res` full-res px per cell (2: half resolution).

    The default (sinkvid's own clips) is the original look: each blob lands in the blur bucket nearest its radius and
    keeps its peak w. Scenes that zoom out (vidgen, `conserve=True`) need blobs to keep their optical depth at any
    scale instead, so a blob's integral PEAK w 2 pi sigma^2 (sigma = SIG r_px: on average what the buckets drew,
    measured) is what's kept:
      - a blob smaller than the finest blur is drawn at that blur and proportionally fainter, not swollen at full
        strength (spray off the stem drew as a disc wider than the bow from high up);
      - a blob between two blurs is split between them in log sigma, so its drawn size grows smoothly with the
        zoom and its age instead of doubling at a bucket edge;
      - each blur level is worked out only in the window its blobs reach, so a full-res buffer costs about what
        the half-res one did."""
    SIG = 1.07            # the drawn sigma against the radius passed, and the peak against w, as the buckets
    PEAK = 0.84           # drew them on average (so a zoomed-in scene keeps its look)

    def __init__(self, W, H, res=2, conserve=False):
        self.res, self.conserve = res, conserve
        self.hw, self.hh = W // res, H // res
        self.shape = (self.hh + 2 * PAD, self.hw + 2 * PAD)
        # blur levels in buffer cells: level 0 is the buffer's own grid at radius 1; level k >= 1 is a grid f = 2^(k-1)
        # coarser at radius 2. sigma^2 = r(r+1) for three box passes
        self.levels = [(1, 1)] + [(2 ** (k - 1), 2) for k in range(1, 8 if res == 1 else 7)]
        self.lsig = np.log([f * math.sqrt(r * (r + 1)) for f, r in self.levels])

    def render(self, px, py, r_px, w):
        """px, py: full-res screen px; r_px: full-res radius; w: peak opacity. Returns the field at the buffer's
        resolution. A bucket of blur radius R is splatted into a grid f = R/2 times coarser and blurred there with
        radius 2, then upsampled: the big soft buckets cost no more than the small ones."""
        if self.conserve:
            return self._render_conserve(px, py, r_px, w)
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

    def _render_conserve(self, px, py, r_px, w):
        g = self.res
        out = np.zeros((self.hh, self.hw), np.float32)
        if len(px) == 0:
            return out
        px, py, r_px, w = (np.asarray(a, np.float32) for a in (px, py, r_px, w))
        sig = np.maximum(self.SIG * r_px / g, 1e-3)              # in buffer cells
        mass = w * (self.PEAK * 2 * math.pi) * sig * sig         # the blob's integral, kept at every level
        x, y = (px + 0.5) / g - 0.5, (py + 0.5) / g - 0.5        # buffer cell coordinates
        L = self.lsig
        k = np.clip(np.searchsorted(L, np.log(sig)) - 1, 0, len(L) - 2)
        t = np.clip((np.log(sig) - L[k]) / (L[k + 1] - L[k]), 0, 1).astype(np.float32)
        for lv, (f, r) in enumerate(self.levels):
            share = np.where(k == lv, 1 - t, 0) + np.where(k + 1 == lv, t, 0)
            reach = 3 * r + 2
            # blobs that can touch the buffer from this level
            mx = (x + 0.5) / f - 0.5
            my = (y + 0.5) / f - 0.5
            gw, gh = -(-self.hw // f), -(-self.hh // f)
            m = (share > 0) & (w != 0) & (mx > -reach) & (my > -reach) & (mx < gw + reach) & (my < gh + reach)
            if not m.any():
                continue
            mx, my, mm = mx[m], my[m], (mass[m] * share[m]) / (f * f)
            i0 = max(int(math.floor(mx.min())) - reach, -reach)
            j0 = max(int(math.floor(my.min())) - reach, -reach)
            i1 = min(int(math.floor(mx.max())) + reach + 2, gw + reach)
            j1 = min(int(math.floor(my.max())) + reach + 2, gh + reach)
            nw, nh = i1 - i0, j1 - j0
            ix, iy = np.floor(mx).astype(int), np.floor(my).astype(int)
            fx, fy = mx - ix, my - iy
            ix -= i0
            iy -= j0
            buf = np.zeros(nh * nw, np.float32)
            for ox, oy, ww in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)),
                               (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
                buf += np.bincount((iy + oy) * nw + ix + ox, mm * ww, nh * nw).astype(np.float32)
            blurred = box_blur(buf.reshape(nh, nw), r)
            if f > 1:
                blurred = np.asarray(Image.fromarray(blurred, "F").resize((nw * f, nh * f), Image.BILINEAR))
            X0, Y0 = i0 * f, j0 * f
            a0, b0 = max(0, X0), max(0, Y0)
            a1, b1 = min(self.hw, X0 + blurred.shape[1]), min(self.hh, Y0 + blurred.shape[0])
            if a0 < a1 and b0 < b1:
                out[b0:b1, a0:a1] += blurred[b0 - Y0:b1 - Y0, a0 - X0:a1 - X0]
        return out


def upscale(a, W, H):
    if a.shape == (H, W):
        return a.astype(np.float32)
    return np.array(Image.fromarray(a.astype(np.float32), "F").resize((W, H), Image.BILINEAR))


# ---------------------------------------------------------------- water
def compass(deg):
    """Unit vector in screen-world axes toward a compass bearing (north is screen up)."""
    r = math.radians(deg)
    return np.array([math.sin(r), -math.cos(r)])


SEA_WIND = float(np.hypot(*WIND))   # m/s: the waves' wind by default is the smoke's (about Beaufort 3)
SWELL = (1.0, 10.0, 240.0)          # Hs m, Tp s, from (compass, north = screen up): a moderate swell across the wind
WATER_BODY = (0.0005, 0.0056, 0.0102)  # ocean.py's water body, set so the sea's mean matches the old palette's


class Water:
    """The open sea (ocean.py: a spectral wind sea and swell, shaded with sky, body and sun glint), with the baked
    wake's and the blasts' slopes added: it's a linear surface, so they just sum."""

    def __init__(self, rng, W, H, s, C, beaufort=None, swell=SWELL):
        self.W, self.H, self.s = W, H, s
        u, v = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
        self.mx, self.my = (u - C[0]) / s, (v - C[1]) / s       # metres from the ship's centre
        # the old swell and ripple tile's draws (now a fixed count: a zoom's scenes at every scale must draw the same
        # numbers, so their smoke and salvos match)
        rng.uniform(size=(14, 3))
        rng.standard_normal((256, 256))
        U = SEA_WIND if beaufort is None else ocean.beaufort_u(beaufort)
        wdir = WIND / np.hypot(*WIND)
        hs, tp, frm = swell
        sea = ocean.Sea(wdir * U, (hs, tp, -compass(frm)))
        L = (math.cos(math.radians(SUN_EL)) * unit(SUN_AZ)[0], math.cos(math.radians(SUN_EL)) * unit(SUN_AZ)[1],
             math.sin(math.radians(SUN_EL)))
        self.sea = ocean.Ocean(W, H, s, C, sea, L, body=WATER_BODY)
        noise = np.random.default_rng(4241).standard_normal((H // 8 + 2, W // 8 + 2)).astype(np.float32)
        self.foam_noise = np.clip(0.75 + 0.35 * upscale(box_blur(noise, 1), W, H), 0.3, 1.2)

    def shade(self, cam, t, wake=None, half=None, rough=None):
        """wake: (hx, hy, calm) full-frame: the baked wake's slopes, added, and how much its slick flattens the
        short waves (0..1). half: (hx, hy) more slopes on the half-res grid (smooth ones), added. rough: (ripples,
        sheen) full-frame, from the gun blasts: a multiplier on the short waves, and a signed sheen (+ the frost's
        silvery sky, - the leading edge's dark)."""
        calm = None
        if wake is not None and np.ndim(wake[2]):
            calm = 1 - wake[2]
        if rough is not None:
            calm = rough[0] if calm is None else calm * rough[0]
        hx, hy, h, vx, vy = self.sea.slopes(t, cam, calm)
        if half is not None:
            hx += upscale(half[0], self.W, self.H)
            hy += upscale(half[1], self.W, self.H)
        if wake is not None:
            hx += wake[0]
            hy += wake[1]
        col = self.sea.display(self.sea.radiance(hx, hy, h, vx, vy))
        if rough is not None:
            sh = rough[1]
            up = np.maximum(sh, 0)[..., None]
            col += (WATER_SKY - col) * up
            col *= (1 + np.minimum(sh, 0))[..., None]
        return col


# ---------------------------------------------------------------- the scene
class Mount:
    pass


class Pose:
    """The ship's pose for magazine.Blast: ship-local <-> world, its velocity, and whether a world point is over
    the hull (the hull layer's alpha: the camera follows the ship and the heading is fixed, so it stands still)."""

    def __init__(self, sc):
        self.sc = sc

    @property
    def vel(self):
        return self.sc.vel

    def world(self, xy):
        return self.sc.world_of(xy)

    def dirw(self, v):
        return self.sc.dir_of(v)

    def local(self, w):
        a = math.radians(self.sc.heading)
        R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
        return (np.asarray(w, float) - self.sc.pos) @ R

    def deck(self, local3):
        """Ship-local (n, 3) points on the ship -> world (n, 3), and whether each is still above water: after a
        break the wreck's pieces carry them."""
        local3 = np.atleast_2d(np.asarray(local3, float))
        sc = self.sc
        if not sc.broken():
            return np.c_[self.world(local3[:, :2]), local3[:, 2]], np.ones(len(local3), bool)
        wr = sc.wreck
        x, y, z = (local3[:, i].astype(np.float32) for i in range(3))
        X, Y, Z = wr.tf(x, y, z, wr.tl.label(x, y, z), wr.tl.poses(wr.t))
        return np.c_[X + sc.pos_b[0], Y + sc.pos_b[1], Z], Z > 0.5

    def on_hull(self, w):
        w = np.atleast_2d(w)
        x, y = self.sc.scr(w[:, 0], w[:, 1])
        xi, yi = np.round(x).astype(int), np.round(y).astype(int)
        H, W = self.sc.hull_alpha.shape
        ok = (xi >= 0) & (yi >= 0) & (xi < W) & (yi < H)
        out = np.zeros(len(w), bool)
        out[ok] = self.sc.hull_alpha[yi[ok], xi[ok]] > 0.5
        return out


class Ship:
    """One ship of the scene: its exported design, its layers on the scene's canvas, its mounts and firing schedule,
    its funnels and its baked wake. The ships of a line steam on one course at one speed, so each stands still on
    screen at its own anchor C: the scene's centre plus its station `off` (metres along the heading)."""

    def __init__(self, src: Path, propellant=None):
        self.src = src
        self.sprite = json.loads((src / "sprite.json").read_text())
        self.hit = json.loads((src / "hitboxes.json").read_text())
        self.report = json.loads((src / "report.json").read_text())
        self.name = self.sprite.get("name", self.sprite["id"])
        navy = self.report["inputs"].get("look", {}).get("navy")
        self.propellant = propellant or NAVY_PROPELLANT.get(navy, "single_base")
        res = self.report["results"]
        self.L, self.B = res["length_m"], res["beam_m"]
        self.speed_kn = float(self.report["inputs"].get("speed_kn", 20))
        self.deck_m = self.sprite["shadow"]["deck_m"]
        self.freeboard = self.hit["vertical"].get("freeboard", self.deck_m)
        self.off = 0.0

    def place(self, sc):
        """Its anchor on the scene's canvas, once the scene's scale and centre are set."""
        self.sc = sc
        self.C = sc.C + unit(sc.heading) * (self.off * sc.s)

    @property
    def pos(self):
        """Its centre in world metres."""
        return self.sc.pos + unit(self.sc.heading) * self.off

    def to_screen(self, m):
        """Ship-local metres (+x bow, +y starboard) -> screen px."""
        return self.C + rot(np.asarray(m, float), self.sc.heading) * self.sc.s

    def world_of(self, m):
        """Ship-local metres (one point or an (n, 2) array) -> world metres."""
        return self.pos + self.sc.dir_of(m)

    def layers(self, S0):
        """Its hull sprite (RGBA) and height map (PIL "L") on the scene's canvas."""
        sc = self.sc
        k = sc.s / S0
        hull = Image.open(self.src / self.sprite["layers"]["hull"]).convert("RGBA")
        height = Image.open(self.src / self.sprite["shadow"]["height_map"]).convert("L")
        size = (max(1, round(hull.width * k)), max(1, round(hull.height * k)))
        origin = np.array(self.sprite["origin_px"]) * k
        if k < 1:
            hull = hull.resize(size, Image.LANCZOS)
            height = height.resize(size, Image.BOX)
        return np.asarray(sc._affine(hull, origin, Image.BICUBIC, self.C)), sc._affine(height, origin, Image.BILINEAR,
                                                                                         self.C)

    def build_mounts(self, S0, target, lag=0.0):
        """Its mounts, trained on the target bearing, and its firing schedule (self.events), opening `lag` s after
        the last mount is on target."""
        sc = self.sc
        k = sc.s / S0
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
            mt.ship = self
            mt.id, mt.kind, mt.type = m["id"], m["kind"], m["type"]
            mt.img, desc = types[m["type"]]
            mt.pos_m = np.array(m["pos_m"], float)
            mt.screen = self.to_screen(mt.pos_m)
            mt.top_m = m["top_m"]
            # turret shadows are swept from the barbette top (the height map under the pivot) up to the roof, and
            # measured from the deck the mount stands on (a low percentile of the height map around it, sea left
            # out), not the main deck: a raised forecastle turret would otherwise cast too long
            px, py = int(round(mt.screen[0])), int(round(mt.screen[1]))
            Hh, Hw = sc.Hs.shape
            inside = 0 <= px < Hw and 0 <= py < Hh
            mt.base_h = min(float(sc.Hs[py, px]), mt.top_m) if inside else self.deck_m
            r = max(2, int(mt.img.width * 0.35))
            patch = sc.Hs[max(0, py - r):py + r, max(0, px - r):px + r]
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
            # gun ports, where each barrel leaves the gunhouse's face (magazine.py's jet openings)
            body = np.array(loc["body"]) if loc.get("body") else None
            front = float(body[:, 0].max()) if body is not None else 0.0
            mt.ports = [(front, float(m[1])) for m in mt.muzzles]
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
        self.t_fire = max((mt.train[1] for mt in bearing), default=REST_S) + SETTLE_S + lag
        # firing schedule: each main battery in full salvos on its own beat (bigger guns load slower), secondaries
        # rippling on their own beat, torpedoes once. The biggest battery opens fire; the others follow within half
        # a second, so mixed batteries don't all flash on one frame
        ev = []
        rng = sc.rng
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
                while t < self.t_fire + sc.fire_s - 0.5:
                    for i in range(n):
                        ev.append((t + rng.uniform(0, 0.12) + 0.04 * i, mt, i))
                    t += salvo[mt.gun]
            else:
                period = 0.7 + mt.calibre / 180
                t = self.t_fire + 0.3 + rng.uniform(0, period)
                while t < self.t_fire + sc.fire_s - 0.3:
                    for i in range(n):
                        ev.append((t + 0.05 * i, mt, i))
                    t += period * rng.uniform(0.85, 1.15)
        self.events = ev

    def build_funnels(self):
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

    def bake_wake(self):
        """Bake its steady wake (wake.py) over the whole canvas and warp it there: (slopes x, y in screen axes,
        fresh, residual and wash foam densities)."""
        sc = self.sc
        res, style = self.report["results"], self.report["inputs"].get("style")
        deck = np.array(self.hit["hull"]["points"] if isinstance(self.hit["hull"], dict) else self.hit["hull"])
        L, B = res["length_m"], res["beam_m"]
        self.wl = wl = wake.waterline(deck, style, L)
        self.stem = np.array([deck[:, 0].max(), 0.0])
        W, H, s = sc.W, sc.H, sc.s
        h = math.radians(sc.heading)
        c, sn = math.cos(h), math.sin(h)
        # every pixel in this ship's local metres: the scene's, less its station along the heading
        lx = sc.lx - np.float32(self.off)
        pad = 4 / s + 5
        extent = (float(lx.min()) - pad, float(lx.max()) + pad,
                  float(max(-sc.ly.min(), sc.ly.max())) + pad)
        dx = max(1.5 / s, L / 400)
        shafts = int(self.report.get("plant", {}).get("shafts", 2) or 2)
        wash = (2.0 if style == "planing" else 1.0) * (0.85 + 0.075 * min(shafts, 4))
        bk = wake.bake(wl, B, res.get("draught_m", self.deck_m), sc.speed, extent, dx,
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
        self.spray_rate = sc.speed * max(0.0, bk.info["Zb"] - 1.0) * 4
        return hx * lim, hy * lim, warp(bk.fresh), warp(bk.resid), warp(bk.wash)

    def spawn_spray(self, dt):
        """Spray thrown off the stem when the bow wave stands high (wake.md 3.2 item 5); the wake itself is baked."""
        sc = self.sc
        rng = sc.rng
        n = int(rng.poisson(dt * self.spray_rate))
        if not n:
            return
        B = self.report["results"]["beam_m"]
        # thrown from where the bow crest leaves the hull, along the waterline's first stretch: spawned on the
        # centreline with big soft blobs, it read as a fuzzy block ahead of the stem, apart from the crest
        if sc.speed < sc.v0:
            n = int(rng.binomial(n, sc.wake_k() ** 2))
            if not n:
                return
        xw = self.wl[:, 0].max() - rng.uniform(0, 0.12, n) ** 1.5 * self.wake_info["L"]
        side = np.where(rng.random(n) < 0.5, 1.0, -1.0)
        p = np.stack([xw, side * (wake.half_breadth(self.wl, xw) + rng.uniform(0, 0.04, n) * B)], 1)
        out = np.stack([rng.uniform(-0.1, 0.25, n), side * rng.uniform(0.2, 0.5, n)], 1) * sc.speed
        w, v = self.world_of(p), sc.dir_of(out)
        fs = min(1.0, max(0.3, self.wake_info["L"] / 150))
        sc.spray.add(x=w[:, 0], y=w[:, 1], vx=v[:, 0], vy=v[:, 1], life=rng.uniform(0.3, 0.8, n),
                     r0=0.3 * fs, r1=rng.uniform(0.6, 1.3, n) * fs, a0=rng.uniform(0.15, 0.35, n))

    def spawn_smoke(self, dt):
        sc = self.sc
        rng = sc.rng
        for c, r, top in self.funnels:
            n = int(rng.poisson(dt * (10 + 2 * r)))
            if not n:
                continue
            p = c + rng.normal(0, r * 0.25, (n, 2))
            w = self.world_of(p)
            v = np.tile(sc.vel * 0.6, (n, 1)) + rng.normal(0, 0.6, (n, 2))
            sc.smoke.add(x=w[:, 0], y=w[:, 1], vx=v[:, 0], vy=v[:, 1], life=rng.uniform(*PLUME_LIFE, n),
                         r0=r * 0.6, r1=r * 1.6 + 3, a0=rng.uniform(0.15, 0.3, n) * (1.6 if self.coal else 1.0),
                         h=top, coal=float(self.coal))

    def prewarm_smoke(self, t0, t1, rng):
        """The plume as it would be at t1 had she steamed since t0 (both before the clip, t1 the warm-up's start,
        when she's at sc.pos): puffs made along her track, each carried analytically (its velocity relaxing to the
        wind with the particles' tau). Its own rng, so everything else in a clip draws the same numbers."""
        sc = self.sc
        tau = sc.smoke.tau
        for c, r, top in self.funnels:
            n = int(rng.poisson((t1 - t0) * (10 + 2 * r)))
            if not n:
                continue
            ts = rng.uniform(t0, t1, n)
            age = (t1 - ts)[:, None]
            p = c + rng.normal(0, r * 0.25, (n, 2))
            w = self.world_of(p) + sc.vel[None, :] * (ts - t1)[:, None]
            v0 = np.tile(sc.vel * 0.6, (n, 1)) + rng.normal(0, 0.6, (n, 2))
            k = np.exp(-age / tau)
            xy = w + WIND[None, :] * age + (v0 - WIND[None, :]) * tau * (1 - k)
            v = WIND[None, :] + (v0 - WIND[None, :]) * k
            life = rng.uniform(*PLUME_LIFE, n)
            keep = age[:, 0] < life
            sc.smoke.add(x=xy[keep, 0], y=xy[keep, 1], vx=v[keep, 0], vy=v[keep, 1], age=age[keep, 0],
                         life=life[keep], r0=r * 0.6, r1=r * 1.6 + 3,
                         a0=rng.uniform(0.15, 0.3, n)[keep] * (1.6 if self.coal else 1.0), h=top, coal=float(self.coal))


class Scene:
    def __init__(self, srcs, W, H, fps, heading, target, seed, seconds=None, propellant=None, explode=None,
                 tier="blast", explode_at=None, sea=None, sink=False, spacing=LINE_SPACING, fire_s=FIRE_S,
                 fit=None, scale=None, view=None, feat_m=None):
        """srcs: one exported ship, or a list: a line of battle, the first leading. scale: px per metre, in place
        of fitting the ship or line to the frame (never above the sprites' own scale). view: (W, H, C, Wo, Ho), a
        canvas W x H with the line's centre at C, for a zoom's level (make_zoom); the HUD is for an Wo x Ho output.
        feat_m: the wake foam's clump size, fixed (a zoom), in place of one tied to the scale."""
        srcs = [srcs] if isinstance(srcs, (str, Path)) else list(srcs)
        if explode and len(srcs) > 1:
            raise ValueError("magazine explosions are for one ship for now")
        self.W, self.H, self.fps = W, H, fps
        self.fire_s = fire_s
        self.rng = np.random.default_rng(seed)
        self.ships = [Ship(Path(p), propellant) for p in srcs]
        lead = self.ships[0]
        # the explosion, the wreck and the HUD read the lead's design (explosions are single-ship for now)
        self.src, self.sprite, self.hit, self.report = lead.src, lead.sprite, lead.hit, lead.report
        self.heading = heading
        if target is None:
            target = auto_target([m for sh in self.ships for m in sh.sprite["mounts"]])
        self.target_bearing = target % 360.0
        self.speed = min(sh.speed_kn for sh in self.ships) * KN     # a line steams at its slowest ship's speed
        self.vel = unit(heading) * self.speed
        self.deck_m, self.freeboard = lead.deck_m, lead.freeboard

        # stations in line ahead, the lead first and each next one `spacing` m astern (centre to centre); the
        # line's middle (halfway between its ends) sits where a lone ship's centre would
        # (plain floats: a numpy scalar in the scale would promote the float32 fields it touches, wake.bake's included)
        st = [-spacing * i for i in range(len(self.ships))]
        fore = max(x + sh.L / 2 for x, sh in zip(st, self.ships))
        aft = min(x - sh.L / 2 for x, sh in zip(st, self.ships))
        mid = 0.5 * (fore + aft)
        for x, sh in zip(st, self.ships):
            sh.off = float(x - mid)
        self.spacing = spacing

        # scale: fit the line's canvas (rotated) into 80% x 62% of the frame, never above the sprites' own scale
        S0 = min(sh.sprite["scale_px_per_m"] for sh in self.ships)
        Lm, Bm = fore - aft, max(sh.B for sh in self.ships)
        ch, sh_ = abs(math.cos(math.radians(heading))), abs(math.sin(math.radians(heading)))
        fit = (fit, fit) if fit else (EXPLODE_FIT, EXPLODE_FIT) if explode else (0.80, 0.62)
        self.s = s = min(S0, scale) if scale else min(S0, fit[0] * W / (Lm * ch + Bm * sh_),
                                                      fit[1] * H / (Lm * sh_ + Bm * ch))
        # the line sits a little ahead of centre so the wake has room
        self.C = np.array([W / 2, H / 2]) + unit(heading) * (0.07 * W)
        # an explosion clip's camera pans (Scene.cam): the scene is drawn on a bigger canvas with the ship fixed at
        # C there, and each frame is the output window cut from it where the camera puts the ship on screen
        self.Wo, self.Ho = W, H
        self.frames_at = None
        self.feat_m = feat_m
        self.bare = False
        if view:
            self.W, self.H = W, H = view[0], view[1]
            self.C = np.array(view[2], float)
            self.Wo, self.Ho = view[3], view[4]
        if explode:
            keys = [CAM_GUNS, CAM_BLAST] + ([CAM_SINK] if sink else [])
            P = np.array([(k[0] * W, k[1] * H) for k in keys])
            lo, hi = P.min(0), P.max(0)
            self.C = hi + CAM_MARGIN
            self.W, self.H = W, H = [int(math.ceil(v)) for v in hi - lo + (W, H) + 2 * CAM_MARGIN]
            self.frames_at = P
        self.pos = np.zeros(2)
        for sh in self.ships:
            sh.place(self)

        self._static_layers()
        self._mounts(self.target_bearing)
        for sh in self.ships:
            sh.build_funnels()
        self.coal = lead.coal
        self.duration = seconds or (self.t_fire_last + fire_s if self.has_guns else 10.0)
        self.v0 = self.speed
        self.blasts, self.t_stop, self.t_hit = [], None, None
        self.wreck = None
        if explode:
            self._explode(explode, tier, explode_at, seed, seconds)
            if sink:
                self._wreck(seed, seconds)

        self.water = Water(self.rng, W, H, s, self.C, **(sea or {}))
        self.dens = Density(W, H, res=1, conserve=True)   # full res, blobs keep their optical depth at any zoom
        self._wake()
        self.foam = Particles((0, 0), 2.5)       # water at rest; the push from the hull dies away
        self.spray = Particles((0, 0), 0.6)      # thrown off the stem, falls back within a second
        self.smoke = Plume(WIND, 1.2)
        self.set_look(s)
        self.shots = []                           # muzzle.Shot: flash, smoke puff and shell, all analytic in time
        self.gun_blasts = []                      # muzzle.Blast: each mount's salvo on the water
        self.fish = []                            # torpedoes [x, y, vx, vy, t0]
        self.edge_noise = self._noise_tile(128, 0.05)
        # explosion puffs' clumps (_blast_blobs): offsets in the puff's spread, shares, and a slow turn, by seed
        crng = np.random.default_rng(997)
        self.clump_off = (crng.normal(0, CLUMP_SPREAD, (997, CLUMPS, 2))).astype(np.float32)
        self.clump_w = crng.dirichlet(np.full(CLUMPS, 2.0), 997).astype(np.float32)
        self.clump_spin = crng.uniform(-0.3, 0.3, 997).astype(np.float32)
        self.t = -WARM_S
        prng = np.random.default_rng(seed + 7919)
        for sh in self.ships:
            sh.prewarm_smoke(-WARM_S - PLUME_LIFE[1], -WARM_S, prng)
        self.hud = self._hud()

    def set_look(self, s):
        """The looks drawn by zoom (gun smoke's share, the plume's fade, flash glare, the wake's lace), for s px/m. A
        zoom renders each frame from a scene at a fixed scale a little above s, and sets these to s itself, so
        they change smoothly while the scene switches."""
        self.look_s = s
        self.lace_k = lace_k(s)
        if self.feat_m:       # a fixed clump size: its lace fades as the clumps shrink under ~2 px
            self.lace_k *= smoothstep((self.feat_m * s - 1.0) / 1.5)
        self.glare = FLASH_GLARE * smoothstep(math.log(S_REF / s) / math.log(S_REF / GLARE_FULL_S))
        self.smoke_vis = min(1.0, GUN_SMOKE_VIS * (S_REF / s) ** GUN_SMOKE_ZOOM)
        self.smoke.fade_s = PLUME_FADE_S * (S_REF / s) ** PLUME_FADE_ZOOM

    # ----- setup
    def to_screen(self, m):
        """The lead's ship-local metres (+x bow, +y starboard) -> screen px."""
        return self.ships[0].to_screen(m)

    def world_of(self, m):
        """The lead's ship-local metres (one point or an (n, 2) array) -> world metres."""
        return self.ships[0].world_of(m)

    def dir_of(self, m):
        """Rotate ship-local vectors (one or (n, 2)) into world axes."""
        a = math.radians(self.heading)
        R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
        return np.asarray(m, float) @ R.T

    def _affine(self, im, origin, resample, C):
        h = math.radians(self.heading)
        c, sn = math.cos(h), math.sin(h)
        Cx, Cy = C
        data = (c, sn, origin[0] - c * Cx - sn * Cy, -sn, c, origin[1] + sn * Cx - c * Cy)
        return im.transform((self.W, self.H), Image.AFFINE, data, resample=resample)

    def _static_layers(self):
        """Every ship's hull and height map on one canvas: in a line they all stand still on screen, so they're
        merged once, and the shadows are marched over the merged height map."""
        hull, hs = None, None
        for sh in self.ships:
            h, m = sh.layers(sh.sprite["scale_px_per_m"])
            if hull is None:
                hull, hs = h, m
            else:       # ships never overlap: each pixel takes the hull that covers it most
                hull = np.where(h[..., 3:4] > hull[..., 3:4], h, hull)
                hs = Image.fromarray(np.maximum(np.asarray(hs), np.asarray(m)), "L")
        self.hull = hull
        self.Hs = np.asarray(hs, np.float32) * HEIGHT_STEP_M
        self.hull_alpha = self.hull[..., 3].astype(np.float32) / 255
        self.hull_shadow = np.asarray(shadow_mask(hs, self.s, SUN_AZ, SUN_EL), np.float32) / 255

    def _mounts(self, target):
        """Every ship's mounts and firing schedule, merged."""
        self.mounts, ev = [], []
        for i, sh in enumerate(self.ships):
            lag = self.rng.uniform(*LINE_LAG) if i else 0.0
            sh.build_mounts(sh.sprite["scale_px_per_m"], target, lag)
            self.mounts += sh.mounts
            ev += sh.events
        gunned = [sh for sh in self.ships if sh.has_guns]
        self.has_guns = bool(gunned)
        self.t_fire = min((sh.t_fire for sh in gunned), default=self.ships[0].t_fire)
        self.t_fire_last = max((sh.t_fire for sh in gunned), default=self.t_fire)
        self.events = sorted(ev, key=lambda e: e[0])
        self.next_ev = 0

    def _explode(self, mags, tier, t_hit, seed, seconds):
        """Set up the magazine explosion (magazine.py): a hit on the mount over the magazine EXPLODE_AFTER s after the
        first salvo (or at t_hit), the jet phase, then the main event. Its own rng, so the rest of the clip matches
        the plain one. After a blast the ship is out of action: no more firing, and it loses way (STOP_TAU)."""
        rng = np.random.default_rng(seed + 7919)
        if t_hit is None:
            t_hit = (self.t_fire if self.has_guns else REST_S) + EXPLODE_AFTER
        mounts = {mt.id: dict(pos=mt.pos_m, top_m=mt.top_m, bearing=self.bearing(mt, t_hit),
                              el=mt.el if mt.aim is not None else 0.0, ports=mt.ports) for mt in self.mounts}
        specs = magazine.plan(self.hit, mounts, mags, tier, t_hit, self.freeboard, rng)
        self.blasts = [magazine.Blast(sp, rng, WIND) for sp in specs]
        self.rng_fx = rng
        self.t_hit = t_hit
        first = specs[0]
        if tier == "blast":
            self.t_stop = first["t_main"]
            self.events = [e for e in self.events if e[0] < first["t_main"]]
            self.duration = seconds or (specs[-1]["t_main"] + EXPLODE_TAIL)
        else:   # the column: the mount over the magazine is burning out; the rest fight on
            self.t_stop = None
            lost = {sp["mount"] for sp in specs}
            self.events = [e for e in self.events if e[0] < t_hit or e[1].id not in lost]
            self.duration = seconds or (first["t_lift"] + magazine.COLUMN_S + 10.0)
        self.mount_by_id = {mt.id: mt for mt in self.mounts}
        self.pose = Pose(self)
        # the hull scorched around each magazine (research 3.4), and the barbette open where a gunhouse was thrown
        u, v = np.meshgrid(np.arange(self.W, dtype=np.float32), np.arange(self.H, dtype=np.float32))
        self.scorch = []
        for sp in specs:
            c = self.to_screen(sp["centre"])
            R = max(12.0, 0.15 * sp["D"] if tier == "blast" else 1.5 * sp["barbette"]["r"] if sp["barbette"] else 10)
            m = np.exp(-((u - c[0]) ** 2 + (v - c[1]) ** 2) / (2 * (R * self.s) ** 2)) * self.hull_alpha
            hole = None
            if sp["barbette"] and tier == "blast":
                b = self.to_screen(sp["barbette"]["xy"])
                hole = np.clip(sp["barbette"]["r"] * self.s - np.hypot(u - b[0], v - b[1]) + 0.5, 0, 1)
            self.scorch.append((sp, m.astype(np.float32), hole))

    def _wake(self):
        """Bake each ship's steady wake once (wake.py) and warp it to the frame: the heading is fixed and the camera
        follows the line, so the wakes' envelopes stand still on screen. Only the foam's texture moves, anchored to
        the water, so the ships steam through it. A line's wakes are merged: slopes add (a linear surface), foam
        takes the denser."""
        t0 = time.perf_counter()
        W, H, s = self.W, self.H, self.s
        h = math.radians(self.heading)
        c, sn = math.cos(h), math.sin(h)
        # every pixel in metres from the line's centre, in ship axes
        u, v = np.meshgrid(np.arange(W, dtype=np.float32) + 0.5, np.arange(H, dtype=np.float32) + 0.5)
        dX, dY = u - self.C[0], v - self.C[1]
        self.lx, self.ly = (c * dX + sn * dY) / s, (-sn * dX + c * dY) / s
        for i, sh in enumerate(self.ships):
            hx, hy, fresh, resid, wash = sh.bake_wake()
            if i == 0:
                self.wake_hx, self.wake_hy = hx, hy
                self.wake_fresh, self.wake_resid, self.wake_wash = fresh, resid, wash
            else:
                self.wake_hx, self.wake_hy = self.wake_hx + hx, self.wake_hy + hy
                self.wake_fresh = np.maximum(self.wake_fresh, fresh)
                self.wake_resid = np.maximum(self.wake_resid, resid)
                self.wake_wash = np.maximum(self.wake_wash, wash)
        self.wake_info = self.ships[0].wake_info
        self.wake_calm = np.clip(self.wake_wash * 0.9, 0, 0.75)

        # foam tiles in ship axes, anchored to the water: streaky along the track for the wash, rounder for crests
        feat = self.feat_m or max(0.6, 2.5 / s)   # foam clump size, m: never finer than about two and a half pixels
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

    def _hud(self, single=False):
        """The caption: the ship, or the line (single: the lead alone, as a zoom opens on it)."""
        im = Image.new("RGBA", (self.Wo, self.Ho), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        res = self.report["results"]
        big, small = font(max(14, self.Ho // 30)), font(max(11, self.Ho // 50))
        x, y = self.Ho // 36, self.Ho - self.Ho // 36
        if len(self.ships) == 1 or single:
            name = self.ships[0].name
            nm = len(self.mounts) if len(self.ships) == 1 else len(self.ships[0].sprite["mounts"])
            stats = (f"{res['length_m']:.0f} m  ·  {res['standard_displacement_t']:,} t std  ·  "
                     f"{self.report['inputs'].get('speed_kn', '?')} kn  ·  {nm} mounts")
        else:
            runs = []           # sister ships in a row: "3 × Lion-like  ·  Tiger-like"
            for sh in self.ships:
                if runs and runs[-1][0] == sh.name:
                    runs[-1][1] += 1
                else:
                    runs.append([sh.name, 1])
            name = "  ·  ".join(f"{k} × {n}" if k > 1 else n for n, k in runs)
            tons = sum(sh.report["results"]["standard_displacement_t"] for sh in self.ships)
            stats = (f"line ahead, {len(self.ships)} ships {self.spacing:.0f} m apart  ·  {tons:,} t std  ·  "
                     f"{self.speed / KN:.4g} kn  ·  {len(self.mounts)} mounts")
        d.text((x + 1, y - big.size - small.size - 5), name, font=big, fill=(0, 0, 0, 140))
        d.text((x, y - big.size - small.size - 6), name, font=big, fill=(240, 244, 246, 235))
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

    def fire(self, mt, i):
        rng = self.rng
        ang = self.heading + self.bearing(mt, self.t)
        d = unit(ang)
        muz = mt.ship.pos + rot(mt.pos_m, self.heading) + rot(mt.muzzles[i], ang)
        if mt.kind == "torpedo":
            self.fish.append([muz[0], muz[1], *(self.vel + d * 22.0), self.t])
            self.foam.add(x=muz[0] + rng.normal(0, 1, 12), y=muz[1] + rng.normal(0, 1, 12),
                          vx=d[0] * 4, vy=d[1] * 4, life=2.0, r0=0.5, r1=2.5, a0=0.7)
            return
        D = mt.fxD
        shot = muzzle.Shot(mt.fx, D, muz, mt.muzzle_h, math.radians(ang), mt.el, self.t, self.vel, WIND, rng)
        # the clumps its smoke is drawn as: offsets in units of the puff's spread, a slow drift of their own
        shot.sub_off = rng.normal(0, 0.7, (SUB_PUFFS, 2))
        shot.sub_vel = rng.normal(0, 0.6, (SUB_PUFFS, 2))
        shot.sub_f = rng.uniform(0.15, 1.2, SUB_PUFFS)
        shot.sub_w = rng.dirichlet(np.full(SUB_PUFFS, 2.0))
        # the jet punch (muzzle_blast_waves.md 5.2): older smoke in the cone ahead of the muzzle (3 lam_f long,
        # 20 degrees half-angle) is shoved along the bore and spread, its amount kept. Puffs still under their own
        # jet are left alone
        lf = shot.lam_f
        for o in self.shots:
            if self.t - o.t0 < 0.3:
                continue
            p = o.puff(self.t)
            if p is None:
                continue
            push = self._jet_push(muz, d, lf, p["xy"][None, :])
            if push is not None and push[0].any():
                o.push(self.t, push[0], 1.2)
        if len(self.smoke):
            sm = self.smoke.d
            push = self._jet_push(muz, d, lf, np.stack([sm["x"], sm["y"]], 1))
            if push is not None:     # particles relax to the wind over the smoke's tau: a kick of push / tau
                sm["vx"] += (push[:, 0] / self.smoke.tau).astype(np.float32)
                sm["vy"] += (push[:, 1] / self.smoke.tau).astype(np.float32)
        self.shots.append(shot)
        # the blast on the water (muzzle_blast_water-vfx.md): one event per mount's salvo, the guns that fire
        # within 0.2 s of its first summing their energy
        ev = next((b for b in reversed(self.gun_blasts) if b.mount is mt and self.t - b.t0 < 0.2), None)
        if ev is None:
            ev = muzzle.Blast(mt, muz, mt.muzzle_h, math.radians(ang), mt.el, self.t)
            self.gun_blasts.append(ev)
        ev.add(D["E_blast"], muz)
        # spray torn off the sea where the near field and the jet reach it (research 3.3: count by lam^2, only
        # when the muzzle isn't far above the water; smooth, no calibre or height cutoff)
        lb = D["lam_b"]
        k = int(rng.poisson(math.exp(-(mt.muzzle_h / (1.5 * lb)) ** 2) * (4 + 0.25 * lb * lb)))
        if k:
            along = rng.uniform(0.3, 1.6, k) * lb
            side = rng.normal(0, 0.3 * lb, k)
            n = np.array([-d[1], d[0]])
            x = muz[0] + d[0] * along + n[0] * side
            y = muz[1] + d[1] * along + n[1] * side
            sp = rng.uniform(6, 18, k)
            self.spray.add(x=x, y=y, vx=d[0] * sp + n[0] * side * 0.5, vy=d[1] * sp + n[1] * side * 0.5,
                           life=rng.uniform(0.4, 1.0, k), r0=0.5, r1=0.05 * lb + 1.0, a0=0.45)

    def _jet_push(self, muz, d, lf, pts):
        """Displacement (n, 2) the gas jet from a muzzle at muz along d gives to points pts, or None if none is in
        its cone: d k lam_f e^(-dist/lam_f), k 0.5 (muzzle_blast_waves.md 5.2)."""
        rel = pts - muz[None, :]
        along = rel @ d
        perp = np.abs(rel[:, 0] * d[1] - rel[:, 1] * d[0])
        inside = (along > 0) & (along < 3 * lf) & (perp < along * math.tan(math.radians(20)))
        if not inside.any():
            return None
        dist = np.hypot(rel[:, 0], rel[:, 1])
        k = np.where(inside, 0.5 * lf * np.exp(-dist / lf), 0.0)
        return k[:, None] * d[None, :]

    def _wreck(self, seed, seconds):
        """--sink: the explosion breaks her in two (sinkvid's break, shipgen's sinking.Break) at the main event. The
        cut runs through the middle of the exploded magazines, which are the torn zone. From the main event on,
        sinkvid's scene draws the ship (its 3D hull, turrets as trained, the thrown gunhouses gone) and the
        surface (crossing foam, boils, rings, oil, wreckage) under vidgen's sea, smoke, fire and camera. Its clock
        starts sinkvid.HIT_S before the break so the hit lands on the main event."""
        import sinkvid
        specs = [b.s for b in self.blasts]
        x0, x1 = min(sp["span"][0] for sp in specs), max(sp["span"][1] for sp in specs)
        self.t_break = specs[0]["t_main"]
        host = dict(s=self.s, C=self.C, cut=0.5 * (x0 + x1), zone=(x0, x1), why=" and ".join(sp["id"] for sp in specs),
                    bearing={mt.id: self.bearing(mt, self.t_break) for mt in self.mounts},
                    skip={sp["mount"] for sp in specs if sp.get("mount")})
        wr = self.wreck = sinkvid.SinkScene(self.src, self.W, self.H, self.fps, self.heading, "break", seed, host=host)
        self.t_sink0 = self.t_break - sinkvid.HIT_S
        # she coasts on with the way she had, along her heading; the camera follows, as before the break. Her speed
        # is steady until the main event, so where she is then is known up front
        hit, v, tau, h = sinkvid.HIT_S, self.v0, BREAK_STOP_TAU, unit(self.heading)
        self.glide = lambda ts: v * tau * (1 - math.exp(-max(0.0, ts - hit) / tau))     # on the wreck's clock
        wr.tl.glide = self.glide
        wr.cam_of = lambda ts: h * self.glide(ts)
        self.pos_b = h * v * (self.t_break + WARM_S)
        if not seconds:
            self.duration = max(self.duration, self.t_sink0 + wr.tl.t_last + 4 + sinkvid.TAIL_S)

    def broken(self):
        return self.wreck is not None and self.t >= self.t_break

    def cam(self):
        """An explosion clip's camera: where the ship's centre is on the output frame now, in px (CAM_*)."""
        P = self.frames_at
        t_main = self.blasts[0].s["t_main"]
        end, d = CAM_PAN_BLAST
        p = P[0] + (P[1] - P[0]) * smootherstep((self.t - (t_main - end - d)) / d)
        if len(P) > 2:
            t0, d = CAM_PAN_SINK
            p = p + (P[2] - P[1]) * smootherstep((self.t - t_main - t0) / d)
        return p

    def wake_k(self):
        """How much of the baked wake is left as the ship loses way after a magazine explosion: the bake is steady,
        so it's faded with the speed (DEPARTURE from any wake model; until the sinking clip takes over)."""
        return self.speed / self.v0 if self.v0 > 0 else 1.0

    def splash(self, xy, size):
        """A piece of debris (or a gunhouse) falling into the sea: a white burst and a foam ring that lingers."""
        rng = self.rng_fx
        k = int(6 + 3 * size)
        a = rng.uniform(0, 2 * math.pi, k)
        v = np.stack([np.cos(a), np.sin(a)], 1) * rng.uniform(0.5, 1.5, (k, 1)) * size
        self.foam.add(x=xy[0] + v[:, 0] * 0.3, y=xy[1] + v[:, 1] * 0.3, vx=v[:, 0], vy=v[:, 1],
                      life=rng.uniform(3, 6, k), r0=0.5 * size, r1=1.6 * size, a0=0.5)
        self.spray.add(x=xy[0] + rng.normal(0, 0.3 * size, 4), y=xy[1] + rng.normal(0, 0.3 * size, 4),
                       life=rng.uniform(0.3, 0.7, 4), r0=0.3 * size, r1=0.8 * size, a0=0.25)

    def step(self, dt):
        if self.wreck is not None and self.t + dt > self.t_break:
            self.t += dt
            self.speed = self.v0 * math.exp(-(self.t - self.t_break) / BREAK_STOP_TAU)
            self.vel = unit(self.heading) * self.speed
            self.pos = self.pos_b + unit(self.heading) * self.glide(self.t - self.t_sink0)
        else:
            if self.blasts and self.t_stop is not None and self.t > self.t_stop:
                self.speed = self.v0 * math.exp(-(self.t - self.t_stop) / STOP_TAU)
                self.vel = unit(self.heading) * self.speed
            self.pos = self.pos + self.vel * dt
            self.t += dt
        if self.wreck is not None:
            while self.wreck.t < self.t - self.t_sink0 - 1e-6:
                self.wreck.step(dt)
        for b in self.blasts:
            b.step(self.t, dt, self.pose)
            for xy, size in b.new_splashes:
                self.splash(xy, size)
        if not self.broken():         # after the break the wreck makes the funnel smoke, and nothing cuts the sea
            for sh in self.ships:
                sh.spawn_spray(dt)
                sh.spawn_smoke(dt)
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
        self.gun_blasts = [b for b in self.gun_blasts if self.t - b.t0 < b.life]
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
        wk = self.wake_k()
        rough, bfoam = self._gun_blast_water()
        wr = self.wreck if self.broken() else None
        if wr is not None:      # the broken wreck: its boils' and rings' slopes and the oil's calm join the sea's
            sf = wr.surface(wr.t)
            calm = self.wake_calm * wk if sf.slick is None else np.maximum(self.wake_calm * wk, 0.85 * sf.slick)
            frame = self.water.shade(self.pos, self.t, (self.wake_hx * wk, self.wake_hy * wk, calm), half=sf.half,
                                     rough=rough)
            wash, fresh, resid = self.wake_wash * wk, self.wake_fresh * wk, self.wake_resid * wk
            wr.draw_oil(frame, sf)
            hl = wr.hull_layers(wr.t)
            wr.draw_hull(frame, hl, False)
        elif wk < 1:      # the ship losing way after a magazine explosion: the steady wake fades with its speed
            frame = self.water.shade(self.pos, self.t, (self.wake_hx * wk, self.wake_hy * wk, self.wake_calm * wk),
                                     rough=rough)
            wash, fresh, resid = self.wake_wash * wk, self.wake_fresh * wk, self.wake_resid * wk
        else:
            frame = self.water.shade(self.pos, self.t, (self.wake_hx, self.wake_hy, self.wake_calm), rough=rough)
            wash, fresh, resid = self.wake_wash, self.wake_fresh, self.wake_resid
        self._blobs = self._blast_blobs() if self.blasts else None

        # baked wake: the wash tints the water to a pale churned slick, then the three foam densities are broken up
        # by water-anchored noise (wake.md 6, shader note), the residual foam at half opacity
        frame += (CHURN - frame) * np.clip(wash * 0.9, 0, 0.7)[..., None]
        tw = self.foam_tex(self.tiles_wash, self.t, ridged=True)
        tc = self.foam_tex(self.tiles_crest, self.t, ridged=True)
        lk = self.lace_k
        f = np.maximum(np.maximum(lace(wash, tw, "wash", lk), lace(fresh, tc, "fresh", lk)),
                       LACE_RESID * lace(resid, tw, "resid", lk))
        if bfoam is not None:
            np.maximum(f, lace(BLAST_FOAM * bfoam, tc, "fresh", lk), out=f)
        if self.blasts:
            self._shock(frame, f, tc)
        frame += (FOAM - frame) * f[..., None]
        if wr is not None:
            wr.draw_foam(frame, wr.t, sf)
        foam = upscale(self.field(self.foam) + self.field(self.spray), W, H) * self.water.foam_noise
        frame += (FOAM - frame) * np.clip(1 - np.exp(-1.6 * foam), 0, 0.95)[..., None]

        # hull, then static and turret shadows on everything below the turrets (the wreck: its own hull, shadow
        # and wreckage)
        if wr is not None:
            wr.draw_debris(frame)
            wr.draw_hull(frame, hl, True)
            shade = np.zeros((H, W), np.float32)
        else:
            a = self.hull_alpha[..., None]
            frame = frame * (1 - a) + self.hull[..., :3].astype(np.float32) / 255 * a
            if self.blasts:
                self._scorch(frame)
            shade = self.hull_shadow.copy()
        rots = []
        gone = {b.s["mount"] for b in self.blasts if b.thrown}
        for mt in self.mounts if wr is None else ():
            if mt.id in gone:
                continue
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
        flying = self._flyers(shade, rots) if self.blasts else []
        self.last_shade = shade          # kept for debugging shadow issues
        frame *= (1 - SHADE * shade)[..., None]
        for arr, x0, y0 in rots:
            blend(frame, arr, x0, y0)
        if self.blasts:
            self._fire_light(frame)

        # smoke, funnel, gun and explosion alike: one optical-depth field with a colour per puff, shadows cast from
        # each puff's height, then lit from the sun side as a surface whose height goes with the (blurred) log
        # thickness
        tau, col, shd = self._smoke_fields()
        self._tau = tau
        if shd.any():
            dk = 0.4 * (1 - np.exp(-shd))
            if self.blasts:   # explosion smoke is thick enough to take the sea toward 30 % (research 3.2)
                dk = dk + 0.3 * (1 - np.exp(-shd / 6)) ** 2
            frame *= (1 - np.clip(upscale(dk, W, H), 0, 0.7))[..., None]
        self._shells(frame, shadow=True)
        if tau.any():
            sd = unit(SUN_AZ)
            # the relief is in metres, so a puff is lit the same at any zoom: blurred over LIGHT_BLUR_M, its slope
            # per metre (tuned per half-res pixel at S_REF: a pixel's slope was LIGHT_SLOPE of it)
            g = self.dens.res
            kz = s / g                     # buffer cells per metre
            gy, gx = np.gradient(box_blur(np.log1p(tau), int(round(LIGHT_BLUR_M * kz))))
            gk = 2.0 * LIGHT_SLOPE * kz
            if self._tau_ex is None:
                light = np.clip(1.0 - gk * (gx * sd[0] + gy * sd[1]), 0.6, 1.25)
            else:
                # explosion smoke is far thicker than funnel smoke, so its clumps are lit as a coarser relief too
                # (the 6-way flipbooks' stand-in, research 3.4); thin smoke and the funnels' look are unchanged
                ey, ex = np.gradient(box_blur(np.log1p(self._tau_ex), int(round(2 * LIGHT_BLUR_M * kz))))
                share = np.clip(self._tau_ex / np.maximum(tau, 1e-6), 0, 1)
                light = np.clip(1.0 - gk * (gx * sd[0] + gy * sd[1]) - EX_RELIEF * LIGHT_SLOPE * kz * (ex * sd[0] + ey * sd[1]),
                                0.6 - 0.25 * share, 1.25 + 0.2 * share)
            c = col / np.maximum(tau, 1e-6)[..., None] * light[..., None]
            c = np.stack([upscale(c[..., i], W, H) for i in range(3)], -1)
            al = np.clip(upscale(1 - np.exp(-tau), W, H), 0, SMOKE_MAX)[..., None]
            frame = frame * (1 - al) + c * al

        # explosion: flying debris and gunhouses over the smoke (dimmed by the smoke at their spot), then the fire
        # glowing through it
        if self.blasts:
            self._solids(frame, tau, flying)
            self._fire(frame)
        if wr is not None:      # the fires on the torn ends
            wr._glow(frame, wr.t)
        # the flashes over the smoke (research 7.6: the fireball is in front of its own smoke), and the shells over
        # the flashes: on the slowed clock they're still inside the fireball they really outran, so they show as
        # silhouettes against it, as in high-speed photographs of a shell leaving the muzzle
        self._flashes(frame)
        self._shells(frame)
        shake = (0.0, 0.0)
        if self.blasts:
            shake = self._exposure(frame)
        self.C_out = self.C
        if self.frames_at is not None:     # the camera's window on the canvas; the shake moves the window
            o = np.round(self.C - self.cam()).astype(int)
            self.C_out = self.C - o
            o -= shake
            frame = frame[o[1]:o[1] + self.Ho, o[0]:o[0] + self.Wo]
            W, H, shake = self.Wo, self.Ho, (0, 0)

        # target marker and captions
        frame = np.clip(frame, 0, 1)
        out = (frame * 255).astype(np.uint8)
        if shake != (0, 0):
            dx, dy = shake
            p = np.pad(out, ((abs(dy), abs(dy)), (abs(dx), abs(dx)), (0, 0)), mode="edge")
            out = np.ascontiguousarray(p[abs(dy) - dy:abs(dy) - dy + H, abs(dx) - dx:abs(dx) - dx + W])
        if self.bare:
            return out
        return self.compose(out)

    def compose(self, out, scale_bar=None, hud=None):
        """The HUD, phase caption and target marker over a finished Wo x Ho frame (C_out: where the marker's ray
        starts, the line's centre). scale_bar: px per metre, to draw a scale bar. hud: an RGBA caption in place of
        the scene's."""
        hud = (self.hud if hud is None else hud).astype(np.float32) / 255
        ha = hud[..., 3:4]
        out = (out * (1 - ha) + hud[..., :3] * 255 * ha).astype(np.uint8)
        out = self._overlay(out)
        if scale_bar:
            out = self._scale_bar(out, scale_bar)
        return out

    def _scale_bar(self, out, s):
        """A scale bar at the top right (the target marker often sits bottom right): the 1-2-5 length nearest a
        sixth of the frame, its ends ticked."""
        im = Image.fromarray(out)
        d = ImageDraw.Draw(im, "RGBA")
        want = self.Wo / 6 / s
        e = 10 ** math.floor(math.log10(want))
        L = min((m * e for m in (1, 2, 5, 10)), key=lambda v: abs(math.log(v / want)))
        px = L * s
        m = self.Ho // 36
        x1, y = self.Wo - 3 * m, 2.5 * m
        x0 = x1 - px
        col = (235, 240, 242, 220)
        d.line([(x0, y), (x1, y)], fill=col, width=max(2, self.Ho // 400))
        for x in (x0, x1):
            d.line([(x, y - m / 3), (x, y + m / 3)], fill=col, width=max(2, self.Ho // 400))
        lab = f"{L / 1000:g} km" if L >= 1000 else f"{L:g} m"
        w = d.textlength(lab, font=self.font_small)
        d.text(((x0 + x1) / 2 - w / 2, y - m * 1.4), lab, font=self.font_small, fill=col)
        return np.asarray(im)

    def _gun_blast_water(self):
        """The guns' blasts on the sea (muzzle.Blast, muzzle_blast_water-vfx.md 3.2), worked out at quarter
        resolution (they're smooth; the lace texture brings the foam's detail) in a window per event: the ripple
        multiplier 1 + BLAST_FROST frost - BLAST_LEAD lead (full-frame; the leading edge lays the ripples down, the
        frost behind it roughens them toward silver) and the scour foam's density. Overlapping blasts take the strongest of each. DEPARTURE: no bright seam where two fronts
        cross (the Iowa photo's): gated by the thin leading edge, it drew hard pale arcs."""
        if not self.gun_blasts:
            return None, None
        mx, my = self.water.mx[0, 2::4], self.water.my[2::4, 0]
        hh, hw = len(my), len(mx)
        r_max = g_max = fo = None
        band_min = 6.0 / self.s
        for b in self.gun_blasts:
            tt = self.t - b.t0
            if tt <= 0:
                continue
            # frost and the edge live within the front; once the frost has gone only the foam's patch is left
            if tt < 4 * TAU_FROST_VIS + b.r_vis / muzzle.C0:
                R = b.radius(self.t) + 3 * muzzle.C0 * 0.0009 * b.lam
            else:
                R = 4.5 * b.lam
            cx, cy = b.pos - self.pos
            x0, x1 = np.searchsorted(mx, cx - R), np.searchsorted(mx, cx + R)
            y0, y1 = np.searchsorted(my, cy - R), np.searchsorted(my, cy + R)
            if x0 >= x1 or y0 >= y1:
                continue
            if r_max is None:
                r_max, g_max, fo = (np.zeros((hh, hw), np.float32) for _ in range(3))
            X = (mx[x0:x1] - np.float32(cx))[None, :]
            Y = (my[y0:y1] - np.float32(cy))[:, None]
            rg, ld, fm = b.fields(X, Y, self.t, band_min)
            win = (slice(y0, y1), slice(x0, x1))
            np.maximum(r_max[win], rg, out=r_max[win])
            np.maximum(g_max[win], ld, out=g_max[win])
            np.maximum(fo[win], fm, out=fo[win])
        if r_max is None:
            return None, None
        k = np.maximum(1 + BLAST_FROST * r_max - BLAST_LEAD * g_max, 0.15)
        sheen = BLAST_SHEEN * r_max - BLAST_DARK * g_max
        return ((upscale(k, self.W, self.H), upscale(sheen, self.W, self.H)),
                (upscale(fo, self.W, self.H) if fo.any() else None))

    # ----- magazine explosions (magazine.py)
    def lift(self, z, z0):
        """Screen px a point at height z rises up the screen above its source at z0 (the oblique VFX projection)."""
        return K_OBL * H_C * (1 - np.exp(-np.maximum(z - z0, 0) / H_C)) * self.s

    def _blast_blobs(self):
        """Every blast particle as Density blobs, as for the gun smoke: each gas puff is CLUMPS clumps (offsets and
        shares picked by its seed, turning slowly with its age) so the cloud breaks up like the funnel smoke, not one
        smooth disc per puff. Each blob has where it's drawn (lifted), where its shadow is cast from (its true
        position), its optical depth, colour and temperature. Sparks and debris are single points with their own
        luminance. A blob's drawn sigma is about 1.22x the radius passed (Density); a puff's own spread is ~0.55 r
        (the reference's profile). Blobs under the smallest bucket keep their integral (weights fall by the area
        ratio)."""
        s = self.s
        live = [b for b in self.blasts if len(b.p)]
        out = dict(n=0)
        if not live:
            return out
        cat = lambda k: np.concatenate([b.p.d[k] for b in live])
        z0 = np.concatenate([np.full(len(b.p), b.s["deck_z"]) for b in live])
        pos, r, m, T, kind, age, seed, life = (cat(k) for k in ("pos", "r", "m", "temp", "kind", "age", "seed", "life"))
        sx, sy = self.scr(pos[:, 0], pos[:, 1])
        py = sy - self.lift(pos[:, 2], z0)
        tau_pk = 0.85 * magazine.KAPPA * m / np.maximum(r, 0.3) ** 2
        # fire light on the smoke near it: orange from inside and below (research 3.3)
        lit = np.zeros(len(r))
        for b in live:
            for c, I in b.lights:
                lit += min(I / I_REF, 3.0) * 3600.0 / (((pos - c) ** 2).sum(1) + 900.0)
        lit = 1 - np.exp(-0.35 * lit)
        g = np.nonzero(kind < 2)[0]
        K = CLUMPS
        j = (seed[g] * len(self.clump_off)).astype(int)
        sp = 0.55 * r[g] * s                                       # the puff's spread, px
        ang = self.clump_spin[j] * age[g]
        ca, sa = np.cos(ang)[:, None], np.sin(ang)[:, None]
        ox, oy = self.clump_off[j, :, 0], self.clump_off[j, :, 1]
        dx, dy = (ox * ca - oy * sa) * sp[:, None], (ox * sa + oy * ca) * sp[:, None]
        sc = CLUMP_SIGMA * sp                                      # each clump's sigma, px
        # never in the smallest bucket: its 7-px box support shows as a square once a dense clump saturates
        rp = np.maximum(sc / 1.22, 3.0)
        cfac = np.minimum(1.0, (sc / (1.22 * rp)) ** 2)
        fade = np.clip((life[g] - age[g]) / 0.3, 0, 1)            # short-lived jet puffs thin out, not vanish
        pk = tau_pk[g] * (1 - 0.45 * T[g]) * EXPLODE_VIS / CLUMP_SIGMA ** 2 * cfac * fade
        col = np.where((kind[g] == 1)[:, None], STEAM[None, :], np.array(SMOKE_SOOT)[None, :]) \
            + lit[g, None] * FIRELIT
        rep = lambda a: np.repeat(a, K, 0)
        out.update(n=len(g) * K, px=(sx[g, None] + dx).ravel(), py=(py[g, None] + dy).ravel(),
                   sx=(sx[g, None] + dx).ravel(), sy=(sy[g, None] + dy).ravel(), h=rep(pos[g, 2]),
                   rp=rep(rp), tau=(pk[:, None] * self.clump_w[j]).ravel(), col=rep(col), T=rep(T[g]))
        # sparks and burning debris: points with a blackbody luminance, under a pixel, so by their area
        q = np.nonzero(kind >= 2)[0]
        sig = 0.55 * r[q] * s
        # burning debris glows as flaming wreckage (~1500 K at most), not as hot as the grains thrown from the vents
        L = magazine.fire_luminance(np.where(kind[q] == 3, T[q], 0.6 * T[q])) / L_BG * EXPOSE * np.where(kind[q] == 3, 1.0, 0.5)
        L *= np.minimum(1.0, (sig / np.maximum(2.83, sig)) ** 2) * (T[q] > 0.03)
        out.update(qpx=sx[q], qpy=py[q], qsx=sx[q], qsy=sy[q], qh=pos[q, 2], qrp=sig / 1.22, qL=L, qT=T[q],
                   deb=kind[q] == 2, qr=r[q])
        return out

    def _shock(self, frame, f, tc):
        """The blast on the water (the muzzle-blast event at the magazine's lam, research 2.4): a dark leading edge
        racing out at about the speed of sound, a frosted disc behind it fading in 2 s, and scour foam ~lam across,
        drawn as the wake's fresh lace and fading over 10 s."""
        s = self.s
        for b in self.blasts:
            if b.shock is None:
                continue
            (cx, cy), t0, lam = b.shock
            te = self.t - t0
            if te < 0 or te > 40:
                continue
            X = self.water.mx[0] + np.float32(self.pos[0] - cx)
            Y = self.water.my[:, 0] + np.float32(self.pos[1] - cy)
            r = np.sqrt(X[None, :] ** 2 + Y[:, None] ** 2)
            if te < 3:
                Rf = 345 * te + 2.5 * lam * (1 - math.exp(-te / 0.08))
                sk = np.clip(1 - r / (4.0 * lam), 0, 1)
                lead = sk * np.exp(-((r - Rf) / 5.0) ** 2)
                frost = sk * (r < Rf) * math.exp(-te / 2.0)
                frame *= (1 - 0.45 * lead)[..., None]
                frame += (0.05 * frost)[..., None]
            if te > 0.05:
                d = np.clip(1.2 - r / lam, 0, 1) ** 1.5 * math.exp(-te / 10)
                np.maximum(f, lace(d, tc, "fresh", self.lace_k), out=f)

    def _scorch(self, frame):
        for sp, m, hole in self.scorch:
            t0 = sp["t_main"] if sp["tier"] == "blast" else sp["t_lift"]
            k = smoothstep((self.t - t0) / 0.3)
            if k <= 0:
                continue
            frame *= (1 - 0.85 * k * m)[..., None]
            if hole is not None:
                frame += (DEBRIS - frame) * (k * hole)[..., None]

    def _fire_light(self, frame):
        """The fire as a point light on the sea and the ship (research 3.3), restrained: in daylight it's a warm pool."""
        fc = np.array([1.0, 0.45, 0.15], np.float32)
        for b in self.blasts:
            for c, I in b.lights:
                In = I / I_REF
                Lz = max(float(c[2]), 8.0)
                X = self.water.mx[0] + np.float32(self.pos[0] - c[0])
                Y = self.water.my[:, 0] + np.float32(self.pos[1] - c[1])
                d2 = X[None, :] ** 2 + Y[:, None] ** 2 + np.float32(Lz * Lz)
                irr = np.float32(In * (Lz / 60.0) ** -0.5) * (np.float32(Lz * Lz) / d2) ** 1.5
                irr *= 1 + 0.5 * self.hull_alpha
                frame += np.minimum(irr, 3.0)[..., None] * (0.12 * fc)

    def _flyers(self, shade, rots):
        """Thrown gunhouses: in the air, a turret sprite tumbling (squashed by the cosine of its tilt, dark when the
        bottom shows), scaled 1 + z / H_CAM and lifted like the smoke, with its shadow on whatever is below it; landed
        on the deck, drawn with the mounts. Returns the airborne ones' sprites for _solids."""
        s, out = self.s, []
        for b in self.blasts:
            for fl in b.flyers:
                if fl["landed"] == "sunk":
                    continue
                mt = self.mount_by_id[fl["mount"]]
                base = self.heading + self.bearing(mt, self.t)
                im = mt.img
                if fl["landed"] is not None:
                    if self.broken():
                        continue
                    loc, z, ang = fl["landed"]
                    c = self.to_screen(loc)
                    arr = np.asarray(im.rotate(-(base + ang), resample=Image.BICUBIC, expand=True))
                    rots.append((arr, int(round(c[0] - arr.shape[1] / 2)), int(round(c[1] - arr.shape[0] / 2))))
                    continue
                p = fl["p"]
                ct = math.cos(math.radians(fl["tilt"]))
                k = 1 + p[2] / H_CAM
                w = max(1, round(im.width * k * max(0.12, abs(ct))))
                h = max(1, round(im.height * k))
                sq = im.resize((w, h), Image.BILINEAR)
                if ct < 0:      # the underside: the dark trunk and roller path
                    a = np.asarray(sq).copy()
                    a[..., :3] = (a[..., :3] * 0.3).astype(np.uint8)
                    sq = Image.fromarray(a)
                arr = np.asarray(sq.rotate(-(base + fl["ang"]), resample=Image.BICUBIC, expand=True))
                cx, cy = self.scr(p[0], p[1])
                alpha = arr[..., 3].astype(np.float32) / 255
                off = sun_offset_px(s, SUN_AZ, SUN_EL, float(p[2]))
                x0, y0 = int(round(cx - arr.shape[1] / 2)), int(round(cy - arr.shape[0] / 2))
                stamp_max(shade, alpha * 0.9, x0 + int(round(off[0])), y0 + int(round(off[1])), self.Hs, float(p[2]))
                cy -= float(self.lift(p[2], b.s["deck_z"]))
                out.append((arr, int(round(cx - arr.shape[1] / 2)), int(round(cy - arr.shape[0] / 2))))
        return out

    def _solids(self, frame, tau, flying):
        """Debris pieces as small dark discs and the airborne gunhouses, dimmed where smoke stands in front."""
        B = self._blobs
        H, W = frame.shape[:2]
        g = self.dens.res
        tf = lambda x, y: float(tau[min(max(int(y / g), 0), tau.shape[0] - 1), min(max(int(x / g), 0), tau.shape[1] - 1)])
        for arr, x0, y0 in flying:
            vis = math.exp(-0.5 * tf(x0 + arr.shape[1] / 2, y0 + arr.shape[0] / 2))
            a = arr.copy()
            a[..., 3] = (a[..., 3] * vis).astype(np.uint8)
            blend(frame, a, x0, y0)
        if not B or "deb" not in B or not B["deb"].any():
            return
        for i in np.nonzero(B["deb"])[0]:
            cx, cy = B["qpx"][i], B["qpy"][i]
            R = max(0.8, 0.6 * B["qr"][i] * self.s)
            x0, x1 = int(math.floor(cx - R - 1)), int(math.ceil(cx + R + 1))
            y0, y1 = int(math.floor(cy - R - 1)), int(math.ceil(cy + R + 1))
            x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
            if x0 >= x1 or y0 >= y1:
                continue
            X = np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5 - np.float32(cx)
            Y = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5 - np.float32(cy)
            a = np.clip(R - np.sqrt(X * X + Y * Y) + 0.5, 0, 1) * 0.95 * math.exp(-0.5 * tf(cx, cy))
            win = frame[y0:y1, x0:x1]
            win += (DEBRIS - win) * a[..., None]

    def _fire(self, frame):
        """The fire's light: the hot gas as an emitting, absorbing medium, S (1 - e^-tau_hot), with S the blackbody
        luminance (magazine.fire_luminance) at the hot gas's tau-weighted mean temperature over the pixel, dimmed by
        the hot share of all the smoke there, (tau_hot / tau)^FIRE_SKIN: the soot skin is on top of the core (the
        reference cools it first), so the fire shows through where it's thin. A ratio of two smooth fields: an
        exponential in the cold optical depth (up to ~100 in the jets) cut holes with the coarse grid's straight
        edges. Two splat passes more than the smoke. The
        temperature is stirred by world-anchored noise rising with the gas (the flipbooks' stand-in, research 3.4), and luminance is steep in temperature, so the noise draws hot folds and dark
        lanes. Sparks and burning debris add their own light. Then the flash's bloom and roll-off."""
        B = self._blobs
        if not B or not B["n"]:
            return
        tau = self._tau
        if "qL" not in B:
            return
        hw = B["tau"] * np.clip((B["T"] - 0.2) / 0.25, 0, 1) ** 2     # the hot share of each blob's optical depth
        th = self.dens.render(B["px"], B["py"], B["rp"], hw)
        TT = self.dens.render(B["px"], B["py"], B["rp"], hw * B["T"])
        Tm = TT / np.maximum(th, 1e-6)
        hot = th > 1e-3
        Lq = None
        if B["qL"].any():
            Lq = self.dens.render(B["qpx"], B["qpy"], B["qrp"], B["qL"])
        if not hot.any() and Lq is None:
            return
        ys, xs = np.nonzero(hot | (Lq > 1e-3) if Lq is not None else hot)
        if not len(xs):
            return
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        # noise in world metres, on the density grid; rises at ~8 m/s and turns over (two tiles crossfaded) every ~3 s
        gr = self.dens.res
        hh = (np.arange(y0, y1, dtype=np.float32) + 0.5) * gr
        ww = (np.arange(x0, x1, dtype=np.float32) + 0.5) * gr
        X = (ww[None, :] - self.C[0]) / self.s + np.float32(self.pos[0])
        Y = (hh[:, None] - self.C[1]) / self.s + np.float32(self.pos[1]) + np.float32(8.0 * self.t)
        n = self.edge_noise.shape[0]
        ph = 2 * math.pi * self.t / 3.0
        g1 = sample_points(self.edge_noise, X / (FIRE_NOISE_M * n / 20), Y / (FIRE_NOISE_M * n / 20))
        g2 = sample_points(self.edge_noise, X / (FIRE_NOISE_M * n / 50) + 0.37, Y / (FIRE_NOISE_M * n / 50) + 0.61)
        g = g1 * math.cos(ph) + g2 * math.sin(ph)
        Tw = Tm[y0:y1, x0:x1] * (1 + FIRE_STIR * g)
        tw, tt = th[y0:y1, x0:x1], tau[y0:y1, x0:x1]
        L = (magazine.fire_luminance(Tw) / L_BG * EXPOSE * (1 - np.exp(-tw))
             * np.clip(tw / np.maximum(tt, 1e-6), 0, 1) ** FIRE_SKIN * hot[y0:y1, x0:x1])
        rgb = magazine.fire_rgb(Tw)
        rgb = rgb / np.maximum(rgb @ muzzle.LUM, 1e-3)[..., None]
        F = (L[..., None] * rgb).astype(np.float32)
        if Lq is not None:
            F += Lq[y0:y1, x0:x1, None] * SPARK
        Wf, Hf = self.W, self.H
        M = 60 // gr
        hy0, hx0 = max(0, y0 - M), max(0, x0 - M)
        hy1, hx1 = min(tau.shape[0], y1 + M), min(tau.shape[1], x1 + M)
        Fh = np.zeros((hy1 - hy0, hx1 - hx0, 3), np.float32)
        Fh[y0 - hy0:y1 - hy0, x0 - hx0:x1 - hx0] = F
        Ff = np.stack([upscale(Fh[..., i], gr * (hx1 - hx0), gr * (hy1 - hy0)) for i in range(3)], -1)
        bx0, by0 = gr * hx0, gr * hy0
        Ff = np.ascontiguousarray(Ff[:Hf - by0, :Wf - bx0])
        self._glow(frame, Ff, bx0, by0)

    def _glow(self, frame, F, bx0, by0):
        """Bloom on a compressed copy of the light F (display units, a window of the frame at bx0, by0), or a big
        flash paints the whole frame (research 7.2 item 6), then the luminance roll-off on what it adds only."""
        src = F / (1 + F / 6)
        g = self.glare
        for frac, r in ((0.20, 1), (0.10 + 0.6 * g, 6), (0.05 + 0.3 * g, 17)):
            for c in range(3):
                F[..., c] += frac * box_blur(src[..., c], r)
        sub = frame[by0:by0 + F.shape[0], bx0:bx0 + F.shape[1]]
        sub += tonemap(sub + F) - tonemap(sub)

    def _exposure(self, frame):
        """A warm exposure pulse at the main event and a short camera shake, both by the blast's lam (research 3.5).
        The shake's direction comes from the clock, not the scene's rng, so rendering never changes the sim."""
        dx = dy = 0.0
        for b in self.blasts:
            if b.shock is None:
                continue
            te = self.t - b.shock[1]
            lam = b.shock[2]
            if 0 <= te < 2:
                frame += np.float32(0.10 * min(1.0, lam / 60) * math.exp(-te / 0.25)) * np.array(
                    [1.0, 0.8, 0.6], np.float32)
                A = min(6.0, 0.05 * lam * self.s) * math.exp(-te / 0.3)
                dx += A * math.sin(97.0 * self.t)
                dy += A * math.cos(131.0 * self.t)
        return int(round(dx)), int(round(dy))

    def _smoke_fields(self):
        """Funnel smoke particles and every shot's gun smoke as blobs for one Density pass each: optical depth, the
        tau-weighted colour, and tau again moved along the sun by each blob's height for the shadows. A shot's puff
        (muzzle.py: its A, centre and spread) is drawn as SUB_PUFFS clumps scattered about its centre with their
        own slow drift, strung along the jet from the muzzle, sharing its A, so it breaks up like the funnel smoke rather than one disc. Its optical depth
        is shown at GUN_SMOKE_VIS of the research's (a look; the game's visibility uses the full value)."""
        sm = self.smoke
        px, py, r, w, h, cols = [], [], [], [], [], []
        if len(sm):
            x, y = self.scr(sm.d["x"], sm.d["y"])
            px.append(x), py.append(y), r.append(sm.radius() * self.s), w.append(1.4 * sm.opacity())
            h.append(sm.d["h"] + 4)
            cols.append(np.where(sm.d["coal"][:, None] > 0.5, np.array(SMOKE_COAL, np.float32),   # each ship's own
                                 np.array(SMOKE_OIL, np.float32)))
        for shot in self.shots:
            p = shot.puff(self.t)
            if p is None or p["A"] <= 0:
                continue
            k = len(shot.sub_w)
            sig = p["sh"] * SUB_SIGMA
            # strung along the jet from the muzzle (drifting with the wind) to the puff's centre and a little past
            root = shot.pos + WIND * p["age"]
            c = (root[None, :] + (p["xy"] - root)[None, :] * shot.sub_f[:, None] + shot.sub_off * p["sh"]
                 + shot.sub_vel * p["age"])
            x, y = self.scr(c[:, 0], c[:, 1])
            px.append(x), py.append(y), r.append(np.full(k, sig * self.s))
            w.append(self.smoke_vis * p["A"] * shot.sub_w / (2 * math.pi * sig * sig))
            h.append(np.full(k, p["z"]))
            # warm near the muzzle for NC powders, fading over about 5 s (research 7.4); water fog is white
            tint = SMOKE_NEUTRAL + (shot.D["tint"] - SMOKE_NEUTRAL) * math.exp(-p["age"] / 5.0)
            cc = (tint * p["A_p"] + 0.97 * p["A_w"]) / p["A"] * SMOKE_GAIN
            cols.append(np.broadcast_to(cc.astype(np.float32), (k, 3)))
            # its smoke ring (muzzle_blast_waves.md 5.3), when one formed: RING_BLOBS blobs around the ring, whose
            # axis is the bore, so from above a flat gun's ring is a bar across the bore and a raised gun's opens
            # into an ellipse
            rg = shot.ring(self.t)
            if rg is not None and rg["A"] > 0:
                ph = np.linspace(0, 2 * math.pi, RING_BLOBS, endpoint=False) + shot.lobes[0]
                n = np.array([-shot.hdir[1], shot.hdir[0]])
                c = (rg["xy"][None, :] + n[None, :] * (rg["R"] * np.cos(ph))[:, None]
                     + shot.hdir[None, :] * (rg["R"] * math.sin(shot.el) * np.sin(ph))[:, None])
                sig = RING_CORE * rg["R"]
                x, y = self.scr(c[:, 0], c[:, 1])
                px.append(x), py.append(y), r.append(np.full(RING_BLOBS, sig * self.s))
                w.append(np.full(RING_BLOBS, RING_VIS * self.smoke_vis * rg["A"] / RING_BLOBS / (2 * math.pi * sig * sig)))
                h.append(np.full(RING_BLOBS, rg["z"]))
                cols.append(np.broadcast_to(cc.astype(np.float32), (RING_BLOBS, 3)))
        if self.wreck is not None:   # the wreck's funnel smoke, the torn ends' fire smoke and the boilers' steam
            wr = self.wreck
            fk = 1.3 * (1.6 if self.coal else 1.0)      # sinkvid puffs are a little thinner than vidgen's funnels
            for ps, c, k in ((wr.smoke, SMOKE_COAL if self.coal else SMOKE_OIL, 1.4 * fk), (wr.blast, SMOKE_SOOT, 1.4),
                             (wr.steam, STEAM, 1.0)):
                if not len(ps):
                    continue
                x, y = self.scr(ps.d["x"] + self.pos_b[0], ps.d["y"] + self.pos_b[1])
                px.append(x), py.append(y), r.append(ps.radius() * self.s), w.append(k * ps.opacity())
                h.append(ps.d["h"] + 4)
                cols.append(np.broadcast_to(np.array(c, np.float32), (len(ps), 3)))
        shx, shy = list(px), list(py)    # where each blob's shadow is cast from (explosion puffs are drawn lifted)
        B = getattr(self, "_blobs", None)
        if B and B["n"]:
            px.append(B["px"]), py.append(B["py"]), r.append(B["rp"]), w.append(B["tau"])
            h.append(B["h"]), cols.append(B["col"])
            shx.append(B["sx"]), shy.append(B["sy"])
        z = np.zeros((self.dens.hh, self.dens.hw), np.float32)
        self._tau_ex = None
        if not px:
            return z, z[..., None], z
        px, py, r, w, h, cols, shx, shy = (np.concatenate(a) for a in (px, py, r, w, h, cols, shx, shy))
        tau = self.dens.render(px, py, r, w)
        col = np.stack([self.dens.render(px, py, r, w * cols[:, i]) for i in range(3)], -1)
        self._tau_ex = self.dens.render(B["px"], B["py"], B["rp"], B["tau"]) if B and B["n"] else None
        off = np.array(sun_offset_px(self.s, SUN_AZ, SUN_EL, 1.0))
        if B and B["n"] and B["deb"].any():     # debris casts small shadows too (it isn't smoke)
            dd = B["deb"]
            shx, shy = np.r_[shx, B["qsx"][dd]], np.r_[shy, B["qsy"][dd]]
            h, r, w = np.r_[h, B["qh"][dd]], np.r_[r, B["qrp"][dd]], np.r_[w, np.full(dd.sum(), 1.0)]
        shd = self.dens.render(shx + off[0] * h, shy + off[1] * h, r, w)
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
        frame interval (4 samples, so a flash shorter than a frame is dimmed, not missed). The primary and
        intermediate flashes are splatted as oriented gaussians with ANALYTIC normalisation (sigma at least 0.6 px),
        so they keep their total light at any zoom. The secondary fireball is a temperature field (_fireball). First
        the flashes light what's around them (_flash_light), then bloom on a compressed copy and a luminance
        roll-off to white, applied only to what the flash adds."""
        dt = 1.0 / self.fps
        subs = [self.t - dt * (i + 0.5) / 4 for i in range(4)]
        ems = []
        for shot in self.shots:
            if shot.t0 > self.t or shot.flash_end < self.t - dt:
                continue
            acc = {}
            for ts in subs:                              # latest first: its geometry is the one drawn
                for e in shot.emitters(ts):
                    a = acc.setdefault(e["kind"], [0.0, e, ts])
                    a[0] += e["I"] / 4
            ems += [(shot, I, e, ts) for I, e, ts in acc.values() if I > 0]
        if not ems:
            return
        self._flash_light(frame, ems)
        s, H, W = self.s, frame.shape[0], frame.shape[1]
        wins = []
        for shot, I, e, ts in ems:
            su = max(e["a"] * math.cos(shot.el) / 1.5, 0.6 / s)
            sv = max(e["b"] / 1.5, 0.6 / s)
            cx, cy = self.scr(e["c"][0], e["c"][1])
            # the fireball field fades in over 1.5-3 px across, the analytic splat out (no switch for a zoom to pop at)
            fire = (smoothstep((FIREBALL_R * min(e["b"], e["a"] * math.cos(shot.el)) * s - 1.5) / 1.5)
                    if e["kind"] == "secondary" else 0.0)
            ext = max(FIREBALL_R * 1.5 * max(e["a"] * math.cos(shot.el), e["b"]) if fire > 0 else 0.0,
                      3.5 * 1.3 * max(su, sv)) * s
            wins.append((shot, I, e, ts, su, sv, cx, cy, ext, fire))
        M = 60                                           # bloom reach (box blur r=17, 3 passes)
        bx0 = max(0, int(min(w[6] - w[8] for w in wins)) - M)
        by0 = max(0, int(min(w[7] - w[8] for w in wins)) - M)
        bx1 = min(W, int(max(w[6] + w[8] for w in wins)) + M + 1)
        by1 = min(H, int(max(w[7] + w[8] for w in wins)) + M + 1)
        if bx0 >= bx1 or by0 >= by1:
            return
        F = np.zeros((by1 - by0, bx1 - bx0, 3), np.float32)
        for shot, I, e, ts, su, sv, cx, cy, ext, fire in wins:
            x0, x1 = max(bx0, int(cx - ext)), min(bx1, int(cx + ext) + 1)
            y0, y1 = max(by0, int(cy - ext)), min(by1, int(cy + ext) + 1)
            if x0 >= x1 or y0 >= y1:
                continue
            dx = (np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5 - np.float32(cx)) / s
            dy = (np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5 - np.float32(cy)) / s
            ca, sa = math.cos(shot.az), math.sin(shot.az)
            u, v = dx * ca + dy * sa, -dx * sa + dy * ca
            if fire > 0:
                L, rgb = self._fireball(shot, e, ts, u, v)
                F[y0 - by0:y1 - by0, x0 - bx0:x1 - bx0] += (L * np.float32(fire * I / e["I"] / L_BG * EXPOSE))[..., None] * rgb
            if fire >= 1:
                continue
            # a fireball under a couple of pixels (or the primary and intermediate flashes): the analytic splat
            w = np.exp(-0.5 * ((u / su) ** 2 + (v / sv) ** 2))
            area = 2 * math.pi * su * sv
            Lpx = w * np.float32((1 - fire) * I / area / L_BG * EXPOSE)
            rgb = e["rgb"] / max(float(e["rgb"] @ muzzle.LUM), 1e-3)
            F[y0 - by0:y1 - by0, x0 - bx0:x1 - bx0] += Lpx[..., None] * rgb.astype(np.float32)
        self._glow(frame, F, bx0, by0)

    def _fireball(self, shot, e, ts, u, v):
        """The secondary flash as burning gas, not a sprite: a temperature field over the fireball's ellipse (u, v:
        metres along and across the bore), its luminance and colour from the blackbody and sodium ramps per pixel
        (research 2.6: drive brightness through T). DEPARTURE from the reference's single-temperature ellipse
        (research 7.2 asks for flipbooks with temperature in a channel; this is their procedural stand-in):
          - the core runs FIREBALL_CORE hotter than the emitter's T and the gas cools outward, so the edge isn't cut
            but burns down through yellow and orange to a red fringe (luminance is steep in T);
          - turbulence: two octaves of noise warp the radius into lobes and tongues and stir T by FIREBALL_STIR,
            in coordinates that grow with the ball and slide outward and churn over its life, so it billows;
          - late in the envelope T falls (the reference's 0.75 + 0.25 env), and the cooler gas drops out first,
            leaving hot pockets: the fireball breaks up instead of fading as one disc.
        Returns luminance (cd/m^2, physical, before the frame-average scaling) and unit-luminance rgb."""
        tt = max(ts - shot.t0, 1e-4)
        life = tt / shot.t_s
        ce = math.cos(shot.el)
        ra, rb = max(0.8 * e["a"] * ce, 0.6 / self.s), max(0.8 * e["b"], 0.6 / self.s)
        un, vn = u / ra, v / rb
        o0, o1 = shot.noise_off
        # the turbulence's features grow a little faster than the ball (they roll outward) and churn
        k = 1.0 / (1.0 + 0.35 * life)
        n1 = sample_points(self.edge_noise, un * 0.33 * k + o0 + 0.12 * life, vn * 0.33 * k + o1 - 0.07 * life)
        n2 = sample_points(self.edge_noise, un * 0.6 * k + o1 - 0.2 * life, vn * 0.6 * k + o0 + 0.15 * life)
        ang = np.arctan2(vn, un)
        lobes = 1 + 0.16 * np.sin(3 * ang + shot.lobes[0]) + 0.10 * np.sin(5 * ang + shot.lobes[1])
        q = np.sqrt(un * un + vn * vn) / (lobes * (1 + 0.20 * n1 + 0.07 * n2))
        Tc = e["T"] * (1 + FIREBALL_CORE)
        T = Tc * (1 - FIREBALL_FALL * np.minimum(q, 1.6) ** 2) * (1 + FIREBALL_STIR * (0.6 * n2 + 0.4 * n1))
        # optical thickness: the path through an ellipsoid, thinning to nothing at q = FIREBALL_R
        path = np.sqrt(np.clip(1 - (q / FIREBALL_R) ** 2, 0, 1))
        eps = 1 - np.exp(-(rb * path) / 6.0)
        L = eps * muzzle.bb_luminance_v(T) * np.float32(e["env"])
        return L, muzzle.flash_rgb_v(T)

    def _flash_light(self, frame, ems):
        """The flashes as point lights on everything already drawn: deck, turrets, smoke and sea (research 7.3).
        Illuminance on a surface below the emitter E = I (h + FLASH_WRAP rho) / (d^2 + r0^2)^1.5, h the emitter's
        height over the surface (the height map; the sea at 0), rho the ground distance, r0 the source's size;
        FLASH_WRAP stands for the rough and vertical faces that turn toward it. Against the sun's E_SUN on the
        same surfaces, it raises each pixel's own colour, warm, capped at FLASH_LIGHT_MAX x. Worked out on a
        quarter-res grid and upsampled. Day only: by day it's a warm pool, not the night's orange-lit cloud."""
        s, H, W = self.s, frame.shape[0], frame.shape[1]
        st = 4
        lights = []
        for shot, I, e, ts in ems:
            r0 = 0.6 * max(e["a"], e["b"])
            R = min(400.0, (I * max(e["c"][2], 1.0) / (0.02 * E_SUN)) ** (1 / 3) + r0)
            cx, cy = self.scr(e["c"][0], e["c"][1])
            lights.append((I, e, cx, cy, R * s, r0))
        x0 = max(0, int(min(l[2] - l[4] for l in lights)) // st * st)
        y0 = max(0, int(min(l[3] - l[4] for l in lights)) // st * st)
        x1 = min(W, int(max(l[2] + l[4] for l in lights)) + st)
        y1 = min(H, int(max(l[3] + l[4] for l in lights)) + st)
        if x0 >= x1 or y0 >= y1:
            return
        gx = np.arange(x0, x1, st, dtype=np.float32) + st / 2
        gy = np.arange(y0, y1, st, dtype=np.float32) + st / 2
        hs = self.Hs[y0:y1:st, x0:x1:st][:len(gy), :len(gx)]
        acc = np.zeros((len(gy), len(gx), 3), np.float32)
        for I, e, cx, cy, Rp, r0 in lights:
            dx = (gx - np.float32(cx))[None, :] / s
            dy = (gy - np.float32(cy))[:, None] / s
            rho2 = dx * dx + dy * dy
            h = np.maximum(np.float32(e["c"][2]) - hs, 0.5)
            E = np.float32(I) * (h + FLASH_WRAP * np.sqrt(rho2)) / (rho2 + h * h + r0 * r0) ** 1.5
            rgb = (e["rgb"] / max(float(e["rgb"] @ muzzle.LUM), 1e-3)).astype(np.float32)
            acc += (E / np.float32(E_SUN))[..., None] * rgb
        acc = np.minimum(acc, FLASH_LIGHT_MAX)
        Hw, Ww = y1 - y0, x1 - x0
        g = np.stack([np.asarray(Image.fromarray(acc[..., c], "F").resize((len(gx) * st, len(gy) * st),
                                                                       Image.BILINEAR))[:Hw, :Ww] for c in range(3)], -1)
        win = frame[y0:y0 + g.shape[0], x0:x0 + g.shape[1]]
        # diffuse surfaces (deck, hull, smoke, foam: warm or neutral) take the light by their own colour; the sea
        # (blue) mostly mirrors the sky, which the flash doesn't change, so it takes almost none (lit by its colour,
        # the frosted sea went green)
        take = np.clip(1 - (win[..., 2] - win[..., 0]) / 0.08, 0.05, 1.0)[..., None]
        win += win * g * take

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
        if self.t_hit is not None and t >= self.t_hit:
            phase = "Hit" if t < self.t_hit + magazine.HIT_LEAD else "Magazine explosion"
        if self.broken() and t >= self.t_break + 6:
            phase = self.wreck._break_phase()
        m = self.Ho // 36
        d.text((m, m), phase, font=self.font_small, fill=(235, 240, 242, 220))
        if self.has_guns and t >= REST_S - 0.5:
            b = self.target_bearing
            dvec = unit(self.heading + b)
            # where the ray from the ship's centre leaves the frame, pulled in by a margin
            ts = []
            for i, lim in ((0, self.Wo), (1, self.Ho)):
                if abs(dvec[i]) > 1e-6:
                    for edge in (m * 2, lim - m * 2):
                        tt = (edge - self.C_out[i]) / dvec[i]
                        if tt > 0:
                            ts.append(tt)
            tt = min(ts)
            p = self.C_out + dvec * tt
            n = rot(np.array([1.0, 0]), self.heading + b)
            q = rot(np.array([0, 1.0]), self.heading + b)
            sz = self.Ho / 50
            tri = [tuple(p), tuple(p - n * sz * 1.6 + q * sz * 0.8), tuple(p - n * sz * 1.6 - q * sz * 0.8)]
            alpha = int(200 * min(1.0, (t - REST_S + 0.5) / 0.5))
            d.polygon(tri, fill=(230, 60, 50, alpha))
            d.text(tuple(p - n * sz * 3.4 - np.array([sz, sz * 0.6])), "target", font=self.font_small,
                   fill=(235, 220, 215, alpha))
        return np.asarray(im)


# ---------------------------------------------------------------- driver
def make(src, out: Path, args, still=None, frames=None):
    """Render one clip (or one PNG at `still` s) of one ship, or of a line of them (src a list, the lead first). frames=(a, b): only frames a..b-1, to out (a chunk of a clip
    rendered in parallel: the scene is rebuilt from the seed and stepped to frame a, and drawing never touches the
    sim, so every chunk sees the same scene)."""
    sc = Scene(src, args.w, args.h, args.fps, args.heading, args.target, args.seed, args.seconds, args.propellant,
               args.explode, args.tier, args.explode_at, sea_args(args), args.sink, args.spacing, args.fire,
               args.fit, args.scale)
    if not args.quiet:
        i = sc.wake_info
        print(f"  {sc.src.name} wake: Fr_L {i['FrL']:.2f}, Zb {i['Zb']:.1f} m, solve {i['solve'][0]}x{i['solve'][1]}, "
              f"grid {i['grid'][0]}x{i['grid'][1]}, bake {i['t_total'] * 1000:.0f} ms, "
              f"setup {i['t_setup'] * 1000:.0f} ms")
        for b in sc.blasts:
            sp = b.s
            print(f"  {sp['id']}: {sp['tier']}, M {sp['M'] / 1000:.1f} t, fireball {sp['D']:.0f} m / {sp['t_fb']:.1f} s, "
                  f"lam {sp['lam']:.0f} m, {len(sp['openings'])} openings, main at {sp['t_main']:.1f} s")
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
    a, b = frames or (0, n)
    import imageio_ffmpeg
    w = imageio_ffmpeg.write_frames(str(out), (args.w, args.h), fps=args.fps, codec="libx264",
                                    pix_fmt_out="yuv420p", macro_block_size=1,
                                    output_params=["-crf", str(args.crf), "-preset", "medium",
                                                   "-movflags", "+faststart"])
    w.send(None)
    for i in range(min(b, n)):
        if i >= a:
            w.send(np.ascontiguousarray(sc.render()).tobytes())
        sc.step(dt)
        if i % args.fps == 0 and not args.quiet:
            print(f"\r  {out.name}: {i / args.fps:4.1f}/{sc.duration:.1f} s", end="", flush=True)
    w.close()
    if frames is None:
        print(f"\r  {out.name}: {sc.duration:.1f} s, {n} frames")
    return out


# ---------------------------------------------------------------- the zoom (user, 2026-10-08): one ship close up, out
# to reveal it was a squadron, ending at the strategic scale
ZOOM_S = (4.0, 0.25)      # px/m at the start (one Lion fills about half a 1080p frame) and the end (strategic)
ZOOM_T = (9.0, 18.0, 8.0) # s: held close (training, the first salvos), zooming out, held at the strategic scale
ZOOM_STEP = math.sqrt(2)  # the levels' scales apart: each frame is drawn from the level at or just above its scale
ZOOM_HUD = (2.8, 2.0)     # px/m: the caption crossfades from the lead's to the line's as the next ship comes in
ZOOM_FEAT = 0.6           # m: the wake foam's clump size, fixed through a zoom (its lace fades as it goes sub-pixel)


class Zoom:
    """The zoom's timeline: s(t) holds, then runs smootherstep in log s, then holds. The camera's centre (world
    metres from the line's centre) goes from the lead ship to a little behind the line's centre as the view widens,
    u = (1/s - 1/s0) / (1/s1 - 1/s0), so the lead stays put while close and the line slides in as it opens."""

    def __init__(self, W, H, fps, heading, lead_off):
        self.W, self.H, self.fps = W, H, fps
        self.n = int(round(sum(ZOOM_T) * fps))
        s0, s1 = ZOOM_S
        self.levels = []
        v = s0
        while v > s1 * 1.0001:
            self.levels.append(v)
            v /= ZOOM_STEP
        self.levels.append(s1)
        h = unit(heading)
        self.focus = h * lead_off
        self.end = -h * (0.07 * W / s1)          # the line a little ahead of centre, as in a still clip

    def s(self, t):
        a, b, _ = ZOOM_T
        x = smootherstep(min(1.0, max(0.0, (t - a) / b)))
        return math.exp(math.log(ZOOM_S[0]) + (math.log(ZOOM_S[1]) - math.log(ZOOM_S[0])) * x)

    def u(self, s):
        s0, s1 = ZOOM_S
        return (1 / s - 1 / s0) / (1 / s1 - 1 / s0)

    def cam(self, s):
        u = self.u(s)
        return self.focus * (1 - u) + self.end * u

    def level(self, s):
        return max(k for k, v in enumerate(self.levels) if v >= s * 0.9999)

    def view(self, k):
        """Level k's canvas: (W, H, C), covering every frame drawn from it, with the line's centre at C."""
        sk = self.levels[k]
        lo, hi = np.array([np.inf, np.inf]), np.array([-np.inf, -np.inf])
        for i in range(self.n):
            s = self.s(i / self.fps)
            if self.level(s) != k:
                continue
            c = self.cam(s) * sk
            half = np.array([self.W, self.H]) / 2 * sk / s
            lo, hi = np.minimum(lo, c - half), np.maximum(hi, c + half)
        lo, hi = np.floor(lo) - 4, np.ceil(hi) + 4
        Wc, Hc = (int(v) + int(v) % 2 for v in hi - lo)
        return Wc, Hc, -lo


def make_zoom(srcs, out: Path, args, frames=None, stills=None):
    """The zoom clip (or frames a..b-1 of it, a chunk): every level is a Scene at its own fixed scale with the
    same seed, so they all run the same sim (smoke, salvos) and any of them can draw a frame. A frame is drawn
    bare from its level's scene with the looks set to its own scale, cut around the camera, downsampled
    (Lanczos, by up to ZOOM_STEP), then the HUD goes on with a scale bar. Scenes are made when first needed and
    stepped up to the clip's time; a zoom only goes out, so a scene is dropped once it's passed. stills: frame
    indices to write as PNGs beside `out` instead of a clip."""
    W, H, fps = args.w, args.h, args.fps
    probe = Scene(srcs, 320, 180, fps, args.heading, args.target, args.seed, scale=0.1)
    z = Zoom(W, H, fps, args.heading, probe.ships[0].off)
    del probe
    dt = 1.0 / fps
    a, b = frames or ((min(stills), max(stills) + 1) if stills else (0, z.n))
    scenes = {}
    huds = None
    import imageio_ffmpeg
    if not stills:
        w = imageio_ffmpeg.write_frames(str(out), (W, H), fps=fps, codec="libx264", pix_fmt_out="yuv420p",
                                        macro_block_size=1, output_params=["-crf", str(args.crf), "-preset", "medium",
                                                                           "-movflags", "+faststart"])
        w.send(None)
    for i in range(a, b):
        t = i / fps
        s = z.s(t)
        k = z.level(s)
        if stills and i not in stills:
            for sc_ in scenes.values():
                sc_.step(dt)
            continue
        if k not in scenes:
            for j in [j for j in scenes if j < k]:
                del scenes[j]
            Wc, Hc, C = z.view(k)
            sc = Scene(srcs, W, H, fps, args.heading, args.target, args.seed, seconds=sum(ZOOM_T),
                       propellant=args.propellant, sea=sea_args(args), spacing=args.spacing, fire_s=sum(ZOOM_T),
                       scale=z.levels[k], view=(Wc, Hc, C, W, H), feat_m=ZOOM_FEAT)
            sc.bare = True
            for _ in range(int(WARM_S * fps)):
                sc.step(dt)
            sc.t = 0.0
            sc.next_ev = 0
            for _ in range(i):
                sc.step(dt)
            scenes[k] = sc
            if not args.quiet:
                print(f"\n  level {k}: {z.levels[k]:.3g} px/m, canvas {Wc}x{Hc}", flush=True)
        sc = scenes[k]
        sc.set_look(s)
        img = Image.fromarray(sc.render())
        sk = sc.s
        c = sc.C + z.cam(s) * sk
        hw, hh = W / 2 * sk / s, H / 2 * sk / s
        img = img.resize((W, H), Image.LANCZOS, box=(c[0] - hw, c[1] - hh, c[0] + hw, c[1] + hh))
        u = z.u(s)
        sc.C_out = np.array([W / 2, H / 2]) + (z.focus * (1 - u) - z.cam(s)) * s    # the marker leaves the lead,
        if huds is None:                                                            # then the line's centre
            huds = (sc._hud(single=True).astype(np.float32), sc.hud.astype(np.float32))
        m = smoothstep(math.log(ZOOM_HUD[0] / s) / math.log(ZOOM_HUD[0] / ZOOM_HUD[1]))
        hud = (huds[0] * (1 - m) + huds[1] * m).astype(np.uint8)
        fr = np.ascontiguousarray(sc.compose(np.asarray(img), scale_bar=s, hud=hud))
        if stills:
            Image.fromarray(fr).save(out.parent / f"{out.stem}_{i:04d}_L{k}.png")
        else:
            w.send(fr.tobytes())
        for sc_ in scenes.values():
            sc_.step(dt)
        if i % fps == 0 and not args.quiet:
            print(f"\r  {out.name}: {t:4.1f}/{sum(ZOOM_T):.1f} s, {s:.3g} px/m", end="", flush=True)
    if not stills:
        w.close()
    return out


def make_zoom_chunked(srcs, out: Path, args, chunks):
    """make_zoom in `chunks` parallel parts, joined without re-encoding (as make_chunked)."""
    from concurrent.futures import ProcessPoolExecutor
    import imageio_ffmpeg
    import subprocess
    n = int(round(sum(ZOOM_T) * args.fps))
    tmp = out.parent / (out.stem + "_parts")
    tmp.mkdir(exist_ok=True)
    cuts = [round(n * j / chunks) for j in range(chunks + 1)]
    parts = [tmp / f"part{j:02d}.mp4" for j in range(chunks)]
    args.quiet = True
    t0 = time.time()
    with ProcessPoolExecutor(chunks) as pool:
        list(pool.map(make_zoom, [srcs] * chunks, parts, [args] * chunks,
                      [(cuts[j], cuts[j + 1]) for j in range(chunks)]))
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts))
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-c", "copy", "-movflags", "+faststart", str(out)], check=True)
    for p in parts + [lst]:
        p.unlink()
    tmp.rmdir()
    print(f"  {out.name}: {n} frames in {chunks} parts, {time.time() - t0:.0f} s")
    return out


def make_chunked(src, out: Path, args, chunks):
    """One clip rendered as `chunks` parts in parallel processes, then joined without re-encoding. Each part
    steps the scene from the start (cheap next to drawing). Parts go to a scratch folder beside the output, so no
    two processes ever write one file."""
    from concurrent.futures import ProcessPoolExecutor
    import shutil
    import subprocess
    import imageio_ffmpeg
    sc = Scene(src, args.w, args.h, args.fps, args.heading, args.target, args.seed, args.seconds, args.propellant,
               args.explode, args.tier, args.explode_at, sea_args(args), args.sink, args.spacing, args.fire,
               args.fit)
    n = int(round(sc.duration * args.fps))
    for b in sc.blasts:
        sp = b.s
        print(f"  {sp['id']}: {sp['tier']}, M {sp['M'] / 1000:.1f} t, fireball {sp['D']:.0f} m / {sp['t_fb']:.1f} s, "
              f"lam {sp['lam']:.0f} m, {len(sp['openings'])} openings, main at {sp['t_main']:.1f} s")
    del sc
    tmp = out.parent / f".{out.stem}_parts"
    tmp.mkdir(exist_ok=True)
    cuts = [round(n * i / chunks) for i in range(chunks + 1)]
    parts = [tmp / f"part{i:02d}.mp4" for i in range(chunks)]
    quiet = args.quiet
    args.quiet = True
    t0 = time.perf_counter()
    with ProcessPoolExecutor(chunks) as pool:
        futs = [pool.submit(make, src, parts[i], args, None, (cuts[i], cuts[i + 1])) for i in range(chunks)]
        for f in futs:
            f.result()
    args.quiet = quiet
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts))
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-c", "copy", "-movflags", "+faststart", str(out)], check=True)
    shutil.rmtree(tmp)
    print(f"  {out.name}: {n / args.fps:.1f} s, {n} frames in {chunks} parts, {time.perf_counter() - t0:.0f} s")
    return out


def sea_args(args):
    sea = {"beaufort": args.beaufort}
    if args.swell:
        sea["swell"] = tuple(float(v) for v in args.swell.split(","))
    return sea


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ships", nargs="+",
                    help="out_designs/<id> folders or ids, or 'all'; ids joined by '+' (invincible+inflexible) "
                         "steam in line ahead in one clip, the first leading")
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
    ap.add_argument("--chunks", type=int, default=0,
                    help="one ship's clip rendered in this many parallel parts (default: up to 6 for one ship; "
                         "memory bandwidth, not cores, is the limit past that)")
    ap.add_argument("--explode", default=None,
                    help="blow up a magazine: its room id ('Magazine Y') or a mount it serves ('Y'); several "
                         "comma-separated go up in turn (tier 4). Writes <id>_explode_<mag>.mp4")
    ap.add_argument("--tier", choices=("blast", "column"), default="blast",
                    help="blast: fireball, gunhouse thrown (tier 3); column: the roof lifts and the barbette vents a "
                         "flame column, the ship fights on (tier 1)")
    ap.add_argument("--sink", action="store_true",
                    help="with --explode (blast): the explosion breaks her in two at the magazines and both halves "
                         "sink (sinkvid's break). Writes <id>_explode_<mag>_sink.mp4")
    ap.add_argument("--explode-at", type=float, default=None,
                    help=f"time of the hit, s (default: {EXPLODE_AFTER:g} s after the first salvo)")
    ap.add_argument("--fire", type=float, default=FIRE_S,
                    help=f"how long the guns fire, s (default {FIRE_S:g})")
    ap.add_argument("--fit", type=float, default=None,
                    help="zoom: the share of the frame the ship or line fills, across and down (default 0.8 x 0.62; "
                         f"{EXPLODE_FIT:g} in explosion clips); 0.17 is a strategic view")
    ap.add_argument("--scale", type=float, default=None,
                    help="zoom as px per metre, in place of --fit (the strategic view of a four-ship line at "
                         "1920x1080 is about 0.25)")
    ap.add_argument("--zoom", action="store_true",
                    help="the zoom demo: one ship close up, out to the whole line, ending at the strategic scale "
                         f"({ZOOM_S[0]:g} to {ZOOM_S[1]:g} px/m). Writes <ids>_zoom.mp4")
    ap.add_argument("--spacing", type=float, default=LINE_SPACING,
                    help=f"a line's distance between ships, centre to centre, m (default {LINE_SPACING:g}, ~2 cables)")
    ap.add_argument("--beaufort", type=float, default=None,
                    help=f"sea state for the waves (default: the smoke's {SEA_WIND:g} m/s wind, about 3); the smoke "
                         "keeps its own wind")
    ap.add_argument("--swell", default=None,
                    help="swell as HS,TP,FROM: height m, period s, compass bearing it comes from (north is screen "
                         f"up; default {','.join(f'{v:g}' for v in SWELL)}; 0,10,0 for none)")
    args = ap.parse_args()
    args.w, args.h = (int(v) for v in args.size.lower().split("x"))
    if args.w % 2 or args.h % 2:
        ap.error("--size must be even in both dimensions")
    base = Path(args.designs)
    def find(s):
        return Path(s) if (Path(s) / "sprite.json").exists() else base / s
    # each entry is one clip: one ship, or a line of them
    srcs = [[p.parent] for p in sorted(base.glob("*/sprite.json"))] if args.ships == ["all"] else [
        [find(s) for s in arg.split("+") if s] for arg in args.ships]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ext = ".png" if args.still is not None else ".mp4"
    tag = ""
    if args.explode:
        args.explode = [m.strip() for m in args.explode.split(",") if m.strip()]
        tag = "_explode_" + "_".join(re.sub(r"\W+", "", m.replace("Magazine", "")) for m in args.explode)
        tag += "_column" if args.tier == "column" else ""
        tag += "_sink" if args.sink and args.tier == "blast" else ""
    if args.fit:
        tag += f"_fit{args.fit:g}"
    if args.scale:
        tag += f"_s{args.scale:g}"
    if args.sink and (not args.explode or args.tier != "blast"):
        ap.error("--sink needs --explode with --tier blast")
    if args.explode and any(len(g) > 1 for g in srcs):
        ap.error("--explode is for one ship for now, not a line")
    if args.zoom:
        if len(srcs) != 1 or args.explode or args.still is not None:
            ap.error("--zoom takes one ship or one line, no --explode or --still")
        group = srcs[0]
        name = "+".join(p.name for p in group)
        path = out / f"{name}_zoom.mp4"
        chunks = args.chunks or min(6, os.cpu_count() or 1)
        print(f"wrote {make_zoom_chunked(group if len(group) > 1 else group[0], path, args, chunks)}")
        return
    todo = []
    for group in srcs:
        missing = [s for s in group if not (s / "sprite.json").exists()]
        if missing:
            print(f"skip {'+'.join(str(s) for s in group)}: no sprite.json in {missing[0]}", file=sys.stderr)
            continue
        name = "+".join(s.name for s in group)
        todo.append((group[0] if len(group) == 1 else group, out / f"{name}{tag}{ext}"))
    jobs = max(1, min(args.jobs or os.cpu_count() or 1, len(todo)))
    args.quiet = jobs > 1          # interleaved progress lines would be noise; report each ship as it finishes
    chunks = args.chunks or (min(6, os.cpu_count() or 1) if len(todo) == 1 else 1)
    if args.still is None and len(todo) == 1 and chunks > 1:
        print(f"wrote {make_chunked(*todo[0], args, chunks)}")
        return
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
