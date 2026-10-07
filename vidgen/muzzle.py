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
        self.sec_on = rng.random() < D["P_sec"]
        self.jit = float(np.exp(0.25 * rng.standard_normal()))
        self.lobes = rng.random(2) * 2 * math.pi
        self.noise_off = rng.random(2)
        E = D["E_blast"] + (D["E_ab"] * self.jit if self.sec_on else 0.0)
        self.lam_f = (E / P0) ** (1 / 3)
        self.t_s = 5.0 * self.lam_f / C0
        self.hdir = np.array([math.cos(az), math.sin(az)])
        self.ax = np.array([math.cos(el) * self.hdir[0], math.cos(el) * self.hdir[1], math.sin(el)])

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
        return dict(kind=kind, c=c, a=a, b=b, L=L, I=L * math.pi * a * b, rgb=rgb)

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
        A_p, A_w = ramp * D["A_p"], ramp * D["A_w"] * math.exp(-tt / D["tau_w"])
        return dict(xy=xy, z=z, sh=sh, A=A_p + A_w, A_p=A_p, A_w=A_w, age=tt)

    # ---- the shell (vidgen's own): vacuum ballistics from the muzzle, keeping the ship's velocity
    def shell(self, t):
        tt = t - self.t0
        v = self.D["v0"]
        vh = v * math.cos(self.el)
        xy = self.pos + (self.hdir * vh + self.carry) * tt
        z = self.h + v * math.sin(self.el) * tt - 0.5 * G * tt * tt
        vel = self.hdir * vh + self.carry
        return xy, z, vel
