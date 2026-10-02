# 02 — Internal Components & Systems of a Warship (1890–1945) and How They Fail

Research base for the damage model of a top-down 2D WWII-era naval game with a parametric ship generator.
Scope: pre-dreadnoughts (~1890) through WWII fast battleships; all ship sizes.

**Conventions**
- Positions are given as a fraction of length from the bow (0.0 = bow, 1.0 = stern) and by deck level. These are *typical* values for a conventional big-gun ship with an "A-B / X-Y" turret layout. They are generalisations for the auto-layout, not measurements of any one ship.
- "Citadel" means the armoured box: the belt, the armoured deck and the transverse bulkheads.
- **[UNCERTAIN]** marks figures that conflict between sources or that come from a single weak source.
- Each section ends with a **MODEL NOTE** that turns the history into game ideas.

---

## 0. Cross-cutting lessons (read first)

1. **Most ships are mission-killed long before they sink.** Naval Gazing's survey of mission kills calls electrical distribution "the real Achilles heel". Ships kept generators that still ran, but damaged cables and switchboards left them unable to fight. Later designs answered with dispersed turbo-generators, separated diesel generators and cross-connections ([navalgazing.net — Survivability: Mission Kills](https://www.navalgazing.net/Survivability-Mission-Kills)).
2. **Catastrophic losses are almost always ammunition.** Examples include the Jutland battlecruisers, Hood, Barham, Arizona, Mutsu, Kongō, Mikuma, Yamato and Astoria's 5-inch magazine. Most of these explosions came from flash or fire reaching propellant, not from a shell bursting inside the magazine.
3. **Fire is a force multiplier.** Fires light the ship up as a target, destroy unarmoured systems, and make compartments uninhabitable. At Savo Island the Bureau of Ships concluded that Astoria was lost mainly to uncontrolled fire, not structural damage ([NHHC War Damage Report 29](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-quincy-ca39-astoria-ca34-vincennes-ca44-war-damage-report-no29.html)).
4. **Splinters dominate topside.** Unarmoured superstructure holds the directors, radar, bridge, AA crews and cable runs. It is shredded by hits of every calibre, including AP shells that pass straight through.
5. **Systems are coupled.** Losing one node takes others with it:
   - steam → generators → pumps, turrets, radar and steering
   - the feed-water path → boilers → speed
   - cables → fire control

   Design the damage model as a dependency graph, not as independent hit points.

---

## 1. Ammunition: magazines, shell rooms, handling rooms, hoists, and deck-stowed explosives

### 1.1 Function and layout

Each main turret is fed from the bottom of its barbette:
- a **magazine** for propellant ("powder room")
- a **shell room** for projectiles
- **handling rooms**, where charges are passed out of the magazine through flash-tight scuttles
- **hoists**, which run up through the barbette to the working chamber and then the gunhouse

