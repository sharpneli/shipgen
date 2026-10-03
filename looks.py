"""
looks — visual styles: how a navy paints and builds its ships in a given era, with no effect on the design.

A design picks one with "look": {"navy": "kure", "era": "wwii"} (default generic, wwii). A look changes only the
sprites: colours, deck finish, funnel bands, how turrets are drawn and the silhouette. It never touches the
layout, the physics, the hitboxes or the sprite sizes, so the same design in two looks plays identically.

Looks are indexed twice: NAVIES[navy]["eras"][era]. A navy may change anything from one era to the next (paint,
turrets, bows), and navies differ freely from each other. A navy with no entry for an era is drawn as the
"generic" navy in that era, so every navy and era pair renders. ERAS lists the eras, oldest first.

Each look (one navy in one era) has:
    palette    colour overrides for every ship style (DEFAULT_PALETTE keys, plus the optional
               "funnel_band" and "steel_line")
    by_style   further overrides for one style (merchant, planing, ...), applied over that style's own
               STYLE_PALETTES entry: a merchant keeps its merchant colours unless the look says otherwise
    turrets    how armoured (bb) turrets are drawn: "standard", "slab", "round", "classic", "faceted" or "drum"
               (shipgen.build_turret). The outline stays close to the hitbox shape (geometry.turret_shapes).
    shapes     silhouette variations, all drawn only (shipgen.look_hull_spec, Painter):
                 bow_power, bow_flare, transom   a fuller bow, a flared shoulder, a wider transom. Only ever
                                                 fuller than the layout's hull, so deck-edge fittings stay on deck
                 funnel   "box", "oval" or "capped" (default: stadium)
                 blocks   superstructure corners: "boxy", "soft", "bowfront" (round fronts, square backs) or
                          "chamfer" (default: as laid out)
                 mast     "pole": no tripod legs; "fighting_top": pole masts with a round fighting top;
                          "cage": US lattice masts
    shapes_by_style   further shape overrides for one style (optional)
    adjust     colour nudges applied over the finished palette (optional, see below)
    from       inherit another look and list only the differences (optional, see below)

Nudging instead of repainting. An era step is often a small change: a lighter grey, a weathered deck, legs
taken off the tripods. Two keys let a look say only that:

    from      "era" (the same navy in another era) or "navy/era". The look starts as a copy of that one, then
              its own keys merge over it: palette, shapes and each style's by_style / shapes_by_style key by
              key, turrets replaced, adjust appended after the parent's. Chains are fine
    adjust    a list of colour operations, run in order over the finished palette (every key, style colours
              included), before the design's own "palette". Each is a dict:
                 keys      which colours: "all" (default), a GROUPS name, a palette key, or a list of these
                 lighten   -1..1: toward white (+) or black (-)
                 saturate  -1..1: toward grey (-) or away from it (+)
                 tint      [colour, amount]: blend toward the colour by amount (0..1)
                 styles    only for these styles (default every style), e.g. NAVAL to spare merchants
              e.g. [{"keys": "upperworks", "lighten": 0.15}, {"keys": "hull", "tint": ["#3e4b59", 0.2]}]
    adjust_by_style   further operations for one style, run after adjust (optional)

Shapes take numbers as well as the named modes (a named mode is a preset of the numbers, and a number given
beside it wins):
    block_round        [fore, aft] corner radius factors (boxy 0.35/0.35, soft 1.6/1.4, bowfront 1.5/0.4,
                       default 1/1)
    funnel_round       0..1 corner radius as a fraction of the funnel's half-width (box 0.44, default 1)
    funnel_squareness  superellipse exponent of the oval funnel (2.6; 2 = ellipse, higher = squarer)
    funnel_band_w      width of the painted top band in m (0.25)
    tripod             tripod leg length factor (1; 0 = pole masts; pole, fighting_top and cage give 0)
    top_r              fighting top radius in m (0 = none; fighting_top gives 1.6)
    top_tiers          stacked tops, each smaller and lighter (1; 3 or so reads as a pagoda)
    cage_r             US cage mast foot radius in m (0 = none; mast "cage" gives 3)
    deck_line_opacity  planking and plate seam lines (0.45; 0 = a plain deck)

Precedence, lowest first: DEFAULT_PALETTE, look palette, STYLE_PALETTES[style], look by_style, design "palette".
All colours live here: the design side (shipdesign, styles) has none.

To add a look: add an era entry under a navy in NAVIES (a new navy or era also goes in NAVIES or ERAS), often
just a "from" and a few nudges. A new turret style also needs a branch in shipgen.look_turret_body.
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

# Colour groups an adjust operation can name (any palette key works too)
GROUPS = {
    "hull": ["hull"],
    "decks": ["deck", "wood", "deck_line", "steel_line", "flight_deck"],
    "upperworks": ["levels", "boat", "fitting", "crane"],
    "armament": ["turret", "barbette", "barrel", "tube", "tub"],
    "funnels": ["funnel", "funnel_cap", "funnel_band"],
    "rigging": ["mast", "chain"],
    "markings": ["marking", "stripe", "track"],
    "cargo": ["hatch", "hatch_coaming"],
}


def _rgb(c):
    return [int(c[i:i + 2], 16) for i in (1, 3, 5)]


def _hex(c):
    return "#" + "".join(f"{max(0, min(255, round(v))):02x}" for v in c)


def _mix(a, b, t):
    return [x + (y - x) * t for x, y in zip(a, b)]


def adjust_colour(c: str, op: dict) -> str:
    """One adjust operation (lighten, saturate, tint; any of them, in that order) on one #rrggbb colour."""
    rgb = _rgb(c)
    k = op.get("lighten", 0.0)
    if k:
        rgb = _mix(rgb, [255] * 3 if k > 0 else [0] * 3, abs(k))
    k = op.get("saturate", 0.0)
    if k:
        grey = [0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]] * 3
        rgb = _mix(rgb, grey, -k) if k < 0 else [v + (v - g) * k for v, g in zip(rgb, grey)]
    if op.get("tint"):
        col, t = op["tint"]
        rgb = _mix(rgb, _rgb(col), t)
    return _hex(rgb)


