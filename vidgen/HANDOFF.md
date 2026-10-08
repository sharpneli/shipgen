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
- **Code:** `wake.py`, `muzzle.py`, `magazine.py` and `ocean.py` are vidgen's own (numpy only). `ocean-surface-research.md` and `sea_state_lab.html` (WebGL2) are the sea's research and prototype. `wake.md` and `wake_bake_ref.py` are the
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
- **Water (2026-10-07, `ocean.py`, from `ocean-surface-research.md` and its prototype `sea_state_lab.html`):** the
  user asked for lightweight spectral waves for reasonable sea states, without the research's foam, to make the
  videos look better; the realtime version comes later. It replaced 14 hand-picked sine components and a scrolling
  ripple tile (in git history), which read as a scratchy lattice when zoomed out (Gangut).
  - **Sea:** the lab's JONSWAP wind sea (fetch 150 km) plus a narrow swell, in its three cascades plus the ripple
    cascade, with its Cox–Munk roughness top-up and choppy displacement (lambda 1). The waves' wind is the smoke's
    `WIND`, 6 m/s from the south (about Beaufort 3, Hs 0.8 m). `--beaufort` sets the waves' wind speed only; the
    smoke keeps its own. The default swell is 1 m, 10 s, from 240° (screen north is up), 60° across the wind
    (research 2.1: the cross-sea is much of what reads as ocean). `--swell HS,TP,FROM` overrides it.
  - **Linear sum:** the wake's baked slopes, sinkvid's boil and ring slopes and the blasts' roughness are added to
    the sea's slopes before shading, as research 5.3 says (superposition holds in linear theory). The wake's wash
    and sinkvid's oil slick damp the short waves (cascade 2, the ripples and the unresolved roughness); a blast's
    frost roughens them.
  - **Departures** (listed in `ocean.py`'s docstring): no FFT tile or textures, the spectrum is summed straight at
    the pixels as a separable DFT (two matmuls per cascade, exact at any zoom; waves under 3 px go into the glint's
    roughness). The wavenumber grid is jittered, so nothing tiles and hex bombing isn't needed. The Jacobian is
    summed over cascades 0–1. A sun aureole in the sky (my pick: the lab's plain gradient left everything outside
    the glitter path flat from straight above). The water body is set so the sea's mean colour matches the old
    palette (0.110, 0.218, 0.278), keeping the flash, smoke and deck calibration.
  - **Look notes:** the glitter path sits upper left, toward the sun, from the lab's virtual perspective eye (40°
    FOV above the frame centre). Wake divergent waves now show mostly through the glint. Without foam, Beaufort 5+
    looks too clean; keep to 2–4, or add whitecaps from research 3.3.
  - **Cost:** about 65 ms a frame at 720p (was about 30), single-threaded. vidgen now sets the BLAS thread count to
    1 like sinkvid: the matmuls are small, threaded OpenBLAS was 3x slower on them, and clips render in parallel.
  - **Rng:** `Water` still draws the old swell and ripple numbers from the scene's rng, so everything else in a clip
    (smoke, spray, firing phases) is unchanged and before/after clips differ only in the water.
- **Speed:** about 0.35 s a frame at 720p before the spectral sea (which adds about 35 ms), so 2–3 minutes a clip. The foam lace makes
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
  unchanged. Day only; there's no night mode or exposure adaptation.
- **Fireball (user, 2026-10-07: "it feels like it's just a sprite splatted in"):** the secondary flash is a
  temperature field, `Scene._fireball`, not one flat ellipse at one temperature. Luminance and colour come per pixel
  from the blackbody and sodium ramps (research 2.6: drive brightness through T). The core runs `FIREBALL_CORE` 5 %
  over the emitter's T and the gas cools outward by `FIREBALL_FALL` 25 % at q = 1, so the edge burns down through
  yellow and orange to a red fringe instead of being cut. Two noise octaves warp the radius into lobes and tongues
  and stir T by ±8 %. Their coordinates grow with the ball, slide outward and churn over its life, so it billows.
  Late in the envelope the cooler gas drops out first, leaving hot pockets inside the young smoke. The sodium share
  fades out over 1650–1250 K (`flash_rgb_v`), so cooling gas goes redder. It's the procedural stand-in for research
  7.2's flipbooks. A fireball under ~2 px across falls back to the analytic splat.
