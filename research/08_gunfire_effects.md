# 08 — Gunfire Effects: What a Shell Does When It Hits

*Research for the damage model, in the same vein as `07_magazine_explosions.md`. It covers what happens at the target, from the moment a shell arrives to the damage it leaves. Penetration formulas, decapping and the fuze-arming formula are already in `05_mechanics_and_games.md` §A1–A4 and are used here, not repeated. Bombs come in a later doc.*

*The scope runs from a destroyer's 5-inch hitting a battleship's superstructure, through cruiser and battleship fire on armoured ships, up to a full broadside of 18-inch HE landing on a destroyer. Armoured targets get the most space.*

*Scope: **everything here assumes the shell has already hit** (or, for §3.8 and near misses, already landed at a known distance from the hull). Whether it hits, through dispersion, fire control and hit rates, belongs to the separate ballistics and fire-control research. The fire-control model hands this one an impact point, striking velocity, fall angle and target angle.*

Tags follow the other damage docs: **[INFERRED]** marks my own reasoning, fits or tuning values, and **[UNCERTAIN]** marks conflicting or thin sources.

**Companion code:** `claude/gunfire_ref.py` (pure Python, ~750 lines, runs in about 20 s). Every number in §6 comes out of it. It contains the shell table, penetration and fuze-arming checks, outcome classes, burst radii, fragment reach, side-view target zones for a Fletcher and a South Dakota, and Monte Carlo runs of N given hits. It also has a small point-mass ballistics function that supplies striking velocity and fall angle by range; it does not model whether shells hit.

---

## 0. TL;DR for the model

1. **What a hit does depends on where the shell bursts, not how big it is.** The same 16-inch AP shell can:
   - pass clean through a destroyer and leave two 40 cm holes,
   - burst in a battleship's machinery and flood 600 t,
   - shatter harmlessly on a turret face.

   Resolve every hit in four steps: **(a) where it lands → (b) what plates it meets → (c) whether and where the fuze fires → (d) what is within reach of the burst.**
2. **Big AP against thin ships mostly passes straight through.** A base fuze needs about **0.07 calibre of plate** to start: 28 mm for a 16-inch shell, 32 mm for a 46 cm shell. Destroyer plating is 6–12 mm and superstructure about 10 mm.
   - WDR 51: AP "normally pass[es] all the way through a lightly built ship unless a heavy unit of machinery… is encountered".
   - At Samar "numerous projectiles passed all the way through both the destroyers and the escort carriers… without detonating".
   - The model gives **~94 % pass-through for 16-inch and 46 cm AP hits on a Fletcher**. The bursts that do happen come from striking turbines, gears or boilers, which is what happened to Johnston.
3. **Big HE against thin ships is the opposite: it bursts on the first plate, every time.** One 46 cm Type 0 shell (61.7 kg of filler) bursting inside a Fletcher wrecks everything within about 6 m and opens a hole of about 1.5 m radius in the plating it struck.
   - Its blast reaches far enough to breach the next watertight bulkhead.
   - Per hit, the model gives **~30 % "crippled" and ~5 % "lost" for one hit, ~52/13 % for two and ~83/33 % for five**.
4. **Per hit, a heavy HE shell is a destroyer-killer and a heavy AP shell is not.** If one broadside puts k hits on a Fletcher at 15 km, the results are:

   | k hits | 46 cm Type 0 HE (crippled / lost) | 46 cm Type 91 AP (crippled / lost) |
   |---|---|---|
   | 1 | 32 / 7 % | 11 / 1 % |
   | 2 | 53 / 14 % | 21 / 2 % |
   | 4 | 77 / 26 % | 37 / 3 % |

   The RN 18″ CPC behaves like AP here: it has a base fuze, so it passes through too. The Japanese at Samar switched from AP to HE for exactly this reason.
5. **Medium-calibre fire on a battleship gives a mission kill, never a sinking.**
   - **The effect:** it destroys radar, searchlights, AA crews, communications and cables, and sometimes the command group, and it starts many small fires.
   - **The evidence:** South Dakota (26 hits), Hiei (~85 hits), San Francisco (45 hits), Graf Spee (~20 hits) and Mikasa (40 hits) all **stayed afloat**.
   - **The rule:** none of these hits touches speed, the main turrets or buoyancy unless a shell gets into the steering or the unarmoured waterline. Hiei's two 8-inch hits in the steering room were the exception that crippled her.
6. **5-inch hits on a battleship.** Thirty hits start about 8 small fires and kill about 30 people. They damage the bridge area (~50 %), AA positions (~50 %) and search radar (~25 %). Even 75 hits barely touch the armoured directors (~4 %), turrets, machinery or buoyancy.
7. **Against armour the outcome classes are what matter, and most heavy hits do not penetrate anything vital.**
   - Bismarck took ~300–400 hits; ~3 holes were found in the main belt and none underwater in the citadel.
   - South Dakota's belt was hit 6 times and penetrated 0 times.
   - At Jutland, British APC got through thick plate and burst properly **1 time in 17**.
   - The damage comes from hits on superstructure, ends, turrets and barbettes, from plunging fire, and from the occasional shell that dives under the belt.
8. **Turret and barbette hits disable turrets even without penetrating.** A non-penetrating heavy hit jams the turret in about **35 %** of cases [INFERRED].
   - Examples: Von der Tann A, Tiger Q, Scharnhorst Anton, Jean Bart, South Dakota III.
   - A hit that does penetrate starts a propellant fire, which is where `07_magazine_explosions.md` takes over.
9. **Shell quality is a per-nation, per-year knob that matters as much as calibre.**
   - British 1916 APC holed plate but broke up.
   - German C/11 fuzes worked about half the time.
   - IJN Type 91 fuzes had a long delay that made them **over-penetrate almost everything except armour**.
   - US 5-inch AA Common gave only ~50 % high-order bursts against ships.
10. **Fires come from HE, fragments come from AP.** Per burst, a WWII HE hit starts a fire ~45 % of the time; South Dakota and San Francisco both had about 0.5 fires per hit. An AP hit starts one ~15 % of the time. Pre-1905 ships with wood, coal on deck and paint burn at ~0.6–0.8 per hit (Yalu, Santiago, Tsushima).

---

## 1. The spectrum: shooter × target

This answers the brief's "from a destroyer shooting a battleship's superstructure to a battleship's 18-inch HE broadside into a destroyer". Numbers are historical where a case exists and from `gunfire_ref.py` otherwise.

| Shooter → target | What usually happens per hit | What decides it | Historical anchor | Model anchor (§6) |
|---|---|---|---|---|
| **DD 4.7–5″ → BB superstructure** | HE bursts on 10 mm plating. Wrecks ~2 m radius and starts a fire ~25–45 % of the time. Kills exposed crew. Cuts cables and radar leads. | Whether the hit lands on bridge, radar or AA, or on empty structure | Hiei (bridge raked, Abe wounded, chief of staff killed); Kirishima's searchlights and mantlets; Acasta's 4.7″ "shrapnel damage only" 30 hits → bridge damaged 48 %, search radar 24 %, main director 1 %. 75 hits → 82 / 52 / 4 % |
| **DD 5″ → BB belt or turret** | Nothing, beyond paint and a dent | Armour > 0.25 calibre | Yalu: ~200 QF hits per Chinese ironclad, belt never pierced | 55 % of 5″ hits on a SoDak "defeated / on armour" |
| **DD 5″ → DD** | Every hit bursts inside. ~40 % fire, ~19 t water, ~2 casualties. 1 hit in 8 reaches machinery. | Machinery hits and fires. Hit count matters only in bulk | Sterett 11 hits, survived. Monssen ~39 hits, Hoel >40, both lost. Cushing and Monssen lost to magazines after fire | 10 hits: 77 % crippled / 17 % lost. 40 hits: 100 / 74 % |
| **CL/CA 6–8″ → DD** | HE/HC behaves like 5″ but bigger. **AP mostly passes through (74–93 %)** | Shell type: AP is wasted on DDs, especially IJN Type 91 | Ralph Talbot 5×8″, Onslow 3×8″, Bailey 2–3×8″: all survived. Hoel's first 8″ salvo went through the bridge without bursting | 5×8″ AP: 43 % crippled / 5 % lost |
| **CL/CA 6–8″ → CA/CL** | Topside wrecked; waterline hits flood; one shell in a boiler or below the belt can stop the ship | Waterline and below-belt hits; boilers | Exeter at Java Sea (1×8″ → 5 kn); Boise (8″ below the belt into the magazine, 1,200 t); Graf Spee (8″ wrecked the fuel plant) | — |
| **CA 8″ → BB** | Superstructure shredded, mostly pass-throughs (IJN). Belt untouched. Steering in the ends is vulnerable | Over-penetration; unarmoured steering | South Dakota (18×8″ of 26: blind, 38–40 killed); Hiei (~30×8″, steering flooded) | Per hit: 23 % burst, 30 % no burst, 47 % defeated |
| **BB 11–18″ AP → DD/DE/CVE** | Two shell-sized holes. Kills people and cuts cables on its line of flight. **Bursts only on heavy machinery** | Whether the path crosses the machinery | Johnston (3 heavy shells burst on gear, turbine and boiler → 17 kn); Gambier Bay and Kalinin Bay (AP through, Kalinin Bay survived 15 hits); the Japanese switched to HE | 94 % pass-through. 3 hits: 32 % crippled / 3 % lost |
| **BB 14–18″ HE → DD/DE** | Bursts on contact. One hit wrecks a whole compartment and often the next, gives ~90 t of average flooding (hundreds of tonnes on a waterline hit) and a 66 % fire chance | Waterline machinery hit = sinking | Samuel B. Roberts: one 14″ salvo opened a **40 × 10 ft** hole in No. 2 engine room; abandoned within ~10–20 min. Laffey: 14″ Type 3 did "no significant damage" | 1 hit: 30 % crippled / 5 % lost; 2 hits: 52 / 13 %; 5 hits: 83 / 33 % |
| **BB 14–18″ HE → BB** | Bursts on the armour face: superstructure wrecked, belt untouched | Superstructure share of hits | San Francisco (CA) took 14″ bombardment HE: the 5″ barbette "defeated them easily". South Dakota's 14″ HE hits did the same | 92 % burst, all outside the citadel; 56 % fire |
| **BB AP → BB** | Range-dependent. Belt penetrations inside the immune-zone near edge; deck penetrations beyond its far edge; superstructure and end hits everywhere | Range, fall angle, target angle, shell quality | Bismarck (~400 hits, 3 belt holes); Kirishima (20×16″ at ~7.7 km: steering, hydraulics, flooding → capsize); Dunkerque (4×15″, 2 through the belt or deck → out of action); Jutland (1 in 17) | Per hit: 5–11 % citadel bursts at 8–22 km, ~0 % inside the immune zone, 20 % beyond it. Turret out 2–8 % |

