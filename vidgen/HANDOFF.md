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
- **Code:** `wake.py` is vidgen's own (numpy only); `wake.md` and `wake_bake_ref.py` are its research notes and
  the scipy prototype it was ported from. `from shadow import HEIGHT_STEP_M, shadow_mask, sun_offset_px`. It reaches shipgen's root through
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
- **Lighting and wind:** sun at bearing 225° on screen (upper left), elevation 45°. Wind blows 6 m/s from the
  south (screen bottom, user 2026-10-05) so smoke drifts away from the starboard guns. The ship's heading is fixed for the whole clip.
- **Wake (2026-10-05, from `wake.md`):** `wake.py` bakes the steady ship-frame wake once per clip: one FFT of the
  linear pressure-patch model gives the surface height, and two foam densities (`crest`: bow sheet, peel line,
  breaking crests; `wash`: the propulsor's wake) are advected bow to stern. It takes 50–250 ms. The heading is fixed
  and the camera follows the ship, so `Scene._wake` warps the bake to the frame once; per frame only the foam
  texture moves. That's two gaussian noise tiles in ship axes, anchored to the water and crossfaded over 14 s, mapped
  to uniform 0..1 and thresholded by the density (wake.md 3.2 item 3). The wash uses ridged noise for lace. Stem spray
  is still particles (rate from Noblesse's Zb), as are the gun blasts and torpedo tracks. Frame time is unchanged.
  Departures from wake.md, all mine and tuned by eye:
  - **Waterline:** shipgen exports only the deck edge, so `wake.waterline` shrinks it by an assumed stem rake,
    stern overhang and flare per style. wake.md 3.2 item 7 asks shipgen to export the real waterline; when it does,
    use that.
  - **Entrance angle:** from Cb, `8 + (Cb - 0.45) * 50` degrees, capped at 30. The steeper mapping in wake.md made a
    Liberty at 11 kn white at the bow. Bow whiteness and crest breaking also fade below Fr_L 0.25.
  - **Domain:** solved on a padded grid (3 spans behind, the Kelvin spread sideways, at most ~3M cells), then
    resampled onto a fine grid that covers only the frame. Without the padding the waves wrapped round the FFT and
    showed ahead of the bow.
  - **Normals:** the wake's slopes at 1x, not wake.md's 2–3x (the swell already carries the light), capped at 0.3,
    and eta is left whole under the hull: zeroing it there put a cliff in the normals that read as a halo.
  - **Crest foam:** slope breaking is weighted 0.25 and `tau_crest` is 5 s, not 8 s. The peel line spreads more
    slowly, and the bow sheet thickens toward the stem so it shows past the deck's overhang.
  - **Wash:** capped at 0.85, so the noise always breaks it up (else a planing boat's wash is a flat slab). The
    wash multiplier is 2 for planing craft and 0.925–1.15 by shaft count. The wash also tints the sea toward
    `CHURN` and flattens the ripples, the slick.
  - Semi-planing hulls (Fr_L > 0.6) get the chine whiskers and a smaller bow sheet (wake.md 4).
- **Particles:** smoke, spray, gun smoke and blast foam are splatted into half-resolution density buffers in blur
  buckets (`Density`). Buckets with a big radius are splatted into coarser grids, which halved the frame time.
- **Water:** 14 low-steepness components with no dominant pair, because two strong crossing swells read as a
  lattice. The swell is summed at half resolution, with ripples at full resolution. The ripple tile grows when
  zoomed far out (Gangut, 904 m), where it would alias.
- **Speed:** about 0.35 s a frame at 720p, so 2–3 minutes a clip (unchanged by the baked wake). The foam lace makes
  the MP4s 3–4× bigger (Bismarck 13.6 MB, was 3.5 MB); raise `--crf` if that matters.

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
- Masts cast long, thin, solid shadows on the sea. That's correct for a 23 m mast at 45°, but it can look heavy.
- Coal smoke shades the deck dark around the funnels. That's intended.

## Ideas not done
- Shell splashes at a target that's in view
- A turning ship, with the heading changing over the clip. The baked wake would then need wake.md 3.2's runtime
  half: shear the near-field lookup by the yaw rate, and draw a trail ribbon along the track
- Aircraft on carriers
- Recoil
- Funnel smoke by plant load
- A merchant-specific look; merchants currently get the same effects
