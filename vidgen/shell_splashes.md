# Shell Splashes — Implementation Brief

Context for Claude Code: this is the design spec for naval shell splash VFX in an RTS with a 3/4 camera and thousands of simultaneous splashes in a line of battle. Splash sizes and timings are **design estimates** (scaled from caliber and tuned against period photos), not measured data. Historical dye facts are sourced at the bottom.

## Key decisions

- Keep the 3/4 camera; couple pitch to zoom (shallow up close, near top-down at strategic zoom).
- A splash is a 32-byte GPU record + a clock. No per-frame CPU work. All animation is a pure function of `(now - t0)` in shaders; deterministic from seed (replay/network friendly).
- Four LOD tiers chosen by projected column height in pixels; continuous crossfade, no popping.
- Below 2 px, splashes become a foam + dye stamp in a world-space sea-stain texture.
- Overdraw is the real cost, not instance count: composite translucent splashes at half resolution.
- Dye color per firing ship is both historical and the main readability tool.

## Splash anatomy (16-inch miss; scale times with √H)

1. **Impact, 0–0.3 s** — low white crown flares as a thin cone, ~15–25 m across. No flash for AP.
2. **Sheet and jet rise, 0.3–4 s** — dense white column ~10–15 m wide; central jet (cavity collapse) punches through and reaches peak height.
3. **Apex and blossom, 4–5 s** — top stalls and mushrooms into a ragged crown, opaque white → grey-white spray. Dye strongest here.
4. **Collapse, 5–9 s** — rain curtain falls back; low base surge rolls out to ~2–3 column widths.
5. **Residue, 10–60 s** — mist drifts downwind; white foam disc (+ dye stain) marks the impact point.

Optional (hero tier only): AP with delay fuze can produce a low white dome and a second dirtier spout shortly after impact (underwater burst).

## Size by caliber

```
H = H16 * (d / 0.406 m)^k      H16 ≈ 73 m, k ∈ [0.75, 1.0]
t_apex = sqrt(2H / g)
column_life ≈ 2 * t_apex + 1 s
width ≈ 25 * d
foam_radius ≈ 1.5 * width, lifetime 30–60 s (all calibers)
```

k = 1 is geometric scaling; k = 0.75 is energy scaling (makes small calibers relatively taller). Values below use k = 1.

| Caliber | Typical user | Peak H (m) | Width (m) | Apex (s) | Column life (s) |
|---|---|---|---|---|---|
| 18.1 in / 460 mm | Yamato | 83 | 12 | 4.1 | 9 |
| 16 in / 406 mm | Iowa, Nagato | 73 | 10 | 3.9 | 9 |
| 15 in / 381 mm | Bismarck, Queen Elizabeth | 69 | 10 | 3.7 | 8 |
| 14 in / 356 mm | KGV, Kongō, New York | 64 | 9 | 3.6 | 8 |
| 12 in / 305 mm | Dreadnought era | 55 | 8 | 3.3 | 8 |
| 11 in / 283 mm | Scharnhorst | 51 | 7 | 3.2 | 7 |
| 8 in / 203 mm | Heavy cruisers | 37 | 5 | 2.7 | 6 |
| 6 in / 152 mm | Light cruisers | 27 | 4 | 2.4 | 6 |
| 5 in / 127 mm | Destroyers, secondaries | 23 | 3 | 2.2 | 5 |

## What changes the look

**Angle of fall** (from range) is the biggest modifier after caliber. US 16-inch AP Mk 8 reference:

| Range | Angle of fall | Time of flight | Look |
|---|---|---|---|
| 5,000 yd / 4.6 km | 2.9° | 6.8 s | Low leaning spray fan; frequent ricochets |
| 10,000 yd / 9.1 km | 6.8° | 14.5 s | Leaning column, ~70% height, elongated foam |
| 20,000 yd / 18.3 km | 17.9° | 32.6 s | Near-vertical, full height |
| 30,000 yd / 27.4 km | 34.1° | 56.6 s | Vertical, round foam disc |
| 35,000 yd / 32 km | 44.9° | 74.4 s | Tallest, cleanest pillar |

Drive from angle of fall θ:
- **Lean** — tilt column toward direction of travel at shallow θ.
- **Height multiplier α(θ)** — 0.5 at 3°, ramping to 1.0 above 15°.
- **Foam ellipse stretch** along the shell track at shallow θ.

