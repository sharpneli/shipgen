# Magazine explosion VFX — research + prototype (2026-10-06)

Companion to `claude/damage-research/07_magazine_explosions.md` (the mechanics), `claude/sinking-vfx-research.md` (what happens to the pieces) and `claude/muzzle-blast-water-vfx.md` (the blast-on-water event this reuses). Reference code: `claude/magazine_explosion_ref.py` (numpy, simulation and top-down renderer), `claude/magazine_explosion_side.py` (sailor's-eye renderer), `claude/magazine_jet_clip.py` (jet-phase clip), `claude/magazine_explosion_video.py`. Media delivered in chat: `magx_jet_phase_night.mp4`, `magx_side_night.mp4`, `magx_strip_column.png`, `magx_strip_column_night.png`, `magx_strip_blast_day.png`, `magx_strip_blast_night.png`, `magx_projection_compare.png`.

Goal: the flame columns and fireballs should look great, at a realtime budget, in a top-down 2D-sprite game over a 3D model. The real events were already spectacular, so the target is fidelity, not exaggeration: physically scaled sizes and timings, then good rendering.

Tags as in the damage docs: **[INFERRED]** = my reasoning or calculation, **[UNCERTAIN]** = thin or conflicting sources.

---

## 0. TL;DR for the implementer

1. **The camera is the main problem, not the fire.** Seen from straight above, a vertical column is a disc. In the prototype the tier 1 flame column vanishes under its own smoke cap, and only the shadow tells you it is tall (`magx_projection_compare.png`). Fix: draw **vertical VFX in an oblique "3/4" projection**, `screen = (x, y + k·z')` with k ≈ 0.5–0.7, plus a soft height compression `z' = H_c·(1 − e^(−z/H_c))`, H_c ≈ 400–500 m. Ships and water stay strictly top-down. The column then rises up the screen, the cap moves off the ship (so the ship stays readable), and the fire's reflection hangs down the screen in the water. A true perspective lean is worse: at the screen centre, where the player will be looking, the column points straight at the camera.
2. **The shadow on the water is the second-strongest height cue, and it is nearly free.** A 1 km smoke column at 35° sun elevation throws a shadow ~1.4 km long. Compute it in true 3D (sun direction), not in the oblique projection.
3. **Drive every size and timing from the mechanics state, through four physical scalings:**
   - **Flame column (tier 1):** Heskestad flame height `L = 0.235·Q^(2/5) − 1.02·D`, where Q (kW) = vented burn rate × ~4 MJ/kg and D = barbette diameter. Lion's "200 ft" column needs ~1.5 GW ≈ 380 kg/s of cordite, about 3 charges a second **[INFERRED]**.
   - **Fireball (tier 3/4):** `D = 5.8·M^(1/3)` m, duration `t = 0.45·M^(1/3)` s (M < 30 t) or `2.6·M^(1/6)` s, lift-off height ≈ D. M = propellant burned in the fast phase. Queen Mary's "800 ft" flame fits M ≈ 20 t; Invincible's "400 ft" fits M ≈ 2–3 t **[INFERRED]**.
   - **Smoke cap:** a buoyant thermal, rising roughly as `z ∝ t^(1/2)` once the fireball has lifted off and widening at ~0.25 z, up to "thousands of feet" (Barham) over ~30–60 s, sheared downwind.
   - **Shock on the water:** the muzzle-blast event with `λ = (E/p₀)^(1/3)`; 20 t burned gives λ ≈ 73 m and a frost disc ~300 m across.
   - **Jet phase (before the fireball):** every failed opening (gun ports, hatches, hoods, ventilators) fires a directional flame jet of length `≈ 45·d·sqrt(P/p₀)`, tens of metres, for 0.3–1 s before the turret lifts (Arizona's half-second flame; Hood's ventilators). §2.5.
4. **Ten layers, all from the existing toolset:** fireball and flame puffs (flipbooks, emissive), smoke puffs (6-way lit flipbooks), steam (white), debris with smoke-trail ribbons ("octopus" tendrils), sparks, fire point lights on water and ships, the reflection of the fire, the smoke shadow, the blast frost and foam, and post (bloom, heat haze, exposure flash, camera shake).
5. **Budget: roughly 1–2.5 ms GPU at 1080p for one hero event, ≤ ~3k particles. The cost is overdraw, not particle count.** Draw large smoke at half resolution, merge puffs as they age, and never let one puff cover more than about a third of the screen.

---

## 1. What it looked like (sources)

### 1.1 Eyewitness and film

| Event | Observation | Source |
|---|---|---|
| **Queen Mary** (Jutland) | "A terrific **crimson** flame shot up through a great cloud of smoke to a height of approximately **800 feet**" (≈ 244 m) | [USNI Proceedings 1925, *Lessons of Jutland affecting design of turret armor*](https://www.usni.org/magazines/proceedings/1925/april/lessons-jutland-affecting-design-turret-armor) |
| **Invincible** | "A **crimson** flame rose about **400 feet** high and carried with it a huge bulk of plating" (≈ 122 m) | same |
| **Lion** Q turret | "The flame shot about **200 feet** high" (≈ 61 m). It escaped "upwards through the roof of the turret by the hole made by the enemy shell-burst"; the photo from Lydiard shows the flame **under** the smoke | same; [Devon Heritage](https://www.devonheritage.org/Places/DevonCounty/JutlandHMSLion.htm) |
| **Derfflinger** Caesar turret | Flames "as high as a house" | USNI 1925 |
| **Indefatigable** | "Smoke and flames gushed from the forward part of the ship and large pieces were thrown **200 feet** into the air" | [Wikipedia](https://en.wikipedia.org/wiki/HMS_Indefatigable_(1909)) |
| **Hood** | "Enveloped in a flash of flame and smoke which rose high into the air in the shape of a **giant mushroom**"; "sections of funnels, masts and other parts were hurled **hundreds of feet** into the sky"; after 3–4 min, "a flicker of flame and smoke on the water's surface" | [The War Illustrated via TracesOfWar](https://tracesofwar.nl/thewarillustrated/94/i-was-there-i-saw-one-vast-explosion-the-hood-had-gone.asp) |
| **Barham** (filmed from Valiant) | The explosion "lifts a **turret roof** and puts a column of smoke **thousands of feet** into the air"; she was rolled over far enough that the bilge keel was out of the water | [Hampshire Prints](https://www.hampshireprints.co.uk/blogs/royal-navy-warship-and-submarine-classes-complete-guide/hms-barham-04-the-only-battleship-sinking-ever-caught-on-camera) |
| **Arizona** | "A large visible flame fronting turret number one a **half-second** before the magazine explosion"; the whole process took "slightly less than **seven seconds**", captured on film | [USNI Proceedings 1997, *Seven Seconds to Infamy*](https://www.usni.org/magazines/proceedings/1997/december/seven-seconds-infamy) |
| **Queen Mary** debris | Tiger "was showered with debris from the explosion" | [Wikipedia](https://en.wikipedia.org/wiki/HMS_Queen_Mary) |

**Visual vocabulary** that comes out of this:

- a **precursor flash** at a hatch or turret (Arizona's half second);
- a **crimson** flame column or fireball, tens to hundreds of metres;
- a **dark** smoke column with a **mushroom** cap, rising to "thousands of feet";
- **debris** in high arcs, up to ~60–100+ m, landing on ships nearby;
- a **turret roof** or a whole turret thrown;
- **fire and smoke on the water** afterwards.

### 1.2 Colour **[INFERRED]**

- **Cordite and other nitrocellulose propellants are smokeless powders.** The flame is bright and fairly clean; eyewitnesses say *crimson*.
- **The heavy black and brown smoke** comes from what the fire picks up: fuel oil, coal dust (WWI), paint, cork insulation, linoleum, bedding.
- **White plumes** are steam from ruptured boilers and steam lines, and water thrown up where the hull vents below the waterline.

Palette: white-yellow core → orange → **crimson** → dull red, then soot (albedo ~0.07, slightly warm), plus white steam (albedo ~0.8). Smoke right after the blast is lit orange from inside and below; this is the "glorious" part at dusk and at night.

---

## 2. Scaling: from mechanics state to VFX parameters

### 2.1 Tier 1 — vented flame column (Lion, Seydlitz, Derfflinger)

The mechanics ODE (07 §6.2) gives the vented gas mass flow ṁ(t) and the magazine pressure P(t). Use:

```
Q(t)   = ṁ_burn(t) · ΔH          ΔH ≈ 4 MJ/kg (cordite heat of explosion, order of magnitude) [INFERRED]
L(t)   = 0.235 · Q^(2/5) − 1.02 · D_barbette       Heskestad; Q in kW, L and D in m
w_jet  ≈ sqrt(2 · ΔP / ρ_gas), capped                 how "jetty" the base looks (momentum vs buoyancy) [INFERRED]
```

Heskestad's correlation is for buoyant pool fires ([formula](https://calculator.academy/flame-height-calculator/)). A pressurised vent adds momentum, so the true flame is somewhat longer near the start. Treat the result as the floor.

| Flame length | Q needed (D = 8.5 m) | Cordite burn rate | Example |
|---|---|---|---|
| 15 m | 0.10 GW | ~25 kg/s | a few loose charges in a gunhouse |
| 30 m | 0.35 GW | ~90 kg/s | |
| **61 m** | **1.5 GW** | **~380 kg/s** | **Lion "200 ft"** — about 3 full 13.5" charges per second |
| 122 m | 7.3 GW | ~1.8 t/s | Invincible "400 ft" (a fireball, not a steady column) |

- **Duration:** the charges in transit, a few tonnes at most, burn out in seconds to tens of seconds. In the prototype the column lasts 14 s with a slow 0.7 Hz / 0.23 Hz pulse (fresh charges catching).
- **Turret roof plates and the gunhouse:** launch them as debris with `v ∝ sqrt(P − P_fail)` (07 §6.2).
- **Sparks:** burning grains and charge fragments carried up the column, 1.5–3.5 s life, additive.

### 2.2 Tier 3/4 — fireball, mushroom, stem

Fireball correlations (BLEVE/propellant-fireball practice; [AIDIC CET vol. 82](https://www.aidic.it/cet/20/82/036.pdf)):

```
D_max  = 5.8 · M^(1/3)                  (CCPS; Hord gives 7.93 · M^(1/3))     M in kg
t_fb   = 0.45 · M^(1/3)     M < 30 t    (momentum-dominated)
t_fb   = 2.6  · M^(1/6)     M > 30 t    (buoyancy-dominated; the two meet at ~14 s)
H_c    ≈ D_max                           fireball centre height at the end (van den Bosch & Weterings)
```

The CET paper quotes standard errors of ~30 % on D and ~80 % on t. **That spread is useful:** randomise per event.

| M burned in the fast phase | D (m) | t_fb (s) | Top of fireball ≈ 1.5 D (m) | Blast λ (m) | Frost disc radius ≈ 4λ (m) |
|---|---|---|---|---|---|
| 0.5 t | 46 | 3.6 | 69 | 22 | 86 |
| 2 t | 73 | 5.7 | 110 | 34 | 136 |
| 5 t | 99 | 7.7 | 149 | 46 | 185 |
| 10 t | 125 | 9.7 | 187 | 58 | 233 |
| **20 t** | **157** | **12.2** | **236** (QM "800 ft" ✓) | 73 | 293 |
| 50 t | 214 | 15.8 | 321 | 100 | 398 |
| 100 t | 269 | 17.7 | 404 | 125 | 502 |

(λ uses E = 0.5 · M · 4 MJ/kg, the same as the muzzle-blast doc **[INFERRED]**.)

- **What is M?** It is not the whole magazine. Take M as the **propellant burned in the cascade window** of the mechanics ODE, about the first second after the hull boundaries fail. The rest burns afterwards as fires, which feed the stem (§3.4).
- **Calibration:** Queen Mary's 800 ft fits M ≈ 20 t; Invincible's 400 ft fits M ≈ 2–3 t, or more if the flame was the column rather than the fireball top **[INFERRED]**.

**After lift-off: a buoyant thermal.** A thermal (instantaneous buoyant release) rises as `z ∝ (B·t²)^(1/4)`, i.e. `z ∝ t^(1/2)`, while its radius grows at ~0.25 z (classic Morton–Taylor–Turner / Scorer entrainment; continuous-plume constants in [Huppert's lecture notes](https://dennou-h.ep.sci.hokudai.ac.jp/arch/fdeps/2004-12-06/huppert/lecture4/pub/Japan4.pdf)).
- The **vortex-ring circulation** turns the cap into a mushroom: up through the middle, out over the top, down the outside and back in underneath.
- **Target:** cap at ~1 km by 30–60 s ("thousands of feet"), then stalling and spreading downwind.
- **Wind shear:** use `u(z) = u₁₀·(z/10)^0.14`. The column leans downwind with height, and that lean is a big part of the silhouette.

### 2.3 Debris

- **Speeds:** "200 feet" (Indefatigable) and "hundreds of feet" (Hood) give apexes of ~60–150 m, i.e. launch speeds ~35–55 m/s. Turrets travel ~40 m horizontally (Vanguard, 07).
- **Count:** ~30–80 visible pieces per tier 3 event.
- **Trails:** about half the pieces burn and trail smoke. Those trails are the classic "octopus tendrils" seen in big-explosion photographs.
- **Splashes:** each piece makes a splash and foam dot where it lands. Pieces can land on neighbouring ships (Tiger, Bellerophon), so give debris a collision check against nearby hull sprites and spawn a small hit spark plus a scorch decal there.

### 2.4 Water

- **Blast frost ring and dark leading edge:** the muzzle-blast event as is, with λ from the table. Scour foam into the crest-foam channel with radius ~λ.
- **Debris splashes:** foam dots (τ ≈ 6 s).
- **Fire light:** point lights at the fire's emission-weighted centre (§3.3).
- **Reflection** of the column (§3.3).
- **Smoke shadow** (§3.2).
- **Oil on fire** and boils as the pieces sink: these come from the sinking doc.

### 2.5 Jet phase — flame jets from the openings (before and during the main event)

**Yes, this happens at battleship scale, and it is the first thing an observer sees.** It is the same thing as the hatch jets in a tank cook-off ("jack-in-the-box"), only bigger and longer.

| Case | What was seen | Reading |
|---|---|---|
| **Arizona** | "A large visible flame fronting turret number one a **half-second** before the magazine explosion" ([USNI 1997](https://www.usni.org/magazines/proceedings/1997/december/seven-seconds-infamy)) | A jet from openings at the turret: ports, hatches, the hoist. It came before the boundaries gave way |
| **Hood** | First flame "from the vicinity of the mainmast", which **vented through the engine-room ventilators** (07 §1) | A jet from a ventilator far from the turret, at the end of a gas path through the ship |
| **Lion** Q | The flame went "upwards through the roof of the turret by the hole made by the enemy shell-burst" | A single opening carrying the whole column |
| **Indefatigable** | "Smoke and flames gushed from the forward part of the ship" before the large pieces were thrown | Jets, then the break-up |

**Why it happens [INFERRED from 07 §2.3–2.4]:**

- In the mechanics model the openings are the first boundaries to fail: flash doors, scuttles, hoist trunks, hatches, sighting hoods and ventilators, all at < 1 bar.
- The turret lifts at ~1.3 bar, and decks and sides go at 5–15 bar.
- The magazine is big and the burn has to race the vents, so the build-up between "first opening" and "turret lifts" lasts **tenths of a second to about a second**. In a tank the same gap is a few milliseconds to a second.
- Gas at 1–3 bar absolute leaves an opening close to the speed of sound.
- **Propellant gas is fuel-rich** (CO, H₂). When it mixes with air it burns a second time, the same thing as a gun's secondary muzzle flash, "caused by the mixture of fuel-rich gases and oxygen in the atmosphere surrounding the muzzle" ([muzzle flash](https://military-history.fandom.com/wiki/Muzzle_flash)). So each opening fires a **directional flame jet** much longer than the opening is wide.

**Jet length [INFERRED, tuning value]:**

```
L_jet ≈ C · d · sqrt(P / p₀),    C ≈ 40–50,    capped per opening (L_max)
```

- d is the opening's equivalent diameter. `d·sqrt(P/p₀)` is the usual "notional nozzle" scaling for jets from a pressurised opening.
- C ≈ 45 is chosen so that a ~1 m opening at 2–3 bar gives 60–80 m, the scale of Lion's "200 ft". Real momentum jet flames run L/d ≈ 100–200 for hydrocarbons; diluted CO/H₂ propellant gas should be shorter.
- For large openings (an open barbette, 8.5 m) the length is limited by buoyancy and supply, not momentum. Cap them with the Heskestad column from §2.1 (≈ 60–120 m).
- Jet **direction** = the opening's normal: gun ports along the barrels (horizontal), hoods and hatches straight up, side scuttles sideways, ventilators up through the deckhouse.

**Data the mechanics resolver should hand to VFX, per opening:**

```
Opening { pos, dir, d_equiv, P_fail, L_max }      # from the boundary list (07 §6.1 boundaries[])
fail time t_i  = first t where P(t) > P_fail(i)   # from the ODE
P(t)           = magazine pressure                 # drives every jet's length, live
```

Each jet then lives for `t ∈ [t_i, t_main + ~0.5 s]`.
- **A violent event** (tier 3/4) ends the phase: the turret lifts and the fireball swallows the jets.
- **A burn-out** (tier 1/2): pressure plateaus, the jets keep going for seconds, and the barbette column takes over (§2.1).

**Rendering:**

- **Emitter:** spawn puffs **along the jet axis** each frame (a "spawn along a line" GPU emitter). Use a cone: radius `0.45 d + 0.06 s L` at fraction s, lateral jitter 1.5–8 % of L.
- **Puffs:** very hot (T ≈ 1 at the exit, 0.7 at the tip), 0.1–0.3 s cooling, 0.6–1.8 s life, then they drift up as light smoke.
- **Sparks:** burning grains thrown from each opening at 15–40 % of the jet speed.
- **Light:** each jet is a strong emitter, so the fire point light (§3.3) jumps at the first jet. That is the "precursor flash".
- **Count:** ~10 openings per magazine group is plenty. Only openings on the camera's side need full detail.
- **Cost:** ~20–40 puffs per jet live at once, so ≤ ~400 particles for the phase. Smaller than the fireball.
- **Top-down / oblique view:** horizontal port jets read best, as long straight streaks along the guns. Vertical jets rise up the screen like small columns. All of them cast short shadows.

**Prototype sequence** (`magazine_jet_clip.py`, aft group, guns trained aft; times after first ignition):

| t | Opening |
|---|---|
| 0.00 s | Y-turret gun ports (3) |
| 0.05 s | Y sighting hood |
| 0.10 s | X-turret ports (3) |
| 0.12–0.17 s | Four deck hatches/ventilators over the magazine |
| 0.22 s | Three side scuttles |
| 0.35 s | Engine-room vents at the mainmast (Hood) |
| 0.45 s | Y gunhouse roof lifts, and the barbette becomes an opening (d 8.5 m, capped at 120 m) |
| 0.90 s | Fireball (M = 20 t), debris |

P rises to 3 bar at 0.9 s, then vents down with τ ≈ 0.7 s.

---

## 3. Rendering in a top-down game

### 3.1 Projection: oblique for vertical VFX **[INFERRED, tested in the prototype]**

Three options, compared at the same moment in `magx_projection_compare.png`:

| Option | Look | Problem |
|---|---|---|
| **Pure top-down orthographic** | The column is a disc. The cap covers the burning ship. Only the shadow shows height | The flame column is invisible, and it hides the ship |
| **True perspective lean** (camera at height H) | Columns lean away from the screen centre | At the centre of the screen nothing leans, and the player is looking there. Real smoke columns (1 km) are taller than a camera framing ~900 m of sea (H ≈ 800 m): the camera would be inside the smoke |
| **Oblique "3/4" for VFX** — `sx = x`, `sy = y + k·z'` | The column rises up the screen, the cap sits above the ship and the fire's reflection hangs below it | Not physically consistent with the top-down ships. In practice this reads as normal: 2D RTS and top-down shooters have drawn tall things this way for decades |

Recommended settings:

- **k ≈ 0.6.**
- **Height compression** `z' = H_c(1 − e^(−z/H_c))` with H_c ≈ 450 m, so a 1.5 km cloud still fits on screen.
- **Sorting:** sort particles by world z. In oblique projection that is the correct front-to-back order along each screen ray.
- **Shadows** use true 3D and the sun direction. Shadow and column then point different ways, which helps the 3D read.
- **One global "VFX up" axis.** Apply the same projection to every vertical effect (muzzle smoke, funnel smoke, shell splashes, steam) so they all agree.
- **Sinking-doc pseudo-perspective** (`scale = 1 + Z/H_cam`) can stay for hull pieces; it only matters for a few tens of metres.

### 3.2 Smoke shadow on the water

This is the cheapest strong cue, and good enough as an analytic proxy:

- **Option A (cheapest):** one ellipse per stem segment plus one per cap, projected along `−sun.xy/sun.z · z` onto the water, soft-edged and multiplied in. Proxies come from the particle system's bounds (stem capsule, cap ellipsoid).
- **Option B (prototype):** splat smoke puffs into a low-res density volume (16 m voxels, ~64×64×64 around the event) and sweep optical depth toward the sun (one compute pass, 64 slices). This gives the ground shadow **and** per-puff sun transmittance.
  - Sample the transmittance on the puff's sun-facing surface (`pos + sun·r`), not its centre.
  - Scale the optical depth by ~0.3 to account for multiple scattering. Without both of these, a thick cap goes black.
- Darken the water to ~30 % under full shadow. The sinking doc's sprite shadow already uses the same direction.

### 3.3 Fire light

- **Point lights:** 1–4, at emission-weighted centroids of hot particles. Intensity is Σ T³·m·r² (or just the flipbook emissive integral). Light ships and water with `I·(z/d)³` falloff, warm colour (blackbody ~0.55 on the ramp).
- **Smoke underlighting:** puffs near the fire get `firelit · crimson-orange` on the side facing the light. With 6-way lightmaps this is just one more light. It is what makes the cap glow at dusk.
- **Reflection on the water:**
  - In oblique view, the mirror image of a light at height Lz sits at `(x, y − k·z'/2…)` on screen, below the base. Draw it as a glint ellipse stretched down the screen, multiplied by the water normal/ripple noise so it breaks into dashes.
  - Better: **re-draw the emissive VFX layer flipped about its base** (`sy = y − k·z'`) at quarter resolution, distorted by the water normals, into the water's emissive. This is a planar reflection of the VFX layer only. At night it doubles the column.
- **Exposure flash:** at ignition, a 0.2–0.5 s global ambient pulse (warm), scaled by λ and distance. Arizona's half-second precursor flash can be a smaller first pulse.

### 3.4 Particle layers

| Layer | Count (tier 3) | Lifetime | Material | Notes |
|---|---|---|---|---|
| Fireball puffs | 150–300 | t_fb·(0.35–0.95) cooling | Emissive flipbook (temperature in a channel → blackbody ramp), alpha rises as T falls (soot skin) | Hot core, cooler edges; hot "folds" where the noise is low |
| **Jet phase** (ports, hatches, hoods, ventilators, scuttles, barbette) | ~10 openings × 20–40 puffs live (≤ 400) | puffs 0.6–1.8 s, jets until t_main + 0.5 s | Emissive flipbook, spawn along the jet axis | §2.5. Hood: also the engine-room vents at the mainmast |
| Smoke stem and fires | 2–8 /s, decaying over ~40 s | until faint | 6-way lit flipbook, soot albedo 0.07 | Fed by the post-blast fire (wreck and oil) |
| Cap smoke | (fireball puffs turn into smoke) | 60 s+ | 6-way lit | Merge 4→1 as they grow (LOD) |
| Steam | 1–2 /s for ~12 s | | 6-way lit, albedo 0.8 | Boilers: the white mass is a great contrast |
| Debris | 30–80 | ballistic | Small sprite or mesh, emissive while hot | Collision with nearby ships |
| Debris trails | ribbon per piece, or 5–10 puffs/s per piece for ≤ 6 s | 3–10 s | Soot, emissive at the head | The "octopus" |
| Sparks | 200–2000 | 1.5–3.5 s | Additive, no sorting | |
| Turret / roof | 1–2 | ballistic | Gunhouse sprite rotating in 3D | Lands near or on the wreck (07 §4.4) |

**Flipbooks** (the art quality comes from here; the prototype's noise only stands in for them):

- Bake **2–4 fireball sequences and 2–3 billowing-smoke sequences** in EmberGen, Houdini or Blender, 8×8 frames at 128–256 px per frame, with **motion vectors** for frame blending.
- **6-way lightmaps:** two RGBA textures hold the response to light from ±X, ±Y and ±Z, plus alpha and emissive. Cost is "comparable to a traditional lit sprite", and they give internal shadowing and rim light when backlit ([Unity blog](https://unity.com/blog/engine-platform/realistic-smoke-with-6-way-lighting-in-vfx-graph); [docs](https://docs.unity3d.com/Packages/com.unity.visualeffectgraph@17.0/manual/six-way-lighting.html)). Exporters exist for Houdini and Blender, and EmberGen has an unofficial "Six point" option.
- **Temperature as a channel:** remap it at runtime through the crimson blackbody ramp. The same smoke flipbook then becomes fireball or cooling soot depending on the particle's T. That is exactly what "emissive gradients to transform smoke into explosions" means in the Unity doc.
- **Viewing angle:** bake the flipbooks **from the oblique camera angle** (≈ 30–40° from vertical). The puffs are then seen from the same direction the projection implies.

**Rejected for runtime: true volumetrics.** Sparse volume textures and heterogeneous volumes (Unreal) play back VDB sims, but they are documented as **experimental**, memory-heavy and blocky when volumes overlap ([Epic docs](https://dev.epicgames.com/documentation/en-us/unreal-engine/heterogeneous-volumes-in-unreal-engine)). They are fine for a cinematic replay camera, not for a fleet battle with several events at once.

### 3.5 Post

- **Bloom:** threshold just above white so only the fire blooms.
- **Heat haze:** a few distortion particles over the flame column and fireball, writing screen-space UV offsets.
- **Camera shake:** amplitude ∝ λ/distance, 0.3–0.8 s.
- **Sound:** sync with the audio doc's W^⅓ scaling. The bang arrives after `distance/c` seconds, a nice cue at long range.

---

## 4. Event timeline (map from mechanics tiers, 07 §6.3)

| t | Tier 1 (column) | Tier 3 (severed) | Tier 4 (disintegration) |
|---|---|---|---|
| −1…0 s (**jet phase**, §2.5) | Flash and jets from the turret ports, hood and hoist trunk | **Directional jets from every failed opening**: ports along the guns, hoods and hatches up, ventilators far along the ship, side scuttles; roof plates start to lift. This is the precursor flash (Arizona 0.5 s) | same, at each group |
| 0 | Gunhouse hop / roof plates off; jet starts | **Fireball** (M from the cascade window), side and deck jets, **blast frost ring** + scour foam, exposure flash, debris launch | 2+ fireballs 0.2–1 s apart along the hull; turrets thrown |
| 0–2 s | Column reaches L(Q) | Fireball grows to D in ~t_fb/2; vent jets from funnels and engine-room vents (Hood mainmast) | |
| 2–15 s | Column pulses with new charges; dark smoke above it; sparks | Fireball rises and darkens from the edge in (soot skin), crimson inside; debris tendrils arc; splashes | |
| 10–60 s | Burns out; turret smoulders; smoke drifts | Thermal cap rises to ~1 km and mushrooms; stem fed by fires; steam from the boilers; **hull break** visuals (sinking doc) start | Middle gone, both ends rise |
| 1–5 min | — | Pieces sink; oil fires, boils, slam; the pall drifts downwind for minutes | |
| Capsized ship explodes (Barham, Yamato) | — | Fireball **partly underwater**: dirty brown water dome + spray column, smoke bursts up through it, much smaller visible flame | |

---

## 5. Budget (estimates, 1080p, mid-range GPU)

| Item | How | Cost |
|---|---|---|
| Particle sim | GPU, ≤ 3k live per hero event | < 0.1 ms |
| Smoke and fire drawing | Half-res offscreen transparency, bilateral upsample; 6-way flipbooks | **0.5–1.5 ms, dominated by overdraw.** Cap the screen size of a puff; merge aged puffs |
| Sparks and debris | Additive / small sprites | < 0.1 ms |
| Shadow | Option A: analytic ellipses in the water shader (~free). Option B: 64³ density splat + sun sweep (compute) | ~0.05 / ~0.2 ms |
| Fire lights | 1–4 point lights in the water and sprite shaders | ~0.1 ms |
| Reflection | VFX emissive layer redrawn flipped at ¼ res, sampled with normal distortion | ~0.2 ms |
| Blast frost, foam, splashes | Existing event buffers (muzzle blast, foam channel) | ~free |
| Post | Bloom (exists), distortion, shake | ~0.1 ms |
| **Total, one hero event** | | **~1–2.5 ms** |
| Several at once / far away | LOD: no reflection, analytic shadow, 30 % of the particles, quarter-res | ~0.3 ms each |

**Texture memory:** ~6 flipbooks × 2 RGBA (6-way) at 2048² BC7 ≈ 6 × 2 × 4 MB ≈ 48 MB, or about half of that at 1024² per sheet. **[INFERRED]**

---

## 6. Prototype (`magazine_explosion_ref.py`)

CPU numpy stand-in for the GPU system:

- particles: fire, smoke, steam, debris, sparks;
- buoyancy from a slowly decaying heat content, drag toward a sheared wind, entrainment growth;
- poloidal circulation for the mushroom;
- splats sorted by z, composited "over";
- a 16 m density grid with a sun sweep for shadows;
- one fire point light;
- an oblique or perspective projection;
- bloom and a tonemap.

Scene: a 230 m capital ship. The aft magazine group (0.77 L) goes up with M = 20 t, with a vent at the mainmast (Hood-like). The tier 1 column is on a forward-midships turret at Q ≈ 1.6 GW (62 m flame).

**Findings**

- **The oblique projection is what makes it work.** Top-down: the cap sits on the ship (or, with a perspective lean, beside it) and the tier 1 column disappears under its own smoke. Oblique: flame at the base, smoke above it, ship readable, and the fire's reflection drops down the screen. Same particles, same frame (`magx_projection_compare.png`).
- **The tier 1 column is the best-looking result** (`magx_strip_column*.png`). At night, a 62 m crimson flame with sparks, a dark cap lit orange from below, and a broken reflection under it already looks right with nothing more than soft splats. At a 900 m framing it is small (a 230 m ship); it needs gameplay zoom, or a short automatic camera ease toward the event.
- **The shadow carries height in daylight.** The tier 3 shadow is ~1 km long by 15 s, far more legible than anything drawn on the cloud itself.
- **The time scales from the correlations feel right without compression.** The fireball glows for ~8–12 s (M = 20 t, t_fb = 12 s), the cap is mushrooming by 15 s, and the pall and steam dominate from 30 s. Arizona's "under seven seconds" is the violent part, not the whole event.
- **Debris tendrils and the white steam mass give the most structure** for the least cost. Keep both.
- **Weak spot: the fireball and cap read as smooth balls.** Overlapping soft splats average the noise away. This is exactly what baked 6-way fireball/smoke flipbooks with temperature channels fix, so don't judge the final look from these frames. Two lighting lessons do carry over:
  - Take sun transmittance at the puff's **sun-facing surface**, and soften optical depth (×0.3) for multiple scattering. Otherwise the cap goes flat black.
  - **Cool the fireball from the top and outside first** ("soot skin"), so crimson stays underneath. If you overdo it, the fireball dies in 4 s and the night shot loses its glow (tested).
- **Fire light needs restraint at night.** Strong irradiance turns the whole sea beige. Keep the diffuse term to a local pool and let the reflection carry the drama.
- **Prototype cost:** 1–20 s per frame on CPU depending on particle count (up to ~4k). On GPU the same work is particles plus one compute sweep.

**Jet phase test** (`magazine_jet_clip.py`, `magx_jet_phase_night.mp4`, 100 frames at 20 fps, night, from 600 m abeam at 18 m eye height):
- **The jets carry the first second.** They come out in a staggered sequence: horizontal tongues along the trained-aft guns, vertical jets from the hood and hatches, the engine-room vent column well forward of the turret, then the barbette column when the roof lifts. Together they read as "the ship is venting fire from everywhere" before the fireball, much more convincing than a fireball out of nothing.
- **Jets must be narrow:** about 2–8 % lateral spread, and puffs that die in about 1–2 s. The first try (13 % spread, long-lived puffs) gave fat blobs and 19k particles; the fix gave ~3.4k.
- **At a few hundred metres the scale lands.** The 120 m barbette column and the 60–90 m port jets tower over a 9 m freeboard hull, and their reflections double them.

**Not modelled:** the 6-way flipbooks themselves (fbm noise stands in), heat haze, the planar reflection pass (only a glint), hull-piece motion (sinking doc), underwater/capsized explosions, multiple fireballs for tier 4, debris collisions with other ships.

---

## 7. Next steps (Claude Code side)

1. **Expose from the mechanics resolver (07 §6.2):** per opening the position, direction, equivalent diameter and fail time, plus live P(t) for the jet phase (§2.5); per event the tier, ṁ_burn(t) and P(t) for the column, M_fast (propellant burned in the cascade window), failed boundaries with their positions (turret, sides, vents) and launch velocities, d_section for the debris count. VFX only consumes these.
2. **Add the global VFX projection** (oblique k, H_c) and switch funnel smoke and splashes to it, so every vertical effect agrees.
3. **Bake flipbooks** (2–4 fireballs, 2–3 smoke, 1 steam) with 6-way + temperature + motion vectors, from the oblique angle.
4. **Implement:** the particle emitters per §3.4, the analytic shadow (option A) first, fire point lights, and the reflection pass.
5. **Hook up** the muzzle-blast event (λ from M) and the foam channel.
6. **Tune against the anchors:** Lion (61 m column, seconds), Queen Mary (crimson flame to ~240 m, cap to ~1 km), Arizona (precursor flash 0.5 s, whole event < 7 s), Barham (turret roof lifted, smoke "thousands of feet").

## Sources

- USNI Proceedings (1925), *Lessons of Jutland affecting design of turret armor* — https://www.usni.org/magazines/proceedings/1925/april/lessons-jutland-affecting-design-turret-armor
- USNI Proceedings (1997), *Seven Seconds to Infamy* — https://www.usni.org/magazines/proceedings/1997/december/seven-seconds-infamy
- Devon Heritage, HMS Lion at Jutland — https://www.devonheritage.org/Places/DevonCounty/JutlandHMSLion.htm
- The War Illustrated, "I saw one vast explosion: the Hood had gone" — https://tracesofwar.nl/thewarillustrated/94/i-was-there-i-saw-one-vast-explosion-the-hood-had-gone.asp
- Hampshire Prints, HMS Barham caught on camera — https://www.hampshireprints.co.uk/blogs/royal-navy-warship-and-submarine-classes-complete-guide/hms-barham-04-the-only-battleship-sinking-ever-caught-on-camera
- Wikipedia: [HMS Indefatigable](https://en.wikipedia.org/wiki/HMS_Indefatigable_(1909)), [HMS Queen Mary](https://en.wikipedia.org/wiki/HMS_Queen_Mary)
- AIDIC Chemical Engineering Transactions vol. 82 (2020), fireball correlations — https://www.aidic.it/cet/20/82/036.pdf
- Heskestad flame height — https://calculator.academy/flame-height-calculator/
- Huppert, lecture notes on plumes (entrainment scaling) — https://dennou-h.ep.sci.hokudai.ac.jp/arch/fdeps/2004-12-06/huppert/lecture4/pub/Japan4.pdf
- Unity, 6-way lighting in VFX Graph — https://unity.com/blog/engine-platform/realistic-smoke-with-6-way-lighting-in-vfx-graph and https://docs.unity3d.com/Packages/com.unity.visualeffectgraph@17.0/manual/six-way-lighting.html
- Epic, Heterogeneous volumes in Unreal Engine — https://dev.epicgames.com/documentation/en-us/unreal-engine/heterogeneous-volumes-in-unreal-engine
- Muzzle flash (secondary flash from fuel-rich gases) — https://military-history.fandom.com/wiki/Muzzle_flash
- Project: `claude/damage-research/07_magazine_explosions.md`, `claude/muzzle-blast-water-vfx.md`, `claude/sinking-vfx-research.md`, `claude/sound-design-gunfire.md`, `claude/sprite-pipeline.md`