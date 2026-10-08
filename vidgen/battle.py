"""
battle: two lines of battle firing at each other (user, 2026-10-08: "2 battlelines firing at each other in anger
for the visual feel", no explosions). vidgen's Scene places the lines and draws; this module holds the gunnery
(where a salvo falls) and what the fall of shot looks like (Splash, Hit). The splash follows shell_splashes.md (the
user's implementation brief: anatomy, sizes by calibre, angle of fall, salvo ripple, dye, animation curves). numpy
only, units metres and seconds, world axes as vidgen's (screen x right, y down, z up).

The look, not a ballistics model. My picks, each marked where it's used:
  - Range is compressed: the lines steam a couple of km apart so both fit one frame (real battle ranges, 12-18 km,
    would put the enemy 20 frames away at the squadron scale). Everything about the fall of shot that depends on
    range (angle of fall, the salvo pattern, spotting errors) is taken at a separate `fall range` (FALL_RANGE,
    Jutland-like), so splashes look as they would at a real range while the lines sit close on screen.
  - Shells fly the vacuum path over the compressed range on a clock stretched so the flight takes at least TOF_MIN:
    flash, a pause, then the splashes, the rhythm of a gunnery duel (a real 14 km flight is ~23 s).
  - Spotting: each battery's salvo has a mean point of impact off the target by a range error that starts at
    BRACKET0 of the fall range, flips over/short and shrinks by BRACKET_K each salvo (the bracket closing) to
    BRACKET_MIN, plus a line error. Shells fall about it in a pattern ~6x longer in range than across (brief: 5-8x;
    ~250 m long at 14 km, as USS Massachusetts' at Casablanca).
  - A shell whose fall is inside the target's waterline is a hit: no column (brief), a flash, a fire and a smoke
    trail; no damage.

What the brief's realtime design does with LOD tiers vidgen gets from its conserving splats (Density): a column
under a pixel is drawn widened and proportionally fainter, so splashes fade with altitude and never pop.
"""
from __future__ import annotations

import math

import numpy as np

G = 9.81
TOF_MIN = 5.0             # s: the shortest drawn flight (compressed ranges are flown in 2-4 s)
FALL_RANGE = 14000.0      # m: the range the fall of shot is drawn for (Jutland: 12-18 km)
BRACKET0 = 0.04           # the first salvo's mean range error, share of the fall range (~560 m at 14 km)
BRACKET_K = 0.55          # each next salvo's mean error against the last (and flipped over/short)
BRACKET_MIN = 0.005       # the mean error never closes below this share (spotting, rolling, the enemy's helm)
LINE_ERR = 0.002          # the mean point's error across the line of fire, share of fall range (1 sigma)
DISP = 0.0045             # one shell's spread about the salvo's mean along the line of fire, share of fall range
DISP_X = 1 / 6            # ... and across it, against the spread along (brief: patterns 5-8x longer than wide)
SEC_DISP = 2.0            # secondaries spread this much more
LAND_JITTER = 0.12        # s: time-of-flight jitter (1 sigma), so a salvo lands as a ripple (brief: 0.2-0.5 s)
H16, K_CAL = 73.0, 1.0    # brief: column height H16 (d / 0.406 m)^k
SPLASH_TAU = 2.4          # a column blob's optical depth at its core (dense spray: white and opaque)
MIST_S = 9.0              # s: the mist's fade (brief: residue drifts 10-60 s; here it's thin by then)
MIST_TAU = 0.35           # the mist's core optical depth against a column's (a full salvo's mist stacked into a
                          # white wall at 1.5)
FOAM_LIFE = (30.0, 60.0)  # s: the foam disc (brief)
HIT_FIRE_S = (12.0, 30.0) # s: how long a hit burns (random within)
RICOCHET_P = 0.3          # chance of a ricochet at a very flat fall, fading out by 8 degrees (brief: sub-8 deg)

