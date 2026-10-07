"""Reference model: gun muzzle flash + propellant smoke, top-down, any calibre (20 mm .. 2000 mm).

Companion to claude/muzzle-flash-smoke-research.md.  Shares the blast length with
claude/muzzle-blast-water-vfx.md:   E = 0.45 * m_prop * Q,  lam = (E/p0)^(1/3).

Everything is analytic per shot, so the same numbers can drive
  * the renderer (HDR emitters + smoke puffs, energy-conserving at every zoom), and
  * gameplay (luminous intensity for detection, smoke optical depth for line of sight).

Units: metres, seconds, kg, K, candela (cd), cd/m^2 (nit).  Bore points +x unless rotated.
Tags in comments: [INFERRED] = fit / my reasoning, [SRC] = from a cited source (see the .md).
"""
from dataclasses import dataclass, field
import math
import numpy as np

P0, C0, G = 101325.0, 343.0, 9.81

# ---------------------------------------------------------------- propellant families
# Q        heat of explosion, J/kg (used only for blast energy, like the blast doc's 3.8 MJ/kg)
# e_ab     afterburn energy available when CO/H2 burn in air, J/kg of propellant  [INFERRED from
#          typical product mixes: single-base ~35 % CO + ~1.2 % H2 by mass -> ~5 MJ/kg]
# flash0   flash propensity offset (logit units) [INFERRED, calibrated to the cases in the .md §3.3]
# T_sec    peak secondary-flash temperature, K  (Steward 2012: 1200-1600 K band-averaged, 152 mm) [SRC+INFERRED]
# solids   primary-smoke solids from the propellant itself, kg/kg (black powder 0.56 [SRC])
# alpha    mass extinction of those solids, m^2/g (natural log, ~550 nm) [INFERRED, obscurant range 2-5 m^2/g]
# water    H2O in muzzle gas incl. afterburn, kg/kg [INFERRED]
# tint     near-muzzle smoke tint (linear RGB albedo)
PROPELLANTS = {
    "black_powder": dict(Q=2.8e6, e_ab=1.0e6, flash0=-0.6, T_sec=1700, solids=0.56, alpha=1.5, water=0.02,
                         tint=(0.90, 0.89, 0.86), label="black powder (pre-1890)"),
    "single_base": dict(Q=3.8e6, e_ab=5.0e6, flash0=1.0, T_sec=1800, solids=0.002, alpha=3.0, water=0.28,
                        tint=(0.86, 0.80, 0.70), label="single-base NC (USN SPD, IMR, M1/M6)"),
    "double_base": dict(Q=4.6e6, e_ab=3.6e6, flash0=1.6, T_sec=1900, solids=0.001, alpha=3.0, water=0.22,
                        tint=(0.86, 0.82, 0.74), label="double-base (cordite MD/SC, RPC/12, M2)"),
    "diglycol": dict(Q=3.4e6, e_ab=4.4e6, flash0=0.0, T_sec=1700, solids=0.001, alpha=3.0, water=0.26,
                     tint=(0.86, 0.83, 0.77), label="cool double-base (diglycol RPC/38, Gudol)"),
    "triple_base": dict(Q=3.6e6, e_ab=3.4e6, flash0=-0.9, T_sec=1650, solids=0.004, alpha=3.0, water=0.30,
                        tint=(0.90, 0.89, 0.86), label="triple-base / picrite (Cordite N, SPCG, M30/M31)"),
    "lova": dict(Q=4.0e6, e_ab=4.0e6, flash0=0.6, T_sec=1800, solids=0.0005, alpha=3.0, water=0.25,
                 tint=(0.90, 0.90, 0.88), label="modern nitramine / LOVA"),
}


@dataclass
class Gun:
    name: str
    d: float                      # bore, m
    L_cal: float = 50.0           # barrel length in calibres
    m_prop: float | None = None   # charge, kg (None -> 4000 d^3 (L/50))
    prop: str = "single_base"
    salt: float = 0.0             # K-salt flash reducer, mass fraction (0.01 = 1 %)
    igniter: float = 0.005        # black-powder igniter fraction (bag guns ~1 %, cased ~0.3 %) [INFERRED]
    liner: float = 0.0            # TiO2/wax/talc wear-reducer fraction (modern 0.5-1 %)
    device: str = "none"          # none | hider | brake
    n: int = 1                    # guns firing together from one mount (summed energy)

    @property
    def charge(self):
        return self.m_prop if self.m_prop is not None else 4000.0 * self.d ** 3 * (self.L_cal / 50.0)


