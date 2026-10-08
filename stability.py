"""
stability — the solved ship's stability and balance: transverse GM at full load and light, roll period, heel in a
beam gale, trim, the full-load hydrostatics a game needs to settle a flooded ship, and the warnings on all of them.
navarch.solve sizes the ship; evaluate() then reads its weights (res.weights, z already set) and fills in the rest.
Design side, standard library only. Heights above the keel unless a function says otherwise.
"""
from __future__ import annotations

import math

from geometry import cwp
from weights import SEAWATER

WIND_REF_MS = 26.0      # the beam gale for the heel check: the IMO weather criterion's 504 Pa
WIND_PA_K = 0.746       # wind pressure Pa = WIND_PA_K x (m/s)^2 on a ship's profile (504 Pa at 26 m/s)
WIND_HEEL_WARN = 16.0   # warn above this steady heel (degrees, IMO), or 0.8 of the deck-edge angle if that is less


def roll_period(L, B, T, gm):
    """Natural roll period, s (IMO: T = 2 C B / sqrt(GM), C = 0.373 + 0.023 B/T - 0.043 L/100). A stiff ship rolls
    quickly and snappily, a tender one slowly; the game decides what that does to its gunnery."""
    if gm <= 0 or T <= 0:
        return 0.0
    c = 0.373 + 0.023 * B / T - 0.043 * L / 100.0
    return 2.0 * c * B / math.sqrt(gm)


def wind_heel(L, B, D, cb, full, std, gm_full, gm_light, windage):
    """The steady heel a beam gale gives, at full load and light (fuel burnt: more freeboard, less weight), the worse
    of the two: the wind's heeling lever P A Z / (g disp) over GM, with A the side profile (the hull's freeboard plus
    the layout's windage) and Z from the middle of the draught to its centre. Also the deck-edge immersion angle and
    the wind that heels the ship that far. Only ever a warning: a player may build a ship that capsizes on a windy
    day."""
    if windage is None:
        return {}
    out = None
    for cond, disp, gm in (("full load", full, gm_full), ("light", std, gm_light)):
        T = disp / (SEAWATER * L * B * cb)
        fb = max(0.0, D - T)
        a_hull = 0.95 * L * fb
        area = a_hull + windage["area_m2"]
        z = (a_hull * (T + fb / 2) + windage["area_m2"] * (D + windage["z_m"])) / area if area else T
        arm = area * (z - T / 2) / (9.81 * disp * 1000.0)     # heeling lever, m per Pa of wind
        edge = math.degrees(math.atan2(fb, B / 2))
        heel = math.degrees(math.atan(WIND_PA_K * WIND_REF_MS ** 2 * arm / gm)) if gm > 0 else 90.0
        p_edge = math.tan(math.radians(edge)) * gm / arm if gm > 0 and arm > 0 else 0.0
        r = dict(condition=cond, heel_deg=heel, deck_edge_deg=edge,
                 deck_edge_wind_kn=math.sqrt(p_edge / WIND_PA_K) / 0.5144, area_m2=area)
        if out is None or heel > out["heel_deg"]:
            out = r
    return out


def hydrostatics(form, res):
    """The full-load hydrostatics a game needs to settle, trim and heel a flooded ship by added weight: sinkage
    = w / (100 tpc_t) m, trim = w (x - lcf) / (100 mct_tm) cm (+ down by the bow), heel = w y / (Δ gm_t) rad.
    Heights above the main deck. gm_t is the report's (evaluate's estimate); gm_l comes from the hull form's
    waterplane with evaluate's kb and the weights' kg."""
    L, D, T, disp = form.hull.L, res.depth, res.draught, res.full
    area, lcf, i_l, i_t = form.waterplane()
    vol = disp / SEAWATER
    kg = sum(w.w * w.z for w in res.weights) / sum(w.w for w in res.weights)
    kb = 0.53 * T
    gm_l = kb + i_l / vol - kg
    return dict(displacement_t=round(disp), volume_m3=round(vol), waterplane_m2=round(area, 1),
                lcf=round(lcf, 3), lcg=round(res.lcg, 3), lcb=round(res.lcb, 3), kg=round(kg - D, 2),
                kb=round(kb - D, 2), gm_t=round(res.gm_full, 3), gm_l=round(gm_l, 1),
                i_t_m4=round(i_t), i_l_m4=round(i_l), tpc_t=round(SEAWATER * area / 100, 2),
                mct_tm=round(disp * gm_l / (100 * L), 1))


