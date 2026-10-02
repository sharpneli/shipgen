"""
looks — visual styles: how a navy paints and builds its ships, with no effect on the design.

A design picks one with "look": "kure" (default "standard"). A look changes only the sprites: colours,
deck finish, funnel bands and how turrets are drawn. It never touches the layout, the physics, the
hitboxes or the sprite sizes, so the same design in two looks plays identically.

Each look has:
    palette    colour overrides for every ship style (shipgen.DEFAULT_PALETTE keys, plus the optional
               "funnel_band" and "steel_line")
    by_style   further overrides for one style (merchant, planing, ...), applied over that style's own
               PALETTE: a merchant keeps its merchant colours unless the look says otherwise
    turrets    how armoured (bb) turrets are drawn: "standard", "slab", "round", "classic" or "faceted"
               (shipgen.build_turret). The outline stays close to the hitbox shape (geometry.turret_shapes).
    shapes     silhouette variations, all drawn only (shipgen.look_hull_spec, Painter):
                 bow_power, bow_flare, transom   a fuller bow, a flared shoulder, a wider transom. Only ever
                                                 fuller than the layout's hull, so deck-edge fittings stay on deck
                 funnel   "box", "oval" or "capped" (default: stadium)
                 blocks   superstructure corners: "boxy", "soft", "bowfront" (round fronts, square backs) or
                          "chamfer" (default: as laid out)
                 mast     "pole": no tripod legs

Precedence, lowest first: DEFAULT_PALETTE, look palette, style PALETTE, look by_style, design "palette".

To add a look: add an entry to LOOKS. A new turret style also needs a branch in shipgen.look_turret_body.
"""
from __future__ import annotations

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
}

DEFAULT_LOOK = "standard"


def look_name(design) -> str:
    return design.get("look", DEFAULT_LOOK)


def get(design) -> dict:
    return LOOKS[look_name(design)]


def validate(design) -> list[str]:
    name = look_name(design)
    return [] if name in LOOKS else [f"look = {name!r}: use {', '.join(LOOKS)}"]


def palette(design, style) -> dict:
    """The design's palette overrides (merged over shipgen.DEFAULT_PALETTE by the renderer)."""
    lk = get(design)
    return {**lk["palette"], **style.PALETTE, **lk["by_style"].get(style.name, {}), **design.get("palette", {})}
