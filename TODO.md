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
- [ ] Aft control only from 130 m (`layout.py` `la`); the mainmast goes with it, silently
- [ ] Bridge tower's levels over the bridge: 1, or 2 from 180 m (`layout.py` `over`)
- [ ] Mounts under 150 mm weigh 4 t more than at 150 mm (`navarch.mount_weights` `mech`)
- [ ] Rounds per gun step at 150 and 200 mm (`navarch.rounds_per_gun`)
- [ ] Officer share 0.15 under 30 crew, 0.08 from 30: 29 crew get 4 officers, 30 get 2 (`crew.py`)
- [ ] Sickbay only from 15 crew and over 3 days' endurance; +40 m² over 1000 crew (`crew.needs`)
- [ ] Carrier island default tower: 3 levels, 4 from 200 m (only without `tower_levels`)
- [ ] Merchants: 2 boats, 4 from 110 m (`styles/merchant.py`)
- [ ] Slender-hull warning at a hard-coded L/B 12 (the beamy one is `lb_warn` in tuning)
- [ ] Drawing: deck drawn as wood from 150 m regardless of `deck_wood_mm`; undocumented `"deck"` key
- [ ] Drawing: tripod foremast and breakwater from 150 m, depth-charge racks under 140 m, boat deck on roofs of 60 m² or more

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
- [ ] More multi-battery designs (KGV 2 × 4 + 1 × 2, Lord Nelson, Danton, Brennus)
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
- [ ] Buoyancy realism undecided; sinking demo lacks counter-flooding, displaced cargo/fuel, real plunge/capsize

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

## Shelved by the user
- Turtleback (sloped) armour decks
