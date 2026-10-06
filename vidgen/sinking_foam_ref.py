"""Sinking-ship surface VFX: reference prototype (numpy).

Companion to wake_bake_ref_v2.py / wake_turn_ref.py / muzzle_blast_ref.py.
Top-down, stylised. The ship is a 3D rigid body (pose from the damage/buoyancy model); the surface
effects are derived from how that 3D hull crosses the plane z = 0. Nothing is hand-placed per
scenario except the pose keyframes, which in game come from the flooding model.

Layers produced (all world-space, the sinking ship is ~stationary so a local world canvas works):
  1. crossing foam   : hull surface points that cross z=0 between steps deposit foam where they cross.
                       Going down = water pouring over the deck/edge (white, rate ~ |vz|),
                       going up   = water cascading off a rising end (weaker).
                       -> the white line sweeps along the deck exactly as the ship goes under.
  2. contact ring    : a thin band around the current waterline cut (where the hull pierces the
                       surface), brighter where the hull moves vertically fast (plunge).
  3. air boils       : compartment air displaced by water. Released as boil events at the surface
                       above the compartment's highest point once that point is submerged; a share is
                       trapped and burps up after the ship is gone, from ever deeper -> later, bigger,
                       fainter boils (plume spread ~0.1*depth, rise ~2 m/s).
  4. closure         : when the last part goes under: big boil + radial ring wave (eta, lighting).
  5. oil             : leak puddles, Fay gravity-inertial spreading, Bonn appearance codes for colour,
                       damps ripples (slick).
  6. debris          : floating points released from the submerging deck, pushed by boils, drift.
Sprite handling: hull parts above water drawn lit, parts below water tinted by depth (visible to a few
metres), drop shadow of raised parts (stern rising) onto the water: the key height cue top-down.
"""
import os
import time
import numpy as np
from scipy.ndimage import gaussian_filter, distance_transform_edt, maximum_filter, binary_erosion

G = 9.81
RNG = np.random.default_rng(7)


def smooth(a, lo, hi):
    t = np.clip((np.asarray(a, dtype=np.float64) - lo) / (hi - lo), 0, 1)
    return t * t * (3 - 2 * t)


# --------------------------------------------------------------------------------------------
# Hull description (same planform law as the wake bake) + a little sprite decor with heights
# --------------------------------------------------------------------------------------------
class Hull:
    def __init__(self, name, L, B, T, F, n_fore=1.7, n_aft=5.0, deck_col=(0.52, 0.55, 0.58),
                 turrets=(), supers=(), funnels=(), fuel_m3=500.0):
        self.name, self.L, self.B, self.T, self.F = name, L, B, T, F
        self.n_fore, self.n_aft, self.deck_col = n_fore, n_aft, np.array(deck_col)
        self.turrets, self.supers, self.funnels = turrets, supers, funnels
        self.fuel_m3 = fuel_m3

    def hb(self, x):
        xi = 2 * np.asarray(x) / self.L
        n = np.where(xi > 0, self.n_fore, self.n_aft)
        h = 0.5 * self.B * np.clip(1 - np.abs(xi) ** n, 0, None)
        return np.where(np.abs(xi) <= 1, h, 0.0)


