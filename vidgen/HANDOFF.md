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
- **Code:** `wake.py`, `muzzle.py` and `magazine.py` are vidgen's own (numpy only). `wake.md` and `wake_bake_ref.py` are the
  wake's research notes and the scipy prototype (v2.2) it was ported from. `magazine.py` is the port of `magazine_explosion_ref.py` (research `magazine_explosion.md`). `muzzle_flash_research.md`,
  `muzzle_flash_ref.py` and `figs_muzzle_flash.py` are the same for the guns (the figure script needs scipy and
  matplotlib; the research's `claude/...` paths are where another session wrote it). `from shadow import HEIGHT_STEP_M, shadow_mask, sun_offset_px`. It reaches shipgen's root through
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
- **Target bearing (user, 2026-10-07):** no separate beam clips. By default `auto_target` picks the starboard
  bearing the most main mounts reach, then the most mounts of any kind, then the one nearest 55°. Arc ends are
  candidates, so a cross-deck arc that only just reaches counts at its edge: Babel, Seydlitz, Invincible, Duilio,
  Inflexible and Doom get 60°, every other design 55°. `--target` still overrides it.
- **Bearing logic:** every mount whose arcs hold the target bearing trains and fires; the rest stay at rest. A
  mount moves from rest to aim inside `traverse_deg` (`unwrap`). This shows the turret logic the game is
  meant to have.
- **Firing pattern:** each main battery fires salvos on its own beat, `1.6 + calibre/250` s (381 mm 3.1 s,
  305 mm 2.8 s, 203 mm 2.4 s). A battery is one gun (calibre and calibre length from the turret type id), so
  shipgen's several main batteries (2026-10-07, `babel`, `connecticut`, `lord_nelson`) each keep their own rhythm.
  The biggest opens fire and the others follow 0.2–0.5 s later. This replaced one shared beat picked by a 280 mm
  cutoff (2.8 s or 2.2 s). Calibres are parsed with decimals ("164.7mm"). Secondaries fire on their
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
- **Particles:** funnel smoke (with the gun smoke, see "Guns"), spray and blast foam are splatted into half-resolution density buffers in blur
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

## Guns: flash, smoke and shells (muzzle.py, 2026-10-07)
The user asked to replace the placeholder flashes (a chain of orange blobs sized `1 + calibre/30` m) with the
research's system, and the tracers (glowing streaks, `calibre >= 75` only) with shells that look like shells.
`muzzle.py` ports `muzzle_flash_ref.py`'s per-gun constants and per-shot emitters and puff. Each shot is a `Shot`
that is analytic in time: the scene keeps a list and asks each for its emitters, puff and shell at the frame's
time, and drops it when the shell has landed or left and the smoke is thin (peak tau < 0.01) or far away.
- **Inputs:** the bore and calibre length from the turret type id; the charge from the research's fit
  `4000 d^3 (L/50)`. The propellant comes from the look's navy (double-base for portsmouth and kiel, single-base
  otherwise) or `--propellant`. shipgen doesn't export ammunition yet; when it does (propellant, flash-reducer salt,
  bag or cased), read it from there. RH 0.7, wind as for the funnel smoke.
