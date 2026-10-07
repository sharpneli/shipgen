"""Magazine explosion VFX reference (top-down, numpy).

Companion to claude/magazine-explosion-vfx-research.md and
claude/damage-research/07_magazine_explosions.md.

Stand-in for the GPU particle system: CPU particles + soft splats, sorted by
height and composited 'over' as the GPU would. Everything here maps to:
  - particles (fire, smoke, steam, debris, sparks)   -> GPU particles, flipbook quads
  - coarse density grid + sun optical depth          -> 3D shadow volume / 6-way lightmaps
  - fire point lights                                -> 1-4 dynamic point lights
  - water: shadow, fire light, glint, shock frost    -> water shader terms (event buffers)

Events (from the mechanics doc, §6.3 tiers):
  tier 1  'column'   vented flame column out of a barbette (Lion, Seydlitz)
  tier 3+ 'blast'    fireball + mushroom + stem + debris + shock (Queen Mary, Hood)

Scaling laws used (see the doc for sources):
  fireball   D = 5.8 M^(1/3) m, t = 0.45 M^(1/3) s (M < 30 t) else 2.6 M^(1/6) s, lift-off H ~ D
  flame      L = 0.235 Q^(2/5) - 1.02 D   (Heskestad; Q in kW)
  blast      lambda = (E/p0)^(1/3) (same as muzzle_blast_ref.py)
"""
import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates, zoom, shift as nd_shift

KAPPA = 900.0     # particle opacity scale (m^2 per unit mass)
I_REF = 3.0e4     # fire light normalisation


