# Porting shipgen to C#

Plan written 2026-10-08, before any C# code exists. This covers what to port and how to test it.

## Decisions (user, 2026-10-08; amended as questions are settled)

- **Target:** C# on the game's existing **SDL_GPU** skeleton. The SVG + cairosvg path is replaced by a renderer
  written for SDL_GPU.
- **Python may still change until the port starts** (user, 2026-10-08): small features such as underwater torpedo
  tubes for battleships, or more HANDOFF work. Nothing that changes this plan is expected. Capture the goldens
  (Step 0) right before the port begins, not earlier.
- **Python is frozen** once the golden data below is captured. From then on all work happens in C#. Python stays in
  the repo only as the reference that produced the goldens. If Python ever has to change during the port, recapture
  the goldens in the same commit.
- **The ship model must not change.** Everything deterministic must match Python: validation, sizing, layout,
  report, hitboxes, subdivision, `sprite.json` metadata. This is the test base.
- **Port the generator as it is, bugs included** (TODO.md "Generator bugs", "Hidden thresholds"). Fix them in C#
  after the goldens pass, updating the goldens on purpose, one fix per commit.
- **Drawing only has to look right.** Clutter placement, dazzle, antialiasing and exact pixels may differ.
  There's no need to port Python's `random.Random`. Any seeded RNG works, as long as it is deterministic for each
  ship id (so a ship looks the same every time it's generated). Seed **per feature**, not with one stream for the
  whole ship: for example `"<id>/clutter/<roof or deck key>"`, `"<id>/dazzle"`. Then a refit that changes one part
  doesn't reshuffle the clutter everywhere else (see "Refits").
- **Bake once.** The renderer draws a ship into textures when it is designed, refitted or repainted for a new
  era. It doesn't draw ships live. This can change later with a refactor.
- **The height map is not antialiased** (user). Averaging heights at an edge invents a height that doesn't exist:
  a vertical wall gets a ledge halfway up. Height data has to be combined with min or max, never averaged, just as
  a depth buffer isn't resolved with MSAA in 3D. This applies to rasterising it and to its mips.
- **The command line is for testing.** The game calls the libraries directly.
- **Not ported:** vidgen, `hitview.py` (3D debug views), `sinking.py` (a demo; game-side if ever), `lookgrid.py`,
  `fleet.py` (the hand-authored fleet), `calibrate.py`. `fuzz.py` and `verify.py` get C# versions later (step 6).

## Solution layout

```
Shipgen.Core      design side. No package dependencies. Pure, deterministic, no I/O beyond JSON (de)serialisation.
Shipgen.Render    render side. Depends on Core's ship types and the SDL3 bindings the game skeleton already uses.
                  The caller passes in its SDL_GPUDevice: the game passes its own, the CLI creates a headless one.
Shipgen.Cli       the design.py equivalent: designs/*.json -> out_designs/<id>/ (report, hitboxes, sprite.json, PNGs).
Shipgen.Tests     golden tests against the frozen Python output (xUnit or NUnit).
```

Public API, the same contract as today (README "Pipeline"):

```csharp
IReadOnlyList<string> errs = ShipDesigner.Validate(design, limits: true);   // + Looks.Validate(design)
Ship ship = ShipDesigner.Build(design, hintLengthM: null);                  // ~ms; the designer UI calls this per knob
ShipSprites sprites = ShipRenderer.Render(device, ship, look, scalePxPerM, mips);  // GPU textures + SpriteMeta
```

The Python rules carry over as project references:
- Core never references Render.
- Render reads only the `Ship` it is given.
- `geometry` is the shared layer and lives in Core.
- Colours live only in Looks, which is in Render.

## Dependencies and where to get them

| Need | Source | Notes |
|---|---|---|
| JSON | `System.Text.Json` (in the BCL) | Keep key order as in Python, for readable diffs. Compare goldens as parsed numbers, not bytes. |
| CRC-32 (hull number: `100 + crc32(id) % 900`) | `System.IO.Hashing` (NuGet, Microsoft) or a 15-line table implementation | Must match zlib's CRC-32, or hull numbers change. |
| SDL3 / SDL_GPU bindings | Whatever the game skeleton already uses | Render takes a device, so it doesn't care which binding. |
| Shader compilation | Whatever the skeleton uses, probably SDL_shadercross (HLSL → SPIR-V/DXIL/MSL) | There are about 4 tiny shaders. Build them the way the game builds its own. |
| Hull-number text | SDL3_ttf (its GPU text engine or a surface upload), **or** glyph outlines converted to paths | The only text is the number painted on the foredeck, usually digits. |
| Font | DejaVu Sans Bold `.ttf`, embedded as a resource | dejavu-fonts.github.io (Bitstream Vera licence, free to bundle), or copy `/usr/share/fonts/truetype/dejavu/` from WSL. Today the code loads it from that Linux path. |
| PNG writing (CLI only) | SDL3_image `IMG_SavePNG`, or `StbImageWriteSharp` (NuGet, public domain) | The game uploads textures and never needs PNGs. |
| CLI parsing | `System.CommandLine` (NuGet), or a hand-written parser | design.py only has 6 flags. |
| Tests | xUnit/NUnit (NuGet) | |
| numpy / Pillow work | Plain loops over `Span<T>` or GPU passes | Height-map max-reduce, 2× box reduce for mips, alpha-to-grey conversion. |

Nothing else is needed. The design side currently uses only Python's standard library.

## Step 0: capture the goldens (Python, the last Python commit)

Add `tools/golden.py`, run it in WSL with `~/.venv/bin/python`, and commit its output under `golden/`. For every
`designs/*.json`, **plus about 300–500 fuzz-mutated designs** (fuzz.py's mutator, with the mutated design files
saved, both with limits and without), record:

1. `shipdesign.validate(design, limits=True)`, `validate(..., limits=False)` and `looks.validate(design)`, as exact
   strings.
2. The **whole `ship` dict** from `shipdesign.build(design)`: design, report, hitboxes and render (spec, deck_m,
   mounts, columns, summary). This is the core contract, wider than report.json + hitboxes.json.
3. `build(design, hint=length_m)` must give the same result as without the hint. Record that it does.
4. `sprite.json` from `render.render_ship`. Looks never change it (HANDOFF), so it's deterministic metadata:
   canvas size, origin, mount pixel positions, rest angles, arcs, z, mip rects. The new renderer must reproduce it.
5. When Python raises, record the exception type and message. The C# version must not crash on these either, but
   the expected output is "anything sane" (the generator is permissive; a Python crash there is a bug).
6. Build time per design, as a performance baseline (Python is 5–170 ms).

Generate the goldens with `PYTHONHASHSEED=0`. Check that nothing on the design side depends on `set` iteration
order or `hash()`. If something does, write down the order it relies on so the C# version can reproduce it.

## Step 1: the design side (Shipgen.Core)

About 9.6k lines of Python. Port bottom-up along the imports, so each module can be tested against the goldens as
soon as it exists:

```
weights (20) · geometry (961) · powerplant (411) · propulsion (182)
→ decks (51) · geo (61) · arcs (110) · batteries (145) · stability (118)
→ hullweight (272) · ordnance (137) · armour (364) · hull/plant/crew_templates
→ navarch (254)          (the size solver; imports styles: break the cycle with an interface)
→ layout (2858) + armament (346) + firecontrol (266)   (they import each other; port as one unit)
→ crew (419) · subdivision (551) · hitbox (248)
→ styles/base (306) · warship (30) · carrier (622) · merchant (368) · planing (183)
→ shipdesign (450)       (validate, build, height_columns)
```

Data model:
- **Typed records** for the design input, matching the current JSON schema (README "Design input"), and for the
  `Ship` output that the game reads (report, hitboxes, render spec).
- Internal modules may start closer to the Python, with small dictionaries and records, and get tidied once the
  goldens pass.
- Avoid a `Dictionary<string, object>` port of the whole thing. The game reads this data, so it should be typed.

Traps when converting Python to C#. Every one of these has to be checked:
- **`%` and `//`** round toward minus infinity in Python. In C#, `%` and integer `/` truncate. Coordinates are
  often negative, so write `PyMod`/`FloorDiv` helpers and use them everywhere Python used these operators.
- **`round()`** rounds halves to even, which is C#'s default `Math.Round` (`MidpointRounding.ToEven`), so these
  match. But `round(x, n)` with n digits differs at the last ulp from `Math.Round(x, n)`. Python rounds the
  correctly rounded decimal value; .NET scales by 10^n. Since report values are rounded this way, write a
  `PyRound(x, n)` helper that formats with "R", then rounds the decimal string. Golden tests will catch any
  mismatch.
- **`int()`** truncates toward zero, the same as a `(int)` cast, but Python ints never overflow. Watch the
  products of counts.
- **`min`/`max`/`sorted` with `key=`** are stable and return the *first* of equal elements. LINQ's `OrderBy` is
  stable too. `MinBy`/`MaxBy` also return the first; check each use.
- **Truthiness:** `if x:` is false for 0, 0.0, "", empty containers and None. Python design code often uses
  `d.get("k") or default`, which also replaces 0. Port that exactly, not as `??`.
- **Dict and JSON key order** is insertion order in Python. Keep ordered structures where output order is visible.
- **Float printing:** Python writes `1.0` and `1e-05`; .NET writes `1` and `1E-05`. The tests compare parsed
  values, so this only affects how the files read.
- **Maths library differences:** Windows' `Math.Sin`/`Pow`/`Exp` can differ from glibc in the last bit. The
  size solver iterates and layout makes threshold decisions, so a 1-ulp difference could occasionally flip a
  discrete choice. Compare floats with a tight relative tolerance (about 1e-9). Treat any difference in a
  **discrete** field (counts, ids, positions jumping, warnings) as a failure to look into, never something to
  loosen the tolerance for.

Done when: every golden design and fuzz case matches (validation strings exactly, numbers within tolerance), and
C# builds are no slower than Python. Expect them to be much faster.

## Step 2: CLI, design side only

`shipgen design designs/*.json [--no-limits] [--out DIR]` writes report.json and hitboxes.json, and prints the
same one-line summary design.py does. This lets the same diff workflow used on the Python side work for C# from
the start.

## Step 3: the renderer (Shipgen.Render on SDL_GPU)

Split it in two:

1. **Display list (CPU, pure C#, testable without a GPU).** Ship + look + seed produce an ordered list of draw
   commands for each layer (hull, each turret type, height map). It's a port of `shipgen.py`'s hull and turret
   drawing, `looks.py` and `clutter.py`, but emitting commands instead of SVG text. Commands:
   - `FillPath(polygons, fillRule, rgba)`
   - `StrokePath(polyline, width, cap, join, dash, rgba)`
   - `FillCircle` / `FillEllipse`
   - `PushClip(path)` / `PopClip`
   - `PushOpacity(a)` / `PopOpacity` (only needed where a whole group is faded)
   - `Transform`
   - `Text(string, size, rotation)`

   The SVG features used today are exactly these: path (with arcs), rect, circle, ellipse, line, clipPath, `g`
   with opacity or transform, dash arrays, linecap/linejoin, and one `<text>`. Flatten arcs and curves on the CPU,
   with an error tolerance in pixels.

   Also write a tiny **SVG writer** for the display list (about 100 lines). It replaces `hull.svg` for debugging
   and gives a GPU-free view of the drawing.

2. **SDL_GPU backend.** It runs the display list into render-target textures:
   - **Fills:** stencil-then-cover. Draw a triangle fan of each polygon into the stencil with increment/decrement
     (nonzero rule) or invert (even-odd), then cover where stencil ≠ 0. This needs no triangulation library and
     handles concave and self-intersecting outlines. Circles and ellipses get tessellated into polygons, so they
     go through the same path.
   - **Strokes:** expand to polygons on the CPU (butt/round/square caps, miter/round joins, dashes), then fill them.
     Strokes are thin and simple here.
   - **Clips:** a second stencil bit, or the clip's coverage written into the stencil before its children.
   - **Group opacity:** render into an offscreen texture and composite it with alpha. Opacity on a single shape
     is just the fill's alpha.
   - **Antialiasing (colour layers only):** MSAA (prefer 8×; check `SDL_GPUTextureSupportsSampleCount`, fall
     back to 4×), resolved into the sampled texture.
   - **Large canvases:** a 1 km ship at 10 px/m is about 10,000 px. Check the device's maximum texture size and
     render in tiles when the canvas exceeds it.
   - **Height map: no antialiasing** (see Decisions). An R8 target with 1 sample, drawn in column order (lowest
     first, so the taller wins, as now). Grey level = `round(top_m / 0.25)`, clamped to 0–255
     (`shadow.HEIGHT_STEP_M`). Every pixel then holds a height that really exists in the ship's columns.
     - A pixel is covered when its centre is inside a shape. That's the standard rasterisation rule, and enough to
       start with.
     - If thin parts (masts, rails) break up, the fix is a resolve that combines samples without averaging them:
       draw with MSAA, then resolve with a compute pass that takes the **max** over each pixel's samples (the
       taller structure wins at its edge). Never use the hardware resolve.
     - This is a deliberate break from Python: cairo antialiased the height map, so the golden `height.png` files
       have blended edges. Don't compare against them, except for a coverage check (any height above 0).
   - **Mips:**
     - Colour layers: 2×2 box reduce. Do it premultiplied, to avoid the dark fringes Pillow's straight-alpha
       reduce gives.
     - Height map: 2×2 **max** reduce (`shadow.reduce_max`) in a compute pass or on the CPU.
     - SDL's `GenerateMipmaps` is fine for colour layers, but not for the height map.
   - **`mip_rects` and the packed `_mips.png` atlas** exist only for the CLI's PNG interchange. The game uploads
     each level to its own textures.
   - **Readback (CLI only):** `SDL_DownloadFromGPUTexture` into a transfer buffer, then write PNGs.

3. **Previews.** preview_rest/starboard, debug_hitboxes and sheet are debug output.
   - preview_rest (hull + turrets at rest + sun shadow from `shadow.shadow_mask`) is worth having in the CLI to
     review looks.
   - Port the shadow as a GPU pass. The game will need the same shader anyway.
   - Port the rest only if it's missed.

Done when:
- sprite.json matches the golden for every design, with exact integers.
- Every design renders without errors.
- The images look right to the user next to the frozen `out_designs/` PNGs. They are not compared pixel by pixel;
  a coarse per-layer alpha-coverage IoU check above about 0.98 catches drawings that are broken or missing.

### Headless and test notes
- The CLI creates the device without a window. SDL_GPU only needs a window for a swapchain.
- Build and run on **Windows**, not WSL. The GPU in WSL is unreliable, and building over `\\wsl$` is slow. Clone
  the repo on the Windows side, and add a `.gitattributes` (`* text=auto`, `*.png binary`, goldens `-text`).
- For GPU-less test runs (CI), check whether the skeleton's SDL build can use D3D12 WARP (Windows' software
  adapter) or lavapipe. Otherwise keep render tests to the display list, the SVG writer, and sprite.json, which
  doesn't need the GPU if its layout is computed on the CPU first. **Design it so it is.**

