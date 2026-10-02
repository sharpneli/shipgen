"""
looks — visual styles: how a navy paints and builds its ships, with no effect on the design.

A design picks one with "look": "kure" (default "standard"). A look changes only the sprites: colours,
deck finish, funnel bands and how turrets are drawn. It never touches the layout, the physics, the
hitboxes or the sprite sizes, so the same design in two looks plays identically.

Each look has:
    palette    colour overrides for every ship style (DEFAULT_PALETTE keys, plus the optional
               "funnel_band" and "steel_line")
    by_style   further overrides for one style (merchant, planing, ...), applied over that style's own
               STYLE_PALETTES entry: a merchant keeps its merchant colours unless the look says otherwise
    turrets    how armoured (bb) turrets are drawn: "standard", "slab", "round", "classic" or "faceted"
               (shipgen.build_turret). The outline stays close to the hitbox shape (geometry.turret_shapes).
    shapes     silhouette variations, all drawn only (shipgen.look_hull_spec, Painter):
                 bow_power, bow_flare, transom   a fuller bow, a flared shoulder, a wider transom. Only ever
                                                 fuller than the layout's hull, so deck-edge fittings stay on deck
                 funnel   "box", "oval" or "capped" (default: stadium)
                 blocks   superstructure corners: "boxy", "soft", "bowfront" (round fronts, square backs) or
                          "chamfer" (default: as laid out)
                 mast     "pole": no tripod legs; "fighting_top": pole masts with a round fighting top
    shapes_by_style   further shape overrides for one style (optional)

Precedence, lowest first: DEFAULT_PALETTE, look palette, STYLE_PALETTES[style], look by_style, design "palette".
All colours live here: the design side (shipdesign, styles) has none.

To add a look: add an entry to LOOKS. A new turret style also needs a branch in shipgen.look_turret_body.
"""
from __future__ import annotations

# The renderer's base colours: a WWII haze-grey scheme (formerly fleet.py)
DEFAULT_PALETTE = {
    "line": "#1c2126",
    "hull": "#4b545d",
    "deck": "#7b858e",
    "wood": "#a68c63",
    "deck_line": "#3c3328",
    "levels": ["#8e979f", "#a3abb2", "#b6bdc3", "#c7cdd2"],
    "turret": "#959ea6",
    "barbette": "#6c757d",
    "barrel": "#454c53",
    "tube": "#5b636a",
    "tub": "#6f7880",
    "funnel": "#8a939b",
    "funnel_cap": "#2b2f33",
    "mast": "#30363b",
    "boat": "#c9ced2",
    "fitting": "#5e666d",
    "chain": "#2a2e32",
    "flight_deck": "#55606b",
    "marking": "#e9ece6",
    "stripe": "#e4c64a",
    "track": "#3b424a",          # catapult tracks
    "hatch": "#5d6650",          # cargo hatch tarpaulins
    "hatch_coaming": "#4a5157",
    "crane": "#3a4045",
}

# Each style's own colours, under any look (formerly the styles' PALETTE): merchants are not navy grey
STYLE_PALETTES = {
    "merchant": {"hull": "#2a2b2c", "deck": "#7f776b", "deck_line": "#3a352e",
                 "levels": ["#e3ded2", "#e9e5da", "#eeebe2", "#f2f0e9"], "funnel": "#b5852f",
                 "funnel_cap": "#1b1b1b", "boat": "#e6e2d8", "mast": "#4a3f33", "fitting": "#6a6258"},
    "planing": {"deck": "#6f7a72", "deck_line": "#2f3530", "hull": "#4d5650",
                "levels": ["#8b958e", "#9da69f", "#b0b8b2", "#c3cac5"]},
}