def _op_keys(keys) -> set | None:
    """The palette keys an operation touches (None: all of them)."""
    keys = keys or "all"
    out = set()
    for k in [keys] if isinstance(keys, str) else keys:
        if k == "all":
            return None
        out.update(GROUPS.get(k, [k]))
    return out


def adjust_palette(pal: dict, ops: list) -> dict:
    """pal with each adjust operation applied in turn. List values (levels) are adjusted item by item."""
    pal = dict(pal)
    for op in ops:
        keys = _op_keys(op.get("keys"))
        for k, v in pal.items():
            if keys is not None and k not in keys:
                continue
            pal[k] = [adjust_colour(c, op) for c in v] if isinstance(v, list) else adjust_colour(v, op)
    return pal


# The styles that wear navy paint; an adjust with "styles": NAVAL leaves merchants their own colours
NAVAL = ["warship", "carrier", "planing"]
# Masts outside warships: no fighting tops, pagodas or cages
_PLAIN_MASTS = {s_: {"top_r": 0.0, "cage_r": 0.0} for s_ in ("merchant", "carrier", "planing")}

# The eras a look can be drawn in, oldest first
ERAS = ("victorian", "great_war", "treaty", "wwii", "cold_war")

# NAVIES[navy]["eras"][era] is one look. National navies are named after a dockyard; "generic" is no navy in
# particular and stands in for any navy without its own entry for an era
NAVIES = {
    "generic": dict(
        desc="No navy in particular",
        eras={
            # the 1890s black, white and buff most navies wore. Holystoned teak, black drum turrets with sighting
            # hoods, buff funnels and masts with fighting tops, a full beamy bow. Merchants get varnished teak
            # deckhouses and a red funnel with a black top; torpedo craft are all black
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
                                       "funnel_band": "#161616", "boat": "#f1eee6", "hatch": "#4b4a3d",
                                       "mast": "#b08640"},
                          "planing": {"hull": "#1b1b1c", "deck": "#2f2f31", "deck_line": "#121213",
                                      "levels": ["#3a3a3c", "#454547", "#505052", "#5b5b5d"], "turret": "#3a3a3c"}},
                turrets="drum",
                shapes={"bow_power": 0.4, "funnel": "oval", "blocks": "soft", "mast": "fighting_top"},
                shapes_by_style={s_: {"mast": "pole"} for s_ in ("merchant", "carrier", "planing")}),
            # 1904-1920: the first service greys, darker than later ones; tall tripods with spotting tops, teak,
            # black funnel tops. Merchants keep their own colours
            "great_war": {
                "from": "wwii", "desc": "1904-1920: dark early grey, teak decks, tripods with spotting tops",
                "palette": {"funnel_band": "#2b2f33"},
                "adjust": [{"keys": ["hull", "upperworks", "armament", "funnels", "rigging"], "lighten": -0.15,
                            "styles": NAVAL},
                           {"keys": "decks", "tint": ["#8a6a3e", 0.25], "styles": NAVAL}],
                "shapes": {"bow_power": 0.25, "funnel": "oval", "tripod": 1.3, "top_r": 1.4, "funnel_band_w": 0.4,
                           "deck_line_opacity": 0.6},
                "shapes_by_style": _PLAIN_MASTS},
            # 1920-1936: light peacetime grey, holystoned white teak, tripods with director tops
            "treaty": {
                "from": "wwii", "desc": "1920-1936: light peacetime grey, white teak, tripods with director tops",
                "palette": {"funnel_band": "#2b2f33"},
                "adjust": [{"keys": ["hull", "upperworks", "armament", "funnels"], "lighten": 0.15, "styles": NAVAL},
                           {"keys": "wood", "tint": ["#e2d5b5", 0.3], "styles": NAVAL}],
                "shapes": {"bow_power": 0.15, "tripod": 1.2, "top_r": 1.1, "funnel_band_w": 0.4},
                "shapes_by_style": _PLAIN_MASTS},
            # the original WWII haze-grey scheme
            "wwii": dict(desc="Haze grey, generic", palette={}, by_style={}, turrets="standard", shapes={}),
            # 1950-1970: bluish haze grey, dark non-skid steel decks, pole and lattice masts, welded boxy upperworks
            "cold_war": {
                "from": "wwii", "desc": "1950-1970: haze grey, dark non-skid decks, pole masts, boxy upperworks",
                "palette": {"deck": "#4c5359", "steel_line": "#2a2f34", "flight_deck": "#3e444a"},
                "adjust": [{"keys": ["hull", "upperworks", "armament", "funnels"], "tint": ["#6e7d8c", 0.12],
                            "styles": NAVAL}],
                "shapes": {"tripod": 0.0, "blocks": "boxy", "funnel": "capped", "deck_line_opacity": 0.2}},
        }),
    "brooklyn": dict(
        desc="US-inspired",
        eras={
            # US-inspired 1890s-1900s, the Great White Fleet: white hull and turrets, buff upperworks, funnels and masts
            "victorian": {
                "from": "generic/victorian", "desc": "US-inspired 1890s-1900s: white hull, buff upperworks and funnels",
                "palette": {"hull": "#ecebe5", "wood": "#d8c8a0", "deck": "#8c8170",
                            "levels": ["#cfb07a", "#d6b984", "#ddc28f", "#e4cb9a"],
                            "turret": "#ecebe5", "barbette": "#d6d3c9", "barrel": "#2b2b2c", "tub": "#dcd9cf",
                            "funnel": "#c9a04a", "funnel_cap": "#161616", "funnel_band": "#161616",
                            "boat": "#f4f2ec", "fitting": "#8a7d63", "mast": "#b8913f", "crane": "#8a7d63"},
                "turrets": "slab",
                "shapes": {"transom": 0.15, "blocks": "boxy"}},
            # US-inspired 1910s: light blue-tinged grey, cage masts, boxy turrets
            "great_war": {
                "from": "generic/great_war", "desc": "US-inspired 1910s: light blue-grey, cage masts, boxy turrets",
                "adjust": [{"keys": ["hull", "upperworks", "armament", "funnels"], "lighten": 0.12, "styles": NAVAL},
                           {"keys": ["hull", "upperworks"], "tint": ["#6f8aa3", 0.08], "styles": NAVAL}],
                "turrets": "slab",
                "shapes": {"transom": 0.15, "funnel": "box", "blocks": "boxy", "mast": "cage", "tripod": 0.0,
                           "top_r": 0.0}},
            # US-inspired 1920s-30s: light navy grey, the cage masts kept until the rebuilds
            "treaty": {
                "from": "generic/treaty", "desc": "US-inspired 1920s-30s: light navy grey, cage masts, boxy turrets",
                "adjust": [{"keys": ["hull", "upperworks"], "tint": ["#6f8aa3", 0.08], "styles": NAVAL}],
                "turrets": "slab",
                "shapes": {"transom": 0.15, "funnel": "box", "blocks": "boxy", "mast": "cage", "tripod": 0.0,
                           "top_r": 0.0}},
            # US-inspired: Measure 21-style deck blue on every horizontal surface, boxy slab-sided turrets
            "wwii": dict(
                desc="US-inspired: deck-blue horizontals, boxy turrets",
                palette={"hull": "#465361", "deck": "#3e4b59", "wood": "#4f5b68", "deck_line": "#232b33",
                         "levels": ["#5d6b7a", "#6b7988", "#7a8795", "#8995a2"],
                         "turret": "#6a7a8b", "barbette": "#4a5765", "barrel": "#363e47", "tub": "#56636f",
                         "funnel": "#6b7988", "funnel_cap": "#20262c", "boat": "#8c98a4", "fitting": "#4d5964",
                         "mast": "#2a3138", "flight_deck": "#3b4858", "marking": "#eef0ea", "stripe": "#e4c64a"},
                # merchants: wartime grey
                by_style={"merchant": {"hull": "#4f5862", "deck": "#646d75", "deck_line": "#2f353b",
                                       "levels": ["#8c96a0", "#98a1aa", "#a4acb4", "#b0b7be"], "funnel": "#7d8892",
                                       "funnel_band": "#1f1f1f", "boat": "#9aa4ad", "hatch": "#4c5560",
                                       "mast": "#2e353c"},
                          "planing": {"hull": "#3f4d3c", "deck": "#4f5d4a", "deck_line": "#262d23",
                                      "levels": ["#62705c", "#6f7d68", "#7c8a75", "#8a9782"]}},
                turrets="slab",
                shapes={"transom": 0.15, "funnel": "box", "blocks": "boxy"}),
            # US-inspired 1950s-60s: haze grey over deck-grey non-skid
            "cold_war": {
                "from": "generic/cold_war", "desc": "US-inspired 1950s-60s: haze grey, deck-grey non-skid, boxy turrets",
                "palette": {"deck": "#454c54", "flight_deck": "#3b424a"},
                "turrets": "slab",
                "shapes": {"transom": 0.15, "funnel": "box"}},
        }),
    "kure": dict(
        desc="Japan-inspired",
        eras={
            # Japan-inspired 1890s-1900s: the Tsushima war paint, dark green-grey all over, black funnel bands
            "victorian": {
                "from": "generic/victorian", "desc": "Japan-inspired 1890s-1900s: dark green-grey war paint, black bands",
                "palette": {"hull": "#4f534f", "deck": "#5d605b", "wood": "#b9a57f", "deck_line": "#5c4a33",
                            "steel_line": "#3a3d39",
                            "levels": ["#6d716c", "#7a7e79", "#878b86", "#949893"],
                            "turret": "#5f635e", "barbette": "#4f534f", "barrel": "#2a2c2b", "tub": "#5f635e",
                            "funnel": "#5f635e", "funnel_cap": "#161616", "funnel_band": "#161616",
                            "boat": "#9fa29b", "fitting": "#4a4d49", "mast": "#3f423e", "crane": "#4a4d49"},
                "turrets": "round",
                "shapes": {"bow_flare": 0.04}},
            # Japan-inspired 1910s: British-built lines and turrets, dark grey, tripods, black funnel tops
            "great_war": {
                "from": "generic/great_war", "desc": "Japan-inspired 1910s: British-built turrets, dark grey, tripods",
                "palette": {"funnel_band": "#1c1d1e"},
                "adjust": [{"keys": ["hull", "upperworks", "armament", "funnels"], "tint": ["#555a5c", 0.35],
                            "styles": NAVAL}],
                "turrets": "classic",
                "shapes": {"blocks": "soft", "bow_flare": 0.04}},
            # Japan-inspired 1920s-30s: the Kure look before the rebuilds: smaller early pagodas, finer bows
            "treaty": {
                "from": "wwii", "desc": "Japan-inspired 1920s-30s: Kure grey, linoleum decks, early pagoda masts",
                "shapes": {"bow_flare": 0.04, "top_r": 2.6, "top_tiers": 2}},
            # Japan-inspired: dark Kure grey, pale hinoki wood, brown linoleum on steel decks, black-topped funnels,
            # rounded turrets with long rangefinder arms, red and white carrier deck stripes
            "wwii": dict(
                desc="Japan-inspired: Kure grey, linoleum decks, rounded turrets",
                palette={"hull": "#555a5c", "deck": "#7a5844", "wood": "#c8b58e", "deck_line": "#5c4a33",
                         "steel_line": "#b39050",
                         "levels": ["#767b7c", "#848989", "#929797", "#a0a4a4"],
                         "turret": "#7b8081", "barbette": "#5d6263", "barrel": "#3f4345", "tub": "#686d6e",
                         "funnel": "#787d7e", "funnel_cap": "#1c1d1e", "funnel_band": "#1c1d1e", "boat": "#b9b39f",
                         "fitting": "#5a5e5f", "mast": "#2d3032", "flight_deck": "#ae966b", "stripe": "#c63b2f",
                         "marking": "#f1eee6"},
                # merchants: black hull, white house
                by_style={"merchant": {"hull": "#1e1f20", "deck": "#8f7a62", "deck_line": "#4a3d2e",
                                       "levels": ["#ece9e1", "#f0ede6", "#f3f1eb", "#f6f4ef"], "funnel": "#1d1d1d",
                                       "funnel_band": "#e8e4d8", "hatch": "#4f5446", "mast": "#3a3027"},
                          "planing": {"hull": "#555a5c", "deck": "#6c7173", "deck_line": "#34383a",
                                      "levels": ["#767b7c", "#848989", "#929797", "#a0a4a4"]}},
                turrets="round",
                # pagoda masts built up round the tripods
                shapes={"bow_flare": 0.08, "funnel": "oval", "blocks": "soft", "tripod": 1.4, "top_r": 3.2,
                        "top_tiers": 3},
                shapes_by_style=_PLAIN_MASTS),
            # Japan-inspired 1950s-60s: Kure-tinted haze grey, rounded turrets, flared bows
            "cold_war": {
                "from": "generic/cold_war", "desc": "Japan-inspired 1950s-60s: Kure-tinted haze grey, rounded turrets",
                "adjust": [{"keys": ["hull", "upperworks", "armament", "funnels"], "tint": ["#555a5c", 0.2],
                            "styles": NAVAL}],
                "turrets": "round",
                "shapes": {"funnel": "oval", "blocks": "soft", "bow_flare": 0.08}},
        }),
    "portsmouth": dict(
        desc="UK-inspired",
        eras={
            # UK-inspired 1890s: the Victorian black, white and buff with bright holystoned planking on every deck,
            # hooded barbettes and military masts with two fighting tops
            "victorian": {
                "from": "generic/victorian", "desc": "UK-inspired 1890s: black, white and buff, two-tier fighting tops",
                "palette": {"wood": "#e4d8b8", "deck": "#cbbd99", "deck_line": "#9a8660", "steel_line": "#8f7b56"},
                "turrets": "classic",
                "shapes": {"blocks": "bowfront", "top_r": 1.9, "top_tiers": 2}},
            # UK-inspired 1910s: darker Edwardian grey, weathered teak, tall tripods with spotting tops
            "great_war": {
                "from": "wwii", "desc": "UK-inspired 1910s: dark grey, weathered teak, tripods with spotting tops",
                "adjust": [{"keys": ["hull", "upperworks", "armament", "funnels"], "lighten": -0.25, "styles": NAVAL},
                           {"keys": "decks", "tint": ["#8a6a3e", 0.3], "styles": NAVAL}],
                "shapes": {"tripod": 1.3, "top_r": 1.4, "funnel_band_w": 0.6, "deck_line_opacity": 0.7},
                "shapes_by_style": _PLAIN_MASTS},
            # UK-inspired 1920s-30s: light Home Fleet grey, white teak, tripods with director tops
            "treaty": {
                "from": "wwii", "desc": "UK-inspired 1920s-30s: light Home Fleet grey, white teak, director tops",
                "adjust": [{"keys": ["hull", "upperworks", "armament", "funnels"], "lighten": 0.1, "styles": NAVAL},
                           {"keys": "wood", "tint": ["#e6dcc0", 0.3], "styles": NAVAL}],
                "shapes": {"tripod": 1.2, "top_r": 1.1, "funnel_band_w": 0.4},
                "shapes_by_style": _PLAIN_MASTS},
            # UK-inspired: pale Admiralty grey, holystoned teak, white boats, black funnel tops, straight-sided turrets
            # with a rounded rear
            "wwii": dict(
                desc="UK-inspired: light Admiralty grey, pale teak, black funnel tops",
                palette={"hull": "#7a8489", "deck": "#8b959a", "wood": "#d2c19b", "deck_line": "#7b6a4c",
                         "levels": ["#a9b1b5", "#b6bdc0", "#c3c9cb", "#d0d5d7"],
                         "turret": "#adb5b9", "barbette": "#828b90", "barrel": "#4c5458", "tub": "#8e979b",
                         "funnel": "#a9b1b5", "funnel_cap": "#1e2022", "funnel_band": "#1e2022", "boat": "#ecebe4",
                         "fitting": "#737c81", "mast": "#3b4246", "flight_deck": "#7d868b", "stripe": "#ecebe4"},
                # merchants: tramp colours, buff funnel
                by_style={"merchant": {"hull": "#232324", "deck": "#a39478", "deck_line": "#55493a",
                                       "levels": ["#e6e1d4", "#ebe7dc", "#efece3", "#f3f1ea"], "funnel": "#c9a24c",
                                       "funnel_band": "#161616", "hatch": "#5b5f4a", "mast": "#8a6a3e"},
                          "planing": {"hull": "#8a9397", "deck": "#9aa3a7", "deck_line": "#5e676b",
                                      "levels": ["#b3bbbe", "#bfc6c9", "#cbd1d3", "#d7dcde"]}},
                turrets="classic",
                shapes={"bow_power": 0.35, "transom": 0.05, "blocks": "bowfront"}),
            # UK-inspired 1950s-60s: light Admiralty grey over dark non-skid, black funnel tops
            "cold_war": {
                "from": "generic/cold_war", "desc": "UK-inspired 1950s-60s: light Admiralty grey, dark non-skid decks",
                "palette": {"funnel_band": "#1e2022"},
                "adjust": [{"keys": ["hull", "upperworks", "armament", "funnels"], "lighten": 0.08, "styles": NAVAL}],
                "turrets": "classic",
                "shapes": {"bow_power": 0.35, "transom": 0.05, "blocks": "bowfront"}},
        }),
    "kiel": dict(
        desc="Germany-inspired",
        eras={
            # German-inspired 1890s: the Kaiserliche Marine's light grey with yellow-buff funnels, heavy military tops
            "victorian": {
                "from": "generic/victorian", "desc": "German-inspired 1890s: light grey, yellow-buff funnels",
                "palette": {"hull": "#a9afb2", "deck": "#7d8386", "wood": "#c2a679", "deck_line": "#6e5a3a",
                            "steel_line": "#5a6064",
                            "levels": ["#bfc4c6", "#c9cdcf", "#d3d6d8", "#dde0e1"],
                            "turret": "#b3b8bb", "barbette": "#8e9497", "barrel": "#2e3134", "tub": "#9fa5a8",
                            "funnel": "#d8b64e", "funnel_cap": "#161616", "funnel_band": "#161616",
                            "boat": "#eeeeea", "fitting": "#6a7073", "mast": "#5a5f62", "crane": "#6a7073"},
                "turrets": "faceted",
                "shapes": {"funnel": "capped", "blocks": "chamfer", "top_r": 1.8}},
            # German-inspired 1910s: light blue-grey, pole masts with small spotting tops, faceted turrets
            "great_war": {
                "from": "generic/great_war", "desc": "German-inspired 1910s: light blue-grey, pole masts, faceted turrets",
                "adjust": [{"keys": ["hull", "upperworks", "armament", "funnels"], "lighten": 0.2, "styles": NAVAL},
                           {"keys": ["hull", "upperworks"], "tint": ["#7d8fa0", 0.08], "styles": NAVAL}],
                "turrets": "faceted",
                "shapes": {"bow_power": 0.2, "bow_flare": 0.04, "funnel": "capped", "blocks": "chamfer", "tripod": 0.0,
                           "top_r": 0.9}},
            # German-inspired 1920s-30s: the Reichsmarine's lighter hull, pole masts with spotting tops
            "treaty": {
                "from": "wwii", "desc": "German-inspired 1920s-30s: lighter hull, pole masts with spotting tops",
                "adjust": [{"keys": "hull", "lighten": 0.12, "styles": NAVAL}],
                "shapes": {"top_r": 0.9},
                "shapes_by_style": _PLAIN_MASTS},
            # German-inspired: dark grey hull and decks under light grey upperworks, mid teak, grey funnel caps,
            # faceted turrets
            "wwii": dict(
                desc="German-inspired: dark hull, light upperworks, faceted turrets",
                palette={"hull": "#4f5458", "deck": "#64696d", "wood": "#9e8159", "deck_line": "#3d3122",
                         "levels": ["#a2a7aa", "#aeb3b5", "#babec0", "#c6c9cb"],
                         "turret": "#9da2a5", "barbette": "#61666a", "barrel": "#3c4044", "tub": "#7a7f82",
                         "funnel": "#a2a7aa", "funnel_cap": "#2a2d30", "funnel_band": "#868b8e", "boat": "#cfd2d3",
                         "fitting": "#55595d", "mast": "#33373a", "flight_deck": "#6c675d", "stripe": "#e9ece6"},
                # merchants: dark hull, light grey house
                by_style={"merchant": {"hull": "#3a3e42", "deck": "#6f695f", "deck_line": "#3b362f",
                                       "levels": ["#d8dad8", "#dfe1df", "#e5e6e5", "#ebecea"], "funnel": "#1e1e1e",
                                       "funnel_band": "#b3332a", "hatch": "#545a52", "mast": "#33373a"},
                          "planing": {"hull": "#8e9396", "deck": "#9fa4a7", "deck_line": "#5d6265",
                                      "levels": ["#b5b9bb", "#c0c4c6", "#cbcfd0", "#d6d9da"]}},
                turrets="faceted",
                shapes={"bow_power": 0.2, "bow_flare": 0.04, "funnel": "capped", "blocks": "chamfer", "mast": "pole"}),
            # German-inspired 1950s-60s: light haze grey, faceted turrets, capped funnels
            "cold_war": {
                "from": "generic/cold_war", "desc": "German-inspired 1950s-60s: light haze grey, faceted turrets",
                "adjust": [{"keys": ["hull", "upperworks", "armament", "funnels"], "lighten": 0.1, "styles": NAVAL}],
                "turrets": "faceted",
                "shapes": {"bow_power": 0.2, "bow_flare": 0.04, "funnel": "capped",
                           "blocks": "chamfer"}},
        }),
}

