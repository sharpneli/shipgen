"""v2.1 of the wake bake: fixes the 'blocky bow' problem of v1.

Changes vs wake_bake_ref.py (v1):
  1. Hull forcing = thin-ship (Michell-style) SOURCE distribution q = U * dm/dx on the waterplane
     instead of a pressure patch. A pressure patch makes a trough under/around the bow (it models
     a planing pad), so v1 had no crest at the stem and the near field was a dark wedge.
     Sources at the entrance (dm/dx > 0 going forward) push water out -> crest at the stem,
     trough at the shoulder, sinks at the run -> stern wave. Depth attenuation (1-e^{-kT})/k.
  2. Waterplane rasterised with 4x4 supersampling (no staircase -> no Gibbs ringing at the bow).
  3. Surface velocity from the same FFT (perturbation potential) and foam advected ALONG STREAMLINES
     (column march bow->stern with lateral displacement v/|u|*dx). Foam now curves away from the bow
     instead of streaking straight back as hull-parallel bands.
  4. Foam = fresh whitewater (short tau, max-combined) + residual foam (additive, long tau, laterally
     diffused, low opacity).
     v2.1 tuning: residual is fed by the share of whitewater that decays each step (resolution
     independent; v2's per-column feed scaled with 1/dx), narrower residual blur, no potential-flow
     steering aft of -0.2L (kills the transom lens), wash never steered, and stern-crest breaking
     weighted by Fr_L (0.3 at Fr_L<=0.3 -> 1.0 at Fr_L>=0.65). v1 used one long-tau max -> every source point smeared into a straight
     streak -> filled parallelograms with straight edges.
  5. Hull-side band uses a true signed distance (EDT) and soft edges, no geometric peel line;
     breaking is driven by the computed crest (height + steepness), so the detachment shape comes
     from the wave field itself.
"""
import time
import numpy as np
from scipy import fft as sfft
from scipy.ndimage import gaussian_filter, gaussian_filter1d, distance_transform_edt

G = 9.81


def half_breadth(xs, L, B, n_fore, n_aft):
    xi = 2 * xs / L
    n = np.where(xi > 0, n_fore, n_aft)
    h = 0.5 * B * np.clip(1 - np.abs(xi) ** n, 0, None)
    return np.where(np.abs(xi) <= 1, h, 0.0)


def planform_aa(x, y, L, B, n_fore, n_aft, ss=4):
    """Anti-aliased waterplane coverage in [0,1] (ss x ss supersampling)."""
    dx = x[1] - x[0]
    off = (np.arange(ss) + 0.5) / ss - 0.5
    cov = np.zeros((len(y), len(x)), np.float32)
    for ox in off:
        h = half_breadth(x + ox * dx, L, B, n_fore, n_aft)[None, :]
        for oy in off:
            cov += (np.abs(y[:, None] + oy * dx) < h)
    return cov / ss ** 2


