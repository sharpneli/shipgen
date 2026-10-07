# What the muzzle pressure wave makes visible — research (2026-10-07)

Follow-up to `claude/muzzle-flash-smoke-research.md`. Extends `claude/muzzle-blast-water-vfx.md`, which already covers the main top-down signature, the roughness "frost disc" on the sea. Reference code: `claude/blast_wave_visibles_ref.py` (pure Python + numpy; prints every number below).

The question: **does a gun make a visible pressure wave like a big explosion does, and what else does the wave make visible?**

Tags as elsewhere: **[INFERRED]** = my reasoning or fit; **[UNCERTAIN]** = thin or conflicting sources.

---

## 0. TL;DR

1. **The shock front itself is transparent.** It is a ~1 µm density step of a few percent at most, and it shows only through what it does to other things. From a top-down camera, in order of importance:

   | Rank | What becomes visible | Coverage |
   |---|---|---|
   | 1 | The sea surface (frost disc and dark leading edge) | Existing doc |
   | 2 | Smoke and fog the wave or gas jet moves, including the **vortex ring** | §5 |
   | 3 | Spray and foam in the near field | Existing doc |
   | 4 | A faint **sun-shadow line** on surfaces right under the near-field shock, in bright sun only | §3 |
   | 5 | Very rarely, a **condensation (Wilson) haze** | §2 |

