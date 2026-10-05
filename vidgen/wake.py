"""
Steady ship-frame wake bake for vidgen (after wake.md and wake_bake_ref.py, ported to numpy without scipy).

One FFT solves the linearised free surface under a moving pressure patch, the ship's waterplane (Havelock /
Darmon et al.). The surface height eta gives the divergent-wave shading. Two foam densities are advected bow to
stern and decayed: `crest` (breaking crests, the bow-wave sheet on the hull and the peel line off the shoulder;
it dies within a ship length or so) and `wash` (the propulsor's bubbly wake from the transom; long-lived, spreading
with age). vidgen bakes once per clip, so a ship's heading and speed must stay fixed.

Departures from wake.md, all for a visualiser:
- The waterline is the exported deck outline shrunk by an assumed overhang and flare (`waterline`), because
  shipgen exports only the deck edge. wake.md §3.2 item 7 asks shipgen for a real waterline outline.
- The domain covers the frame plus about one wavelength behind the stern (not 4 spans), so the grid can be fine
  enough to show the near-hull field at screen resolution.
- The entrance angle comes from the block coefficient, and the wash multiplier from the style (planing craft 2x).
- Semi-planing hulls (Fr_L > 0.6) get the stylised chine whiskers of wake.md §4 and a smaller bow sheet.
"""
from __future__ import annotations

import math
import time

import numpy as np
from PIL import Image, ImageDraw

G = 9.81
KELVIN = math.radians(19.47)


def blur_axis(a, r, axis, passes=3):
    """Separable 3-pass box blur along one axis (sigma^2 ~ r(r+1)), edges clamped."""
    if r < 1:
        return a
    n = a.shape[axis]
    for _ in range(passes):
        p = np.pad(a, [(r + 1, r) if ax == axis else (0, 0) for ax in range(a.ndim)], mode="edge")
        c = np.cumsum(p, axis=axis, dtype=np.float32)
        a = (np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
             - np.take(c, np.arange(0, n), axis=axis)) / (2 * r + 1)
    return a


def blur(a, r):
    return blur_axis(blur_axis(a, r, 0), r, 1)


def waterline(deck, style, L):
    """The waterline outline guessed from the deck edge (ship-local metres, (n, 2)): the stem rakes and the stern
    overhangs past the waterline, and flare widens the deck (wake.md §3.2 item 7, prototype values)."""
    bow, stern, flare = {"planing": (0.06, 0.0, 1.12), "merchant": (0.02, 0.01, 1.02)}.get(style, (0.03, 0.01, 1.05))
    xb, xs = deck[:, 0].max(), deck[:, 0].min()
    nb, ns = xb - bow * L, xs + stern * L
    x = ns + (deck[:, 0] - xs) * (nb - ns) / (xb - xs)
    return np.stack([x, deck[:, 1] / flare], 1)


def raster(poly, x0, y0, dx, nx, ny):
    im = Image.new("L", (nx, ny), 0)
    ImageDraw.Draw(im).polygon([((px - x0) / dx, (py - y0) / dx) for px, py in poly], fill=255)
    return np.asarray(im, np.float32) / 255


class Bake:
    """The baked fields on a grid in ship-local metres: column i is x0 + i*dx (bow +x), row j is y0 + j*dx (+y
    starboard)."""