def bb_luminance(T):
    """Blackbody luminance, cd/m^2 (fit to Planck x CIE y, 800-3200 K, <5 %)."""
    lnT = math.log(T)
    # log10 L as a cubic in ln T fitted to the photometric integral (see .md §4.1 table)
    pts = [(1000, 2.73), (1200, 141), (1400, 2460), (1600, 2.15e4), (1800, 1.18e5),
           (2000, 4.67e5), (2200, 1.44e6), (2500, 5.65e6), (2800, 1.66e7), (3000, 3.03e7)]
    xs = np.log([p[0] for p in pts]); ys = np.log10([p[1] for p in pts])
    return float(10 ** np.interp(lnT, xs, ys, left=ys[0] - 40 * (xs[0] - lnT), right=ys[-1]))


def bb_rgb(T):
    """Linear sRGB chroma of a blackbody, max channel = 1 (from the same table)."""
    tab = [(1000, (1, .029, 0)), (1200, (1, .073, 0)), (1400, (1, .121, 0)), (1600, (1, .17, 0)),
           (1800, (1, .219, 0)), (2000, (1, .266, .008)), (2200, (1, .313, .028)), (2500, (1, .38, .068)),
           (3000, (1, .484, .155))]
    Ts = [a for a, _ in tab]
    return np.array([np.interp(T, Ts, [c[i] for _, c in tab]) for i in range(3)])


def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


# ---------------------------------------------------------------- per-weapon derived constants
def derive(g: Gun, RH=0.7, T_amb_C=15.0):
    p = PROPELLANTS[g.prop]
    m = g.charge * g.n
    E_blast = 0.45 * m * p["Q"]                             # blast doc convention
    lam_b = (E_blast / P0) ** (1 / 3)
    # muzzle pressure from the gas energy left in the bore [INFERRED]
    V_bore = math.pi * g.d ** 2 / 4 * g.L_cal * g.d * 1.15
    p_m = 0.25 * 0.6 * (0.45 * g.charge * p["Q"]) / V_bore
    p_stag = 1.8 * p_m                                       # sonic exit -> stagnation
    x_M = 1.0 * g.d * math.sqrt(p_stag / P0)                 # Mach-disk distance, k=1 matches 20-25 cal [SRC navweaps]
    # secondary-flash propensity (logit) [INFERRED]
    M = (p["flash0"] + 0.6 * math.log10(g.d / 0.02) - math.log10(g.L_cal / 50.0)
         - g.salt / 0.006 - (1.5 if g.device == "hider" else 0.0) + (0.3 if g.device == "brake" else 0.0))
    P_sec = sigmoid(2.0 * M)
    E_ab = m * p["e_ab"]
    lam_f = ((E_blast + P_sec * E_ab) / P0) ** (1 / 3)      # expected flash length scale
    t_s = 5.0 * lam_f / C0                                   # secondary duration [INFERRED, fits 6 ms rifle, 100 ms 152 mm]
    t_e = g.L_cal * g.d / 300.0 + 2e-4                       # gun-emptying / primary+intermediate [INFERRED, Steward 20 ms]
    # smoke (extinction areas, m^2, natural log) [INFERRED; calibrated to the 30 mm CQMS, .md §5.3]
    hyg = 1.0 + 2.0 * RH ** 4                                # K-salt aerosols take up water
    y_sol = p["solids"] + 1.0 * g.salt + 0.56 * g.igniter + 0.8 * g.liner
    alpha = p["alpha"] if g.prop != "black_powder" else 1.5
    A_p = m * 1000.0 * y_sol * alpha * hyg
    chi = 0.15 * np.clip((RH - 0.5) / 0.5, 0, 1) ** 2 * (1 + max(0.0, (10 - T_amb_C) / 20))
    A_w = m * 1000.0 * p["water"] * min(chi, 0.4) * 0.5     # condensed water, 0.5 m^2/g
    tau_w = 2.0 / max(1.0 - RH, 0.03)                        # fog evaporation time
    return dict(m=m, E_blast=E_blast, lam_b=lam_b, p_m=p_m, x_M=x_M, M=M, P_sec=P_sec, E_ab=E_ab,
                lam_f=lam_f, t_s=t_s, t_e=t_e, A_p=A_p, A_w=A_w, tau_w=tau_w, T_sec=p["T_sec"],
                tint=np.array(p["tint"]), flash_len=x_M + 1.5 * lam_f, y_sol=y_sol)


