# Bow wave & wake VFX — research baseline (2026-10-05)

Hand-off for the Claude Code side. Goal: a cheap, good-looking **top-down** bow wave + wake system that reads like the reference photo (Finnish fast attack craft at speed, waterjets) and scales correctly across the parametric fleet (FAC → Fletcher → Iowa). It has to run in real time. Pre-baking is allowed, but the bake must also be fast (tens of ms, not minutes).

Reference code: `claude/wake_bake_ref.py` (numpy prototype, ~170 lines). Images from the prototype were delivered in chat (`wake_bake_nearfield.png`, `wake_bake_full.png`, and `wake_bake_nearfield_deck.png`, which draws the deck silhouette over a wake baked from the waterline; see §3.2 item 7).

---

## 0. TL;DR for the implementer

1. **From above, foam is what you see, not wave height.** Five visual parts, in order of importance: (a) the white **stern/propulsor wash** trail, (b) the **bow-wave sheet** climbing the forward hull, (c) the breaking **bow crest peeling off** the shoulder at a V angle, (d) **divergent Kelvin waves** shown only as light/dark shading streaks inside the V, (e) **spray** particles at the stem. Transverse waves are barely visible top-down; spend nothing on them.
2. **Everything scales with two numbers.** Length Froude number `Fr_L = U/√(gL)` sets the pattern shape. Bow-wave height `Zb` (Noblesse formula, §2.3) sets how white the bow is.
3. **Recommended pipeline:** *bake per (hull, speed bucket)* a ship-frame steady wake by **one FFT** (linear pressure-patch / Havelock model). It outputs a height field (→ normal map) and foam-density fields. Measured cost is **25–55 ms CPU (numpy, 512-class grid)** per bake; a GPU compute port would be ~1 ms. At runtime draw it as **(1) a near-field stamp quad attached to the ship** plus **(2) a trail ribbon** along the ship's position history, so turns bend the wake. Use a **world-space tiled foam texture** thresholded by the baked density for the detail.
4. **Don't lerp between speed bakes naively.** Wavelength ∝ U², so blending two bakes ghosts the crests. Either re-bake when speed changes by more than ~3–5 % (amortised, one ship per frame, crossfade 0.3–0.5 s), or blend in λ-normalised coordinates.

---

## 1. What the photo shows (decomposition)

| Element | Where | Driver | Top-down look |
|---|---|---|---|
| Bow-wave sheet | Stem → ~⅓ L along both sides | Zb (speed², entrance angle, draft) | Thin bright white line hugging the hull, thickest at the stem |
| Bow crest peel / "moustache" | Leaves the hull at the forward shoulder, runs out and aft | Same, and breaking | White line diverging at roughly the wake angle, breaking into streaks |
| Hull-side turbulence | Mid → aft along the sides | Speed | Faint foam, mostly fades before the stern |
| Stern wash | Transom → far astern | Propulsor power; waterjets ≫ screws | The widest and longest-lived white region; grows wider with age |
| Divergent waves | Inside the V | Fr_L | Diagonal light/dark streaks (lighting only) |
| Spray | Stem, high speed | Zb, sea state | Particles; optional |

The photo craft (~45–50 m, ~30 kn) is at **Fr_L ≈ 0.7**, i.e. semi-planing. That is why the bow rides up, the white water is huge and the stern wash dominates. A battleship at full speed is only Fr_L ≈ 0.3 and looks very different: a narrow wake, a bigger but more "glassy" bow wave, and a relatively thinner wash.

---

## 2. Physics baselines

### 2.1 Froude regimes (Fr_L = U/√(gL))

| Fr_L | Regime | Visual |
|---|---|---|
| < 0.25 | Cruising, displacement | Small bow cushion, clear Kelvin V at 19.47°, little foam |
| 0.25–0.40 | Fast displacement (battleships at flank) | Strong bow wave, foam mostly at the bow and stern |
| ~0.40 | "Hull speed" (transverse wavelength ≈ L) | Ship sits in its own trough, stern wave rises |
| 0.40–1.0 | Semi-displacement (destroyers at flank, FACs) | Big white bow, **wake visibly narrows**, wide stern wash |
| > ~1.0 | Planing | Bow lifts, spray sheets, very narrow V, wash dominates |

Fleet examples from the prototype: Fletcher 15 kn → 0.23; Iowa 32 kn → 0.32; Fletcher 35 kn → 0.54; 44 m FAC 30 kn → 0.74.