def bake(wl, B, T, U, extent, dx, *, cb=0.55, wash=1.0, tau_crest=5.0, tau_wash=45.0, damp=0.08):
    """wl: waterline polygon (n, 2), B beam, T draught, U speed (m/s), extent (xmin, xmax, ymax) the ship-local
    box that must be covered, dx grid step (m)."""
    t0 = time.perf_counter()
    U = max(U, 0.5)
    xb, xs = wl[:, 0].max(), wl[:, 0].min()
    L = xb - xs
    lam = 2 * math.pi * U * U / G
    span = max(L, lam)
    FrL = U / math.sqrt(G * L)
    FrD = U / math.sqrt(G * max(T, 0.3))
    beta = math.radians(np.clip(8 + (cb - 0.45) * 50, 6, 30))      # entrance half-angle from fullness
    Zb = 2.2 * U * U / G * math.tan(beta) / (math.cos(beta) * (1 + FrD))   # Noblesse bow-wave height
    plane = float(np.clip((FrL - 0.6) / 0.4, 0, 1))                 # semi-planing stylisation weight

    # the solve runs on a big, coarser grid: 3 spans behind and the Kelvin spread sideways, so the damped waves die
    # before they wrap round the FFT. The output grid covers only `extent`, at dx, with eta resampled onto it.
    X0, X1 = xs - 3 * span, xb + 0.6 * span
    YH = ((xb - X0) * math.tan(KELVIN) + B) * 1.2
    dxs = max(dx, math.sqrt((X1 - X0) * 2 * YH / 3.0e6))
    sx, sy = int(math.ceil((X1 - X0) / dxs)) // 2 * 2 + 2, int(math.ceil(2 * YH / dxs)) // 2 * 2 + 2
    ms = blur(raster(wl, X0, -YH, dxs, sx, sy), max(1, int(round(B / 5 / dxs))))

    # linear steady response: eta^ = -g T |k| m^ / (g|k| - U^2 kx^2 - i eps U kx); with numpy's FFT convention
    # this damping sign puts the waves behind the ship
    kx = 2 * math.pi * np.fft.rfftfreq(sx, dxs).astype(np.float32)
    ky = 2 * math.pi * np.fft.fftfreq(sy, dxs).astype(np.float32)
    KX, KY = np.meshgrid(kx, ky)
    K = np.sqrt(KX * KX + KY * KY)
    D = G * K - (U * KX) ** 2 - 1j * (damp * G) * KX
    D[0, 0] = 1
    H = -G * T * K * np.fft.rfft2(ms) / D
    H[0, 0] = 0
    big = np.fft.irfft2(H, s=(sy, sx)).astype(np.float32)
    t_fft = time.perf_counter() - t0
    Zcal = float(np.percentile(big[ms < 0.05], 99.9))

    x0, x1, yh = extent[0], extent[1], extent[2]
    nx, ny = int(math.ceil((x1 - x0) / dx)), int(math.ceil(2 * yh / dx))
    x = x0 + dx * np.arange(nx, dtype=np.float32)
    y = -yh + dx * np.arange(ny, dtype=np.float32)
    k = dx / dxs
    eta = np.asarray(Image.fromarray(big, "F").transform(
        (nx, ny), Image.AFFINE, (k, 0, (x0 - X0) / dxs, 0, k, (YH - yh) / dxs), resample=Image.BILINEAR))
    m = raster(wl, x0, -yh, dx, nx, ny)

    # calibrate the crest to Zb; the linear model overshoots at a full transom, so clamp the troughs
    eta = eta * (Zb / max(Zcal, 1e-3))
    eta = np.clip(eta, -1.5 * Zb, 1.5 * Zb)    # left whole under the hull: a cut there would be a cliff in the normals

    # foam sources
    gy, gx = np.gradient(eta, dx)
    slope = np.hypot(gx, gy)
    src_crest = 0.25 * np.clip((slope - 0.5) / 0.4, 0, 1) * (eta > 0.3 * Zb) * min(1.0, FrL / 0.25)
    half = np.abs(y)[:, None] * m
    half = half.max(0)                                   # waterline half-breadth per column
    d_out = np.abs(y)[:, None] - half[None, :]
    inl = half > 0
    along = np.clip((x - xs) / L, 0, 1)
    # a slow ship pushes a glassy cushion, not white water; a planing bow lifts out
    bow_white = float(np.clip((Zb - 0.5) / 2.5, 0, 1)) * min(1.0, FrL / 0.25) * (1 - 0.5 * plane)
    # the sheet thickens toward the stem, so it shows past the deck's overhang and flare
    band = np.maximum(1.5 * dx, (0.06 + 0.12 * along ** 4) * B)
    src_sheet = inl[None, :] * (d_out > -dx) * (d_out < band[None, :]) * bow_white * along[None, :] ** 3

    # the bow crest peels off the shoulder at the visible wake angle (narrowing as 1/Fr_L at high speed)
    theta = min(KELVIN, 0.16 / FrL) if FrL > 0.45 else KELVIN
    theta = max(theta, beta + math.radians(4))
    x_sh = xb - 0.15 * L
    peel_len = 3.5 * U * U / G * 0.35 * bow_white + 0.15 * L
    s_back = x_sh - x
    y_line = 0.45 * B + np.clip(s_back, 0, None) * math.tan(theta)
    w_line = 0.6 * dx + 0.04 * B + 0.012 * np.clip(s_back, 0, None)
    reach = (s_back > 0) & (s_back < peel_len)
    fade = reach * np.clip(1 - s_back / peel_len, 0, 1) ** 0.5
    src_peel = np.exp(-((np.abs(y)[:, None] - y_line[None, :]) / w_line[None, :]) ** 2) * (fade * bow_white)[None, :]
    src = np.maximum(np.maximum(src_crest, src_sheet), src_peel)
    if plane > 0:
        # spray whiskers from the chine of a semi-planing hull, ~12 deg out
        xc = xs + 0.55 * L
        s2 = xc - x
        y2 = 0.5 * B + np.clip(s2, 0, None) * math.tan(math.radians(12))
        w2 = 0.6 * dx + 0.03 * B + 0.01 * np.clip(s2, 0, None)
        f2 = (s2 > 0) * np.clip(1 - s2 / (1.5 * L), 0, 1)
        src = np.maximum(src, np.exp(-((np.abs(y)[:, None] - y2[None, :]) / w2[None, :]) ** 2) * (0.8 * plane * f2)[None, :])
    src *= 1 - m

    # propulsor wash, injected over the transom's breadth
    i_tr = int(np.clip((xs - x0) / dx, 0, nx - 1))
    w0 = 0.4 * B
    inj = np.exp(-(y / w0) ** 2) * min(U / 10, 1.0) * 0.8 * wash * (1 + plane)

    # advect bow -> stern (water runs -x at U); crest foam keeps its max and decays fast, the wash accumulates
    dc = math.exp(-dx / (U * tau_crest))
    crest = np.empty_like(src)
    a = np.zeros(ny, np.float32)
    for i in range(nx - 1, -1, -1):
        a = np.maximum(a * dc, src[:, i])
        crest[:, i] = a
    dw = math.exp(-dx / (U * tau_wash))
    wsh = np.zeros_like(src)
    if i_tr > 0:
        wsh[:, :i_tr + 1] = inj[:, None] * (dw ** (i_tr - np.arange(i_tr + 1)))[None, :]
        # lateral spreading ~ sqrt(age): banded blur, keeping each column's total
        age = (xs - x)[:i_tr + 1]
        step = max(dx, float(age.max()) / 48)
        for lo in np.arange(0, age.max() + step, step):
            cols = np.nonzero((age >= lo) & (age < lo + step))[0]
            if not len(cols):
                continue
            rr = int(round(0.15 * math.sqrt(B * (lo + 0.5 * step + 1)) / dx))
            part = wsh[:, cols]
            bl = blur_axis(part, rr, 0)
            wsh[:, cols] = bl * (part.sum(0) / np.maximum(bl.sum(0), 1e-6))[None, :]
    wsh = np.clip(wsh, 0, 0.85) * (1 - m)     # capped so the noise always breaks it up

    b = Bake()
    b.x0, b.y0, b.dx, b.nx, b.ny = float(x0), float(-yh), dx, nx, ny
    b.eta, b.crest, b.wash, b.mask = eta, np.clip(crest, 0, 1), wsh, m
    b.info = dict(solve=(sx, sy), dx_solve=dxs, L=L, U=U, FrL=FrL, FrD=FrD, Zb=Zb, lam=lam, theta_deg=math.degrees(theta),
                  entrance_deg=math.degrees(beta), grid=(nx, ny), dx=dx, t_fft=t_fft,
                  t_total=time.perf_counter() - t0)
    return b