---

## 2. The shells

### 2.1 What is in them

Data from navweaps. Burster = filler mass. "TNT-eq" uses the filler factors in `gunfire_ref.py`; black powder counts as about 1/3 of TNT (Okun).

| Gun / shell | Shell kg | Filler kg (type) | % | Fuze | Notes |
|---|---|---|---|---|---|
| IJN 12.7 cm/50 Type 0 HE | 23.0 | 1.88 (TNA) | 8.2 | nose | DD main battery |
| USN 5″/38 AAC Mk 35 | 25.0 | 3.3 (Exp. D / Comp A) | 13.2 | PD / MT / VT | Used against ships too: ~50 % high-order bursts on surface targets (Lundgren) |
| USN 5″/38 Common Mk 32 | 24.5 | 1.2 (Exp. D) | 4.9 | base | Surface shell |
| USN 6″/47 AP Mk 35 | 59.0 | 0.9 (Exp. D) | 1.5 | base | |
| USN 6″/47 HC Mk 34 | 47.6 | 6.0 (Exp. D) | 12.6 | nose + base | |
| USN 8″/55 AP Mk 21 (SH) | 152 | 2.3 (Exp. D) | 1.5 | base | |
| USN 8″/55 HC Mk 25 | 118 | 9.7 (Exp. D) | 8.2 | nose | |
| IJN 20 cm Type 91 AP | 125.9 | 3.11 (TNA) | 2.5 | base, long delay | Japanese 8″ common: 8.2 kg |
| KM 28 cm APC / HE (nose) | 330 / 315 | 7.0 / 23.0 (TNT) | 2.1 / 7.3 | base / nose | |
| RN 15″ APC Mk Ia (1916) | 871 | 27.4 (lyddite) | 3.1 | base 0.025 s | Broke up on oblique plate |
| RN 15″ APC Mk XXII (WWII) | 879 | 22.0 (Shellite) | 2.5 | base 0.025 s | |
| RN 15″ HE Mk VII | 879 | 59 (TNT/RDX) | 6.7 | nose | |
| KM 38 cm APC / HE (nose) | 800 / 800 | 21.4 / 66.2 (TNT) | 2.7 / 8.3 | base / nose | Also a base-fuzed HE with 36.2 kg |
| USN 14″/45 AP / HC | 680 / 578 | 10.4 / 47.3 (Exp. D) | 1.5 / 8.2 | base / nose | |
| IJN 36 cm Type 91 AP / Type 0 HE | 673.5 / 625 | 11.1 / 29.5 (TNA) | 1.6 / 4.7 | base / nose | |
| USN 16″/50 AP Mk 8 | 1,225 | 18.55 (Exp. D) | 1.5 | Mk 21 BDF, **0.033 s** | |
| USN 16″/50 HC Mk 13 | 862 | 69.7 (Exp. D) | 8.1 | Mk 29 PD | |
| **IJN 46 cm Type 91 / Type 1 APC** | 1,460 | **23.9 (TNA)** | 1.6 | base, long delay | MV 780 m/s |
| **IJN 46 cm Type 0 "Common" HE** | 1,360 | **61.7 (TNA)** | 4.5 | nose (instantaneous) or time | MV 805 m/s |
| IJN 46 cm Type 3 *sankaidan* | 1,360 | 900 incendiary tubes | — | time (~1,000 m) | AA shrapnel. Not a ship-killer |
| **RN 18″/40 APC** | 1,506 | **54.0** | 3.6 | base | Only shell fired in anger (monitors, 1918) |
| **RN 18″/40 CPC** | 1,506 | **110.2** (black powder) | 7.3 | base | Furious outfit (30 rpg) |
| RN 18″/40 HE | 1,506 | n/a | — | — | "No more than two" were delivered |

Sources: navweaps pages for each gun (listed at the end).

