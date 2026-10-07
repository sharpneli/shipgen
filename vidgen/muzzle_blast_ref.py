"""Prototype: muzzle-blast footprint on the sea surface (top-down), analytic per-event.

Physics model (see claude/muzzle-blast-water-vfx.md):
  * Blast energy E = f_blast * m_prop * e_prop,  scaling length lam = (E/p0)^(1/3)          (Fansler 1998)
  * Directivity  beta(theta) = mu cos(theta) + sqrt(1 - mu^2 sin^2 theta), mu ~ 0.78       (Fansler 1998)
  * Peak overpressure dp/p0 = 0.11 (lam'/r) + 0.0061 (lam'/r)^2,  lam' = lam*beta          (Fansler 1998 fit)
  * Shock front speed Us = c0 sqrt(1 + (g+1)/(2g) dp/p0)  (Rankine-Hugoniot), integrated to arrival time
  * Visible effect = ROUGHNESS change ("cat's paw"): the post-shock gust u ~ dp/(rho c) roughens ripples.
    It is a lighting effect, not a height field. Foam only in the near field (scaled distance r/lam' < k_foam).
Ship moves +x. Units: metres, seconds, Pa.
"""
import numpy as np
from scipy.ndimage import gaussian_filter, zoom

P0, C0, GAM, RHO_AIR = 101325.0, 343.0, 1.4, 1.2


def blast_lambda(prop_kg, n_guns=1, e_prop=3.8e6, f_blast=0.45):
    return (n_guns * prop_kg * e_prop * f_blast / P0) ** (1 / 3)


def beta(cos_th, mu=0.78):
    sin2 = 1 - cos_th ** 2
    return mu * cos_th + np.sqrt(1 - mu ** 2 * sin2)


def overpressure(r, lam_eff):
    x = lam_eff / np.maximum(r, 1e-3)
    return P0 * (0.11 * x + 0.0061 * x * x)


def arrival_lut(r_max_scaled=40.0, n=512):
    """Arrival time of the front vs scaled distance z=r/lam', in units of lam'/c0. One LUT for every calibre."""
    z = np.linspace(0.05, r_max_scaled, n)
    dpp = overpressure(z, 1.0) / P0
    us = np.sqrt(1 + (GAM + 1) / (2 * GAM) * dpp)  # in units of c0
    t = np.concatenate([[0], np.cumsum(0.5 * (1 / us[1:] + 1 / us[:-1]) * np.diff(z))])
    return z, t


Z_LUT, T_LUT = arrival_lut()


def blast_fields(X, Y, t, ev, p_vis=1000.0, p_sat=4000.0, tau_frost=2.0, k_foam=1.0, tau_foam=7.0):
    """Returns (rough, ring, foam) in 0..1 for one event at time t (s) after firing.

    ev: dict(x, y, h (muzzle height above water), az (bearing of bore, rad), el (elevation, rad), lam)
    """
    dx, dy, dz = X - ev["x"], Y - ev["y"], -ev["h"]
    r = np.sqrt(dx * dx + dy * dy + dz * dz)
    bore = np.array([np.cos(ev["el"]) * np.cos(ev["az"]), np.cos(ev["el"]) * np.sin(ev["az"]), np.sin(ev["el"])])
    cos_th = (dx * bore[0] + dy * bore[1] + dz * bore[2]) / r
    lam_eff = ev["lam"] * beta(cos_th)
    dp = overpressure(r, lam_eff)
    # front arrival time per pixel (directional, because lam' depends on angle)
    t_arr = np.interp(r / lam_eff, Z_LUT, T_LUT) * lam_eff / C0
    age = t - t_arr
    arrived = age >= 0
    # frost: roughness boost proportional to log overpressure above the visibility threshold
    s = np.clip(np.log(dp / p_vis) / np.log(p_sat / p_vis), 0, 1)
    rough = s * arrived * np.exp(-np.clip(age, 0, None) / tau_frost)
    # leading-edge band: positive phase length ~ c0*T+, T+ ~ 0.9 ms per metre of lam' (tunable, matches audio doc)
    band = C0 * 0.0009 * ev["lam"]
    # signed: +1 = dark, flattened leading edge (gust lays ripples down), then frost builds behind it
    ring = s * arrived * np.exp(-((age * C0) / band) ** 2)
    rough = rough * (1 - np.exp(-((age * C0) / (2 * band)) ** 2))  # frost develops just behind the front
    # near-field blast scour -> foam (same channel as the wake's crest foam)
    zf = r / lam_eff
    foam = np.clip(1.3 - zf / k_foam, 0, 1) ** 1.5 * arrived * np.exp(-np.clip(age, 0, None) / tau_foam)
    return rough, ring, foam


