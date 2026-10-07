"""
warship: displacement-hull armoured warships, destroyer to battleship. The layout is layout.py.

"secondary" is one battery or a list of them, each with per_side and "mount": "deck" (the default: amidships, on the
main deck or the deckhouse as its "stands_on" says) or "casemate" (in the hull side, below the main deck).
"""
from __future__ import annotations

from layout import build_layout
from styles.base import Style


class Warship(Style):
    name = "warship"
    MAIN_LIST = True         # several main batteries, sharing the turret groups (layout.py)
    MIDSHIPS_TURRETS = True
    WING_TURRETS = True
    SECONDARY_LIST = True    # several secondary batteries, each on deck or in casemates (layout.py)
    CASEMATES = True
    MIN_TOWER = 2            # the bridge (level 2) at least
    DECKHOUSE_LEVELS = True
    RAISED_MOUNTS = True     # main.amidships_stands_on, secondary.stands_on
    RAISED_HULL = True       # hull.raised

    def build_layout(self, design, res, shift=0.0, spread=0.0):
        return build_layout(design, res, shift, spread)


STYLE = Warship()
