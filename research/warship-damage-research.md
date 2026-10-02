# Warship internals & damage modelling: research base (1890–1945)

*Compiled 2026-10-02 for the Naval project's ship generator (shipgen). This is the broad, un-pared research step. Gamification and performance trimming come later.*

**How to use this doc.** It is the synthesis. Five detailed research files back it (≈40k words, every figure cited inline). They are stored next to this doc as `claude/damage-research/01…05`:

| File | Scope |
|---|---|
| `01_capital_subdivision.md` | Bulkheads, armour schemes, torpedo protection (TDS), ends, counterflooding; table of 19 capital ships |
| `02_components.md` | Every internal system and how it fails; component summary table; crew-casualty mechanisms |
| `03_small_vessels.md` | Protected/armoured cruisers, cruisers, TBs/TBDs, destroyers, escorts, MTB/PT/S-boat/MAS/G-5, submarines |
| `04_carriers.md` | Flight deck, lifts, hangars, avgas, ordnance, island, TDS, air group, CVEs; 17-carrier table |
| `05_mechanics_and_games.md` | Shell, fuze and penetration formulas, shock, flooding/stability, fire, loss statistics; prior art (RTW, UA:D, Atlantic Fleet, WoWS, Harpoon, tabletop) |

Conventions: positions are fractions of waterline length L from the bow (0 = bow, 1 = stern). "Tier A/B/C/D" protection: A = inside citadel under belt + armour deck; B = heavy local armour (turret, barbette, CT); C = splinter-proof (~25–50 mm); D = none. "(?)" means approximate, conflicting or weakly sourced; see §14.

---

## 1. The ten things that matter most

1. **Ships sink from water, not from holes in armour.** Penetrating the citadel rarely sinks a ship. Bismarck took ~400 hits with no underwater penetration of the citadel. What kills is flooding that gets *around* subdivision (shaft glands, vents, open doors, failed rivets), **asymmetric flooding → capsize**, or a **magazine explosion**.
2. **Catastrophic losses are nearly always ammunition, usually via flash or fire, not a shell bursting inside the magazine.** Examples: the Jutland battlecruisers, Hood, Barham, Arizona, Mutsu, Kongō, Yamato, Mikuma, Astoria and Liscome Bay. Propellant chemistry is a per-navy setting: British cordite was very flash-sensitive, while German brass-cased RP C/12 burned without detonating (Derfflinger, Gneisenau).
3. **Mission kills come long before sinking.** South Dakota took 26 hits, almost all medium-calibre or HE, and nothing threatened buoyancy. She still lost radar, fire control, communications and power for minutes at a time. **Electrical distribution was the real Achilles heel** of WWII ships. Model systems as a **dependency graph**, not as separate hit-point bars.
4. **The stern is the "golden BB" zone.** Rudders and shafts cannot be armoured. Bismarck (rudder jammed 12°), Hiei and Kirishima (steering), and Prince of Wales (one torpedo at a shaft → shaft whip → progressive flooding → power loss → sunk) were all doomed by stern hits.
5. **Torpedo protection depth is the most important underwater number.** WWII systems were 4–7 m deep amidships, rated for 300–450 kg TNT. They were **always shallower near the end turrets**, and that is where hits got through (North Carolina, Yamato, Littorio).
6. **Small ships die by adjacent-compartment flooding and broken backs.** USN destroyers were designed to survive four adjacent main compartments flooding; in practice the limit was ~2 machinery spaces (small) to ~3 (large). One torpedo usually killed them (7 of 31 survived). Gunfire, bombs and kamikazes did not (84% survived). Bow or stern loss is survivable; heavy damage amidships breaks the hull girder.
7. **Carriers die by fire and fuel vapour, and the state at the moment of the hit matters more than armour.** Fuelled and armed aircraft, loose ordnance and live avgas lines turned single hits into losses (Akagi, Kaga, Franklin, Taihō). Vapour explosions came hours late: Lexington +1.5 h, Shōkaku +2.8 h, Taihō +6.4 h.
8. **Fire is a force multiplier, not a hit-point drain.** It lights the ship as a target, destroys unarmoured systems, makes spaces uninhabitable and cooks off magazines over time. Water on the fire within about a minute usually prevented ammunition explosions.
9. **Damage-control quality multiplies everything.** Identical hulls survive or sink depending on counterflood speed, pump power, closure discipline and doctrine. Compare USN 1943+ with the IJN, and Audacious and Prince of Wales with North Carolina.
10. **Hit count is a terrible predictor; location dominates.** Seydlitz survived 21 heavy hits plus a torpedo; Lützow was lost to 2 underwater hits forward. The rough rule "≈1 lb of ordnance per ton of target" (?) is only a sanity check.

---

## 2. Anatomy: the ship as layered zones

### 2.1 Vertical zones (all steel warships)

| Zone | What's there | Damage behaviour |
|---|---|---|
| **Bottom** (double or triple bottom, ~1.5–1.8 m ≈ 0.07–0.10 D) | Fuel and water tanks, voids | Mine and under-keel torpedo whipping; grounding |
| **Side protection** (TDS / bulges / coal bunkers / cofferdams) | Void–liquid–void layers, holding bulkhead | Absorbs contact underwater explosions; always floods on the hit side |
| **Below armour deck: the "raft"** | Magazines, shell rooms, boiler and engine rooms, plot or transmitting station, switchboards, generators, steering gear (boxed) | Well subdivided; slow flooding spread; tier A |
| **Between armour deck and weather deck** | Crew spaces, galley, secondary handling, cable runs, casemates, vents | Weakly subdivided; water spreads fast once it is below the sea (Lützow); fire load |
| **Superstructure** | Bridge, CT, directors, radar, masts, AA, boats, aircraft, funnels | No buoyancy. Splinters and soft-target damage; mission kills |

### 2.2 Longitudinal layout templates (typical fractions, for the auto-layout)

**Capital ship (2 turrets forward, 2 aft):**
- 0–0.08 forepeak and chain locker
- 0.08–0.20 bow (soft end)
- 0.15–0.35 forward magazine group under A/B
- ~0.25–0.35 conning tower, bridge, foremast director
- 0.35–0.55 boiler rooms
- 0.55–0.70 engine rooms
- 0.65–0.85 aft magazine group under X/Y
- 0.70–0.95 shaft alleys
- 0.90–0.97 steering gear
- 0.95–1.0 rudders
- **Citadel ≈ 0.50–0.70 L** (Yamato 53.5%, Nelson 54.7%, Bismarck ~70%; Majestic belt ~56%).

**Cruiser:**
- 0–0.08 forepeak
- 0.08–0.30 forward turrets over boxed magazines
- 0.30–0.65 machinery (US: unit system FR/ER/FR/ER)
- 0.65–0.85 aft turrets and magazines
- 0.85–1.0 steering
- Belt and deck cover ~0.25–0.80 only.

**Destroyer (Fletcher-like):**
- 0–0.05 forepeak
- 0.05–0.25 forward magazines under mounts 1–2
- 0.25–0.30 bridge/CIC above, tanks below
- **0.35–0.65 machinery** (~⅓ of length, ~½ of volume); torpedo mounts above it
- 0.65–0.85 aft magazines
- 0.85–1.0 steering, depth charges

**Carrier:** machinery amidships under the hangar. Avgas tanks forward and aft, low and inboard. Bomb magazines fore and aft. Uptakes rise through or beside the hangar into the island (USN/RN) or out of the side (IJN). Lifts at ~0.2, ~0.5 and ~0.8. Flight deck runs the full length.

**PT boat (Higgins 78 ft, 8 WT compartments, plywood bulkheads):** forepeak → crew/galley → wardroom → forward tank room → engine room → aft tank room → aft crew → lazarette/rudder.

