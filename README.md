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
   ├─ layout.py    warship layout + shared layout primitives; balances CG over CB by shifting the arrangement
   ├─ armament.py  style-neutral gun, torpedo and AA placement (used by carrier and merchant)
   └─ hitbox.py    fixed firing arcs by mount kind; hitbox export
   │
   │  ship = {design, report, hitboxes, render: {spec, deck_m, mounts, columns, summary}}
   ▼  RENDER SIDE: reads only `ship`                           (~0.5 s game assets, ~3 s with previews)
   render.py      render_ship(ship, out_dir, scale, mips, look=None, previews=True)
   ├─ looks.py     every colour, turret drawing and silhouette (by the design's "look")
   ├─ shipgen.py   SVG/PNG drawing (hull_base, turrets, hull_upper)
   └─ shadow.py    rasterises the height-map columns; the reference shadow renderer

   geometry.py   shared by both: hull form, turret polygons (sprite AND hitbox), AA sizes, arc helpers
design.py      the command line: validate, shipdesign.build, write report.json and hitboxes.json, render
```
- Use the design side alone (a game's designer UI): `ship = shipdesign.build(design)` gives the report and hitboxes
  in about 5–170 ms (sizing the hull is most of it). After a small change, pass the previous result's length,
  `shipdesign.build(design, hint=ship["report"]["results"]["length_m"])`, to make it about twice as fast with the
  same result. `render.render_ship(ship, ...)` can run later, elsewhere, or from the same dict loaded `render.render_ship(ship, ...)` can run later, elsewhere, or from the same dict loaded
  from JSON.
- The rules that keep the halves apart: nothing on the design side imports the renderer, PIL, cairosvg or numpy;
  the renderer imports no design-side module (only `geometry` and `looks`); and the renderer reads nothing but
  the `ship` dict. `shipdesign.py`'s docstring documents that dict.

## Design input
```json
{
  "id": "battleship", "name": "Fast Battleship", "type": "BB", "look": "standard",
  "hull": {"block_coefficient": 0.59},
  "speed_kn": 33, "range_nm": 15000,
  "armour": {"belt_mm": 307, "deck_mm": 152, "turret_mm": 432},
  "main": {"calibre_mm": 406, "calibre_length": 50, "barrels": 3, "fore": 2, "aft": 1},
  "secondary": {"calibre_mm": 127, "calibre_length": 38, "barrels": 2, "per_side": 5},
  "torpedoes": {"mounts": 0, "tubes": 5},
  "aa": {"heavy": 20, "light": 30},
  "machinery": {"stress": 0.4, "shafts": 4, "tech": {...}},
  "funnels": null
}
```
`machinery` is the propulsion plant (`powerplant.py`, from `research/powerplant-model.md`). There is no year input: `tech` holds the researched technology as numbers, so a navy can have a tech earlier or later than history did. `plant-templates.md` has blocks to copy for every period from 1880 to 1970, and `python plant_templates.py` regenerates them. A design without `tech` gets a 1940 high-pressure turbine plant (merchants: a 1940 oil-fired triple expansion; planing craft: 1940 petrol engines). The other keys are design choices: `stress`, `shafts`, `units_per_shaft`, `transmission`, `arrangement` (`grouped` or alternating `unit`), `centreline_bulkhead`, `bunkers` (`wing` or `ends`) and `wing_bunker_m`. The template's table explains each one. What the plant decides:
- **Weight, fuel and engineering crew:** from the tech and the stress. Range is computed at cruise speed through the tech's part-load curve.
- **Machinery length:** the plant's volume, fitted into the room the hull gives it. Across, that's the beam inside the frames, less torpedo protection (`armour.tds_m` per side) and wing bunkers, with units standing in rows. Up, it's the inner bottom to the armour deck.
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
- `"casemate"`: single guns at the hull side. Only a round port shield and the barrels show, outboard. Casemates stay where the hull is at least 85% of its full beam (`layout.CASEMATE_BEAM`). Two tiers, set by `"tier"`:
  - `"lower"` (the default): in the hull side, one level below the main deck (base −2.6 m, top 0). They keep clear of the main barbettes and of each other.
  - `"upper"`: on the main deck (base 0, top 2.6 m), each in an armoured housing against the deck edge (a level-1 superstructure block). Housings close together join into one gallery. They keep clear of whatever stands on the main deck and of the main turrets' sweeps. The tiers stagger, so the upper guns stand between the lower ones and every gun shows.
  - Placement: the lower tier fills first, then the upper. Within a tier, each battery takes the free places nearest amidships in list order, so list the battery you want amidships first. The rows centre on the hull's full-width part and move with the balancing shift.
  - Spacing: a comfortable pitch if every gun fits that way. Failing that, the lower guns sit just far enough apart for one upper gun between each pair. Failing that too, closer still.
- Battery mount ids are `S1S`/`S1P`, ... for the first battery, then `SB...`, `SC...`. Casemate guns carry `"mount": "casemate"` in `hitboxes.json` and `sprite.json`.
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
- **carrier**: `"aviation": {"flight_deck": "axial" | "angled" | "none", "aircraft": 90, "aircraft_t": 6, "hangar_decks": 1, "elevators": 2, "deck_edge_elevators": 1, "catapults": 2, "cranes": 0, "number": "9"}`.
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
- To add a style: subclass `styles.base.Style` in a new module, give it a `build_layout` (and whichever weight and report hooks it needs), and register it in `styles.STYLES`. The shared building blocks are `layout.add_block`, `Layout.decks` and `Layout.sponsons`, and the `armament` helpers.

## Looks
`"look"` sets how the ship is painted and drawn, as a navy of a given nation might build it. It's purely visual: the layout, physics, report results, hitboxes and sprite sizes are identical in every look, so two ships that differ only in look play the same. A look applies to every style (warship, carrier, merchant, planing).

| look | inspired by | what changes |
|---|---|---|
| `standard` (default) | generic | WWII haze grey, teak decks |
| `brooklyn` | US | deck blue on every horizontal surface, slab-sided boxy turrets with rear rangefinder hoods, a wide square transom, boxy funnels and superstructure. Merchants: wartime grey |
| `kure` | Japan | dark Kure grey, pale hinoki wood, brown linoleum steel decks with brass strips, black-topped funnels, rounded turrets with a long rangefinder across the rear, a flared bow, oval funnels, soft rounded superstructure, wooden carrier decks with red stripes. Merchants: black hull, white house |
| `portsmouth` | UK | light Admiralty grey, pale holystoned teak, white boats, black funnel tops, straight-sided turrets with a round rear, a fuller bow, bridges with round fronts and square backs. Merchants: tramp colours, buff funnel with a black top |
| `kiel` | Germany | dark hull and steel decks under light grey upperworks, mid teak, grey funnel caps, faceted turrets with domed cupolas, a flared Atlantic bow, chamfered superstructure, capped funnels, pole masts. Merchants: dark hull, black funnel with a red band |
| `victorian` | the 1890s, any navy | black hull, white upperworks, buff funnels and masts with black tops, holystoned teak (dark corticene on steel decks), black drum turrets with sighting hoods, pole masts with round fighting tops, a full beamy bow. Merchants: black hull, varnished teak deckhouses, red funnel with a black top. Torpedo craft: all black |

- Looks live in `looks.py`. Each is a palette for all styles, plus overrides per style, plus a turret drawing (`shipgen.look_turret_body`) and silhouette `shapes` (also overridable per style).
- Only armoured (`bb`) turrets change shape. The drawn outline stays close to the hitbox shape, and `verify.py` checks it like any other sprite.
- Silhouettes (`shapes` in a look) are drawn only: the bow and stern may be fuller than the layout's hull (never finer, so nothing at the deck edge overhangs), and funnels, superstructure corners and masts change style. Hitboxes keep the layout's shapes. The height map follows the drawn hull, so shadows match the sprite.
- A design's own `"palette"` still overrides everything.
- To add a look: add an entry to `looks.LOOKS`. A new turret drawing also needs a branch in `shipgen.look_turret_body`.

## Outputs (out_designs/<id>/)
- `report.json`: valid flag, errors, warnings, the hull's length, beam and block coefficient, displacement (std/full), draught, power, fuel, crew, GM, trim, and the weight list with x/z. Carriers add aircraft and capacity, flight deck size and height; merchants add cargo, deadweight and hold count.
  - `plant`: the plant's static numbers for the game (`powerplant.published`), and how it sits in the hull:
    - power: rated and continuous kW, overload headroom, shafts and units
    - fuel: fuel rate and the part-load curve
    - draught system and engineering crew
    - its space: machinery length, boiler and engine rooms, rows, protrusion, bunkers
    - funnels: count, gas area and velocity, and smoke reach
- `hitboxes.json`: all values in metres, ship-local (origin = sprite centre, +x bow, +y starboard). It describes the ship for the game's damage model (where things are, what armours them, what links to what), never what a hit does.
  - Heights (`base`/`top`/`z`) are metres above the main deck, negative below it. On a carrier the main deck is the hangar deck.
  - `vertical`: `keel`, `waterline` and `armour_deck` (null on a ship without belt or deck armour) on that height scale, plus `draught`, `depth` and `freeboard` (full load).
  - `hull`: the hull outline polygon.
  - `armour`: present only for the armour the ship has (`navarch.armour_geometry`, the same geometry its weights come from).
    - `belt`: `thickness_mm`, `x0`/`x1` (the citadel), `bottom`/`top`. Centred on the waterline.
    - `deck`: `thickness_mm`, `x0`/`x1`, `z`. It sits on top of the belt (2.5 m below the main deck on a ship without one).
    - `bulkheads`: the citadel's forward and aft ends: `x`, `thickness_mm`, `bottom`/`top`.
  - `components`:
    - Turrets: `local` body/parts/barrels polygons (rotate them by the turret angle, then add x, y), `broadphase_r`, `arcs_deg`, `rest_deg`, base/top heights.
      - `armour_mm` is the face. `armour` splits it into `face`/`side`/`rear`/`roof` (`hitbox.TURRET_*` ratios).
      - Gun mounts link to their `barbette` (a component) and their `magazine` (a compartment). The barbette links back with `mount` and reaches down to the armour deck.
    - Superstructure: polygons with heights and a `role`: `bridge`, `director`, `aft_control`, `island`, `hangar`, `casemate` or `deckhouse` (`hitbox.BLOCK_ROLES`). A control position in a funnel's smoke lists those funnels in `smoke`.
    - Funnels: polygons with heights. `boiler_rooms` lists the rooms each one serves. An `uptake` component runs from the top of the boilers up to the funnel's base, with the same footprint and links.
    - `casing`: over machinery taller than its space, from the bounding deck up, with `armour_mm`.
    - `conning_tower`: a circle inside the bridge's front on warships with a belt, armoured like the belt. It isn't drawn.
    - Decks: `flight_deck`, and `deck` for raised forecastles, bridge decks and poops. `sponson`: gun and AA platforms, and deck-edge elevators. All are polygons with heights.
    - AA: circles.
  - `compartments`: boxes `x0`/`x1`, `half_width` about `y` (0 if absent), `base`/`top`. They reach from the keel up to the armour deck, or the main deck on an unarmoured ship. Kinds:
    - All ships: the machinery as `boiler_room`, `engine_room` and `bunker` (`fuel` is coal, oil, diesel or petrol), and steering gear (`steering`).
      - Rooms are no longer than about 0.07 L.
      - Wing bunkers stand beside the machinery from the inner bottom to the main deck, and give their `tonnes`.
      - Planing craft have a single `engine_room`.
    - Warships and carriers: citadel (belt/deck mm).
    - Warships: one `magazine` per gun mount (`mount` links back). An off-centre mount's magazine stays inside the inner hull on its own side.
    - Planing craft: crew space and fuel tanks.
    - Carriers: hangar (above the hangar deck), aviation magazines and aviation fuel.
    - Merchants: `hold` or `cargo_tank` per hold.
- `sprite.json`: layers, origin_px, mount px positions, rest angles, arcs and z order.
- `hull_base.png`, `turrets/*.png`, `hull_upper.png`, each with an SVG alongside. Level 0 is `--scale` px/m (default 10). No shadows are baked in.
- `height.png`: greyscale height map on the same canvas. Grey × `height_step_m` (0.25) = metres above the waterline, and 0 = sea. Its mips use a 2×2 max filter, not an average, so a tall column never shrinks.
- `<layer>_mips.png` sits next to each layer PNG (`hull_base`, `hull_upper`, `height`, `turrets/<type>`) and packs level 0 plus every lower level into one image of 1.5W × H. Level 0 is on the left. Level 1 sits to its right at the top, and each next level goes alternately below and to the right of the previous one.
  - The exact `[x, y, w, h]` of every level is in `sprite.json`: `mip_rects` for the hull-sized layers, and `turret_types.<type>.mip_rects` for the turrets.
  - Each level is half the one before, made with a 2×2 box filter on premultiplied alpha. `--mips N` sets the count. Every canvas is a multiple of 2^(N+1) px, so each level halves exactly.
  - Within level k, sizes, `origin_px`, `pivot_px` and mount `px` are the level-0 values / 2^k.
  - The levels touch each other with no gap. Slice them into real GPU mip levels, or clamp UVs to each rect if you sample the packed image directly.
- `preview_*.png`, `sheet.png`: stats, firing-arc diagram and previews, shadowed with the sun at bearing 240°, elevation 50°. `debug_hitboxes.png`: hitboxes drawn over the sprite.

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
- `layout.py`: the clearances (bow_pref/min, st_pref/min), turret spacing, bridge size and AA spacing.
- Each style's `tuning()` overrides `TUNING` for its designs: hull weight, freeboard, outfit fraction, hull CG height, the draught limit, and so on.
- Calibration (std / full displacement, t; real values in brackets):

  | design | model | real ship |
  |---|---|---|
  | `battleship` (Iowa-like) | 47.7k std | ~45k std |
  | `heavy_cruiser` (Baltimore-like) | 13.9k std | 14.5k std |
  | `destroyer` (Fletcher-like) | 1.9k std | 2.05k std |
  | `fleet_carrier` (Essex-like) | 27.2k / 32.5k, 154k shp, crew 2,660, 90 aircraft | 27.1k / 36.4k, 150k shp, ~2,600 crew, 90–100 aircraft |
  | `supercarrier` (Forrestal-like) | 54.6k / 63.5k | 59k / 81k |
  | `escort_carrier` (Casablanca-like) | 9.1k / 10.3k | 7.8k / 10.9k |
  | `liberty` (Liberty ship) | 3.3k / 14.0k, 2,300 shp | 3.4k / 14.2k, 2,500 ihp |
  | `tanker` (T2-like) | 5.1k / 22.1k | ~5.3k / 21.9k |
  | `gangut` (Gangut-like) | 20.4k std, 38.9k shp | 23.3k normal, 42k shp |
  | `dreadnought` (HMS Dreadnought-like, 21 kn) | 17.4k std, 26.7k shp | 18.1k normal, 23k shp |
  | `nassau` (Nassau-like, 19.5 kn) | 17.1k std, 21.8k shp | 18.6k normal, 22k ihp |
  | `nassau_casemates` (casemated secondaries) | 18.3k std, 22.7k shp | 18.6k normal, 22k ihp |
  | `mikasa` (Mikasa-like, 18 kn, `steam_recip`) | 11.4k std, 12.6k shp | 15.1k normal, 15k ihp |
  | `connecticut` (Connecticut-like, no 8" turrets, `steam_recip`) | 13.8k std, 13.8k shp | 16.0k normal, 16.5k ihp |
  | `kongo` (Kongo as built, 27.5 kn) | 29.2k std, 87.2k shp | 27.5k normal, 64k shp |
  | `invincible` (Invincible-like, 25.5 kn) | 16.9k std, 48.1k shp | 17.3k normal, 41k shp |
  | `battlecruiser` (Lion-like, 28 kn) | 28.9k std, 90.6k shp | 26.3k normal; ~92k shp for 28 kn on trials |
  | `mtb` (Vosper 70 ft-like) | 35 / 44 t, 3,000 hp at 39 kn | ~47 t, 3,750 hp |
  | `pt_boat` (Elco 80 ft-like) | 60 / 72 t, 5,300 hp at 41 kn | ~46 / 56 t, 4,500 hp |

  - The tanker needs about 30% more power than a real T2: the Admiralty-coefficient power model is pessimistic for full hulls above Froude 0.18.
  - Carrier full loads run light because the range model burns less fuel at cruise than these ships actually carried.
  - The planing numbers rest on the placeholder power model; the PT boat comes out heavy.
