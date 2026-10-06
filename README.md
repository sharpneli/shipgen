# shipgen: parametric top-down ship designer and sprite generator

```
pip install cairosvg pillow numpy             # the renderer only; the design side needs the standard library alone
python design.py designs/*.json            # player designs -> out_designs/<id>/ (10 px/m + 5 mip levels)
python design.py designs/x.json --no-limits # skip the input ranges; errors (capsizing etc.) never block output
python design.py designs/x.json --no-previews # game assets only (sprites, mips, height map): ~0.5 s, not ~3 s
python verify.py out_designs/battleship     # pixel check: sprites vs hitboxes
python fuzz.py designs/*.json               # robustness: mutated designs must build (no crash, hang or memory blow-up);
                                            # 150 cases by default, --cases 1600 for a thorough run
python shipgen.py                           # the original hand-authored fleet (fleet.py)
python vidgen/vidgen.py bismarck            # style check: a short gameplay-style video -> vidgen/out/bismarck.mp4
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
   ├─ sinking.py   demo: floods the subdivision from a breach and draws the ship settling, plunging or capsizing
   ├─ shipgen.py   SVG/PNG drawing (hull, turrets)
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
             "end_belts": {"fore": {"mm": 0, "tip_mm": 0, "reach": 1.0, "bulkhead_mm": 0}, "aft": {"mm": 0, "tip_mm": 0, "reach": 1.0, "bulkhead_mm": 0}},
             "steering_box": {"mm": 343, "deck_mm": 157, "bulkhead_mm": 287},
             "turret_mm": 432, "decks": [{"deck": 1, "mm": 152, "extent": "citadel"}]},
  "main": {"calibre_mm": 406, "calibre_length": 50, "barrels": 3, "fore": 2, "aft": 1},
  "secondary": {"calibre_mm": 127, "calibre_length": 38, "barrels": 2, "per_side": 5, "stands_on": "deckhouse"},
  "torpedoes": {"mounts": 0, "tubes": 5},
  "aa": {"heavy": 20, "light": 30},
  "machinery": {"stress": 0.4, "shafts": 4, "rudders": 2, "tech": {...}},
  "crew": {"standard": {...}, "endurance_days": 45, "distiller": true},
  "superstructure": {"t_per_m2": 0.32, "material": "steel", "tower_levels": 7},
  "fire_control": {"main": {"directors": 2, "rangefinder_m": 7.9, "armour_mm": 38, "radar_t": 2.0, "computer_t": 8.0},
                   "secondary": {...}, "aa": {...}, "search_radar_t": 4.0},
  "funnels": null
}
```
`armour` holds the belt, turret and torpedo protection (`tds_m`) values, and `decks`: the armour decks, top down. Every design lists them, even an empty list.
- **Torpedo protection** is weighed as longitudinal bulkheads totalling `TUNING tds_mm_per_m` (12 mm) per metre of `tds_m`, each side over the citadel, from the inner bottom to the roof deck (Bismarck: a 45 mm torpedo bulkhead and thinner ones, 5.5 m deep). An armoured ship's **conning tower** (the hitbox's cylinder, walls as thick as the belt, a roof half that) is weighed too.
- **The deck stack:** the hull's decks lie every `navarch.DECK_PITCH` (2.6 m) down from the main deck to the inner bottom. Deck 0 is the main deck (a carrier's hangar deck), deck 1 the second deck, and so on. A deck closer than 1 m to the inner bottom is left out, so the hold is 1–3.6 m tall. Raised stretches of hull (`hull.raised`) add decks above the main deck, numbered −1, −2, …, which exist only over their stretches.
- **An armour deck** is `{"deck": n, "mm": thickness, "extent": "citadel" | "full" | "fore" | "aft" | "ends"}`. `citadel` covers the citadel, `full` the whole length, and `fore`, `aft` and `ends` (both) the hull beyond the citadel's ends: the protective deck at a pre-dreadnought's ends, or the deck over an all-or-nothing ship's steering gear. List the decks top down. A deck may appear twice only over different stretches (the citadel and its ends, say 76 mm on the second deck amidships and 51 mm on it at the ends). A deck the hull is too shallow for lies on its lowest deck, with a warning; overlapping decks pushed onto the same one add up. A raised deck (−1, −2, …) is plated only over its stretches, and one higher than any the ship has lies on the highest there is (or the main deck). Raised decks are never the main armour deck or the roof.
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
- `upper_belt`: `{"mm", "to_deck", "extent"}`, a strake from the top of the belt below it up to deck `to_deck` (0 the main deck; −1, −2, … a raised deck, which it reaches over the raised stretches, and the main deck elsewhere). Over the citadel it starts at the main belt's top; beyond it, at the end belt's top (or the main belt's waterline band if there's none). It has no height, and warns, when the belt already reaches that deck. `extent` takes the deck extents, and `full` is one strake over the citadel and one beyond each end.
- `end_belts`: `{"fore": {"mm", "tip_mm", "reach", "bulkhead_mm"}, "aft": {...}}`, the waterline belt carried on from the citadel toward the stem and the stern. It's as deep as the main belt and reaches up to the thickest armour deck over that end when that's higher. It is `mm` thick at the citadel and tapers linearly to `tip_mm` at its far end.
  - `reach` is how far it goes: 1 all the way to the stem (stern), 0.5 half way, 0 not at all. Real practice varied widely, from belts closed short of the ends by a bulkhead (many pre-dreadnoughts aft) to full-length belts, so this is a number and not a choice.
  - `bulkhead_mm` closes a belt that stops short (`reach` under 1) with an armoured transverse bulkhead at its far end, from the citadel bulkheads' lower edge up to the belt's top. 0 leaves it open.
