# 03 — Smaller Warships: Layout, Subdivision, Protection and Damage Behaviour (c.1890–1945)

Research base for the damage model of a top-down 2D naval game with a parametric ship generator. Scope: protected and armoured cruisers, light and heavy cruisers, torpedo boats and TBDs, destroyers, escorts, coastal forces (MTB/PT/S-boat/MAS/G-5), and a short section on submarines.

**Conventions.** Sources are cited inline. **[UNCERTAIN]** marks a figure from a weak or secondary source, or one I could not confirm. **[INFERRED]** marks my own interpretation (layout fractions, design rules), not a sourced number. "Std" means standard displacement and "FL" means full load. "WT" means watertight. "MODEL NOTE" paragraphs are suggestions for the game, not history.

---

## 0. Cross-cutting findings (read this first)

1. **How small ships die is decided by flooding of adjacent main compartments and loss of longitudinal strength, more than by armour penetration.** In the USN's own analysis, destroyers were designed as "four-compartment ships", meaning four adjacent main compartments between main transverse bulkheads could flood freely. In practice the upper limit of flooding was "somewhat greater than two machinery spaces for the smaller classes, and somewhat greater than three machinery spaces for the larger" ([USN Destroyer Report – Torpedo & Mine](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-torpedo-mine-damage.html); [USN Destroyer Report – Gunfire, Bomb, Kamikaze](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-gunfire-bomb-kamikaze-damage.html)).
2. **One torpedo is usually fatal to a destroyer-size ship.** Of 31 USN destroyers torpedoed, only 7 survived. Of 8 that were mined, 5 survived ([USN DD Torpedo/Mine report](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-torpedo-mine-damage.html)).
3. **Gunfire, bombs and kamikazes were survivable far more often.** Of 192 cases, 162 destroyers survived (84%). Of 95 destroyers hit by kamikazes or Baka bombs, only 13 (13.7%) sank. Causes of the 30 losses: 14 from flooding, 6 from structural failure (jack-knifed or sagged by the stern), and 5 from magazine explosion ([USN DD Gun/Bomb/Kamikaze report](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-gunfire-bomb-kamikaze-damage.html)).
4. **Breaking in two ("broken back") is a distinct and common failure mode for long, thin hulls.** Examples:
   - BRISTOL broke in two about 4 minutes after a torpedo hit.
   - STRONG broke in two after 39 minutes.
   - BEATTY failed structurally after 4 h 20 min.
   - MEREDITH broke in two about 29 hours after being mined.
   - HAMBLETON survived with her section modulus cut to about 15% of intact. Stresses reached about 22 tons/sq in, the yield point of HTS.
   
   (Source for all: [USN DD Torpedo/Mine report](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-torpedo-mine-damage.html).)
5. **Ends can be lost and the ship can survive.** This applies to destroyers (CHEVALIER and SELFRIDGE lost bows; ABNER READ and FOOTE lost sterns; same report) and to cruisers (New Orleans, Minneapolis, Pittsburgh; §2.6). A hit outside the midship machinery block is far less lethal than one in it.
6. **Immediate magazine explosion is rare, but delayed explosion after fire is not.** Only 1 USN destroyer blew up at once when struck. In 5 more, fire reached the magazines later ([USN DD Torpedo/Mine report](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-torpedo-mine-damage.html)).
7. **Fuel type matters at the small end.** Petrol boats (PT, MTB, CMB, MAS, G-5) burn and explode. Diesel S-boats did not have that problem (§5).

### Threat reference: underwater warhead sizes

The USN report lists these warheads as encountered:

| Weapon | Charge |
|---|---|
| German standard torpedo | 660 lb hexanite (≈ 860 lb TNT equivalent) |
| German "Curly" and acoustic torpedoes | 590 lb hexanite |
| German aircraft torpedoes | 400–470 lb |
| Japanese Type 93 (24-in) | ≈ 1,086 lb |
| Japanese Type 90 | ≈ 880 lb |
| Japanese aircraft torpedoes | 338–812 lb |
| German moored contact mines | 330–660 lb |
| German ground mines | 660–1,850 lb |
| Japanese mines | 121–550 lb |

Source: [USN DD Torpedo/Mine report](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-torpedo-mine-damage.html).

---

## 1. Protected and armoured cruisers (c.1885–1910)

### 1.1 The protected cruiser scheme

- **Armoured deck instead of a belt.** The armour is a full-length deck. It is flat amidships, set roughly at the waterline, and its sides slope down to below the waterline at the ship's side. Engines, boilers and magazines sit beneath it. Shells reach the deck at a very oblique angle, so a thin deck works ([Wikipedia – Protected cruiser](https://en.wikipedia.org/wiki/Protected_cruiser)).
  - *Esmeralda* (1883) had a full-length deck up to 2 in (51 mm) on the slopes and a cork-filled cofferdam along the sides.
