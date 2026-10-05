# vidgen handoff

Read `vidgen.py`'s docstring first: it covers usage and what a clip shows. This file holds what the code
doesn't: why it was built, the choices behind it, its ties to shipgen, and what's still open.

## Purpose
The user asked for it on 2026-10-05: "we just want to see how the ships would look like in an actual game". It's a
style visualiser, not the game. It turns one exported ship (`out_designs/<id>/` from shipgen) into a short
top-down MP4. The camera follows the ship. Its weapons start at rest, train on a target bearing, then fire.
The user plans to move vidgen into its own repo, to keep shipgen focused on design and sprites.

## Ties to shipgen (to cut when it moves)
- **Input:** only shipgen's exported files: `sprite.json`, `hitboxes.json`, `report.json`, `hull.png`, `height.png`
  and `turrets/*.png`. It never imports the design side, so it's a stand-in for the game consumer. Read
  shipgen's README "Outputs", "Conventions" and "Shadows" for the formats:
  - bow is +x, bearings run clockwise from ahead
  - `traverse_deg` is one interval that never wraps
  - a mount's `top_m` and the height map are metres above the waterline; hitbox heights are above the main deck
- **Code:** `from shadow import HEIGHT_STEP_M, shadow_mask, sun_offset_px`. It reaches shipgen's root through
  `sys.path`. `shadow.py` imports `shipgen.py`, which needs cairosvg. In a new repo, copy `shadow_mask` and
  `sun_offset_px` (about 40 lines of numpy) and set `HEIGHT_STEP_M = 0.25`. Point `--designs` at shipgen's
  `out_designs`; the default `ROOT / "out_designs"` assumes vidgen sits inside shipgen.
- **Docs:** shipgen's README has a "Style videos (vidgen/)" section and a command line near the top. shipgen's
  `.gitignore` has `vidgen/out/`. Remove all three when it moves.
- **Python:** `~/.venv/bin/python` with numpy, pillow and `imageio-ffmpeg`. The system has no ffmpeg;
  imageio-ffmpeg brings its own binary.

## Choices (mine, tuned by eye; nothing feeds back into the design)
- **Training rates:** 30°/s for main guns, 40°/s for secondaries and 30°/s for torpedoes (`TRAIN_RATE`). That's
  about 5–10× real, to keep clips short (about 14 s with aft turrets).
- **Bearing logic:** every mount whose arcs hold the target bearing trains and fires; the rest stay at rest. A
  mount moves from rest to aim inside `traverse_deg` (`unwrap`). This shows the turret logic the game is
  meant to have.
- **Firing pattern:** main guns fire in salvos (2.8 s with 280 mm and up, else 2.2 s). Secondaries fire on their
  own beat (`0.7 + calibre/180` s, with a random phase). Torpedo mounts fire once, tube by tube. Muzzle points are
  the tips of each barrel polygon in `hitboxes.json`.
- **Scale:** the ship fits 80% × 62% of the frame and is never drawn above the sprite's own px/m. It sits 7% of
  the width ahead of centre, so the wake has room.
- **Lighting and wind:** sun at bearing 225° on screen (upper left), elevation 45°. Wind blows 6 m/s toward
  screen-down. The ship's heading is fixed for the whole clip.
- **Particles:** everything is splatted into half-resolution density buffers in blur buckets (`Density`).
  Buckets with a big radius are splatted into coarser grids, which halved the frame time.
  - Foam size scales with hull length (`fs`), so a PT boat gets a crisp Kelvin V and not blobs.
  - Bow foam (the `kelvin` system) keeps its outward push longer, so the arms spread.
- **Water:** 14 low-steepness components with no dominant pair, because two strong crossing swells read as a
  lattice. The swell is summed at half resolution, with ripples at full resolution. The ripple tile grows when
  zoomed far out (Gangut, 904 m), where it would alias.
- **Speed:** about 0.35 s a frame at 720p, so 2–3 minutes a clip.

- **Turret shadows depart from shipgen's README "Shadows"** (user, 2026-10-05: "barbettes don't have shadows
  rendered"). Barbettes are in the height map, but the turret above them rotates, so the README stamps one
  roof silhouette offset by `top_m - deck_m`. That leaves a gap between the barbette's thin crescent and a
  floating roof shadow. On Seydlitz's raised A it also overshoots, because the offset is measured from the main
  deck. vidgen instead:
  - sweeps the silhouette in slices from the barbette top (`base_h`, the height map under the pivot) to `top_m`,
    about 1.5 px of shadow apart and at most 24 slices
  - measures each slice from the deck the mount stands on (`recv_h`, the 20th percentile of the height map
    around the mount, sea left out)
  - keeps each slice only where the receiving surface is lower than it
  - smears barrel shadows slightly along the sun direction, which is acceptable here

  The game's shader and shipgen's previews have the same gap. If the sweep looks right, the same fix belongs in
  shipgen's `shadow.py` docs and `render.py`.

## Known oddities
- Gangut is so small on screen that its stern churn piles into a disc.
- Masts cast long, thin, solid shadows on the sea. That's correct for a 23 m mast at 45°, but it can look heavy.
- Coal smoke shades the deck dark around the funnels. That's intended.

## Ideas not done
- Shell splashes at a target that's in view
- A turning ship, with the heading changing over the clip
- Aircraft on carriers
- Recoil
- Funnel smoke by plant load
- A merchant-specific look; merchants currently get the same effects
