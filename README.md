# shipgen: parametric top-down ship designer and sprite generator

```
pip install cairosvg pillow numpy
python design.py designs/*.json            # player designs -> out_designs/<id>/ (10 px/m + 5 mip levels)
python design.py designs/x.json --no-limits # skip the input ranges; errors (capsizing etc.) never block output
python verify.py out_designs/battleship     # pixel check: sprites vs hitboxes
python shipgen.py                           # the original hand-authored fleet (fleet.py)
```

## Pipeline
```
design JSON (player input: counts, calibres, armour, speed)
   │
   ├─ styles/      the design style: warship, carrier, merchant (limits, tuning, layout, extra weights)
   ├─ navarch.py   weights → displacement, draught, power, fuel, GM, trim   (iterates to a fixed point)
   ├─ layout.py    warship layout + shared layout primitives; balances CG over CB by shifting the arrangement
   ├─ armament.py  style-neutral gun, torpedo and AA placement (used by carrier and merchant)
   ├─ hitbox.py    fixed firing arcs by mount kind; hitbox export
   ├─ geometry.py  turret polygons shared by the sprite AND the hitbox (single source of truth)
   ├─ shadow.py    height map for sun shadows + the reference shadow renderer
   └─ shipgen.py   SVG/PNG renderer (hull_base, turrets, hull_upper)
```

## Design input
```json
{
  "id": "battleship", "name": "Fast Battleship", "type": "BB",
  "hull": {"length": 262, "beam": 33, "block_coefficient": 0.59},
  "speed_kn": 33, "range_nm": 15000,
  "armour": {"belt_mm": 307, "deck_mm": 152, "turret_mm": 432},
  "main": {"calibre_mm": 406, "calibre_length": 50, "barrels": 3, "fore": 2, "aft": 1},
  "secondary": {"calibre_mm": 127, "calibre_length": 38, "barrels": 2, "per_side": 5},
  "torpedoes": {"mounts": 0, "tubes": 5},
  "aa": {"heavy": 20, "light": 30},
  "funnels": null
}
```
`main` options:
- `"mid": n` (warship style only) puts n centreline turrets amidships, between the funnels. Lion has a Q turret; Gangut has two amidships.
- `"superfire"` sets how many turrets of each end group step up: `true` (default, all), `false` (none, so each group has one end turret and flush turrets behind it), or `{"fore": 2}`. A flush turret behind a stepped one (Nelson's X) fires to the sides only.
- `"wing": n` (warship style only) adds n pairs of wing turrets, one each side, standing on the deckhouse amidships. They fire bow to stern on their own side and never across the deck, so the forward pairs can fire dead ahead together with the forward group.
  - By default each pair stands abreast. The first pair goes at the forward end of the middle, the second at the aft end, then they fill inward (Dreadnought: one pair; Nassau: two, hexagonal).
  - `"echelon": true` staggers each pair, port forward and starboard aft, and spreads the pairs among the funnels (Invincible, Neptune). An echelon pair fits a beam that's too narrow for an abreast pair, at the cost of length.
  - Wing turrets stow fore-and-aft toward the nearer end of the ship. Secondaries fill the spots the wing turrets leave free.
- Examples: `gangut.json` (1 + 2 amidships + 1, all flush), `dreadnought.json` (A, wing pair, X, Y), `nassau.json` (hexagonal), `invincible.json` (echelon), `battlecruiser.json` (Lion-style Q turret), `all_forward_flush.json` (all-forward with a flush third turret).

Limits are generous on purpose: the game's designer enforces the gameplay limits, and the generator only keeps its input sane (`styles.base.COMMON_LIMITS`). Guns can be 1–2000 mm with 1–20 barrels, armour up to 2 m, and torpedo, secondary and AA counts are in the hundreds. Hull form and speed stay within the range where the physics formulas mean something. Hulls go up to 1,000 × 100 m, and each turret group (`fore`, `aft`, `mid`) can hold up to 40 turrets, named A, B, C, A4, A5, ... (and Q, P, R, S, Q5, ... amidships). Silly designs are allowed; the physics decides whether they're valid. For example, twenty 305 mm Q turrets need about 650 m of middle section and a wide beam.

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
- `"machinery": {"type": ...}` works on every style: `naval_turbine` (the warship default), `steam_turbine`, `steam_recip` (the merchant default), `diesel`, `petrol` (the planing default), `fast_diesel`, or `coal_turbine` (pre-1920 coal-fired naval turbines, about 13 shp/t, for dreadnought-era designs). Each type sets machinery weight per shp and fuel use (`navarch.MACHINERY`).
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

## Outputs (out_designs/<id>/)
- `report.json`: valid flag, errors, warnings, displacement (std/full), draught, power, fuel, crew, GM, trim, and the weight list with x/z. Carriers add aircraft and capacity, flight deck size and height; merchants add cargo, deadweight and hold count.
- `hitboxes.json`: all values in metres, ship-local (origin = sprite centre, +x bow, +y starboard).
  - `hull`: the hull outline polygon.
  - `components`:
    - Turrets: `local` body/parts/barrels polygons (rotate them by the turret angle, then add x, y), `broadphase_r`, `arcs_deg`, `rest_deg`, `armour_mm`, base/top heights.
    - Barbettes, superstructure and funnels: polygons with heights.
    - Decks: `flight_deck`, and `deck` for raised forecastles, bridge decks and poops. `sponson`: gun and AA platforms, and deck-edge elevators. All are polygons with heights.
    - AA: circles.
  - Heights (`base`/`top`) are metres above the main deck. On a carrier that's the hangar deck.
  - `compartments`: citadel (belt/deck mm), magazines, machinery, steering gear. Carriers add hangar, aviation magazines and aviation fuel; merchants add `hold` or `cargo_tank` per hold.
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
  | `invincible` (Invincible-like, 25.5 kn) | 16.9k std, 48.1k shp | 17.3k normal, 41k shp |
  | `battlecruiser` (Lion-like, 28 kn) | 28.9k std, 90.6k shp | 26.3k normal; ~92k shp for 28 kn on trials |
  | `mtb` (Vosper 70 ft-like) | 35 / 44 t, 3,000 hp at 39 kn | ~47 t, 3,750 hp |
  | `pt_boat` (Elco 80 ft-like) | 60 / 72 t, 5,300 hp at 41 kn | ~46 / 56 t, 4,500 hp |

  - The tanker needs about 30% more power than a real T2: the Admiralty-coefficient power model is pessimistic for full hulls above Froude 0.18.
  - Carrier full loads run light because the range model burns less fuel at cruise than these ships actually carried.
  - The planing numbers rest on the placeholder power model; the PT boat comes out heavy.
