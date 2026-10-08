"""Muzzle flash, propellant smoke and the shell's flight for vidgen, one shot at a time (numpy only).

A port of muzzle_flash_ref.py (research: muzzle_flash_research.md). The formulas are the reference's; what vidgen
adds or changes is marked DEPARTURE. Everything is analytic in the time since the shot, so nothing is simulated:
the scene keeps a list of shots and asks each for its emitters, smoke puff and shell position at the frame's time.

Units: metres, seconds, kg, K, cd/m^2. World axes are vidgen's (screen x right, y down), z up from the water.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

P0, C0, G = 101325.0, 343.0, 9.81
GAM = 1.4

# smoke the gas jet moves (muzzle_blast_waves.md 5.2, 5.3)
RING_P = 0.3              # share of shots that blow a smoke ring in light air
RING_SHARE = 0.25         # of the shot's smoke the ring carries
PUSH_EASE = 0.15          # s: a jet's shove on older smoke is eased in over this, not a one-frame jump

# propellant families (research 3.1; values are the reference's, [INFERRED] there)
PROPELLANTS = {
    "black_powder": dict(Q=2.8e6, e_ab=1.0e6, flash0=-0.6, T_sec=1700, solids=0.56, alpha=1.5, water=0.02,
                         tint=(0.90, 0.89, 0.86)),
    "single_base": dict(Q=3.8e6, e_ab=5.0e6, flash0=1.0, T_sec=1800, solids=0.002, alpha=3.0, water=0.28,
                        tint=(0.86, 0.80, 0.70)),
    "double_base": dict(Q=4.6e6, e_ab=3.6e6, flash0=1.6, T_sec=1900, solids=0.001, alpha=3.0, water=0.22,
                        tint=(0.86, 0.82, 0.74)),
    "diglycol": dict(Q=3.4e6, e_ab=4.4e6, flash0=0.0, T_sec=1700, solids=0.001, alpha=3.0, water=0.26,
                     tint=(0.86, 0.83, 0.77)),
    "triple_base": dict(Q=3.6e6, e_ab=3.4e6, flash0=-0.9, T_sec=1650, solids=0.004, alpha=3.0, water=0.30,
                        tint=(0.90, 0.89, 0.86)),
    "lova": dict(Q=4.0e6, e_ab=4.0e6, flash0=0.6, T_sec=1800, solids=0.0005, alpha=3.0, water=0.25,
                 tint=(0.90, 0.90, 0.88)),
}

# blackbody luminance (cd/m^2) and linear-sRGB chroma against temperature (research 2.6)
_BB_T = np.log([1000, 1200, 1400, 1600, 1800, 2000, 2200, 2500, 2800, 3000])
_BB_L = np.log10([2.73, 141, 2460, 2.15e4, 1.18e5, 4.67e5, 1.44e6, 5.65e6, 1.66e7, 3.03e7])
_RGB_T = [1000, 1200, 1400, 1600, 1800, 2000, 2200, 2500, 3000]
_RGB = np.array([(1, .029, 0), (1, .073, 0), (1, .121, 0), (1, .17, 0), (1, .219, 0), (1, .266, .008),
                 (1, .313, .028), (1, .38, .068), (1, .484, .155)])
NA_D = np.array([1.0, 0.62, 0.18])     # sodium-line chroma mixed into the secondary flash (research 2.6, 8.2)
LUM = np.array([0.2126, 0.7152, 0.0722])


def bb_luminance(T):
    lnT = math.log(T)
    return float(10 ** np.interp(lnT, _BB_T, _BB_L, left=_BB_L[0] - 40 * (_BB_T[0] - lnT), right=_BB_L[-1]))


def bb_rgb(T):
    return np.array([np.interp(T, _RGB_T, _RGB[:, i]) for i in range(3)])


def bb_luminance_v(T):
    """bb_luminance over an array (the same table, log-log interpolated)."""
    lnT = np.log(np.maximum(T, 1.0))
    lo = _BB_L[0] - 40 * (_BB_T[0] - lnT)
    return np.power(10.0, np.where(lnT < _BB_T[0], lo, np.interp(lnT, _BB_T, _BB_L))).astype(np.float32)


def flash_rgb_v(T, na=0.55):
    """Linear-sRGB chroma of flash gas at temperature T (array), normalised to unit luminance: the blackbody's,
    with the sodium line mixed in by na where the gas is hot enough to excite it (research 2.6). DEPARTURE: the
    reference mixes a fixed 55 %; here the share fades out over 1650-1250 K, so a fireball's cooler edges and
    dying pockets go redder."""
    share = na * np.clip((T - 1250.0) / 400.0, 0, 1)
    rgb = np.stack([np.interp(T, _RGB_T, _RGB[:, i]) for i in range(3)], -1)
    rgb = rgb * (1 - share)[..., None] + NA_D * share[..., None]
    return (rgb / np.maximum(rgb @ LUM, 1e-4)[..., None]).astype(np.float32)


@dataclass
class Gun:
    d: float                      # bore, m
    L_cal: float = 50.0           # barrel length, calibres
    prop: str = "single_base"
    salt: float = 0.0             # K-salt flash reducer, mass fraction
    igniter: float | None = None  # black-powder igniter fraction (None: from the bore, see derive)
    liner: float = 0.0

    @property
    def charge(self):
        return 4000.0 * self.d ** 3 * (self.L_cal / 50.0)       # research 2.1 fit, kg


def derive(g: Gun, RH=0.7, T_amb_C=15.0):
    """Per-gun constants (research 2.2-2.5, 5.2), plus the shell's mass and muzzle velocity."""
    p = PROPELLANTS[g.prop]
    m = g.charge
    E_blast = 0.45 * m * p["Q"]
    V_bore = math.pi * g.d ** 2 / 4 * g.L_cal * g.d * 1.15
    p_stag = 1.8 * 0.25 * 0.6 * E_blast / V_bore
    x_M = g.d * math.sqrt(p_stag / P0)
    M = p["flash0"] + 0.6 * math.log10(g.d / 0.02) - math.log10(g.L_cal / 50.0) - g.salt / 0.006
    P_sec = 1.0 / (1.0 + math.exp(-2.0 * M))
    # DEPARTURE: the reference's ladder gives cased guns (5" and under) 0.3 % igniter and bag guns 1 %. vidgen
    # doesn't know which a mount is, so the igniter share rises smoothly with the bore over 100-200 mm instead of
    # stepping at a calibre. Bag vs cased should become a battery input when shipgen exports ammunition.
    ig = g.igniter if g.igniter is not None else 0.003 + 0.007 * _smooth((g.d - 0.1) / 0.1)
    hyg = 1.0 + 2.0 * RH ** 4
    y_sol = p["solids"] + g.salt + 0.56 * ig + 0.8 * g.liner
    A_p = m * 1000.0 * y_sol * p["alpha"] * hyg
    chi = 0.15 * min(max((RH - 0.5) / 0.5, 0.0), 1.0) ** 2 * (1 + max(0.0, (10 - T_amb_C) / 20))
    A_w = m * 1000.0 * p["water"] * min(chi, 0.4) * 0.5
    # DEPARTURE (not in the research): shell mass ~ 14000 d^3 kg (380 mm 770 kg, 127 mm 29 kg, 406 mm 940 kg) and
    # 30 % of the charge's energy as the shell's kinetic energy; a longer barrel burns more charge, so it's faster
    # (380/52: 780 m/s, 150/55: 830 m/s, 105/65: 900 m/s)
    shell_kg = 14000.0 * g.d ** 3
    v0 = math.sqrt(2 * 0.3 * m * p["Q"] / shell_kg)
    return dict(m=m, E_blast=E_blast, lam_b=(E_blast / P0) ** (1 / 3), x_M=x_M, P_sec=P_sec, E_ab=m * p["e_ab"],
                t_e=g.L_cal * g.d / 300.0 + 2e-4, A_p=A_p, A_w=A_w, tau_w=2.0 / max(1.0 - RH, 0.03),
                T_sec=p["T_sec"], tint=np.array(p["tint"]), shell_kg=shell_kg, v0=v0)


