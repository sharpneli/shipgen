"""
Style hooks with neutral defaults. A style overrides what it needs.
"""
from __future__ import annotations

import math

from armour import armour_errors

# Input limits shared by every style: (lo, hi) per dotted path; a style's LIMITS are merged over these.
# These are sanity bounds for the generator, not gameplay rules: the game's designer enforces those. Armament
# and armour are deliberately wide (silly designs may look stupid or fail the physics, but they run); hull form
# and speed stay within the range where the weight, power and stability formulas mean something.
COMMON_LIMITS = {
    ("hull", "block_coefficient"): (0.42, 0.68),
    ("hull", "construction", "yield_mpa"): (100, 1500), ("hull", "construction", "join_factor"): (0.8, 1.5),
    ("hull", "construction", "standard"): (0.5, 2.0), ("hull", "freeboard"): (0.3, 2.0),
    ("hull", "raised", "decks"): (1, 2), ("hull", "plating", "shell_mm"): (0, 200),
    ("hull", "plating", "deck_wood_mm"): (0, 300),
    ("speed_kn",): (8, 42), ("range_nm",): (1000, 25000),
    ("main", "calibre_mm"): (1, 2000), ("main", "calibre_length"): (1, 200), ("main", "barrels"): (1, 20),
    ("main", "fore"): (0, 40), ("main", "aft"): (0, 40), ("main", "mid"): (0, 40),
    ("main", "wing"): (0, 20), ("main", "armour_mm"): (0, 2000),
    ("secondary", "calibre_mm"): (1, 2000), ("secondary", "calibre_length"): (1, 200),
    ("secondary", "barrels"): (1, 20), ("secondary", "per_side"): (0, 100), ("secondary", "count"): (0, 200),
    ("main", "rounds_per_gun"): (0, 1000), ("secondary", "rounds_per_gun"): (0, 1000),
    ("torpedoes", "mounts"): (0, 40), ("torpedoes", "tubes"): (1, 20),
    ("aa", "heavy"): (0, 500), ("aa", "light"): (0, 500),
    ("armour", "belt_mm"): (0, 2000),
    ("armour", "tds_m"): (0, 20), ("armour", "bulkhead_mm"): (0, 2000),
    ("armour", "belt_bottom_mm"): (0, 2000), ("armour", "belt_depth_m"): (0, 30), ("armour", "belt_height_m"): (0, 30),
    ("armour", "upper_belt", "mm"): (0, 2000),
    ("armour", "end_belts", "fore", "mm"): (0, 2000), ("armour", "end_belts", "fore", "tip_mm"): (0, 2000),
    ("armour", "end_belts", "aft", "mm"): (0, 2000), ("armour", "end_belts", "aft", "tip_mm"): (0, 2000),
    **{("armour", "end_belts", e, k): lim for e in ("fore", "aft")
       for k, lim in (("reach", (0, 1)), ("bulkhead_mm", (0, 2000)))},
    **{("armour", "steering_box", k): (0, 2000) for k in ("mm", "deck_mm", "bulkhead_mm")},
    ("superstructure", "t_per_m2"): (0, 5), ("superstructure", "tower_levels"): (1, 30),
    ("superstructure", "levels_over_bridge"): (0, 30),
    ("superstructure", "deckhouse_levels"): (1, 30), ("superstructure", "plating_mm"): (0, 200),
    ("superstructure", "control_mm"): (0, 500),
    **{("fire_control", b, k): lim for b in ("main", "secondary", "aa") for k, lim in (
        ("directors", (0, 100)), ("rangefinder_m", (0, 50)), ("armour_mm", (0, 2000)), ("radar_t", (0, 500)),
        ("computer_t", (0, 500)))},
    ("fire_control", "search_radar_t"): (0, 500),
    ("funnels",): (0, 60), ("machinery", "tech", "draught", "velocity_m_s"): (1, 100), ("machinery", "tech", "draught", "gas_temp_k"): (300, 2000),
}