def bake2(L, B, T, U, *, n_fore=1.7, n_aft=5.0, entrance_deg=12.0, wash=1.0,
          tau_fresh=3.0, tau_resid=15.0, tau_turb=45.0, resid_share=0.5, max_cells=1024, damp=0.08):
    t0 = time.perf_counter()
    lam = 2 * np.pi * U ** 2 / G
    span = max(L, lam)
    ahead_m, behind_m = 0.5 * L + 0.6 * span, 0.5 * L + 4.0 * span
    halfw_m = 0.45 * behind_m + B
    dx = max(L / 80, (ahead_m + behind_m) / max_cells)
    nx = sfft.next_fast_len(int((ahead_m + behind_m) / dx))
    ny = sfft.next_fast_len(int(2 * halfw_m / dx))
    x = (-behind_m + dx * np.arange(nx)).astype(np.float32)
    y = (-halfw_m + dx * np.arange(ny)).astype(np.float32)
    X, Y = np.meshgrid(x, y)

    m = planform_aa(x, y, L, B, n_fore, n_aft)
    m_s = gaussian_filter(m, sigma=max(0.75, 0.04 * B / dx))  # light smoothing only
    q = U * np.gradient(m_s, dx, axis=1)  # source density: + at entrance, - at run

    kx = 2 * np.pi * sfft.fftfreq(nx, dx)
    ky = 2 * np.pi * sfft.fftfreq(ny, dx)
    KX, KY = np.meshgrid(kx, ky)
    K = np.sqrt(KX ** 2 + KY ** 2)
    K[0, 0] = 1e-6
    att = (1 - np.exp(-K * T)) / K  # depth attenuation of a source sheet over the draft
    Q = sfft.fft2(q, workers=-1)
    eps = damp * G / U

    def solve(sign):
        D = G * K - (U * KX) ** 2 + sign * 1j * eps * U * KX
        Phi = -G * Q * att / D            # surface perturbation potential (up to scale)
        Phi[0, 0] = 0
        return Phi
    Phi = solve(-1)
    eta = sfft.ifft2(1j * KX * Phi, workers=-1).real  # eta ∝ phi_x (Bernoulli, linear)
    if np.abs(eta[:, x > 0.5 * L + 0.2 * span]).mean() > np.abs(eta[:, x < -0.5 * L - span]).mean():
        Phi = solve(+1)  # wrong radiation side -> flip
        eta = sfft.ifft2(1j * KX * Phi, workers=-1).real
    # orientation: crest at the stem must be positive
    stem = (np.abs(X - 0.5 * L) < 0.05 * L) & (np.abs(Y) < B)
    sgn = 1.0 if eta[stem].max() >= -eta[stem].min() else -1.0
    eta *= sgn
    Phi *= sgn
    t_fft = time.perf_counter() - t0

    # amplitude calibration (Noblesse bow wave height)
    beta = np.radians(entrance_deg)
    FrD = U / np.sqrt(G * T)
    Zb = 2.2 * U ** 2 / G * np.tan(beta) / (np.cos(beta) * (1 + FrD))
    scale = Zb / max(eta[stem & (m < 0.5)].max(), 1e-9)
    eta *= scale
    # surface perturbation velocity, consistent with eta = (U/g) u'  ->  u' = g*eta/U
    u = sfft.ifft2(1j * KX * Phi, workers=-1).real * scale * G / U
    v = sfft.ifft2(1j * KY * Phi, workers=-1).real * scale * G / U
    # outward check: v must push water away from the centreline at the entrance
    if np.mean(v[stem] * np.sign(Y[stem])) < 0:
        v = -v
    # linear theory blows up right at the waterline edges; foam only needs the gentle outer flow.
    # Smooth over ~B/4 and clamp to a fraction of U (bow-wave sheet leaves at ~ entrance angle).
    v_max = np.tan(beta + np.radians(4)) * U
    u = np.clip(gaussian_filter(u, 0.25 * B / dx), -0.3 * U, 0.3 * U)
    v = np.clip(gaussian_filter(v, 0.25 * B / dx), -v_max, v_max)
    eta = (eta * (1 - m)).astype(np.float32)
    tx = np.clip((X - X.min()) / (0.15 * (X.max() - X.min())), 0, 1)
    ty = np.clip((Y.max() - np.abs(Y)) / (0.15 * Y.max()), 0, 1)
    eta *= (tx * ty) ** 2
    # far-field readability: linear theory + light damping keeps the Kelvin arms crisp for many L.
    # Real divergent waves lose contrast with distance (~r^-1/2 plus dissipation); fade with distance
    # astern so the V reads near the ship and becomes subtle shading further back.
    behind = np.clip(-X - 0.5 * L, 0, None)
    eta *= 1.0 / (1.0 + behind / (1.5 * L))

    # ---- foam sources ----------------------------------------------------------
    gy, gx = np.gradient(eta, dx)
    slope = np.hypot(gx, gy)
    sm = lambda a, lo, hi: np.clip((a - lo) / (hi - lo), 0, 1) ** 2 * (3 - 2 * np.clip((a - lo) / (hi - lo), 0, 1))
    bow_white = sm(Zb, 0.5, 3.0)
    # breaking crest: high AND steep (both soft)
    src_break = sm(eta / Zb, 0.5, 0.9) * sm(slope, 0.2, 0.4)  # front face of the crest only
    # hull sheet via true distance to the waterline, soft, strongest forward
    d_out = distance_transform_edt(m < 0.5) * dx
    along = sm((X / L) + 0.5, 0.3, 1.0)
    src_hull = np.exp(-(d_out / (0.04 * B + 1.5 * dx)) ** 2) * (m < 0.5) * along * bow_white * (np.abs(X) < 0.55 * L)
    # stern-crest breaking grows with speed: weak at Fr_L~0.3 (battleship), full by ~0.65 (FAC)
    FrL = U / np.sqrt(G * L)
    aft_w = float(np.clip(0.3 + 2.0 * (FrL - 0.3), 0.3, 1.0))
    w_break = aft_w + (1 - aft_w) * sm(X / L, -0.45, -0.15)  # 1 along the forward/mid body
    # Breaking is a NEAR-HULL phenomenon. The linear Kelvin arms keep their steepness far out, but
    # real divergent waves of a displacement ship do not whitecap there (calm sea): limit breaking to a
    # band around the hull whose width grows only for fast/small craft (FAC whitewater is wide).
    band = B * (0.5 + 2.0 * max(FrL - 0.5, 0.0))      # Fletcher 35 kn ~0.6 B, FAC 30 kn ~1.0 B
    w_near = np.exp(-(d_out / band) ** 2)
    src_fresh = np.clip(np.maximum(src_break * w_break * w_near * bow_white * 1.2, src_hull), 0, 1).astype(np.float32)

    # transom wash
    s_aft = -0.5 * L - X
    src_turb = (sm(s_aft, 0, 2 * dx) * (s_aft < 3 * dx) * np.exp(-(Y / (0.3 * B * np.sqrt(wash))) ** 2)
                * min(U / 10, 1) * 0.8 * wash).astype(np.float32)
    ramp = sm(s_aft, 0, 0.6 * B)  # wash whitens over the first ~0.6 B (dead-water hollow at transom)

    # ---- advect along streamlines: march bow -> stern ---------------------------
    ux = -U + u  # ship frame: water flows -x
    slope_y = (v / np.minimum(ux, -0.2 * U)) * (-1)  # dy per unit -dx travelled
    slope_y = np.clip(slope_y, -1.0, 1.0)
    # potential-flow steering only around the forward/mid body; aft of that the stern sink makes
    # streamlines converge (transom 'lens' artifact) -> fade lateral steering to 0 by the stern.
    slope_y = slope_y * sm(X / L, -0.5, -0.2)
    # outward-only steering: along the run the flow closes in toward the hull; following it pushes
    # the bow foam INTO the hull mask where it vanishes (hard cut-off at the shoulder).
    slope_y = np.where(slope_y * np.sign(Y) > 0, slope_y, 0.0)
    rows = np.arange(ny, dtype=np.float32)
    fresh = np.zeros((ny, nx), np.float32)
    resid = np.zeros((ny, nx), np.float32)
    turb = np.zeros((ny, nx), np.float32)
    a = np.zeros(ny, np.float32); r = np.zeros(ny, np.float32); b = np.zeros(ny, np.float32)
    df, dr, dtb = (np.exp(-dx / (U * t)) for t in (tau_fresh, tau_resid, tau_turb))
    for i in range(nx - 1, -1, -1):
        # backtrace: value at row j in column i came from row j - slope*1 in column i+1
        src_rows = rows - slope_y[:, i]
        a = np.interp(src_rows, rows, a); r = np.interp(src_rows, rows, r)  # wash is not steered
        # residual = a share of the whitewater that decays this step (resolution independent)
        r = r * dr + resid_share * a * (1 - df)
        a = np.maximum(a * df, src_fresh[:, i])
        b = b * dtb + src_turb[:, i]
        fresh[:, i], resid[:, i], turb[:, i] = a, r, b
    # lateral diffusion with age, sigma ~ k*sqrt(B*age). Smooth: blur at a few sigma levels and
    # lerp per column between the two nearest levels (v2 used hard column bands -> visible steps).
    def age_blur(f, k, x0):
        age = np.clip(x0 - x, 0, None)
        sig = k * np.sqrt(B * (age + 1)) / dx                 # per column, in cells
        levels = np.geomspace(max(sig.min(), 0.3), max(sig.max(), 0.31), 8)
        stack = np.stack([gaussian_filter1d(f, s_, axis=0) for s_ in levels])
        t = np.interp(np.log(np.clip(sig, levels[0], levels[-1])), np.log(levels), np.arange(len(levels)))
        i0 = np.floor(t).astype(int).clip(0, len(levels) - 2)
        w = (t - i0)[None, :]
        cols = np.arange(nx)
        return stack[i0, :, cols].T * (1 - w) + stack[i0 + 1, :, cols].T * w
    resid = np.clip(age_blur(resid, 0.08, 0.5 * L), 0, 1)
    # Spreading conserves bubble 'mass', so a plain blur dims the core as it widens and the strip
    # vanishes after a few hundred metres. Visually a big ship's wake stays a stable white lane for
    # minutes: keep most of the pre-blur peak (exponent 0.75 = mostly whiteness-preserving).
    pre = turb.max(axis=0)
    turb = age_blur(turb, 0.10, -0.5 * L)
    post = np.maximum(turb.max(axis=0), 1e-6)
    turb *= np.where(pre > 1e-4, (pre / post) ** 0.75, 1.0)[None, :]
    turb = np.clip(turb, 0, 1.5) * ramp
    t_total = time.perf_counter() - t0
    info = dict(nx=nx, ny=ny, dx=dx, t_fft=t_fft, t_total=t_total, Zb=Zb, FrL=FrL,
                FrD=FrD, lam_t=lam)
    return x, y, eta, dict(fresh=fresh * (1 - m), resid=resid * (1 - m), turb=turb * (1 - m)), m, (u, v), info