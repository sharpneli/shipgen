# Muzzle flash and propellant smoke — VFX + visibility research (2026-10-07)

Companion to `claude/muzzle-blast-water-vfx.md` (the blast on the water: same λ, same event buffer), `claude/magazine-explosion-vfx-research.md` (oblique "VFX up" projection, flipbooks, fire lights, smoke shadows) and `claude/sound-design-gunfire.md` (same W^⅓ scaling). Reference code: `claude/muzzle_flash_ref.py` (numpy, ~450 lines: physics, photometry, smoke puffs, line-of-sight queries, a reference renderer) and `claude/figs_muzzle_flash.py`. Media delivered in chat: `mf_strip.png` (calibre × time, day and night), `mf_zoom.png` (the same salvo at four map zooms), `mf_los.png` (own-smoke obscuration over time).

Scope: every gun from 20 mm AA to the 2000 mm "turbocannon", day and night, top-down and zoomable. Smoke is modelled with the visibility calculation in mind: the same per-shot number that sets the smoke's on-screen opacity gives the optical depth along any line of sight.

Tags as in the other docs: **[INFERRED]** = my reasoning, fit or tuning value; **[UNCERTAIN]** = thin or conflicting sources.

---

## 0. TL;DR for the implementer

1. **"The muzzle flash" is mostly the *secondary* flash.** The propellant gas leaves the muzzle fuel-rich (CO, H₂). After the gas is re-heated at the Mach disk it mixes with air and burns a second time, as a ragged yellow-white fireball. The primary flash (hot gas at the muzzle) and the intermediate flash (a reddish disc at the Mach disk) are small and short. Flash reducers (potassium salts, cool triple-base powders, mechanical flash hiders) work by stopping the second burn. **The price is smoke.**
2. **One length scale per shot drives size and time:**
   - `λ_f = ((E_blast + P_sec·E_ab)/p₀)^⅓`. E_blast is the muzzle-blast doc's `0.45·m·Q`; E_ab ≈ 3.4–5 MJ per kg of propellant is the afterburn energy.
   - Fireball ≈ 1.6 λ_f across.
   - Secondary flash lasts **t_s ≈ 5 λ_f / c₀**. That fits ~6 ms for a rifle (Luo 2023) and ~100 ms for a 152 mm howitzer (Steward 2012).
   - Resulting values: **16″/50: 43 m fireball, 0.39 s. 20 mm: 1.9 m, 17 ms. 2000 mm: 195 m, 1.8 s.**
3. **The intermediate-flash disc sits ~20 calibres ahead of the muzzle for every gun.** That is the Mach-disk distance `x_M ≈ d·√(p_stag/p₀)`, and NavWeaps gives "20–25 calibres for larger weapons". It is the dark gap between the muzzle and the fireball, and it scales the whole shape with the gun.
4. **Day vs night is photometry, not two art sets.**
   - Blackbody luminance rises roughly as **T¹⁵** around 1500 K. A 1600–1900 K fireball is ~10³–10⁵ cd/m², so it is a few times to a few tens of times brighter than sunlit sea (~1500 cd/m²) and ~10⁸ times brighter than a night sea (~0.002 cd/m²).
   - Render the flash as one HDR emitter in physical units. Exposure (plus eye adaptation at night) produces both looks.
5. **Flash vs smoke is a per-propellant trade-off.** Make it data, not a special case.
   - Potassium salts are "the greatest single contributor" to muzzle smoke (US patent 4,315,785).
   - British flashless NF cordite was smoky; US flash-reducer additives made "a great deal of smoke" (Naval Gazing).
   - In the model, the 16″ SPCG flashless charge cuts the secondary-flash probability from 0.97 to 0.13 and the effective intensity ~100×, and **doubles the smoke**.
6. **Smoke is one conserved number per shot: its extinction area A (m²).** It is the smoke mass times the mass-extinction coefficient.
   - Each shot is a Gaussian puff that drifts, rises and spreads. Vertical optical depth (render alpha) and the optical depth along any line of sight (gameplay) are both closed-form from the same puff.
   - The 30 mm field measurement (Yan et al. 2023, CQMS 2.35 m² decadic = 5.4 m² natural) is reproduced to 5 %.
   - Per shot: **20 mm ≈ 0.5 m², 5″ ≈ 115 m², 16″ SPD ≈ 10,000 m², 16″ flashless ≈ 20,000 m², 2000 mm ≈ 870,000 m².**
7. **Visible at every zoom, by construction.**
   - Splat each emitter as a Gaussian with **analytic** normalisation and σ ≥ 0.6 px. The integrated intensity is then preserved, and the flash turns from a sprite into a blob into a bloomed point star as you zoom out.
   - Sub-frame flashes are averaged over the frame. A minimum on-screen duration is allowed if the Blondel–Rey effective intensity is held constant.
   - Cull on pixel contrast, not on size.
8. **Small guns: smoke can be pooled, not ignored.** A 20 mm round makes 0.5 m² (invisible). A twin 5″ at 15 rpm keeps a sight line 150 m downwind at ~75 % transmittance for as long as it fires. Merge rapid-fire puffs per mount into one trail.
9. **Cost:** the physics is a few dozen flops per shot. Rendering is ≤ 3–4 billboards per active flash (≤ 0.4 s each) plus one smoke puff per shot (merged). Large smoke at half resolution, as in the magazine doc. **< 0.3 ms GPU for a heavy night battle** [INFERRED].

---

## 1. What a muzzle flash is

### 1.1 The five components

| Component | Where | When / how long | Look | Cause |
|---|---|---|---|---|
| **Muzzle glow** (pre-flash) | At the muzzle | Before shot exit | Small reddish tongue, brightest in worn guns | Gas leaking past the driving band (NavWeaps) |
| **Primary flash** | 0 to ~½ x_M | From shot exit until the chamber empties (t_e) | Small, very hot, white-orange; "amongst the brightest" but dissipates fast | Propellant gas exiting behind the projectile, cooling as it expands (Wikipedia) |
| **Intermediate flash** | At the Mach disk, ~20–25 cal ahead (large guns) | Shot exit until the chamber pressure drops | **Reddish disc, slightly dished toward the gun**, brightest on the gun side | Gas recompressed by the Mach shock to near chamber temperature (NavWeaps) |
| **Secondary flash** | Beyond the Mach disk | Starts a few ms after shot exit; ~6 ms (rifle) to ~100 ms (152 mm), longer for bigger guns | **Ragged yellow-white fireball**, by far the largest and brightest | Fuel-rich gas (CO, H₂) mixing with air and igniting (Klingenberg & Heimerl) |
| **Sparks / embers** | Thrown forward | After the flash | Streaks | Unburnt grains, primer metal, salt crystals in flashless powder (NavWeaps). **Bag guns also throw burning silk and igniter fragments** [INFERRED] |

