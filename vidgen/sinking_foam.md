# Sinking ship surface VFX — research + prototype (2026-10-06)

Companion to `claude/wake-vfx-research.md` and `claude/muzzle-blast-water-vfx.md`. Reference code: `claude/sinking_foam_ref.py` (numpy, ~600 lines). Media delivered in chat: `strip_{bow_first,stern_first,capsize,break_in_two}.png` and matching `sink_*.gif` / `.mp4`.

Goal: top-down, stylised, 2D sprites over a full 3D hitbox model. When a ship goes down (bow first, stern first, capsizing, breaking in two, or settling evenly), the water around it must tell the story: foam where the hull goes under, air boils, a closing "slam", oil and debris that linger.

---

## 0. TL;DR for the implementer

1. **Drive everything from the 3D pose, not from per-scenario art.** The damage/buoyancy model already produces sinkage, trim and list per hull segment over time. Every surface effect below is derived from how that rigid hull crosses the plane z = 0. Bow-first, stern-first, capsize and break-in-two then come out of the same code. The prototype only hand-writes pose keyframes as a stand-in for the flooding model.
2. **Six layers, in order of visual importance:**
   - (a) **crossing foam**: hull surface that passes down through the waterline deposits white water where it crosses (water pouring over the deck edge). Weight grows with vertical speed. Surface coming *up* out of the water deposits weaker "cascade" foam.
   - (b) **contact collar**: a thin band around the current waterline cut, much brighter where the hull is moving vertically (the plunge).
   - (c) **air boils**: water in = air out, per compartment. Air comes up as boil events above the compartment's highest opening once that opening is under water. Part of it is trapped and burps up **after** the ship is gone: later, bigger and fainter as the wreck goes deeper.
   - (d) **closure slam**: when the last part goes under, one big boil plus a radial ring wave in η (lighting only).
   - (e) **oil**: leak puddles that spread (Fay), coloured by the Bonn appearance codes. Oil also damps ripples, so it uses the signed `roughness_delta` from the blast doc.
   - (f) **debris**: floating points released from the submerging deck, pushed outward by boils, drifting with the wind.
3. **The sprite carries half the effect.** Per pixel, compute the 3D height of the sprite layer under the current pose. Parts above water are drawn lit. Parts below water are tinted toward the water colour with depth (visible to ~3–5 m, stylised). The drop shadow of raised parts onto the water is the strongest height cue top-down: a rising stern casts a long shadow. Foam goes **over** submerged hull and **under** above-water hull.
4. **No whirlpool.** The "suction vortex" is a myth: MythBusters' test and Titanic survivor accounts both found none. A sinking ship leaves a boil (upwelling), not a drain. If art wants drama, use the slam and the boils.
5. **Cheap at runtime.** Crossing foam and the collar are one hull-mesh pass into a small world-space foam canvas per sinking ship. Boils, rings and oil are analytic event buffers, like the blast doc. Debris is particles.

---

## 1. What really happens (sources + what it looks like top-down)