**What "18-inch HE" means for the game.** Only two real "18-inch" shells exist, and neither is a dedicated HE design:
- **Yamato's Type 0** (46 cm): ~62 kg of filler in a thick-walled shell.
- **The RN 18″ CPC:** 110 kg, but black powder, so roughly 38 kg TNT-equivalent [INFERRED from Okun's ⅓ factor].

A US-style thin-walled HC shell scaled to 46 cm would hold roughly 8 % of its weight in filler, about 100–110 kg [INFERRED]. For game balance, 18-inch HE should land between the Type 0 and a hypothetical HC shell, **~60–110 kg**.

### 2.2 AP versus HE in one table

| | AP / APC | SAP / CPC / Common | HE / HC |
|---|---|---|---|
| Filler | 1.5–3.5 % | 4–8 % | 6–13 % |
| Fuze | Base, delayed (0.025–0.035 s; IJN T91 longer) | Base, short delay | Nose, instantaneous (some with a base back-up) |
| Defeats plate | Its full penetration curve | ~0.5–0.6 of AP [INFERRED] | **~0.16–0.25 calibre**, then bursts at the plate (05 §A3; USNI 1909: "will scarcely perforate… one-quarter of its caliber") |
| Against thin structure | **Passes through** unless something ≥ 0.07 cal is in the way | Arms on ~0.04–0.07 cal | Bursts on first contact (≥ a few mm) |
| Fragments | Heavy body: fewer, larger pieces, plus a nose slug that carries on (up to 33 % of the body) | Medium | Many light fragments; side spray |
| Fire | Low (~15 % per burst) | Medium | High (~45 % per burst) |
| Best target | Belt, barbette, deck, turret | Cruisers, casemates, light armour | Topsides, destroyers, AA crews, radar |

---

## 3. Terminal ballistics: the per-hit pipeline

### 3.1 Where the shell lands: side or top

A falling shell sees the target as a footprint:

```
depth (range axis) = B·|sin(aspect)| + L·|cos(aspect)| + h_eff / tan(fall)
width (deflection) = L·|sin(aspect)| + B·|cos(aspect)|
```

The `h_eff / tan(fall)` term is the **danger space**: shells that would have landed beyond the hull strike the side or the superstructure on the way down.
- Whether a hit is on the **side** or on the **top** follows directly from that term: `P(side) = (h_eff / tan(fall)) / depth`.
- For a battleship with h_eff ≈ 13 m:

| Range | Fall angle | P(side) |
|---|---|---|
| 5 km | 3° | 89 % |
| 15 km | 11° | 66 % |
| 25 km | 24° | 47 % |

This one formula produces belt hits at short range and deck hits at long range. Within the chosen face, pick the zone by projected area (`Zone.side` or `Zone.top` in the code). **[INFERRED]**

### 3.2 What the shell meets

Each zone has an ordered list of plates (`path`): outer hull, then belt, then whatever is behind. Thicknesses combine with Okun's spaced-plate rule, `(Σ t^1.4)^(1/1.4)`. Obliquity on a side hit is:

```
cos(ob) = cos(fall + belt_incline) · cos(target_angle)
```

On a deck hit it is `90° − fall`.

Penetration capability comes from the Garzke & Dulin fit in 05 §A3. The obliquity terms below are my fit to the navweaps 16″/50 Mk 8 tables:

```
vertical plate:   T = T₀(v) · 0.967 · cos(ob)^1.59      (within 3 % to 30 kyd)
horizontal plate: T = T₀(v) · 0.82  · cos(ob)^1.125     (within 5 % to 40 kyd)
```

Below about 11-inch calibre this extrapolates; treat it as ±15 %. **[INFERRED fit]**

### 3.3 Outcome classes

This list is merged from Okun, Naval Gazing's Jutland analysis, and the Bismarck and Jean Bart surveys.

| Code | Outcome | Effect | Example |
|---|---|---|---|
| RIC | Ricochet / glance (obliquity above ~45–60° and plate not defeated) | Leaves, or bursts outboard (~25–35 %), or hits other structure | 3 of 17 Jutland hits on thick plate; "many shells ricocheted off the 50 mm main deck" (Bismarck) |
| SHT | Shatter, no penetration | Gouge plus fragments outside. Spall behind thin roofs | South Dakota III barbette, gouged 1.5″. Boise's barbette: 8″ AP "fizzing" |
| BRK | Holed, but the shell broke up | Plug and pieces go inboard; little burst | Jutland: 5 of 13 holed with "little internal damage" |
| PIB | Burst while penetrating | Effect mostly caught by splinter layers | Jutland 6–9″ plate: 6 of 17 |
| PEN | Penetration plus burst after the fuze delay | **The design case**: full burst inside | Hood 1919 trial: burst 34–40 ft behind the plate |
| LO | Penetration, low-order burst | ~⅓ radius, but a forward cone of heavy chunks | Post-war Shellite before tetryl boosters |
| DUD | Penetration, no burst | Holes along the path only | PoW's under-belt 38 cm hit; Warspite's 12″ at Jutland |
| OVR | Over-penetration (fuze never armed) | Two holes; cables and people on the line of flight | Bismarck's bow (14″ straight through, 1,000–2,000 t taken in); South Dakota's 8″ hits; Samar |
| UW | Short "diving" hit below the belt | Hits the torpedo-defence system or machinery | PoW → Bismarck (generator room flooded); Boise (magazine); Kirishima hits 6–7 |

**Rates on armour the shell can defeat** (`OUTCOME` in the code). These are fitted loosely to the cases. **[INFERRED]**

| Era / shell | PEN | PIB | LO | DUD | BRK |
|---|---|---|---|---|---|
| RN 1914–16 lyddite APC | 10 % | 35 % | 10 % | 5 % | 40 % |
| German 1916 APC (C/11 fuze) | 40 % | 15 % | 10 % | 15 % | 20 % |
| RN Greenboy 1918–30 | 55 % | 10 % | 20 % | 10 % | 5 % |
| WWII capped AP, good lot | 75 % | 5 % | 7 % | 8 % | 5 % |
| IJN Type 91 | 70 % | 5 % | 7 % | 13 % | 5 % |

**Modifiers**
- A marginal penetration (P/T 1.0–1.15) moves about 15 points from PEN into BRK and PIB.
- A decapping plate of ~0.08–0.12 calibre ahead of face-hardened plate sends the shell to the shatter row. Okun on the Kirishima hit on South Dakota: decapping "prevented all but rather minimal damage".
- The German 1916 fuze as a separate roll: about 45 % correct delay, 20 % instantaneous, 20 % long delay, 15 % dud (Okun) **[INFERRED split]**.

### 3.4 Fuze arming: why big AP passes through small ships

Okun gives the minimum plate for a USN Mk 21 base fuze (single plate) in 05 §A1. Model output, mm:

| Shell | 0° | 30° | 45° | 60° | Arms on DD side (9–12 mm)? | Arms on 10 mm superstructure? |
|---|---|---|---|---|---|---|
| 6″/47 AP | 11 | 8 | 6 | 5 | yes | no |
| 8″/55 AP | 14 | 11 | 8 | 6 | no | no |
| IJN 20 cm T91 | 14 | 11 | 8 | 6 | no | no |
| 14″/45 AP | 25 | 19 | 14 | 11 | no | no |
| 16″/50 AP Mk 8 | 28 | 22 | 16 | 13 | no | no |
| 46 cm T91 | 32 | 24 | 18 | 14 | no | no |

**What arms a big AP shell in a thin ship:**
- "Heavy units of machinery": turbine casings, reduction gears, boilers and their drums.
- Gun mounts and barbettes.
- On a battleship, the internal slope, the far-side torpedo-defence bulkheads and the barbettes.

The code puts this in `Zone.heavy`, which is the chance that the path crosses such a mass: 0.55 in a Fletcher's machinery zone and 0.05 at the ends.

Johnston is the reference case. The three heavy shells "detonated after impact with the after reduction gear, the after H.P. turbine and No. 4 boiler" (WDR 51). The result was a cut steam line, the gyro and the after guns' power lost, slow flooding, and a drop to 17 kn.

### 3.5 Where the shell bursts

`burst distance ≈ delay × residual velocity`, capped by the first plate that stops the shell. **[INFERRED]** Measured: Hood 1919 trial, 15″ Greenboy at 1,430 ft/s through 7″ at 40°, burst **34–40 ft (10–12 m)** behind the plate (Okun).

| Residual velocity | 0.025 s (RN) | 0.035 s (USN/KM) | IJN Type 91 (long delay) |
|---|---|---|---|
| 150 m/s (marginal) | 4 m | 5 m | Stops before bursting |
| 300 m/s | 8 m | 11 m | Through the ship |
| 450 m/s | 11 m | 16 m | Through the ship |
| 600 m/s (thin plate, close range) | 15 m | 21 m | Through the ship |

**Consequences**
- **Beam check.** A cruiser is 18–20 m wide, so an AP shell that defeats a cruiser belt easily often bursts **in the far side or outboard**.
- **IJN Type 91.** The commonly quoted 0.4 s delay (South Dakota WDR, navweaps tech-092) is **[UNCERTAIN]**. Whatever the exact value, it means the shell bursts only after being stopped. That matches South Dakota's experience: of 26 hits, ~15–18 passed straight through her upperworks.
- **Slopes and turtlebacks.** A shell that defeats the belt but not the slope is either stopped or deflected upward, and bursts in the wedge between belt and slope [INFERRED ~70 %]. The citadel below survives. That was Bismarck's dominant result.

### 3.6 What a burst wrecks

These are cube-root scaled rules, fitted to war-damage cases. They are game-tuning values, not engineering ratings. W is the TNT-equivalent filler in kg. **[INFERRED]**

| Radius | Formula | Meaning | Fitted to |
|---|---|---|---|
| `R_wreck` | 1.6·W^⅓ m | Equipment wrecked, light bulkheads torn out, ~80 % of crew within it become casualties | Kirishima casemate hits: 16″ Mk 8 (18.6 kg) made holes ~10 m across |
| `R_hole` | 0.45·W^⅓·√(6/t_mm) m | Hole radius in plating from a contact burst | IJN 8″ common on ¼″ STS → 0.9 m (South Dakota hit 5: 6 ft hole); 14″ on ¾″ → 0.8 m (South Dakota hit 2: 5×4 ft) |
| `R_blast` | 3.5·W^⅓ m | Light structure, fittings and personnel injured | — |
| Bulkhead breach | `R_wreck > 0.4 × compartment length` | The burst also opens the next watertight compartment | Samuel B. Roberts; Kirishima |

**Values per shell** (from the code):

| Shell | W kg | R_wreck | R_blast | Hole in 6 mm | 50 % of fragments still defeat 6 mm out to |
|---|---|---|---|---|---|
| 5″/38 AAC | 3.1 | 2.3 m | 5.1 m | 0.7 m | ~2 m |
| 6″ HC | 5.7 | 2.9 | 6.3 | 0.8 | 2 |
| 8″ AP / 8″ HC | 2.2 / 9.2 | 2.1 / 3.4 | 4.5 / 7.3 | 0.6 / 0.9 | 3 / 4 |
| 14″ AP / 14″ HC | 9.9 / 45 | 3.4 / 5.7 | 7.5 / 12.4 | 1.0 / 1.6 | 15 / 29 |
| 15″ APC Mk XXII | 22 | 4.5 | 9.8 | 1.3 | 19 |
| 16″ Mk 8 AP / Mk 13 HC | 17.6 / 66 | 4.2 / 6.5 | 9.1 / 14.2 | 1.2 / 1.8 | 23 / 42 |
| **46 cm T91 AP / T0 HE** | 23.9 / 61.7 | **4.6 / 6.3** | 10.1 / **13.8** | 1.3 / **1.8** | 34 / **52** |
| 18″ RN APC / CPC | 57 / 39 | 6.1 / 5.4 | 13.4 / 11.8 | 1.7 / 1.5 | 34 |

**Fragments** (Okun, *Misc. armour formulae*). These give the STS thickness defeated as a function of distance, both in calibres.

| Distance from burst | 50 % of fragments defeat | 10 % defeat |
|---|---|---|
| ≤ 5 cal (contact) | 0.08 cal (AP); 0.11 cal (HE) | — |
| 20 cal | 0.021 cal | 0.093 cal |
| 50 cal | 0.016 cal | — |
| 100 cal | 0.011 cal | — |

**Fragment counts and spray pattern [UNCERTAIN, via a summarising fetch]**
- About 2,000 fragments for an 8″ HE, about 3,000 for common/SAP, about 4,000 (smaller) for AP.
- Side spray goes out in a thin ring perpendicular to the shell axis.
- The AP nose (≤ 33 % of body weight) carries on as a slug. The base plug shields a rear 90° cone.
- A low-order or black-powder burst throws a 60° forward cone of medium chunks at about 600 ft/s.

**Practical reading.** A 16″ AP burst perforates every light bulkhead (≤ 10 mm) within roughly 20 calibres (8 m). Its 1–1.5″ splinter plating holds beyond 2–8 m. Fragments from WDR 51 measurements: a 6″ HC averages about 3,200 ft/s.

### 3.7 Non-penetrating heavy hits

| Target | Effect | Evidence | Rule [INFERRED] |
|---|---|---|---|
| Turret face / barbette | Jam in train; one gun out; sights knocked out of alignment; crew stunned | Von der Tann A (jammed at 120°); Tiger Q; Scharnhorst Anton; Jean Bart (glacis pushed down; **firing again the same day**); South Dakota III (training gear) | ≥ 11″: jam 35 % (half repairable in 10–60 min), one gun out 15 %, sights 25 %, stunned 2–5 min 50 %. 8″: jam 5 %. ≤ 6″: 1 % |
| Thin turret roof (< 0.3 cal) | Roof plate driven in, spall kills crew | Tiger's Q roof (2 dead, rangefinder wrecked); Dunkerque turret 1 (roof deflected the shell but was driven in; one half-turret's crew asphyxiated by fire) | Spall cone 30–45°, 3–5 m |
| Conning tower | Vision slits and communications; fragments through the slits | Derfflinger CT; Suvorov (helmsman killed); Bismarck CT "swiss cheese" | — |
| Belt at the waterline | Plate shoved in, seams opened, slow leaks; the tank or bulge outside it holed | South Dakota hit 4 (5 tanks flooded); Bismarck belt displaced by a torpedo | ≥ 11″: 40 % seam leak of 5–50 t/h; 25 % outboard tank flooded (10–100 t) |
| Any heavy hit | Shock to lighting, switchboards and instruments | South Dakota: breaker trips; even her own Turret III blast caused a 1-minute power loss | 10 % chance of shock damage to equipment within 10 m; electrical trip 1–5 min |

### 3.8 Diving shells and underwater hits

- **Frequency.** Okun knows of **no** penetrating underwater hit except Boise. Lundgren's Kirishima reconstruction has several underwater hits among 20 **[UNCERTAIN — the two sources conflict]**.
- **Rule [INFERRED]:**
  - Non-diving AP landing 0–30 m short: 8–15 % become underwater hits.
  - IJN Type 91 landing 0–80 m short: 25–35 %.
  - An underwater hit strikes 1–4 m deep, below the belt, at 30–50 % of its velocity, and defeats at most ~0.5 calibre of plate.
  - Against a torpedo-defence system, it bursts on or is stopped by the holding bulkhead. The outer tanks flood (100–1,000 t).
  - Against a cruiser, or the ends of a battleship, it goes straight into a magazine or machinery space (Boise: 1,200 t and ~3,000 lb of powder burned).
  - Dud rate ~30 %, but duds still flood through the hole.

### 3.9 Fire and ready ammunition

| Situation | P(fire) per burst | Evidence |
|---|---|---|
| WWII HE in superstructure / deck | 0.40–0.50 | South Dakota 13–14 fires / 26 hits; San Francisco ~22 / 45; Hipper 1 hangar fire / 3 × 6″ |
| WWII AP | 0.10–0.20 | Mostly pass-throughs |
| 1890–1905 ships (wood, coal on deck, paint) | 0.60–0.80 | Yalu, Santiago, Tsushima |
| Fragments reach ready-use or exposed propellant | ~0.5 | Sterett (3 powder fires from 11 hits); Hood's boat deck (one 8″ hit); Malaya's 6″ battery (most of 65 dead); South Dakota's 1.1″ clipping room; Giulio Cesare (37 mm ready ammunition → fumes into the boiler rooms → 4 boilers out) |
| Fire becomes serious (> 10 min of damage control) | ~0.05 USN WWII; ~0.25 if fire mains are cut or the ship carries wood or deck coal | Ralph Talbot lost the firemain; Santiago |

