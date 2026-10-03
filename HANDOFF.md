# Handoff notes for the next session

Read README.md first: it documents the inputs, outputs and conventions. This file covers what the README
doesn't: the decisions behind the current design, how to work safely here, and what's still open.

## Decisions the user made (don't undo them without asking)
- **Style vs type:** `style` is the design family (warship, carrier, merchant, planing). `type` (BB, BC, DD, ...) is only a gameplay label. Battlecruisers and destroyers are warships.
- **Arcs are fixed by mount kind** (`hitbox.ARC_*`), never deduced from obstructions. The user wanted no fiddling.
  - End turrets: ±135°. Side mounts, including wing turrets: ±90°.
  - Side-firing centreline turrets (flush turrets behind a superfiring one, amidships turrets): ±65° about each beam.
  - Fixed MTB tubes: ±1°.
- **Side-firing turrets stow fore-and-aft** like real ships, so their rest bearing is outside their arcs. The game trains them out before firing.
- **Wing turrets never fire across the deck,** echelon ones included. That's their deliberate limitation. Each fires only on its own side, from dead ahead to dead astern (`main.wing` pairs, `main.echelon`), and stows fore-and-aft at the edge of that arc. Wing turrets forward of amidships can therefore join the forward group's fire: A plus a wing pair gives 3 guns ahead, and A, B plus a pair gives 4. The layout keeps their muzzles short of the end groups' inner turrets.
- **Warships are built around their guns.** Main turrets are placed first and reserve their barrel sweep (`Layout.reserve_sweep`). Superstructure placed later must keep out of it.
- **Carriers and merchants have no main battery.** All their guns are secondaries fitted where they suit, and overlap is acceptable. Planing craft still have a main battery; the user hasn't decided whether MTB guns should become secondaries.
- **The generator is permissive.** Gameplay limits will live in the game's designer UI. `--no-limits` skips the input ranges entirely. Silly designs may look stupid or fail the physics, but they must run.
- **Looks are visual only** (`"look"` in the design, `looks.py`). The user wants ships of different powers to look different with no gameplay effect: a look may change only the sprite images, never the layout, physics, report results, hitboxes or `sprite.json`. Turret drawings and silhouettes (bow, stern, funnels, superstructure corners, masts) differ by look, but hitboxes always use the layout's shapes. A look's hull may only be fuller than the layout's, never finer, so deck-edge fittings stay on deck. **Looks are indexed by navy and era** (`"look": {"navy", "era"}`, `looks.NAVIES[navy]["eras"][era]`; user, 2026-10-03), because a navy's ships should change over time. A navy may change anything between eras, turret drawings and hull shapes included, and navies differ freely. A missing pair is drawn as `generic` in that era. Navies are named after dockyards: `generic`, `brooklyn` (US), `kure` (Japan), `portsmouth` (UK), `kiel` (Germany). Eras so far: `victorian` (only `generic` has one) and `wwii` (the four national looks and the old `standard`). Mikasa is `kure`/`victorian` and victory_1944 `portsmouth`/`victorian`, both drawn as generic until those navies get a victorian entry. The game picks the era (its calendar, a refit), not the design's physics: `render_ship(look={"era": ...})` repaints.
- **Design and drawing are separate, with a plain-data contract** (`shipdesign.build(design) -> ship` dict; `render.render_ship(ship, ...)`). The user's game calls the design side on every knob change in its designer UI and needs it fast; the preview may lag. Keep the rules: the design side (shipdesign, navarch, layout, armament, hitbox, styles) uses the standard library only and never imports the renderer; the renderer (render, shipgen, shadow, looks) imports no design-side module and reads only the `ship` dict; `geometry.py` is the shared layer. Colours live only in `looks.py`. A physics refactor should change only the design side, and a drawing change only the render side.
- Shadows come from the height map, not baked in. Mips are packed per layer (`<layer>_mips.png`, rects in `sprite.json`).
- **No period-based physics (user, 2026-10-03).** Nothing is weighed or limited by era: 10 t of armour weighs 10 t whenever it was designed. Differences between periods come from material science, given in the design as numbers like `machinery.tech`. For armour, the material (`armour.materials`, a plain string passed through to the hitboxes) sets its protective value in the game's ballistics; mass stays thickness × area × density. There are no artificial period limits. Armour schemes such as all-or-nothing or incremental aren't rules here either: the inputs only describe where the armour is, and a separate game system will handle design styles.
- **Mip atlases are an interchange format only.** The game uploads each level to the GPU separately (Vulkan mip layout is hardware dependent) and never samples the packed image, so the missing gutters don't matter. Large sprites are fine too: the game may drop the biggest mip levels.

