# 01 — Capital Ship Subdivision & Protection (c. 1890–1945)

Research base for the damage model of a top-down 2D naval game with a parametric ship generator.
Scope: pre-dreadnoughts → dreadnoughts → battlecruisers → treaty & fast battleships.

Conventions: thicknesses in mm (inches in brackets where the source used inches). "(approx.)" = rounded or source-dependent; "(unverified)" = commonly cited but not confirmed in the sources fetched for this note. All positions are given as rough fractions of waterline length L (0 = bow, 1 = stern), of beam B, or of depth D (keel = 0, upper deck = 1).

---

## 0. Executive summary for designers

1. **A capital ship is a "raft" of buoyancy (the armoured citadel, ~50–70 % of L) plus two soft ends.** Citadels: Yamato 53.5 % of WL length, Nelson 54.7 % ([USNI 1953](https://www.usni.org/magazines/proceedings/1953/october/design-and-construction-yamato-and-musashi)); Bismarck belt 170.7 m ≈ 70 % of WL ([kbismarck.com](https://www.kbismarck.com/proteccioni.html)). Majestic belt only 220 ft of a 390 ft hull ≈ 56 % ([Wikipedia](https://en.wikipedia.org/wiki/Majestic-class_battleship)).
2. **Ships rarely sink from penetrations of the citadel — they sink from flooding** that bypasses subdivision (shaft glands, ventilation, open doors, failed rivets), from **asymmetric flooding → capsize**, or from **magazine explosions**. Bismarck took 400+ hits but had "no underwater penetrations of the ship's fully armoured citadel" ([Wikipedia](https://en.wikipedia.org/wiki/German_battleship_Bismarck)).
3. **Armour ≈ 30–41 % of displacement** in WWII battleships: Yamato 33.1 % ([USNI 1953](https://www.usni.org/magazines/proceedings/1953/october/design-and-construction-yamato-and-musashi)), Iowa 35 % ([pwencycl](http://pwencycl.kgbudge.com/I/o/Iowa_class.htm)), Bismarck ~40 % ([kbismarck.com](https://www.kbismarck.com/proteccioni.html)), North Carolina 41 % ([Wikipedia](https://en.wikipedia.org/wiki/North_Carolina-class_battleship)). (Definitions differ: some include TDS bulkheads and splinter plating.)
4. **TDS depth is the single most important number** for underwater survival ([NavWeaps tech-047](https://www.navweaps.com/index_tech/tech-047.php)). WWII systems were ~4–7 m deep amidships and rated ~320–450 kg (700–1,000 lb) TNT, but **thinner near the end turrets** where the hull narrows — the classic failure point (North Carolina 1942, Yamato 1943, Littorio 1940).
5. **Damage control quality is a huge multiplier**: identical hulls survive or sink depending on counterflooding speed, power availability and closure discipline (Audacious 1914, Prince of Wales 1941, USN post-1942).

---

## 1. Hull structure & subdivision

### 1.1 Transverse watertight (WT) bulkheads

**What:** Full-height (keel to at least the main/armour deck) plate bulkheads across the hull dividing it into main WT compartments. They define the "floodable length" units of the ship.

**Where:** Spaced along the whole length; the citadel ends are closed by **armoured transverse bulkheads** (see §2.5). Inside the citadel, main bulkheads typically separate each magazine group, each boiler room, each engine room.

**Typical counts (main WT compartments):**
| Ship | Main WT compartments | Source |
|---|---|---|
| Nassau (1908) | 16 (sisters 19) | [Wikipedia](https://en.wikipedia.org/wiki/Nassau-class_battleship) |
| Kaiser (1911) | 17 | [Wikipedia](https://en.wikipedia.org/wiki/Kaiser-class_battleship) |
| Seydlitz (1912) | 17 | [Wikipedia](https://en.wikipedia.org/wiki/SMS_Seydlitz) |
| Lützow (1913) | Derfflinger + 1 extra (≈ 17–18, unverified) | [Wikipedia](https://en.wikipedia.org/wiki/SMS_Lützow) |
| Bismarck (1939) | 22 | [Wikipedia](https://en.wikipedia.org/wiki/Bismarck-class_battleship) |

Implied main-bulkhead spacing: Kaiser 172 m / 17 ≈ 10 m; Bismarck ~241 m (WL ~241 m, approx.) / 22 ≈ 11 m. **Rule of thumb: main WT bulkheads every ~0.05–0.07 L, i.e. 15–22 main compartments for a capital ship.** (Derived; treat as approx.)

**Total (small) compartments** are far more numerous because decks and longitudinal bulkheads subdivide further:
- Majestic-type pre-dreadnought (HMS Mars): 72 WT compartments inside the citadel + 78 outside ([Wikipedia](https://en.wikipedia.org/wiki/Majestic-class_battleship)).
- Tennessee class (1919): 768 compartments below waterline + 180 above ([Wikipedia](https://en.wikipedia.org/wiki/Tennessee-class_battleship)).
- Bismarck: >250 compartments on the upper platform deck, a similar number on the middle platform deck, >200 on the lower platform deck ([kbismarck.com](https://www.kbismarck.com/proteccioni.html)).
- Yamato: 1,147 WT compartments, 1,065 of them below the armour deck ([USNI 1953](https://www.usni.org/magazines/proceedings/1953/october/design-and-construction-yamato-and-musashi)).

**How it fails:**
- Seams/rivets open under blast or whipping (holding bulkhead of North Carolina failed by rivet failure, not plate rupture — [WDR 61](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-north-carolina-bb55-war-damage-report-no-61.html)).
- Penetrations (shaft glands, pipes, cables, vents) leak or are torn open (see §1.6).
- Doors/hatches open or not closed (Audacious; California at Pearl Harbor sank through open manhole covers — [Summary of War Damage 1941–42](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/summary-of-war-damage-17-oct-1941-to-7-dec-1942.html)).
- Overpressure from the water head when compartments outboard/forward flood fully; Seydlitz at Jutland steamed astern "to relieve pressure on strained bulkheads" ([Wikipedia](https://en.wikipedia.org/wiki/SMS_Seydlitz)).

> **MODEL NOTE:** Generate `N_main = round(L / s)` with `s ≈ 0.055·L_ref` (≈ 10–12 m for a 200–250 m hull), snapping bulkheads to turret barbettes, boiler/engine room boundaries and citadel ends. Each bulkhead gets an integrity value scaled by build era (riveted pre-1935 weaker; welded later) and a "penetrations" leak rate. A compartment floods to the outside waterline; adjacent bulkheads then roll a failure check each tick based on head of water (depth of flooding) × era factor. Fine subdivision (decks/flats) can be abstracted as a "subdivision quality" scalar that reduces flooding rate and the volume fraction that floods per hit.

### 1.2 Longitudinal bulkheads (and the centreline danger)

**What:** Fore-and-aft bulkheads: (a) torpedo/holding bulkheads in the TDS (§3), (b) wing bulkheads bounding wing/bunker compartments, (c) **centreline bulkheads** splitting boiler/engine rooms into port and starboard halves.

**Why dangerous:** A hit on one side floods only that side of the split machinery space → large heeling moment → list → loss of freeboard on the low side → more flooding → capsize. "All six British pre-dreadnoughts that were sunk by torpedo attack during WWI capsized," attributed partly to longitudinal subdivision; the USN "avoided longitudinal bulkheads entirely" in machinery spaces, accepting larger compartments for symmetric flooding ([Naval Gazing – Flooding](https://www.navalgazing.net/Survivability-Flooding)).

**Examples:** Formidable (single U-24 torpedo, 1915), Audacious (mine 1914; list 15°, reduced to 9° by counterflooding, capsized ~12 h later — [Wikipedia](https://en.wikipedia.org/wiki/HMS_Audacious_(1912))), Yamato 1945 (all hits port side; 11 torpedoes vs Musashi's 19 hits spread on both sides — [Naval Gazing](https://www.navalgazing.net/Survivability-Flooding); [Wikipedia](https://en.wikipedia.org/wiki/Japanese_battleship_Yamato)), Kirishima 1942 (18° list, capsized — [Wikipedia](https://en.wikipedia.org/wiki/Japanese_battleship_Kirishima)).

> **MODEL NOTE:** Give the player/generator a binary `centreline_machinery_bulkhead`. If true: machinery compartments are split port/stb (more, smaller compartments → less water per hit, but each hit floods off-centre ⇒ heel moment `M = w · y_cg`, where `y_cg ≈ ±B/4`). If false: whole-width compartments (more water per hit, but on centreline ⇒ sinkage/trim only). This creates a real design trade-off.

### 1.3 Double / triple bottom, inner bottom

**What:** An inner hull plating above the outer bottom shell, the space between forming tanks (fuel, water) or voids. Protects against grounding and mines/torpedoes under the keel.

**Typical extent/depth:**
- Nassau and Kaiser: double bottom for 88 % of length ([Nassau](https://en.wikipedia.org/wiki/Nassau-class_battleship), [Kaiser](https://en.wikipedia.org/wiki/Kaiser-class_battleship)).
- Bismarck: double bottom for 83 % of length; bottom protection depth 1.7 m ([Wikipedia](https://en.wikipedia.org/wiki/Bismarck-class_battleship)).
- Nelson: 5 ft (1.5 m) double bottom as part of a 12 ft TDS ([Wikipedia](https://en.wikipedia.org/wiki/Nelson-class_battleship)).
- North Carolina: **triple bottom** 5.75 ft (1.75 m) deep — 3 ft liquid-filled lower layer + 2.75 ft void upper layer ([Wikipedia](https://en.wikipedia.org/wiki/North_Carolina-class_battleship)). South Dakota and Iowa also triple bottom, with the lower belt running down to it ([SoDak](https://en.wikipedia.org/wiki/South_Dakota-class_battleship_(1939)), [Iowa](https://en.wikipedia.org/wiki/Iowa-class_battleship)).

**Failure:** Magnetic/influence mines and under-keel torpedo explosions whip the hull and break the bottom; Audacious' mine exploded ~4.9 m (16 ft) below the bottom near the port engine room bulkhead ([Wikipedia](https://en.wikipedia.org/wiki/HMS_Audacious_(1912))). Pre-1940 designs largely ignored under-keel shots.

> **MODEL NOTE:** `bottom_layers ∈ {1,2,3}` and `bottom_depth ≈ 0.07–0.10·D` (≈1.5–1.8 m). Damage from under-keel hits reduced by layers; a triple bottom costs displacement and draft but sharply cuts machinery flooding from mines.

### 1.4 Wing compartments, bunkers, cofferdams

- **Coal bunkers as protection (1890–~1915):** Outboard bunkers absorbed energy and fragments; coal "absorbed a great deal of energy when pulverized"; bunkers were typically only ~60 % full, limiting flooding volume. Drawbacks: non-watertight scuttles often open, coal dust explosions, protection falls as coal is burned ([Naval Gazing – UW Protection 1](https://www.navalgazing.net/Underwater-Protection-Part-1)).
- **Cofferdams:** narrow void spaces separating tanks from magazines/machinery; also used in Richelieu filled with "ébonite mousse" (rubber foam) to limit flooding ([Wikipedia](https://en.wikipedia.org/wiki/Richelieu-class_battleship)). Littorio filled the 250 mm gap between outer 70 mm plate and main belt with "Cellulite" foam ([Wikipedia](https://en.wikipedia.org/wiki/Littorio-class_battleship)).
- **Splinter cells:** Bismarck had 30 mm longitudinal splinter bulkheads creating 51 armoured cells between decks ([kbismarck.com](https://www.kbismarck.com/proteccioni.html)).

> **MODEL NOTE:** Represent fuel state: bunkers/tanks full of coal or oil reduce flooding volume (permeability μ ≈ 0.4 for coal-filled, ~0.95 for empty), but burning fuel during a mission degrades protection — a nice emergent mechanic for coal-era ships.

### 1.5 Watertight decks / flats

The armour deck(s) form the top of the "raft"; below them platform decks/flats subdivide horizontally. Water entering above the armour deck (ends, upper hull) spreads freely along unsubdivided upper decks — this is how Lützow's bow flooding grew progressively ("multiple shell holes in the forecastle above the armored deck allowed progressive water ingress as the ship's draft increased") ([Wikipedia](https://en.wikipedia.org/wiki/SMS_Lützow)).

> **MODEL NOTE:** Two flooding layers per section: **below armour deck** (subdivided, slow spread) and **above armour deck** (weakly subdivided, spreads to neighbours quickly once the deck goes below the waterline through sinkage/trim). This single rule reproduces Lützow, Seydlitz and Bismarck's bow behaviour.

### 1.6 Doors, hatches, penetrations, ventilation, cable glands, shaft glands

Documented leak paths:
- **Shaft glands / shaft alleys:** Prince of Wales — one torpedo at frame 280 by the port outer shaft; the eccentric whirling shaft wrecked WT glands at frames 270, 253, 242, 228 and 206; flooding ran up the shaft alley into Y action machinery room, diesel dynamo room and B engine room (via gland at frame 184); B engine room evacuated ~18 min after the hit; list 11.5° ([Garzke, Dulin & Denlay, "Death of a Battleship", 2012](https://pacificwrecks.com/ship/hms/prince-of-wales/death-of-a-battleship-2012-update.pdf)).
- **Pipes, valves, hatches:** Audacious — "water was found to have spread through bulkheads because of faulty seals around pipes and valves, broken pipes and hatches which did not close properly"; ship not at action stations, WT doors open ([Wikipedia](https://en.wikipedia.org/wiki/HMS_Audacious_(1912))).
- **Ventilation ducts:** North Carolina — ~2 ft of water entered Turret I lower handling room via a damaged ventilation duct; fire-control cables saturated ([WDR 61](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-north-carolina-bb55-war-damage-report-no-61.html)). Naval Gazing: "cable glands leak if not maintained, ventilation systems are natural flooding paths" ([link](https://www.navalgazing.net/Survivability-Flooding)).
- **Piping through holding bulkhead:** Saratoga flooded "through damaged piping at holding bulkhead" ([War Damage Summary](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/summary-of-war-damage-17-oct-1941-to-7-dec-1942.html)).
- **Casemate openings:** Iron Duke's low 6-in casemates' hinged covers "were easily washed away" → flooding in heavy seas ([Wikipedia](https://en.wikipedia.org/wiki/Iron_Duke-class_battleship)).
- **Design response:** RN dreadnoughts from Dreadnought onward are commonly described as having main bulkheads below the main deck unpierced by doors, with compartments accessed vertically (Dreadnought had five lifts — [Wikipedia](https://en.wikipedia.org/wiki/HMS_Dreadnought_(1906))) (unverified detail). After Audacious the RN added bilge pumps, circulating-pump bilge suctions and ventilation duct valves.

> **MODEL NOTE:** Every bulkhead has a `leak_rate` = base (era/build quality) + Σ(penetrations). Damage events adjacent to a bulkhead can raise it. Add a crew "readiness/closure" state (peace cruising vs general quarters) multiplying leak rates (e.g. ×3–5 when not at action stations — game tuning value, not historical). A special "shaft whip" event on hits near propeller shafts (aft 0.75–0.95 L) propagates leaks along all bulkheads the shaft passes through — reproduces PoW.

### 1.7 Evolution 1890 → 1945 (subdivision)

| Era | Typical features |
|---|---|
| 1890–1905 pre-dreadnought | Short belt (~55–65 % L), turtleback armour deck with sloped sides, coal bunkers as side protection, double bottom, centreline bulkhead in machinery, many WT doors. 72+78 compartments on Majestic-type ([Wikipedia](https://en.wikipedia.org/wiki/Majestic-class_battleship)). |
| 1906–1914 early dreadnoughts | Torpedo bulkheads appear: Dreadnought only abreast magazines (2 in / 4 in near P & Q turrets); Bellerophon full-length 0.75–3 in ([Bellerophon](https://en.wikipedia.org/wiki/Bellerophon-class_battleship)). German ships: full-length torpedo bulkhead 30–40 mm, 16–19 main compartments, double bottom 88 % L, wide beam. |
| 1914–1918 lessons | Audacious (open doors, leaking pipes), Jutland (bow flooding of Lützow 8,000 t, Seydlitz 5,308 t). Bulges retrofitted. |
| 1915–1925 US Standard type & bulged British | All-or-nothing; multi-layer liquid TDS (Tennessee: 4 TDS bulkheads, inner pair liquid-filled, 768+180 compartments). |
| 1930s treaty / WWII | Oil fuel in liquid layers, deep TDS (4–7 m), triple bottoms (US), welded structure appearing, very fine subdivision (Yamato 1,147 compartments). Persisting weaknesses: TDS narrowing at ends, shaft penetrations, riveted joints. |

---

## 2. Armour schemes

### 2.1 Belt (main, upper, ends)

**What/where:** Vertical armour at the waterline, typically ~1.0–1.5 m below to ~1–3 m above the design WL (height ≈ 0.3–0.6·D). Main belt covers the citadel; thinner strakes may continue to the ends (incremental schemes).

**Examples:**
- Majestic: 9 in Harvey, 220 ft long, 5 ft 6 in above / 9 ft 6 in below WL ([Wikipedia](https://en.wikipedia.org/wiki/Majestic-class_battleship)).
- Formidable: 9 in Krupp; 3 in forward of belt, 1.5 in aft ([Wikipedia](https://en.wikipedia.org/wiki/Formidable-class_battleship)).
- Dreadnought: 11 in tapering to 7 in at lower edge; 8 in upper belt ([Wikipedia](https://en.wikipedia.org/wiki/HMS_Dreadnought_(1906))).
- Nassau: 290–300 mm, 170 mm lower edge, ends 140→100 mm forward, 130→90 mm aft ([Wikipedia](https://en.wikipedia.org/wiki/Nassau-class_battleship)).
- Kaiser: 350 mm, upper strake 203 mm, ends 180→120 mm / 120→80 mm ([Wikipedia](https://en.wikipedia.org/wiki/Kaiser-class_battleship)).
- Nevada: 13.5 in, 17 ft 4.6 in high (8 ft 6 in below WL), lower edge 8 in ([Wikipedia](https://en.wikipedia.org/wiki/Nevada-class_battleship)).
- Hood: 12 in inclined belt, 7 in middle belt, 5 in upper belt ([Wikipedia](https://en.wikipedia.org/wiki/HMS_Hood)).
- KGV: 14.7 in (magazines) / 13.7 in (machinery), 23.5 ft high, reaching 15 ft below deep WL ([Wikipedia](https://en.wikipedia.org/wiki/King_George_V-class_battleship_(1939))).
- Bismarck: 320 mm main belt (220 mm thinnest parts), upper side 145 mm ([Wikipedia](https://en.wikipedia.org/wiki/Bismarck-class_battleship); [Okun](https://www.combinedfleet.com/okun_biz.htm)); design 3.3 m above / 1.5 m below WL, in service ~2.6 m / 2.2 m ([kbismarck.com](https://www.kbismarck.com/proteccioni.html)).

**Inclined & internal belts:** Inclination increases effective thickness vs plunging fire. Nelson internal belt sloped 18° ([Wikipedia](https://en.wikipedia.org/wiki/Nelson-class_battleship)); South Dakota 12.2 in internal at 19° ≈ 17.3 in vertical equivalent at 19,000 yd ([Wikipedia](https://en.wikipedia.org/wiki/South_Dakota-class_battleship_(1939))); Richelieu 327–330 mm at 15°24′ ≈ 478 mm equivalent ([navypedia](https://www.navypedia.org/ships/france/fr_bb_richelieu.htm)); Yamato 410 mm at 20° ([Wikipedia](https://en.wikipedia.org/wiki/Yamato-class_battleship)). Internal belts are cheaper (shorter, lower height for same coverage) but put the outer hull in front — repairs after hits are harder and the space between becomes floodable.

**Lower belt to the bottom (anti-diving-shell):** South Dakota/Iowa lower belt runs down to the triple bottom tapering 310 → 25–41 mm and forms a TDS bulkhead ([SoDak](https://en.wikipedia.org/wiki/South_Dakota-class_battleship_(1939)), [Iowa](https://en.wikipedia.org/wiki/Iowa-class_battleship)); Yamato 200 mm lower belt below main belt ([Wikipedia](https://en.wikipedia.org/wiki/Yamato-class_battleship)).

**Failure:** Penetration above/below the belt (shells passing over the belt into upper hull, or underwater "diving" hits beneath it); belt-edge joints shearing (Yamato); plates dislodged by blast (unverified generalisation).

> **MODEL NOTE:** Belt as a vertical band: `belt_top = WL + h_up`, `belt_bot = WL − h_dn`; `h_up + h_dn ≈ 0.35–0.55·D` (approx.). Effective thickness `t_eff = t / cos(θ_incline + θ_fall)`. Weight ∝ t × height × length (length = citadel fraction × L). When ship sinks deeper/trims/lists, belt_top relative to the sea drops → upper hull exposed to flooding hits. This is a cheap but powerful dynamic.

### 2.2 Armoured decks: flat vs sloped (turtleback / "Panzerdeck + Böschung")

**Turtleback / slopes:** The armour deck runs flat above WL amidships and slopes down to meet the lower belt edge. Pre-dreadnought standard (Majestic: 3 in flat, 4 in slopes; Formidable 2 in flat, 3 in slope — [Majestic](https://en.wikipedia.org/wiki/Majestic-class_battleship), [Formidable](https://en.wikipedia.org/wiki/Formidable-class_battleship)); Dreadnought 1.75 in flat / 2.75 in slopes; Nassau 38 mm flat / 58 mm slopes.

**German WWII scheme (Bismarck):** 50 mm upper deck; main armour deck 80 mm (machinery) / 95–100 mm (magazines) flat, with 110–120 mm slopes ("Böschung") at ~22° meeting the belt's lower edge; 145 mm upper side belt ([Okun](https://www.combinedfleet.com/okun_biz.htm); [kbismarck.com](https://www.kbismarck.com/proteccioni.html)). Logic: a shell penetrating the 320 mm belt must still defeat the slope → excellent protection of vitals at short/medium range, at the price of a low armour deck (more volume above it unprotected: communications, fire control, upper hull). Okun: the amidships non-magazine deck structure is "ineffective against its own gun" at some ranges; upper side armour weight "could have added at least an inch" to the main deck.

**Flat high armour deck (US/British "all-or-nothing" style):** Armour deck at top of belt (KGV 4.88–5.88 in plus thinner layers; Iowa ~6 in combined; North Carolina 5 in + 1.45 in), with a splinter deck below to catch fragments. Maximises protected volume and stability buoyancy but relies on belt alone vs flat trajectory hits.

**Splinter decks:** 0.62–0.75 in (NC third deck), 0.625 in (SoDak/Iowa) below the main armour deck; Richelieu 40 mm lower deck with 50 mm slopes ([Wikipedia](https://en.wikipedia.org/wiki/Richelieu-class_battleship)).

**Deck/belt weight shift:** horizontal protection rose to ~70 % of belt weight by Iowa (approx.) ([Naval Gazing – Armor 3](https://www.navalgazing.net/Armor-Part-3)).

> **MODEL NOTE:** Offer the player `deck_style ∈ {flat_high, turtleback_low}`. Flat-high: larger protected volume (more reserve buoyancy counted as "protected"), better vs long-range plunging fire. Turtleback-low: shells that beat the belt must also beat the slope (add slope thickness × 1/cos(angle) to path), but everything between armour deck and upper deck (fire control cables, comms, secondary handling, crew) is outside protection; upper hull flooding raises KG problems.

### 2.3 Decapping / bomb decks and spaced armour

- **Iowa / South Dakota:** 1.5 in STS "bomb deck"/weather deck to initiate bomb and shell fuzes before the main armour deck ([Iowa](https://en.wikipedia.org/wiki/Iowa-class_battleship); [pwencycl](http://pwencycl.kgbudge.com/I/o/Iowa_class.htm)); North Carolina 1.45 in first deck "for delay-fuzed projectile detonation" ([Wikipedia](https://en.wikipedia.org/wiki/North_Carolina-class_battleship)).
- **KGV:** 1.25 in Ducol weather deck ([Wikipedia](https://en.wikipedia.org/wiki/King_George_V-class_battleship_(1939))).
- **Bismarck:** 50 mm upper deck + 145 mm upper side belt meant as a first layer (decapping/yaw-inducing) ([Okun](https://www.combinedfleet.com/okun_biz.htm)).
- **Littorio (Vittorio Veneto):** 70 mm homogeneous outer belt plate, 250 mm gap, 280 mm cemented main belt — explicit decapping scheme ([Wikipedia](https://en.wikipedia.org/wiki/Littorio-class_battleship)).
- **Yamato:** no decapping; relied on sheer thickness (410 mm belt, 200–230 mm deck) ([Wikipedia](https://en.wikipedia.org/wiki/Yamato-class_battleship)).

> **MODEL NOTE:** A "first plate" ≥ ~0.08 × shell calibre (approx., tuning value) strips AP caps → raise penetration difficulty of the next layer (e.g. ×1.1–1.2). Also arms delay fuzes so bombs/shells burst between decks rather than below the armour deck.

### 2.4 Barbettes, turrets, conning tower, steering box

- **Barbettes:** Majestic 14 in exposed / 7 in below deck; Dreadnought 11 in; Kaiser 305 mm exposed; Iowa 17.3 in beam / 11.6 in centreline; NC 14.7–16 in; Bismarck 340 mm exposed, 220 mm behind upper hull; Richelieu 405 mm (80 mm between decks) (sources as per ship pages above).
- **Turret faces:** Formidable 8 in; Dreadnought 11 in; Nevada 18 in; NC 16 in; Iowa 19.5 in; Bismarck 360 mm; Richelieu 430 mm; Yamato 650 mm.
- **Conning tower:** Majestic 14 in; Nevada 16 in; Bismarck 350 mm; Iowa 17.3 in.
- **Steering gear:** Nassau 81 mm; Kaiser 120 mm deck over steering gear; Bismarck 110 mm turtle deck aft; Richelieu 150 mm over steering ([Nassau](https://en.wikipedia.org/wiki/Nassau-class_battleship); [Kaiser](https://en.wikipedia.org/wiki/Kaiser-class_battleship); [kbismarck.com](https://www.kbismarck.com/proteccioni.html); [Richelieu](https://en.wikipedia.org/wiki/Richelieu-class_battleship)). The rudders themselves are unprotectable: Bismarck's port rudder jammed 12° by one aerial torpedo; Littorio's rudder destroyed at Taranto; Kirishima's rudders/steering destroyed by Washington ([Bismarck](https://en.wikipedia.org/wiki/German_battleship_Bismarck); [Littorio](https://en.wikipedia.org/wiki/Italian_battleship_Littorio); [Kirishima](https://en.wikipedia.org/wiki/Japanese_battleship_Kirishima)). "Shafts and rudder remained unprotectable, ultimately dooming Bismarck" ([Naval Gazing UW 2](https://www.navalgazing.net/Underwater-Protection-Part-2)). Bismarck's stern was also "weakly constructed" ([Wikipedia](https://en.wikipedia.org/wiki/Bismarck-class_battleship)).

> **MODEL NOTE:** Model rudder/steering and shafts as discrete critical components at 0.92–1.0 L (rudder) and 0.70–0.95 L (shafts) below WL. Steering box armour only protects the gear *inside*; any torpedo/near-miss at 0.9–1.0 L rolls a "rudder jam" check (jam angle random ±0–15°). Twin rudders reduce but don't remove risk.

### 2.5 Armoured transverse bulkheads

Close the citadel ends to stop raking fire and flooding from the soft ends: Majestic 14 in fwd / 12 in aft; Formidable 9 / 9–10 in; Dreadnought 8 in; Kaiser 305 mm; Nevada 8–13 in; KGV 12 in fwd / 10 in aft; Richelieu 355 mm fwd / 233 mm aft; Yamato up to 355 mm (sources: class pages above).

### 2.6 Incremental ("everything") vs All-or-Nothing

- **Incremental:** Main belt + upper belt + casemate armour + thinner end belts (Royal Navy & German WWI practice; Bismarck/KGV retained elements). Intent: keep out HE and splinters everywhere, keep ends buoyant. Risk: medium armour acts as a fuze for AP shells.
- **All-or-Nothing (US Standard type, Nevada, 1912):** "eschewed any medium protection in favor of a thicker belt, massive turret faces, and thicker turret tops and decks"; designed around the **raft body** — enough buoyancy within the citadel to float even with ends riddled ([NavWeaps tech-070](https://www.navweaps.com/index_tech/tech-070.php); [Naval Gazing](https://www.navalgazing.net/Armor-Part-3)). Adopted by Nelson (first British) and all treaty ships to varying degrees.
- **Downside shown in WWII:** unarmoured superstructure/upper works get wrecked by medium-calibre fire — South Dakota at Guadalcanal: 27 hits (mostly medium calibre, plus one 14 in which failed to penetrate turret) left her "deaf, dumb, blind, and impotent" after an electrical switchboard error and radar loss ([Wikipedia](https://en.wikipedia.org/wiki/USS_South_Dakota_(BB-57))).

### 2.7 Immune zone

Range band where the citadel can't be penetrated by a specified gun: inner limit set by belt (penetration falls with range), outer limit by deck (plunging fire). Concept formalised ~1929 ([Naval Gazing](https://www.navalgazing.net/Armor-Part-3)). Examples: Iowa 16,100–28,500 m vs 16"/45; 21,600–25,000 m vs 16"/50 ([pwencycl](http://pwencycl.kgbudge.com/I/o/Iowa_class.htm)); KGV vs 15 in, estimates range from ~17,200 to 32,000 yd depending on source ([Wikipedia](https://en.wikipedia.org/wiki/King_George_V-class_battleship_(1939))).

> **MODEL NOTE:** The generator can compute and display an immune zone per enemy gun — great player feedback. Use a simple penetration curve per gun (vertical penetration decreasing with range; deck penetration increasing) and intersect with belt `t_eff` and deck thickness.

### 2.8 Armour weight fractions

| Ship | Armour weight | % of displacement | Source |
|---|---|---|---|
| Yamato | 23,500 t | 33.1 % | [USNI 1953](https://www.usni.org/magazines/proceedings/1953/october/design-and-construction-yamato-and-musashi) |
| Iowa | 17,056 t | 35 % | [pwencycl](http://pwencycl.kgbudge.com/I/o/Iowa_class.htm) |
| Bismarck | 19,082 t (incl. underwater & splinter) | ~40 % of design combat weight | [kbismarck.com](https://www.kbismarck.com/proteccioni.html) |
| North Carolina | — | 41 % | [Wikipedia](https://en.wikipedia.org/wiki/North_Carolina-class_battleship) |
| Iron Duke | +820 t added post-Jutland | — | [Wikipedia](https://en.wikipedia.org/wiki/Iron_Duke-class_battleship) |

Pre-dreadnought/dreadnought armour fractions are typically quoted around 25–35 % (approx., unverified here).

> **MODEL NOTE:** Budget armour as `W_armour = Σ(area_i × t_i × 7.85 t/m³)`; target 28–42 % of displacement for a "real" capital ship; flag designs outside 20–45 % as unrealistic.

---

## 3. Torpedo / underwater protection (TDS)

### 3.1 Principles

- Depth matters most: "the greater the distance between the point of impact on the side shell and the holding bulkhead, the more likely the system would protect the interior" ([NavWeaps tech-047](https://www.navweaps.com/index_tech/tech-047.php)).
- Classic layering: **outer void** (lets gas bubble expand), **liquid layers** (spread the pressure and catch fragments), **inner void** (lets the holding bulkhead deflect elastically without transmitting load), **holding bulkhead** (thin, ductile, high-elongation steel). "No reliable equations to predict TDS performance were ever developed"; small-scale tests didn't scale ([Naval Gazing UW 1](https://www.navalgazing.net/Underwater-Protection-Part-1)).
- German early finding: void outboard of the coal bunker greatly improves protection ([Naval Gazing UW 1](https://www.navalgazing.net/Underwater-Protection-Part-1)).

### 3.2 National systems (depth amidships, design charge)

| System | Depth | Layers | Rated charge | Source |
|---|---|---|---|---|
| Dreadnought (1906) | — | 2 in torpedo bulkheads abreast magazines only (4 in near P/Q) | — | [Wiki](https://en.wikipedia.org/wiki/HMS_Dreadnought_(1906)) |
| German WWI (Nassau, Kaiser) | (approx. 4 m, unverified) | coal bunker + 30–40 mm torpedo bulkhead | — | [Nassau](https://en.wikipedia.org/wiki/Nassau-class_battleship), [Kaiser](https://en.wikipedia.org/wiki/Kaiser-class_battleship) |
| Ramillies bulge (1917) | — | bulge with 8–9 in sealed tubes + wood pulp | ~400 lb (amateur estimate) | [NavWeaps](https://www.navweaps.com/index_tech/tech-047.php), [dionysus.biz](https://dionysus.biz/torpedodefense.html) |
| Hood | 7.5 ft bulge | outer void + crushing tubes + 1.5 in bulkhead | — | [Wiki](https://en.wikipedia.org/wiki/HMS_Hood) |
| Tennessee (US Standard) | (approx. 17 ft) | 4 TDS bulkheads, inner pair liquid | — | [Wiki](https://en.wikipedia.org/wiki/Tennessee-class_battleship), [Naval Gazing](https://www.navalgazing.net/Underwater-Protection-Part-1) |
| Nelson | 12 ft incl. 5 ft double bottom | water-filled layers between air layers | 750 lb | [Wiki](https://en.wikipedia.org/wiki/Nelson-class_battleship) |
| KGV | ~13 ft sandwich + 8 ft aux. spaces | void-liquid-void, 1.5–1.75 in holding bulkhead | 1,000 lb (full-scale tested) | [Wiki](https://en.wikipedia.org/wiki/King_George_V-class_battleship_(1939)) |
| North Carolina | 18.5 ft (5.64 m) | 5 bulkheads; outer 2 and innermost void, 3–4 liquid | 700 lb | [Wiki](https://en.wikipedia.org/wiki/North_Carolina-class_battleship) |
| South Dakota | 17.9 ft (5.46 m) | 4 bulkheads; outer two liquid, inner two void; lower belt = 3rd bulkhead | 700 lb | [Wiki](https://en.wikipedia.org/wiki/South_Dakota-class_battleship_(1939)) |
| Iowa | 17.9 ft (5.46 m) | 4 bulkheads (16 mm, lower belt, 16 mm, 22 mm); liquid-liquid-void-void | 700 lb | [pwencycl](http://pwencycl.kgbudge.com/I/o/Iowa_class.htm), [Naval Gazing](https://www.navalgazing.net/Underwater-Protection-Part-2) |
| Bismarck | 5.5 m | 45 mm torpedo bulkhead (53 mm per Wiki), oil tanks | — | [Wiki](https://en.wikipedia.org/wiki/Bismarck-class_battleship), [kbismarck.com](https://www.kbismarck.com/proteccioni.html) |
| Littorio (Pugliese) | (drum 3.8 m dia.; ~7 m overall, unverified) | void drum 6 mm walls inside liquid, 40 mm curved bulkhead | 350 kg | [Wiki](https://en.wikipedia.org/wiki/Littorio-class_battleship) |
| Richelieu | 7 m (Jean Bart 8.5 m) | deep conventional + ébonite mousse; 30 mm torpedo bulkhead | — | [navypedia](https://www.navypedia.org/ships/france/fr_bb_richelieu.htm) |
| Yamato | 5.1 m | no liquid layers; relied on lower belt/bulkhead | 400 kg (880 lb) | [Wiki](https://en.wikipedia.org/wiki/Yamato-class_battleship), [Naval Gazing](https://www.navalgazing.net/Underwater-Protection-Part-2) |

An amateur regression on historical systems suggests roughly `rating(lb TNT) ≈ 37.6 × depth(ft) − 132` ([dionysus.biz](https://dionysus.biz/torpedodefense.html)) — it under-predicts US systems (18.5 ft → ~560 lb vs 700 lb rated), so use only as a coarse baseline.

### 3.3 Failure modes (with cases)

1. **Shallow system near the end turrets.** North Carolina, 15 Sep 1942, I-19 torpedo (660 lb warhead) at frames 45–46, 20 ft 4 in below WL, abreast Turret I where the TDS had "one less torpedo protection bulkhead": TDS bulkhead 1 demolished, 3 and 4 torn; holding bulkhead No. 5 pushed within 3 in of the turret stool with seams opened by rivet failure; 970 t flooded (22 voids, 12 fuel tanks, 4 magazines); list 5.5° corrected in 6 min with ~480 t counterflooding; sustained speed 18 kn (24 kn briefly) ([WDR 61](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-north-carolina-bb55-war-damage-report-no-61.html)). Pugliese width cut from 3,800 mm to 2,280 mm abreast the main turrets ([Littorio](https://en.wikipedia.org/wiki/Littorio-class_battleship)). "All treaty battleships suffered from insufficient depth near the ends" ([Naval Gazing](https://www.navalgazing.net/Underwater-Protection-Part-2)).
2. **Weak structural joints.** Yamato: one torpedo from USS Skate (Dec 1943) aft, hole ~25 m across 5 m below top of bulge; ~3,000 t flooded; joint between upper and lower belt failed and the aft turret's upper magazine flooded ([Wikipedia](https://en.wikipedia.org/wiki/Japanese_battleship_Yamato)); the joint "relied entirely on the shear strength of rivets" ([Naval Gazing](https://www.navalgazing.net/Underwater-Protection-Part-2)). Pugliese: riveted bottom joint of the bulkhead failed before the drum collapsed. PoW: the "shelf-like" belt/lower hull joint pushed inboard, puncturing the inboard bulkhead ([Garzke et al.](https://pacificwrecks.com/ship/hms/prince-of-wales/death-of-a-battleship-2012-update.pdf)).
3. **Hits outside the TDS (ends, shafts, rudder):** PoW (shaft), Bismarck (rudder), Littorio at Taranto (2 bow, 1 stern; settled by the bow, decks awash to the turrets) ([Littorio](https://en.wikipedia.org/wiki/Italian_battleship_Littorio)); Musashi's Tunny hit near the bow, 5.8 m hole, 3,000 t ([Musashi](https://en.wikipedia.org/wiki/Japanese_battleship_Musashi)).
4. **Wrong liquid loading / counterflooding into TDS voids:** PoW flooded starboard TDS voids to counter list — this "eliminated the air-gap buffer" for subsequent starboard hits ([Garzke et al.](https://pacificwrecks.com/ship/hms/prince-of-wales/death-of-a-battleship-2012-update.pdf)).
5. **Cumulative hits in the same area** overwhelm any TDS: Musashi 19 torpedoes + 17 bombs; Yamato ~11 torpedoes + 6 bombs mostly port side ([Musashi](https://en.wikipedia.org/wiki/Japanese_battleship_Musashi); [Yamato](https://en.wikipedia.org/wiki/Japanese_battleship_Yamato)). Oklahoma took 7–9 aerial torpedoes and West Virginia 9 (or six torpedoes + two bombs per another account) at Pearl Harbor ([NavWeaps](https://www.navweaps.com/index_tech/tech-047.php); [Ricketts](https://en.wikipedia.org/wiki/Claude_V._Ricketts)).
6. **Shock / whipping:** generally modest on battleships (NC: "shock effect to electrical equipment was remarkably slight") but power loss from flooding of generator spaces is decisive (PoW lost 5 of 8 generators).

**Typical single-torpedo flooding in a capital ship:** ~1,000–4,000 t: NC 970 t; Bismarck bow hit (shell) 1,000–2,000 t; Vittorio Veneto at Matapan ~4,000 t; Littorio June 1942 ~1,500 t (+350 t counterflood); Yamato and Musashi ~3,000 t each; Musashi first hit at Sibuyan Sea 3,000 t, 5.5° list ([sources above](https://en.wikipedia.org/wiki/Japanese_battleship_Musashi)).

### 3.4 Underwater shell hits (diving shells)

Japanese Type 88/91 AP shells had a flat "cap head" nose (~50 % of cross-section) after the windscreen broke away on water impact, giving stable underwater travel; most other nations' AP tumbled and fuzed immediately on water entry. Documented case: USS Boise's forward magazine hit by an 8 in Type 91 underwater ([NavWeaps tech-041](http://navweaps.com/index_tech/tech-041.php)). Yamato's 200 mm lower belt and the US lower belts down to the triple bottom addressed this ([Yamato](https://en.wikipedia.org/wiki/Yamato-class_battleship); [SoDak](https://en.wikipedia.org/wiki/South_Dakota-class_battleship_(1939))). Okun criticised Bismarck's designers for not considering diving shells although "a great many hits in WWII were underwater hits" ([Okun](https://www.combinedfleet.com/okun_biz.htm)). Kirishima received two 16 in hits below WL aft ([Wikipedia](https://en.wikipedia.org/wiki/Japanese_battleship_Kirishima)).

> **MODEL NOTE (TDS):** Parameterise from beam: `TDS_depth ≈ k · B` amidships with `k ≈ 0.15–0.22` (US 5.5 m on 33 m beam ≈ 0.17; Richelieu 7 m on 33 m ≈ 0.21; Yamato 5.1 m on 38.9 m ≈ 0.13 — derived, approx.). Taper depth linearly to ~50–60 % at the end turrets (where waterplane narrows with Cb) and to 0 beyond the citadel. Rating `R = f(depth, layers, liquid_ok)`; damage to inside = max(0, warhead − R(depth_at_x)) → floods compartments inboard of holding bulkhead. Always flood the TDS outer layers on the hit side (~200–1,000 t per hit). Penalise riveted joints (era < 1935) with a "joint failure" chance that floods the next inboard compartment. Counterflooding into TDS voids should reduce that side's rating. Diving shells: AP hitting water within ~X m short of target (calibre-scaled) can continue underwater if nation flag = Japan; resolved against lower belt.

---

## 4. Ends: unarmoured bow/stern flooding, trim, speed and stability

**What:** Volume outside the citadel (~30–50 % of L). In all-or-nothing ships it is deliberately sacrificial; in incremental ships thin end belts (Nassau 100–140 mm, Kaiser 80–180 mm, Hood 5–6 in) and end decks (Kaiser 61 mm fwd/61–102 mm aft) attempt to limit hole size.

**Effects and cases:**
- **Lützow (Jutland):** ~8 hits concentrated forward; flooding progressed above the armour deck as draught increased; ~8,000 t of water; forward draught >17 m (normal 9.2 m); speed down to 3 kn to avoid bulkhead failure; forward pumps jammed; scuttled ([Wikipedia](https://en.wikipedia.org/wiki/SMS_Lützow)).
- **Seydlitz (Jutland):** 21 heavy hits + 1 torpedo (12 × 4 m hole under fore turret); 5,308 t of water; freeboard 2.5 m; bow nearly submerged; steamed astern to ease bulkheads; survived ([Wikipedia](https://en.wikipedia.org/wiki/SMS_Seydlitz)).
- **Derfflinger:** ~300 t through a bow hole ([Wikipedia](https://en.wikipedia.org/wiki/SMS_Derfflinger)).
- **Bismarck (Denmark Strait):** one 14 in hit through the bow → 1,000–2,000 t, 9° list to port (as given by Wikipedia; other accounts give a smaller list, unverified), 3° trim by bow, fuel contaminated/cut off — this fuel loss shaped the rest of the operation ([Wikipedia](https://en.wikipedia.org/wiki/German_battleship_Bismarck)).
- **Littorio at Taranto:** settled by the bow, decks awash up to the main turrets ([Wikipedia](https://en.wikipedia.org/wiki/Italian_battleship_Littorio)).
- **Musashi:** progressive bow trim — bow down 4 m by mid-afternoon; counterflooding reduced list but cost 1.8 m forward freeboard ([Wikipedia](https://en.wikipedia.org/wiki/Japanese_battleship_Musashi)).
- **Iowa:** fine lines → "bow wet and vulnerable to damage" ([pwencycl](http://pwencycl.kgbudge.com/I/o/Iowa_class.htm)).

**Speed effects:** NC 24 → 18 kn sustained; Musashi 27 → 22 → 20 → 6 kn as flooding accumulated; Lützow ~3 kn. A ship trimmed by the bow must slow because water pressure on forward bulkheads rises with speed (Seydlitz/Lützow).

**Stability design margins (Yamato):** reserve buoyancy 57,450 t; could correct 18.3° heel by counterflooding; designed to stay stable to 20° list and with forward freeboard down to 4.5 m; capsize limit ~30° in damaged condition ([USNI 1953](https://www.usni.org/magazines/proceedings/1953/october/design-and-construction-yamato-and-musashi)).

> **MODEL NOTE:** Compute per-section buoyancy along L (use Cb to shape the waterplane: fuller Cb ⇒ more volume in ends). Flooded mass at x creates trim moment; trim lowers the bow freeboard, which raises the flooding rate of above-armour-deck compartments forward (spreads like Lützow). Speed limit `v_max_damaged = v_max × f(trim, bow freeboard)`, plus a "bulkhead stress" check scaling with v² × flooded-forward-volume: going fast while bow-heavy risks forward bulkhead collapse. Rule: lose ~1 kn per 300–500 t of bow flooding (game tuning, loosely fitted to NC/Musashi/Seydlitz — approx.).

---

## 5. Counterflooding, pumping, damage control organisation

### 5.1 Counterflooding & pumping (facts)

- **Audacious 1914:** list 15° → 9° by counterflooding in an hour; machinery rooms abandoned at 10:50; capsized ~12 h after hit ([Wikipedia](https://en.wikipedia.org/wiki/HMS_Audacious_(1912))).
- **North Carolina 1942:** 5.5° list removed in 6 minutes with ~480 t counterflooding, later pumped out ([WDR 61](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-north-carolina-bb55-war-damage-report-no-61.html)).
- **West Virginia, Pearl Harbor:** counterflooding after heeling from multiple torpedo hits (Lt. Ricketts) is credited with her settling upright rather than capsizing like Oklahoma ([Ricketts](https://en.wikipedia.org/wiki/Claude_V._Ricketts); outcome per general accounts, unverified detail).
- **Prince of Wales:** list 11.5° → 9° after counterflooding TDS voids (–2.5°); ~100 min from first hit to capsizing; total water ~18,000 t by 12:50 per the survey report; only 3 of 8 generators (330 kW each) running at the second attack; pumps couldn't keep pace ([Garzke et al.](https://pacificwrecks.com/ship/hms/prince-of-wales/death-of-a-battleship-2012-update.pdf)).
- **Musashi:** repeatedly corrected list (5.5° → 1°; 10° → 6°) at the cost of trim and freeboard; abandoned at 12°, sank ~9 h after first hit ([Wikipedia](https://en.wikipedia.org/wiki/Japanese_battleship_Musashi)).
- **Yamato 1945:** list 5–6° → 15–18°; counterflooding of starboard spaces insufficient; capsized and a forward magazine detonated ([Wikipedia](https://en.wikipedia.org/wiki/Japanese_battleship_Yamato)).
- **Shokaku (carrier, illustrates IJN practice):** generator/switchboard knocked out → no pump power; excessive counterflooding flipped her from starboard to port heel ([combinedfleet](https://www.combinedfleet.com/shoksink.htm)).
- **Lützow:** pumps unusable because control rods jammed ([Wikipedia](https://en.wikipedia.org/wiki/SMS_Lützow)).

### 5.2 Organisation

**USN (post-1942):** Damage Control Central coordinating numbered area repair parties via sound-powered phones (Yorktown had Repair I–V + a gasoline party); after Yorktown/Lexington, mandatory DC and firefighting training from boot camp upward, salvage parties standard from June 1942, fire-retardant paints, better welding, portable pumps (160 lb portable, 500 lb mobile gasoline pumps), fog nozzles (Lt. Harold Burke, 260+ instructors trained), CO2 purging of gasoline lines ([USNI "Fighting for Survival"](https://www.usni.org/magazines/naval-history-magazine/2019/december/fighting-survival); [pwencycl DC](http://pwencycl.kgbudge.com/D/a/Damage_Control.htm)). Material conditions of readiness (X-Ray / Yoke / Zebra) label every door, hatch and fitting by when it must be closed ([DC Museums](http://www.damagecontrolmuseums.org/presentations/DCRS1-7.pdf); WWII introduction date unverified). Liquid loading diagrams and list-correction procedures (NC's 6-minute correction) show the drilled approach.

**IJN:** responsibility divided between chief engineer and deck officer; "damage control teams were drawn from men who normally had other duties"; difficulty repairing multicore cables ([pwencycl DC](http://pwencycl.kgbudge.com/D/a/Damage_Control.htm)). Ship designs nevertheless had large counterflooding capacity (Yamato 18.3° correction).

**RN:** Pre-war ships designed with good passive protection, but PoW shows electrical power dependence and limited pump capacity; WWI lessons (Audacious) produced more bilge pumps and duct valves.

> **MODEL NOTE (DC):** Crew-quality parameter `DC_skill` (0–1) and nation presets (e.g. USN 1943+ high, IJN low-mid, RN mid, KM mid-high). Mechanics:
> - **Counterflood action:** each tick can move up to `C_rate` t/min (design value ∝ displacement; NC ~80 t/min fitted from 480 t in 6 min — derived) into designated opposite-side tanks; reduces heel, increases total flooded mass (lower freeboard, lower speed); flooding TDS voids lowers that side's TDS rating.
> - **Pumping:** `P_rate` t/min needs electrical/steam power; generators are discrete components (located in machinery spaces and aft auxiliary rooms) — losing them cuts pumping, turret power and ventilation (PoW, Shokaku, South Dakota).
> - **Closure discipline:** state "Cruising / Battle" changes bulkhead leak rates.
> - **Overcorrection risk:** low DC_skill adds noise to counterflood amount (Shokaku flop).
> - **Bulkhead shoring:** reduces bulkhead failure chance over time for compartments adjacent to floods.

---

## 6. Example ship table

Thickness = maximum in citadel. "WT comp." = main watertight compartments unless stated. TDS rating in TNT equivalent.

| Ship (year) | Displ. (t) | Main belt | Armour deck(s) | WT compartments | TDS depth / rating | Notes |
|---|---|---|---|---|---|---|
| Majestic (1895) | ~16,000 (full) | 9 in Harvey, 220 ft long | 3 in flat / 4 in slopes / 2.5 in ends | 72 in citadel + 78 outside (HMS Mars) | coal bunkers | [Wiki](https://en.wikipedia.org/wiki/Majestic-class_battleship) |
| Formidable (1898) | 14,500–15,900 | 9 in Krupp; 3 in fwd/1.5 in aft | 1 in upper; 2 in flat / 3 in slope | — | coal bunkers | Sunk by 1 torpedo 1915 · [Wiki](https://en.wikipedia.org/wiki/Formidable-class_battleship) |
| Dreadnought (1906) | ~18,000 (approx.) | 11 in (7 in lower edge); 8 in upper | 0.75–1 in main; 1.75 in flat / 2.75 in slope middle | — | 2–4 in bulkheads at magazines only | [Wiki](https://en.wikipedia.org/wiki/HMS_Dreadnought_(1906)) |
| Nassau (1908) | — | 290–300 mm | 38 mm flat / 58 mm slopes | 16 (sisters 19); DB 88 % L | 30 mm torpedo bulkhead | [Wiki](https://en.wikipedia.org/wiki/Nassau-class_battleship) |
| Kaiser (1911) | 24,724 / 27,000 | 350 mm; upper 203 mm | 30 mm centre; 61–102 mm ends | 17; DB 88 % L | 40 mm torpedo bulkhead | [Wiki](https://en.wikipedia.org/wiki/Kaiser-class_battleship) |
| Iron Duke (1912) | 25,000 / ~30,000 | 12 in → 4 in ends | 1–2.5 in | — | — | +820 t armour post-Jutland · [Wiki](https://en.wikipedia.org/wiki/Iron_Duke-class_battleship) |
| Derfflinger (1913) | 26,600 / 31,200 | 300 mm | 30–80 mm | ~17 (Lützow +1, unverified) | torpedo bulkhead (≈45 mm, unverified) | 17 heavy hits at Jutland, survived · [Wiki](https://en.wikipedia.org/wiki/SMS_Derfflinger) |
| Nevada (1914) | 27,500 / 28,400 | 13.5 in, 17.4 ft high | 3 in + 1.5 in splinter | — | none at build; bulges 1927–30 | First AoN · [Wiki](https://en.wikipedia.org/wiki/Nevada-class_battleship) |
| Hood (1920) | 46,680 deep | 12 in @12°, 7 in mid, 5 in upper | multiple 1–3 in decks | — | 7.5 ft bulge with crushing tubes | Magazine explosion 1941 · [Wiki](https://en.wikipedia.org/wiki/HMS_Hood) |
| Nelson (1927) | — | 14/13 in internal @18° | 6.25 in mags / 3.75 in machinery | — | 12 ft / 750 lb | First British AoN · [Wiki](https://en.wikipedia.org/wiki/Nelson-class_battleship) |
| KGV (1940) | 38,030 std / 45,360 full | 14.7 / 13.7 in, 23.5 ft high | 5.88 in mags / 4.88 in mach. (+1.25 in weather) | — | ~13 ft (+8 ft aux) / 1,000 lb | PoW lost via shaft · [Wiki](https://en.wikipedia.org/wiki/King_George_V-class_battleship_(1939)) |
| North Carolina (1941) | 35,000 std / 45,280 (at hit) | 12 in @15° | 1.45 + 5 in + 0.62–0.75 in | — | 18.5 ft / 700 lb; triple bottom 5.75 ft | Armour 41 %; I-19 hit 970 t · [Wiki](https://en.wikipedia.org/wiki/North_Carolina-class_battleship) |
| South Dakota (1942) | — | 12.2 in internal @19°, lower belt to bottom | 1.5 + 5.75–6.05 + 0.625 in | — | 17.9 ft / 700 lb | [Wiki](https://en.wikipedia.org/wiki/South_Dakota-class_battleship_(1939)) |
| Iowa (1943) | ~48,000 std (approx.) | 12.1 in @19° (to 1.62 in at bottom) | 1.5 + ~6 + 0.625 in | — | 17.9 ft / 700 lb | Armour 17,056 t = 35 % · [pwencycl](http://pwencycl.kgbudge.com/I/o/Iowa_class.htm) |
| Bismarck (1940) | ~50,000 full (approx.) | 320 mm; 145 mm upper | 50 mm upper; 80/95–100 mm flat, 110–120 mm slope | 22; DB 83 % L | 5.5 m; 45 mm bulkhead | Armour 19,082 t ≈ 40 % · [kbismarck](https://www.kbismarck.com/proteccioni.html) |
| Richelieu (1940) | — | 327–330 mm @15°24′ | 150/170 mm main; 40/50 mm lower | — | 7 m (Jean Bart 8.5 m) | Ébonite mousse fill · [navypedia](https://www.navypedia.org/ships/france/fr_bb_richelieu.htm) |
| Littorio (1940) | — | 70 mm + 280 mm spaced, 11–15° | 150 mm (mags inboard) / 100 mm (mach.) | — | Pugliese drum 3.8 m (2.28 m at turrets) / 350 kg | [Wiki](https://en.wikipedia.org/wiki/Littorio-class_battleship) |
| Yamato (1941) | 69,100 trial / 72,809 full | 410 mm @20°; 200 mm lower | 200–230 mm | 1,147 total (1,065 below armour deck) | 5.1 m / 400 kg | Armour 23,500 t = 33.1 %; citadel 53.5 % L · [USNI](https://www.usni.org/magazines/proceedings/1953/october/design-and-construction-yamato-and-musashi) |

---

## 7. Consolidated parametric model sketch (from L, B, D, Cb, armour inputs)

1. **Citadel length** `L_cit = clamp(0.50–0.70)·L`, driven by turret count/spacing and machinery length (auto-layout). Cost: belt and deck weight ∝ L_cit.
2. **Compartments:** main transverse bulkheads every ~0.055 L (~15–22 total); within citadel snap to magazine/boiler/engine boundaries. Options: centreline machinery bulkhead (yes/no), bottom layers (1–3).
3. **Vertical zones:** below armour deck (subdivided, "raft"), between armour deck and upper deck (soft), superstructure (no buoyancy). Armour deck height = top of belt (flat-high) or ~WL with slopes (turtleback).
4. **Belt:** thickness t, inclination θ, height (above/below WL), optional lower belt taper, optional end belts (incremental) — weight computed.
5. **TDS:** depth = k·B amidships (k chosen by player 0.10–0.22, eating internal volume/boiler room width), tapered at citadel ends; layers & liquid loading; era-based joint strength.
6. **Flooding sim:** per compartment volume × permeability; flood rate ∝ hole area × √(head); spread via bulkhead leak rates; above-armour-deck spread fast; trim/heel from mass moments; capsize when heel > ~20–30° (Yamato design 20°, limit ~30°) or freeboard at deck edge ≤ 0.
7. **Critical components:** magazines (catastrophic loss if penetrated + fire), generators (pumps/power), shafts (whip leak propagation), rudders (jam), boilers/engines (speed), fire control/comms above armour deck (AoN weakness).
8. **DC layer:** counterflood rate, pump rate (needs power), crew skill, closure state.

### Key numeric anchors for tuning
- Single torpedo vs modern TDS amidships: ~500–1,500 t flooding, list 3–6°, correctable.
- Single torpedo near end turrets/aft: ~1,000–3,000 t, possible magazine flooding, possible rudder/shaft loss.
- Heavy shell through unarmoured bow at speed: 1,000–2,000 t (Bismarck) up to progressive 8,000 t (Lützow) if not controlled.
- Loss thresholds observed: PoW ~4 torpedoes (+shaft cascade); Yamato ~11 torpedoes one side; Musashi ~19 torpedoes both sides; Seydlitz survived 5,308 t; Lützow lost at ~8,000 t (≈ 25–30 % of displacement) (derived approx.).

---

## Sources (main)

- NavWeaps: [Torpedo Defense Systems of WWII](https://www.navweaps.com/index_tech/tech-047.php); ["All or Nothing" Protection](https://www.navweaps.com/index_tech/tech-070.php); [Underwater Projectile Hits](http://navweaps.com/index_tech/tech-041.php)
- Okun, [Armor Protection of KM Bismarck](https://www.combinedfleet.com/okun_biz.htm)
- [kbismarck.com – Bismarck armour protection](https://www.kbismarck.com/proteccioni.html)
- Naval Gazing: [Flooding](https://www.navalgazing.net/Survivability-Flooding), [Underwater Protection 1](https://www.navalgazing.net/Underwater-Protection-Part-1), [Underwater Protection 2](https://www.navalgazing.net/Underwater-Protection-Part-2), [Armor 3](https://www.navalgazing.net/Armor-Part-3)
- USN: [War Damage Report 61, North Carolina](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-north-carolina-bb55-war-damage-report-no-61.html); [Summary of War Damage 1941–42](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/summary-of-war-damage-17-oct-1941-to-7-dec-1942.html)
- Garzke, Dulin, Denlay et al., [Death of a Battleship: Loss of HMS Prince of Wales (2012 update)](https://pacificwrecks.com/ship/hms/prince-of-wales/death-of-a-battleship-2012-update.pdf)
- [USNI Proceedings 1953 – Design and Construction of Yamato and Musashi](https://www.usni.org/magazines/proceedings/1953/october/design-and-construction-yamato-and-musashi); [USNI Naval History 2019 – Fighting for Survival](https://www.usni.org/magazines/naval-history-magazine/2019/december/fighting-survival)
- [Pacific War Online Encyclopedia – Iowa class](http://pwencycl.kgbudge.com/I/o/Iowa_class.htm), [Damage Control](http://pwencycl.kgbudge.com/D/a/Damage_Control.htm)
- [navypedia – Richelieu](https://www.navypedia.org/ships/france/fr_bb_richelieu.htm); [combinedfleet – Shokaku sinking](https://www.combinedfleet.com/shoksink.htm); [dionysus.biz – TDS estimates (amateur)](https://dionysus.biz/torpedodefense.html)
- Wikipedia class/ship pages linked inline throughout.