**Escalation**
- A fire in a handling room or a turret uses `07_magazine_explosions.md` (flash chain → plateau pressure).
- A fire on a destroyer that reaches a magazine hours later: Cushing and Monssen.
- Torpedo warheads in fires (Preston). Note that Ralph Talbot's torpedo mount took a direct 8″ burst without setting off its warheads.

---

## 4. Case data

### 4.1 Heavy and medium guns against thin-skinned ships

| Target (size) | Action | Shooter / shell | Hits | What happened | Outcome | Source |
|---|---|---|---|---|---|---|
| **Johnston** (Fletcher, 2,050 t) | Samar 1944 | First salvo "14-inch or larger" (Wikipedia: Yamato 46 cm AP), then 5–8″ | ≥ 13 identified (WDR) | Hits 1–3 burst on the after reduction gear, HP turbine and No. 4 boiler: steam line cut, gyro, SC radar and after-gun power lost, slow flooding, **17 kn**. Hits 5–6 on the bridge (one dud through): both directors out. Hit 11: handling-room fire. Hit 12: forward magazine flooded. **Hit 13 flooded the forward fireroom and stopped her** | DIW about 09:40, sank 10:10. 186 of 327 died. WDR: would probably have survived "but for the continued presence of the enemy" | WDR 51; DANFS |
| **Hoel** (Fletcher) | Samar | Haguro 8″ **AP** first, then many | > 40 | 1st salvo: 2 × 8″ through the bridge and director **without bursting**, yet radar, radio and gun control were lost. 3rd salvo: 2 below the waterline, port engine and after generator lost, −4.5 kn. 6.1″ hit on the last boiler → DIW | Sank 08:55, about 1 h 50 min after the first hit. 253 of 273 died | Wikipedia; NHHC Samar |
| **Samuel B. Roberts** (DE, 1,350 t) | Samar | Cruiser 8″, then Kongō 14″ | Several | 8″ in a boiler (28 → 17 kn). **14″ salvo: 40 × 10 ft hole in No. 2 engine room**, fuel tanks ruptured, fires | Abandoned about 09:10. 89 killed | DANFS; NHHC |
| **Gambier Bay** (CVE) | Samar | 46 cm, 14″, 8″ | ~15 | AP "over-penetrated her hull without exploding". The 08:20 hit flooded the forward engine room (10 kn) → DIW | Capsized about 61 min after the first hit | Wikipedia |
| **Kalinin Bay** (CVE) | Samar | 1 × 14/16″ + 14 × 8″ AP | 15 | Flight and hangar decks holed, radar and radio lost | **Survived**, 5 dead | DANFS |
| **San Francisco** (CA) | Guadalcanal, 13 Nov 1942 | Hiei/Kirishima 14″ bombardment shells; 8″, 6″, 5″ | ~45 (2 × 14″) | All topside. 14″ bombardment shells "defeated… easily" by the 5″ barbette. ~22 fires, all controlled. Bridge officers almost all killed (Callaghan). **≤ 500 t water, no hits below the waterline** | Survived and fought on | WDR 26 |
| **Atlanta** (CL) | Same action | ~19 × 8″ from San Francisco (friendly fire) | 19+ | "Almost all… passed through the thin skin… without detonating"; fragments killed Adm. Scott. A torpedo did the real damage | Scuttled | Wikipedia |
| **Laffey** (DD) | Same action | Hiei 14″ Type 3 | 1–2 | "Neither shell caused significant damage" | Lost to a torpedo | Wikipedia |
| **Sterett** (DD) | Same action | 4–6″ | 11 | Fragments set off ready 5″ powder (3 separate powder fires); steering damaged; "considerable, although not vital" | Survived | WDR Sterett |
| **Monssen** (DD) | Same action | Mixed, incl. 3 battleship-calibre | ~39 | Burning hulk within ~20 min | Lost: **magazine explosion after fire** | WDR 51 |
| **Ralph Talbot** (DD) | Savo 1942 | IJN 8″ | 5 | Hit on the torpedo mount burst; warheads did not go off. Firemain cut. Sheer-strake hit: ~240 t flooding, 20° list | Survived | WDR 51 |
| **Boise** (CL) | Cape Esperance 1942 | 8″ common and AP; 5″ | 8 | 8″ AP on the barbette broke up. **8″ diving hit under the belt burst in a magazine: ~3,000 lb of powder burned**; quick flooding saved her. ~1,200 t water | Back in formation in ~2 h; 107 killed | WDR 24 |
| **Achates** (DD) | Barents Sea 1942 | Hipper 20.3 cm | 1 heavy + near miss | One hit killed 40 including the CO; list grew | Sank about 2 h 15 min after the hit | Wikipedia |
| **Onslow** (DD) | Barents Sea | Hipper 20.3 cm | 3 + near miss | 2 guns out, fire, radar damaged. 17 killed | Survived | Wikipedia |
| **Friedrich Eckoldt** (DD) | Barents Sea | Sheffield 6″ at 4,000 m, by surprise | Broadsides | "Broke in two and sank… in less than two minutes" | Lost with all hands | Wikipedia |
| **Saumarez** (DD) | North Cape 1943 | Scharnhorst | 1 + near miss | A dud passed **through the director tower**, killing 11 | Survived on one engine | Wikipedia |
| **Exeter** (CA) | Java Sea 1942 | Haguro 8″ | 1 | Through a 4″ mount into B boiler room: **6 boilers off line, 5 kn** | Survived the day | Wikipedia |
| **Sydney** (CL) | vs Kormoran 1941 | 15 cm from ~8 km | Many | 2nd salvo: bridge and director. 3rd–4th: A and B turrets. Waterline hit by the forward engine room, plus 1 torpedo | Burned for hours; lost with all 645 | Wikipedia |
| **Alfieri, Carducci** (DDs) | Matapan 1941 | 15″ at 3,800 yd | Broadsides | Both "sunk in the first five minutes" | Lost | Wikipedia |
| **Kent** (armoured cruiser) | Falklands 1914 | 10.5 cm | 38 | "Did not cause significant damage" | — | Wikipedia |

**USN aggregate figures** (WDR 51, destroyers)

- **Hull girder.** There was "no instance… in which gunfire damage seriously weakened the main hull girder". Destroyers hit by gunfire died from:
  - loss of watertight integrity and vital systems (flooding with list: Preston, Hoel, Johnston; with trim: Duncan);
  - magazines after fire (Cushing, Monssen).
- **Survival.** 84 % of destroyers damaged by above-water weapons survived (see `damage-model-research.md`).
- **Size rule.** "No ship larger than 3,000 tons… was sunk by gunfire from weapons 5″ or smaller" in WWII. This is quoted from the USN war-damage series via a secondary source **[UNCERTAIN wording]**.

### 4.2 Medium calibre against capital ships and armoured cruisers

| Ship | Action | Shooters | Hits | Effects | Outcome |
|---|---|---|---|---|---|
| **South Dakota** | Guadalcanal, 14–15 Nov 1942 | Kirishima 14″, Atago/Takao 8″, cruisers' 6″/5.5″, destroyers' 5″ | 26 (BuShips: 1 × 14″, 18 × 8″, 6 × 6″, 1 × 5″). Lundgren: 2 × 14″ HE, several "6″" actually 5.5″ | ~15–18 passed through without bursting. Every search radar lost (SC antenna shot away). Sky Control out (23 cables cut by a 5.5″ dud). 5″ director No. 1 column severed. 13 fires. Electrical: a 3-min F.C./I.C. loss from shorts, plus a 1-min loss caused by her own Turret III blast. 6 belt hits, **0 penetrations**. List 0.75° | "Neither the strength, buoyancy nor stability were measurably impaired". 38–40 killed **[UNCERTAIN count]**. Lee: "deaf, dumb, blind and impotent" |
| **Hiei** | Guadalcanal, 13 Nov 1942 | US cruisers' 8″/6″, destroyers' 5″ at point blank | ~85 (≈30 × 8″) | Bridge raked (Laffey at ~20 ft): Abe wounded, chief of staff killed. Main and secondary fire control out. Superstructure ablaze. **2 × 8″ in the steering room: flooded, rudder jammed** | Circled at ~5 kn; sunk next day by aircraft and scuttled. 188 killed |
| **Kirishima's 5″ damage** | 15 Nov 1942 | Washington 5″/38 | Unknown; 40 claimed, judged "too high" (Lundgren) | Rope mantlets and searchlights on fire; casemate fires | Sunk by the 16″ hits (§4.3) |
| **Graf Spee** | River Plate 1939 | Exeter 8″; Ajax and Achilles 6″ | ~20 (2–3 × 8″ + ~17 × 6″); one source says ~70 **[UNCERTAIN]** | An 8″ shell through 2 decks wrecked the **fuel purification plant (16 h of fuel left)**; also desalination and galley. Bow hole. 2/3 of AA out | Mission kill; scuttled. 36 killed |
| **Hipper** | Barents Sea 1942 | Sheffield/Jamaica 6″ | 3 | One flooded No. 3 boiler with oil and water; starboard turbine out → 23 kn. Two hits started a hangar fire | Admiral broke off |
| **Colorado** | Tinian 1944 | 150 mm shore batteries | 22 | 43 killed, 198 wounded: crowded AA positions | Fought on |
| **Oryol** | Tsushima 1905 | Japanese 6–12″ common/HE | 5 × 12″, 2 × 10″, 9 × 8″, 39 × 6″ + 21 smaller | 0 of 4 belt hits penetrated. 8″ hits jammed two 6″ turrets; one turret burnt out by an ammunition fire. 43 killed | "Only moderately damaged" |
| **Zhenyuan / Dingyuan** | Yalu 1894 | Japanese QF 4.7–6″, 12.6″ | ~220 / ~200 | Belts never pierced ("none… deeper than 4 inches"). Repeated fires | Both afloat. Dingyuan: 14 killed |
| **Mikasa** | Tsushima | Russian 6–12″ | > 40 | "None seriously damaged her". 113 casualties | Fought on |

### 4.3 Capital calibre against capital ships

