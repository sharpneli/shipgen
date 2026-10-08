"""
weights — the Weight record every design module books its tonnes in (navarch.solve sums them), and the densities
they are weighed with. Design side, standard library only.
"""
from __future__ import annotations

from dataclasses import dataclass

STEEL = 7.85  # t/m^3
SEAWATER = 1.025  # t/m^3


@dataclass
class Weight:
    name: str
    group: str
    w: float
    x: float = 0.0
    z: float | None = None              # absolute height above keel, set once D is known
    z_rel: tuple = ("frac", 0.5)         # ("frac", k) -> k*D ; ("deck", h) -> D + h
