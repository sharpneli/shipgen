# 05 — Damage Mechanics: Real-World Physics & Statistics, and Prior Art in Games

Research base for the damage model of a top-down 2D naval game (1890 pre-dreadnoughts to WWII fast battleships, carriers, destroyers, MTBs) with a parametric ship generator. This file covers breadth, concrete numbers and prior art. It does not decide the design. Gamification comes later.

**Conventions**
- Sources are cited inline.
- **[UNVERIFIED]** marks figures I recall from general naval-architecture or historical knowledge but did not confirm against a source in this session.
- **[CONFLICTING]** marks figures where the sources disagree.
- Imperial units are kept where the sources use them: inches, lb, ft/s.

---

## Part A — How ships actually took damage and died

### A1. Shell types

| Type | Burster (% of shell weight) | Purpose | Notes |
|---|---|---|---|
| AP / APC (capped) | 1.5–5% (USN 16" Mk 8: 1.5% of 2,700 lb) | Defeat belt, deck and turret armour, then burst inside | Base fuze with delay. The cap raises the "biting" angle and spreads the shock of impact on hardened faces. |
| SAP / CPC ("common pointed capped") | ~2.5–4% (the "Common" class) | Moderately armoured targets such as cruisers and casemates | Penetrates roughly ⅓ calibre of armour (interwar "Common" definition). |
| HE / HC | 6–8% | Unarmoured targets, superstructure, destroyers, shore | Nose fuze, instantaneous or short delay. Starts fires, wrecks topsides. |

Source for all of the above: NavWeaps "Definitions and Information about Naval Guns" — https://www.navweaps.com/Weapons/Gun_Data_p2.php

**Fuzes**
- Base fuzes (AP) arm by set-back and spin. They fire by inertia on impact.
- The mechanical function alone takes about **0.003 s**. Delay elements burn for **0.006–0.03 s** (https://www.navweaps.com/index_tech/tech-020.php).

Typical AP delays by nation:

| Nation | Fuze delay | Source |
|---|---|---|
| UK (WWI–WWII), No. 16D | 0.025 s nominal (some sources say 0.024). The British kept this delay through WWII. | https://www.navweaps.com/index_nathan/British_Fuzes_after_Jutland.php |
| USN and Germany (WWII) | 0.033–0.035 s average | same |
| Germany (WWII) | Bd.Z.38 = 0.035 s; Bd.Z.38 KV = 0.015 s; range 0.015–0.035 s | https://www.navweaps.com/index_nathan/germanWWIIFuzes.php |
| Japan (Type 91) | Unusually long delay, designed for underwater "diving" hits. The commonly cited 0.4 s figure is **[UNVERIFIED]**. | https://navweaps.com/index_tech/tech-041.php |

- Japanese Type 91 shells had a break-away windscreen and a flat "cap head". After impact this leaves a flat face of about 50% of the shell's cross-section, which lets the shell travel nose-first underwater. One confirmed example is the hit on USS *Boise*'s forward magazine (https://navweaps.com/index_tech/tech-041.php).
- In RTW3, "diving shells" turn some long-range near misses into below-belt hull hits, at the cost of more pass-throughs and duds (RTW3 manual, https://ftp.matrixgames.com/pub/RuletheWaves3/Rule%20the%20Waves%203%20Manual%20EBOOK.pdf).

**Fuze arming threshold.** An AP shell needs to hit enough plate to start its fuze. Okun's formula for US WWII base fuzes:

```
Tfuze = Tfzmin * D * { (1 + cos(2*Ob)) / 2 + 0.4537 * sin(Ob)^5.7019 }
  Tfzmin = 0.07 (single-plate designs) or 0.05 (two-plate designs)
  D      = calibre (in)
  Ob     = obliquity (deg), capped at 61°
```

Source: https://www.navweaps.com/index_nathan/Miscarmr.php

- Rule of thumb: the plate must be about **5–7% of calibre** or the AP shell passes through without arming. This is an **overpenetration**.
- WoWS uses the same idea with 1/6 calibre as the arming threshold. Its example is the Iowa 16" needing about 38 mm (https://wiki.worldofwarships.com/Ship:Armor_Penetration).

**Duds and failures.** Failure modes include:
- shatter on the face-hardened layer
- cap torn off at obliquity
- filler going off on impact (British lyddite in WWI)
- fuze failure (German C/11 fuzes giving no delay or a very long delay)

At Jutland, of 17 British shells that struck armour thicker than 9", **only one penetrated and burst inside**. Against 6–9" plates, more than half either failed to hole the plate or burst with no effect (Naval Gazing, https://www.navalgazing.net/Shells-at-Jutland). Post-war tests showed a British 15" AP shell **breaking up on a 6" plate at 20° obliquity**. The fix was the "Greenboy" APC (harder caps, stronger bodies, 60/40 lyddite/dinitrophenol filler), in service from April 1918 (same source).

### A2. Armour, obliquity, decapping

- **Armour families:**
  - Harvey (c. 1890s), then Krupp cemented (KC, c. 1898+), then WWI–WWII face-hardened (FH) plate.
  - FH plate is for belts and turret faces. Homogeneous plate (STS, Class B, Wotan) is for decks and thinner plates.
  - FH plate breaks up shells. Homogeneous plate resists by ductility.
  - Penetration formulas for homogeneous plate do not apply to FH plate, especially when the cemented layer is thin (under 15% of plate thickness) (http://www.navweaps.com/index_nathan/apShellVsArmor.php).
- **Caps:**
  - Uncapped AP shatters on FH plate.
  - In tests at 21°, capped shells "went through everything". Caps stay effective up to about 20° obliquity, where uncapped shells fail (same source).
- **Decapping:** a thin outer plate strips the cap before the main belt.
  - Plate needed: about 0.075–0.1 calibre at 30–45° obliquity, and 0.105–0.12 calibre at normal impact.
  - Krupp-type "Type 2" hard caps need roughly double that.
  - The gap behind the decapping plate should be 1–3 calibres.
  - The *Vittorio Veneto* class used a deliberately spaced decapping belt (https://www.navweaps.com/index_tech/tech-085.php).
- **Obliquity:** above the "biting angle" the shell nose is pushed sideways and the energy needed to penetrate rises sharply (https://www.navweaps.com/index_nathan/Hstfrmla.php).
- **Ricochet:** game thresholds from WoWS: auto-ricochet at 60°+, chance of ricochet at 45–60°, no ricochet below 45°. "Normalization" turns the shell 6–10° toward the plate normal, depending on calibre. Real behaviour is messier and depends on calibre and shell. The WoWS numbers are game values, not physics.
- **Edge effects:** a hit within 1.5 calibres of an unsupported plate edge loses up to **15%** of plate quality (https://www.navweaps.com/index_nathan/Miscarmr.php). This is a good justification for "joint weakness" randomness.

### A3. Penetration formulas usable in a game

**De Marre** (French, ~1890; homogeneous / nickel steel). This is the classic one:

```
T/D = 0.00005021 * D^0.07144 * [ (W/D^3) * (V/C)^2 * cos^3(Ob) ]^0.71429
  T  = plate thickness (in)
  D  = calibre (in)
  W  = shell weight (lb)
  V  = striking velocity (ft/s)
  C  = De Marre quality coefficient (~1.0–1.25)
  Ob = obliquity (deg)
```

Source: https://www.navweaps.com/index_nathan/Hstfrmla.php

The common game shortcut is the proportional form:

```
T ∝ W^0.5 * V^1.43 / D^0.75 * (cos Ob)^?     (exponents from 0.71429 = 1/1.4)
```

- It is valid from about 0.1 to 0.75 calibre thickness. Above 0.75 calibre the exponent climbs toward 1.0 (same source).
- War Thunder uses a De Marre variant: https://wiki.warthunder.com/jacob_de_marre

**Krupp "all-purpose"** (1930s):

```
T/D = 0.30386 * D^0.25 * [ (W/D^3) * (V/C)^2 ]^0.625      (C ≈ 525–804; normal impact only)
```

**Thompson F-formula** (USN 1930), with a convenient ballistic-limit form:

```
T/D = 1728.04 * (W/D^3) * [ V * cos(Ob) / F ]^2
VL  = 0.024056 * D * (T/W)^0.5 * F / cos(Ob)
```

**Garzke & Dulin fit** (APC vs US Class B homogeneous plate, 0° obliquity, calibres 11.1"–18.1"):

```
T(in) = 0.0004689 * W^0.55 * D^-0.65 * V^1.1
```

Source: https://www.navweaps.com/index_tech/tech-109.php

**Okun's caution:** single-term formulas are accurate "only when the plate always fails in exactly the same way no matter how thick it is". Against FH plate, the weight term exponent is only about 0.2 against about 1.21 for velocity. His full model is the *FACEHARD* program (v6.8 is within 1–10% of test No-Break-Limits for capped shells) (http://www.navweaps.com/index_nathan/apShellVsArmor.php). Okun also publishes ready-made penetration tables per gun: https://navweaps.com/index_nathan/Penetration_index.php

**Spaced and laminated plates** (Okun):

```
Te_i     = Q_i * T_i                                  (quality-weighted thickness)
Tsum     = Σ Te_i
Tspaced  = ( Σ Te_i^1.4 )^0.71429
Tlam     = (Tsum + Tspaced) / 2      (plates in contact)
```

Source: https://www.navweaps.com/index_nathan/Miscarmr.php

The 1.4 / 0.71429 exponent pair falls straight out of De Marre. Spaced plates are worth less than one solid plate of the same total thickness unless one of them decaps the shell.

**HE nose-fuzed "hole-punching" thickness** (no delay, STS plate):

```
T_he = 2.576e-20 * D * V^5.6084 * cos(2*(Ob-45°)) + 0.156*D
```

Rule of thumb: HE defeats only about **0.16 calibre** of plate at modest velocity (same source). WoWS uses 1/6 calibre by default and 1/4 for British BBs and German ships, which matches.

**Game simplification candidate.** Precompute per gun a curve `pen_belt(range)` and `pen_deck(range)` from De Marre. Fall angle comes from a simple ballistic table. Then resolve with:

```
eff_belt = t_belt / cos(Ob_horizontal_component)
eff_deck = t_deck / sin(fall_angle)
penetrates if pen_x(range) * rand(0.9..1.1) > eff_x * quality
```

### A4. Immune zone; plunging vs flat fire

- The **zone of immunity** is the band of ranges between "belt penetrated" (too close) and "deck penetrated by plunging fire" (too far) (https://en.wikipedia.org/wiki/Zone_of_immunity).
- At long range the fall angle steepens, so the belt's effective thickness rises while the deck's falls.
- Scharnhorst's critical hit was a **long-range shell from *Duke of York* that pierced the lower armour deck and wrecked No. 1 boiler room**, dropping her from 30+ knots to about 10 knots (https://en.wikipedia.org/wiki/Battle_of_the_North_Cape).
- Hood's thin, spread-out decks were meant to detonate shells on the top deck. Delay-fuzed shells defeated that idea (https://en.wikipedia.org/wiki/HMS_Hood).
- RTW3 shows players their immune zone, but only against their *own* nation's guns at current tech (https://steamcommunity.com/app/2008100/discussions/0/4307201374342424414/).

### A5. Splinters and blast

- Splinters from near misses and superstructure hits do most of the "soft" damage:
  - severed cables
  - wrecked fire-control directors and radars
  - punctured uptakes and funnels
  - crew losses on exposed guns
- *South Dakota* (Guadalcanal, 14–15 Nov 1942), as summarised by Lundgren/Okun at https://www.navweaps.com/index_lundgren/South_Dakota_Damage_Analysis.php:
  - BuShips counted 26 hits: 1×14", 18×8", 6×6", 1×5". The re-analysis argues several of the "8-inch" hits were actually 14" Type 0 HE.
  - Hit 12 severed the Sky Control and Main Battery Director cables.
  - Hit 6 killed Secondary Director #1.
  - A hit through the 1.1" clipping room started an ammunition fire.
  - The ship was tactically neutralised (fire control, radar, power) without any threat of sinking. This is the textbook **"mission kill"**.
- RTW3 manual rule: "Splinter damage can occur to hull, machinery, funnel uptakes, main guns and secondary/tertiary guns from near misses or superstructure hits. **Armour of 2 inches and above will protect from splinter damage.**" This is a usable threshold.
- Blast in a confined space: penetrating HE or AP bursting inside wrecks bulkheads and doors over several compartments. This is what opens paths for progressive flooding (see the destroyer report below).
- The Japanese used multicore electrical cables, which were very hard to repair after splinter damage (http://pwencycl.kgbudge.com/D/a/Damage_Control.htm).

### A6. Torpedoes and mines (underwater explosions)

**Warhead sizes**

| Torpedo | Charge | Source |
|---|---|---|
| Japan Type 93 (24", surface) | ~490 kg Type 97 (≈7% stronger than TNT) | https://en.wikipedia.org/wiki/Type_93_torpedo |
| Japan Type 89 (sub) | ~660 lb Shimose (estimate from the *North Carolina* report) | below |
| US Mk 14 | Mod 0: 507 lb TNT; Mod 3: 643 lb Torpex | https://en.wikipedia.org/wiki/Mark_14_torpedo |
| UK 21" Mk VIII / IX | 750 lb TNT, later 805 lb Torpex | https://www.navweaps.com/Weapons/WTBR_WWII.php |
| UK 18" aerial Mk XII | 388 lb TNT (one 1942 memo says 440 lb); Mk XV: 545 lb Torpex | same |
| Germany G7a | ~280 kg Schießwolle 36 (250–300 kg by head type) | https://en.wikipedia.org/wiki/G7a_torpedo |

Rule of thumb for game tiers:
- About 150–250 kg for aerial and early torpedoes.
- About 250–350 kg for standard 21" torpedoes.
- About 490 kg for the Japanese 24" Long Lance.

**Contact vs non-contact**
- A **contact** hit on the side blows a hole and floods compartments. A torpedo defence system (TDS) absorbs this:
  - Layered TDS designs run void, liquid, liquid, liquid, void, then the holding bulkhead.
  - Depth matters most. The USN turbo-electric battleships had about 17' deep systems.
  - Coal bunkers about 60% full served as early TDS.
  - Source: https://www.navalgazing.net/Underwater-Protection-Part-1
- A **non-contact** detonation under the keel uses the gas bubble and shock to whip the hull and break its back. A smaller charge does more damage there. This was the design intent of the magnetic exploders: the US Mk 6, the German Pi G7a-MZ, and British Duplex.
  - All of these failed badly early in the war. The Mk 14 ran about 10 ft deep, the magnetic exploders fired early, and contact pistols jammed at high speed. Germany had its "Torpedokrise" (https://en.wikipedia.org/wiki/Mark_14_torpedo ; https://en.wikipedia.org/wiki/G7a_torpedo).
  - G7a contact pistols needed a minimum impact angle of about 16° to fire (G7a source). This gives a natural dud mechanic for glancing hits.
- Rule of thumb, secondary source: a warhead is about **4× more effective at the ship's side and about 10× more effective under the keel** (relative to what is unstated) (https://chuckhillscgblog.net/2011/03/14/what-does-it-take-to-sink-a-ship/). **[UNVERIFIED primary]**

**Hole size, worked example: *North Carolina*, 15 Sep 1942** (https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-north-carolina-bb55-war-damage-report-no-61.html)
- The hit landed about 2 ft below the belt.
- The hole was **32 ft long × 18 ft deep**, and plating was demolished between frames 43 and 52.
- **970 t** of water came in, plus **480 t** of counterflooding.
- She took a 5.5° list, which was corrected in about **6 minutes**.
- Two 16" magazines flooded.
- Shock effects were "remarkably slight".
- Afterwards she was limited to 18 kn sustained (24 kn bursts) to spare the shored bulkheads.

**Shock**

The standard metric is the shock factor:

```
HSF = sqrt(W) / R
KSF = HSF * (1 + sin θ) / 2
  W = TNT-equivalent charge (lb)
  R = slant range (ft)
  θ = depression angle from hull to charge
```

The structure of these formulas follows https://en.wikipedia.org/wiki/Shock_factor. The exact constants are **[UNVERIFIED]**: the page fetched in this session lists the variables but did not display the equations.

Damage thresholds (same source):

| Shock factor | Effect |
|---|---|
| < 0.1 | Insignificant |
| 0.1–0.15 | Electrical and lighting failures, pipe leaks |
| 0.15–0.2 | Pipe ruptures, machinery failures |
| ≥ 0.5 | "Usually considered lethal" |

- Shock-mounting of machinery and electronics became standard largely *after* WWII lessons.
- Even "near misses" from large bombs (*Warspite*'s blister was ripped open at Salerno) and torpedo whipping did serious damage.
- *O'Brien* (DD-415) was lost in transit from "extensive flexural vibration damage" after a torpedo hit (https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/summary-of-war-damage-17-oct-1941-to-7-dec-1942.html).

**Shaft-line hits.** *Prince of Wales* was hit by one torpedo at the port outer shaft. The shaft kept turning, wrecked the shaft passage, and let the sea run all the way into the engine room (https://www.navalgazing.net/Survivability-Flooding):
- about **2,400 t** of water came in
- an **11.5° list**
- speed fell to 15–16 kn
- the aft 5.25" turrets and auxiliary power were lost

In total she took 4 torpedoes and 1 bomb and sank about 95 min after the first torpedo (first hit ~11:44, capsized 13:20; corrected in synthesis) (https://en.wikipedia.org/wiki/Sinking_of_Prince_of_Wales_and_Repulse).

### A7. Bombs

- **General purpose (GP)** bombs are about 30–40% explosive by weight (https://en.wikipedia.org/wiki/General-purpose_bomb). They wreck topsides and flight decks and start fires, but rarely get through armour decks.
- **AP and SAP** bombs carry a much lower filler fraction:
  - German PC 1600: 20% filler, penetrates about 180 mm when dropped from 4–6 km at 60° (https://en.wikipedia.org/wiki/PC_1600).
  - Pearl Harbor's *Arizona* killer: a 41 cm AP shell converted into a **797 kg** bomb. It hit near turret II. The forward magazines blew about **7 s later**, killing 1,177 of 1,512 aboard (https://en.wikipedia.org/wiki/USS_Arizona_(BB-39)).
- **Heavy bombs on older ships:** *Marat* (1941) took two near-simultaneous **1,000 kg** bomb hits by the forward superstructure. The forward magazine detonated, she settled in about 11 m of water (326 killed), and her stern was later used as a floating battery firing 1,971 rounds of 12" (https://en.wikipedia.org/wiki/Soviet_battleship_Marat). This is a good "sunk but not gone" precedent.
- **Guided bombs** (Fritz X, 1,362 kg; weight **[UNVERIFIED]**):
  - *Roma*: the first hit went through the ship and exploded under the keel, starboard side. The second set off turret 2's magazines and blew the turret overboard. She capsized and broke in two, with 1,253–1,393 killed (https://en.wikipedia.org/wiki/Italian_battleship_Roma_(1940)).
  - *Warspite*: the bomb cut through all decks and blew a **20 ft hole in the bottom**. A near miss ripped the bulge. She was towed home, and one boiler room and X turret were never repaired (https://en.wikipedia.org/wiki/HMS_Warspite_(03)).
- **Near misses** are their own damage class: underwater shock, sprung plating, and splinters. Musashi's 24 Oct 1944 tally included **20 near misses** on top of the direct hits (https://www.combinedfleet.com/musashi.htm).
- **Kamikaze:** against US destroyers they were *less* lethal per damaged ship than conventional attack. 95 destroyers were damaged by kamikaze or Baka and 13 (13.7%) sank, against 28.9% for conventional bombs and torpedoes (https://ibiblio.org/hyperwar/NHC/WarDamageReports/WarDamageReportDDGunBombKamikaze/WarDamageReportDDGunBombKamikaze.html).

### A8. Flooding, buoyancy and stability

**Two ways to die**
1. **Founder:** loss of reserve buoyancy. The ship settles on an even-ish keel, or plunges by the bow or stern once the deck edge goes under.
2. **Capsize:** loss of transverse stability from off-centre flooding, free surface, or topweight.

Plunging dominated US destroyer losses: "a far greater number have gone down by plunging than by bodily sinkage or capsizing". Only *Preston* and *Johnston* were clear-cut stability capsizes (https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-torpedo-mine-damage.html).

**Longitudinal bulkheads are double-edged**
- They keep flooding to one side, which limits free surface but produces large lists.
- **All six British pre-dreadnoughts sunk by torpedo in WWI capsized**, partly for this reason.
- The USN avoided centreline bulkheads. Japan used them heavily: *Yamato* (attacked mostly from one side) sank after about 11 torpedoes, while *Musashi* (hit on both sides) took 19 (https://www.navalgazing.net/Survivability-Flooding).
- The Borodino class had a centreline bulkhead between engine and boiler rooms (https://en.wikipedia.org/wiki/Borodino-class_battleship).

**Free-surface effect.** The standard naval-architecture correction **[UNVERIFIED in-session]** is:

```
GG' (virtual rise of G) = (ρ_liquid * i_fs) / (ρ_sw * ∇)
  i_fs = second moment of area of the free surface about its own centreline ≈ l * b^3 / 12
  ∇    = displaced volume
GM_effective = GM_solid - Σ GG'
```

- Because of the b³ term, **wide, partly flooded compartments** are the killers, especially athwartships flats.
- The destroyer report singles out flooding "in way of the first platform aft" for its large free surface and many watertight doors (DD gunfire report above).
- Full wing tanks help. The 1945 Damage Control Handbook notes that the same flooding would have caused a 5–6° list had the wing tanks been empty (https://maritime.org/doc/dc/index.php).

**Progressive flooding routes.** These are what really sink ships:
- open or blown watertight doors and manholes
- ventilation trunks
- cable and pipe glands
- shaft tunnels
- damaged holding bulkheads

At Pearl Harbor, *California* and *Nevada* flooded through "open manhole covers" and failed holding bulkheads (1941–42 summary above). The Handbook's verdict on one loss: "entirely attributable to progressive flooding… flooding boundaries must be determined quickly and maintained". Its rule of thumb is useful for a game: **"If the ship does not sink within a very few minutes after damage, she probably will survive for several hours."**

**Floodable length and subdivision**
- Classic warship standards aimed at 2–4 adjacent compartments floodable.
- US destroyers "could typically survive flooding of up to four major compartments; exceeding that was generally fatal" (DD gunfire report).
- Commercial (SOLAS) permeabilities are about 0.95 for accommodation, about 0.85 for machinery and about 0.6 for cargo **[UNVERIFIED]**. These are good defaults for "how much of a compartment's volume fills".

**Counterflooding**
- It works when done quickly and in moderation: *North Carolina* used 480 t to correct 5.5° in 6 min.
- It is lethal when overdone. It adds weight, lowers freeboard and creates new free surface.
- *Kirishima*: the XO's counterflooding settled her deeper. The captain then flooded the port engine room to correct a starboard list, which triggered the capsize to port (https://www.navweaps.com/index_lundgren/kirishimaDamageAnalysis.php).
- *Yamato* was counterflooded from 15–18° down to 10°. Further correction would have meant flooding engine and boiler rooms (https://en.wikipedia.org/wiki/Japanese_battleship_Yamato).

**How much water big ships absorbed**

| Ship | Water / list | Outcome | Source |
|---|---|---|---|
| *Seydlitz* (Jutland) | ~**5,300 t**, freeboard down to 2.5 m, bow nearly awash | Survived. 21 heavy hits plus 1 torpedo (40×13 ft hole). | https://en.wikipedia.org/wiki/SMS_Seydlitz |
| *Prince of Wales* | ~2,400 t from 1 torpedo | Sank after 4 torpedoes | above |
| *North Carolina* | 970 t + 480 t counterflood | Survived | above |
| *Bismarck* | Settling by the stern, 20° port list by 10:20 | Sank 10:40 (scuttling debated) | https://en.wikipedia.org/wiki/Last_battle_of_the_battleship_Bismarck |
| *Musashi* | 19 torpedoes (10 port / 9 starboard) + 17 bombs + 20 near misses | Capsized ~19:36, after roughly 9 hours of attacks | combinedfleet |

Exact Musashi/Yamato water tonnages were not confirmed this session. Figures of **several thousand tonnes** (Musashi ~4,000 t taken in after the early hits, plus large counterflooding) appear in secondary sources **[UNVERIFIED]**.

Speed and flooding: in RTW3, damaged ships running at full speed suffer "bulkhead rupture" events that worsen flooding. The AI notoriously "suicides by flooding" (https://steamcommunity.com/app/2008100/discussions/0/4633736978453594994/). That is realistic: *North Carolina* held to 18 kn to protect her shored bulkheads. It is an easy, meaningful player decision.

**Topweight and overload: Tsushima**
- The Borodino class left about **1,700 t overweight**, with coal and stores stowed high.
- The belt sat mostly submerged: only about 4'6" of upper belt showed above water.
- They had a centreline bulkhead.
- **Three of four capsized**: *Suvorov*, *Aleksandr III* and *Borodino*, the last after magazine detonations. *Oryol* survived and surrendered (https://en.wikipedia.org/wiki/Borodino-class_battleship).

This is a strong argument for letting the parametric generator's stability (GM) and load state feed the damage model.

### A9. Fire

**Fuels**
- Bunker oil was relatively hard to ignite.
- **Cordite and propellant**: British cordite was much more sensitive than single-base powders. In WWII tests, a flash that would ignite 1 unit of US single-base propellant **set off 75 units of cordite**. Ageing WWI cordite also had impurities (https://www.navalgazing.net/There-Seems-To-Be-Something-Wrong-With-Our-Bloody-Ships-Today).
- **Avgas** was the carrier killer:
  - *Lexington*: vapour explosions after the action.
  - *Taihō*: a **single torpedo** cracked the avgas tanks. Vapour spread, and the damage-control officer ordered all ventilation to full and opened hatches, which spread the vapour through the ship. She exploded about **6.5 h later** and sank stern-first with ~1,650 of 2,150 lost (https://en.wikipedia.org/wiki/Japanese_aircraft_carrier_Taih%C5%8D).
  - US carrier losses: 5 carriers lost, **4 to fire and 1 (Yorktown) to flooding**. After *Lexington* the USN made firefighting "what rifle marksmanship was to the infantry". It introduced fog nozzles, CO₂ purging of fuel lines, portable pumps, and foam every 100 ft on carriers (http://pwencycl.kgbudge.com/D/a/Damage_Control.htm).
- Paint, linoleum, wooden decks, ready-use ammunition, life jackets (*South Dakota*'s clipping room), aircraft and stores were other fuels.

**Fire behaviour useful for games**
- About **50% of above-water-damaged US destroyers had fires**.
- "The deciding factor… is the promptness with which hose streams are brought to bear". Ships that put water on the fire **within ~1 minute** usually avoided ammunition explosions.
- Firemain ruptures were a frequent casualty. They disable firefighting, which is a nice coupled failure.
- Five of the 30 destroyer losses were magazine explosions: one from a direct hit, four from secondary fires.
- Source for this list: the DD gunfire report.

**Delay to full effect.** The Admiralty Trilogy delays shell- and bomb-fire and flooding effects by **3 tactical turns**, about **9–12 minutes** of historical fire development. Torpedo flooding is immediate (https://www.admiraltytrilogy.com/pdf/CW2008_Variable_Damage_Effects.pdf).

**Flash to magazine: the Jutland lesson**
- *Indefatigable*: 2 survivors of 1,019.
- *Queen Mary*: 9 of 1,275 survived.
- *Invincible*: 6 of 1,032 survived. Hit through Q turret amidships.
- Source: https://en.wikipedia.org/wiki/Battle_of_Jutland

Causes:
- crews stockpiling charges in handling rooms
- removing anti-flash doors
- unstable cordite

*Lion*'s Q turret was saved by flooding the magazine and keeping doors shut. Over 60 men died in the cordite fire anyway (Naval Gazing, above). *Seydlitz* at Dogger Bank (1915) had a barbette penetration whose fire burned out **both aft turrets** (159 killed). Flooding the magazines saved the ship, and Germany fixed its handling procedures before Jutland (https://en.wikipedia.org/wiki/SMS_Seydlitz).

*Hood* (1941) sank in about 3 minutes, with 3 survivors of 1,418. The inquiry found the aft magazines exploded, possibly via the 4" magazine (https://en.wikipedia.org/wiki/HMS_Hood).

### A10. Statistics

**US Navy destroyers, gunfire / bomb / kamikaze, 17 Oct 1941 – 15 Aug 1945** (https://ibiblio.org/hyperwar/NHC/WarDamageReports/WarDamageReportDDGunBombKamikaze/WarDamageReportDDGunBombKamikaze.html)
- 251 damage incidents in total.
- Above-water weapons: 162 survived and 30 sank (**84% survival**).
- Torpedo or mine: 21 survived and 27 sank (**44% survival**).

Causes of the 30 above-water losses:

| Cause | Losses | Detail |
|---|---|---|
| Flooding | 14 | Loss of buoyancy with severe list or trim |
| Structural failure | 6 | 5 jackknifed, 1 sagged by the stern. All 2,050–2,200 t ships. |
| Magazine explosion | 5 | 1 direct hit, 4 from fires |

Key observations from the same report:
- "More destroyer losses are attributable to progressive flooding than to fire."
- Machinery takes up **about ⅓ of length and ½ of hull volume**, so most big hits hit machinery.
- **Split-plant** arrangement saved ships. *Johnston* kept 20 kn for 2 h with the after turbines dead.

**US Navy destroyers, torpedo and mine, 1941–44 subset** (https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-torpedo-mine-damage.html)
- 31 torpedoed, 7 survived.
- 8 mined, 5 survived.
- **[CONFLICTING]** with the 21/27 figure above because the date ranges and denominators differ.

**What sank US ships**, citing the US Navy War Damage Report series via a secondary source (https://chuckhillscgblog.net/2011/03/14/what-does-it-take-to-sink-a-ship/). Of 92 losses:

| Cause | Losses | Share |
|---|---|---|
| Torpedoes alone | 38 | 41% |
| Suicide planes | 16 | 17% |
| Bombs alone | 12 | 13% |
| Gunfire alone | 11 | 12% |
| Combinations | remainder | |

- Of 23 major warships (BB, CV, CA/CL), **17 (74%) involved torpedoes**, and **every battleship and fleet carrier loss required torpedoes**.
- "No ship larger than 3,000 t full load was sunk by gunfire from weapons 5" or smaller."
- *Astoria* took 65+ hits of 8" and 5" and sank 9 h later.
- Rule of thumb: **about 1 lb of bombs or shells on target per ton of ship** for a confident sink.
- Treat these as secondary-source figures.

**Ship losses at large**
- Of 2,788 ships sunk by U-boats, 92% were torpedoed and 8% sunk by gunfire.
- British ground mines in north-west Europe: about 50,000 laid for 1,043 Axis ships sunk.
- Source: https://navyhistory.au/the-effectiveness-of-torpedoes-and-mines-in-world-war-ii/

**US vs Japanese damage control**
- The US had a single, trained DC officer with centralised responsibility.
- Japan split responsibility: the chief engineer below, a junior deck officer topside. Its cables were hard to repair (pwencycl, above).
- *Shinano*'s untrained crew could not stop progressive flooding after 4 torpedoes (Naval Gazing, above).
- Japan's DC did improve later: *Zuikaku* at the Philippine Sea was abandoned and then recovered (pwencycl).
- In-game, this maps naturally to a national or crew "DC quality" multiplier.

**Hits to sink, sketch.** Data points:
- *Bismarck*: ~400 hits from ~2,800 shells by four ships, plus torpedoes.
- *Kirishima*: ~20 major-calibre + 17 secondary hits per Japanese officers, against Lee's estimate of 8. Rudders jammed, then she capsized (Lundgren).
- *Lützow*: 10 hits, of which 2 forward below the waterline from *Invincible* proved fatal. Scuttled.
- *Seydlitz*: 21 heavy hits plus 1 torpedo, survived.
- *Warspite* at Jutland: 15 hits, steering jammed, survived.

Lesson: **hit count is a terrible predictor**. Location (waterline, forward ends, machinery, magazines) dominates.

### A11. Case studies (one to three lines each)

- **Tsushima (1905), Borodino class:** overloaded and top-heavy, belt submerged, centreline bulkhead. 3 of 4 capsized under gunfire.
- **Jutland (1916):**
  - *Indefatigable*, *Queen Mary* and *Invincible* were lost to turret or magazine flash, worsened by cordite practice.
  - *Lion* was saved by flooding her magazine.
  - *Lützow* was lost to bow flooding from 2 underwater hits and scuttled.
  - *Seydlitz* survived about 5,300 t of water.
  - *Warspite*'s jammed helm made her circle under fire.
- **Hood (1941):** aft magazine explosion from a *Bismarck* 15" hit. 3 survivors, gone in about 3 min.
- **Bismarck (1941):** an aerial torpedo jammed her rudders at 12° port, giving a "mobility kill" that doomed her. She was then gunned into a wreck (~400 hits), torpedoed, and possibly scuttled.
- **Prince of Wales (1941):** one torpedo at the shaft caused 2,400 t of flooding, an 11.5° list and power loss. Sank ~95 min after the first hit (corrected in synthesis). *Repulse* took 4 torpedoes.
- **Scharnhorst (1943):** one plunging 14" hit in a boiler room cut her from 30+ to 10 kn. Destroyer torpedoes finished her (several hits) and she capsized.
- **Kirishima (1942):** ~20 × 16" hits at close range. Compartment boundaries reached only to the middle deck, so flooding spread port to starboard. Both rudders were jammed. Misjudged counterflooding led to the capsize.
- **South Dakota (1942):** 26+ hits, mostly cruiser-calibre or HE. Fire control and radar were knocked out. No danger of sinking: the textbook mission kill.
- **Yamato (1945):** ≥11 torpedoes (mostly port) and 6 bombs. Counterflooding limits were reached, the forward magazine overheated, and she capsized as the magazine exploded. About 3,055 of 3,332 lost.
- **Musashi (1944):** 19 torpedoes, 17 bombs and 20 near misses. Slow progressive flooding. Capsized about 9 h after the attacks began.
- **Kongō (1944):** 2 (possibly 3) submarine torpedoes flooded two boiler rooms in a 32-year-old hull. Hours later her forward magazine exploded (https://en.wikipedia.org/wiki/Japanese_battleship_Kong%C5%8D).
- **Haruna (1945):** bombed by carrier aircraft at Kure and settled in shallow water **[UNVERIFIED details]**.
- **Roma (1943):** 2 Fritz X. One went through and exploded under the keel; the other set off the magazine. She capsized and broke in two.
- **Warspite (1943):** a Fritz X made a 20 ft hole in the bottom and flooded a boiler room. Towed. Permanent damage.
- **Marat (1941):** 2 × 1,000 kg bombs, forward magazine explosion, settled in shallow water. The aft part was used as a battery.
- **Arizona (1941):** a converted AP bomb penetrated the forward magazine. 1,177 killed.
- **Taihō (1944):** 1 torpedo, avgas vapour, bad ventilation orders. Explosion 6.5 h later.

---

## Part B — How games and simulations model warship damage

### B1. Rule the Waves 2/3 (NWS)

**Model**
- Hit location covers belt, deck, turret faces and tops, barbettes, conning tower, superstructure, extended (unarmoured or thin) ends, and an "upper belt".
- Hit location depends on range, which sets the fall angle: belt at short range, deck at long range.
- Ships die three ways: hull destruction (structural damage), loss of buoyancy (flooding), or magazine detonation (https://en.namu.wiki/w/Rule%20the%20Waves%203).

**Penetration**
- Armour in inches. Above **12"** armour gives "less than proportional" protection, and the cap is 20".
- Inclined belts beat vertical ones.
- AP, SAP and HE are tracked per shot. "Pass-through" hits go through without detonating, so players switch to SAP against cruisers (RTW3 manual; https://steamcommunity.com/app/2008100/discussions/0/4307201374342424414/).
- Penetrations are marked with `*` in the post-battle log.

**Splinters:** plates of 2" or more protect against splinters. Splinter hits can damage hull, machinery, uptakes and guns.

**Components:** fire control, radar, turrets (jammed or destroyed), rudder, electrical systems and engines can be damaged. Rudders and engines can be temporarily repaired in battle. Speed loss comes from engine, uptake or boiler damage and from flooding (https://www.magicgameworld.com/rule-the-waves-3-hits-damage-and-fires/).

**Flooding**
- Torpedo defence comes from TDS and bulges (bulges cost speed).
- Running fast while flooded triggers "bulkhead rupture" events. The AI often runs itself under (https://steamcommunity.com/app/2008100/discussions/0/4633736978453594994/).

**Flash fires**
- Penetrated turrets and barbettes can flash to the magazine. This is more frequent early on and for Britain (a national trait).
- A hidden learning mechanic lowers future flash risk after you suffer flash fires.
- The developer's intent is to represent "weird things like shells entering coal loading ports or a door left open" (https://steamcommunity.com/app/2008100/discussions/0/4633736485039802305/).

**Crew and DC:** training and a "damage control" doctrine speed up flooding reduction and firefighting. Technology improves DC over time.

**Strengths:** the community regards it as one of the most historically credible strategic-level models. It is driven by abstract stats rather than geometry and is very cheap to compute. Results look like real battles: mission kills, long fights, sudden magazine losses.

**Weaknesses:** the UI. Damage is buried in a text log with hundreds of lines. "There is a detailed damage model… but you have to search them." There is no damage report panel that ties symptoms to causes (https://steamcommunity.com/app/2008100/discussions/0/596274133248049126/).

### B2. Ultimate Admiral: Dreadnoughts (Game-Labs)

**Model**
- Ships are 3D models. Shots are ballistically simulated and hit actual geometry and armour zones.
- Armour zones: main belt, extended belt, upper belt, main deck, extended deck, inner belt and deck (citadel layers), turret (side, top), barbette, conning tower.
- Citadel styles 1–5 (e.g. turtleback) and "all-or-nothing" vs incremental schemes.
- **Penetration through layers:** the tooltip says at least 50% of remaining penetration is lost after an inner layer. The exact rule is undisclosed (https://steamcommunity.com/app/1069660/discussions/0/4701286722074967150/).
- Vanilla armour-layer multipliers are ×1.7, ×3.3 and ×8 for layers 1, 2 and 3. A popular mod changed them to ×2.2, ×3, ×4 (https://www.nexusmods.com/ultimateadmiraldreadnoughts/mods/7).

**Hit outcomes**

| Outcome | Damage |
|---|---|
| Ricochet | none |
| Partial penetration | ~33% damage (mod raised the threshold to 80% and reduced the damage) |
| Full penetration | 100% |
| Over-penetration | ~20% |
| Ammo detonation (critical) | large extra damage |

- Armour is **ablative**: repeated hits at one spot degrade the plate.

**Sections and compartments**
- There are **10 compartments**. Flooding sinks the ship at a threshold of floodable compartments; the mod set it to 75%. A separate fire-loss threshold exists (the mod raised it to 95%).
- There is a structure HP pool per section and for the whole ship.
- Modules (bulkhead tech, "reinforced compartments", TDS) scale resistance.

**Criticals and components**
- Conning tower (officers or command)
- Turrets (accuracy)
- Engines (speed)
- Rudder (manoeuvre)
- Fire control
- Flooding (speed)
- Fires

**Player criticism** (https://steamcommunity.com/app/1069660/discussions/0/3142927289448237964/ ; https://steamcommunity.com/app/1069660/discussions/0/3414304680789074947/ ; https://steamcommunity.com/app/1069660/discussions/0/4514381284536651597/):
- Partial penetrations dominate, leaving 80% of hits ineffective.
- Late-game modules make internal damage "almost impossible", so fights become HP-sponge grinds.
- Fires sink ships directly, where players argue fire should instead degrade crew and DC.
- Rapid-fire HE beats AP against armoured ships.
- Crew casualties were initially not modelled, giving 75% of crew left on wrecks.
- Damage control "fairly strong", with flooding fixed quickly.
- Formulas are kept hidden "to prevent min-maxing", which frustrates designers.
- **Lesson:** a geometry-accurate hit model can still feel wrong if the downstream damage-to-effect mapping is HP-centric.

### B3. Atlantic Fleet / War on the Sea / Cold Waters (Killerfish)

**Atlantic Fleet** (turn-based; https://killerfishgames.com/wp-content/uploads/2016/03/AtlanticFleetManual-v102.pdf)
- No hit points. **Real buoyancy physics.**
- "Ships are made up of individual compartments with subsystems assigned to them which take damage depending on where a shell hits."
- Water enters only through hits **at or below the waterline**. Plunging fire can penetrate and flood far-side compartments, so ships can capsize toward the *undamaged* side (https://steamcommunity.com/app/420440/discussions/0/412448792349813767/).
- Every sinking is unique and emergent. Trapped air can leave wrecks afloat, but they are counted as sunk.
- Subsystems:
  - Propulsion: hits aft (shafts), amidships (engines and boilers) and on funnels. It is temporary-disable only.
  - Rudder
  - **Pumps**: once destroyed they cannot be repaired and flooding greatly increases.
  - Fire control and radar
  - Flight deck
  - Turrets and torpedo mounts
  - Magazines: crew experience lowers explosion chance by 2–10%.
- Tactic the model teaches: **concentrate hits on one side or one end** to capsize or plunge a ship. Spreading damage lets the ship settle evenly.
- AP is advised for armour thicker than about 50% of calibre, and HE otherwise.
- Repairs: automatic per-turn subsystem repair. Permanent damage carries over between campaign battles.

**Cold Waters / War on the Sea** add a crew-allocation damage control screen (flooding and fire per compartment). The wiki pages were not fetchable this session.

**Strengths:** emergent, readable sinking that plays well in 2D (list and trim are visible), with the "aim at the waterline" decision. **Cost:** a per-compartment volume model plus rigid-body buoyancy.

### B4. World of Warships (Wargaming)

**Hit location** is a 3D raycast against a detailed armour mesh. Sections are bow, stern, casemate (midship above the citadel), superstructure and citadel. There are also module hitboxes: turrets, engine, steering, torpedo tubes, magazines.

**AP resolution**
- Ricochet: auto at 60°+, chance at 45–60°.
- **Overmatch:** if plate thickness is less than calibre/14.3, there is no ricochet.
- Normalization 6–10° by class.
- Fuze delay of 0.033 s (some 0.1 s), and an arming threshold of 1/6 calibre (https://wiki.worldofwarships.com/Ship:Armor_Penetration).

**HE**: penetrates if plate ≤ calibre × 1/6 (1/4 or 1/5 for some lines; +25% with IFHE).

**Damage multipliers (% of shell alpha)**

| Outcome | Damage |
|---|---|
| Over-pen | 10% |
| Penetration | 33% |
| Citadel | 100% |
| Destroyers hit by AP ≥280 mm | capped at 10% |

**Section HP and saturation**
- Each section has its own HP slice. After a first threshold, damage to that section halves. Once **saturated**, a section takes only **10%** of the shell's alpha.
- Citadel, fire and flooding bypass saturation (https://wiki.worldofwarships.com/Ship:Damage_System).
- **This stops "farm the bow forever" and pushes players to aim at different areas.**

**Fire** (https://wiki.worldofwarships.com/Ship:Fire)
- 0.3% of max HP per second per fire (CVs 1%).
- Duration 60 s for BBs and 30 s for cruisers and DDs.
- Maximum of **4 fire zones**: bow, stern, and two amidships.
- Fire chance:

```
FireChance = FRC * (1 - DCM1) * (1 - FP) * ((FCB * IFHE) + DE + Σ signals)
```

**Flooding** (https://wiki.worldofwarships.com/Ship:Flooding)
- At most 2 floods: one fore, one aft.
- About 30% speed penalty.
- Chance reduced by torpedo protection (×0.33 against the anti-torpedo belt, plus a per-ship TDS %).

**Repair**
- "Damage Control Party" instantly ends fires, floods and incapacitations, then has a cooldown.
- "Repair Party" heals about 14% of base HP over 28 s. 100% of fire damage can be recovered, but only small fractions of citadel damage. The exact fractions were **[UNVERIFIED this session]**; commonly cited as citadel 10%, penetration 50%, fire/flood 100%.

**Detonation:** random magazine explosion (instant kill) is a rare chance on hits to the magazine hitbox, reduced by a flag signal.

**Strengths:** very readable feedback (ribbons), and skill expression through angling and aiming.
**Weaknesses:** HP-pool abstraction. Burning as damage over time is unhistorical (battleships "burn down"). Overmatch is a step function.

**Performance:** only a handful of section HP pools plus module hitboxes. Fire and flooding are simple per-zone timers.

### B5. Battlestations: Midway / Pacific (Eidos)

- An arcade action-RTS.
- The **underwater hull HP** is the health bar.
- Separate damage types:
  - leaks: from torpedoes and belt penetrations, causing continuous loss
  - fires: from fuel tanks
  - **magazine** hits: big explosions, and the magazine can be "detonated multiple times"
  - engine hits: mobility
  - general hull damage: slow self-repair
- A radial repair menu lets the player prioritise pumps, fires, engines or guns (https://strategywiki.org/wiki/Battlestations:_Pacific/Ship_Tactics).
- **Pattern:** a few typed DoTs plus a player-prioritised repair queue. Very readable, low realism.

### B6. Silent Hunter III–V (Ubisoft)

- Ship damage uses **zones**: box hitboxes in `.zon` files with hitpoints, armour level and effect type (critical or explosive zones such as ammo and boilers).
- Each ship has **flotation HP** plus compartment-based flooding. A mod scene ("Better and Realistic Flotation") retunes these values (https://www.subsim.com/radioroom/showthread.php?t=164953).
- Torpedo hits under the keel and on the boilers are especially effective.
- Details **[UNVERIFIED this session]**: the threads were not readable. Known from modding docs: zones.cfg defines per-zone HP and armour, and ships sink when flotation is lost or a critical zone detonates.
- **Pattern:** "zones with HP + flotation pool + criticals". It is cheap and moddable.

### B7. From the Depths

- Voxel or block construction. **Every block has HP and an armour class.**
- Kinetic damage:

```
EffectiveDamage = Kinetic * min(AP / Armour, 1)
```

- A projectile keeps punching blocks until its damage is spent.
- Explosive damage falls off exponentially with distance and is reduced exponentially by armour.
- HEAT forms a jet. HESH forms spall. EMP travels along metal blocks to electronics.
- Stacked armour gets 20% of the backing armour's value (https://steamcommunity.com/sharedfiles/filedetails/?id=1722624225).
- The game has full buoyancy from blocks, so flooding is implicit through block loss.
- **Pattern:** a fully physical block grid. Maximum emergence, high computational cost, and needs player-built ships. This is relevant because the generator could emit a coarse block or compartment grid.

### B8. Highfleet

- Ships are module grids. Each module has HP: armour, fuel tanks, ammo depots, engines, bridge.
- **The ship dies when the bridge is destroyed**, either directly or by an ammo explosion chaining to it.
- Fuel tanks are fragile and start fires that spread module to module. Fire suppression systems race the fire.
- Fuel loss means engine loss, which means the ship falls and explodes (https://steamcommunity.com/sharedfiles/filedetails/?id=2580804883).
- **Pattern:** a "chain-reaction graph" of adjacent modules. Highly readable in 2D and directly applicable to a top-down view.

### B9. Command: Modern Operations (and Harpoon)

- **Damage points (DP).** Ship DP is mostly displacement-based. Weapon DP is **1 DP = 1 kg TNT** in Command, against 5 kg in the older Harpoon computer games.
- Explosive conversion: a Mk 84 has 429 kg Tritonal ≈ 643.5 DP (https://command.matrixgames.com/?page_id=2920).
- Command adds component damage (sensors, mounts, propulsion) and fire and flooding status with BDA readouts (https://command.matrixgames.com/?p=1787). Internals were not documented in the FAQ.
- **Admiralty Trilogy** (Harpoon, Command at Sea, Fear God & Dread Nought), per Cold Wars 2008 "Variable Damage Effects" (https://www.admiraltytrilogy.com/pdf/CW2008_Variable_Damage_Effects.pdf):
  - Weapon DP ∝ **(total energy)^(1/3)**: blast energy plus fragment kinetic energy plus residual missile kinetic energy.
  - The DP value is fixed. **Variability comes from fire and flooding criticals**, not from warhead randomness.
  - Hit-location detail is deliberately minimised for playability.
  - Fire and flooding critical severity is era-dependent:

| Era | Roll |
|---|---|
| Pre-dreadnought (≤1907) | 2d6+2 |
| WWI (1908–24) | 1d6+2 |
| WWII–modern (≥1925) | 1d6 |

  - Damage from non-penetrating hits and from fires caused by guns smaller than 76 mm is halved.
  - Shell and bomb fires and flooding take effect after **3 turns**. Torpedo flooding is immediate.
  - **Damage control capacity** depends on ship size class (A–G). Severity bands run from "Minor" (1–6% of DP) to "Overwhelmed" (≥13%). A d10 roll then shifts the result by −2d6% to +2d6% per turn. Ships can boost DC capacity, and neighbours can assist with half their "Minor" value.
  - Kill categories: mobility, firepower, mission, and hard kill.
  - A community proposal adds survivability "levels" that scale DP by construction standard: 100% for warships down to 12.5% for merchants (https://harpgamer.com/harpforum/topic/25945-new-damage-points-considerations/).
- **Fear God & Dread Nought** (WWI, same family) uses range-dependent penetration measured precisely, with many torpedo types (https://theboardgamingway.com/fear-god-and-dread-nought-a-boardgaming-way-review/). The rules PDF could not be fetched.

### B10. Tabletop, briefly

- **General Quarters** (GQ I–III). From https://chuckgame.blogspot.com/2017/01/general-quarters-review.html:
  - A straddle table gives the armour class each gun penetrates at each range bracket.
  - Three dice are rolled together: hit, hull damage and armament damage.
  - Hull boxes are crossed off, and **hull damage directly reduces maximum speed**.
  - A non-penetrating hit does half hull damage and no armament damage.
  - A "2" on the hull die triggers a **critical-hit table** (fires, steering, engine room). Some results need penetration.
  - Praised as "detail baked into the factors".
- **Seekrieg (4th ed.)**. From https://chuckgame.blogspot.com/2017/01/seekrieg-fourth-edition-review.html:
  - Percentile **hit-location chart by range**: deck, side belt, conning tower, turret or superstructure (carriers have flight deck, hangar, island).
  - Shell type multipliers for APC, SAP, Common and HE.
  - Penetration chart by range and thickness.
  - **DP = 0.033 × tonnage**. The ship is lost at total DP.
  - Penetrating hits roll on critical charts (turrets, magazines flooded, searchlights).
  - Criticism: 1890 and 1935 hulls degrade identically.
- **Fletcher Pratt's Naval War Game** (1930s–40s): a flotation-point system from displacement and penetration from calibre and range, with estimated (not rolled) gunnery. The page was not reachable; formula **[UNVERIFIED]**.
- **Victory at Sea** (Mongoose / Warlord). From https://en.wikipedia.org/wiki/Victory_at_Sea_(game) and https://www.wargamingftb.net/?p=8506:
  - Attack dice, then damage dice against armour.
  - A 6 on a damage die gives a critical check (4+), then a critical table: fire, crew, speed, weapons.
  - Some criticals worsen each turn on 4+.
  - Ships become **"crippled"** at a threshold. A d6 repair roll each end phase. Hull damage cannot be repaired.
- **Naval Thunder, Steel Navy:** both use hit boxes plus critical tables in the GQ/VaS mould. No details verified this session.

### B11. Design patterns extracted

| # | Pattern | Seen in | Pros | Cons / pitfalls |
|---|---|---|---|---|
| 1 | **Global HP / damage points** (DP ∝ tonnage; weapon DP ∝ charge or energy^⅓) | Seekrieg, Harpoon, Command, VaS | Trivial, scalable, easy to balance. Tonnage scaling falls straight out of the generator. | Ignores location. "1890 hull = 1935 hull". Hit count matters more than placement, which is unhistorical. |
| 2 | **Section HP + saturation** | WoWS, UA:D (structure per section) | Readable. Gives aiming value. Saturation stops farming one area. | Still an HP sponge. Mismatch with "a ship that is a wreck but afloat". |
| 3 | **Armour-zone hit location from range or angle** (belt vs deck by fall angle) | RTW, Seekrieg, GQ | Captures immune zones and plunging fire cheaply, with no 3D needed. | Needs a hit-location table. Abstract to the player. |
| 4 | **Geometric raycast against armour mesh** | WoWS, UA:D | Angling and geometry matter, and design choices show up visibly. | Expensive. Hidden formulas frustrate players (UA:D). Needs a good feedback UI. A top-down 2D game can do a **2D raycast plus a vertical-band lookup** (waterline / belt / upper belt / deck) instead. |
| 5 | **Probabilistic penetration** (pen ± noise vs effective thickness, plus quality and dud factors) | most | Captures shell-quality eras (British 1916 duds), decapping and edge effects. | Variance can feel unfair. Show the odds. |
| 6 | **Penetration outcome classes** (ricochet / non-pen / partial / pen / over-pen / dud) with damage multipliers | WoWS, UA:D, RTW | Gives AP vs SAP vs HE choice depth. Over-pen is historically real (fuze thresholds). | Too many partial pens makes fights feel futile (UA:D). |
| 7 | **Critical-hit tables** (triggered by penetration or a dice result) | GQ, Seekrieg, VaS, Harpoon | Cheap. Historical "freak" outcomes (rudder jam, magazine). | Pure randomness. Can feel arbitrary unless tied to location. |
| 8 | **Component/module hitboxes** (turrets, rudder, director, boiler, magazine) | WoWS, RTW, AF, Highfleet | Mission kills arise naturally, and they map to generator layout. | Needs a layout plus a 2D footprint. Small modules are rarely hit unless sized by real area. |
| 9 | **Compartment grid with real buoyancy** (volume × permeability, list/trim from moments) | Atlantic Fleet, FtD | Emergent capsizes and plunges. "Hit one side" tactics. Shows *why* ships sink. | Heavier compute. Tuning needed so ships do not sink too easily or too slowly. Players need list/trim feedback. |
| 10 | **Flooding as a rate** (inflow ∝ hole area × √depth; pumps subtract) plus progressive spread | AF, War on the Sea, Cold Waters (DC crews) | Time dimension: "if not sunk in minutes, survives hours". DC decisions matter. | Need to tune hole sizes. Avoid busy micromanagement. |
| 11 | **DoT fire / flood with zone cap** (max 4 fires / 2 floods) | WoWS | Super readable, cheap. | Fires that "burn the HP bar" are unhistorical. Better: fire degrades crew, guns, DC and threatens magazines (UA:D criticism). |
| 12 | **Delayed secondary effects** (fire or flood takes N turns or minutes to bite) | Admiralty Trilogy | Matches historical fire development (9–12 min). Creates a DC window. | Delayed cause and effect needs UI. |
| 13 | **Damage control capacity bands** (severity vs capacity → roll) | Admiralty Trilogy, RTW crew training | Ship size, crew quality and nation (US vs IJN) all fit in one number. | Abstract. |
| 14 | **Chain-reaction adjacency graph** (fire → magazine → bridge) | Highfleet, RTW flash fire | Spectacular, readable in 2D. Rewards good internal layout (generator!). | Can produce too many sudden deaths. Tune by era and tech (RTW's flash learning). |
| 15 | **Mission-kill vs hard-kill victory** | Harpoon, South Dakota-style outcomes | Battles end realistically. Crippled ships retreat. | Needs a scoring and AI retreat logic. |
| 16 | **Ablative armour** | UA:D | Repeated hits at one spot matter. | Bookkeeping per plate cell. |
| 17 | **Speed-stress on damaged hull** (fast + flooded → bulkhead failure) | RTW3 | Meaningful "slow down to survive" choice (*North Carolina* 18 kn). | AI must handle it (RTW "suicide by flooding"). |
| 18 | **Damage log or report UI** | RTW (bad example) | — | The best model fails without a symptom-to-cause report. Plan this early. |

### B12. Implications for this project (notes, not decisions)

- **The generator already knows** the length, beam, draft, compartment layout, armour thicknesses and component positions. That makes patterns **3 + 8 + 9/10 + 14** natural:
  1. a 2D hit point on the plan view, plus a vertical band from fall angle and range
  2. an armour check with a De Marre-style curve
  3. a component hit, with blast and splinter radius in compartments
  4. a hole in a compartment at a depth, giving an inflow rate
  5. buoyancy, list and trim from compartment water moments, giving founder or capsize
  6. fire spread over the compartment adjacency graph toward magazines
- Cheap buoyancy is available. With N≈10–30 longitudinal × 2–3 transverse compartments (wing, centre), list and trim follow from summed water mass moments against a GM from the generator's weights. That is closed form and needs no rigid-body physics.
- **Era knobs:**
  - shell quality and dud rate (British 1914–17 poor)
  - cordite flash sensitivity (high for RN WWI)
  - DC doctrine (US vs IJN)
  - TDS depth
  - shock mounting (post-1940s)
  - overload and topweight (Tsushima)
- **Calibration targets from history:**
  - US destroyers: about 84% survival against above-water hits, 44% against torpedo or mine.
  - Destroyers survive up to about 4 flooded main compartments.
  - Battleships absorb thousands of tonnes (*Seydlitz* ~5,300 t).
  - No ship over 3,000 t sunk by guns of 5" or less.
  - Capital-ship losses almost always involve torpedoes or magazines.
  - Mission kills (*South Dakota*, *Bismarck*'s rudder, *Scharnhorst*'s boiler room) are common.
