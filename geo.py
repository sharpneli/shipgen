"""Layout facts: what the layout found that the physics and the later passes need (Layout.geo).

The layout (layout.py and each style's build_layout) writes them; navarch.solve, armour.armour_geometry, the
styles' weights, crew, subdivision, ordnance, propulsion, firecontrol, hitbox and shipdesign read them. Before a
layout exists (the first rough solve) navarch gets a bare Geo(), so the before-layout defaults live here, as
methods taking the length.

slots: writing a field that isn't declared here fails, so a typo can't make a new key. A field a style never
sets keeps its default; every None below means "no layout has said", and the reader decides what that means.

Lives in its own module, not layout.py: navarch and armour need it, and layout imports navarch.
"""
from __future__ import annotations

from dataclasses import dataclass

import propulsion


@dataclass(slots=True)
class Geo:
    # the layout's shift of everything along the hull to trim the ship (m, + forward); the size search sets it
    shift: float = 0.0
    # the machinery block's span (x0, x1) and its middle, where navarch puts the plant and fuel weights
    machinery: tuple | None = None
    machinery_x: float | None = None
    # layout.plan_machinery's plant: dict(fuel, space, segments, wing_t, wing_m, end_m, width, height,
    # inner_bottom, top, armoured, deck_mm, tds, decks)
    plant: dict | None = None
    # powerplant.funnel_plan for the planned boilers (layout.plan_funnels)
    funnel_plan: dict | None = None
    # how far astern of a funnel its smoke spoils a director (powerplant.smoke_reach); directors keep out of it
    smoke_reach: float = 0.0
    # the stretch (x0, x1) the vital spaces, belt and citadel armour decks cover (layout.set_citadel)
    citadel: tuple | None = None
    # the steering gear's stretch (x0, x1) and the hull's mean width over it (layout.add_steering)
    steering: tuple | None = None
    steering_beam: float | None = None
    # raised stretches of hull: Layout.raised (dict(id, x0, x1, levels)), for hullweight's girder and the armour
    raised: list | tuple = ()
    # what the wind sees from abeam (layout.lateral_profile: dict(area_m2, z_m)), for the wind heel
    windage: dict | None = None
    # the bridge's level and what decided it (warship layout): dict(level, floor, need, tower, turret_roof)
    bridge: dict | None = None
    # merchant: the cargo holds' spans [(x0, x1), ...]
    holds: list | None = None
    # carrier: the aviation magazines' and aviation fuel's centres (x, z above the main deck)
    magazine: tuple | None = None
    avgas: tuple | None = None

    def machinery_mid(self, L):
        """Where the plant's and fuel's weights stand: the machinery's middle, or a little abaft amidships."""
        return -0.02 * L if self.machinery_x is None else self.machinery_x

    def citadel_span(self, L):
        """The citadel's stretch, or the middle 0.6 L."""
        return self.citadel or (-0.3 * L, 0.3 * L)

    def steering_span(self, L):
        """The steering gear's stretch: the layout's or the rule's (propulsion.steering_span)."""
        return self.steering or propulsion.steering_span(L)