## Refits (future; structure the port for it)

The user's example: the hull's shape stays the same, and a designer refits two triple 12" turrets into two twin
15" ones and makes the ship top-heavy. A refit keeps the hull and changes parts. The physics then reports what it
costs: stability, trim, draught. Refits aren't part of the port, but two things in the port should make them easy
to add:

- **Design side:** the seam already exists in Python (`shipdesign.solve`).
  - `size(design, hint)` picks the length and beam.
  - A grow loop retries with a bigger hull while the layout comes back `short`.
  - `balance(with_hull(design, L, B))` lays out, weighs and balances on that fixed hull. `spread_ends` then
    refines it.
  - The draught comes from the weights in `navarch.solve`, so on a fixed hull it rises with added weight, as it
    should.

  Keep these as separate public stages in C#. A refit then skips `size` and the grow loop, runs `balance` on the
  old L and B, and turns `short` into an error ("doesn't fit") instead of growing the ship. Stability, trim and
  freeboard warnings come out as they do now. Which parts a refit may move (the machinery? the bulkheads? the
  layout shift?) is a game-design question for later. Note that `balance` lays the whole ship out again: on a
  fixed hull, a heavier turret can still move the bridge or the funnels. Keeping untouched parts where they stand
  would need a layout that starts from the old one. That's new work, not part of the port.
