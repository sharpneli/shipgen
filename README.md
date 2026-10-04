# shipgen: parametric top-down ship designer and sprite generator

```
pip install cairosvg pillow numpy             # the renderer only; the design side needs the standard library alone
python design.py designs/*.json            # player designs -> out_designs/<id>/ (10 px/m + 5 mip levels)
python design.py designs/x.json --no-limits # skip the input ranges; errors (capsizing etc.) never block output
python design.py designs/x.json --no-previews # game assets only (sprites, mips, height map): ~0.5 s, not ~3 s
python verify.py out_designs/battleship     # pixel check: sprites vs hitboxes
python shipgen.py                           # the original hand-authored fleet (fleet.py)
```

## Pipeline
Two halves with one contract between them: the design side turns the player's design into plain data, and the
renderer draws only from that data.
```
design JSON (player input: counts, calibres, armour, speed, look)
   │
   ▼  DESIGN SIDE: standard library only, no drawing          (about 1-30 ms per ship)
   shipdesign.py  validate(design) -> errors;  build(design) -> ship (plain, JSON-serialisable dict)
   ├─ styles/      the design style: warship, carrier, merchant, planing (limits, tuning, layout, extra weights)
   ├─ navarch.py   weights → displacement, draught, power, fuel, GM, trim   (iterates to a fixed point)
   ├─ hullweight.py  hull structure from plate area × thickness, construction tech and the hull girder
   ├─ layout.py    warship layout + shared layout primitives; balances CG over CB by shifting the arrangement
   ├─ armament.py  style-neutral gun, torpedo and AA placement; every style books its mounts with add_mount
   ├─ ordnance.py  magazines for every style: ammunition (and a carrier's bombs and avgas) stowed low
   ├─ hitbox.py    fixed firing arcs by mount kind; hitbox export
   └─ subdivision.py  the hull below the main deck as watertight cells, and the rooms that own them
   │
   │  ship = {design, report, hitboxes, render: {spec, deck_m, mounts, columns, summary}}
   ▼  RENDER SIDE: reads only `ship`                           (~0.5 s game assets, ~3 s with previews)
   render.py      render_ship(ship, out_dir, scale, mips, look=None, previews=True)
   ├─ looks.py     every colour, turret drawing and silhouette (by the design's "look")
   ├─ hitview.py   debug views of the hitbox model in 3D, and the subdivision in plan (hitbox_*.png)
   ├─ shipgen.py   SVG/PNG drawing (hull_base, turrets, hull_upper)
   └─ shadow.py    rasterises the height-map columns; the reference shadow renderer

   geometry.py   shared by both: hull form, turret polygons (sprite AND hitbox), AA sizes, arc helpers
design.py      the command line: validate, shipdesign.build, write report.json and hitboxes.json, render
```
- Use the design side alone (a game's designer UI): `ship = shipdesign.build(design)` gives the report and hitboxes
  in about 5–170 ms (sizing the hull is most of it). After a small change, pass the previous result's length,
  `shipdesign.build(design, hint=ship["report"]["results"]["length_m"])`, to make it about twice as fast with the
  same result. `render.render_ship(ship, ...)` can run later, elsewhere, or from the same dict loaded
  from JSON.
- The rules that keep the halves apart: nothing on the design side imports the renderer, PIL, cairosvg or numpy;
  the renderer imports no design-side module (only `geometry` and `looks`); and the renderer reads nothing but
  the `ship` dict. `shipdesign.py`'s docstring documents that dict.

## Design input
```json
{
  "id": "battleship", "name": "Fast Battleship", "type": "BB", "look": {"navy": "generic", "era": "wwii"},
  "hull": {"block_coefficient": 0.59},
  "speed_kn": 33, "range_nm": 15000,
  "armour": {"belt_mm": 307, "belt_depth_m": 3.0, "belt_height_m": 3.0, "belt_bottom_mm": 307, "bulkhead_mm": 287, "upper_belt": {"mm": 0, "to_deck": 0, "extent": "citadel"},
             "end_belts": {"fore": {"mm": 0, "tip_mm": 0}, "aft": {"mm": 0, "tip_mm": 0}},
             "turret_mm": 432, "decks": [{"deck": 1, "mm": 152, "extent": "citadel"}]},
  "main": {"calibre_mm": 406, "calibre_length": 50, "barrels": 3, "fore": 2, "aft": 1},
  "secondary": {"calibre_mm": 127, "calibre_length": 38, "barrels": 2, "per_side": 5},
  "torpedoes": {"mounts": 0, "tubes": 5},
  "aa": {"heavy": 20, "light": 30},
  "machinery": {"stress": 0.4, "shafts": 4, "tech": {...}},
  "crew": {"standard": {...}, "endurance_days": 45, "distiller": true},
  "superstructure": {"t_per_m2": 0.32, "material": "steel", "tower_levels": 4},
  "fire_control": {"main": {"directors": 2, "rangefinder_m": 7.9, "armour_mm": 38, "radar_t": 2.0, "computer_t": 8.0},
                   "secondary": {...}, "aa": {...}, "search_radar_t": 4.0},
  "funnels": null
}
```
`armour` holds the belt, turret and torpedo protection (`tds_m`) values, and `decks`: the armour decks, top down. Every design lists them, even an empty list.
- **Torpedo protection** is weighed as longitudinal bulkheads totalling `TUNING tds_mm_per_m` (12 mm) per metre of `tds_m`, each side over the citadel, from the inner bottom to the roof deck (Bismarck: a 45 mm torpedo bulkhead and thinner ones, 5.5 m deep). An armoured ship's **conning tower** (the hitbox's cylinder, walls as thick as the belt, a roof half that) is weighed too.
- **The deck stack:** the hull's decks lie every `navarch.DECK_PITCH` (2.6 m) down from the main deck to the inner bottom. Deck 0 is the main deck (a carrier's hangar deck), deck 1 the second deck, and so on. A deck closer than 1 m to the inner bottom is left out, so the hold is 1–3.6 m tall.
- **An armour deck** is `{"deck": n, "mm": thickness, "extent": "citadel" | "full" | "fore" | "aft" | "ends"}`. `citadel` covers the citadel, `full` the whole length, and `fore`, `aft` and `ends` (both) the hull beyond the citadel's ends: the protective deck at a pre-dreadnought's ends, or the deck over an all-or-nothing ship's steering gear. List the decks top down. A deck may appear twice only over different stretches (the citadel and its ends, say 76 mm on the second deck amidships and 51 mm on it at the ends). A deck the hull is too shallow for lies on its lowest deck, with a warning; overlapping decks pushed onto the same one add up.
- **What the decks decide:**
  - The thickest deck over the citadel is the main armour deck. The higher one wins a tie. The belt (its band from `belt_depth_m` below the waterline to `belt_height_m` above it) reaches up to it when it's higher, and the barbettes reach down to it.
  - The lowest deck over the citadel is the roof of the vital spaces: the machinery and the magazines stand under it. A low roof squeezes the machinery, which makes it longer.
  - Each deck weighs its area × thickness. A `full` deck covers the hull's waterplane.
- `battleship_layered.json` is the battleship with Iowa-style layers: a 38 mm bomb deck on the main deck over the whole length, the 152 mm main armour deck on the second deck, and a 16 mm splinter deck on the third.
- `armour.deck_mm` is gone, and a design that still has it is rejected.

