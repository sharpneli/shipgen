"""
Steady ship-frame wake bake for vidgen: wake_bake_ref.py (v2.2 of wake.md) ported to numpy without scipy.

The hull is a thin-ship source sheet q = U dm/dx on the waterplane (+ at the entrance, - along the run), attenuated
over the draught. One FFT solves the linearised steady free surface for its perturbation potential phi; eta ~ phi_x
gives the divergent-wave shading and the bow crest, and the same spectrum gives the surface velocity. Three foam
densities are advected bow to stern along the streamlines of that flow:
- `fresh`: whitewater from the breaking front face of the crest (near the hull only) and the hull sheet, max-combined
  with a short life;
- `resid`: residual foam fed by the share of whitewater that decays each step, long-lived, spreading with age;
- `wash`: the propulsor's bubbly wake from the transom, a stable lane that widens slowly and keeps its whiteness.
vidgen bakes once per clip, so a ship's heading and speed must stay fixed.

Departures from wake_bake_ref.py, for a visualiser and for numpy:
- The waterline is the exported deck outline shrunk by an assumed overhang and flare (`waterline`), because
  shipgen exports only the deck edge (wake.md 3.2 item 7), and it is rasterised from that polygon, not from the
  analytic fore/aft exponents.
- The entrance angle comes from the block coefficient (`8 + (Cb - 0.45) * 50` deg, capped at 30).
- The FFT runs on the reference's padded domain (grown to cover the frame if that is bigger), at half the reference's step (capped at ~3M cells).
  Everything after it runs on a fine grid that covers only the frame: eta, its slopes and the velocity are
  resampled bicubically. The slopes are taken spectrally, not by differencing the masked eta.
- Gaussian blurs are applied in the spectrum (the smoothing of m and of the velocity) or by a padded 1-D FFT (the
  age blur). The distance to the waterline is the exact distance to the polygon, near the hull only (no EDT).
- The reference's resolution-tied widths (the hull band's 1.5 dx, the smoothing of m) use the reference's own grid
  step, so the look doesn't change with the frame's zoom.
"""
from __future__ import annotations

import math
import time

import numpy as np
from PIL import Image, ImageDraw

G = 9.81


def sm(a, lo, hi):
    t = np.clip((np.asarray(a, np.float32) - lo) / (hi - lo), 0, 1)
    return t * t * (3 - 2 * t)


def waterline(deck, style, L):
    """The waterline outline guessed from the deck edge (ship-local metres, (n, 2)): the stem rakes and the stern
    overhangs past the waterline, and flare widens the deck (wake.md §3.2 item 7, prototype values)."""
    bow, stern, flare = {"planing": (0.06, 0.0, 1.12), "merchant": (0.02, 0.01, 1.02)}.get(style, (0.03, 0.01, 1.05))
    xb, xs = deck[:, 0].max(), deck[:, 0].min()
    nb, ns = xb - bow * L, xs + stern * L
    x = ns + (deck[:, 0] - xs) * (nb - ns) / (xb - xs)
    return np.stack([x, deck[:, 1] / flare], 1)


def half_breadth(poly, x):
    """The polygon's largest |y| at each x (0 outside it)."""
    a, b = poly, np.roll(poly, -1, 0)
    lo, hi = np.minimum(a[:, 0], b[:, 0]), np.maximum(a[:, 0], b[:, 0])
    t = (x[None, :] - a[:, 0:1]) / np.where(b[:, 0] == a[:, 0], 1, b[:, 0] - a[:, 0])[:, None]
    yy = np.abs(a[:, 1:2] + t * (b[:, 1] - a[:, 1])[:, None])
    yy = np.where((x[None, :] >= lo[:, None]) & (x[None, :] <= hi[:, None]), yy, 0)
    return yy.max(0).astype(np.float32)


def coverage(poly, x0, y0, dx, nx, ny, ss=4):
    """Anti-aliased waterplane coverage 0..1 on the grid x0 + i*dx, y0 + j*dx (ss x ss supersampling), so the
    sharp stem has no staircase to ring in the FFT."""
    im = Image.new("L", (nx * ss, ny * ss), 0)
    ImageDraw.Draw(im).polygon([(((px - x0) / dx + 0.5) * ss, ((py - y0) / dx + 0.5) * ss) for px, py in poly],
                               fill=255)
    return np.asarray(im, np.float32).reshape(ny, ss, nx, ss).mean((1, 3)) / 255