## Planned by the user
- **The game spans about 1890 to 1970:** pre-dreadnoughts, through the dreadnought era, to early modern ships. Defaults and new features should cover that whole range.
- **More looks** (`looks.py`). The navy × era scaffolding is done (2026-10-03); filling it in is next, probably in a fresh session. Eras I suggested, none confirmed yet: `victorian` (1885–1903), `great_war` (1904–1920, first greys, tripods, US cage masts, dazzle), `treaty` (1920–1936, light peacetime greys, awnings, pagoda masts), `wwii` (1937–1946), `cold_war` (1950–1970, non-skid decks, lattice masts, macks, deck numbers). Possible new navies: Italy (`la_spezia`, forecastle recognition stripes) and France (`toulon`). Palette-only eras are cheap; awnings, deck stripes, new masts and camouflage need new Painter features. Kongo (1913) is `kure`/`wwii` for now and belongs in `great_war` once it exists.
- **Casemates (done):** warship `secondary` may be a list of batteries, each `"mount": "deck"` or `"casemate"`. Casemates fire ±60° about the beam and come in two tiers: `"lower"` in the hull side, and `"upper"` in housings on the main deck, staggered between the lower guns. The user is happy with 2 tiers for now and explicitly wants silly builds, such as a WWII-tech ship of the line, to work. Examples: `mikasa`, `connecticut`, `nassau_casemates`, `kongo`, `victory_1944`. Open items:
  - The pre-dreadnoughts came out light (Mikasa 11.3k std against 15.1k t real). The secondary armour brought them closer (Mikasa 12.3k t, Connecticut 14.5k t against 16k t). Any remaining gap is for material and tech inputs (hull construction, plant), never a period factor.
  - Lower and upper guns never stack at the same x (from above, stacked guns would look like one). Stacked British two-storey casemates therefore come out staggered.
  - Connecticut's 203 mm wing turrets need a second main battery, which ties into the French "floating hotels" below.
  - verify.py flags the 88 mm casemates at the ends of `nassau_casemates` at about 0.85 at one 37° angle. It's rasterisation of a 2 px barrel; the other angles score 0.89–0.96. It flips between pass and fail as the beam moves by a few cm (it failed at 0.849 after the belt band change on 2026-10-03, then passed after the belt taper), so treat it as noise.