| Ship | Action | Hits | Hit-by-hit highlights | Outcome |
|---|---|---|---|---|
| **Kirishima** | 15 Nov 1942, Washington at ~7.8–8.4 km | 20 × 16″ + 17 × 5″ in ~7 min (Lundgren from the Japanese damage sketch; US estimate 8–9) | Hit 1: compass bridge. Hits 2–3: holes ~10 m across in the deck above the secondary battery. Hits 6–7 underwater: through the slope, middle deck opened to the sea. Turret 1 hit: magazine flooded. Hit 15 on the 75 mm stern belt: rudder room flooded, jammed at 10°. **Hits 16 and 19 on the hydraulic pump rooms: turrets 3–4 silenced**. Hits 17–18 on No. 2 barbette | Capsized about 2¼ h later after counter-flooding. 1914-era subdivision. ~1,100 of ~1,400 saved |
| **Bismarck** | Denmark Strait, 24 May 1941 | 3 × 14″ from PoW | Bow: **over-pen**, 1,000–2,000 t taken in, ~1,000 t of fuel cut off, 3° trim. **Under-belt hit burst on the torpedo bulkhead**: generator room flooded, a boiler room partly flooded, 2 boilers shut down. Boat/catapult hit | 9° list, −2 kn; this shaped the run to France |
| **Prince of Wales** | Denmark Strait | 4 × 38 cm + 3 × 20.3 cm | 38 cm **through the compass platform without bursting**: most people there killed (cap and debris). Radar office crew killed by a 20.3 cm hit. **38 cm diving hit: 4 m inboard, stopped by the torpedo bulkhead, dud**. Gun output −26 %, mostly mechanical | Broke off. 13 killed |
| **Bismarck** | 27 May 1941 | ~300–400 (≈80 heavy) | 09:02 Rodney 16″: bridge and forward director, senior officers. Aft director lasted 3 salvos. **All 4 turrets silent by 09:31 (~44 min)**. Caesar jammed by a 356 mm face hit. Dora: 3 barbette penetrations, a barrel split. Belt: **~3 holes**, all above water; no underwater citadel penetration (Ballard) | Sank 10:40 after torpedoes and scuttling. Gunfire "contributed little to the eventual sinking" |
| **Scharnhorst** | North Cape 1943 | ~13 heavy **[UNCERTAIN]** + 8″/6″ | Norfolk 8″: **forward Seetakt radar destroyed**. DoY first 14″ hit: Anton jammed in train. **18:20: 14″ through the upper belt burst in No. 1 boiler room: 31 → 8–10 kn**, back to 22 kn after repairs | Torpedoes finished her. 36 of 1,968 survived |
| **Gneisenau** | Lofoten 1940 | 2 × 15″ (Renown) | One went **through the main director without bursting** (6 killed); one on the after turret / Anton rangefinder **[UNCERTAIN]** | Broke off |
| **Dunkerque** | Mers-el-Kébir 1940 | 4 × 15″ | 1: deflected off the turret 1 roof but drove it in; fire, half-turret crew asphyxiated. 2: through the stern without bursting, cut the rudder control line. 3: upper edge of the belt into a secondary handling room, ammunition fire. **4: through the belt and torpedo bulkhead, burst in boiler room 2: power lost** | Beached; out of action |
| **Bretagne** | Mers-el-Kébir | 4 large-calibre | Hits near turret 4 and in the centre engine room; ready ammunition | **Blew up and capsized ~10 min after the first hit**. 1,012 killed |
| **Jean Bart** (incomplete) | Casablanca 1942 | 7 × 16″ (Massachusetts) | Through both armour decks into an **empty** magazine. Turret glacis pushed down: **jammed, firing again by 17:24**. One deflected by the belt went down through the bottom (dud) | 22 killed |
| **Seydlitz** | Dogger Bank / Jutland | 1 (13.5″) / 21 heavy + torpedo | Dogger Bank: a barbette hit that did not get through still sent flash into the working chamber; **both after turrets burned out, 159 dead**. Jutland: 5 of 16–22 heavy hits pierced armour; **5,308 t** aboard, freeboard 2.5 m | Survived both |
| **Lützow** | Jutland | 24 heavy (8 in the bow, 2 underwater) | ~8,000 t by 02:20; forward draught > 17 m | Scuttled |
| **Derfflinger** | Jutland | 17 heavy + 9 secondary | **9 hits in 6 minutes: C and D turrets burned out** (73 of 78 and 80 of 80 dead); ~3,000 t | Survived, 157 killed |
| **Von der Tann** | Jutland | 4 heavy | A jammed by a barbette hit; B and D lost to mechanical failure. **No main battery for a long spell** | Survived |
| **Lion** | Dogger Bank / Jutland | 14 / 13–14 | Dogger Bank: **a feed-water tank ruptured → port engine out → 15 kn**, ~3,000 t, 10° list. Jutland: Q turret face/roof joint; magazine flooded in time | Survived |
| **Tiger** | Dogger Bank | 6 | An 11″ shell burst **on Q turret's roof without penetrating**; fragments damaged a breech and jammed training | Q out |
| **Warspite** | Jutland | 15 | A hit near the wing engine room **jammed the steering**: two full circles under fire | Survived |
| **Exeter** | River Plate | 7 × 11″ | B turret out, and **its splinters killed all but 3 on the bridge**. A out; Y lost later to flooding of its machinery. 7–8° list | Left with one 8″ gun; 61 killed |
| **Ajax** | River Plate | **1 × 11″** | X out and Y jammed | — |
| **Tsesarevich** | Yellow Sea 1904 | 13 × 12″ + 2 × 8″ | One 12″ salvo on the bridge: **Admiral Vitgeft and staff killed, helm jammed**, she swung out of line; Russian line broke up | Did not sink |
| **Oslyabya** | Tsushima | "Several heavy" | Unarmoured bow holed at the waterline; speed drove water in; 12° list in ~30 min | **Capsized in ~1 h — first steel battleship sunk by gunfire alone** |

Sources for 4.1–4.3: per-ship Wikipedia articles; NHHC WDRs 24, 26, 51, 57; Lundgren's South Dakota and Kirishima analyses; USNI 1991 "Who sank Bismarck?"; Naval Gazing "Shells at Jutland"; navweaps INRO Bismarck; full list at the end.

### 4.4 Trials

| Trial | What was fired | Result |
|---|---|---|
| **Edinburgh hulk** 1908–10 (RN) | Lyddite AP against modern armour | Lyddite AP **burst while penetrating** at oblique impact; Ordnance Board asked for a new AP shell in 1910 [secondary source, UNCERTAIN] |
| **Hood 1919** (RN, Okun) | 15″ Greenboy, 1,430 ft/s, 7″ at 40° | Through plate, turtleback and a bulkhead; **burst 34–40 ft behind the plate**. Behind a 1″ magazine roof it was a magazine hit. A 2″ roof made it burst on the roof |
| **Baden 1921** (RN) | 17 × 15″ from Terror at ~500 yd, then Erebus | New shells "much more effective" than the Jutland types. **7″ casemate armour "completely useless"**: it fuzed shells that burst inside the battery. Bursts in the ends lifted the upper deck 4 ft 6 in and tore away 43 ft. One AP dud; two SAP broke up |
| **Ex-Washington BB-47** 1924 (USN) | Torpedoes, bombs, an internal 400 lb charge, 14 × 14″ dropped from 4,000 ft (1 penetrated), then 14 more 14″ from Texas | Survived everything except the final 14″ hits. Led to thicker decks and triple bottoms |

---

## 5. Patterns, as model rules

**R1. Fuze physics decides "over-penetration vs burst". It is not a random roll.**
- Compare the plate in the path with the arming threshold (0.07 cal at 0°, falling to ~0.03 cal at 60°).
- If nothing arms the fuze, the result is two holes. Damage is limited to systems and people on the line of flight.
- Exception: heavy machinery in the path arms the fuze (Johnston). Give each zone a "heavy mass" chance.

**R2. HE has a ceiling of ~0.2 calibre of plate.**
- Below the ceiling it bursts just inside. Above it, it bursts outside. Above-armour effects only: splinters, fittings, AA crews, fire.
- This is why HE is the best destroyer-killer and useless against citadels.

**R3. Destroyers die by losing machinery, then by flooding or fire. Hit count is a poor predictor.**
- One machinery hit = crippled.
- Two adjacent spaces flooded, or a burst that breaches a bulkhead = sinking.
- Fire reaching a magazine = delayed loss.
- With the enemy still present, crippled ships get finished off (Johnston, Hoel).

**R4. Medium calibre against armoured ships = mission kill.**
- It strips radar, fire control, communications, AA, searchlights and the bridge.
- Its one dangerous route is the **unarmoured steering and waterline ends** (Hiei, Warspite, Kirishima).

**R5. Heavy hits on armour mostly do not penetrate. They still matter.**
- Turret and barbette jams (~35 %).
- Spall from roofs.
- Seam leaks.
- Command loss through CT slits.

**R6. The first heavy hits go to fire control.**
- Tall superstructures catch a large share of hits: Bismarck 09:02, Gneisenau, Kirishima hit 1, PoW, Tsesarevich, Exeter, Sydney.
- Area weighting alone produces this; no special "crit" rule is needed.

**R7. Ends flood, and speed drives the water in.**

| Ship | Hits | Water |
|---|---|---|
| Bismarck | 1 bow hit | 1,000–2,000 t |
| Von der Tann | 1 × 15″ underwater | 600 t |
| Lion | ~14 | ~3,000 t |
| Derfflinger | 17 | ~3,000 t |
| Seydlitz | 21 + 1 torpedo | 5,308 t |
| Lützow | 24, 8 in the bow | ~8,000 t, fatal |

Averaged: ~150–350 t per heavy hit over a whole beating [INFERRED]. Make inflow scale with speed (`02`/`damage-model-research` §8.4).

**R8. Electrical and hydraulic nodes are the battleship's soft spots.**
- Kirishima's pump rooms silenced turrets 3–4.
- South Dakota's breakers tripped.
- Bismarck's generator room flooded.
- Trips last minutes; floods last for the rest of the battle.

**R9. Battleships are rarely sunk by gunfire alone. Battleship sinkings come from:**
- magazine explosion (Hood, Invincible, Queen Mary, Defence, Bretagne);
- stability collapse in older ships (Kirishima, Oslyabya);
- torpedoes or scuttling after a gunfire mission kill (Bismarck, Scharnhorst, Hiei, Yamashiro, Lützow, Blücher).

**R10. Casualties are a low baseline plus rare spikes.**
- Baseline [INFERRED from §4]: ~1–3 killed per ordinary heavy hit; ~1–2 per medium hit; ~0.5 for a pass-through.
- Spikes: turret, bridge or casemate fires kill 50–160 in one event (Seydlitz 159, Derfflinger 80, Malaya 65).
- Crowded open AA positions take ~8–12 casualties per medium HE hit (Colorado, Tennessee, Onslow).

---

## 6. What the reference model produces

