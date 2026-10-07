# Muzzle blast on the water surface — VFX research (2026-10-05)

Companion to `claude/wake-vfx-research.md`. Reference code: `claude/muzzle_blast_ref.py` (numpy, ~150 lines). Frame strip delivered in chat: `muzzle_blast_frames.png` (Iowa-type broadside, 20° elevation, t = 0.08 → 4 s).

Reference photo: USS Iowa full broadside, 1 July 1984, off Puerto Rico. Turret III fired a moment before I and II ([historyofwar.org](https://www.historyofwar.org/Pictures/pictures_USS_Iowa_BB61_broadside_1984.html)), so there are two overlapping circular patches that make a "heart".

---

## 0. TL;DR

1. **The pulse in the photo is not a wave, and it isn't foam.** It is a **change in surface roughness** (short wind ripples) that changes how sun and sky reflect. The blast front sweeps out at roughly the speed of sound. Right behind it there is a short outward gust (u ≈ Δp/(ρc), ~2–7 m/s at the visible edge) that roughens or lays down the ripples, like a giant instantaneous *cat's paw*. The real height change is millimetres. **So render it as a roughness/glint modulation, not through η or the FFT bake.**
2. **Three layers per blast event:**
   - (a) **front ring**: a thin dark leading edge expanding at ~345–400 m/s;
   - (b) **frost disc**: a lighter, silvery roughened area behind the front that fades in ~1.5–4 s;
   - (c) **near-muzzle scour foam** + spray, written into the **same crest-foam channel the bow wave uses** (τ ≈ 6–8 s, same world-space foam texture and threshold shader).
3. **One number scales everything:** the blast length λ = (E/p₀)^⅓, with E the blast energy of the propellant. It is the same W^⅓ (Hopkinson) scaling the audio doc uses for pulse duration, so sound and visuals stay consistent per calibre.
4. **Cheapest implementation:** analytic in the water shader from a small buffer of active blast events (≤ 32). No render target and no simulation. Each event lives ≤ ~4 s, so most frames have 0–6 active events. The foam part is a decal stamp into the existing foam composite.

---

## 1. What the photo shows

Scale: Iowa is 270 m long, ≈ 0.14 m/px in the 2000 px image.

| Feature | Measured / observed | Interpretation |
|---|---|---|
| Two near-circular patches, lighter / "frosted" | Right (turret III) ring radius ≈ 75–80 m | Area the blast front has already crossed |
| Circle centres offset **outboard** of the muzzles by ~30–40 m | Not centred on the ship | Muzzle blast is directional (strong along the bore) → the iso-pressure footprint is an offset circle |
| Sharp edge with a darker rim | Leading edge | The front is still moving: snapshot ≈ 0.2 s after firing (78 m / ~345 m/s) |
| Faint concentric inner rings, seam where the two patches meet | Inside the discs | Secondary (negative-phase) gust, and two fronts colliding |
| Little white water at the muzzles | Moderate elevation | Foam needs the near field or gas jet to reach the water; at low elevation it is much bigger |

Wikipedia's 16"/50 page says the same: the sea "is roiled by the guns' muzzle blast, which creates the illusion of motion in still photos" ([Wikipedia](https://en.wikipedia.org/wiki/16-inch/50-caliber_Mark_7_gun); [Naval Gazing](https://www.navalgazing.net/Did-Iowa-Move-Sideways-During-a-Broadside)). The ship does not move sideways meaningfully.

An analogue that is well documented in nuclear-test literature: the expanding "slick" (a dark ring) and "crack" (a white patch) on water, produced when a shock meets the surface ([Glasstone & Dolan ch. 2](https://www.abomb1.org/nukeffct/enw77b2.html)). That case is an underwater shock. The visual vocabulary (a fast dark ring, then a light patch) is the same.

> Mechanism caveat: I found no paper that explains the photo itself. The roughness and gust mechanism is my inference from blast physics (post-shock particle velocity) plus how cat's paws look. It is a confident explanation of the *look*, and enough for VFX.

---

## 2. Physics baselines

### 2.1 Blast energy and length scale

Fansler's modified ideal scaling for gun muzzle blast ([Fansler 1998, BRL](https://pdfs.semanticscholar.org/3d38/1586308286c8c6c7c55114167d49cbd9e903.pdf); [DTIC ADA330051](https://apps.dtic.mil/sti/pdfs/ADA330051.pdf)):

```
E      = available blast energy  (propellant energy − projectile KE − barrel losses)
λ      = (E / p₀)^(1/3)                                  p₀ = 101 325 Pa
β(θ)   = μ cos θ + sqrt(1 − μ² sin² θ),   μ ≈ 0.78       θ = angle from the bore axis
λ'     = λ · β(θ)                                         (paper adds small barrel-emptying terms; ignore)
Δp/p₀  = 0.11 (λ'/r) + 0.0061 (λ'/r)²                     peak overpressure, far field
```

β gives ~8× stronger blast straight ahead than straight behind. Game estimate: E ≈ 0.45 · m_prop · 3.8 MJ/kg. The 0.45 is my estimate: single-base propellant ≈ 3.5–4 MJ/kg, and a 16" shell takes ~0.3–0.36 GJ of ~1.1 GJ. Several guns firing together: sum E, so λ ∝ N^⅓.

**Front speed:** Rankine–Hugoniot, U_s = c₀·sqrt(1 + (γ+1)/(2γ)·Δp/p₀). Integrate it once into a **single LUT t_arrival(r/λ')·λ'/c₀ for every calibre** (the prototype does this).

### 2.2 Numbers for the fleet

Visible-edge threshold p_vis = 1 kPa (gust ≈ 2.4 m/s), low-elevation fire. These are the far-field formula's values. The near field (< ~λ) is underpredicted, so use the scaled-distance foam rule in §3.

| Mount | m_prop (kg) | λ (m) | r_vis forward | r_vis side | r_vis rear | front reaches side r_vis |
|---|---|---|---|---|---|---|
| 20 mm | 0.03 | 0.8 | 16 m | 6 m | 2 m | 0.01 s |
| 5"/38 twin | 2×7 | 6.2 | 123 m | 43 m | 15 m | 0.12 s |
| 8"/55 triple | 3×41 | 12.8 | 254 m | 89 m | 31 m | 0.25 s |
| 14" triple | 3×150 | 19.7 | 392 m | 138 m | 48 m | 0.39 s |
| 16"/50 single | 297 | 17.1 | 341 m | 120 m | 42 m | 0.34 s |
| 16"/50 triple | 3×297 | 24.7 | 492 m | 173 m | 61 m | 0.49 s |

**Photo check:** for a 16" triple turret the side distance where Δp = 2.5 kPa is ≈ 74 m, matching the ≈ 78 m ring. Use **p_vis ≈ 1–3 kPa as the art knob**: 2.5 kPa reproduces the photo footprint, 1 kPa gives the dramatic version. Sea state also matters: in rough water the effect is less visible, so raise p_vis with wind.

### 2.3 Why not a height field

The impulse (~Δp·T₊/2 ≈ 20–30 Pa·s at the visible edge) gives surface displacements of order millimetres at gravity-wave scales. That is invisible top-down. Only near the muzzle (tens of kPa plus the hot gas jet) does the water actually get torn up, into spray and white water. So **η/normals get nothing from the far-field blast.** Put it in a roughness channel.

### 2.4 Timescales (tunable, unverified)

- Front: 0.1–0.5 s to full size, depending on calibre (table). At 60 fps a 16" front moves ~6 m per frame, so evaluate it analytically, not by stamping.
- Frost recovery: ripples regrow on a seconds timescale under wind. **τ_frost ≈ 2 s** (1.5 s in fresh wind, 4 s in calm).
- Scour foam: like breaking-crest foam, **τ ≈ 6–8 s** (the wake doc uses 8 s).
- Optional time stretch ×1.5–2 on the front for readability at gameplay zoom. The audio doc has the same question about time compression.

---

## 3. Recommended implementation

### 3.1 Data per event (one per turret salvo, or per gun if staggered)

`{ pos.xy (muzzle), h (muzzle height above water), bore azimuth, elevation, λ, t_fire }` in a small UBO/SSBO ring buffer (≤ 32). Delete an event when `t − t_fire > max(4·τ_frost, τ_foam·3)`. λ comes from the weapon definition (propellant mass × guns); it is the same parameter that drives the audio pulse.

### 3.2 Water shader, per pixel and per event (early-out on bounding circle r > 1.2·r_vis(0°))

```
d     = (P.xy − pos.xy, −h);  r = |d|;  cosθ = dot(d, bore3D)/r
λ'    = λ·β(cosθ);  Δp = p₀(0.11 λ'/r + 0.0061 (λ'/r)²)
t_arr = LUT(r/λ')·λ'/c₀;  age = t − t_fire − t_arr;  if age < 0 → skip
s     = saturate( ln(Δp/p_vis) / ln(p_sat/p_vis) )            p_sat ≈ 4–6 kPa
lead  = s · exp(−(age·c₀ / band)²)                            band ≈ c₀·T₊, T₊ ≈ 0.9 ms per m of λ
frost = s · (1 − exp(−(age·c₀/2band)²)) · exp(−age/τ_frost)
```

Combine events: `frost = max_i + 0.5·(Σ − max)` where two fronts are both active (the bright seam in the photo), and `lead = max_i`.

Use in lighting:
- **Roughness / slope variance:** σ = σ_wind · (1 + 2.5·frost − 0.7·lead). It drives the specular lobe width and glint.
- **Diffuse sky / sun scatter:** goes up with σ, which gives the silvery frosted disc. The leading edge flattens the ripples, so it goes dark.
- Optional: rotate the ripple anisotropy radially inside the disc (the gust is radial). This adds faint radial streaks, a subtle win.

Cost: a few ALU ops plus one LUT fetch per event per pixel, only inside bounding circles. The numpy prototype does 3 events over 100k px in ~20–40 ms on CPU. On GPU it is negligible.

### 3.3 Foam: reuse the bow-wave foam system

- **Same channel:** blast scour writes into the **crest-foam density** (fast decay, τ ≈ 6–8 s), not the wash channel. It is then shaded by the **same world-space tiled foam texture + threshold** (`foam = saturate((density − (1 − tex)·k)/softness)`), so blast foam and bow foam look like the same material.
- **Source shape:** `density = saturate(1.3 − (r/λ')/k_foam)^1.5 · exp(−age/τ_foam)`, k_foam ≈ 1.0 (art knob). Because λ' carries the directivity, the patch is automatically elongated along the bore azimuth and grows sharply as elevation drops. At point-blank or low elevation, also add a **jet-impingement lobe**: an ellipse along the bore ground track, length ~3–5 λ·cos(el), only when el < ~10°.
- **Texture direction:** sample the foam texture in **polar coordinates around the event** (radial anisotropy) instead of along-track as for the wake. This gives the radially streaked blast scour.
- **How to draw it:**
  - If the wake uses near-field stamps and ribbons, draw a **foam decal quad** per event (radius ≈ 2.5 λ). It writes `max()` into the same foam composite pass as the wake stamps.
  - If you later switch to the world-anchored foam RT alternative from the wake doc, splat it there.
  - Either way it composites after wake foam: `foam = max(wake, blast)`.
- **Spray particles:** same emitter type as the bow spray. Burst at the scour patch, count ∝ λ², and only when el is low or the muzzle height is < ~1.5 λ.
- **Wake interaction:** the frost does not erase wake foam (foam is on top). The far-wake "slick" in the wake doc (smoother, lighter water) is the **same roughness channel with the opposite sign**. Make roughness_delta a shared signed term: + blast frost, − wake slick.

### 3.4 Unified "surface state" contract (proposal for the wake system)

| Term | Writers | Decay | Used by |
|---|---|---|---|
| η / normal | wake FFT bake, (later) shell splash rings | — | lighting |
| foam_crest | bow sheet, bow peel, breaking crests, **blast scour**, shell splashes | 6–8 s | foam shader |
| foam_wash | propulsor wash | 45 s | foam shader |
| roughness_delta (signed) | **blast frost (+), blast leading edge (−)**, wake slick (−), optional rain or wind gusts | 2 s / long | specular σ, sky scatter |

Adding roughness_delta to the wake pipeline costs one extra scalar. It gives the blast effect and the far-wake slick for the same price.

### 3.5 Composite order (extends the wake doc)

water (roughness & normals) → wake + blast foam → hull_base → turrets → hull_upper → spray → **muzzle fireball/smoke sprites** (separate system, drawn above everything).

---

## 4. Prototype findings

- The heart-shaped union, the offset circles and the dark leading edge all come out of the analytic model without hand-placement (see frame strip).
- At 20° elevation the scour foam is small, which matches the photo. At 1 kPa the frost disc grows to ~170 m side and ~300+ m outboard; that is too big for gameplay framing. Start with p_vis ≈ 2–2.5 kPa.
- The far-field overpressure fit is invalid within ~λ of the muzzle. That is why foam uses the scaled-distance rule, not Δp.
- Not modelled: blast reflection off the own hull (an image source mirrored on the hull side; cheap to add as a second event at 0.5 strength) and the muzzle height and deck shielding for rear arcs.

## 5. Next steps (Claude Code side)

1. Add `blast_lambda` to the weapon definitions (propellant mass, guns per mount); share it with the audio bench.
2. Add the roughness_delta term to the water shader and implement §3.2 with an event buffer and a 1D arrival LUT.
3. Blast foam decal → existing crest-foam composite, polar-sampled foam texture.
4. Tune p_vis, τ_frost and k_foam against the photo (t ≈ 0.2 s frame) and against low-elevation reference footage.
5. Later: shell splashes and near misses use the same event buffer: roughness ring + foam_crest + optional η ring via wave particles.

## Sources

- Fansler, "Description of muzzle blast by modified ideal scaling models", Shock & Vibration 1998 — https://pdfs.semanticscholar.org/3d38/1586308286c8c6c7c55114167d49cbd9e903.pdf (also DTIC ADA330051)
- "16-Inch Gunblast Experiments", DTIC ADA210220 — https://apps.dtic.mil/sti/tr/pdf/ADA210220.pdf (not readable from here; worth checking for measured near-field values)
- 16"/50 Mark 7 gun (propellant 6×50 kg, roiled-sea note) — https://en.wikipedia.org/wiki/16-inch/50-caliber_Mark_7_gun
- Photo caption — https://www.historyofwar.org/Pictures/pictures_USS_Iowa_BB61_broadside_1984.html
- Naval Gazing, "Did Iowa move sideways during a broadside?" — https://www.navalgazing.net/Did-Iowa-Move-Sideways-During-a-Broadside
- Glasstone & Dolan, The Effects of Nuclear Weapons (slick & crack) — https://www.abomb1.org/nukeffct/enw77b2.html
- Wake system baseline — `claude/wake-vfx-research.md`; audio scaling — `claude/sound-design-gunfire.md`