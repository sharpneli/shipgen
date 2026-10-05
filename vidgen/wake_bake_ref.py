"""Prototype: steady ship-frame wake bake via FFT (linear pressure-patch / Havelock model).

Ship moves +x (bow +x, project convention). Output in ship frame:
  eta  : surface elevation [m]
  foam : 0..1 foam density (breaking crests + bow/hull-side + turbulent centre wake, advected & decayed)
"""
import time
import numpy as np
from scipy import fft as sfft
from scipy.ndimage import gaussian_filter

G = 9.81


def planform(X, Y, L, B, n_fore=1.7, n_aft=5.0):
    """1 inside the waterplane, 0 outside. Fine bow (n_fore small), full stern."""
    xi = 2 * X / L  # -1 stern .. +1 bow
    n = np.where(xi > 0, n_fore, n_aft)
    half = 0.5 * B * np.clip(1 - np.abs(xi) ** n, 0, None)
    half = np.where(np.abs(xi) <= 1, half, 0)
    return ((np.abs(Y) <= half) & (half > 0)).astype(np.float32), half


def deck_planform(X, Y, L, B, n_fore=1.7, n_aft=5.0, *, bow_overhang=0.03, stern_overhang=0.01,
                  flare=1.08, deck_fullness=0.85):
    """Top-of-hull silhouette (what the sprite shows), drawn OVER the wake.

    Bigger than the waterline: the stem rakes forward (bow_overhang * L ahead of the WL stem),
    the stern overhangs (stern_overhang * L), and flare/knuckles widen the deck (flare * B).
    Flare is strongest forward, so the deck bow is fuller (n_fore * deck_fullness).
    The wake bake itself always uses the waterline planform.
    """
    x_bow = 0.5 * L + bow_overhang * L
    x_stern = -0.5 * L - stern_overhang * L
    Ld = x_bow - x_stern
    Xc = X - 0.5 * (x_bow + x_stern)
    return planform(Xc, Y, Ld, B * flare, n_fore * deck_fullness, n_aft)


