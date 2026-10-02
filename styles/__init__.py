"""
styles: ship design styles. A style is a family of ships built on the same principles; everything else
(battleship vs battlecruiser, destroyer vs cruiser) is just the design's "type" label.

    warship   displacement-hull armoured warships, destroyer to battleship (layout.py)
    carrier   aircraft carriers: flight deck (axial or angled) or seaplane carrier (no flight deck)
    merchant  cargo ships and tankers; carry cargo deadweight
    planing   planing-hull fast craft: motor torpedo boats, PT boats, motor gunboats

A design picks its style with "style" (default "warship"). Warships and planing craft are built around their
main battery. Carriers and merchants have none: their guns are secondaries fitted where they suit (a list of
batteries with count/where, see armament.batteries), so a merchant can carry guns (Q-ship, DEMS) and a
carrier can carry cruiser guns.

Each style module provides the hooks of styles.base.Style. To add a style, subclass Style in a new
module and register it in STYLES below.
"""
from __future__ import annotations

import importlib

STYLES = {"warship": "styles.warship", "carrier": "styles.carrier", "merchant": "styles.merchant",
          "planing": "styles.planing"}
_cache = {}


def get(design_or_name):
    name = design_or_name if isinstance(design_or_name, str) else design_or_name.get("style", "warship")
    if name not in STYLES:
        raise KeyError(f"unknown style {name!r} (known: {', '.join(STYLES)})")
    if name not in _cache:
        _cache[name] = importlib.import_module(STYLES[name]).STYLE
    return _cache[name]