def _smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def ring_chance(wind):
    """Share of shots that blow a smoke ring (muzzle_blast_waves.md 5.3, [INFERRED]): 0.3 in light air, falling
    linearly to none at 10 m/s of wind. Naval guns have no muzzle brake."""
    return RING_P * min(1.0, max(0.0, (10.0 - wind) / 5.0))


def elevation(v0, range_m):
    """Vacuum elevation for range_m, clamped to 45 degrees when the gun can't reach. Drag is ignored: a visual
    stand-in, a few degrees flat for big guns at long range."""
    return 0.5 * math.asin(min(1.0, G * range_m / (v0 * v0)))


class Shot:
    """One gun firing: muzzle at pos (world xy) and height h, bore along azimuth az (radians, screen axes) at
    elevation el. carry is the ship's velocity, which the shell and (DEPARTURE) the young smoke keep."""

    def __init__(self, gun: Gun, D, pos, h, az, el, t0, carry, wind, rng):
        self.gun, self.D = gun, D
        self.pos, self.h, self.az, self.el, self.t0 = np.asarray(pos, float), h, az, el, t0
        self.carry, self.wind = np.asarray(carry, float), np.asarray(wind, float)
        self.shell_carry = self.carry   # what the shell keeps of the ship's way (a caller drawing it on a slowed
                                        # clock may raise it so the shell still lands where the ships will be)
        self.sec_on = rng.random() < D["P_sec"]
        self.jit = float(np.exp(0.25 * rng.standard_normal()))
        self.lobes = rng.random(2) * 2 * math.pi
        self.noise_off = rng.random(2)
        E = D["E_blast"] + (D["E_ab"] * self.jit if self.sec_on else 0.0)
        self.lam_f = (E / P0) ** (1 / 3)
        self.t_s = 5.0 * self.lam_f / C0
        self.hdir = np.array([math.cos(az), math.sin(az)])
        self.ax = np.array([math.cos(el) * self.hdir[0], math.cos(el) * self.hdir[1], math.sin(el)])
        self.pushes = []
        self.has_ring = rng.random() < ring_chance(float(np.hypot(*self.wind)))

    @property
    def flash_end(self):
        return self.t0 + max(self.t_s if self.sec_on else 0.0, self.D["t_e"])

    # ---- flash (research 2.3, 2.5, 2.6): three emitters, each an ellipse along the bore
    def emitters(self, t):
        D, out = self.D, []
        tt = t - self.t0
        if tt < 0:
            return out
        base = np.array([self.pos[0], self.pos[1], self.h])
        xM = D["x_M"]
        if tt < D["t_e"]:
            f = tt / D["t_e"]
            r = 1.5 * self.gun.d + 0.12 * xM * min(1, 4 * f)
            out.append(self._em("primary", base + self.ax * 0.35 * xM, 0.35 * xM + r, r, 2000 - 800 * f,
                                1 - math.exp(-r / 2.0)))
            ri = 0.22 * xM
            out.append(self._em("intermediate", base + self.ax * xM, 0.10 * xM, ri, 1900 - 500 * f,
                                1 - math.exp(-ri / 3.0)))
        if self.sec_on and tt < self.t_s:
            ts = self.t_s
            rise = 0.12 * ts
            env = tt / rise if tt < rise else 1 - ((tt - rise) / (ts - rise)) ** 2
            T = D["T_sec"] * (0.75 + 0.25 * env) * self.jit ** 0.05
            grow = min(1.0, 0.35 + 0.65 * tt / (0.5 * ts))
            a, b = 0.8 * self.lam_f * grow, 0.5 * self.lam_f * grow
            c = base + self.ax * (xM + 0.7 * self.lam_f * grow) + np.array([0, 0, 0.3 * G * tt * tt])
            out.append(self._em("secondary", c, a, b, T, 1 - math.exp(-b / 6.0), env))
        return out

    def _em(self, kind, c, a, b, T, eps, env=1.0):
        L = eps * bb_luminance(T) * env
        rgb = bb_rgb(T)
        if kind == "secondary":
            rgb = 0.45 * rgb + 0.55 * NA_D
        return dict(kind=kind, c=c, a=a, b=b, L=L, I=L * math.pi * a * b, rgb=rgb, T=T, eps=eps, env=env)

    # ---- smoke (research 5.2, 5.3): one gaussian puff with extinction area A
    def puff(self, t):
        tt = t - self.t0
        if tt <= 0:
            return None
        D, lf = self.D, self.lam_f
        tau_m = 0.04 * lf + 0.05
        k = 1 - math.exp(-tt / tau_m)
        s = 2.5 * lf * k
        # DEPARTURE: the reference's gun stands on the ground; here the gas leaves at the ship's speed and loses
        # it to the air on the same time constant as its own forward carry
        xy = self.pos + self.hdir * (D["x_M"] + s) * math.cos(self.el) + self.wind * tt + self.carry * tau_m * k
        z = self.h + (D["x_M"] + s) * math.sin(self.el) + 0.6 * lf * (1 - math.exp(-tt / (3 + 0.05 * lf)))
        U = float(np.hypot(*self.wind))
        sh = math.sqrt((0.35 * lf) ** 2 + ((0.07 * U + 0.2) * tt) ** 2 + 0.5 * tt)
        ramp = 1 - math.exp(-tt / (0.5 * max(self.t_s, D["t_e"]) + 0.004))
        # the ring, when one forms, carries off RING_SHARE of the smoke (research 5.3: line of sight stays honest)
        ramp *= 1 - RING_SHARE if self.has_ring else 1.0
        A_p, A_w = ramp * D["A_p"], ramp * D["A_w"] * math.exp(-tt / D["tau_w"])
        if self.pushes:
            xy = xy + self._pushed(t)
            sh *= self._grown(t)
        return dict(xy=xy, z=z, sh=sh, A=A_p + A_w, A_p=A_p, A_w=A_w, age=tt)

    # ---- vortex ring (muzzle_blast_waves.md 5.3): the gas slug rolls up into a ring that carries smoke away
    def ring(self, t):
        """The smoke ring's centre (xy, z), radius R and extinction area A at t, or None (no ring, or broken up).
        It forms on a share of shots (RING_P, decided at the shot), takes RING_SHARE of the puff's A, slows as
        t^(1/4) and breaks up after ~8 lam of travel, fading over the last 30 %."""
        if not self.has_ring:
            return None
        tt = t - self.t0
        if tt <= 0:
            return None
        lam = self.D["lam_b"]
        U0 = 25.0 * math.sqrt(lam / 5.0)
        tau = 2.0 * lam / U0
        x = 4 * U0 * tau * ((1 + tt / tau) ** 0.25 - 1)
        if x >= 8 * lam:
            return None
        R = 0.25 * lam * (1 + 0.08 * x / lam)
        p = self.puff(t)
        fade = min(1.0, (8 * lam - x) / (2.4 * lam))
        xy = self.pos + self.hdir * (self.D["x_M"] + x) * math.cos(self.el) + self.wind * tt + self._pushed(t)
        z = self.h + (self.D["x_M"] + x) * math.sin(self.el)
        return dict(xy=xy, z=z, R=R, A=RING_SHARE * p["A"] * fade / (1 - RING_SHARE), x=x)

    # ---- the jet punch (muzzle_blast_waves.md 5.2): a later shot's gas jet shoves this puff along its bore
    def push(self, t, d, grow=1.2):
        self.pushes.append((t, np.asarray(d, float), grow))

    def _pushed(self, t, ease=PUSH_EASE):
        out = np.zeros(2)
        for tp, d, _ in self.pushes:
            if t > tp:
                out += d * (1 - math.exp(-(t - tp) / ease))
        return out

    def _grown(self, t, ease=PUSH_EASE):
        k = 1.0
        for tp, _, g in self.pushes:
            if t > tp:
                k *= 1 + (g - 1) * (1 - math.exp(-(t - tp) / ease))
        return k

    # ---- the shell (vidgen's own): vacuum ballistics from the muzzle, keeping the ship's velocity
    def shell(self, t):
        tt = t - self.t0
        v = self.D["v0"]
        vh = v * math.cos(self.el)
        xy = self.pos + (self.hdir * vh + self.shell_carry) * tt
        z = self.h + v * math.sin(self.el) * tt - 0.5 * G * tt * tt
        vel = self.hdir * vh + self.shell_carry
        return xy, z, vel


