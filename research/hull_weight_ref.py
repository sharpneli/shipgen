"""
hull_weight_ref.py — reference implementation of the Tier-2 hull structure
weight model (Naval project, claude/hull-weight-model.md, rev 3).

Every constant and every per-ship input used to produce the tables in the
note lives in this file. Run it:  python3 hull_weight_ref.py

Units: metres, tonnes, mm (plate), MPa (stress), kN·m (moment).
"""

from dataclasses import dataclass

RHO_STEEL = 7.85e-3          # t per (m² · mm)

# ----------------------------------------------------------------------------
# Fitted constants (fit = 6 USN escorts + Bismarck + Hood, Dreadnought at half
# weight; grid search over k_s ∈ [2.0..2.6], C_M ∈ [30..40], f_fit ∈ [.08...12])
# ----------------------------------------------------------------------------
K_S     = 2.5     # framing/stiffener/minor-structure multiplier on min-gauge plate
C_M     = 40.0    # hogging bending-moment coefficient: M = Δ·g·L / C_M
F_FIT   = 0.10    # brackets, foundations, local reinforcement
SF      = 2.1     # σ_eff = σ_y / SF
SIG_CAP = 185.0   # MPa; buckling/fatigue ceiling (E is the same for all steels)

# Geometry factors (these are what the note previously left implicit)
SHELL_SIDE_F    = 0.90   # side shell area = 2 · 0.90 · D · L
SHELL_BOT_F     = 0.95   # bottom shell area = 0.95 · B · L · √Cb
INT_DECK_F      = 0.85   # each internal deck = 0.85 · strength-deck area
INT_DECK_T      = 0.60   # internal decks are 0.6 · t_min thick
BHD_SPACING     = 0.06   # one main transverse bulkhead per 0.06 · L  → N = 1 + 1/0.06
BHD_AREA_F      = 0.75   # bulkhead section = 0.75 · B · D (hull is not a rectangle)
BHD_FULL_F      = 0.80   # 80 % of bulkheads are full-depth, rest are partial → area · 0.8
BHD_T           = 0.70   # bulkheads are 0.7 · t_min thick
DB_EXTENT       = 0.80   # inner bottom runs over 80 % of length (Hipper 72 %, Nassau 88 %)
DB_FLOORS_F     = 1.60   # inner-bottom plate ×1.6 for floors and girders
SUPER_T         = 0.50   # superstructure plating is 0.5 · t_min thick
GIRDER_TAPER    = 0.75   # strength plating tapers toward the ends → 0.75 of full area
NEUTRAL_AXIS_F  = 0.45   # neutral axis sits at 0.45 · D above keel
ARM_DECK_WIDTH_F= 0.85   # continuous armour deck spans 0.85 · B

T_MIN_A = 4.0            # t_min = 4.0 + 0.03·L  [mm]
T_MIN_B = 0.03

# ----------------------------------------------------------------------------
# Technology presets: (σ_y of the girder steel mix [MPa], joining factor)
# ----------------------------------------------------------------------------
TECH = {
    "iron_1880":     (190.0, 1.12),
    "ms_riv_1900":   (235.0, 1.10),
    "ht_riv_1914":   (290.0, 1.10),
    "hts_riv_1925":  (340.0, 1.08),
    "hts_mix_1937":  (350.0, 1.04),
    "sts_weld_1942": (420.0, 1.02),
    "weld_1945":     (350.0, 1.00),
    "hy80_1960":     (420.0, 1.00),
}


def sigma_eff(tech: str) -> float:
    sy, _ = TECH[tech]
    return min(sy / SF, SIG_CAP)


# ----------------------------------------------------------------------------
# Inputs
# ----------------------------------------------------------------------------
@dataclass
class HullInputs:
    L: float            # waterline / pp length
    B: float            # max beam
    D: float            # depth, keel to strength deck, amidships
    Cb: float           # block coefficient
    disp_full: float    # full-load displacement (t)
    n_int: int          # number of internal (non-strength) decks/platforms
    double_bottom: bool # inner bottom fitted
    A_super: float      # superstructure plating area (m²). 0 if weighed elsewhere.
    tech: str
    arm_deck_mm: float = 0.0   # continuous armour deck thickness (mm), 0 = none
    arm_deck_h: float = 0.0    # its height above keel (m)
    f_std: float = 1.0         # construction standard: 0.85 light / 1.0 naval / 1.25 robust


