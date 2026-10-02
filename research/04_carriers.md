# 04 — Aircraft Carriers (1920s–1945): Components, Subdivision, Protection, Damage Behaviour

Research base for the damage model. Breadth over polish; numbers are sourced inline. Figures marked **[?]** are uncertain, conflicting between sources, or from secondary/advocacy sources. Where sources disagree, both values are given.

Source-bias notes:
- **armouredcarriers.com** argues for the RN armoured carrier. Its facts are detailed, but its conclusions are partisan.
- **navweaps tech-030** ("Were armored flight decks worthwhile?") argues the opposite.
- The USN **War Damage Reports** (WDR) are primary sources and the most reliable in this list.

---

## 0. Executive summary for the modellers

1. **Carriers die by fire and gas far more often than by flooding.** Most carrier losses ran: hit, then avgas or ordnance fire or vapour explosion, then loss of power or fire mains, then the ship was abandoned or scuttled. Lexington, the four Midway carriers, Taiho, Shokaku, Wasp, Princeton and Liscome Bay all went this way. The ships lost purely to flooding were Ark Royal, Courageous, Shinano, Yorktown (in the end) and Gambier Bay.
2. **"Mission kill" happens long before sinking.** A single bomb through the flight deck could end flight ops for the rest of a battle (Zuiho and Shokaku at Santa Cruz, Glorious). A jammed elevator throttles them (Enterprise at Santa Cruz).
3. **State at the moment of the hit matters more than armour.** Fuelled and armed aircraft in the hangar or on deck, live avgas lines and loose ordnance turned one hit into a total loss (Akagi, Kaga, Franklin, Bunker Hill, Princeton). Purged lines and an empty, struck-down deck let ships shrug off similar hits (Yorktown at Midway's bomb phase, Formidable).
4. **Vapour is a delayed time-bomb.** The explosions at Lexington (+1 h 34 min), Taiho (+6.5 h) and Shokaku (+2.8 h) came long after the initial hit. Model leaked avgas as an accumulating vapour concentration with a per-tick ignition chance.
5. **Two protection philosophies:**
   - **USN (to 1945):** wooden flight deck as superstructure, armoured hangar deck as the strength deck, open hangar. Holes were cheap to patch but there was nothing to stop bombs reaching the hangar.
   - **RN:** armoured flight deck as the strength deck, closed armoured box hangar. Ships shrugged off kamikazes but carried small air groups, and heavy distortion was often uneconomic to repair.
   - **IJN:** closed hangars and unarmoured decks until Taiho and Shinano. Avgas tanks were integral with the hull and cracked under shock.

---

## 1. Flight deck

### 1.1 Structural role
| Practice | Examples | Strength deck | Flight deck |
|---|---|---|---|
| USN "open" carrier | Lexington, Ranger, Yorktown, Wasp, Essex, CVL, CVE | **Hangar (main) deck** | Wooden planking on light steel, carried as superstructure with **expansion joints** |
| RN armoured box | Illustrious, Indomitable, Implacable | **Flight deck** (3 in armour) | Armoured "lid" between the lifts; ends unarmoured |
| IJN late armoured | Taiho, Shinano | Armoured flight deck (75–80 mm on 20 mm) | Armour "lid" between the two lifts only |
| USN CVB | Midway | Disputed **[?]** — see right | 3.5 in armour between the lifts. armouredcarriers says it was still superstructure; Wikipedia's *Armoured flight deck* article says the strength deck moved up |

- The Franklin WDR states explicitly: "Main deck (hangar deck) is the strength deck on this class of carrier." Because of this, damage above it "will not compromise the strength of the hull." Franklin's flight deck was "virtually demolished aft of the after elevator" with a hole about **60×80 ft** aft of the after expansion joint (frame 149), yet the hull girder survived. ([Franklin WDR No. 56](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-franklin-cv-13-war-damage-report-no-56.html))
- On Illustrious the flight deck was the primary hull strength deck. The armoured box was **458 ft × 62 ft**: a 3 in deck between the lifts with 4.5 in C-armour hangar sides. ([armouredcarriers – Illustrious design](https://www.armouredcarriers.com/hms-illustrious-armoured-aircraft-carrier-design))
- The design standard was proof against 6 in plunging fire below 23,000 yd and **500 lb SAP bombs dropped from 7,000 ft**. ([navweaps tech-030](https://www.navweaps.com/index_tech/tech-030.php))
- **The downside of an armoured strength deck:** large distortions damage the hull girder itself.
  - Illustrious was judged a postwar "write-off due to war damage", with centreline shaft problems blamed on structural deformation.
  - Indomitable suffered a 1951 petrol explosion that was "quite minor" but caused irreparable structural damage; she was scrapped. ([navweaps tech-030](https://www.navweaps.com/index_tech/tech-030.php))
- Other armoured decks:
  - **Taiho:** 75–80 mm CNC over 20 mm DS, about **150 m × 19.7 m** between the lifts. ([armouredcarriers – Taiho](https://www.armouredcarriers.com/japanese-aircraft-carrier-taiho-armoured-flight-decks))
  - **Shinano:** 75 mm on 20 mm, meant to resist 500 kg bombs. ([Wikipedia Shinano](https://en.wikipedia.org/wiki/Japanese_aircraft_carrier_Shinano))
  - **Graf Zeppelin** (unfinished): 45 mm flight deck and a 60 mm armoured hangar/main deck. ([Wikipedia](https://en.wikipedia.org/wiki/German_aircraft_carrier_Graf_Zeppelin))
- **Hangar height trade-off:** RN hangars were 14–16 ft against Essex's 17 ft 6 in. ([navweaps tech-030](https://www.navweaps.com/index_tech/tech-030.php)) Wikipedia gives about 27 ft "usable" for USN ships **[?, likely a different measurement]**.

### 1.2 Arresting gear, barriers, catapults
- **Arresting wires and barriers:** USN fleet carriers ran multiple transverse wires aft plus crash barriers, which protected the forward deck park. I could not confirm exact WWII wire and barrier counts from accessible sources **[?]**.
  - Formidable resumed landings 4 h after her 4 May 1945 hit "with only one functional crash barrier". Barriers are therefore a distinct, damageable sub-component. ([armouredcarriers – Formidable 4 May](https://www.armouredcarriers.com/hms-formidable-may-4-kamikaze))
- **Catapults:**
  - Yorktown class: 2 flight-deck catapults plus 1 hangar-deck catapult; the hangar unit was removed in 1942. ([navypedia](https://www.navypedia.org/ships/usa/us_cv_yorktown.htm))
  - Wasp: 4 hydraulic catapults, 2 on the flight deck and 2 on the hangar deck. ([Wikipedia](https://en.wikipedia.org/wiki/USS_Wasp_(CV-7)))
  - Essex: early ships had one H-4A, later two H-4B. ([Wikipedia Essex class](https://en.wikipedia.org/wiki/Essex-class_aircraft_carrier))
  - Midway: two H4-1 units, rated 28,000 lb at 90 mph. ([armouredcarriers – Midway](https://www.armouredcarriers.com/uss-midway-design-and-development))
  - Lexington: a 155 ft flywheel catapult, removed in 1934 as unnecessary. ([Wikipedia Lexington class](https://en.wikipedia.org/wiki/Lexington-class_aircraft_carrier))
  - CVE: one catapult, which was essential because CVEs were slow. ([Wikipedia Casablanca](https://en.wikipedia.org/wiki/Casablanca-class_escort_carrier))

### 1.3 Deck park
- **USN:** permanent deck parks; the air group exceeded hangar capacity.
- **RN:** originally struck everything below; from about 1943 they adopted deck parks, which raised Illustrious-class complements from 36 to as many as 57. ([Wikipedia Illustrious class](https://en.wikipedia.org/wiki/Illustrious-class_aircraft_carrier)) Implacable class went from 48 in the hangar to up to 81 with a deck park. ([Wikipedia](https://en.wikipedia.org/wiki/Implacable-class_aircraft_carrier))
- **Deck-park exposure:**
  - Franklin had 31 fuelled and armed aircraft on deck on 19 Mar 1945.
  - Formidable lost **10 aircraft** (1 blown overboard plus 9 burned) from one kamikaze, despite the armoured deck.

### 1.4 Damage effects and repair times (wooden vs armoured)
| Ship / date | Hit | Flight-deck effect | Time to resume ops |
|---|---|---|---|
| Yorktown, Midway, 4 Jun 1942 | 3 bombs | Hole about **10×10 ft** abaft No. 2 elevator | Hole "repaired within about 25 minutes". Boilers back and making 20 kt about 1 h 30 min after the hits; she was refuelling fighters when the torpedoes hit. ([Yorktown action report](https://www.history.navy.mil/research/archives/digital-exhibits-highlights/action-reports/wwii-battle-of-midway/uss-yorktown-action-report.html)) midway42.org gives the hole as about 12 ft. ([midway42](http://www.midway42.org/TheBattle/YorktownDamage.aspx)) |
| Intrepid 1945 (kamikaze) | — | — | Flight deck repaired in 3 h ([navweaps tech-042](https://www.navweaps.com/index_tech/tech-042.php)) |
| Hancock 1945 (kamikaze) | — | — | Fires out in 30 min; flight ops in under 1 h (tech-042) |
| Franklin, 30 Oct 1944 (kamikaze) | Crashed through to the gallery deck | — | Recovered aircraft 76 min later ([Wikipedia](https://en.wikipedia.org/wiki/USS_Franklin_(CV-13))) |
| Formidable, 4 May 1945 | Zeke with 500–1000 lb bomb at frame 79, about 9 ft right of the centreline | Dent about **24×20 ft**, 2 ft deep; hole only "several inches". A splinter about **1 ft × 9 in** went down through the hangar deck into the centre boiler room steam pipe. Speed fell to 18 kt, restored to 24 kt at 1300. | Landings at 1700 (**+4 h**). Hole filled with quick-setting concrete and steel plate. ([armouredcarriers](https://www.armouredcarriers.com/hms-formidable-may-4-kamikaze)) |
| Indefatigable, 1 Apr 1945 | Kamikaze at the base of the island | Minimal | Flight deck back in action within about 30 min; 21 killed ([Wikipedia Implacable class](https://en.wikipedia.org/wiki/Implacable-class_aircraft_carrier)). The claim that the bomb did not detonate is **[?]**. |
| Victorious, 9 May 1945 | 3 kamikaze hits | The second "dished in a section of the flight deck and managed to pierce it" | Remained in action ([navweaps tech-030](https://www.navweaps.com/index_tech/tech-030.php)) |
| Zuiho, Santa Cruz | 1–2 × 500 lb bombs | Unable to land aircraft | Rest of the battle ([Wikipedia Santa Cruz](https://en.wikipedia.org/wiki/Battle_of_the_Santa_Cruz_Islands)) |
| Shokaku, Santa Cruz | 3–6 × 1000 lb bombs | Flight deck wrecked | Under repair until March 1943 (same source) |
| Shokaku, Coral Sea | 3 bombs (2 per navypedia) | Could not recover aircraft | Returned to Japan; dry-dock repairs about 10 days after docking on 16 Jun ([Wikipedia](https://en.wikipedia.org/wiki/Japanese_aircraft_carrier_Sh%C5%8Dkaku)) **[?]** |
| Glorious, 8 Jun 1940 | 11 in shell, forward flight deck | "Prevented any other aircraft from taking off" | Never (sunk 1 h 32 min later) ([Wikipedia](https://en.wikipedia.org/wiki/HMS_Glorious)) |

A widely quoted contemporary line on kamikaze hits: "When a kamikaze hits a Limey carrier it's just a case of 'Sweepers, man your brooms'". A 1945 Pacific Fleet assessment added that without armoured decks TF 57 "would have been out of action… for at least 2 months". ([navweaps tech-042](https://www.navweaps.com/index_tech/tech-042.php); [Wikipedia Armoured flight deck](https://en.wikipedia.org/wiki/Armoured_flight_deck))

**MODEL NOTE — flight deck**
- Represent the flight deck as segments along the length (bow / fwd lift / mid / aft lift / round-down), each with a state: `OK | HOLED | WRECKED | FIRE`.
  - Launch needs a clear run of N segments forward of the deck park.
  - Recovery needs the aft segments (wires) and at least 1 barrier intact.
- **Holed** (wooden deck, small bomb): repair 20–60 min for a USN wooden deck. Light armour plus concrete takes 4–12 h (Formidable).
- **Wrecked:** no ops for the rest of the engagement.
- **Armoured segment:** a penetration threshold per armour class (e.g. 3 in blocks a 250 kg SAP from about 7,000 ft). On a non-penetrating hit, deal a "dent" (small repair) plus a splinter roll that passes damage to the compartment below. Formidable shows that even a non-penetrating hit can hurt the machinery.
- **Strength-deck flag:** if the flight deck is the strength deck, heavy damage adds hull-girder damage (long-term repair, possible "write-off"). If not, upper damage never threatens the girder.
- **Deck park:** a list of aircraft on deck, each with `fuel` and `armed` flags. A hit in a segment destroys the aircraft there and adds fire load scaled by their fuel and ordnance.

---

## 2. Elevators (lifts)

| Ship | Count / position | Size / capacity |
|---|---|---|
| Langley | 1 | — ([Wikipedia](https://en.wikipedia.org/wiki/USS_Langley_(CV-1))) |
| Lexington | 2 centreline | Fwd 30×60 ft, 16,000 lb; aft 30×36 ft, 6,000 lb ([Wikipedia](https://en.wikipedia.org/wiki/Lexington-class_aircraft_carrier)) |
| Ranger | 3 | — |
| Yorktown | 3 centreline | 14.6×13.7 m, 7.7 t ([navypedia](https://www.navypedia.org/ships/usa/us_cv_yorktown.htm)) |
| Wasp | 2 centreline + 1 **deck-edge** (the first one, an outrigger type) | — ([Wikipedia](https://en.wikipedia.org/wiki/USS_Wasp_(CV-7))) |
| Essex | 2 centreline (48'3"×44'3", 28,000 lb) + 1 port deck-edge (60×34 ft, 18,000 lb) | ([naval-encyclopedia](https://naval-encyclopedia.com/ww2/us/essex-class-fleet-aircraft-carriers.php)) |
| Midway | 2 centreline + 1 deck-edge | ([Wikipedia](https://en.wikipedia.org/wiki/Midway-class_aircraft_carrier)) |
| Illustrious | 2 centreline, unarmoured, outside the box at the ends | 45×22 ft, 13,440 lb in 30 s, later 15,000 lb ([armouredcarriers](https://www.armouredcarriers.com/hms-illustrious-armoured-aircraft-carrier-design)) |
| Implacable | 2 | Fwd 45×33 ft (upper hangar only); aft 45×22 ft (both hangars) |
| Courageous / Glorious | 2 | 46×48 ft |
| Akagi (post-1938) | 3 | 11.8×13 m / 12.8×8.4 m / 11.8×13 m |
| Kaga (post-1935) | 3 | Up to 10.67×15.85 m |
| Shokaku | 3 | Fwd 13×16 m, others 13×12 m. **15 s from lower hangar to flight deck**; 5,000 kg ([Wikipedia class](https://en.wikipedia.org/wiki/Sh%C5%8Dkaku-class_aircraft_carrier)) |
| Taiho | 2 | 14×14 m (aft) |
| Shinano | 2 | 7,500 kg; larger one 15×14 m |
| Béarn | 3, electric | 2,000 kg fwd / 5,000 kg others; **3–5 min per cycle** ([Wikipedia](https://en.wikipedia.org/wiki/French_aircraft_carrier_B%C3%A9arn)) |
| Hosho | 2 | 10.35×7.86 m; 13.71×6.34 m |
| Casablanca CVE | 2 | — |

Essex elevator cycle: about **45 s** automatic. Hydraulic, with HP/LP oil tanks and the pump room deep in the ship; Hornet CV-12 museum data, post-war. ([Curbside Classic](https://www.curbsideclassic.com/blog/museum/how-to-operate-an-elevator/))

**Failure cases**
- **Lexington, Coral Sea:** both elevators were disabled by loss of hydraulic pressure after the forward torpedo hit. ([Lexington WDR No. 16](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-lexington-cv2-war-damage-report-no16.html)) The later explosions vented into the elevator well.
- **Enterprise, Santa Cruz:** the forward elevator was jammed in the "up" position by a bomb. She stopped recovery at 10:00 with a full deck, then recovered 57 of 73 airborne aircraft between 11:39 and 13:22; the rest ditched. ([Wikipedia](https://en.wikipedia.org/wiki/Battle_of_the_Santa_Cruz_Islands))
- **Illustrious, 10 Jan 1941:** the aft lift was destroyed (unarmoured, outside the box). Another bomb pierced the armour forward of it and bent the forward lift; a later hit went into the aft lift well again. ([Wikipedia](https://en.wikipedia.org/wiki/HMS_Illustrious_(87)))
- **Taiho:** the forward elevator dropped canted about 1 m below the deck and the forward flight deck was unusable. The crew planked over the pit by 09:20 and continued ops, but the pit collected avgas and water. ([combinedfleet Taiho](https://www.combinedfleet.com/Taiho.htm))
- **Akagi, Midway:** a 1,000 lb bomb hit the edge of the midships/aft elevator and burst in the upper hangar. ([Wikipedia](https://en.wikipedia.org/wiki/Japanese_aircraft_carrier_Akagi)) Hiryu's forward elevator was wrecked by 4 bombs forward ([USNI](https://www.usni.org/magazines/naval-history-magazine/2017/june/sinking-carriers)); the oft-repeated detail that it was blown against the island is **[?]**.
- **Shokaku, Philippine Sea:** water surged through the open No. 1 elevator into the hangar as the bow sank. ([combinedfleet](https://www.combinedfleet.com/shoksink.htm))
- **Elevator holes are weak points:** large centreline elevators are big openings in the deck. A deck-edge lift leaves the deck intact and "increased effective deck space when 'up'". ([Wikipedia Essex](https://en.wikipedia.org/wiki/Essex-class_aircraft_carrier))

**MODEL NOTE — elevators**
- Each lift has `state ∈ {OK, JAMMED_UP, JAMMED_DOWN, DESTROYED}` and depends on hydraulic or electric power.
- `JAMMED_UP` keeps the deck intact but stops hangar to deck flow. `JAMMED_DOWN` / `DESTROYED` leaves a hole in the deck segment, which blocks a launch run or recovery across it until planked.
- Flow rate = Σ lifts × (1 / cycle time). This gates re-spot and strike tempo.
- Centreline lifts in a closed hangar also act as vents and flood paths (Shokaku). A lift pit is a low point where leaked liquids collect (Taiho).

---

## 3. Hangars

### 3.1 Open vs closed
- **USN open hangar:** the sides had roller curtains or openings, so blast and vapour could vent and aircraft could warm up below.
  - Even the armoured Midway kept an "open" hangar for blast venting, divided into four sections by three fire doors. The Franklin WDR recommended **five compartments separated by 40–50 lb STS bulkheads** for the CVB. ([armouredcarriers Midway](https://www.armouredcarriers.com/uss-midway-design-and-development); [Franklin WDR](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-franklin-cv-13-war-damage-report-no-56.html))
- **RN closed box:**
  - Steel fire curtains divided the hangar into thirds, with "double-blast-door lobbies" for access. A high-pressure seawater spray "proved capable of containing hangar fires within minutes", though the salt water damaged aircraft. ([armouredcarriers](https://www.armouredcarriers.com/hms-illustrious-armoured-aircraft-carrier-design))
  - The weakness: on Illustrious on 10 Jan 1941 the large bomb burst 10 ft above the hangar deck. It wrecked the aft sprinklers and **shredded the steel fire curtains into lethal fragments**, so they were replaced by asbestos ones. ([Wikipedia](https://en.wikipedia.org/wiki/HMS_Illustrious_(87)))
  - armouredcarriers claims "no British hangar was even mildly affected" by kamikaze or Japanese bomb hits in 1945 **[advocacy]**.
- **IJN closed hangars, often two stacked** (Akagi, Kaga, Shokaku, Taiho):
  - Fire suppression was difficult because they were fully enclosed. ([Wikipedia Kaga](https://en.wikipedia.org/wiki/Japanese_aircraft_carrier_Kaga))
  - Vapour could not vent. On Taiho, "both Upper and Lower hangar decks were full of the mixed gas" by noon. ([combinedfleet Taiho](https://www.combinedfleet.com/Taiho.htm))
  - Localised fighting relied on closing fire-curtain sections fed by port and starboard fire mains. Kaga's spread of hits destroyed both mains. ([Shattered Sword summary via blog](http://uncommonsenseok.blogspot.com/2019/10/the-wreck-of-kaga.html) **[secondary]**)

### 3.2 Hangar sprinklers and fog / foam
- **USN:**
  - Hangar sprinklers and water curtains, a conflagration station, and after 1942 "foamite" outlets about every 100 ft. ([Pacific War Online Encyclopedia – Damage Control](http://pwencycl.kgbudge.com/D/a/Damage_Control.htm))
  - Fog nozzles were adopted through Lt. Harold Burke (ex-FDNY). Essex ships added **two gasoline-driven fire mains independent of ship power**. (same source)
- **Franklin, 30 Oct 1944:** sprinklers confined a hangar fire between frames 90–160, and it was out in about 2 h.
- **Franklin, 19 Mar 1945:** "Hangar sprinklers and water curtains were demolished before they had an opportunity to produce an appreciable effect." The conflagration station was wrecked and its crew killed. Recommendation: armour the conflagration station with ¾ in STS and run its cables in an armoured trunk. ([Franklin WDR](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-franklin-cv-13-war-damage-report-no-56.html))
- **Yorktown at Midway:** sprinklers put out the hangar fires. ([Navy Lookout](https://www.navylookout.com/the-survivability-of-the-aircraft-carrier/))

### 3.3 Fuelled and armed aircraft as fire load
- **Kaga, Midway:** about **80,000 lb** of loose ordnance was in the hangar during the rearm/re-spot: about 28 × 800 kg bombs, 40 × 250 kg bombs and 20 torpedoes. Parked aircraft held roughly **10,000 gal** of fuel, and the avgas lines were not purged. ([blog summarising Shattered Sword](http://uncommonsenseok.blogspot.com/2019/10/the-wreck-of-kaga.html); [Wikipedia Kaga](https://en.wikipedia.org/wiki/Japanese_aircraft_carrier_Kaga)) **[secondary, from Parshall & Tully]**
  - Four bombs (1 × 1000 lb + 3 × 500 lb) killed the bridge team including Capt. Okada, so leadership was lost. The engine room crew was overcome or stopped about 1300; 213 engineers died. 811–814 dead in all; scuttled at 19:25. ([combinedfleet Kaga](https://www.combinedfleet.com/kaga.htm))
- **Akagi:** **one** 1,000 lb hit plus near misses. The bomb burst among armed and fuelled B5Ns in the upper hangar; torpedo explosions came from about 10:29. A near miss jammed the rudder at about 20–30°, and the starboard aft engine room went down (12 kt). Scuttled 05:20 the next day; about 263–267 dead. ([combinedfleet Akagi](https://www.combinedfleet.com/Akagi.htm); [Wikipedia](https://en.wikipedia.org/wiki/Japanese_aircraft_carrier_Akagi))
- **Franklin, 19 Mar 1945:** 2 × 250 kg bombs.
  - Load at the time: **31 fuelled and armed aircraft on deck** (5 VB with 2×250 + 2×500 lb; 14 VT with 4×500 lb; 12 VFB with one 11.75 in Tiny Tim rocket each). **22 aircraft in the hangar**, some fuelled and some with Tiny Tims.
  - About 60 of the 66 × 500 lb bombs detonated, and all 12 deck Tiny Tims. At least 40% of the bombs went off **low order**. Heavy explosions went on for about 5 h.
  - The armoured hangar deck (2 × 1¼ in STS) kept damage below it "comparatively minor", with only 4 large holes. List reached 13°.
  - **Casualties:** 724–807 killed. The ship survived: "principal strength structure, watertight integrity and vital machinery below the hangar deck remained intact." ([Franklin WDR](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-franklin-cv-13-war-damage-report-no-56.html); [Wikipedia](https://en.wikipedia.org/wiki/USS_Franklin_(CV-13)))
- **Bunker Hill, 11 May 1945:** 2 Zeros, each with a 250 kg bomb. The first set the parked, fuelled aircraft aft on fire. The second hit near the island, and its bomb reached the VF-84 ready room, killing 22 pilots. 396 killed (incl. 43 missing) and 264 wounded. She steamed at 20 kt to Ulithi and was still in the yard at VJ-day. ([Wikipedia](https://en.wikipedia.org/wiki/USS_Bunker_Hill_(CV-17)))
- **Princeton CVL, 24 Oct 1944:** one bomb went through the wooden deck and hangar between the elevators and started gasoline fires among the TBMs. At 15:24 a large explosion, possibly the aft bomb magazine, hit Birmingham alongside: 241 killed and 412 wounded on Birmingham, against 108 lost on Princeton. Scuttled about 17:50. ([Wikipedia](https://en.wikipedia.org/wiki/USS_Princeton_(CVL-23)))

**MODEL NOTE — hangar**
- Divide the hangar into bays (2–5). Each bay holds a list of aircraft (`fuel%`, `ordnance`), a loose-ordnance tonnage (e.g. from a rearm in progress), `fire_intensity`, `vapour` and suppression state (sprinklers, curtain, fog/foam, all needing a fire main and a conflagration station).
- Fire spreads to adjacent bays unless the curtain or bulkhead holds. Blast inside a closed hangar can shred curtains (Illustrious) and lose sprinkler control (Franklin).
- Ordnance cook-off: a per-tick chance by type; some fraction goes off low-order (Franklin about 40%).
- **Open vs closed:** an open hangar vents blast and vapour (lower over-pressure, faster vapour decay) but gives no protection. A closed hangar traps both.
- **Tempo trap:** add a `rearm_in_progress` state that dumps loose bombs and torpedoes on the hangar deck. This was the Midway lesson.

---

## 4. Aviation gasoline (avgas)

### 4.1 Quantities
| Ship | Avgas | Source |
|---|---|---|
| Lexington | 132,264 or 163,000 US gal **[?]** | [Wikipedia](https://en.wikipedia.org/wiki/Lexington-class_aircraft_carrier) |
| Yorktown | 673,900 L (about 178,000 US gal) | [navypedia](https://www.navypedia.org/ships/usa/us_cv_yorktown.htm) |
| Essex | **231,650 US gal** in several separated tanks low in the hull | [naval-encyclopedia](https://naval-encyclopedia.com/ww2/us/essex-class-fleet-aircraft-carriers.php) |
| Akagi | about 150,000 US gal | [Wikipedia](https://en.wikipedia.org/wiki/Japanese_aircraft_carrier_Akagi) |
| Shokaku | about 150,000 gal (Wikipedia) **[?]**; navypedia gives "1800 t", which looks too high for avgas alone **[?]** | [navypedia](https://www.navypedia.org/ships/japan/jap_cv_shokaku.htm) |
| Shinano | 720,000 L | Wikipedia |
| Ark Royal (1938) | about 100,000 gal (likely Imperial) | [navweaps tech-030](https://www.navweaps.com/index_tech/tech-030.php) |
| Illustrious | 50,540–50,650 Imp gal | navweaps / [Wikipedia](https://en.wikipedia.org/wiki/HMS_Illustrious_(87)) |
| Implacable | 94,650 Imp gal **[?]** | [Wikipedia](https://en.wikipedia.org/wiki/Implacable-class_aircraft_carrier) |
| Courageous / Glorious (1939) | 34,500 Imp gal | [Wikipedia](https://en.wikipedia.org/wiki/HMS_Courageous_(50)) |
| Béarn | 100,000 L in 3 compartments inside the citadel, **nitrogen-inerted** | [Wikipedia](https://en.wikipedia.org/wiki/French_aircraft_carrier_B%C3%A9arn) |
| US-built CVE (RN service) | 75,000–88,000 gal, cut to 36,000 after the Dasher loss | [Wikipedia Dasher](https://en.wikipedia.org/wiki/HMS_Dasher_(D37)) |

### 4.2 Stowage practices
- **RN:** cylindrical tanks suspended in **seawater-filled compartments** below the waterline under armour. Spilled fuel dispersed into water rather than forming vapour. Lines were purged with CO2. The USN adopted similar ideas after information exchanges in 1940. ([armouredcarriers](https://www.armouredcarriers.com/hms-illustrious-armoured-aircraft-carrier-design); [Wikipedia Armoured flight deck](https://en.wikipedia.org/wiki/Armoured_flight_deck))
- **USN (Essex):** seawater displacement. Water is pumped into the tank to push avgas up to the delivery lines, so tanks never contain an ullage of vapour. ([naval-encyclopedia](https://naval-encyclopedia.com/ww2/us/essex-class-fleet-aircraft-carriers.php))
  - **Lexington's tanks** lay forward of frame 75 with fresh-water-filled voids around them. They were built into the structure and the torpedo breached them. Lessons from her loss:
    - keep the tank layers inboard of the gasoline tanks void and **continuously inert-filled**;
    - **segregate port/starboard** gasoline systems;
    - shut down sparking electrical gear;
    - check vent-duct tightness.
    ([Lexington WDR](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-lexington-cv2-war-damage-report-no16.html))
  - **Yorktown at Midway:** jettisoned an 8,000 gal auxiliary tank, drained the lines and filled them with **CO2 at 20 psi**, and filled the gasoline compartments with CO2. "The prior precaution of smothering the gasoline system with CO2 undoubtedly prevented the gasoline from igniting." ([action report](https://www.history.navy.mil/research/archives/digital-exhibits-highlights/action-reports/wwii-battle-of-midway/uss-yorktown-action-report.html); [Wikipedia](https://en.wikipedia.org/wiki/USS_Yorktown_(CV-5)))
  - **Franklin, 19 Mar 1945:** the forward system was purged, but the aft system was live: "topping off had just been completed", with 3 aircraft being fuelled. ([Franklin WDR](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-franklin-cv-13-war-damage-report-no-56.html))
- **IJN:**
  - Tanks were **integral with the hull structure** (Kaga) ([Wikipedia](https://en.wikipedia.org/wiki/Japanese_aircraft_carrier_Kaga)), so hull whipping and shock cracked them.
  - **Taiho:** "integral" tanks with a CO2 void, "only partially encompassed by 50–60 mm CNC". The torpedo "split a joint in the armour above the forward avgas tank". ([armouredcarriers Taiho](https://www.armouredcarriers.com/japanese-aircraft-carrier-taiho-armoured-flight-decks))
  - **Shokaku:** 105 mm NVNC over the avgas stowage ([Wikipedia class](https://en.wikipedia.org/wiki/Sh%C5%8Dkaku-class_aircraft_carrier)). Zuikaku got additional concrete around her tanks in Aug 1944 ([navypedia](https://www.navypedia.org/ships/japan/jap_cv_shokaku.htm)).

### 4.3 Vapour explosion case studies
1. **Lexington, Coral Sea, 8 May 1942** ([WDR No. 16](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-lexington-cv2-war-damage-report-no16.html))
   - **The attack (11:13–11:32):** 2 (possibly 3) port torpedoes, the forward one at frames 60–65 in the gasoline stowage area; 2 bomb hits. List of 6–7°, corrected in about 80 min by shifting oil. She was **recovering aircraft** at this point.
   - **12:47:** gasoline vapour that had leaked into the **I.C. motor-generator room** detonated, ignited by running electrical machinery.
   - **13:19:** secondary explosion. **14:45:** explosion in the elevator well, then hangar fire and the forward machinery abandoned.
   - **After 15:30:** fire-main pressure collapsed (about 30 psi at the flight deck by 16:30).
   - **Ending:** abandon ship ordered 17:07; a torpedo-warhead explosion at 17:27; scuttled about 20:00. 2,770 evacuated.
   - **Takeaway:** a ship with a combat-worthy hull was lost to **vapour + ignition source**, about **1.5 h after** the hit.
2. **Taiho, 19 Jun 1944** ([combinedfleet](https://www.combinedfleet.com/Taiho.htm); [Wikipedia](https://en.wikipedia.org/wiki/Japanese_aircraft_carrier_Taih%C5%8D))
   - **The hit:** one torpedo from Albacore at 08:10, starboard frame 54, abreast No. 1 lift. Trim 1.5 m by the bow, forward lift dropped, elevator pit planked over and ops continued.
   - **Vapour build-up:** avgas and water collected in the lift well. The damage-control officer ordered ventilation at full and opened all doors and hatches, which spread the vapour through both hangars.
   - **14:32 (+6 h 22 min):** explosion. It buckled the armoured flight deck upward, blew out the hangar sides and stopped propulsion.
   - **End:** sank 16:28. About 1,650 of 2,150 died (combinedfleet gives about 660 ship's crew).
3. **Shokaku, 19 Jun 1944** ([combinedfleet analysis](https://www.combinedfleet.com/shoksink.htm))
   - **The hits:** 3–4 torpedoes from Cavalla at about 11:18–11:22. One shattered an avgas main forward of the island, and electrics failed at once.
   - **Progression:** periodic explosions of gas and ammunition, plus vapour from unrefined Tarakan fuel oil.
   - **14:08 (+2 h 50 min):** an aerial bomb in the hangar, then forward magazine detonations. Sank with 1,263–1,272 dead.
4. **Wasp, 15 Sep 1942:** 2–3 torpedoes from I-19 near the gasoline tanks and magazines, about 14:45. The forward water mains were destroyed, so there was "no water… to fight the forward fires". Explosions followed within 24 min; abandon at 15:20; 193 dead and 45 aircraft lost. ([Wikipedia](https://en.wikipedia.org/wiki/USS_Wasp_(CV-7)))
5. **HMS Dasher (CVE), 27 Mar 1943:** internal explosion, probably petrol fumes from leaking tanks with ignition **[cause uncertain]**. 379 of 528 died. RN CVE avgas was then cut to 36,000 gal. ([Wikipedia](https://en.wikipedia.org/wiki/HMS_Dasher_(D37)))
6. **Indomitable, 1951** (postwar): a "minor" petrol explosion caused irreparable structural damage. ([navweaps](https://www.navweaps.com/index_tech/tech-030.php))

**MODEL NOTE — avgas**
- Treat each avgas tank group as a **"liquid magazine"** with:
  - `fill` (0–1);
  - `protection` (none / armour / water-jacket / CO2-inerted);
  - `integral` flag (IJN = higher crack chance under shock and near-miss whipping);
  - `system_state ∈ {LIVE, DRAINED, CO2_PURGED}` (a doctrine choice, set when the ship goes to General Quarters).
- **On a hit or shock to the tank zone:** roll a leak, with leak rate ∝ fill × breach size. A leak adds `vapour` to the compartment and connected spaces each tick (more if ventilation runs or hatches are open; vents outward in an open hangar).
- **Ignition roll per tick** ∝ vapour concentration × ignition sources (powered electrical machinery, fire nearby, an aircraft crash). An explosion deals blast to the compartment and its neighbours, can buckle even an armoured deck (Taiho), and starts fires.
- **Doctrine knobs** (USN learned these mid-war; IJN reached them late or never): `drain_and_purge_lines`, `shut_off_sparking_equipment`, `ventilation_policy`.
- A live system at the moment of the hit adds fire load along the deck lines (Franklin aft system).

---

## 5. Bomb and torpedo magazines, ordnance handling

- **Capacities:** Ark Royal about **225 t** of bombs and torpedoes; Illustrious about **175 t**. ([navweaps tech-030](https://www.navweaps.com/index_tech/tech-030.php)) I found no reliable sourced figure for Essex **[?]**.
- **Location and protection:**
  - **Illustrious:** magazines deep in the hull, under 120–100 lb NC from the hangar deck with 180 lb C side plating. Where they lay outside the armoured flight deck they had 3 in caps, plus 2–1.5 in NC bulkheads. ([armouredcarriers](https://www.armouredcarriers.com/hms-illustrious-armoured-aircraft-carrier-design))
  - **Shokaku:** 165 mm NVNC belt and 132 mm NVNC deck over the magazines. ([Wikipedia class](https://en.wikipedia.org/wiki/Sh%C5%8Dkaku-class_aircraft_carrier))
  - **Essex:** 2.5 in STS over steering gear and magazine. ([naval-encyclopedia](https://naval-encyclopedia.com/ww2/us/essex-class-fleet-aircraft-carriers.php))
- **Handling:** bombs travel by bomb elevators from the magazines to the hangar deck and flight deck. The danger is the ordnance *in transit or loose*, not in the magazine:
  - Kaga had 80,000 lb in the hangar.
  - On Franklin the lower magazines were never involved ("no fires or damaging effect were transmitted to the lower magazine spaces"), while deck and hangar ordnance devastated the ship.
- **Magazine flooding as damage control:**
  - Yorktown flooded magazines because of a rag-store fire next to them.
  - On Akagi the forward magazines were flooded, but the aft ones could not be because of valve damage.
- **Magazine detonations that lost the ship:**
  - **Liscome Bay:** one torpedo from I-175 behind the aft engine room set off the bomb stowage. It "sheared off nearly the entire stern", and she sank in **23 minutes** with 644 lost (702 in the end) of 916. ([Wikipedia](https://en.wikipedia.org/wiki/USS_Liscome_Bay))
  - **Shokaku:** forward magazines at the end.
  - **Princeton:** probably the aft magazine.
  - **HMS Avenger (CVE):** one torpedo from U-155. She sank "quickly"; 12 of 555 rescued. ([Wikipedia](https://en.wikipedia.org/wiki/HMS_Avenger_(D14))) The common claim that the bomb room detonated is **[?, not in this source]**.

**MODEL NOTE — magazines**
- Use standard magazine logic (see the battleship research). Carrier-specific extras:
  1. A **ready-ordnance pool** on the hangar and flight decks, which cooks off with fire much more readily than the magazine.
  2. **Bomb elevators** as a damageable component gating rearm rate.
  3. A **flood-magazine action** that needs working valves (Akagi).
- For CVEs, use a near-zero protection threshold and a high chance that a torpedo in the aft quarter detonates the magazine.

---

## 6. Island

- **Contents:** bridge (navigation), flag bridge, primary flight control, radar and radio aerials, and on USN, RN and late IJN ships the **funnel uptakes**.
- **Early and odd layouts:**
  - Hosho's island was removed in 1924 because it got in the way of aircraft. She used hinged funnels that swung horizontal during flight ops. ([Wikipedia](https://en.wikipedia.org/wiki/Japanese_aircraft_carrier_H%C5%8Dsh%C5%8D))
  - Ranger had six small hinged stacks. ([Wikipedia](https://en.wikipedia.org/wiki/USS_Ranger_(CV-4)))
  - Akagi and Hiryu had **port-side islands**; Akagi had a downward-angled main funnel to starboard.
  - Kaga had a single downturned starboard funnel after 1935 (her original long horizontal ducts were a failure). ([Wikipedia Kaga](https://en.wikipedia.org/wiki/Japanese_aircraft_carrier_Kaga))
  - Shokaku had two downward-curving starboard funnels.
  - Lexington had a huge funnel block and four 8 in twin turrets on the island side. ([Wikipedia](https://en.wikipedia.org/wiki/Lexington-class_aircraft_carrier))
- **Island hits:**
  - **Kaga:** a bomb destroyed the bridge, killing the captain, XO, navigator and gunnery officer. Damage control was left to junior officers and aviators, and the fires were soon out of control. ([combinedfleet Kaga](https://www.combinedfleet.com/kaga.htm))
  - **Glorious:** the bridge was hit at 16:58. ([Wikipedia](https://en.wikipedia.org/wiki/HMS_Glorious))
  - **Hornet (Santa Cruz):** a damaged Val crashed into the island, killing 7 and spraying burning fuel. ([Wikipedia](https://en.wikipedia.org/wiki/USS_Hornet_(CV-8)))
  - **Bunker Hill:** the second kamikaze hit near the island, and its bomb reached the ready room.
  - **Indefatigable:** a kamikaze hit the base of the island; 21 killed, deck operating again in about 30 min.
- **Funnel and uptake hits through the deck:**
  - **Yorktown, Midway:** a bomb exploded in the lower funnel, rupturing uptakes for three boilers and putting out boiler fires. Speed fell to 6 kt, then the ship stopped; she was back to about 20 kt roughly 1.5 h later. ([action report](https://www.history.navy.mil/research/archives/digital-exhibits-highlights/action-reports/wwii-battle-of-midway/uss-yorktown-action-report.html))
  - **Yorktown, Coral Sea:** punctured air intakes made three boiler rooms draw smoke back and be abandoned. ([midway42](http://www.midway42.org/TheBattle/YorktownDamage.aspx))
  - **Soryu:** one bomb went deep into the lower hangar and destroyed the engine uptakes. ([USNI](https://www.usni.org/magazines/naval-history-magazine/2017/june/sinking-carriers))

**MODEL NOTE — island**
- The island is a small, high-value target with sub-components:
  - `bridge` (loss gives a command/DC-efficiency penalty for N minutes);
  - `fly_control` (reduces the launch/recovery rate);
  - `radar` (loss of fighter direction and CAP effectiveness);
  - `uptakes` (link to the boilers: a hit there gives a temporary loss of boilers, which can be repaired in about 1–2 h; Yorktown).
- In the generator, if `funnel_type = island` route uptakes through the island. If it is `downturned_side` (IJN), place the uptake vulnerability in the side and gallery.

---

## 7. Machinery

- **Conversions inherited capital-ship machinery:**
  - **Lexington/Saratoga** kept their battlecruiser **turbo-electric** plant: 180,000 shp designed and over 202,000 shp on trials, with 4 GE turbo-generators and electric motors on the shafts. ([Wikipedia](https://en.wikipedia.org/wiki/Lexington-class_aircraft_carrier)) Its weakness is electrical: when an I-26 torpedo hit Saratoga on 31 Aug 1942 it flooded one fire room and **shorted the turbo-electric drive**, so she was towed by Minneapolis. ([Wikipedia](https://en.wikipedia.org/wiki/USS_Saratoga_(CV-3)))
  - **Langley** (ex-collier Jupiter) was the USN's first turbo-electric ship. ([Wikipedia](https://en.wikipedia.org/wiki/USS_Langley_(CV-1)))
  - **Béarn** (ex-Normandie battleship) had a mixed plant: Parsons turbines on the inner shafts and triple-expansion engines on the outer shafts. 21.5 kt. ([Wikipedia](https://en.wikipedia.org/wiki/French_aircraft_carrier_B%C3%A9arn))
  - **Courageous/Glorious** were ex-"large light cruisers" with fast cruiser machinery. **Akagi/Kaga** were battlecruiser/battleship conversions.
- **Purpose-built plants:**
  - **Essex:** 8 B&W boilers, 4 shafts, 150,000 shp, 33 kt. ([Wikipedia](https://en.wikipedia.org/wiki/Essex-class_aircraft_carrier))
  - **Shokaku:** 8 boilers, 160,000 shp. **Taiho:** 8 boilers, 160,000 shp, 33.3 kt.
  - **Midway:** 12 boilers, 212,000 shp.
  - **Graf Zeppelin:** 16 La Mont high-pressure boilers, 200,000 shp. **Illustrious:** 6 boilers, 3 shafts, 111,000 shp, 30.5 kt.
  - **Casablanca CVE:** 2 Skinner Unaflow reciprocating engines, 9,000 shp, 19 kt.
  - **Ranger:** 53,500 shp, 29.3 kt.
- **Uptakes run across or above the hangar, so they are vulnerable from the deck.** See section 6.
- **Electrical power as a single point of failure:**
  - **Ark Royal** had all electrical generation steam-driven and **no diesel backup**. When the boilers flooded, power was gone: no pumps and no lighting. The Bucknill Committee called this "a major design failure". ([Wikipedia](https://en.wikipedia.org/wiki/HMS_Ark_Royal_(91)))
  - **Kaga's** emergency pump generator was damaged. **Courageous** lost all electrical power from 2 torpedoes and capsized in 20 min.

**MODEL NOTE — machinery**
- Machinery: boiler rooms and engine rooms, plus a separate **power-generation graph**: turbo-generators, diesel generators (present or absent), switchboards.
- Fire mains, elevators, lift hydraulics, steering and sprinklers all draw on that graph.
- `turbo_electric` flag: higher shp density, but electrical flooding or shorting stops propulsion.
- `diesel_backup` flag: present on USN mid-war ships, absent on Ark Royal.

---

## 8. Side belt, TDS and torpedo vulnerability

### 8.1 Protection data
| Ship | Belt | Decks | TDS notes |
|---|---|---|---|
| Lexington | 7–5 in tapered (BC belt retained) | 2 in STS over machinery | 3–6 bulkheads of 0.375–0.75 in, with liquid layers |
| Yorktown | 2.5–4 in (102–64 mm) | 38 mm main deck / "60 lb" protective | Moderate |
| Wasp | 3.5 in side | 1.25 in | **No real TDS** |
| Ranger | 2 in | 1 in over steering | Minimal |
| Essex | 2.5–4 in on 0.75 in STS | 2.5 in hangar deck + 1.5 in 4th deck | — |
| Midway | 7.6 in port / 7 in starboard | 2 in hangar deck, 3.5 in flight deck | — |
| Illustrious | 4.5 in | 3 in flight deck, 4.5 in hangar sides | Voids plus oil wing tanks, rated for a **750 lb** warhead |
| Indomitable | as Illustrious | Hangar sides 1.5 in | — |
| Implacable | 4.5 in | 3 in flight deck; hangar sides 1.5–2 in; hangar deck 1.5–2.5 in | — |
| Ark Royal | 4.5 in | 3.5 in over boilers and magazines | Long uninterrupted boiler room |
| Courageous / Glorious | 2–3 in | 0.75–1 in | 1–1.5 in torpedo bulkheads |
| Béarn | 83 mm deep belt | 24 mm upper deck | — |
| Akagi (1938) | 152 mm | 79 mm **[?: lower protective deck]** | — |
| Kaga (1935) | 152 mm | 38 mm | — |
| Shokaku | 46 mm general; 65 mm machinery; 165 mm magazines | 65 mm machinery; 132 mm magazines; 105 mm avgas; flight and hangar decks unprotected | First IJN carrier with a torpedo belt system (liquid sandwich, 18–30 mm Ducol bulkhead) |
| Taiho | 40–152 mm | 75–80 mm flight deck; 32 mm lower hangar | — |
| Shinano | 160–400 mm | 75 mm flight deck | Flawed belt/bulge joint |
| Graf Zeppelin | 100 mm | 45 mm flight deck + 60 mm | — |
| Casablanca CVE | none (splinter plating) | — | none |

Sources: the class and ship Wikipedia pages cited above; [navypedia Yorktown](https://www.navypedia.org/ships/usa/us_cv_yorktown.htm); [navypedia Shokaku](https://www.navypedia.org/ships/japan/jap_cv_shokaku.htm); [armouredcarriers](https://www.armouredcarriers.com/hms-illustrious-armoured-aircraft-carrier-design).

### 8.2 Torpedo-loss case studies
- **Ark Royal, 13–14 Nov 1941:** **one** torpedo from U-81 at 15:40, amidships below the island between the bunkers and the bomb store. It made a **130×30 ft** hole and flooded the starboard boiler room, **main switchboard**, oil tanks and 106 ft of the starboard bilge. Water got in via uptakes and air intakes. Power was lost and the list grew to about 45°; she capsized at 06:19 next day, **about 15 h** later. One man died. ([Wikipedia](https://en.wikipedia.org/wiki/HMS_Ark_Royal_(91)))
- **Courageous, 17 Sep 1939:** 2 of 3 torpedoes from U-29 hit to port. All electrical power was lost, and she capsized in **20 min** with 519 lost. ([Wikipedia](https://en.wikipedia.org/wiki/HMS_Courageous_(50)))
- **Yorktown, Midway:**
  - **Air torpedoes:** two port hits at frames 90 and 75 blew out all boiler fires; dead in the water, 26° list, abandoned.
  - **Next day:** salvage was under way when 2 torpedoes from I-168 hit, plus 1 on the destroyer Hammann alongside. She sank on 7 June. Unrepaired Coral Sea damage in the same area is cited as a factor. ([midway42](http://www.midway42.org/TheBattle/YorktownDamage.aspx); [Wikipedia](https://en.wikipedia.org/wiki/USS_Yorktown_(CV-5)))
- **Hornet, Santa Cruz:**
  - **The air attack:** 3 bombs, 2 air torpedoes and 2 crashing aircraft. Power was lost and she was taken in tow by Northampton at 5 kt.
  - **The fatal hit:** a later torpedo to starboard, giving a 14° list.
  - **Scuttling:** US ships fired 9 torpedoes (most failed) and **430 rounds of 5 in** without sinking her. Japanese destroyers finished her with 4 Long Lances. 140 dead. ([Wikipedia](https://en.wikipedia.org/wiki/USS_Hornet_(CV-8)))
- **Saratoga:** 11 Jan 1942, I-6, 3 boiler rooms flooded, 16 kt max, 6 killed. 31 Aug 1942, I-26, 1 fire room, 4° list, turbo-electric drive disabled. She survived both. ([Wikipedia](https://en.wikipedia.org/wiki/USS_Saratoga_(CV-3)))
- **Shinano, 29 Nov 1944:** 4 of 6 torpedoes from Archerfish, set at a **10 ft depth**. They hit the stern, the starboard shaft compartment, No. 3 boiler room and the air-compressor room. All detonated at the weak **belt/bulge joint**. Most watertight doors were not fitted and compartments were untested, and the pumps were inoperable. She sank **about 7.75 h** later with 1,435 dead. ([Wikipedia](https://en.wikipedia.org/wiki/Japanese_aircraft_carrier_Shinano))
- **Wasp, Taiho, Shokaku, Liscome Bay:** torpedo hits whose real killer was avgas, fire or magazine (see sections 4 and 5).

**MODEL NOTE — belt and TDS**
- Reuse the hull TDS model: depth, layers, liquid loading, rated warhead.
- Carrier extras:
  1. A **"shallow hit at a joint" weak-point modifier** (Shinano).
  2. **Uptake and air-intake flooding paths** from boiler rooms that spread flooding once power is lost (Ark Royal).
  3. **Tank-zone adjacency:** a torpedo hit next to the avgas or magazine zone calls the avgas or magazine logic (Taiho, Wasp, Lexington, Liscome Bay, Shokaku).
  4. **Incomplete ship / green crew** modifiers: missing watertight doors, poor DC (Shinano).

---

## 9. Air group as a component

| Ship | Aircraft |
|---|---|
| Langley | 34–36 |
| Lexington | about 90 design |
| Ranger | 76 normal / 86 max |
| Yorktown | 90–96 design |
| Wasp | up to 100 |
| Essex | 90–100+ (110 per navweaps) |
| Midway | 132 in 1945 (64 F4U, 64 SB2C, 4 F6F-P) |
| Illustrious | 33–36, later 52–57 |
| Implacable | 48 hangar, up to 81 |
| Ark Royal | 72 design, 50–60 actual |
| Courageous / Glorious | 48 |
| Béarn | 32 |
| Akagi | 86–91 (60 at Midway) |
| Kaga | 90 (72 operational + 18 spare) |
| Shokaku | 72 + 12 |
| Taiho | 65 (53–82 planned) |
| Shinano | 47 organic plus a ferry load of up to 120 |
| Hosho | 15 |
| Graf Zeppelin | 42 planned |
| Casablanca CVE | 27 |

**Losses of the air group as a mission kill:**
- Saratoga, 21 Feb 1945: **40 aircraft destroyed**, 123 dead or missing.
- Franklin: 59 lost on deck plus hangar losses.
- Formidable: 10 lost from one kamikaze.
- Illustrious, 1941: 9 Swordfish + 5 Fulmars.
- Wasp: 45 went down with the ship.
- Hornet: 21.
- Enterprise, Santa Cruz: 16 of 73 ditched because the deck could not take them.

There is also an **attrition trade-off:** TF 58 (15 carriers) destroyed 1,908 Japanese aircraft against TF 57 (4 RN carriers) with 75, and each force had 4 carriers damaged. ([navweaps tech-030](https://www.navweaps.com/index_tech/tech-030.php)) D.K. Brown concluded: "More fighters would have been better protection than armour."

**MODEL NOTE — air group**
- Track aircraft individually or as squadrons, with a location (`hangar bay N`, `deck segment N`, `airborne`) and `fuel` and `armed` state.
- Ship damage destroys aircraft by location.
- Capability = f(surviving aircraft, deck state, lift state, avgas available, ordnance available, island/fly control).
- A carrier can be "alive but useless". Score that as a **mission kill** separate from sinking.
- Airborne aircraft without a usable deck must divert or ditch on a fuel timer.

---

## 10. Escort carriers

- **Casablanca class:** about 8,188 t standard / 10,902 t full load, 512 ft, 27 aircraft, 2 lifts, 1 catapult. **No armour** beyond splinter plating. Twin reciprocating engines, 19 kt; crew about 910–916. Five were lost: Liscome Bay (torpedo/magazine), Gambier Bay (gunfire), St. Lo, Ommaney Bay and Bismarck Sea (kamikazes). ([Wikipedia](https://en.wikipedia.org/wiki/Casablanca-class_escort_carrier))
- **Hulls:** merchant-type hulls (C3 for Bogue) or the purpose-designed Casablanca on mercantile lines.
- **Liscome Bay, 24 Nov 1943:** one torpedo into the bomb stowage aft; sank in 23 min, 644 died at once. The group was not zig-zagging. ([Wikipedia](https://en.wikipedia.org/wiki/USS_Liscome_Bay))
- **Gambier Bay, 25 Oct 1944:** at least 15 hits (8 in from Chikuma, 6 in, possibly 18.1 in from Yamato).
  - AP shells **over-penetrated without detonating** **[the Yamato attribution is contested]**.
  - A hit at about 08:20 flooded the forward engine room: speed fell to 10 kt, then dead in the water about 15 min later.
  - Capsized 09:07, sank 09:11; 147 killed. ([Wikipedia](https://en.wikipedia.org/wiki/USS_Gambier_Bay))
- **RN CVEs:** Avenger lost to one torpedo with 12 survivors; Dasher lost to an internal avgas explosion. ([Avenger](https://en.wikipedia.org/wiki/HMS_Avenger_(D14)); [Dasher](https://en.wikipedia.org/wiki/HMS_Dasher_(D37)))

**MODEL NOTE — CVE**
- Use the same component model with protection set to zero.
- Thin plating gives a **high AP over-penetration (dud) chance**: large shells may pass through without fuzing.
- Use a single engine-room pair, so one flooded engine room causes a large speed loss.
- Magazine aft near the shafts, giving a high chance of catastrophic detonation from a torpedo aft.

---

## 11. Damage-control lessons

- **USN improvement curve, 1942–45:**
  - Lexington's loss produced inerting, segregated gasoline systems and spark control.
  - Yorktown's CO2 purge worked at Midway.
  - Fog nozzles, foam outlets, gasoline-driven emergency fire pumps, handy-billy portable pumps, and universal fire-fighting training (260+ instructors trained). ([Pacific War Encyclopedia](http://pwencycl.kgbudge.com/D/a/Damage_Control.htm))
  - Franklin and Bunker Hill survived catastrophic fires because:
    1. the structure, watertight integrity and machinery below the armoured hangar deck stayed intact;
    2. 706 men (103 officers + 603 enlisted, per the WDR) stayed aboard to fight fires;
    3. other ships came alongside to help.
- **Franklin WDR recommendations:**
  - fire-main sectionalisation in about 4 sections rather than 8;
  - armoured conflagration station;
  - longer hoses;
  - hangar subdivision into 5 compartments;
  - an armoured flight deck on the CVB.
  - The report also notes British armoured decks made kamikazes "ricochet". ([Franklin WDR](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-franklin-cv-13-war-damage-report-no-56.html))
  - The WDR gives the CVB armoured flight deck as "1½-inch STS". Other sources say 3.5 in **[conflict]**.
- **Kamikazes against armoured decks:**
  - **RN ships stayed on station:** Formidable was out of action about 4–6 h and lost 8–9 killed.
  - **USN ships were withdrawn for months:** Bunker Hill (389–396 killed, about 4 months), Ticonderoga (143 killed), Saratoga (123), Franklin (724–807, never returned to active service). ([armouredcarriers](https://www.armouredcarriers.com/were-the-armoured-carriers-worthwhile) **[advocacy]**; [navweaps tech-042](https://www.navweaps.com/index_tech/tech-042.php))
  - **Counter-view:** RN carriers received "relatively tame treatment from the kamikazes". Long-term structural damage made several RN armoured carriers uneconomic to repair or rebuild (Illustrious, Formidable, Indomitable, and Victorious's costly rebuild). ([navweaps tech-030](https://www.navweaps.com/index_tech/tech-030.php))
- **Japanese losses to fire:**
  - Damage-control responsibility was divided between engineering below and the deck officer topside, and training was poor. ([Pacific War Encyclopedia](http://pwencycl.kgbudge.com/D/a/Damage_Control.htm))
  - Taiho's DC officer made it worse by opening the ventilation.
  - Multicore cables were hard to repair.
  - Later improvement: Zuikaku at Philippine Sea contained her fires.

**MODEL NOTE — damage control**
- Use a per-nation, per-year DC tech and doctrine table:
  - `fog_foam` (USN from mid-1942);
  - `independent_fire_pumps`;
  - `gas_purge_doctrine` (USN after May 1942, IJN effectively never);
  - `vent_policy` (good: exhaust only from affected spaces; bad: open everything);
  - `crew_DC_skill`;
  - `conflagration_station_armoured`.
- Fire mains are sectioned. A hit severing both port and starboard mains in a zone disables suppression there (Kaga, Wasp).
- Helper ships alongside add pumping and hoses but are exposed to blast (Birmingham alongside Princeton).

---

## 12. Representative carriers

Displacement in long tons standard unless noted. "FD" = flight deck armour; "HD" = hangar deck or protective deck armour. Avgas is in US gal unless noted.

| Ship (year) | Displ. | Aircraft | FD armour | HD / prot. deck | Belt | Lifts | Avgas | Damage fate |
|---|---|---|---|---|---|---|---|---|
| Langley CV-1 (1922) | 12,700 | 34–36 | none (wood) | — | none | 1 | ? | Hit by 5 bombs (G4M) on 27 Feb 1942; scuttled |
| Lexington CV-2 (1927) | 36,000 | ~90 design; ~70 actual | none | 2 in STS over machinery | 7–5 in | 2 | 132k–163k [?] | Coral Sea 1942: 2–3 torpedoes + 2 bombs, then avgas vapour explosions; fire mains lost; scuttled |
| Akagi (1938 rebuild) | 36,500 | 86–91 | none | 79 mm [?] | 152 mm | 3 | ~150,000 | Midway: 1 bomb + near misses; hangar ordnance and avgas fire; rudder jammed; scuttled |
| Kaga (1935 rebuild) | 38,200 | 90 | none | 38 mm | 152 mm | 3 | ? (tanks integral) | Midway: 4 bombs, bridge destroyed, 80,000 lb of hangar ordnance; 811 dead; scuttled |
| Hosho (1922) | 7,470 | 15 | none | none | none | 2 | ? | Survived the war |
| Ranger CV-4 (1934) | 14,576 | 76–86 | none | 1 in (steering) | 2 in | 3 | ? | Survived (Atlantic) |
| Yorktown CV-5 (1937) | 19,875 (25,484 full load) | 90–96 | none | 38 mm / "60 lb" | 2.5–4 in | 3 | ~178,000 (673,900 L) | Coral Sea bomb; Midway: 3 bombs (deck patched in 25 min), 2 air torpedoes + 2 submarine torpedoes; sank |
| Essex CV-9 (1942) | 27,100–30,800 (36,380 full load) | 90–110 | none (wood) | 2.5 in hangar deck + 1.5 in 4th deck | 2.5–4 in | 2 + 1 deck-edge | 231,650 | None lost; Franklin and Bunker Hill survived catastrophic fires |
| Ark Royal (1938) | 22,000 | 50–60 (72 design) | none [? "3.5 in deck" was the lower deck] | 3.5 in over boilers and magazines | 4.5 in | 3 | ~100,000 (Imp?) | 1 torpedo in 1941; flooding via uptakes, no backup power; sank about 15 h later; 1 dead |
| Illustrious (1940) | 23,000 | 36, later 57 | 3 in (box 458×62 ft) | 4.5 in hangar sides | 4.5 in | 2 | 50,540–50,650 Imp | Jan 1941: 6 bombs (one 1,000 kg class penetrated); 126 killed; survived |
| Implacable (1944) | 32,110 full load | 48, later 81 | 3 in | 1.5–2.5 in HD; 1.5–2 in sides | 4.5 in | 2 | 94,650 Imp [?] | No kamikaze damage; Indefatigable resumed ops 30 min after an island hit |
| Shokaku (1941) | 25,675 | 72 + 12 | none | 65 mm (machinery) / 132 mm (magazines) / 105 mm (avgas) | 46 / 65 / 165 mm | 3 | ~150,000 [?] | Coral Sea and Santa Cruz bomb damage survived; 1944: 3–4 torpedoes, avgas main shattered, magazine explosion after about 2.8 h; sank |
| Taiho (1944) | 29,770 | 65 | 75–80 mm on 20 mm | 32 mm lower HD | 40–152 mm | 2 | ? | 1 torpedo, then avgas vapour; ventilation spread it; explosion at +6.4 h; sank |
| Shinano (1944) | 65,800 t | 47 + ferry | 75 mm on 20 mm | — | 160–400 mm | 2 | 720,000 L | 4 torpedoes at the belt/bulge joint; unfinished watertight work; sank after about 7.75 h |
| Graf Zeppelin (unfinished) | 33,550 full load | 42 planned | 45 mm | 60 mm | 100 mm | 3 | ? | Never completed; Soviet target ship in 1947 |
| Midway CVB-41 (1945) | 45,000 (60,000 full load) | 132 | 3.5 in [WDR says 1.5 in] | 2 in | 7.6 in / 7 in | 2 + 1 deck-edge | ? | Postwar |
| Casablanca CVE | 8,188 | 27 | none | none | none | 2 | ? (US CVE type 75k–88k?) | Liscome Bay: 1 torpedo, magazine detonation, 23 min; Gambier Bay: gunfire, about 50 min |
| *Extra:* Courageous / Glorious | 24,210–24,970 | 48 | none | 0.75–1 in | 2–3 in | 2 | 34,500 Imp | Courageous: 2 torpedoes, 20 min. Glorious: 11 in shells; flight deck out at the first hit; sank 92 min after it |
| *Extra:* Béarn | 22,146 | 32 | none | 24 mm | 83 mm | 3 (slow) | 100,000 L, N2-inerted | Survived |
| *Extra:* Wasp CV-7 | 14,700 | ~100 | none | 1.25 in | 3.5 in | 2 + deck-edge | ? | 2–3 torpedoes near the avgas; fire mains lost; scuttled |

---

## 13. Suggested component list for the parametric carrier generator

1. **Flight deck segments** (×5–7): armour class, strength-deck flag, state, repair timer.
2. **Arresting gear** (wires as one group) and **barriers** (×1–3), each damageable.
3. **Catapults** (0–2 deck, 0–2 hangar).
4. **Elevators** (×1–3): centreline or deck-edge, power source, state.
5. **Hangar bays** (×2–5 per hangar level; 1–2 levels): open or closed, curtain or bulkhead between bays, sprinkler/foam, aircraft list, loose ordnance.
6. **Avgas tank groups** (fwd/aft): fill, protection type, integral flag, line state (live / drained / purged), vapour field.
7. **Avgas lines** (port/starboard, segregated or not): run along the hangar and gallery.
8. **Bomb/torpedo magazines** (fwd/aft) and **bomb elevators**.
9. **Island:** bridge, fly control, radar, uptakes (linked to boilers).
10. **Machinery:** boiler and engine rooms, power generation (turbo-generators, diesels, switchboards), turbo-electric flag.
11. **Fire mains** (sections ×4–8, port and starboard) plus independent pumps; **conflagration station**.
12. **Belt / TDS / armoured deck:** reuse the generic hull model, with the joint-weakness modifier.
13. **Ventilation network** (for vapour and smoke spread; Bunker Hill smoke, Taiho vapour).
14. **Air group:** aircraft entities with location, fuel and armed state.

Mission-kill conditions to expose to gameplay:
- Launch impossible: no clear deck run, or no catapult and insufficient wind or speed.
- Recovery impossible: aft segments or wires or all barriers gone.
- Re-spot rate zero: all lifts down.
- No avgas: tanks lost or lines cut.
- No ordnance: magazines flooded, or bomb elevators down.
