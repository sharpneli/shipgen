"""Reference: what the muzzle PRESSURE WAVE itself makes visible (beyond the water roughness of
claude/muzzle-blast-water-vfx.md).  Companion to claude/blast-wave-visibles-research.md.

Phenomena (each returns size / time / strength so the renderer can decide):
  1. Wilson (condensation) cloud in the negative phase: rarefaction cools humid air below the dew point.
     Needs droplets to GROW within the negative phase -> strongly calibre- and humidity-dependent.
  2. Sun shadowgraph line: the density jump refracts sunlight -> a moving bright/dark line on surfaces.
  3. Refraction "lens" distortion of what is seen through the shock shell (screen-space ripple).
  4. Spray / spindrift ripped off wave crests where the post-shock gust exceeds ~12 m/s.
  5. Vortex ring ("smoke ring") formed by the gas puff, made visible by its smoke / water fog.
  6. Existing smoke jolted (cm..dm) by the shock; punched (m) by the gas jet.

Blast field: Fansler fit, same as the water doc:  dp/p0 = 0.11 x + 0.0061 x^2,  x = lam'/r,
lam' = lam*beta(theta).  Near field (r < ~3 lam) is UNDER-predicted (16" data: ~14 kPa at ~48 m, §2 of the .md).
Units SI.
"""
import math
import numpy as np

P0, C0, RHO, GAM = 101325.0, 343.0, 1.2, 1.4


def lam_blast(m_prop, n=1, Q=3.8e6):
    return (0.45 * m_prop * n * Q / P0) ** (1 / 3)


def beta(cos_th, mu=0.78):
    return mu * cos_th + math.sqrt(1 - mu * mu * (1 - cos_th * cos_th))


def dp_pos(r, lam_e):
    x = lam_e / r
    return P0 * (0.11 * x + 0.0061 * x * x)


def t_pos(lam):
    return 0.9e-3 * lam            # positive-phase duration, s (blast/audio docs: 0.9 ms per m of lam)


# ---------------------------------------------------------------- 1. Wilson cloud
def sat_vapour_density(T):
    """kg/m^3 (Magnus over water)."""
    Tc = T - 273.15
    e = 610.94 * math.exp(17.625 * Tc / (Tc + 243.04))
    return e / (461.5 * T)


def wilson(r, lam_e, lam, RH=0.9, T=293.0, k_neg=0.25, N_ccn=150e6, G=1.0e-10):
    """Condensation in the negative phase at distance r.
    k_neg: peak underpressure / peak overpressure for these weak blasts [INFERRED 0.13-0.4], capped at 10 kPa
           (Granstrom's near-field plateau)  [UNCERTAIN]
    N_ccn: marine cloud-condensation nuclei, m^-3 (100-300 /cm^3)  [INFERRED typical]
    G:     droplet growth constant, m^2/s (r dr/dt = G (S-1)) ~1e-10 near 20 C
    Returns dict(S, r_drop, beta_ext, life) — extinction coefficient (1/m) at the end of growth."""
    dpn = min(k_neg * dp_pos(r, lam_e), 10e3)
    d = dpn / P0
    dT = T * (1 - (1 - d) ** ((GAM - 1) / GAM))                     # adiabatic cooling
    S = RH * (1 - d) * sat_vapour_density(T) / sat_vapour_density(T - dT) * (T - dT) / T * (T / (T - dT))
    # ^ vapour density scales with (1-d)^(1/gam); keep it simple: partial pressure ~ (1-d), e_s(T-dT)
    S = RH * (1 - d) * (math.exp(17.625 * (T - 273.15) / (T - 29.11)) / math.exp(17.625 * (T - dT - 273.15) / (T - dT - 29.11)))
    t_neg = 3.0 * t_pos(lam)                                        # negative phase ~2-3x positive  [INFERRED]
    t_grow = 0.6 * t_neg                                            # time spent supersaturated
    if S <= 1.0:
        return dict(S=S, r_drop=0.0, beta=0.0, life=0.0, dpn=dpn)
    r_d = math.sqrt(2 * G * (S - 1) * t_grow + (0.05e-6) ** 2)
    # cap by available excess vapour
    lwc_max = sat_vapour_density(T - dT) * (S - 1) / S
    lwc = min(N_ccn * 4 / 3 * math.pi * r_d ** 3 * 1000.0, lwc_max)
    r_eff = (lwc / (N_ccn * 4 / 3 * math.pi * 1000.0)) ** (1 / 3)
    Q = 2.0 if r_eff > 0.5e-6 else 2.0 * (r_eff / 0.5e-6) ** 4 * 4  # crude Mie: small droplets scatter weakly
    Q = min(Q, 2.0)
    beta_ext = N_ccn * math.pi * r_eff ** 2 * Q
    life = t_neg + (r_eff ** 2) / (2 * G * max(1 - RH, 0.01))      # + re-evaporation time in the recovered air
    return dict(S=S, r_drop=r_eff, beta=beta_ext, life=life, dpn=dpn)


def wilson_extent(lam, RH, T=293.0, theta_deg=0.0, tau_min=0.05):
    """Largest r (along angle theta from the bore) where a path ~ the local shell width gives tau >= tau_min."""
    lam_e = lam * beta(math.cos(math.radians(theta_deg)))
    best = None
    for r in np.geomspace(0.3 * lam_e, 40 * lam_e, 300):
        w = wilson(r, lam_e, lam, RH, T)
        width = 0.5 * r                                             # shell region thickness seen from above [INFERRED]
        if w["beta"] * width >= tau_min:
            best = (r, w)
    return best