Other modifiers:
- **Ricochet** — for a fraction of sub-8° impacts, spawn a second smaller splash 300–800 m downrange.
- **AP vs HE** — AP: clean white water. HE: brief orange flash, shorter broader column, grey-black smoke mixed in.
- **Hits** — no water column; flash, smoke, debris on the ship. Near-misses alongside drench the deck and briefly hide the hull.
- **Salvo pattern** — long ellipse, ~5–8× longer along range than across (USS Massachusetts at Casablanca: ~2 mils deflection, 200–300 yd in range).
- **Salvo timing** — US triple turrets fired ~60 ms apart (left, right, centre) via delay coils. Add time-of-flight jitter so a 9-gun salvo lands as a ripple over 0.2–0.5 s, not one frame. **Implement this early; it is most of the "glorious broadside".**

## Dye loads

Historical basis: USN introduced "splash colors" in 1930; most navies used them in WWII so ships firing at one target could spot their own fall of shot. Dye sat between the AP cap and windscreen (USN: dry powder in paper bags, 1.5 lb nominal on the 16" Mk 8, up to 3 lb as weight trim). British windscreens were vented to let water carry the dye out.

| Navy | Ship | Dye | Confidence |
|---|---|---|---|
| USN | Iowa | Orange | sourced |
| USN | New Jersey | Blue | sourced |
| USN | Missouri | Red | unverified |
| USN | Wisconsin | Green | unverified |
| USN | North Carolina | Green | sourced (1945) |
| USN | Washington | Orange | sourced (1945) |
| USN | South Dakota | Blue | sourced (1945) |
| USN | Indiana | Red | sourced (1945) |
| USN | Massachusetts | Green | sourced (1945) |
| USN | Alabama | None | sourced (1945) |
| IJN | Nagato | Pink | sourced (secondary) |
| IJN | Mutsu | Black | sourced (secondary) |
| French | Jean Bart | Orange | unverified |
| French | Richelieu | Yellow | unverified |

IJN term: *chakushokudan* ("pillar coloring shell"); Type 1 AP shells carried a dye bag; Taffy 3 crews at Samar remembered brightly colored geysers. Whether Yamato's were red or undyed is disputed. German use is thinly evidenced (one anecdote of pink marker dye).

Implementation rules:
- Assign dye per ship, unique within a division (colors repeat across a navy). Palette ~7 colors + "none".
- Not neon: base and falling curtain stay mostly white; tint upper column and crown 30–50% toward dye; tint grows as the column thins. Mist and foam stain hold color longest.
- Leave a faint dye tint in the foam stain for 30–60 s — this is what players read at high zoom.
- Colorblind-safe palette + optional "vivid" toggle.

## Camera

On-screen column height ≈ `H * cos(pitch) / metersPerPixel`.

| Zoom | View width (2560 px) | m/px | Pitch | 16" column on screen | Player reads |
|---|---|---|---|---|---|
| Hero | 600 m | 0.25 | 20–35° | 250+ px | Full anatomy, dye, mist |
| Tactical | 3 km | 1.2 | 40–50° | ~40 px | Columns, ripple, colors |
| Fleet | 10 km | 4 | 55–65° | ~8 px | Thin pillars, foam |
| Strategic | 30 km+ | 12+ | 70–85° | ~1 px | Foam + dye stains only |

- Use cylindrical (vertical-axis) billboards, not screen-facing quads — screen-facing looks like paper cutouts from above.
- Occlusion rule: dither columns to ~40% opacity where they cover the selected ship or the cursor.

## Rendering architecture

### Per-splash record (32 bytes)

| Field | Size |
|---|---|
| position (float3) | 12 B |
| t0 impact time (float) | 4 B |
| caliber (half) | 2 B |
| angle of fall (half) | 2 B |
| heading of travel (half) | 2 B |
| dye RGBA8 | 4 B |
| seed + flags (AP/HE, ricochet, …) | 4 B |
| padding | 2 B |

Ring buffer of 16k records = 512 KB. Simulation appends one record at impact; nothing else touches it CPU-side.

### Frame pipeline

1. **Stamp** — on spawn, splat foam disc + dye tint (+ elongated sun-direction shadow blob) once into a world-space sea-stain texture (clipmap around camera). Global per-frame decay fades it. Constant cost regardless of count.
2. **Cull and classify** (compute) — frustum + lifetime cull; compute projected column height `p` in px; append to one or two tier buckets with blend weight; write indirect draw args.
3. **Draw tiers** — one instanced indirect draw per tier. Vertex shader evaluates height/lean/width/crown from analytic curves; pixel shader uses a shared column texture + world-space noise seeded per splash.
4. **Composite** — translucent layers to half-res buffer (mist can go quarter-res), depth-aware upsample, before ocean foam and HUD.

### LOD tiers (by projected column height p)

| Tier | When | Draws | Cost |
|---|---|---|---|
| T0 Stain | p < 2 px | Stain stamp only; optional 2 px glint sprite for the first ~4 s so the salvo ripple still flickers | stamp once, 0–1 point |
| T1 Pillar | 2–16 px | One cylindrical billboard, procedural gradient column, dye tint at top | 2 tris |
| T2 Column | 16–96 px | Column + crown + mist billboards, flat expanding base-surge ring, 8–16 GPU spray sprites | ~40 tris |
| T3 Hero | p > 96 px, capped to nearest 32–64 | Vertex-animated column mesh, soft particles, rain curtain, optional underwater burst, deck wetting | few hundred tris |

### Zoom continuity

- Crossfade adjacent tiers across a ±25% band of `p` with dithered alpha. `p` is continuous in zoom, so no hysteresis needed.
- **Size floor:** if true width < 2 px, widen to 2 px and scale alpha down by the same factor (constant perceived brightness → fades with altitude, never pops).
- True world scale above the floor; the floor is the single realism/readability knob.

### Overdraw

- Half-res compositing (4× cheaper); quarter-res mist.
- No sorting: splashes are near-white, so weighted blended OIT or unsorted premultiplied alpha is fine.
- Spend detail on silhouette: noisy hard-ish edge, soft core.

### Lighting

- Cylinder normal → wrap diffuse + forward-scatter term so backlit columns glow at the rim (reads as water, not smoke).
- Shadows via the stain-texture blob along sun direction for T1/T2.

### Budget target

10,000 live splashes, ~300 at T2, ≤64 at T3: well under 1 ms GPU excluding overdraw. Profile the composite first.

## Animation curves (T1/T2)

With `t_a = sqrt(2H/g)` and `tau = t / t_a`:

```
h(tau)   = H * alpha(theta) * (1 - (1 - min(tau, 1))^2)     // column top height
rho(tau) = tau < 1 ? 1 : exp(-1.5 * (tau - 1))               // column opacity
crown radius: 0.5 -> 2.0 column widths over tau 0.8..1.6
dye mix: 0.1 at base -> 0.5 at crown; 0.2 at impact -> 0.6 by tau = 1.5
base-surge ring: radius linear to 2.5 widths by tau = 2.5, faded by tau = 4
```

## Suggested build order

1. T0 + T1 (carry strategic view and the 10k load).
2. Salvo ripple (60 ms firing order + time-of-flight jitter) before polishing any single splash.
3. Dye palette (~7 + none, colorblind-checked, vivid toggle).
4. T2, then profile overdraw at tactical zoom with two full battle lines firing.
5. Tune k and H16 against 10–15 reference photos (Iowa-class firing trials, Samar, Casablanca).
6. Decide on T3 extras: ricochets, delayed underwater bursts, deck wetting.

## Sources

- NavWeaps, USA 16"/45 Mark 6 — https://navweaps.com/Weapons/WNUS_16-45_mk6.php (range table, dispersion, delay coils, 1945 dyes)
- NavSource, Splash Colors — https://www.navsource.org/archives/01/pdf/016292s.pdf
- NavWeaps, Japanese projectile terms — https://navweaps.com/Weapons/WNJAP_projectiles.php
- NavWeaps, Japanese 46 cm/45 Type 94 — https://navweaps.com/Weapons/WNJAP_18-45_t94.php
- Naval Gazing, Shells Part 3 — https://www.navalgazing.net/Shells-Part-3
- The Tides of History, Japanese 16.1"/45 — https://thetidesofhistory.com/2020/09/27/japanese-16-1-45-3rd-year-type-gun/
- NHHC, The Battle off Samar — https://history.navy.mil/browse-by-topic/wars-conflicts-and-operations/world-war-ii/1944/samar.html
- Wikipedia, Mountbatten pink — https://en.wikipedia.org/wiki/Mountbatten_pink
- Scientific American (1911), A Landsman's Log — https://www.scientificamerican.com/article/a-landsmans-log-aboard-the-battlesh-1911-11-11