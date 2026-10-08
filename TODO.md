# TODO

Open items from HANDOFF.md, one line each (details there). Keep this in sync: tick off or delete what's done, add what's found.

## Generator bugs
- [ ] `superfire: {"fore": 1}` with 3 fore turrets: B's sweep hits C (Nelson works around it)
- [ ] Main director 2 placed inside X's barrel sweep (Colorado uses 1 director)
- [ ] Wing turrets with `amidships_stands_on: "deck"` may overlap the bridge's level-1 core
- [ ] Batteries with different `stands_on` on one ship aren't kept apart (deck-level wing turrets leave raised secondaries forward of them with no deckhouse under them)
- [ ] Upper belt beyond the citadel ignores a short end belt's `reach`
- [ ] Nassau verify noise at the 0.85 threshold (use 0.845 or a finer raster)

## Hidden thresholds (user: no arbitrary cutoffs; details in HANDOFF)
- [ ] Officer share 0.15 under 30 crew, 0.08 from 30: 29 crew get 4 officers, 30 get 2 (`crew.py`)
- [ ] Sickbay only from 15 crew and over 3 days' endurance; +40 m² over 1000 crew (`crew.needs`)
- [ ] Carrier island default tower: 3 levels, 4 from 200 m (only without `tower_levels`)
- [ ] Merchants: 2 boats, 4 from 110 m (`styles/merchant.py`)
- [ ] Slender-hull warning at a hard-coded L/B 12 (the beamy one is `lb_warn` in tuning)
- [ ] Drawing: deck drawn as wood from 150 m regardless of `deck_wood_mm`; undocumented `"deck"` key
- [ ] Drawing: tripod foremast and breakwater from 150 m, depth-charge racks under 140 m, boat deck on roofs of 60 m² or more

## Code structure (review 2026-10-08; details in HANDOFF)
- [ ] Semantics parsed from ids: block role, mount battery (`battery_of`), `"W"` wing prefix, AA calibre from `"40" in type` (3x), vidgen regexes calibre
- [ ] Export numeric `calibre_mm`/`calibre_length` in sprite.json turret types and hitbox components
- [ ] Normalise "one battery or a list" once after validation (about 12 copies; secondary default 25 mm armour 5x)
- [ ] Split layout.py: shared primitives (public names) vs the warship's `build_layout` into styles/warship.py
- [ ] Armour out of navarch into its own module (geometry, weights, materials, extents, `armour_errors`)
- [ ] `armour_geometry` recomputed in 4 places: keep it on the solved result
- [ ] `lay.geo` is an untyped bag of ~20 keys; Layout gains attributes after `__init__` (`getattr(lay, "crew", None)`)
- [ ] Private `_` keys as side channels: `b["_plate_mm"]` (layout → hitbox), `spec["_clutter"]` (shipgen → render)
- [ ] Mount rest bearing stored twice (`lay.mounts`, `lay.spec["turrets"]`), synced by `assign_arcs`; published twice too
- [ ] Height columns and hitboxes restate the same shapes (AA `base + 2.0`, barbette `r * 0.95`, funnel rrect)
- [ ] `finish_layout` places the search radar and computes windage
- [ ] Split shipgen.py: SVG primitives and painter into a drawing module, legacy fleet CLI stays
- [ ] Shared reader for the exports (hull half-width exists 4 ways in hitview, vidgen, sinking); sinking imports render
- [ ] Arc helpers reimplemented (geometry, vidgen `in_arc`, verify, shipgen `clamp_angle`); legacy `traverse` means ± degrees
- [ ] Small: `RAISED_ANCHORS` defined twice; validators copy the dotted-path walk; merchant/planing import helpers from carrier

## Speed
- [ ] Extreme designs take 25–90 s: cache footprint bboxes and bucket by x in `Layout.free_at`

## Sizing and physics
- [ ] Beam refit after `spread_ends` (deferred by user)
- [ ] Pitch/yaw gyradius in the report (deferred by user)
- [ ] `M_req` undercounts the middle's length need (deferred by user)
- [ ] User-facing sizing parameters: hull form, beam preference, `Style.SIZE` rules, engine efficiency
- [ ] Cruise and fuel-range tuning (early turbine ships run 15–20 % long)
- [ ] Calibration: carriers' full load light, PT boat heavy, T2 tanker underpowered, Duilio and Inflexible +70 % heavy (long armoured middle)
- [ ] Unexplained weight gaps: Mikasa −19 %, Forrestal −27 %, Casablanca −22 %
- [ ] Research a real planing power model (`navarch.planing_power`)
- [ ] navarch GM uses its own cwp, not the hull form's; cwp doesn't know about transoms
- [ ] Ballast hint for low light-condition GM
- [ ] Small craft overmanned (PT boat, MTB)
- [ ] Barbette weight doesn't match the barbette hitbox depth
- [ ] Bulbous bow tickbox (optional)

## Powerplant and crew
- [ ] Generator rooms for electric transmission
- [ ] Carrier island crowds out directors when a split boiler plant adds funnels
- [ ] Cruising-turbine choice in the cruise model
- [ ] Funnel gas area not re-planned for raised (taller) funnels
- [ ] Hotel electrical load and distiller energy
- [ ] Crew fills citadel cells first (optional, deferred by user)
- [ ] Morale inputs in the report: quarters' surroundings (beside boilers, below waterline, wet ends) per rank
- [ ] Morale inputs in the report: per-rank sleep space and the officer/rating gap (`sleep_m2_per_man` is an all-hands average)

