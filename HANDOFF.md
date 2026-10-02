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
- **Looks are visual only** (`"look"` in the design, `looks.py`). The user wants ships of different powers to look different with no gameplay effect: a look may change only the sprite images, never the layout, physics, report results, hitboxes or `sprite.json`. Turret drawings differ by look, but hitboxes always use `geometry.turret_shapes`. Looks are named after dockyards: `brooklyn` (US), `kure` (Japan), `portsmouth` (UK), `kiel` (Germany), plus the default `standard`. More are planned.
- Shadows come from the height map, not baked in. Mips are packed per layer (`<layer>_mips.png`, rects in `sprite.json`).
- **Mip atlases are an interchange format only.** The game uploads each level to the GPU separately (Vulkan mip layout is hardware dependent) and never samples the packed image, so the missing gutters don't matter. Large sprites are fine too: the game may drop the biggest mip levels.

## Planned by the user
- **The game spans about 1890 to 1970:** pre-dreadnoughts, through the dreadnought era, to early modern ships. Defaults and new features should cover that whole range.
- **More looks** (`looks.py`). Four nations are done; more will follow. A period look (Victorian black hull, white upperworks and buff funnels for the 1890s) would suit the pre-dreadnoughts.
- **Pre-dreadnoughts with lots of casemated guns.** The secondaries need a casemate mount type in the hull side, not only deck mounts. This would also fix Nassau-like ships, which can fit only 3 of their 6 secondaries per side on the deckhouse beside the wing turrets.
- **French "floating hotel" pre-dreadnoughts** with many different calibres: several main and intermediate batteries, often in wing turrets. The layout will need more than one main or secondary battery.
- A refactor of the whole design physics (engine models etc.). It should make the physics configurable by period, so engine efficiency and similar values can change over time.
- Research to replace the planing power placeholder (`navarch.planing_power`). It's one function by design.

## How to work here
- **Git:** the repo is on GitHub (`git@github.com:sharpneli/shipgen.git`, branch `main`). Pushing over SSH works with the user's key. Commit or push only when the user asks.
- Dependencies are `pip install cairosvg pillow numpy`. The system Python lacks them; use the venv at `~/.venv` (`~/.venv/bin/python design.py ...`).
- **Checking a look change:** render a design in every look and confirm `hitboxes.json`, `sprite.json` and `report.json` (except its `inputs` echo) are identical across looks. `standard` must stay byte-identical to the old sprites.
- **Regression method used throughout:** copy `out_designs/` aside, regenerate, and `diff -r`. Unrelated designs should stay byte-identical; expected changes should be limited to the designs you meant to change. The hand-authored fleet (`python shipgen.py --out <dir>`) has stayed byte-identical through all the changes, so keep it that way.
- Run `python verify.py out_designs/*` after every change. It does pixel checks of sprites against hitboxes.
- A turret-sweep checker existed only in the previous session's scratch folder. It rebuilds each main turret's sweep and tests it against taller blocks and funnels. Folding it into `verify.py` would be a good addition.
- The user edits files in `designs/` themselves. Never overwrite their designs. As of the end of this session:
  - `destroyer.json` has `calibre_mm: 1270`, probably a deliberate silly test.
  - `murica.json` has block coefficient 0.34 (needs `--no-limits`).
- Output folders are named after the design's `id`, not its file name. Duplicate ids overwrite each other; this already happened once.

## Known gaps and ideas
- **Physics calibration:** carriers' full loads run light; the PT boat runs heavy; the T2 tanker needs about 30% more power than real.
- **No sweep reservation outside warships.** That's deliberate for carriers and merchants (see above).
- **Height map:** columns only, so mast yards, derricks and barrels are left out. It's 8-bit with a 0.25 m step, so anything above 63.75 m clips.
- **Baked lighting:** the light rim on the upper-left edges of blocks and funnels is still baked in.
- **No aircraft are drawn** on carriers; the game is assumed to spawn them.
- **Wing turrets on narrow ships** (beam under 15 m) stand on the main deck, and the small deckhouse under the bridge may overlap them. No real design does this, so it hasn't been handled.
- **Missing turrets:** a mount that doesn't fit (beam too narrow, deck taken) is left off the drawing and listed as an error, even with `--no-limits`.
