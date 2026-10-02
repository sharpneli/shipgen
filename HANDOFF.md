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
- **Looks are visual only** (`"look"` in the design, `looks.py`). The user wants ships of different powers to look different with no gameplay effect: a look may change only the sprite images, never the layout, physics, report results, hitboxes or `sprite.json`. Turret drawings and silhouettes (bow, stern, funnels, superstructure corners, masts) differ by look, but hitboxes always use the layout's shapes. A look's hull may only be fuller than the layout's, never finer, so deck-edge fittings stay on deck. National looks are named after dockyards: `brooklyn` (US), `kure` (Japan), `portsmouth` (UK), `kiel` (Germany). Period looks are named after the period: `victorian`. The default is `standard`. More are planned.
- **Design and drawing are separate, with a plain-data contract** (`shipdesign.build(design) -> ship` dict; `render.render_ship(ship, ...)`). The user's game calls the design side on every knob change in its designer UI and needs it fast; the preview may lag. Keep the rules: the design side (shipdesign, navarch, layout, armament, hitbox, styles) uses the standard library only and never imports the renderer; the renderer (render, shipgen, shadow, looks) imports no design-side module and reads only the `ship` dict; `geometry.py` is the shared layer. Colours live only in `looks.py`. A physics refactor should change only the design side, and a drawing change only the render side.
- Shadows come from the height map, not baked in. Mips are packed per layer (`<layer>_mips.png`, rects in `sprite.json`).
- **Mip atlases are an interchange format only.** The game uploads each level to the GPU separately (Vulkan mip layout is hardware dependent) and never samples the packed image, so the missing gutters don't matter. Large sprites are fine too: the game may drop the biggest mip levels.

## Planned by the user
- **The game spans about 1890 to 1970:** pre-dreadnoughts, through the dreadnought era, to early modern ships. Defaults and new features should cover that whole range.
- **More looks** (`looks.py`). Four nations and the period look `victorian` are done; more will follow.
- **Casemates (done):** warship `secondary` may be a list of batteries, each `"mount": "deck"` or `"casemate"`. Casemates fire ±60° about the beam and come in two tiers: `"lower"` in the hull side, and `"upper"` in housings on the main deck, staggered between the lower guns. The user is happy with 2 tiers for now and explicitly wants silly builds, such as a WWII-tech ship of the line, to work. Examples: `mikasa`, `connecticut`, `nassau_casemates`, `kongo`, `victory_1944`. Open items:
  - The pre-dreadnoughts come out light (Mikasa 11.3k std against 15.1k t real). The weight model is calibrated on WWII ships; the physics refactor by period should fix this.
  - Lower and upper guns never stack at the same x (from above, stacked guns would look like one). Stacked British two-storey casemates therefore come out staggered.
  - Connecticut's 203 mm wing turrets need a second main battery, which ties into the French "floating hotels" below.
  - verify.py flags the 88 mm casemates at the ends of `nassau_casemates` at 0.846 at one 37° angle. It's rasterisation of a 2 px barrel; the other angles score 0.89–0.96.
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
- Remaining physics refactor: the rest of the weight model by period (hull, armour quality and so on) and the parameters the user plans for sizing (hull form, beam preference).
- Research to replace the planing power placeholder (`navarch.planing_power`). It's one function by design.
- **Size from contents (done; README "Design input"):** designs give no length or beam (`hull.length` and `hull.beam` are now validation errors). The designer works out the hull from what it carries, and hitting a tonnage or length target is the player's job.
  - The rules and their default values (`Style.SIZE`, `shipdesign.min_length`, merchant `STOWAGE`) are internal for now. The user will add parameters to control them later (engine efficiency etc.), probably alongside the period physics refactor.
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
      - **Secondary and abreast wing-turret magazines are grouped** at the ends of the machinery block (option b, as on real ships with ammunition passages). They're sized by ammunition weight at 0.35 t/m³ (`layout.MAGAZINE_T_PER_M3`).
        - A first try at 2r × 2r per mount made Mikasa 27 m longer.
        - Now lengths move a few metres: Mikasa 129 m (was 133), Kongo 263.5 m (was 257.5), Invincible 194.5 m (was 192), victory_1944 107 m (was 114).
      - **The extra tier (done): a flat at the waterline.** Tiers are bottom, hold, platform and between, or bottom, hold and between when unarmoured. The user expects more tiers later for armour schemes: turtleback decks, and several armour decks such as thin armour over the quarters and thicker over magazines below them. `subdivision.decks` takes a list of decks, each with optional `armour_mm` and x extent, so more armour decks slot in. Cells already carry `armour_above_mm`. A sloped deck would need cells with sloped bounds, which they don't have yet.
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
      - carrier and merchant gun magazines
  - Step 3: links and flags, best done with the period refactor: engine room to shaft (uptakes to boiler rooms are done), generators to fore and aft power networks, grouped or alternating machinery, fuel type, centreline bulkhead, torpedo protection depth along the length. Carrier extras: flight-deck segments, lifts, hangar bays, avgas fore and aft.
  - **Buoyancy:** the user hasn't decided how realistic it should be. It will likely be a grid, but it must not drive a full simulation of the ship's motion. Flooding only makes the ship settle: a deeper draught costs speed and puts more of the belt under water.
  - Known simplifications: carrier and merchant guns have no magazines yet. The barbette weight (`navarch.mount_weights`, 0.45 × depth) doesn't match the barbette hitbox, which reaches down to the armour deck.