## Armament
- [ ] Default rounds per gun (designer UI default, `TUNING["rounds"]`): 8" gets as many as 18" (100); real treaty cruisers ~150
- [ ] Report: per-battery rounds and magazine tonnes, so the designer UI can show the endurance-vs-weight trade
- [ ] Abreast wing pairs keep full barrel swings apart: Lord Nelson and Danton run 30 % long
- [ ] Export ammunition per battery (propellant family, flash-reducer salt, bag or cased): vidgen guesses it from the navy (vidgen HANDOFF "Guns")
- [ ] Torpedo placement full check (Japanese-cruiser-size batteries, funnel spacing, swing room) (deferred by user)

## Superstructure
- [ ] Upper levels growing, gated by use (terraces recommended; fresh session)
- [ ] Corner styles per look for polygon blocks (separate session)
- [ ] Big ships' secondary directors sit low (~10 m); check tall-tower roofs too
- [ ] Bridge and aft-control level-1 cores are fixed beam fractions
- [ ] Deckhouse-levels extension runs when level 1 covers under half the middle
- [ ] Tall bridge vs short funnels: check the smoke check doesn't penalise height
- [ ] Deckhouse levels for merchants and carriers
- [ ] Idea: superstructure under superfiring mounts (Fletcher-style)
- [ ] Idea: deckhouses that taper with the hull
- [ ] Idea: `sweep.py` for knob sweeps
- [ ] Gun height has no payoff yet (needs a wetness/seakeeping model)

## Raised decks
- [ ] verify's barrel swing ignores raised decks
- [ ] No raised-deck anchor for wing/midships turrets
- [ ] Aft control's raised-deck break has no 0.75 m margin (bridge's has)
- [ ] Carriers don't take `hull.raised`
- [ ] No-forward-turret ship with a tall forecastle can fail trim

## Damage model and hitboxes
- [ ] Cells list barbettes, uptakes and casings passing through
- [ ] Double-bottom contents (oil, water)
- [ ] TDS layers in detail
- [ ] Clean up remaining shared cells
- [ ] Links and flags: engine room → shaft, generators → power networks, grouped vs alternating machinery, fuel type, bottom layers, riveted/welded, centreline bulkhead, TDS depth along length
- [ ] Carrier extras: flight-deck segments, lifts, hangar bays, avgas fore and aft
- [ ] Systems session: radar and masts, plotting room as a room, power and hydraulic networks, director armour material
- [ ] Reload torpedoes, depth charges and boats as hitboxes
- [ ] Destroyer has 19 sections (research: 12–16)
- [ ] Buoyancy realism undecided; sinking demo lacks counter-flooding, displaced cargo/fuel, real plunge/capsize (`sinking.Break`'s pieces have large-angle buoyancy; the flooding clips don't)

## Looks
- [ ] Victorian pass: `generic` and `portsmouth` still close
- [ ] Carriers, destroyers and merchants differ little between navies
- [ ] Merchant liveries: victorian all generic; treaty portsmouth/kure use wwii colours
- [ ] Older navies don't use the new features (dazzle, awnings, lattice masts)
- [ ] Toulon's blue-grey sits near the sea colour
- [ ] Brooklyn hull numbers crossed by anchor chains
- [ ] Fighting tops and two-tier tops hard to see
- [ ] Turret drawings not adjustable by numbers; `faceted` fits tightest (0.853)
- [ ] True mack (funnel and mast in one)
- [ ] Merchant clutter kit; awning stanchions, boat booms, derricks, signal lamps, coal-only gear
- [ ] Height map: columns only, clips above 63.75 m
- [ ] Baked light rim on blocks and funnels
- [ ] Missiles, helicopters and electronics for Cold War ships

## vidgen
- [ ] Shells and fire legible from high up (with ships firing at each other)
- [ ] Wake at ~0.5 px/m may read too smooth (a beam); faint lengthwise streaks could come back
- [ ] Battle extras (HANDOFF "Battle"): hit debris, near-miss deck wetting, dye stain in foam, camera moves and a zoom within a battle clip
- [ ] Line of battle: explosions and sinking on any ship of a line (blasts, Pose and the wreck are per scene, lead only)
- [ ] Line of battle: ships at different speeds or headings (hull layers cropped and moved, wakes shifted per frame)
- [ ] Breaking in two: sinkvid's own break clips still use a stand-in flash and smoke (`vidgen.py --explode Y --sink` has the real explosion)
- [ ] Breaking in two: shipgen should export weight extents (`sinking.weight_curve` spreads point weights by guessed spans)
- [ ] Breaking in two: shallow water (pieces grounding with ends out, Invincible-style)
- [ ] Mechanics resolver for magazine explosions (M, P(t), opening fail times; `magazine.F_FAST` is a stand-in)
- [ ] Gun blast extras not done: hull reflection of the blast, sun-shadow line, polar scour-foam texture, night flash lighting and exposure adaptation
- [ ] Explosion extras not done: fire reflection, heat haze, smoke self-shadow sweep, underwater/capsized blasts, debris hitting other ships
- [ ] Trailer (trailer.py): music; the explosion inside the battle once a line can explode (now a cut to a lone Lion)
- [ ] Sea (ocean.py) not done: whitecap foam for Beaufort 5+, gust patches, wave groups, ship heave/pitch/roll from the swell (research 5.2), wake foam riding the swell's displacement

## Shelved by the user
- Turtleback (sloped) armour decks