### 2.2 Wake angle

- **Kelvin:** the outer envelope half-angle is arcsin(1/3) = **19.47°** for any speed ([Rabaud & Moisy 2013](https://www.irphe.fr/~duchemin/Journal_Club/Rabaud20132.pdf)).
- **At high Froude** the *visible* (maximum-amplitude) angle narrows roughly as **1/Fr_L**, starting around Fr_L ≈ 0.5–0.7. Rabaud & Moisy observed this in airborne images. Darmon, Benzaquen & Raphaël derive φ_max ≈ 0.147/Fr for a Gaussian pressure source and a transition near Fr ≈ 0.7 ([JFM / arXiv 1309.6751](https://arxiv.org/pdf/1309.6751)). The constant depends on hull shape. **Use φ = min(19.47°, c/Fr_L) with c ≈ 0.16–0.20, chosen for continuity.** The prototype uses 0.16 when Fr_L > 0.45.
- The FFT bake reproduces this narrowing automatically. The analytic constant is only needed for the stylised peel line and for the trail ribbon width.

### 2.3 Bow-wave height (the "how white is the bow" number)

Noblesse et al., simple analytical relations for fine bows ([Ship bow waves, J. Hydrodynamics 2013](https://dcwan.sjtu.edu.cn/userfiles/2013-4%20Shipbowwaves.pdf); [ResearchGate](https://www.researchgate.net/publication/231996182_Simple_analytical_relations_for_ship_bow_waves)):

```
Zb · g / U² = 2.2 · tan β / ( cos β · (1 + Fr_D) ),   Fr_D = U / √(g·T)
Xb (crest distance aft of stem) ∝ T · Fr_D
X0 (bow-wave length)            ∝ (f + 2.3)·(cos β + cos β̄)/(1+Fr_D) · T · Fr_D²
```

Here β is the waterline entrance half-angle and T the draft. Prototype values:

| Case | U | T | β | Fr_D | **Zb** |
|---|---|---|---|---|---|
| FAC 30 kn | 15.4 m/s | 1.5 m | 14° | 4.0 | 2.7 m |
| Fletcher 15 kn | 7.7 | 4.2 | 10° | 1.2 | 1.1 m |
| Fletcher 35 kn | 18.0 | 4.2 | 10° | 2.8 | 3.4 m |
| Iowa 32 kn | 16.5 | 11.0 | 12° | 1.6 | 5.1 m |

Use Zb for three things: (1) to **calibrate the amplitude** of the linear FFT field (the prototype scales so the 99.9th-percentile crest equals Zb, because the raw linear model overshoots), (2) for **bow whiteness**, `bow_white = clamp((Zb − 0.5)/2.5, 0, 1)`, and (3) for spray particle emission. Entrance angle comes from hull form: destroyers ≈ 8–12°, cruisers/battleships ≈ 10–18°, full merchant hulls 25–40° (approx.). Derive it from the designer's Cb and the fore-body exponent.

### 2.4 Wavelengths (sizes the bake domain)

The transverse wavelength is λ = 2πU²/g ≈ 0.64·U² (U in m/s):

| Speed | 10 kn | 20 kn | 30 kn | 35 kn |
|---|---|---|---|---|
| λ | 17 m | 68 m | 152 m | 208 m |

The bake domain must cover several λ *and* several L, so the prototype uses span = max(L, λ): ahead 0.6·span, behind 4·span. Divergent waves near the hull are much shorter, and the grid must resolve the hull: dx ≤ L/80 is good, and L/50 is acceptable for small fast craft.

### 2.5 Foam lifetimes (tunable, unverified)

- Breaking-crest foam (bow peel, whitecaps): decays in seconds. The prototype uses τ = 8 s → visible for ~U·τ ≈ 1–1.5 L.
- Bubbly turbulent wake (propulsor wash): long-lived. The prototype uses τ = 45 s → 300–800 m. Real ship wakes stay visible from the air for kilometres. For gameplay, cap the length by distance and fade to a faint "slick" (slightly lighter, smoother water) instead of white.
- Wash width grows with age, roughly ∝ √(B·age_distance) in the prototype (empirical).
- Waterjets / high-power craft: wash multiplier ≈ 2× twin screws (artistic, matches the photo).

---

## 3. Recommended architecture

### 3.1 Bake (per hull × speed bucket), CPU or GPU compute

Inputs from the ship designer: L, B, T, planform (fore/aft fullness exponents from Cb), entrance angle, propulsion type → `wash`, speed U.

1. Rasterise the waterplane, then blur it (σ ≈ B/5). This is the pressure patch `p = ρ g T · m(x,y)`.
2. One forward FFT, multiply, one inverse FFT (steady linearised free surface in the ship frame, as in Darmon et al.):
   `η̂(k) = −g T |k| m̂(k) / ( g|k| − U²kx² ∓ i ε U kx )`, with ε = 0.08·g/U as Rayleigh damping (it enforces waves behind the ship and hides FFT wrap). Pick the sign so the waves trail, and taper the domain edges.
3. Rescale η so the crest peak equals Zb (§2.3) and zero the field inside the hull.
4. Build foam sources:
   - crest breaking: `clamp((|∇η| − 0.30)/0.30)` where η > 0.3·Zb;
   - hull sheet: a thin band outside the waterline, ∝ bow_white·along³;
   - bow peel: a line from the shoulder at angle φ (§2.2) whose length scales with U²/g;
   - wash: injected at the transom.
5. **Advect and decay in the ship frame.** Water moves −x at U, so foam is a single scan from bow to stern per row: `a = max(a·e^{−dx/(Uτ)}, src)`. Then blur the wash laterally with σ growing with age. This is trivially parallel per row on GPU.
6. Outputs (store as 2 textures):
   - RG16F: η (or pre-derived normal xy);
   - RG8: crest-foam density and wash-foam density, kept separate so they can fade differently.

**Measured cost (prototype, numpy, 2-core cloud box):**

| Case | Grid | Bake |
|---|---|---|
| Iowa 32 kn | 448×350 | 25–35 ms |
| Fletcher 15 kn | 448×343 | 28–37 ms |
| Fletcher 35 kn (512-class) | — | 42–54 ms |
| FAC 30 kn (512-class) | — | 39–47 ms |
| FAC 30 kn, hi-res 1372×1078 | 1372×1078 | 0.9–1.8 s (the python loop dominates) |

The FFT itself is 10–40 ms of that. In C#/C++ with a real FFT library, or on GPU, expect ≤ 5 ms CPU or ≤ 1 ms GPU at 512². Cache bakes by `(hull_id, round(U / step))` with a ~3–5 % speed step. A 30-kn ship then needs ~60 buckets, but only those actually visited get baked.

### 3.2 Runtime (every frame, per visible ship)

1. **Near-field stamp.** A quad in ship space from ~0.6 span ahead to ~1.5–2 L astern. It samples the baked textures.
   - Turning: shear the lookup `y' = y − ½κx²` (κ = yaw rate / U) so the near wake curves.
   - Accel/decel: crossfade between two cached bakes over 0.3–0.5 s.
2. **Trail ribbon.** Keep a history of stern positions (a sample every ~0.25·B or 0.1 s, ring buffer, a few hundred points). Build a strip whose half-width = B/2 + age_dist·tan φ, capped. In the fragment shader, map each pixel to (distance-along-track s, lateral offset d) and sample the far-field columns of the bake (or an analytic fallback: wash Gaussian ∝ e^{−s/(Uτ)}, plus two V-arm crest streaks). This makes the wake follow the real path through turns at the cost of one draw call. Self-overlap in tight turns: take max for foam and add normals.
3. **Foam shading = the "looks good" part.** Use a tiling world-space foam texture (2 octaves, slight scroll, anisotropic along the track) and compute `foam = saturate((density − (1 − tex)·k) / softness)`. Add a solid core only where density > 0.9. This is what turns smooth density blobs into the streaky, broken foam in the photo. The prototype's own noise is deliberately crude; do this properly in the shader.
4. **Water lighting.** Derive the normal from η (scaled ×2–3 for readability top-down) and use it for sun diffuse plus a specular glint. The divergent-wave streaks come almost entirely from this.
5. **Spray particles (optional).** Emit at the stem and the bow shoulder at a rate ∝ U·max(0, Zb − 1 m). Short lifetime, drawn above the hull layer.
6. **Composite order:** water → wake normals/foam → hull_base → turrets → hull_upper → spray.
7. **Bake on the waterline, draw the deck on top.** Seen from above, the deck edge is bigger than the waterline: the raked stem overhangs it, the stern overhangs it, and flare or knuckles widen the deck (most of all forward). The bake must use the **waterline** planform. The sprite (deck silhouette) is drawn over the wake, so it hides the first metres of the bow sheet and the hull-hugging foam. The wake then *appears* to start a little aft of the stem and outboard of the deck edge, which is what photos show. A slight soft drop shadow of the deck edge onto the foam sells the height.
   - Prototype `deck_planform()` parameters (per hull, approx.): FAC bow +6 % L, stern 0, beam ×1.12; Fletcher +3 % L, +1 % L, ×1.06; Iowa +2.5 % L, +1.5 % L, ×1.04. The deck bow is also fuller (fore exponent ×0.85) because of flare.
   - **Sprite pipeline consequence:** `geometry.py` should export **two outlines per hull**, the deck edge (sprite/hitbox) and the waterline (wake bake input). They are not the same shape. Several ships' wakes go into one screen-space or world-space RT: add normals and max foam.

LOD: beyond some zoom, drop the normal map and draw only the foam ribbon. Only the N nearest moving ships get near-field stamps. For comparison, one other web naval game reports ~0.2 ms per hull for analytic bow + Kelvin wakes ([goldflag/ship-game PR #455](https://github.com/goldflag/ship-game/pull/455)).

### 3.3 Alternatives considered

- **Pure analytic Kelvin in the shader** (stationary-phase V pattern + stem crest): the cheapest option, no bake, and it handles turns per-pixel. It needs hand-tuning per hull and gives less "hull-specific" character. Good fallback, or for far LOD.
- **Wave particles** ([Yuksel et al. 2007](https://www.cemyuksel.com/research/waveparticles/)) or an iWave-style heightfield sim: interactive (ships' wakes interact, shells splash). Costlier, and the steady V pattern is hard to make look right at Fr > 0.5. Consider it later only for splashes and explosions layered on top.
- **Triton-style vertex-shader wakes** ([Sundog Triton 2.3](https://sundog-soft.com/2013/07/ship-wakes-in-triton-2-3-kelvin-wakes-bow-wakes-propeller-wash-and-more/)): circular waves emitted along the track and summed in the vertex program. Good for a 3D camera, overkill for top-down.
- **World-anchored wake render texture** (splat each frame and decay; see [ocean-drive #55](https://github.com/danielluis07/ocean-drive/issues/55)): handles arbitrary paths and overlap naturally, but costs RT memory and needs camera-scroll management. It is a valid alternative to the ribbon if many ships manoeuvre in a small area.

---

## 4. Prototype findings and known issues

- Fletcher and Iowa look right in structure: a narrow V for Iowa, a strong bow sheet, and a peel line.
- Fr_L > 0.6 (the FAC) is outside the linear model's comfort zone. The V narrows as it should, but the near-hull field is too smooth, and the "riding up" bow and spray sheets of a semi-planing hull are not captured. For Fr_L > 0.6, add stylised features: whisker spray lines from the chine at ~10–15°, wider and whiter wash, and a smaller bow sheet (the bow lifts out).
- The linear model overshoots at a full transom (a stern trough of several metres). The Zb calibration and clamping hide this. A better pressure shape (thin-ship source ∝ dB/dx, or a softer stern) is a cheap fix.
- FFT wrap appears as faint parallel streaks at the edges. Damping plus an edge taper is enough; padding ×1.25 is the robust fix.
- Foam thresholds (crest slope 0.30, bow-white 0.5–3 m Zb ramp, τ values) are artistic. Tune them against reference photos at 3–4 Fr_L values.

## 5. Next steps (Claude Code side)

1. Port `wake_bake_ref.py` to the game language (GPU compute if available) and keep the same parameter names.
2. Map designer outputs to `n_fore`, `n_aft`, `entrance_deg`, `wash`. Use Cb and the style/era for fullness; propulsion type for wash.
3. Implement the near-field stamp, then the trail ribbon, then the shader foam breakup. Get the look right on Fletcher at 15/25/35 kn first.
4. Add a high-Fr stylisation path (> 0.6) for FACs and MTBs.
5. Optional: shell splashes and explosion rings as wave-particle overlays.

---

## 6. Fix: "blocky bow" / foam doesn't detach (2026-10-05)

Symptom (game build, reproduced exactly by v1 `wake_bake_ref.py`): the eta field shows a dark wedge around the bow and **no crest at the stem**. The foam map shows straight-edged parallelograms: a hull-parallel band, a straight peel line, and the whole area behind them filled in. Reference fix: `claude/wake_bake_ref_v2.py` (`bake2`). The comparison image `bow_fix_v1_vs_v2.png` was delivered in chat.

**Causes, most important first:**
1. **The pressure-patch forcing is the wrong model for a displacement bow.** A positive surface pressure makes a *depression* under and around it, because it models a planing pad. A fine bow is a slowly rising pressure, so the near field is a trough and the stem never gets a crest. Everything downstream (crest-driven breaking) has nothing to work with near the bow.
   **Fix:** force with a thin-ship (Michell-style) **source distribution** `q = U·∂m/∂x` on the waterplane. It is + on the entrance (pushes water out → crest at the stem) and − on the run (stern wave). Use draft attenuation `(1−e^{−kT})/k`. Response: `φ̂ = −g·q̂·att / D`, `η ∝ ∂φ/∂x`. Then auto-check two signs: waves must trail, and η at the stem must be positive. Same single FFT cost.
2. **Foam is advected straight along −x with one long-τ max.** Every source pixel smears into a horizontal streak. That gives the hard straight edges and fills everything behind the peel line.
   **Fix:** advect along **streamlines** of the surface flow (−U + u′, v′). The flow comes from the same FFT (`u′ = g·η/U`, v′ from ∂φ/∂y), smoothed over ~B/4 and clamped (|u′| ≤ 0.3U, |v′| ≤ U·tan(β+8°)). Implementation: a bow→stern column march where each column backtraces rows by `v/|ux|·dx` (one 1-D interp per column, trivially parallel on GPU). The bow sheet then curves outward and detaches.
3. **Single foam tier.** Split it into three:
   - **fresh whitewater**: max-combined, τ ≈ 1.5 s, bright;
   - **residual foam**: additive, fed at ~8 % of fresh, τ ≈ 15 s, blurred laterally with σ ∝ √age, drawn at ~45 % opacity;
   - **wash**: as before.
4. **Geometric foam primitives with hard edges** (boolean hull band using `|y| − half(x)`, a hand-placed peel line). `|y| − half(x)` is not a distance: at a fine bow it underestimates the normal distance by 1/cos, so the band pinches, and at the stem (half → 0) it leaks a needle along the centreline ahead of the bow. That is the thin bright line in the game images.
   **Fix:** use a true distance transform (EDT) of the waterplane with a Gaussian falloff. Drop the peel line, so breaking comes from the computed crest: `smoothstep(η/Zb, 0.35, 0.8) · smoothstep(slope, 0.15, 0.35)`.
5. **Binary waterplane raster.** The staircase at the sharp stem causes Gibbs ringing in the FFT, which shows as blocky crests. **Fix:** 4×4 supersampled coverage, plus only a light blur (σ ≈ 0.04 B) instead of B/5 (the big blur also fattened the bow ahead of the stem).

**v2.1 tuning (done, in `wake_bake_ref_v2.py`).** The image `wake_v21_nearfield.png` was delivered in chat.

| Problem in v2 | Cause | Fix |
|---|---|---|
| Residual foam envelope too wide around midships | Residual was fed `0.08·src` *per column*, so it scaled with 1/dx (resolution-dependent), plus a wide blur | Residual gains the share of whitewater that decays each step: `r = r·e^{−dx/(Uτr)} + 0.5·a·(1−e^{−dx/(Uτf)})`. Blur k 0.12 → 0.08. Drawn at 50 % opacity |
| Lens at the transom | Stern sink → converging streamlines concentrate foam | Potential-flow steering faded to 0 between x = −0.2 L and the stern. The wash is never steered |
| Bow foam cut off abruptly at the shoulder | Inward flow along the run steered foam *into* the hull mask | Outward-only steering (`slope_y·sign(y) > 0`), v clamp tightened to U·tan(β+4°) |
| Bow foam "ears" too fat, then a hard end | Broad breaking source and τ_fresh = 1.5 s | Breaking = front face only (`smoothstep(η/Zb, .5, .9)·smoothstep(slope, .2, .4)`), thinner hull band (0.04 B), τ_fresh = 3 s, so the sheet tapers into trailing streaks |
| Iowa stern crest too white | Linear stern crest ≥ bow crest at Fr_L ≈ 0.3 | Stern-crest breaking weight = clamp(0.3 + 2(Fr_L − 0.3), 0.3, 1), full along the forward/mid body |
| Visible steps in the wash width | Age blur applied in hard column bands | 8 blur levels (geomspace σ) with a per-column lerp between neighbours |

**Shader note.** A hard threshold on the density field reads as blocky edges even when the field is smooth. Use the soft breakup:
- `t = 1 − d`
- `brk = saturate((noise − t + 0.18)/0.36)`
- `alpha = brk · saturate(1.6·d)`

Use streaky world-space noise (cells ~2.5 m, stretched ×4 along the track).

**Timings v2.1 (numpy):**
- 512-class grids: FAC 134 ms, Fletcher 123 ms, Iowa 99 ms.
- 1024-wide FAC: 1.6 s.

The FFT part is still only 17–100 ms. The rest is the Python column march and the blur stack, which are per-row/per-column parallel and belong in compute or C++.

**Remaining known limits:**
- FAC (Fr_L 0.74) aft white water is very large. That matches the reference photo, but it is still a linear model past its range (see the regime table discussion: semi-planing Fr_∇ ≈ 2).
- Iowa's bow white is thin because its long waves never get steep. If it looks too tame in game, make breaking use height relative to Zb more and slope less for large hulls.

**v2.2: foam lane too wide (user review).** In v2.1, Fletcher's foam fanned out into a wide V within ~2 L. Big ships actually leave a fairly **stable, narrow foam lane**: observed turbulent/bubble wakes are tens to ~160 m wide, persist for ~10 min (max ~30 min), and stay visible for km ([Ocean Science preprint os-2020-59](https://os.copernicus.org/preprints/os-2020-59/os-2020-59-manuscript-version5.pdf)).

Causes and fixes:
1. **Breaking was allowed along the whole Kelvin V.** The linear arms stay steep far out, but a displacement ship's divergent waves don't whitecap in a calm sea. Breaking is now limited to a band around the hull: `exp(−(d_hull/band)²)` with `band = B·(0.5 + 2·max(Fr_L − 0.5, 0))`, i.e. ~0.6 B for Fletcher at 35 kn and ~1 B for the FAC. The V shows only as wave shading.
2. **The wash dimmed as it widened** (a mass-conserving blur), so it vanished after a few hundred metres. It now keeps most of its peak while spreading: `turb *= (pre_peak/post_peak)^0.75`. Spreading is slower (k 0.15 → 0.10).
3. **The Kelvin arms stayed crisp for many L.** η is now faded with distance astern by `1/(1 + behind/1.5 L)` (artistic, ~1/r), so the V reads near the ship and becomes subtle shading further back.
4. Wash start width scales with √wash (waterjets get a wider lane).

Result: the foam lane half-width at 300 m / 550 m astern is
- Fletcher 35 kn: 9 / 10 m (B = 12);
- Fletcher 20 kn: 7 / 3 m (fading);
- Iowa 32 kn: 17 / 20 m (B = 33);
- FAC 30 kn: 9 / 11 m (B = 8).

The image `wake_v22_long.png` was delivered in chat.

## Sources

- Rabaud & Moisy, "Ship wakes: Kelvin or Mach angle?", PRL 2013 — https://www.irphe.fr/~duchemin/Journal_Club/Rabaud20132.pdf
- Darmon, Benzaquen, Raphaël, "Kelvin wake pattern at large Froude numbers", JFM 2014 — https://arxiv.org/pdf/1309.6751
- Noblesse et al., "Ship bow waves", J. Hydrodynamics 2013 — https://dcwan.sjtu.edu.cn/userfiles/2013-4%20Shipbowwaves.pdf
- Noblesse et al., "Simple analytical relations for ship bow waves" — https://www.researchgate.net/publication/231996182_Simple_analytical_relations_for_ship_bow_waves
- Yuksel, House, Keyser, "Wave Particles", SIGGRAPH 2007 — https://www.cemyuksel.com/research/waveparticles/
- Sundog Software, "Ship wakes in Triton 2.3" — https://sundog-soft.com/2013/07/ship-wakes-in-triton-2-3-kelvin-wakes-bow-wakes-propeller-wash-and-more/
- goldflag/ship-game PR #455 (analytic bow waves + Kelvin wakes, perf numbers) — https://github.com/goldflag/ship-game/pull/455
- danielluis07/ocean-drive #55 (world-anchored wake texture) — https://github.com/danielluis07/ocean-drive/issues/55