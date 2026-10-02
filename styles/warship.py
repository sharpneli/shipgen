"""
warship: displacement-hull armoured warships, destroyer to battleship. The layout is layout.py.

"secondary" is one battery or a list of them, each with per_side and "mount": "deck" (the default: on the deckhouse
amidships) or "casemate" (in the hull side, below the main deck).
"""
from __future__ import annotations

from layout import build_layout
from styles.base import Style


class Warship(Style):
    name = "warship"
    MIDSHIPS_TURRETS = True
    WING_TURRETS = True
    SECONDARY_LIST = True    # several secondary batteries, each on deck or in casemates (layout.py)
    CASEMATES = True
    LIMITS = {("hull", "length"): (50, 1000)}

    def build_layout(self, design, shp, depth, shift=0.0):
        return build_layout(design, shp, depth, shift)


STYLE = Warship()