# ---------------------------------------------------------------- 2/3. refraction
def shadow_contrast(dp, r, sun_mrad=9.3, L=12.0):
    """Approximate contrast of the sun-shadowgraph line cast by a spherical shock of radius r onto a surface
    L metres beyond the grazing point.  Deflection near grazing ~ (n-1) (drho/rho) sqrt(2 r / w), smeared by the
    sun's 0.53 deg disc.  [INFERRED order-of-magnitude]"""
    drho = dp / (GAM * P0)
    w = max(L * sun_mrad * 1e-3, 0.01)                              # blur width set by the sun disc
    eps = 2.9e-4 * drho * math.sqrt(2 * r / w)
    return min(eps * L / w, 1.0)


def lens_shift(dp, r, h):
    """Apparent shift (m) of a surface h metres behind the shock shell as seen through it (top-down)."""
    drho = dp / (GAM * P0)
    return 2.9e-4 * drho * math.sqrt(2 * r / 0.05) * h


# ---------------------------------------------------------------- 4. spray / spindrift
def gust(dp):
    return dp / (RHO * C0)                                          # post-shock particle velocity, weak-shock limit


# ---------------------------------------------------------------- 5. vortex ring
def vortex_ring(lam, t):
    """Turbulent ring from the muzzle gas puff: x ~ t^(1/4) self-similar (impulse-conserving turbulent ring),
    radius grows slowly with x.  Constants fitted to tank-gun / howitzer smoke-ring footage scale [INFERRED]:
    formation radius ~0.25 lam, initial speed ~ 25 m/s * (lam/5 m)^0.5, carries ~8 lam before it breaks up."""
    R0 = 0.25 * lam
    U0 = 25.0 * math.sqrt(lam / 5.0)
    tau = 2.0 * (lam / U0)                                          # so that x(t) = 4 U0 tau ((1+t/tau)^(1/4) - 1)
    x = 4 * U0 * tau * ((1 + t / tau) ** 0.25 - 1)
    R = R0 * (1 + 0.08 * x / lam)
    alive = x < 8 * lam
    return x, R, alive


# ---------------------------------------------------------------- 6. smoke jolt
def smoke_jolt(dp, lam):
    """Peak displacement of existing smoke by the shock alone: ~ positive impulse / (rho c)."""
    return 0.5 * dp * t_pos(lam) / (RHO * C0)


if __name__ == "__main__":
    guns = [("20 mm", 0.028, 1), ("40 mm quad", 0.31, 4), ("5\"/38 twin", 7.0, 2), ("8\"/55 triple", 41, 3),
            ("16\"/50 single", 297, 1), ("16\"/50 triple", 297, 3), ("2000 mm turbo", 32000, 1)]
    print("1) Wilson cloud: forward extent where tau>=0.05 (r, peak underpressure, droplet radius, lifetime)")
    print(f"{'gun':16s} {'lam':>6s} | " + " | ".join(f"RH {int(rh*100)}%".center(30) for rh in (0.75, 0.9, 0.97)))
    for name, m, n in guns:
        lam = lam_blast(m, n)
        cells = []
        for rh in (0.75, 0.9, 0.97):
            e = wilson_extent(lam, rh)
            if e is None:
                cells.append("none".center(30))
            else:
                r, w = e
                cells.append(f"r {r:6.1f} m dp- {w['dpn']/1e3:4.1f}k {w['r_drop']*1e6:4.2f}um {w['life']*1e3:4.0f}ms".center(30))
        print(f"{name:16s} {lam:6.1f} | " + " | ".join(cells))

    print("\n2-6) per gun, forward direction")
    print(f"{'gun':16s} {'t+ ms':>6s} {'r(5kPa) spray':>14s} {'gust@r':>7s} {'shadow C @lam':>14s} {'lens shift@lam,h=10':>20s} "
          f"{'ring R0':>8s} {'ring travel':>11s} {'ring life':>9s} {'smoke jolt@2kPa':>15s}")
    for name, m, n in guns:
        lam = lam_blast(m, n)
        lam_f = lam * beta(1.0)
        # radius where dp = 5 kPa (spindrift / spray lift threshold)
        rr = np.geomspace(0.1 * lam_f, 50 * lam_f, 2000)
        dps = np.array([dp_pos(r, lam_f) for r in rr])
        r5 = rr[dps >= 5e3].max() if (dps >= 5e3).any() else 0
        dp_l = dp_pos(lam_f, lam_f)
        ts = np.linspace(0, 30, 3000)
        xs = [vortex_ring(lam, t) for t in ts]
        life = ts[max(i for i, v in enumerate(xs) if v[2])]
        print(f"{name:16s} {t_pos(lam)*1e3:6.1f} {r5:12.1f} m {gust(5e3):6.1f} {shadow_contrast(dp_l, lam_f):14.3f} "
              f"{lens_shift(dp_l, lam_f, 10.0)*100:17.2f} cm {0.25*lam:7.1f}m {8*lam:9.0f} m {life:8.1f}s "
              f"{smoke_jolt(2e3, lam)*100:12.1f} cm")
    # 16" sanity check against the measured 2 psi contour at ~159 ft (48 m)
    lam1 = lam_blast(297)
    print("\n16\" single check: fit at 48 m:", {th: round(dp_pos(48, lam1 * beta(math.cos(math.radians(th)))) / 1e3, 1)
                                          for th in (0, 45, 90, 135)}, "kPa  vs measured ~13.8 kPa (2 psi)")