- **Flash:** primary, intermediate and secondary emitters as the reference. Each emitter's intensity is averaged
  over 4 samples in the frame interval, splatted with analytic normalisation (sigma >= 0.6 px), and converted to
  display units as `L / 1500 cd/m^2 * 0.18` (the sunlit sea maps to about the water's own value). Then bloom on a
  compressed copy (radii 1, 6, 17 px) and a luminance roll-off above 0.7 that turns at most 75 % white. The
  roll-off is applied only to what the flash adds (`frame + T(frame + F) - T(frame)`), so the rest of the frame is
  unchanged. Day only; there's no night mode, flash lighting on smoke or the water, or exposure adaptation.
- **Smoke (unified with the funnel smoke; user, 2026-10-07: the first version's opaque single discs looked like
  sprites beside the funnel smoke):** funnel particles and gun smoke go into one optical-depth field (`Density`
  blobs, a 64 px bucket added for big puffs) with a tau-weighted colour per blob. They share the lighting (a
  surface whose height is the blurred log thickness), the opacity `1 - e^-tau` capped at `SMOKE_MAX` 0.9, and the
  shadows (each blob's tau moved along the sun by its own height; funnel smoke used one mean height before). A
  shot's puff keeps the reference's A, drift, rise and spread, but is drawn as `SUB_PUFFS` 14 clumps (each 0.45 of
  its spread). They're strung along the jet from the wind-drifted muzzle to a little past the puff's centre, with
  their own slow drift and Dirichlet shares of A. The drawn optical depth is `GUN_SMOKE_VIS` 0.07 of the research's.
  That's a look: by the research a 380 mm puff stays opaque for tens of seconds, which buried the ship. The game's
  unified smoke system should use the full value for visibility. The colour starts at the propellant's tint and
  fades to neutral over 5 s; water fog is white. Puffs aren't merged (research 5.5): vidgen's rates stay under
  ~100 live shots.
- **Blast ring:** foam particles as before, now sized by `lam_b` (ring speed `2 lam_b`/s, 1.2 lam_b/s forward).
  The count is weighted by `exp(-(h_muzzle/lam_b)^2)` in place of the `calibre >= 150` switch: a 380 mm at 8 m gets
  ~0.8, a 150 mm on a deckhouse almost none.
- **Shells:** every gun. Mass `14000 d^3` kg, and muzzle velocity from 30 % of the charge's energy (380/52: 905
  m/s, 105/65 about 900). Elevation is the vacuum angle for `TARGET_RANGE_M` = 12 km (Bismarck 4 degrees, Devastation
  with black powder 31). The shell keeps the ship's velocity. It's drawn as a 4.5-calibre ogive lit as a cylinder,
  at least 0.9 px in radius (fainter by the root of the true over the drawn area), with a fading smear of half a
  frame's motion. Its shadow on the sea moves away from the sun by its height, and its strength falls as
  `d / (d + 0.0093 z)`, the sun's disc blurring it.
- **Departures, my picks by eye:**
  - **Slowed shells:** `SHELL_TIME` = 0.132 (user, 2026-10-07: 10 % faster than the first 0.12). At real speed a shell crosses the frame in 2–3 frames, inside its
    own fireball. Its path is real; only its clock is slowed, like `TRAIN_RATE`.
  - **Shells over the flash:** on the slowed clock a shell is still inside the fireball it really outran, so it's
    drawn on top, a dark silhouette as in high-speed photographs.
  - **Flash profile:** the secondary fireball is flat-topped (`exp(-q^2/2)`, normalised analytically) with noise
    on its edge. A gaussian's tail stayed visible out to about twice the fireball's size.
  - **Ship velocity:** the young smoke keeps it for the forward carry's time constant (the reference's gun is on
    the ground).
  - **Igniter share:** it rises smoothly from 0.3 % at 100 mm to 1 % at 200 mm. The reference gives cased guns
    0.3 % and bag guns 1 %; vidgen doesn't know which a mount is.
  - **No smoke attenuation of the flash** (research 7.6): the flash's own smoke ramps in during the fireball and
    would put it out.
- **Speed:** about 0.35–0.55 s a frame at 720p while firing (five `Density` passes for smoke: tau, three colour
  channels, shadow).

## Magazine explosions (magazine.py, 2026-10-07)
The user asked for the research's effect (`magazine_explosion.md`, prototype `magazine_explosion_ref.py`), with the
smoke in the same broad look as the funnel and gun smoke where it's thin. It's the effect only: the stern breaking
off and the sinking (from `sinking.py`) come later. `vidgen.py <id> --explode Y` (a magazine room id or a mount it
serves; `Y,X` sends a second one 0.3–0.8 s later, tier 4) writes `out/<id>_explode_Y.mp4`; `--tier column` is tier 1
(Lion: the roof lifts, the barbette vents a flame column, the ship fights on); `--explode-at T` times the hit
(default 4 s after the first salvo).
- **From the ship, not hand-placed:** `magazine.plan` reads `hitboxes.json`'s magazine room (tonnes, x span, the
  mounts it serves), the barbette, the adjacent boiler and engine rooms and the hull outline:
  - M (propellant burned in the cascade window) = room tonnes × the propellant's share of a round (muzzle.py's
    charge fit against its shell fit, 23 % for 380/52) × `F_FAST` 0.3. That's a tuning value until a mechanics
    resolver exists: Queen Mary's forward group fits ~0.45, Invincible's ~0.17. Bismarck's Y: 22 t, fireball 163 m
    for 12.6 s, lam 76 m.
  - Openings: a gun port per barrel (where it leaves the gunhouse, along the trained barrel), the sighting hood,
    deck hatches over the magazine (one per ~4 m), four side scuttles, the vents of machinery rooms that share a
    bulkhead with the magazine (Hood), then the barbette when the roof lifts. Fail times are the prototype's
    sequence; the pressure is its stand-in curve (the column plateaus instead, so its jets keep going).
  - Steam from the nearest boiler room; stem fires spread over the magazine's length.
- **Physics:** the reference's particles, ported as is (buoyancy from a decaying heat, drag to the sheared wind,
  entrainment growth, the mushroom's circulation, the soot skin). The gunhouse flies as a tumbling turret sprite;
  for a tier 3 event it stays inside the fireball the whole time, so it's correctly hidden.