Sources: [NavWeaps tech-090](https://www.navweaps.com/index_tech/tech-090.php), [Wikipedia: Muzzle flash](https://en.wikipedia.org/wiki/Muzzle_flash), Heimerl, [Muzzle flash and alkali salt inhibition (DTIC)](https://apps.dtic.mil/sti/pdfs/ADA126129.pdf).

Points that matter for the model:
- **The secondary flash carries most of the radiated energy.** In Heimerl's words, the energy released in the secondary flash is comparable to that released inside the gun. My product-mix estimate agrees: ~5 MJ/kg of afterburn against ~3.8 MJ/kg of propellant energy.
- **What starts the secondary flash is the intermediate flash.** Combustion begins in the core of the intermediate-flash region, where oxygen is entrained just behind the Mach disk. Alkali salts act there, keeping the temperature below the ignition level ([Heimerl & Klingenberg, Fraunhofer EMI](https://publica.fraunhofer.de/entities/publication/42afc048-b6c2-4de7-b0f7-04ec39340251); [Klingenberg, DTIC ADA183911](https://apps.dtic.mil/sti/pdfs/ADA183911.pdf)).
- **It is erratic in small guns.** Photometer work on small arms found the primary flash consistent but the secondary flash inconsistent: one ammunition never produced it, another often did ([Dye, NDIA](https://ndia.dtic.mil/wp-content/uploads/2016/armament/18357_Dye.pdf)). Large guns with unsuppressed powder flash essentially every round (Iowa). **→ model the secondary flash as a per-shot Bernoulli event with probability P_sec** (§2.4).

### 1.2 Measured anchors

| Gun | Measurement | Source |
|---|---|---|
| 5.8 mm and 7.62 mm rifles | Flame + smoke radiation mostly 2–5 µm, **~6 ms total, peak ~2 ms** | [Luo et al. 2023](https://m.researching.cn/articles/OJbdbf3ec43082e758) |
| 152 mm howitzer, 3 munitions, 201 firings | **Combustion ~100 ms at 1200–1600 K**, dominated by H₂O and CO₂. Non-burning plume ~20 ms at 850–1050 K, emissivity ~0.36. Strong Na, K, Li, Cu, Ca lines | [Steward, Gross & Perram 2012](https://modis.gsfc.nasa.gov/sci_team/pubs/abstract_new.php?id=07813) |
| Tank gun | Large-calibre flash lasts **< 0.2 s** in the 3–5 µm band | [Telops application note](https://info.telops.com/Website-content-requests_07---LP---FAST-Thermal-Imaging---Tank-Muzzle-Flash-Analysis.html) |
| NH-type propellant, film | Reactions last of order 100 ms; the secondary flash "starts in a small region and gradually builds" a few ms after shot exit | [Singh, J. SMPTE](https://journal.smpte.org/periodicals/Journal%20of%20the%20SMPTE/71/1A/103/07308845.pdf) |
| 30 mm cannon | Smoke mass peaks **9.5 ms** after shot exit (primary + intermediate flash only; no secondary in that charge) | [Yan et al. 2023](https://pmc.ncbi.nlm.nih.gov/articles/PMC9979356) |

---

## 2. Physics → parameters

### 2.1 Inputs per weapon

From the ship designer: **bore d, barrel length in calibres, guns per mount**, plus the ammunition's **propellant family, K-salt fraction, igniter fraction, wear-reducer fraction and muzzle device**. The charge mass can be given; otherwise:

```
m_prop ≈ 4000 · d³ · (L_cal/50)    kg, d in m   [INFERRED fit, naval high-velocity guns]
```

| Gun | Real charge | Fit |
|---|---|---|
| 20 mm | 0.028–0.03 kg | 0.032 |
| 5″/38 | 7 kg | 6.3 |
| 8″/55 | 41 kg | 37 |
| 16″/50 | 297 kg | 268 |
| Gustav 80 cm | ~1.9 t | 1.6 t |

Charge masses come from the blast doc's table and NavWeaps. Howitzers and mortars carry far less (0.2–0.5× this); give them an explicit charge.

### 2.2 Energies and the master length

```
E_blast = 0.45 · m · Q                       (blast doc; Q ≈ 3.8 MJ/kg single-base, 4.6 double-base)
λ_b     = (E_blast/p₀)^⅓                     → muzzle blast on the water (existing doc)
E_ab    = m · e_ab                           afterburn energy, e_ab ≈ 3.4–5 MJ/kg  [INFERRED from product mixes]
λ_f     = ((E_blast + s·E_ab)/p₀)^⅓          s = 1 if this shot has a secondary flash, else 0
```

Where e_ab comes from: single-base gas is roughly 35 % CO and 1 % H₂ by mass. That is 0.35 × 10.1 + 0.012 × 120 ≈ 5 MJ/kg. A triple-base powder (more N₂ and H₂O) is ~3.4.

### 2.3 Mach disk and the near field

```
p_m    ≈ (γ−1)·0.6·E_gun / V_bore,    V_bore = (π d²/4)·L_cal·d·1.15,   γ−1 ≈ 0.25   [INFERRED]
p_stag ≈ 1.8 p_m   (sonic exit)
x_M    ≈ 1.0 · d · √(p_stag/p₀)
```

The steady-jet constant is 0.67 (Ashkenas–Sherman). The value 1.0 is chosen so that large guns land on NavWeaps' 20–25 calibres.

**Result:** x_M ≈ 19–23 calibres from 40 mm to 2000 mm (table §6). That is about 8.6 m for a 16″ gun. Small arms come out ~2× too far (NavWeaps gives ~7.5 cm for a rifle). This does not matter at game scale **[INFERRED]**.

Geometry used by the reference renderer:

| Element | Shape and position |
|---|---|
| Intermediate disc | Radius 0.22 x_M, thickness 0.1 x_M, centred at x_M |
| Primary core | Centred at 0.35 x_M, along-bore semi-axis 0.35 x_M + r, radius r = 1.5 d + 0.12 x_M |
| Secondary fireball | Centred at x_M + 0.7 λ_f. Semi-axes 0.8 λ_f along the bore, 0.5 λ_f across. Grows from 35 % to 100 % over the first half of t_s |

The shape is elongated along the bore. From top-down, its along-bore extent shrinks by cos(elevation): an AA gun at 60° shows a round blob, and in the oblique projection it is lifted up the screen.

### 2.4 Does this shot have a secondary flash?

The secondary flash happens when the gas behind the Mach disk is hot enough, rich enough in fuel, and not chemically inhibited. Carfagno's and Yousefian's ignition criteria encode exactly this ([DTIC ADA126103](https://apps.dtic.mil/sti/pdfs/ADA126103.pdf)). For a game, a logistic index is enough **[INFERRED, calibrated to the cases below]**:

```
M     = flash0(propellant) + 0.6·log10(d/0.02 m) − log10(L_cal/50)
        − salt/0.006 − 1.5·[flash hider] + 0.3·[muzzle brake]
P_sec = 1/(1 + e^(−2M))
```

How the terms behave:
- **Bigger bore → more flash.** Larger jets cool more slowly and the Mach disk is stronger.
- **Longer barrel → less flash.** The gas leaves cooler and at lower pressure.
- **1 % K salt subtracts ~1.7.**
- **A flash hider subtracts 1.5.** Flash hiders are a small-arms device; their effect on the flash itself is limited, and they mainly shield the gunner's eyes (NavWeaps).
- **A brake adds a little.**

Calibration cases:

| Case | M | P_sec | Real |
|---|---|---|---|
| 16″/50 SPD (Iowa) | +1.7 | 0.97 | Flashes every round (Desert Storm photos) |
| 5.56 rifle, ball powder, 1 % salt, no hider | ~0 | ~0.5 | "Unpredictable secondary flash" (Dye) |
| 155 mm triple-base + 1 % K salt | −1.9 | 0.02 | Modern howitzer charges are effectively flashless |
| 16″ SPCG flashless | −0.9 | 0.13 | Flashless full charges were only fielded up to 8″/55; the 16″ kept flashing (Naval Gazing comments citing OP 1664) |

### 2.5 Duration and envelope

| Phase | Duration | Envelope |
|---|---|---|
| Gun emptying (primary + intermediate) | `t_e ≈ L_barrel/300 m/s + 0.2 ms` **[INFERRED]**: 20 ms for a 152 mm (Steward's non-burning ~20 ms), 68 ms for a 16″/50, 5 ms for a 20 mm | Temperature falls 2000 → 1200 K (primary) and 1900 → 1400 K (intermediate) over t_e |
| Secondary flash | `t_s ≈ 5·λ_f/c₀` | Rise over 0.12 t_s, then `1 − ((t − rise)/(t_s − rise))²`. T_peak per propellant 1650–1900 K, at 75–100 % of peak during the envelope. Per-shot intensity scatter: lognormal σ ≈ 0.25 |

At the joke tier (λ_f ≳ 50 m, t_s ≳ 1 s) **buoyant lift-off** starts to matter. The reference code adds `z += ½·0.6·g·t²` to the fireball centre. It is negligible below ~0.5 s and lifts the 2000 mm fireball ~10 m during its life. For anything larger, hand over to the magazine doc's fireball correlations.

### 2.6 Temperature, emissivity, luminance, colour

```
L = ε · L_bb(T) · envelope        ε = 1 − exp(−b / 6 m)   (secondary; b = lateral semi-axis)
I = L · π a b                     luminous intensity seen from above (cd)
```

| T (K) | Blackbody luminance (cd/m²) | Linear sRGB chroma |
|---|---|---|
| 1000 | 2.7 | (1, .03, 0) |
| 1200 | 141 | (1, .07, 0) |
| 1400 | 2.5·10³ | (1, .12, 0) |
| 1600 | 2.2·10⁴ | (1, .17, 0) |
| 1800 | 1.2·10⁵ | (1, .22, 0) |
| 2000 | 4.7·10⁵ | (1, .27, .01) |
| 2500 | 5.7·10⁶ | (1, .38, .07) |

Computed from Planck × CIE 1931 (multi-lobe fit) in the scratch script behind `bb_luminance()`.

- **Luminance is extremely temperature-sensitive.** Steward's 850–1050 K non-burning plume is only a few cd/m², invisible in daylight. The 1200–1600 K burning gas is 10²–10⁴ cd/m². A few hundred kelvin decides whether the flash shows at noon at all. So **drive brightness through T, not a linear intensity knob.**
- **A pure 1600–1900 K blackbody renders salmon-red.** That is the first prototype's mistake (§8). The observed yellow-white comes from strong **Na D-line (589 nm)** and K emission (Steward) and from hotter cores. The code mixes 55 % of a sodium-yellow chroma (1, 0.62, 0.18) into the secondary flash **[INFERRED weight]**.
- **K-salted charges** suppress the secondary flash. What is left is the red-orange primary and intermediate flash: dimmer, redder, shorter. That is the right look for flashless powder.

### 2.7 Muzzle devices and elevation

- **Brake:** two lateral lobes at ±(100–135°) from the bore, carrying ~30 % of the gas **[INFERRED]**. Top-down, a braked tank gun or howitzer shows a "T" or arrow-head flash and kicks dust sideways. Naval guns of the period have no brakes.
- **Flash hider:** small arms only. Reduces P_sec; leaves the primary flash.
- **Elevation:** along-bore extents scale with cos(el) in the plane. The height of every element goes into the oblique `sy = y + k·z′` (k ≈ 0.6, as in the magazine doc). High-angle AA flashes therefore pop up the screen slightly. That reads well.

---

## 3. Propellants: the flash/smoke trade-off

### 3.1 Family table (parameters in `PROPELLANTS`)

| Family | Examples | Q MJ/kg | e_ab MJ/kg | flash0 | T_sec K | Own solids | Smoke tint |
|---|---|---|---|---|---|---|---|
| Black powder | pre-1890 guns, igniters, saluting charges | 2.8 | 1.0 | −0.6 | 1700 | **0.56 kg/kg** | white |
| Single-base NC | USN SPD, IMR, M1/M6 | 3.8 | 5.0 | +1.0 | 1800 | 0.002 | warm grey-brown near the muzzle **[UNCERTAIN]** |
| Double-base | Cordite MD/SC, RPC/12, M2 | 4.6 | 3.6 | **+1.6** | 1900 | 0.001 | warm grey |
| Cool double-base | Diglycol (RPC/38), Gudol | 3.4 | 4.4 | 0.0 | 1700 | 0.001 | grey |
| Triple-base / picrite | Cordite N/NQ, SPCG, M30/M31 | 3.6 | 3.4 | **−0.9** | 1650 | 0.004 (cryolite) | white |
| Nitramine / LOVA | modern | 4.0 | 4.0 | +0.6 | 1800 | 0.0005 | white |

Notes:
- The family values are **[INFERRED]** from the ordering in the sources below. Do not treat the absolute numbers as data.
- The British solventless cordite SC "gave rise to an enormous flash", which picrite (nitroguanidine) was added to eliminate ([RNCF history](https://wargm.org/WASC/Files/wasc_2251_00.pdf)).
- Black powder solids: one study measured 55.91 % solid products ([Gunpowder](https://mirror2.polsri.ac.id/wiki/wp/g/Gunpowder.htm)); patent literature gives "about 43 percent of gas, 56 percent of solids" ([US4128443A](https://patents.google.com/patent/US4128443A/en)). The smoke is K₂CO₃ or K₂SO₄ particles depending on the sulfur content ([Koshi](https://www.jes.or.jp/mag/stem/Vol.79/documents/Vol.79,No.3,p.59-69.pdf)).

### 3.2 Additives (per-charge parameters)

| Additive | Typical fraction | Flash | Smoke |
|---|---|---|---|
| K₂SO₄ / KNO₃ flash reducer | ~1 % small arms ("about one percent", US 4,315,785); up to 2 % in flashless cordite (MNLF/2P = 2 % K₂SO₄, [JSP 333](https://www.bulletpicker.com/pdf/Services-Textbook-of-Explosives.pdf)) | −1.7 logit per 1 % | **Largest single source of smoke.** Solids ≈ 1:1 with the salt |
| Black-powder igniter | Bag guns ~1 %, cased ~0.3 % **[INFERRED]**. Each 110 lb Iowa bag had a BP igniter pad ([Naval Gazing](https://www.navalgazing.net/Powder-Part-4)) | — | 0.56 × fraction. NF cordite needed a larger BP igniter, hence more smoke (Naval Gazing) |
| Wear reducer (TiO₂/wax/talc) | 0.5–1 % modern | — | Yes ([US H18](https://patents.justia.com/patent/H18)) |
| Cryolite / K₃AlF₆ | Flashless cordite | Reduces | More solids than K₂SO₄: "particularly in daytime, such a heavy formation of smoke can be more revealing… than a big muzzle flash" ([US 4,078,955](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/4078955)) |
| Ammonium (bi)carbonate, oxamide coolant | Modern alternatives | Reduces | None ([US H18](https://patents.justia.com/patent/H18); [US 4,315,785](https://patents.justia.com/patent/4315785)) |

### 3.3 History the game can use

- **USN interwar.** Additives to existing powder fixed the flash but produced "a great deal of smoke, far too much for the searchlight control used at the time". The British flashless NF triple-base cordite was smoky too, because it was hard to ignite and needed a bigger BP igniter. It was limited to 6″ guns because flashless charges were larger ([Naval Gazing, Powder Part 4](https://www.navalgazing.net/Powder-Part-4)).
- **USN WWII.**
  - Smaller guns: K-salt pellets added to existing powder.
  - Larger guns: Canadian Cordite N.
  - Albanite (flashless, mostly smokeless) arrived "right around VJ Day". It was ~10 % heavier for the same power.
  - In 1947, flashless *full* charges existed only up to 8″/55, and SPCG weighed ~5 % more (comments citing OP 1664). **So a WWII 16″ always flashes.**
- **Modern guns** use triple-base powders "low on both flash and smoke" (same source).
- **Day vs night choice.** Patents frame the trade-off directly: muzzle flash reveals a position at night, muzzle smoke reveals it by day ([US 4,315,785](https://patents.justia.com/patent/4315785)). A per-mount "night charge" toggle (lower P_sec, more smoke, ~5 % heavier) is a historically grounded player choice.

---

## 4. Photometry: day, night, how far it is seen

### 4.1 Backgrounds

| Scene | Background luminance |
|---|---|
| Sunlit open sea | ~1000–3000 cd/m² (reference uses 1500) **[INFERRED: 100 klx × albedo ~0.05 / π, plus sky reflection]** |
| Overcast | ~300 |
| Moonlit | ~0.01 |
| Starlit | ~0.001 |

### 4.2 Effective intensity and detection

Flashes are short, so detection uses the **Blondel–Rey effective intensity**:

```
I_e = ∫ I dt / (0.2 s + (t₂ − t₁))
```

This is the FAA, NBS and IALA convention; the 0.2 s constant ranges 0.1–0.3 s by country ([IALA dictionary](https://www.iala.int/wiki/dictionary/index.php/Blondel-Rey_Law); [NIST](https://www.nist.gov/pml/sensor-science/optical-radiation/effective-intensity-flashing-lights)).

Range then comes from **Allard's law**, `E = I_e·e^(−σr)/r²`, with σ = 3.912 / visibility, solved for E = E_t:
- **Night:** a dark-adapted eye detects ~1.5 × 10⁻⁷ lux ([AMS glossary](https://glossary.ametsoc.org/wiki/threshold-illuminance/)).
- **Day:** `log₁₀E_t = 0.57·log₁₀B + 0.05·(log₁₀B)² − 6.66`. This is the ICAO-style RVR relation, quoted from memory; **[UNCERTAIN, verify against ICAO Doc 9328]**. It gives ~4.5 × 10⁻⁵ lux at B = 1500 cd/m².
- **Horizon:** ~31 km for a 10 m flash seen from 30 m.

Model output, 20 km visibility:

| Gun | Peak I | I_e | Seen by day | Seen at night |
|---|---|---|---|---|
| 20 mm | 1.2·10⁴ cd | 470 cd | 2.5 km | 13 km |
| 40 mm | 1.3·10⁵ | 1.0·10⁴ | 7 km | 23 km |
| 5″/38 | 2.4·10⁶ | 4.1·10⁵ | 17 km | 37 km* |
| 16″/50 SPD | 5.7·10⁷ | 1.9·10⁷ | 31 km* | 53 km* |
| 16″ SPCG flashless | 1.9·10⁶ | 1.9·10⁵ | 15 km | 34 km* |
| 2000 mm | 1.3·10⁹ | 6.3·10⁸ | 45 km* | 69 km* |

\* Beyond the geometric horizon. Only the glow lighting clouds and the gun's own smoke is seen there. Historically, gun flashes below the horizon were seen as "lightning" on cloud **[INFERRED]**.

**Takeaways for game design:**
- At night every gun on the map is visible to everyone in range, and the big ones beyond the horizon. Flashless charges cut the night signature ~100× (≈ 1.5× shorter range).
- By day, light AA flashes are invisible past a few km. Big-gun flashes are seen to the horizon. **Smoke, not flash, is the daytime signature.**

---

## 5. Smoke

### 5.1 What the smoke is

| Component | Source | Extinction | Lifetime |
|---|---|---|---|
| **Primary smoke (particles)** | K salts from the flash reducer, BP igniter residue, wear-reducer oxides, a little soot and unburnt material; black powder: 56 % of the charge | ~3 m²/g for sub-micron hygroscopic salts, ×(1 + 2·RH⁴) for water uptake; BP 1.5 m²/g **[INFERRED within the obscurant range: RP ~3.6 m²/g ([DTIC ADA142143](https://apps.dtic.mil/sti/pdfs/ADA142143.pdf))]** | Minutes; only dilution removes it |
| **Secondary smoke (water fog)** | H₂O in the gas (+ H₂ afterburned to H₂O) condensing when the plume mixes with cold or humid air. Same mechanism as rocket "secondary smoke"; afterburning hydrogen increases contrail propensity ([UNR, DTIC ADA151209](https://apps.dtic.mil/sti/pdfs/ADA151209.pdf); STANAG 6016 terms) | ~0.5 m²/g droplets, small condensed fraction (≤ 0.4, rises with RH and cold) | **Seconds** (τ_w ≈ 2 s / (1 − RH)): bright white puff in cold, damp weather |
| **NO₂ tint** | Nitrate propellants | Colour only | Fades in seconds **[UNCERTAIN]**; brownish near-muzzle tint for NC powders |
| **Kicked-up dust or spray** | Blast on ground or water | Separate system (blast doc foam/spray; land dust: [US 6,308,608](https://patents.justia.com/patent/6308608)) | — |

Tank crews know the combination: the cloud from smoke, heat and debris can obscure the gunner's view "for several seconds", depending on climate ([US 4,260,384](https://patents.google.com/patent/US4260384)). WWII trials judged the 17-pounder's obscuration bad enough that strikes could not be sensed under ~1,000–2,000 yards ([The Chieftain's Hatch](https://worldoftanks.com/en/news/history/The_Chieftains_Hatch_Firefly2/)).

### 5.2 The one number: extinction area A

```
y_solid = solids(prop) + 1.0·salt + 0.56·igniter + 0.8·liner          kg/kg
A_p     = m·1000·y_solid·α·(1 + 2 RH⁴)                                 m²   (α in m²/g)
A_w     = m·1000·water·χ(RH, T)·0.5 · e^(−t/τ_w)                       m²
A(t)    = ramp(t)·(A_p + A_w),   ramp = 1 − e^(−t / (0.5·max(t_s, t_e) + 4 ms))
```

**Calibration.** Yan et al. define CQMS = −log₁₀(T)·V/l. That is exactly A in decadic units: Beer–Lambert integrated over the cloud volume.

| | Measured | Model |
|---|---|---|
| 30 mm charge | **2.35 ± 0.06 m²** decadic = **5.4 m²** natural | **5.7 m²**, assuming a 0.11 kg single-base charge with 1 % K salt |

It also matches the shape of the measurement: the smoke mass peaks right after the flash phase (the ramp). For large calibres, Zhao et al. measured transmittance falling to 0.9 % (20 % average) behind a **130 mm** cannon ([Chinese J. Energetic Materials 2013](https://www.energetic-materials.org.cn/hnclen/article/abstract/2011212)). That is qualitatively consistent with the model's τ_v > 1 for 5″+ guns.

### 5.3 Puff dynamics (per shot) **[INFERRED tuning, form standard]**

```
forward carry: s(t)  = 2.5·λ_f·(1 − e^(−t/τ_m)),   τ_m = 0.04·λ_f + 0.05 s     (gas-jet momentum)
centre       : xy    = muzzle + bore_h·(x_M + s)·cos(el) + wind·t
height       : z     = h + (x_M + s)·sin(el) + 0.6·λ_f·(1 − e^(−t/(3 + 0.05 λ_f)))   (buoyant rise)
spread       : σ_h²  = (0.35 λ_f)² + ((0.07 U + 0.2)·t)² + 0.5·t,    σ_z = 0.8 σ_h
```

**The buoyant rise is the most sensitive knob in the model.** It decides whether a puff passes over or through a sight line 10–30 m high. In the prototype, rise = 1.2 λ_f lifted the 16″ SPD cloud clean over a 15 m line. That is why it now uses 0.6 λ_f and a fatter σ_z. Battleship-broadside photos show the cloud spanning from the water to well above the masts. Tune this one against reference footage first.

Numbers per shot (wind 5 m/s, RH 70 %):

| Gun | A (m²) | σ_h at 5 s / 30 s / 120 s | Peak vertical τ at 5 s / 30 s / 120 s |
|---|---|---|---|
| 20 mm | 0.46 | 3 / 17 / 67 m | 0.008 / ~0 / ~0 |
| 40 mm | 5.1 | 3 / 17 / 67 | 0.08 / 0.003 / ~0 |
| 5″/38 | 114 | 4 / 17 / 67 | **1.1** / 0.06 / ~0 |
| 16″/50 SPD | 10,000 | 10 / 20 / 67 | 15 / **4.1** / 0.35 |
| 16″ SPCG flashless | 20,000 | 7 / 18 / 67 | 72 / **10** / 0.7 |
| 2000 mm | 870,000 | 45 / 48 / 80 | 71 / 60 / **21** |

### 5.4 Visibility queries: closed form

A Gaussian puff with total extinction area A has these optical depths:

```
vertical (top-down render alpha):   τ_v(x,y) = A/(2π σ_h²) · exp(−r²/(2σ_h²))
                                    alpha = 1 − e^(−τ_v)

horizontal sight line a→b:          τ = A/(2π σ_h σ_z) · exp(−d⊥²/(2σ_h²) − Δz²/(2σ_z²))
                                        · ½[erf((L − s₀)/(√2 σ_h)) − erf(−s₀/(√2 σ_h))]
```

In the horizontal formula, d⊥ is the horizontal miss distance, Δz the height difference, s₀ the position of the puff's foot along the segment, and L the segment length.

Sum τ over puffs, then take `T = e^(−τ)`. For spotting:
- multiply the target's apparent contrast by T, **or**
- use the Koschmieder-style rule: detected if `C₀·T > 0.02–0.05`.

A lit smoke cloud also adds its own luminance (airlight), which lowers contrast further. In daylight, white gun smoke in front of a dark hull hides it better than T alone suggests **[INFERRED]**.

`mf_los.png` shows own-smoke obscuration on a 15 m line 150 m downwind, wind 5 m/s:

| Case | Minimum T | Duration |
|---|---|---|
| 16″ triple SPD | 0.01 at ~30 s | Clear (> 0.9) after 44 s |
| 16″ triple SPCG flashless | ~0 | Clear after 46 s, longer and deeper |
| 6″ black powder, 1 round | 0 | Opaque ~12 s |
| Twin 5″/38, 15 rpm | Plateau 0.73 | Holds for as long as it fires |

### 5.5 Rapid fire

Merge puffs from the same mount that lie within one σ of each other (`merge_puffs`):
- sum A;
- A-weighted centroid;
- second-moment σ.

A 40 mm quad at 2 rps per barrel then makes one trail, not 480 puffs a minute. Below A ≈ 1 m² per shot (20–40 mm), emit one merged puff per mount every 1–2 s carrying the accumulated A. Smoke does matter there for sustained fire. Single-shot puffs from 20 mm can be dropped.

---

## 6. The calibre ladder (model output, `python muzzle_flash_ref.py`)

| Gun | m kg | λ_b m | λ_f m | x_M m (cal) | P_sec | Flash length m | Fireball m | t_s | t_e | A_smoke m² |
|---|---|---|---|---|---|---|---|---|---|---|
| 20 mm Oerlikon | 0.028 | 0.78 | 1.18 | 0.32 (16) | 0.85 | 2.1 | 1.9 | 17 ms | 4.9 ms | 0.46 |
| 40 mm Bofors | 0.31 | 1.74 | 2.67 | 0.84 (21) | 0.91 | 4.8 | 4.3 | 39 ms | 7.7 ms | 5.1 |
| 5″/38 | 7 | 4.9 | 7.7 | 2.7 (21) | 0.96 | 14 | 12 | 112 ms | 16 ms | 114 |
| 6″/47 | 15 | 6.3 | 9.9 | 3.3 (21) | 0.96 | 18 | 16 | 144 ms | 24 ms | 506 |
| 155 mm howitzer (triple-base + K salt) | 12 | 5.8 | 5.9 | 3.1 (20) | **0.02** | 12 | — | — | 20 ms | 1,260 |
| 8″/55 | 41 | 8.8 | 13.8 | 4.3 (21) | 0.96 | 25 | 22 | 201 ms | 37 ms | 1,380 |
| 15″/42 cordite SC | 196 | 15.9 | 22.2 | 8.7 (23) | 0.99 | 42 | 36 | 323 ms | 54 ms | 5,740 |
| **16″/50 SPD** | 297 | 17.1 | 26.8 | 8.6 (21) | 0.97 | 49 | **43** | **391 ms** | 68 ms | **10,000** |
| 16″/50 SPCG flashless | 312 | 17.1 | 18.5 | 8.6 (21) | **0.13** | 36 | — | — | 68 ms | **20,200** |
| 46 cm/45 | 360 | 18.3 | 28.6 | 9.4 (20) | 0.98 | 52 | 46 | 417 ms | 69 ms | 12,100 |
| 80 cm railway (diglycol) | 1,640 | 29 | 45 | 15 (19) | 0.89 | 82 | 71 | 649 ms | 107 ms | 48,000 |
| 1000 mm turbocannon | 4,000 | 41 | 61 | 21 (21) | 0.96 | 112 | 97 | 884 ms | 167 ms | 108,000 |
| **2000 mm turbocannon** | 32,000 | 83 | 122 | 41 (21) | 0.97 | 224 | **195** | **1.77 s** | 334 ms | **867,000** |

Reading across the table:
- Size grows as m^⅓ (≈ linear in calibre).
- Smoke grows as m (≈ calibre³).
- So **big guns are smoke-dominated, small guns flash-dominated**. This falls out of the physics and matches the brief's "for very small guns smoke may be ignored".

---

## 7. Implementation

### 7.1 Data

```
WeaponFX (per gun type, computed once)        // from derive()
  d, L_cal, n_guns, charge_kg, prop_family, salt, igniter, liner, device
  lam_b, E_blast, E_ab, x_M, t_e, P_sec, T_sec, A_p, water, tint
  // lam_b is already shared with the blast-on-water doc and the audio bench

ShotEvent (ring buffer, ≤ 128)                 // one per gun per round (or per mount for salvos < 20 ms apart)
  pos.xyz (muzzle), az, el, t_fire, seed, sec_on (Bernoulli(P_sec)), jit (lognormal)
  lam_f, t_s                                    // per shot, from sec_on and jit

SmokePuff (pool, ≤ 512, merged)                // spawned by ShotEvent; lives until peak τ_v < 0.01
  A_p, A_w0, τ_w, origin, bore, t0, lam_f       // state is analytic in t: no simulation needed
```

### 7.2 Flash rendering (per active ShotEvent, ≤ 0.4 s for a 16″)

1. **Emitters:** 3 elements, each an ellipse with temperature T(t), ε, envelope:
   - primary core;
   - intermediate disc;
   - secondary fireball.

   Add 2 lateral lobes when the gun has a brake. Plus an optional ember burst (bag guns): 20–80 sparks, ~0.3–1 s.
2. **Look:**
   - Close zoom (fireball ≥ ~24 px): a **flipbook billboard** per element, in the existing flipbook pipeline: 2–3 baked turbulent-fireball sequences, temperature in a channel, remapped through the blackbody + Na ramp (§2.6) at runtime. Stretch it along the bore by a/b and lift it by the oblique height.
   - Far zoom: the analytic Gaussian splat.
   - Cross-fade between the two by on-screen size.
3. **Energy-conserving splat (the core of "visible at every zoom"):**
   - `L_px = I·w(u,v) / (2π σ_u σ_v)` with `σ ≥ 0.6 px`.
   - **The normalisation is analytic**, so the integrated intensity is identical whether the flash covers 10⁴ pixels or a fraction of one.
   - Never normalise by the sum of visible weights (§8).
4. **Temporal:**
   - Evaluate I(t) as an average over the frame interval (4 sub-samples). A 4 ms 20 mm flash is never missed or flickered by the frame rate.
   - For readability, a flash may be shown for ≥ 2 frames with intensity scaled to keep I_e: `I′ = I·t·(0.2 + t′)/(t′·(0.2 + t))`. A 4 ms flash shown over 33 ms keeps 14 % of its peak (`stretch_for_frames`).
5. **HDR and exposure:**
   - Write physical cd/m² into the HDR target.
   - Exposure is keyed to the background luminance (day ~1500, night floor ~0.05).
   - **Flash adaptation:** the key may rise toward the screen mean (fast attack ~50 ms, slow release ~1–2 s). Capped at 4× by day and ~10⁴× at night, so a night salvo dims the rest of the scene for a moment, as the eye does.
6. **Bloom on a compressed source:** `src = x/(1 + x/6)` before blurring, at 3 radii (1.5, 6, 18 px). Without the compression a 10⁸ cd flash paints the whole screen.
7. **Tonemap on luminance, then roll the excess to white.** Do not clip per channel: per-channel clipping turns every flash flat yellow (§8).
8. **Culling:**
   - Drop an emitter when its frame-averaged pixel contrast `I/(mpp²·L_bg) < 0.01` **and** its bloom contribution is below 1 LSB.
   - By day this removes light-AA flashes beyond ~1–3 km of screen scale. At night it removes almost nothing, which is correct.
   - Cap the active count with a priority on I_e.

### 7.3 Light from the flash

| Light | Rule | Effect |
|---|---|---|
| **Point lights** | 1–8 (clustered by mount), at the fireball centroid, intensity I(t) | Light hulls, smoke and water |
| **Water** | The existing sun-glint lobe with the flash as a second light | At night the sea under a broadside flares orange in a broken glint path. The magazine doc's flipped-emissive reflection works here too |
| **Smoke at night** | Lit by the flash only during t_s: `E = I/r²` on each puff, scattered with albedo ~0.9 | It then goes dark. A night salvo reads as flash → orange-lit cloud → black cloud against the moonlit sea |
| **Exposure pulse** | Scaled by I_e and distance | Shared with the magazine doc's "exposure flash" |

### 7.4 Smoke rendering

| Element | Spec |
|---|---|
| Draw | One soft billboard per puff in the oblique projection at its z |
| Opacity | Alpha from `1 − e^(−τ_v)`, the same function gameplay uses, so what the player sees and what blocks sight agree by construction |
| Shading | The existing 6-way-lit smoke flipbook. Albedo 0.9 (white) for salt, BP and triple-base; a warm tint near the muzzle for NC powders, fading over ~5 s |
| Water fog (A_w) | Pure white, evaporating with τ_w |
| Shadow | The magazine doc's analytic ellipse shadow, projected along the sun. In daylight this is the strongest height cue for big-gun smoke |
| Resolution | Half resolution with bilateral upsample. Cap the on-screen size of one puff and merge old puffs (magazine doc §5) |

### 7.5 Gameplay API

```
smoke_tau(a: vec3, b: vec3) -> float      // sum of closed-form puff integrals (§5.4); ~30 flops per puff
smoke_tau_vertical(x, y) -> float         // for air spotting and for the renderer
flash_events(observer, t) -> [(shot, I_e, range)]   // Allard + threshold(B) → "gun flashes seen at bearing …"
```

Acceleration: bin puffs into a coarse 2D grid (256 m cells), test segment–AABB with the 3σ footprint first. A heavy action (100 live puffs × 50 spotting pairs) costs ~0.1 ms of CPU.

### 7.6 Composite order (extends the blast doc §3.5)

water (roughness, blast frost, flash glint) → foam → hull_base → turrets → hull_upper → spray → **smoke (lit, shadowed, half-res)** → **flash emitters (additive HDR)** → bloom → tonemap.

Flashes go after smoke on purpose: the fireball is in front of the smoke it is making. Puffs from *earlier* shots that lie between the camera and the fireball can attenuate it by `e^(−τ_v)` along the column. This is cheap, and right for a broadside fired through its own smoke.

---

## 8. Prototype findings

1. **Normalisation bug: the important one for the engine.**
   - The first renderer normalised each Gaussian by the sum of its weights *inside the tile*.
   - A fireball just off-screen then dumped its full intensity into the tail pixels at the screen edge, giving a white wall on the border.
   - Fix: normalise analytically (∫ = 2πσ_uσ_v). The same bug will appear in any GPU splat that normalises per tile or per screen.
2. **Pure-blackbody colour is wrong for flashes.** 1600–1900 K is salmon-red on screen. Adding the sodium-line chroma (§2.6) gives the yellow-orange of reference photos and keeps salted charges redder.
3. **Per-channel clipping turned every night flash into flat yellow.** A luminance tonemap with roll-to-white fixes it.
4. **Unbounded bloom painted entire night tiles.** Compress the bloom source.
5. **The zoom ladder works with no LOD code** (`mf_zoom.png`), from 15 m to 10 km per tile:
   - At 40 m/px a 16″ flash is a single bloomed point, still clearly visible by day.
   - The neighbouring 40 mm battery is a faint dot by day and a clear point at night.
   - The only explicit LOD is flipbook ↔ splat by on-screen size.
6. **Smoke must ramp in.** Drawing the full A at t = 0 put a grey halo around the young flash. Real smoke peaks after the flash (Yan's 9.5 ms).
7. **Daytime flash is modest, and that is right.** Against 1500 cd/m² sea, the 16″ fireball is a warm, bright, short blob. The white smoke is the bigger daytime event. Resist making it brighter: the night contrast comes free.
8. **The buoyant-rise sensitivity** (§5.3). A ×2 change in rise flips the 16″ SPD sight-line result from "barely obscured" to "opaque for 15 s".

---

## 9. Open questions

- **Rise and σ_z of gun smoke over water.** There is no quantitative source. The best path is frame-measuring Iowa or Missouri broadside footage at known wind: cloud height vs time, width vs time.
- **SPD smoke colour (NO₂ brown?).** Accounts and colour photos disagree **[UNCERTAIN]**. Keep the tint as an art knob.
- **Flash temperatures by propellant.** T_sec per family is inferred from Steward's 1200–1600 K (one gun, IR band-averaged) and the known flash ordering. The visible core is probably hotter than the IR average. Calibrate exposure-matched against Desert Storm night footage of Wisconsin and Missouri.
- **Day threshold formula.** Verify the ICAO relation (Doc 9328). It only moves the day detection ranges.
- **Muzzle-brake lobe split and angle** for tank guns and howitzers, if land units are ever added.
- **Igniter fractions per bag charge.** The 1 % figure is a guess; it matters for the 16″ smoke total (~75 % of SPD's A comes from the igniter in this model).
- **Joke tier.** Above ~1000 mm the flash becomes a buoyant fireball (Froude scaling), and the water-fog component dominates cold-weather smoke. Both are handled qualitatively. Fine for a joke weapon; just do not cite the numbers.

---

## Sources

**Muzzle flash physics**
- DiGiulian, *Muzzle Flash* (NavWeaps tech-090) — https://www.navweaps.com/index_tech/tech-090.php
- Wikipedia, *Muzzle flash* — https://en.wikipedia.org/wiki/Muzzle_flash
- Heimerl, *Muzzle flash and alkali salt inhibition* (DTIC ADA126129) — https://apps.dtic.mil/sti/pdfs/ADA126129.pdf
- Klingenberg, *Gun muzzle flash research* (DTIC ADA183911) — https://apps.dtic.mil/sti/pdfs/ADA183911.pdf
- Heimerl & Klingenberg, *Combustion following turbulent mixing in muzzle flows* (Fraunhofer EMI) — https://publica.fraunhofer.de/entities/publication/42afc048-b6c2-4de7-b0f7-04ec39340251
- Heimerl, *The muzzle flash of guns and rockets* (DTIC ADA164593) — https://apps.dtic.mil/sti/pdfs/ADA164593.pdf
- *Muzzle flash onset: an algebraic criterion* (DTIC ADA126103) — https://apps.dtic.mil/sti/pdfs/ADA126103.pdf
- Carfagno & Rudyj, *Relationship between propellant composition and flash and smoke* (DTIC AD0750187) — https://apps.dtic.mil/sti/pdfs/AD0750187.pdf
- Habersat, *Mk 66 rocket signature reduction* (K₂SO₄ suppression) — https://apps.dtic.mil/sti/tr/pdf/ADA114222.pdf
- UNR / AFOSR, *Inhibition of afterburning by potassium salts* (DTIC ADA151209) — https://apps.dtic.mil/sti/pdfs/ADA151209.pdf

**Measurements**
- Steward, Gross & Perram 2012, *Characterization and discrimination of large caliber gun blast and flash signatures* (SPIE 8360) — https://modis.gsfc.nasa.gov/sci_team/pubs/abstract_new.php?id=07813
- Luo et al. 2023, *Measurement for optical properties of gun flame and smoke* — https://m.researching.cn/articles/OJbdbf3ec43082e758
- Dye, *Small arms muzzle flash measurement* (NDIA 2016) — https://ndia.dtic.mil/wp-content/uploads/2016/armament/18357_Dye.pdf
- Telops, *Tank muzzle flash analysis* — https://info.telops.com/Website-content-requests_07---LP---FAST-Thermal-Imaging---Tank-Muzzle-Flash-Analysis.html
- Telops, *Characterization of small-arms muzzle flash* — https://www.telops.com/wp-content/uploads/2022/08/characterization-of-small-arms-muzzle-flash-using-high-speed-thermal-infrared-imaging.pdf
- Singh, *Chemical reactions in gases emerging from the muzzle of a gun* (J. SMPTE) — https://journal.smpte.org/periodicals/Journal%20of%20the%20SMPTE/71/1A/103/07308845.pdf

**Smoke**
- Yan et al. 2023, *Quantitative assessment method of muzzle smoke in a field environment* (ACS Omega) — https://pmc.ncbi.nlm.nih.gov/articles/PMC9979356
- Zhao et al. 2013, *A measurement method for gun muzzle smoke aggregates* (130 mm) — https://www.energetic-materials.org.cn/hnclen/article/abstract/2011212
- US 4,315,785, *Propellant charge with reduced muzzle smoke and flash* — https://patents.justia.com/patent/4315785
- US 4,078,955, *Flash-reducing agent for powder* — https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/4078955
- US H18, *Reduction of erosion and muzzle flash of gun tubes* — https://patents.justia.com/patent/H18
- US 4,260,384, *Obscuration device for tank gunners* — https://patents.google.com/patent/US4260384
- US 6,308,608, *Dust suppression* — https://patents.justia.com/patent/6308608
- Koshi, *Smoke generation in black powder combustion* — https://www.jes.or.jp/mag/stem/Vol.79/documents/Vol.79,No.3,p.59-69.pdf
- US 4,128,443 (black powder 43 % gas / 56 % solids) — https://patents.google.com/patent/US4128443A/en
- *Visual and IR mass extinction of obscurants* (DTIC ADA142143) — https://apps.dtic.mil/sti/pdfs/ADA142143.pdf
- *A catalog of optical extinction data for military smokes* (DTIC ADA034500) — https://apps.dtic.mil/sti/pdfs/ADA034500.pdf
- The Chieftain's Hatch, *US Firefly pt 2* (17-pdr obscuration trials) — https://worldoftanks.com/en/news/history/The_Chieftains_Hatch_Firefly2/

**Propellants and naval history**
- Naval Gazing, *Powder Part 4* (and comments citing OP 1664) — https://www.navalgazing.net/Powder-Part-4
- *A brief history of cordite* (RNCF) — https://wargm.org/WASC/Files/wasc_2251_00.pdf
- Ministry of Defence, *Services Textbook of Explosives* (JSP 333) — https://www.bulletpicker.com/pdf/Services-Textbook-of-Explosives.pdf
- US Army TM 9-1300-214, ch. 9 *United States propellants* — https://19january2021snapshot.epa.gov/sites/static/files/2015-05/documents/9530609-4.pdf
- Gunpowder composition — https://mirror2.polsri.ac.id/wiki/wp/g/Gunpowder.htm

**Photometry**
- IALA, *Blondel–Rey law* — https://www.iala.int/wiki/dictionary/index.php/Blondel-Rey_Law
- NIST, *Effective intensity of flashing lights* — https://www.nist.gov/pml/sensor-science/optical-radiation/effective-intensity-flashing-lights
- AMS Glossary, *Threshold illuminance* — https://glossary.ametsoc.org/wiki/threshold-illuminance/
- AMS Glossary, *Allard's law* — https://glossary.ametsoc.org/wiki/Allard%27s_law

**Blast scaling (shared)**
- Fansler, *Description of muzzle blast by modified ideal scaling models* (DTIC ADA330051) — https://apps.dtic.mil/sti/pdfs/ADA330051.pdf

**Project:** `claude/muzzle-blast-water-vfx.md`, `claude/magazine-explosion-vfx-research.md`, `claude/sound-design-gunfire.md`, `claude/damage-research/08_gunfire_effects.md`, `claude/sprite-pipeline.md`.