- **Flash light (research 7.3):** each emitter is a point light on what's already drawn (deck, turrets, smoke,
  foam), `E = I (h + 0.3 rho) / (d^2 + r0^2)^1.5` against the sun's `E_SUN` 70 klx, with h from the height map.
  It raises each pixel's own colour, capped at `FLASH_LIGHT_MAX` 1x the sun (1.5x turned the whole ship orange in
  a broadside). The sea takes almost none (it's blue: mostly mirrored sky; lit by its own colour it went green).
  It's worked out on a quarter-res grid. A big salvo washes the ship warm for a few frames: that's most of the
  "big gun" feel.
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
- **Blast on the water (2026-10-07, `muzzle.Blast`, from `muzzle_blast_water-vfx.md` and `muzzle_blast_ref.py`;
  replaced the foam-particle "blast ring"):** one event per mount's salvo. Guns of a mount firing within 0.2 s sum
  their energy, so lam grows as N^(1/3) (Bismarck's twin 380: 25 m, the visible edge 250 m ahead, ~90 m abeam). It
  has Fansler's directivity, so the disc is offset outboard along the bore, and the arrival time comes from the
  Rankine-Hugoniot LUT. The far field is the sea's roughness, not a height field: the ripple amplitude goes as
  `1 + 0.8 frost - 0.7 lead`, plus a signed sheen (frost toward the sky's silver at `BLAST_SHEEN` 0.35, the leading
  edge darkened by `BLAST_DARK` 0.22). User, 2026-10-07, found these "a bit too much" and they went to 0.55, 0.25, 0.15;
  2026-10-08 the culprit turned out to be the Iowa photo's bright seam (frost summed by half where fronts cross,
  gated by the thin leading edge): it drew hard pale arcs. The seam is gone and the first values are back. Near field: scour foam `(1.3 - r/lam')^1.5` plus the jet's lobe along the
  bore's ground track for low fire, drawn as the wake's fresh lace at `BLAST_FOAM` 0.6. Spray particles come by
  lam^2, weighted by `exp(-(h/1.5 lam)^2)`. Worked out at quarter res in a window per event. Departures:
  - **Mach stem:** lam x 2^(1/3) over water (`muzzle_blast_waves.md` 0.7), faded smoothly by elevation
    (`exp(-(el/20 deg)^2)`), not switched on "low-elevation fire".
  - **Jet lobe:** an ellipse 4 lam cos(el) long, 0.9 lam wide, weighted `exp(-(el/10 deg)^2) exp(-(h/1.5 lam)^2)`,
    with no elevation cutoff.
  - **Frost:** the research's `1 + 2.5 frost` glittered like whitecaps, because vidgen's ripples carry the sun
    glint, so the ripples get 0.55 and the silver comes from the sheen. p_vis is 2 kPa (research: 2–2.5 matches the
    Iowa photo).
  - **Not done:** the hull's reflection (an image source), the sun-shadow line, the faint precursor ring, polar
    foam texture, Wilson haze (research: it doesn't happen for real guns).
- **Smoke the jet moves (`muzzle_blast_waves.md` 5):**
  - **Jet punch:** a shot shoves older smoke in the cone ahead of its muzzle (3 lam_f, 20 degrees) by
    `0.5 lam_f e^(-d/lam_f)` along the bore and spreads it 1.2x, eased over `PUSH_EASE` 0.15 s. Puffs under 0.3 s
    old are left alone. Funnel particles get the same push as a velocity kick. A broadside fired through its own
    smoke clears a tunnel.
  - **Smoke rings:** 0.3 of shots in light air, falling linearly to none at 10 m/s of wind (0.24 here). A ring
    takes 25 % of the shot's A and moves as `x ~ t^(1/4)` to 8 lam_b. It's drawn as 10 blobs around a ring whose
    axis is the bore: a bar across the bore for flat guns, an ellipse for raised ones. DEPARTURE: drawn at
    `RING_VIS` 0.3 of the puff's look; at the full share it drew as an opaque white pill.
  - **Not done:** the shock's one-frame ripple through the smoke (under a pixel at 30 fps).
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
  - **Ship velocity:** the young smoke keeps it for the forward carry's time constant (the reference's gun is on
    the ground).
  - **Igniter share:** it rises smoothly from 0.3 % at 100 mm to 1 % at 200 mm. The reference gives cased guns
    0.3 % and bag guns 1 %; vidgen doesn't know which a mount is.
  - **No smoke attenuation of the flash** (research 7.6): the flash's own smoke ramps in during the fireball and
    would put it out.
- **Speed:** about 0.35–0.8 s a frame at 720p while firing (five `Density` passes for smoke: tau, three colour
  channels, shadow). Bismarck's second salvo with 26 live blasts: 0.80 s, against 0.62 before the blast, fireball
  and light work (blast fields 0.05 s, flashes 0.14 s).

## Magazine explosions (magazine.py, 2026-10-07)
The user asked for the research's effect (`magazine_explosion.md`, prototype `magazine_explosion_ref.py`), with the
smoke in the same broad look as the funnel and gun smoke where it's thin. `--sink` adds the break and the sinking (below,
"Explosion, break and sinking in one clip"). `vidgen.py <id> --explode Y` (a magazine room id or a mount it
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
- **Framing:** an explosion clip fits the ship to 34 % of the frame width (`EXPLODE_FIT`) so the column and the
  cap have room. The clip runs 40 s past the main event.
- **Camera (2026-10-08, user):** explosion clips pan. The ship starts up and left (`CAM_GUNS`), so the gun blasts
  have the right and the bottom of the frame. It pans low and a little left for the explosion (`CAM_BLAST`, so the
  top left isn't empty while the column rises), arriving 0.3 s before the main event after a 3 s pan
  (`CAM_PAN_BLAST`). With `--sink` it then drifts toward the middle for the sinking (`CAM_SINK`, from 20 s after
  the main event, over 10 s). The pans are smootherstep. The positions are my picks by eye.
  - How: the scene is drawn on a canvas bigger than the frame by the pan's range plus `CAM_MARGIN` 8 px, with the
    ship fixed at `C` there. Each frame cuts the output window from it (`Scene.cam`, at whole pixels). The blast's
    camera shake moves the window, so it no longer smears the frame's edge. That costs about 1.6x the pixels on
    Invincible with `--sink`. Clips without `--explode` are byte-identical (checked on a Bismarck still).
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
- **Open:** the flooding clips (stern, bow) still can't capsize (the timeline refuses one). There are no side or
  bottom sprites (doc 2.7): a plunge only shows walls from the height-map steps.

### Breaking in two (2026-10-07)
The user asked for a sinking for "absolute loss": the ship breaking at the aft, middle or front. `--end break-aft`,
`break-mid`, `break-fore` (or `breaks`) and `--cut X`. The physics is shipgen's `sinking.Break` (README "Sinking
demo"); sinkvid only draws it.
- **Where:** aft and fore are the centres of the aftmost and foremost main-battery magazine rooms. The torn zone is
  the magazine room. Mid is the section holding amidships, a girder failure. With no main magazines (merchants), the
  section a quarter of the length from that end. These were my picks: magazines are how big ships were lost
  outright (Hood, Barham, Arizona, Queen Mary).
- **Time:** the sim runs in game time at 0.05 s steps. The clip plays it in real time while the pieces' ends move at
  0.8 m/s or more (`BreakTimeline.V_REF`), and up to 20x faster while they just flood (`RATE_MAX`). The warp follows
  only pieces still in sight and is smoothed over 2 s. The HUD shows `(time xN)`. On Bismarck:
  - aft: the stern is gone at 18 s; the main body floods for about 5 minutes, then capsizes and sinks (97 s of clip)
  - mid: both halves are gone within a minute (63 s)
  - fore: the bow is gone at 18 s, the rest as for aft (99 s)
- **Drawing (my picks by eye):**
  - The cut is ragged: `Cut.x_at`, sines across y and z of 0.07 B, plus a slant. Every point (deck, walls, the coarse
    bottom) takes its piece from that surface.
  - Both pieces get torn faces over the section at the cut, from the keel up to whatever stands there. They're dark,
    with the decks as light lines and rust patches. Deck within ~0.12 B of the cut is scorched.
  - In break clips the hull's bottom is drawn too, in antifouling. It shows only once a piece rolls or pitches past
    the vertical: Bismarck's main body capsizes keel up.
  - Points are grouped by (piece, normal kind), the bottom last. Old stern/bow clips are byte-identical (checked on
    stills at 12 and 30 s).
- **The blast (a stand-in for magazine.py's explosion, which needs vidgen.py's scene):** a flash (added light,
  0.3–0.9 B, 0.25 s), a boil of 0.1 L and a ring, 420 spray particles, 320 thin smoke puffs (each at most 36 px:
  vidgen's coarsest blur buckets drew a few big puffs as squares), steam and wreckage over 3 B. Fires and smoke burn
  on each torn end while it's out of the water.
- **Oil:** each torn end leaks half the flooding clips' rate, decaying over 15 s (torn bunkers empty fast). At a
  steady rate, five compressed minutes pooled it black. As each piece goes under, it dumps its share by weight of
  the intact wreck's eight tank puddles.
- **Pieces can survive:** a broken-off end can float on trapped air (the destroyer's stern), and a boat's wooden
  halves stay up. Invincible's main body survives a fore break for 45 minutes. The sim stops once the pieces still
  afloat have lain still and taken under 0.5 t/s for 120 s (judged over 30 s windows: a step's flows chatter in and
  out of a cell). That's honest to the model. If total loss should be certain, raise `BREAK_LEAK` or lower
  `BULKHEAD_HEAD` in sinking.py.

### Explosion, break and sinking in one clip (2026-10-08)
The user asked for one "magnum opus" clip: Invincible's magazine explosion followed by the ship breaking in two and
sinking. `vidgen.py invincible --explode W1S,W1P --sink` writes `out/invincible_explode_W1S_W1P_sink.mp4`
(`--sink` needs `--explode` at `--tier blast`). vidgen owns the clip; sinkvid only draws the wreck for it
(`SinkScene(host=...)`, `Scene._wreck`).
- **Where:** the cut is the middle of the exploded magazines and the torn zone is their span (-19.1..4.0 m on
  Invincible). With that, both halves sink at sinking.py's defaults; a plain mid break left the bow afloat.
- **When:** the break lands on the main event (sinkvid's clock starts `HIT_S` before it). Before that it's the old
  explosion clip, byte for byte. On Invincible: break at 12.5 s, the bow (capsizing, keel up) gone ~88 s, the stern
  ~135 s; 173 s long.
- **Hand-over at the break:** sinkvid's 3D hull takes over with the turrets as trained and the thrown gunhouses
  gone (`Ship3D` `bearing`/`skip`). vidgen keeps the sea, camera, smoke, fire and HUD: sinkvid's boils, rings and
  oil calm join the sea's slopes; its funnel smoke, fire smoke and steam go into vidgen's smoke blobs; its stand-in
  blast isn't drawn. The halves coast to a stop along the heading over `BREAK_STOP_TAU` 4 s (an open section is a
  huge drag; my pick), and the camera follows (`BreakTimeline.glide`, `SinkScene.cam`). The magazine's stem fires
  and steam ride the wreck via `Pose.deck` and go out once their spot is under water (the steam then boils up at
  the surface). Landed gunhouses vanish at the break.
- sinkvid's render was split into `surface`/`draw_oil`/`draw_hull`/`draw_foam`/`draw_debris` for this; its own
  clips are byte-identical (destroyer break-mid stills).

## Line of battle (2026-10-08)
The user asked for several ships in one clip, starting with two of the same side in a line of battle ("the vibes
of a massive battleline shooting broadside for those Jutland feelings"); ships shooting at each other come later.
`vidgen.py invincible+invincible --fire 20` writes `out/invincible+invincible.mp4`.
- **Code:** `Ship` holds one ship's design files, layers, mounts and firing schedule, funnels, baked wake, spray and
  smoke spawning. `Scene` holds the sea, smoke, shots, blasts, camera and HUD, plus everything for the explosion
  and the wreck, which reads the lead (`--explode` with a line is refused for now). Particles gained a `coal` field
  so each ship's funnel smoke keeps its colour.
- **Geometry (my picks):** line ahead on one course at the slowest ship's speed, `--spacing` 366 m centre to centre
  (about two cables, close order), the lead first. The line's middle sits where a lone ship's centre did, and the
  line is fitted to the frame like a lone ship (80 % x 62 %): two Invincibles come out at ~1.8 px/m against ~5 alone.
  All ships share the target bearing (`auto_target` over all mounts); for a target at battle range the lines of
  sight are near enough parallel.
- **The locked-layer trick holds:** with one velocity every ship stands still on screen, so hulls (each pixel from
  the ship covering it most), height maps (max) and so the shadows, and the wakes (slopes summed, foam densities
  maxed) are merged once at setup. A frame costs about what a lone ship's does; each extra ship adds one wake bake
  (~0.5 s). Followers steam through the leader's wake, as they did.
- **Firing:** each ship trains and fires on its own schedule. Ships after the lead open `LINE_LAG` 0.3–1.5 s after
  they're on target, so sister ships don't flash in lockstep. `--fire S` (default `FIRE_S` 7) sets the firing phase.
- **Byte-identical for one ship:** checked on stills (Bismarck, Kongo `--target 300`, Connecticut, destroyer,
  Invincible `--explode`, and `--sink` at 40 s). A trap found on the way: a numpy float64 scale (from the line's
  arithmetic) promoted wake.bake's float32 fields and changed the wake slightly; the line geometry is kept in plain
  floats.
- **Squadron and strategic views (2026-10-08):** the user wants the look "majority of the time one is looking at
  squadron level", and a strategic one with the squadron at a sixth of the screen. `lion+lion+lion+tiger_1914
  --size 1920x1080 --fire 20` and the same with `--fit 0.1667` (`--fit`: the share of the frame the line fills).
  At 0.17 (~0.25 px/m at 1080p) the sea's swell reads as fine diagonal streaks and the wake as a thin line; nothing
  is tuned for that scale yet.
- **Next (user's order):** more ships and the line's look; then ships firing at each other (range compression on
  screen, shells landing, splashes and hits need research first); then explosions and sinking on any ship.
  Different speeds or headings would break the locked layers: hulls cropped to their box and wakes shifted per frame.

## Long zoom (2026-10-08)
The user wants the effects "clear" from high up instead of blobs, with smooth zooming in mind (a zoom demo comes
later), built up on one ship firing: `vidgen.py lion --size 1920x1080 --scale 0.25 --fire 20` (`--scale` is px/m,
in place of `--fit`; 0.25 is the strategic view's scale). Their criteria: the smoke sim stays the objective
reference for visibility, but it may be drawn differently from higher up; the gun flashes inside the smoke are
loved and must stay. Every change is a smooth function of the scale `s`, never a switch (a zoom would pop at it).
- **Why it was blobby:** `Density` drew a blob smaller than its finest blur at that blur and at full peak, so
  sub-pixel particles swelled (the stem spray was a white disc wider than the bow, gun smoke clumps 10x their
  area); it ran at half resolution; blob sizes snapped to powers of two; smoke lighting was per pixel, so at 0.25
  every puff clipped into a lit and a dark half.
- **`Density(conserve=True)`** (vidgen's scene; sinkvid's own clips keep the old mode): each blob keeps its integral
  `PEAK w 2 pi (SIG r)^2` (1.07, 0.84: the old buckets' measured average, so close-ups look as before), split
  between the two nearest blur levels in log sigma, at full resolution, each level blurred only in the window its
  blobs reach. It's faster than the old half-res one (5-16 ms against 84 for 3000 blobs at 1080p). The gun smoke's
  1 px radius floors are gone; the explosion's fire and debris read the grid's `res`.
- **Smoke lighting in metres:** `LIGHT_BLUR_M`, `LIGHT_SLOPE` from the half-res pixel tuning at `S_REF` 4 px/m
  (Bismarck at 720p). Explosion clips (~2.5 px/m) light their relief about 1.6x softer than before; the Invincible
  still looked the same to me.
- **Drawn by zoom (looks, not visibility):** gun smoke at `GUN_SMOKE_VIS (S_REF/s)^0.5` of the research (0.28 at
  0.25 px/m): a puff is the sign she's firing when the ship is 7 px wide. Funnel smoke is a `Plume`: puffs live
  80-100 s, grow by the old rate plus `PLUME_SPREAD` 1 m/s (Pasquill D, sigma_y ~ 0.07 x), peak falling as 1/r^2,
  and fade as `e^(-age/fade)`, fade 8 s close up rising as `(S_REF/s)^0.83` to ~80 s at 0.25. Kept whole the
  soot laid a black slab astern close up; faded fast there was no trail from high up. It's pre-warmed analytically
  along the track with its own rng (`Ship.prewarm_smoke`), so clips start with the trail.
- **Fireball:** the temperature field and the analytic splat crossfade over 1.5-3 px across (was a switch at 2 px).
- **Wake foam (`lace_k`):** the lace texture is never drawn finer than ~2.5 px, so from high up it was coarse
  clumps, a dashed confetti ribbon. Lace now blends toward its mean coverage (the noise is uniform, so the mean of
  a lace layer is just its coverage c) by smoothstep in log s from 1.5 px/m (all lace; the line clips at ~1.8 keep
  theirs) to 0.4 (none): a smooth bright stripe fading astern, as a wake reads from altitude. Blast scour foam too.
  At 0.5 it can look a touch too smooth, a beam; some low-frequency streaks could come back there.
- **Flash glare:** the bloom's 6 and 17 px halos gain 0.6 and 0.3 x `FLASH_GLARE` from S_REF out to 0.25 px/m
  (smoothstep in log s), so a salvo flares from high up while staying point-like. The light itself is unchanged;
  the explosion fire shares `_glow`, so it gets the same glare at the same zoom.
- **Clips (user's to compare):** `out/lion_s0.25_v1.mp4` and `lion_s1_v1.mp4` (smoke only), `lion_s0.25.mp4` and
  `lion_s0.5.mp4` (plus wake and glare).
- **The sea:** left as it is. At 1:1 the "streaks" at 0.25 are the swell's long crests broken into groups, as swell
  looks from altitude; ocean.py is exact at any zoom (waves under 3 px go into the glint's roughness).
- **Shells:** left. A shell is invisible at 4 m/px; how to show fire from high up belongs with ships firing at each
  other (research first).

## The zoom demo (2026-10-08)
The user: "start with looking at just one ship, then zoom out to reveal it was a squadron and then end up at
strategic scale. It conveys the scale the game mostly operates on." `vidgen.py lion+lion+lion+tiger_1914 --size
1920x1080 --zoom` writes `out/<ids>_zoom.mp4` (`make_zoom`, `Zoom`).
- **Timeline (`ZOOM_T`, `ZOOM_S`):** 9 s on the lead at 4 px/m (training, the first salvos), 18 s zooming out
  (smootherstep in log s) to 0.25 px/m, 8 s held there; the line fires throughout. The camera's centre goes from
  the lead to a little behind the line's centre by `u = (1/s - 1/s0)/(1/s1 - 1/s0)`, so the lead stays put while
  close and the line slides in as the view opens. The caption crossfades from the lead's to the line's between 2.8
  and 2.0 px/m (`ZOOM_HUD`); the target marker's ray leaves from the lead, then the line's centre. A scale bar
  (1-2-5 lengths, top right: the target marker usually sits bottom right) shows the scale. The clip renders in
  ~11 min (6 parts).
- **How:** every scale-dependent layer in vidgen (hull, height map and shadows, the wake bake and warp, the sea's
  DFT matrices, turret sprites) is made once per Scene at one scale. So the zoom keeps a ladder of Scenes, `ZOOM_STEP`
  sqrt 2 apart (9 levels), each with the same seed, so they run the same sim. A frame is drawn bare from the level at
  or just above its scale, on a canvas covering every frame that level draws (`Zoom.view`, about 2x the frame's
  pixels), cut around the camera and Lanczos-downsampled by up to sqrt 2, then captioned. `Scene.set_look(s)` sets
  the zoom-drawn looks (gun smoke share, plume fade, glare, lace) to the frame's own scale, so they're smooth while
  the levels switch. Frames either side of a switch matched by eye. The levels are the mip chain, so shipgen's
  exported mips (user's pointer: `hull_mips.png`, `height_mips.png` (2x2 max), `turrets/<type>_mips.png`, rects in
  `sprite.json`) aren't needed here; a realtime renderer zooming per frame should use them.
- **Same sim at every scale:** `Water` drew a canvas-sized foam noise and a scale-dependent number of old swell
  numbers from the scene's stream; both are now fixed (the noise has its own stream). Every clip's smoke and firing
  phases shifted once for this. The wake foam's clump size is fixed through a zoom (`ZOOM_FEAT` 0.6 m, `feat_m`),
  and its lace fades as the clumps go under ~2 px.
- **Cost:** each level's scene is built when first needed (4 wake bakes) and stepped from the start; a chunk holds
  only its levels.

## Battle: two lines firing at each other (2026-10-08)
The user: "2 battlelines firing at each other in anger for the visual feel", no explosions, a short shot and the
framework in place, for a storyboard and a faux trailer next session. `vidgen.py lion+lion --vs seydlitz+seydlitz
--size 1920x1080 --fire 22` writes `out/lion+lion_vs_seydlitz+seydlitz.mp4`; `--scale 1.0 --focus 2` frames the
enemy lead closer. Code: `battle.py` (gunnery, `Splash`, `Hit`), wired in `Scene` (`enemy=`, `_battle_step`,
`_splash`, `_hit_glow`, splash blobs in `_smoke_fields`).
- **Geometry (my picks):** both lines on one course and speed, the second `--range` (2 km) to starboard, so the
  locked layers still hold (a Run to the South). Heading -78 in a battle, so the gap runs across the frame's long
  side. Each ship engages its opposite number; the second line replies `BATTLE_REPLY` 2 s later. Only main
  batteries fire: at a real range the secondaries were out of reach (every 4" gun firing at 2 km filled the sea).
- **Range compression:** the lines are 2 km apart on screen, but everything range-dependent in the fall of shot is
  taken at `--fall-range` (14 km, Jutland-like): angle of fall from the brief's 16" table (~12 deg), the salvo
  pattern (sigma 0.45 % of range along, 1/6 of that across: ~250 m by 40 m) and spotting errors. Shells fly the
  vacuum path over the screen range on a clock stretched to at least `TOF_MIN` 5 s (a real 14 km flight is ~23 s),
  with `LAND_JITTER` so a salvo lands as a ripple. The shell keeps pace with the ships on the slowed clock
  (`Shot.shell_carry`).
- **Spotting:** per battery, the salvo's mean point starts 4 % of range off, flips over/short and closes by 0.55
  a salvo to 0.5 %: the first salvos fall short, then over, then straddle and hit.
- **Splash (`shell_splashes.md`, the user's brief):** its sizes (H = 73 m (d/0.406), width 25 d, t_a), curves (top,
  opacity, crown blossom 0.5-2 widths, base surge to 2.5 widths), angle-of-fall height factor, lean and foam ellipse,
  ricochets at flat falls, dye rules (per firing ship, unique in its line; `--dye auto` dyes only `wwii` and
  `cold_war` looks: navies dyed from ~1930, so Jutland splashes white). Drawn as blobs in the shared smoke field,
  lifted up the screen by height (the explosion column's oblique projection), so a column reads as a pillar and
  casts its long shadow. The foam disc is foam particles that appear as the column falls back. The brief's LOD
  tiers aren't needed offline: the conserving splats widen a sub-pixel column and dim it by the same factor (the
  brief's "size floor"). Departures: the mist is thin (`MIST_TAU` 0.35, fading over 9 s): a salvo's stacked mist
  made a white wall; the column is a ragged stack, not a capsule.
- **Hits:** inside the target's waterline (`wake.waterline`): no column (brief), a 0.1 s burst, a flickering fire
  for 12-30 s by calibre and dark smoke trailing like the funnels' (`HIT_SMOKE`). No damage, no debris yet.
- **Camera:** `--focus N` centres any ship (the first line, then the second) for storyboard shots.
- **Not done:** hits' debris and deck wetting by near misses, AP delayed underwater bursts, HE, a dye stain in
  the foam (foam is one colour), ships manoeuvring (breaks the locked layers), firing in a zoom (`--zoom` is one
  line), the camera moving within a battle clip.

## The trailer (trailer.py, 2026-10-08)
The user asked for "a short kickstarter style trailer" for maximum hype ("and inevitable disappointment when it
never comes out"); the game will be free. Their storyboard, with my additions (cards, the caption, the stamp, our
own Lion being the one that blows up, as at Jutland): cold open on a lone Lion, "DESIGN EVERY RIVET.", the design
bureau flicking through nine real designs (stats, warnings and cutaways from their exports) to Lion stamped
APPROVED, a match cut from her plan view onto the zoom clip's lead ship, the zoom out over "COMMAND THE LINE.", a
camera swing round onto a 4 v 4 battle in three framings, a cut to the forward magazines going up with "LIVE WITH THE CONSEQUENCES.", a
whiteout into the animated end card from `stylecard.html`.
- **Run:** render the footage (`TRAILER_CLIPS` in trailer.py lists the vidgen command lines; all at
  `--size 1920x1080 --clean --out vidgen/out/trailer`), then `~/.venv/bin/python vidgen/trailer.py` writes
  `vidgen/out/fleetwright_trailer.mp4`. `--still T` writes one frame of the cut; `--only sheets|end|cards` a piece.
- **`--clean` (vidgen):** leaves off the HUD, caption, target marker and scale bar. It goes through the environment
  (`VIDGEN_CLEAN`) because Python 3.14's forkserver workers don't inherit module globals.
- **Footage cost at 1080p:** run four at a time at most (`--chunks 4`): six at once filled the 30 GB. The zoom and
  the explosion took ~25 min each with three others running; a 34 s 4 v 4 battle about the same.
- **The edit:** `Clip` reads a clip forward and blends neighbouring frames, so `ramp` can play pieces at any speed
  (slow-mo explosion at 0.5x, the zoom's training and zoom-out at 2x). Cuts are hard except the fade in, the drop
  into the sea and the whiteout.
- **The swing (user, 2026-10-08: the hard cut from the zoom turned the ships from -12 to -78 in one frame):**
  `trailer.py --render-swing` writes `out/trailer/swing.mp4` (117 frames; 4 parts take about 4 min). It's the
  battle's own sim (the wide shot's seed and ships) drawn on a 2812x2994 canvas at the wide shot's scale and cut
  through a moving camera, so the swing can turn 66 deg without empty corners. The camera follows the zoom's own
  path (turned 66 deg) for `SWING_XF` while the zoom, playing on at 2x, dissolves into it; the dissolve hides the
  zoom's gun smoke, which the battle sim doesn't have yet. Then a cubic Hermite in log scale and position (it starts
  with the zoom's velocity, so the pull-back carries on, dips to 0.28 px/m and comes back in to 0.384) and a
  smootherstep turn bring it to rest on the wide shot's framing. It holds there for `SWING_HOLD` and dissolves into the
  wide shot itself. The sims match frame for frame, but `Water.foam_noise` is laid out by the canvas size, so the
  wake's foam texture differs a little; the dissolve at rest hides that. The sea's virtual eye is moved over the
  frame's centre every frame (`Ocean._light_setup`), and the sun is turned with the camera so the glint stays put on
  screen as in both clips (the ships' shadows keep the canvas sun; at 0.3 px/m they're a pixel). Times hang off
  `BATTLE_WIDE[0][0]` and `SWING_ZOOM_AT` (where the zoom's last piece ends): change either and re-render the swing.
- **The match cut:** the zoom starts with the lead centred at 4 px/m and heading -12 (`ZOOM_START`), so Lion's
  preview_rest.png (the same sprite at 10 px/m) is scaled, turned and slid there and the footage fades up under it.
  If the zoom's start changes, change `ZOOM_START`.
- **Type:** Bodoni Moda and IBM Plex Mono are in `vidgen/fonts` (OFL). Bodoni is set at optical size 20, not the
  display 96: at 96 its hairlines go under a pixel and x264 eats them.
- **Not done:** a rendered explosion inside the battle (vidgen still refuses `--explode` in a line, so it's a cut
  to a lone Lion). Music: see the next section.

## The trailer score (score.py, synth.py, 2026-10-08)
The user asked for music "of naval battles and somewhat serene", beat-matched to the cut, with `soundfx.md` as an
environment guide only and no gun sounds for now. Node and system ffmpeg aren't installed, so instead of ZzFX it's
a numpy orchestra (`synth.py`: additive strings, horns/trombones/trumpets, choir, harp, celesta, ship's bell,
timpani, taiko, field drum, cymbals, risers, a braam, a sea bed; per-bus convolution hall; a lookahead limiter).
No samples and no AI audio. `scipy`, `soundfile`, `pyloudnorm` and `matplotlib` were added to `~/.venv`.
- **Run:** `~/.venv/bin/python vidgen/score.py` (about 85 s) writes `out/fleetwright_score.wav` (48 kHz 24-bit,
  -14 LUFS, -1.2 dBTP), float stems in `out/score_stems/` (strings, brass, choir, keys, perc, fx, sea; same length,
  pre-limiter, sum them to rebalance) and muxes `out/fleetwright_trailer_scored.mp4`. `--from/--to` renders a
  stretch for drafts; `synth.py` alone writes `out/synth_demo.wav`, every instrument in turn.
- **Music:** D minor, one theme (A-D-E-F) three times: lone horn on the cold open, strings over the zoom, brass
  over the battle; the montage is a bass climbing D to C# with harp sixteenths that speed up with the sheets;
  B-flat tutti on the stamp; D minor tutti on the hit, slow-motion strings, the braam on the fireball, the theme's
  head on a horn under the last card; D major under the title, and it lets go on "[HAH, AS IF]".
- **Beat-matching:** `timeline()` rebuilds every section's start from trailer.py's constants (the zoom's speed
  pieces are copied from `cut()`, keep them in step). From Lion's sheet to the hit the cut is a 100 BPM grid
  (`G`, anchored on the stamp, the sea, the wide shot, the cut to the second Lion and the hit; under 3 % tempo
  drift); the open (`O`), the montage (`M`, one beat per sheet) and the end card (`E`, title on beat 2) have their
  own. Flash times in the footage (Lion's salvos 24.37/27.20, the squadron's, the fireball 55.07) were measured
  off the render and are hard-coded: re-measure if the footage changes. The run prints each hit's onset error.
- **Can't listen:** balance was set from per-stem RMS tables and spectrograms only; the user's ears decide.


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