Magazines sit under the waterline, behind the belt and below the armoured deck, so that they can be flooded and are protected by the most armour ([Wikipedia — Magazine (artillery)](https://en.wikipedia.org/wiki/Magazine_(artillery))).

- **Typical location:** directly under each turret. In a 2-forward / 2-aft ship the forward group sits at about 0.15–0.35 and the aft group at about 0.65–0.85. The lowest decks are the hold and platform decks.
- **Protection tier:** highest. Inside the citadel and below the waterline.
- **Secondary and AA magazines** were often wing compartments or separate, less well-protected spaces. Barham's 4-inch magazines were *outboard* of the main 15-inch magazines ([Wikipedia — HMS Barham](https://en.wikipedia.org/wiki/HMS_Barham_(04))).

#### Shell rooms above or below the magazine?

- **Traditional Royal Navy practice:** the shell room was lowest and the cordite magazine above it.
- **Nelson and Rodney** were the first British ships in service with the magazine *below* the shell room. **King George V** and **Vanguard** did the same. Vanguard's turret design expected charges to come *up* from above the shell room, so she needed an extra powder-handling level ([NavWeaps forum — Vanguard mags](https://www.tapatalk.com/groups/warships1discussionboards/hms-vanguards-powder-mags-over-or-under-shell-room-t31569.html)).
- **KGV figures:** cordite was stowed deepest, at hold level, with 8 magazines and 821 cordite cases around the magazine handling room. The shell rooms were on the deck above with 392 rounds ([NavWeaps — British 14in quadruple turret](https://www.navweaps.com/index_tech/tech-122.php)).

The reasoning:
- **Propellant is the dangerous item.** Cased shells are inert unless struck hard, but burning cordite can turn into an explosion. Putting the propellant deepest moves it furthest from plunging fire and bombs.
- **Shells low** had favoured handling and stability, and gave some protection from below.
- The post-Jutland, long-range, air-attack world favoured **propellant deepest**.

**[UNCERTAIN]** For the US, Japanese and German arrangements I found no single authoritative table. USN fast battleships kept most projectiles on "shell decks" within the barbette, with the powder magazines below; treat this as typical, not universal.

### 1.2 Propellants and why they matter

| Propellant | Composition | Behaviour |
|---|---|---|
| British Cordite Mk I (1893) | 58% nitroglycerine / 37% nitrocellulose / 5% petroleum jelly | Hot and very erosive |
| Cordite MD (1901) | 65% nitrocellulose / 30% nitroglycerine / 5% petroleum jelly | Used at Jutland; stowed in silk bags, often in cylindrical "Clarkson cases" in the magazine |
| Cordite SC (1927) | 49.5% nitrocellulose / 41.5% nitroglycerine / 9% centralite stabiliser | WWII standard |
| German RP C/12 | ≈64% nitrocellulose / 30% nitroglycerine / 5.75% centralite | Fore charge in silk; main charge in a **brass cartridge case** |
| US SPD | 99.5% nitrocellulose / 0.5% diphenylamine stabiliser | Single-base, silk bags; very stable in storage |
| Japanese DC (1924) | 64.8% nitrocellulose / 30% nitroglycerine / 4.5% centralite | Originally used British cordite |

Sources: [NavWeaps — Naval Propellants overview](https://www.navweaps.com/index_tech/tech-100.php); [Naval Gazing — Powder Part 3](https://www.navalgazing.net/Powder-Part-3).

Key behaviours:
- **German RP C/12 burns rather than detonates.**
  - When the magazine of *Gneisenau* holding 23 t of RP C/32 ignited in 1942, "there was no explosion", although the turret was displaced ([NavWeaps tech-100](https://www.navweaps.com/index_tech/tech-100.php)).
  - At Jutland, Derfflinger's gunnery officer wrote that burning cases "only blazed, they did not explode as had been the case with the enemy. This saved the ship" ([von Hase, *Kiel and Jutland*, via wtj.com](https://www.wtj.com/archives/hase_03.htm)).
- **Instability over time.** Nitrocellulose decomposes autocatalytically, and heat plus moisture make it worse.
  - *Iéna* exploded in 1907. Two-thirds of her 12-inch charges were over six years old.
  - *Liberté* exploded in 1911, killing about 300 aboard.
  - Other losses to this cause include *Matsushima* (1908) and *Aquidabã* (1906).
  - Remedies were refrigerated magazines and stabilisers (diphenylamine from 1908). Source: [Naval Gazing — Powder Part 3](https://www.navalgazing.net/Powder-Part-3).
- **Black-powder igniters and saluting charges** are a hidden sensitive item. Leading theories for both Arizona and Mutsu involve them:
  - Arizona: a black-powder magazine for saluting and catapult charges, possibly with a hatch open ([Wikipedia — USS Arizona](https://en.wikipedia.org/wiki/USS_Arizona_(BB-39))).
  - Mutsu: Mike Williams' theory of an adjacent fire reaching the black-powder primers ([Wikipedia — Mutsu](https://en.wikipedia.org/wiki/Japanese_battleship_Mutsu)).

### 1.3 Failure modes

1. **Flash propagation down the hoist train.** A hit in the gunhouse or working chamber ignites charges in transit. Flame then travels down hoists and trunks to the handling room and magazine through doors that are open, or that are interlocked but have failed.
   - **Seydlitz at Dogger Bank (24 Jan 1915).** A 13.5-inch shell holed the deck and the rear barbette. It flashed into the working chamber, and the fire spread through an open connecting door into the second aft turret.
     - 159 men were killed and both aft turrets were burned out.
     - The ship was saved because Pumpenmeister Heidkamp flooded the magazines, turning "red-hot valves" ([Wikipedia — SMS Seydlitz](https://en.wikipedia.org/wiki/SMS_Seydlitz)).
     - The Germans then fitted flash-tight doors and changed handling procedures.
   - **Lion, Q turret, Jutland.** A shell from Lützow penetrated at the join between the face plate and the roof.
     - Major Harvey ordered the magazine doors shut and the magazine flooded.
     - About 28 minutes later, charges left in the working chamber and on the hoists ignited (16:28). The flame reached masthead height and killed the men in the handling rooms and shell room.
     - The magazine doors buckled, but the flooded magazine behind them held ([Wikipedia — Francis Harvey](https://en.wikipedia.org/wiki/Francis_Harvey)).
   - **Derfflinger, turrets Caesar and Dora, Jutland.** In Caesar, 73 of 78 men died. In Dora, all 80 men died, including the magazine men. The brass-cased charges burned but did not explode ([von Hase](https://www.wtj.com/archives/hase_03.htm)).
2. **Magazine detonation, which means loss of the ship.**
   - **Jutland battlecruisers:**
     - Indefatigable: 2 survivors of 1,019.
     - Queen Mary: 9 survivors of 1,275 (sources vary slightly).
     - Invincible: 6 survivors of 1,032 ([Wikipedia — Battle of Jutland](https://en.wikipedia.org/wiki/Battle_of_Jutland)).
     - Contributing practices included stockpiling charges outside magazines and propping open anti-flash doors to raise the rate of fire. Historians debate how much each factor mattered: Lambert's thesis versus the critiques summarised on [Dreadnought Project — "A Direct Train of Cordite"](https://dreadnoughtproject.org/tfs/index.php/A_Direct_Train_of_Cordite). **[UNCERTAIN: relative weight of design vs. procedure]**
   - **Hood (24 May 1941).** 3 survivors of 1,418; she sank in about 3 minutes. The board of enquiry found a 15-inch hit "in or adjacent to Hood's 4-inch or 15-inch magazines… The probability is that the 4-inch magazines exploded first" ([Wikipedia — HMS Hood](https://en.wikipedia.org/wiki/HMS_Hood)).
   - **Barham (25 Nov 1941).** Three torpedoes hit, she capsized, and the magazines exploded about 4 minutes after the hits. The enquiry blamed a fire in the outboard 4-inch magazines spreading to the 15-inch magazines. 862 were killed ([Wikipedia — HMS Barham](https://en.wikipedia.org/wiki/HMS_Barham_(04))).
   - **Arizona (7 Dec 1941).** A bomb near turret II detonated the forward magazines about 7 seconds later. 1,177 of 1,512 aboard were killed, and the fires burned for two days ([Wikipedia — USS Arizona](https://en.wikipedia.org/wiki/USS_Arizona_(BB-39))).
   - **Mutsu (8 Jun 1943).** The No. 3 turret magazine exploded at anchor, cutting the ship in two. 1,121 of about 1,474 were killed ([Wikipedia — Mutsu](https://en.wikipedia.org/wiki/Japanese_battleship_Mutsu)).
   - **Kongō (21 Nov 1944).** Two submarine torpedoes flooded two boiler rooms. Her speed fell from 16 kn to 11 kn and she reached a 45° list.
     - She lost all power at 05:18, the forward 14-inch magazine exploded, and she sank about 2 h 38 min after the hits.
     - Over 1,200 were lost ([Wikipedia — Kongō](https://en.wikipedia.org/wiki/Japanese_battleship_Kong%C5%8D)).
     - Loss of power plus a list lets fire or friction reach the magazines.
   - **Yamato (7 Apr 1945).** At least 11 torpedoes and 6 bombs hit her. A bow magazine detonated as she capsized; the magazines could not be flooded because the pumping stations had been knocked out ([Wikipedia — Yamato](https://en.wikipedia.org/wiki/Japanese_battleship_Yamato)).
3. **Fire reaching a magazine from outside (slow cook-off).**
   - Astoria at Savo Island: a wardroom fire fed by furnishings, paint and records reached and exploded the **unflooded 5-inch magazine** below it ([WDR 29](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-quincy-ca39-astoria-ca34-vincennes-ca44-war-damage-report-no29.html)).
   - USN destroyers: only one destroyer suffered an *immediate* magazine explosion from an enemy weapon. In 5 other cases, fire later reached the magazines ([NHHC — Destroyer Report, Torpedo & Mine Damage](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-torpedo-mine-damage.html)).
4. **Unstable propellant or accident** with no enemy action: see 1.2. In WWI the British lost Bulwark (1914), Natal (1915) and Vanguard (1917) to internal explosions.

### 1.4 Mitigations

- **Flash-tight scuttles and anti-flash doors**, and interlocked hoists in later designs. In the KGV quad turret, "an interlock prevents the cages being raised unless the flash doors on the trunk in the shell and cordite handing rooms are closed" ([NavWeaps tech-122](https://www.navweaps.com/index_tech/tech-122.php)). There is a trade-off: interlock complexity cost Prince of Wales firepower (see section 2).
- **Flooding and sprinkling.** Sprinklers act quickly on fires near the magazine. Full flooding takes minutes, needs working valves (Seydlitz) and working pumps or power (Yamato), and makes the turret useless.
- **Cool, stable propellant and brass cases** (German practice).

### 1.5 Ready-use and secondary/AA ammunition

- Ready-use lockers sit next to open mounts and are topside and unprotected.
  - Hood's first damage was a boat-deck fire among 4-inch ready-use ammunition and UP rocket projectiles ([Wikipedia — HMS Hood](https://en.wikipedia.org/wiki/HMS_Hood); [Denmark Strait](https://en.wikipedia.org/wiki/Battle_of_the_Denmark_Strait)).
  - South Dakota, Hit No. 7: "several 1.1-inch clips exploded and ignited life jackets of dead and wounded men" ([NHHC — South Dakota WDR 57](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-south-dakota-bb57-war-damage-report-no57.html)).
  - Wasp: "Ready service ammunition forward detonated" ([NHHC Summary of War Damage 1941–42](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/summary-of-war-damage-17-oct-1941-to-7-dec-1942.html)).
- **Quincy at Savo Island:** a barbette hit on the shell deck of turret II detonated ready ammunition so violently that the captain thought the ship had blown up ([NavWeaps forum — turret v. barbette hits](https://www.tapatalk.com/groups/warships1discussionboards/turret-v-barbette-hits-t4491.html)).

### 1.6 Torpedo warheads on deck (Japanese cruisers and destroyers especially)

Japanese cruisers carried Type 93 "Long Lance" torpedoes on deck with large oxygen-fuelled warheads and reloads, under light or no protection.
- **Mikuma (Midway, 6 Jun 1942).** A fire amidships reached her torpedoes at about 13:58, "triggering a chain of massive secondary explosions". About 650 were killed and she sank ([Wikipedia — Mikuma](https://en.wikipedia.org/wiki/Japanese_cruiser_Mikuma)).
- **Mogami**, her sister in the same battle, had **jettisoned her torpedoes** on the order of her damage-control officer. A bomb then hit near the tubes and she survived ([Wikipedia — Mogami](https://en.wikipedia.org/wiki/Japanese_cruiser_Mogami_(1934))). This is a clean A/B comparison.
- **Furutaka (Cape Esperance).** About 90 shell hits, "some ignited her Type 93 'Long Lance' torpedoes, starting fires" ([Wikipedia — Furutaka](https://en.wikipedia.org/wiki/Japanese_cruiser_Furutaka)).
- **Chōkai (Samar, 1944).** She was long believed lost to a torpedo detonation, but the 2019 wreck survey found her torpedoes intact ([Wikipedia — Chōkai](https://en.wikipedia.org/wiki/Japanese_cruiser_Ch%C5%8Dkai)). Treat torpedo cook-off as *probabilistic*, not certain.
- **Lützow (Jutland).** Underwater hits forward wrecked the broadside torpedo flat. She flooded to over 8,000 t, her speed fell from 26 kn to 3 kn, and she was scuttled ([Navy General Board — Lützow](https://www.navygeneralboard.com/sms-lutzow-and-her-doomed-journey-home/)). Torpedo rooms below the waterline are big, weakly subdivided flooding holes.

### 1.7 Depth charges and other stern stowage

- Destroyers carried depth charges in racks at the stern and in throwers. If they were not set to "safe", they could detonate as a sinking ship went down, among the survivors in the water.
- **USS Strong (1943):** "several of her depth charges exploded" as she sank ([Wikipedia — USS Strong](https://en.wikipedia.org/wiki/USS_Strong_(DD-467))).
- USN practice was to check charges were set on safe: Abner Read's severed stern sank "with no explosions" ([NHHC Destroyer Report](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-torpedo-mine-damage.html)).

**MODEL NOTE — Ammunition**
- Model each magazine as a node with a **sensitivity** (cordite high, RP C/12 low, NC low-to-medium, black powder very high), a **fill fraction**, and a **state**: dry / sprinkled / flooded.
- **Detonation check.** Run it when a penetrating shell bursts in or next to a magazine, or when fire reaches it, or (via the flash chain) when a turret burns. Chance = sensitivity × fill × (1 − flood state). A result of "detonate" means the ship is lost, or for small ships broken in two.
- **Flash chain.** A turret fire rolls to propagate gunhouse → working chamber → handling room → magazine. Each anti-flash door has an integrity value. A "rate-of-fire doctrine" toggle (doors propped open) multiplies the propagation chance; that is the Jutland trade-off.
- **Flooding a magazine** is a player or AI action. It takes about N turns, needs valves (crew) or pumps (power), removes the ammunition, and adds flooding weight.
- **Ready-use ammunition** is a small topside fire source next to each AA or secondary mount. It never sinks the ship, but it causes casualties and fires.
- **Deck torpedoes** are a high-risk topside explosive. Allow a "jettison" action (Mogami). A cook-off deals heavy internal damage over 0.4–0.6 of length.
- Wing secondary magazines (Barham) are a magazine with less protection and a high fire-propagation link to the main magazine.

---

## 2. Main battery: gunhouse, barbette, working chamber, training and elevating gear

### 2.1 Anatomy and location

- **Gunhouse:** the armoured rotating shield with the guns, rammers and sights, and often a turret rangefinder. It sits on top of the **rotating structure** (the turntable on a **roller path**), which hangs down inside the fixed **barbette**.
- **Working chamber:** under the gunhouse, where ammunition is transferred.
- **Machinery:** the training engine and pinion on a fixed rack, elevating cylinders, and hoists. Hoists run through the barbette to the handling rooms.
- **Location:** on the centreline at about 0.15–0.30 (A/B) and 0.70–0.85 (X/Y). Wing or echelon turrets appear in the dreadnought era.
- **Protection:** face plate thickest, then barbette, then roof. Barbette armour usually tapers below the main deck because the belt is expected to cover it.

### 2.2 Power

- **Royal Navy:** hydraulic turret machinery throughout. Dreadnought's turrets were hydraulic ([Wikipedia — HMS Dreadnought](https://en.wikipedia.org/wiki/HMS_Dreadnought_(1906))). The pumping engines were remote from the turret: Marlborough had a "Hydraulic Engine Room", flooded by her Jutland torpedo hit ([Dreadnought Project — Marlborough at Jutland](https://www.dreadnoughtproject.org/tfs/index.php/H.M.S._Marlborough_at_the_Battle_of_Jutland)).
- **USN:** electric-hydraulic drives. Electric motors drove hydraulic pumps for training, elevation and rammers ([GlobalSecurity — Main Battery Turret](https://www.globalsecurity.org/military/systems/ship/turrets.htm)).
- **German (Bismarck):** electric training with hydraulic elevation ([Wikipedia — Bismarck class](https://en.wikipedia.org/wiki/Bismarck-class_battleship)).
- **Consequence:** loss of electrical or hydraulic power slows the turret to hand training (very slow) or stops it. Prince of Wales' aft 5.25-inch turrets had "no electric power at all", which also prevented manual training in practice ([Death of a Battleship, 2012](https://pacificwrecks.com/ship/hms/prince-of-wales/death-of-a-battleship-2012-update.pdf)).

### 2.3 Failure modes

| Mode | Mechanism | Examples |
|---|---|---|
| Penetration of gunhouse | Crew killed and charges ignited (see the flash chain in section 1) | Lion Q; Derfflinger C and D; Seydlitz |
| Joint / roof hit | The face-roof joint is weak; spalled armour enters | Lion Q; Tiger Q roof-edge hit destroyed the rangefinder and killed 2 with spalled roof plate ([USNI Proceedings 1925](https://www.usni.org/magazines/proceedings/1925/april/lessons-jutland-affecting-design-turret-armor)) |
| Barbette hit, no penetration | Ring distorted, so training jams | Vincennes turret I "jammed in train"; Astoria turret I knocked out by two 8-inch barbette hits ([NavWeaps forum](https://www.tapatalk.com/groups/warships1discussionboards/turret-v-barbette-hits-t4491.html)). South Dakota turret III: a 14-inch hit gouged the 17.3-inch barbette 1.5 in deep with no penetration ([WDR 57](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-south-dakota-bb57-war-damage-report-no57.html)) |
| Face hit, no penetration | Armour chunk knocked off; turret jams; internal spall | Vincennes turret III jammed in train; Houston turret II face hit caused fragments and powder fires |
| Hoist/cage damage | Loading stops | Tiger Q: "Both loading cages were damaged… electric firing circuits carried away" ([USNI 1925](https://www.usni.org/magazines/proceedings/1925/april/lessons-jutland-affecting-design-turret-armor)) |
| Mechanical/interlock failures (no hit) | Complex anti-flash interlocks, shell ring jams | Prince of Wales at Denmark Strait: A1 failed after the first salvo; Y turret's shell ring jammed at salvo 20; about 26% loss of output, 7 of 10 guns working at the end ([Wikipedia — Denmark Strait](https://en.wikipedia.org/wiki/Battle_of_the_Denmark_Strait)). KGV at North Cape: shells "took charge" in a roll and jammed three guns for 15 min ([NavWeaps tech-122](https://www.navweaps.com/index_tech/tech-122.php)) |
| Shell passes through without detonating | One gun disabled | Chōkai forward turret: one gun still usable ([NavWeaps forum](https://www.tapatalk.com/groups/warships1discussionboards/turret-v-barbette-hits-t4491.html)) |
| List | Loading and training slow down | Marlborough at a 7° list: shells slipped during loading, brakes unshipped in 4 turrets ([Dreadnought Project](https://www.dreadnoughtproject.org/tfs/index.php/H.M.S._Marlborough_at_the_Battle_of_Jutland)). Prince of Wales' 5.25-inch turrets could not depress far enough at an 11.5° list ([Death of a Battleship](https://pacificwrecks.com/ship/hms/prince-of-wales/death-of-a-battleship-2012-update.pdf)) |
| In-bore explosion / overram | Accident | **Iowa turret II, 19 Apr 1989** (postwar example): 47 killed; a fireball at 2,500–3,000 °F spread through all three gun rooms; the magazines were flooded and did not explode ([Wikipedia](https://en.wikipedia.org/wiki/USS_Iowa_turret_explosion)) |
| Barrel hit | Damaged barrel cannot fire | Derfflinger's secondary battery had one barrel burst and one gun destroyed ([von Hase](https://www.wtj.com/archives/hase_03.htm)). **[UNCERTAIN]** I found no well-sourced main-battery barrel-hit example; treat it as a plausible low-frequency event |

- Rates of fire matter for "turret down" penalties. The KGV turret's hoist cycles were 26 s, 17 s and 30 s, giving a nominal maximum of 2 rounds per minute ([NavWeaps tech-122](https://www.navweaps.com/index_tech/tech-122.php)).
- **Recovery is possible.** Scharnhorst's turret Bruno was knocked out by Duke of York's first salvo and later brought back into action; Anton was not ([Wikipedia — North Cape](https://en.wikipedia.org/wiki/Battle_of_the_North_Cape)).

**MODEL NOTE — Main battery**
- Split each turret into sub-components:
  - Gunhouse (crew + guns): penetration kills crew and rolls the flash chain.
  - Barbette/roller path: armour; a non-penetrating heavy hit rolls "jammed in train", lasting the rest of the battle or N turns to free.
  - Hoists: rate of fire × 0.5 or 0.
  - Per-gun barrel state.
- **Power dependency:** with no turret power, use hand training at about 10% of normal traverse speed or none, and a 2–4× slower reload. **[UNCERTAIN: exact factors; tune for gameplay]**
- **Mechanical unreliability** without hits: a per-salvo malfunction chance, scaled by the "complexity" of new quad or triple turrets and anti-flash interlocks.
- **List penalty:** above about 5°, reload slows; above about 10°, depression and elevation limits block some arcs.

---

## 3. Secondary and AA batteries; casemates; open mounts

- **Casemates** (pre-dreadnought to WWI) are armoured boxes in the hull side at main or upper deck level, often along 0.25–0.75 of length.
  - **Wash:** Iron Duke's 6-inch casemates were "mounted too low". The hinged covers "were easily washed away… water easily entered the ship and caused significant flooding". The fix was dwarf bulkheads and rubber seals ([Wikipedia — Iron Duke class](https://en.wikipedia.org/wiki/Iron_Duke-class_battleship)).
  - **Heavy seas:** at Coronel, Good Hope's and Monmouth's main-deck casemate 6-inch guns were largely unworkable, because opening the gun doors flooded the ship ([Wikipedia — Coronel](https://en.wikipedia.org/wiki/Battle_of_Coronel)).
  - **Fire:** cordite in casemate batteries is an open fire chain across a long gun deck.
- **Enclosed secondary turrets and gunhouses** (dual-purpose 5-inch/38, 5.25-inch, 15 cm) depend on power and on the director. Prince of Wales' aft 5.25-inch turrets lost power entirely after one torpedo ([Death of a Battleship](https://pacificwrecks.com/ship/hms/prince-of-wales/death-of-a-battleship-2012-update.pdf)).
- **Open mounts** (light AA such as 20 mm, 25 mm, 40 mm, 1.1-inch, pom-poms) have splinter shields at most.
  - Crew losses come from strafing, near-miss bomb fragments and shell splinters. On Yamato's last sortie, "strafing had incapacitated many of the gun crews who manned Yamato's unprotected 25 mm anti-aircraft weapons" ([Wikipedia — Yamato](https://en.wikipedia.org/wiki/Japanese_battleship_Yamato)).
  - South Dakota's superstructure hits fell mostly on unprotected stations; she lost 38 killed and 60 wounded ([Naval Gazing — Mission Kills](https://www.navalgazing.net/Survivability-Mission-Kills)).

**MODEL NOTE — Secondary/AA**
- Casemates get a **sea-state penalty**: firing is impossible above a threshold that depends on casemate height above the waterline. A hit on a casemate can add a flooding source at the main deck.
- Open mounts are cheap, numerous, and "soft". Use a **crew pool per mount**, damaged by splinter blasts (area effect) rather than direct penetration. A mount with no crew is out until crew is transferred.
- DP turrets: power dependency plus director dependency (local control penalty, as in section 4).

---

## 4. Fire control: directors, rangefinders, transmitting station / plotting room, radar

### 4.1 Components and location

- **Main battery director and spotting top:** high on the foremast, tripod or pagoda, at about 0.25–0.35 of length, unarmoured or splinter-proof. Often there is an **after director** at about 0.6–0.7.
  - Hood had a 15-foot director rangefinder plus a 30-foot rangefinder in each turret ([HMS Hood Association — Fire Control](https://www.hmshood.org.uk/ship/fire_control.htm)).
  - Bismarck had three fire-control stations, each with a rangefinder cupola and a FuMO 23 radar ([Wikipedia — Bismarck class](https://en.wikipedia.org/wiki/Bismarck-class_battleship)).
- **Transmitting station (RN) or plotting room (USN):** "below the waterline and inside the armored belt" ([Wikipedia — Ship gun fire-control system](https://en.wikipedia.org/wiki/Ship_gun_fire-control_system)).
  - It houses the analogue fire-control computer: the Dreyer Table (RN), the Ford Rangekeeper Mk 1 (USN, about 3,125 lb), or the German Rechenstelle.
  - Hood's transmitting station was on the Platform Deck, 9 levels below the director ([HMS Hood Association](https://www.hmshood.org.uk/ship/fire_control.htm)).
- **Turret rangefinders** allow **local control**. Iowa's turrets could fire under local control with 46-foot rangefinders and Mk 3 computers. The turret I rangefinder was removed because spray blinded it ([Naval Gazing — Fire Control Part 2](https://www.navalgazing.net/Fire-Control-Part-2)).
- **Radar** (from 1941–42), e.g. USN Mk 4, 8, 12 and 22 on Mk 37 / Mk 38 directors; Mk 4 first went to sea in Sept 1941 ([Wikipedia — Ship gun fire-control system](https://en.wikipedia.org/wiki/Ship_gun_fire-control_system)).
  - Antennas are thin, exposed and splinter-fragile.
  - Waveguides and cables run down through the superstructure.
- **Communications to the guns:** fire-control circuits run through the superstructure. These are extremely vulnerable (section 8).

### 4.2 Failure modes and examples

- **Director destroyed:**
  - Bismarck: Rodney's 16-inch hit at 09:02 wrecked the forward superstructure, damaging the bridge and main director and killing most senior officers. All turrets were out by about 09:31 ([Wikipedia — Last battle of Bismarck](https://en.wikipedia.org/wiki/Last_battle_of_the_battleship_Bismarck)).
  - Naval Gazing gives the forward director lost after about 15 min and the aft director about 30 min later ([Mission Kills](https://www.navalgazing.net/Survivability-Mission-Kills)). **[UNCERTAIN: exact timing differs by source]**
- **Radar knocked out:**
  - Scharnhorst at North Cape: Norfolk's hit destroyed her forward radar, leaving her "virtually blind in a mounting snowstorm" ([Wikipedia — North Cape](https://en.wikipedia.org/wiki/Battle_of_the_North_Cape)).
  - South Dakota: "All radio transmitting antennae and all radars, except the one on Main Battery Director II, were rendered inoperative". Hits 13–15 demolished radar plot, and hit 6 severed the 5-inch director's centre column ([WDR 57](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-south-dakota-bb57-war-damage-report-no57.html)). The captain called the morale effect of losing search radar "most depressing".
- **Spotting top communications cut:** Derfflinger had "telephones and speaking-tubes running to the fore-top… shot away". The gunnery officer fell back on messengers and speaking tubes ([von Hase](https://www.wtj.com/archives/hase_03.htm)).
- **Smoke interference:** Dreadnought's foremast behind the forward funnel put the spotting top "right in the plume of hot exhaust gases" ([Wikipedia — HMS Dreadnought](https://en.wikipedia.org/wiki/HMS_Dreadnought_(1906))). Battle smoke and funnel smoke degrade optical rangefinding.
- **Rigging fouling:** after Savo, stays were removed from heavy cruisers' masts to stop them fouling the directors ([WDR 29](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-quincy-ca39-astoria-ca34-vincennes-ca44-war-damage-report-no29.html)).
- **Accuracy hierarchy.** Radar-directed USN fire (Washington against Kirishima at about 8,400 yd at night: at least 20 hits with 16-inch and 17 with 5-inch) is far better than optical or local control at night ([Wikipedia — Kirishima](https://en.wikipedia.org/wiki/Japanese_battleship_Kirishima)). **[UNCERTAIN]** I found no clean published number for the director-versus-local-control accuracy ratio. Game designers should choose one (e.g. local control at 30–50% of director hit rate, worse at long range).

**MODEL NOTE — Fire control**
- Model a hierarchy: **Radar FC → Optical director → After/secondary director → Turret local control**. Each level down reduces effective range and accuracy, and the drop is steeper at night or in poor visibility.
- Fire-control nodes are topside (high, splinter-only protection) except the **computer/plot**, which is deep in the citadel.
- If the plot is lost but directors survive, the directors fall back to "director with degraded solution". If the **FC cable links** are lost (an electrical-network edge), the result is the same as losing the director.
- **Radar antennas** take damage from any hit or splinter burst on the superstructure. Make them high-probability, low-hit-point items, repairable only by spares (low chance at sea).
- **Smoke:** the auto-layout should penalise a director placed just aft of a funnel.

---

## 5. Command: conning tower, bridge, CIC, communications

- **Conning tower (CT):** heavily armoured, at about 0.25–0.30 of length, at the base of the forward superstructure. It holds engine-order telegraphs, voice pipes, telephones and often a wheel ([Wikipedia — Conning tower](https://en.wikipedia.org/wiki/Conning_tower)).
  - Armour ranges from about 3 inches to over 12 inches (Nelson). KGV had 4.5-inch sides.
  - **Commanders rarely used it.** There is "no evidence that RN captains and admirals used the armoured conning towers" at Denmark Strait. The USN replaced heavy CTs with cruiser-style ones in rebuilt battleships ([Wikipedia](https://en.wikipedia.org/wiki/Conning_tower); [NavWeaps forum — Armored conning tower or not](https://www.tapatalk.com/groups/warships1discussionboards/armored-conning-tower-or-not-t50311.html)).
  - **Vision slits are a weak point:** at Jutland, splinters came "through the aperture on to the bridge" on Derfflinger and gas entered the CT ([von Hase](https://www.wtj.com/archives/hase_03.htm)).
- **Bridge, compass platform and flag bridge:** unarmoured and high in the forward superstructure.
  - **Tsesarevich (Yellow Sea, 10 Aug 1904):** a 12-inch hit killed Admiral Vitgeft and his staff and jammed the wheel. The ship heeled 12° in a sharp port turn and turned back through her own line. Retvizan followed her, and the Russian squadron dissolved ([Wikipedia — Battle of the Yellow Sea](https://en.wikipedia.org/wiki/Battle_of_the_Yellow_Sea)).
  - **Prince of Wales (Denmark Strait):** a 15-inch hit on the compass platform killed most of the people there. Captain Leach survived ([Wikipedia — PoW](https://en.wikipedia.org/wiki/HMS_Prince_of_Wales_(53))).
  - **Hiei (1st Guadalcanal):** Laffey raked the superstructure, wounding Admiral Abe and killing his chief of staff ([Wikipedia — Hiei](https://en.wikipedia.org/wiki/Japanese_battleship_Hiei)).
  - **Mogami (Surigao Strait):** hits destroyed the bridge and air-defence centre and killed the captain and executive officer ([Wikipedia — Mogami](https://en.wikipedia.org/wiki/Japanese_cruiser_Mogami_(1934))).
  - **Bismarck:** most senior officers were killed by the 09:02 hit ([Wikipedia](https://en.wikipedia.org/wiki/Last_battle_of_the_battleship_Bismarck)).
- **CIC (USN, winter 1942–43 onward):** a radar-plot and information-fusion room created after the Solomons night actions exposed disorganisation ([Wikipedia — Combat information center](https://en.wikipedia.org/wiki/Combat_information_center)). Early CICs were in the superstructure; later ones moved lower. **[UNCERTAIN: location by date]**
- **Communications:**
  - **Signal halyards and flags:** at Dogger Bank, "most of Lion's signal halyards had been shot away". Beatty's signals were misread and the battlecruisers turned on Blücher instead of chasing Hipper ([Wikipedia — HMS Lion](https://en.wikipedia.org/wiki/HMS_Lion_(1910))).
  - **Wireless (W/T) rooms and aerials:** Lützow's wireless hits killed 12 and cut Hipper off from his command, so he had to change ship ([Navy General Board](https://www.navygeneralboard.com/sms-lutzow-and-her-doomed-journey-home/)). Hits on Peresvet's masts stopped Prince Ukhtomsky from signalling ([Yellow Sea](https://en.wikipedia.org/wiki/Battle_of_the_Yellow_Sea)).
  - **Internal communications:** voice pipes and sound-powered phones, which work without power, plus ship-power telephones. Ark Royal's single torpedo "knocked out all internal communications" ([Wikipedia — Ark Royal](https://en.wikipedia.org/wiki/HMS_Ark_Royal_(91))).

**MODEL NOTE — Command**
- Have a **Command node** (the bridge), with a backup (CT or secondary conning position aft) and a **Flag** sub-node on flagships.
- **Bridge hit:**
  - Roll for officer casualties.
  - Apply a "command delay" of N turns, in which the AI keeps its last order. A helm hit can also lock the rudder (Tsesarevich).
  - Loss of the flag means fleet orders go out of sync and division ships follow their leader blindly.
- **Comms nodes:**
  - Radio room and aerials control inter-ship orders and air spotting.
  - Signal halyards are the pre-radio fallback (visual range only, cut by smoke).
  - Internal comms degrade the link between command and the steering, engine and gun nodes: orders arrive late.
- The CT reduces casualties to the command node only if the player chooses to "fight from the CT", at the cost of a visibility or detection penalty.

---

## 6. Propulsion: boilers, engines, shafts, propellers, uptakes, fuel

### 6.1 Evolution and arrangements

- **Engines:**
  - Pre-1905: reciprocating triple- or quadruple-expansion engines, running at about 120 rpm on the Lord Nelson class.
  - From 1906: direct-drive turbines. Dreadnought ran at 325 rpm, with 18 B&W boilers at 250 psi, 23,000 shp and 21.6 kn.
  - Then geared turbines and turbo-electric drive. Sources: [Naval Gazing — Propulsion Part 2](https://www.navalgazing.net/Engineering-Part-2); [Wikipedia — Dreadnought](https://en.wikipedia.org/wiki/HMS_Dreadnought_(1906)).
- **Fuel:** coal, then mixed (oil sprayed on coal), then all-oil (RN from Queen Elizabeth, about 1912). Oil let roughly "100 firemen and 112 coal passers" be replaced "by 24 men" and gave 30–55% more endurance per ton. The cost was losing the protective coal bunkers ([Naval Gazing](https://www.navalgazing.net/Engineering-Part-2)).
- **Turbo-electric** (USN New Mexico/Tennessee/Colorado classes; Lexington carriers):
  - Lexington had 4 turbo-generators of 35.2 MW each and 8 motors of 22,500 shp ([Wikipedia — USS Lexington](https://en.wikipedia.org/wiki/USS_Lexington_(CV-2))).
  - It allowed finer subdivision, with motor rooms separate from the generators. It was heavy, and flooding or arcing in the electrical gear was a known risk. **[UNCERTAIN: no specific battle-damage example of turbo-electric failure found]**
- **Grouped versus unit (alternating) arrangement:**
  - Grouped: all boiler rooms together, then all engine rooms. One hit can flood the whole plant.
  - Unit system: boiler-room / engine-room pairs alternate, so "a single torpedo hit… could not flood all of the boiler or engine rooms" ([Wikipedia — Unit system](https://en.wikipedia.org/wiki/Unit_system_of_machinery)).
  - The cost: Leander-class (Amphion group) machinery spaces grew by 8 ft, the armour by 57 ft, and the ship needed two funnels.
  - USN later destroyers, the Iowa "split plant", and many WWII cruisers used the unit system ([Naval Gazing — Iowa engine room](https://www.navalgazing.net/Pictures-Iowa-Engine-Room)).
- **Location:**
  - Boiler rooms at about 0.35–0.55 of length and engine rooms at about 0.55–0.70, inside the citadel on the lowest decks, with the funnels above the boiler rooms.
  - Shafts run aft from the engine rooms through **shaft alleys** to struts and propellers at about 0.85–1.0, outside the citadel on most designs.

### 6.2 Failure modes and examples

| Failure | Mechanism | Example |
|---|---|---|
| Boiler-room flooding | Torpedo, mine or penetrating shell; loss of steam from that room | Kongō: 2 boiler rooms flooded by two torpedoes ([Wikipedia](https://en.wikipedia.org/wiki/Japanese_battleship_Kong%C5%8D)). Marlborough: "A" boiler room, diesel room and hydraulic room flooded; speed fell to 17 kn, then 15 and 13 ([Dreadnought Project](https://www.dreadnoughtproject.org/tfs/index.php/H.M.S._Marlborough_at_the_Battle_of_Jutland)) |
| Shell in boiler room | Steam loss, then repaired | Scharnhorst: a 14-inch hit destroyed No. 1 boiler room and speed fell to 10 kn; she "recovered to 22 kn" after repairs ([Wikipedia — North Cape](https://en.wikipedia.org/wiki/Battle_of_the_North_Cape)) |
| Feed-water contamination | Saltwater entering the feed system makes boilers unusable | Lion at Dogger Bank: a splinter holed the capstan engine exhaust, which "contaminated the auxiliary condenser with saltwater". Engines failed; speed fell from 27 kn to about 15 kn, then 8 kn, with about 3,000 t of water aboard and a 10° list ([Wikipedia — HMS Lion](https://en.wikipedia.org/wiki/HMS_Lion_(1910))) |
| Fuel system | Purifiers, transfer pumps or tanks lost, so fuel is unusable | Graf Spee: about 70 hits destroyed her oil purification plant, desalination plant and galley; a major factor in going into Montevideo ([Wikipedia](https://en.wikipedia.org/wiki/German_cruiser_Admiral_Graf_Spee)). Bismarck: a PoW hit cut off 1,000 t of forward fuel, caused an oil slick and a 2 kn speed loss ([Denmark Strait](https://en.wikipedia.org/wiki/Battle_of_the_Denmark_Strait)) |
| Shaft whip / shaft alley | A damaged strut lets the shaft wobble and wreck the bulkhead glands along the shaft alley, so flooding enters the machinery | Prince of Wales (10 Dec 1941). (1) A torpedo tore a hole of about 4 × 6 m abaft the port outer stern tube. (2) The shaft kept turning out of true and broke a strut arm. (3) Glands at frames 270, 253, 242, 228 and 206 were wrecked and the shaft came apart. (4) Results: an 11.5° list, speed falling from 25 kn to 15 kn, then 8 kn, about 18,000 t of water by 12:50, and only 3 of 8 generators running ([Death of a Battleship, 2012](https://pacificwrecks.com/ship/hms/prince-of-wales/death-of-a-battleship-2012-update.pdf)) |
| Uptakes and funnels | Hits or flooding cut boiler draught | Ark Royal: "power was lost shipwide when the boiler uptakes became choked" by flooding ([Wikipedia](https://en.wikipedia.org/wiki/HMS_Ark_Royal_(91))). Funnel hits from shellfire cut draught; widely reported for coal-era ships. **[UNCERTAIN: no quantified funnel-hit speed loss found; suggest a modest penalty]** |
| Steam line rupture | High-pressure or superheated steam (250 psi in 1906, about 600 psi or more in WWII USN ships) scalds crews and empties the boiler room. **[UNCERTAIN: exact WWII pressures by class not verified here]** | Seen generally in USN destroyer war damage reports ([Destroyer Report](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-torpedo-mine-damage.html)) |
| Whole-plant loss from one hit (destroyers) | Machinery fills about 40% of the length | 31 USN destroyers torpedoed and only 7 saved. Survival needed flooding of fewer than 3 complete machinery spaces and keeping some propulsion. Hambleton's keel was pushed up 16 in; Strong broke in two after 39 min ([Destroyer Report](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-torpedo-mine-damage.html)) |

- **Coal bunkers as protection:** Wikipedia's armoured-cruiser article says "two feet of coal was considered the equivalent of one foot of steel" ([Wikipedia — Armored cruiser](https://en.wikipedia.org/wiki/Armored_cruiser)). **[UNCERTAIN: that ratio looks far too generous. The rule of thumb usually quoted elsewhere is about 2 ft of coal ≈ 1 in of steel. I could not verify either against a primary source, so treat the protective value as low and as a designer choice.]** Bunkers also added buoyancy when compartments flooded (same source). The protection shrinks as coal is burned.
- **Oil tanks** are a liquid layer in the side protection system, but they also feed fires, leak and leave a trail (Bismarck), and can be cut off.

**MODEL NOTE — Propulsion**
- Each **boiler room** gives steam points. **Engine rooms** turn steam into shaft power, and each **shaft** turns power into thrust. Speed scales with the cube root of delivered power, which means losing half the plant still leaves about 80% of speed. That matches PoW's 25 kn → 15 kn after losing 2 of 4 shafts, plus extra drag.
- **Unit versus grouped** should be a generator option: unit layouts cost length and armour but survive single torpedoes.
- **Shaft whip:** after an aft underwater hit on a shaft, if the shaft is still powered there is a chance each turn to propagate flooding forward along the shaft alley. The player can choose to "stop the shaft", trading speed for flooding.
- **Feed water:** a global "feed reserve" or contamination status. A rare splinter event takes boilers offline gradually (Lion).
- **Fuel:** tanks as side layers. Hits add a fire chance and an oil slick (detection by aircraft), and cut off part of the fuel (an endurance penalty for the campaign layer).
- **Coal-era ships:** bunker protection value that decreases with coal remaining. Stoker crews are a big casualty pool.
- **Funnel hit:** about −5 to −10% boiler output per funnel holed, plus a smoke penalty to own fire control **[designer choice; not sourced]**.

---

## 7. Steering

- **Components:** rudder(s) at about 0.95–1.0 of length; the steering gear room or tiller flat above them, usually aft of the citadel or in an armoured box; steering engines (steam, later electro-hydraulic); the transmission from the bridge (telemotor, electrical); an emergency hand position.
  - Twin rudders were common in RN dreadnoughts and German ships. Dreadnought had twin rudders ([Wikipedia](https://en.wikipedia.org/wiki/HMS_Dreadnought_(1906))).
  - Yamato had main and auxiliary rudders ([Wikipedia](https://en.wikipedia.org/wiki/Japanese_battleship_Yamato)).
- **Failure examples:**
  - **Bismarck:** a Swordfish torpedo hit astern at about 20:47 on 26 May 1941 "jammed Bismarck's rudder and steering gear 12° to port". Steering by alternating shaft power failed and pushed her towards the British ([Wikipedia — Last battle](https://en.wikipedia.org/wiki/Last_battle_of_the_battleship_Bismarck)). Bismarck had two closely spaced rudders; the Wikipedia class article's "single rudder system" phrasing seems to be an error. **[UNCERTAIN]**
  - **Hiei:** San Francisco hit the steering gear room, "flooding it with water, shorting out her power steering generators". The rudder jammed and she circled at 5 kn and was later finished by aircraft. "Without these hits, Hiei would have survived the battle" ([Wikipedia — Hiei](https://en.wikipedia.org/wiki/Japanese_battleship_Hiei)).
  - **Kirishima:** the last 16-inch hit "destroyed Kirishima's twin rudders", and steering by propellers was ineffective ([Wikipedia — Kirishima](https://en.wikipedia.org/wiki/Japanese_battleship_Kirishima)).
  - **Tsesarevich:** helm jammed from the bridge, a command failure plus jammed helm ([Yellow Sea](https://en.wikipedia.org/wiki/Battle_of_the_Yellow_Sea)).
  - **Prince of Wales:** steering was lost through loss of electrical power aft, and standby steam leads were not enough ([Death of a Battleship](https://pacificwrecks.com/ship/hms/prince-of-wales/death-of-a-battleship-2012-update.pdf)).
  - **Yamato:** with the auxiliary steering room flooded she "lost maneuverability and became stuck in a starboard turn" ([Wikipedia](https://en.wikipedia.org/wiki/Japanese_battleship_Yamato)).
  - **Abner Read:** the severed stern took the steering gear with it ([Destroyer Report](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-torpedo-mine-damage.html)).

**MODEL NOTE — Steering**
- Rudder state: free / jammed at angle X / missing.
  - A **jam** is the worst case, forcing a circle.
  - **Missing** allows steering-by-engines with differential shaft power, about 20–40% of normal turn rate on 3–4 shaft ships. It is impossible on single-shaft ships and poor on 2 shafts at low speed. **[designer estimate]**
- **Steering gear room** is a separate node, power-dependent. Losing power means hand steering, which is slow, needs crew, and has a limited angle.
- **Bridge-to-steering link** (telemotor or cable) can be cut, forcing a local helm (command delay).
- Make the stern a "golden BB" zone for torpedoes and aircraft: low hit chance, huge consequence. Players should value twin or auxiliary rudders spaced apart.

---

## 8. Electrical system

- **Evolution:**
  - 1890s pre-dreadnoughts: dynamos mainly for lighting, searchlights, some ammunition hoists and ventilation fans.
  - Dreadnought (1906): about 100 V DC from steam- and diesel-driven dynamos, rated around 100 kW each. Total capacity was a few hundred kW. Wikipedia lists three 100 kW Siemens units driven by two Brotherhood steam and two Mirrlees diesel engines. **[UNCERTAIN count]** Power was used for lifts, winches, pumps, ventilation, lighting and phones ([Wikipedia](https://en.wikipedia.org/wiki/HMS_Dreadnought_(1906))).
  - Bismarck (1940): 8 diesel generators of 500 kW and 10 turbo-generators of 690 kW, plus AC sets, totalling **7,910 kW** at 220 V ([Wikipedia — Bismarck class](https://en.wikipedia.org/wiki/Bismarck-class_battleship)).
  - Prince of Wales: 6 turbo-dynamos and 2 diesel dynamos of 330 kW each ([Death of a Battleship](https://pacificwrecks.com/ship/hms/prince-of-wales/death-of-a-battleship-2012-update.pdf)). **[UNCERTAIN: other sources give higher ratings]**
  - Iowa: 4 ship-service turbo-generators of 1,250 kW at 450 V AC in the engine rooms, split into a forward and an after plant, with several switchboards ([Naval Gazing — Iowa engine room](https://www.navalgazing.net/Pictures-Iowa-Engine-Room)). Wikipedia-derived totals of about 10 MW include emergency diesels. **[UNCERTAIN: emergency diesel count/rating not verified here]**
- **By 1941 almost everything depended on power:** turret drives (US and German), DP mounts, radar, fire-control computers and synchro transmission, pumps, ventilation, steering and lighting.
- **Failure modes:**
  - **Generator loss.** Steam generators fail when boiler rooms flood (Ark Royal had no diesel backup, the main switchboard flooded, and she sank after about 14 hours; [Wikipedia](https://en.wikipedia.org/wiki/HMS_Ark_Royal_(91))). PoW lost 5 of 8 generators.
  - **Switchboard flooding or arcing.** Saratoga: "Electrical arcing occurred on main oil switches. Electrical explosions resulted in loss of power" ([NHHC Summary 1941–42](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/summary-of-war-damage-17-oct-1941-to-7-dec-1942.html)).
  - **Cable cuts and short circuits overloading breakers.** South Dakota at 2nd Guadalcanal:
    - The *shock of her own turret III firing* made a bus-transfer switch parallel generators out of phase, rupturing a feeder and cutting power to the after 5-inch director and mounts for about 1 minute.
    - Later, superstructure hits caused short circuits that tripped the IC switchboard, giving about 3 minutes without power. She lost fire control, internal communications and search radar ([WDR 57](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-south-dakota-bb57-war-damage-report-no57.html); [Naval Gazing](https://www.navalgazing.net/Survivability-Mission-Kills)).
  - **Ring main severed.** PoW lost the whole after ring main and power to 6 of 8 secondary turrets ([Naval Gazing](https://www.navalgazing.net/Survivability-Mission-Kills)).
  - **Darkness** slows damage control: PoW's stern was "plunged… into darkness".
- **Mitigations:**
  - Dispersed generators and cross-connected switchboards.
  - **Diesel emergency generators.** After Savo, the USN added 50–75 kW diesels forward and aft on cruisers ([WDR 29](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-quincy-ca39-astoria-ca34-vincennes-ca44-war-damage-report-no29.html)).
  - **Casualty power:** portable cables rigged around damage. The USN system is described in [NSTM ch. 320](https://maritime.org/doc/nstm/ch320.pdf).
  - Battle lanterns.

**MODEL NOTE — Electrical**
- Use a **graph**: generators, connected through switchboards, feeding bus or ring segments, which feed consumers.
- Each consumer draws on a segment. If a segment has no live path to a running generator, its consumers lose power.
- Generators need steam (link to boiler rooms) or diesel (independent).
- **Short-circuit event:** any superstructure hit with cable runs rolls a chance to trip a breaker, causing a 1–3 turn blackout of that segment. Crews reset it (South Dakota). Rarely, it is permanent until casualty power is rigged.
- **Casualty-power action:** a damage-control team rigs a bypass in N turns (USN late-war bonus).
- Era scaling: 1890s ships depend little on power (hand and steam backups everywhere); 1940s ships depend heavily on it, so a blackout hurts them much more.

---

## 9. Hydraulics and auxiliaries

- **Hydraulic pumping engines** (RN turrets) sit in separate rooms. If the hydraulic engine room floods (Marlborough), the turrets have to share the remaining pumps.
- **Pumps:** drainage and bilge pumps (steam or electric) and fire-main pumps.
  - Loss of power means no pumping (PoW, Ark Royal, Kongō).
  - **Fire mains** severed by hits or splinters leave only CO₂ extinguishers and bucket brigades (Astoria). A ruptured fire main can also *cause* flooding: Ralph Talbot reached a 20° list from topside flooding through a broken main ([NHHC Summary 1941–42](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/summary-of-war-damage-17-oct-1941-to-7-dec-1942.html)).
  - The post-Savo fix was looped fire mains along the full length of the ship ([WDR 29](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-quincy-ca39-astoria-ca34-vincennes-ca44-war-damage-report-no29.html)).
- **Ventilation:** forced draught for boilers and ventilation of spaces. Ducts carry smoke and fire between compartments, and stopping the fans makes engine rooms (often over 120 °F on Iowa) and magazines uninhabitable or hot ([Naval Gazing — Iowa](https://www.navalgazing.net/Pictures-Iowa-Engine-Room)).
- **Evaporators and distillers** make boiler feed water and drinking water. Graf Spee lost her desalination plant ([Wikipedia](https://en.wikipedia.org/wiki/German_cruiser_Admiral_Graf_Spee)).
- **Refrigeration** cooled magazines (for propellant stability) as well as provisions ([Naval Gazing — Powder 3](https://www.navalgazing.net/Powder-Part-3)).
- **Capstans and anchor gear** are on the forecastle, at about 0.05–0.15 of length. Lion's capstan engine exhaust was the path for feed-water contamination ([Wikipedia — Lion](https://en.wikipedia.org/wiki/HMS_Lion_(1910))).

**MODEL NOTE — Auxiliaries**
- Collapse these into a few abstract nodes: **Pumps** (flooding-removal rate, needs power), **Fire Main** (firefighting rate, needs power, can itself rupture), **Ventilation** (fire and smoke spread, magazine temperature), and **Evaporators** (a campaign or endurance effect).
- Do not micro-model capstans and the like. Fold them into "forecastle hit" flavour, with a rare chance of a feed-water event.

---

## 10. Aviation on battleships and cruisers

- **Catapult types and locations:**
  - Types: powder catapults ("essentially a giant gun") were the worldwide standard; some compressed-air, hydraulic and electric.
  - Locations: turret-top (early RN), quarterdeck (USN battleships, about 0.9–1.0 of length), or amidships cross-deck with hangars (RN, German, Japanese; about 0.45–0.6).
  - The RN dropped battleship aviation by 1944; the USN kept it ([Naval Gazing — Battleship Aviation Part 2](https://www.navalgazing.net/Battleship-Aviation-Part-2)).
  - Bismarck had 4 Ar 196 and one double catapult ([Wikipedia](https://en.wikipedia.org/wiki/Bismarck-class_battleship)).
- **Hazards:** fuelled aircraft, avgas stowage and catapult charges.
  - At Savo Island, aircraft in hangars and on catapults "burned fiercely" and lit up the US cruisers for the Japanese gunners. Afterwards, captains were given discretion to fly off or jettison aircraft before action ([WDR 29](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-quincy-ca39-astoria-ca34-vincennes-ca44-war-damage-report-no29.html)).
  - PoW's first Denmark Strait hit, and Bismarck's hit on the boat and catapult area, struck aviation spaces ([Denmark Strait](https://en.wikipedia.org/wiki/Battle_of_the_Denmark_Strait)).
  - **Gasoline vapour** is a class of its own on carriers. Lexington was lost when sparks lit vapour from cracked avgas tanks ([Wikipedia](https://en.wikipedia.org/wiki/USS_Lexington_(CV-2))). Wasp had 3 vapour explosions ([NHHC Summary](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/summary-of-war-damage-17-oct-1941-to-7-dec-1942.html)).

**MODEL NOTE — Aviation**
- Floatplanes, hangar and avgas form a **topside fire bomb**. They give a spotting and scouting bonus before battle, and a high fire chance (plus a night illumination debuff on the own ship) once hit.
- Add a pre-battle "launch/jettison aircraft" choice.
- Avgas tanks below decks: a vapour-explosion chance when nearby compartments are damaged, rising over time if not purged.

---

## 11. Crew spaces, sickbay, galley, accommodation — fire load

- **Fuel for fire:** "Cork insulation, upholstered furniture, linoleum, and clothing not stored in metal lockers", paint, papers, cable insulation and wooden packing ([Naval Gazing — Survivability: Fire](https://www.navalgazing.net/Survivability-Fire)).
  - Paint builds up over time: a late-1970s British survey found up to 80 coats on some frigates.
  - Astoria's wardroom fire, fed by furnishings, paint and records, led to the magazine explosion. A ruptured kerosene tank spread fire over the well deck ([WDR 29](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-quincy-ca39-astoria-ca34-vincennes-ca44-war-damage-report-no29.html)).
  - Burning life jackets appear in South Dakota's report ([WDR 57](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-south-dakota-bb57-war-damage-report-no57.html)).
- **Wartime stripping:**
  - USN: "all linoleum was taken off the ships and all oil paints were put ashore… Paint was chipped off down to bare metal and later was replaced with latex or water paints" ([Wallin, *Pearl Harbor*, ch. 14](https://www.ibiblio.org/hyperwar/USN/Wallin/Wallin-14.html)).
  - USN also used fire-resistant paints, fireproof bedding stowage and glass-fibre curtains ([Naval Gazing — Fire](https://www.navalgazing.net/Survivability-Fire)).
  - Japan: Yamato's preparations for the last sortie included removing flammable materials ([Wikipedia — Yamato](https://en.wikipedia.org/wiki/Japanese_battleship_Yamato)).
  - **[UNCERTAIN]** German practice was not researched in depth here.
  - **Wooden decks** (teak or pine planking over steel, typical on RN, USN and German capital ships) add some fire load. **[UNCERTAIN: no quantified source found]**
- **Galley, bakery and sickbay:**
  - The galley is a fire source, and losing it hurts endurance and morale (Graf Spee).
  - The sickbay is the casualty-treatment node; it was often relocated to protected dressing stations in wartime. **[UNCERTAIN]**

**MODEL NOTE — Crew spaces**
- Each compartment carries a **fire load** attribute. Peacetime fit-out is high; "stripped for war" (a doctrine or year toggle, e.g. USN post-1942, IJN 1944–45) is low and costs morale in long campaigns.
- Accommodation spaces are mostly fire-spread conduits and crew-casualty zones, not combat-critical.
- A sickbay or dressing station node raises the conversion of wounded back to duty, or lowers wounded-to-dead.

---

## 12. Masts, searchlights, boats, booms — topside clutter

- **Masts:** pole, tripod (Dreadnought era, RN), pagoda (IJN rebuilds), tower (Bismarck, KGV, Nelson), lattice cage masts (USN until the 1940s rebuilds). Masts carry spotting tops, directors, radar, W/T aerials and signal halyards.
  - A mast hit can knock out several of those systems at once (Peresvet at the Yellow Sea).
  - Rigging stays fouled directors (removed after Savo).
- **Searchlights:** night-action essentials before radar. They are fragile, and switching them on reveals the ship's position. **[No specific damage data researched]**
- **Boats, booms and cranes:** Hood's boat-deck fire was among ready-use ammunition stored there. Boats feed fires (Savo: "ships' boats" listed among fire sources; [WDR 29](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-quincy-ca39-astoria-ca34-vincennes-ca44-war-damage-report-no29.html)). Splinter-riddled boats also mean no lifeboats for abandoning ship.
- **Superstructure as a "shell-catcher":** AP shells often pass through soft superstructure without detonating. South Dakota took 26 hits, "most… passed through structures without detonating" because of 0.4 s fuze delays ([WDR 57](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-south-dakota-bb57-war-damage-report-no57.html)). The damage was concentrated in cables, radar and exposed crews.

**MODEL NOTE — Topside**
- Represent topside as **soft area targets**. AP shells have an over-penetration chance (low damage, possible cable cut). HE shells cause splinter bursts over a radius that hit crew pools, radar, directors, boats, aircraft and ready-use ammunition.
- Mast health: if lost, everything mounted on it goes, including the spotting top, radar, W/T and halyards.
- Boats: abandon-ship survival modifier and fire fuel.

---

## 13. Summary table

Protection tiers: **A** = inside the citadel, under the armoured deck and belt; **B** = heavy local armour (turret, CT, barbette); **C** = splinter-proof (about 1–2 inches); **D** = none.

| Component | Typical location (frac. L / level) | Protection tier | Primary threat | Consequence of loss | Repair at sea? |
|---|---|---|---|---|---|
| Main magazine | under turrets, 0.15–0.35 & 0.65–0.85 / hold | A | Flash from turret, plunging shell or bomb, fire, torpedo + list | Ship lost (explosion); if flooded, that turret is out | No (flooding is a choice) |
| Shell room | adjacent to magazine | A | As above (less sensitive) | Turret starved | No |
| Secondary / AA magazine | wings or separate, often outboard | A–B (often weaker) | Fire, torpedo | Can chain to main magazine (Barham, Hood) | No |
| Ready-use ammunition | beside mounts / weather deck | D | Splinters, fire | Local fire and casualties | Replenish only |
| Deck torpedoes | amidships / upper deck | D–C | Shell, bomb, fire | Massive internal explosion (Mikuma) | Jettison pre-emptively |
| Depth charges | stern / weather deck | D | Fire, sinking | Kills survivors in the water | Set "safe" |
| Turret gunhouse | centreline | B | Penetration, joint hits | Turret out, flash chain | Sometimes (Scharnhorst's Bruno) |
| Barbette / roller path | centreline | B | Heavy hit, distortion | Turret jammed in train | Rarely, hours |
| Turret machinery / power | in barbette / remote pump rooms | A–B | Power loss, flooding | Slow hand operation or turret out | Yes if power restored |
| Gun barrel | turret | D (exposed) | Direct hit, burst | One gun out | No |
| Secondary casemate | hull side, main deck | C–B | Sea wash, splinters, cordite fire | Guns out; flooding entry | Partial |
| Open AA mount | upper decks | D–C (shield) | Splinters, strafing | Crew casualties | Yes (crew replacement) |
| Main director + rangefinder | foremast top, 0.25–0.35 | C–D | Any superstructure hit | Fall to after director or local control | Rarely |
| Radar antenna | mast tops | D | Splinters, blast | Night/poor-visibility degradation | Sometimes (spares) |
| Plot / transmitting station | deep, 0.3–0.6 | A | Flooding, power loss | Degraded solutions | Partial |
| Bridge / compass platform | forward superstructure | D–C | Any hit | Command delay, officer deaths | Shift to backup position |
| Conning tower | base of forward superstructure | B | Slits, spall | Usually unused; backup command | — |
| Radio room / aerials | superstructure | C–D | Splinters | No inter-ship orders | Jury-rig aerials |
| Signal halyards | masts | D | Splinters | No visual signals (Lion) | Yes, quickly |
| Boiler room | 0.35–0.55 / bottom | A | Torpedo, mine, plunging shell | Loss of steam → speed, power | Sometimes (Scharnhorst) |
| Engine room | 0.55–0.70 / bottom | A | Torpedo, flooding | Shaft(s) lost | Rarely |
| Shaft / shaft alley | 0.70–1.0 / bottom | D–A (varies) | Underwater hit aft | Speed loss, progressive flooding (PoW) | Stop the shaft |
| Propeller / strut | 0.85–1.0 / underwater | D | Torpedo, mine | Speed loss, vibration | No |
| Uptakes / funnels | above boiler rooms | C (gratings) | Shell, flooding | Draught loss, smoke | Partial |
| Fuel tanks / purifiers | sides, double bottom; purifiers in machinery spaces | A–C | Underwater hits, shell | Fire, slick, fuel cut off, unusable fuel (Graf Spee) | Partial (transfer) |
| Feed-water system | machinery spaces | A | Contamination from splinter or flood | Boilers die gradually (Lion) | Slow |
| Rudder | 0.95–1.0 / underwater | D | Aerial or ship torpedo, large shell | Jammed = circling; lost = steer by engines | Almost never |
| Steering gear room | 0.90–0.97 / lower decks | A–B (variable) | Flooding, power loss, shell | Hand steering or none | Sometimes |
| Generators | machinery spaces, plus diesels separate | A | Flooding of steam spaces | Cascade blackout | Yes if not flooded |
| Switchboards / ring main | below armour deck; cables everywhere | A (boards) / D (cables) | Flooding, cable cuts, arcing, shock | Blackout of segments (PoW, South Dakota) | Breaker resets; casualty power |
| Pumps / fire main | distributed | A–D | Power loss, rupture | No dewatering or firefighting | Partial |
| Ventilation | distributed | D–A | Hits, power loss | Smoke spread, heat | Partial |
| Evaporators | machinery spaces | A | Hits, flooding | Feed and drinking water loss (campaign) | Slow |
| Catapult / aircraft / avgas | amidships or stern / weather deck | D | Any hit | Fires, illumination (Savo) | Jettison |
| Accommodation / wardroom | everywhere above armour deck | D | Fire | Fire spread, magazine cook-off (Astoria) | Strip pre-war |
| Galley | superstructure / upper deck | D | Hits | Endurance and morale (Graf Spee) | Partial |
| Masts | centreline | D | Shell, splinters | Loss of everything mounted | Jury rig |
| Boats, booms, searchlights | upper deck | D | Splinters, fire | Fire fuel, lower survival on abandon | No |

---

## 14. Crew-casualty mechanisms

1. **Direct blast and penetration inside a compartment:** turret crews of about 70–80 wiped out per hit (Derfflinger C and D: 73 and 80 killed; [von Hase](https://www.wtj.com/archives/hase_03.htm)).
2. **Splinters / fragmentation:** the dominant topside killer for bridges, AA crews and open stations (South Dakota 38 killed and 60 wounded with no armour penetrated; PoW's compass platform). Armour spall from behind the plate (Tiger's turret roof; [USNI 1925](https://www.usni.org/magazines/proceedings/1925/april/lessons-jutland-affecting-design-turret-armor)).
3. **Propellant flash fire:** cordite and powder fires in turrets and handling rooms (Seydlitz: 159 dead; Lion's handling rooms).
4. **Magazine detonation:** whole-ship loss; survivors in single digits (Hood 3/1,418; Indefatigable 2/1,019; Arizona 1,177 killed).
5. **Burns from steam:** ruptured main steam lines in boiler and engine rooms (pressures from 250 psi in 1906 upwards).
6. **Smoke and toxic gases:** CO and toxic combustion gases (Iowa 1989: cyanide from foam; Derfflinger's CT gassed). Ventilation spreads them.
7. **Drowning by flooding:** trapped crews in flooded machinery spaces and below-deck compartments (Marlborough's diesel room: 2 stokers killed instantly), and engine-room crews on capsizing ships.
8. **Capsize and sinking speed:** fast capsizes (Barham about 4 min; Hood about 3 min) trap most of the crew. Slow losses (Ark Royal about 14 h) save almost all.
9. **Strafing and air attack:** open AA crews (Yamato's 25 mm crews).
10. **In the water after sinking:**
    - Depth charges detonating (Strong).
    - Oil fires on the water.
    - Exposure: water temperature decides survival (North Cape: 36 of 1,968 survived; [Wikipedia](https://en.wikipedia.org/wiki/Battle_of_the_North_Cape)).
    - Rescue interrupted: Blücher's rescuers were driven off by a Zeppelin bombing them ([Wikipedia](https://en.wikipedia.org/wiki/SMS_Bl%C3%BCcher)).
11. **Heat stroke:** extreme engine-room heat (Iowa above 120 °F) when ventilation is lost.
12. **Secondary ammunition cook-off:** ready-use clips exploding among the wounded (South Dakota's 1.1-inch clips).
13. **Self-inflicted / accident:** own-gun blast, in-bore explosions (Iowa 1989), unstable propellant (Liberté, Iéna, Mutsu).

**MODEL NOTE — Crew**
- Give each compartment a crew count. Hits kill a fraction that depends on mechanism: penetration-burst high, splinters medium at open stations, fire over time, flooding killing trapped crew if the space floods faster than a threshold.
- Crew are a **repair and damage-control resource** too. Losing damage-control parties (Lexington's main damage-control station was destroyed by an explosion) should reduce the fire-fighting and flooding-control rate.
- Abandon-ship survival = f(time to sink, sea temperature, boats remaining, enemy presence).

---

## 15. Source list (primary pages consulted)

**Navy reports and manuals**
- NHHC War Damage Reports:
  - [South Dakota WDR 57](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-south-dakota-bb57-war-damage-report-no57.html)
  - [Savo cruisers WDR 29](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/uss-quincy-ca39-astoria-ca34-vincennes-ca44-war-damage-report-no29.html)
  - [Summary of War Damage 1941–42](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/summary-of-war-damage-17-oct-1941-to-7-dec-1942.html)
  - [Destroyer Report — Torpedo & Mine](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/w/war-damage-reports/destroyer-report-torpedo-mine-damage.html)
- [NSTM ch. 320 (electric power distribution)](https://maritime.org/doc/nstm/ch320.pdf)

**Technical articles**
- [Death of a Battleship (PoW, 2012 update)](https://pacificwrecks.com/ship/hms/prince-of-wales/death-of-a-battleship-2012-update.pdf)
- NavWeaps: [Propellants](https://www.navweaps.com/index_tech/tech-100.php), [KGV 14in quad turret](https://www.navweaps.com/index_tech/tech-122.php)
- Naval Gazing: [Mission Kills](https://www.navalgazing.net/Survivability-Mission-Kills), [Fire](https://www.navalgazing.net/Survivability-Fire), [Powder 3](https://www.navalgazing.net/Powder-Part-3), [Fire Control 2](https://www.navalgazing.net/Fire-Control-Part-2), [Propulsion 2](https://www.navalgazing.net/Engineering-Part-2), [Iowa engine room](https://www.navalgazing.net/Pictures-Iowa-Engine-Room), [Battleship Aviation 2](https://www.navalgazing.net/Battleship-Aviation-Part-2)
- [USNI Proceedings 1925 — Lessons of Jutland affecting turret armor](https://www.usni.org/magazines/proceedings/1925/april/lessons-jutland-affecting-design-turret-armor)

**First-hand accounts and specialist sites**
- [von Hase — Derfflinger at Jutland](https://www.wtj.com/archives/hase_03.htm)
- [HMS Hood Association — Fire Control](https://www.hmshood.org.uk/ship/fire_control.htm)
- [Dreadnought Project — Marlborough at Jutland](https://www.dreadnoughtproject.org/tfs/index.php/H.M.S._Marlborough_at_the_Battle_of_Jutland)
- [Dreadnought Project — A Direct Train of Cordite](https://dreadnoughtproject.org/tfs/index.php/A_Direct_Train_of_Cordite)
- [Wallin — Pearl Harbor salvage, ch. 14](https://www.ibiblio.org/hyperwar/USN/Wallin/Wallin-14.html)

**Wikipedia (individual ship and battle articles)**
- Cited inline throughout.

**Not reached:** ibiblio/hyperwar HTML versions of the war damage reports and gwpda.org were unreachable from this environment (redirect and egress blocks). The NHHC mirrors were used instead.