All numbers come from `gunfire_ref.py`. They are illustrations of the rules in §3 and §5, not predictions. The targets are a **Fletcher** (114.7 × 12 m, 2,900 t, 6 zones) and a **South Dakota** (207 × 33 m, 44,500 t, 11 zones: 311 mm belt at 19° behind 32 mm of hull, 38 + 146 mm decks, 457/184 mm turrets).

### 6.1 Ballistics and penetration (sanity check)

The point-mass model uses one drag form factor (i = 1.10) for every shell.

| Check | Model | navweaps |
|---|---|---|
| 16″ Mk 8 at 20 kyd: striking velocity / fall angle | 1,732 fps / 15.0° | 1,740 fps / 14.9° |
| 16″ Mk 8 at 30 kyd | 1,580 fps / 27.7° | 1,567 fps / 28.3° |
| 46 cm T91 at 10 km / 15 km | 622 / 559 m/s | 620 / 562 m/s |
| 16″ Mk 8 side armour at 10 / 20 / 30 kyd | 643 / 507 / 399 mm | 664 / 509 / 380 mm |
| 16″ Mk 8 deck armour at 10 / 20 / 30 kyd | 42 / 100 / 174 mm | 43 / 99 / 169 mm |

**Immune zone of the SoDak scheme** (broadside-on target, inclined belt):

| Shell | Belt defeated out to | Deck defeated from | Immune zone |
|---|---|---|---|
| 14″/45 AP | 14.5 km | 30.0 km | 14.5–30 km |
| 15″ APC Mk XXII | 16.0 km | 27.0 km | 16–27 km |
| 38 cm APC | 17.5 km | 30.5 km | 17.5–30.5 km |
| 16″/50 AP Mk 8 | 23.0 km | 26.5 km | **23–26.5 km** |
| 46 cm T91 | 23.5 km | 26.5 km | 23.5–26.5 km |
| 18″/40 APC | 19.0 km | 23.0 km | 19–23 km |

The historical SoDak design zone against the lighter 16″/45 shell was about 16–23 km. Against the super-heavy Mk 8 it shrank, consistent with the narrow band above.

### 6.2 Given a hit: side or top

From §3.1. The fall angle at the range of the hit decides how many hits strike vertical faces (belt, hull side, superstructure fronts) rather than decks and roofs. Both targets are broadside-on.

| Shell | Range | Fall | Fletcher: side share | SoDak: side share |
|---|---|---|---|---|
| 5″/38 AAC | 5 / 10 / 15 km | 4.7° / 19.9° / 40.1° | 88 / 62 / 41 % | 83 / 52 / 32 % |
| 8″/55 AP | 5 / 15 / 25 km | 3.3° / 18.2° / 44.2° | 91 / 64 / 38 % | 87 / 55 / 29 % |
| 16″/50 Mk 8 | 5 / 15 / 25 km | 2.8° / 11.3° / 24.1° | 92 / 75 / 57 % | 89 / 66 / 47 % |
| 46 cm T0 HE | 5 / 15 / 25 km | 2.6° / 10.7° / 23.6° | 93 / 76 / 57 % | 90 / 68 / 47 % |

The faster fall of the light shells explains why, at the same range, a cruiser's 8″ lands on decks more often than a battleship's 16″.

### 6.3 Per-hit outcomes

Monte Carlo, 6,000 hits each; zones chosen by projected area.

| Shell → target @ range | Burst inside | No burst (over-pen / dud) | Defeated / ricochet / on armour | E[water t] | P(fire) | E[casualties] |
|---|---|---|---|---|---|---|
| 5″/38 AAC → Fletcher @ 8 km | 100 % | 0 % | 0 % | 19 | 41 % | 2.3 |
| 6″ HC → Fletcher @ 10 km | 100 % | 0 % | 0 % | 21 | 44 % | 3.4 |
| 8″ AP SH → Fletcher @ 12 km | 26 % | **74 %** | 0 % | 13 | 3 % | 0.6 |
| IJN 20 cm T91 → Fletcher @ 12 km | 7 % | **93 %** | 0 % | 13 | 1 % | 0.4 |
| 16″ AP → Fletcher @ 15 km | 6 % | **94 %** | 0 % | 17 | 0 % | 0.6 |
| 16″ HC → Fletcher @ 15 km | 100 % | 0 % | 0 % | 90 | 67 % | 17.5 |
| 46 cm T91 AP → Fletcher @ 15 km | 6 % | **94 %** | 0 % | 18 | 0 % | 0.7 |
| **46 cm T0 HE → Fletcher @ 15 km** | **100 %** | 0 % | 0 % | **89** | **66 %** | **16.8** |
| 5″/38 AAC → SoDak @ 8 km | 45 % | 0 % | 55 % | 13 | 26 % | 1.0 |
| 8″ AP SH → SoDak @ 12 km | 23 % | 30 % | 47 % | 12 | 4 % | 0.5 |
| IJN 36 cm T0 HE → SoDak @ 8 km | 77 % | 0 % | 23 % | 43 | 43 % | 5.7 |
| 16″ AP → SoDak @ 10 / 20 / 28 km | 33 / 32 / 44 % | 57 / 46 / 43 % | 10 / 22 / 14 % | 23 / 17 / 7 | 5 % | ~2 |
| 46 cm T0 HE → SoDak @ 20 km | 92 % | 0 % | 8 % | 72 | 56 % | 10.2 |

Notes on the table:
- "Burst inside" on the SoDak mostly means superstructure and ends.
- On a 46 cm HE hit against the Fletcher, the burst breaches the next watertight bulkhead **22 %** of the time.

**Capital-ship AP against the SoDak, per hit**

| Shell | 8 km citadel burst / turret out | 15 km | 22 km | 28 km |
|---|---|---|---|---|
| 14″/45 AP | 10.8 / 7.3 % | 4.3 / 2.6 % | 0 / 2.3 % | 0.5 / 2.3 % |
| 15″ APC 1916 (Jutland shell) | **2.8** / 6.4 % | 1.9 / 3.4 % | 0 / 2.4 % | 4.0 / 2.1 % |
| 15″ APC Mk XXII | 10.6 / 7.6 % | 7.0 / 3.3 % | 0 / 2.4 % | 18.1 / 2.4 % |
| 16″/50 Mk 8 | 11.4 / 7.7 % | 8.7 / 6.3 % | 5.2 / 4.2 % | 20.6 / 2.3 % |
| 46 cm T91 | 9.2 / 7.7 % | 7.7 / 6.7 % | 4.8 / 4.2 % | 9.7 / 2.0 % |

**What the table shows**
- Even at point-blank range, only ~1 heavy hit in 9–10 bursts inside the citadel. Bismarck: ~3 belt holes in ~400 hits.
- Inside the immune zone that drops to ~0, and beyond it deck penetrations return.
- At 28 km, the long Type 91 delay sends many deck-penetrating shells right through to burst beyond the citadel, which costs it against the Mk 8.
- The Jutland-era shell quality cuts citadel bursts by about 4×. That is the 1-in-17 effect.

### 6.4 How many hits does a destroyer take?

Fletcher state after N hits ("crippled" = machinery lost or > 300 t aboard; "lost" = flooding past reserve, a magazine explosion, or a fire reaching a magazine). **[INFERRED]** rules are in `dd_status()`.

| Shell (range) | N = 1 | 2 | 3 | 5 | 10 | 20 | 40 |
|---|---|---|---|---|---|---|---|
| 5″/38 AAC (8 km) | 12 / 1 % | 23 / 3 % | 33 / 5 % | 48 / 6 % | 77 / 17 % | 98 / 44 % | 100 / 74 % |
| 6″ HC (10 km) | 13 / 2 % | 24 / 3 % | 35 / 6 % | 54 / 8 % | 79 / 18 % | 98 / 48 % | 100 / 76 % |
| 8″ AP SH (12 km) | 10 / 1 % | 19 / 2 % | 27 / 2 % | 43 / 5 % | 67 / 9 % | 90 / 15 % | 100 / 33 % |
| 8″ HC (12 km) | 14 / 2 % | 27 / 4 % | 38 / 7 % | 55 / 9 % | 83 / 21 % | 98 / 49 % | 100 / 82 % |
| 16″ AP (15 km) | 12 / 1 % | 22 / 2 % | 32 / 3 % | 46 / 4 % | 71 / 8 % | 90 / 17 % | 100 / 51 % |
| 46 cm T91 AP (15 km) | 12 / 1 % | 22 / 2 % | 32 / 3 % | 47 / 4 % | 71 / 9 % | 92 / 19 % | 100 / 51 % |
| **46 cm T0 HE (15 km)** | **30 / 5 %** | **52 / 13 %** | **65 / 20 %** | **83 / 33 %** | **98 / 74 %** | 100 / 95 % | 100 / 100 % |

**Checks against history**

| Case | Historical | Model |
|---|---|---|
| Sterett | 11 hits, survived crippled | 10 hits: 77 / 17 % |
| Monssen, Hoel | ~40 hits, lost | 40 hits: 74 % lost |
| Ralph Talbot, Onslow | 3–5 × 8″, survived | 43 / 5 % at 5 hits |
| Johnston | ≥ 13 including 3 heavy, crippled, sunk only because the enemy stayed | — |
| Samuel B. Roberts | 14″ HE in the engine room, lost | Smaller DE; the model's 30 / 5 % per hit is for a Fletcher |

### 6.5 The two headline cases

**A — One heavy broadside lands k hits on a Fletcher at 15 km**

| Shell | k = 1 crippled / lost | k = 2 | k = 3 | k = 4 | E[water] per hit | E[casualties] per hit |
|---|---|---|---|---|---|---|
| **46 cm Type 0 HE** | **32 / 7 %** | **53 / 14 %** | **67 / 19 %** | **77 / 26 %** | 90 t | 16.6 |
| 16″ HC Mk 13 | 31 / 7 % | 54 / 14 % | 68 / 19 % | 78 / 28 % | 92 t | 17.4 |
| 46 cm Type 91 AP | 11 / 1 % | 21 / 2 % | 30 / 3 % | 37 / 3 % | 17 t | 0.6 |
| 16″ AP Mk 8 | 11 / 1 % | 21 / 2 % | 31 / 3 % | 38 / 3 % | 17 t | 0.6 |
| RN 18″ APC | 10 / 1 % | 19 / 2 % | 27 / 3 % | 35 / 3 % | 16 t | 0.7 |
| RN 18″ CPC (base-fuzed, black powder) | 10 / 1 % | 18 / 2 % | 27 / 2 % | 34 / 3 % | 15 t | 0.6 |