- **Slope thicker than the flat.** USS *Olympia* (1892) had a 2 in flat deck. The slopes were 4.75 in amidships and 3 in at the ends, with a 4 in glacis around the engine-room hatches ([Wikipedia – USS Olympia](https://en.wikipedia.org/wiki/USS_Olympia_(C-6))).
  - Small ships used very thin decks. The *Montgomery* class (2,000 t) had 5/16 in (8 mm) on the flat and 7/16 in (11 mm) on the slope ([Wikipedia – Montgomery class](https://en.wikipedia.org/wiki/Montgomery-class_cruiser)).
- **Coal bunkers as armour.** Bunkers ran along the sides above and beside the slopes, so coal absorbed splinters and shell bursts. *Olympia* carried up to 1,169 short tons of coal. "Coal-protected" was a contemporary term. As coal was burned, the protection fell. **MODEL NOTE:** let side protection over machinery scale with remaining coal on coal-fired ships.
- **Cofferdams with cellulose.** A waterline belt of compartments (in the US, a "Woodite"/cellulose cofferdam about 3 ft 11 in high on *Montgomery*) was packed with compressed coconut-husk cellulose. The material swelled when wet and self-sealed shot holes.
  - Material: about 1 part fibre to 14 parts cellulose, compressed to half volume, density about 0.12.
  - Horten test, 1890: an 8 ft × 3 ft 4 in cellulose belt was hit by three 6-inch shells, leaving 14×8 in and 11×10 in holes. The first water came through after 6, 19 and 38 minutes. After an hour the leak had settled at about 2 gal/min for all three holes together.
  - Users: France, Russia, Netherlands, Greece, Denmark, Norway, Japan and the USN.
  - Source: [USNI Proceedings 1892 – "Cellulose and its Application as a Protection to Vessels"](https://www.usni.org/magazines/proceedings/1892/april/cellulose-and-its-application-protection-vessels).
- **Gun protection** was shields and light turrets. *Olympia* had 3.5 in Harvey turrets, 4.5 in barbettes, 4 in shields on the 5-in guns, and a 5 in conning tower.

**Subdivision in words [INFERRED from the descriptions above]:**
- Below the protective deck: magazines forward and aft at about 0.15–0.30 L and 0.70–0.85 L, with boiler and engine rooms between them (about 0.30–0.70 L).
- Above the deck at the waterline: a cellular layer (cofferdam plus bunkers) along the sides.
- The ends forward and aft of the magazines are unprotected and finely subdivided.

**Key vulnerabilities:**
- Flooding above the protective deck. A holed waterline lets water spread across the flat deck, which costs stability even though the vitals are intact.
- Unprotected guns and crews.
- Underwater torpedo hits, because the deck gives no underwater protection.

### 1.2 Armoured cruisers

- **Belt plus deck.** These ships added a waterline belt, usually tapered at the ends, to the protective deck. Krupp and Harvey cemented armour (mid-1890s onward) made a light but useful belt possible ([Wikipedia – Armored cruiser](https://en.wikipedia.org/wiki/Armored_cruiser)).
- **Typical belts:**
  - *Cressy* class: 6 in Krupp.
  - *Pennsylvania* class: 6 in belt, 6.5 in turrets, 9 in conning tower.
  - *Léon Gambetta*: up to 150 mm.
  - *Edgar Quinet*: up to 170 mm.
  - Around 4 in was thought enough against quick-firing guns in the mid-1890s.
- **Demonstrated weaknesses:**
  - At Jutland, *Defence*, *Warrior* and *Black Prince* were destroyed by 11–12 in fire. Their belts were inadequate and they were too slow to escape.
  - *Aboukir*, *Hogue* and *Cressy* were all sunk by U-9 on one day in 1914. Belts do nothing underwater.
  - Capped AP shells defeated Harvey and Krupp plate (same source).

**MODEL NOTE:**
- Model the protected cruiser as **an armoured deck layer plus side "cellular" buffer HP** (bunkers and cofferdam) above vitals.
- Model the armoured cruiser as **belt + deck + unarmoured ends**.
- Both should be very vulnerable to torpedoes: no torpedo-defence system and roughly 10–15 main transverse compartments **[UNCERTAIN, not sourced per class]**.

---

## 2. Light and heavy cruisers (WWI – WWII)

### 2.1 WWI light cruisers: belt as hull structure

The British *Arethusa* (1913) had a 1–3 in waterline belt and a 1 in deck on 3,512 t normal displacement, with eight Yarrow boilers, four shafts and 28.5 kn ([Wikipedia – Arethusa class 1913](https://en.wikipedia.org/wiki/Arethusa-class_cruiser_(1913))). On these ships the "belt" was high-tensile plating that also formed part of the hull's strength. It was not bolted-on armour **[detail on HT-plating-as-structure from general literature; not verified in the cited page]**.

### 2.2 The treaty cruiser problem

The Washington Treaty capped cruisers at 10,000 tons standard with 8-in guns. Designers had to pick between speed, armament and armour. The early treaty ships were thinly protected, with "tin-clad" or splinter-proof turrets, and some quietly exceeded the limit.

**Japanese heavy cruisers:**
- *Takao* class: 102 mm machinery belt; 127 mm magazine belt tapering to 38 mm; main deck 37 mm max; bulkheads 76–100 mm; **turrets only 25 mm**. Machinery was 12 Kampon boilers and 4 shafts (132,000 shp). Std 11,350 t (well over the treaty limit), 203.8 m ([Wikipedia – Takao class](https://en.wikipedia.org/wiki/Takao-class_cruiser)).
- *Mogami* class: 100 mm belt (140 mm at magazines); 35 mm deck; 25 mm turrets; 127 mm magazine protection. Officially 8,500 t std; actual trial displacement 11,169 t, and over 13,000 t after rebuild ([Wikipedia – Mogami class](https://en.wikipedia.org/wiki/Mogami-class_cruiser)).
- *Furutaka*: 76 mm belt and 35 mm deck, intended only against 6-in shells. Overweight conditions partly submerged the belt ([Wikipedia – Furutaka](https://en.wikipedia.org/wiki/Japanese_cruiser_Furutaka)).

**Italian heavy cruisers:** *Zara* class was the best-protected treaty cruiser. Belt 150 mm at the waterline tapering to 100 mm; deck 70 mm; turrets and barbettes 150 mm; conning tower 150 mm sides and 80 mm roof. Two shafts, eight boilers, 95,000 shp. Std 11,326–11,712 t, so substantially over the limit. Crew 841 ([Wikipedia – Zara class](https://en.wikipedia.org/wiki/Zara-class_cruiser)).

**German heavy cruisers:** *Admiral Hipper* class.
- Belt 80 mm amidships and 70 mm aft. Upper deck 30 mm. Main armoured deck 20–50 mm. Turret faces 105 mm and sides 70 mm.
- **Fourteen watertight compartments, with a double bottom along 72% of the keel length.**
- Three shafts, 132,000 shp. 16,170 t design displacement and 18,200 t FL; 202.8 m; crew 1,382–1,600.
- Source: [Wikipedia – Admiral Hipper class](https://en.wikipedia.org/wiki/Admiral_Hipper-class_cruiser).

**US heavy cruisers:**
- *New Orleans* class: belt 3–5 in, deliberately shortened so it could be thicker over machinery. Deck 1.25–2.25 in. Turret faces 8 in (the first US cruiser turrets proof against 8-in fire). Barbettes 5 in (6.5 in on *San Francisco*).
  - Magazines were **"box" protected deep below the waterline with about 4 in sides**, plus splinter belts and the armour deck. This was good against shellfire but put the magazines where torpedoes strike, as Tassafaronga showed (§2.6).
  - 9,950 t std / 12,463 t loaded; 588 ft; 8 boilers, 4 shafts, 107,000 shp; crew 708.
  - Source: [Wikipedia – New Orleans class](https://en.wikipedia.org/wiki/New_Orleans-class_cruiser).
- *Baltimore* class (unconstrained by treaty): belt 4–6 in; deck 2.5 in; turrets 1.5–8 in; barbettes 6.3 in; conning tower 6.5 in; transverse bulkheads 6 in. 13,600 t std / 17,000 t FL; 673 ft; 4 boilers, 4 shafts, 120,000 shp; crew 1,146 ([Wikipedia – Baltimore class](https://en.wikipedia.org/wiki/Baltimore-class_cruiser)).

**US light cruisers:**
- *Brooklyn* class: belt 5 in on 0.625 in STS at machinery, **but only 2 in at magazines** (the magazines were deeper and boxed). Deck 2 in. Barbettes 6 in. Turret face 6.5 in, sides 1.25 in, roof 2 in. 9,767 t std / 12,207 t FL; 608 ft; crew 868 ([Wikipedia – Brooklyn class](https://en.wikipedia.org/wiki/Brooklyn-class_cruiser)).
- *Atlanta* class (AA cruiser): belt 1.1–3.75 in; deck and turrets 1.25 in. 6,718 t std; 541 ft; 4 boilers, 2 shafts ([Wikipedia – Atlanta class](https://en.wikipedia.org/wiki/Atlanta-class_cruiser)).

**British light cruisers:** *Town* class / HMS *Belfast*. Belt 4.5 in (114 mm). Deck 3 in over magazines and 2 in over machinery. Turrets up to 4 in. Bulkheads 2.5 in. Four boilers and four shafts; 2,400 t fuel oil ([Wikipedia – HMS Belfast](https://en.wikipedia.org/wiki/HMS_Belfast)). The *Gloucester* sub-group added an intermediate armour layer over magazines and machinery and thicker turrets ([Wikipedia – Town class](https://en.wikipedia.org/wiki/Town-class_cruiser_(1936))).

### 2.3 Generic cruiser layout [INFERRED, consistent with the sources above]

- 0–0.08 L: forepeak, chain locker, stores. Unarmoured.
- 0.08–0.30 L: forward turrets, with magazines and shell rooms below in an armoured box (side plates plus crown). Belt or box ends at an armoured transverse bulkhead.
- 0.30–0.65 L: machinery. In US practice from *St. Louis*/*Helena* on, these were alternating fire rooms and engine rooms (the unit system). This block sits under the main belt and deck.
- 0.65–0.85 L: after turret(s) and magazine box.
- 0.85–1.0 L: steering gear, often with light splinter protection, then the stern.
- Hipper example: 14 main WT compartments over 202 m, so a mean spacing of about 14 m, or about 0.07 L.

### 2.4 Unit machinery

The *St. Louis* and *Helena* sub-group of the Brooklyn class introduced "a unit system of machinery that alternated boiler and engine rooms to prevent a ship from being immobilized by a single unlucky hit; this system would be used in all subsequent US cruisers" ([Wikipedia – Brooklyn class](https://en.wikipedia.org/wiki/Brooklyn-class_cruiser)).

Without a unit system, one hit can stop the ship. *Chōkai* was crippled by "a bomb down the stack, destroying her engine room" ([Wikipedia – Takao class](https://en.wikipedia.org/wiki/Takao-class_cruiser)). *Canberra* (CA-70) was immobilised by one aircraft torpedo in the engine room ([Wikipedia – Baltimore class](https://en.wikipedia.org/wiki/Baltimore-class_cruiser)).

### 2.5 Japanese cruiser torpedo hazard

Japanese cruisers carried oxygen-fuelled Type 93 torpedoes, about 1,080 lb warhead each, in deck mounts with reloads. When these mounts were hit, the explosions were catastrophic:

- **Furutaka**, Cape Esperance, 1942: about 90 shells hit her and "some ignited her Type 93 'Long Lance' torpedoes, starting fires". She sank after a destroyer torpedo flooded the forward engine room ([Wikipedia – Furutaka](https://en.wikipedia.org/wiki/Japanese_cruiser_Furutaka)).
- **Mikuma**, Midway, 1942: after bomb hits, "at 1358 several torpedoes explode, wrecking the catapult deck and the mainmast and blowing out a section of the hull below the waterline". About 700 killed ([combinedfleet TROM – Mikuma](https://www.combinedfleet.com/mikuma_t.htm)).
- **Suzuya**, Samar, 1944: "A near-miss to starboard detonates SUZUYA's No. 1 torpedo mount." The cascade continued at 1100 and wrecked the starboard engine rooms and No. 7 boiler room. The remaining torpedoes and ammunition exploded at about noon, and she sank at 1322 ([combinedfleet TROM – Suzuya](https://www.combinedfleet.com/suzuya_t.htm)). **A near miss alone set off the torpedoes.**
- *Takao* and *Atago* had 16 tubes in quadruple mounts with rapid reload. *Maya* was refitted with no reloads ([Wikipedia – Takao class](https://en.wikipedia.org/wiki/Takao-class_cruiser)).

**MODEL NOTE:** Give deck torpedo mounts their own "explosive store" component. Its detonation chance should depend on fire, splinters and near-miss blast, scaled by warhead type (oxygen torpedoes worse). Detonation should cause a hull breach below the mount.

### 2.6 Bow loss and broken keels in cruisers

- **Tassafaronga, 30 Nov 1942.**
  - *New Orleans*: a Type 93 hit set off the forward magazines. She lost "nearly one-third of the ship, including the bow" and had over 180 dead or missing. She steamed to Australia stern-first, was fitted with a coconut-log stub bow, and was rebuilt at Puget Sound ([National WWII Museum](https://www.nationalww2museum.org/war/articles/mystery-disembodied-bow-ironbottom-sound)).
  - *Minneapolis*: the bow folded down about 70° and was lost forward of frame 20; **three of four firerooms flooded**, yet she survived ([USN Summary of War Damage 1941–42](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/summary-of-war-damage-17-oct-1941-to-7-dec-1942.html)).
  - *Northampton*: two deep-running torpedoes, uncontrolled fires, ready-service ammunition detonating, five main compartments flooded. Lost (same source).
- **Pittsburgh (CA-72), Typhoon Viper, June 1945.** A 104 ft bow section broke off at poor plate welds. No casualties. She made 6 kn to Guam ([Wikipedia – USS Pittsburgh](https://en.wikipedia.org/wiki/USS_Pittsburgh_(CA-72))).
- **Belfast, Nov 1939.** A magnetic ground mine broke her keel and wrecked an engine and boiler room. One killed. Repairs took until November 1942 ([Wikipedia – HMS Belfast](https://en.wikipedia.org/wiki/HMS_Belfast)).
- **Fires and magazines at Savo, 1942.** *Astoria* had uncontrolled fires and a magazine explosion nine hours after the action. *Quincy* took at least 36 hits and burned. *Juneau* had already been torpedoed in the forward fireroom; a second, submarine torpedo made her "blew up and disappeared in approximately 60 seconds" ([USN Summary of War Damage 1941–42](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/summary-of-war-damage-17-oct-1941-to-7-dec-1942.html)).
- **Blücher, 1940.** Two shore-battery torpedoes started an uncontrollable fire, then a magazine explosion, then she capsized ([Wikipedia – Admiral Hipper class](https://en.wikipedia.org/wiki/Admiral_Hipper-class_cruiser)).

**MODEL NOTE for cruisers:**
1. Belt and deck layers cover only the "citadel" span (about 0.25–0.8 L). Ends are plain hull.
2. Magazines are boxed. A box hit by a torpedo or ground mine detonates far more easily than one hit by shellfire, because box crowns and sides are designed against shells.
3. Bow severance happens when a forward magazine detonates, or when structural damage exceeds a threshold forward of the first turret. The ship survives with reduced speed and heavy trim, and can only steam astern or slowly.
4. Unit vs non-unit machinery decides whether one machinery hit stops the ship.
5. Fire is a major killer: ready ammunition, aircraft gasoline, torpedoes.

---

## 3. Torpedo boats and TBDs of the 1880s–1900s

- **Torpedo boats.** The British "war scare" 125-footers (1885–87) were about 60 t, 125–128 ft × 12–14 ft. They had 700 ihp compound engines and **locomotive boilers**, and made 20.5 kn ([naval-encyclopedia – British torpedo boats](https://naval-encyclopedia.com/ww1/uk/british-torpedo-boats.php?amp=1)).
  - Construction: steel frames, light steel plating, coal along the hull flanks (doubling as informal protection), and machinery amidships. The conning tower was proof only against small arms and splinters.
  - Second-class torpedo boats "needed absolutely calm weather" (same source).
  - Austro-Hungarian *Schichau* class (1885–91): 39.9 m, 83–90 t, a single locomotive boiler (later two Yarrow boilers), one shaft, 19 kn, crew 16–18, two 14-in tubes. The 45 kg warhead had a 600 m range ([Wikipedia – Schichau class](https://en.wikipedia.org/wiki/Schichau-class_torpedo_boat)).
- **Torpedo-boat destroyers.**
  - *Havock* (1893): 275 t, 165 ft. *Daring*: 260 t, 185 ft, Thornycroft water-tube boilers, 27 kn. Armament one 12-pdr, three 6-pdr and three 18-in tubes. Hulls were "high-tensile steel only 1/8 in (3.2 mm) thick" ([Wikipedia – Torpedo boat destroyer](https://en.wikipedia.org/wiki/Torpedo_boat_destroyer)).
  - 27-knotters: about 260 t, about 200 ft, crew 46–53, coal-fired water-tube boilers ("initially, some had 'locomotive type' fire-tube boilers"), one 12-pdr, up to five 6-pdr, two 18-in tubes. The turtleback forecastle made them very wet forward ([Wikipedia – A class 1913](https://en.wikipedia.org/wiki/A-class_destroyer_(1913))).
  - 30-knotters: about 350 t (344–445), 209–215 ft, crew 62–68. 11 of 40 were lost ([Wikipedia – C class 1913](https://en.wikipedia.org/wiki/C-class_destroyer_(1913))).
- **Structural fragility.** HMS *Cobra* (about 450–470 t, turbine-driven) "broke her back" in heavy seas in 1901, about 150 ft from the bow between the two aft boilers. 67 died. The engines were 28 t over design weight ([Wikipedia – HMS Cobra](https://en.wikipedia.org/wiki/HMS_Cobra_(1899))). HMS *Viper* was wrecked six weeks earlier.

**Subdivision in words [INFERRED]:**
- Bow tube / forepeak: 0–0.15 L.
- Crew space.
- Boiler room(s) with side coal bunkers: about 0.3–0.55 L.
- Engine room: about 0.55–0.7 L.
- Officers' quarters and after tube aft.
- Roughly 6–10 transverse bulkheads **[UNCERTAIN]**.

**MODEL NOTE:** At about 100–400 t with 3 mm plating, any shell above about 37 mm passes through. A hit's effect is the compartment it bursts in (boiler: steam casualty, possible explosion; coal bunker: absorbs splinters). Hull-girder failure should be possible from heavy weather or a single heavy hit amidships.

---

## 4. Destroyers (WWI–WWII)

### 4.1 Hull and armour

- **No armour.** "The plating throughout a destroyer is so light that it is readily penetrated by thin-walled shells or bombs and by fragments" ([USN DD Gun/Bomb report](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-gunfire-bomb-kamikaze-damage.html)).
- **Plating thickness.** Commonly cited figures for Fletcher are about 0.5 in on the deck, 0.5–0.75 in (13–19 mm) on the upper side shell, and 0.5 in splinter plating on the gun houses **[UNCERTAIN, gaming-forum citation of Friedman, not verified: [Steam discussion](https://steamcommunity.com/app/1280780/discussions/0/3053988173744435179/)]**. The game brief's assumed 6–12 mm range is plausible for WWI and interwar boats. TBDs were down to 3.2 mm.
- **HTS.** WWII USN destroyers used high-tensile steel. HAMBLETON's peak stress reached the HTS yield point of 22 tons/sq in ([USN DD Torpedo/Mine](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-torpedo-mine-damage.html)).
- **Japanese late-war simplification.** The *Tachibana* sub-class of *Matsu* used carbon steel only, a single bottom and a transom stern for mass production ([Wikipedia – Matsu class](https://en.wikipedia.org/wiki/Matsu-class_destroyer)).
- **British framing.** The J/K/N class introduced **longitudinal framing**, "extra strong longitudinals and weaker transverse frames" ([Wikipedia – J, K, N class](https://en.wikipedia.org/wiki/J,_K,_and_N-class_destroyer)).
- **Japanese hull weakness.** The *Fubuki* class had longitudinal-strength problems exposed by the 1935 Fourth Fleet typhoon. They were rebuilt with 40 t of ballast and lighter top-hamper ([Wikipedia – Fubuki class](https://en.wikipedia.org/wiki/Fubuki-class_destroyer)).

### 4.2 Machinery arrangement

| Arrangement | Examples | Consequence |
|---|---|---|
| Boiler rooms grouped forward, engine room(s) aft | Most WWI destroyers; Fubuki; Kagerō (3 boilers, 2 turbines); British Tribal (3 boilers) | One large hit amidships can stop the ship |
| Two boilers in **one** boiler room | British J/K/N | Shorter hull and single funnel, but "a single well-placed hit flooding both" adjacent large compartments gave "a total loss of boiler power" ([Wikipedia J/K/N](https://en.wikipedia.org/wiki/J,_K,_and_N-class_destroyer)) |
| **Alternating / unit ("split plant")**: FR1–ER1–FR2–ER2 | USN Benson/Gleaves, Fletcher (4 boilers, 2 turbines, 2 shafts), Sumner, Gearing | "Loss of one or two adjacent compartments would not disable the entire propulsion" ([Wikipedia – Benson](https://en.wikipedia.org/wiki/Benson-class_destroyer)) |

Split-plant results in action:
- JOHNSTON at Samar steamed at about 20 kn for two hours with her after turbines disabled.
- LA VALLETTE, torpedoed with the forward fireroom and engine room flooded, ran more than 4 hours on one shaft.

(Sources: [USN reports](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-gunfire-bomb-kamikaze-damage.html).)

### 4.3 Subdivision

- **Design standard.** USN destroyers were "four-compartment ships" (four adjacent main compartments floodable). Actual limits are in §0.
- **Bulkhead count.** The number of main WT transverse bulkheads is not published in these sources. A destroyer of 106–115 m with four-compartment standing implies roughly 12–16 main compartments **[INFERRED; the brief's "about a dozen" is consistent]**.
- **Typical Fletcher layout (2,050 t std / 2,500 t FL; 376.5 ft; crew 329) [INFERRED fractions]:**
  - 0–0.05 L: forepeak, chain locker.
  - 0.05–0.25 L: forward magazines and handling rooms under mounts 1–2, with berthing above.
  - About 0.25–0.30 L: bridge/CIC block above, fuel and store tanks below.
  - About 0.35–0.65 L: FR1, ER1, FR2, ER2 (the machinery block, about 30% of length), with fuel tanks in the double bottom and at the sides. Two quintuple torpedo mounts on the centreline above the machinery.
  - 0.65–0.85 L: after magazines under mounts 3–5, plus berthing.
  - 0.85–1.0 L: steering gear, depth-charge racks at the stern.
- **Torpedoes** were carried on deck. USN ships carried no reloads. Japanese ships carried reloads:
  - Kagerō: 8 tubes and 16 Type 93 torpedoes.
  - Fubuki: originally 9 tubes and 18 torpedoes, later cut to 3 reloads for the centre mount only.
  - Sources: [Wikipedia – Kagerō](https://en.wikipedia.org/wiki/Kager%C5%8D-class_destroyer); [Wikipedia – Fubuki](https://en.wikipedia.org/wiki/Fubuki-class_destroyer).
  - **MODEL NOTE:** reload lockers are a second explosive store.

### 4.4 Damage behaviour: cases

- **Bow lost, ship survived:**
  - HMS *Eskimo* (Tribal; 1,891 t std; 377 ft; 3 boilers, 2 shafts) had her bow blown off by a torpedo from Z2 at Narvik (12–13 April 1940; Wikipedia gives 12 April). After temporary repairs she reached Newcastle ([Wikipedia – HMS Eskimo](https://en.wikipedia.org/wiki/HMS_Eskimo_(F75))).
  - USS *Murphy* lost her bow section in a collision in 1943 and was rebuilt ([Wikipedia – Benson](https://en.wikipedia.org/wiki/Benson-class_destroyer)).
  - CHEVALIER and SELFRIDGE lost bows. CHEVALIER was lost after a mass detonation of 5-in projectiles. In SELFRIDGE the inrush of water put out the magazine fire almost at once ([USN DD Torpedo/Mine](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-torpedo-mine-damage.html)).
- **Half a ship survived:** IJN *Amatsukaze*, 16 Jan 1944. A torpedo between the first and second compartments set off the magazine and tore the ship in half. The forward section sank (80 killed); **the aft half floated for six days and was towed to Singapore** ([Wikipedia – Amatsukaze](https://en.wikipedia.org/wiki/Japanese_destroyer_Amatsukaze_(1939))).
- **Stern lost, ship survived:** ABNER READ (mine) and FOOTE ([USN DD Torpedo/Mine](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-torpedo-mine-damage.html)).
- **Torpedo amidships, survived:** HMS *Kelly*, hit amidships by S-31 on 9/10 May 1940. She was towed for four days at 3 kn under air and E-boat attack. Her survival was attributed to watertight workmanship: "a single defective rivet might have finished her" ([Wikipedia – HMS Kelly](https://en.wikipedia.org/wiki/HMS_Kelly_(F01))).
- **Flexural break-up:** BENHAM, bow destroyed forward of frame 14. Flexural vibration buckled the shell and longitudinals at frame 75 and she began to break up ([USN Summary 1941–42](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/summary-of-war-damage-17-oct-1941-to-7-dec-1942.html)).
- **Absorbing punishment:** AARON WARD (DM-34; Sumner hull) took six kamikazes and three large bombs, shipped 1,650 tons of water, and reached port ([USN DD Gun/Bomb](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-gunfire-bomb-kamikaze-damage.html)).
- **Fire leading to later magazine explosion:** CUSHING was abandoned and blew up from fires the next afternoon ([USN Summary 1941–42](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/summary-of-war-damage-17-oct-1941-to-7-dec-1942.html)).

### 4.5 Loss statistics

| Navy | Figure |
|---|---|
| USN (to Aug 1945) | 251 instances of damage from enemy action ([USN DD Gun/Bomb](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-gunfire-bomb-kamikaze-damage.html)). Fletcher class: 19 sunk and 6 not repaired, 17 of them Mar–Jul 1945 off Okinawa ([Wikipedia – Fletcher](https://en.wikipedia.org/wiki/Fletcher-class_destroyer)). |
| IJN | 105 in service Dec 1941, 43 at war's end; **129 lost**: aircraft 50, submarines 39, surface ships 26, miscellaneous 14 ([USNI Proceedings 1952](https://www.usni.org/magazines/proceedings/1952/january/japanese-destroyers-world-war-ii)). Kagerō: 18 of 19 lost; Fubuki: 22 of 24 lost. |
| RN | 1939–40 alone: 37 lost (bombs 14, submarine torpedo 6, mines 6, gunfire 6, ship torpedo 1, collision/accident 4) ([NavWeaps – British destroyer losses](https://www.navweaps.com/index_tech/tech-108.php)). J/K/N: 13 of 24 lost. |

### 4.6 MODEL NOTE: destroyers

- **Compartments.** Use about 12–16 transverse compartments with a "max N adjacent flooded" survival rule: N ≈ 2 machinery spaces plus a margin for 1,500 t ships, and about 3 for 2,000 t+ ships.
- **Hull-girder HP.** Track this separately. Damage amidships (0.35–0.65 L) erodes section modulus. Below about 15–25% remaining, roll a break-in-two chance over time, higher in a seaway. Hits at the ends cost much less girder HP, so bow or stern loss is survivable.
- **Plating.** Treat it as zero armour against anything at or above 20 mm. Splinter shields (about 13 mm) only stop fragments and MG fire.
- **Explosive stores:** forward and aft magazines, deck torpedo mounts and reload lockers, and depth charges at the stern. A depth charge set off by a stern hit should be a risk; this is common knowledge rather than sourced here.
- **Machinery.** A split-plant flag decides whether one hit can stop the ship.

---

## 5. Escorts: corvettes, frigates, DEs, sloops

- **Flower-class corvette.** Based on the whale-catcher *Southern Pride* and built to mercantile standards in small yards.
  - 925 t (1,015 t modified); 205 ft; crew 85.
  - **Single screw**: one 4-cylinder triple-expansion engine of 2,750 ihp, 2 boilers, 16 kn.
  - Armament: one 4-in gun and 40 depth charges (later 70, plus Hedgehog).
  - Losses: 33 of 294 lost — **22 torpedoed by U-boats**, 5 mined, 4 to aircraft.
  - Source: [Wikipedia – Flower class](https://en.wikipedia.org/wiki/Flower-class_corvette).
- **River-class frigate.** Twin screw, 2 boilers, VTE engines of 5,500 ihp (six ships had turbines of 6,500 shp), 20 kn. 1,370 t std / 1,830 t deep; 301 ft; crew 107+. Range 7,200 nm, about double a Flower. Ten lost to enemy action, all torpedoed by U-boats ([Wikipedia – River class](https://en.wikipedia.org/wiki/River-class_frigate)).
- **USN destroyer escort (John C. Butler class).** 1,350 t, 306 ft, crew 215, 2 boilers, 2 turbines, 2 shafts, 24 kn designed. *Samuel B. Roberts* at Samar: cruiser shells hit a boiler, cutting her to 17 kn, then hits from *Kongō* "knocked out her remaining engine" and she sank. 89 killed in battle ([Wikipedia – Samuel B. Roberts](https://en.wikipedia.org/wiki/USS_Samuel_B._Roberts_(DE-413))).

**Layout [INFERRED]:** Merchant-style hull. One boiler room and one engine room amidships (about 0.4–0.65 L). Small magazine forward. Depth-charge stowage aft. Fewer bulkheads than a destroyer.

**MODEL NOTE:** A single-screw escort has one shaft and one engine room, so any machinery hit means dead in the water. A twin-screw frigate or DE has a two-shaft redundancy flag. Escorts should die to one torpedo nearly always, matching the Flower and River loss modes. Low speed but a robust merchant hull: lower girder stress than a destroyer at similar size.

---

## 6. Coastal forces: MTB, PT, S-boat, MAS, G-5, Japanese

### 6.1 US PT boats (Elco 80 ft, Higgins 78 ft)

- **Elco 80 ft:** 80 ft 3 in × 20 ft 7 in; 51 t (61 t in 1945); crew 11 (1942) to 17 (1945) ([pt103.com specs](http://www.pt103.com/PT_Boat_Specifications.html)).
- **Hull.** Two layers of mahogany planking laid diagonally in opposite directions, with aircraft fabric in marine glue between them. On the Elco 77 ft the layers were 3/8 in above the chine and 3/8 + 7/16 in below.
  - Frames: 69 transverse frames. Frames 1–34 have laminated spruce/oak/mahogany bottoms; the rest are mahogany ([USN MTB Manual Pt 5](https://www.ibiblio.org/hyperwar/USN/ref/PT-Manual/MTBM-5.html)).
  - Higgins PT-658: 3/8 in spruce plus 3/4 in mahogany planking on 1.5 in mahogany frames spaced 15 in apart ([Oregon NRHP nomination, PT-658](https://heritagedata.prd.state.or.us/historic/index.cfm?do=main.loadFile&load=NR_Noms/12000602.pdf)).
- **Engines.** Three Packard 4M-2500 supercharged V-12 petrol engines (later 5M-2500), about 1,350–1,500 hp each, for 40+ kn clean. Fouled hulls often dropped below 30 kn ([USN MTB Manual](https://www.ibiblio.org/hyperwar/USN/ref/PT-Manual/MTBM-5.html); [GlobalSecurity](https://www.globalsecurity.org/military/systems/ship/pt.htm)). Each engine burned up to about 150 gal/hr ([PT-658 nomination](https://heritagedata.prd.state.or.us/historic/index.cfm?do=main.loadFile&load=NR_Noms/12000602.pdf)).
- **Fuel.**
  - Elco: 3,000 US gal of 100-octane aviation petrol in three tanks — a 1,300 gal centre tank and two 850 gal wing tanks — under the crew's day room amidships, just forward of the engine room. Range 259 mi at 35 kn ([pt103.com](http://www.pt103.com/PT_Boat_Specifications.html)).
  - Higgins: 3,000 gal in **two tank rooms, one forward and one aft of the engine room**. The forward room holds "two 800-gallon rubber-lined self-sealing" tanks, with similar capacity aft ([PT-658 nomination](https://heritagedata.prd.state.or.us/historic/index.cfm?do=main.loadFile&load=NR_Noms/12000602.pdf)). **So late-war PTs did have self-sealing tanks.**
- **Fire protection:** hand CO2 extinguishers plus an automatic Lux CO2 system with heat actuators in the tank and engine rooms ([USN MTB Manual](https://www.ibiblio.org/hyperwar/USN/ref/PT-Manual/MTBM-5.html)).
- **Subdivision (Higgins 78): "eight watertight compartments separated by built-up plywood bulkheads".** In order from the bow:
  1. Forepeak / chain locker
  2. Forward crew's quarters and galley
  3. Officers' wardroom
  4. Forward tank room
  5. Engine room
  6. Aft tank room
  7. Aft crew quarters
  8. Lazarette / rudder room
  
  (Source: [PT-658 nomination](https://heritagedata.prd.state.or.us/historic/index.cfm?do=main.loadFile&load=NR_Noms/12000602.pdf).) The Elco order was similar: forward bulkheads 1–3, crew's quarters, officers' quarters, tank compartment, engine room, lazarette ([MTB Manual](https://www.ibiblio.org/hyperwar/USN/ref/PT-Manual/MTBM-5.html)).
- **Armour.** Essentially none. The PT-658 deckhouse was plywood. Some units added improvised plating **[not sourced]**.
- **Armament.** Four 21-in torpedoes (Mk 8 in tubes early, later Mk 13 on roll-off racks). Late-war boats added a 40 mm, 20 mm, twin .50s, a 37 mm and rockets ([GlobalSecurity](https://www.globalsecurity.org/military/systems/ship/pt.htm)).
- **How they died.**
  - PT-109 was cut in two by *Amagiri*, and "a fireball of exploding aviation fuel 100 feet (30 m) high" lit the sea. The forward hull stayed afloat on its watertight compartments and wooden buoyancy for about 12 hours. 2 were killed ([Wikipedia – PT-109](https://en.wikipedia.org/wiki/Patrol_torpedo_boat_PT-109)).
  - Overall losses: 69 of 531 in service — 26 to enemy action and 43 to accidents, friendly fire or sea conditions ([bricep.net stats](https://www.bricep.net/PTBoats/stats.htm); figure also in [naval-encyclopedia](https://naval-encyclopedia.com/ww2/us/pt-boats.php)).
  - Shells passing through wooden hulls without fuzing: reported anecdotally, e.g. naval-encyclopedia says shells "passed through without exploding" **[UNCERTAIN, secondary source]**. The physics is sound: thin wood gives too little resistance to trigger many base or impact fuzes.

### 6.2 British boats: CMB, Vosper and Fairmile D

- **Thornycroft CMB (WWI).** The 40 ft boat (5.1 t, mahogany plank-on-frame) carried one torpedo. The 55 ft boat (750–900 hp) carried two. Aircraft petrol engines (Sunbeam, Napier) gave 35–41 kn.
  - The torpedo was carried in a stern trough and pushed out tail-first by a cordite ram.
  - 16 lost in WWI. "At least two unexplained losses due to fires in port are thought to have been caused by a build-up of petrol vapour igniting."
  - Source: [Wikipedia – Coastal motor boat](https://en.wikipedia.org/wiki/Coastal_motor_boat).
- **Vosper 70–73 ft MTB.** 44.5–48.75 t; three Packard engines of 1,400 hp each; 40 kn; crew 13. Type I had four 18-in tubes. **"Armour plate around the bridge"** ([Wikipedia – Vosper 73 ft](https://en.wikipedia.org/wiki/Vosper_73_ft_motor_torpedo_boat)).
- **Fairmile D ("Dog boat").** 115 ft × 20 ft 10 in; 90 t std / 107 t FL; four Packard 4M-2500 (5,000 hp); 29 kn; crew 21.
  - Fuel: about 5,000 gal of 100-octane, rising to 8,000 gal with Mediterranean deck tanks. Hull pre-fabricated in wood. Range 2,000 nm economical.
  - Source: [Wikipedia – Fairmile D (MGB 606 article)](https://en.wikipedia.org/wiki/Fairmile_D_motor_torpedo_boat).

### 6.3 German S-boats (Schnellboote)

- **Hull.** Wooden planking over light-alloy frames, with a round bilge that made them better sea-boats than hard-chine Allied craft. The S-26 type was 34.94 m × 5.38 m and about 112 t FL, with a crew of 21–24 ([Wikipedia – E-boat](https://en.wikipedia.org/wiki/E-boat)).
- **Subdivision.** "Nine watertight compartments … made of 4 mm steel below the waterline and slightly thinner light metal alloy above" **[UNCERTAIN, blog source: [WW2 in Review](https://worldwar2inreview.blogspot.com/2025/06/german-schnellboot-fast-attack-craft-s.html)]**.
- **Engines.** Three Daimler-Benz diesels:
  - MB 501 (V-20): 1,500 hp continuous / 2,000 hp max.
  - MB 511 (supercharged): 2,500 hp max.
  - MB 518: up to about 3,000 hp.
  - Fuel consumption about 0.37–0.40 lb/hp/hr ([Old Machine Press](https://oldmachinepress.com/2017/03/05/mercedes-benz-500-series-diesel-marine-engines/)).
  - Speed: S-26 about 39–43.5 kn, briefly 48 ([Wikipedia – E-boat](https://en.wikipedia.org/wiki/E-boat)).
- **Why diesel mattered:**
  1. Diesel fuel does not form explosive vapour the way 100-octane petrol does, so there is far less fire and explosion risk.
  2. Range of 700–750 nm, versus about 260 mi at speed for an Elco.
  
  Early boats used petrol; MAN and then Daimler-Benz diesels replaced it ([Wikipedia – E-boat](https://en.wikipedia.org/wiki/E-boat); [naval-encyclopedia S-boote](https://naval-encyclopedia.com/ww2/germany/s-bootes.php)). Fuel was about 11,640–15,000 L depending on source **[figures differ]**.
- **Armour.** From 1943 the "Kalotte" partially armoured bridge cupola gave small-arms protection ([Wikipedia – E-boat](https://en.wikipedia.org/wiki/E-boat)).
- **Armament.** Two bow 533 mm tubes with reloads (four torpedoes total). Guns grew from 20 mm to 37 mm and 40 mm. The S-701 type had four tubes.
- **Durability.** S-105 came home in March 1942 "riddled by 80 shell fragments, bullets and shell holes" ([naval-encyclopedia](https://naval-encyclopedia.com/ww2/germany/s-bootes.php)).
- **Losses.** Roughly 130+ lost or disposed of:
  - aircraft about 45, including the Le Havre raid of 14 June 1944, which destroyed 14–16 boats;
  - scuttled about 25;
  - surface action about 20;
  - mines about 15;
  - collisions about 10;
  - other about 15.
  
  Source: [s-boot.net losses](http://www.s-boot.net/englisch/sboats-kriegsmarine-Losses.html) **[approximate, from summary]**.

### 6.4 Italian MAS, Soviet G-5 and Japanese boats

- **MAS.**
  - Wooden hulls, 20–30 t, crew about 10, two 450 mm torpedoes. WWII engines were Isotta Fraschini ASM 184 petrol units of 1,500 hp, for up to 45 kn.
  - Greatest success: MAS 15 sank the battleship *Szent István*, 10 June 1918.
  - Source: [Wikipedia – MAS](https://en.wikipedia.org/wiki/MAS_(motorboat)).
- **Soviet G-5 (Tupolev).**
  - **Duralumin hull** with galvanic-corrosion trouble: boats could stay in the water only 5–7 days in summer.
  - Series 10: 19 m, 16.3 t, two GAM-34BS aero engines of 850 bhp, 53 kn, minimum practical speed 18 kn. Fuel about 1,600 kg; crew 6–7.
  - **Two 533 mm torpedoes in stern troughs**, ejected backward. Minimal armour.
  - Losses: 73 of about 300 lost in action.
  - Source: [Wikipedia – G-5](https://en.wikipedia.org/wiki/G-5-class_motor_torpedo_boat).
- **Japanese T-1 type gyoraitei (1941).** About 20 t, wooden hull, crew 7, two 450 mm torpedoes. Of the six boats, all but one were lost by 1943 ([War Thunder wiki history section](https://wiki.warthunder.com/unit/jp_type_t1_1941)) **[UNCERTAIN, game-wiki source; lengths and engines not confirmed]**.

### 6.5 MODEL NOTE: coastal forces

- **Size threshold.** Below about 150 t, drop armour and belt modelling entirely and use a small compartment strip (about 6–9 compartments). The Higgins order is a good template: forepeak, crew, wardroom, tank, engine, tank, crew, lazarette.
- **Fuel-type flag** (petrol vs diesel). For petrol, any hit in the tank or engine compartments rolls fire. A fire has a chance of vapour explosion, which destroys the boat or cuts it in half (PT-109). Self-sealing tanks (late PT) cut leak and fire chance. For diesel (S-boat), fire chance is much lower.
- **Wooden hull.** Large-calibre HE may over-penetrate without detonating; give a "pass-through" chance scaled by shell fuze sensitivity. Damage is then small holes, low flooding per hit, and the wreck floats on wooden buoyancy for hours.
- **Light-alloy or duralumin hull (G-5).** Same behaviour, but with a corrosion "readiness" stat (optional).
- **Crew and gun exposure.** Small-arms and 20–40 mm fire kills crew and guns, so crew casualty modelling matters more than hull HP at this size. A bridge armour toggle covers the Vosper plate and the S-boat Kalotte.

---

## 7. Submarines (brief)

- **Hull layout.** The USN fleet boat had a **partial double hull**: an inner pressure hull wrapped by an outer hydrodynamic hull. Fuel and ballast tanks sit in the space between them ([Wikipedia – Gato class](https://en.wikipedia.org/wiki/Gato-class_submarine)). The Type VII U-boat put its main ballast tank inside the pressure hull under the control room, with external tanks at the bow and stern plus saddle tanks. **Its diesel fuel was inside the pressure hull to prevent leaks after depth charging** ([uboataces – Type VII](https://www.uboataces.com/uboat-type-vii.shtml)).
- **Pressure hull and depth.**
  - Type VIIC: 18.5 mm pressure hull, about 200 m crush depth. VIIC/41: 21 mm, about 250 m ([uboataces](https://www.uboataces.com/uboat-type-vii.shtml)).
  - Gato: 300 ft test depth ([Wikipedia – Gato](https://en.wikipedia.org/wiki/Gato-class_submarine)). Pressure hull thickness not confirmed from a source here.
- **Compartments (fleet boat): 8 WT compartments separated by pressure bulkheads, plus the conning tower.**
  1. Forward torpedo room
  2. Forward battery
  3. Control room
  4. After battery
  5. Forward engine room
  6. After engine room
  7. Maneuvering room
  8. After torpedo room
  
  (Source: [The Fleet Type Submarine, ch. 3](https://legacy.maritime.org/doc/fleetsub/chap3.php).)
- **Batteries.** Two batteries of 126 cells each, about 1,650 lb per cell, in the lower hull under the officers' berthing (forward battery) and crew berthing (after battery). Charging produces hydrogen, which is an explosion hazard and needs ventilation. **Seawater in the cells produces chlorine gas** (USS *Squalus* had a limited chlorine problem) ([fleetsubmarine.com – Batteries](https://fleetsubmarine.com/battery.html)).
- **Other figures.** Gato: 1,525 t surfaced / 2,424 t submerged; 311 ft; crew 60; 10 tubes (6 forward, 4 aft); 24 torpedoes. Type VIIC: 761/865 t; 67.1 m; crew 44; 5 tubes; 14 torpedoes.

**MODEL NOTE:**
- Pressure-hull breach = loss of that compartment and depth-limited.
- Outer-hull or ballast-tank damage = buoyancy loss, can't surface fully, and an oil slick from external fuel tanks (USN).
- Battery-compartment flooding = chlorine (crew casualties) and loss of submerged power.
- Depth-charge damage is a function of distance and depth.

---

## 8. Representative ship table

| Ship / class | Type | Year | Length | Displacement | WT compartments (main) | Armour | Machinery arrangement | Source |
|---|---|---|---|---|---|---|---|---|
| RN 125-ft TB | 1st-class TB | 1885–87 | 125–128 ft | ~60 t | n/a | none (conning tower splinter-proof) | locomotive boiler, compound engine, 1 shaft | [naval-enc.](https://naval-encyclopedia.com/ww1/uk/british-torpedo-boats.php?amp=1) |
| Schichau class (A-H) | TB | 1885–91 | 39.9 m | 83–90 t | n/a | none | 1 locomotive boiler, VTE, 1 shaft | [WP](https://en.wikipedia.org/wiki/Schichau-class_torpedo_boat) |
| Daring/Havock | TBD | 1893 | 165–185 ft | 260–275 t | n/a | none; 1/8 in HTS hull | 2 boilers, VTE, 2 shafts | [WP](https://en.wikipedia.org/wiki/Torpedo_boat_destroyer) |
| 30-knotter (C class) | TBD | 1896–1901 | ~210 ft | ~350 t | n/a | none | coal water-tube boilers, VTE, 2 shafts | [WP](https://en.wikipedia.org/wiki/C-class_destroyer_(1913)) |
| Montgomery | protected cruiser (small) | 1891 | 257 ft | 2,000 t | n/a | deck 8/11 mm; cellulose cofferdam; coal | 2 shafts, VTE | [WP](https://en.wikipedia.org/wiki/Montgomery-class_cruiser) |
| Olympia | protected cruiser | 1892 | 344 ft | 5,586 t std | n/a | deck 2 in flat / 4.75 in slope; 3.5 in turrets | 6 boilers, 2 VTE, 2 shafts | [WP](https://en.wikipedia.org/wiki/USS_Olympia_(C-6)) |
| Cressy | armoured cruiser | 1899 | ~472 ft [UNCERTAIN] | ~12,000 t [UNCERTAIN] | n/a | 6 in Krupp belt | 2 shafts, VTE | [WP](https://en.wikipedia.org/wiki/Armored_cruiser) |
| Arethusa | light cruiser | 1913 | 456 ft | 3,512 t | n/a | belt 1–3 in, deck 1 in | 8 boilers, 4 turbines, 4 shafts | [WP](https://en.wikipedia.org/wiki/Arethusa-class_cruiser_(1913)) |
| Furutaka | heavy cruiser | 1926 | ~185 m [UNCERTAIN] | 8,100 t std | n/a | belt 76 mm, deck 35 mm | 4 shafts | [WP](https://en.wikipedia.org/wiki/Japanese_cruiser_Furutaka) |
| Takao | heavy cruiser | 1932 | 203.8 m | 11,350 t std / 15,490 t FL | n/a | belt 102 mm (127 mm magazines), deck 37 mm, turrets 25 mm | 12 boilers, 4 shafts | [WP](https://en.wikipedia.org/wiki/Takao-class_cruiser) |
| Mogami | heavy/light cruiser | 1935 | 201.6 m | 8,500 t official / 11,169 t trial | n/a | belt 100–140 mm, deck 35 mm, turrets 25 mm | 8–10 boilers, 4 shafts | [WP](https://en.wikipedia.org/wiki/Mogami-class_cruiser) |
| Zara | heavy cruiser | 1931 | 182.8 m | 11,326–11,712 t std | n/a | belt 150 mm, deck 70 mm, turrets 150 mm | 8 boilers, 2 shafts | [WP](https://en.wikipedia.org/wiki/Zara-class_cruiser) |
| Admiral Hipper | heavy cruiser | 1939 | 202.8 m | 16,170 t design / 18,200 t FL | **14**; double bottom 72% L | belt 80 mm, deck 20–50 mm, turrets 105/70 mm | 3 shafts | [WP](https://en.wikipedia.org/wiki/Admiral_Hipper-class_cruiser) |
| New Orleans | heavy cruiser | 1934 | 588 ft | 9,950 t std | n/a | belt 3–5 in, deck 1.25–2.25 in, turret face 8 in, magazine box ~4 in | 8 boilers, 4 shafts | [WP](https://en.wikipedia.org/wiki/New_Orleans-class_cruiser) |
| Brooklyn (St. Louis sub-group) | light cruiser | 1937–39 | 608 ft | 9,767 t std | n/a | belt 5 in (2 in at magazines), deck 2 in | St. Louis/Helena: **unit system** | [WP](https://en.wikipedia.org/wiki/Brooklyn-class_cruiser) |
| Belfast | light cruiser | 1939 | 613 ft | ~11,550 t [UNCERTAIN]; Edinburgh group 13,175 t (WP) | n/a | belt 4.5 in, deck 2–3 in, turrets ≤4 in | 4 boilers, 4 shafts | [WP](https://en.wikipedia.org/wiki/HMS_Belfast) |
| Atlanta | AA cruiser | 1941 | 541 ft | 6,718 t std | n/a | belt ≤3.75 in, deck 1.25 in | 4 boilers, 2 shafts | [WP](https://en.wikipedia.org/wiki/Atlanta-class_cruiser) |
| Baltimore | heavy cruiser | 1943 | 673 ft | 13,600 t std / 17,000 t FL | n/a | belt 4–6 in, deck 2.5 in, turrets ≤8 in | 4 boilers, 4 shafts, unit system | [WP](https://en.wikipedia.org/wiki/Baltimore-class_cruiser) |
| Fubuki | destroyer | 1928 | 118.4 m | 1,750 t std | n/a | none | 4 boilers, 2 shafts, grouped | [WP](https://en.wikipedia.org/wiki/Fubuki-class_destroyer) |
| Tribal (RN) | destroyer | 1938 | 377 ft | 1,891 t std / 2,519 t deep | n/a | none | 3 boilers, 2 shafts | [WP](https://en.wikipedia.org/wiki/HMS_Eskimo_(F75)) |
| J/K/N | destroyer | 1939 | ~356 ft [UNCERTAIN] | 1,773 t std / 2,384 t deep | n/a | none | 2 boilers in 2 adjacent rooms, 1 funnel, longitudinal framing | [WP](https://en.wikipedia.org/wiki/J,_K,_and_N-class_destroyer) |
| Kagerō | destroyer | 1939 | 118.5 m | 2,000 t std / 2,500 t battle | n/a | none | 3 boilers, 2 shafts; 8 TT + 8 reloads | [WP](https://en.wikipedia.org/wiki/Kager%C5%8D-class_destroyer) |
| Benson/Gleaves | destroyer | 1940 | 348 ft | 1,620 t std / 2,474 t FL | ~"four-compartment" standard | none | alternating FR/ER, split plant | [WP](https://en.wikipedia.org/wiki/Benson-class_destroyer) |
| Fletcher | destroyer | 1942 | 376.5 ft | 2,050 t std / 2,500 t FL | "four-compartment ship" | ~0.5 in splinter [UNCERTAIN] | 4 boilers, 2 turbines, 2 shafts, split plant | [WP](https://en.wikipedia.org/wiki/Fletcher-class_destroyer) |
| Matsu | destroyer escort | 1944 | 100 m | 1,260 t std | single bottom (Tachibana) | none | 2 boilers, 2 shafts | [WP](https://en.wikipedia.org/wiki/Matsu-class_destroyer) |
| Flower | corvette | 1940 | 205 ft | 925–1,015 t | n/a | none | 2 boilers, 1 VTE, **1 shaft** | [WP](https://en.wikipedia.org/wiki/Flower-class_corvette) |
| River | frigate | 1942 | 301 ft | 1,370 t std / 1,830 t deep | n/a | none | 2 boilers, 2 VTE, 2 shafts | [WP](https://en.wikipedia.org/wiki/River-class_frigate) |
| John C. Butler | DE | 1944 | 306 ft | 1,350 t | n/a | none | 2 boilers, 2 turbines, 2 shafts | [WP](https://en.wikipedia.org/wiki/USS_Samuel_B._Roberts_(DE-413)) |
| CMB 55 ft | MTB | 1916 | 55 ft | ~10 t [UNCERTAIN] | n/a | none | 2 petrol aero engines | [WP](https://en.wikipedia.org/wiki/Coastal_motor_boat) |
| Elco 80 ft PT | MTB | 1942 | 80 ft | 51–61 t | ~7–8 [Elco not fully confirmed] | none | 3 Packard petrol; 3,000 gal in 3 tanks amidships | [pt103](http://www.pt103.com/PT_Boat_Specifications.html) |
| Higgins 78 ft PT | MTB | 1943 | 78 ft | ~56 t | **8** (plywood bulkheads) | none | 3 Packard; 2 tank rooms, self-sealing tanks | [PT-658](https://heritagedata.prd.state.or.us/historic/index.cfm?do=main.loadFile&load=NR_Noms/12000602.pdf) |
| Vosper 73 ft | MTB | 1944 | 73 ft | 44.5–48.75 t | n/a | bridge plating | 3 Packard 1,400 hp | [WP](https://en.wikipedia.org/wiki/Vosper_73_ft_motor_torpedo_boat) |
| Fairmile D | MTB/MGB | 1942 | 115 ft | 90–107 t | n/a | none | 4 Packard; 5,000–8,000 gal | [WP](https://en.wikipedia.org/wiki/Fairmile_D_motor_torpedo_boat) |
| S-26 type S-boat | MTB | 1940 | 34.9 m | ~112 t FL | 9 [UNCERTAIN] | Kalotte bridge (1943+) | 3 DB diesels, 3 shafts | [WP](https://en.wikipedia.org/wiki/E-boat) |
| MAS 500 series | MTB | 1930s | ~17 m [UNCERTAIN] | 20–30 t | n/a | none | Isotta Fraschini petrol | [WP](https://en.wikipedia.org/wiki/MAS_(motorboat)) |
| G-5 series 10 | MTB | 1930s | 19 m | 16.3 t | n/a | none; duralumin hull | 2 GAM-34 petrol | [WP](https://en.wikipedia.org/wiki/G-5-class_motor_torpedo_boat) |
| Gato | submarine | 1941 | 311 ft | 1,525 / 2,424 t | **8** + conning tower | pressure hull | 4 diesel-electric, 2 shafts | [Fleet Sub](https://legacy.maritime.org/doc/fleetsub/chap3.php) |
| Type VIIC | submarine | 1940 | 67.1 m | 761 / 865 t | ~5 [UNCERTAIN] | 18.5 mm pressure hull | 2 diesels, 2 e-motors | [uboataces](https://www.uboataces.com/uboat-type-vii.shtml) |

"n/a" means the number was not found in the sources consulted. Do not treat it as zero.

---

## 9. Consolidated model recommendations by size tier [INFERRED]

| Tier | Displacement | Components to model | Compartments | Special rules |
|---|---|---|---|---|
| Coastal craft | < 150 t | crew, guns, engines (per shaft), fuel tanks, torpedo tubes, bridge | 6–9 | fuel-type fire/explosion; wooden pass-through; wreck floats; crew casualties dominate |
| TB / TBD / escort | 150–1,500 t | + boilers, engine room, magazine, depth charges, steering | 8–12 | single-screw flag; one torpedo ≈ loss; hull girder HP |
| Destroyer | 1,500–3,000 t | + split-plant flag, torpedo mounts and reloads, fire spread, director | 12–16 | four-compartment rule; break-in-two from amidships girder loss; bow/stern loss survivable |
| Cruiser | 3,000–20,000 t | + belt, deck, magazine boxes, turret armour layers, unit machinery, aircraft fuel | 14–25 | magazine detonation from underwater hits; torpedo-mount explosion (IJN); fire as main killer; bow severance |
| Submarine | 250–2,500 t | pressure vs outer hull, batteries, ballast, diesel/e-motor | 5–8 | chlorine, depth-limited survival, external fuel leak |

**General rules:**
- Track **two pools**: buoyancy and stability (per compartment) and hull-girder strength (a midships section-modulus fraction).
- **Fire** is a third pool. It is fed by petrol, aircraft fuel, ready ammunition and torpedoes, and it can reach magazines over time (CUSHING, *Astoria*).
- **Immediate magazine detonation** should be rare from shellfire and much more likely from torpedo or mine hits under a magazine (*New Orleans*, *Amatsukaze*, *Juneau*).