def dist_out(poly, x, y, reach):
    """Distance (m) from each grid point to the polygon's edge, within `reach` of the hull (inf further out)."""
    d = np.full((len(y), len(x)), np.inf, np.float32)
    cx = np.nonzero((x > poly[:, 0].min() - reach) & (x < poly[:, 0].max() + reach))[0]
    cy = np.nonzero(np.abs(y) < np.abs(poly[:, 1]).max() + reach)[0]
    if not len(cx) or not len(cy):
        return d
    px, py = np.meshgrid(x[cx], y[cy])
    best = np.full(px.shape, np.inf, np.float32)
    for a, b in zip(poly, np.roll(poly, -1, 0)):
        e = b - a
        ll = float(e @ e)
        if ll == 0:
            continue
        t = np.clip(((px - a[0]) * e[0] + (py - a[1]) * e[1]) / ll, 0, 1)
        np.minimum(best, (px - a[0] - t * e[0]) ** 2 + (py - a[1] - t * e[1]) ** 2, out=best)
    d[cy[0]:cy[-1] + 1, cx[0]:cx[-1] + 1] = np.sqrt(best)
    return d


def age_blur(f, sig):
    """Blur each column of f along y by its own sigma (cells): a few gaussian levels via a padded 1-D FFT,
    lerped per column between the two nearest (hard column bands showed as steps in the width)."""
    ny = f.shape[0]
    levels = np.geomspace(max(float(sig.min()), 0.3), max(float(sig.max()), 0.31), 8)
    pad = int(min(4 * levels[-1] + 2, 2 * ny))
    n = ny + 2 * pad
    F = np.fft.rfft(np.pad(f, ((pad, pad), (0, 0))), axis=0)
    k = 2 * math.pi * np.fft.rfftfreq(n)
    t = np.interp(np.log(np.clip(sig, levels[0], levels[-1])), np.log(levels), np.arange(len(levels)))
    out = np.zeros_like(f)
    for i, s in enumerate(levels):
        w = np.clip(1 - np.abs(t - i), 0, 1).astype(np.float32)
        if w.any():
            out += np.fft.irfft(F * np.exp(-0.5 * (k * s) ** 2)[:, None], n, axis=0)[pad:pad + ny].astype(np.float32) * w
    return out


class Bake:
    """The baked fields on a grid in ship-local metres: column i is x0 + i*dx (bow +x), row j is y0 + j*dx (+y
    starboard)."""


