# Open-ocean surface (sea states) — research + prototype (2026-10-07)

Companion to `claude/wake-vfx-research.md` (ship wakes) and `claude/sinking-vfx-research.md` (slicks, debris). Reference prototype: `claude/sea_state_lab.html` (WebGL2, single file, ~450 lines; the same page is published as the "Sea State Lab" artifact).

Goal: an always-on water surface for every sea state, cheap enough to never think about, that holds up across the game's whole zoom range: from orbit (~1 km per pixel) down to peering at parts of a ship (~1 cm per pixel). Camera is strictly top-down orthographic; ships are sprites drawn over the water.

Tags as in the other docs: **[MEASURED]** = run in the prototype, **[INFERRED]** = my reasoning/estimate, **[UNCERTAIN]** = thin sources.

---

## 0. TL;DR for the implementer

1. **Top-down changes the problem.** From straight above, wave *height* is almost invisible. What reads is (a) the slope field through Fresnel/sky and sun glint, (b) foam, (c) a little horizontal "choppy" displacement. So: **no water mesh at all.** One full-screen pass shades the sea per pixel from slope/foam textures. Geometry is only needed for ship buoyancy, and that comes from a CPU evaluation (§5.2).
2. **Wave model: Tessendorf FFT, 3 cascades, JONSWAP + swell, driven by Beaufort.** Spectral synthesis makes sea state a parameter (wind speed, fetch, swell) instead of hand-tuned Gerstner sets, and the FFT cost is fixed regardless of how many wave components exist. Cascade tiles 1987 m / 251 m / 31.7 m, band-split at 4 tile-wavelengths so no wave is counted twice.
3. **The zoom range is solved by filtering, not by LOD switching.** Store *slope moments* (sx, sz, sx², sz²) in mipmapped textures (LEAN mapping). Hardware trilinear filtering then turns unresolved waves into BRDF roughness automatically. This is the Bruneton–Neyret–Holzschuch geometry → normal → BRDF chain, minus the geometry. Waves too small for any cascade are added as roughness, topped up to the **Cox–Munk** measured slope variance for the wind speed, so the orbit view's sun-glint patch has the physically observed size.
4. **Tiling is killed by hex-tile bombing on the two big cascades** (§3.2): every hexagonal cell (~0.6 tile across) samples the FFT tile at its own random offset and a small rotation, blended so contrast is preserved. Repetition score at 5 m/px, Beaufort 8: **0.60 → 0.01 [MEASURED]**. The smallest cascade still fades to its 1×1-mip statistics once its tile is under ~48 px on screen. "Gust patches", a 1–9 km noise that modulates roughness and foam, add realistic large-scale variation (cat's paws, wind streaks).
5. **Foam = Jacobian of the choppy displacement, with persistence, auto-calibrated to a stylised whitecap target**: 0.35 × Monahan's W (W = 3.84·10⁻⁶·U¹⁰·⁴¹), capped at 12 %. Full Monahan coverage looked too foamy in the game view, so the user OK'd less foam than reality. A feedback loop adjusts the Jacobian threshold until rendered coverage matches; it lands within ±1 % of target at Beaufort 3–11 **[MEASURED]**. Seed threshold 0.79. Whitecaps are soft multi-metre patches (coarser foam mip), streaked along the wind, and clustered in wave groups (§3.3).
6. **Cost [MEASURED on RTX 4090, 2.2 Mpx, WebGL2]:** FFT sim 0.59 ms per frame (fragment-shader FFT, 3 cascades, N = 128, every frame); shading 0.17 ms without hex bombing, 0.34 ms with it (5 m/px), 0.37 ms at ship zoom. A modest GPU is roughly 6–8× slower, so ≈ 2–3 ms for shading at 1080p plus the sim **[INFERRED scaling]**. A compute FFT at 30 Hz cuts the sim to a fraction. See §4.2 for where the shading budget goes.

---

## 0.1 Verification setup

Measurements marked [MEASURED] after 2026-10-07 13:00 were run on the user's RTX 4090 through the Claude desktop app's browser. Earlier ones were run in a CPU software rasteriser. The image-repetition metric is the autocorrelation at the tile lattice minus the off-lattice background, on a Hann-windowed screenshot.

## 1. Options compared

| Approach | Sea-state control | Per-frame cost | Zoom range | Verdict |
|---|---|---|---|---|
| Scrolling normal-map sprites | Artistic only | ~0 | Tiles and aliases badly | Too fake for a naval game |
| Sum of Gerstner waves (vertex or pixel) | Hand-tuned per state; unclear how to map to Beaufort | O(waves) per pixel; 30+ waves needed for a real sea | Needs per-band fading | OK for a few swell trains, not for wind sea |
| **FFT spectral (Tessendorf), multi-cascade** | Physical: U10, fetch, swell Hs/Tp/dir | O(N² log N) per cascade, independent of wave count | With slope-moment filtering, seamless | **Recommended** |
| FFT baked to a looping texture array | Same | Near zero | Same | Memory-heavy (§4.3); only for a lowest tier |
| Wave particles / heightfield sim | Interactive | Higher | Local only | Only for wakes/splashes on top (see wake doc) |

Production precedents: Atlas (GDC 2019) uses the Tessendorf spectrum → evolve → inverse FFT pipeline and notes it depends only on absolute time and spectrum parameters, so server and clients agree. Their stated weaknesses are lack of detail and tiling, which §3 addresses. GodotOceanWaves (open source) is a good modern reference: Stockham FFT in compute, several cascades, Jacobian foam, Atlas-style BSDF.

## 2. Sea-state model

### 2.1 Spectrum

- **Wind sea: JONSWAP**, fetch-limited: α = 0.076·(gF/U²)^−0.22, ωp = 22·(g²/UF)^⅓, γ = 3.3.
- **Cap at full development (Pierson–Moskowitz):** ωp ≥ 0.855 g/U10, α ≥ 0.0081, and γ fades from 3.3 to 1 as ωp approaches the PM value. Without the γ fade the developed sea comes out ~20 % too high.
- **Directional spreading:** Longuet-Higgins cos^2s(θ/2), normalised, with Mitsuyasu's frequency-dependent s (s_p = 11.5·(ωp U/g)^−2.5, ∝ (ω/ωp)⁵ below the peak, ∝ (ω/ωp)^−2.5 above). The Horvath (2015) paper surveys these spreading functions for graphics and adds a "swell" elongation parameter; worth reading before tuning.
- **Swell:** a separate narrow JONSWAP (γ = 5, s = 40) scaled to a target Hs, with its own Tp and direction. Swell usually comes from a different direction than the local wind; that cross-sea is a big part of what makes the surface read as "ocean".
- **Sign convention (bug found and fixed 2026-10-07):** with an inverse FFT using e^(+ik·x), evolve as h(k,t) = h0(k)·e^(−iωt) + h0*(−k)·e^(+iωt). Tessendorf's notes write e^(+iωt) for the first term, which makes the h0(k) term travel along −k. His (k̂·ŵ)² spectrum is symmetric, so this doesn't show there, but with a one-sided spreading function (cos^2s(θ/2), as here) the waves travel **upwind**. The prototype had this flip; the user spotted it. **[MEASURED]** with wind from N, the height field moved 3.9 m north in 0.4 s before the fix and 3.9 m south after. Add this direction check as a unit test next to the variance check.
- **Phases are fixed per cascade (seeded RNG); only amplitudes change with sea state.** So weather can change continuously without the pattern popping. Lerping h0 between two states is also valid.
- Amplitude: h0(k) = (ξ₁ + iξ₂)·½·√P(k), P(k) = S(ω,θ)·(dω/dk)/k·Δk². This makes realised height variance equal Σ P. **[MEASURED]** realised/expected variance per cascade: 1.02, 0.94, 0.86 at N = 128 (and similar at 64/256; cascade 2 has the largest sampling scatter). A first version had a factor-2 error here; the variance check is worth keeping as a unit test.

### 2.2 Beaufort mapping

Fetch 150 km tracks the WMO "probable" open-sea wave heights well up to Beaufort 8 and undershoots storms, which in reality have longer fetch and duration. Recommended: fetch ≈ 150 km up to Bft 8, then raise it towards 300–1000 km, or drive it from weather data.

| Bft | U10 m/s | Hs @150 km | Tp | Hs fully developed | WMO probable | Cox–Munk mss | Monahan W | foam J-threshold seed |
|---|---|---|---|---|---|---|---|---|
| 1 | 1.5 | 0.05 m | 1.1 s (dev.) | 0.05 m | 0.1 m | 0.011 | 0.002 % | 0.64 |
| 2 | 3.3 | 0.24 m | 2.5 s (dev.) | 0.24 m | 0.2 m | 0.020 | 0.023 % | 0.66 |
| 3 | 5.4 | 0.65 m | 4.0 s (dev.) | 0.65 m | 0.6 m | 0.031 | 0.12 % | 0.68 |
| 4 | 7.9 | 1.40 m | 5.9 s (dev.) | 1.40 m | 1 m | 0.043 | 0.44 % | 0.71 |
| 5 | 10.7 | 2.43 m | 7.3 s | 2.57 m | 2 m | 0.058 | 1.2 % | 0.74 |
| 6 | 13.8 | 3.33 m | 7.9 s | 4.28 m | 3 m | 0.074 | 3.0 % | 0.77 |
| 7 | 17.1 | 4.31 m | 8.5 s | 6.56 m | 4 m | 0.091 | 6.1 % | 0.81 |
| 8 | 20.7 | 5.11 m | 9.1 s | 9.62 m | 5.5 m | 0.109 | 11.8 % | 0.85 |
| 9 | 24.4 | 5.91 m | 9.6 s | 13.4 m | 7 m | 0.128 | 20.7 % | 0.89 |
| 10 | 28.4 | 6.76 m | 10.1 s | 18.1 m | 9 m | 0.148 | 34.7 % | 0.93 |
| 11 | 32.6 | 7.64 m | 10.6 s | 23.9 m | 11.5 m | 0.170 | 55.5 % | 0.98 |
| 12 | 36 | 8.34 m | 10.9 s | 29.1 m | 14 m | 0.187 | 60 % (capped) | 1.02 |

Mean-square slope (mss) is Cox & Munk's clean-surface fit, 0.003 + 0.00512·U, split as upwind 0.00316·U and crosswind 0.003 + 0.00192·U. Monahan & O'Muircheartaigh's 1980 power law is clamped at 60 %. Both are wind-speed only; neither knows about fetch or swell **[UNCERTAIN at the extremes: Monahan scatter is large and the formula was fitted mostly below ~20 m/s]**.

### 2.3 Cascades

| Cascade | Tile | Wavelength band | Texel at N = 128 |
|---|---|---|---|
| 0 | 1987 m | > 63 m (swell, wind-sea peak) | 15.5 m |
| 1 | 251 m | 8–63 m | 2.0 m |
| 2 | 31.7 m | 8 m down to Nyquist (0.5 m at N = 128) | 0.25 m |
| 3 (ripples) | 4.0 m | cascade-2 texture resampled ×7.93 | 3 cm |

- Band split at k = 2π·4/L_next. Each wave lives in exactly one cascade; each cascade resolves its band with ≥ 4 texels per wavelength.
- Tile sizes are deliberately non-commensurate.
- **Cascade 3 is free:** cascade 2's slope texture sampled at 1/7.93 scale, with its amplitude set so it takes half of the remaining Cox–Munk budget. It gives visible capillary detail at deck zoom, and its variance moves from BRDF into visible normals as you zoom in. At 1/7.93 scale its pattern drifts at 1/8 of cascade 2's phase speed, which is roughly right for short gravity–capillary waves (~0.2 m/s) **[INFERRED]**.

## 3. Rendering across a 10⁵ zoom range

### 3.1 Per pixel (one full-screen pass)

1. **Undo choppy displacement:** sample the three displacement maps at the pixel, step back once (q = p − D(p)), and sample everything at q. One fixed-point iteration is enough for λ ≤ 1.2.
2. **Sample moments** with `textureGrad` using the analytic footprint (metres/pixel ÷ tile). Top-down ortho has an isotropic footprint, so no anisotropic filtering is needed.
3. **Combine:** mean slope m = Σ E[s]; variance σ² = Σ (E[s²] − E[s]²) + unresolved top-up, per axis. The off-diagonal term is dropped; LEAN supports it if anisotropy along a diagonal ever matters.
4. **Light:** Fresnel-weighted sky reflection, plus a **Cox–Munk sun-glint** term, `E_sun · F(v·h) · p(slope_h − m; σ²) / (4 μ_v μ_h⁴)`, with p an anisotropic Gaussian; plus a dark water-body term. This is the Bruneton ocean BRDF with a Gaussian slope PDF.
5. **Foam** (§3.3), then the ship sprites and wakes on top.

**Glint eye.** With a true orthographic camera the view vector is the same for every pixel, so the sun glint would be uniform across the screen. The prototype shades with a *virtual* perspective eye above the screen centre (FOV slider, 40° default). The glitter path then moves across the sea with the sun, and from orbit you see a sun-glint patch exactly where satellites see one. Shading only; geometry stays orthographic. Set FOV 0 to compare with true ortho.

### 3.2 Anti-tiling

**Hex-tile bombing on cascades 0 and 1 [MEASURED].** The earlier "shifted copy" blend failed at 5 m/px: a shifted copy of a periodic texture repeats with the same period, so the 251 m tile still read as a grid (~35 copies on screen). The fix follows Mikkelsen 2022 (JCGT, *Practical Real-Time Hex-Tiling*):

- A triangular lattice with spacing S = 0.6·L. Each pixel finds its 3 nearest hex centres and barycentric weights, sharpened with w³ and renormalised so seams are narrow and ghosting is low.
- Each hex samples the tile with its own random UV offset and a small rotation: ±12° on the 1987 m cascade, ±20° on the 251 m one. Swell direction stays coherent, short waves stay isotropic-looking.
- **Slopes and displacements are rotated back** to world space. **Second moments are rotated** with cos²/sin² (cross term dropped). This keeps the LEAN filtering correct.
- **Contrast-preserving blend:** means are divided by √Σw² (variance-preserving), second moments and foam are blended linearly. Without this, slope contrast dips at the seams and the hex lattice itself shows.
- Hex cells are evaluated once at the pixel and reused for the displacement-corrected lookup.
- Hex-bombed cascades no longer need the "pattern → statistics" fade, so mid zoom keeps visible whitecap texture instead of a flat veil.

Measurements: an autocorrelation peak at the tile lattice minus off-lattice background, at Beaufort 8.

| Zoom | Before | After |
|---|---|---|
| 5 m/px, shaded | +0.60 | +0.01 |
| 5 m/px, foam | +0.60 | +0.01 |
| 10–20 m/px | +0.01–0.04 | ≈ 0 |

The hex lattice itself measures ≈ 0 (≤ 0.004).

**Other rules:**
- **Pattern → statistics** for cascade 2 only: it fades to its 1×1-mip moments as its 31.7 m tile shrinks from 48 to 20 px.
- **Gust patches:** a 3-octave noise (9 km, 2.25 km, 0.56 km) scaling slopes and foam by ±55 %. Every procedural noise octave fades to its mean once its cells are under ~6 px.
- **Every procedural offset is camera position mod an exact multiple of its period** (hex offsets wrap on 256 hash cells), so precision doesn't degrade as the camera travels.
- Tried and rejected: **crest clustering** (modulating whitecaps by the height of the 2 km waves). It adds a large-scale pattern, but at 5 m/px it reads as blotchy patches. It is left as a slider at 0.

### 3.3 Foam

- **Source:** the Jacobian per cascade, J = (1 + λJxx)(1 + λJzz) − λ²Jxz². Source = smoothstep(0, 1, (thr − J)·7).
- **Persistence:** f = max(f_prev·e^(−dt/τ), source), τ ≈ 4 s, ping-pong per cascade.
- **Only cascade 1 (251 m tile) makes visible whitecaps.** Cascade 0's 15 m texels made fog-like blobs, and cascade 2 (< 8 m waves) scattered uniform speckle.
- **Whitecaps as patches, not texels.** Foam is sampled from cascade 1 with an LOD bias of +1.5 (gradient × 2.8), using a separate hex lookup of the foam channel only (3 fetches). Each whitecap becomes a soft ~6 m patch, and the breakup noise carves the edge. Mips are mean-preserving, so coverage is unchanged. Before this, Beaufort 9–11 looked like salt: one 2 m blob per texel, everywhere.
- **Streaks along the wind, moving with the water.** The breakup noise is rotated into wind axes and stretched 2× along / ½ across. It is sampled at the **Lagrangian (wave-displaced) position q**, so foam rides the orbital motion of passing waves, plus a slow downwind drift of 0.03·U10 + 0.2 m/s (surface foam drift). Before, the noise was pinned in world space: whitecaps flickered under fixed outlines instead of moving. **[MEASURED]** frame-to-frame foam correlation at zero offset after 1.5 s: 0.80 before (static) → 0.45 after.
- **Wind-axis offsets wrapped per axis.** The camera is rotated into wind axes on the CPU and wrapped on whole noise periods per axis (along 409.6·streak, across 409.6/streak). The earlier world-space wrap jumped when panning past it with a diagonal wind.
- **Wave groups (travelling downwind at the peak waves' group speed c_g = g/(2ω_p)).** Coverage is multiplied by a group factor n²/E[n²] (mean 1). n is quintic value noise with cells of 1.6 × the peak wavelength across the wind and 3.5 × along it, blended in at strength 0.4. This gives the distant view structure: whitecaps cluster in bands, as in aerial photos. Without it, foam at 5 m/px averages into an even grey veil.
- **Gust modulation is mean-preserving:** amp^2.5 is divided by its mean (~1.2). It had inflated coverage by ~1.5×.
- **Distant foam dimmed** to 45 % between 1.5 and 10 m/px (artistic, per user OK). Area-averaged foam is mostly thin decaying foam, which is greyer than active whitecaps, so this is also defensible physically **[INFERRED]**.
- **Subtle by design (background element):** foam opacity is capped at 70 %, distant foam is dimmed to 35 %, and the coverage target is 0.25 × Monahan W, capped at 8.6 %. Rendered texture coverage on target: 0.11 / 1.5 / 5.2 / 8.7 % at Bft 5 / 7 / 9 / 11. The earlier 0.35 setting is in the table below.
- **Previous coverage target:** 0.35 × Monahan W, capped at 12 %. The prototype has "Foam amount" and "Wave groups" sliders. Converged threshold is 0.76–0.82 at every Beaufort, so a constant seed of 0.79 works:

  | Bft | Monahan W | Target | Rendered (texture) |
  |---|---|---|---|
  | 3 | 0.12 % | 0.04 % | 0.03 % |
  | 5 | 1.2 % | 0.44 % | 0.43 % |
  | 7 | 6.1 % | 2.2 % | 2.2 % |
  | 9 | 20.7 % | 7.2 % | 7.3 % |
  | 11 | 55 % | 12 % (cap) | 12.0 % |

  **[MEASURED]**
- **Close-up breakup, mean-preserving:** a 4-octave noise (1.6 m → 2.5 cm cells), each octave fading to its mean when sub-pixel. The threshold sits at the (1 − coverage) quantile of the still-resolved noise (logistic inverse-CDF approximation with the tracked spread), so breakup changes foam *shape* but not its average. The wake doc's old formula is not mean-preserving: it dropped 12 % coverage to 4 % at 1.5 m/px. Wake foam should use the same formula.
- **Cost of all foam changes:** +0.03–0.05 ms on the RTX 4090 at 2.2 Mpx, within measurement noise **[MEASURED]**.
- **Remaining look issue:** Beaufort 9+ at 5 m/px still reads pale. That is foam bands plus strong sky reflection off a rough surface. It's plausible for a gale; turn "Foam amount" down if the game wants darker storms.

## 4. Cost

### 4.1 Prototype pass structure

- Per cascade per sim step: 1 spectrum pass (writes 8 real fields packed as 4 complex fields in 2 RGBA32F MRT), 2·log₂N radix-2 Stockham passes, 1 combine pass, and 2 mip generations.
  - N = 128: 16 passes per cascade, 48 total.
  - Texture memory at N = 128: ~1.5 MB (the panel shows it per size).
- Shade pass: ~20 fetches per pixel (3 displacement, 6 moments/foam, 4 tile-break, 6 top-mip constants that are cache hits, 1 ripple) and ~150 ALU ops.

### 4.2 Measured cost and engine recommendations

**[MEASURED]** RTX 4090, WebGL2 in the Claude desktop app's browser, 1091×1976 canvas (2.2 Mpx), Beaufort 5–8, GPU timer queries (±0.05 ms noise):

| Part | Cost |
|---|---|
| FFT sim, 3 cascades, N = 128, fragment-shader FFT, every frame | 0.59 ms |
| Shading at 5 m/px, no hex | 0.17 ms |
| Shading at 5 m/px, hex bombing | 0.34 ms |
| Shading at 0.35 m/px, hex bombing | 0.37 ms |

Skipping the choppy-displacement inversion beyond 1.5 m/px (faded, not popped) saved ~0.1 ms at mid zoom; displacement is sub-pixel-ish there anyway.

Scaling to a modest GPU (~1/6–1/8 of a 4090) gives ≈ 2–3 ms of shading at 1080p plus the sim **[INFERRED]**. That is more than "free", so:

- Do the FFT in **compute**: one dispatch per axis per cascade, a whole row in groupshared memory. That is ~2 dispatches per cascade instead of 14–16 passes, with ~8× less bandwidth. Use **RGBA16F** for the working set. **Update at 30 Hz** (15 Hz for cascade 0).
- **Skip cascades by zoom:** past the zoom where a cascade is pure statistics, its sim and lookups can stop.
- **Hex bombing only where it's needed:** repetition is only visible when ≳ 4 tiles fit on screen. Gating it per cascade by tile size in pixels would remove its cost at ship zoom. The switch needs a crossfade or it pops; not done yet.
- **Shade at half resolution** at far zoom: the water is statistically smooth there. Combine with a full-res foam/glint pass if needed.

### 4.3 Baked looping option (lowest tier)

Quantising ω to multiples of 2π/T makes the field exactly periodic in T. The prototype's "Loopable dispersion (T = 64 s)" checkbox shows the quantisation is invisible at T = 64 s. But baking 64 s at 15 fps is 960 frames × 3 cascades × 128² × 16 B ≈ 750 MB, so **baking is not cheaper than computing the FFT live** at this quality. For a very low tier: bake cascades 1–2 with T = 16 s (short waves tolerate coarse ω steps) and do swell as 4–8 analytic Gerstner trains.

## 5. Integration with the other water systems

### 5.1 Shared water-layer contract

This proposal unifies the channels used in the wake and sinking docs:

| Channel | Ocean writes | Wakes / sinking write | Combine |
|---|---|---|---|
| Mean slope (xy) | FFT cascades | Wake η normals | Add |
| Slope variance (xy) | Cascade moments + Cox–Munk top-up | `roughness_delta` from wake turn slick and oil slicks | **Multiply** variance by (1 + delta), with delta < 0 for slicks. Oil and slicks damp the short waves, which is exactly the unresolved part |
| Foam coverage | Whitecaps | Crest / residual / wash foam | Max (or 1 − Π(1 − f)) |

All of it is shaded once by the same BRDF and the same foam breakup. A slick then shows correctly as a *darker, glassier lane with a tighter glint* at every zoom.

### 5.2 Buoyancy / sprite pose

- Don't read heights back from the GPU for gameplay.
- Evaluate the **K most energetic spectral bins** of cascades 0–1 on the CPU, e.g. K = 64–128, picked when the sea state changes. Same seeds and h0, so the large-scale motion matches the render exactly. Cost is K complex exponentials per probe point; use ~4 probes per ship (bow, stern, both beams) for heave, pitch and roll.
- Deterministic from (time, seed, sea state), so the server and every client agree with no sync traffic, the same property Atlas relied on.
- Short waves (cascade 2) don't move a ship.
- Hull sprites get the pose via the per-layer height table from the sinking doc.

### 5.3 Wake sim on top of swell

The wake doc's ship-following linear grid adds linearly to this field. Superposition is valid in linear theory, so no coupling is needed. The wake grid's sponge band should damp to *zero perturbation*, not to zero surface; it already does, since it simulates only the ship's contribution.

## 6. Known issues / next steps

- **Theatre zoom (10–50 m/px) in strong winds:** gust patches read a little like cloud shadows. Real imagery at that scale shows wind streaks (Langmuir rows) aligned with the wind. Next step: stretch the gust noise ×3–5 along the wind direction for Bft ≥ 6.
- **Bft ≥ 9 foam** has the right coverage and no longer repeats, but lacks the wind-aligned streaks (spindrift) real storms show. Add them as a separate long-lived foam texture stretched along the wind.
- **Cross-cascade Jacobian:** foam uses per-cascade J (standard approximation). True J needs all three displacement derivatives summed; that costs one more combine pass.
- **Sky:** a gradient placeholder. Plug in the game's sky model; reflection is only ~2 % of radiance from top-down, so it matters less than the water-body colour and glint.
- **Water body colour** is a constant deep-ocean navy. It could come from a chlorophyll / region map (green coastal, deep blue tropics).
- **Planet curvature** is ignored. At 1.7 km/px the view is ~2000 km across, where the horizon starts to matter; clamp max zoom or add a spherical mapping (Proland's ocean does this).
- **Prototype hull** is a placeholder planform only, for scale.

## Sources

- Tessendorf, *Simulating Ocean Water* (SIGGRAPH course notes) — https://jtessen.people.clemson.edu/reports/papers_files/coursenotes2004.pdf
- Bruneton, Neyret, Holzschuch, *Real-time Realistic Ocean Lighting using Seamless Transitions from Geometry to BRDF*, CGF 2010 — https://evasion.inrialpes.fr/Publications/2010/BNH10 ; slides — https://cgg.mff.cuni.cz/%7Ejaroslav/teaching/2012-npgr031/prezentace/Realtime%20Realistic%20Ocean%20Lighting.pdf ; Proland ocean (spherical, horizon) — https://proland.inrialpes.fr/doc/proland-4.0/ocean/html/page-examples.html
- Olano & Baker, *LEAN Mapping*, I3D 2010 (used for Civilization V's ocean) — https://userpages.cs.umbc.edu/olano/papers/lean/
- Dupuy et al., *LEADR mapping*, and SIGGRAPH 2014 PBS course slides (ocean filtering) — https://blog.selfshadow.com/publications/s2014-shading-course/dupuy/s2014_pbs_leadr_slides.pdf
- Horvath, *Empirical directional wave spectra for computer graphics*, DigiPro 2015 — https://doi.org/10.1145/2791261.2791267
- Mihelich & Tcheblokov, *Wakes, Explosions and Lighting: Interactive Water Simulation in Atlas*, GDC 2019 — https://gpuopen.com/gdc-presentations/2019/gdc-2019-agtd6-interactive-water-simulation-in-atlas.pdf
- GodotOceanWaves (Stockham FFT, cascades, Jacobian foam) — https://github.com/2Retr0/GodotOceanWaves
- Cox & Munk slope statistics (as tabulated by Hu et al. 2008, ACP 8:3593) — https://opac.geologie.ac.at/ais312/dokumente/copernicus.org/acp-8-3593-2008.pdf ; upwind/crosswind coefficients — https://apps.dtic.mil/sti/pdfs/ADA537951.pdf
- Monahan & O'Muircheartaigh 1980, whitecap power law (as used in Myrhaug et al. 2016) — https://czasopisma.pan.pl/Content/100159
- Mikkelsen, *Practical Real-Time Hex-Tiling*, JCGT 11(3), 2022 — https://jcgt.org/published/0011/03/05/
- Hasselmann et al. 1973 (JONSWAP); parameter forms as in ScientiMate — https://scientimate.readthedocs.io/en/stable/_sources/matlab_functions/water_wave_properties/jonswappsd.rst.txt