- **Render side:** baking a whole ship on the GPU should take milliseconds, so a refit simply re-bakes everything.
  Seeding per feature (see Decisions) means the parts a refit didn't touch keep the same clutter and look the same.

## Step 4: CLI, full output

`shipgen design designs/*.json [--scale 10] [--mips 5] [--out out_designs] [--no-limits] [--no-previews]` writes
the same files as design.py: report, hitboxes, sprite.json, hull.png, turrets/*.png, height.png, `*_mips.png` and
previews. Also add `shipgen golden-diff GOLDEN_DIR OUT_DIR` for the comparison with tolerance.

## Step 5: retire Python

Once steps 1–4 pass:
- Move README/HANDOFF/TODO to describe the C# code.
- Keep the Python under `reference/` (or a tag) alongside `golden/`.
- Change the regression workflow in HANDOFF and memory: generate everything before and after a change and diff,
  which becomes `shipgen design --no-previews` + `golden-diff`.

## Step 6: fuzz and verify in C#

- Port `fuzz.py`. Its mutator and its time and memory guards become a `shipgen fuzz` command or a test.
- Port `verify.py`'s pixel check of sprites against hitboxes. It reads PNGs, so it can run on CLI output.

## Effort, roughly

| Part | Python lines | Notes |
|---|---|---|
| Design side incl. styles | ~9.6k | Mechanical, but long. `layout.py` alone is 2.9k. |
| Renderer (shipgen.py drawing, looks, clutter, render, shadow) | ~3.1k | Ported as display-list producers. |
| SDL_GPU backend | new | Stencil fills, stroker, clip/opacity layers, mips, readback. |

Golden tests let the design side be ported module by module with confidence. Expect most of the time to go to
`layout.py` and the styles, and to the stroker and stencil work in the GPU backend.

## Open questions for the implementer

- Which SDL3 C# bindings and shader toolchain the skeleton uses. Reuse them; don't add a second set.
- Settled: bake once, not live (Decisions); no antialiasing on the height map (Decisions, Step 3).