2. **No Beirut-style condensation dome for real guns.**
   - Explosion clouds form in the blast's negative phase, when the air is briefly expanded and cooled below its dew point.
   - A gun's negative phase lasts ~15–70 ms (16″ positive phase measured at 10.3 ms at the muzzle). Explosions large enough for a famous Wilson cloud have phases of hundreds of ms.
   - Droplets need time to grow, and in 15–70 ms they stay too small to scatter much light.
   - The model gives **no visible cloud for any real gun under baseline assumptions, even at 97 % RH**. With every uncertain input pushed toward condensation, heavy guns give at most a **faint (τ ≈ 0.05–0.1), 25–75 ms haze shell** in very humid air, mostly when a salvo is fired into its own salt-laden smoke. That is 2–5 frames.
   - The 2000 mm turbocannon does get a proper one: a ~260 ms white shell, 130–420 m forward. Joke gun, joke-worthy effect.
   - The 16″ gunblast report saw the blast on film and on the water, and mentions no condensation ([DTIC ADA210220](https://apps.dtic.mil/sti/pdfs/ADA210220.pdf)).
3. **The vortex ring ("smoke ring") is the most readable pressure-wave effect after the water.** The exiting gas puff rolls into a turbulent ring that carries smoke and water fog away from the muzzle.
   - Size: radius ~0.25 λ. That is ~1.3 m for a 120 mm tank gun and ~4 m for a 16″ gun.
   - Motion: it slows as t^¼ and travels ~8 λ before breaking up, over 5–15 s **[INFERRED scale]**.
   - From above, a near-horizontal gun's ring is a bar across the bore line. A high-angle AA ring is an open circle rising up the screen.
4. **Existing smoke is barely moved by the shock** (cm–dm). It is **punched by the gas jet** (metres) along the bore. Show the jolt as a 1–2 frame UV ripple, and the punch as a real displacement.
5. **The sun-shadow line** is the density jump refracting sunlight into a thin bright/dark doublet on the surface below.
   - Contrast is a few percent at r ≈ λ. It is visible only in bright sun and only in the near field (≲ 1–2 λ).
   - It is the one honest version of the game-trope "shock ring". Keep it thin, faint and near.
   - A big screen-space distortion ring is not physical for a top-down camera: the apparent shift through the shell is ~1 cm.
6. **Calibration flag for the existing water doc.** The measured 16″ near field is ~2–5× stronger than the far-field fit we use: ~2 psi (13.8 kPa) at ~48 m (free-field corrected), against 1–7 kPa from the fit. This is a near-field underestimate the fit is known for, and the visible-edge threshold was tuned to the photo, so nothing breaks. Use the measured value if near-field pressures ever drive gameplay (crew, AA mounts, boats).
7. **Over water the blast behaves as if the charge were doubled.** The report corrects data inside the ground Mach stem by treating the gun as having "twice the service charge", distances scaled by 2^⅓. Low-elevation fire over the sea reflects the same way. This is a free improvement to the frost-disc footprint: λ × 1.26 inside the Mach-stem region.

---

## 1. The shock front: why you don't see it directly

| Quantity | Value | Consequence |
|---|---|---|
| Density jump `Δρ/ρ ≈ Δp/(γp₀)` | ~7 % at 10 kPa, 1–2 % at the visible-water edge (1–3 kPa) | The refractive index changes by `(n−1)Δρ/ρ ≈ 3·10⁻⁴ × 0.07 ≈ 2·10⁻⁵` |
| Apparent shift of the sea seen through the shell from above (near grazing, h = 10 m) | **~1 cm** at r = λ for every calibre (`lens_shift`) | No visible "lens" from overhead. Seen from the side, against the horizon, clouds or the sun, the same jump is visible ([NASA BOS with the Sun as background](https://science.nasa.gov/earth/earth-observatory/seeing-shock-waves-86742/); the "lens around the artillery" in [Ynet](https://ynetnews.com/health_science/article/hy6d9wbst)) |
| Speed | 345–400 m/s | At 60 fps the front moves 6–7 m per frame. Evaluate analytically (water doc) |

What the camera *can* see is the wave's effect on media that already exist: water ripples, smoke, spray, humid air, sunlight.

---

## 2. Condensation (Wilson) cloud

### 2.1 Mechanism

Behind the positive pulse comes the **negative phase**. There the air is briefly expanded and cooled adiabatically, and if it was humid enough it dips below its dew point. Water condenses into a cloud that "disappears" when pressure recovers ([Wikipedia: Condensation cloud](https://en.wikipedia.org/wiki/Condensation_cloud), after Glasstone & Dolan). Beirut 2020 is the famous recent example.

Two conditions must both hold:

- **Supersaturation:** `S = RH·(1−δ)·e_s(T)/e_s(T−ΔT)`, with δ = |p₋|/p₀ and `ΔT = T(1 − (1−δ)^(0.286))` ≈ 0.85 K per kPa.
  - At RH 90 % this needs |p₋| ≳ 2.4 kPa; at 97 %, ≳ 0.8 kPa.
  - Near-field underpressures plateau around 10 kPa (Granström; the [Rigby 2014](https://lajss.org/index.php/LAJSS/article/download/6706/3041/22462) fits differ ~2–3×) **[UNCERTAIN]**.
- **Growth time:** droplets grow as `r·dr/dt = G(S−1)` with G ≈ 10⁻¹⁰ m²/s. The supersaturated window is about the negative-phase duration, ~2–3× the positive phase.
  - Positive phase: ~0.9 ms per m of λ (the audio and water docs), or 10.3 ± 2 ms measured at the 16″ muzzle.
  - Window: **~15–70 ms for real guns**, against hundreds of ms for kiloton-scale blasts.

### 2.2 Model results (`wilson`, `wilson_extent`)

Visible means τ ≥ 0.05 through a shell region ~0.5 r thick seen from above. Marine nuclei are 150 /cm³ unless stated **[INFERRED]**.

| Scenario | 5″ twin | 8″ triple | 16″ single | 16″ triple | 2000 mm |
|---|---|---|---|---|---|
| A: baseline fit, p₋ = 0.25 p₊, RH 90 / 97 % | none / none | none / none | none / none | none / none | 132 m / 423 m, ~260 ms |
| B: near field ×3 (16″ data), p₋ = 0.4 p₊ | none / none | none / none | none / 56 m (τ≈0.05) | 122 / 377 m, ~110 ms | 0.7 / 2.4 km |
| C: B + 3000 /cm³ nuclei (salvo into own salt smoke) | 36 / 78 m, 24–34 ms | 101 / 275 m, ~40 ms | 143 / 414 m, ~55 ms | 216 / 669 m, ~75 ms | 0.8 / 2.5 km, ~225 ms |

**Reading:**
- For real guns the cloud is **at best a faint, brief haze shell**: τ ≈ 0.05–0.1, a few frames, only in very humid air.
- It is most likely on the **second and later salvos**, because the first salvo's smoke supplies abundant nuclei. That is a nice emergent detail.
- Within the model's uncertainty "never" is also defensible.
- The turbocannon makes a real white shell lasting ~¼ s.

**Implementation, if used at all:**
- **Rule:** a translucent white shell decal between the shock radius R(t) and ~0.6 R(t), in the oblique projection. Opacity `τ·shape`, lifetime from the table, gated by RH > 0.85 and calibre.
- **Night:** lit by the flash, so orange.
- **Cost:** one quad.
- **Recommendation:** gate it to λ ≳ 20 m and RH ≳ 0.9 as a rare atmospheric flourish, and do not make it a standard effect. Turbocannon: always on above RH 0.75.

**Not to confuse** with the white puff that *is* common in humid, cold weather: the **water fog condensing out of the propellant gas itself** (`A_w` in the flash doc). It lives in the gas cloud, not in the shock shell, and lasts seconds.

---

## 3. Sun shadowgraph line

A density jump bends light. Parallel sunlight passing near-grazing through the shell is deflected by `ε ≈ (n−1)(Δρ/ρ)·√(2r/w)`. On a surface a distance L beyond, that concentrates and depletes light into a thin bright/dark doublet: a natural shadowgraph ([Wikipedia: Shadowgraph](https://en.wikipedia.org/wiki/Shadowgraph)). The sun's 0.53° disc blurs the doublet over `w ≈ L·9 mrad`.

| Gun (forward, r = λ′) | Line contrast (`shadow_contrast`) |
|---|---|
| 20 mm | ~1 % |
| 5″ twin | ~4 % |
| 16″ triple | ~7 % |
| 2000 mm | ~13 % |

The estimate is order-of-magnitude **[INFERRED]**. Contrast falls roughly as Δp, so it is gone beyond ~1–2 λ.

**Render:** a 1–2 px bright-over-dark line riding the shock front, modulating surface luminance (water, decks, smoke tops) by ±C. Rules:
- full sun only (scale by direct-sun fraction);
- only where `Δp(r) > ~5 kPa`;
- fades with distance and is off at night.

This uses the same analytic front as the water shader: one extra term, no new data.

---

## 4. Spray and spindrift

Post-shock gust `u ≈ Δp/(ρc)` (weak-shock limit):

| Δp | Gust |
|---|---|
| 1 kPa | 2.4 m/s |
| 5 kPa | 12 m/s |
| 20 kPa | ~50 m/s |

The gust lasts only t₊ (~1–20 ms). That is enough to roughen ripples (the frost) but too short to tear spray off swell crests, except near the muzzle where Δp is tens of kPa *and* the hot gas jet arrives.

| Gun | Radius where Δp ≥ 5 kPa, forward (fit) |
|---|---|
| 20 mm | ~3 m |
| 5″ twin | ~25 m |
| 16″ single | ~70 m |
| 16″ triple | ~100 m |

Fit values: measured near-field pressure is higher, so treat them as minima.

**Model consequence:** keep the water doc's scaled-distance foam rule (k_foam ≈ 1 λ′). Add **crest-tip spray flicks**, small white specks lasting 0.2–0.5 s, on existing crest foam inside the 5 kPa radius. That lets the shock "brush" the sea visibly in the near field.

---

## 5. Smoke the wave and jet move

### 5.1 Shock jolt (small)

Peak displacement of existing smoke by the shock alone is ~`½Δp·t₊/(ρc)`. At a 2 kPa crossing that is **~0.2 cm (20 mm) to ~5 cm (16″ triple)** (`smoke_jolt`): invisible as motion. What *is* visible in close footage is the **refraction ripple running through the smoke texture** as the front crosses.

**Render:** a 1–2 frame radial UV offset of ~0.5–1 px in smoke billboards inside the moving front, amplitude ∝ Δp. Free, and it reads as "the wave passed through".

### 5.2 Jet punch (large)

The muzzle gas jet carries momentum: ~2.5 λ_f forward in the flash doc's puff model. Smoke from earlier rounds in the cone ahead of the muzzle (length ~3 λ_f, half-angle ~20°) is pushed forward by metres to tens of metres and thinned along the axis. **A gun firing through its own smoke clears a tunnel.**

**Implement** at fire time:
- for each existing puff in the cone, add `Δxy = bore·k·λ_f·exp(−d/λ_f)` (k ≈ 0.5);
- multiply its σ_h by 1.2;
- leave A unchanged, so smoke is conserved and the gameplay line-of-sight stays honest **[INFERRED]**.

### 5.3 Vortex ring (`vortex_ring`)

The exiting gas slug rolls up into a ring vortex. Turbulent self-similar rings travel as `x ∝ t^¼` and grow slowly (Glezer & Coles 1990, [JFM 211](https://www.cambridge.org/core/journals/journal-of-fluid-mechanics/article/abs/an-experimental-study-of-a-turbulent-vortex-ring/0E47E30C9A21E93C5A56FCEE93FD5B6C)). The rings carry gunshot residue far from the muzzle ([Comiskey & Yarin, JFM 2019](https://www.cambridge.org/core/journals/journal-of-fluid-mechanics/article/abs/selfsimilar-turbulent-vortex-rings-interaction-of-propellant-gases-with-blood-backspatter-and-the-transport-of-gunshot-residue/81F43FB54E7FF28A0230667CD559D60F)). Visible "smoke rings" from howitzers, mortars and tank guns are this ring, made visible by smoke and condensed water.

```
R₀ = 0.25 λ,   U₀ = 25 m/s·√(λ/5 m),   τ = 2λ/U₀
x(t) = 4 U₀ τ ((1 + t/τ)^¼ − 1),   R = R₀(1 + 0.08 x/λ),   dies at x ≈ 8 λ        [INFERRED constants]
```

| Gun | λ | Ring radius | Travel | Life |
|---|---|---|---|---|
| 20 mm | 0.8 m | 0.2 m | 6 m | 2.4 s |
| 120 mm tank (~8 kg) | 5.4 m | 1.3 m | ~43 m | ~6.5 s |
| 5″ twin | 6.2 m | 1.5 m | 49 m | 6.7 s |
| 16″ single | 17 m | 4.3 m | 137 m | 11 s |
| 2000 mm | 81 m | 20 m | 650 m | 24 s |

**When it forms** **[INFERRED]**: a clean slug exit and calm air.
- P ≈ 0.3 per shot with no muzzle brake and wind < 5 m/s, falling to ~0 above 10 m/s.
- ×0.3 with a muzzle brake (the side jets break the slug).
- More likely with smoky or flashless charges (more marker, less turbulent afterburn).

**Smoke accounting:** the ring takes ~25 % of the shot's smoke extinction area A_p and A_w, so it is also a moving line-of-sight blocker. The rest stays in the main puff.

**From above:**

| Elevation | How the ring looks | Projection |
|---|---|---|
| Near-horizontal gun | A ring with a horizontal axis is seen **edge-on: a short bar (2R × ~0.3R) across the bore line**, moving away and slowing | Oblique lift by its height |
| High-angle AA (60–80°) | Seen face-on: an **open circle rising up the screen** | Oblique projection |

Both read immediately as "smoke ring".

**Render:** one billboard per ring: a soft annulus sprite in local ring coordinates, oriented by the bore direction, lit like smoke (6-way). At night, flash-lit for t_s, then dark.

---

## 6. Other effects, and why most are left out

| Effect | Verdict |
|---|---|
| Precursor shock | Gas and air pushed ahead of the projectile make a weak precursor blast before shot exit. The dust patent describes "two ball-shaped shock waves" ([US 6,308,608](https://patents.justia.com/patent/6308608)). Top-down it adds a faint inner ring to the frost disc in the near field. Optional; the water shader can add a second event at 0.1·λ, t − 2 ms |
| Reflection off water / deck | The Mach stem behaves as a doubled charge (§0.7). Hull reflections load equipment from behind (16″ report) |
| Ship-side debris | Blast damage to boats, light fixtures and loose fittings is real but invisible at game scale. Optional: paint-chip / cork "glitter" particles off the deck near the muzzles, ~10–30 sparkles, 0.5 s |
| Heat haze over the hot gas | The refractive index of 600 K gas differs by ~1.5·10⁻⁴. From overhead the shimmer displaces the sea by ≲ 1 cm, so it is invisible. Side views only |
| Projectile shock cone, shock diamonds | Invisible to the eye. The Mach-disk structure is already shown by the intermediate flash |
| Camera shake | The camera is not in the scene. If used at all, tie it to the shock *arriving at a chosen focus point* (ship centre), amplitude ∝ Δp there, for consistency with audio |

---

## 7. Implementation summary

Everything hangs off the **existing blast event buffer** (pos, bore, elevation, λ, t_fire) from the water doc. One more scalar per event (RH from the weather state) and one more per shot (ring yes/no).

| Element | Where | Data | Cost |
|---|---|---|---|
| Sun-shadow line | Water/deck shader, same front evaluation as the frost ring | Δp(r,θ), sun fraction | ~free |
| Smoke jolt ripple | Smoke billboard shader, front band test | Event buffer | ~free |
| Jet punch | CPU at fire time, puffs in the cone | Puff list | ~µs |
| Vortex ring | 1 billboard per ring, analytic x(t), R(t) | Ring list (≤ 16) | ~0.02 ms |
| Spray flicks | Particle burst on crest foam inside r(5 kPa) | Event buffer + foam | small |
| Wilson haze (rare) | 1 shell decal | Event + RH gate | ~free |
| Mach-stem footprint | λ × 2^⅓ for low-elevation fire in the frost disc | — | free |

---

## 8. Open questions

- **Near-field pressure vs angle for the 16″ gun.** [ADA210220](https://apps.dtic.mil/sti/pdfs/ADA210220.pdf) has nine radials (15–150°), but the figures did not extract. Reading Figs. 9–17 by hand would replace the Fansler fit inside ~3 λ.
- **Negative-phase amplitude for gun blast.** The 0.25–0.4 ratio is inferred; the report only mentions a short negative phase. This is the main uncertainty in §2.
- **Vortex-ring constants** (U₀, travel ≈ 8 λ, formation probability) are scaled from the look of footage, not measured. Frame-measure a few howitzer and tank smoke-ring clips to fix them.
- **Shadow-line contrast** is an order-of-magnitude estimate. If it matters, a quick raytrace through a spherical density step would pin it.

## Sources

- *16-Inch Gunblast Experiments* (DTIC ADA210220) — https://apps.dtic.mil/sti/pdfs/ADA210220.pdf (summary also at https://www.academia.edu/85290230/16_Inch_Gunblast_Experiments)
- Wikipedia, *Condensation cloud* — https://en.wikipedia.org/wiki/Condensation_cloud
- Rigby et al. / Granström negative-phase model (review in LAJSS) — https://lajss.org/index.php/LAJSS/article/download/6706/3041/22462 and https://scielo.br/j/lajss/a/gxQHfqVGcj5LBDh7F55pvkC/?lang=en
- Wikipedia, *Shadowgraph* — https://en.wikipedia.org/wiki/Shadowgraph
- NASA Earth Observatory, *Seeing shock waves* (BOS with the Sun as background) — https://science.nasa.gov/earth/earth-observatory/seeing-shock-waves-86742/
- Ynet, *How a shock wave is generated during artillery fire* — https://ynetnews.com/health_science/article/hy6d9wbst
- Giannuzzi et al. 2016, blast-driven vortex ring and blast wind, shadowgraph — https://nmt.edu/academics/mecheng/faculty/mhargather/docs/Giannuzzi2016.pdf
- Glezer & Coles 1990, *An experimental study of a turbulent vortex ring* (JFM 211) — https://www.cambridge.org/core/journals/journal-of-fluid-mechanics/article/abs/an-experimental-study-of-a-turbulent-vortex-ring/0E47E30C9A21E93C5A56FCEE93FD5B6C
- Comiskey & Yarin 2019, *Self-similar turbulent vortex rings… gunshot residue* (JFM 876) — https://www.cambridge.org/core/journals/journal-of-fluid-mechanics/article/abs/selfsimilar-turbulent-vortex-rings-interaction-of-propellant-gases-with-blood-backspatter-and-the-transport-of-gunshot-residue/81F43FB54E7FF28A0230667CD559D60F
- US 6,308,608, *Dust suppression* (two ball-shaped shocks from the muzzle) — https://patents.justia.com/patent/6308608
- Project: `claude/muzzle-blast-water-vfx.md`, `claude/muzzle-flash-smoke-research.md`, `claude/sound-design-gunfire.md`