# ---------------------------------------------------------------- one shot
@dataclass
class Shot:
    gun: Gun
    pos: tuple = (0.0, 0.0)
    h: float = 10.0               # muzzle height above water
    az: float = 0.0               # bore bearing in the map plane, rad
    el: float = 0.05              # elevation, rad
    t0: float = 0.0
    seed: int = 0
    wind: tuple = (5.0, 0.0)
    RH: float = 0.7
    T_amb_C: float = 15.0
    D: dict = field(default=None)

    def __post_init__(self):
        self.D = derive(self.gun, self.RH, self.T_amb_C)
        rng = np.random.default_rng(self.seed)
        # per-shot randomness: secondary flash fires or not (small guns), intensity scatter
        self.sec_on = rng.random() < self.D["P_sec"]
        self.jit = float(np.exp(0.25 * rng.standard_normal()))
        self.lobes = rng.random(6) * 2 * np.pi
        E = self.D["E_blast"] + (self.D["E_ab"] * self.jit if self.sec_on else 0.0)
        self.lam_f = (E / P0) ** (1 / 3)
        self.t_s = 5.0 * self.lam_f / C0

    # ---- bore geometry
    def axis3(self):
        return np.array([math.cos(self.el) * math.cos(self.az), math.cos(self.el) * math.sin(self.az), math.sin(self.el)])

    def emitters(self, t):
        """Active luminous emitters at time t (s after t0).
        Each: centre (x,y,z), semi-axes (along-bore a, lateral b), temperature T, emissivity eps -> L, I."""
        D, out = self.D, []
        tt = t - self.t0
        if tt < 0:
            return out
        ax = self.axis3(); base = np.array([self.pos[0], self.pos[1], self.h])
        d, xM = self.gun.d, D["x_M"]
        # primary: hot core at the muzzle, cools as it expands  (decays over ~0.5 t_e)
        if tt < D["t_e"]:
            f = tt / D["t_e"]
            # hot core only: the bulk of the non-burning plume is 850-1050 K (Steward 2012), ~invisible in daylight
            T = 2000 - 800 * f
            r = 1.5 * d + 0.12 * xM * min(1, 4 * f)
            out.append(self._em(base + ax * 0.35 * xM, 0.35 * xM + r, r, T, 1 - math.exp(-r / 2.0), "primary"))
            # intermediate: reddish disc just downstream of the Mach disk, re-heated by the normal shock
            Ti = 1900 - 500 * f
            ri = 0.22 * xM
            out.append(self._em(base + ax * xM, 0.10 * xM, ri, Ti, 1 - math.exp(-ri / 3.0), "intermediate"))
        # secondary: fuel-rich gas burning with entrained air
        if self.sec_on:
            ts = self.t_s
            rise, fall = 0.12 * ts, ts
            if tt < fall:
                env = min(1.0, tt / rise) * (1 - ((tt - rise) / (fall - rise)) ** 2 if tt > rise else 1.0)
                T = D["T_sec"] * (0.75 + 0.25 * env) * self.jit ** 0.05
                lf = self.lam_f
                grow = min(1.0, 0.35 + 0.65 * tt / (0.5 * ts))
                a, b = 0.8 * lf * grow, 0.5 * lf * grow
                c = base + ax * (xM + 0.7 * lf * grow)
                # buoyant lift: negligible below ~1 s duration, visible for the joke tier [INFERRED]
                c = c + np.array([0, 0, 0.5 * 0.6 * G * tt ** 2])
                eps = 1 - math.exp(-b / 6.0)
                out.append(self._em(c, a, b, T, eps, "secondary", env))
        return out

    def _em(self, c, a, b, T, eps, kind, env=1.0):
        L = eps * bb_luminance(T) * env
        rgb = bb_rgb(T)
        if kind == "secondary":
            # Na D (589 nm) + K + soot continuum: observed flash is yellow-orange, not 1700 K red  [SRC Steward 2012
            # lines; mix weight INFERRED]. K-salted charges suppress this lobe, leaving the red primary/intermediate.
            rgb = 0.45 * rgb + 0.55 * np.array([1.0, 0.62, 0.18])
        return dict(c=c, a=a, b=b, T=T, eps=eps, L=L, I=L * math.pi * a * b, kind=kind, rgb=rgb)

    def intensity(self, t):
        return sum(e["I"] for e in self.emitters(t))

    def effective_intensity(self, dt=1e-4, a=0.2):
        """Blondel-Rey effective intensity over the whole flash: Ie = int I dt / (a + t2 - t1)."""
        T = max(self.t_s if self.sec_on else 0, self.D["t_e"]) * 1.05
        ts = np.arange(0, T, dt)
        I = np.array([self.intensity(self.t0 + x) for x in ts])
        on = ts[I > 0.02 * I.max()] if I.max() > 0 else ts[:1]
        return I.sum() * dt / (a + (on[-1] - on[0])), I.max(), on[-1] - on[0]

    # ---- smoke puff (one Gaussian per shot; merge for rapid fire)
    def puff(self, t):
        tt = t - self.t0
        if tt <= 0:
            return None
        D, lf = self.D, self.lam_f
        ax = self.axis3()
        hdir = np.array([ax[0], ax[1]]) / max(1e-6, math.hypot(ax[0], ax[1]))
        X_inf, tau_m = 2.5 * lf, 0.04 * lf + 0.05            # forward carry of the gas jet [INFERRED]
        s = X_inf * (1 - math.exp(-tt / tau_m))
        xy = np.array(self.pos) + hdir * (D["x_M"] + s) * math.cos(self.el) + np.array(self.wind) * tt
        # buoyant rise of the warm cloud: the most uncertain knob here; it decides whether a puff passes
        # over or through a 10-30 m sight line [INFERRED]
        z = self.h + (D["x_M"] + s) * math.sin(self.el) + 0.6 * lf * (1 - math.exp(-tt / (3 + 0.05 * lf)))
        U = math.hypot(*self.wind)
        sh = math.sqrt((0.35 * lf) ** 2 + ((0.07 * U + 0.2) * tt) ** 2 + 0.5 * tt)   # [INFERRED]
        sz = 0.8 * sh
        # smoke "develops" as the gas cools and salts/water condense: ramp over ~ the flash duration [INFERRED;
        # Yan 2023: 30 mm smoke mass peaks ~9.5 ms after shot exit, i.e. after the flash phase]
        ramp = 1 - math.exp(-tt / (0.5 * max(self.t_s, D["t_e"]) + 0.004))
        A = ramp * (D["A_p"] + D["A_w"] * math.exp(-tt / D["tau_w"]))
        return dict(xy=xy, z=z, sh=sh, sz=sz, A=A, tint=D["tint"])