# ---------------------------------------------------------------- the blast on the water
# A port of muzzle_blast_ref.py (research: muzzle_blast_water-vfx.md, extended by muzzle_blast_waves.md). The blast
# front itself is transparent; what shows top-down is the sea's roughness: a dark leading edge where the gust lays
# the ripples down, a frosted (rougher, silvery) disc behind it, and scour foam in the near field.
P_VIS = 2000.0            # Pa: the visible edge (research 2.2: 2-2.5 kPa matches the Iowa photo; 1 kPa is too big)
P_SAT = 5000.0            # Pa: full frost
TAU_FROST = 2.0           # s: ripples regrow
TAU_FOAM = 7.0            # s: scour foam decays like breaking-crest foam
K_FOAM = 1.0              # foam reaches 1.3 K_FOAM lam' (scaled distance, research 3.3)
MACH_STEM = 2 ** (1 / 3)  # research (waves) 0.7: over water a low-elevation blast acts as a doubled charge


def beta(cos_th, mu=0.78):
    """Fansler's directivity: lam' = lam beta, about 8x stronger straight ahead than straight behind."""
    return mu * cos_th + np.sqrt(1 - mu * mu * (1 - cos_th * cos_th))


def overpressure(r, lam_eff):
    x = lam_eff / np.maximum(r, 1e-3)
    return P0 * (0.11 * x + 0.0061 * x * x)