**Submarine (USN fleet boat, 8 pressure-bulkheaded compartments + conning tower):** forward torpedo room → forward battery → control → after battery → forward engine room → after engine room → manoeuvring → after torpedo room.

---

## 3. Subdivision & bulkheads

### 3.1 Transverse watertight bulkheads

- **Main WT compartments:**
  - Nassau 16–19; Kaiser and Seydlitz 17; Bismarck 22; Admiral Hipper 14.
  - **Rule of thumb: a main bulkhead every ≈0.05–0.07 L**, so 15–22 for capital ships, 12–16 for destroyers, 6–9 for coastal craft.
- **Fine subdivision** (decks, flats, longitudinals) multiplies the count: Majestic 72 compartments in the citadel + 78 outside; Tennessee 768 below the waterline + 180 above; Yamato 1,147, of which 1,065 are below the armour deck. Abstract this as a scalar **"subdivision quality"** (lower flooded fraction per hit, slower spread).
- **Bulkheads snap to function:** barbettes, magazine groups, each boiler and engine room, citadel ends (armoured transverse bulkheads).
- **How bulkheads fail:**
  - Riveted seams open under blast or whipping (North Carolina's holding bulkhead failed by its rivets, not its plate).
  - Penetrations leak.
  - Doors are left open.
  - Water head or speed overloads the plate (Seydlitz steamed *astern* to ease her bulkheads).

### 3.2 Longitudinal bulkheads: the centreline trap

A centreline bulkhead splitting the machinery spaces confines flooding to one side. That causes heel, which lowers freeboard on that side, which floods more, until the ship capsizes.
- **All six British pre-dreadnoughts sunk by torpedo in WWI capsized.**
- The Borodinos at Tsushima capsized (centreline bulkhead plus ~1,700 t overload).
- Yamato (hits mostly to port) went after ~11 torpedoes; Musashi (hit on both sides) took 19.
- The USN deliberately avoided machinery centreline bulkheads.
- **Generator option:** `centreline_machinery_bulkhead: bool`. True means less water per hit but heeling moment `w·(±B/4)`.

### 3.3 Bottoms, wing spaces, fill materials

- **Double bottom** over 72–88% of L (Hipper 72%, Bismarck 83%, Nassau/Kaiser 88%). **Triple bottom** on US fast battleships (NC: 5.75 ft). `bottom_layers ∈ {1,2,3}` reduces under-keel damage.
- **Coal bunkers** (1890–~1915) absorbed splinters and limited flooding (μ ≈ 0.4 when full). Protection falls as coal burns. Their value against shells is low; see §14.
- **Cofferdams:**
  - Cellulose / coconut fibre (1890s protected cruisers): swelled shut. In a 1890 test, three 6-in holes had a combined leak of only ~2 gal/min after an hour.
  - "Ébonite mousse" foam (Richelieu) and "Cellulite" (Littorio).
- **Splinter cells:** Bismarck's 30 mm longitudinals made 51 armoured cells between decks.

### 3.4 Torpedo protection systems (TDS)

| System | Depth amidships | Rated charge |
|---|---|---|
| Nelson | 12 ft (incl. 5 ft double bottom) | 750 lb |
| KGV | ~13 ft + 8 ft auxiliary | 1,000 lb (full-scale tested) |
| North Carolina | 18.5 ft, 5 bulkheads | 700 lb |
| SoDak / Iowa | 17.9 ft, 4 bulkheads (lower belt = 3rd) | 700 lb |
| Bismarck | 5.5 m, 45–53 mm bulkhead | — |
| Littorio (Pugliese) | 3.8 m drum (2.28 m at turrets) | 350 kg |
| Richelieu | 7 m (Jean Bart 8.5 m) | — |
| Yamato | 5.1 m, no liquid layers | 400 kg |
| Illustrious (CV) | — | 750 lb |

- **Parametric rule:** `TDS_depth ≈ k·B`, k ≈ 0.13–0.22 (US 0.17, Richelieu 0.21, Yamato 0.13).
  - Taper the depth to ~50–60% at the end turrets and to 0 outside the citadel.
  - An amateur regression, `rating_lb ≈ 37.6·depth_ft − 132`, under-predicts US systems; use it only as a baseline.
- **Failure modes:**
  1. Shallow sections near the turrets (NC: 970 t, two magazines flooded).
  2. Riveted belt/bulge joints shear (Yamato 1943, ~3,000 t; Shinano; Pugliese).
  3. Hits outside the TDS: ends, shafts, rudder.
  4. Counterflooding into TDS voids removes the air buffer (PoW).
  5. Repeated hits in one area overwhelm any system.
- **Typical single-torpedo flooding on a capital ship:** ~1,000–4,000 t; list 3–6°, correctable.

### 3.5 Leak paths (what really sinks ships)

- **Shaft glands / shaft alley.** PoW: the whirling shaft wrecked glands at 5 bulkheads, and the engine room was evacuated 18 min after the hit.
- **Ventilation trunks.** NC handling-room flooding; Taihō vapour spread.
- **Pipes and valves through bulkheads, cable glands, open WT doors and manholes.** Audacious; California at Pearl Harbor.
- **Casemate ports.** Iron Duke; Good Hope and Monmouth at Coronel.
- **Boiler uptakes and air intakes.** Ark Royal.
- **Fire mains.** Ruptured mains *cause* flooding: Ralph Talbot listed 20°.

Model each bulkhead's `leak_rate = base(era, riveted/welded) + Σ penetrations`. Multiply by closure state (cruising vs general quarters).

### 3.6 Above vs below the armour deck

Two flooding layers per section. Below the armour deck is subdivided and spreads slowly. Above it, spread is fast **once that deck goes below the outside waterline through sinkage or trim**. This one rule reproduces Lützow (~8,000 t, forward draught over 17 m, scuttled), Seydlitz (5,308 t, survived) and Bismarck's bow.

---

## 4. Armour

### 4.1 Elements

- **Main belt** at the waterline, ~1–1.5 m below to ~1–3 m above the design waterline (height ≈ 0.35–0.55 D).
  - Optional upper belt, end belts (incremental schemes) and inclined or internal belts (`t_eff = t / cos θ`).
  - Optional lower belt tapering to the bottom (SoDak, Iowa, Yamato) against diving shells.
- **Armour deck:** flat-high (US/RN all-or-nothing) or low with sloped sides (turtleback; pre-dreadnoughts; Bismarck 80–100 mm flat + 110–120 mm slopes).
  - Plus a **splinter deck** below (~16 mm) and/or a **bomb/decapping deck** above (Iowa 1.5 in, KGV 1.25 in, Bismarck 50 mm).
- **Armoured transverse bulkheads** close the citadel ends.
- **Barbettes** are thickest exposed and thinner behind the belt. **Turret faces** are thickest, then sides, then roof; the face–roof joint is weak (Lion Q, Tiger).
- **Conning tower:** heavily armoured, rarely used by commanders, and its vision slits let splinters in.
- **Steering gear box:** protects the gear, not the rudder.
- **Spaced decapping plate** (Littorio 70 mm + 250 mm gap + 280 mm) needs ≈0.08–0.12 calibre to strip a cap.

### 4.2 Schemes

| | Incremental ("everything") | All-or-nothing (Nevada 1912 →) |
|---|---|---|
| Idea | Medium armour everywhere keeps out HE and splinters and keeps ends buoyant | Thick belt, deck, turrets and barbettes over a "raft" citadel; nothing elsewhere |
| Weakness | Medium plate fuzes AP shells | Upper works shredded by medium calibre → mission kill (South Dakota) |

- **Armour weight ≈ 30–41% of displacement** in WWII battleships (Yamato 33%, Iowa 35%, Bismarck ~40%, NC 41%). Flag designs outside ~20–45%.
- **Immune zone:** the range band where the belt holds (near limit) and the deck holds (far limit). Example: Iowa vs 16″/45, 16,100–28,500 m.
  - Cheap to compute per enemy gun and excellent player feedback.
  - RTW shows it only against your own guns, and players wish for more.

---

## 5. Component catalogue

Tiers present: **M** = MTB/coastal, **D** = destroyer/escort, **C** = cruiser, **B** = battleship, **V** = carrier.

| Component | Present | Typical location | Prot. | Primary threat | Effect when lost | Repair at sea | Depends on |
|---|---|---|---|---|---|---|---|
| Main magazine (propellant) | D C B V | under turrets 0.15–0.35 / 0.65–0.85, hold level | A | Flash chain, plunging shell or bomb, fire, torpedo under it | **Ship lost**; if flooded, that turret is out | Flooding is an action | Valves (crew) or pumps (power) to flood |
| Shell room | D C B | next to magazine (RN: propellant deepest from Nelson on) | A | As above, less sensitive | Turret starved | No | — |
| Secondary/AA magazine | D C B V | often outboard / separate | A–B | Fire, torpedo | Can chain to main magazine (Barham, Hood) | No | — |
| Ready-use ammo lockers | M D C B V | beside mounts | D | Splinters, fire | Local fire and casualties | Restock | — |
| Deck torpedoes + reloads | M D C | amidships deck | D–C | Shell, fire, **even a near miss** (Suzuya) | Massive explosion and hull breach (Mikuma) | **Jettison** (Mogami survived) | — |
| Depth charges | D | stern | D | Fire, sinking | Kills survivors in the water | Set safe | — |
| Turret gunhouse | D C B | centreline | B (DD: C) | Penetration, joint hits | Crew killed; flash chain | Sometimes | Power, crew |
| Barbette / roller path | C B | under gunhouse | B | Heavy non-penetrating hit | **Jammed in train** | Rarely, hours | — |
| Hoists | C B | in barbette | B | Hits, power loss | Rate of fire ×0.5 or 0 | Partial | Power |
| Gun barrel | all | turret | D | Direct hit | One gun out | No | — |
| Casemate | C B (pre-1918) | hull side, main deck | C–B | Sea wash, splinters, cordite | Guns out; flooding entry | Partial | Sea state |
| Open AA mount | all | weather decks | D–C | Splinters, strafing | Crew killed | Re-crew | Crew pool |
| Main director + rangefinder | D C B V | foremast top ~0.25–0.35; after director ~0.6–0.7 | C–D | Any superstructure hit | Fall back to after director, then local control | Rarely | FC cables, power |
| Radar antennas | D C B V (1941+) | mast tops | D | Splinters, blast | Night/visibility penalty; no fighter direction (CV) | Spares, low odds | Power |
| Plot / transmitting station | C B | deep, 0.3–0.6 | A | Flooding, power | Degraded solution | Partial | Power |
| Bridge / compass platform | all | fwd superstructure | D–C | Any hit | Officers killed, command delay; helm may jam (Tsesarevich) | Shift to backup | — |
| Conning tower | C B | base of fwd superstructure | B | Slits, spall | Backup command | — | — |
| Flag bridge | flagships | superstructure | D | Hits | Fleet orders desync | — | — |
| W/T room + aerials | D C B V | superstructure | C–D | Splinters | No inter-ship orders | Jury rig | Power |
| Signal halyards | all | masts | D | Splinters | No visual signals (Lion at Dogger Bank) | Quick | — |
| Boiler room | D C B V (TB too) | 0.35–0.55 bottom | A (D: none) | Torpedo, mine, plunging shell | Steam lost → speed, generators | Sometimes (Scharnhorst 10 → 22 kn) | Feed water, uptakes |
| Engine room | D C B V | 0.55–0.70 bottom | A | Torpedo, flooding | Shafts lost | Rarely | Steam |
| Diesel/petrol engines | M (S-boats, subs) | amidships | D | Any hit | Speed; petrol fire | Partial | Fuel |
| Shaft + shaft alley | all | 0.70–1.0 bottom | D–A | Underwater hit aft | Speed; **shaft-whip progressive flooding** (PoW) | Stop the shaft | Engine |
| Propeller / strut | all | 0.85–1.0 underwater | D | Torpedo, mine | Speed, vibration | No | — |
| Uptakes / funnels | D C B V | over boiler rooms / island | C | Shells, bombs, flooding | Draught loss (Yorktown 6 kn → stop; +1.5 h to 20 kn), smoke | Partial | — |
| Fuel tanks / purifiers | all | sides, double bottom | A–C | Underwater hits | Fire, slick, fuel cut off (Bismarck), unusable fuel (Graf Spee) | Transfer | — |
| Feed-water / evaporators | D C B V | machinery | A | Contamination | Boilers fade (Lion); campaign water | Slow | — |
| Rudder(s) | all | 0.95–1.0 underwater | D | Torpedo, large shell, near miss | Jammed = circling; lost = steer by engines | Almost never | — |
| Steering gear room | all | 0.90–0.97 | A–B / D | Flooding, power loss, shell | Hand steering or none | Sometimes | Power, telemotor link |
| Generators (steam / diesel) | D C B V | machinery spaces + separate diesels | A | Flooding of steam spaces | **Cascade blackout** | If not flooded | Steam / diesel |
| Switchboards + ring main / cables | D C B V | boards below armour; cables everywhere | A / D | Flooding, cable cuts, arcing, own-gun shock (SoDak) | Segment blackout (PoW, South Dakota) | Breaker reset; casualty power | — |
| Hydraulic pump rooms | B (RN) V | remote rooms | A | Flooding | Turrets / lifts slow | — | Power |
| Pumps (drainage) | all | distributed | A–D | Power loss | No dewatering | — | Power |
| Fire main | all | distributed (looped post-Savo) | D–A | Ruptures | No firefighting; can *cause* flooding | Partial | Power; independent pumps |
| Ventilation | all | distributed | D–A | Hits, power loss | Smoke, vapour and fire spread; heat | Partial | Power |
| Catapult + floatplanes + avgas | C B | amidships or stern | D | Any hit | Fire beacon at night (Savo) | Jettison or launch | — |
| Accommodation / wardroom | all | above armour deck | D | Fire | Fire spread → magazine cook-off (Astoria) | Strip pre-war | — |
| Galley / sickbay | all | superstructure / protected stations | D | Hits | Endurance and morale; wounded → dead | Partial | — |
| Masts | all | centreline | D | Shells, splinters | Everything mounted on them lost | Jury rig | — |
| Boats, searchlights, booms | C B V | upper deck | D | Splinters, fire | Fire fuel; worse abandon-ship survival | No | — |

### 5.1 Ammunition: the flash chain

Gunhouse → working chamber → hoist trunks → handling room → magazine, with anti-flash doors or scuttles at each step.
- **Seydlitz, Dogger Bank:** both aft turrets burned out (159 dead). She was saved by flooding the magazines.
- **Lion's Q turret, Jutland:** magazine doors shut and the magazine flooded; the handling-room crews died but the ship survived.
- **Jutland battlecruisers:** charges were stockpiled and doors propped open to raise the rate of fire. Historians debate how much this mattered compared with design flaws.

**Magazine model:**
- Per-magazine `sensitivity` (cordite high; RP C/12 low; US SPD single-base low; black-powder primers very high), `fill` and `state ∈ {dry, sprinkled, flooded}`.
- `P(detonate) ∝ sensitivity × fill × (1 − flood)`.
- A **rate-of-fire doctrine** toggle raises propagation risk.
- Flooding a magazine takes minutes, needs valves or power, removes that turret and adds weight. Yamato's magazines could not be flooded because the pumping stations were gone.
- **Fire reaching a magazine later** is more common than an immediate detonation:
  - USN destroyers: 1 immediate case vs 5 later from fire.
  - Astoria blew up 9 h after Savo.
  - Cushing blew up the next afternoon.
- **Unstable old propellant** also caused peacetime losses: Iéna, Liberté, Bulwark, Natal, Vanguard, probably Mutsu.

### 5.2 Main battery

Sub-components: gunhouse (crew, guns), barbette/roller path (jam in train), hoists (rate of fire), per-gun barrels, power.
- **Power:** RN turrets were hydraulic from separate pump rooms; USN electro-hydraulic; Bismarck electric training with hydraulic elevation. Without power: hand training at ~10% speed (?) and 2–4× slower reload (?).
- **Mechanical unreliability even without hits:** PoW at Denmark Strait lost ~26% of output (A1 failed after the first salvo; Y's shell ring jammed). KGV at North Cape had shells "take charge" in a roll, jamming three guns for 15 min.
- **List penalty:** Marlborough at 7° had loading trouble; PoW's 5.25″ could not depress at 11.5°.
- **Recovery is possible:** Scharnhorst's Bruno came back into action; Anton did not.

### 5.3 Fire control hierarchy

Radar FC → optical director → after director → turret local control. Each step loses range and accuracy, much more at night. No clean published accuracy ratio was found; choose one (e.g. local control at 30–50% of director hit rate).
- The plot or transmitting station is deep (tier A). Everything else is topside and fragile.
- Smoke from your own funnel blinds directors placed just aft of it (Dreadnought's spotting top). **The layout code should penalise that placement.**
- Rigging stays fouled directors and were removed after Savo.

### 5.4 Command & communications

Bridge node with a backup (CT or aft conning position), plus a flag sub-node on flagships.
- **Bridge hits:**
  - Tsesarevich's 12″ hit killed Vitgeft and jammed the helm; the Russian line broke up.
  - Kaga lost her captain and senior officers, so fires went uncontrolled.
  - Others: PoW's compass platform, Hiei's bridge, Mogami (captain and XO killed), Bismarck at 09:02.
- **Comms:**
  - Signal halyards lost → Beatty's signals misread at Dogger Bank.
  - W/T lost → Hipper had to change ship.
  - Internal comms lost → orders arrive late (Ark Royal).
- **USN CIC** from winter 1942–43 is a late-war capability node.

### 5.5 Propulsion

**Era progression:**
- Reciprocating triple- or quadruple-expansion engines (~120 rpm).
- Direct-drive turbines from 1906 (Dreadnought: 18 boilers, 23,000 shp).
- Geared turbines.
- Turbo-electric (US New Mexico through Colorado classes, Lexington/Saratoga). Fine-grained, but electrical shorting stops the ship (Saratoga 1942 had to be towed).
- Fuel: coal → mixed → oil (RN all-oil from Queen Elizabeth). Oil let ~212 stokers be replaced by ~24 men but removed the bunker protection.

**Grouped vs unit (alternating) machinery is the key layout flag:**
- Unit layouts cost length and armour; Leander's Amphion group grew 8 ft of machinery and 57 ft of belt.
- They survive single hits: Johnston held 20 kn for 2 h with the after turbines dead.
- Grouped plants die to one hit: Chōkai (bomb down the stack), Canberra CA-70, J/K/N destroyers (two boilers in adjacent rooms).

**Other rules:**
- Speed ∝ (delivered power)^(1/3) roughly, so half the plant leaves ~80% of speed (plus drag from damage).
- **Feed-water contamination is a slow killer:** Lion fell from 27 to 8 kn through a splinter in the capstan exhaust.
- **Funnel or uptake hits cut draught.** Yorktown at Midway: 3 boilers out, stopped, then 20 kn after ~1.5 h. Bombs down uptakes reached the machinery (Chōkai, Sōryū).

### 5.6 Steering

States: free / jammed at angle X / missing.
- **Jammed** forces a circle: Bismarck at 12° port, Hiei, Akagi at ~20–30°, Yamato stuck in a starboard turn.
- **Missing** allows steering by differential shaft power, ~20–40% of normal turn rate on 3–4 shaft ships (?). Impossible with one shaft; poor with two at low speed.
- The steering room is a separate, power-dependent node. The bridge-to-steering link (telemotor or cable) can be cut, forcing local helm and command delay.
- Twin or spaced rudders reduce risk but do not remove it. Kirishima lost both.

### 5.7 Electrical

- **1890s ships** used little power (lighting, searchlights, some hoists, fans), with hand or steam backups everywhere.
- **By 1941** almost everything depended on it: turret drives, DP mounts, radar, FC computers and synchros, pumps, ventilation, steering and lighting.
- **Capacity growth:**
  - Dreadnought: a few hundred kW at ~100 V DC.
  - PoW: 8 × 330 kW (?).
  - Bismarck: 7,910 kW total.
  - Iowa: 4 × 1,250 kW split fore and aft, plus diesels.
- **Failure modes:**
  - Generators lost to flooded steam spaces. **Ark Royal had no diesel backup**: one torpedo led to a sinking ~15 h later with 1 dead.
  - Switchboard flooding or arcing (Saratoga).
  - Cable cuts and shorts trip breakers. South Dakota had ~3 min without power; a 1-minute blackout came from her **own turret firing**.
  - Ring main severed (PoW lost power to 6 of 8 secondary turrets).
  - Darkness slows damage control.
- **Mitigations:**
  - Dispersed generators and cross-connected switchboards.
  - 50–75 kW emergency diesels fore and aft (USN after Savo).
  - **Casualty power** cables, rigged in minutes by USN crews.

### 5.8 Fire load and crew spaces

- Fuels: linoleum, cork, upholstery, paint (up to 80 coats), papers, life jackets, wooden decks, boats, aircraft, ready ammo.
- **"Stripped for war"** is a doctrine or year toggle: USN post-1942 removed linoleum and oil paint; Yamato 1945 removed flammables. Lower fire load, some long-term morale cost.

### 5.9 Crew-casualty mechanisms

1. Blast or penetration in a compartment: turret crews of ~70–80 killed per hit.
2. Splinters and armour spall: dominant topside.
3. Propellant flash fire.
4. Magazine detonation: survivors in single digits.
5. Steam scalding.
6. Smoke and toxic gas, spread by ventilation.
7. Drowning in flooded spaces.
8. Fast capsize trapping crews: Barham ~4 min, Hood ~3 min, vs Ark Royal ~15 h (almost all saved).
9. Strafing of open AA crews.
10. In the water: depth charges (Strong), burning oil, exposure (North Cape 36/1,968 saved), interrupted rescue.
11. Heat.
12. Ready-ammo cook-off among the wounded.
13. Accidents and in-bore explosions.

**Crew is also the damage-control resource.** Losing repair parties or the conflagration station (Lexington, Franklin) slows all repair.

---

## 6. Size tiers

| Tier | Displ. | Main compartments | Components worth modelling | Signature rules |
|---|---|---|---|---|
| Coastal craft (MTB/PT/S-boat/MAS/G-5) | < 150 t | 6–9 | crew, guns, engines per shaft, fuel tanks, torpedo tubes/racks, bridge | **Fuel-type flag** (petrol → fire + vapour explosion; diesel ≈ safe); wooden hull → large shells may pass through unfuzed (?); wreck floats on wood for hours (PT-109 ~12 h); crew casualties dominate |
| TB / TBD (1885–1905) | 60–450 t | ~6–10 (?) | + locomotive or water-tube boilers, coal bunkers | 3.2 mm plating; anything ≥37 mm passes through; hull girder weak (Cobra broke up in a seaway) |
| Escort (corvette/frigate/DE) | 900–1,500 t | ~8–12 | + single/twin screw flag, depth charges | Single-screw Flower: any machinery hit → dead in the water; one torpedo ≈ loss (22 of 33 Flower losses were U-boat torpedoes) |
| Destroyer | 1,500–3,000 t | 12–16 | + split-plant flag, torpedo mounts and reloads (IJN), director, magazines fore and aft | "Four-compartment" standard; **hull-girder pool**: amidships damage → break in two (Hambleton survived with ~15% of section modulus); bow/stern loss survivable |
| Protected cruiser (1885–1905) | 2,000–6,000 t | ~10–15 (?) | armoured deck with slopes, coal + cellulose cofferdam layer | Vitals under the deck; flooding above the deck costs stability; no underwater protection |
| Armoured cruiser | 8,000–15,000 t | ~12–18 (?) | + belt | Too weak vs battleships (Defence, Black Prince); torpedoes (Aboukir, Hogue, Cressy) |
| Light/heavy cruiser | 3,500–17,000 t | 14–25 | + belt over machinery, **boxed magazines**, thin turrets (IJN 25 mm), unit machinery (US post-1937), aircraft and avgas | Boxed magazines below the waterline are exposed to torpedoes (New Orleans lost ⅓ of the ship); **bow severance** survivable; IJN deck Long Lances; fire is the main killer (Savo) |
| Capital ship | 12,000–72,000 t | 15–22 main (+hundreds) | everything in §5 | Raft citadel, TDS, ends flooding/trim, flash chain, stern golden-BB |
| Carrier | 7,500–65,000 t | as hull type | §7 | Fire/vapour, mission kills |
| Submarine | 250–2,500 t | 5–8 | pressure hull, outer hull/ballast, batteries, diesel/e-motors | Pressure-hull breach → depth-limited; battery + seawater → chlorine; external fuel leak → slick |

**Survival anchors for small ships:**
- USN destroyers: above-water weapons 84% survival; torpedo/mine 44%.
- Causes of the 30 above-water losses: 14 flooding, 6 structural (jack-knifing), 5 magazine.
- Destroyers mostly went down by **plunging**, not capsizing (only Preston and Johnston clearly capsized).
- "No ship > 3,000 t was sunk by gunfire ≤ 5″."
- Aaron Ward took 6 kamikazes and shipped 1,650 t of water, and still made port.

---

## 7. Carriers

### 7.1 Protection philosophies

| | USN (to 1945) | RN armoured box | IJN |
|---|---|---|---|
| Strength deck | Hangar deck | **Flight deck** (3 in) | Hangar/main; Taihō and Shinano had armoured flight decks (75–80 mm) |
| Hangar | Open (vents blast and vapour) | Closed box, fire curtains, spray | Closed, often two levels (traps vapour) |
| Flight deck damage | Wooden: patched in 25 min – 3 h | Dented; concrete + plate in ~4 h (Formidable) | Holes = ops over |
| Cost | Bombs reach the hangar | Small air groups (36 → 57 with a deck park); distortion often uneconomic to repair | Fire vulnerability |

### 7.2 Carrier-specific components

1. **Flight-deck segments** (5–7) with state `OK | HOLED | WRECKED | FIRE`. Launch needs a clear run forward of the deck park; recovery needs the aft segments, wires and ≥1 barrier. Barriers are a separate component: Formidable landed aircraft again with one barrier left.
2. **Lifts** (1–3; centreline or deck-edge), state `OK | JAMMED_UP | JAMMED_DOWN | DESTROYED`.
   - Hydraulic or electric, so power-dependent: Lexington lost both to hydraulic pressure loss.
   - Cycle time sets re-spot tempo: Essex ~45 s, Shōkaku 15 s, Béarn 3–5 min.
   - Centreline lift wells act as vents and flood paths (Shōkaku) and collect liquids (Taihō).
3. **Hangar bays** (2–5 per level). Each holds aircraft with `fuel%`/`armed`, **loose ordnance**, fire, vapour and suppression state.
   - The sprinkler, curtain and fog/foam systems need fire mains and a conflagration station. Franklin's was wrecked; recommended armour was ¾ in STS.
   - **`rearm_in_progress`** dumps ordnance on the hangar deck: Kaga had ~80,000 lb loose at Midway (?).
4. **Avgas tank groups** = "liquid magazines" with `fill`, protection (none / armour / water-jacket / CO₂ / N₂ inerted), an `integral_with_hull` flag (IJN: cracks under shock), and `line_state ∈ {LIVE, DRAINED, CO2_PURGED}`.
   - Leaks accumulate **vapour**, spread by ventilation and open hatches. Ignition per tick ∝ vapour × ignition sources (running electrics, fire, crashes).
   - Quantities: Essex 231,650 US gal; Yorktown ~178k; Illustrious ~50.6k Imp gal; Shinano 720,000 L.
   - USN water-displacement and CO₂ practices after Lexington; Yorktown's purge at Midway worked.
5. **Bomb/torpedo magazines + bomb elevators.**
   - Capacity: Ark Royal ~225 t; Illustrious ~175 t.
   - Ordnance in transit is the danger, not the magazine: Franklin's lower magazines were never involved.
   - CVE: aft magazine plus a torpedo means quick loss (Liscome Bay, 23 min; Avenger).
6. **Island:** bridge, fly control, radar/fighter direction, **uptakes** (hit → temporary boiler loss).
7. **Machinery + power graph** with `turbo_electric` and `diesel_backup` flags. Uptake and air-intake flooding paths (Ark Royal).
8. **Fire mains** in sections, port and starboard, plus independent gasoline-driven pumps (Essex). Losing both mains in a zone ends firefighting there (Kaga, Wasp, Lexington).
9. **Air group entities** with location (hangar bay / deck segment / airborne), fuel and armed state. Airborne aircraft with no deck must divert or ditch on a fuel timer: Enterprise lost 16 of 73 at Santa Cruz.

**Mission-kill conditions:** no launch run; no recovery (aft deck, wires or barriers gone); all lifts down; no avgas; no ordnance (magazines flooded or bomb elevators down); fly control or radar lost.

---

## 8. Damage mechanics (physics → candidate rules)

### 8.1 Shells, fuzes, penetration

| Type | Burster | Fuze | Use |
|---|---|---|---|
| AP/APC | 1.5–5% | Base, delay 0.015–0.035 s (RN 0.025; USN/KM ~0.035; IJN Type 91 long, for diving hits) | Armour |
| SAP/CPC | ~2.5–4% | Base, short delay | Cruisers, casemates |
| HE | 6–8% | Nose, instant | Topsides, destroyers, fires |

**Arming threshold:** AP needs plate ≳ 5–7% of calibre to fuze. Below that it **over-penetrates** (South Dakota's superstructure, Gambier Bay). WoWS uses 1/6 calibre.

**Duds and quality:** at Jutland only 1 of 17 British shells striking >9″ plate penetrated and burst. Model this with a per-nation, per-era shell-quality factor.

**De Marre** (homogeneous plate, good game baseline):
```
T/D = 0.00005021 · D^0.07144 · [ (W/D³) · (V/C)² · cos³(Ob) ]^0.71429
T, D in inches; W lb; V ft/s; C ≈ 1.0–1.25; Ob obliquity
```

**Spaced plates** (Okun): `T_spaced = (Σ (Q_i·T_i)^1.4)^(1/1.4)`. These are worth less than a solid plate unless one layer decaps the shell.

**HE penetration** ≈ 0.16 calibre (WoWS uses 1/6, 1/4 for some lines). **Splinter-proof:** RTW uses "≥ 2 in stops splinters."

**Edge effects:** within 1.5 calibres of a plate edge, plate quality drops up to 15%. This gives a physical basis for "joint weakness" rolls.

**Cheap resolution:**
1. Precompute per gun `pen_belt(range)`, `pen_deck(range)` and fall angle.
2. `eff_belt = t / cos(θ_h)`, `eff_deck = t / sin(fall)`.
3. Penetrate if `pen × U(0.9, 1.1) > eff × quality`.

Okun's FACEHARD and per-gun penetration tables on NavWeaps can calibrate the curves.

**Diving shells:** Japanese Type 91 AP can travel underwater from short near misses and hit below the belt (Boise). RTW3 models this.

### 8.2 Underwater weapons

**Warheads:**

| Weapon | Charge |
|---|---|
| Aerial torpedoes | ~150–250 kg (RN Mk XII 388 lb) |
| 21″ standard | 250–350 kg (G7a ~280 kg; Mk 14 507–643 lb; RN Mk VIII 750–805 lb) |
| IJN 24″ Type 93 | ~490 kg |
| Mines | 55–840 kg |

**Contact:** the hole and flooding are absorbed by the TDS. North Carolina's hole was 32 × 18 ft, letting in 970 t.

**Under-keel (influence):** the gas bubble whips and breaks the hull girder, so a smaller charge does more damage. Belfast's keel was broken by a ground mine; O'Brien was lost to flexural damage later.

**Shock factor:** `HSF = √W / R`, `KSF = HSF·(1+sin θ)/2`.

| Shock factor | Effect |
|---|---|
| < 0.1 | Nil |
| 0.1–0.15 | Electrics and lighting fail, pipes leak |
| 0.15–0.2 | Pipes rupture, machinery fails |
| ≥ 0.5 | Lethal |

Shock mounting of machinery is post-WWII. Constants are approximate (?).

**Duds:** G7a contact pistols needed ≥16° impact angle. Early-war magnetic exploders failed (Mk 14, the German Torpedokrise).

### 8.3 Bombs

- **GP bombs** are 30–40% explosive: they wreck topsides and flight decks.
- **AP/SAP bombs** are ~15–20% explosive and penetrate decks. Arizona's was a converted 41 cm shell (797 kg); her magazine blew 7 s after the hit.
- **Near misses** are their own class: shock, sprung plating, splinters, rudder jams (Akagi). Musashi took 20 near misses.
- **Guided bombs:** Roma lost to a magazine explosion; Warspite took a 20 ft bottom hole.
- **Kamikazes** were *less* lethal per damaged US destroyer: 13.7% sunk, vs 28.9% for conventional bombs and torpedoes.

### 8.4 Flooding & stability

**Two deaths:**
- **Founder or plunge** (loss of reserve buoyancy, usually by an end): typical of destroyers, Lützow.
- **Capsize** (loss of transverse stability from off-centre flooding, free surface or topweight): Borodinos, the British pre-dreadnoughts, Kirishima, Yamato, Barham, PoW.

**Inflow:** `∝ hole_area × √head`. Spread goes through bulkhead leak rates and paths (§3.5).

**Permeability defaults:** ~0.95 voids/accommodation, ~0.85 machinery, ~0.6 stores, ~0.4 full coal bunkers (?).

**Free surface:** `GG' = ρ·i / (ρ_sw·∇)`, with `i ≈ l·b³/12`. Wide, partly flooded flats are the killers. Full wing tanks help: the same damage would have meant a 5–6° list with them empty.

**Counterflooding:**
- Works fast and in moderation: NC moved 480 t in 6 min, ≈80 t/min.
- Lethal when overdone: Kirishima; Shōkaku flipped heel from one side to the other; Musashi traded list for bow freeboard.
- Counterflooding TDS voids weakens that side.

**Speed and stress:** running fast while flooded forward overloads bulkheads. NC held 18 kn; Seydlitz went astern. RTW3 models "bulkhead rupture"; its AI "suicides by flooding", so the AI must respect the rule.

**Time rule (1945 DC Handbook):** "If the ship does not sink within a very few minutes after damage, she probably will survive for several hours."

**Capsize thresholds:** Yamato was designed to stay stable at 20° list, could correct 18.3° by counterflooding, and had a damaged limit of ~30°. Generic rule: capsize at heel > 20–30°, or when the deck edge submerges with GM ≤ 0.

**Pre-damage state matters:** Tsushima's overloaded Borodinos had their belts submerged. Feed the generator's GM, load state and overload directly into the damage model.

### 8.5 Fire

- **Sources:** propellant (cordite was 75× more flash-sensitive than US single-base in WWII tests), avgas, petrol, ready ammo, aircraft, paint and linoleum, deck torpedoes. Bunker oil is hard to ignite.
- **Rules:**
  - ~50% of above-water-damaged US destroyers had fires.
  - **Hose on the fire within ~1 min** usually prevented ammunition explosions.
  - Fire-main ruptures disable firefighting.
  - Admiralty Trilogy delays shell- and bomb-caused fire and flooding by ~9–12 min of game time; torpedo flooding is immediate.
- **Effects to model:**
  - Crew and system damage.
  - Uninhabitable compartments.
  - Spread along an adjacency graph and through ventilation.
  - Magazine cook-off risk over time.
  - **Night illumination** of your own ship (Savo).
  - Not direct hull HP loss (players criticised UA:D for this).

---

## 9. System dependency graph (core of a mission-kill model)

```
Fuel ──► Boilers ──► Steam ──► Turbines/Engines ──► Shafts ──► Propellers ──► SPEED
  │         ▲  ▲                                        │
  │   Feed-water  Uptakes/Funnels (draught)              └─► shaft-whip leaks (aft)
  │
  └──► Diesel gens ─┐
Steam ──► Turbo gens ┴─► Switchboards ──► Ring main / bus segments ──┬─► Turret drives / hoists ──► FIREPOWER
                                                                      ├─► Directors, radar, FC computer, synchro links
                                                                      ├─► Steering gear (or hand) ──► MANOEUVRE
                                                                      ├─► Drainage pumps ──► FLOODING CONTROL
                                                                      ├─► Fire pumps ──► Fire main ──► FIRE CONTROL
                                                                      ├─► Ventilation (also spreads smoke/vapour)
                                                                      ├─► Lifts, catapults, sprinklers (CV)
                                                                      └─► Radio, internal comms, lighting
Bridge/CT ──► (telemotor, phones, voice pipes) ──► steering, engine orders, gun orders  [COMMAND]
Crew pools ──► every repair/DC action; DC Central / conflagration station multiplies them
```

Era scaling: an 1890s ship barely depends on the electrical branch (steam and hand backups). A 1942 ship depends on it almost totally, so a blackout is far worse.

---

## 10. Era / nation knobs

| Knob | Values / notes |
|---|---|
| Propellant sensitivity | RN cordite (high; worst in WWI) · KM RP C/12 brass-cased (burns, low) · USN SPD single-base (low) · IJN cordite-derived (med–high) · black-powder igniters (very high) |
| Flash protection / RoF doctrine | Pre-Jutland RN poor; post-1915 KM good; interlocks later |
| Shell quality / dud rate | RN 1914–17 poor; "Greenboy" from 1918 good |
| Fuze delay | RN 0.025 s; USN/KM ~0.035 s; IJN Type 91 long (diving) |
| Armour quality | Harvey → KC → WWII FH; per-nation multipliers |
| Construction | Riveted (joint failure) → welded (late 1930s+); IJN late-war simplification (single bottom, carbon steel) |
| TDS depth / layers | §3.4 |
| Centreline machinery bulkhead | RN pre-dreads, IJN, Borodino yes · USN no |
| Unit machinery | USN cruisers from St. Louis, DDs from Benson; Iowa split plant |
| Electrical dependence | Low 1890 → total 1942 |
| Emergency diesels / casualty power | USN post-1942 yes; Ark Royal none |
| DC skill & doctrine | USN 1943+ high · RN mid · KM mid-high · IJN low-mid (split responsibility, multicore cables), improving late |
| Fire-load "stripped for war" | USN post-1942; IJN 1944–45 |
| Avgas practice | USN post-Coral Sea: purge, inerting, segregation · RN water-jacket + CO₂ · French N₂ · IJN integral tanks |
| Small-craft fuel | Petrol (PT, MTB, CMB, MAS, G-5) vs diesel (S-boats) |
| Overload / topweight | Campaign state; Tsushima |

---

## 11. Calibration anchors (numbers to test a model against)

| Situation | Target behaviour |
|---|---|
| 1 torpedo amidships vs WWII TDS | 500–1,500 t flooding, 3–6° list, corrected in minutes; speed −10–25% (NC 970 t, 24 → 18 kn sustained) |
| 1 torpedo near end turret / aft | 1,000–3,000 t; magazine flooding possible; rudder/shaft risk (Yamato 1943 ~3,000 t) |
| 1 torpedo at a shaft | Progressive flooding cascade; PoW: ~2,400 t early, 11.5° list, power aft lost, 25 → 15 kn; sank ~95 min after the first hit with 4 torpedoes total |
| Heavy shell through unarmoured bow at speed | 1,000–2,000 t (Bismarck, 3° bow trim, fuel cut off) up to 8,000 t progressive (Lützow) if not slowed |
| Survivable capital-ship flooding | Seydlitz 5,308 t; Lützow lost at ~8,000 t (≈25–30% of displacement) |
| Torpedoes to sink a modern BB | PoW 4 (shaft cascade) · Yamato ~11 one side · Musashi ~19 both sides |
| Destroyer, 1 torpedo | Usually lost (7/31 survived); survives if < ~2–3 machinery spaces flood; break-in-two 4 min to 29 h later |
| Destroyer, gunfire/bomb/kamikaze | ~84% survive; 4-compartment limit |
| Magazine hits | Immediate detonation rare from shellfire; likelier from torpedo or mine under the magazine (New Orleans, Amatsukaze, Juneau); delayed cook-off from fire common |
| Medium-calibre storm on an AoN battleship | Mission kill, not sinking (South Dakota: 26 hits, ~38 killed, blind and deaf) |
| Single aerial torpedo in the stern | Rudder jam → circling (Bismarck) |
| Carrier, 1 bomb in a rearming hangar | Loss (Akagi) |
| Carrier, 1 torpedo + bad vapour DC | Loss hours later (Taihō +6.4 h) |
| Carrier, armoured deck kamikaze | Ops resume in 0.5–4 h |
| Wooden-deck CV hole | Patched in 25 min – 3 h |
| PT boat rammed | Petrol fireball; bow section floats ~12 h |
| Sinking time vs survivors | Minutes → few survivors (Hood 3/1,418; Barham ~4 min); hours → most saved (Ark Royal 1 dead) |

---

## 12. Prior art: what other games do

| Game | Hit model | Damage | Lesson |
|---|---|---|---|
| **Rule the Waves 2/3** | Abstract zones chosen by range/fall angle | AP/SAP/HE, pass-throughs, splinter threshold 2″, flash fire (national trait + learning), bulkhead rupture at speed, DC training | Most historically credible results at very low compute; **UI buries cause and effect in a text log** |
| **Ultimate Admiral: Dreadnoughts** | 3D ballistics vs armour zones | Ricochet / partial / full / over-pen multipliers; 10 compartments; section structure HP; ablative armour | Geometry is accurate but **HP-centric outcomes feel wrong** (partial-pen spam, fires that sink, hidden formulas) |
| **Atlantic Fleet** (Killerfish) | Compartments with subsystems | **Real buoyancy**, no HP; only waterline/below hits flood; capsize toward the far side via plunging fire | Emergent, readable sinking; teaches "hit one side / one end"; costs a compartment buoyancy model |
| **World of Warships** | 3D raycast, section HP + saturation | Citadel / pen / over-pen ×1.0/0.33/0.1; fire and flood as DoT with zone caps | Very readable feedback; HP-pool and DoT burning unhistorical |
| **Highfleet** | 2D module grid | Fire and ammo **chain reactions** between adjacent modules | Directly relevant to top-down 2D; rewards good internal layout |
| **Harpoon / Admiralty Trilogy / Command** | Damage points ∝ tonnage; weapon DP ∝ energy^⅓ (Command: 1 DP = 1 kg TNT) | Variability from **fire and flood criticals by era**; delayed effects; DC capacity bands; mobility / firepower / mission / hard kill | Clean abstraction for scaling and DC; weak on location |
| **Tabletop** (GQ, Seekrieg, Victory at Sea) | Range-based location tables, crit tables | Hull boxes reduce speed; DP = 0.033 × tonnage (Seekrieg); "crippled" states | Cheap and flavourful; random criticals feel arbitrary unless tied to location |

### 12.1 Design patterns that fit this project

The generator already knows geometry, compartments, armour and component positions, so the natural fit combines:
1. A 2D plan-view hit point plus a **vertical band from fall angle** (bottom / below belt / belt / upper belt / deck / superstructure), instead of 3D raycasts.
2. Probabilistic penetration from De Marre-style curves, with outcome classes (ricochet / non-pen / pen / over-pen / dud).
3. Component hitboxes taken from `layout.py` placements, with blast and splinter radius in compartments.
4. **Compartment flooding as a rate**, with list and trim from summed water moments against the generator's GM. Closed form, no rigid-body physics, N ≈ 10–30 longitudinal × 2–3 transverse cells.
5. A **chain-reaction graph** for fire, flash and vapour toward magazines and avgas.
6. The **dependency graph** in §9 for mission kills.
7. Delayed fire and flood effects, a DC capacity scaled by crew/nation/era, and mission-kill vs hard-kill scoring.

**Pitfalls to avoid:** a global HP bar, fire that drains hull HP, many futile partial pens, hidden formulas, and a damage log with no symptom → cause readout. Plan the damage-report UI early; RTW shows the best model fails without one.

---

## 13. What the generator could emit for the damage model (suggestion, not decided)

The generator already produces geometry (`geometry.py`), weights and stability (`navarch.py`) and placements (`layout.py`). A damage model would need roughly:

- **Hull:** L, B, D, T, Cb; waterplane and section shape per station (from Cb); GM, KG, displacement and load state; freeboard per station.
- **Compartments:** a list of `{x0, x1, y_side ∈ {port, centre, stbd}, z_band ∈ {bottom, below_armour, between_decks}, volume, permeability, contents, crew}`. Bulkheads have `{x, type (main/armoured/torpedo/holding/centreline), leak_rate, riveted}`.
- **Armour:**
  - Belt: `t, θ, top, bottom, x-extent`.
  - Lower and upper belts, end belts.
  - Decks: per layer, `t, z, slope`.
  - Transverse bulkheads; turret face/side/roof; barbettes (exposed / behind belt); CT; steering box.
  - Material and quality per nation and year.
- **TDS:** depth(x), layers, liquid loading, rating(x).
- **Components:** each with `{type, x, y, z_band, footprint, protection_tier/armour_ref, hp_or_state, power_bus, crew}`. Includes magazines (with propellant type and fill), turrets and sub-parts, directors, radar, bridge/CT, boilers, engines, generators (steam or diesel), switchboards, shafts (path from engine room to propeller), rudders, steering room, pumps, fire-main sections, uptakes/funnels, fuel tanks, avgas groups, torpedo mounts and reloads, depth charges, aircraft/catapult, lifts, hangar bays, flight-deck segments.
- **Graphs:**
  - Compartment adjacency (for flooding and fire).
  - Vent/duct links.
  - Electrical buses (generator → switchboard → consumers).
  - Steam links (boiler room → engine room / turbo-generators).
  - Command links.
- **Flags:** `unit_machinery`, `centreline_machinery_bulkhead`, `bottom_layers`, `deck_style (flat_high | turtleback)`, `scheme (AoN | incremental)`, `turbo_electric`, `diesel_backup`, `fuel (coal | mixed | oil | diesel | petrol)`, `hull_material (steel | wood | duralumin)`, `strength_deck (hangar | flight)`, `hangar (open | closed)`.

**Possible size-tier LOD:** model fewer components and compartments below ~1,500 t and ~150 t, per §6. This also helps performance.

---

## 14. Known uncertainties and conflicts

**Corrected during synthesis:**
- Prince of Wales sank ~95 min after the first torpedo (hit ~11:44, capsized 13:20 per Wikipedia), not "45 min" as one research file says.
- The ~2,400 t (early, one torpedo) and ~18,000 t (Garzke survey, total by 12:50) PoW flooding figures refer to different moments.

**Figures to treat with caution:**
- **Coal protection.** "2 ft coal ≈ 1 ft steel" (Wikipedia, armoured cruiser) looks far too generous; treat the protective value as low and a design choice.
- **Midway (CVB) flight deck.** 3.5 in vs "1½-inch STS" in the Franklin WDR. Strength-deck status is also disputed.
- **Musashi / Yamato total flooding tonnage.** Not confirmed.
- **Japanese Type 91 fuze delay.** The 0.4 s figure is unverified.
- **Shock-factor constants.** The formula structure is standard; exact damage thresholds are approximate.

**Data not found:**
- **Main WT compartment counts.** Missing for most British and US capital ships, cruisers and destroyers. The "~0.055 L spacing" rule is derived.
- **Accuracy ratio** of director vs local control: no published figure.
- **Hand-training and reload slowdown** without power: no published figure.
- **Funnel-hit speed loss:** not quantified (designer choice).

**Weakly sourced:**
- **Small-craft sources.** S-boat 9 compartments (blog), Fletcher plating thickness (forum citing Friedman), Japanese T-1 boat (game wiki), shells passing through wooden hulls unfuzed (anecdotal, physically plausible).

**Biased sources:**
- **armouredcarriers.com** is pro-armoured-deck and **navweaps tech-030** is sceptical; the carrier file keeps both views.

---

## 15. Key sources

- **USN War Damage Reports** (NHHC): [North Carolina WDR 61](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-north-carolina-bb55-war-damage-report-no-61.html) · [South Dakota WDR 57](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-south-dakota-bb57-war-damage-report-no57.html) · [Savo cruisers WDR 29](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-quincy-ca39-astoria-ca34-vincennes-ca44-war-damage-report-no29.html) · [Franklin WDR 56](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-franklin-cv-13-war-damage-report-no-56.html) · [Lexington WDR 16](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-lexington-cv2-war-damage-report-no16.html) · [Destroyers: torpedo & mine](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-torpedo-mine-damage.html) · [Destroyers: gunfire, bomb, kamikaze](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-gunfire-bomb-kamikaze-damage.html) · [Summary of War Damage 1941–42](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/summary-of-war-damage-17-oct-1941-to-7-dec-1942.html)
- **Garzke, Dulin, Denlay et al.:** [Death of a Battleship: HMS Prince of Wales (2012)](https://pacificwrecks.com/ship/hms/prince-of-wales/death-of-a-battleship-2012-update.pdf)
- **USNI:** [Design and Construction of Yamato and Musashi (1953)](https://www.usni.org/magazines/proceedings/1953/october/design-and-construction-yamato-and-musashi) · [Lessons of Jutland for turret armor (1925)](https://www.usni.org/magazines/proceedings/1925/april/lessons-jutland-affecting-design-turret-armor) · [Cellulose protection (1892)](https://www.usni.org/magazines/proceedings/1892/april/cellulose-and-its-application-protection-vessels)
- **NavWeaps:**
  - Technical articles: [TDS of WWII](https://www.navweaps.com/index_tech/tech-047.php) · [All-or-nothing](https://www.navweaps.com/index_tech/tech-070.php) · [Underwater projectile hits](http://navweaps.com/index_tech/tech-041.php) · [Propellants](https://www.navweaps.com/index_tech/tech-100.php) · [Armoured flight decks](https://www.navweaps.com/index_tech/tech-030.php)
  - Okun: [penetration formulas](https://www.navweaps.com/index_nathan/Hstfrmla.php) · [spaced plates and misc.](https://www.navweaps.com/index_nathan/Miscarmr.php) · [AP shell vs armour](http://www.navweaps.com/index_nathan/apShellVsArmor.php) · [Bismarck armour](https://www.combinedfleet.com/okun_biz.htm)
- **Naval Gazing:** [Flooding](https://www.navalgazing.net/Survivability-Flooding) · [Mission kills](https://www.navalgazing.net/Survivability-Mission-Kills) · [Fire](https://www.navalgazing.net/Survivability-Fire) · [Underwater protection 1](https://www.navalgazing.net/Underwater-Protection-Part-1) · [Underwater protection 2](https://www.navalgazing.net/Underwater-Protection-Part-2)
- **Pacific War Online Encyclopedia:** [Damage Control](http://pwencycl.kgbudge.com/D/a/Damage_Control.htm)
- **combinedfleet.com:** [Taihō](https://www.combinedfleet.com/Taiho.htm) · [Shōkaku sinking](https://www.combinedfleet.com/shoksink.htm) · [Kaga](https://www.combinedfleet.com/kaga.htm) · [Akagi](https://www.combinedfleet.com/Akagi.htm)
- **Carriers:** [armouredcarriers.com, Illustrious design](https://www.armouredcarriers.com/hms-illustrious-armoured-aircraft-carrier-design)
- **Small craft and submarines:** [USN MTB manual](https://www.ibiblio.org/hyperwar/USN/ref/PT-Manual/MTBM-5.html) · [PT-658 NRHP nomination](https://heritagedata.prd.state.or.us/historic/index.cfm?do=main.loadFile&load=NR_Noms/12000602.pdf) · [The Fleet Type Submarine](https://legacy.maritime.org/doc/fleetsub/chap3.php)
- **Game references:**
  - Manuals and analyses: [RTW3 manual](https://ftp.matrixgames.com/pub/RuletheWaves3/Rule%20the%20Waves%203%20Manual%20EBOOK.pdf) · [Atlantic Fleet manual](https://killerfishgames.com/wp-content/uploads/2016/03/AtlanticFleetManual-v102.pdf) · [Admiralty Trilogy: variable damage effects](https://www.admiraltytrilogy.com/pdf/CW2008_Variable_Damage_Effects.pdf)
  - WoWS wiki: [damage system](https://wiki.worldofwarships.com/Ship:Damage_System) · [armour penetration](https://wiki.worldofwarships.com/Ship:Armor_Penetration)
- Wikipedia class and ship articles throughout. Full inline citations are in files 01–05.