# ---------------------------------------------------------------- gameplay queries
def tau_vertical(puffs, x, y):
    """Vertical optical depth (what the top-down camera sees through)."""
    tau = 0.0
    for p in puffs:
        r2 = (x - p["xy"][0]) ** 2 + (y - p["xy"][1]) ** 2
        tau = tau + p["A"] / (2 * np.pi * p["sh"] ** 2) * np.exp(-r2 / (2 * p["sh"] ** 2))
    return tau


def tau_los(puffs, a, b):
    """Optical depth along the straight segment a->b (3D points). Exact for Gaussian puffs
    with horizontal sigma sh and vertical sigma sz, segment assumed near-horizontal."""
    from math import erf, sqrt
    a, b = np.asarray(a, float), np.asarray(b, float)
    seg = b - a; Lh = math.hypot(seg[0], seg[1])
    if Lh < 1e-6:
        return 0.0
    u = seg[:2] / Lh
    tau = 0.0
    for p in puffs:
        rel = p["xy"] - a[:2]
        s0 = rel @ u                                  # along-segment coordinate of the puff centre
        dperp = rel[0] * u[1] - rel[1] * u[0]
        zline = a[2] + seg[2] * np.clip(s0 / Lh, 0, 1)
        dz = zline - p["z"]
        k = p["A"] / (2 * np.pi * p["sh"] * p["sz"]) * math.exp(-dperp ** 2 / (2 * p["sh"] ** 2) - dz ** 2 / (2 * p["sz"] ** 2))
        frac = 0.5 * (erf((Lh - s0) / (sqrt(2) * p["sh"])) - erf((0 - s0) / (sqrt(2) * p["sh"])))
        tau += k * frac
    return tau