def bake(L, B, T, U, *, n_fore=1.7, n_aft=5.0, entrance_deg=12.0, tau_crest=8.0, tau_turb=45.0,
         wash=1.0, max_cells=1024, damp=0.08):
    """wash: propulsor turbulence multiplier (1 = twin screws, ~2 = waterjets / high-power craft)."""
    t0 = time.perf_counter()
    lam = 2 * np.pi * U ** 2 / G
    span = max(L, lam)
    ahead_m, behind_m = 0.5 * L + 0.6 * span, 0.5 * L + 4.0 * span
    halfw_m = 0.45 * behind_m + B
    dx = max(L / 80, (ahead_m + behind_m) / max_cells)
    x = np.arange(-behind_m, ahead_m, dx, dtype=np.float32)
    y = np.arange(-halfw_m, halfw_m, dx, dtype=np.float32)
    nx, ny = sfft.next_fast_len(len(x)), sfft.next_fast_len(len(y))
    x = x[0] + dx * np.arange(nx, dtype=np.float32)
    y = y[0] + dx * np.arange(ny, dtype=np.float32)
    X, Y = np.meshgrid(x, y)  # [ny, nx]

    m, half = planform(X, Y, L, B, n_fore, n_aft)
    m_s = gaussian_filter(m, sigma=max(1.0, B / 5 / dx))  # smoothed pressure patch

    # --- linear wave response in Fourier space ---------------------------------
    kx = 2 * np.pi * sfft.fftfreq(nx, dx).astype(np.float32)
    ky = 2 * np.pi * sfft.fftfreq(ny, dx).astype(np.float32)
    KX, KY = np.meshgrid(kx, ky)
    K = np.sqrt(KX ** 2 + KY ** 2)
    eps = damp * G / max(U, 0.1)  # Rayleigh damping -> radiation condition (waves trail behind)
    D = G * K - (U * KX) ** 2 - 1j * eps * U * KX
    D[0, 0] = 1.0
    Mh = sfft.fft2(m_s, workers=-1)
    H = -G * T * K * Mh / D
    H[0, 0] = 0
    eta = sfft.ifft2(H, workers=-1).real.astype(np.float32)
    # Fix sign of radiation condition automatically: waves must be behind the bow.
    if np.abs(eta[:, X[0] > 0.8 * L]).mean() > np.abs(eta[:, X[0] < -1.5 * L]).mean():
        D = G * K - (U * KX) ** 2 + 1j * eps * U * KX
        D[0, 0] = 1.0
        H = -G * T * K * Mh / D
        H[0, 0] = 0
        eta = sfft.ifft2(H, workers=-1).real.astype(np.float32)
    t_fft = time.perf_counter() - t0

    # --- amplitude calibration: pin the bow crest to Noblesse's analytical height ---------
    beta = np.radians(entrance_deg)
    FrD = U / np.sqrt(G * T)
    Zb = 2.2 * U ** 2 / G * np.tan(beta) / (np.cos(beta) * (1 + FrD))
    near_bow = (X > 0) & (X < 0.5 * L + 0.1 * span) & (np.abs(Y) < B + 0.1 * L) & (m < 0.5)
    eta *= Zb / max(np.percentile(eta[m < 0.5], 99.9), 1e-3)
    eta *= (1 - m)  # hull interior irrelevant for rendering
    # soft taper toward domain edges (hides FFT wrap)
    tx = np.clip((X - X.min()) / (0.15 * (X.max() - X.min())), 0, 1)
    ty = np.clip((Y.max() - np.abs(Y)) / (0.15 * Y.max()), 0, 1)
    eta *= (tx * ty) ** 2

    # --- foam sources ---------------------------------------------------------
    gy, gx = np.gradient(eta, dx)
    slope = np.hypot(gx, gy)
    s_break = 0.30  # crest slope at which whitecapping starts (tunable, ~ Stokes limit 0.44 rad)
    src_crest = np.clip((slope - s_break) / s_break, 0, 1) * (eta > 0.3 * Zb)

    # hull-side white water: thin sheet hugging the forward hull, fading aft
    d_out = np.abs(Y) - half
    xi = 2 * X / L
    on_hull = (np.abs(xi) <= 1) & (d_out > -dx) & (d_out < max(1.5 * dx, 0.08 * B))
    along = np.clip((xi + 1) / 2, 0, 1)  # 0 stern .. 1 bow
    bow_white = np.clip((Zb - 0.5) / 2.5, 0, 1)  # starts whitening around Zb ~ 0.5 m
    src_hull = on_hull * bow_white * along ** 3

    # bow-wave "peel": the breaking crest leaves the hull at the shoulder and runs outward
    FrL = U / np.sqrt(G * L)
    theta_k = np.radians(19.47)
    theta = min(theta_k, 0.16 / max(FrL, 1e-3)) if FrL > 0.45 else theta_k  # Rabaud-Moisy narrowing
    theta = max(theta, beta + np.radians(4))
    x_sh = 0.5 * L - 0.15 * L  # shoulder (where the bow crest detaches)
    peel_len = (1.2 + 2.3) * U ** 2 / G * 0.35 * bow_white + 0.15 * L  # ~ Noblesse X0 scale, tunable
    s_back = x_sh - X
    y_line = 0.5 * B * 0.9 + s_back * np.tan(theta)
    w_line = 0.6 * dx + 0.04 * B + 0.02 * np.clip(s_back, 0, None)
    src_peel = ((s_back > -0.12 * L) & (s_back < peel_len)) * np.exp(-((np.abs(Y) - y_line) / w_line) ** 2)
    src_peel *= bow_white * np.clip(1 - s_back / peel_len, 0, 1) ** 0.5
    src_hull = np.maximum(src_hull, src_peel)

    # turbulent / propulsor centre wake injected at the transom
    s_aft = -0.5 * L - X
    w0 = 0.40 * B
    src_turb = ((s_aft > 0) & (s_aft < 2 * dx)) * np.exp(-(Y / w0) ** 2)
    src_turb = src_turb * np.clip(U / 10.0, 0, 1) * 0.8 * wash

    # advect + decay in ship frame (water moves -x at U). Crest foam dies fast, bubbly wake slowly.
    dc = np.exp(-dx / (U * tau_crest))
    dt_ = np.exp(-dx / (U * tau_turb))
    crest = np.zeros_like(src_crest)
    turb = np.zeros_like(src_crest)
    a = np.zeros(ny, np.float32)
    b = np.zeros(ny, np.float32)
    src_c = np.maximum(src_crest, src_hull)
    sig_step = None
    for i in range(nx - 1, -1, -1):  # bow -> stern
        a = np.maximum(a * dc, src_c[:, i])
        b = b * dt_ + src_turb[:, i]
        crest[:, i] = a
        turb[:, i] = b
    # lateral spreading of the turbulent wake ~ sqrt(age): blur columns with growing sigma (banded)
    age_m = np.clip(s_aft[0], 0, None)
    out = turb.copy()
    for lo in np.arange(0, age_m.max() + 1, max(dx, 0.25 * span)):
        cols = (age_m >= lo) & (age_m < lo + max(dx, 0.25 * span))
        if cols.any():
            sig = (0.15 * np.sqrt(B * (lo + 1)) ) / dx
            blurred = gaussian_filter(turb[:, cols], sigma=(sig, 0))
            out[:, cols] = blurred * (turb[:, cols].sum(0) / np.maximum(blurred.sum(0), 1e-6))
    turb = np.clip(out, 0, 1.5)
    foam = np.clip(np.maximum(crest, turb), 0, 1) * (1 - m)
    t_total = time.perf_counter() - t0
    info = dict(nx=nx, ny=ny, dx=dx, t_fft=t_fft, t_total=t_total, Zb=Zb,
                FrL=U / np.sqrt(G * L), FrD=FrD, lam_t=lam)
    info["L"], info["B"], info["n_fore"], info["n_aft"] = L, B, n_fore, n_aft
    return x, y, eta, foam, m, info