The side armour is the main belt and up to three secondary pieces. Every design lists them all, with 0 mm for what it lacks:
- `belt_mm`: the main belt over the citadel.
- `belt_bottom_mm`: the main belt keeps `belt_mm` down to the waterline, then tapers linearly to this at its lower edge, as most real belts did (Mikasa 229 → 127 mm, Dreadnought 279 → 229 mm). Equal to `belt_mm` for a uniform belt. A tapered belt is lighter, so a deep belt costs less.
- `belt_depth_m` and `belt_height_m`: the belt's band, in metres below and above the full-load waterline. The main belt reaches up to the main armour deck when that's higher, so belt and deck close the box. The end belts share the band. The designs carry 0.15 × draught + 1.2 m each way, the old built-in rule. A belt under 1 m deep warns, because rolling or flooding uncovers the side under it, and the game settles a flooded ship deeper.
- `bulkhead_mm`: the citadel's transverse ends, closing the belts from 0.4 belt heights under the belt up to the top of the main or upper belt.
- `upper_belt`: `{"mm", "to_deck", "extent"}`, a strake from the top of the belt below it up to deck `to_deck` (0 the main deck). Over the citadel it starts at the main belt's top; beyond it, at the end belt's top (or the main belt's waterline band if there's none). It has no height, and warns, when the belt already reaches that deck. `extent` takes the deck extents, and `full` is one strake over the citadel and one beyond each end.
- `end_belts`: `{"fore": {"mm", "tip_mm"}, "aft": {...}}`, the waterline belt carried on from the citadel to the stem and the stern. It's as deep as the main belt and reaches up to the thickest armour deck over that end when that's higher. It is `mm` thick at the citadel and tapers linearly to `tip_mm` at the hull's end.
- How the schemes come out:
  - **All or nothing** (Nevada onward): a thick belt and deck over the citadel, heavy bulkheads, and nothing else (`battleship.json`, `all_forward.json`).
  - **Incremental, dreadnought era**: a main belt, an upper belt to the main deck, and end belts, often thicker forward than aft, with deck plates over the ends (`dreadnought.json`, `nassau.json`, `kongo.json`). `invincible.json` has a fore end belt only, and a deck over the steering gear aft.
  - **Pre-dreadnought** (`mikasa.json`, `connecticut.json`): a waterline belt from stem to stern, tapering toward the ends, an upper belt between the barbettes, and the protective deck at the ends (`ends` deck plates).
  - **Full-length upper belt** (Gangut, the early French): `upper_belt.extent` `full`.

`armour.materials` names the armour material per part: `belt`, `upper_belt`, `end_belts`, `bulkheads`, `decks`, `turrets`, `barbettes`, `conning_tower`, `secondary` and, on carriers, `flight_deck`. A deck entry, `upper_belt`, an end belt or a secondary battery may give its own `material`, which wins over the map.
- **They're plain strings,** passed unchanged to every armour piece in `hitboxes.json` for the game's ballistics, which looks them up. The designer doesn't read them: armour weighs thickness × area × 7.85 t/m³ whatever it's made of, and no material is tied to a period.
- **The designs use names of the time** (`wrought iron` and `compound` suit anything older):
  - `Harvey nickel steel`, `nickel steel`
  - `Krupp cemented`, `Krupp non-cemented`, `Vickers cemented`
  - British `cemented armour` / `non-cemented armour`, and `high-tensile steel`
  - US `Class A` (face-hardened), `Class B` (homogeneous) and `STS`
  - `mild steel` on unarmoured ships

  Any other string works too.

`crew` sets how the crew lives (`crew.py`, from `research/crew-space-model.md`).
- `standard` is the habitability standard as numbers: net areas per head, shared spaces, headroom, water and provisions rates, and the hotel fraction.
  - `crew-templates.md` has six reference blocks, H0 (sleep at station) to H5 (single cabins). `python crew_templates.py` regenerates it.
  - The game rates comfort from the numbers smoothly, with no tiers.
  - The default standard is H2 for warships and carriers, H3 for merchants and H0 for planing craft.
- `endurance_days` is the provisions carried. It defaults to the fuel's range at cruise speed. A ship may carry more, like a tender that loiters; a shorter value only warns.
- `distiller`, `water_l_per_day`, `berth_ratio` and `officer_fraction` are optional.

The complement is built from what the ship carries:
- **Engineering:** the plant's crew.
- **Weapons:** each gun mount gets barrels × (0.5 + 0.09 per mm of calibre) + 0.02 per mm, which counts its handling rooms. That's about 120 for a 16-inch triple and 26 for a 5-inch twin. Torpedo mounts and AA count too.
- **Deck and command:** 0.8 × √(standard displacement), tapering below 1,000 t. Merchants use 0.3.
- **Air group:** carriers only.
- **Hotel crew:** the standard's fraction of the total.

The crew lives wherever the ship has empty volume (`crew.crew_space`):
- **The volume:** the hull from the inner bottom to the main deck, plus the superstructure, less the machinery, magazines, bunkers, holds, tanks and torpedo protection.
- **The crew's share:** `crew.USABLE` (0.65) of what's left. That share has to hold the quarters, the provisions and any water the double bottom can't take after the fuel. Too little room makes the hull grow.
- **Weights:** crew, provisions and water are real weights. `misc_frac` no longer includes them.
- **Hull first, then up:** the crew lives in the hull first. The share of the needed volume the hull can't hold is quartered in the superstructure, spread over its blocks by volume (not directors, casemate housings, AA platforms or hangars), and weighed there. The report's `crew` gives `quartered_in_superstructure` and `superstructure_quarters` ({block: men}). Those blocks' hitboxes carry `crew`: a superstructure hit can kill off-watch men only where they actually sleep. The subdivision quarters the rest in the hull.
- **Where they sleep:** the subdivision spreads the complement by volume over the cells no room claims above the waterline (`Quarters <section>`), and over a planing craft's crew space. A merchant whose holds fill the hull has no quarters below the main deck; its crew lives in the superstructure, which the subdivision doesn't cover.