# numbers the physics divides by or takes as counts: outside these the result isn't silly but undefined, so they're
# checked even with no limits (design.py --no-limits). (path, low, low_inclusive, high or None)
DEFINED = (
    (("hull", "block_coefficient"), 0.0, False, 1.0), (("speed_kn",), 0.0, False, None),
    (("main", "barrels"), 1, True, None), (("main", "calibre_mm"), 0.0, False, None),
    (("main", "calibre_length"), 0.0, False, None), (("secondary", "barrels"), 1, True, None),
    (("secondary", "calibre_mm"), 0.0, False, None), (("secondary", "calibre_length"), 0.0, False, None),
    (("main", "rounds_per_gun"), 0, True, None), (("secondary", "rounds_per_gun"), 0, True, None),
)


# what a battery or torpedo outfit must give when the design has one (a non-empty dict; "secondary" may be a list)
REQUIRED = {"main": ("calibre_mm", "calibre_length", "barrels"),
            "secondary": ("calibre_mm", "calibre_length", "barrels"), "torpedoes": ("mounts", "tubes")}


def undefined_errors(design):
    """Missing gun and torpedo data (REQUIRED), and numbers outside the range where the physics means anything at
    all (DEFINED)."""
    errs = []
    for group, keys in REQUIRED.items():
        v = design.get(group)
        for i, b in enumerate(v if isinstance(v, list) else [v] if v else []):
            where = f"{group}[{i}]" if isinstance(v, list) else group
            if not isinstance(b, dict):
                errs.append(f"{where}: give an object with {', '.join(keys)}")
                continue
            errs += [f"{where}.{k} is missing" for k in keys if k not in b]
    for path, lo, incl, hi in DEFINED:
        ds = [design]
        for k in path[:-1]:
            ds = [e for d in ds for e in (lambda v: v if isinstance(v, list) else [v or {}])(d.get(k))]
        for d in ds:
            if path[-1] not in d:
                continue
            v = d[path[-1]]
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or (
                    v < lo if incl else v <= lo) or (hi is not None and v > hi):
                errs.append(f"{'.'.join(path)} = {v!r}: must be {'at least' if incl else 'above'} {lo}"
                            + (f" and at most {hi}" if hi is not None else ""))
    return errs


SUPERSTRUCTURE_KEYS = ("t_per_m2", "material", "plating_mm", "control_mm", "tower_levels", "deckhouse_levels",
                       "aft_control", "levels_over_bridge")
# what a raised stretch runs between, bow to stern: the ends and the features (layout.RAISED_ANCHORS)
RAISED_ANCHORS = ("bow", "fore_group", "bridge", "funnels", "aft_control", "aft_group", "stern")


def raised_errors(design, style) -> list[str]:
    """hull.raised: [{"from": an anchor, "to": an anchor, "decks": n}], raised stretches of hull over both anchors and
    all between (RAISED_ANCHORS: the bow, the stern or a feature; either order)."""
    rs = (design.get("hull") or {}).get("raised", [])
    if not isinstance(rs, list):
        return ["hull.raised: use a list of raised stretches, e.g. [{\"from\": \"bow\", \"to\": \"bridge\", "
                "\"decks\": 1}]"]
    if rs and not style.RAISED_HULL:
        return [f"hull.raised: the {style.name} style lays out its own raised decks"]
    errs = []
    for k, r in enumerate(rs):
        if not isinstance(r, dict):
            errs.append(f"hull.raised[{k}]: use {{\"from\", \"to\", \"decks\"}}")
            continue
        for key in ("from", "to"):
            if r.get(key) not in RAISED_ANCHORS:
                errs.append(f"hull.raised[{k}].{key} = {r.get(key)!r}: use one of {', '.join(RAISED_ANCHORS)}")
        if not (isinstance(r.get("decks"), int) and not isinstance(r.get("decks"), bool) and r["decks"] >= 1):
            errs.append(f"hull.raised[{k}].decks: use a whole number of decks, 1 or more")
    return errs
STANDS_ON = ("deck", "deckhouse")   # what a raisable battery stands on (layout.stands_on)