- `steering_box`: `{"mm", "deck_mm", "bulkhead_mm"}`, a separate armoured box round the steering gear, as on all-or-nothing ships (Iowa, Yamato). All zeros means none. It can be combined with any end belts.
  - Its sides (`mm`) run along the hull side over the steering gear's length (0.03–0.08 L forward of the stern), from the inner bottom up to the deck over the gear. That's where `layout.add_steering` stands it, 2 deck spaces up. `deck_mm` is the roof on that deck, and `bulkhead_mm` the two ends. The roof and bulkheads span the hull's width at the box.
  - The hull between the citadel and the box stays unarmoured: that gap is the all-or-nothing trade. A box on a heavily armoured ship costs more than its own tonnes, because the weight aft lengthens the ship and the citadel with it (Yamato's 1.3k t box adds 5.4k t standard).
- How the schemes come out:
  - **All or nothing** (Nevada onward): a thick belt and deck over the citadel, heavy bulkheads, and nothing else (`all_forward.json`). The later ones add an armoured box over the steering gear (`battleship.json`, `yamato.json`).
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
- **Hull first, then up:** the crew lives in the hull first. The share of the needed volume the hull can't hold is quartered in the superstructure, spread over its blocks by volume (not directors, casemate housings or hangars), and weighed there. The report's `crew` gives `quartered_in_superstructure` and `superstructure_quarters` ({block: men}). Those blocks' hitboxes carry `crew`: a superstructure hit can kill off-watch men only where they actually sleep. The subdivision quarters the rest in the hull.
- **Where they sleep:** the subdivision spreads the complement by volume over the cells no room claims above the waterline (`Quarters <section>`), and over a planing craft's crew space. A merchant whose holds fill the hull has no quarters below the main deck; its crew lives in the superstructure, which the subdivision doesn't cover.

`superstructure` is how the upperworks are built. Every design writes it out.
- `t_per_m2`: structure weight per m² of each level's footprint. Steel is about 0.32; aluminium (Forrest Sherman, Spruance) about 0.2. Planing craft use 0.10 (a wooden charthouse).
- `material`: a plain string passed to the superstructure's hitboxes for the game (an aluminium house burns and dents in a seaway). The designer doesn't read it.
- Every warship superstructure level is laid out like a deck, not a slab, by one rule (`layout.add_level`, `level_outline`): the 01 deckhouse, the deckhouse levels over it, the bridge tower (`Bridge base n`, `Bridge`, `Bridge upper`, `Tower n`) and the aft control. The layout decides each level's core (where it goes, how long and wide); the rule shapes it:
  - It stands on its support and is clipped to it: the deck, 0.6 m in from the edge, for level 1 (so it narrows toward its ends with the hull), and the level below for the rest. The bridge itself stands on the deck band, so its wings may overhang a tapered column.
  - Its ends keep clear of the end turrets' bodies (plus 1 m) and of their barrels' swing at any height, for blast and swing (wing and midships turrets don't count). They also keep clear of every other turret's sweep lower than the roof, and of whatever stands at the level's height (secondaries, wing turrets, the bridge beside a deckhouse level; funnels pass through). Inside a turret's blind arc that gives a nose pointing at it with swept shoulders.
  - Each end is convex and symmetric, with at most two corners a side: either flat, or a face across the ship (at least 1.5 m wide, or none: a point) with one straight sweep from each edge back to the side, as shallow as the obstacles allow. A sweep must fall back at least 0.75 m and add 3 m² a side over the flat end. Nothing random goes in. Corners are sharp.
  - No level grows past its core, so towers keep their setbacks. A level never pulls back from under what stands on it.
- Level 1 (warships) is built under what needs it, with no size rule:
  - Under the bridge, from 3 m aft of it to 1 m forward (the bridge's base levels stand on it), and under the aft control (`Aft control base 1`).
  - Under the riders: guns that stand on the deckhouse (`secondary.stands_on`, `main.amidships_stands_on`, below) and the upper casemates' housings. The riders get one piece over all of them, as wide as the widest needs (each gun's footprint plus 0.6 m; for housings, out to their inner faces, so the level and the housings make one battery deck). It runs on under the bridge and the aft control where the main deck between is free (nothing stands there or sweeps it below the roof; funnels pass through), since a gap there would only be bare deck.
  - A ship whose guns all stand on the main deck keeps level 1 under its towers only (Dreadnought). Its `deckhouse_levels` can still carry a house along the centreline.
- `deckhouse_levels` (warships): how many levels the deckhouse amidships has; 1 is the old single level. Each level above stands on the one below, wraps around the funnels, and keeps clear of what stands on the roof below (secondaries, wing and midships turrets, bridge, aft control) and of the guns' sweeps. It is as wide as it can be while keeping 70% of the length it would have at 3 m wide, and its roof carries AA and directors. Where something on the roof below (a secondary) would break it, the level narrows there instead, a notch with 45° shoulders, so it runs on in one piece (`layout.notch_outline`, at least half its width; a notch shallower than 0.75 m narrows the whole level instead). The levels above keep the notch. An end within 1.5 m of the bridge tower or aft control at the same level runs on to butt flush against it (`DH_JOIN`); where it is wider than that block's face, each side falls back to the face's edge in a straight shoulder, 2 m along per m across (`DH_SHOULDER`, at most a quarter of its length). The upper levels' free corners get a bolder bevel (`BEVEL_UPPER`: 2 m, 15 % of the width) (`layout.add_deckhouse_levels`). Where level 1's deckhouse covers less than half the middle (no riders: only under the bridge), the first extra level carries it along the middle first, Fletcher-style. The blocks are `Deckhouse k[-i]`. Extra levels are room for the crew, so a crowded ship gets shorter instead of longer, but they cost topweight (the sizing then needs more beam for GM) and windage. Example: the destroyer at 2 levels comes out 114 m long instead of 130 m (Fletcher: 114 m), with GM 0.76 m instead of 1.28 m. A ship with room in its hull only gets heavier.
- `tower_levels` (warships and carriers): the bridge tower's (or the island's) top level: the tower's height, a slider that trades sight against stability. On a warship the navigating bridge stands as high in the tower as leaves the levels over it (`Bridge upper`, `Tower n`, narrowing as they rise, with the main director on top: 1 level, 2 from 180 m), on full-width `Bridge base n` levels. It never stands lower than the first level whose deck is `layout.BRIDGE_CLEAR` (1 m) over the roof of the highest forward turret, so it sees over it: 2 with nothing superfiring ahead, about 4 on a destroyer with a superfiring mount, 5 on a battleship. A tower too low for that puts the bridge on its top level with a warning, never an error (a squat ship is the player's call). One model for every navy: a tall setting is a Nelson or Yamato tower (Nelson's bridge stood about level 8 of 10). Above level 6 (`layout.TOWER_TAPER_FROM`) the base levels taper, about 7 % narrower and 4 % shorter per level, so a very tall tower becomes a pagoda, its bridge a full-width platform near the top. Height buys the bridge's and directors' horizons (report `bridge`, `fire_control`) and costs topweight and windage (`gm_full_m`, `gale_heel_deg`, `windage_m2`); the size search widens the hull to hold GM, so big ships pay little and small ones a lot. The aft control (ships from 130 m) follows the same rule over the aft group's highest turret, with `Aft control base n` levels under it and one upper level over it; it has no slider. A carrier's island bridge is level 3. Funnels stand as tall as a tower of up to 4 levels, whatever the tower, and 3 m (`layout.FUNNEL_ABOVE`) over the highest deckhouse level they pass through (`layout.raise_funnels`). Without the key: the lowest bridge that sees over the guns, plus the levels over it.

**Topweight and windage** (`navarch.wind_heel`, `roll_period`). Everything up top raises the centre of gravity, and the sizing then needs more beam for its GM (more power, more weight). On top of that the report gives:
- `windage_m2`: the side profile the wind sees: the hull's freeboard plus the union of the superstructure, raised decks (a carrier's hangar and flight deck), funnels, masts, mounts and AA (`layout.lateral_profile`).
- `gale_heel_deg`: the steady heel in a 26 m/s beam gale (the IMO weather criterion's 504 Pa), at full load or light (fuel burnt), whichever is worse (`gale_heel_condition`), with `deck_edge_deg` (the angle that puts the deck edge under) and `deck_edge_wind_kn` (the wind that heels it that far).
- `roll_period_s`: the natural roll period at full load (IMO formula). A stiff ship rolls fast and snappily, a tender one slowly. The game decides what that does to gunnery.
- Heeling more than 16°, or 0.8 of the deck-edge angle, warns. It's never an error: the game's designer UI decides what to allow, and a player may insist on a ship that capsizes on a windy day.
- Examples: the destroyer with three deckhouse levels heels 22° light (5° as built). The seaplane carrier (GM 0.66 m) heels 14°; the battleship heels 2°.

`fire_control` is the directors and the plotting rooms behind them (`firecontrol.py`). Every design writes out all three batteries, with zeros for what it lacks. Each battery takes `{"directors", "rangefinder_m", "armour_mm", "radar_t", "computer_t"}`, plus `search_radar_t` for the search radar.
- **Directors** stand on the superstructure's roofs as blocks of their own (role `director` in the hitboxes, with `battery`, `rangefinder_m`, `armour_mm` and `radar`). Main directors take the highest roofs, the first two at least a quarter of the length apart (fore and aft) when they can. Secondary and AA directors take the highest roofs, for their horizon: at each height, spots out of the funnels' smoke first, then a pair (one each side) where it fits and two are left, else singly on the roof's line (a narrow house, a tower top, a carrier's island). A director with no roof to stand on is an error. Each is drawn and hit as the same shape (`geometry.director_parts`): a hood with a cut front, the rangefinder's tube across it and an end hood at each tip standing out past its sides, and a radar aerial on the roof when `radar_t` > 0. A director without a rangefinder (a Mk 51 gyro sight) is a round tub.
- **Weights** (estimates, `firecontrol.py`): a 2.2 m hood of 6 mm plate around a rangefinder whose arms stick out athwartships (`rangefinder_m` + 1 m wide), training gear and sights (1 + 1.2 × base t), the rangefinder (0.03 × base² t), the hood's armour and the radar, all at the director's height. `computer_t` is the director's share of the plotting room (range clock, Dreyer table, rangekeeper), low in the hull. A Mk 37 comes out at about 20 t, a Mk 51 (no rangefinder) at 1.7 t, and Bismarck's 10.5 m main directors at about 45 t each.
- The search radar sits on the foremast top. Masts now weigh 0.012 × height² t per leg (a tripod has three legs) at half their height.
- **The report's `fire_control`** lists every director with its eye height above the waterline and its visual horizon (3.57 √(1.17 h) km). The game decides what that means for spotting. A main battery with no director warns that its turrets fire under local control.
- The values are raw numbers. Templates (a bureau's director that many ships share) belong to the game's designer UI.

`aa` (`heavy` 40 mm quads, `light` 20 mm singles) stands high, as on real ships (`armament.place_aa`, the warship's `aa_slots`):
- **Order of preference:** tubs on the superstructure's roofs, the bridge and aft control levels first, then the tower's top and the deckhouse (01 level). Once the roofs are full, the rest go on the bare deck edges. AA goes high only where the superstructure already is: a mount never gets a pedestal of its own. Within each, nearest amidships first, and pairs before single mounts on a roof's centreline (`layout.AA_ROOF_PEN`, `AA_DECK_PEN`).
- Carriers put tubs on the island's roofs first, then on sponsons; merchants on the houses and ends.
- **Weight:** a mount above the main deck also weighs its tub, platform and splinter shield (`armament.AA_TUB_T`: quad 3 t, single 0.3 t), and a platform's pedestal weighs as superstructure. All of it counts at its height, so a ship crowded with AA pays in topweight.
- Collision tests are height-aware (`Layout.free_at`): a tub may stand on a roof but not inside a taller block.

`machinery` is the propulsion plant (`powerplant.py`, from `research/powerplant-model.md`). There is no year input: `tech` holds the researched technology as numbers, so a navy can have a tech earlier or later than history did. `plant-templates.md` has blocks to copy for every period from 1880 to 1970, and `python plant_templates.py` regenerates them. A design without `tech` gets a 1940 high-pressure turbine plant (merchants: a 1940 oil-fired triple expansion; planing craft: 1940 petrol engines). The other keys are design choices: `stress`, `shafts`, `units_per_shaft`, `transmission`, `arrangement` (`grouped` or alternating `unit`), `centreline_bulkhead`, `bunkers` (`wing` or `ends`), `wing_bunker_m` and `rudders` (1 on the centreline, 2 or more spread behind the inner propellers; `propulsion.py`). The template's table explains each one. What the plant decides:
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

`hull.raised` (warship style) lists raised stretches of hull: a forecastle, a poop, a forecastle stepping down in two decks. Each entry is `{"from": "bow" | "stern", "to": a feature, "decks": n}`: the hull rises `n` decks (2.6 m each, the same pitch as the deck stack and the superstructure levels) from that end through the feature, its break just beyond it. Features, bow to stern: `fore_group` (the forward turrets), `bridge`, `funnels`, `aft_control`, `aft_group`. Entries are independent and combine by taking the highest deck at each point, so any combination is valid; a feature the ship lacks falls back to the next one toward the entry's end, with a warning. `"decks"` is limited to 1–2 (`--no-limits` takes more). Every warship design states it (`[]`: flush-decked to the main deck). `hull.freeboard` stays the main deck's freeboard; a raised stretch stands on top of it.
- A raised stretch is hull: it is weighed at the hull's minimum gauge (deck, sides, the break bulkheads), it works in the hull girder by its mean height over the middle 0.4 L (`navarch.raised_girder_h`: a long forecastle carries it, a short one near the bow doesn't, as on real ships; the girder deepens, so it needs less strength plating), it gets cells in the subdivision (quarters unless a room claims them), and the crew lives there before the deckhouse.
- Levels count from the main deck, so a one-deck forecastle is level 1 where it stands. Guns and superstructure on it stand on its deck: the bridge tower on a forecastle needs one fewer level of superstructure for the same height, and `stands_on: "deckhouse"` guns over a forecastle stand on its deck with no deckhouse under them. Upper casemates over a raised stretch are in its hull side, without housings.
- Main turrets stand on the deck under them. A superfiring turret stays a step over the turret it fires over, and a turret whose barrel sweep reaches over a higher raised deck stands higher, until its guns clear that deck by 1.1 m (`layout.raised_lift`); arcs stay fixed. The bridge rule counts the raised deck under the forward group.
- Funnels don't trunk across a break.
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
- `"superfire"` sets how many turrets of each end group step up: `true` (default, all), `false` (none, so each group has one end turret and flush turrets behind it), or `{"fore": 2}`. A flush turret behind a stepped one (Nelson's X) fires to the sides only. Each stepped tier stands `2.0 + 0.2 × turret height` m above the one it fires over (about a deck: 2.3 m for 5in twins, 2.6 m for 16in triples, after Atlanta and Iowa).
- `"wing": n` (warship style only) adds n pairs of wing turrets, one each side, amidships. They fire bow to stern on their own side, so the forward pairs can fire dead ahead together with the forward group, and across the deck only with `cross_deck`.
  - By default each pair stands abreast. The first pair goes at the forward end of the middle, the second at the aft end, then they fill inward (Dreadnought: one pair; Nassau: two, hexagonal).
  - `"echelon": true` staggers each pair, port forward and starboard aft, and spreads the pairs among the funnels (Invincible, Neptune). An echelon pair fits a beam that's too narrow for an abreast pair, at the cost of length.
  - Wing turrets stow fore-and-aft toward the nearer end of the ship. Secondaries fill the spots the wing turrets leave free.
  - `"cross_deck": true` (echelon pairs only; an abreast pair only warns) lets each wing turret also fire across the deck, through a second, narrower arc of ±30° about the far beam (`hitbox.ARC_CROSS`). It trains across through the end it stows toward (the forward turret through ahead, the aft one through astern), because the partner usually blocks the other way (it does on Invincible; on Seydlitz it stands just out of reach, but only one way is reserved and exported). The layout keeps that whole swing clear: the stagger keeps the partner's body out of the cross arc, and the funnels, midships turrets, bridge and aft control on the turn side stand beyond the muzzles' reach (open machinery deck counts toward that). It costs length: Invincible 194 → 206 m, mostly from moving the funnels clear of the forward turret's turn. Every echelon design states it; `invincible.json` and `seydlitz.json` use it.
- `"amidships_stands_on"` (warship style): what the wing and midships turrets stand on. `"deck"` (the default) is the main deck. `"deckhouse"` is the roof of level 1, 2.6 m higher, and level 1 is built under them. Raised guns are drier and stand over what's on the main deck (boats, torpedoes, AA), at the cost of topweight and the deckhouse under them. Every design states it when it has wing or midships turrets. Dreadnought has `"deck"`; Nassau, Invincible, Kongo, Lion and Gangut have `"deckhouse"`.
- Examples: `gangut.json` (1 + 2 amidships + 1, all flush), `dreadnought.json` (A, wing pair, X, Y), `nassau.json` (hexagonal), `invincible.json` (echelon, cross-deck), `seydlitz.json` (echelon, cross-deck, superfiring aft pair, casemates), `battlecruiser.json` (Lion-style Q turret), `all_forward_flush.json` (all-forward with a flush third turret).

`secondary` (warship style) is one battery or a list of batteries, each with its own calibre, `per_side` and `armour_mm`, and `"mount"`:
- `"deck"` (the default): turrets or open mounts amidships. The first deck battery spreads evenly along the middle; later ones take the free spots nearest amidships. `"stands_on"`: `"deck"` (the default, the main deck) or `"deckhouse"` (level 1's roof, built under them), as for `main.amidships_stands_on`. Every deck battery states it.
- `"casemate"`: single guns at the hull side. Only a round port shield and the barrels show, outboard: half the barrel length (`geometry.BARREL_SHOWN`; turrets show 0.8 of theirs). Casemates stay where the hull is at least 85% of its full beam (`layout.CASEMATE_BEAM`). Two tiers, set by `"tier"`:
  - `"lower"` (the default): in the hull side, one level below the main deck (base −2.6 m, top 0). They keep clear of the main barbettes and of each other.
  - `"upper"`: on the main deck (base 0, top 2.6 m), each in an armoured housing against the deck edge (a level-1 superstructure block). Housings close together join into one gallery, and level 1 fills the deck between the two sides' housings (a battery deck: Victory, Mikasa). They keep clear of whatever stands on the main deck and of the main turrets' sweeps. The tiers stagger, so the upper guns stand between the lower ones and every gun shows.
  - Placement: the lower tier fills first, then the upper. Within a tier, each battery takes the free places nearest amidships in list order, so list the battery you want amidships first. The rows centre on the hull's full-width part and move with the balancing shift: after the nearest-first fill, the whole arrangement slides so its middle sits on that centre, wherever every gun still fits.
  - Spacing: a comfortable pitch if every gun fits that way. Failing that, the lower guns sit just far enough apart for one upper gun between each pair. Failing that too, closer still.
- Battery mount ids are `S1S`/`S1P`, ... for the first battery, then `SB...`, `SC...`. Casemate guns carry `"mount": "casemate"` in `hitboxes.json` and `sprite.json`.

`torpedoes` (warship style): mounts stand in pairs at the deck edges, nearest the machinery first, where the beam leaves room for a mount's swing beside the edge (half the beam, less the mount's radius and 0.8 m, at least its swing). Otherwise they stand on the centreline between the funnels, which then stand far enough apart (Fletcher). When those spots are taken, the mounts go on the deckhouse roof's centreline.
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

Limits are generous on purpose: the game's designer enforces the gameplay limits, and the generator only keeps its input sane (`styles.base.COMMON_LIMITS`). Guns can be 1–2000 mm with 1–20 barrels, armour up to 2 m, and torpedo, secondary and AA counts are in the hundreds. Hull form and speed stay within the range where the physics formulas mean something. Each turret group (`fore`, `aft`, `mid`) can hold up to 40 turrets, named A, B, C, A4, A5, ... (and Q, P, R, S, Q5, ... amidships). Silly designs are allowed; the physics decides whether they're valid, and the designer simply makes the hull as big as they need. For example, Gangut's twenty 305 mm Q turrets come out on a 904 m hull. A few inputs are checked even with `--no-limits`, because outside them the physics isn't silly but undefined: a block coefficient or speed of 0, a battery without barrels, calibre or calibre length, torpedoes without mounts or tubes (`styles.base` `DEFINED`, `REQUIRED`), and funnel gas no hotter than the air or with no velocity (`powerplant.validate`).

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
| `portsmouth` / `wwii` | UK | Admiralty disruptive camouflage in Western Approaches white, pale blue and green over hull, upperworks and decks (`dazzle_decks`), light Admiralty grey, pale holystoned teak, white boats, black funnel tops, straight-sided turrets with a round rear, a fuller bow, bridges with round fronts and square backs. Merchants: tramp colours, buff funnel with a black top |
| `kiel` / `wwii` | Germany | Bismarck as she sailed in May 1941: the Baltic scheme's black and white stripes on the hull sides only (`dazzle_upperworks: 0`), teak decks, grey turret roofs, a dark hull under light grey upperworks, grey funnel caps, faceted turrets with domed cupolas, a flared Atlantic bow, chamfered superstructure, capped funnels, pole masts. Merchants: dark hull, black funnel with a red band |
| `la_spezia` / `wwii` | Italy | light grey under dark grey and blue-grey dazzle panels, red and white recognition chevrons on the forecastle and quarterdeck, long wedge-faced "lancia" turrets, round-fronted tower bridges, raked funnels with "frying pan" caps. Merchants: black hull, white house, white funnel with a red band |
| `la_spezia` / other eras | Italy | `victorian`: black and white, the guns under white hoods on open barbettes, big single tops. `great_war`: light grey, white teak, pole masts. `treaty`: the palest grey afloat, awnings aft. `cold_war`: light haze grey, lattice masts, pennant numbers |
| `toulon` / `wwii` | France | dark blue-grey, decks painted gris bleu (the French mark in every era but the Victorian), wide split "quadruple" turrets with red and yellow roof bands (1940–42), funnels raked far aft like a mack, very round-fronted upperworks. Merchants: black hull, white house, red funnel with a black top |
| `toulon` / other eras | France | `victorian` "floating hotels": black hull in a broad tumblehome under ochre upperworks, mushroom-roofed "champignon" drum turrets, three-tier military tops, awnings aft. `great_war`: gris bleu, teak, a little tumblehome. `treaty`: light blue-grey, tripods, awnings. `cold_war`: deep blue-grey, broad black funnel "hats", lattice masts, pennant numbers |
| every navy / `great_war` | 1904–1920 | each navy owns one deck colour, which is most of the sprite from above, plus one signature. `generic` mid teak. `portsmouth` dark weathered teak under three-colour dazzle carried across the decks, black and white turret-roof bands. `brooklyn` pale cool teak, light blue-grey, big cage masts. `kure` red-brown decks, dark green-grey, white funnel bands, two-tier tops. `kiel` dark deck under light grey upperworks. `la_spezia` cream teak with red and white chevrons on the forecastle. `toulon` decks painted gris bleu, blue-grey all over, tumblehome. `lookgrid.py` sheets compare them |
| every navy / `treaty` | 1920–1936 | a deck colour each plus a signature. `generic` mid teak. `portsmouth` Mediterranean grey, teak holystoned nearly white, red, white and blue turret-roof bands (the 1936–39 Spanish neutrality patrol). `kiel` dark grey decks under light grey, black, white and red turret bands. `brooklyn` darker navy grey, honey teak, white hull numbers on the foredeck, cage masts. `kure` chocolate linoleum with brass seams, early pagodas. `la_spezia` cream teak, bow chevrons, awnings. `toulon` lighter gris-bleu painted decks, awnings |
| every navy / `cold_war` | 1950–1970 | muted on purpose (user: the flashy early looks have faded): a quiet deck tone each, on steel and teak. `generic` haze grey, dark non-skid, mid teak. `brooklyn` faintly blue non-skid, weathered grey teak, white foredeck numbers. `kure` muted brown non-skid, red-brown teak. `portsmouth` green-grey non-skid, pale teak, broad black funnel tops. `kiel` light steel, silver teak. `la_spezia` warm grey non-skid, cream teak, numbers. `toulon` blue-grey decks, black funnel hats, numbers |
| `generic` / `victorian` | the 1890s, any navy | black hull, white upperworks, buff funnels and masts with black tops, holystoned teak (dark corticene on steel decks), black drum turrets with sighting hoods, pole masts with round fighting tops, a full beamy bow. Merchants: black hull, varnished teak deckhouses, red funnel with a black top. Torpedo craft: all black |

- Each look is a palette for all styles, plus overrides per style, plus a turret drawing (`shipgen.look_turret_body`) and silhouette `shapes` (also overridable per style).
- Only armoured (`bb`) turrets change shape. The drawn outline stays close to the hitbox shape, and `verify.py` checks it like any other sprite.
- Silhouettes (`shapes` in a look) are drawn only: the bow and stern may be fuller than the layout's hull (never finer, so nothing at the deck edge overhangs), and funnels, superstructure corners and masts change style. Hitboxes keep the layout's shapes. The height map follows the drawn hull, so shadows match the sprite.
- **Painted features** (shapes keys, any navy may use them): `dazzle` (panels in the palette's `camo` colours over the hull band, superstructure and funnels, a repeatable pattern per design id; `dazzle_decks`, an opacity 0–1, carries them across the open decks too, under the plank lines; `dazzle_upperworks`, 0–1, default 1, sets them on the superstructure and funnels, so 0 keeps them on the hull sides), `deck_stripes` (recognition stripes on the open foredeck and optionally the quarterdeck, chevron or diagonal), `turret_bands` (bands across armoured turret roofs), `awnings` (canvas over the open quarterdeck) and `hull_number`. Silhouette extras: `tumblehome` (the hull drawn wider than the deck), `funnel_rake`, `funnel_cap` (`pan` or `hat`), `blocks: "tower"` and `mast: "lattice"`. The features that paint the deck keep clear of turrets, superstructure and funnels (`shipgen.open_ends`), and skip flight decks.
- A design's own `"palette"` still overrides everything.
- **Muting by era** (`looks.ERA_MUTE`): the looks quieten over time, from the Great War (the wildest after the Victorian liveries) to the Cold War (muted by hand). One number per era, `great_war` 0.12, `treaty` 0.27, `wwii` 0.43 (`victorian` and `cold_war` 0), takes that share of the saturation from the paint (decks, turret roofs, funnels), half of it from the hull, upperworks and teak, pulls markings (stripes, camouflage, numbers, turret bands) that far toward the upperworks grey, and fades painted decks. Every navy keeps its hue and lightness. It applies to naval styles; merchants keep their liveries but their camouflage is muted. Raise or lower an era's number to tune it.
- **Comparing navies** (`lookgrid.py`): `python lookgrid.py designs/a.json designs/b.json ... --era great_war --out DIR` builds each design once and draws it in every navy's look for that era. It writes one sheet per navy (`<navy>.png`, every design at the same scale in a grid) and `compare.png` (one row per design, one column per navy, smaller), the quick way to see looks that are too alike. Options: `--navies`, `--scale`, `--cols`, `--compare-scale`, `--jobs`. `--falloff` instead draws each design in every navy (rows) and every era (columns), `falloff_<id>.png`, to judge the muting.
- To add a look: add an era entry under a navy in `looks.NAVIES` (a new navy goes in `NAVIES`, a new era also in `ERAS`). A new turret drawing also needs a branch in `shipgen.look_turret_body`.
- **Clutter** (`clutter.py`, drawing only): the gear on open roofs and decks, by era. The shapes key `clutter` names a kit (`victorian`, `great_war`, `treaty`, `wwii`, `cold_war`) and defaults to the look's era; `None` turns it off. Victorian: cowl vents, skylights, nested boats on the boat deck, coal scuttles along the sides, planked boat-deck roofs. Great War: steam pinnaces, searchlights, paravanes. Treaty: mushroom vents, motor launches, the first Carley floats. WWII: ready-use lockers, Carley floats, vent trunks, depth-charge racks on ships under 140 m, few boats. Cold War: liferaft canisters, vent housings, one pair of motor whaleboats. Counts are per 100 m² of open surface; on a roof above 600 m² they grow with the square root of its area, the rest of the area goes to the kit's big gear (boiler-room cowls and fan houses by the funnels, engine-room skylights, searchlight platforms), which also takes room from the small gear; roofs at level 3 and up get 0.6 of the count. Every open roof gets a guardrail. Knobs: `clutter_density` (1), `roof_planks` (smallest planked roof in m², 0 = steel) and `roof_rails`. Placement is seeded by the design id and kit, keeps off higher blocks, funnels, masts, turrets, AA and deck breaks, and pairs items across the centreline. Each item also adds a low column to the height map, so it casts a shadow. Hitboxes, `sprite.json` and the report never change. The hand-authored fleet (`shipgen.py`) uses no look, so it keeps the old level-1 vents.
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
  - `vertical`: `keel`, `waterline` and `armour_deck` (the main armour deck, null on a ship without deck armour) on that height scale, plus `draught`, `depth` and `freeboard` (full load). `raised` (when there are any) lists the raised stretches of hull: `id`, `x0`, `x1` and the `top` of their deck. Their decks are in `decks` (`kind` "raised", deck numbers −1, −2, …, with the `spans` where each exists), and their tiers only exist over those spans.
  - `hull`: the hull outline polygon: the main deck's edge, the widest the hull gets.
  - `hydrostatics` (`hitbox.hydrostatics`): the full-load numbers a game needs to settle a flooded ship by added weight. A flood of w tonnes at (x, y) sinks the ship w / (100 `tpc_t`) m, trims it w (x − `lcf`) / `mct_tm` cm (+ by the bow) and heels it w y / (Δ′ GM′) rad. Keys: `displacement_t`, `volume_m3`, `waterplane_m2` and `lcf` (the waterplane's centre, from `hull_form`), `lcg`, `lcb`, `kg` and `kb` (above the main deck), `gm_t` (the report's GM), `gm_l`, `i_t_m4`, `i_l_m4`, `tpc_t` (t per cm of sinkage) and `mct_tm` (t·m per cm of trim). `sinking.py` shows them in use.
  - `hull_form`: the hull's cross-sections (`geometry.HullForm`). The underwater body holds exactly the displacement volume (Cb × L × B × T). Above the waterline the side flares straight out to the deck edge.
    - Under the waterline each section has a flat floor where it's full and a vee or hollow at the fine ends. Toward the ends it takes a U or V character: forward from the speed (a U near Fn 0.23, a V either side), aft from the screws (a U into a single screw, a flat-floored run over several). Planing craft have a hard chine.
    - The keel isn't flat to the ends: a rounded forefoot (longer on fast ships, a long rocker on planing craft). Aft, a single screw keeps the keel to the sternpost at the rudder and has the counter above water abaft it; several screws get a cut-up, so the propellers and rudders hang under the hull bottom, rising on smoothly to the stern (a wide transom stays immersed, a narrow cruiser stern fades out at the waterline).
    - `stations`: sections from stern to bow (denser at the ends), each `{x, z: [heights], y: [half-breadths]}`, from the section's keel (its first height; nothing of the hull is below it) up to the main deck with the waterline among them. A station abaft a sternpost starts at the waterline. Interpolate between them (`geometry.table_half_width`). Above the main deck, the deck outline holds.
    - Along the length the sectional area curve comes first: a parallel midbody from the prismatic coefficient (a third of the length on a tanker, none on warships), then entrance and run out to the ends, centred on the ship's centre of buoyancy (`report.json` `lcb_m`). Each station meets its area with its waterline (inside the deck edge) and its section's fullness together.
    - `midship_coefficient` and `waterplane_coefficient`. The waterplane aims for `navarch.cwp(Cb)`, but the section always takes part of the fining, so warships come out at about 0.70–0.73, fuller than that formula; merchants meet it.
  - `armour`: present only for the armour the ship has (`navarch.armour_geometry`, the same geometry its weights come from). Every armour piece carries `material`, the design's `armour.materials` string, when the design names one. The same goes for armoured components (turrets, barbettes, the conning tower, armoured casings, an armoured flight deck with its `armour_mm`) and for deck `plates`. Armoured transverse bulkheads carry `armour_material`; cells carry `belt_material` and `armour_above_material` (parallel to `armour_above_mm`).
    - `belt`: `thickness_mm`, `x0`/`x1` (the citadel), `bottom`/`top`. A tapered belt adds `bottom_mm` (at `bottom`) and `taper_from` (the waterline, where the taper starts). From below the waterline up to the main armour deck, or centred on the waterline if that deck is lower.
    - `decks`: the armour decks, top down: `deck` (its id, such as `Second deck`), `thickness_mm`, `extent`, `x0`/`x1`, `z`, and the flags `main` (the main armour deck) and `roof` (the lowest, over the vital spaces).
    - `strakes`: the side armour other than the main belt (`armour.upper_belt`, `armour.end_belts` and `armour.steering_box`), each with `id`, `kind` (`upper` | `end` | `box`), `extent` (`citadel` | `fore` | `aft`), `thickness_mm` (at the citadel end), `tip_mm` (at its far end, only when it tapers), `x0`/`x1` and `bottom`/`top`.
    - `bulkheads`: the armoured transverse bulkheads: `id`, `x`, `thickness_mm`, `bottom`/`top`. These are the citadel's forward and aft ends, an end belt's closing bulkhead (`Fore end belt bulkhead`), and the steering box's two ends.
    - The steering box's roof is a deck plate with `extent` `steering`.
  - `components`:
    - Turrets: `local` body/parts/barrels polygons (rotate them by the turret angle, then add x, y), `broadphase_r`, `arcs_deg`, `traverse_deg`, `rest_deg`, base/top heights.
      - `armour_mm` is the face. `armour` splits it into `face`/`side`/`rear`/`roof` (`hitbox.TURRET_*` ratios).
      - Gun mounts link to their `barbette` (a component) and their `magazine` (a room). The barbette links back with `mount` and reaches down to the main armour deck (the belt top without deck armour, the second deck on an unarmoured ship). A mount on a sponson or a flight deck has only a 1 m pedestal on its platform.
    - Superstructure: polygons with heights and a `role`: `bridge`, `director`, `aft_control`, `island`, `hangar`, `casemate` or `deckhouse` (`hitbox.BLOCK_ROLES`). A control position in a funnel's smoke lists those funnels in `smoke`. Rounded-rectangle blocks also give their parameters in `rrect`. Blocks with their own outline (the warship's superstructure levels, bevelled, and the directors: hood and rangefinder arms, or a round tub) give only `points`.
    - Funnels: polygons with heights. `boiler_rooms` lists the rooms each one serves. An `uptake` component runs from the top of the boilers up to the funnel's base, with the same footprint and links.
    - `casing`: over machinery taller than its space, from the bounding deck up, with `armour_mm`.
    - `conning_tower`: a circle inside the bridge's front on warships with a belt, armoured like the belt. It isn't drawn.
    - **The propulsion train** (`propulsion.py`). Nothing in it is weighed: the plant's weight includes its shafting, and the hull's includes the rudders. All of it is underwater, so the sprite doesn't show it.
      - `shaft` (`shape` `segment`): a straight line from `p0` (its engine room, just over the inner bottom) to `p1` (its propeller), each `[x, y, z]`, with radius `r`. `points` is its plan, for a broad phase. It carries `position` (`centre` | `wing` | `inner` | `outer`), `engine_room`, `propeller`, `alley` (when it has one) and `leaves_hull_x`, where it leaves the hull (`hull_form`). Abaft that x a wing shaft runs in the open on its brackets. The outer shafts come from the forward engine rooms, the inner ones and the centre shaft from the aft ones. Shafts sit at 0.28 B × k / pairs either side.
      - `shaft_alley`: the watertight tunnel round a shaft, from the machinery's aft end to where the shaft leaves the hull, with its `shaft`. A shaft that leaves inside the machinery (engines aft) has none.
      - `propeller` (`shape` `disc`): centre `x`, `y`, `z` and `diameter_m`, about the x axis; `points`/`base`/`top` bound it. Each sits just ahead of the rudders, each pair further out 0.05 L further forward. The diameter grows with the power per shaft (1.2 × MW^0.4 m) and is capped at 0.75 × draught. Planing craft hang smaller ones under the hull bottom.
      - `rudder`: a thin blade under the steering gear, with its `steering` room, `x`/`y` (the stock) and `area_m2` (1.7% of L × T in all). `machinery.rudders` sets the count.
      - Links back: an engine room lists its `shafts` and the steering gear room its `rudders`. A cell a shaft or alley passes through lists them in `through`.
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
      - Extent: `x0`/`x1`, `y0`/`y1` (out to the hull's widest point over the section at the cell's top, so clip to `hull_form`) and `base`/`top`. Low cells are narrower than high ones, and a wing cell exists only where the hull reaches past its bulkhead.
      - `volume_m3` is the hull's cross-sections inside the box, sampled in slices. The part below the waterline is scaled so the underwater parts add up to the displacement volume exactly (a correction of under 1%).
      - `permeability` comes from the room's kind (`subdivision.PERMEABILITY`; a full coal bunker is 0.4), and `below_waterline` is set from the tier (the whole cell is under water).
      - The owning `room`, and `also`: the rooms that share this cell because they're too small for one of their own.
      - Armour and protection: `citadel`, `armour_above_mm` (the armour decks above the cell, top down, as a list of thicknesses), `belt_mm` (an outer cell level with side armour: the thickest belt or strake beside it, at the cell's middle along a tapered end belt and at the top of its overlap down a tapered main belt) and `tds_m` (a wing cell inside the citadel: the depth from the shell to the torpedo bulkhead at the cell's middle height. It is `armour.tds_m` at the waterline, where the bulkhead is set, and less toward the bilge as the hull narrows, down to 0).
      - `crew`: the complement spread over the quarters by volume.
      - `neighbours`: `[cell id, boundary]` pairs. The boundary is the bulkhead or deck id between them, or `"open"` inside one room.
      - `through`: the shafts and shaft alleys that pass through the cell (when any).
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
- `hull.png` (everything that doesn't rotate) and `turrets/*.png`, each with an SVG alongside. Level 0 is `--scale` px/m (default 10). No shadows are baked in.
- `height.png`: greyscale height map on the same canvas. Grey × `height_step_m` (0.25) = metres above the waterline, and 0 = sea. Its mips use a 2×2 max filter, not an average, so a tall column never shrinks.
- `<layer>_mips.png` sits next to each layer PNG (`hull`, `height`, `turrets/<type>`) and packs level 0 plus every lower level into one image of 1.5W × H. Level 0 is on the left. Level 1 sits to its right at the top, and each next level goes alternately below and to the right of the previous one.
  - The exact `[x, y, w, h]` of every level is in `sprite.json`: `mip_rects` for the hull-sized layers, and `turret_types.<type>.mip_rects` for the turrets.
  - Each level is half the one before, made with a 2×2 box filter on premultiplied alpha. `--mips N` sets the count. Every canvas is a multiple of 2^(N+1) px, so each level halves exactly.
  - Within level k, sizes, `origin_px`, `pivot_px` and mount `px` are the level-0 values / 2^k.
  - The levels touch each other with no gap. Slice them into real GPU mip levels, or clamp UVs to each rect if you sample the packed image directly.
- `preview_*.png`, `sheet.png`: stats, firing-arc diagram and previews, shadowed with the sun at bearing 240°, elevation 50°. `debug_hitboxes.png`: hitboxes drawn over the sprite.
- `hitbox_bow.png`, `hitbox_quarter.png`, `hitbox_side.png`, `hitbox_internal.png` (`hitview.py`, debug only): the hitbox model in 3D, with every hitbox extruded from its base to its top.
  - Views: from the starboard bow, the port quarter, a side elevation, and an internal view that shows only rooms (less the quarters, stores, double bottom and torpedo protection that fill the rest), barbettes, uptakes and armour inside the hull's edges.
  - `hitbox_cells.png`: every tier of the subdivision in plan, keel tier at the bottom, with cells coloured by their room's kind. Labels give the section, `+` for a shared cell, and the crew.
  - The hull is translucent and the waterline is drawn in blue. Colours are by kind, with a legend.

## Sinking demo (sinking.py)
`python sinking.py out_designs/battleship [--scenario stern|bow|starboard|port|all] [--hole M2] [--leak K]` writes `sinking/sink_<scenario>.gif` and `sinking_sheet.png` (six frames per scenario) in the export directory. It reads only `hitboxes.json`, `sprite.json` and the sprite images, so it is a sketch of what the game can do with them.
- **Breaches:** `stern` and `bow` hole every cell under the waterline in that quarter of the length; `starboard` and `port` hole the outer cells within 0.06 L of amidships (a torpedo). `--hole` is the total hole area (default 0.1 √Δ m²).
- **Flooding:** a holed cell fills through its hole (Q = 0.6 A √(2 g head)), and a main-deck cell through its hatches once the sea is over the deck there. Water falls through decks and levels out inside a room. Bulkheads and the inner bottom only leak (`LEAK`, scaled by `--leak`), which is what carries the flooding on from section to section. A full cell open to the sea lets it on up into the cell over it.
- **Attitude:** added weight with the exported `hydrostatics`. Heel comes from the wall-sided GZ curve with GM corrected for the water's height and the free surface of partly filled cells (weighted 4f(1 − f)), so a negative GM gives a loll.
- **The end:** the ship founders when a third of its deck is awash (a plunge by the lower end, or settling level) or heels 8° past its deck edge (capsize). That part is a canned animation, because the small-angle model doesn't hold there.
- **Drawing:** each sprite pixel becomes a point at its height-map height (turrets at their roof), plus the hull bottom from `hull_form` and walls down every height step. The points are rolled, pitched and sunk, then shaded by depth, with foam at the surface.
- **What it shows about the designs:** ships with wing bulkheads (`tds`, coal wing bunkers) list toward a side hit and can capsize. A hull with only centre cells settles level, because nothing holds the water to one side; that historically favoured centre-only hulls. Added weight ignores what a cell held: an oil-laden tanker's flooded tank counts as an empty one filling, so the tanker sinks in minutes.

## Style videos (vidgen/)
`vidgen/vidgen.py` makes a short MP4 of one exported ship, to judge how the sprites look in motion. It reads only
`out_designs/<id>/`, as the game would, and changes nothing there. Needs `pip install imageio-ffmpeg` (it bundles
an ffmpeg binary) besides numpy and pillow.
- The camera looks straight down and follows the ship at its design speed (`inputs.speed_kn`). The ship is scaled
  to fit the frame (never above the sprites' own 10 px/m). Procedural water, a bow wave that spreads into Kelvin
  arms, stern wash, and funnel smoke on the wind (darker on coal).
- Timeline: weapons at rest, then every mount whose arcs hold the target bearing (`--target`, relative to the
  bow) trains on it, moving only inside its `traverse_deg`. Then they fire: main guns in salvos, secondaries on their
  own beat, torpedo mounts once. Muzzle points come from the barrel polygons in `hitboxes.json`. Mounts that can't
  bear stay at rest.
- Shadows as README "Shadows": `shadow.shadow_mask` on the height map, and turret sprites in black, offset by
  `(top_m - deck_m) / tan(elevation)` and kept where the height map is below `top_m`. Smoke casts a soft shadow.
- `vidgen.py all`, `--jobs N` (default one ship per core), `--size 1920x1080`, `--heading`, `--target`, `--seconds`, `--seed`, `--crf`; `--still T` writes
  one PNG at time T instead. About 0.35 s a frame at 720p, so a 14 s clip takes 2–3 minutes. Videos go to
  `vidgen/out/` (git-ignored).

## Conventions
- Bow → +x. Angles run clockwise from dead ahead (90 = starboard). Arcs are `[start, end]` intervals, clockwise; `end` may exceed 360.
- Firing arcs are fixed by mount kind, centred on the rest bearing (`hitbox.ARC_*`):
  - Centreline guns of a forward or aft group, including superfiring and carrier island-line guns: ±135°.
  - Centreline guns with a turret ahead of them (amidships turrets, flush turrets behind a superfiring one): ±65° about each beam. They stow fore-and-aft like real ships, pointing away from the nearest other centreline turret. Their rest bearing is therefore outside their arcs: train them out before firing. Every other mount rests inside its arcs.
  - Side mounts (secondaries, sponson guns, side torpedo mounts, wing turrets): ±90°, bow to stern on their own side. Wing turrets rest fore-and-aft, at the edge of that arc. Cross-deck wing turrets (`main.cross_deck`) have a second arc, ±30° about the far beam, listed after their own side's.
  - Casemate guns: ±60° about their beam (`ARC_CASEMATE`), resting abeam.
  - Centreline torpedo mounts: ±60° about each beam.
  - Fixed tubes: ±1° about their bearing.
- **Traverse** (`traverse_deg` on every mount in `hitboxes.json` and `sprite.json`; `hitbox.mount_traverse`): the one interval `[start, end]` the mount turns within, holding its rest bearing and all its arcs, always under a full turn. The game trains a mount by moving its bearing inside that interval, never wrapping past either end, so it never swings its barrels through the bridge, a superfiring turret's blind arc or a cross-deck partner. With one arc it is the arc (a superfiring A: `[225, 495]`, never through astern). Side-firing centreline turrets and centreline torpedo mounts go from one beam arc to the other through their rest bearing, away from the turret ahead (Nelson's X stowed aft: `[25, 335]`). Cross-deck wing turrets go from their own side through the end they stow toward to the cross-deck arc (Invincible's W1P: `[180, 480]`). Fixed tubes get their ±1°.
  - Nothing on deck limits an arc. Instead, the warship layout places the main turrets first, and each reserves its sweep zone: a sector as long as its barrels, covering exactly its `traverse_deg`. Everything placed afterwards that stands taller than that turret's guns keeps out of the zone: bridge, aft control, funnels, masts, deckhouse, boats, secondaries, torpedo mounts and AA. The bridge and aft control step back, the deckhouse ends are trimmed and shaped (it keeps out of the end turrets' sweeps at any height), and the space needed is budgeted up front (a stowed turret's barrels, and the gap a side-firing turret needs beside its neighbours).
- Draw order: hull, then the turrets by ascending z. A mount's z is its rank by base height, main guns over secondaries over the rest at equal height (`layout.draw_order`), so a turret's barrels pass over the lower mounts they swing across, as the hitboxes have it. Turret pivot = image centre. Turrets draw over the whole hull: anything taller than a turret's guns keeps out of its sweep, so a turret rarely overlaps taller structure, and where it does (a mast's legs) it wins. Inside `hull.png`, roof items (`layer: "upper"`: level 2+ blocks, AA on roofs, boats) draw after level 1, and funnels, masts and cranes last.
- Pixel position = origin_px + metres × scale. Canvases are multiples of 2^(mips+1) px, so the origin falls exactly on a pixel at every mip level.

## Shadows
The sun is dynamic, so the game casts the shadows. `shadow.py`'s docstring has the details, and `shadow_mask()` there is a numpy reference implementation to port.
- Static structure: in a shader, march from each pixel toward the sun across `height.png`. A pixel is in shadow if `H(p + t·d) > H(p) + t·tan(elevation)` for some t > 0. `d` is the sun direction in ship-local space (sun bearing minus ship heading). The receiver's own height H(p) makes the result correct for sea, deck and roofs alike. Draw the shadow quad larger than the sprite by `max_height_m / tan(elevation)` and sample with a border of 0.
- Turrets aren't in the height map because they rotate. Draw each turret sprite in black after the hull and before the turrets. Rotate it with the turret and offset it away from the sun by `(top_m − deck_m) / tan(elevation)`, and keep it only where `H(p) < top_m` (a turret's shadow doesn't climb a funnel or a tower taller than its roof; `shadow.below_mask`).
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
