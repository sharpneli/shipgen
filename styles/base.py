"""
Style hooks with neutral defaults. A style overrides what it needs.
"""
from __future__ import annotations

# Input limits shared by every style: (lo, hi) per dotted path; a style's LIMITS are merged over these.
# These are sanity bounds for the generator, not gameplay rules: the game's designer enforces those. Armament
# and armour are deliberately wide (silly designs may look stupid or fail the physics, but they run); hull form
# and speed stay within the range where the weight, power and stability formulas mean something.
COMMON_LIMITS = {
    ("hull", "block_coefficient"): (0.42, 0.68),
    ("speed_kn",): (8, 42), ("range_nm",): (1000, 25000),
    ("main", "calibre_mm"): (1, 2000), ("main", "calibre_length"): (1, 200), ("main", "barrels"): (1, 20),
    ("main", "fore"): (0, 40), ("main", "aft"): (0, 40), ("main", "mid"): (0, 40),
    ("main", "wing"): (0, 20),
    ("secondary", "calibre_mm"): (1, 2000), ("secondary", "calibre_length"): (1, 200),
    ("secondary", "barrels"): (1, 20), ("secondary", "per_side"): (0, 100), ("secondary", "count"): (0, 200),
    ("torpedoes", "mounts"): (0, 40), ("torpedoes", "tubes"): (1, 20),
    ("aa", "heavy"): (0, 500), ("aa", "light"): (0, 500),
    ("armour", "belt_mm"): (0, 2000), ("armour", "turret_mm"): (0, 2000),
    ("armour", "tds_m"): (0, 20), ("armour", "bulkhead_mm"): (0, 2000),
    ("armour", "upper_belt", "mm"): (0, 2000),
    ("armour", "end_belts", "fore", "mm"): (0, 2000), ("armour", "end_belts", "fore", "tip_mm"): (0, 2000),
    ("armour", "end_belts", "aft", "mm"): (0, 2000), ("armour", "end_belts", "aft", "tip_mm"): (0, 2000),
}


# extents that may share one deck (different stretches of it)
SHARED_DECK = ({"citadel", "fore"}, {"citadel", "aft"}, {"citadel", "ends"}, {"fore", "aft"})


def armour_errors(design) -> list[str]:
    """armour.decks: a list of {"deck": n (0 the main deck, 1 the second, ...), "mm", "extent"}, top down."""
    from navarch import ARMOUR_EXTENTS
    a = design.get("armour") or {}
    errs = []
    if "deck_mm" in a:
        errs.append("armour.deck_mm is gone: list the armour decks top down in armour.decks, e.g. "
                    "[{\"deck\": 1, \"mm\": 152, \"extent\": \"citadel\"}]")
    decks = a.get("decks", [])
    if not isinstance(decks, list):
        return errs + ["armour.decks: use a list of armour decks, top down"]
    last, prev = -1, None
    for k, d in enumerate(decks):
        if not isinstance(d, dict) or not isinstance(d.get("deck"), int) or d["deck"] < 0:
            errs.append(f"armour.decks[{k}].deck: use a deck number (0 the main deck, 1 the second deck, ...)")
            continue
        if not isinstance(d.get("mm"), (int, float)) or d["mm"] < 0:
            errs.append(f"armour.decks[{k}].mm: use a thickness of 0 or more")
        if d.get("extent") not in ARMOUR_EXTENTS:
            errs.append(f"armour.decks[{k}].extent = {d.get('extent')!r}: use {' or '.join(ARMOUR_EXTENTS)}")
        if d["deck"] < last:
            errs.append(f"armour.decks[{k}]: list the armour decks top down")
        elif d["deck"] == last and {d.get("extent"), prev} not in SHARED_DECK:
            errs.append(f"armour.decks[{k}]: a deck may appear twice only over different stretches (the citadel "
                        "and its ends)")
        last, prev = max(last, d["deck"]), d.get("extent")
    ub = a.get("upper_belt")
    if ub is not None:
        if not isinstance(ub, dict):
            errs.append("armour.upper_belt: use {\"mm\", \"to_deck\", \"extent\"}")
        else:
            if not isinstance(ub.get("to_deck", 0), int) or ub.get("to_deck", 0) < 0:
                errs.append("armour.upper_belt.to_deck: use a deck number (0 the main deck, 1 the second deck, ...)")
            if ub.get("extent", "citadel") not in ARMOUR_EXTENTS:
                errs.append(f"armour.upper_belt.extent = {ub.get('extent')!r}: use {' or '.join(ARMOUR_EXTENTS)}")
    eb = a.get("end_belts")
    if eb is not None:
        if not isinstance(eb, dict) or set(eb) - {"fore", "aft"}:
            errs.append("armour.end_belts: use {\"fore\": {\"mm\", \"tip_mm\"}, \"aft\": {...}}")
        else:
            errs += [f"armour.end_belts.{end}: use {{\"mm\", \"tip_mm\"}}" for end, e in eb.items()
                     if not isinstance(e, dict)]
    return errs