def bake(wl, B, T, U, extent, dx, *, cb=0.55, wash=1.0, tau_fresh=3.0, tau_resid=15.0, tau_turb=45.0,
         resid_share=0.5, damp=0.08, max_cells=3.0e6):
    """wl: waterline polygon (n, 2), B beam, T draught, U speed (m/s), extent (xmin, xmax, ymax) the ship-local
    box that must be covered, dx grid step (m)."""
    t0 = time.perf_counter()
    U, T = max(U, 0.5), max(T, 0.3)
    xb, xs = float(wl[:, 0].max()), float(wl[:, 0].min())
    L = xb - xs
    xm = 0.5 * (xb + xs)                               # the reference's origin: midships of the waterline
    lam = 2 * math.pi * U * U / G
    span = max(L, lam)
    FrL = U / math.sqrt(G * L)
    FrD = U / math.sqrt(G * T)
    beta = math.radians(float(np.clip(8 + (cb - 0.45) * 50, 6, 30)))  # entrance half-angle from fullness
    Zb = 2.2 * U * U / G * math.tan(beta) / (math.cos(beta) * (1 + FrD))   # Noblesse bow-wave height
    ahead, behind = 0.5 * L + 0.6 * span, 0.5 * L + 4.0 * span
    d_ref = max(L / 80, (ahead + behind) / 1024)      # the reference's grid step, for its resolution-tied widths

    # ---- solve grid: the reference's padded domain, grown to the frame ----------------------------------------
    X0 = min(xm - behind, extent[0] - 0.1 * span)
    X1 = max(xm + ahead, extent[1] + 0.1 * span)
    YH = max(0.45 * behind + B, extent[2] + 0.1 * span)
    # the source is smoothed at the reference's scale, so half its step resolves everything (the slopes stay smooth
    # when resampled bicubically)
    dxs = max(dx, 0.5 * d_ref, math.sqrt((X1 - X0) * 2 * YH / max_cells))
    sx, sy = int(math.ceil((X1 - X0) / dxs)) // 2 * 2 + 2, int(math.ceil(2 * YH / dxs)) // 2 * 2 + 2
    xg = X0 + dxs * np.arange(sx)
    yg = -YH + dxs * np.arange(sy)
    cov = coverage(wl, X0, -YH, dxs, sx, sy)

    kx = 2 * math.pi * np.fft.rfftfreq(sx, dxs)
    ky = 2 * math.pi * np.fft.fftfreq(sy, dxs)
    KX, KY = np.meshgrid(kx, ky)
    K = np.sqrt(KX * KX + KY * KY)
    K[0, 0] = 1e-6

    def gauss(sig_m):
        return np.exp(-0.5 * (K * sig_m) ** 2)
    # light smoothing, at the reference's grid scale: a finer grid resolves very short divergent waves (the source
    # sheet's sharp stem excites them) that the reference never had, and they showed as fine straight streaks
    Q = U * 1j * KX * np.fft.rfft2(cov) * gauss(max(0.75 * d_ref, 0.04 * B))
    QA = -G * Q * (1 - np.exp(-K * T)) / K            # source sheet over the draught
    eps = damp * G / U

    def solve(sign):
        Phi = QA / (G * K - (U * KX) ** 2 + sign * 1j * eps * U * KX)
        Phi[0, 0] = 0
        return Phi
    Phi = solve(-1)
    eta = np.fft.irfft2(1j * KX * Phi, s=(sy, sx))    # eta ~ phi_x (Bernoulli, linear)
    if np.abs(eta[:, xg > xb + 0.2 * span]).mean() > np.abs(eta[:, xg < xs - span]).mean():
        Phi = solve(+1)                               # waves on the wrong side: flip the radiation condition
        eta = np.fft.irfft2(1j * KX * Phi, s=(sy, sx))
    stem = (np.abs(xg - xb) < 0.05 * L)[None, :] & (np.abs(yg) < B)[:, None]
    if eta[stem].max() < -eta[stem].min():            # the crest at the stem must be positive
        Phi, eta = -Phi, -eta
    Zcal = float(eta[stem & (cov < 0.5)].max())
    cal = Zb / max(Zcal, 1e-9)
    # slopes and velocity from the same spectrum; u' = g eta / U. Linear theory blows up at the waterline edges and
    # foam only needs the gentle outer flow: smoothed over ~B/4 and clamped (the sheet leaves at ~ the entrance angle)
    gxs = np.fft.irfft2(-KX * KX * Phi, s=(sy, sx)) * cal
    gys = np.fft.irfft2(-KX * KY * Phi, s=(sy, sx)) * cal
    Ps = Phi * gauss(0.25 * B) * (cal * G / U)
    us = np.fft.irfft2(1j * KX * Ps, s=(sy, sx))
    vs = np.fft.irfft2(1j * KY * Ps, s=(sy, sx))
    if np.mean(vs[stem] * np.sign(np.broadcast_to(yg[:, None], vs.shape)[stem])) < 0:
        vs = -vs                                      # v must push water away from the centreline at the entrance
    v_max = math.tan(beta + math.radians(4)) * U
    us, vs = np.clip(us, -0.3 * U, 0.3 * U), np.clip(vs, -v_max, v_max)
    eta *= cal
    tx = np.clip((xg - X0) / (0.15 * (X1 - X0)), 0, 1)[None, :]
    ty = np.clip((YH - np.abs(yg)) / (0.15 * YH), 0, 1)[:, None]
    taper = (tx * ty) ** 2                            # edge taper against the FFT's wrap
    t_fft = time.perf_counter() - t0

    # ---- the fine grid over the frame -------------------------------------------------------------------------
    x0, x1, yh = extent
    nx, ny = int(math.ceil((x1 - x0) / dx)), int(math.ceil(2 * yh / dx))
    x = (x0 + dx * np.arange(nx)).astype(np.float32)
    y = (-yh + dx * np.arange(ny)).astype(np.float32)
    k = dx / dxs

    def resample(a, how=Image.BICUBIC):
        return np.asarray(Image.fromarray(np.ascontiguousarray(a, np.float32), "F").transform(
            (nx, ny), Image.AFFINE, (k, 0, (x0 - X0) / dxs + 0.5 - 0.5 * k, 0, k, (YH - yh) / dxs + 0.5 - 0.5 * k),
            resample=how))   # PIL maps pixel centres: the 0.5 - 0.5 k lines grid points up
    m = coverage(wl, x0, -yh, dx, nx, ny)
    # far-field readability: the linear Kelvin arms stay crisp for many L; fade with distance astern (~1/r) so the
    # V reads near the ship and becomes subtle shading further back
    fade = (1.0 / (1.0 + np.clip(xs - x, 0, None) / (1.5 * L)))[None, :]
    eta = resample(eta * taper) * fade
    gx, gy = resample(gxs * taper) * fade, resample(gys * taper) * fade
    u, v = resample(us, Image.BILINEAR), resample(vs, Image.BILINEAR)
    Xr = ((x - xm) / L)[None, :]                     # the reference's X / L
    Y = y[:, None]

    # ---- foam sources -----------------------------------------------------------------------------------------
    slope = np.hypot(gx, gy)
    bow_white = float(sm(Zb, 0.5, 3.0))
    src_break = sm(eta / Zb, 0.5, 0.9) * sm(slope, 0.2, 0.4)          # front face of the crest only
    band = B * (0.5 + 2.0 * max(FrL - 0.5, 0.0))      # breaking is near the hull: ~0.6 B for a fast destroyer
    hull_w = 0.04 * B + 1.5 * d_ref
    d_out = dist_out(wl, x, y, 3 * max(band, hull_w))
    out = m < 0.5
    along = sm(Xr + 0.5, 0.3, 1.0)
    src_hull = np.exp(-(d_out / hull_w) ** 2) * out * along * bow_white * (np.abs(Xr) < 0.55)
    aft_w = float(np.clip(0.3 + 2.0 * (FrL - 0.3), 0.3, 1.0))         # stern-crest breaking grows with speed
    w_break = aft_w + (1 - aft_w) * sm(Xr, -0.45, -0.15)
    w_near = np.exp(-(d_out / band) ** 2)
    src_fresh = np.clip(np.maximum(src_break * w_break * w_near * bow_white * 1.2, src_hull), 0, 1).astype(np.float32)

    s_aft = xs - x[None, :]                           # transom wash, over the first few columns behind it
    src_turb = (sm(s_aft, 0, 2 * dx) * (s_aft < 3 * dx) * np.exp(-(Y / (0.3 * B * math.sqrt(wash))) ** 2)
                * min(U / 10, 1) * 0.8 * wash).astype(np.float32)
    ramp = sm(s_aft, 0, 0.6 * B)                      # whitens over ~0.6 B (dead-water hollow at the transom)

    # ---- advect along streamlines, bow -> stern ---------------------------------------------------------------
    slope_y = np.clip(-v / np.minimum(-U + u, -0.2 * U), -1.0, 1.0)     # dy per unit -dx travelled
    slope_y *= sm(Xr, -0.5, -0.2)                     # no steering aft: the stern sink would focus foam (a lens)
    slope_y = np.where(slope_y * np.sign(Y) > 0, slope_y, 0.0)          # outward only, else it runs into the hull
    rows = np.arange(ny, dtype=np.float32)
    fresh = np.empty((ny, nx), np.float32)
    resid = np.empty((ny, nx), np.float32)
    turb = np.empty((ny, nx), np.float32)
    a = np.zeros(ny, np.float32)
    r = np.zeros(ny, np.float32)
    bb = np.zeros(ny, np.float32)
    df, dr, dtb = (math.exp(-dx / (U * t)) for t in (tau_fresh, tau_resid, tau_turb))
    for i in range(nx - 1, -1, -1):
        src_rows = rows - slope_y[:, i]
        a, r = np.interp(src_rows, rows, a), np.interp(src_rows, rows, r)   # the wash is not steered
        r = r * dr + resid_share * a * (1 - df)       # residual = the share of whitewater decaying this step
        a = np.maximum(a * df, src_fresh[:, i])
        bb = bb * dtb + src_turb[:, i]
        fresh[:, i], resid[:, i], turb[:, i] = a, r, bb
    # lateral spreading with age, sigma ~ k sqrt(B age)
    resid = np.clip(age_blur(resid, 0.08 * np.sqrt(B * (np.clip(xb - x, 0, None) + 1)) / dx), 0, 1)
    # a plain blur conserves bubble 'mass' and dims the lane as it widens; a big ship's wake stays a stable white
    # lane for minutes, so keep most of the pre-blur peak
    pre = turb.max(axis=0)
    turb = age_blur(turb, 0.10 * np.sqrt(B * (np.clip(xs - x, 0, None) + 1)) / dx)
    post = np.maximum(turb.max(axis=0), 1e-6)
    turb *= np.where(pre > 1e-4, (pre / post) ** 0.75, 1.0)[None, :]
    turb = np.clip(turb, 0, 1.5) * ramp

    b = Bake()
    b.x0, b.y0, b.dx, b.nx, b.ny = float(x0), float(-yh), dx, nx, ny
    b.eta, b.gx, b.gy, b.mask = eta, gx, gy, m
    b.fresh, b.resid, b.wash = fresh * (1 - m), resid * (1 - m), turb * (1 - m)
    b.info = dict(solve=(sx, sy), dx_solve=dxs, L=L, U=U, FrL=FrL, FrD=FrD, Zb=Zb, lam=lam,
                  entrance_deg=math.degrees(beta), grid=(nx, ny), dx=dx, t_fft=t_fft,
                  t_total=time.perf_counter() - t0)
    return b