def render(X, Y, rough, ring, foam, dx, seed=1):
    rng = np.random.default_rng(seed)
    # wind ripples: facet slopes, streaked along wind (x)
    sx = gaussian_filter(rng.standard_normal(X.shape), (1.0, 2.0))
    sy = gaussian_filter(rng.standard_normal(X.shape), (1.0, 2.0))
    sx, sy = sx / sx.std(), sy / sy.std()
    sigma = 0.08 * np.clip(1 + 2.5 * rough - 0.7 * ring, 0.15, None)  # roughness scales slope variance
    hx, hy = 0.26, 0.06  # half-vector slope for this sun/camera geometry: calm water mostly dark
    glint = np.exp(-(((sx * sigma - hx) ** 2 + (sy * sigma - hy) ** 2) / (2 * 0.05 ** 2)))
    sky = np.clip(0.15 + 3.0 * (sigma - 0.08), 0, 0.9)  # rougher -> more diffuse sky/sun scatter (silvery)
    deep = np.array([0.03, 0.10, 0.28])
    col = deep * (1 - sky[..., None]) + np.array([0.55, 0.62, 0.70]) * sky[..., None] * 0.6
    col = col + glint[..., None] * np.array([1.0, 1.0, 0.95]) * 0.9
    nz = zoom(rng.random((X.shape[0] // 3 + 2, X.shape[1] // 3 + 2)), 3, order=1)[: X.shape[0], : X.shape[1]]
    f = np.clip((foam - (1 - nz) * 0.9) / 0.2, 0, 1)[..., None]
    col = col * (1 - f) + 0.93 * f
    return (np.clip(col, 0, 1) * 255).astype(np.uint8)


if __name__ == "__main__":
    import time
    from PIL import Image, ImageDraw

    L, B = 270.0, 33.0
    dx = 1.5
    x = np.arange(-260, 260, dx)
    y = np.arange(-70, 380, dx)
    X, Y = np.meshgrid(x, y)
    lam3 = blast_lambda(297, 3)  # 16"/50, three guns per turret
    az = np.radians(90)  # broadside to port (+y)
    el = np.radians(20)
    events = [  # (event, firing delay s): turret III fires first (photo caption)
        (dict(x=-60, y=12, h=12, az=az, el=el, lam=lam3), 0.0),
        (dict(x=55, y=12, h=12, az=az, el=el, lam=lam3), 0.08),
        (dict(x=85, y=12, h=16, az=az, el=el, lam=lam3), 0.08),
    ]
    hull = (np.abs(Y) < 0.5 * B * np.clip(1 - np.abs(2 * X / L) ** np.where(X > 0, 1.7, 5), 0, 1))
    frames = []
    for t in [0.08, 0.2, 0.35, 0.6, 1.5, 4.0]:
        t0 = time.perf_counter()
        R = np.zeros_like(X); RG = np.zeros_like(X); F = np.zeros_like(X)
        fields = [blast_fields(X, Y, t - d, ev) for ev, d in events if t > d]
        if fields:
            Rs = np.array([f[0] for f in fields]); Gs = np.array([f[1] for f in fields])
            R = Rs.max(0) + 0.5 * (Rs.sum(0) - Rs.max(0)) * (Gs.sum(0) > 0.05)  # brighter seam where fronts meet
            RG = Gs.max(0)
            F = np.max([f[2] for f in fields], 0)
        ms = (time.perf_counter() - t0) * 1000
        img = render(X, Y, np.clip(R, 0, 1.3), RG, F, dx)
        img[hull] = (70, 72, 70)
        im = Image.fromarray(img[::-1])
        ImageDraw.Draw(im).text((6, 6), f"t = {t:.2f} s  ({ms:.0f} ms numpy, {X.size/1e3:.0f}k px)", fill=(255, 255, 0))
        frames.append(im)
    w, h = frames[0].size
    sheet = Image.new("RGB", (w * 3, h * 2))
    for i, f in enumerate(frames):
        sheet.paste(f, ((i % 3) * w, (i // 3) * h))
    sheet.save("muzzle_blast_frames.png")
    print("lam per turret", round(lam3, 1), "m")