def superstructure_errors(design, style) -> list[str]:
    """superstructure: {"t_per_m2", "material", "tower_levels"} (the tower only on styles with a bridge tower)."""
    s = design.get("superstructure")
    if s is None:
        return []
    if not isinstance(s, dict):
        return ["superstructure: use {\"t_per_m2\", \"material\", \"tower_levels\"}"]
    errs = [f"superstructure.{k}: not a superstructure setting ({', '.join(SUPERSTRUCTURE_KEYS)})" for k in s
            if k not in SUPERSTRUCTURE_KEYS]
    if "t_per_m2" in s and not (isinstance(s["t_per_m2"], (int, float)) and s["t_per_m2"] >= 0):
        errs.append("superstructure.t_per_m2 must be a number, 0 or more")
    for k in ("plating_mm", "control_mm"):
        if k in s and not (isinstance(s[k], (int, float)) and s[k] >= 0):
            errs.append(f"superstructure.{k}: a number, 0 or more (0: the structure's own gauge)")
    if "material" in s and (not isinstance(s["material"], str) or not s["material"]):
        errs.append("superstructure.material: name the material as a string")
    if "deckhouse_levels" in s:
        if not style.DECKHOUSE_LEVELS:
            errs.append(f"superstructure.deckhouse_levels: the {style.name} style has no deckhouse levels yet")
        elif not isinstance(s["deckhouse_levels"], int) or s["deckhouse_levels"] < 1:
            errs.append("superstructure.deckhouse_levels: use a whole number, 1 or more")
    if "deckhouse" in s:
        errs.append("superstructure.deckhouse is gone: say what each battery stands on instead (secondary.stands_on, "
                    "main.amidships_stands_on: \"deck\" or \"deckhouse\"); level 1 is built under what needs it")
    if "tower_levels" in s:
        if not style.MIN_TOWER:
            errs.append(f"superstructure.tower_levels: the {style.name} style has no bridge tower")
        elif not isinstance(s["tower_levels"], int) or s["tower_levels"] < style.MIN_TOWER:
            errs.append(f"superstructure.tower_levels: use a whole number, {style.MIN_TOWER} or more")
    if "aft_control" in s:
        if not style.CONTROL_TOWERS:
            errs.append(f"superstructure.aft_control: the {style.name} style has no aft control")
        elif not isinstance(s["aft_control"], bool):
            errs.append("superstructure.aft_control: true or false")
    if "levels_over_bridge" in s:
        if not style.CONTROL_TOWERS:
            errs.append(f"superstructure.levels_over_bridge: the {style.name} style has no bridge tower of levels")
        elif not isinstance(s["levels_over_bridge"], int) or isinstance(s["levels_over_bridge"], bool) or \
                s["levels_over_bridge"] < 0:
            errs.append("superstructure.levels_over_bridge: use a whole number, 0 or more")
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
        import hullweight
        errs = powerplant.validate(design, self.DEFAULT_TECH) + crew.validate(design, self.CREW_STANDARD)
        if "type" in (design.get("machinery") or {}):
            errs.append("machinery.type is gone: give the plant's technology as machinery.tech "
                        "(plant-templates.md has examples by year)")
        errs += [f"hull.{k}: the designer works out the hull's size from what it carries; remove it"
                 for k in ("length", "beam") if k in (design.get("hull") or {})]
        errs += hullweight.validate(design)
        errs += armour_errors(design)
        import firecontrol
        errs += firecontrol.validate(design) + superstructure_errors(design, self) + raised_errors(design, self)
        if isinstance(design.get("secondary"), list) and not self.SECONDARY_LIST:
            errs.append(f"secondary: the {self.name} style takes one secondary battery, not a list")
        sec = design.get("secondary") or []
        for b in (sec if isinstance(sec, list) else [sec]):
            if "count" in b and "per_side" in b:
                errs.append("secondary: give count (total mounts) or per_side (pairs), not both")
            mount = b.get("mount", "deck")
            if mount not in ("deck", "casemate"):
                errs.append(f"secondary.mount = {mount!r}: use deck or casemate")
            elif mount == "casemate" and not self.CASEMATES:
                errs.append(f"secondary.mount: the {self.name} style has no casemates")
            if b.get("tier", "lower") not in ("lower", "upper"):
                errs.append(f"secondary.tier = {b['tier']!r}: use lower or upper (casemates only)")
            if "stands_on" in b:
                if not self.RAISED_MOUNTS:
                    errs.append(f"secondary.stands_on: the {self.name} style has no deckhouse to raise guns on")
                elif mount != "deck":
                    errs.append("secondary.stands_on: deck batteries only (casemates use tier)")
                elif b["stands_on"] not in STANDS_ON:
                    errs.append(f"secondary.stands_on = {b['stands_on']!r}: use {' or '.join(STANDS_ON)}")
        mains = design.get("main")
        if mains is not None and not isinstance(mains, (list, dict)):
            errs.append("main: use a list of batteries, each {\"calibre_mm\", \"calibre_length\", \"barrels\", "
                        "\"armour_mm\", \"fore\", \"aft\", ...}")
            mains = []
        mains = mains if isinstance(mains, list) else [mains] if mains else []
        if len(mains) > 1 and not self.MAIN_LIST:
            errs.append(f"main: the {self.name} style takes one main battery, not a list of several")
        for k, main in enumerate(mains):
            if not isinstance(main, dict):
                continue        # undefined_errors says what's missing
            w = f"main[{k}]"
            if main.get("mid") and not self.MIDSHIPS_TURRETS:
                errs.append(f"{w}.mid: the {self.name} style has no midships turrets")
            if main.get("wing") and not self.WING_TURRETS:
                errs.append(f"{w}.wing: the {self.name} style has no wing turrets")
            if "amidships_stands_on" in main:
                if not self.RAISED_MOUNTS:
                    errs.append(f"{w}.amidships_stands_on: the {self.name} style has no deckhouse to raise guns on")
                elif main["amidships_stands_on"] not in STANDS_ON:
                    errs.append(f"{w}.amidships_stands_on = {main['amidships_stands_on']!r}: use "
                                f"{' or '.join(STANDS_ON)}")
            if not isinstance(main.get("echelon", False), bool):
                errs.append(f"{w}.echelon: use true or false")
            if not isinstance(main.get("cross_deck", False), bool):
                errs.append(f"{w}.cross_deck: use true or false")
            sf = main.get("superfire", True)
            if not isinstance(sf, (bool, dict)) or (isinstance(sf, dict) and not all(
                    isinstance(v, int) and 0 <= v <= main.get(k_, 0) for k_, v in sf.items() if k_ in ("fore", "aft"))):
                errs.append(f"{w}.superfire: use true, false, or {{\"fore\": n, \"aft\": n}} within the group sizes")
        return errs + undefined_errors(design)

    DEFAULT_TECH = None         # machinery.tech when the design gives none (None: powerplant.DEFAULT_TECH)
    MAIN_LIST = False           # may "main" list several batteries (each with its own turrets and groups)
    MIDSHIPS_TURRETS = False    # does the layout support main["mid"]
    WING_TURRETS = False        # does the layout support main["wing"] (pairs) and main["echelon"]
    SECONDARY_LIST = False      # may "secondary" be a list of batteries with count/where (armament.batteries)
    CASEMATES = False           # may a secondary battery be "mount": "casemate" (guns in the hull side)
    MIN_TOWER = 0               # the lowest superstructure.tower_levels the style's bridge tower takes (0: no tower)
    DECKHOUSE_LEVELS = False    # does the layout take superstructure.deckhouse_levels
    CONTROL_TOWERS = False      # does the layout take superstructure.aft_control and levels_over_bridge
    RAISED_MOUNTS = False       # may wing / midships turrets and deck secondaries stand on the deckhouse (stands_on)
    RAISED_HULL = False         # does the layout take hull.raised (raised stretches of hull: forecastle, poop)

    def tuning(self, design) -> dict:
        """Overrides of navarch.TUNING for this design."""
        return {}

    def build_layout(self, design, res, shift=0.0, spread=0.0):
        """Lay the ship out for the solved weights res (navarch.Result: power, depth, draught, fuel, plant)."""
        raise NotImplementedError

    def rough_payload(self, design, D) -> list:
        """First-pass weights of style-specific items, before the layout exists."""
        return []

    def strength_deck(self, design, D):
        """A strength deck above the main deck (hullweight.hull_structure): dict(h, decks, plates) or None."""
        return None

    def structure_weights(self, design, L, B, T, D, geo, tun) -> list:
        """Style structure that depends on the hull (counted in standard displacement, before outfit)."""
        return []

    def weather_deck(self, design, L, B):
        """The weather deck the planking (hull.plating.deck_wood_mm) is laid on: (area m2, x, height above the main
        deck). The main deck by default; raised stretches stand over it, so the area holds."""
        import hullweight
        return hullweight.deck_area(L, B, design["hull"]["block_coefficient"]), 0.0, 0.0

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