**Reading:**
- **Nose-fuzed HE is what kills destroyers.** Base-fuzed shells (AP, and the RN CPC "common") pass through a destroyer's 6–12 mm plating without arming, so calibre stops mattering.
- **One heavy HE hit is a coin-flip mission kill, not a guaranteed sinking.** Prompt loss needs a waterline machinery hit with a bulkhead breach (Samuel B. Roberts), a magazine, or fire later (Cushing, Monssen).
- **Near misses add splinter damage the model does not count yet** (§8). For HE shells landing within 10–20 m of a destroyer this may matter as much as the direct hits.

**B — A SoDak takes N hits of 5″/38 AAC at 7 km**

| | 10 hits | 30 hits | 75 hits |
|---|---|---|---|
| Fires started | 2 | 8 | 20 |
| Casualties | 11 | 31 | 80 |
| Bridge / flag damaged ≥ 1× | 20 % | 48 % | 82 % |
| AA mounts | 24 % | 52 % | 82 % |
| CIC / radio | 15 % | 40 % | 77 % |
| Search radar | 8 % | 24 % | 52 % |
| FC radar | 8 % | 18 % | 43 % |
| Main director (38 mm box) | 0 % | 1 % | 4 % |
| A turret jammed | 2 % | 4 % | 4 % |
| Machinery, flooding, speed | ≈ 0 | ≈ 0 | ≈ 0 |

The 75-hit column is Hiei's experience (~85 mixed hits, mostly ≤ 8″), with the steering hit left out.

---

## 7. Proposed implementation

### 7.1 Data (extends `damage-model-research.md` §13)

```
Shell {
  calibre, mass, mv, i_form
  kind: AP | SAP | HE
  filler_kg, filler_type → w_tnt
  fuze: base(delay_s) | nose(instant) | time | vt
  quality_row: rn1916 | km1916 | rn1918 | ww2 | ijn_t91        # §3.3 table
  diving: bool                                                 # IJN T91/T88
}

Zone (per target, from the generator's layout) {
  side_area, top_area, h_band
  path_side[], path_top[]        # (t_mm, kind, gap_m), outer → inner
  incline_deg, depth_m
  heavy_mass_p                   # machinery / slope / barbette in the path
  waterline_share, flood_cap_t, comp_len_m
  crew_density, fire_load, ammo_exposure
  systems[]: (id, area_m2, box_mm, below_wl)   # links to the dependency graph (§9 of damage-model-research)
}
```

The generator already has everything needed for this:
- zone areas and plate thicknesses: `geometry.py` and the armour block;
- systems: `layout.py` placements;
- compartment lengths: bulkhead positions.

### 7.2 Resolution step (per shell)

```
# inputs from the ballistics / fire-control model (separate research):
#   impact point on the target, striking velocity v, fall angle, target angle,
#   or, for a miss, the distance short / beside the hull
on miss_close(shell, distance):
     short by < 30 m (80 m for diving shells): underwater_roll()   # §3.8
     within R_frag of the hull: near_miss_splinters()               # §8 open
on hit(shell):
  face = side | top     by danger-space share (§3.1)
  zone = by projected area on that face
  ob   = obliquity(fall, incline, target angle)
  cap  = pen(shell, v, ob, face)
  if HE: burst at first plate (inside if t ≤ 0.2 cal, else outside)
  else:
     if plates > cap: RIC (if ob > 45°) or SHT  → non-pen effects (§3.7)
     elif no plate ≥ arm(ob) and not heavy_mass: OVR → line-of-flight effects
     else: roll quality row → PEN | PIB | LO | DUD | BRK
           PEN: d = delay·v_res·U(.7,1.1); if d > depth and no heavy mass: burst beyond (OVR)
  effects(burst position):
     systems within R_wreck (protected boxes only if fragments beat the box)
     flooding: waterline hole r_hole → inflow √head (damage-model-research §8.4); bulkhead breach if R_wreck > 0.4·comp_len
     fire roll (§3.9); ready-ammo roll; propellant in turret / handling room → 07 magazine model
     casualties = crew density × (0.8·πR_wreck² + 0.2·π(R_blast² − R_wreck²))
     electrical trip roll (1–5 min) for heavy hits; jam / stun rolls for turret and CT hits
```

**Cost.** One hit is a few table lookups plus about five random draws. `(v, fall)` comes from the ballistics model; the reference code's point-mass integrator is only there to produce plausible inputs.

### 7.3 Events for the damage-report UI

RTW's lesson is to make cause and effect readable. Each hit should log one line in the form *shell → zone → outcome → consequence*, for example:

- "16-inch AP · forward superstructure · **passed through, no burst** · 5-inch director cables cut"
- "46 cm HE · hull side, machinery · **burst inside** · No. 1 fireroom wrecked, bulkhead to engine room breached, 650 t flooding"
- "14-inch AP · Turret B face · **defeated** · turret jammed in train (repair 20 min)"

The outcome class *is* the explanation. Players learn very quickly that AP passes through destroyers.

### 7.4 Tuning anchors (sanity tests the model should reproduce)

1. **Johnston:** 3 heavy AP hits on the machinery zone → 2 of 3 burst, speed ≤ 60 %, slow flooding. Most heavy AP hits elsewhere pass through.
2. **Gambier Bay vs Kalinin Bay:** ~15 mixed hits on a CVE. Survival depends on whether a waterline machinery hit occurs (about 50/50).
3. **South Dakota:** 26 hits, mostly 8″ IJN AP → more than half pass through. All search radar lost in more than 50 % of runs. Flooding < 100 t, list < 1°. Belt never penetrated.
4. **Hiei:** ~85 medium hits → fire control lost, many fires. Steering lost only if a waterline hit falls in the stern zone (~10–20 % of runs). Never sunk by gunfire.
5. **San Francisco:** 45 hits including 14″ HE → ≤ 500 t water, 15–25 fires, bridge crew killed in most runs.
6. **Kirishima:** 20 × 16″ at ~8 km → ≥ 2 turrets out, steering lost likely, ≥ 2,000 t water. Capsize only with 1914-era subdivision plus counter-flooding.
7. **Bismarck 27 May:** ~80 heavy and ~300 medium hits at 3–15 km → all turrets out in 30–60 min. Citadel penetrations a handful. Still afloat after an hour.
8. **Jutland shell quality:** British 1916 APC vs > 9″ plate → effective penetration plus burst about 1 in 15–20.
9. **Yalu / Oryol:** QF HE against an ironclad belt → 0 penetrations in 200 hits, many fires.
10. **Destroyer gunfire endurance:** 5″ ×10 → mostly crippled, rarely lost. ×40 → usually lost.

---

## 8. Open questions and gaps

