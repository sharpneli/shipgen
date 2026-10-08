"""
decks — the hull's deck stack: which decks a hull of a given depth has, their heights and names, and how raised
stretches of hull (forecastle, poop) add decks above the main deck over part of the length.

Deck 0 is the main deck, 1 the second deck, ... down to the inner bottom, every DECK_PITCH (geometry.DECK_PITCH,
shared with the layout and the renderer). Raised decks are -1, -2, ... and exist only over their stretches.
Design side, standard library only.
"""
from __future__ import annotations

from geometry import DECK_PITCH
import powerplant

MIN_TIER = 1.0         # a deck closer than this (m) to the inner bottom (the keel on a planing craft) is left out
MAX_DECKS = 60         # a backstop, far past any ship (156 m deep): a runaway depth must not build decks without end
DECK_NAMES = ["Main deck", "Second deck", "Third deck", "Fourth deck", "Fifth deck", "Sixth deck", "Seventh deck",
              "Eighth deck", "Ninth deck", "Tenth deck"]


def deck_name(n):
    """A deck's name by its number: 0 the main deck, 1, 2, ... down the stack; -1, -2, ... the decks of raised
    stretches of hull above it (forecastle, poop). The game's designer may give them period names."""
    if n < 0:
        return f"Raised deck {-n}"
    return DECK_NAMES[n] if n < len(DECK_NAMES) else f"Deck {n + 1}"


def deck_stack(design, D):
    """The hull's decks, every DECK_PITCH down from the main deck, as heights above the keel, top down:
    [(n, z)] with n = 0 the main deck, 1 the second deck, ... Stops MIN_TIER above the inner bottom (the keel on
    a planing craft); the main deck is always there."""
    floor = 0.0 if design.get("style") == "planing" else powerplant.double_bottom(D)
    out = [(0, D)]
    while D - len(out) * DECK_PITCH >= floor + MIN_TIER - 1e-9 and len(out) <= MAX_DECKS:
        out.append((len(out), D - len(out) * DECK_PITCH))
    return out


def raised_pieces(raised, s0, s1, k):
    """The stretch s0..s1 split where raised stretches (dicts x0, x1, levels) step: [(x0, x1, levels)], each with
    the raised decks over it, at most k."""
    xs = sorted({s0, s1} | {x for r in raised for x in (r["x0"], r["x1"]) if s0 < x < s1})
    out = []
    for a, b in zip(xs, xs[1:]):
        m = (a + b) / 2
        lv = min(k, max((r["levels"] for r in raised if r["x0"] <= m <= r["x1"]), default=0))
        if out and out[-1][2] == lv:
            out[-1] = (out[-1][0], b, lv)
        else:
            out.append((a, b, lv))
    return out