- **French "floating hotel" pre-dreadnoughts** with many different calibres: several main and intermediate batteries, often in wing turrets. The layout will need more than one main or secondary battery.
- **Powerplant (done; `powerplant.py`, `research/powerplant-model.md`, README "Design input").** All four steps of the session plan are in:
  1. plant size and weight from the tech
  2. the machinery block with rooms and bunkers
  3. funnels from gas flow and uptake reach, with midships turrets only in gaps next to the boilers
  4. smoke on control positions, and the published plant numbers (report `plant`)
  - The user's decisions:
    - There is no year input: designs carry the tech as numbers (`machinery.tech`), because players may research things early or late.
    - `plant-templates.md`, written by `plant_templates.py`, has example blocks by year for authoring designs.
    - The spec is "not taken 1:1". Ships getting longer and looking different as requirements are added is fine.
  - Departures from the spec:
    - Boiler rooms use the whole height to the bounding deck. Only engine rooms keep the spec's "unit height + 2.5 m" cap, so low turbines no longer make boiler rooms long. With that, the spec's own densities (ST7 0.34, ST8 0.36) give sensible WWII lengths, so they're unchanged.
    - The forward boiler group may run on under the bridge (`layout.BRIDGE_OVER_BOILERS`, 0.85 of its length). Its funnels stay on open deck.
    - Funnel casings are drawn at 3× the gas area (`powerplant.CASING`).
    - Coal wing bunkers run up to the main deck.
    - Oil also fills the torpedo protection's liquid layers.
    - Funnels never limit arcs. They compete through sweep reservation instead, since arcs stay fixed.
    - Natural and boost draught plants get funnel tops 25 m above the grates (`layout.STACK_NATURAL`).
  - **Calibration (as of 2026-10-02):**
    - Most designs now land within about 10% of the real ships' lengths: Nassau 159.5 m, Mikasa 122.5 m, Connecticut 128 m, the battleship 257 m, the heavy cruiser 200 m, the fleet carrier 245.5 m.
    - Early turbine ships run 15–20% long: Dreadnought 185 m against 160 m, Invincible 192 m against 172 m, Kongo 257 m against 214 m.
    - Most of the rest is cruise fuel: early direct turbines are very inefficient at cruise, so Kongo carries 8,800 t, much of it in end bunkers. That's left for the fuel-range tuning the user plans, together with hull width (beam preference).
  - Not done yet:
    - Generator rooms for electric transmission aren't placed separately.
    - The cruise model has no cruising-turbine choice (the template has a "with cruising turbines" variant).
    - Fuel tonnage drives bunker length, but coal's protective value isn't modelled (that's the game's).
- **Crew (done; `crew.py`, `research/crew-space-model.md`, README "Design input").** The user's decisions:
  - Standards are numbers in the design. The six spec standards are only template blocks (`crew-templates.md`). In the game a slider sets them, and the crew's mood is simulated smoothly from what the ship has.
  - `endurance_days` is its own input. A ship may loiter far longer than its fuel range (a tender). Shorter than the range is silly but only warns.
  - Crew lives in any empty volume, hull or superstructure. At this scale, too narrow for real people is fine.
  - Implementation:
    - The complement is departmental: plant, guns, deck and command, air group, then hotel.
    - Volume is checked against `crew.USABLE` × empty volume. Shortfall is a "length" need, so the hull grows.
    - Crew, provisions and water are explicit weights. `misc_frac` was cut to compensate: warship 0.055, carrier 0.075, merchant 0.03, planing 0.07.
    - The subdivision quarters the crew in free cells above the waterline.
  - Era designs now carry H1 hammocks (pre-1925 warships, the Q-ship, victory_1944).
  - Calibration (as of 2026-10-02):
    - Complements: battleship 1,821 (Iowa about 1,920 as designed), Dreadnought 873, Mikasa 836, Liberty 81 (41 crew + 25 gunners).
    - Lengths barely move, except where crew space binds: Mikasa 133 m (real 131.7 m), the Fletcher-like destroyer 132.5 m (114 m; it carries the wartime 326 men).
    - Small craft are overmanned: PT boat 31 men against about 17, MTB 20 against 13. They come out 5–6 m long. The spec's petrol `crew_k` (3) and the small-gun crews are the knobs.
  - Left game-side: comfort, fatigue and morale (report `crew` carries the inputs), and the damage hooks (fire load, off-watch casualties, sickbay).
  - Later: hotel electrical load and distiller energy (no generator plant yet), and accommodation spilling into a grown superstructure as an alternative to length.
- Remaining physics work:
  - Material inputs, with no period factors (see the decision above): the hull construction (riveted or welded, steel grade). The armour material is done as a string reference.
  - The parameters the user plans for sizing (hull form, beam preference).