def hull_samples(h: Hull, hs, cuts=()):
    """Surface point cloud in ship coords (x fwd, y port, zeta up from waterline).
    Returns dict of arrays: P (n,3), N (n,3), C (n,3), kind (0 deck/top, 1 side, 2 bottom, 3 cut face)."""
    L, B, T, F = h.L, h.B, h.T, h.F
    P, N, C, K = [], [], [], []
    xs = np.arange(-L / 2, L / 2, hs) + hs / 2
    ys = np.arange(-B / 2, B / 2, hs) + hs / 2
    X, Y = np.meshgrid(xs, ys)
    inside = np.abs(Y) < h.hb(X)
    x, y = X[inside], Y[inside]
    # deck colour with decor painted on (decor gets its own raised samples below)
    col = np.tile(h.deck_col, (len(x), 1))
    # a darker centreline-ish shading band for readability
    col *= (1 - 0.06 * np.exp(-(y / (0.12 * B)) ** 2))[:, None]
    P.append(np.c_[x, y, np.full_like(x, F)]); N.append(np.tile([0, 0, 1.0], (len(x), 1))); C.append(col); K.append(np.zeros(len(x)))
    P.append(np.c_[x, y, np.full_like(x, -T)]); N.append(np.tile([0, 0, -1.0], (len(x), 1)))
    C.append(np.tile([0.50, 0.20, 0.16], (len(x), 1))); K.append(np.full(len(x), 2))
    # sides
    zs = np.arange(-T, F, hs) + hs / 2
    XS, ZS = np.meshgrid(xs, zs)
    hbx = h.hb(XS)
    dhb = np.gradient(h.hb(xs), hs)[None, :] * np.ones_like(XS)
    ok = hbx > 0.02
    for sgn in (1, -1):
        x, zz, yy, d = XS[ok], ZS[ok], sgn * hbx[ok], dhb[ok]
        n = np.c_[-d * 0 - d, np.full_like(x, sgn), np.zeros_like(x)]
        n[:, 0] = -d  # outward normal ~ (-dhb/dx, sgn, 0)
        n /= np.linalg.norm(n, axis=1, keepdims=True)
        c = np.where((zz > 0.6)[:, None], [0.47, 0.50, 0.54], np.where((zz > -0.4)[:, None], [0.12, 0.12, 0.13], [0.50, 0.20, 0.16]))
        P.append(np.c_[x, yy, zz]); N.append(n); C.append(c); K.append(np.ones(len(x)))
    # cut faces (break-in-two): both sides of the cut, dark torn interior
    for xc in cuts:
        yy, zz = np.meshgrid(ys, zs)
        ok = np.abs(yy) < h.hb(xc)
        for sgn in (1, -1):
            n_ = len(yy[ok])
            shade = 0.16 + 0.10 * RNG.random(n_)
            P.append(np.c_[np.full(n_, xc + sgn * 1e-3), yy[ok], zz[ok]])
            N.append(np.tile([sgn, 0, 0.0], (n_, 1))); C.append(np.c_[shade * 1.2, shade, shade * 0.9]); K.append(np.full(n_, 3))
    # raised decor: tops only (top-down sprite layers), at deck + height
    def disc(xc, r, top, colr, cap=None):
        xx, yy = np.meshgrid(np.arange(xc - r, xc + r, hs), np.arange(-r, r, hs))
        m = (xx - xc) ** 2 + yy ** 2 < r * r
        cc = np.tile(colr, (m.sum(), 1))
        if cap is not None:
            cc[((xx - xc) ** 2 + yy ** 2)[m] < (0.75 * r) ** 2] = cap
        P.append(np.c_[xx[m], yy[m], np.full(m.sum(), top)]); N.append(np.tile([0, 0, 1.0], (m.sum(), 1)))
        C.append(cc); K.append(np.zeros(m.sum()))
    for (x0, x1, hw, hgt, colr) in h.supers:
        xx, yy = np.meshgrid(np.arange(x0, x1, hs), np.arange(-hw, hw, hs))
        m = np.abs(yy) < np.minimum(hw, h.hb(xx) * 0.9)
        P.append(np.c_[xx[m], yy[m], np.full(m.sum(), F + hgt)]); N.append(np.tile([0, 0, 1.0], (m.sum(), 1)))
        C.append(np.tile(colr, (m.sum(), 1))); K.append(np.zeros(m.sum()))
    for (xc, r) in h.turrets:
        disc(xc, r, F + 2.5, [0.40, 0.43, 0.47])
        # barrel(s): thin strip forward/aft depending on side
        sgn = 1 if xc > 0 else -1
        xx, yy = np.meshgrid(np.arange(0, 1.9 * r, hs), np.arange(-0.12 * r, 0.12 * r, hs))
        P.append(np.c_[xc + sgn * (xx.ravel() + 0.6 * r), yy.ravel(), np.full(xx.size, F + 2.6)])
        N.append(np.tile([0, 0, 1.0], (xx.size, 1))); C.append(np.tile([0.30, 0.32, 0.35], (xx.size, 1))); K.append(np.zeros(xx.size))
    for (xc, r, hgt) in h.funnels:
        disc(xc, r, F + hgt, [0.42, 0.44, 0.46], cap=[0.08, 0.08, 0.09])
    out = dict(P=np.vstack(P).astype(np.float64), N=np.vstack(N), C=np.vstack(C), kind=np.concatenate(K).astype(np.int8))
    return out


def volume_samples(h: Hull, n_comp):
    """Coarse interior points with compartment ids (for 'air out = water in')."""
    hx, hy, hz = h.L / 70, h.B / 8, (h.T + h.F) / 6
    xs = np.arange(-h.L / 2, h.L / 2, hx) + hx / 2
    ys = np.arange(-h.B / 2, h.B / 2, hy) + hy / 2
    zs = np.arange(-h.T, h.F, hz) + hz / 2
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    m = np.abs(Y) < h.hb(X)
    P = np.c_[X[m], Y[m], Z[m]]
    comp = np.clip(((P[:, 0] + h.L / 2) / h.L * n_comp).astype(int), 0, n_comp - 1)
    return P, comp, hx * hy * hz


# --------------------------------------------------------------------------------------------
# Pose: rotation about a pivot on the waterline (roll about x, then pitch about y), then sinkage
# --------------------------------------------------------------------------------------------
def transform(P, pose, N=None):
    px, s, th, ph = pose
    x = P[:, 0] - px
    y, z = P[:, 1], P[:, 2]
    c, sn = np.cos(ph), np.sin(ph)
    y1, z1 = y * c - z * sn, y * sn + z * c
    ct, st = np.cos(th), np.sin(th)
    x2, z2 = x * ct - z1 * st, x * st + z1 * ct
    out = (px + x2, y1, z2 - s)
    if N is None:
        return out
    nx, ny, nz = N[:, 0], N[:, 1] * c - N[:, 2] * sn, N[:, 1] * sn + N[:, 2] * c
    return out, (nx * ct - nz * st, ny, nx * st + nz * ct)


class Keyframes:
    """(t, sinkage m, pitch deg [+ = bow up], roll deg [+ = rolls to starboard/-y]); smooth interp,
    after the last key the wreck keeps descending at v_desc with the last attitude."""

    def __init__(self, keys, pivot, v_desc=8.0):
        self.k = np.array(keys, float)
        self.pivot, self.v_desc = pivot, v_desc

    def __call__(self, t):
        k = self.k
        if t >= k[-1, 0]:
            s = k[-1, 1] + self.v_desc * (t - k[-1, 0])
            return (self.pivot, s, np.radians(k[-1, 2]), np.radians(k[-1, 3]))
        i = max(np.searchsorted(k[:, 0], t) - 1, 0)
        u = smooth((t - k[i, 0]) / (k[i + 1, 0] - k[i, 0]), 0, 1)
        # monotone-ish blend: smoothstep per segment is enough for a prototype (C1 at keys)
        v = k[i, 1:] + (k[i + 1, 1:] - k[i, 1:]) * u
        return (self.pivot, v[0], np.radians(v[1]), np.radians(v[2]))


