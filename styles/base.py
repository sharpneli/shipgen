"""
Style hooks with neutral defaults. A style overrides what it needs.
"""
from __future__ import annotations

# Input limits shared by every style: (lo, hi) per dotted path; a style's LIMITS are merged over these.
# These are sanity bounds for the generator, not gameplay rules: the game's designer enforces those. Armament
# and armour are deliberately wide (silly designs may look stupid or fail the physics, but they run); hull form
# and speed stay within the range where the weight, power and stability formulas mean something.
COMMON_LIMITS = {
    ("hull", "length"): (30, 1000), ("hull", "beam"): (5, 100), ("hull", "block_coefficient"): (0.42, 0.68),
    ("speed_kn",): (8, 42), ("range_nm",): (1000, 25000),
    ("main", "calibre_mm"): (1, 2000), ("main", "calibre_length"): (1, 200), ("main", "barrels"): (1, 20),
    ("main", "fore"): (0, 40), ("main", "aft"): (0, 40), ("main", "mid"): (0, 40),
    ("main", "wing"): (0, 20),
    ("secondary", "calibre_mm"): (1, 2000), ("secondary", "calibre_length"): (1, 200),
    ("secondary", "barrels"): (1, 20), ("secondary", "per_side"): (0, 100), ("secondary", "count"): (0, 200),
    ("torpedoes", "mounts"): (0, 40), ("torpedoes", "tubes"): (1, 20),
    ("aa", "heavy"): (0, 500), ("aa", "light"): (0, 500),
    ("armour", "belt_mm"): (0, 2000), ("armour", "deck_mm"): (0, 2000), ("armour", "turret_mm"): (0, 2000),
}


class Style:
    name = "base"
    LIMITS: dict = {}

    def limits(self):
        return {**COMMON_LIMITS, **self.LIMITS}

    def validate(self, design) -> list[str]:
        """Checks beyond the numeric limits."""
        from navarch import MACHINERY
        mt = self.machinery_type(design)
        errs = [] if mt in MACHINERY else [f"machinery.type = {mt!r}: use {', '.join(MACHINERY)}"]
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

    DEFAULT_MACHINERY = "naval_turbine"
    MIDSHIPS_TURRETS = False    # does the layout support main["mid"]
    WING_TURRETS = False        # does the layout support main["wing"] (pairs) and main["echelon"]
    SECONDARY_LIST = False      # may "secondary" be a list of batteries with count/where (armament.batteries)
    CASEMATES = False           # may a secondary battery be "mount": "casemate" (guns in the hull side)

    def machinery_type(self, design):
        return (design.get("machinery") or {}).get("type", self.DEFAULT_MACHINERY)

    def tuning(self, design) -> dict:
        """Overrides of navarch.TUNING for this design (the base: its machinery type)."""
        from navarch import machinery_tuning
        return machinery_tuning(self.machinery_type(design))

    def build_layout(self, design, shp, depth, shift=0.0):
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

    def crew(self, design, std) -> int:
        return round(1.1 * std ** 0.72)

    def results(self, design, lay, r) -> dict:
        """Extra report values."""
        return {}

    def summary(self, design, lay, r) -> list[str]:
        """Extra lines for the summary sheet."""
        return []