# ----------------------------------------------------------------------------
# Areas — the "box-free" approximations used for calibration. In the game,
# replace these with integrals over the real sections; keep the factors
# INT_DECK_F, BHD_* and DB_* unless you also model those directly.
# ----------------------------------------------------------------------------
def areas(h: HullInputs):
    Cwp = 0.66 + 0.33 * h.Cb
    A_shell = 2 * SHELL_SIDE_F * h.D * h.L + SHELL_BOT_F * h.B * h.L * h.Cb ** 0.5
    A_sdeck = h.B * h.L * Cwp
    A_int   = h.n_int * INT_DECK_F * A_sdeck
    N_bhd   = 1 + 1 / BHD_SPACING                       # 17.67, independent of L
    A_bhd   = N_bhd * BHD_AREA_F * h.B * h.D * BHD_FULL_F
    A_db    = (h.B * h.L * h.Cb * DB_EXTENT * DB_FLOORS_F) if h.double_bottom else 0.0
    return A_shell, A_sdeck, A_int, A_bhd, A_db


# ----------------------------------------------------------------------------
# The model
# ----------------------------------------------------------------------------
def hull_weight(h: HullInputs):
    A_shell, A_sdeck, A_int, A_bhd, A_db = areas(h)
    _, f_join = TECH[h.tech]
    sig = sigma_eff(h.tech)

    # 1. minimum gauge
    t_min = (T_MIN_A + T_MIN_B * h.L) * h.f_std

    # 2. hull-girder requirement
    M      = h.disp_full * 9.81 * h.L / C_M                      # kN·m
    I_req  = M / (sig * 1e3) * (h.D / 2)                          # m⁴  (Z_req · D/2)
    I_arm  = 0.0
    if h.arm_deck_mm > 0:
        I_arm = (ARM_DECK_WIDTH_F * h.B * h.arm_deck_mm / 1000
                 * (h.arm_deck_h - NEUTRAL_AXIS_F * h.D) ** 2)
    Z_per_mm = h.D * (h.B + h.D / 3) / 1000                      # m³ per mm of smeared plate (thin box)
    t_str  = max(0.0, I_req - I_arm) / (h.D / 2) / Z_per_mm       # mm

    # 3. weights
    W_min = RHO_STEEL * K_S * (
        (A_shell + A_sdeck) * t_min
        + A_int  * INT_DECK_T * t_min
        + A_bhd  * BHD_T      * t_min
        + A_db   * t_min
        + h.A_super * SUPER_T * t_min
    )
    W_str = RHO_STEEL * GIRDER_TAPER * (A_shell + A_sdeck) * max(0.0, t_str - t_min)
    W = (W_min + W_str) * (1 + F_FIT) * f_join
    return dict(W=W, W_min=W_min, W_str=W_str, t_min=t_min, t_str=t_str,
                sigma=sig, I_req=I_req, I_arm=I_arm,
                A_shell=A_shell, A_sdeck=A_sdeck, A_int=A_int, A_bhd=A_bhd, A_db=A_db)