`superstructure` is how the upperworks are built. Every design writes it out.
- `t_per_m2`: structure weight per m² of each level's footprint. Steel is about 0.32; aluminium (Forrest Sherman, Spruance) about 0.2. Planing craft use 0.10 (a wooden charthouse).
- `material`: a plain string passed to the superstructure's hitboxes for the game (an aluminium house burns and dents in a seaway). The designer doesn't read it.
- `deckhouse_levels` (warships): how many levels the deckhouse amidships has; 1 is the old single level. Each level above stands on the one below, wraps around the funnels, and keeps clear of what stands on the roof below (secondaries, wing and midships turrets, bridge, aft control) and of the guns' sweeps. It is as wide as it can be while keeping 70% of the length it would have at 3 m wide (`layout.add_deckhouse_levels`). On a narrow ship whose deckhouse is only under the bridge, the first extra level carries the deckhouse along the middle first, Fletcher-style. The blocks are `Deckhouse k[-i]`. Extra levels are room for the crew, so a crowded ship gets shorter instead of longer, but they cost topweight (the sizing then needs more beam for GM) and windage. Example: the destroyer at 2 levels comes out 114 m long instead of 130 m (Fletcher: 114 m), with GM 0.76 m instead of 1.28 m. A ship with room in its hull only gets heavier.
- `tower_levels` (warships and carriers): the bridge tower's (or the island's) top level. The bridge is level 2 (a carrier's island bridge level 3). Each level above 3 is a `Tower n` block (`Island tower n`) that narrows as it rises, and the main director stands on top. Funnels stand as tall as a tower of up to 4 levels, whatever the tower. A tall tower lets the directors see farther, but it costs topweight. The designs carry the old built-in rule: 4 on warships from 180 m (carriers 200 m), else 3.

`fire_control` is the directors and the plotting rooms behind them (`firecontrol.py`). Every design writes out all three batteries, with zeros for what it lacks. Each battery takes `{"directors", "rangefinder_m", "armour_mm", "radar_t", "computer_t"}`, plus `search_radar_t` for the search radar.
- **Directors** stand on the superstructure's roofs as blocks of their own (role `director` in the hitboxes, with `battery`, `rangefinder_m`, `armour_mm` and `radar`). Main directors take the highest roofs, the first two at least a quarter of the length apart (fore and aft) when they can. Secondary directors go in pairs on the highest roofs that take a pair, and AA directors on the lowest roofs, beside their guns. Where no pair fits (a narrow tower, a carrier's island) they stand singly. A director with no roof to stand on is an error.
- **Weights** (estimates, `firecontrol.py`): a 2.2 m hood of 6 mm plate around a rangefinder whose arms stick out athwartships (`rangefinder_m` + 1 m wide), training gear and sights (1 + 1.2 × base t), the rangefinder (0.03 × base² t), the hood's armour and the radar, all at the director's height. `computer_t` is the director's share of the plotting room (range clock, Dreyer table, rangekeeper), low in the hull. A Mk 37 comes out at about 20 t, a Mk 51 (no rangefinder) at 1.7 t, and Bismarck's 10.5 m main directors at about 45 t each.
- The search radar sits on the foremast top. Masts now weigh 0.012 × height² t per leg (a tripod has three legs) at half their height.
- **The report's `fire_control`** lists every director with its eye height above the waterline and its visual horizon (3.57 √(1.17 h) km). The game decides what that means for spotting. A main battery with no director warns that its turrets fire under local control.
- The values are raw numbers. Templates (a bureau's director that many ships share) belong to the game's designer UI.

`aa` (`heavy` 40 mm quads, `light` 20 mm singles) stands high, as on real ships (`armament.place_aa`, the warship's `aa_slots`):
- **Order of preference:** tubs on the superstructure's roofs, the bridge and aft control levels first, then the tower's top and the deckhouse (01 level). Next come raised platforms at the deck edges: a pedestal block one level tall (`AA platform n`, role `aa_platform` in the hitboxes) under the tub. The bare deck edge is the last resort, used only where a raised tub would stand in a turret's sweep. Within each, nearest amidships first, and pairs before single mounts on a roof's centreline (`layout.AA_ROOF_PEN`, `AA_PLATFORM_PEN`, `AA_DECK_PEN`).
- Carriers put tubs on the island's roofs first, then on sponsons; merchants on the houses and ends.
- **Weight:** a mount above the main deck also weighs its tub, platform and splinter shield (`armament.AA_TUB_T`: quad 3 t, single 0.3 t), and a platform's pedestal weighs as superstructure. All of it counts at its height, so a ship crowded with AA pays in topweight.
- Collision tests are height-aware (`Layout.free_at`): a tub may stand on a roof but not inside a taller block.

`machinery` is the propulsion plant (`powerplant.py`, from `research/powerplant-model.md`). There is no year input: `tech` holds the researched technology as numbers, so a navy can have a tech earlier or later than history did. `plant-templates.md` has blocks to copy for every period from 1880 to 1970, and `python plant_templates.py` regenerates them. A design without `tech` gets a 1940 high-pressure turbine plant (merchants: a 1940 oil-fired triple expansion; planing craft: 1940 petrol engines). The other keys are design choices: `stress`, `shafts`, `units_per_shaft`, `transmission`, `arrangement` (`grouped` or alternating `unit`), `centreline_bulkhead`, `bunkers` (`wing` or `ends`) and `wing_bunker_m`. The template's table explains each one. What the plant decides:
- **Weight, fuel and engineering crew:** from the tech and the stress. Range is computed at cruise speed through the tech's part-load curve.
- **Machinery length:** the plant's volume, fitted into the room the hull gives it. Across, that's the beam inside the frames, less torpedo protection (`armour.tds_m` per side) and wing bunkers, with units standing in rows. Up, it's the inner bottom to the lowest armour deck over the citadel (the main deck without deck armour).
  - The volume splits between boiler and engine rooms by `boiler_fraction`.
  - Boiler rooms use the whole height: boilers, drums, fans and uptake trunks reach the deck.
  - Engine rooms use only the units' height plus 2.5 m of auxiliaries, so low turbines leave height unused.
  - A unit taller than that pokes through the deck under a casing, which is armoured if the deck is.
  - Coal fills wing bunkers, which run up to the main deck, then end bunkers. Oil fills the double bottom and the torpedo protection's liquid layers, then end tanks. End bunkers and tanks lengthen the machinery block.
- **Machinery block:** bunkers, boiler rooms and engine rooms in line (`powerplant.segments`). Unit arrangement alternates boiler and engine rooms.
- **Funnels** (`powerplant.funnel_plan`):
  - Count: enough of them to pass the gas, each within its uptakes' `reach_m` of the boilers it serves. `"funnels"` can add more, never fewer.
  - Natural and boost draught plants get funnels at least 25 m above their grates.
  - Old coal plants need many big funnels spread over long boiler rooms.
- **Warship middle.** The deck plan and the machinery below it are laid out together. The deck plan is the bridge, the funnels over their boiler groups, the midships and wing turrets, and the aft control.
  - Midships turrets and echelon wing pairs stand only in gaps between machinery segments next to the boilers. There they stand over their magazines, like Lion's and Kongo's Q turret.
  - More turrets than gaps splits a boiler group, which then needs its own funnel.
  - Engine rooms and bunkers at the ends of the block run on under the bridge, the abreast wing turrets and the aft control.
  - The forward boiler group may also run on under them, up to 0.85 of the bridge's length (`layout.BRIDGE_OVER_BOILERS`). Its funnels stay on open deck aft of the bridge.
  - This is what makes many centreline turrets hard with early plants (a Gangut).
- **Smoke:** a bridge, director or aft control standing in a funnel's smoke (`powerplant.smoke_reach`, which is shortest for oil with air heaters) is flagged in its hitbox and warned about.
The design gives no size. The designer works out the hull from what it carries (`shipdesign.size`), and hitting a tonnage or length target is the player's job, by trading the inputs off. `hull.block_coefficient` (the hull form) is optional, with a default per style.

`hull.construction` is how the hull is built (`hullweight.py`, from `research/hull-weight-model.md`): `yield_mpa` (the hull-girder steel), `join_factor` (riveted above 1, all welded 1.0) and `standard` (minimum plate gauge: 0.85 light, 1.0 naval, 1.25 robust), with an optional `name`. Like the plant, it's numbers, not a year. `hull-templates.md` (`python hull_templates.py`) has a block for each period from wrought iron to HY-80; a design without one gets the all-welded 1945 block. What it decides:
- **The hull structure weight** is plate area × thickness, not a volume law. Small hulls are built to minimum gauge (4 + 0.03 L mm), whatever the steel. Long, heavy hulls also need strength plating to resist bending as a girder (moment Δ g L / 40), and that's where better steel and welding save weight: an Iowa-sized hull weighs about a third more in 1900 mild steel than in 1942 practice, a Fletcher-sized one about 15%.
- **Armour decks are part of the girder.** The `citadel` and `full` plates over amidships stand in for strength plating, the more the thicker they are and the farther from the neutral axis (0.45 D). A thick, high armour deck can carry the whole girder: the WWII battleships need no strength plating beyond minimum gauge.
- Internal decks come from the deck stack (`navarch.STACK_DECK`, 0.6 of a full deck per level, since many are platforms), and the inner bottom's weight comes in from 4,000 to 10,000 t full load (`navarch.INNER_BOTTOM_T`). Both are smooth so the size search doesn't jump.
- Beyond 350 m (`hullweight.LONG`, not in the research) a hull bends like 350 m of itself, since no ocean wave is longer, and minimum gauge stops growing. Only absurd designs get there.
- A hull that needs more strength plating than everything else together warns that it's very long for its depth.
- Planing craft ignore it and keep the volume law (`hull_k`) until light hulls are researched.

`hull.freeboard` scales the style's standard freeboard (1.0, an ocean-going ship; `navarch.design_freeboard`, which grows with length). A navy fighting in sheltered water can trade sea-keeping for a cheaper ship: a lower freeboard means less side shell, fewer decks and a shorter upper belt and bulkheads, so less hull and armour weight, and a lower centre of gravity. Against that, the shallower girder needs more strength plating, and there is less room inside. Machinery taller than the space stands in a casing above the deck rather than lengthening the rooms. Crew and cargo need volume, so a crowded ship (the destroyer) or a merchant gets longer instead. The designer allows any value; the game handles wetness and sea-keeping. Examples at 0.5: battleship 43.5k → 39.4k t std, heavy cruiser 14.0k → 12.9k t, Mikasa 11.6k → 10.6k t.
- **Length:** the shortest hull, on a half-metre grid, that meets two rules:
  - Everything fits, at the layout's comfortable clearances. Warship end groups keep their preferred bow and stern room, which leaves room to shift for trim. Each layout failure is tagged with whether more length or more beam fixes it (`Layout.fail`).
  - It is at least as slender as its speed asks (`shipdesign.min_length`). Slenderness, length over the cube root of the underwater volume, rises with the volumetric Froude number from 5.25 (Liberty, Mikasa) to 8.2 (Fletcher). The rule is fitted to 16 real ships and lands within about 5% for most. Planing craft skip it.
- **Beam:** the narrowest that meets all of these:
  - everything fits across the hull
  - GM is at least `gm_frac` × beam
  - draught is at most `tb` × beam
  - length is at most `lb_max` × beam
  
  The values are per style, in `Style.SIZE`. Warships use 0.06, 0.36 and 10.5; merchants 0.04, 0.46 and 8.
- Merchants also need hold volume for their cargo: 1.4 m³/t dry, 1.25 m³/t oil (`styles.merchant.STOWAGE`).
- Results: the report gives `length_m`, `beam_m` and `block_coefficient`. Most realistic designs land within 2–10% of the real ship's length.
- An error that says something doesn't fit means the largest hull (`Style.SIZE`: 1,000 × 100 m, planing craft 60 × 12 m) still can't carry it.

`main` options:
- `"mid": n` (warship style only) puts n centreline turrets amidships, between the funnels. Lion has a Q turret; Gangut has two amidships.
- `"superfire"` sets how many turrets of each end group step up: `true` (default, all), `false` (none, so each group has one end turret and flush turrets behind it), or `{"fore": 2}`. A flush turret behind a stepped one (Nelson's X) fires to the sides only.
- `"wing": n` (warship style only) adds n pairs of wing turrets, one each side, standing on the deckhouse amidships. They fire bow to stern on their own side and never across the deck, so the forward pairs can fire dead ahead together with the forward group.
  - By default each pair stands abreast. The first pair goes at the forward end of the middle, the second at the aft end, then they fill inward (Dreadnought: one pair; Nassau: two, hexagonal).
  - `"echelon": true` staggers each pair, port forward and starboard aft, and spreads the pairs among the funnels (Invincible, Neptune). An echelon pair fits a beam that's too narrow for an abreast pair, at the cost of length.
  - Wing turrets stow fore-and-aft toward the nearer end of the ship. Secondaries fill the spots the wing turrets leave free.
- Examples: `gangut.json` (1 + 2 amidships + 1, all flush), `dreadnought.json` (A, wing pair, X, Y), `nassau.json` (hexagonal), `invincible.json` (echelon), `battlecruiser.json` (Lion-style Q turret), `all_forward_flush.json` (all-forward with a flush third turret).

`secondary` (warship style) is one battery or a list of batteries, each with its own calibre, `per_side` and `armour_mm`, and `"mount"`:
- `"deck"` (the default): turrets or open mounts on the deckhouse amidships. The first deck battery spreads evenly along it; later ones take the free spots nearest amidships.
- `"casemate"`: single guns at the hull side. Only a round port shield and the barrels show, outboard: half the barrel length (`geometry.BARREL_SHOWN`; turrets show 0.8 of theirs). Casemates stay where the hull is at least 85% of its full beam (`layout.CASEMATE_BEAM`). Two tiers, set by `"tier"`:
  - `"lower"` (the default): in the hull side, one level below the main deck (base −2.6 m, top 0). They keep clear of the main barbettes and of each other.
  - `"upper"`: on the main deck (base 0, top 2.6 m), each in an armoured housing against the deck edge (a level-1 superstructure block). Housings close together join into one gallery. They keep clear of whatever stands on the main deck and of the main turrets' sweeps. The tiers stagger, so the upper guns stand between the lower ones and every gun shows.
  - Placement: the lower tier fills first, then the upper. Within a tier, each battery takes the free places nearest amidships in list order, so list the battery you want amidships first. The rows centre on the hull's full-width part and move with the balancing shift.
  - Spacing: a comfortable pitch if every gun fits that way. Failing that, the lower guns sit just far enough apart for one upper gun between each pair. Failing that too, closer still.
- Battery mount ids are `S1S`/`S1P`, ... for the first battery, then `SB...`, `SC...`. Casemate guns carry `"mount": "casemate"` in `hitboxes.json` and `sprite.json`.
- **Magazines** (`ordnance.py`, the same for every style). Every mount books its ammunition with `armament.add_mount`. Each style then names zones where magazines may go, and `ordnance.stow` makes the rooms, links each mount to its magazine and moves the ammunition weight there.
  - Warships: end, midships and echelon wing turrets each have a magazine under them. The secondaries (deck and casemate) and abreast wing turrets share grouped magazines at the two ends of the machinery block, as real ships fed them through ammunition passages (`layout.magazine_plan`).
  - Each battery sends the forward half of its pairs, rounded up, to the fore group. A wing pair's magazine goes to the end of the middle it stands at.
  - **Magazines sit low.** They stand on the inner bottom, with their tops on a deck of the stack and never above the lowest armour deck (`ordnance.span`). They stow ammunition at `ordnance.T_PER_M3` (0.6 t/m³: shell and powder rooms; the handling rooms and passages are in the deck space above). Each zone is as many decks tall as its contents need over its area, and its rooms share its length by volume.
    - A turret's own magazine is its diameter long and rises as many decks as its ammunition needs.
    - The groups are as wide as the machinery space, planned at `ordnance.TIERS` (2) deck spaces tall, and long enough for their ammunition, so they lengthen the middle a little.
    - The decks above a magazine are free for quarters and stores.
  - There's one magazine per battery and group (`Magazine SB fore`), with a `mounts` list.
  - Carriers: one zone forward of the machinery holds the `Aviation magazines` and the `Gun magazines` for all their guns. The avgas zone is abaft the machinery.
  - Merchants: a `Gun magazine` aft, just forward of the steering gear. Planing craft: an `Ammunition locker` at the forward end of the crew space.
- Examples: `mikasa.json` (152 + 76 mm casemates in both tiers), `victory_1944.json` (a ship of the line: 152 mm lower and 120 mm upper casemates, no main battery), `connecticut.json` (178 + 76 mm casemates; its 203 mm wing turrets need a second main battery, still to come), `nassau_casemates.json` (Nassau's 150 + 88 mm in casemates, so all of them fit), `kongo.json` (152 mm casemates and 76 mm on deck).

Limits are generous on purpose: the game's designer enforces the gameplay limits, and the generator only keeps its input sane (`styles.base.COMMON_LIMITS`). Guns can be 1–2000 mm with 1–20 barrels, armour up to 2 m, and torpedo, secondary and AA counts are in the hundreds. Hull form and speed stay within the range where the physics formulas mean something. Each turret group (`fore`, `aft`, `mid`) can hold up to 40 turrets, named A, B, C, A4, A5, ... (and Q, P, R, S, Q5, ... amidships). Silly designs are allowed; the physics decides whether they're valid, and the designer simply makes the hull as big as they need. For example, Gangut's twenty 305 mm Q turrets come out on a 986 m hull.

The player never enters tonnage or positions. The allowed ranges are `styles.base.COMMON_LIMITS` plus each style's `LIMITS`.

`type` is a free gameplay label (BB, BC, DD, CV, AK, Q, ...). How the ship is designed comes from `style`, which defaults to `warship`. A battlecruiser and a battleship are the same style, and so are a destroyer and a cruiser.

## Styles
| style | what | extra input |
|---|---|---|
| `warship` | displacement-hull armoured warships, destroyer to battleship | — |
| `carrier` | seaplane carriers to angled-deck fleet carriers | `aviation`, `armour.flight_deck_mm` |
| `merchant` | dry cargo ships and tankers | `cargo`, `machinery.position` |
| `planing` | planing-hull fast craft: MTBs, PT boats, motor gunboats | — |

- Warships (and planing craft) are built around their main battery. Carriers and merchants are built around something else, and their guns are fitted wherever they suit:
  - They have no `main` battery; their guns are all `secondary`.
  - `secondary` may be one battery or a list, each with `count` (total mounts) or `per_side`, and `where`:
    - `"sides"` (the default): pairs along the sides or on sponsons; an odd mount goes to an end.
    - `"ends"`: on the centreline at the ends, alternating aft and fore. On a merchant that's the poop and forecastle; on a carrier, the flight deck in line with the island; on a seaplane carrier, the forecastle and hangar roof.
  - These guns stand flat on deck (no superfiring) and reserve no sweep zone, so they may overlap superstructure.
  - `torpedoes` and `aa` work on every style. A merchant with guns is a Q-ship or a DEMS-armed freighter.
- `machinery` works on every style (see Design input above).
- Guns under 76 mm are drawn as open mounts.
- **carrier**: `"aviation": {"flight_deck": "axial" | "angled" | "none", "aircraft": 90, "aircraft_t": 6, "hangar_decks": 1, "elevators": 2, "deck_edge_elevators": 1, "catapults": 2, "cranes": 0, "number": "9", "hangar": "open" | "closed"}`.
  - `hangar` picks which deck carries the hull girder. `open` (Essex, Yorktown, escort carriers): the hangar deck is the strength deck, and the flight deck is superstructure over an open-sided hangar. `closed` (Forrestal, Midway, Illustrious): the flight deck is the strength deck (`Style.strength_deck`), so the girder is the hangar's height deeper and an armoured flight deck counts in it. The hangar sides then become hull shell, and the hangar deck an ordinary internal deck. A closed hangar saves a long carrier its strength plating (Forrestal-size about 10% lighter) but costs a short one shell plating high up (an Essex is about as heavy, with GM 1.6 → 1.1 m; an escort carrier is heavier). The game handles the rest: no engine warm-up in the hangar, and flight-deck hits weaken the girder.
  - `none` is a seaplane carrier: a hangar aft, an aircraft deck over the stern, cranes and catapults.
  - Aircraft capacity comes from hangar and flight deck area, at about 20 × aircraft_t^(2/3) m² per aircraft. Too many aircraft is an error.
  - The main deck is the hangar deck. The flight deck sits 5.6 m × hangar decks + 2 m above it.
  - Guns go on the flight deck in line with the island (`"where": "ends"`), or on sponsons outboard of the deck edges (`"sides"`), as do torpedo mounts and AA. Example: `fleet_carrier.json` has four twin 5" at the island and four single 5" on sponsons.
- **merchant**: `"cargo": {"kind": "dry" | "tanker", "deadweight_t": 8500}`, `"machinery": {"position": "amidships" | "aft"}`.
  - The hull is a three-island ship: forecastle, bridge deck and poop, with holds (hatches, masts, derricks) or tanks (tank hatches, catwalk) between them.
  - Standard displacement is the lightship. Full load adds fuel and cargo, and range is computed at the service speed.
  - The cargo is stowed across the holds so the loaded ship floats level, the way a real loading plan trims a ship.
- **planing**: light wooden hard-chine hulls with a fine bow and a broad transom, exhausts through the transom (no funnels), a charthouse with the open bridge, and engine-room hatches aft.
  - `"torpedoes": {"mounts": 2, "tubes": 1}` are fixed tubes in port/starboard pairs along the deck edges, toed out 5°. They're aimed by steering the boat: in the hitboxes they have `rotating: false` and a 2° arc around their bearing.
  - **The power model is a placeholder** (`navarch.planing_power`): a flat resistance-to-weight ratio once planing (`TUNING planing_rw`, 0.13), ramping up from the hump, divided by a propulsive efficiency of 0.5. It's the one function to replace with a researched model. The report gives the volumetric Froude number Fn∇ and hp/t, and warns below Fn∇ 2 (not fully planing).
- To add a style: subclass `styles.base.Style` in a new module, give it a `build_layout` (and whichever weight and report hooks it needs), and register it in `styles.STYLES`. The shared building blocks are `layout.add_block`, `Layout.decks` and `Layout.sponsons`, the `armament` helpers (book every mount with `armament.add_mount`), `ordnance.stow` for the magazines, and `layout.finish_layout` for the renderer spec.

## Looks
`"look"` sets how the ship is painted and drawn: `{"navy": "kure", "era": "wwii"}`, as that navy built its ships in that era. It's purely visual: the layout, physics, report results, hitboxes and sprite sizes are identical in every look, so two ships that differ only in look play the same. A look applies to every style (warship, carrier, merchant, planing).

- **Two indices.** Looks live in `looks.NAVIES[navy]["eras"][era]`, and `looks.ERAS` lists the eras oldest first. The eras are `victorian` (1885–1903), `great_war` (1904–1920), `treaty` (1920–1936), `wwii` (1937–1946) and `cold_war` (1950–1970). Every navy has all five. A navy may change anything between eras (paint, turret drawings, bows, funnels), and navies differ freely from each other.
- **Every pair renders.** A navy with no entry for an era is drawn as `generic` in that era, and the sheet says so ("drawn as generic"). Unknown navy or era names are validation errors. The default is `generic` / `wwii`.
- **Repainting:** `render_ship(..., look={"era": "victorian"})` overrides the design's look key by key, so the game can redraw a design in a later era (a refit) without changing it.
- National navies are named after dockyards. Navies: `generic`, `brooklyn` (US), `kure` (Japan), `portsmouth` (UK), `kiel` (Germany), `la_spezia` (Italy), `toulon` (France). The table shows a sample; each navy's five eras are described in `looks.py`.
- **Pennant numbers:** `"look": {"navy": "toulon", "era": "cold_war", "number": "D 602"}`. Looks with `hull_number` paint it across the foredeck; without a number, one is made from the design's id.

| navy / era | inspired by | what changes |
|---|---|---|
| `generic` / `wwii` (default) | generic | WWII haze grey, teak decks |
| `brooklyn` / `wwii` | US | deck blue on every horizontal surface, slab-sided boxy turrets with rear rangefinder hoods, a wide square transom, boxy funnels and superstructure. Merchants: wartime grey |
| `kure` / `wwii` | Japan | dark Kure grey, pale hinoki wood, brown linoleum steel decks with brass strips, black-topped funnels, rounded turrets with a long rangefinder across the rear, a flared bow, oval funnels, soft rounded superstructure, wooden carrier decks with red stripes. Merchants: black hull, white house |
| `portsmouth` / `wwii` | UK | light Admiralty grey, pale holystoned teak, white boats, black funnel tops, straight-sided turrets with a round rear, a fuller bow, bridges with round fronts and square backs. Merchants: tramp colours, buff funnel with a black top |
| `kiel` / `wwii` | Germany | dark hull and steel decks under light grey upperworks, mid teak, grey funnel caps, faceted turrets with domed cupolas, a flared Atlantic bow, chamfered superstructure, capped funnels, pole masts. Merchants: dark hull, black funnel with a red band |
| `la_spezia` / `wwii` | Italy | light grey under dark grey and blue-grey dazzle panels, red and white recognition chevrons on the forecastle and quarterdeck, long wedge-faced "lancia" turrets, round-fronted tower bridges, raked funnels with "frying pan" caps. Merchants: black hull, white house, white funnel with a red band |
| `la_spezia` / other eras | Italy | `victorian`: black and white, the guns under white hoods on open barbettes, big single tops. `great_war`: light grey, white teak, pole masts. `treaty`: the palest grey afloat, awnings aft. `cold_war`: light haze grey, lattice masts, pennant numbers |
| `toulon` / `wwii` | France | dark blue-grey, wide split "quadruple" turrets with red and yellow roof bands (1940–42), funnels raked far aft like a mack, very round-fronted upperworks. Merchants: black hull, white house, red funnel with a black top |
| `toulon` / other eras | France | `victorian` "floating hotels": black hull in a broad tumblehome under ochre upperworks, mushroom-roofed "champignon" drum turrets, three-tier military tops, awnings aft. `great_war`: gris bleu, teak, a little tumblehome. `treaty`: light blue-grey, tripods, awnings. `cold_war`: deep blue-grey, broad black funnel "hats", lattice masts, pennant numbers |
| `generic` / `victorian` | the 1890s, any navy | black hull, white upperworks, buff funnels and masts with black tops, holystoned teak (dark corticene on steel decks), black drum turrets with sighting hoods, pole masts with round fighting tops, a full beamy bow. Merchants: black hull, varnished teak deckhouses, red funnel with a black top. Torpedo craft: all black |

- Each look is a palette for all styles, plus overrides per style, plus a turret drawing (`shipgen.look_turret_body`) and silhouette `shapes` (also overridable per style).
- Only armoured (`bb`) turrets change shape. The drawn outline stays close to the hitbox shape, and `verify.py` checks it like any other sprite.
- Silhouettes (`shapes` in a look) are drawn only: the bow and stern may be fuller than the layout's hull (never finer, so nothing at the deck edge overhangs), and funnels, superstructure corners and masts change style. Hitboxes keep the layout's shapes. The height map follows the drawn hull, so shadows match the sprite.
- **Painted features** (shapes keys, any navy may use them): `dazzle` (panels in the palette's `camo` colours over the hull band, superstructure and funnels, a repeatable pattern per design id), `deck_stripes` (recognition stripes on the open foredeck and optionally the quarterdeck, chevron or diagonal), `turret_bands` (bands across armoured turret roofs), `awnings` (canvas over the open quarterdeck) and `hull_number`. Silhouette extras: `tumblehome` (the hull drawn wider than the deck), `funnel_rake`, `funnel_cap` (`pan` or `hat`), `blocks: "tower"` and `mast: "lattice"`. The features that paint the deck keep clear of turrets, superstructure and funnels (`shipgen.open_ends`), and skip flight decks.
- A design's own `"palette"` still overrides everything.
- To add a look: add an era entry under a navy in `looks.NAVIES` (a new navy goes in `NAVIES`, a new era also in `ERAS`). A new turret drawing also needs a branch in `shipgen.look_turret_body`.
- **Nudges instead of new looks.** A look can start from another with `"from": "wwii"` (same navy) or `"from": "generic/great_war"` and list only what differs: palette, shapes and per-style keys merge key by key. `"adjust"` is a list of colour operations run in order over the finished palette (`lighten`, `saturate`, `tint`, each limited by `keys` to a colour group such as `hull`, `decks`, `upperworks`, `armament`, `funnels`, or to single palette keys). Shapes take numbers beside the named modes, which are now presets of them: `block_round`, `funnel_round`, `funnel_squareness`, `funnel_band_w`, `tripod` (leg length, 0 = pole), `top_r` (fighting top) and `deck_line_opacity`. The `looks.py` docstring lists them all. A bad `from` or era name fails when `looks` is imported.

## Outputs (out_designs/<id>/)
- `report.json`: valid flag, errors, warnings, the hull's length, beam and block coefficient, displacement (std/full), draught, power, fuel, crew, GM, trim, and the weight list with x/z. Carriers add aircraft and capacity, flight deck size and height; merchants add cargo, deadweight and hold count.
  - `crew`: the complement by department, with officers, CPOs, ratings and hotel crew. Also:
    - volumes: living, provisions, water (and how much of it is in the double bottom), distiller output
    - space: needed against usable
    - the comfort inputs: sleeping area per man against the standard's, headroom against deck height, berth ratio, sickbay beds, tolerance days, endurance against fuel range
  - `hull`: the structure (`construction` name, `structure_t`, split into `min_gauge_t` and `strength_t`), its plating (`plate_min_mm`, `plate_strength_mm`) and its `girder` amidships: `allowable_stress_mpa`, the moment of inertia it needs (`required_m4`) and what carries it (`plating_m4`, `armour_decks_m4`). For the damage model: the hull breaks when what's left of plating plus armour decks falls well below what's needed. Planing craft give only `structure_t`.
  - `plant`: the plant's static numbers for the game (`powerplant.published`), and how it sits in the hull:
    - power: rated and continuous kW, overload headroom, shafts and units
    - fuel: fuel rate and the part-load curve
    - draught system and engineering crew
    - its space: machinery length, boiler and engine rooms, rows, protrusion, bunkers
    - funnels: count, gas area and velocity, and smoke reach
- `hitboxes.json`: all values in metres, ship-local (origin = sprite centre, +x bow, +y starboard). It describes the ship for the game's damage model (where things are, what armours them, what links to what), never what a hit does.
  - Heights (`base`/`top`/`z`) are metres above the main deck, negative below it. On a carrier the main deck is the hangar deck.
  - `vertical`: `keel`, `waterline` and `armour_deck` (the main armour deck, null on a ship without deck armour) on that height scale, plus `draught`, `depth` and `freeboard` (full load).
  - `hull`: the hull outline polygon.
  - `armour`: present only for the armour the ship has (`navarch.armour_geometry`, the same geometry its weights come from). Every armour piece carries `material`, the design's `armour.materials` string, when the design names one. The same goes for armoured components (turrets, barbettes, the conning tower, armoured casings, an armoured flight deck with its `armour_mm`) and for deck `plates`. Armoured transverse bulkheads carry `armour_material`; cells carry `belt_material` and `armour_above_material` (parallel to `armour_above_mm`).
    - `belt`: `thickness_mm`, `x0`/`x1` (the citadel), `bottom`/`top`. A tapered belt adds `bottom_mm` (at `bottom`) and `taper_from` (the waterline, where the taper starts). From below the waterline up to the main armour deck, or centred on the waterline if that deck is lower.
    - `decks`: the armour decks, top down: `deck` (its id, such as `Second deck`), `thickness_mm`, `extent`, `x0`/`x1`, `z`, and the flags `main` (the main armour deck) and `roof` (the lowest, over the vital spaces).
    - `strakes`: the side armour other than the main belt (`armour.upper_belt` and `armour.end_belts`), each with `id`, `kind` (`upper` | `end`), `extent` (`citadel` | `fore` | `aft`), `thickness_mm` (at the citadel end), `tip_mm` (at the hull's end, only when it tapers), `x0`/`x1` and `bottom`/`top`.
    - `bulkheads`: the citadel's forward and aft ends: `x`, `thickness_mm`, `bottom`/`top`.
  - `components`:
    - Turrets: `local` body/parts/barrels polygons (rotate them by the turret angle, then add x, y), `broadphase_r`, `arcs_deg`, `rest_deg`, base/top heights.
      - `armour_mm` is the face. `armour` splits it into `face`/`side`/`rear`/`roof` (`hitbox.TURRET_*` ratios).
      - Gun mounts link to their `barbette` (a component) and their `magazine` (a room). The barbette links back with `mount` and reaches down to the main armour deck (the belt top without deck armour, the second deck on an unarmoured ship). A mount on a sponson or a flight deck has only a 1 m pedestal on its platform.
    - Superstructure: polygons with heights and a `role`: `bridge`, `director`, `aft_control`, `island`, `hangar`, `casemate` or `deckhouse` (`hitbox.BLOCK_ROLES`). A control position in a funnel's smoke lists those funnels in `smoke`.
    - Funnels: polygons with heights. `boiler_rooms` lists the rooms each one serves. An `uptake` component runs from the top of the boilers up to the funnel's base, with the same footprint and links.
    - `casing`: over machinery taller than its space, from the bounding deck up, with `armour_mm`.
    - `conning_tower`: a circle inside the bridge's front on warships with a belt, armoured like the belt. It isn't drawn.
    - Decks: `flight_deck`, and `deck` for raised forecastles, bridge decks and poops. `sponson`: gun and AA platforms, and deck-edge elevators. All are polygons with heights.
    - AA: circles.
  - Hangars are `hangar_bay` components: boxes above the hangar deck, outside the subdivision.
  - **The subdivision** (`subdivision.py`) is the hull below the main deck as a grid of watertight cells, and the rooms that own them. A point inside the hull below the main deck is in exactly one cell, and every cell has exactly one owning room.
    - `sections`: the hull between transverse bulkheads, `id` numbered from the bow, with `x0`/`x1`.
      - The stations snap to the ends of the rooms (machinery rooms, magazines, holds, steering), the citadel's ends and a collision bulkhead 0.05 L abaft the bow. Where several rooms end at one place, the station counts for more.
      - Stations closer than 0.03 L (at most 8 m) merge, and the more important one stays. Gaps longer than 0.07 L get more bulkheads, except inside a single room such as a long hold.
      - Capital ships come out at 17–21 sections, a destroyer at 19, and a PT boat at 10.
    - `decks`: keel up, `id`, `kind` and `z`. The kinds are `inner_bottom` (not on planing craft), then the deck stack (`deck`, numbered in `deck`, up to the `main` deck). An armoured deck has `armour_mm` over `x0`/`x1`; one armoured over several stretches (the citadel and its ends) lists them in `plates` instead, each with `armour_mm`, `x0`/`x1`.
    - `tiers`: the spaces between decks, keel up, each named after the deck it stands on: `bottom` (the double bottom), `hold`, then ..., `third`, and `second` under the main deck. Each has `base`/`top`, `submerged` (the fraction below the waterline), `below_waterline` (all of it), and its `floor`/`ceiling` deck ids.
    - `bulkheads`:
      - Transverse ones: `x`, `kind` `collision`, `armoured` (the citadel ends when `armour.bulkhead_mm` is above 0, with `armour_mm` from `armour_bottom` to `armour_top`) or `main`. They run from the keel to the main deck.
      - Longitudinal ones per section: `y`, `side`, `x0`/`x1`, `base`/`top`, and a `kind`:
        - `wing`: inboard of coal wing bunkers, up to the main deck.
        - `tds`: inboard of the torpedo protection inside the citadel, up to the lowest armour deck.
        - `centreline`: through the machinery, when `machinery.centreline_bulkhead` is true.
    - `cells`: `id` (`"7 hold S"`), `section`, `tier`, and `band` (`P` | `C` | `S`, with the centre split `CP` | `CS` by a centreline bulkhead).
      - Extent: `x0`/`x1`, `y0`/`y1` (out to the hull's widest point over the section, so clip to the hull outline) and `base`/`top`.
      - `volume_m3` is the hull's plan inside the box times the height. The part below the waterline is scaled so the underwater parts add up to the displacement volume.
      - `permeability` comes from the room's kind (`subdivision.PERMEABILITY`; a full coal bunker is 0.4), and `below_waterline` is set from the tier (the whole cell is under water).
      - The owning `room`, and `also`: the rooms that share this cell because they're too small for one of their own.
      - Armour and protection: `citadel`, `armour_above_mm` (the armour decks above the cell, top down, as a list of thicknesses), `belt_mm` (an outer cell level with side armour: the thickest belt or strake beside it, at the cell's middle along a tapered end belt and at the top of its overlap down a tapered main belt) and `tds_m` (a wing cell inside the citadel).
      - `crew`: the complement spread over the quarters by volume.
      - `neighbours`: `[cell id, boundary]` pairs. The boundary is the bulkhead or deck id between them, or `"open"` inside one room.
    - `rooms`: `id`, `kind`, `cells`, `volume_m3` and their extent (`x0`/`x1`, `base`/`top`), plus what the layout gives them:
      - `fuel` and `tonnes` for bunkers; `mount` or `mounts` for magazines; `crew` for quarters.
      - `shared: true` marks a room that only shares a cell.
      - Rooms snap to whole cells: a room owns a cell when it overlaps the cell by at least half the shorter of the two along every axis. Contested cells go by `subdivision.ROOM_PRIORITY` (magazines first, then machinery), then by overlap.
      - Kinds:
        - All ships: `boiler_room`, `engine_room` and `bunker` (`fuel` is coal, oil, diesel or petrol), and `steering` (`layout.add_steering`: 0.03–0.08 L forward of the stern, low on the inner bottom; a planing craft's tiller flat fills the stern abaft its engines).
        - Every ship with guns: `magazine` (`tonnes`, and `mount` or `mounts`). Carriers also have aviation magazines and `fuel_tank` (aviation fuel).
          - What burns or explodes sits lowest, under the hangar and the armour deck, so a bomb fused by the armour deck bursts in the decks above. Both are `ordnance.stow` zones, only as many decks tall as their contents need (`tonnes` on the room). Their weights sit at the rooms' heights.
            - The aviation magazines hold the ordnance (`carrier.ORDNANCE_K`, 0.6 t per tonne of air group, at `ordnance.T_PER_M3`).
            - The aviation fuel tanks hold the avgas (`carrier.AVGAS_K`, 1.2 t per tonne of air group, at `carrier.AVGAS_T_PER_M3` 0.5 t/m³: petrol with the void and water-filled spaces around the tanks).
        - Merchants: `hold` or `cargo_tank`. Planing craft: crew space, fuel tanks and the tiller flat.
      - Cells no room claims become one room per section and use:
        - `double_bottom` in the bottom tier
        - `tds` (`Torpedo protection 7 S`) in a citadel wing cell
        - `stores` in a tier at least half under water
        - `accommodation` (`Quarters 7`) above that.
- `sprite.json`: layers, origin_px, mount px positions, rest angles, arcs and z order.
- `hull_base.png`, `turrets/*.png`, `hull_upper.png`, each with an SVG alongside. Level 0 is `--scale` px/m (default 10). No shadows are baked in.
- `height.png`: greyscale height map on the same canvas. Grey × `height_step_m` (0.25) = metres above the waterline, and 0 = sea. Its mips use a 2×2 max filter, not an average, so a tall column never shrinks.
- `<layer>_mips.png` sits next to each layer PNG (`hull_base`, `hull_upper`, `height`, `turrets/<type>`) and packs level 0 plus every lower level into one image of 1.5W × H. Level 0 is on the left. Level 1 sits to its right at the top, and each next level goes alternately below and to the right of the previous one.
  - The exact `[x, y, w, h]` of every level is in `sprite.json`: `mip_rects` for the hull-sized layers, and `turret_types.<type>.mip_rects` for the turrets.
  - Each level is half the one before, made with a 2×2 box filter on premultiplied alpha. `--mips N` sets the count. Every canvas is a multiple of 2^(N+1) px, so each level halves exactly.
  - Within level k, sizes, `origin_px`, `pivot_px` and mount `px` are the level-0 values / 2^k.
  - The levels touch each other with no gap. Slice them into real GPU mip levels, or clamp UVs to each rect if you sample the packed image directly.
- `preview_*.png`, `sheet.png`: stats, firing-arc diagram and previews, shadowed with the sun at bearing 240°, elevation 50°. `debug_hitboxes.png`: hitboxes drawn over the sprite.
- `hitbox_bow.png`, `hitbox_quarter.png`, `hitbox_side.png`, `hitbox_internal.png` (`hitview.py`, debug only): the hitbox model in 3D, with every hitbox extruded from its base to its top.
  - Views: from the starboard bow, the port quarter, a side elevation, and an internal view that shows only rooms (less the quarters, stores, double bottom and torpedo protection that fill the rest), barbettes, uptakes and armour inside the hull's edges.
  - `hitbox_cells.png`: every tier of the subdivision in plan, keel tier at the bottom, with cells coloured by their room's kind. Labels give the section, `+` for a shared cell, and the crew.
  - The hull is translucent and the waterline is drawn in blue. Colours are by kind, with a legend.

## Conventions
- Bow → +x. Angles run clockwise from dead ahead (90 = starboard). Arcs are `[start, end]` intervals, clockwise; `end` may exceed 360.
- Firing arcs are fixed by mount kind, centred on the rest bearing (`hitbox.ARC_*`):
  - Centreline guns of a forward or aft group, including superfiring and carrier island-line guns: ±135°.
  - Centreline guns with a turret ahead of them (amidships turrets, flush turrets behind a superfiring one): ±65° about each beam. They stow fore-and-aft like real ships, pointing away from the nearest other centreline turret. Their rest bearing is therefore outside their arcs: train them out before firing. Every other mount rests inside its arcs.
  - Side mounts (secondaries, sponson guns, side torpedo mounts, wing turrets): ±90°, bow to stern on their own side. Wing turrets rest fore-and-aft, at the edge of that arc.
  - Casemate guns: ±60° about their beam (`ARC_CASEMATE`), resting abeam.
  - Centreline torpedo mounts: ±60° about each beam.
  - Fixed tubes: ±1° about their bearing.
  - Nothing on deck limits an arc. Instead, the warship layout places the main turrets first, and each reserves its sweep zone: a sector as long as its barrels, covering its arcs plus the turn from its stowed bearing to the starboard arc, so one side is always free for switching sides. Everything placed afterwards that stands taller than that turret's guns keeps out of the zone: bridge, aft control, funnels, masts, deckhouse, boats, secondaries, torpedo mounts and AA. The bridge and aft control step back, the deckhouse ends are trimmed, and the space needed is budgeted up front (a stowed turret's barrels, and the gap a side-firing turret needs beside its neighbours).
- Draw order: hull_base, then the turrets by ascending z, then hull_upper. Turret pivot = image centre.
- Pixel position = origin_px + metres × scale. Canvases are multiples of 2^(mips+1) px, so the origin falls exactly on a pixel at every mip level.

## Shadows
The sun is dynamic, so the game casts the shadows. `shadow.py`'s docstring has the details, and `shadow_mask()` there is a numpy reference implementation to port.
- Static structure: in a shader, march from each pixel toward the sun across `height.png`. A pixel is in shadow if `H(p + t·d) > H(p) + t·tan(elevation)` for some t > 0. `d` is the sun direction in ship-local space (sun bearing minus ship heading). The receiver's own height H(p) makes the result correct for sea, deck and roofs alike. Draw the shadow quad larger than the sprite by `max_height_m / tan(elevation)` and sample with a border of 0.
- Turrets aren't in the height map because they rotate. Draw each turret sprite in black after `hull_base` and before the turrets. Rotate it with the turret and offset it away from the sun by `(top_m − deck_m) / tan(elevation)`.
- The lighter rim on the upper-left edges of blocks and funnels is still baked in. It's a highlight, not a shadow.

## Tuning
- `navarch.TUNING`: the weight and power constants.
- `hullweight.py`: the hull-structure constants (fitted in `research/hull-weight-model.md`; `research/hull_weight_ref.py` is the reference implementation).
- `layout.py`: the clearances (bow_pref/min, st_pref/min), turret spacing, bridge size and AA spacing.
- Each style's `tuning()` overrides `TUNING` for its designs: the volume-law hull weight (planing craft), freeboard, outfit fraction, hull CG height, the draught limit, and so on.
- Calibration (2026-10-04). Two checks, standard displacement in tonnes:
  - **At the real ship's size** (`python calibrate.py`, `-g` for weight groups) the weights alone are tested. Mean error 11%.
  - **Sized** is what the designer makes of the design, so its size search's errors (beams come out narrow) add to it.

  | design | at real size | sized (std / full, power) | real ship |
  |---|---|---|---|
  | `bismarck` (as completed) | 44.2k (+6%) | 39.8k / 43.8k, 224 × 32.3 m | 41.7k std, 241.6 × 36 m |
  | `battleship_layered` (Iowa-style) | 54.0k (+17%) | 54.1k / 62.3k | ~45–48k std |
  | `battleship` (30 kn Iowa-like) | – | 43.5k / 50.1k | ~45k std |
  | `heavy_cruiser` (Baltimore-like) | 14.7k (0%) | 14.0k / 16.3k | 14.7k std |
  | `destroyer` (Fletcher-like, 80 mm guns) | 1.9k (−8%) | 2.1k / 2.6k | 2.08k std |
  | `fleet_carrier` (Essex-like, open hangar) | 27.0k (−2%) | 26.9k / 34.5k, 162k shp | 27.5k std, 150k shp |
  | `supercarrier` (Forrestal-like, closed hangar) | 44.1k (−27%) | 46.4k / 55.8k | 60.6k std |
  | `escort_carrier` (Casablanca-like) | 6.1k (−22%) | 4.4k / 5.4k | 7.9k std |
  | `liberty` (Liberty ship) | 3.0k (−12%) | 3.2k / 13.3k, 2,100 shp | 3.4k light, 2,500 ihp |
  | `tanker` (T2-like) | – | 4.2k / 20.5k | ~5.3k light |
  | `dreadnought` (21 kn) | 21.4k (+22%) | 23.9k, 33.1k shp | 17.5k (18.4k normal less coal), 23k shp |
  | `nassau` (19.5 kn) | 18.2k (+2%) | 18.3k, 22.1k shp | 17.9k (18.9k normal less coal), 22k ihp |
  | `nassau_casemates` | – | 19.7k, 23.0k shp | as above |
  | `mikasa` (18 kn) | 11.8k (−19%) | 11.6k, 12.9k shp | 14.7k (15.4k normal less coal), 15k ihp |
  | `connecticut` (no 8" turrets) | 14.2k (−7%) | 13.5k, 14.3k shp | 15.4k (16.3k normal less coal), 16.5k ihp |
  | `kongo` (as built, 27.5 kn) | 30.5k (+16%) | 37.0k, 99.9k shp | 26.4k (27.4k normal less coal), 64k shp |
  | `invincible` (25.5 kn) | 16.7k (+1%) | 17.9k, 48.5k shp | 16.5k (17.5k normal less coal), 41k shp |
  | `battlecruiser` (Lion-like, 28 kn) | 26.7k (+4%) | 30.0k, 90.5k shp | 25.7k (26.7k normal less coal); ~92k shp on trials |
  | `gangut` (a silly 22-turret test) | – | 275k | – |
  | `mtb` (Vosper 70 ft-like) | – | 35 / 44 t, 3,000 hp at 39 kn | ~47 t, 3,750 hp |
  | `pt_boat` (Elco 80 ft-like) | – | 60 / 72 t, 5,300 hp at 41 kn | ~46 / 56 t, 4,500 hp |

  - Bismarck's weight statement (kbismarck.com) checks the groups: hull and superstructure +13% (the research found +15%), armour without turrets +8%, outfit, crew and stores within 3%, turrets (with `gun_k`, `mount_k`, `turret_t_avg`) about −6%.
  - Known causes of the big misses: Dreadnought's and Kongo's armour inputs are heavier than the real schemes; the Iowa-style citadel is longer than Iowa's (deck armour 6.6k t); the pre-dreadnoughts and the Forrestal- and Casablanca-like carriers are light, and there's no group data yet to say where.
  - The tanker needs about 30% more power than a real T2: the Admiralty-coefficient power model is pessimistic for full hulls above Froude 0.18.
  - Carrier full loads run light because the range model burns less fuel at cruise than these ships actually carried.
  - The planing numbers rest on the placeholder power model; the PT boat comes out heavy.
