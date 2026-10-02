"""
warship: displacement-hull armoured warships, destroyer to battleship. The layout is layout.py.
"""
from __future__ import annotations

from layout import build_layout
from styles.base import Style


class Warship(Style):
    name = "warship"
    MIDSHIPS_TURRETS = True
    LIMITS = {("hull", "length"): (50, 1000)}

    def build_layout(self, design, shp, depth, shift=0.0):
        return build_layout(design, shp, depth, shift)


STYLE = Warship()