DEFAULT_LOOK = {"navy": "generic", "era": "wwii"}


def style_name(design) -> str:
    return design.get("style", "warship")


def look_of(design) -> dict:
    """The design's look, {"navy", "era"}, with defaults filled in."""
    return {**DEFAULT_LOOK, **design.get("look", {})}


def resolve(design) -> tuple[str, str]:
    """The (navy, era) actually drawn: the design's navy, or "generic" if that navy has no entry for the era."""
    lk = look_of(design)
    navy = lk["navy"] if lk["era"] in NAVIES[lk["navy"]]["eras"] else "generic"
    return navy, lk["era"]


def look_label(design) -> str:
    """The look as text for the preview sheet, e.g. "kure / wwii" ("" for the default look)."""
    lk = look_of(design)
    if lk == DEFAULT_LOOK:
        return ""
    navy, _ = resolve(design)
    return f"{lk['navy']} / {lk['era']}" + (" (drawn as generic)" if navy != lk["navy"] else "")


def _by_style_merge(a: dict, b: dict) -> dict:
    return {s_: {**a.get(s_, {}), **b.get(s_, {})} for s_ in {**a, **b}}


def look(navy: str, era: str, _seen=()) -> dict:
    """One look with its "from" chain resolved: every key filled in, adjust lists concatenated."""
    if (navy, era) in _seen:
        raise ValueError(f"look {navy}/{era}: 'from' loops back on itself")
    lk = NAVIES[navy]["eras"][era]
    if "from" not in lk:
        return {"palette": {}, "by_style": {}, "turrets": "standard", "shapes": {}, **lk}
    src = lk["from"]
    pn, pe = src.split("/") if "/" in src else (navy, src)
    base = look(pn, pe, _seen + ((navy, era),))
    out = {**base, **{k: v for k, v in lk.items() if k != "from"}}
    for k in ("palette", "shapes"):
        out[k] = {**base.get(k, {}), **lk.get(k, {})}
    for k in ("by_style", "shapes_by_style"):
        out[k] = _by_style_merge(base.get(k, {}), lk.get(k, {}))
    out["adjust"] = base.get("adjust", []) + lk.get("adjust", [])
    ab, al = base.get("adjust_by_style", {}), lk.get("adjust_by_style", {})
    out["adjust_by_style"] = {s_: ab.get(s_, []) + al.get(s_, []) for s_ in {**ab, **al}}
    return out


