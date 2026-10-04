"""
hullweight: hull structure weight, by plate area x thickness (research/hull-weight-model.md, "Tier 2"; the
reference implementation is research/hull_weight_ref.py).

Small hulls are minimum-gauge driven: plate area x the thinnest plate a yard can build with (t_min), times a
framing allowance. Big hulls must also resist bending as a girder: the hogging moment grows as displacement x
length, so they need plate beyond t_min in the strength deck and shell (t_str). Construction acts mostly on that
second part: a higher-yield steel raises the allowable girder stress; welding instead of riveting (no laps or
straps) is a flat factor on everything. Continuous armour decks over amidships are part of the girder and stand
in for strength plating.

Standard library only (design side). Units: m, m^2, mm of plate, MPa, kN m, t.
"""
import math

RHO = 7.85e-3          # t per m^2 per mm of steel plate

# Fitted constants (the research's calibration; nothing else is free)
K_S = 2.5              # framing, stiffeners and minor structure, on the minimum-gauge plate
C_M = 40.0             # hogging moment M = full displacement x g x L / C_M
F_FIT = 0.10           # brackets, foundations, local reinforcement
SF = 2.1               # allowable girder stress = yield / SF ...
SIG_CAP = 185.0        # ... but no more than this (buckling and fatigue: every steel has the same stiffness)
T_MIN = (4.0, 0.03)    # t_min = (a + b L) x standard  [mm]

# Geometry factors
SHELL_SIDE = 0.90      # side shell 2 x 0.90 D L
SHELL_BOTTOM = 0.95    # bottom shell 0.95 B L sqrt(Cb)
INT_DECK = 0.85        # each internal deck 0.85 of the strength deck's area ...
INT_DECK_T = 0.60      # ... at 0.6 t_min
BULKHEADS = 1 + 1 / 0.06   # one main transverse bulkhead per 0.06 L, whatever the length
BHD_AREA = 0.75 * 0.80     # a bulkhead is 0.75 B D (the section isn't a box); 80 % run the full depth
BHD_T = 0.70           # bulkheads at 0.7 t_min
DB_AREA = 0.80 * 1.60  # inner bottom over 0.8 L, floors and girders x 1.6, at t_min
GIRDER_TAPER = 0.75    # strength plating thins toward the ends: 0.75 of the shell and deck carry t_str - t_min
NEUTRAL_AXIS = 0.45    # x D above the keel
ARM_DECK_WIDTH = 0.85  # x B: the part of an armour deck that works in the girder

# The research's presets, for hull-templates.md and tests (the design gives the numbers, never a preset name)
PRESETS = {
    "iron_1880":     dict(name="Wrought iron, riveted", yield_mpa=190, join_factor=1.12),
    "ms_riv_1900":   dict(name="Mild steel, riveted", yield_mpa=235, join_factor=1.10),
    "ht_riv_1914":   dict(name="Mild steel hull, high-tensile strength deck, riveted", yield_mpa=290,
                          join_factor=1.10),
    "hts_riv_1925":  dict(name="High-tensile steel (D, Ducol, HTS), riveted", yield_mpa=340, join_factor=1.08),
    "hts_mix_1937":  dict(name="High-tensile steel, riveted shell, welded internals", yield_mpa=350,
                          join_factor=1.04),
    "sts_weld_1942": dict(name="High-tensile and structural STS, mostly welded", yield_mpa=420, join_factor=1.02),
    "weld_1945":     dict(name="High-tensile steel, all welded", yield_mpa=350, join_factor=1.00),
    "hy80_1960":     dict(name="HY-80, all welded", yield_mpa=420, join_factor=1.00),
}
DEFAULT = {**PRESETS["weld_1945"], "standard": 1.0}


def construction(design):
    """hull.construction with its defaults filled in."""
    return {**DEFAULT, **((design.get("hull") or {}).get("construction") or {})}


def allowable_stress(c):
    return min(c["yield_mpa"] / SF, SIG_CAP)


def weight(L, B, D, cb, full, c, n_int, double_bottom, armour_decks=()):
    """The hull structure: dict(t, min_gauge_t, strength_t, t_min_mm, t_str_mm, stress_mpa, i_req_m4, i_armour_m4).
    c            construction: yield_mpa (the girder steel mix), join_factor (riveting > 1, all welded 1.0),
                 standard (scales t_min: 0.85 light, 1.0 naval, 1.25 robust)
    n_int        internal decks and platforms below the strength deck (may be fractional)
    double_bottom how much of an inner bottom there is, 0..1
    armour_decks [(mm, z)] plates over amidships, z above the keel: their section counts in the girder."""
    cwp = 0.66 + 0.33 * cb
    a_shell = 2 * SHELL_SIDE * D * L + SHELL_BOTTOM * B * L * math.sqrt(cb)
    a_deck = B * L * cwp
    a_int = n_int * INT_DECK * a_deck
    a_bhd = BULKHEADS * BHD_AREA * B * D
    a_db = double_bottom * B * L * cb * DB_AREA
    t_min = (T_MIN[0] + T_MIN[1] * L) * c["standard"]
    sig = allowable_stress(c)
    m = full * 9.81 * L / C_M
    i_req = m / (sig * 1000) * (D / 2)
    i_arm = sum(ARM_DECK_WIDTH * B * mm / 1000 * (z - NEUTRAL_AXIS * D) ** 2 for mm, z in armour_decks)
    t_str = max(0.0, i_req - i_arm) / (D / 2) / (D * (B + D / 3) / 1000)
    w_min = RHO * K_S * t_min * (a_shell + a_deck + a_int * INT_DECK_T + a_bhd * BHD_T + a_db)
    w_str = RHO * GIRDER_TAPER * (a_shell + a_deck) * max(0.0, t_str - t_min)
    k = (1 + F_FIT) * c["join_factor"]
    return dict(t=(w_min + w_str) * k, min_gauge_t=w_min * k, strength_t=w_str * k, t_min_mm=t_min,
                t_str_mm=t_str, stress_mpa=sig, i_req_m4=i_req, i_armour_m4=i_arm)


def validate(design):
    c = (design.get("hull") or {}).get("construction")
    if c is None:
        return []
    if not isinstance(c, dict):
        return ["hull.construction: use {\"name\", \"yield_mpa\", \"join_factor\", \"standard\"} "
                "(hull-templates.md has examples)"]
    errs = [f"hull.construction.{k}: must be a number above 0" for k in ("yield_mpa", "join_factor", "standard")
            if k in c and not (isinstance(c[k], (int, float)) and c[k] > 0)]
    if "name" in c and not isinstance(c["name"], str):
        errs.append("hull.construction.name: use a string")
    return errs