- **Drawing:**
  - Oblique lift for everything vertical (research 3.1, k 0.6, H_c 450 m), measured from the deck, not the sea.
    Funnel and gun smoke barely rise and are unlifted, so plain clips are byte-identical (checked against HEAD).
    Shadows use the true height.
  - Smoke goes into the shared optical-depth field: the same lighting, opacity cap and per-blob shadows as funnel
    smoke. Each puff is 4 clumps turning slowly, like the gun smoke's SUB_PUFFS. Thick explosion smoke also gets a
    coarser relief (`EX_RELIEF`) from its own tau, and its shadow can take the sea to 30 %. Both apply only in
    explosion clips.
  - Fire: the hot gas as an emitting medium, `S (1 - e^-tau_hot) (tau_hot / tau)^0.8`. S is the blackbody
    luminance (muzzle.py's tables, so fire and flash share one scale) at the hot gas's mean temperature, stirred
    ±14 % by rising world-anchored noise (the flipbooks' stand-in), then the flash's bloom and roll-off.
  - Water: the dark leading edge at sonic speed and a frost disc (3 s), and scour foam ~lam across drawn as the
    wake's fresh lace (fading over 10 s). Debris and the gunhouse splash.
  - Also: the scorch and the open barbette on the hull, a warm exposure pulse and a camera shake by lam, and a
    restrained fire light on the sea and the hull.
- **Departures, my picks by eye** (each marked DEPARTURE in the code):
  - Smoke drawn at `EXPLODE_VIS` 0.4 of the reference's KAPPA.
  - Fire temperature mapped to 900 + 1100 T K.
  - Soot skin 1.8 (the reference's 0.9 was tuned at night; in daylight the whole cap glowed for 10 s).
  - The fire light is weighted by luminance, not T³: a huge, barely warm cap lit itself orange.
  - Jet puffs at half the mass, fading out at the end of their life.
  - Debris trails: one thin puff per 1.5 m of flight, from burning pieces only. The reference's were beads as
    dense as fireball puffs.
  - Roof plates don't trail.
  - Side vents, stem fires, debris count and speed, and soot mass scale with the fireball (`D_REF` 157 m, the
    reference's 20 t), so a destroyer's 0.3 t magazine doesn't throw a battleship's smoke.
  - Steam is sized by the beam.
  - After a blast the ship stops firing and loses way (`STOP_TAU` 12 s), and the baked wake fades with the speed.
    That's a stand-in until the sinking clip takes over.
- **Framing:** an explosion clip fits the ship to 34 % of the frame width, low on the screen (`EXPLODE_FIT`,
  `EXPLODE_CY`), so the column and the cap have room. The clip runs 40 s past the main event.
- **Speed:** a sim step takes ~1 ms; a frame takes 0.6–0.8 s at 720p (two to five more `Density` passes). A
  single-ship clip now renders in `--chunks` parallel parts (default up to 6, the DRAM bandwidth limit), joined
  without re-encoding: Bismarck's 53 s takes about 5 minutes.
- **Not done:** night (no night mode in vidgen), the reflection of the fire, heat haze, smoke self-shadowing from
  a sun sweep (research 3.2 option B), underwater or capsized explosions, debris hitting other ships, and a
  mechanics resolver feeding M, P(t) and fail times.

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
- **Speed (optimisation pass, 2026-10-06):** both 74 s clips together in about 2 minutes (was 16). One core
  draws a frame in about 0.13 s and steps in 0.013 s (were 0.48 and 0.045).
  - **Parallel:** each clip steps its sim in its own process and hands frames to a pool of drawing workers. Each
    worker holds the same scene, built from the seed. Snapshots carry the lists and particles; the foam canvases
    and finished frames go through a shared-memory ring (`Ring`). So `render` must not touch the sim's state or
    its rng: boils draw their streaks when made, and are pruned in `step`.
  - **DRAM bandwidth is the limit, not cores** (measured on the user's 7950X3D under WSL2):
    - A STREAM-style triad saturates at about 45 GB/s with 2 processes; one already gets 39. With
      cache-sized arrays it scales almost linearly to 16 processes (1660 GB/s).
    - The sim step (15 ms alone) next to 8 background processes:
      - L2-resident arrays: 18 ms
      - L3-resident arrays (24 MB in all): 22 ms
      - L3 full (72 MB): 33 ms
      - DRAM-streaming arrays: 99 ms; just 2 such processes take it to 36 ms

      So DRAM traffic dominates, L3 contention adds a little, and the cores and vector units barely matter.
    - Hyperthreading and CCD placement couldn't be tested: WSL2's vCPUs float over the host's cores, so pinning
      inside the VM doesn't fix which core or CCD a process lands on.

    Past about 6 workers a clip (the default cap), more only contend. Everything was cut for bytes moved:
    - the sim steps on the every-third-point subset
    - foam canvases are updated and copied only inside the box foam has touched (`fbox`)
    - the hull draws only the wall kinds facing the camera (points grouped by normal kind)
    - shadows are cast from the subset into a 1x map
    - z-buffer and shadow map use `np.maximum.at`, not a sort
    - boils, rings and the collar are worked out at half resolution, the agitation at a quarter
    - full-frame blends are windowed to where their layer is
    - the frame centre is float32, since a float64 one promoted every `to_px` result
  - **vidgen's own `Water.shade` (107 -> 30 ms) and `box_blur`:** precomputed swell phases, 1-D ripple indices
    and slice-based cumsum windows. vidgen's output is unchanged (at most 1/255 on a few pixels).
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