# --------------------------------------------------------------------------------------------
# Noise (world-space, fixed) for foam breakup and water texture
# --------------------------------------------------------------------------------------------
def uniform_noise(shape, sigmas, weights, seed):
    r = np.random.default_rng(seed)
    f = sum(w * gaussian_filter(r.standard_normal(shape), s, mode="wrap") / s ** -1 for s, w in zip(sigmas, weights))
    # rank-uniformise -> [0,1] uniform, which makes the threshold breakup behave predictably
    flat = f.ravel()
    out = np.empty_like(flat)
    out[np.argsort(flat)] = np.linspace(0, 1, flat.size)
    return out.reshape(shape)


# --------------------------------------------------------------------------------------------
# Simulation
# --------------------------------------------------------------------------------------------
class SinkSim:
    def __init__(self, hull, segments, *, dx, extent, n_comp=10, p_trap=0.35, p_hold=0.5, leaks=(), t_end=120,
                 drift=(0.12, 0.04), sun=(-0.55, 0.45), sun_elev=50.0, oil_time_scale=1.5, events=()):
        self.h, self.dx = hull, dx
        x0, x1, y0, y1 = extent
        self.nx, self.ny = int((x1 - x0) / dx), int((y1 - y0) / dx)
        self.x0, self.y0 = x0, y0
        self.xc = x0 + dx * (np.arange(self.nx) + 0.5)
        self.yc = y0 + dx * (np.arange(self.ny) + 0.5)
        self.XX, self.YY = np.meshgrid(self.xc, self.yc)
        cuts = [s["x_range"][0] for s in segments if s["x_range"][0] > -hull.L / 2 + 1e-6]
        S = hull_samples(hull, hs=dx * 0.5, cuts=cuts)
        self.S = S
        self.seg_of = np.full(len(S["P"]), -1)
        for i, sg in enumerate(segments):
            a, b = sg["x_range"]
            m = (S["P"][:, 0] >= a - 2e-3) & (S["P"][:, 0] <= b + 2e-3)
            if i > 0:  # cut face belongs to the side it faces
                pass
            self.seg_of[m & (self.seg_of < 0)] = i
        # cut faces: assign by normal direction
        cutm = S["kind"] == 3
        for i, sg in enumerate(segments):
            a, b = sg["x_range"]
            self.seg_of[cutm & (np.abs(S["P"][:, 0] - a) < 0.01) & (S["N"][:, 0] < 0)] = i
            self.seg_of[cutm & (np.abs(S["P"][:, 0] - b) < 0.01) & (S["N"][:, 0] > 0)] = i
        self.segments = segments
        V, comp, dv = volume_samples(hull, n_comp)
        self.V, self.dv = V, dv
        self.vseg = np.zeros(len(V), int)
        for i, sg in enumerate(segments):
            a, b = sg["x_range"]
            self.vseg[(V[:, 0] >= a) & (V[:, 0] < b)] = i
        self.comp = comp + n_comp * self.vseg   # compartments don't span the break
        self.ncomp = n_comp * len(segments)
        self.comp_vol = np.bincount(self.comp, minlength=self.ncomp) * dv
        self.comp_acc = np.zeros(self.ncomp)
        self.comp_held = np.zeros(self.ncomp)   # air held behind closed hatches until the vent submerges
        self.p_hold = p_hold
        self.comp_f = np.zeros(self.ncomp)       # initial draft is not 'flooding': start from t=0 state
        for i, pose in enumerate([sg["pose"](0.0) for sg in segments]):
            m = self.vseg == i
            _, _, vz0 = transform(V[m], pose)
            f = np.bincount(self.comp[m], weights=(vz0 < 0).astype(float), minlength=self.ncomp)
            n = np.bincount(self.comp[m], minlength=self.ncomp)
            self.comp_f = np.where(n > 0, f / np.maximum(n, 1), self.comp_f)
        # deck points per compartment = vents (highest one is used)
        deck = S["kind"] == 0
        dcomp = np.clip(((S["P"][:, 0] + hull.L / 2) / hull.L * n_comp).astype(int), 0, n_comp - 1) + n_comp * np.maximum(self.seg_of, 0)
        self.vent_idx = [np.where(deck & (dcomp == c))[0] for c in range(self.ncomp)]
        self.p_trap, self.trapped = p_trap, np.zeros(len(segments))
        self.gone = [None] * len(segments)
        self.last_area = np.zeros(len(segments))
        self.last_xy = np.zeros((len(segments), 2))
        # fields
        self.fresh = np.zeros((self.ny, self.nx), np.float32)
        self.resid = np.zeros((self.ny, self.nx), np.float32)
        self.boils = []        # dict(t, x, y, S, I)
        self.rings = []        # dict(t, x, y, A)
        self.puddles = []      # (t, x, y, V)
        self.debris = np.zeros((0, 2))
        self.leaks = list(leaks)
        self.drift = np.array(drift)
        self.sun = np.array(sun) / np.linalg.norm(sun)
        self.sun_elev = np.radians(sun_elev)
        self.oil_ts = oil_time_scale
        self.t, self.Zprev = 0.0, None
        self.t_end = t_end
        self.noise_f = uniform_noise((self.ny, self.nx), [1.2 / dx, 3.5 / dx], [1.0, 0.7], 1)
        self.noise_w = uniform_noise((self.ny, self.nx), [0.7 / dx, 2.5 / dx], [1.0, 0.6], 2)
        self.scripted = sorted(events, key=lambda e: e["t"])
        self.timing = dict(step=0.0, render=0.0, n_steps=0)

    # ---- helpers --------------------------------------------------------------------------
    def poses(self, t):
        return [sg["pose"](t) for sg in self.segments]

    def world(self, t, with_normals=False):
        P = self.S["P"]
        X, Y, Z = (np.empty(len(P)) for _ in range(3))
        NX, NY, NZ = (np.empty(len(P)) for _ in range(3))
        for i, pose in enumerate(self.poses(t)):
            m = self.seg_of == i
            if with_normals:
                (x, y, z), (a, b, c) = transform(P[m], pose, self.S["N"][m])
                NX[m], NY[m], NZ[m] = a, b, c
            else:
                x, y, z = transform(P[m], pose)
            X[m], Y[m], Z[m] = x, y, z
        return (X, Y, Z, NX, NY, NZ) if with_normals else (X, Y, Z)

    def to_ij(self, X, Y):
        ix = ((X - self.x0) / self.dx).astype(int)
        iy = ((Y - self.y0) / self.dx).astype(int)
        ok = (ix >= 0) & (ix < self.nx) & (iy >= 0) & (iy < self.ny)
        return ix, iy, ok

    def splat(self, X, Y, w):
        ix, iy, ok = self.to_ij(X, Y)
        f = np.bincount(iy[ok] * self.nx + ix[ok], weights=w[ok], minlength=self.ny * self.nx)
        return f.reshape(self.ny, self.nx)

    def add_boil(self, t_surface, x, y, S, I):
        self.boils.append(dict(t=t_surface, x=x, y=y, S=S, I=I))

    # ---- one simulation step --------------------------------------------------------------
    def step(self, dt):
        t0 = time.perf_counter()
        t = self.t + dt
        X, Y, Z = self.world(t)
        if self.Zprev is None:
            self.Zprev = Z.copy()
        vz = (Z - self.Zprev) / dt
        dens = (0.5 * self.dx) ** 2 / self.dx ** 2     # one sample covers 1/4 px
        # 1. crossing foam
        down = (self.Zprev > 0) & (Z <= 0)
        up = (self.Zprev < 0) & (Z >= 0)
        w = np.zeros_like(Z)
        w[down] = 0.25 + 0.75 * smooth(-vz[down], 0.03, 0.8)
        w[up] = 0.55 * smooth(vz[up], 0.05, 1.0)
        src = np.minimum(self.splat(X, Y, w) * dens * 3.0, 0.8)
        # 2. contact ring around the current waterline cut, brighter where the hull moves vertically
        # waterline cut = columns that contain hull surface both above and below z=0
        Wc = (self.splat(X, Y, (Z > 0).astype(float)) > 0) & (self.splat(X, Y, (Z < 0).astype(float)) > 0)
        Wc = binary_erosion(maximum_filter(Wc, 3), iterations=1) | Wc     # close sampling pinholes
        near = np.abs(Z) < 1.5
        agit = self.splat(X[near], Y[near], np.abs(vz[near]))
        cnt = self.splat(X[near], Y[near], np.ones(near.sum()))
        agit = maximum_filter(agit / np.maximum(cnt, 1), size=int(4 / self.dx) | 1)
        if Wc.any():
            d = distance_transform_edt(~Wc) * self.dx
            ring = np.exp(-(d / 1.3) ** 2) * (~Wc)
            src += ring * (0.18 + 0.82 * smooth(agit, 0.05, 1.2))
        src = np.clip(gaussian_filter(src, 0.5 / self.dx), 0, 1).astype(np.float32)
        tau_f, tau_r = 3.0, 25.0
        df, dr = np.exp(-dt / tau_f), np.exp(-dt / tau_r)
        self.resid = self.resid * dr + 0.5 * self.fresh * (1 - df)
        self.fresh = np.maximum(self.fresh * df, src)
        if int(round(t / dt)) % 10 == 0:          # slow lateral spreading of residual foam
            self.resid = gaussian_filter(self.resid, 0.35 / self.dx)
        # debris released where the deck goes under
        deckdown = down & (self.S["kind"] == 0)
        if deckdown.any():
            pick = deckdown & (RNG.random(len(Z)) < 0.0012)
            if pick.any():
                self.debris = np.vstack([self.debris, np.c_[X[pick], Y[pick]]])
        # 3. air: water in = air out, per compartment
        for i, pose in enumerate(self.poses(t)):
            m = self.vseg == i
            vx, vy, vzz = transform(self.V[m], pose)
            sub = (vzz < 0).astype(float)
            f = np.bincount(self.comp[m], weights=sub, minlength=self.ncomp)
            n = np.bincount(self.comp[m], minlength=self.ncomp)
            f = np.where(n > 0, f / np.maximum(n, 1), self.comp_f)
            dV = np.maximum(f - self.comp_f, 0) * self.comp_vol
            dV[n == 0] = 0
            self.comp_f = np.where(n > 0, f, self.comp_f)
            for c in np.nonzero((dV > 0) | (self.comp_held > 0.5))[0]:
                if not m.any() or n[c] == 0:
                    continue
                vi = self.vent_idx[c]
                if len(vi) == 0:
                    continue
                k = vi[np.argmax(Z[vi])]
                if Z[k] >= 0:
                    # vent above water: most air escapes to the atmosphere, a share is held below
                    self.comp_held[c] += self.p_hold * dV[c]
                    continue
                rel = dV[c] + self.comp_held[c] * min(1.0, dt / 3.0)
                self.comp_held[c] -= self.comp_held[c] * min(1.0, dt / 3.0)
                self.trapped[i] += self.p_trap * rel
                self.comp_acc[c] += (1 - self.p_trap) * rel
                q = max(15.0, self.comp_vol[c] / 25)
                while self.comp_acc[c] > q:
                    Vr = q * (0.6 + 0.8 * RNG.random())
                    self.comp_acc[c] -= Vr
                    depth = -Z[k]
                    jx, jy = RNG.normal(0, 0.25 * self.h.B, 2)   # several openings per compartment
                    S_ = 0.9 * Vr ** (1 / 3) + 0.10 * depth
                    self.add_boil(t + depth / 2.0, X[k] + jx, Y[k] + jy, S_, float(np.clip(1.15 - 0.008 * depth, 0.35, 1.0)))
            # gone? (no part of this segment above water)
            segm = self.seg_of == i
            above = segm & (Z > 0)
            if self.gone[i] is None:
                if above.any():
                    self.last_area[i] = max(self.last_area[i] * 0.0, above.sum() * (0.5 * self.dx) ** 2 * 0.5)
                    self.last_xy[i] = X[above].mean(), Y[above].mean()
                elif t > 1.0:
                    self.gone[i] = t
                    cx, cy = self.last_xy[i]
                    S_ = 3.0 + 0.9 * np.sqrt(max(self.last_area[i], 1.0))
                    self.add_boil(t + 0.3, cx, cy, S_, 1.0)            # closure slam
                    self.rings.append(dict(t=t, x=cx, y=cy, A=0.6 + 0.02 * S_))
                    # tanks rupture as the hull goes under: one big oil release
                    self.puddles.append((t + 2.0, cx, cy, 0.01 * self.h.fuel_m3 / len(self.segments)))
                    rel = RNG.random((25, 2)) - 0.5
                    self.debris = np.vstack([self.debris, np.c_[cx + rel[:, 0] * 0.3 * self.h.L, cy + rel[:, 1] * 0.15 * self.h.L]])
            # trapped air burps: slowly while afloat (bulkheads failing), faster once under
            rate = (1 / 40.0 if self.gone[i] is None else 1 / 14.0)
            if self.trapped[i] > 1 and RNG.random() < dt * 3.0:     # ~3 burps/s at most, sized by pool
                top = np.argmax(np.where(segm, Z, -1e9))
                depth = max(-Z[top], 0.0)
                if depth > 2.0 and depth < 200:
                    Vr = self.trapped[i] * rate / 3.0 * (0.3 + 1.4 * RNG.random())
                    if RNG.random() < 0.04:            # occasional bulkhead collapse: big burst
                        Vr = 0.15 * self.trapped[i]
                    self.trapped[i] -= Vr
                    # wreck glides on the way down; plume spreads ~0.1*depth; rise ~2 m/s
                    jx, jy = RNG.normal(0, 0.15 * self.h.B + 0.05 * depth, 2)
                    S_ = 0.9 * Vr ** (1 / 3) + 0.10 * depth
                    self.add_boil(t + depth / 2.0, X[top] + jx, Y[top] + jy, S_, float(np.clip(1.1 - 0.006 * depth, 0.3, 1.0)))
        # scripted events (torpedo hit etc.)
        while self.scripted and self.scripted[0]["t"] <= t:
            e = self.scripted.pop(0)
            self.add_boil(e["t"], e["x"], e["y"], e["S"], e.get("I", 1.0))
            self.rings.append(dict(t=e["t"], x=e["x"], y=e["y"], A=0.5))
        # 5. oil leaks
        for lk in self.leaks:
            if t >= lk["t0"] and int(round(t / dt)) % 10 == 0:
                seg = lk.get("seg", 0)
                lx, ly, lz = transform(np.array([lk["p"]]), self.poses(t)[seg])
                delay = max(-lz[0], 0) / 1.0
                jx, jy = RNG.normal(0, 0.15 * self.h.B, 2)
                self.puddles.append((t + delay, lx[0] + jx, ly[0] + jy, lk["rate"] * 1.0))
        # 6. debris motion: drift + boil outflow
        if len(self.debris):
            v = np.tile(self.drift, (len(self.debris), 1))
            for b in self.boils:
                a = t - b["t"]
                if a < 0 or a > 12:
                    continue
                d = self.debris - [b["x"], b["y"]]
                r = np.linalg.norm(d, axis=1) + 1e-6
                R = b["S"] * (0.5 + 1.5 * (1 - np.exp(-a / 1.5)))
                sp = 2.0 * b["I"] * np.exp(-a / 3.0) * (r / R) * np.exp(-(r / R) ** 2)
                v += d / r[:, None] * sp[:, None]
            self.debris = self.debris + v * dt
        self.Zprev = Z
        self.t = t
        self.timing["step"] += time.perf_counter() - t0
        self.timing["n_steps"] += 1

    # ---- analytic layers ------------------------------------------------------------------
    def boil_fields(self, t):
        """returns (foam density, eta) from all boil events active at t"""
        dens = np.zeros((self.ny, self.nx), np.float32)
        eta = np.zeros((self.ny, self.nx), np.float32)
        keep = []
        for b in self.boils:
            a = t - b["t"]
            ts = 1.5 * np.sqrt(b["S"] / 4)
            tb = 3.5 * np.sqrt(b["S"] / 4)
            if a > 6 * tb:
                continue
            keep.append(b)
            if a < 0:
                continue
            R = b["S"] * (0.5 + 1.5 * (1 - np.exp(-a / ts)))
            rr = 2.4 * R
            i0, i1 = np.searchsorted(self.xc, [b["x"] - rr, b["x"] + rr])
            j0, j1 = np.searchsorted(self.yc, [b["y"] - rr, b["y"] + rr])
            if i1 <= i0 or j1 <= j0:
                continue
            dxs = self.XX[j0:j1, i0:i1] - b["x"]
            dys = self.YY[j0:j1, i0:i1] - b["y"]
            q = np.hypot(dxs, dys) / R
            # angular wobble so boils aren't perfect circles
            ang = np.arctan2(dys, dxs)
            q = q * (1 + 0.12 * np.sin(3 * ang + b["S"]) + 0.08 * np.sin(5 * ang + 2 * b["x"]))
            I = b["I"] * np.exp(-a / tb)
            if "k" not in b:
                b["k"], b["ph"] = int(RNG.integers(11, 19)), float(RNG.random() * 6.283)
            streak = 0.75 + 0.25 * np.cos(b["k"] * ang + b["ph"] + 3.0 * q)           # radial outflow streaks
            churn = 0.75 * smooth(1 - q, 0.0, 0.6) * np.exp(-a / (0.6 * tb))        # white centre, fades first
            rim = np.exp(-((q - 0.95) / 0.20) ** 2) * streak                          # foam carried to the rim
            tail = 0.25 * b["I"] * np.exp(-a / (5 * tb)) * smooth(1.15 - q, 0, 0.35) * smooth(q, 0.2, 0.9) * streak
            new = (I * (churn + rim) + tail).astype(np.float32)
            cur = dens[j0:j1, i0:i1]
            dens[j0:j1, i0:i1] = np.maximum(cur, new) + 0.35 * np.minimum(cur, new)  # overlap brightens, no blow-out
            # dome of upwelling water -> lighting
            eta[j0:j1, i0:i1] += (0.08 * b["S"] * I * np.exp(-2.5 * q * q)).astype(np.float32)
        self.boils = keep
        return np.clip(dens, 0, 1.2), eta

    def ring_eta(self, t):
        eta = np.zeros((self.ny, self.nx), np.float32)
        for r in self.rings:
            a = t - r["t"]
            if a < 0 or a > 40:
                continue
            d = np.hypot(self.XX - r["x"], self.YY - r["y"])
            R = 5.0 * a
            env = np.exp(-((d - R) / (6 + 0.6 * a)) ** 2) * r["A"] * np.exp(-a / 15) / np.sqrt(1 + R / 20)
            eta += (env * np.cos((d - R) / 3.0)).astype(np.float32)
        return eta

    def oil_thickness(self, t):
        """oil film thickness in metres (sum of Fay gravity-inertial puddles, time-accelerated)."""
        h = np.zeros((self.ny, self.nx), np.float32)
        D = 0.07                                  # (rho_w - rho_o)/rho_w, heavy fuel oil ~0.04-0.08
        for (t0, x, y, V) in self.puddles:
            a = t - t0
            if a <= 0:
                continue
            ae = a * self.oil_ts
            R = 1.14 * (D * G * V * ae * ae) ** 0.25 + 0.5
            cx, cy = x + self.drift[0] * a, y + self.drift[1] * a
            rr = 3.2 * R
            i0, i1 = np.searchsorted(self.xc, [cx - rr, cx + rr])
            j0, j1 = np.searchsorted(self.yc, [cy - rr, cy + rr])
            if i1 <= i0 or j1 <= j0:
                continue
            d = np.hypot(self.XX[j0:j1, i0:i1] - cx, self.YY[j0:j1, i0:i1] - cy) / R
            d = d * (1 + 0.45 * (self.noise_w[j0:j1, i0:i1] - 0.5))         # ragged edge
            core = V / (np.pi * R * R) * smooth(1.15 - d, 0, 0.35)
            halo = 1.5e-6 * smooth(2.2 - d, 0, 1.0)       # sheen/rainbow fringe outside the thick core
            h[j0:j1, i0:i1] += (core + halo).astype(np.float32)
        return h

    # ---- render ----------------------------------------------------------------------------
    def render(self, t):
        t0 = time.perf_counter()
        X, Y, Z, NX, NY, NZ = self.world(t, with_normals=True)
        C = self.S["C"]
        ny, nx = self.ny, self.nx
        # water: base + ripple texture (suppressed by oil) + eta lighting (boil domes, closure rings)
        boil_d, boil_eta = self.boil_fields(t)
        eta = boil_eta + self.ring_eta(t)
        oil = self.oil_thickness(t)
        slick = smooth(np.log10(np.maximum(oil, 1e-9)), -7.6, -6.6)          # >~0.05-0.2 um damps ripples
        gy, gx = np.gradient(eta, self.dx)
        shade = 1 + 1.6 * np.clip(-(gx * self.sun[0] + gy * self.sun[1]), -0.4, 0.4)
        base = np.array([0.105, 0.30, 0.38])
        ripple = (self.noise_w - 0.5) * (1 - 0.85 * slick)
        img = base[None, None, :] * (shade * (1 + 0.16 * ripple))[..., None]
        img = img * (1 - 0.10 * slick)[..., None]                               # slick reads slightly darker/glassier
        img = self.oil_colour(img, oil)
        # hull: z-buffer splat (highest sample wins)
        ix, iy, ok = self.to_ij(X, Y)
        o = np.argsort(Z[ok])
        ii, jj = ix[ok][o], iy[ok][o]
        top_z = np.full((ny, nx), -1e9)
        top_c = np.zeros((ny, nx, 3))
        top_n = np.zeros((ny, nx, 3))
        top_z[jj, ii] = Z[ok][o]
        top_c[jj, ii] = C[ok][o]
        top_n[jj, ii] = np.c_[NX, NY, NZ][ok][o]
        has = top_z > -1e8
        # fill single-pixel holes from sampling
        hole = (~has) & (maximum_filter(np.where(has, 1, 0), 3) > 0) & (binary_erosion(maximum_filter(has, 3)))
        if hole.any():
            zf = maximum_filter(top_z, 3)
            for k in range(3):
                top_c[..., k] = np.where(hole, maximum_filter(top_c[..., k], 3), top_c[..., k])
            top_z = np.where(hole, zf, top_z)
            top_n = np.where(hole[..., None], [0, 0, 1.0], top_n)
            has = has | hole
        under = has & (top_z < 0)
        above = has & (top_z >= 0)
        # submerged hull: tinted toward water with depth (visibility a few metres, stylised)
        depth = np.clip(-top_z, 0, None)
        vis = np.exp(-depth / 3.0) * 0.85
        uw = top_c * 0.75 + 0.25 * base
        img = np.where(under[..., None], img * (1 - vis[..., None]) + uw * vis[..., None], img)
        # foam: crossing + contact + residual + boils, soft breakup on world-space noise
        d = np.clip(self.fresh + 0.5 * self.resid + boil_d, 0, 1)
        tt = 1 - d
        brk = np.clip((self.noise_f - tt + 0.18) / 0.36, 0, 1)
        alpha = np.clip(brk * np.clip(1.6 * d, 0, 1) + 0.6 * smooth(d, 0.85, 1.0), 0, 1)
                # foam churned through thick oil turns brown (mousse-like) and less white
        oily = smooth(oil * 1e6, 50, 600)[..., None]
        foam_c = np.array([0.93, 0.96, 0.97]) * (1 - oily) + np.array([0.50, 0.41, 0.30]) * oily
        alpha = alpha * (1 - 0.3 * oily[..., 0])
        img = img * (1 - alpha[..., None]) + foam_c * alpha[..., None]
        # debris
        if len(self.debris):
            dix, diy, dok = self.to_ij(self.debris[:, 0], self.debris[:, 1])
            for ox, oy in ((0, 0), (1, 0), (0, 1)):
                jx, jy = np.clip(dix[dok] + ox, 0, nx - 1), np.clip(diy[dok] + oy, 0, ny - 1)
                img[jy, jx] = [0.42, 0.34, 0.24] if ox == 0 and oy == 0 else [0.50, 0.42, 0.30]
        # drop shadow of everything above water onto the surface layer (height cue)
        tanE = np.tan(self.sun_elev)
        ab = Z > 0
        sx, sy = X[ab] - Z[ab] * self.sun[0] / tanE, Y[ab] - Z[ab] * self.sun[1] / tanE
        sh = self.splat(sx, sy, np.ones(ab.sum())) > 0
        sh = gaussian_filter(maximum_filter(sh, 3).astype(float), 0.6 / self.dx)
        img = img * (1 - 0.42 * np.clip(sh, 0, 1) * (~above))[..., None]
        # above-water hull: lambert + outline (clean vector look)
        sunv = np.array([self.sun[0] * np.cos(self.sun_elev), self.sun[1] * np.cos(self.sun_elev), np.sin(self.sun_elev)])
        lam = np.clip((top_n @ sunv), 0, 1)
        lit = top_c * (0.55 + 0.55 * lam)[..., None]
        # wet look just above the waterline
        wet = smooth(1.2 - top_z, 0, 1.2) * 0.25
        lit = lit * (1 - wet[..., None])
        img = np.where(above[..., None], lit, img)
        edge = above & ~binary_erosion(above)
        img[edge] *= 0.55
        self.timing["render"] += time.perf_counter() - t0
        return np.clip(img[::-1], 0, 1)       # +y up

    def oil_colour(self, img, h):
        """Bonn Agreement appearance codes (um): sheen .04-.3, rainbow .3-5, metallic 5-50,
        discontinuous true colour 50-200, continuous true colour >200. Stylised."""
        um = h * 1e6
        lg = np.log10(np.maximum(um, 1e-4))
        out = img.copy()
        sheen = smooth(lg, np.log10(0.04), np.log10(0.3)) * (1 - smooth(lg, 0.0, np.log10(5)))
        out = out + 0.07 * sheen[..., None]
        # rainbow: hue cycles with thickness (thin-film interference), broken up by noise
        rb = smooth(lg, np.log10(0.3), 0.0) * (1 - smooth(lg, np.log10(3), np.log10(8)))
        ph = 2 * np.pi * (1.3 * lg + 0.6 * self.noise_w)
        rain = 0.5 + 0.5 * np.stack([np.cos(ph), np.cos(ph - 2.1), np.cos(ph + 2.1)], -1)
        out = out * (1 - 0.30 * rb[..., None]) + (0.30 * rb)[..., None] * (0.25 + 0.5 * rain)
        met = smooth(lg, np.log10(5), np.log10(30)) * (1 - smooth(lg, np.log10(60), np.log10(200)))
        out = out * (1 - 0.45 * met[..., None]) + 0.45 * met[..., None] * np.array([0.20, 0.17, 0.24])
        true = smooth(lg + 0.25 * (self.noise_f - 0.5), np.log10(50), np.log10(300))
        out = out * (1 - 0.70 * true[..., None]) + 0.70 * true[..., None] * np.array([0.06, 0.055, 0.05])
        return out