class Style:
    name = "base"
    LIMITS: dict = {}
    DEFAULT_CB = 0.55   # block coefficient when the design gives none
    # Sizing (shipdesign.size): the hull is the shortest of `length` (min, max) metres that fits everything and is
    # at least as slender as its speed asks (slender: shipdesign.min_length), and as narrow as allowed by:
    # everything fitting across it, GM at least gm_frac x beam, draught at most tb x beam, and length at most
    # lb_max x beam. beam_max caps it.
    SIZE = dict(length=(30.0, 1000.0), beam_max=100.0, gm_frac=0.06, tb=0.36, lb_max=10.5, slender=True)

    def limits(self):
        return {**COMMON_LIMITS, **self.LIMITS}

    def validate(self, design) -> list[str]:
        """Checks beyond the numeric limits."""
        import powerplant
        import crew
        errs = powerplant.validate(design, self.DEFAULT_TECH) + crew.validate(design, self.CREW_STANDARD)
        if "type" in (design.get("machinery") or {}):
            errs.append("machinery.type is gone: give the plant's technology as machinery.tech "
                        "(plant-templates.md has examples by year)")
        errs += [f"hull.{k}: the designer works out the hull's size from what it carries; remove it"
                 for k in ("length", "beam") if k in (design.get("hull") or {})]
        errs += armour_errors(design)
        if isinstance(design.get("secondary"), list) and not self.SECONDARY_LIST:
            errs.append(f"secondary: the {self.name} style takes one secondary battery, not a list")
        sec = design.get("secondary") or []
        for b in (sec if isinstance(sec, list) else [sec]):
            mount = b.get("mount", "deck")
            if mount not in ("deck", "casemate"):
                errs.append(f"secondary.mount = {mount!r}: use deck or casemate")
            elif mount == "casemate" and not self.CASEMATES:
                errs.append(f"secondary.mount: the {self.name} style has no casemates")
            if b.get("tier", "lower") not in ("lower", "upper"):
                errs.append(f"secondary.tier = {b['tier']!r}: use lower or upper (casemates only)")
        main = design.get("main") or {}
        if main.get("mid") and not self.MIDSHIPS_TURRETS:
            errs.append(f"main.mid: the {self.name} style has no midships turrets")
        if main.get("wing") and not self.WING_TURRETS:
            errs.append(f"main.wing: the {self.name} style has no wing turrets")
        if not isinstance(main.get("echelon", False), bool):
            errs.append("main.echelon: use true or false")
        sf = main.get("superfire", True)
        if not isinstance(sf, (bool, dict)) or (isinstance(sf, dict) and not all(
                isinstance(v, int) and 0 <= v <= main.get(k, 0) for k, v in sf.items() if k in ("fore", "aft"))):
            errs.append("main.superfire: use true, false, or {\"fore\": n, \"aft\": n} within the group sizes")
        return errs

    DEFAULT_TECH = None         # machinery.tech when the design gives none (None: powerplant.DEFAULT_TECH)
    MIDSHIPS_TURRETS = False    # does the layout support main["mid"]
    WING_TURRETS = False        # does the layout support main["wing"] (pairs) and main["echelon"]
    SECONDARY_LIST = False      # may "secondary" be a list of batteries with count/where (armament.batteries)
    CASEMATES = False           # may a secondary battery be "mount": "casemate" (guns in the hull side)

    def tuning(self, design) -> dict:
        """Overrides of navarch.TUNING for this design."""
        return {}

    def build_layout(self, design, res, shift=0.0):
        """Lay the ship out for the solved weights res (navarch.Result: power, depth, draught, fuel, plant)."""
        raise NotImplementedError

    def rough_payload(self, design, D) -> list:
        """First-pass weights of style-specific items, before the layout exists."""
        return []

    def structure_weights(self, design, L, B, T, D, geo, tun) -> list:
        """Style structure that depends on the hull (counted in standard displacement, before outfit)."""
        return []

    def payload_weights(self, design, L, D, geo, tun, ctx) -> tuple[list, list]:
        """(standard-load items, full-load-only items): e.g. aircraft, and cargo or aviation fuel.
        ctx: items (the ship so far, with x), fuel and fuel_x, lcb; for stowing cargo to trim."""
        return [], []

    def checks(self, design, r, tun) -> list[str]:
        """Extra warnings once the weights are solved."""
        return []

    CREW_STANDARD = "H2"    # crew.STANDARDS block when the design gives no crew.standard
    CREW_DECK_K = 0.8       # deck and command crew = CREW_DECK_K x standard displacement^0.5 (crew.deck_crew)

    def crew_extra(self, design) -> dict:
        """Departments beyond engineering, weapons and deck (crew.complement): {name: men}."""
        return {}

    def results(self, design, lay, r) -> dict:
        """Extra report values."""
        return {}

    def summary(self, design, lay, r) -> list[str]:
        """Extra lines for the summary sheet."""
        return []