- Research to replace the planing power placeholder (`navarch.planing_power`). It's one function by design.
- **Size from contents (done; README "Design input"):** designs give no length or beam (`hull.length` and `hull.beam` are now validation errors). The designer works out the hull from what it carries, and hitting a tonnage or length target is the player's job.
  - The rules and their default values (`Style.SIZE`, `shipdesign.min_length`, merchant `STOWAGE`) are internal for now. The user will add parameters to control them later (engine efficiency etc.), probably alongside the material inputs.
  - Calibration: most realistic designs land within 2–10% of the real ship's length.
  - Known quirks:
    - Beams come out a little narrow on pre-dreadnoughts (Mikasa 19.9 m against 23.2 m real), because the GM target of 0.06 × beam is met.
    - Nassau comes out long and narrow (172 × 24 m, real 146 × 27 m), because the search finds the shortest length at the narrowest beam that works, and wing turrets can trade beam for length.
    - The `hint` makes a knob change about twice as fast.
  - A designer UI should show length, beam and displacement prominently, since they're now outputs.
- **Damage model data (`research/`; `warship-damage-research.md` is the synthesis, §13 the wish list).** shipgen emits only the physical model (hitboxes per system, armour, links). What a hit does is the game's business.
  - Step 1 (done): `vertical` heights, the `armour` section, turret face/side/rear/roof, barbettes down to the armour deck, block roles, the conning tower, and one magazine per mount with links.
  - **Step 2, the subdivision grid (done 2026-10-02; `subdivision.py`, README "Outputs").** The hull below the main deck is sections × tiers × bands of cells that tile it. The layout's compartments are rooms snapped to whole cells, and every cell has exactly one owning room. `hitboxes.json` lost its old `compartments` and gained `sections`, `decks`, `tiers`, `bulkheads`, `cells` and `rooms`.
    - The user's decisions:
      - **There's no game yet**, so the hitboxes format is free to change. "Go wild": the end goal is a complex designer, so the game only has to care about results like horsepower and top speed.
      - **Secondary and abreast wing-turret magazines are grouped** at the ends of the machinery block (option b, as on real ships with ammunition passages). They're sized by ammunition weight (now `ordnance.T_PER_M3`, 0.6 t/m³ since 2026-10-03).
        - A first try at 2r × 2r per mount made Mikasa 27 m longer.
        - Now lengths move a few metres: Mikasa 129 m (was 133), Kongo 263.5 m (was 257.5), Invincible 194.5 m (was 192), victory_1944 107 m (was 114).
      - **The extra tier** (a flat at the waterline) was replaced on 2026-10-03 by the deck stack (below).
    - Tuning knobs: `MIN_SECTION` 0.03 L (1–8 m), `MAX_SECTION` 0.07 L, `MIN_TIER` 1 m, `ROOM_PRIORITY` (magazine > machinery > steering = bunkers > holds), `PERMEABILITY`.
    - Sections:
      - Capital ships get 17–21, the destroyer 19 (research: 12–16), the PT boat 10 and the MTB 9 (a single tier).
      - A station where several rooms end counts for more when close stations merge.
    - Cells: 9–220 per ship. The export adds about 2–9 ms per build.
    - A room smaller than any cell shares one (`also` on the cell, `shared` on the room). Examples: Mikasa's small casemate magazines inside the main secondary magazine's cell, small end bunkers, and the tanker's steering gear inside its aft engine room. The merchant layout overlaps those two when the engines are aft.
    - Planing craft have no inner bottom.
    - Crew is quartered in unclaimed cells above the waterline. `crew._accommodation` is gone.
    - Still to do:
      - shafts, propellers and rudders
      - per-cell lists of what passes through (barbettes, uptakes)
      - double-bottom contents (oil, water)
      - TDS layers in detail
  - Step 3: links and flags, best done alongside the material inputs: engine room to shaft (uptakes to boiler rooms are done), generators to fore and aft power networks, grouped or alternating machinery, fuel type, centreline bulkhead, torpedo protection depth along the length. Carrier extras: flight-deck segments, lifts, hangar bays, avgas fore and aft.
  - **Buoyancy:** the user hasn't decided how realistic it should be. It will likely be a grid, but it must not drive a full simulation of the ship's motion. Flooding only makes the ship settle: a deeper draught costs speed and puts more of the belt under water.
  - Known simplification: the barbette weight (`navarch.mount_weights`, 0.45 × depth) doesn't match the barbette hitbox, which reaches down to the armour deck.