- **Near-miss splinters.** HE and nose-fuzed shells burst on water impact and riddle destroyer topsides with splinters (Heermann's damage at Samar was "only fragments" per NHHC). This needs a near-miss model: fragment reach from §3.6 against 6–10 mm plating. A 46 cm HE shell probably damages a destroyer from 10–20 m away **[INFERRED]**. If the fire-control model produces many close misses on destroyers, this could matter as much as direct hits for the "18-inch broadside into a destroyer" case. The fire-control model supplies the miss distances; this model would supply the splinter effect.
- **Japanese fuze delay.** The 0.4 s figure is unverified (05 §A1). The behaviour is clear (over-penetration); the number is not.
- **South Dakota hits 13–26, Graf Spee's hit count, Scharnhorst's North Cape heavy-hit total.** These are in the WDR PDF, Campbell and Garzke & Dulin, not online.
- **Baden 1921 hit-by-hit table** (Campbell, Raven & Roberts). Only summaries were found.
- **Fragment velocity numbers.** Okun's text reached me through a summariser; the distance/thickness table is **[UNCERTAIN]** in detail but plausible in shape.
- **Leak rates from displaced belt plates** have no quantitative source. The 5–50 t/h used here is a guess.
- **Funnel and uptake hits:** draught and speed loss are not quantified anywhere I found. Use ~10–15 % chance of a boiler/auxiliary casualty plus ~30 % chance of smoke or draught loss per medium hit [INFERRED].
- **Ricochet-by-angle probabilities.** The 45–65° linear ramp is a game value; no published table exists.
- **Burst-radius constants.** The cube-root rule is fitted to only 2–3 WDR holes. Calibrate further against WDR photographs if the art pipeline needs hole sizes.

---

## Sources

**Shell data (navweaps)**
- [Japan 40 cm/45 Type 94 (= 46 cm Yamato)](https://navweaps.com/Weapons/WNJAP_18-45_t94.php)
- [British 18″/40 Mk I](https://www.navweaps.com/Weapons/WNBR_18-40_mk1.php)
- [British 15″/42 Mk I](https://www.navweaps.com/Weapons/WNBR_15-42_mk1.php)
- [German 38 cm SK C/34](https://www.navweaps.com/Weapons/WNGER_15-52_skc34.php)
- [German 28 cm SK C/34](https://www.navweaps.com/Weapons/WNGER_11-545_skc34.php)
- [USN 16″/50 Mk 7](https://navweaps.com/Weapons/WNUS_16-50_mk7.php)
- [USN 14″/45](https://www.navweaps.com/Weapons/WNUS_14-45_mk10.php)
- [USN 8″/55 Mk 12–15](https://navweaps.com/Weapons/WNUS_8-55_mk12-15.php)
- [USN 6″/47 Mk 16](https://navweaps.com/Weapons/WNUS_6-47_mk16.php)
- [USN 5″/38 Mk 12](https://navweaps.com/Weapons/WNUS_5-38_mk12.php)
- [IJN 12.7 cm/50 3rd Year Type](https://www.navweaps.com/Weapons/WNJAP_5-50_3ns.php)
- [IJN 14″/45 41st Year Type](https://navweaps.com/Weapons/WNJAP_14-45_t41.php)
- [IJN 8″/50 3rd Year Type](https://navweaps.com/Weapons/WNJAP_8-50_3ns.php)
- [Japanese 12″/40 EOC](https://navweaps.com/Weapons/WNJAP_12-40_EOC.php)

**Terminal ballistics (Okun and others)**
- [Misc. armour formulae](https://navweaps.com/index_nathan/Miscarmr.php)
- [Base fuze plate-thickness minimums](https://navweaps.com/index_nathan/baseFuzePlateThicknessMinimums.php)
- [British fuzes after Jutland](https://navweaps.com/index_nathan/British_Fuzes_after_Jutland.php)
- [HMS Hood 1919 armour tests (PDF)](http://www.navweaps.com/index_nathan/HOOD%201919%20Armor%20Tests.pdf)
- [FACEHARD change info](https://www.navweaps.com/index_nathan/facehard69ChangeInfo.php)
- [tech-020 How shell fuzes work](https://www.navweaps.com/index_tech/tech-020.php)
- [tech-041 Underwater hits](https://navweaps.com/index_tech/tech-041.php)
- [tech-085 Decapping](http://www.navweaps.com/index_tech/tech-085.php)
- [tech-092 Kirishima's hit on South Dakota](https://www.navweaps.com/index_tech/tech-092.php)
- [tech-016 Destruction of the Bismarck](https://www.navweaps.com/index_tech/tech-016.php)
- [INRO: Bismarck's final battle](https://www.navweaps.com/index_inro/INRO_Bismarck.php)
- [Naval Gazing: Shells at Jutland](https://navalgazing.net/Shells-at-Jutland)
- [Naval Gazing: Shells Part 2](https://www.navalgazing.net/Shells-Part-2)
- [Naval Gazing: Shells Part 3](https://www.navalgazing.net/Shells-Part-3)
- [Naval Gazing: Armor Part 2](https://navalgazing.net/Armor-Part-2)
- [Naval Gazing: Fuzes Part 3](https://www.navalgazing.net/Fuzes-Part-3)
- [USNI 1909: Projectiles for naval guns](https://www.usni.org/magazines/proceedings/1909/june/projectiles-naval-guns)
- [USNI 1925: Lessons of Jutland for turret armour](https://www.usni.org/magazines/proceedings/1925/april/lessons-jutland-affecting-design-turret-armor)

**War damage reports and analyses**
- [WDR 57 South Dakota](https://history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-south-dakota-bb57-war-damage-report-no57.html) ([PDF](https://www.ibiblio.org/hyperwar/USN/rep/WDR/U.S.S.%20SOUTH%20DAKOTA%20(BB-57),%20GUNFIRE%20DAMAGE%20-%20Battle%20of%20Guadalcanal,%20November%2014-15,%201942.pdf))
- [WDR 51 Destroyers: gunfire, bomb, kamikaze](https://history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-gunfire-bomb-kamikaze-damage.html)
- [WDR 26 San Francisco](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-sanfrancisco-ca38-war-damage-report-no26.html)
- [WDR 24 Boise](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-boise-cl47-war-damage-report-no-24.html) ([hyperwar](https://ibiblio.org/hyperwar/USN/WarDamageReports/WarDamageReportCL47/WarDamageReportCL47.html))
- [WDR Sterett (PDF)](https://www.ibiblio.org/hyperwar/USN/rep/WDR/U.S.S.%20STERETT%20(DD-407),%20GUNFIRE%20DAMAGE%20-%20Battle%20of%20Guadalcanal,%20November%2013,%201942.pdf)
- [Lundgren: South Dakota damage analysis](https://navweaps.com/index_lundgren/South_Dakota_Damage_Analysis.php)
- [Lundgren: Kirishima damage analysis](https://www.navweaps.com/index_lundgren/kirishimaDamageAnalysis.php)
- [USNI 1991: Who sank Bismarck?](https://www.usni.org/magazines/proceedings/1991/june/who-sank-bismarck)
- [USSBS interrogation Nav No. 46 (Hiei)](https://ibiblio.org/hyperwar/AAF/USSBS/IJO/IJO-46.html)
- [NHHC: Battle off Samar](https://history.navy.mil/browse-by-topic/wars-conflicts-and-operations/world-war-ii/1944/samar.html)
- DANFS: [Johnston](https://ibiblio.org/hyperwar/USN/ships/dafs/DD/dd557.html) · [Samuel B. Roberts](https://ibiblio.org/hyperwar/USN/ships/dafs/DE/de413.html) · [Kalinin Bay](https://ibiblio.org/hyperwar/USN/ships/dafs/CVE/cve68.html) · [Dennis](https://www.history.navy.mil/research/histories/ship-histories/danfs/d/dennis.html)
- combinedfleet TROMs: [Hiei](http://www.combinedfleet.com/hiei.htm) · [Kumano](http://www.combinedfleet.com/kumano_t.htm) · [Chōkai](http://www.combinedfleet.com/chokai_t.htm) · [Chikuma](http://www.combinedfleet.com/chikuma_t.htm) · [Haguro](http://www.combinedfleet.com/haguro_t.htm)
- [kbismarck: Denmark Strait](https://kbismarck.com/denmark-strait-battle.html) · [Cameron 2001 Bismarck dive](https://3dhistory.de/html_e/hauptframe/jc/bismarck_dive1_3.htm)
- [Chuck Hill: What does it take to sink a ship](https://chuckhillscgblog.net/2011/03/14/what-does-it-take-to-sink-a-ship/) (secondary)

**Wikipedia ship and battle articles** (used for the case tables)
- Samar: [Johnston](https://en.wikipedia.org/wiki/USS_Johnston_(DD-557)) · [Hoel](https://en.wikipedia.org/wiki/USS_Hoel_(DD-533)) · [Samuel B. Roberts](https://en.wikipedia.org/wiki/USS_Samuel_B._Roberts_(DE-413)) · [Gambier Bay](https://en.wikipedia.org/wiki/USS_Gambier_Bay) · [Battle off Samar](https://en.wikipedia.org/wiki/Battle_off_Samar)
- Guadalcanal: [Atlanta](https://en.wikipedia.org/wiki/USS_Atlanta_(CL-51)) · [Monssen](https://en.wikipedia.org/wiki/USS_Monssen_(DD-436)) · [Laffey](https://en.wikipedia.org/wiki/USS_Laffey_(DD-459)) · [Hiei](https://en.wikipedia.org/wiki/Japanese_battleship_Hiei) · [South Dakota](https://en.wikipedia.org/wiki/USS_South_Dakota_(BB-57)) · [Naval Battle of Guadalcanal](https://en.wikipedia.org/wiki/Naval_Battle_of_Guadalcanal)
- Arctic and Norway: [Barents Sea](https://en.wikipedia.org/wiki/Battle_of_the_Barents_Sea) · [Achates](https://en.wikipedia.org/wiki/HMS_Achates_(H12)) · [Onslow](https://en.wikipedia.org/wiki/HMS_Onslow_(G17)) · [Z16 Friedrich Eckoldt](https://en.wikipedia.org/wiki/German_destroyer_Z16_Friedrich_Eckoldt) · [North Cape](https://en.wikipedia.org/wiki/Battle_of_the_North_Cape) · [Scharnhorst](https://en.wikipedia.org/wiki/German_battleship_Scharnhorst) · [Gneisenau](https://en.wikipedia.org/wiki/German_battleship_Gneisenau) · [Admiral Hipper](https://en.wikipedia.org/wiki/German_cruiser_Admiral_Hipper) · [Acasta](https://en.wikipedia.org/wiki/HMS_Acasta_(H09))
- Atlantic: [Denmark Strait](https://en.wikipedia.org/wiki/Battle_of_the_Denmark_Strait) · [Bismarck](https://en.wikipedia.org/wiki/German_battleship_Bismarck) · [Last battle of Bismarck](https://en.wikipedia.org/wiki/Last_battle_of_the_battleship_Bismarck) · [Prince of Wales](https://en.wikipedia.org/wiki/HMS_Prince_of_Wales_(53)) · [Hood](https://en.wikipedia.org/wiki/HMS_Hood)
- French navy 1940–42: [Dunkerque](https://en.wikipedia.org/wiki/French_battleship_Dunkerque) · [Bretagne](https://en.wikipedia.org/wiki/French_battleship_Bretagne) · [Jean Bart](https://en.wikipedia.org/wiki/French_battleship_Jean_Bart_(1940)) · [Richelieu](https://en.wikipedia.org/wiki/French_battleship_Richelieu)
- River Plate, Java Sea, Sydney, Matapan, Calabria: [River Plate](https://en.wikipedia.org/wiki/Battle_of_the_River_Plate) · [Exeter](https://en.wikipedia.org/wiki/HMS_Exeter_(68)) · [Graf Spee](https://en.wikipedia.org/wiki/German_cruiser_Admiral_Graf_Spee) · [Sydney vs Kormoran](https://en.wikipedia.org/wiki/Battle_between_HMAS_Sydney_and_German_auxiliary_cruiser_Kormoran) · [Matapan](https://en.wikipedia.org/wiki/Battle_of_Cape_Matapan) · [Calabria](https://en.wikipedia.org/wiki/Battle_of_Calabria)
- WWI: [Seydlitz](https://en.wikipedia.org/wiki/SMS_Seydlitz) · [Lützow](https://en.wikipedia.org/wiki/SMS_L%C3%BCtzow) · [Derfflinger](https://en.wikipedia.org/wiki/SMS_Derfflinger) · [Von der Tann](https://en.wikipedia.org/wiki/SMS_Von_der_Tann) · [Lion](https://en.wikipedia.org/wiki/HMS_Lion_(1910)) · [Tiger](https://en.wikipedia.org/wiki/HMS_Tiger_(1913)) · [Warspite](https://en.wikipedia.org/wiki/HMS_Warspite_(03)) · [Malaya](https://en.wikipedia.org/wiki/HMS_Malaya) · [Damage at Jutland](https://en.wikipedia.org/wiki/Damage_to_major_ships_at_the_Battle_of_Jutland) · [Baden](https://en.wikipedia.org/wiki/SMS_Baden_(1915)) · [USS Washington (BB-47)](https://en.wikipedia.org/wiki/USS_Washington_(BB-47))
- 1894–1905: [Yalu 1894](https://en.wikipedia.org/wiki/Battle_of_the_Yalu_River_(1894)) · [Zhenyuan](https://en.wikipedia.org/wiki/Chinese_ironclad_Zhenyuan) · [Yellow Sea](https://en.wikipedia.org/wiki/Battle_of_the_Yellow_Sea) · [Oryol](https://en.wikipedia.org/wiki/Russian_battleship_Oryol) · [Oslyabya](https://en.wikipedia.org/wiki/Russian_battleship_Oslyabya) · [Knyaz Suvorov](https://en.wikipedia.org/wiki/Russian_battleship_Knyaz_Suvorov) · [Mikasa](https://en.wikipedia.org/wiki/Japanese_battleship_Mikasa)

**Project docs:** `05_mechanics_and_games.md` (penetration, fuze arming, decapping), `02_components.md`, `07_magazine_explosions.md` (what happens after propellant ignites), `damage-model-research.md` §8–§13.