def _arrival_lut(z_max=40.0, n=512):
    """Arrival time of the front against scaled distance z = r/lam', in units of lam'/c0: one LUT for every gun."""
    z = np.linspace(0.05, z_max, n)
    us = np.sqrt(1 + (GAM + 1) / (2 * GAM) * overpressure(z, 1.0) / P0)
    t = np.concatenate([[0], np.cumsum(0.5 * (1 / us[1:] + 1 / us[:-1]) * np.diff(z))])
    return z, t


Z_LUT, T_LUT = _arrival_lut()
# the visible edge in scaled distance: 0.11 x + 0.0061 x^2 = P_VIS / P0
_XV = (-0.11 + math.sqrt(0.11 ** 2 + 4 * 0.0061 * P_VIS / P0)) / (2 * 0.0061)


class Blast:
    """One mount's salvo as one blast event (research 3.1): the guns that fire together sum their energy, so
    lam grows as N^(1/3). pos is the muzzles' mean (world xy), h their height above the water."""

    def __init__(self, mount, pos, h, az, el, t0):
        self.mount, self.pos, self.h, self.az, self.el, self.t0 = mount, np.asarray(pos, float), h, az, el, t0
        self.E, self.n = 0.0, 0
        self.bore = np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])

    def add(self, E, pos):
        self.pos = (self.pos * self.n + np.asarray(pos, float)) / (self.n + 1)
        self.n += 1
        self.E += E
        # DEPARTURE (smooth in place of "low-elevation fire"): the Mach-stem doubling fades out by ~30 degrees
        stem = 1 + (MACH_STEM - 1) * math.exp(-(self.el / math.radians(20)) ** 2)
        self.lam = (self.E / P0) ** (1 / 3) * stem

    @property
    def r_vis(self):
        """Furthest reach of the visible edge (straight ahead), m."""
        return beta(1.0) * self.lam / _XV

    @property
    def life(self):
        return max(4 * TAU_FROST, 3 * TAU_FOAM)

    def radius(self, t):
        """The front's furthest reach at t (straight ahead, where it's fastest), capped at the visible edge."""
        tt = t - self.t0
        if tt <= 0:
            return 0.0
        lf = beta(1.0) * self.lam
        return min(self.r_vis, lf * float(np.interp(tt * C0 / lf, T_LUT, Z_LUT, right=Z_LUT[-1])))

    def fields(self, X, Y, t, band_min=0.0):
        """(rough, lead, foam) in 0..1 at world offsets X, Y (m, from self.pos; broadcastable) at time t.
        rough: the frost behind the front; lead: the dark leading edge; foam: near-field scour plus, at low
        elevation, the jet's lobe along the bore's ground track. band_min: the leading edge's least width (m),
        so it's never thinner than about a pixel."""
        tt = t - self.t0
        dz = -self.h
        r = np.sqrt(X * X + Y * Y + dz * dz)
        b = self.bore
        cos_th = (X * b[0] + Y * b[1] + dz * b[2]) / r
        lam_e = self.lam * beta(cos_th)
        z = r / lam_e
        age = tt - np.interp(z, Z_LUT, T_LUT) * lam_e / C0
        arrived = age >= 0
        agep = np.maximum(age, 0)
        dp = overpressure(r, lam_e)
        s = np.clip(np.log(np.maximum(dp, 1e-3) / P_VIS) / math.log(P_SAT / P_VIS), 0, 1) * arrived
        band = max(C0 * 0.0009 * self.lam, band_min)       # positive-phase length, c0 T+
        q = agep * C0 / band
        lead = s * np.exp(-q * q)
        rough = s * np.exp(-agep / TAU_FROST) * (1 - np.exp(-0.25 * q * q))   # frost builds just behind the front
        foam = np.clip(1.3 - z / K_FOAM, 0, 1) ** 1.5
        # the jet lobe (research 3.3, [INFERRED] shape): an ellipse along the bore's ground track, ~4 lam cos(el)
        # long, for low fire from a muzzle not far above the water (smooth weights, no elevation cutoff)
        wj = math.exp(-(self.el / math.radians(10)) ** 2) * math.exp(-(self.h / (1.5 * self.lam)) ** 2)
        if wj > 0.02:
            ce = math.cos(self.el)
            hx, hy = math.cos(self.az), math.sin(self.az)
            u = X * hx + Y * hy - 2.0 * self.lam * ce
            v = -X * hy + Y * hx
            q2 = (u / (2.0 * self.lam * ce)) ** 2 + (v / (0.45 * self.lam)) ** 2
            foam = np.maximum(foam, wj * np.clip(1 - q2, 0, 1) ** 1.5)
        foam = foam * arrived * np.exp(-agep / TAU_FOAM)
        return rough, lead, foam