- **Deck stack and armour decks (done 2026-10-03).** The user wanted magazines low in the ship, with living space above them, and several armour decks.
  - The user's decisions:
    - The deck pitch is a constant (`navarch.DECK_PITCH`, 2.6 m), not a design knob.
    - Armour decks are an explicit list in every design, top down: `armour.decks = [{"deck": n, "mm", "extent": "citadel" | "full"}]`. Deck 0 is the main deck. `deck_mm` is now a validation error. Every design file was converted to the stack deck nearest its old armour deck. That's deck 1 on most ships, and the fleet carrier 2, the supercarrier 3, Gangut 7. Unarmoured designs got `"decks": []`.
    - Superstructure levels stay out of the grid, maybe for good ("not that interesting").
  - Rules (README "Design input"):
    - The thickest armour deck is the main one: the belt reaches up to it, and the barbettes reach down to it.
    - The lowest armour deck is the roof over the machinery and magazines.
    - The waterline flat is gone. Tiers carry a `submerged` fraction, and quarters go in tiers less than half under water.
    - Cells' `armour_above_mm` is now a list, top down.
  - Magazines stand on the inner bottom (`ordnance.span`). A turret's magazine rises as many decks as its ammunition needs. Grouped magazines are planned 2 deck spaces tall (`ordnance.TIERS`).
    - The magazine density (`ordnance.T_PER_M3`) went from 0.35 to 0.6, because the handling space is now the free deck above. That kept the lengths near their old values.
  - Calibration moves:
    - Mikasa 129 → 138 m (real 131.7). Its old armour deck sat 1.6 m below the main deck; deck 1 is 2.6 m down, so the machinery is shorter in height and the block longer.
    - victory_1944 100.5 → 87.5 m.
    - Belted capital ships gain 3–5% standard displacement (Kongo +1.3k t, battleship +1.5k t), because the belt now reaches the second deck.
    - Everything else is within ±2.5 m.
  - New example: `battleship_layered.json`, with a 38 mm full-length bomb deck, the 152 mm second deck and a 16 mm splinter deck on the third. It comes out at 263 m against the battleship's 257 m, because the splinter deck lowers the roof.
  - Not done:
    - The merchants' holds still span the full height (the steering gear was lowered later the same day). The carrier aviation magazines and avgas tanks were lowered the same day. The user wants a roughly realistic stack: the hangar under the flight deck, and whatever explodes easily below that. An armour-piercing bomb's fuse should be set off by the armour deck, so it bursts before it reaches the magazine. Their weights moved down with them: carriers' GM rose a few cm, and the escort carrier is 0.5 m longer.
    - **Turtleback (sloped) decks: left out on purpose (user, 2026-10-03).** For simplicity, several flat armour decks are enough for now.