## Next steps (proposed 2026-10-02, in this order; the user hasn't confirmed the order yet)
1. **Hull cross-section shape.** Every height uses the deck outline now, so double-bottom and hold cells are as wide as the main deck. Give the hull sections that narrow toward the keel, from the block coefficient (full amidships, sharp at the ends).
   - That fixes cell bounds and volumes, torpedo protection depth, belt coverage, hit lookup near the bottom, and the 3D views.
   - Sloped (turtleback) decks need it, so do it before the armour-scheme work.
2. **Propulsion train.** Add shafts from each engine room through shaft alleys to the propellers, and rudders over the steering gear, as components that run through cells. This completes damage step 2 and gives the game its weak spots aft: a jammed rudder, wrecked shaft glands, a flooded shaft alley.
3. **What sits in and passes through each cell:**
   - Each cell lists the barbettes, uptakes and casings that pass through it: the flash path from a turret to its magazine, and the leak path through the uptakes.
   - Double-bottom contents: oil or water, by tonnage.
   - Magazines for carrier and merchant guns.
   - Clean up the remaining shared cells.
4. **Armour schemes on the deck list.** These are design inputs, so agree the knobs with the user first.
   - Several armour decks with their own thickness and extent, such as a thin deck over the quarters and a thick one over the magazines.
   - Turtleback or sloped decks, after step 1.
   - All-or-nothing versus incremental schemes.
   - Belt height and taper.
5. **Links and flags (damage step 3), best done with the period physics refactor:**
   - engine room to shaft
   - generators to fore and aft power networks
   - grouped versus alternating machinery
   - fuel type
   - bottom layers
   - riveted or welded construction

   The refactor also fixes the light pre-dreadnoughts and the long early-turbine ships.

Housekeeping, whenever convenient:
- Fold the turret-sweep checker into `verify.py`.
- Draw the armour deck in the 3D views from the new `decks` list, not from `armour.deck`.
- Watch the destroyer's section count (19 against 12–16 in the research).

## How to work here
- **Git:** the repo is on GitHub (`git@github.com:sharpneli/shipgen.git`, branch `main`). Pushing over SSH works with the user's key. Commit or push only when the user asks.
- Dependencies are `pip install cairosvg pillow numpy`. The system Python lacks them; use the venv at `~/.venv` (`~/.venv/bin/python design.py ...`).
- **Checking the boundary:** `python3 -c "import shipdesign, json; shipdesign.build(json.load(open('designs/battleship.json')))"` must work with the system Python (no PIL, cairosvg or numpy), and importing `render` must not load `shipdesign`, `navarch`, `layout`, `styles`, `hitbox` or `armament` (check `sys.modules`).
- **Speed:** `shipdesign.build` takes about 5–350 ms per ship (coal-era warships are the slowest), and a silly design up to 0.5 s. The size search runs the layout around 10–25 times, and each run takes 0.2–9 ms. A `hint` (the previous length) halves that. `Layout.free` and `geometry.polygons_intersect` reject by bounding box first, and AA spacing checks only the AA footprints. `render_ship(previews=False)` takes about 0.5 s; the previews (numpy shadow march), the sheet and the debug overlay are most of the ~3 s full render.
- **Checking a look change:** render a design in every look and confirm `hitboxes.json`, `sprite.json` and `report.json` (except its `inputs` echo) are identical across looks. `standard` must stay byte-identical to the old sprites.
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
- Output folders are named after the design's `id`, not its file name. Duplicate ids overwrite each other; this already happened once.

## Known gaps and ideas
- **Physics calibration:** carriers' full loads run light; the PT boat runs heavy; the T2 tanker needs about 30% more power than real.
- **No sweep reservation outside warships.** That's deliberate for carriers and merchants (see above).
- **Height map:** columns only, so mast yards, derricks and barrels are left out. It's 8-bit with a 0.25 m step, so anything above 63.75 m clips.
- **Baked lighting:** the light rim on the upper-left edges of blocks and funnels is still baked in.
- **No aircraft are drawn** on carriers; the game is assumed to spawn them.
- **Wing turrets on narrow ships** (beam under 15 m) stand on the main deck, and the small deckhouse under the bridge may overlap them. No real design does this, so it hasn't been handled.
- **Missing turrets:** a mount that doesn't fit (beam too narrow, deck taken) is left off the drawing and listed as an error, even with `--no-limits`.