def _fbm(n=256, seed=7):
    rng = np.random.default_rng(seed)
    f = np.zeros((n, n))
    for o, a in [(4, 1.0), (8, 0.5), (16, 0.25), (32, 0.125)]:
        g = rng.random((o, o))
        f += a * zoom(np.pad(g, 1, mode="wrap"), n / o, order=3)[n // o // 2: n // o // 2 + n, n // o // 2: n // o // 2 + n]
    f = (f - f.min()) / (f.max() - f.min())
    return f


NOISE = None   # flipbook stand-in: one tiling fBm, sampled with a per-particle offset

G = 9.81
P0 = 101325.0

# ----------------------------------------------------------------- scaling
def fireball(M_kg):
    D = 5.8 * M_kg ** (1 / 3)
    t = 0.45 * M_kg ** (1 / 3) if M_kg < 30000 else 2.6 * M_kg ** (1 / 6)
    return D, t


def heskestad(Q_kW, D):
    return max(0.235 * Q_kW ** 0.4 - 1.02 * D, 0.0)


def blast_lambda(M_kg, f=4.0e6, eff=0.5):
    return (eff * f * M_kg / P0) ** (1 / 3)


# ------------------------------------------------------------- colour ramps
def blackbody(T):
    """T in 0..1 -> stylised fire colour (deep red -> crimson -> orange -> yellow -> white).
    Linear HDR, multiplied by intensity outside."""
    keys = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
    cols = np.array([[0.25, 0.02, 0.01],
                     [0.90, 0.10, 0.04],   # crimson (eyewitness word for cordite)
                     [1.00, 0.38, 0.08],
                     [1.00, 0.72, 0.30],
                     [1.00, 0.95, 0.85]])
    T = np.clip(T, 0, 1)
    return np.stack([np.interp(T, keys, cols[:, c]) for c in range(3)], -1)


# --------------------------------------------------------------- particles
class Particles:
    FIELDS = dict(pos=3, vel=3, r=1, m=1, temp=1, heat=1, age=1, life=1, kind=1, tcool=1, seed=1)
    # kind: 0 fire/smoke (soot), 1 steam (white), 2 debris (solid, ballistic), 3 spark

    def __init__(self):
        self.d = {k: np.zeros((0, n)) if n > 1 else np.zeros(0) for k, n in self.FIELDS.items()}

    def add(self, **kw):
        n = len(kw["pos"])
        for k, w in self.FIELDS.items():
            v = kw.get(k, 0.0)
            v = np.broadcast_to(np.asarray(v, float), (n, w) if w > 1 else (n,))
            self.d[k] = np.concatenate([self.d[k], v])

    def keep(self, mask):
        for k in self.d:
            self.d[k] = self.d[k][mask]

    def __len__(self):
        return len(self.d["r"])


def wind(z, u10):
    return u10 * np.clip(np.maximum(z, 1.0) / 10.0, 0, None) ** 0.14


# --------------------------------------------------------------- the event
class MagazineEvent:
    """One magazine event. `mode` = 'column' (tier 1) or 'blast' (tier 3/4)."""

    def __init__(self, x, y, mode, M_burn_kg, barbette_D=8.5, duration=14.0,
                 u10=(6.0, 1.5), seed=3, n_debris=60, vents=(), openings=(), t_main=0.0,
                 P_peak=3.0, roof=None):
        self.p = Particles()
        self.rng = np.random.default_rng(seed)
        self.x, self.y, self.mode = x, y, mode
        self.M = M_burn_kg
        self.Dbar = barbette_D
        self.duration = duration
        self.u10 = np.array(u10)
        self.t = 0.0
        self.vents = list(vents)          # (x, y, delay, strength) secondary vents (Hood mainmast)
        self.lights = []
        self.shock = None
        # jet phase (see the VFX doc, 'Jet phase'): openings fail before the main event
        self.openings = list(openings)    # dicts: pos, dir, d, t_fail, Lmax
        self.t_main = t_main              # fireball / turret lift time after first ignition
        self.P_peak = P_peak              # magazine pressure at t_main, bar absolute
        self.roof = roof                  # (x, y, z, t_lift): a turret roof thrown off by the pressure
        self.n_debris = n_debris
        self._main_done = False
        if mode == "blast":
            self.D, self.t_fb = fireball(M_burn_kg)
            self.lam = blast_lambda(M_burn_kg)
            if t_main <= 0:
                self._spawn_fireball()
                self._spawn_debris(n_debris)
                self._main_done = True
        else:
            self.lam = blast_lambda(M_burn_kg * 0.05)   # turret lift pop only
            self._spawn_debris(max(6, n_debris // 6), vmax=28.0, roof=True)

    # ---- spawners
    def _spawn_fireball(self):
        rng, n = self.rng, 320
        R = self.D / 2
        u = rng.normal(size=(n, 3)); u /= np.linalg.norm(u, axis=1, keepdims=True)
        u[:, 2] = np.abs(u[:, 2]) * 1.6 + 0.2          # hemispherical, biased upward (decks vent up)
        u /= np.linalg.norm(u, axis=1, keepdims=True)
        s = rng.random(n) ** 0.5
        v = u * (s[:, None] * 2.2 * R / self.t_fb)        # reach ~R in ~t_fb/2
        pos = np.c_[np.full(n, self.x), np.full(n, self.y), np.full(n, 6.0)] + u * 4
        self.p.add(pos=pos, vel=v, r=0.14 * R + 0.06 * R * rng.random(n), m=1.6,
                   temp=0.55 + 0.45 * (1 - s) ** 0.5 * rng.uniform(0.7, 1, n), heat=1.0, life=1e9, kind=0,
                   tcool=self.t_fb * (0.35 + 0.6 * rng.random(n)), seed=rng.random(n))
        # side vents along the hull (Hood: gas out through the sides): low flat jets
        k = 50
        side = rng.choice([-1, 1], k)
        pos = np.c_[self.x + rng.uniform(-30, 30, k), self.y + side * 14, np.full(k, 3.0)]
        v = np.c_[rng.normal(0, 6, k), side * rng.uniform(10, 35, k), rng.uniform(2, 12, k)]
        self.p.add(pos=pos, vel=v, r=4 + 4 * rng.random(k), m=0.8, temp=0.8, heat=0.4,
                   life=1e9, kind=0, tcool=0.6 + 0.6 * rng.random(k), seed=rng.random(k))

    def _spawn_debris(self, n, vmax=None, roof=False):
        rng = self.rng
        if vmax is None:
            vmax = np.sqrt(2 * G * 140.0)                  # 'hurled hundreds of feet' -> ~140 m apex
        el = np.radians(rng.uniform(35, 88, n))
        az = rng.uniform(0, 2 * np.pi, n)
        sp = vmax * rng.random(n) ** 0.6
        v = np.c_[np.cos(el) * np.cos(az) * sp, np.cos(el) * np.sin(az) * sp, np.sin(el) * sp]
        pos = np.c_[np.full(n, self.x), np.full(n, self.y), np.full(n, 8.0)]
        burning = rng.random(n) < (0.5 if not roof else 0.2)
        self.p.add(pos=pos, vel=v, r=1.2 + 1.5 * rng.random(n), m=1.0, temp=np.where(burning, 1.0, 0.0),
                   heat=0.0, life=1e9, kind=2, tcool=4 + 6 * rng.random(n), seed=rng.random(n))

    def _emit_column(self, dt):
        """Tier 1 vented column: Q(t) -> flame height by Heskestad; spawn jet puffs."""
        t, rng = self.t, self.rng
        if t > self.duration:
            return 0.0
        env = np.clip(t / 0.4, 0, 1) * np.clip((self.duration - t) / 4.0, 0, 1)
        pulse = 0.75 + 0.25 * np.sin(2 * np.pi * 0.7 * t) * np.sin(2 * np.pi * 0.23 * t + 1)
        Q = 1.6e6 * env * pulse                            # kW; ~60 m flame (Lion '200 ft')
        L = heskestad(Q, self.Dbar)
        if L <= 0:
            return 0.0
        n = int(30 * env * dt / 0.05) + 1
        w0 = 2.2 * L / 1.5                                 # puffs reach L in ~1.5 s
        ang = rng.uniform(0, 2 * np.pi, n); rr = self.Dbar / 2 * np.sqrt(rng.random(n))
        pos = np.c_[self.x + rr * np.cos(ang), self.y + rr * np.sin(ang), np.full(n, 10.0)]
        vel = np.c_[rng.normal(0, 2.5, n), rng.normal(0, 2.5, n), w0 * (0.7 + 0.5 * rng.random(n))]
        self.p.add(pos=pos, vel=vel, r=self.Dbar * (0.5 + 0.25 * rng.random(n)), m=0.6,
                   temp=0.95, heat=0.7, life=1e9, kind=0,
                   tcool=1.1 * (0.6 + 0.6 * rng.random(n)), seed=rng.random(n))
        # sparks / burning grains
        k = int(25 * env * dt / 0.05)
        if k:
            v = np.c_[rng.normal(0, 9, k), rng.normal(0, 9, k), w0 * rng.uniform(0.6, 1.4, k)]
            self.p.add(pos=pos[:1].repeat(k, 0), vel=v, r=0.6, m=1.0, temp=1.0, heat=0.0,
                       life=rng.uniform(1.5, 3.5, k), kind=3, tcool=2.0, seed=rng.random(k))
        return Q

    def _emit_fires(self, dt):
        """After the blast: burning wreck + oil -> continuous low-buoyancy stem smoke."""
        if (self.t - self.t_main) < 0.6 * self.t_fb:
            return 0.0
        rng = self.rng
        env = np.exp(-((self.t - self.t_main) - self.t_fb) / 40.0) if (self.t - self.t_main) > self.t_fb else 1.0
        n = int(rng.random() < 0.5 + 3 * env * dt)
        pos = np.c_[self.x + rng.normal(0, 20, n), self.y + rng.normal(0, 8, n), np.full(n, 6.0)]
        vel = np.c_[rng.normal(0, 2, n), rng.normal(0, 2, n), rng.uniform(8, 20, n)]
        self.p.add(pos=pos, vel=vel, r=10 + 6 * rng.random(n), m=2.5, temp=0.75, heat=0.35,
                   life=1e9, kind=0, tcool=0.8, seed=rng.random(n))
        # boiler steam (white) early on
        if (self.t - self.t_main) < 12:
            k = int(rng.random() < 0.6)
            pos = np.c_[self.x - 60 + rng.normal(0, 10, k), self.y + rng.normal(0, 6, k), np.full(k, 8.0)]
            self.p.add(pos=pos, vel=np.c_[rng.normal(0, 2, k), rng.normal(0, 2, k), rng.uniform(15, 30, k)],
                       r=9.0, m=1.2, temp=0.0, heat=0.3, life=1e9, kind=1, tcool=1, seed=rng.random(k))
        return 3e5 * env

    def _emit_vents(self, dt):
        q = 0.0
        for (vx, vy, delay, s) in self.vents:
            a = self.t - self.t_main - delay
            if 0 < a < 6:
                env = np.sin(np.pi * a / 6) * s
                n = int(30 * env * dt / 0.05) + 1
                rng = self.rng
                pos = np.c_[vx + rng.normal(0, 3, n), vy + rng.normal(0, 3, n), np.full(n, 15.0)]
                vel = np.c_[rng.normal(0, 3, n), rng.normal(0, 3, n), rng.uniform(50, 90, n) * env]
                self.p.add(pos=pos, vel=vel, r=4 + 3 * rng.random(n), m=0.4, temp=1.0, heat=0.6,
                           life=1e9, kind=0, tcool=0.9, seed=rng.random(n))
                q += 8e5 * env
        return q

    # ---- step
    def pressure(self, t):
        """Magazine pressure (bar abs): stand-in for the mechanics ODE (07 §6.2).
        Rises while the burn races the vents, peaks as the boundaries fail, then vents down."""
        if t < self.t_main:
            return 1.0 + (self.P_peak - 1.0) * (t / max(self.t_main, 1e-3)) ** 2
        return 1.0 + (self.P_peak - 1.0) * np.exp(-(t - self.t_main) / 0.7)

    def _emit_jets(self, dt):
        """Directional flame jets from every failed opening: hatches, ports, ventilators, hoods.
        Length ~ 45 d sqrt(P/p0) [INFERRED, fuel-rich propellant gas afterburning in air], capped.
        Puffs are spawned along the jet axis (like a GPU 'spawn along a line' emitter)."""
        rng, t = self.rng, self.t
        P = self.pressure(t)
        q = 0.0
        for o in self.openings:
            a = t - o["t_fail"]
            if a < 0 or P < 1.15:
                continue
            env = min(1.0, a / 0.08)
            L = min(45.0 * o["d"] * np.sqrt(P), o.get("Lmax", 150.0)) * env
            if L < 2:
                continue
            dirv = np.asarray(o["dir"], float); dirv = dirv / np.linalg.norm(dirv)
            perp1 = np.cross(dirv, [0, 0, 1.0])
            if np.linalg.norm(perp1) < 1e-3:
                perp1 = np.array([1.0, 0, 0])
            perp1 /= np.linalg.norm(perp1); perp2 = np.cross(dirv, perp1)
            n = int(max(4, 16 * L / 30) * dt / 0.05)
            s = rng.random(n) ** 0.8
            spread = (0.015 + 0.07 * s) * L
            jit = (rng.normal(size=(n, 1)) * perp1 + rng.normal(size=(n, 1)) * perp2) * spread[:, None] * 0.5
            pos = np.asarray(o["pos"], float) + dirv * (s * L)[:, None] + jit
            w = L / 0.35                                     # jet speed scale (near-sonic at the exit)
            vel = dirv * (w * (1 - s) * 0.12)[:, None] + rng.normal(0, 2, (n, 3))
            self.p.add(pos=pos, vel=vel, r=o["d"] * 0.45 + 0.06 * s * L, m=0.04 + 0.08 * s,
                       temp=1.0 - 0.3 * s * rng.random(n), heat=0.25, life=0.6 + 1.2 * rng.random(n), kind=0,
                       tcool=0.08 + 0.2 * s, seed=rng.random(n))
            k = int(6 * dt / 0.05 * env)
            if k:   # burning fragments / grains thrown out of the opening
                v = dirv * w * rng.uniform(0.15, 0.4, (k, 1)) + rng.normal(0, 6, (k, 3))
                self.p.add(pos=np.repeat([o["pos"]], k, 0), vel=v, r=0.5, m=1.0, temp=1.0, heat=0.0,
                           life=rng.uniform(0.8, 2.0, k), kind=3, tcool=1.5, seed=rng.random(k))
            q += 2e4 * L
        return q

    def step(self, dt):
        self.t += dt
        if self.roof is not None and self.t >= self.roof[3] and not getattr(self, "_roof_done", False):
            self._roof_done = True
            rx, ry, rz, _ = self.roof
            rng = self.rng
            # gunhouse roof plates: big, slow, tumbling up out of the smoke
            v = np.c_[rng.normal(-4, 4, 3), rng.normal(0, 4, 3), rng.uniform(28, 40, 3)]
            self.p.add(pos=np.array([[rx, ry, rz]] * 3) + rng.normal(0, 2, (3, 3)), vel=v, r=[4.0, 2.5, 2.0],
                       m=1.0, temp=0.3, heat=0.0, life=1e9, kind=2, tcool=6.0, seed=rng.random(3))
        if self.mode == "blast" and not self._main_done and self.t >= self.t_main:
            self._main_done = True
            self._spawn_fireball()
            self._spawn_debris(self.n_debris)
        if self.mode == "column":
            q = self._emit_column(dt)
        else:
            q = self._emit_fires(dt) if self._main_done else 0.0
        q += self._emit_vents(dt)
        q += self._emit_jets(dt)
        d, rng = self.p.d, self.rng
        if not len(self.p):
            return
        z = d["pos"][:, 2]
        kind = d["kind"]
        gas = kind < 2
        # gas: buoyancy from heat content, drag toward the wind, entrainment growth
        uw = wind(z, 1.0)[:, None] * np.c_[self.u10[0], self.u10[1], 0.0]
        tau = np.where(gas, 1.6, 1e9)
        a_b = np.where(gas, 26.0 * d["heat"], 0.0)
        d["vel"][:, 2] += a_b * dt
        d["vel"] += (uw - d["vel"]) * (1 - np.exp(-dt / tau))[:, None] * np.where(gas, 1, 0)[:, None]
        d["vel"][:, :2] += (uw[:, :2] - d["vel"][:, :2]) * (1 - np.exp(-dt / 6.0)) * (~gas)[:, None] * 0.3
        # mushroom: poloidal circulation around the rising cap (blast only)
        if self.mode == "blast" and self._main_done and self.t - self.t_main > 0.5 * self.t_fb:
            hot = gas & (d["heat"] > 0.25)
            if hot.sum() > 20:
                w = d["heat"][hot] * d["m"][hot]
                c = (d["pos"][hot] * w[:, None]).sum(0) / w.sum()
                R0 = 0.35 * max(np.sqrt(((d["pos"][hot, :2] - c[:2]) ** 2).sum(1)).mean(), 10)
                dxy = d["pos"][:, :2] - c[:2]; rh = np.linalg.norm(dxy, axis=1) + 1e-3
                er = dxy / rh[:, None]
                rel_r, rel_z = rh - R0, d["pos"][:, 2] - c[2]
                wgt = np.exp(-(rel_r ** 2 + rel_z ** 2) / (2.2 * R0) ** 2) * gas
                k = 0.18 * np.sqrt(G * max(R0, 1)) / max(R0, 1)
                d["vel"][:, :2] += (k * rel_z * wgt)[:, None] * er * dt * 4
                d["vel"][:, 2] += -k * rel_r * wgt * dt * 4
        # gravity for solids
        d["vel"][:, 2] -= np.where(gas, 0.0, G) * dt
        d["pos"] += d["vel"] * dt
        # ground: water at z=0
        hit = (~gas) & (d["pos"][:, 2] < 0)
        if hit.any():
            self.splashes = getattr(self, "splashes", []) + [(*p[:2], self.t) for p in d["pos"][hit & (kind == 2)]]
        speed = np.linalg.norm(d["vel"], axis=1)
        d["r"] += np.where(gas, (0.12 * speed + 0.35) * dt, 0.0)
        # soot skin: the top and outside of the fireball cool first, the fire keeps burning underneath
        cool = np.ones(len(kind))
        hotm = gas & (d["temp"] > 0.1)
        if self.mode == "blast" and hotm.sum() > 10:
            w = d["temp"][hotm] ** 2
            c = (d["pos"][hotm] * w[:, None]).sum(0) / w.sum()
            Rf = max(np.sqrt(((d["pos"][hotm] - c) ** 2).sum(1)).mean(), 5.0)
            rel = d["pos"] - c
            outer = np.clip((rel[:, 2] + 0.6 * np.linalg.norm(rel[:, :2], axis=1)) / Rf - 0.8, 0, None)
            cool = 1 + 0.9 * outer * (d["tcool"] > 1.0)
        d["temp"] *= np.exp(-dt * cool / d["tcool"])
        d["heat"] *= np.exp(-dt / np.where(self.mode == "blast", 28.0, 14.0))
        d["age"] += dt
        # remove: underwater solids, expired, very faint gas
        tau_c = d["m"] / np.maximum(d["r"], 1) ** 2
        alive = (d["age"] < d["life"]) & ~hit & ~((kind < 2) & (tau_c < 6e-5) & (d["temp"] < 0.05))
        # debris trail emitters (the 'octopus' tendrils); every step, thinned at random
        deb = alive & (kind == 2) & (d["pos"][:, 2] > 0) & (rng.random(len(kind)) < 0.25) & (d["age"] < 6)
        idx = np.nonzero(deb)[0]
        src = (d["pos"][idx].copy(), d["vel"][idx] * 0.05, d["temp"][idx].copy())
        self.p.keep(alive)
        if len(idx):
            n = len(idx)
            hotdeb = src[2] > 0.05
            self.p.add(pos=src[0], vel=src[1], r=1.5 + 1.0 * rng.random(n),
                       m=np.where(hotdeb, 1.6, 0.8), temp=src[2] * 0.9, heat=0.05, life=1e9, kind=0,
                       tcool=0.35, seed=rng.random(n))
        # fire lights: emission-weighted centroid of hot particles (1 light; GPU: 1-4)
        d = self.p.d
        e = (d["temp"] ** 3) * d["m"] * d["r"] ** 2 * (d["kind"] != 2)
        self.lights = []
        if e.sum() > 1e-3:
            c = (d["pos"] * e[:, None]).sum(0) / e.sum()
            self.lights = [(c, float(e.sum()))]
        self.Q = q


# --------------------------------------------------------------- the scene
def ship_mask(X, Y, L=230.0, B=31.0, x0=0.0, y0=0.0, gap=None):
    xs = (X - x0) / (L / 2)
    half = B / 2 * np.where(xs > 0.55, np.sqrt(np.clip((1 - xs) / 0.45, 0, 1)), 1.0)
    half = np.where(xs < -0.85, half * np.sqrt(np.clip((xs + 1) / 0.15, 0, 1)) * 0.6 + half * 0.4, half)
    m = (np.abs(xs) <= 1) & (np.abs(Y - y0) <= half)
    if gap is not None:
        m &= ~((X > gap[0]) & (X < gap[1]))
    return m


def render(events, t, view=(-420, 480, -340, 340), px=1.25, proj="oblique", k_obl=0.6, H_cam=900.0,
           H_comp=450.0, cam_fade=None,
           sun_el=35, sun_az=220, night=False, ship=None, seed=0):
    global NOISE
    if NOISE is None:
        NOISE = _fbm()
    x0, x1, y0, y1 = view
    xs = np.arange(x0, x1, px); ys = np.arange(y1, y0, -px)
    X, Y = np.meshgrid(xs, ys)
    H, W = X.shape
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rng = np.random.default_rng(seed)
    sa, se = np.radians(sun_az), np.radians(sun_el)
    sun = np.array([np.cos(se) * np.cos(sa), np.cos(se) * np.sin(sa), np.sin(se)])

    # --- coarse density grid for self-shadow and ground shadow (GPU: 3D RT, 16-24 m voxels)
    vx = 16.0
    gx = np.arange(x0 - 300, x1 + 300, vx); gy = np.arange(y0 - 300, y1 + 300, vx); gz = np.arange(0, 1800, vx)
    rho = np.zeros((len(gz), len(gy), len(gx)))
    parts = [ev for ev in events if len(ev.p)]
    for ev in parts:
        d = ev.p.d
        gas = d["kind"] < 2
        ix = np.clip(((d["pos"][:, 0] - gx[0]) / vx).astype(int), 0, len(gx) - 1)
        iy = np.clip(((d["pos"][:, 1] - gy[0]) / vx).astype(int), 0, len(gy) - 1)
        iz = np.clip((d["pos"][:, 2] / vx).astype(int), 0, len(gz) - 1)
        # extinction ~ particle mass (soot); hot gas is thinner
        np.add.at(rho, (iz[gas], iy[gas], ix[gas]), (d["m"] * KAPPA / vx ** 2 * 0.06)[gas] * (1 - 0.7 * d["temp"][gas]))
    rho = gaussian_filter(rho, 1.2)
    # optical depth toward the sun, swept from the top with a sub-voxel shift per layer
    tau = np.zeros_like(rho)
    shx, shy = sun[0] / sun[2], sun[1] / sun[2]
    acc = np.zeros(rho.shape[1:])
    for k in range(len(gz) - 1, -1, -1):
        tau[k] = acc
        acc = nd_shift(acc + rho[k] * vx / sun[2], (-shy, -shx), order=1, mode="constant")
    ground_tau = acc

    def sample(grid2_or_3, Xw, Yw, Zw=None):
        cj = (Xw - gx[0]) / vx; ci = (Yw - gy[0]) / vx
        if Zw is None:
            return map_coordinates(grid2_or_3, [ci, cj], order=1, mode="nearest")
        return map_coordinates(grid2_or_3, [Zw / vx, ci, cj], order=1, mode="nearest")

    # --- water
    nz = gaussian_filter(rng.standard_normal((H, W)), (1.2, 3.0)); nz /= nz.std()
    if night:
        water = np.array([0.004, 0.009, 0.022]) + 0.003 * nz[..., None]
        sky_amb, sun_I = np.array([0.015, 0.02, 0.04]), 0.0
    else:
        water = np.array([0.03, 0.09, 0.20]) + 0.012 * nz[..., None]
        sky_amb, sun_I = np.array([0.35, 0.40, 0.48]), 1.0
    col = np.broadcast_to(water, (H, W, 3)).copy()
    shadow = np.exp(-sample(ground_tau, X, Y))
    if not night:
        col *= (0.3 + 0.7 * shadow)[..., None]

    # shock frost ring + scour foam (reuse of the muzzle blast event; lambda from burned mass)
    for ev in events:
        r = np.hypot(X - ev.x, Y - ev.y)
        te = t - getattr(ev, "t_main", 0.0)
        if ev.mode == "blast" and te > 0:
            t_ = t; t = te
            Rf = 345 * t + 2.5 * ev.lam * (1 - np.exp(-t / 0.08))   # supersonic near field, stylised
            s = np.clip(1 - r / (4.0 * ev.lam), 0, 1)
            lead = s * np.exp(-((r - Rf) / 5.0) ** 2)
            frost = s * (r < Rf) * np.exp(-t / 2.0)
            col = col * (1 - 0.45 * lead[..., None]) + 0.05 * frost[..., None] * (0.3 if night else 1)
            foam = np.clip(1.2 - r / (1.0 * ev.lam), 0, 1) ** 1.5 * np.exp(-t / 10) * (t > 0.05)
            t = t_
        else:
            foam = np.zeros_like(r)
        for (sx, sy, ts) in getattr(ev, "splashes", []):
            a = t - ts
            if a >= 0:
                foam = np.maximum(foam, np.exp(-((X - sx) ** 2 + (Y - sy) ** 2) / (2 * (1.5 + 1.0 * a) ** 2)) * np.exp(-a / 6))
        fz = gaussian_filter(rng.random((H, W)), 1.0)
        f = np.clip((foam - (1 - fz) * 0.6) / 0.25, 0, 1)
        col = col * (1 - f[..., None]) + f[..., None] * (0.75 if not night else 0.03)

    # --- ship sprite (flat, at deck height, drawn without lean for simplicity)
    shipm = ship_mask(X, Y, **ship) if ship is not None else np.zeros((H, W), bool)
    if ship is not None:
        deck = np.array([0.38, 0.39, 0.41]) if not night else np.array([0.02, 0.02, 0.024])
        # turrets / superstructure blocks for readability
        xs_ = (X - ship["x0"]) / (ship["L"] / 2)
        blocks = shipm & (np.abs(Y - ship["y0"]) < 6) & (((np.abs(xs_ - 0.55) < 0.05) | (np.abs(xs_ - 0.40) < 0.05) |
                                                         (np.abs(xs_ + 0.45) < 0.05) | (np.abs(xs_ + 0.60) < 0.05)))
        sup = shipm & (np.abs(Y - ship["y0"]) < 8) & (xs_ > -0.3) & (xs_ < 0.28)
        base = np.where(shipm[..., None], deck, col)
        base = np.where(sup[..., None], deck * 1.25, base)
        base = np.where(blocks[..., None], deck * 0.8, base)
        col = np.where(shipm[..., None], base * ((0.5 + 0.5 * shadow)[..., None] if not night else 1), col)
        for ev in events:   # scorch
            sc = np.exp(-((X - ev.x) ** 2 + (Y - ev.y) ** 2) / (2 * 20 ** 2)) * shipm * min(1, t / 0.3)
            col *= (1 - 0.85 * sc[..., None])

    # --- fire light on water + ship: point lights; diffuse + glint toward the camera
    fc = blackbody(np.array(0.55))
    for ev in events:
        for (c, I) in ev.lights:
            In = I / I_REF
            Lz = max(c[2], 8.0)
            d2 = (X - c[0]) ** 2 + (Y - c[1]) ** 2 + Lz ** 2
            irr = In * (Lz ** 2 / d2) ** 1.5 * (Lz / 60.0) ** -0.5
            col += irr[..., None] * fc * (0.25 if not night else 0.3) * np.where(shipm, 1.5, 1.0)[..., None]
            if proj == "oblique":   # mirror image of the light hangs below its base on screen
                zc = H_comp * (1 - np.exp(-Lz / H_comp))
                gx_, gy_ = c[0], c[1] - 0.5 * zc * k_obl
                ax = np.array([0.0, -1.0])
            else:
                gx_ = c[0] + (cx - c[0]) * Lz / (Lz + H_cam); gy_ = c[1] + (cy - c[1]) * Lz / (Lz + H_cam)
                ax = np.array([cx - gx_, cy - gy_]); ax = ax / (np.linalg.norm(ax) + 1e-6)
            dx, dy = X - gx_, Y - gy_
            along, across = dx * ax[0] + dy * ax[1], -dx * ax[1] + dy * ax[0]
            g = np.exp(-(along / (0.5 * Lz + 15)) ** 2 - (across / (0.1 * Lz + 6)) ** 2)
            g *= np.clip(nz - 0.3, 0, 3) * ~shipm
            col += g[..., None] * fc * min(In, 1.5) * (0.35 if not night else 0.8)

    # --- particles: project with lean, sort by height (low first), splat 'over'
    if parts:
        P = np.concatenate([np.c_[ev.p.d["pos"], ev.p.d["r"], ev.p.d["m"], ev.p.d["temp"],
                                  ev.p.d["kind"], ev.p.d["seed"]] for ev in parts])
        P = P[np.argsort(P[:, 2])]
        # sample at the sun-facing surface of each puff; 0.3 = multiple-scattering softening
        Ps = P[:, :3] + sun[None] * P[:, 3:4] * 0.8
        Tsun = np.exp(-0.3 * sample(tau, Ps[:, 0], Ps[:, 1], np.clip(Ps[:, 2], 0, None)))
        firelit = np.zeros(len(P))
        for ev in events:
            for (c, I) in ev.lights:
                firelit += min(I / I_REF, 3.0) * 60.0 ** 2 / (((P[:, :3] - c) ** 2).sum(1) + 30.0 ** 2)
        firelit = 1 - np.exp(-0.35 * firelit)
        sun_xy = sun[:2] / (np.linalg.norm(sun[:2]) + 1e-9)
        for n_, (x, y, z, r, m, T, kind, sd) in enumerate(P):
            if z < -1:
                continue
            ze = H_comp * (1 - np.exp(-z / H_comp))            # height compression
            if proj == "oblique":                               # height -> screen-up (3/4 view for VFX)
                k = 1.0; sxp = x; syp = y + k_obl * ze
            else:                                               # true top-down perspective (radial lean)
                k = H_cam / (H_cam - ze)
                sxp = cx + (x - cx) * k; syp = cy + (y - cy) * k
            j0, i0 = (sxp - x0) / px, (y1 - syp) / px
            rp = max(r * k / px, 0.7)
            R = int(2.0 * rp) + 1
            ja, jb = int(max(j0 - R, 0)), int(min(j0 + R + 1, W))
            ia, ib = int(max(i0 - R, 0)), int(min(i0 + R + 1, H))
            if ja >= jb or ia >= ib:
                continue
            jj, ii = np.meshgrid(np.arange(ja, jb), np.arange(ia, ib))
            ux, uy = (jj - j0) / rp, -(ii - i0) / rp
            q2 = ux ** 2 + uy ** 2
            ang = np.arctan2(uy, ux)
            edge = 1 + 0.16 * np.sin(5 * ang + sd * 20) + 0.09 * np.sin(11 * ang + sd * 50)   # flipbook stand-in
            nzt = NOISE[((ii - i0) * 1.3 / max(rp, 1) * 40 + sd * 997).astype(int) % 256,
                        ((jj - j0) * 1.3 / max(rp, 1) * 40 + sd * 613).astype(int) % 256]
            nzt = np.clip((nzt - 0.25) / 0.5, 0, 1); nzt = nzt * nzt * (3 - 2 * nzt)
            # world-anchored billow noise: coherent across overlapping puffs (cauliflower read)
            wx = (sxp - x0 + (jj - j0) * px) / 2.5; wy = (y1 - syp + (ii - i0) * px) / 2.5 + t * 1.5
            wn = NOISE[wy.astype(int) % 256, wx.astype(int) % 256]
            wn = np.clip((wn - 0.3) / 0.4, 0, 1)
            prof = np.exp(-(q2 / edge ** 2) ** 1.5 * 1.8) * (0.25 + 0.6 * nzt + 0.6 * wn)
            if cam_fade if cam_fade is not None else proj != "oblique":   # thin out smoke close to the camera so the ship stays readable
                prof = prof * np.clip((0.8 * H_cam - z) / (0.4 * H_cam), 0.15, 1)
            idx = (slice(ia, ib), slice(ja, jb))
            if kind == 2:   # debris: small dark solid, glowing while hot
                a = np.clip(prof * 1.6, 0, 0.95)
                c_ = np.array([0.04, 0.035, 0.03]) + T * blackbody(np.array(0.8)) * 2
                col[idx] = col[idx] * (1 - a[..., None]) + a[..., None] * c_
                continue
            if kind == 3:   # spark: additive
                col[idx] += prof[..., None] * blackbody(np.array(T * 0.8 + 0.2)) * 1.5
                continue
            dens = m * KAPPA / max(r, 1.0) ** 2
            a = 1 - np.exp(-prof * dens * (1 - 0.45 * T))
            alb = np.array([0.80, 0.80, 0.82]) if kind == 1 else np.array([0.075, 0.064, 0.056])
            # sphere-normal shading (what 6-way lightmaps give a flipbook): lit side faces the sun
            nzs = np.sqrt(np.clip(1 - q2 * 0.5, 0, 1))
            lam_ = np.clip(0.2 + 0.95 * ((ux * sun_xy[0] + uy * sun_xy[1]) * 0.7 * np.cos(np.radians(sun_el)) + nzs * sun[2]), 0, 1)
            lit = alb * (sky_amb[None, None] * 0.5 * (0.5 + wn[..., None]) + sun_I * 2.2 * Tsun[n_] * (lam_ * (0.45 + 0.8 * wn))[..., None])
            lit = lit + firelit[n_] * blackbody(np.array(0.42)) * (0.55 if not night else 0.9) * (1 - 0.5 * nzs[..., None])
            Tp = np.clip(T * (0.35 + 0.45 * nzt + 0.9 * (1 - wn) ** 2), 0, 1)   # soot skin where wn high              # hot folds vs sooty skin
            emis = blackbody(Tp) * (Tp ** 2.0)[..., None] * 3.2
            c_ = lit + emis
            col[idx] = col[idx] * (1 - a[..., None]) + a[..., None] * c_

    # --- bloom + tonemap
    bright = np.clip(col - 1.0, 0, None)
    col = col + gaussian_filter(bright, (6, 6, 0)) * 0.6 + gaussian_filter(bright, (24, 24, 0)) * 0.35
    col = col * 1.15 / (1 + col * 0.65)
    col = np.clip(col, 0, 1) ** (1 / 2.2)
    return (col * 255).astype(np.uint8)


def run(event_factory, times, dt=0.05, **rkw):
    ev = event_factory()
    frames, t = [], 0.0
    for T in times:
        while t < T - 1e-9:
            ev.step(dt); t += dt
        frames.append((T, render([ev], t, **rkw)))
    return frames


if __name__ == "__main__":
    import sys, time
    from PIL import Image, ImageDraw
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    ship = dict(L=230.0, B=31.0, x0=-150.0, y0=-90.0)
    mag_x = ship["x0"] - 0.27 * ship["L"]            # aft group ~0.77 L from the bow
    broken = dict(ship, gap=(mag_x - 25, mag_x + 25))
    blast = lambda: MagazineEvent(mag_x, ship["y0"], "blast", 20000.0, seed=5,
                                  vents=[(ship["x0"] - 20, ship["y0"], 0.4, 1.0)])   # Hood: mainmast vent
    column = lambda: MagazineEvent(ship["x0"] + 10, ship["y0"], "column", 2000.0, duration=14.0, seed=2)
    zoomv = dict(view=(-330, 30, -200, 70), px=0.5)
    t0 = time.time()
    sets = {
        "column": run(column, [0.5, 2.0, 5.0, 9.0, 14.0], ship=ship, **zoomv) if "column" in sys.argv else None,
        "column_night": run(column, [2.0, 5.0, 9.0], ship=ship, night=True, **zoomv) if "column" in sys.argv else None,
        "blast_day": run(blast, [0.3, 1.5, 4.0, 8.0, 15.0, 30.0], ship=broken),
        "blast_night": run(blast, [0.3, 1.5, 4.0, 8.0, 15.0], ship=broken, night=True),
        "proj_top": run(blast, [10.0], ship=broken, proj="top"),
        "proj_obl": run(blast, [10.0], ship=broken, proj="oblique"),
    }
    print("render time %.0f s" % (time.time() - t0))

    def strip(frames, name, label, sc=0.5):
        h, w = frames[0][1].shape[:2]
        W_, H_ = int(w * sc), int(h * sc)
        im = Image.new("RGB", (W_ * len(frames), H_ + 20), (18, 18, 18))
        dr = ImageDraw.Draw(im)
        for i, (T, f) in enumerate(frames):
            im.paste(Image.fromarray(f).resize((W_, H_), Image.LANCZOS), (i * W_, 20))
            dr.text((i * W_ + 6, 4), f"{label}  t = {T:g} s", fill=(230, 230, 230))
        im.save(f"{out}/{name}")
    if sets["column"]:
        strip(sets["column"], "magx_strip_column.png", "tier 1 flame column")
        strip(sets["column_night"], "magx_strip_column_night.png", "tier 1 night", sc=0.6)
    strip(sets["blast_day"], "magx_strip_blast_day.png", "tier 3 blast")
    strip(sets["blast_night"], "magx_strip_blast_night.png", "tier 3 night")
    strip(sets["proj_top"] + sets["proj_obl"], "magx_projection_compare.png", "top-down | oblique", sc=0.8)
    for k, v in sets.items():
        if v:
            np.save(f"{out}/{k}.npy", np.stack([f for _, f in v]))