LOOKS = {
    # the original WWII haze-grey scheme
    "standard": dict(desc="Haze grey, generic", palette={}, by_style={}, turrets="standard", shapes={}),

    # US-inspired: Measure 21-style deck blue on every horizontal surface, boxy slab-sided turrets
    "brooklyn": dict(
        desc="US-inspired: deck-blue horizontals, boxy turrets",
        palette={"hull": "#465361", "deck": "#3e4b59", "wood": "#4f5b68", "deck_line": "#232b33",
                 "levels": ["#5d6b7a", "#6b7988", "#7a8795", "#8995a2"],
                 "turret": "#6a7a8b", "barbette": "#4a5765", "barrel": "#363e47", "tub": "#56636f",
                 "funnel": "#6b7988", "funnel_cap": "#20262c", "boat": "#8c98a4", "fitting": "#4d5964",
                 "mast": "#2a3138", "flight_deck": "#3b4858", "marking": "#eef0ea", "stripe": "#e4c64a"},
        by_style={"merchant": {"hull": "#4f5862", "deck": "#646d75", "deck_line": "#2f353b",   # wartime grey
                               "levels": ["#8c96a0", "#98a1aa", "#a4acb4", "#b0b7be"], "funnel": "#7d8892",
                               "funnel_band": "#1f1f1f", "boat": "#9aa4ad", "hatch": "#4c5560", "mast": "#2e353c"},
                  "planing": {"hull": "#3f4d3c", "deck": "#4f5d4a", "deck_line": "#262d23",
                              "levels": ["#62705c", "#6f7d68", "#7c8a75", "#8a9782"]}},
        turrets="slab",
        shapes={"transom": 0.15, "funnel": "box", "blocks": "boxy"}),

    # Japan-inspired: dark Kure grey, pale hinoki wood, brown linoleum on steel decks, black-topped funnels,
    # rounded turrets with long rangefinder arms, red and white carrier deck stripes
    "kure": dict(
        desc="Japan-inspired: Kure grey, linoleum decks, rounded turrets",
        palette={"hull": "#555a5c", "deck": "#7a5844", "wood": "#c8b58e", "deck_line": "#5c4a33",
                 "steel_line": "#b39050",
                 "levels": ["#767b7c", "#848989", "#929797", "#a0a4a4"],
                 "turret": "#7b8081", "barbette": "#5d6263", "barrel": "#3f4345", "tub": "#686d6e",
                 "funnel": "#787d7e", "funnel_cap": "#1c1d1e", "funnel_band": "#1c1d1e", "boat": "#b9b39f",
                 "fitting": "#5a5e5f", "mast": "#2d3032", "flight_deck": "#ae966b", "stripe": "#c63b2f",
                 "marking": "#f1eee6"},
        by_style={"merchant": {"hull": "#1e1f20", "deck": "#8f7a62", "deck_line": "#4a3d2e",    # black hull, white
                               "levels": ["#ece9e1", "#f0ede6", "#f3f1eb", "#f6f4ef"], "funnel": "#1d1d1d",
                               "funnel_band": "#e8e4d8", "hatch": "#4f5446", "mast": "#3a3027"},
                  "planing": {"hull": "#555a5c", "deck": "#6c7173", "deck_line": "#34383a",
                              "levels": ["#767b7c", "#848989", "#929797", "#a0a4a4"]}},
        turrets="round",
        shapes={"bow_flare": 0.08, "funnel": "oval", "blocks": "soft"}),

    # UK-inspired: pale Admiralty grey, holystoned teak, white boats, black funnel tops, straight-sided turrets
    # with a rounded rear
    "portsmouth": dict(
        desc="UK-inspired: light Admiralty grey, pale teak, black funnel tops",
        palette={"hull": "#7a8489", "deck": "#8b959a", "wood": "#d2c19b", "deck_line": "#7b6a4c",
                 "levels": ["#a9b1b5", "#b6bdc0", "#c3c9cb", "#d0d5d7"],
                 "turret": "#adb5b9", "barbette": "#828b90", "barrel": "#4c5458", "tub": "#8e979b",
                 "funnel": "#a9b1b5", "funnel_cap": "#1e2022", "funnel_band": "#1e2022", "boat": "#ecebe4",
                 "fitting": "#737c81", "mast": "#3b4246", "flight_deck": "#7d868b", "stripe": "#ecebe4"},
        by_style={"merchant": {"hull": "#232324", "deck": "#a39478", "deck_line": "#55493a",    # tramp: buff funnel
                               "levels": ["#e6e1d4", "#ebe7dc", "#efece3", "#f3f1ea"], "funnel": "#c9a24c",
                               "funnel_band": "#161616", "hatch": "#5b5f4a", "mast": "#8a6a3e"},
                  "planing": {"hull": "#8a9397", "deck": "#9aa3a7", "deck_line": "#5e676b",
                              "levels": ["#b3bbbe", "#bfc6c9", "#cbd1d3", "#d7dcde"]}},
        turrets="classic",
        shapes={"bow_power": 0.35, "transom": 0.05, "blocks": "bowfront"}),

    # German-inspired: dark grey hull and decks under light grey upperworks, mid teak, grey funnel caps,
    # faceted turrets
    "kiel": dict(
        desc="German-inspired: dark hull, light upperworks, faceted turrets",
        palette={"hull": "#4f5458", "deck": "#64696d", "wood": "#9e8159", "deck_line": "#3d3122",
                 "levels": ["#a2a7aa", "#aeb3b5", "#babec0", "#c6c9cb"],
                 "turret": "#9da2a5", "barbette": "#61666a", "barrel": "#3c4044", "tub": "#7a7f82",
                 "funnel": "#a2a7aa", "funnel_cap": "#2a2d30", "funnel_band": "#868b8e", "boat": "#cfd2d3",
                 "fitting": "#55595d", "mast": "#33373a", "flight_deck": "#6c675d", "stripe": "#e9ece6"},
        by_style={"merchant": {"hull": "#3a3e42", "deck": "#6f695f", "deck_line": "#3b362f",    # dark hull, grey
                               "levels": ["#d8dad8", "#dfe1df", "#e5e6e5", "#ebecea"], "funnel": "#1e1e1e",
                               "funnel_band": "#b3332a", "hatch": "#545a52", "mast": "#33373a"},
                  "planing": {"hull": "#8e9396", "deck": "#9fa4a7", "deck_line": "#5d6265",
                              "levels": ["#b5b9bb", "#c0c4c6", "#cbcfd0", "#d6d9da"]}},
        turrets="faceted",
        shapes={"bow_power": 0.2, "bow_flare": 0.04, "funnel": "capped", "blocks": "chamfer", "mast": "pole"}),

    # a period livery rather than a nation: the 1890s black, white and buff most navies wore. Holystoned teak,
    # black drum turrets with sighting hoods, buff funnels and masts with fighting tops, a full beamy bow.
    # Merchants get varnished teak deckhouses and a red funnel with a black top; torpedo craft are all black
    "victorian": dict(
        desc="1890s livery: black hull, white upperworks, buff funnels and masts",
        palette={"hull": "#1d1d1f", "deck": "#6b5f50", "wood": "#d6c7a2", "deck_line": "#8a7650",
                 "steel_line": "#3e352b",
                 "levels": ["#e9e5da", "#eeebe2", "#f2f0e9", "#f6f4ef"],
                 "turret": "#2c2c2e", "barbette": "#3a3a3c", "barrel": "#1b1b1c", "tub": "#2c2c2e",
                 "funnel": "#c9a04a", "funnel_cap": "#161616", "funnel_band": "#161616", "boat": "#f1eee6",
                 "fitting": "#3a3631", "mast": "#b08640", "flight_deck": "#cbb98f", "stripe": "#1d1d1f",
                 "marking": "#f4f1e8", "chain": "#1e1e1e", "crane": "#2c2c2e"},
        by_style={"merchant": {"hull": "#1b1b1c", "deck": "#c9b78f", "deck_line": "#7d6a46",
                               "levels": ["#8e5f35", "#9a6a3e", "#a67548", "#b28052"], "funnel": "#b8402e",
                               "funnel_band": "#161616", "boat": "#f1eee6", "hatch": "#4b4a3d", "mast": "#b08640"},
                  "planing": {"hull": "#1b1b1c", "deck": "#2f2f31", "deck_line": "#121213",
                              "levels": ["#3a3a3c", "#454547", "#505052", "#5b5b5d"], "turret": "#3a3a3c"}},
        turrets="drum",
        shapes={"bow_power": 0.4, "funnel": "oval", "blocks": "soft", "mast": "fighting_top"},
        shapes_by_style={s_: {"mast": "pole"} for s_ in ("merchant", "carrier", "planing")}),
}

DEFAULT_LOOK = "standard"


def style_name(design) -> str:
    return design.get("style", "warship")


def look_name(design) -> str:
    return design.get("look", DEFAULT_LOOK)


def get(design) -> dict:
    return LOOKS[look_name(design)]


def validate(design) -> list[str]:
    name = look_name(design)
    return [] if name in LOOKS else [f"look = {name!r}: use {', '.join(LOOKS)}"]


def shapes(design) -> dict:
    lk = get(design)
    return {**lk["shapes"], **lk.get("shapes_by_style", {}).get(style_name(design), {})}


def palette(design) -> dict:
    """The design's palette overrides (merged over DEFAULT_PALETTE by the renderer)."""
    lk, st = get(design), style_name(design)
    return {**lk["palette"], **STYLE_PALETTES.get(st, {}), **lk["by_style"].get(st, {}), **design.get("palette", {})}