# ----------------------------------------------------------------------------
# Calibration set. Every value here is what produced the note's table.
# A_super for escorts is included because their Group-1 figure includes it.
# Capital ships: 3 internal decks, double bottom, A_super 3000.
# ----------------------------------------------------------------------------
LT = 1.016
CAL = [
    # name,            L,     B,     D,     Cb,   Δfull,  n_int, db,    A_sup, tech,            armdeck(mm,h), actual
    ("FFG-7",         124.4, 13.78,  9.14, 0.47,  3730,  2, False, 1300, "weld_1945",    (0, 0),      1257*LT),
    ("Knox",          126.5, 13.96,  8.63, 0.47,  4080,  2, False, 1200, "weld_1945",    (0, 0),      1330*LT),
    ("Garcia",        118.9, 13.38,  9.14, 0.47,  3525,  2, False, 1100, "weld_1945",    (0, 0),      1122*LT),
    ("Bronstein",     106.7, 12.04,  8.78, 0.47,  2600,  2, False,  900, "weld_1945",    (0, 0),       801*LT),
    ("Dealey",         93.9, 11.09,  6.25, 0.47,  1907,  1, False,  500, "weld_1945",    (0, 0),       595*LT),
    ("Claud Jones",    91.7, 11.77,  6.49, 0.47,  1720,  1, False,  500, "weld_1945",    (0, 0),       580*LT),
    ("Bismarck",      241.6, 36.0,  15.0,  0.56, 50900,  3, True,  3000, "hts_mix_1937", (100, 10.5), 10505),
    ("Hood",          246.9, 31.7,  15.0,  0.57, 46680,  3, True,  3000, "hts_riv_1925", (0, 0),      14830),
    ("Dreadnought*",  160.6, 25.0,  13.4,  0.60, 21800,  3, True,  1500, "ht_riv_1914",  (0, 0),      6100*LT),
]

# Illustrative designs. NOTE: A_super = 0 here because in navarch the
# superstructure is weighed separately. That is the single biggest reason a
# re-implementation using the calibration-style A_super lands ~2 kt higher.
IOWA     = dict(L=262.0, B=33.0, D=16.5, Cb=0.59, disp_full=57500, n_int=3, double_bottom=True,  A_super=0.0, arm_deck_mm=150, arm_deck_h=11.5)
FLETCHER = dict(L=114.7, B=12.0, D=7.0,  Cb=0.50, disp_full=2900,  n_int=1, double_bottom=False, A_super=0.0)


def _row(name, h, actual=None):
    r = hull_weight(h)
    err = f"{100*(r['W']-actual)/actual:+.0f}%" if actual else "  –  "
    act = f"{actual:7.0f}" if actual else "      –"
    return (f"| {name:14s} | {h.tech:13s} | {act} | {r['W']:7.0f} | {err:>5s} | {r['sigma']:4.0f} "
            f"| {r['t_str']:4.1f} | {r['t_min']:4.1f} | {r['W_min']:7.0f} | {r['W_str']:7.0f} |")


if __name__ == "__main__":
    hdr = ("| Ship           | tech          |  actual |  Tier 2 |  err  | σ_eff | t_str | t_min |   W_min |   W_str |\n"
           "|---|---|---|---|---|---|---|---|---|---|")
    print("## Calibration\n" + hdr)
    for (n, L, B, D, Cb, dF, ni, db, sa, tech, (am, ah), act) in CAL:
        h = HullInputs(L, B, D, Cb, dF, ni, db, sa, tech, am, ah)
        print(_row(n, h, act))

    print("\n## Iowa-like by technology (A_super = 0, 150 mm deck credited at 11.5 m)\n" + hdr)
    for tech in TECH:
        print(_row("Iowa-like", HullInputs(tech=tech, **IOWA)))
    print("\n## Iowa-like, no armour-deck credit\n" + hdr)
    for tech in ("ht_riv_1914", "sts_weld_1942"):
        d = dict(IOWA); d.update(arm_deck_mm=0, arm_deck_h=0)
        print(_row("Iowa-like", HullInputs(tech=tech, **d)))

    print("\n## Fletcher-like by technology (A_super = 0)\n" + hdr)
    for tech in TECH:
        print(_row("Fletcher-like", HullInputs(tech=tech, **FLETCHER)))

    print("\n## Area breakdown (m²) for two designs")
    for name, d in (("Iowa-like", IOWA), ("Fletcher-like", FLETCHER)):
        r = hull_weight(HullInputs(tech="weld_1945", **d))
        print(f"{name:14s} shell={r['A_shell']:.0f} sdeck={r['A_sdeck']:.0f} int={r['A_int']:.0f} "
              f"bhd={r['A_bhd']:.0f} db={r['A_db']:.0f}  I_req={r['I_req']:.1f} I_arm={r['I_arm']:.1f}")