def evaluate(res, L, B, cb, tun, windage):
    """GM (full load, and light: fuel burnt and cargo out, no ballast), roll period, wind heel (windage: the
    layout's, or None before there is one) and trim of the solved ship res (navarch.Result), set on res."""
    def gm(disp_case, include_fuel):
        T_ = disp_case / (SEAWATER * L * B * cb)
        ws = [w for w in res.weights if include_fuel or w.group not in ("fuel", "cargo")]
        kg = sum(w.w * w.z for w in ws) / sum(w.w for w in ws)
        kb = 0.53 * T_
        cw = cwp(cb)
        it = 0.0372 * (2 * cw + 1) ** 3 * L * B ** 3 / 12
        bm = it / (disp_case / SEAWATER)
        return kb + bm - kg

    res.gm_full = gm(res.full, True)
    res.gm_light = gm(res.std, False)       # fuel burnt (and cargo out), no ballast
    res.roll_s = roll_period(L, B, res.draught, res.gm_full)
    res.wind = wind_heel(L, B, res.depth, cb, res.full, res.std, res.gm_full, res.gm_light, windage)

    # --- longitudinal balance ---
    res.lcg = sum(w.w * w.x for w in res.weights) / res.full
    res.lcb = tun["lcb_frac"] * L
    cw = cwp(cb)
    bml = 0.0743 * cw ** 2 * L ** 2 / (cb * res.draught)
    res.trim_m = (res.lcg - res.lcb) * L / bml  # + = down by the bow


def checks(res, L, B, tun):
    """Stability and trim errors and warnings, appended to res.errors and res.warnings."""
    gmin = res.gm_full
    if gmin <= 0:
        res.errors.append(f"Unstable: GM {gmin:.2f} m. The ship would capsize. Lower the weight high up.")
    elif gmin < 0.035 * B:
        res.warnings.append(f"Top-heavy: GM {gmin:.2f} m (want at least {0.035 * B:.2f} m).")
    if res.gm_light <= 0 < gmin:
        res.warnings.append(f"Needs water ballast when low on fuel (light-condition GM {res.gm_light:.2f} m).")
    if res.gm_full > tun.get("gm_stiff_frac", 0.15) * B:
        res.warnings.append(f"Very stiff: GM {res.gm_full:.2f} m. Snappy roll, poor gun platform.")
    trim_tol = tun.get("trim_tol_frac", 0.01)
    if abs(res.trim_m) > trim_tol * L:
        res.errors.append(f"Badly out of trim: {abs(res.trim_m):.1f} m by the {'bow' if res.trim_m > 0 else 'stern'}.")
    elif abs(res.trim_m) > tun.get("trim_warn_frac", 0.004) * L:
        res.warnings.append(f"Trimmed {abs(res.trim_m):.1f} m by the {'bow' if res.trim_m > 0 else 'stern'}.")
    w = res.wind
    if w and w["heel_deg"] > min(WIND_HEEL_WARN, 0.8 * w["deck_edge_deg"]):
        res.warnings.append(f"Heels {w['heel_deg']:.0f}° in a beam gale ({WIND_REF_MS:.0f} m/s, {w['condition']}): too "
                            f"much windage for its stability. The deck edge goes under at {w['deck_edge_deg']:.0f}°, "
                            f"in a {w['deck_edge_wind_kn']:.0f} kn wind.")