def merge_puffs(puffs, k=1.0):
    """Merge puffs closer than k*sigma (rapid-fire guns): sum A, A-weighted centroid, second-moment sigma."""
    out = []
    for p in sorted(puffs, key=lambda q: -q["A"]):
        for q in out:
            d2 = float(np.sum((p["xy"] - q["xy"]) ** 2))
            if d2 < (k * max(p["sh"], q["sh"])) ** 2:
                A = p["A"] + q["A"]; w = p["A"] / A
                c = q["xy"] * (1 - w) + p["xy"] * w
                sh2 = (1 - w) * (q["sh"] ** 2 + np.sum((q["xy"] - c) ** 2) / 2) + w * (p["sh"] ** 2 + np.sum((p["xy"] - c) ** 2) / 2)
                q.update(xy=c, A=A, sh=math.sqrt(sh2), sz=0.8 * math.sqrt(sh2), z=q["z"] * (1 - w) + p["z"] * w)
                break
        else:
            out.append(dict(p))
    return out


# ---------------------------------------------------------------- photometry helpers
def threshold_illuminance(B):
    """Point-source threshold illuminance at the eye (lux) vs background luminance B (cd/m^2).
    log10 Et = 0.57 log10 B + 0.05 (log10 B)^2 - 6.66, floored at night ~2e-7 lux.  [UNCERTAIN: ICAO-style
    relation quoted from memory; the night floor is the AMS/IALA 0.15-0.2 microlux value]"""
    lb = math.log10(max(B, 1e-6))
    return max(10 ** (0.57 * lb + 0.05 * lb * lb - 6.66), 2e-7)


def detection_range(Ie, B, vis_km=20.0, h_src=10.0, h_eye=30.0):
    """Allard's law E = I exp(-sigma r)/r^2 solved for E = Et(B); sigma = 3.912/V (Koschmieder).
    Returns (range m, geometric horizon m). Beyond the horizon only sky-glow on cloud/smoke remains (night)."""
    Et, sig = threshold_illuminance(B), 3.912 / (vis_km * 1e3)
    lo, hi = 1.0, 1e7
    for _ in range(80):
        mid = math.sqrt(lo * hi)
        if Ie * math.exp(-sig * mid) / mid ** 2 > Et:
            lo = mid
        else:
            hi = mid
    horizon = 3570.0 * (math.sqrt(h_src) + math.sqrt(h_eye))
    return lo, horizon


def stretch_for_frames(I, t_flash, t_min):
    """Blondel-Rey-preserving stretch: render a flash shorter than t_min over t_min at reduced intensity."""
    if t_flash >= t_min:
        return I, t_flash
    return I * t_flash * (0.2 + t_min) / (t_min * (0.2 + t_flash)), t_min


