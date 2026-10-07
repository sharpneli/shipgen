"""
ocean: the open sea for vidgen, ported from sea_state_lab.html (research: ocean-surface-research.md).

A Tessendorf spectral sea: wind sea (fetch-limited JONSWAP capped at Pierson-Moskowitz, Mitsuyasu spreading) plus a
narrow swell from another direction, in three cascades (1987 m, 251 m, 31.7 m tiles, band-split at 4 tile
wavelengths) and the lab's free ripple cascade (cascade 2's spectrum at 7.93x the wavenumber, taking half the
Cox-Munk slope budget the spectrum leaves). Shading is the lab's: Fresnel sky reflection, a water body, and a
Cox-Munk sun glint whose slope variance carries every wave too short to draw, seen by a virtual perspective eye
above the frame's centre.

Departures from the lab, for an offline numpy renderer whose camera only translates:
- **No FFT to a tile and no texture lookups.** Each cascade's spectrum is summed directly at the frame's pixels as a
  separable DFT, `Ey @ spec @ Ex.T` (two matmuls), since the frame is an axis-aligned grid. That's exact at any zoom,
  so there are no mips: wavenumbers a pixel can't hold (wavelength under `RESOLVE_PX` px) are tapered out of the
  sum, and their slope variance goes into the glint's roughness instead (the LEAN step, done in the spectrum).
- **No tiling, and so no hex bombing.** The wavenumber grid is jittered per row and per column (antisymmetric, so
  the sea stays real). The sum is then not periodic at all.
- **Choppy displacement over all of cascades 0 and 1 together** (the research's "cross-cascade Jacobian"): the
  Lagrangian slope uses the summed Jacobian. Cascade 2 and the ripples are drawn unchopped, at the pixel.
- **No foam** (whitecaps, gust patches, wave groups): vidgen's clips are moderate seas.
- **A sun aureole in the sky** (`AUREOLE`): the lab's sky is a plain zenith-horizon gradient, so straight down only
  the glitter path showed any waves and the rest of the frame was flat. The real sky is several times brighter
  near the sun, so facets tilted sunward reflect more: waves read over the whole frame.
- **Colours are the caller's:** vidgen passes a darker, greener water body (its old palette's mean) than the lab's
  navy. The crest tint scales with the body.

Other water (the wake, blasts, boils) is linear too, so callers add its slopes to `slopes()`'s and shade the sum.

numpy only. Units: metres, seconds. Axes are vidgen's: screen x right, y down, z up.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image

G = 9.81
TAU = 2 * math.pi
CASC = (1987.0, 251.0, 31.7)             # tile sizes, deliberately non-commensurate
N = 128                                    # bins per axis per cascade
BAND = (0.0, TAU * 4 / CASC[1], TAU * 4 / CASC[2], math.inf)   # cascade c holds |k| in [BAND[c], BAND[c+1])
RIPPLE_K = 7.93                            # the ripple cascade: cascade 2 at this many times its wavenumber
JITTER = 0.35                              # +- share of a bin the wavenumber grid is jittered by (kills tiling)
RESOLVE_PX = 3.0                           # shortest wavelength drawn, px; shorter waves become roughness
LONG_SAMPLES = 12                          # grid points per shortest wave of cascades 0-1 (their own coarse grid)
CHOP = 1.0                                 # choppiness lambda (the lab's default)
ES = np.float32(3.2)                       # the sun's irradiance in the lab's units
GLINT_TINT = (1.0, 0.96, 0.88)
AUREOLE = (3.0, 0.42)                      # the sky brightens toward the sun: 1 + a e^((cos g - 1) / w^2), w ~ 24 deg
LUT_N, LUT_TOP = 16384, 3.0                # tonemap table: radiance 0..3 (beyond is white)

# Beaufort mid-range 10 m wind, m/s (the lab's table)
BFT_U = (0.2, 1.5, 3.3, 5.4, 7.9, 10.7, 13.8, 17.1, 20.7, 24.4, 28.4, 32.6, 36.0)


def beaufort_u(b):
    i = min(int(b), 11)
    f = b - i
    return BFT_U[i] * (1 - f) + BFT_U[i + 1] * f


def _spread(s, th):
    """Longuet-Higgins cos^2s(theta/2), normalised over the circle."""
    ln = (2 * s - 1) * math.log(2) + 2 * math.lgamma(s + 1) - math.lgamma(2 * s + 1) - math.log(math.pi)
    return np.exp(ln) * np.abs(np.cos(th / 2)) ** (2 * s)


def _jonswap(w, wp, gamma):
    sig = np.where(w <= wp, 0.07, 0.09)
    r = np.exp(-((w - wp) ** 2) / (2 * sig * sig * wp * wp))
    return w ** -5.0 * np.exp(-1.25 * (wp / w) ** 4) * gamma ** r


class Sea:
    """The directional spectrum S(omega, theta) for a wind (m/s, the direction it blows toward, screen axes) and a
    swell (Hs m, Tp s, the direction it travels toward)."""

    def __init__(self, wind, swell=(1.0, 10.0, (0.0, -1.0)), fetch_km=150.0):
        self.U = U = max(float(np.hypot(*wind)), 0.3)
        self.wind_ang = math.atan2(wind[1], wind[0])
        F = fetch_km * 1000
        wp = 22 * (G * G / (U * F)) ** (1 / 3)
        alpha = 0.076 * (G * F / (U * U)) ** -0.22
        wp_pm = 0.855 * G / U
        if wp < wp_pm:                          # fully developed: Pierson-Moskowitz
            wp, alpha = wp_pm, 0.0081
        self.gamma = 1 + 2.3 * min(max((wp / wp_pm - 1) / 0.5, 0), 1)   # peak enhancement fades out at full development
        self.wp, self.alpha = wp, max(alpha, 0.0081)
        self.sp = min(11.5 * (wp * U / G) ** -2.5, 40)
        hs, tp, sdir = swell
        self.swp = TAU / tp
        self.swell_ang = math.atan2(sdir[1], sdir[0])
        w = np.arange(0.05, 6, 0.001)
        I = float(np.sum(_jonswap(w, self.swp, 5.0)) * 0.001)
        self.sA = (hs / 4) ** 2 / I if hs > 0 and I > 0 else 0.0

    def S(self, w, th):
        w = np.maximum(w, 1e-6)
        s = np.where(w < self.wp, self.sp * (w / self.wp) ** 5, self.sp * (w / self.wp) ** -2.5)
        v = self.alpha * G * G * _jonswap(w, self.wp, self.gamma) * _spread_v(np.maximum(s, 0.5), th - self.wind_ang)
        if self.sA > 0:
            v = v + self.sA * _jonswap(w, self.swp, 5.0) * _spread(40, th - self.swell_ang)
        return v

    def cox_munk(self):
        """Clean-surface mean-square slope per screen axis, upwind 0.00316 U, crosswind 0.003 + 0.00192 U."""
        su, sc = 0.00316 * self.U, 0.003 + 0.00192 * self.U
        c, s = math.cos(self.wind_ang), math.sin(self.wind_ang)
        return su * c * c + sc * s * s, su * s * s + sc * c * c


def _lgamma_v(z):
    return np.vectorize(math.lgamma, otypes=[np.float64])(z)


def _spread_v(s, th):
    """_spread with a per-bin s (Mitsuyasu's s varies with frequency)."""
    ln = (2 * s - 1) * math.log(2) + 2 * _lgamma_v(s + 1) - _lgamma_v(2 * s + 1) - math.log(math.pi)
    return np.exp(ln) * np.abs(np.cos(th / 2)) ** (2 * s)


def _taper(k, kcut):
    """1 below 0.7 kcut, smoothly to 0 at kcut: the share of a wave the pixel grid draws."""
    x = np.clip((kcut - k) / (0.3 * kcut), 0, 1)
    return x * x * (3 - 2 * x)


class Cascade:
    """One cascade's spectrum on a jittered product grid of wavenumbers, trimmed to the rows and columns that hold
    anything, with h0(k) and h0*(-k) ready for time evolution (lab: buildH0, then P_SPEC)."""

    def __init__(self, c, sea, rng):
        L = CASC[c]
        dk = TAU / L
        n = np.arange(-N // 2 + 1, N // 2)                        # no Nyquist bin, so -n is always present
        j = rng.uniform(-JITTER, JITTER, N // 2)
        jit = np.concatenate([-j[1:][::-1], [0.0], j[1:]])        # antisymmetric: k(-n) = -k(n)
        kv = (n + jit) * dk
        g1, g2 = rng.standard_normal((2, n.size, n.size))         # drawn whole, so phases don't depend on the sea
        kx, ky = np.meshgrid(kv, kv)                               # [row (y), col (x)]
        k = np.hypot(kx, ky)
        band = (k >= BAND[c]) & (k < BAND[c + 1]) & (k > 0)
        w = np.sqrt(G * k)
        P = np.where(band, sea.S(w, np.arctan2(ky, kx)) * (G / (2 * np.maximum(w, 1e-9))) / np.maximum(k, 1e-9)
                     * dk * dk, 0.0)                               # height variance in the bin
        keep_r, keep_c = P.any(axis=1), P.any(axis=0)
        keep_r, keep_c = keep_r | keep_r[::-1], keep_c | keep_c[::-1]   # symmetric, so -k stays on the grid
        self.kx, self.ky = kv[keep_c], kv[keep_r]
        P = P[np.ix_(keep_r, keep_c)]
        g1, g2 = g1[np.ix_(keep_r, keep_c)], g2[np.ix_(keep_r, keep_c)]
        self.P = P
        self.h0 = (g1 + 1j * g2) * 0.5 * np.sqrt(P)                # E|h0|^2 = P/2, so the realised variance is sum P
        self.h0m = np.conj(self.h0[::-1, ::-1])                    # h0*(-k): the trimmed grid is still symmetric
        K = np.hypot(*np.meshgrid(self.kx, self.ky))
        self.K = K
        self.w = np.sqrt(G * K)
        self.var = float(P.sum())
        KX, KY = np.meshgrid(self.kx, self.ky)
        self.mss = (float((KX * KX * P).sum()), float((KY * KY * P).sum()))

    def spec(self, t, cam):
        """h(k, t) with the camera's position folded in as a phase, so the DFT matrices stay fixed."""
        e = np.exp(-1j * self.w * t)
        h = self.h0 * e + self.h0m * np.conj(e)
        return h * np.exp(1j * (self.kx[None, :] * cam[0] + self.ky[:, None] * cam[1]))


class Ocean:
    """The sea over one frame (W x H px at s px/m, ship centre C px). shade() gives display RGB per pixel."""

    def __init__(self, W, H, s, C, sea: Sea, sun, seed=7, eye_fov=40.0, expo=1.0, body=None, sky=None):
        self.W, self.H, self.s = W, H, s
        self.sea = sea
        rng = np.random.default_rng(seed)
        self.casc = [Cascade(c, sea, rng) for c in range(3)]
        self.Hs = 4 * math.sqrt(sum(c.var for c in self.casc))
        px = 1.0 / s
        kcut = TAU / (RESOLVE_PX * px)
        # screen metres from the ship centre, as vidgen's Water had them
        X = (np.arange(W) - C[0]) / s
        Y = (np.arange(H) - C[1]) / s
        self.X, self.Y = X, Y

        # cascades 0-1 on their own coarse grid (the shortest of them is 7.9 m), with choppy displacement
        lam_min = TAU / BAND[2]
        self.dl = dl = max(px, lam_min / LONG_SAMPLES)
        m = 3 + int(math.ceil(4 * sea_disp_bound(self) / dl))           # margin: the displacement inversion reads past the frame
        self.gx = X[0] + dl * np.arange(-m, int(math.ceil((X[-1] - X[0]) / dl)) + m + 1)
        self.gy = Y[0] + dl * np.arange(-m, int(math.ceil((Y[-1] - Y[0]) / dl)) + m + 1)
        kcut_l = min(kcut, TAU / (RESOLVE_PX * dl))
        self.long = []
        unres = np.zeros(2)
        for c in self.casc[:2]:
            wx, wy = _taper(np.abs(c.kx), kcut_l), _taper(np.abs(c.ky), kcut_l)
            wt = wy[:, None] * wx[None, :] * _taper(c.K, kcut_l)
            Ex = np.exp(1j * np.outer(self.gx, c.kx)).astype(np.complex64)
            Ey = np.exp(1j * np.outer(self.gy, c.ky)).astype(np.complex64)
            self.long.append((c, wt, Ex, Ey))
            unres += _unres(c, wt)
        # PIL's affine from frame pixels to the coarse grid (it samples both at pixel centres)
        a = 1 / (s * dl)
        self.up = (a, 0, -0.5 * a - (self.gx[0] - X[0]) / dl + 0.5, 0, a, -0.5 * a - (self.gy[0] - Y[0]) / dl + 0.5)

        # cascade 2 and the ripples at the pixels, unchopped
        c2 = self.casc[2]
        cmx, cmy = sea.cox_munk()
        rx = sum(c.mss[0] for c in self.casc)
        ry = sum(c.mss[1] for c in self.casc)
        self.var_u = np.array([max(cmx - rx, 4e-4), max(cmy - ry, 4e-4)])   # Cox-Munk top-up for unmodelled short waves
        self.k3 = np.sqrt(0.5 * self.var_u / np.maximum(np.array(c2.mss), 1e-12))
        self.short = []
        unres_s = np.zeros(2)
        for c, f, amp in ((c2, 1.0, np.ones(2)), (c2, RIPPLE_K, self.k3)):
            wt = _taper(np.abs(c.ky) * f, kcut)[:, None] * _taper(np.abs(c.kx) * f, kcut)[None, :] * _taper(c.K * f, kcut)
            keep_r, keep_c = wt.any(axis=1), wt.any(axis=0)
            res = _resolved(c, wt) * amp ** 2                 # the ripples are cascade 2's slopes times amp
            unres_s += np.array(c.mss) - res if f == 1.0 else -res     # the ripples' total already sits in var_u
            if not keep_r.any():
                continue
            sel = np.ix_(keep_r, keep_c)
            Ex = np.exp(1j * np.outer(X * f, c.kx[keep_c])).astype(np.complex64)
            Ey = np.exp(1j * np.outer(Y * f, c.ky[keep_r])).astype(np.complex64)
            self.short.append((c, sel, wt[sel], Ex, Ey, amp, c.kx[keep_c][None, :], c.ky[keep_r][:, None]))
        self.var_long = unres                     # unresolved slope variance of cascades 0-1
        self.var_short = unres_s                  # of cascade 2, less the ripples' resolved share
        # light
        self.L = np.asarray(sun, np.float32)
        self.eye_h = (W / s / 2) / math.tan(math.radians(eye_fov) / 2) if eye_fov > 0 else 0.0
        self.expo = expo
        self.body = np.array(body if body is not None else (0.004, 0.022, 0.05), np.float32)
        self.sky_z, self.sky_h = (np.array(v, np.float32) for v in (sky or ((0.09, 0.19, 0.42), (0.55, 0.66, 0.78))))
        ex, ey = (np.arange(W) - W / 2) / s, (np.arange(H) - H / 2) / s     # from the frame centre, for the eye
        self.ex, self.ey = ex.astype(np.float32), ey.astype(np.float32)
        self._light_setup()

    # ----- waves
    def _long(self, t, cam):
        """Cascades 0-1 on the coarse grid: Lagrangian slopes and height at the displaced (screen) points."""
        acc = None
        for c, wt, Ex, Ey in self.long:
            h = c.spec(t, cam) * wt
            KX, KY = c.kx[None, :], c.ky[:, None]
            ik = np.where(c.K > 1e-9, 1 / np.maximum(c.K, 1e-12), 0)
            fields = np.stack([
                1j * KX * h - KY * h,                      # sx + i sy
                1j * KX * ik * h - KY * ik * h,            # Dx + i Dy
                -h * KX * KX * ik + 1j * (-h * KY * KY * ik),   # Jxx + i Jyy
                -h * KX * KY * ik + 1j * h,                # Jxy + i h
            ]).astype(np.complex64)
            out = Ey @ fields @ Ex.T
            acc = out if acc is None else acc + out
        sx, sy, Dx, Dy = acc[0].real, acc[0].imag, acc[1].real, acc[1].imag
        jxx, jyy, jxy = 1 + CHOP * acc[2].real, 1 + CHOP * acc[2].imag, CHOP * acc[3].real
        h = acc[3].imag
        J = np.maximum(jxx * jyy - jxy * jxy, 0.15)
        lx = np.clip((jyy * sx - jxy * sy) / J, -2.5, 2.5)
        ly = np.clip((-jxy * sx + jxx * sy) / J, -2.5, 2.5)
        # undo the displacement: the surface at grid point p came from q = p - D(p) (one fixed-point step)
        gh, gw = h.shape
        qi = np.arange(gh, dtype=np.float32)[:, None] - (CHOP / self.dl) * Dy
        qj = np.arange(gw, dtype=np.float32)[None, :] - (CHOP / self.dl) * Dx
        return [_bilinear(a, qi, qj) for a in (lx, ly, h)]

    def _short(self, t, cam):
        sx = sy = 0
        for c, sel, wt, Ex, Ey, amp, KX, KY in self.short:
            h = c.spec(t, cam)[sel] * wt
            spec = ((1j * KX * h) * amp[0] - (KY * h) * amp[1]).astype(np.complex64)   # sx + i sy, cascade units
            out = Ey @ spec @ Ex.T
            sx = sx + out.real
            sy = sy + out.imag
        return sx, sy

    def slopes(self, t, cam, calm=None):
        """Mean slope (sx, sy), height h and the slope variance (vx, vy) per pixel."""
        lx, ly, h = self._long(t, cam)
        up = [self._up(a) for a in (lx, ly, h)]
        sx, sy = self._short(t, cam)
        var_short = self.var_short + self.var_u
        if calm is not None:
            sx, sy = sx * calm, sy * calm
            c2 = calm * calm
            vx = np.float32(self.var_long[0]) + np.float32(var_short[0]) * c2
            vy = np.float32(self.var_long[1]) + np.float32(var_short[1]) * c2
        else:
            vx = np.float32(self.var_long[0] + var_short[0])
            vy = np.float32(self.var_long[1] + var_short[1])
        return up[0] + sx, up[1] + sy, up[2], vx, vy

    def _up(self, a):
        return np.asarray(Image.fromarray(np.ascontiguousarray(a, np.float32), "F").transform(
            (self.W, self.H), Image.AFFINE, self.up, resample=Image.BILINEAR))

    # ----- light
    def _light_setup(self):
        """Everything that depends only on the eye and the sun, which are fixed for the clip."""
        W, H, L = self.W, self.H, self.L
        if self.eye_h > 0:
            Vx = np.broadcast_to(-self.ex[None, :], (H, W))
            Vy = np.broadcast_to(-self.ey[:, None], (H, W))
            inv = 1 / np.sqrt(Vx * Vx + Vy * Vy + np.float32(self.eye_h ** 2))
            Vx, Vy, Vz = Vx * inv, Vy * inv, np.float32(self.eye_h) * inv
        else:
            Vx = Vy = np.zeros((H, W), np.float32)
            Vz = np.ones((H, W), np.float32)
        Hx, Hy, Hz = L[0] + Vx, L[1] + Vy, L[2] + Vz
        hn = 1 / np.sqrt(Hx * Hx + Hy * Hy + Hz * Hz)
        Hx, Hy, Hz = Hx * hn, Hy * hn, Hz * hn
        vh = np.clip(Vx * Hx + Vy * Hy + Vz * Hz, 0, 1)
        self.V = (Vx.astype(np.float32), Vy.astype(np.float32), Vz.astype(np.float32))
        self.glint_m = ((-Hx / Hz).astype(np.float32), (-Hy / Hz).astype(np.float32))   # the slope that mirrors the sun
        # Es F(v.h) / (4 mu_v mu_h^4), with the gaussian's 1 / 2 pi
        self.glint_k = (ES * (0.02 + 0.98 * (1 - vh) ** 5) / (4 * np.maximum(Vz, 0.05) * Hz ** 4) / TAU).astype(np.float32)
        amb = self.sky(np.float32(1.0))
        self.body_rad = self.body * (ES * L[2] + 2 * amb[2])
        # subsurface light through the crests: the lab's tint, scaled with the body (vidgen's is darker)
        self.crest_rad = np.array((0.002, 0.012, 0.012), np.float32) * ES * L[2] * np.float32(self.body[1] / 0.022)
        x = np.linspace(0, LUT_TOP, LUT_N, dtype=np.float64)
        self.lut = ((1 - np.exp(-x * 1.6 * self.expo)) ** (1 / 2.2)).astype(np.float32)

    def sky(self, rz):
        e = np.maximum(rz, 0) ** 0.45
        return (self.sky_h + (self.sky_z - self.sky_h) * np.asarray(e)[..., None]) * 0.55

    def radiance(self, mx, my, h, vx, vy):
        """Linear radiance (the lab's units) of a sea with mean slopes m, height h and slope variance v per axis."""
        Vx, Vy, Vz = self.V
        L = self.L
        n_inv = 1 / np.sqrt(mx * mx + my * my + 1)
        vn = np.clip((Vz - Vx * mx - Vy * my) * n_inv, 0, 1)
        F = 1 - vn
        F *= F * F * F * F
        F = 0.02 + 0.98 * F
        # R = reflect(-V, N): the sky's elevation, and its angle to the sun for the aureole
        k2 = 2 * vn * n_inv
        rz = k2 - Vz
        e = np.maximum(rz, 0) ** np.float32(0.45)
        cg = (-k2 * mx - Vx) * L[0] + (-k2 * my - Vy) * L[1] + rz * L[2]
        aur = 1 + np.float32(AUREOLE[0]) * np.exp((cg - 1) * np.float32(1 / AUREOLE[1] ** 2))
        zx, zy = self.glint_m[0] - mx, self.glint_m[1] - my
        q = zx * zx * (np.float32(-0.5) / vx) + zy * zy * (np.float32(-0.5) / vy)
        glint = np.exp(q) * (self.glint_k / np.sqrt(vx * vy))
        crest = np.clip(h * np.float32(1 / max(self.Hs * 0.5, 0.05)), 0, 1)
        crest *= crest * (1 - F)
        col = np.empty((self.H, self.W, 3), np.float32)
        for c in range(3):
            sky = (self.sky_h[c] + (self.sky_z[c] - self.sky_h[c]) * e) * (np.float32(0.55) * aur)
            v = self.body_rad[c] + F * (sky - self.body_rad[c])
            v += crest * self.crest_rad[c]
            v += glint * GLINT_TINT[c]
            col[..., c] = v
        return col

    def display(self, col):
        """The lab's tonemap, 1 - e^(-1.6 x), then gamma 2.2, by table."""
        i = np.minimum(col * np.float32((LUT_N - 1) / LUT_TOP) + np.float32(0.5), np.float32(LUT_N - 1)).astype(np.int32)
        return self.lut[i]


def sea_disp_bound(o):
    """Rough bound on the choppy displacement, m (3 sigma of the long cascades' height)."""
    return CHOP * 3 * math.sqrt(o.casc[0].var + o.casc[1].var)


def _unres(c, wt):
    KX, KY = np.meshgrid(c.kx, c.ky)
    lost = (1 - wt * wt) * c.P
    return np.array([(KX * KX * lost).sum(), (KY * KY * lost).sum()])


def _resolved(c, wt):
    KX, KY = np.meshgrid(c.kx, c.ky)
    kept = wt * wt * c.P
    return np.array([(KX * KX * kept).sum(), (KY * KY * kept).sum()])


def _bilinear(a, qi, qj):
    """a sampled at fractional (row, col) indices, clamped at the edges."""
    gh, gw = a.shape
    qi = np.clip(qi, 0, gh - 1.001)
    qj = np.clip(qj, 0, gw - 1.001)
    i0, j0 = qi.astype(np.int32), qj.astype(np.int32)
    fi, fj = (qi - i0).astype(np.float32), (qj - j0).astype(np.float32)
    a00, a01, a10, a11 = a[i0, j0], a[i0, j0 + 1], a[i0 + 1, j0], a[i0 + 1, j0 + 1]
    return (a00 * (1 - fj) + a01 * fj) * (1 - fi) + (a10 * (1 - fj) + a11 * fj) * fi