| Phenomenon | Evidence | Top-down look |
|---|---|---|
| **Plunge by an end** is the usual way to go | US destroyer war-damage report: "a far greater number have gone down by plunging than by bodily sinkage or capsizing" ([USN WDR, DD torpedo/mine](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-torpedo-mine-damage.html)) | The deck waterline sweeps along the ship. The high end shortens (foreshortening) and casts a long shadow. A white collar surrounds the remaining stub. |
| **Breaking in two** | *Strong* (DD-467): "split in the middle with the bow and stern going up in the air and sinking immediately". *Bristol* broke ~4 min after the hit; *Meredith* 29 h later (same report) | A V: two segments, each pitching toward the break, with a foam/boil centre at the break |
| **Capsize** | Only *Preston* and *Johnston* were clear-cut destroyer capsizes (same report). Battleships: Bismarck "slowly capsizing and sinking by the stern" ([survivor, USNI](https://www.usni.org/magazines/naval-history-magazine/1995/february/i-escaped-bismarck)); Musashi, Yamato, Oklahoma | The deck slews sideways, then the side, then the red antifouling bottom rolls into view. Foam pours off the rising side. |
| **Near-vertical end** | Titanic's stern "reached an angle of nearly 90 degrees" ([Worcestershire museums](https://www.museumsworcestershire.org.uk/wp-content/uploads/2021/05/15.-Death-of-a-Titan.pdf)); Hood's stern section "sank vertically within seconds" ([napoleonvswellington](https://napoleonvswellington.org/2015/05/hood.html)) | Only a small stub of the end shows, ringed by a bright collar, with a long shadow |
| **Trapped air** | Titanic: stern "not completely full of water as it sank… implosions of trapped air" (museum PDF); Hood survivors "likely saved by air bubbles… that propelled them to the surface" | Boils during the plunge and bursts continuing after the ship has gone |
| **No suction vortex** | MythBusters: "Neither Adam nor Jamie were sucked under… not even when they were riding directly on top of it"; Titanic baker Joughin stepped off the stern ([MythBusters wiki](https://mythbusters.fandom.com/wiki/Sinking_Titanic_Myth?oldid=5002)) | Do not draw a whirlpool |
| **Oil** | Bismarck: "oil from the ship rose to the surface" (USNI). Sea Diamond wreck: a "long, continuous release… steady stream of 'bubbles' of oil"; HFO surfaced as 5–10 ml "pearls" that "flattened… into large, thick 'coins'" and then spread into sheens; leaked for >1 year ([ITOPF](https://www.itopf.org/fileadmin/uploads/itopf/data/Documents/Papers/interspill09_seadiamond.pdf)) | A thick black core over the wreck, a rainbow/sheen fringe, drifting downwind, persisting |
| **Gas plume surfacing** | Subsea blowout studies: the plume rises at **5–10 m/s in the centre**, far above single-bubble speed (~0.25 m/s). At the surface the water "turns and moves in a horizontal layer away from the center", making a "boil zone" ([BSEE report 287](https://bsee.gov/sites/bsee.gov/files/osrr-oil-spill-response-research//287aa.pdf)) | A domed upwelling with a white churned centre, then a foam rim carried outward. Debris is pushed away from it. |

Timing anchors for gameplay (from `claude/damage-model-research.md`): sinking takes minutes (Hood ~3 min, Barham ~4 min) to hours (Musashi ~9 h). The *visual* final phase (deck awash → gone) is short: **~20–60 s for destroyers, 1–2 min for capital ships** in the prototype. Compress time in the plunge if needed, but never in the boils: their lag after the ship disappears is what makes the moment read.

---

## 2. Model

### 2.1 Pose (input from the damage model)

Per hull segment (one, or two after a break): pivot x_p on the centreline at the waterline, sinkage s, pitch θ (+ = bow up), roll φ.

```
r = p_local - (x_p, 0, 0)
roll:   y1 = y cosφ - ζ sinφ ;  z1 = y sinφ + ζ cosφ
pitch:  x2 = x cosθ - z1 sinθ ; z2 = x sinθ + z1 cosθ
world:  X = x_p + x2,  Y = y1,  Z = z2 - s
```

- The prototype keyframes (t, s, θ, φ) are smoothstep-interpolated. After the last key the wreck keeps descending at v_desc ≈ 7–8 m/s (approx.; Titanic bow estimates are in that range).
- In game, take these from the flooding model. For a break, each segment gets its own pose with the pivot at the break.

### 2.2 Crossing foam and contact collar (world foam canvas)

Sample the hull surface: deck, sides, bottom, raised layer tops, and cut faces for breaks. Each step:

```
down = Z_prev > 0 >= Z ;  up = Z_prev < 0 <= Z ;  vz = (Z − Z_prev)/dt
w_down = 0.25 + 0.75·smoothstep(−vz, 0.03, 0.8 m/s)      # pouring over the deck/edge
w_up   = 0.55·smoothstep(vz, 0.05, 1.0 m/s)              # water cascading off a rising end
src    = min(splat(w)·k, 0.8)                            # capped < 1 so the noise breakup still bites
W      = columns containing hull surface both above and below 0      # the current waterline cut
collar = exp(−(dist_out(W)/1.3 m)²)·(0.18 + 0.82·smoothstep(|vz| near surface, 0.05, 1.2))
fresh  = max(fresh·e^{−dt/3 s}, blur(src + collar, 0.5 m))
resid  = resid·e^{−dt/25 s} + 0.5·fresh·(1 − e^{−dt/3 s})   # same two-tier scheme as wake v2.1
```

- Because foam is deposited where the surface crosses, **the white line sweeps along the deck exactly as the ship goes under**, front first or back first, with no special cases.
- A slow settle gives a thin band. The plunge gives a wide, bright collar.
- The wake's two-tier fresh/residual foam scheme (τ 3 s / 25 s) is reused, so sinking foam looks like the same material.

### 2.3 Air boils (water in = air out)

- Coarse interior volume points carry a compartment id; compartments do not span a break.
- Each step, compute each compartment's submerged fraction f (relative to t = 0, so the initial draft is not "flooding"). The air displaced is `dV = Vc·Δf`.
- **Vent** = the compartment's highest deck point.
  - Vent above water: the air escapes to the atmosphere. p_hold ≈ 0.5 of it is held behind closed hatches.
  - Vent under water: release `dV + held·dt/3 s`. A share p_trap ≈ 0.35 goes to the segment's trapped pool, and the rest is quantised into boil events of 15 m³ to Vc/25.
- **Boil event at depth d:**
  - surfaces after d / 2 m/s (plume rise, approx.; plume centre speeds 5–10 m/s per BSEE, slower as it entrains);
  - size `S = 0.9·V^{1/3} + 0.10·d` (plume spread ~0.1·depth, approx.);
  - intensity `clamp(1.15 − 0.008·d, 0.35, 1)`;
  - position jittered ±0.25 B (several openings).
- **Trapped pool:** burps at most ~3 per second, draining slowly while afloat (bulkheads failing) and with τ ≈ 14 s once under. 4 % of burps are a "bulkhead collapse" taking 15 % of the pool. The source is the wreck's top point as it descends, so post-sinking boils come later, wider, fainter and wander (glide).
- **Boil shape (analytic, per event age a):**
  - `R = S(0.5 + 1.5(1 − e^{−a/ts}))`, ts = 1.5√(S/4) s, life τb = 3.5√(S/4) s;
  - white churned centre (fades at 0.6 τb), a foam rim at q = r/R ≈ 0.95 with radial streaks (cos(k·angle), k 11–18), and a long faint tail (5 τb);
  - a dome in η for lighting;
  - overlapping boils combine as `max + 0.35·min`, not sum, to avoid white blow-outs.

### 2.4 Closure slam and ring

When a segment has no surface above z = 0:
- a boil with `S = 3 + 0.9·√(last above-water area)`, I = 1;
- an η ring: radius 5 m/s·a, wavelength ~19 m, Gaussian envelope widening 6 + 0.6a, decaying e^{−a/15}/√(1 + R/20). Lighting only;
- tanks rupture: an oil release of ~1 % of fuel volume;
- ~25 debris points spread over ~0.3 L × 0.15 L.

### 2.5 Oil

- **Spreading:** Fay gravity–inertial puddles, `R = k1(Δ g V t²)^{1/4}` with k1 ≈ 1.14 and Δ = (ρw − ρo)/ρw ≈ 0.04–0.08 for heavy fuel. The later regimes are gravity–viscous `R = k2(Δ g V² t^{3/2}/ν^{1/2})^{1/6}` and surface tension. Coefficients vary by source: NOAA GNOME uses (1.53, 1.21, 1.45) ([GNOME spreading](https://gnome.orr.noaa.gov/doc/pygnome/_sources/autoapi/gnome/weatherers/spreading/index.rst.txt)), Fay's originals are commonly quoted as 1.14 / 1.45 / 2.30 (unverified in-session).
- **Real slicks spread faster** in waves and wind ([arXiv 2403.06530](https://arxiv.org/html/2403.06530v1): Fay–Hoult "markedly lower than… observed"). The prototype therefore uses a time scale ×1.5 plus drift of ~3 % of wind (0.12, 0.04 m/s).
- **Emission:** continuous leak puddles from damaged tanks (rate per leak 0.03–0.3 m³/s in the prototype), rising with depth delay, plus a closure release. Edges are ragged via world noise.
- **Colour by thickness** ([Bonn Agreement codes via AMSA](https://www.amsa.gov.au/sites/default/files/2014-01-mp-amsa22-identification-oil-on-water.pdf)), stylised:

| Code | µm | Look | Prototype |
|---|---|---|---|
| 1 Sheen | 0.04–0.3 | silvery/grey | +0.07 lighten |
| 2 Rainbow | 0.3–5 | interference colours | hue cycles with log thickness + noise |
| 3 Metallic | 5–50 | blue/purple/brown, single colour | purple-brown tint |
| 4–5 True colour | 50–200 / >200 | patchy → continuous dark | near black, 70 % |

- **Oil damps capillary ripples.** Write it into `roughness_delta` (negative), the same channel as the wake slick. Foam churned through thick oil turns brown and less opaque (mousse look).

### 2.6 Debris

- Release points from deck surface going under (p ≈ 0.1 % per deck sample crossing), plus a burst at closure.
- Velocity = drift + Σ boil outflow `2·I·e^{−a/3}·(r/R)·e^{−(r/R)²}` (radial).
- In game: small sprite particles (planks, cork floats, rafts, life rings) with slow spin. A few hundred per ship at most.

### 2.7 Sprite treatment (the part the foam sits around)

- **Height per sprite pixel:** layer height (hull_base = deck F, turrets F + 2.5, hull_upper F + 7…20) → local (x, y, ζ) → pose → world (X, Y, Z). Do this in the vertex shader: treat each sprite layer as a 3D quad at its height and transform it. The orthographic top-down projection then foreshortens a pitching hull automatically.
- **Above water:** lit (Lambert with the rotated face normal) plus a darker "wet" band within ~1.2 m of the water.
- **Below water:** `mix(sprite, water, 1 − 0.85·e^{−depth/3 m})`. Fully hidden below ~10 m.
- **Shadow:** offset by `Z/tan(sun_elev)` along the sun direction, soft, ~40 % darkening, on the surface layers only.
- **Extra sprites shipgen must export** (sprite pipeline consequence):
  - **side elevations** (port/starboard, with boot-top and red antifouling), used once |list| or |trim| exposes them;
  - a **bottom/keel sprite** (antifouling red, keel line, shafts and rudder) for capsized hulls;
  - **cut-face sprites** (dark torn section at a given x) for breaks;
  - a per-layer **height table**.

  The prototype draws these faces from a point cloud. In game they are 3–5 extra quads per segment, drawn only when facing up.
- **Optional pseudo-perspective:** scale = 1 + Z/H_cam (H_cam ~ 300–600 m) exaggerates a rising stern. Artistic choice; untested.

### 2.8 Composite order

water (η, roughness incl. oil slick) → oil colour → **submerged hull (depth-tinted)** → wake + sinking foam (crossing, collar, residual, boils, slam) → debris → shadows → **above-water hull** → spray / steam / smoke.

This is the wake doc's order, with the sprite split at the waterline.

---

## 3. GPU / runtime implementation

| Piece | How | Cost (estimate) |
|---|---|---|
| Sink canvas | One world-anchored RG16F RT per sinking ship (fresh, resid), ~256–512² covering ~1.6 L × 0.9 L, alive until foam has faded (~2 min), then free it | 0.5–1 MB each |
| Crossing foam | Draw the hull mesh (low-poly, ~200 tris) top-down into the canvas. The vertex shader gets **both** previous and current pose. The fragment computes Z_prev and Z_now and outputs w_down/w_up on a sign change, with additive blend. Missed thin crossings at high speed: also emit when \|Z\| < vz·dt | 1 draw |
| Waterline cut W | Same pass with 2 extra channels (Z > 0, Z < 0) under MAX blend → W = both | free |
| Collar | Dilate W by 3–4 taps (or a 2-pass jump flood on the small RT), times agitation | ~0.05 ms |
| Decay / residual | One full-screen pass on the canvas per sim step (10–20 Hz) | ~0.05 ms |
| Boils, slam, rings, oil | Analytic in the water shader from event buffers (≤ 64 boils, ≤ 4 rings, ≤ 64 puddles), early-out on bounding circles, same pattern as the blast doc | a few ALU per event per covered pixel |
| Air bookkeeping | CPU: per compartment, submerged fraction from the damage model (it already tracks flooding) → event emission | negligible |
| Debris | CPU or GPU particles | negligible |

**Prototype timing (numpy, 2-core cloud box):**

| Grid | Step | Render |
|---|---|---|
| 553×273, dx 0.35 m, ~144k hull points | 33 ms | ~175 ms |
| Iowa, dx 0.75 m | ~41 ms | ~190 ms |

All of it is splat/blur/bincount work that maps 1:1 to the GPU passes above.

---

## 4. Prototype findings

- **Bow-first (Fletcher):** foredeck awash at ~30 s with a thin crossing band. Plunge 42–60 s: a white trail along the foredeck, boils popping over the submerged forward compartments, the stern stub rising (shortened sprite plus a long shadow) inside a bright collar. Gone at 60 s, then a slam and a ring, and trapped-air boils keep coming for ~30–50 s, drifting and widening.
- **Stern-first (Baltimore):** the mirror image. It reads clearly as a different event because the bow sprite (pointed) is what rises.
- **Capsize (Iowa):** the deck slews, the side and then the red bottom roll into view. Cascade foam pours off the rising side along the full length (the w_up term). Floating keel-up with a small exposed bottom, then it founders. Underwater superstructure stays faintly visible on the low side.
- **Break in two:** the torpedo boil at the break, then the V. Both ends rise, there are two collars and two closure slams ~3 s apart, and the boils are concentrated at the break.
- **Tuning notes:**
  - Crossing foam must be capped below 1, or the submerged deck reads as white paint.
  - Combining boils as max + 0.35·min (not sum) was needed.
  - Oil at physical Fay rates is fine for minutes. The prototype's first try (×8 time scale, 4 % of fuel at closure) swamped the scene.
  - The debris colour must be lighter than the water, or it reads as dirt in the foam.
- **Not modelled:**
  - spray/steam (boiler steam bursts when cold water reaches hot boilers: white puff particles, a good cue for "machinery flooded");
  - magazine explosions (separate system);
  - survivors and rafts;
  - water pouring *out* of hull openings on a rising end (could reuse w_up as a particle emitter);
  - sea-state interaction (in rough water, raise thresholds and shorten foam life).

## 5. Next steps (Claude Code side)

1. Damage model → per-segment pose (s, θ, φ) and per-compartment flooded fraction at 10–20 Hz. The sinking VFX consumes these and nothing else.
2. shipgen: export side, bottom and cut-face sprites plus the layer height table (§2.7).
3. Implement the sink canvas (crossing + W + collar + decay) as a hull-mesh pass.
4. Add boil / ring / oil event buffers to the water shader, reusing the blast-doc event pattern and `roughness_delta`.
5. Tune against footage at 3 scales (DD, CA, BB) and 3 modes (end plunge, capsize, break).

## Sources

- USN War Damage Report, destroyers, torpedo/mine — https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-torpedo-mine-damage.html
- "I Escaped the Bismarck", Naval History 1995 — https://www.usni.org/magazines/naval-history-magazine/1995/february/i-escaped-bismarck
- Museums Worcestershire, "Death of a Titan" — https://www.museumsworcestershire.org.uk/wp-content/uploads/2021/05/15.-Death-of-a-Titan.pdf
- "Why did so few men survive the sinking of HMS Hood?" — https://napoleonvswellington.org/2015/05/hood.html
- MythBusters, Sinking Titanic myth — https://mythbusters.fandom.com/wiki/Sinking_Titanic_Myth?oldid=5002
- BSEE OSRR report 287 (subsea gas plume, boil zone) — https://bsee.gov/sites/bsee.gov/files/osrr-oil-spill-response-research//287aa.pdf
- ITOPF, Sea Diamond (Interspill 2009) — https://www.itopf.org/fileadmin/uploads/itopf/data/Documents/Papers/interspill09_seadiamond.pdf
- AMSA, Identification of oil on water (Bonn codes) — https://www.amsa.gov.au/sites/default/files/2014-01-mp-amsa22-identification-oil-on-water.pdf
- NOAA GNOME spreading module — https://gnome.orr.noaa.gov/doc/pygnome/_sources/autoapi/gnome/weatherers/spreading/index.rst.txt
- Thin-film oil spreading in waves, arXiv 2403.06530 — https://arxiv.org/html/2403.06530v1
- Project: `claude/wake-vfx-research.md`, `claude/muzzle-blast-water-vfx.md`, `claude/damage-model-research.md`, `claude/sprite-pipeline.md`