# ---------------------------------------------------------------- renderer (numpy stand-in for the GPU path)
def render(shots, t, mpp, W=256, H=256, centre=(0.0, 0.0), night=False, k_obl=0.6, frame_dt=1 / 60, sun_lux=1e5, adapt=True):
    """HDR top-down render. Emitters are splatted energy-conservingly (sprite -> blob -> point automatically).
    Returns tonemapped sRGB uint8."""
    from scipy.ndimage import gaussian_filter
    xs = centre[0] + (np.arange(W) - W / 2 + 0.5) * mpp
    ys = centre[1] + (np.arange(H) - H / 2 + 0.5) * mpp
    X, Y = np.meshgrid(xs, ys)
    L_bg = 0.002 if night else 1500.0
    sea = np.array([0.20, 0.42, 0.80]) / 0.4 * L_bg                     # linear rgb scaled to luminance
    img = np.broadcast_to(sea, (H, W, 3)).copy()
    # ---- smoke (drawn in oblique "VFX up" projection: sy = y + k z')
    zc = lambda z: 450.0 * (1 - np.exp(-z / 450.0))
    puffs = [p for p in (s.puff(t) for s in shots) if p is not None]
    # sub-frame averaged flash light for smoke illumination at night
    flash_sub = [t - frame_dt * (i + 0.5) / 4 for i in range(4)]
    lights = []
    for s in shots:
        for ts in flash_sub:
            for e in s.emitters(ts):
                lights.append((e["c"], e["I"] / 4, e["rgb"]))
    for p in puffs:
        cx, cy = p["xy"][0], p["xy"][1] + k_obl * zc(p["z"])
        tau = p["A"] / (2 * np.pi * p["sh"] ** 2) * np.exp(-((X - cx) ** 2 + (Y - cy) ** 2) / (2 * p["sh"] ** 2))
        alpha = 1 - np.exp(-tau)
        if night:
            Lsm = np.zeros(3) + 0.004                                    # starlight / moon
            for c, I, rgb in lights:
                r2 = (c[0] - p["xy"][0]) ** 2 + (c[1] - p["xy"][1]) ** 2 + (c[2] - p["z"]) ** 2 + p["sh"] ** 2
                Lsm = Lsm + 0.9 * I / r2 / np.pi * rgb / max(rgb.sum() / 3, 1e-3) * 0.5
        else:
            Lsm = 0.9 * sun_lux / np.pi * 0.35 * np.ones(3)               # multiple-scatter fudge 0.35
        col = p["tint"] * Lsm
        # self-shadowing: thick centres darker on the far side [cheap]
        shade = 1 - 0.35 * (1 - np.exp(-0.5 * tau))
        img = img * (1 - alpha[..., None]) + (col * shade[..., None]) * alpha[..., None]
    # ---- flash emitters, time-averaged over the frame (no flicker/aliasing for sub-frame flashes)
    lum = np.zeros((H, W, 3))
    for s in shots:
        for ts in flash_sub:
            for e in s.emitters(ts):
                cx, cy = e["c"][0], e["c"][1] + k_obl * zc(e["c"][2])
                ca, sa = math.cos(s.az), math.sin(s.az)
                sx_ = max(e["a"] * abs(math.cos(s.el)) / 1.5, 0.6 * mpp)  # projected along-bore sigma
                sy_ = max(e["b"] / 1.5, 0.6 * mpp)
                dx, dy = X - cx, Y - cy
                u, v = dx * ca + dy * sa, -dx * sa + dy * ca
                ang = np.arctan2(v, u)
                rmod = 1 + (0.18 * np.sin(3 * ang + s.lobes[0]) + 0.12 * np.sin(5 * ang + s.lobes[1])) * (e["kind"] == "secondary")
                w = np.exp(-0.5 * ((u / (sx_ * rmod)) ** 2 + (v / (sy_ * rmod)) ** 2))
                # ANALYTIC normalisation (integral of the Gaussian), never w.sum() over visible pixels: an emitter
                # just off-screen would otherwise dump its whole intensity into the tail pixels at the edge.
                Lpix = e["I"] / 4 * w / (2 * np.pi * sx_ * sy_ * 1.03)   # cd/m^2  (1.03 ~ mean rmod^2)
                lum += Lpix[..., None] * (e["rgb"] / max(e["rgb"] @ np.array([.2126, .7152, .0722]), 1e-3))
    img = img + lum
    # exposure keyed to the background, with a night floor (eye is not a camera at 0.002 nit)
    # + "flash adaptation": key follows the screen mean when emitters dominate (game: fast attack ~0.05 s,
    # slow release ~1-2 s, so the dark-adapted night view returns after the salvo)
    Ymean = float((img @ np.array([0.2126, 0.7152, 0.0722])).mean())
    key = max(L_bg, 0.05, 0.6 * Ymean if adapt else 0.0)
    key = min(key, 4.0 * L_bg if not night else 500.0)               # day: barely adapts; night: up to 1e4x
    x = img * (0.18 / key) * (0.25 if night and key <= 0.05 else 1.0)
    # glare / bloom on a COMPRESSED source: a 1e8 cd flash must not paint the whole screen [game choice]
    src = x / (1 + x / 6.0)
    for frac, sig in ((0.20, 1.5), (0.10, 6.0), (0.05, 18.0)):
        x = x + frac * np.stack([gaussian_filter(src[..., i], sig) for i in range(3)], -1)
    # hue-preserving tonemap on luminance, then roll excess energy toward white (no per-channel clip -> no "yellow")
    Y = np.maximum(x @ np.array([0.2126, 0.7152, 0.0722]), 1e-9)
    Yt = 1 - np.exp(-Y)
    rgb = x * (Yt / Y)[..., None]
    mx = rgb.max(-1, keepdims=True)
    over = np.clip((np.log2(np.maximum(Y, 1e-9))[..., None] - 0.0) / 4.0, 0, 1)   # 1x..16x over white -> desat
    rgb = rgb / np.maximum(mx, 1.0) * (1 - over) + Yt[..., None] * over
    return (np.clip(rgb, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)


# ---------------------------------------------------------------- the calibre ladder
LADDER = [
    Gun("20 mm Oerlikon", 0.020, 70, 0.028, "single_base", igniter=0.003),
    Gun("40 mm Bofors", 0.040, 56, 0.31, "single_base", igniter=0.003),
    Gun("5\"/38", 0.127, 38, 7.0, "single_base", igniter=0.003),
    Gun("6\"/47", 0.152, 47, 15.0, "single_base", igniter=0.01),
    Gun("155 mm howitzer", 0.155, 39, 12.0, "triple_base", salt=0.01, liner=0.005, igniter=0.01),
    Gun("8\"/55", 0.203, 55, 41.0, "single_base", igniter=0.01),
    Gun("15\"/42 cordite SC", 0.381, 42, 196.0, "double_base", igniter=0.01),
    Gun("16\"/50 SPD", 0.406, 50, 297.0, "single_base", igniter=0.01),
    Gun("16\"/50 SPCG flashless", 0.406, 50, 312.0, "triple_base", igniter=0.01, salt=0.005),
    Gun("46 cm/45", 0.460, 45, 360.0, "single_base", igniter=0.01),
    Gun("80 cm railway (Gustav-like)", 0.800, 40, None, "diglycol", igniter=0.01),
    Gun("1000 mm turbocannon", 1.000, 50, None, "lova", igniter=0.01),
    Gun("2000 mm turbocannon", 2.000, 50, None, "lova", igniter=0.01),
]


def ladder_table(RH=0.7):
    rows = []
    for g in LADDER:
        s = Shot(g, seed=1, RH=RH)
        s.sec_on = s.D["P_sec"] > 0.5  # deterministic for the table
        Ie, Ipk, dur = s.effective_intensity(dt=max(2e-5, s.D["t_e"] / 200))
        D = s.D
        r_night, hor = detection_range(Ie, 0.002)
        r_day, _ = detection_range(Ie, 1500.0)
        rows.append(dict(name=g.name, m=D["m"], lam_b=D["lam_b"], lam_f=D["lam_f"], x_M=D["x_M"], x_M_cal=D["x_M"] / g.d,
                         P_sec=D["P_sec"], len=D["flash_len"], fireball=1.6 * D["lam_f"] if s.sec_on else 0,
                         t_s=D["t_s"] if s.sec_on else 0, t_e=D["t_e"], Ipk=Ipk, Ie=Ie, r_day=r_day, r_night=r_night,
                         A_p=D["A_p"], A_w=D["A_w"]))
    return rows


if __name__ == "__main__":
    import sys
    rows = ladder_table()
    hdr = (f"{'gun':30s} {'m kg':>8s} {'lam_b':>6s} {'lam_f':>6s} {'x_M':>6s} {'x_M/d':>5s} {'Psec':>5s} "
           f"{'flashL':>7s} {'ballD':>6s} {'t_sec':>7s} {'t_e':>7s} {'Ipk cd':>9s} {'Ie cd':>9s} {'r_day':>7s} {'r_night':>8s} {'A_smoke':>8s} {'A_fog':>7s}")
    print(hdr)
    for r in rows:
        print(f"{r['name']:30s} {r['m']:8.3g} {r['lam_b']:6.2f} {r['lam_f']:6.2f} {r['x_M']:6.2f} {r['x_M_cal']:5.1f} {r['P_sec']:5.2f} "
              f"{r['len']:7.2f} {r['fireball']:6.1f} {r['t_s']*1e3:6.0f}ms {r['t_e']*1e3:6.1f}ms {r['Ipk']:9.3g} {r['Ie']:9.3g} "
              f"{r['r_day']/1e3:6.2f}k {r['r_night']/1e3:7.0f}k {r['A_p']:8.3g} {r['A_w']:7.3g}")
    # CQMS calibration check (Yan et al. 2023: 30 mm charge, 2.35 m^2 decadic at 460 nm, t1 = 9.5 ms)
    g30 = Gun("30 mm (CQMS check)", 0.030, 80, 0.11, "single_base", salt=0.01, igniter=0.003)
    D30 = derive(g30, RH=0.6)
    print("\n30 mm CQMS check: model A_p =", round(D30["A_p"], 2), "m^2 (natural)  vs measured 2.35*ln10 =",
          round(2.35 * math.log(10), 2), "m^2  [charge mass assumed 0.11 kg]")
    if "--figs" in sys.argv:
        import figs_muzzle_flash  # noqa: F401  (separate figure script)