# --------------------------------------------------------------------------------------------
# Hulls and scenarios (pose keyframes stand in for the flooding/buoyancy model)
# --------------------------------------------------------------------------------------------
def fletcher():
    L, B = 114.0, 12.0
    gray = [0.60, 0.62, 0.64]
    return Hull("Fletcher-like DD", L, B, 4.2, 5.0, 1.7, 5.0, deck_col=(0.50, 0.53, 0.57),
                turrets=[(0.36 * L, 2.2), (0.28 * L, 2.2), (-0.26 * L, 2.2), (-0.34 * L, 2.2), (-0.42 * L, 2.2)],
                supers=[(0.13 * L, 0.24 * L, 0.33 * B, 7.0, gray), (-0.30 * L, -0.18 * L, 0.26 * B, 2.5, gray)],
                funnels=[(0.06 * L, 1.6, 10.0), (-0.06 * L, 1.6, 10.0)], fuel_m3=520)


def baltimore():
    L, B = 205.0, 21.6
    gray = [0.60, 0.62, 0.64]
    return Hull("Baltimore-like CA", L, B, 7.3, 7.5, 1.8, 5.0, deck_col=(0.50, 0.53, 0.57),
                turrets=[(0.30 * L, 4.8), (0.22 * L, 4.8), (-0.31 * L, 4.8)],
                supers=[(0.05 * L, 0.16 * L, 0.33 * B, 10.0, gray), (-0.22 * L, -0.10 * L, 0.28 * B, 6.0, gray)],
                funnels=[(0.01 * L, 2.3, 14.0), (-0.07 * L, 2.3, 14.0)], fuel_m3=2400)


