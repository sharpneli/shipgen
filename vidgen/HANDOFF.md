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
  the scipy prototype (v2.2) it was ported from. `from shadow import HEIGHT_STEP_M, shadow_mask, sun_offset_px`. It reaches shipgen's root through
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
- **Wake (2026-10-05, from `wake.md` v2.2 and `wake_bake_ref.py`):** `wake.py` bakes the steady ship-frame wake
  once per clip. The hull is a thin-ship source sheet `q = U dm/dx`, and one FFT gives the perturbation potential.
  Eta, its slopes and the surface velocity all come from it. Three foam densities are advected bow to stern along
  the streamlines: `fresh` (the breaking crest's front face near the hull, plus the hull sheet), `resid` (residual
  foam fed by decaying whitewater) and `wash` (the propulsor lane). The bake takes 0.4–2 s; the column march and
  age blur dominate. The heading is fixed and the camera follows the ship, so `Scene._wake` warps the bake to the
  frame once; per frame only the foam texture moves. That's two gaussian noise tiles in ship axes, anchored to the
  water and crossfaded over 14 s, made ridged (high along the noise's zero lines) and mapped to uniform 0..1.
  Foam is drawn where the noise beats `1 - c`, with coverage `c = cap * d^gamma` of the density (`LACE`), at most
  0.9 opaque, with the residual at half opacity. This departs from wake.md 6's soft breakup on smooth noise, which
  read as mush, and from its solid core: the reference's fresh foam is a broad plateau near 1 beside the forward
  hull, and the wash reaches 1.5, so both drew as flat white slabs. Lace needs the coverage well under a half, so
  the caps keep the densest foam holed, and fresh foam's gamma 1.5 keeps the bow ears thin away from the hull. The wash also
  tints the sea toward `CHURN` and flattens the ripples (the slick). Stem spray is still particles (rate from
  Noblesse's Zb), as are the gun blasts and torpedo tracks.
  The port replaced the earlier pressure-patch bake and its hand tweaks (bow crest envelope, peel line, wash cap
  0.85, crest trail 0.35, chine whiskers); those are in git history (f92886d4). Departures from the reference:
  - **numpy only:** gaussian blurs are spectral (m and the velocity in the 2-D spectrum, the age blur by a padded
    1-D FFT). The distance to the waterline is the exact distance to the polygon near the hull, not an EDT.
  - **Waterline:** shipgen exports only the deck edge, so `wake.waterline` shrinks it by an assumed stem rake,
    stern overhang and flare per style. wake.md 3.2 item 7 asks shipgen to export the real waterline; when it does,
    use that. It is rasterised 4x4 supersampled from that polygon, not from fore/aft exponents.
  - **Entrance angle:** from Cb, `8 + (Cb - 0.45) * 50` degrees, capped at 30.
  - **Grids:** the FFT runs on the reference's padded domain (grown to cover the frame) at half the reference's
    step. Everything after it runs on a fine grid over the frame only, with eta, slopes (spectral) and velocity
    resampled bicubically. The reference's resolution-tied widths (the hull band's `1.5 dx`, the smoothing of m)
    use the reference's own step `d_ref`. Smoothing m at the fine step let very short divergent waves through,
    and they showed as fine straight streaks.
  - **Checked:** the bake's fields match `wake_bake_ref.py` run through a numpy stand-in for scipy.
  - **Normals:** the wake's slopes at 1x, not wake.md's 2–3x (the swell already carries the light), capped at 0.3.
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

## Sinking clips (sinkvid.py, 2026-10-06)
The user asked for stern- and bow-first sinkings of Bismarck in vidgen's look, with the wake's lace foam, as a
visual demo of `sinking_foam.md` (research by another session; `sinking_foam_ref.py` is its scipy prototype)
before a realtime version. `sinkvid.py bismarck [--end stern|bow|both] [--still T ...]` writes
`out/<id>_sink_<end>.mp4`. It reuses vidgen's water, lace, particles and HUD, and shipgen's `sinking.py`
(flooding model) and `render.composite` (one more tie to cut when vidgen moves).
- **Pose:** zero until the hit at 1 s, then `sinking.Flood`'s history squeezed into 16 s (game time and flooded
  weight share the clip, like `sinking.simulate`'s frames), then a scripted plunge (`PLUNGE`: pitch to 48° in 27
  s, with the extra sinkage that brings the rising end's tip to the surface), then 8 m/s down. Monotone cubic
  through all keys. Rotation is about the lcf, as in `sinking.Points.frame`. Bismarck: by the stern at T+81 min,
  by the bow at T+117.
- **Ship:** `sinking.Points`' recipe plus normals, at twice the frame's resolution: about 0.9 M points. The ship
  is z-buffered there, lit by its rotated normals (a flat deck at rest stays as drawn), shadowed by a sun shadow
  map (casters above water at their ground projection), faded with depth under water, then downsampled. The
  bottom is a coarser set that only feeds the waterline cut and the crossing foam.
- **Surface:** the doc's layers on a fixed world canvas (the ship is stopped, the camera fixed): crossing foam,
  the collar (`W` = columns with hull above and below), boils from the **hitbox cells** (not the reference's
  uniform compartments), the slam and ring, oil and debris. Crossing and collar foam are drawn as the wake's
  `fresh` lace, the residual as `resid`, the boils as `wash` lace over the churn tint.
- **Departures from the doc, my picks by eye:**
  - A cell's vent is the main deck over it, or its top if that's higher. Air from a hold goes up its trunks;
    venting at the cell's own top made every flooded hold boil at once.
  - The flooding model's fill counts as air already gone.
  - Oil is well under the reference: leak 0.06 m³/s, 0.4 % of the fuel at the end in 8 staggered puddles, true
    colour at 45 %, rainbow at 15 %. At its numbers the slick buried the foam in black discs.
  - Funnel smoke runs until the funnel top goes under, then a steam burst (the doc's "not modelled" cue), drawn
    unlit.
- **Speed:** about 0.6 s a frame at 720p (step 0.05 s), so a 74 s clip takes about 25 minutes. The foam source
  is worked out in a window round the ship.
- **Open:** capsize and break-in-two aren't drawn (the timeline refuses a capsize). There are no side, bottom or
  cut-face sprites (doc 2.7): a plunge only shows walls from the height-map steps.

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