def get(design) -> dict:
    return look(*resolve(design))


def validate(design) -> list[str]:
    lk = design.get("look", {})
    if not isinstance(lk, dict):
        return [f'look = {lk!r}: give {{"navy": ..., "era": ...}}']
    extra = sorted(set(lk) - set(DEFAULT_LOOK))
    errs = [f"look has unknown keys: {', '.join(extra)}"] if extra else []
    lk = look_of(design)
    if lk["navy"] not in NAVIES:
        errs.append(f"look.navy = {lk['navy']!r}: use {', '.join(NAVIES)}")
    if lk["era"] not in ERAS:
        errs.append(f"look.era = {lk['era']!r}: use {', '.join(ERAS)}")
    return errs


def shapes(design) -> dict:
    lk = get(design)
    return {**lk["shapes"], **lk.get("shapes_by_style", {}).get(style_name(design), {})}


def palette(design) -> dict:
    """The design's palette overrides (merged over DEFAULT_PALETTE by the renderer)."""
    lk, st = get(design), style_name(design)
    pal = {**lk["palette"], **STYLE_PALETTES.get(st, {}), **lk["by_style"].get(st, {})}
    ops = [op for op in lk.get("adjust", []) + lk.get("adjust_by_style", {}).get(st, []) if st in op.get("styles", [st])]
    if ops:
        pal = adjust_palette({**DEFAULT_PALETTE, **pal}, ops)
    return {**pal, **design.get("palette", {})}


# Catch a mistyped "from" or era name when the module loads, not halfway through a render
for _navy, _n in NAVIES.items():
    for _era in _n["eras"]:
        assert _era in ERAS, f"look {_navy}/{_era}: {_era!r} is not in ERAS"
        look(_navy, _era)