def value_noise(shape, scale, seed=0):
    rng = np.random.default_rng(seed)
    out = np.zeros(shape, np.float32)
    amp, tot = 1.0, 0.0
    for octv in range(4):
        s = max(1, int(scale / 2 ** octv))
        small = rng.random((shape[0] // s + 2, shape[1] // s + 2)).astype(np.float32)
        from scipy.ndimage import zoom
        up = zoom(small, s, order=1)[: shape[0], : shape[1]]
        out += amp * up
        tot += amp
        amp *= 0.5
    return out / tot


def render(x, y, eta, foam, hull, dx, sun=(-0.4, 0.6, 0.7), shadow_px=(2, -2)):
    gy, gx = np.gradient(eta, dx)
    n = np.stack([-gx * 2.5, -gy * 2.5, np.ones_like(eta)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    s = np.array(sun) / np.linalg.norm(sun)
    lit = np.clip(n @ s, 0, 1)
    deep = np.array([0.05, 0.16, 0.30])
    shallow = np.array([0.18, 0.38, 0.55])
    col = deep + (shallow - deep) * ((lit - 0.6) * 2.2 + 0.4)[..., None]
    from scipy.ndimage import zoom
    nz0 = value_noise((eta.shape[0], eta.shape[1] // 4 + 1), 5)
    nz = zoom(nz0, (1, 4), order=1)[:, : eta.shape[1]]  # streaky along the track
    f = np.clip((foam - (1 - nz) * 0.95) / 0.2, 0, 1)  # noise-broken foam
    f = np.maximum(f * 0.9, np.clip(foam - 0.9, 0, 1) * 8)  # solid core only where very dense
    f = np.clip(f, 0, 1)[..., None]
    col = col * (1 - f) + np.array([0.92, 0.95, 0.97]) * f
    if shadow_px:  # soft drop shadow of the deck edge onto water/foam
        sh = np.roll(hull, shadow_px, axis=(0, 1))
        sh = gaussian_filter(sh.astype(np.float32), 1.5)
        col = col * (1 - 0.35 * sh[..., None])
    col = np.where(hull[..., None] > 0.5, np.array([0.22, 0.24, 0.22]), col)
    return (np.clip(col, 0, 1) * 255).astype(np.uint8)