def iowa():
    L, B = 270.0, 33.0
    gray = [0.60, 0.62, 0.64]
    return Hull("Iowa-like BB", L, B, 11.0, 8.5, 1.9, 5.0, deck_col=(0.62, 0.55, 0.43),
                turrets=[(0.30 * L, 8.5), (0.21 * L, 8.5), (-0.29 * L, 8.5)],
                supers=[(0.02 * L, 0.15 * L, 0.30 * B, 16.0, gray), (-0.20 * L, -0.09 * L, 0.25 * B, 8.0, gray)],
                funnels=[(-0.01 * L, 3.3, 20.0), (-0.07 * L, 3.3, 20.0)], fuel_m3=8000)


def scenario(name):
    if name == "bow_first":          # destroyer, flooded forward, plunges by the bow
        h = fletcher()
        L = h.L
        kf = Keyframes([(0, 0, 0, 0), (8, 0.5, -0.5, 1), (30, 2.0, -2.5, 2), (40, 3.5, -6, 3), (48, 8, -20, 3),
                        (54, 18, -45, 3), (59, 35, -60, 2), (62, 46, -65, 2)], pivot=-0.15 * L, v_desc=8)
        segs = [dict(x_range=(-L / 2, L / 2), pose=kf)]
        ext = (-0.85 * L, 0.85 * L, -0.42 * L, 0.42 * L)
        leaks = [dict(t0=5, p=(0.30 * L, 0, -2.0), rate=0.03)]
        return h, segs, dict(dx=0.35, extent=ext, leaks=leaks, t_end=125, n_comp=10)
    if name == "stern_first":        # heavy cruiser, torpedo aft, settles by the stern, bow rises
        h = baltimore()
        L = h.L
        kf = Keyframes([(0, 0, 0, 0), (20, 1, 1, 2), (50, 3, 3.5, 5), (65, 6, 9, 6), (75, 14, 25, 6),
                        (83, 30, 45, 5), (90, 55, 58, 4), (95, 75, 62, 4)], pivot=0.15 * L, v_desc=8)
        segs = [dict(x_range=(-L / 2, L / 2), pose=kf)]
        ext = (-0.85 * L, 0.85 * L, -0.42 * L, 0.42 * L)
        leaks = [dict(t0=3, p=(-0.38 * L, -0.4 * h.B, -3.0), rate=0.12)]
        return h, segs, dict(dx=0.6, extent=ext, leaks=leaks, t_end=150, n_comp=12)
    if name == "capsize":            # battleship, one-sided flooding: list -> roll over -> founders keel-up
        h = iowa()
        L = h.L
        kf = Keyframes([(0, 0, 0, 0), (15, 1, 0.3, 4), (40, 2.5, 0.6, 12), (55, 4, 1.0, 25), (62, 6, 1.5, 60),
                        (68, 8, 2.0, 120), (76, 9, 2.5, 160), (100, 13, 4, 168), (115, 26, 12, 172),
                        (125, 55, 25, 175)], pivot=0.0, v_desc=7)
        segs = [dict(x_range=(-L / 2, L / 2), pose=kf)]
        ext = (-0.8 * L, 0.8 * L, -0.42 * L, 0.42 * L)
        leaks = [dict(t0=2, p=(0.05 * L, -0.5 * h.B, -4.0), rate=0.3)]
        return h, segs, dict(dx=0.75, extent=ext, leaks=leaks, t_end=175, n_comp=12)
    if name == "break_in_two":       # destroyer, torpedo under the keel amidships: V-break, both ends rise
        h = fletcher()
        L = h.L
        xb = -0.04 * L
        kf_f = Keyframes([(0, 0, 0, 0), (2, 0.5, 0.5, 0), (4, 1.5, 3, 1), (11, 5, 15, 3), (18, 14, 35, 4),
                          (24, 28, 55, 4), (28, 42, 65, 4)], pivot=xb, v_desc=8)
        kf_a = Keyframes([(0, 0, 0, 0), (2, 0.5, -0.5, 0), (4, 1.5, -4, -1), (10, 5, -18, -2), (16, 14, -40, -3),
                          (21, 26, -60, -3), (25, 38, -70, -3)], pivot=xb, v_desc=8)
        segs = [dict(x_range=(-L / 2, xb), pose=kf_a), dict(x_range=(xb, L / 2), pose=kf_f)]
        ext = (-0.85 * L, 0.85 * L, -0.42 * L, 0.42 * L)
        leaks = [dict(t0=1, p=(xb + 3, 0, -3.0), rate=0.05, seg=1)]
        ev = [dict(t=0.3, x=xb, y=0.0, S=9.0, I=1.0)]
        return h, segs, dict(dx=0.35, extent=ext, leaks=leaks, t_end=85, n_comp=10, events=ev)
    raise ValueError(name)


def run(name, out_dir, dt=0.1, frame_every=0.5, strip_times=None):
    h, segs, kw = scenario(name)
    sim = SinkSim(h, segs, **kw)
    os.makedirs(out_dir, exist_ok=True)
    frames, strip = [], {}
    n = int(round(sim.t_end / dt))
    fe = int(round(frame_every / dt))
    st = set(int(round(x / dt)) for x in (strip_times or []))
    for k in range(1, n + 1):
        sim.step(dt)
        if k % fe == 0 or k in st:
            img = sim.render(sim.t)
            if k % fe == 0:
                frames.append((sim.t, img))
            if k in st:
                strip[round(sim.t, 1)] = img
    return sim, frames, strip