# the brief's US 16" Mk 8 range table: range (km) -> angle of fall (deg); shorter/longer ranges extrapolate flat
FALL_TABLE = ((0.0, 0.0), (4.6, 2.9), (9.1, 6.8), (18.3, 17.9), (27.4, 34.1), (32.0, 44.9))
# dye loads (brief): a colour-blind-safe set (Okabe-Ito), muted further where it's mixed in; unique within a line
DYES = {"orange": (0.90, 0.62, 0.0), "sky": (0.34, 0.71, 0.91), "green": (0.0, 0.62, 0.45),
        "yellow": (0.94, 0.89, 0.26), "blue": (0.0, 0.45, 0.70), "red": (0.84, 0.37, 0.0),
        "pink": (0.80, 0.47, 0.65)}
DYE_ERAS = ("wwii", "cold_war")   # dye 'auto': navies dyed their splashes from about 1930 (USN), so the looks
                                 # of those eras; earlier ones splash white


def tof(v0, el):
    return 2 * v0 * math.sin(el) / G


def angle_of_fall(range_m):
    """Degrees, from the brief's table (linear between rows, the last slope beyond)."""
    km = range_m / 1000
    t = FALL_TABLE
    for (r0, a0), (r1, a1) in zip(t, t[1:]):
        if km <= r1:
            return a0 + (a1 - a0) * (km - r0) / (r1 - r0)
    (r0, a0), (r1, a1) = t[-2], t[-1]
    return min(80.0, a1 + (a1 - a0) * (km - r1) / (r1 - r0))


def in_poly(pt, poly):
    """Point in polygon (ray casting)."""
    x, y = pt
    px, py = poly[:, 0], poly[:, 1]
    qx, qy = np.roll(px, -1), np.roll(py, -1)
    c = ((py > y) != (qy > y)) & (x < (qx - px) * (y - py) / np.where(qy != py, qy - py, 1e-12) + px)
    return bool(np.count_nonzero(c) % 2)