- **Secondary armour (started 2026-10-03).** The user asked for end belts and upper belts, so that armour schemes from pre-dreadnought to all-or-nothing can all be built.
  - The knobs (README "Design input"), written out in every design:
    - `bulkhead_mm` (was fixed at 0.6 × belt; the designs got that value rounded, a few tonnes' change)
    - `upper_belt` `{mm, to_deck, extent}`
    - `end_belts` `{fore, aft: {mm, tip_mm}}`, linear taper to the ends
    - deck extents `fore`, `aft` and `ends`. A deck may appear twice over different stretches.
  - The main belt stays `belt_mm`, so the hitboxes' `armour.belt` is unchanged. The rest is `armour.strakes`, and a deck with several plates lists `plates`. A cell's `belt_mm` is the thickest strake beside it.
  - All the geometry lives in `navarch.armour_geometry` (`strakes`, `bulkhead_top`), so the weights and the hitboxes can't disagree.
  - Only plates over the citadel (`citadel` or `full`) can be the main armour deck or the roof, and only they make a ship "armoured" (its machinery casings and gratings).
  - The period designs carry their real schemes. Gangut is left alone, because it's a silly test design. Calibration moves, standard displacement with the real ship in brackets:
    - Mikasa 10.5k → 12.6k t (15.1k), 129.5 × 21.8 m (131.7 × 23.2). The pre-dreadnoughts were light and narrow, and both improved.
    - Connecticut 12.1k → 14.8k t (16k), 134 × 23 m (139 × 23.4).
    - Nassau 17.7k → 21k t (18.9k).
    - Invincible 18.7k → 20.1k t (17.4k).
    - Dreadnought 22k → 27k t (18.1k), 187.5 m. Its armour is 10k t against about 5k t real, mostly from before: a long citadel, and a 76 mm deck where the real ship had 19–44 mm. Armour mass is physical and won't get a period factor, so any fix belongs in the design (a thinner deck) or the citadel length.
    - Kongo 33.7k → 38.1k t (27.5k), already heavy before.
    - AoN ships got heavier bulkheads (battleship 287 mm, Nelson-like 305 mm): +0.7–1.1k t, +0.5–1 m.
  - Belt band (same day): `belt_depth_m` and `belt_height_m` replaced the hidden `TUNING belt_h` rule (kept only as the fallback). The designs got the rule's value for their draught, rounded to 0.1 m: ±0.1k t and up to 1 m of length. `belt_bottom_mm` (same day) tapers the main belt below the waterline to its lower edge. Mikasa, Connecticut, Dreadnought and the Nassaus have historical tapers (0.2–0.45k t lighter); the rest are uniform. The AoN battleships stay uniform: Iowa's real taper (307 → 41 mm) belongs to a much deeper lower belt than the 3 m band here.
  - Armour materials (same day): `armour.materials` maps each part to a string, with per-deck, per-strake and per-battery `material` overrides. Every armour piece in `hitboxes.json` carries the string unchanged, for the game's ballistic simulator. The user wants only a string reference here, with no yield strengths or other properties in this pipeline. The designer never reads it: mass is the same for every material. The designs use the names of their time (Krupp cemented, Harvey nickel steel, Vickers cemented, British cemented/non-cemented, US Class A/B and STS, mild steel). The flight deck component now also reports its `armour_mm`.
  - Not done: a separate armoured box over the steering gear (side armour aft that stops short of the stern). An `aft` deck plate and an aft end belt stand in for it.
- **Unifying the styles (started 2026-10-03).** The user wants complex systems shared by every style. Only placement (where guns, superstructure and funnels go, hull forms, deck plans) stays per style. Small length changes are fine. Each step is committed and pushed separately, so it can be rolled back.
  1. **Ordnance (done).**
     - `ordnance.py` turns every style's ammunition into magazines. Every mount is booked through `armament.add_mount`, the warship's included, so its four hand-written copies are gone.
     - Styles only name zones: warships keep their own magazines and grouped magazines; carriers put the aviation magazines with the gun magazines; merchants put a gun magazine aft; planing craft an ammunition locker.
     - Effects:
       - Warship secondaries now book barbette weights like other styles' mounts (+0.5–1.5% std displacement).
       - MTB +1 m and PT boat +1.5 m: the locker takes crew space, which binds on those boats.
  2. **Superstructure blocks (done).** The warship's two local `add_block` copies (one never called) were replaced by the shared `layout.add_block`. Outputs are identical.
  3. **Finishing the layout (done).** `layout.finish_layout` builds the renderer spec and sets the layout's parts for every style, replacing four copies, the carrier's `_finish` among them. Outputs are byte-identical.
  4. **AA (done).** The warship supplies its slots (`aa_slots`: deckhouse roof, deck edges, a stern centreline slot offered last) to the shared `armament.place_aa`. That function now also checks the guns' sweeps and can ignore ids depending on a slot's base. Outputs are identical.
  5. **Steering gear and citadel (done).** `layout.add_steering` is one rule for every displacement hull (`STEERING`: 0.03–0.08 L forward of the stern, 0.25 B each side; merchants used to be 0.02–0.06 L). It stands low (`ordnance.span`, 2 deck spaces); planing craft keep their tiller flat over the whole stern abaft the engines. `layout.set_citadel` sets `lay.geo["citadel"]`; the old `Citadel` compartments were dead data (nothing read them) and are gone. Destroyer 130 → 128.5 m (crew space freed); the rest unchanged.
  - Still per style, on purpose: where guns, superstructure, funnels and decks go. Small leftovers: the carrier's `_common` layout setup, and its "machinery over half the hull" check, which other styles don't make.

## Next steps (proposed 2026-10-02, in this order; the user hasn't confirmed the order yet)
1. **Hull cross-section shape.** Every height uses the deck outline now, so double-bottom and hold cells are as wide as the main deck. Give the hull sections that narrow toward the keel, from the block coefficient (full amidships, sharp at the ends).
   - That fixes cell bounds and volumes, torpedo protection depth, belt coverage, hit lookup near the bottom, and the 3D views.
2. **Propulsion train.** Add shafts from each engine room through shaft alleys to the propellers, and rudders over the steering gear, as components that run through cells. This completes damage step 2 and gives the game its weak spots aft: a jammed rudder, wrecked shaft glands, a flooded shaft alley.
3. **What sits in and passes through each cell:**
   - Each cell lists the barbettes, uptakes and casings that pass through it: the flash path from a turret to its magazine, and the leak path through the uptakes.
   - Double-bottom contents: oil or water, by tonnage.
   - Clean up the remaining shared cells.
4. **Armour (mostly done 2026-10-03; see "Secondary armour" above).** Done: several armour decks, upper and end belts, belt band and taper, explicit bulkheads, and materials. Left:
   - An armoured box over the steering gear: side armour aft that stops short of the stern, with its own bulkhead. I offered it; the user hasn't answered yet.
   - Turtleback or sloped decks: the user has shelved them; several flat decks stand in for now.
   - Cells carry one `belt_mm` (the thickest beside them). If the ballistics wants the exact strake hit, it should use `armour.belt` and `armour.strakes` geometry, not the cell summary.
5. **Links and flags (damage step 3), best done alongside the material inputs:**
   - engine room to shaft
   - generators to fore and aft power networks
   - grouped versus alternating machinery
   - fuel type
   - bottom layers
   - riveted or welded construction

   The long early-turbine ships are a plant question (`machinery.tech`, the planned cruise and fuel-range tuning), not a period factor.

Housekeeping, whenever convenient:
- Fold the turret-sweep checker into `verify.py`.
- Watch the destroyer's section count (19 against 12–16 in the research).
- The warship citadel covers the main turrets and the whole machinery block with its grouped magazines (fixed 2026-10-02). Before that, an all-forward ship's machinery lay outside the belt: all_forward went from 27.9k to 34.8k t std. Now its Engine room 2 shares a cell, because the citadel-end bulkhead outranks the room's own end when stations merge.

## How to work here
- **Git:** the repo is on GitHub (`git@github.com:sharpneli/shipgen.git`, branch `main`). Pushing over SSH works with the user's key. Commit or push only when the user asks.
- Dependencies are `pip install cairosvg pillow numpy`. The system Python lacks them; use the venv at `~/.venv` (`~/.venv/bin/python design.py ...`).
- **Checking the boundary:** `python3 -c "import shipdesign, json; shipdesign.build(json.load(open('designs/battleship.json')))"` must work with the system Python (no PIL, cairosvg or numpy), and importing `render` must not load `shipdesign`, `navarch`, `layout`, `styles`, `hitbox` or `armament` (check `sys.modules`).
- **Speed:** `shipdesign.build` takes about 5–350 ms per ship (coal-era warships are the slowest), and a silly design up to 0.5 s. The size search runs the layout around 10–25 times, and each run takes 0.2–9 ms. A `hint` (the previous length) halves that. `Layout.free` and `geometry.polygons_intersect` reject by bounding box first, and AA spacing checks only the AA footprints. `render_ship(previews=False)` takes about 0.5 s; the previews (numpy shadow march), the sheet and the debug overlay are most of the ~3 s full render.
- **Checking a look change:** render a design in every navy and era and confirm `hitboxes.json`, `sprite.json` and `report.json` (except its `inputs` echo) are identical across looks. `standard` must stay byte-identical to the old sprites.
- **Always regenerate `out_designs/` after a change** (`~/.venv/bin/python design.py designs/*.json --no-limits`), not just a scratch folder for comparison. The user reads the outputs there, and they're committed with the code.
- **Regression method used throughout:** copy `out_designs/` aside, regenerate, and `diff -r`. Unrelated designs should stay byte-identical; expected changes should be limited to the designs you meant to change. The hand-authored fleet (`python shipgen.py --out <dir>`) has stayed byte-identical through all the changes, so keep it that way.
- Run `python verify.py out_designs/*` after every change. It does pixel checks of sprites against hitboxes.
- **Look at the 3D hitbox views** (`hitbox_*.png`, `hitview.py`) after hitbox changes. They caught compartments sticking out of the hull and barbettes hanging under sponsons.
  - Cells reach the hull's widest point over their section; the views clip them to the hull outline.
  - The 3D views draw every cell. The space-filling rooms (quarters, stores, double bottom, torpedo protection; `hitview.FILLER`) are faint, so the user can see the whole state at a glance: coal wing bunkers outside the machinery, and the citadel's length from the belt and its armoured end bulkheads (dark slabs).
  - `hitbox_cells.png` shows every tier of the subdivision in plan. `verify.py` checks the subdivision: one owning room per cell, points in the hull in exactly one cell, mutual neighbours, and magazine links.
  - Barbettes reach the armour deck only for mounts inside the hull and below any flight deck.
- A turret-sweep checker existed only in the previous session's scratch folder. It rebuilds each main turret's sweep and tests it against taller blocks and funnels. Folding it into `verify.py` would be a good addition.
- The user edits files in `designs/` themselves. Never overwrite their designs. As of the end of this session:
  - `destroyer.json` has `calibre_mm: 1270`, probably a deliberate silly test. Sized, it comes out at 418 m and 163k t.
  - `murica.json` has block coefficient 0.34 (needs `--no-limits`).
  - The user asked for `length` and `beam` to be removed from every design. That was done on 2026-10-02, and nothing else in the designs was touched.
- **Adding a key to every design:** the designs are hand-formatted JSON. Edit only the substring of the object you change (find `"armour": {`, match the braces, `json.loads` it, check `json.dumps` reproduces it exactly, then splice the new dump back in). `gangut.json` is multi-line, so insert lines there instead. Never re-dump whole files: it would reformat the user's designs.
- Output folders are named after the design's `id`, not its file name. Duplicate ids overwrite each other; this already happened once.

## Known gaps and ideas
- **Physics calibration:** carriers' full loads run light; the PT boat runs heavy; the T2 tanker needs about 30% more power than real.
- **No sweep reservation outside warships.** That's deliberate for carriers and merchants (see above).
- **Height map:** columns only, so mast yards, derricks and barrels are left out. It's 8-bit with a 0.25 m step, so anything above 63.75 m clips.
- **Baked lighting:** the light rim on the upper-left edges of blocks and funnels is still baked in.
- **No aircraft are drawn** on carriers; the game is assumed to spawn them.
- **Wing turrets on narrow ships** (beam under 15 m) stand on the main deck, and the small deckhouse under the bridge may overlap them. No real design does this, so it hasn't been handled.
- **Missing turrets:** a mount that doesn't fit (beam too narrow, deck taken) is left off the drawing and listed as an error, even with `--no-limits`.
