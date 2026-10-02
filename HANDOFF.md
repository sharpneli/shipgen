# Handoff notes for the next session

Read README.md first: it documents the inputs, outputs and conventions. This file covers what the README
doesn't: the decisions behind the current design, how to work safely here, and what's still open.

## Decisions the user made (don't undo them without asking)
- **Style vs type:** `style` is the design family (warship, carrier, merchant, planing). `type` (BB, BC, DD, ...) is only a gameplay label. Battlecruisers and destroyers are warships.
- **Arcs are fixed by mount kind** (`hitbox.ARC_*`), never deduced from obstructions. The user wanted no fiddling.
  - End turrets: ±135°. Side mounts: ±90°.
  - Side-firing centreline turrets (flush turrets behind a superfiring one, amidships turrets): ±65° about each beam.
  - Fixed MTB tubes: ±1°.
- **Side-firing turrets stow fore-and-aft** like real ships, so their rest bearing is outside their arcs. The game trains them out before firing.
- **Warships are built around their guns.** Main turrets are placed first and reserve their barrel sweep (`Layout.reserve_sweep`). Superstructure placed later must keep out of it.
- **Carriers and merchants have no main battery.** All their guns are secondaries fitted where they suit, and overlap is acceptable. Planing craft still have a main battery; the user hasn't decided whether MTB guns should become secondaries.
- **The generator is permissive.** Gameplay limits will live in the game's designer UI. `--no-limits` skips the input ranges entirely. Silly designs may look stupid or fail the physics, but they must run.
- Shadows come from the height map, not baked in. Mips are packed per layer (`<layer>_mips.png`, rects in `sprite.json`).

## Planned by the user
- A refactor of the whole design physics (engine models etc.).
- Research to replace the planing power placeholder (`navarch.planing_power`). It's one function by design.

## How to work here
- **This is not a git repo.** Suggest `git init` before big changes.
- Dependencies are `pip install cairosvg pillow numpy`; the user's system Python didn't have them.
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
- **Mips:** the packed levels have no gutter between them, so bleeding is possible if the game samples the packed image directly.
- **No aircraft are drawn** on carriers; the game is assumed to spawn them.
- **Sprite size:** at 10 px/m a 1000 m ship is about 10,000 px wide, and its mips atlas about 15,000 px. That's near GPU texture limits.
- **Missing turrets:** a mount that doesn't fit (beam too narrow, deck taken) is left off the drawing and listed as an error, even with `--no-limits`.