def smoothstep(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


class Gunnery:
    """The fall of each battery's salvos: per (ship, battery), the salvo count and its mean point's error."""

    def __init__(self, rng, fall_range=FALL_RANGE):
        self.rng = rng
        self.fall_range = fall_range
        self.theta = angle_of_fall(fall_range)
        self.state = {}

    def aim(self, key, t, main):
        """The aim offset (along the line of fire, across it) in metres for one shell of the salvo `key` fired at t.
        A new salvo starts when the battery hasn't fired for a second."""
        rng, R = self.rng, self.fall_range
        st = self.state.get(key)
        if st is None or t - st["t"] > 1.0:
            n = 0 if st is None else st["n"] + 1
            sign = rng.choice((-1.0, 1.0)) if st is None else -st["sign"]
            mean = max(BRACKET0 * BRACKET_K ** n, BRACKET_MIN) * R * sign * rng.uniform(0.6, 1.2)
            st = dict(n=n, sign=sign, mean=mean, line=rng.normal(0, LINE_ERR * R), t=t)
            self.state[key] = st
        st["t"] = t
        k = 1.0 if main else SEC_DISP
        along = st["mean"] + rng.normal(0, DISP * R * k)
        across = st["line"] + rng.normal(0, DISP * DISP_X * R * k)
        return along, across


class Splash:
    """A shell's fall in the sea at xy (world, metres) at t0: calibre d (m), travelling along `travel` (unit
    vector) at angle of fall theta (deg), with a dye (rgb or None). Analytic in time, drawn as blobs in vidgen's
    smoke field (lifted up the screen by height, so a column reads as a pillar from above, and casting its long
    shadow). The brief's anatomy and curves, with t_a = sqrt(2H/g) and tau = t/t_a:
      - impact crown, 0-0.3 s: a low white cone ~2 widths across;
      - the column: top h = H alpha(theta) (1 - (1 - min(tau, 1))^2), opacity 1 then exp(-1.5 (tau - 1)), leaning
        along the travel at a flat fall;
      - apex blossom: the crown opens from 0.5 to 2 widths over tau 0.8-1.6;
      - base surge: a low ring out to 2.5 widths by tau 2.5, gone by 4;
      - mist: drifts downwind and thins over MIST_S;
      - dye: 0.1 at the base to 0.5 at the crown, 0.2 at impact to 0.6 by tau 1.5 (of the dye's mix).
    The foam disc (1.5 widths, 30-60 s, an ellipse along the track at a flat fall) is the caller's (vidgen's foam
    particles)."""
    COL = 14
    CROWN = 8
    SURGE = 10
    MIST = 8

    def __init__(self, xy, d, t0, travel, theta, dye, rng):
        self.xy, self.d, self.t0 = np.asarray(xy, float), d, t0
        self.travel = np.asarray(travel, float)
        self.theta = theta
        self.alpha = 0.5 + 0.5 * smoothstep((theta - 3.0) / 12.0)     # brief: 0.5 at 3 deg, 1 above 15
        self.H = H16 * (d / 0.406) ** K_CAL * self.alpha * rng.uniform(0.85, 1.1)
        self.t_a = math.sqrt(2 * H16 * (d / 0.406) ** K_CAL / G)       # timing by the full height (brief's table)
        self.Wd = 25.0 * d                                             # column width
        self.lean = 0.6 * (1 - smoothstep((theta - 2.0) / 13.0))       # m across per m up, along the travel
        self.dye = None if dye is None else np.asarray(dye, np.float32)
        self.jit = rng.normal(0, 0.2, (self.COL, 2)) * self.Wd          # a ragged, not capsule, column
        self.w = rng.uniform(0.6, 1.4, self.COL)
        self.rk = rng.uniform(0.7, 1.3, self.COL)
        self.crown_k = rng.uniform(0.6, 1.5, self.CROWN)
        self.ring = rng.uniform(0, 2 * math.pi) + np.linspace(0, 2 * math.pi, 64, endpoint=False)
        self.mist_off = rng.normal(0, 0.6, (self.MIST, 2))
        self.mist_w = rng.uniform(0.6, 1.4, self.MIST)
        self.life = 2.5 * self.t_a + 2.5 * MIST_S

    def _ring(self, n, k, R):
        a = self.ring[k:k + n]
        return np.stack([np.cos(a), np.sin(a)], 1) * R

    def parcels(self, t, wind, white):
        """The blobs' xy (world), height z, radius r (m), core optical depth and rgb at t; None when gone."""
        tt = t - self.t0
        if tt < 0 or tt > self.life:
            return None
        Wd, tau = self.Wd, tt / self.t_a
        wind = np.asarray(wind, float)
        white = np.asarray(white, np.float32)
        out = []

        def dyed(f, n):
            if self.dye is None:
                return np.broadcast_to(white, (n, 3))
            m = (0.1 + 0.4 * f) * min(1.0, (0.2 + 0.4 * min(tau / 1.5, 1.0)) / 0.6)
            m = np.broadcast_to(np.asarray(m, np.float32), (n,))[:, None]
            return white * (1 - m) + self.dye * m

        # the impact crown: a thin low cone, the first 0.3 s
        if tt < 0.45:
            k = smoothstep(tt / 0.1) * (1 - smoothstep((tt - 0.25) / 0.2))
            xy = self.xy + self._ring(self.CROWN, 0, Wd * (0.6 + 2.0 * tt))
            out.append((xy, np.full(self.CROWN, 4.0 + 20 * tt), np.full(self.CROWN, 0.25 * Wd),
                        np.full(self.CROWN, SPLASH_TAU * 0.8 * k), dyed(0.0, self.CROWN)))
        # the column, from the sea to its top, leaning along the travel
        rho = 1.0 if tau < 1 else math.exp(-1.5 * (tau - 1))
        top = self.H * (1 - (1 - min(tau, 1.0)) ** 2)
        if top > 0.5 and rho > 0.01:
            f = np.linspace(0, 1, self.COL)
            z = top * f
            fall = max(tau - 1, 0.0)
            xy = (self.xy + self.travel[None, :] * (self.lean * z)[:, None] + self.jit * (1 + fall)
                  + wind[None, :] * 0.25 * tt * f[:, None])
            r = Wd * (0.32 + 0.12 * f) * (1 + 0.6 * fall) * self.rk
            tk = SPLASH_TAU * self.w * rho * smoothstep(tt / 0.15) * (1 - 0.3 * f)
            out.append((xy, z, r, tk, dyed(f, self.COL)))
            # the apex blossom: the crown opens 0.5 -> 2 widths over tau 0.8-1.6, ragged, thinning as it falls
            if tau > 0.7:
                c = smoothstep((tau - 0.8) / 0.8)
                R = Wd * (0.5 + 1.5 * c)
                xy = (self.xy + self.travel * self.lean * top + self._ring(self.CROWN, 8, R) * self.crown_k[:, None]
                      + wind * 0.25 * tt)
                zc = np.full(self.CROWN, top * (1 - 0.15 * c))
                tk = np.full(self.CROWN, SPLASH_TAU * 0.7 * rho * smoothstep((tau - 0.7) / 0.2))
                out.append((xy, zc, np.full(self.CROWN, Wd * (0.35 + 0.25 * c)), tk, dyed(1.0, self.CROWN)))
        # the base surge: a low ring rolling out to 2.5 widths by tau 2.5, gone by 4
        if 0.9 < tau < 4.0:
            u = (tau - 0.9) / 1.6
            R = Wd * (0.5 + 2.0 * min(u, 1.0))
            k = smoothstep((tau - 0.9) / 0.3) * (1 - smoothstep((tau - 2.5) / 1.5))
            xy = self.xy + self._ring(self.SURGE, 20, R)
            out.append((xy, np.full(self.SURGE, 3.0), np.full(self.SURGE, 0.45 * Wd), np.full(self.SURGE,
                        SPLASH_TAU * 0.5 * k), dyed(0.0, self.SURGE)))
        # the mist: what hangs after the collapse, drifting downwind, spreading and thinning
        if tau > 1.2:
            m = tt - 1.2 * self.t_a
            k = smoothstep(m / self.t_a)
            r = Wd * (0.9 + 0.35 * m) * np.ones(self.MIST)
            xy = (self.xy + self.travel * self.lean * self.H * 0.5 + self.mist_off * Wd * (1 + 0.2 * m)
                  + wind[None, :] * 0.8 * m)
            z = np.full(self.MIST, 6.0 + 0.25 * self.H * (1 - k * 0.6))
            tk = SPLASH_TAU * MIST_TAU * self.mist_w * k * math.exp(-m / MIST_S) * (Wd * 0.9 / r) ** 2
            out.append((xy, z, r, tk, dyed(0.6, self.MIST)))
        if not out:
            return None
        return tuple(np.concatenate([o[i] for o in out]) for i in range(5))


class Hit:
    """A shell hitting a ship: a flash, then a fire burning for a while with a smoke trail (brief: hits throw no
    water column). On the ship at `local` (ship metres), so it moves with her."""

    def __init__(self, ship, local, d, t0, rng):
        self.ship, self.local, self.d, self.t0 = ship, np.asarray(local, float), d, t0
        self.fire_s = rng.uniform(*HIT_FIRE_S) * (0.5 + 1.3 * d)
        self.ph = rng.uniform(0, 2 * math.pi, 3)

    def flash(self, t):
        """Display luminance (peak, before bloom), radius (m) and temperature (K) of the hit's flash and fire at t,
        or None."""
        tt = t - self.t0
        if tt < 0 or tt > self.fire_s:
            return None
        d = self.d
        burst = 9.0 * math.exp(-tt / 0.12)                  # the burst: a tenth of a second, very bright
        flick = 1 + 0.25 * math.sin(11 * tt + self.ph[0]) + 0.15 * math.sin(23 * tt + self.ph[1])
        fire = 1.4 * flick * min(1.0, tt / 0.3) * (1 - tt / self.fire_s) ** 0.7
        L = burst + fire
        r = (2.0 + 9.0 * d) * (1.0 if burst > fire else 0.5)
        T = 2600.0 if burst > fire else 1500.0 + 150 * flick
        return L, r, T

    def smoke_rate(self, t):
        """Smoke puffs a second (burst, then the fire's trail)."""
        tt = t - self.t0
        if tt < 0 or tt > self.fire_s:
            return 0.0
        return 30.0 * math.exp(-tt / 0.4) + 6.0 * (1 - tt / self.fire_s)
