# Powerplant Model v2: hand-off spec

**Replaces:** `L_mach = 0.14 * sqrt(shp)`, which ignored beam, depth and technology.
**Goal:** machinery length, weight, fuel use and crew that depend on available width, available height, tech family and tech maturity. Incremental research improves a tech. Step changes come from moving to a new tech.

> **Design-freedom rule.** Nothing in this model depends on ship type, role or size. Every parameter is a property of the plant or a design choice made on the plant. Historical practice ("destroyers ran plants hard", "petrol only in small boats") appears only as **presets and AI defaults**, never as a constraint. A battleship can carry a destroyer-style plant, and a destroyer can carry a conservative one. The trade-offs come from the plant itself.

> **Data honesty.** The *Anchors* (§8) are sourced. Every number in the tech tables is an **estimate fitted to those anchors**, chosen to be plausible and to keep the ordering right. Treat them as tuning defaults, not historical truth.

---

## 1. Units & conventions

- Store **shaft power in kW** internally. 1 shp = 0.7457 kW.
- Reciprocating engines were rated in **ihp**. Shaft power = ihp × η_mech, with η_mech = 0.85–0.92. If you want to show ihp for period flavour, display `ihp = P_s / 0.88`.
- **Weight** is the whole propulsion plant: boilers with water, engines/turbines, gearing, condensers, shafting, propellers and propulsion auxiliaries. It **excludes fuel**. 1 lb/shp = 0.608 kg/kW.
- **Fuel use:** compare techs on **SEC (MJ per kWh)**, because fuels differ. Fuel mass = SEC / LHV.

| fuel | LHV MJ/kg | stowage m³/t | notes |
|---|---|---|---|
| coal (good steam coal) | 30 (Welsh up to ~33) | 1.30 | Bunkers only (no double bottom). Wing bunkers give splinter/flood protection. |
| furnace/bunker oil | 41 | 1.07 | Can use double bottom and TDS liquid layers. |
| diesel / distillate | 42.8 | 1.19 | |
| petrol | 44 | 1.37 | Vapour explosion risk; small craft only. |

---

## 2. Core model

```
inputs:  tech, m (maturity 0..1), s (design stress 0=conservative .. 1=max stress),
         P_s (kW), n_shafts, units_per_shaft, firing (coal/mixed/oil, steam only),
         transmission (direct/geared/electric), W_avail (m), H_avail (m), arrangement flags

lerp_m(a,b)  = a + (b-a) * (1 - (1-m)^2)        # ease-out: early research pays most
P_unit       = P_s / (n_shafts * units_per_shaft)       # must be <= unit_max(tech,m)

w_spec       = lerp_m(w_intro, w_mature) * stress_mult(s) * variant_mult * firing_mult * trans_mult   # kg/kW
stress_mult  = 1 - (1 - stress_floor) * s             # per-tech stress_floor (table)
W_plant (t)  = P_s * w_spec / 1000

rho          = rho_base * (0.85 + 0.15*s)              # conservative plants have bigger margins and access space
V_gross (m³) = W_plant / rho                           # gross machinery-space box volume

# geometry: unit size scales with cube root of unit power
s   = (P_unit / P_ref)^(1/3)
h_u = h_ref*s ; w_u = w_ref*s ; l_u = l_ref*s

# HEIGHT
if H_avail < h_u:  protrusion = h_u - H_avail   # see §6. Either infeasible, or the plant pokes
                                                # through the deck and needs a casing/glacis
H_eff = min(H_avail, h_u + 2.5)                 # one aux flat above the units is useful; more
                                                # height gives no further shortening

# WIDTH (quantized: units sit abreast in rows)
pitch = w_u + 0.8                               # unit + side aisle
W_side = centreline_bulkhead ? W_avail/2 : W_avail
rows  = floor(W_side / pitch)                   # rows==0 -> infeasible (hull too narrow)
used  = rows * pitch
W_eff = (used + 0.5*(W_side - used)) * (centreline_bulkhead ? 2 : 1)   # leftover width is half-useful (aux)

L = V_gross / (W_eff * H_eff)
L *= unit_system ? 1.10 : 1.0                   # alternating boiler/engine rooms
L = max(L, l_u + 2.0)                           # cannot be shorter than one unit
split: boiler_rooms = L * boiler_frac ; engine_rooms = L * (1 - boiler_frac)
```

**Defining W_avail and H_avail** (the generator supplies these):

- **W_avail** = beam at the machinery space, minus TDS/side-protection depth on both sides, minus wing bunker width if the design has `wing_bunkers` on.
  - `wing_bunkers` is a design flag, not something coal firing forces. Coal stowed in wing bunkers (typically 1.5–3 m per side) costs width but gives splinter and flood protection.
  - Coal stowed fore and aft of the machinery instead costs length.
- **H_avail** = height from the inner bottom to the deck that bounds machinery (the armoured deck if there is one, otherwise the main deck).

**Expected behaviour:** wide, deep hulls get short machinery spaces. Narrow hulls can drop a row, which causes a step jump in length. A shallow hull plus a tall plant gives protrusion. Old techs are huge.

Worked checks, computed with the defaults:

| case | inputs | new model | old formula |
|---|---|---|---|
| Fletcher | ST7 m=1, s=1, 44.7 MW, 2 shafts, W 11 m, H 6 m | **34 m** | 34 m |
| KGV-like | ST7 m=1, s=0, 82 MW, 4 shafts, W 23 m (inside TDS), H 9.5 m | **64 m** | 46 m |
| 1895 pre-dreadnought | ST3 m=1, s=0, 6.6 MW, 2 shafts, W 17 m (inside wing bunkers), H 8 m | **36 m** | 13 m |

The pre-dreadnought gap is the point of the change. The KGV case runs long. Raise ST7 `rho_base` to about 0.40, or give the battleship s ≈ 0.3, if you want it closer to 46 m.

**Calibration knob:** tune `rho_base` per tech so the 1935–45 cases land within ±20 % of the old formula. Earlier techs should come out *longer*.

---

## 3. Tech data

`sfc` is in g/kWh at the rated point (intro → mature); SEC = sfc × LHV / 1000. `w` is kg/kW at the **conservative** design point (s = 0). `stress_floor` is the weight multiplier at maximum stress (s = 1): how far this technology can physically be pushed. `unit_max` is MW per prime-mover unit (per engine, or per turbine set on a shaft). `h/w/l_ref` are metres at `P_ref` MW. `crew_k`: engineering crew ≈ `crew_k * P_MW^0.75`. `start` = cold start to full power, in hours. `curve` = part-load curve (§4).

```yaml
# ---------- STEAM (lineage ST; each step dominates the previous on its headline stats) ----------
ST1: {name: "Simple expansion, low-pressure box boilers", years: [1840, 1865], psi: [5, 30],
      fuel: coal, sfc: [3300, 2300], w: [340, 280], stress_floor: 0.85, rho_base: 0.22,
      unit_max: [1, 3], P_ref: 2, h_ref: 4.0, w_ref: 4.5, l_ref: 6, boiler_frac: 0.6,
      crew_k: 42, start: 4, curve: REC,
      note: "Horizontal engines keep below waterline (h_ref). Vertical option: h*1.6, w*0.6."}
ST2: {name: "Compound + cylindrical (Scotch) boilers", years: [1865, 1885], psi: [60, 100],
      fuel: coal, sfc: [1800, 1350], w: [260, 200], stress_floor: 0.75, rho_base: 0.24,
      unit_max: [2, 5], P_ref: 3, h_ref: 5.5, w_ref: 4.5, l_ref: 6, boiler_frac: 0.6,
      crew_k: 40, start: 8, curve: REC,
      variants: {loco_boiler: {from: 1875, w_mult: 0.6, unit_max: 1.5, reliability: 0.85, note: "locomotive-type fire-tube boilers: light, priming-prone, short life"}}}
ST3: {name: "Triple expansion + Scotch boilers", years: [1885, 1900], psi: [150, 200],
      fuel: coal, sfc: [1250, 1050], w: [190, 150], stress_floor: 0.75, rho_base: 0.26,
      unit_max: [4, 9], P_ref: 5, h_ref: 7.5, w_ref: 4.5, l_ref: 9, boiler_frac: 0.6,
      crew_k: 38, start: 8, curve: REC,
      variants: {loco_boiler: {from: 1885, w_mult: 0.6, unit_max: 2, reliability: 0.85}},
      note: "Tall vertical engines: classic protrusion through protective deck. Still buildable long after 1900."}
ST4: {name: "Triple/quad expansion + water-tube boilers", years: [1893, 1910], psi: [250, 300],
      fuel: coal, sfc: [1050, 930], w: [150, 115], stress_floor: 0.45, rho_base: 0.28,
      unit_max: [6, 12], P_ref: 5, h_ref: 7.5, w_ref: 4.5, l_ref: 9, boiler_frac: 0.55,
      crew_k: 34, start: 2, curve: REC,
      variants: {quad_expansion: {sfc_mult: 0.92, w_mult: 1.05, l_mult: 1.2, vibration: low},
                 express_boilers: {w_mult: 0.6, h_mult: 0.85, reliability: 0.9,
                   note: "small-tube Yarrow/Thornycroft/Normand. At s=1 this is the 30-knotter TBD plant (~31 kg/kW)."}},
      note: "Default boilers are large-tube (Belleville/Niclausse/B&W)."}
ST5: {name: "Direct-drive steam turbines + water-tube", years: [1905, 1918], psi: [200, 280],
      fuel: [coal, mixed, oil], sfc: [950, 800], w: [120, 95], stress_floor: 0.35, rho_base: 0.30,
      unit_max: [8, 20], P_ref: 10, h_ref: 4.5, w_ref: 4.5, l_ref: 7, boiler_frac: 0.6,
      crew_k: 30, start: 3, curve: DT,
      options: {cruising_turbines: {w_mult: 1.05, curve: GTB}},
      note: "Headline: low height, high unit power, sustained speed. Poor cruise economy without cruising turbines."}
ST6: {name: "Geared turbines + oil-fired small-tube boilers", years: [1915, 1930], psi: [250, 300],
      fuel: oil, sfc: [520, 430], w: [75, 52], stress_floor: 0.42, rho_base: 0.32,
      unit_max: [15, 35], P_ref: 15, h_ref: 4.5, w_ref: 4.5, l_ref: 8, boiler_frac: 0.55,
      crew_k: 12, start: 2, curve: GTB}
ST7: {name: "High-pressure superheated geared turbines", years: [1930, 1945], psi: [400, 650],
      fuel: oil, sfc: [420, 340], w: [45, 34], stress_floor: 0.5, rho_base: 0.34,
      unit_max: [25, 45], P_ref: 30, h_ref: 5.0, w_ref: 5.0, l_ref: 8, boiler_frac: 0.5,
      crew_k: 10, start: 1.5, curve: GTB,
      note: "700-850 F superheat, economisers, air heaters. Fletcher/KGV/Iowa generation."}
ST8: {name: "Very-high-pressure steam (1200 psi / 950 F)", years: [1937, 1965], psi: [850, 1200],
      fuel: oil, sfc: [340, 300], w: [34, 26], stress_floor: 0.55, rho_base: 0.36,
      unit_max: [40, 55], P_ref: 40, h_ref: 5.0, w_ref: 5.0, l_ref: 8, boiler_frac: 0.45,
      crew_k: 9, start: 1.5, curve: GTB,
      note: "1937 intro = German Wagner/Benson-type plants (bad reliability at m~0). US mature 1950s-60s."}

# ---------- RECIPROCATING INTERNAL COMBUSTION ----------
PE1: {name: "Petrol (gasoline) engines, small craft", years: [1905, 1945], fuel: petrol,
      sfc: [340, 290], w: [8.5, 6.5], stress_floor: 0.7, rho_base: 0.40, unit_max: [0.2, 1.1],
      P_ref: 1, h_ref: 1.2, w_ref: 1.1, l_ref: 2.5, crew_k: 3, start: 0.1, curve: DSL,
      note: "CMB/MTB/PT-boat engines. Small unit_max means many units for big power. Petrol vapour risk (§5) scales with fuel carried; no size ban."}
DI1: {name: "Early marine diesel (4-stroke, unsupercharged)", years: [1910, 1925], fuel: diesel,
      sfc: [270, 240], w: [140, 100], stress_floor: 0.6, rho_base: 0.42, unit_max: [0.4, 2],
      P_ref: 1, h_ref: 4.5, w_ref: 2.5, l_ref: 7, crew_k: 6, start: 0.5, curve: DSL,
      note: "s=1 end = submarine-style lightweight engines. Low reliability at intro."}
DI2: {name: "Medium-speed lightweight 2-stroke (MAN double-acting)", years: [1928, 1945],
      fuel: diesel, sfc: [250, 230], w: [50, 38], stress_floor: 0.75, rho_base: 0.42,
      unit_max: [3, 7], P_ref: 5, h_ref: 4.5, w_ref: 3.5, l_ref: 10, crew_k: 5, start: 0.5,
      curve: DSL, note: "Deutschland-class plant. Loud and vibrating (sonar penalty), long range."}
DI3: {name: "Lightweight high-speed diesel (E-boat)", years: [1933, 1945], fuel: diesel,
      sfc: [245, 230], w: [14, 11.5], stress_floor: 0.7, rho_base: 0.45, unit_max: [0.9, 2.2],
      P_ref: 1.5, h_ref: 1.8, w_ref: 1.6, l_ref: 4, crew_k: 3, start: 0.2, curve: DSL,
      note: "E-boat practice = s≈1 (MB 501: 1,500 hp continuous / 2,000 hp max). Short overhaul intervals at high s."}
DI4: {name: "Post-war high-speed turbocharged (Deltic class)", years: [1950, 1970], fuel: diesel,
      sfc: [235, 220], w: [11.5, 9.3], stress_floor: 0.7, rho_base: 0.45, unit_max: [1.5, 3],
      P_ref: 2.5, h_ref: 2.0, w_ref: 2.0, l_ref: 3.5, crew_k: 3, start: 0.2, curve: DSL,
      note: "Aluminium variants give a low magnetic signature (MCM bonus)."}
DI5: {name: "Modern medium-speed diesel", years: [1965, 2010], fuel: diesel, sfc: [215, 185],
      w: [30, 20], stress_floor: 0.8, rho_base: 0.42, unit_max: [3, 12], P_ref: 6, h_ref: 4.0,
      w_ref: 3.0, l_ref: 7, crew_k: 3, start: 0.3, curve: DSL, note: "Reliable; CODAD/CODOG cruise plant."}
DI6: {name: "Modern high-speed diesel (MTU-class)", years: [1980, 2020], fuel: diesel,
      sfc: [225, 200], w: [17, 11.5], stress_floor: 0.7, rho_base: 0.45, unit_max: [3, 10], P_ref: 5,
      h_ref: 2.6, w_ref: 2.0, l_ref: 5, crew_k: 2.5, start: 0.2, curve: DSL,
      note: "MTU publishes the same engine at several load-factor ratings (e.g. 16V1163 M74 'high load factor' vs M94 'low load factor'). That is exactly the s slider."}
DIS: {name: "Slow-speed 2-stroke crosshead (merchant)", years: [1912, 2010], fuel: diesel,
      sfc: [230, 165], w: [150, 60], stress_floor: 0.9, rho_base: 0.40, unit_max: [2, 60],
      P_ref: 10, h_ref: 9, w_ref: 6, l_ref: 15, crew_k: 3, start: 0.5, curve: DSL,
      note: "Direct drive, no gearbox. Very tall and heavy, but the most fuel-efficient option."}

# ---------- GAS TURBINES ----------
GT1: {name: "Early naval gas turbine (boost)", years: [1947, 1962], fuel: diesel, sfc: [520, 400],
      w: [16.5, 13], stress_floor: 0.85, rho_base: 0.22, unit_max: [1.8, 3.5], P_ref: 3, h_ref: 1.5,
      w_ref: 1.5, l_ref: 4, crew_k: 3, start: 0.1, curve: GTS, life_hours: low,
      note: "MGB 2009 / Brave class era. Short life and poor SFC make it a boost engine in practice; nothing forbids cruising on it."}
GT2: {name: "First-gen marinised aero GT (Olympus/Tyne)", years: [1962, 1978], fuel: diesel,
      sfc: [330, 285], w: [19, 14], stress_floor: 0.85, rho_base: 0.22, unit_max: [4, 21], P_ref: 20,
      h_ref: 3.2, w_ref: 2.8, l_ref: 8, crew_k: 2.5, start: 0.25, curve: GTS}
GT3: {name: "High-pressure-ratio aeroderivative (LM2500/Spey)", years: [1970, 1995], fuel: diesel,
      sfc: [250, 225], w: [15, 12], stress_floor: 0.85, rho_base: 0.22, unit_max: [15, 25], P_ref: 25,
      h_ref: 3.2, w_ref: 3.0, l_ref: 8, crew_k: 2, start: 0.2, curve: GTS}
GT4: {name: "Modern simple-cycle (LM2500+G4/MT30)", years: [1995, 2025], fuel: diesel,
      sfc: [220, 205], w: [12, 9.5], stress_floor: 0.85, rho_base: 0.23, unit_max: [25, 40], P_ref: 36,
      h_ref: 3.5, w_ref: 3.2, l_ref: 8.5, crew_k: 1.5, start: 0.2, curve: GTS}
GT5: {name: "Intercooled-recuperated GT (WR-21)", years: [2000, 2025], fuel: diesel,
      sfc: [200, 188], w: [14, 11], stress_floor: 0.85, rho_base: 0.21, unit_max: [21, 25], P_ref: 25,
      h_ref: 4.5, w_ref: 4.0, l_ref: 9, crew_k: 1.5, start: 0.5, curve: ICR,
      note: "Flat part-load (~30% less fuel over a typical profile). Reliability penalty at m<0.5."}
```

**Funnels, uptakes and intakes** are covered in §6b.

---

## 4. Part-load SFC multipliers

Interpolate on the **per-unit** load fraction f. If the plant has several units, the game should shut units down so that the running ones sit near their best point. That rule is what makes CODOG/CODAD and "cruise on one engine" emerge naturally. Steam plants share boilers and turbines on a shaft, so apply their curve to plant load.

| curve | f=0.10 | 0.25 | 0.50 | 0.75 | 1.00 | above 1.00 (overload, §5) |
|---|---|---|---|---|---|---|
| REC (reciprocating steam) | 1.45 | 1.20 | 1.07 | 1.02 | 1.00 | +0.5 per 0.1 overload |
| DT (direct turbine) | 2.60 | 1.90 | 1.40 | 1.12 | 1.00 | +0.3 per 0.1 |
| GTB (geared steam turbine) | 1.90 | 1.45 | 1.18 | 1.05 | 1.00 | +0.3 per 0.1 |
| DSL (any diesel/petrol) | 1.25 | 1.10 | 1.03 | 1.00 | 1.01 | +0.4 per 0.1 |
| GTS (simple-cycle GT) | 2.80 | 1.85 | 1.35 | 1.12 | 1.00 | +0.2 per 0.1 |
| ICR | 1.35 | 1.12 | 1.03 | 1.00 | 1.00 | +0.2 per 0.1 |

These are SFC multipliers. "+0.5 per 0.1" means that at f = 1.1 the REC multiplier is 1.05.

Power scales roughly as v³, so cruising at half speed is f ≈ 0.125. That is why direct-turbine destroyers had poor range.

---

## 5. Modifiers

**Design stress s (0 conservative … 1 max stress).** This is chosen per plant design, on any ship.

What it physically represents:

- boiler forcing rate (steam produced per m² of heating surface);
- shaft rpm;
- casing and scantling thickness;
- margins and design life;
- for diesels and gas turbines, the manufacturer's rating class.

Effects:

| effect | formula |
|---|---|
| weight | × `1 - (1 - stress_floor)·s` |
| gross density | `rho` rises with s (less access space) |
| SEC at rated power | × (1 + 0.08·s) (hard-forced boilers and engines run less efficiently) |
| continuous rating | `P_cont = P_rated · (1 - 0.15·s)`. Above P_cont, accumulate wear (below). |
| overload headroom | `ovl_max = 1 + 0.15·(1 - s)`. A conservative plant can be pushed to ~115 % in emergencies. A max-stress plant has none. |
| reliability, overhaul interval | see the reliability formula |
| shock / damage tolerance | component HP × (1.2 - 0.4·s) |

Presets (AI and quick-design only, not rules): torpedo boats and destroyers s ≈ 0.8–1, cruisers ≈ 0.5, capital ships and merchants ≈ 0–0.2. Historical exception: fast battleships and battlecruisers often sat nearer 0.4–0.6.

**Operational overload ("drive her hard").** This is separate from design stress. It is a captain's order during play.

- Allowed up to `f = ovl_max`.
- Wear accumulates while running above P_cont: `wear += dt · ((f·P_rated - P_cont)/P_rated)² · k_wear · (0.5 + s)`.
- When wear crosses a threshold, roll for a breakdown: a boiler, turbine or gearbox casualty.
- Historically, ships often beat their rated power on trials (Lexington: 202,000 shp against 180,000 rated).

**Petrol vapour risk.** This is a property of the fuel, not the hull. Each hit or fire event in a compartment holding petrol tanks or petrol engines rolls for vapour explosion, with chance ∝ petrol tonnage in that compartment. A big petrol-engined ship is legal, just dangerous.

**Firing (steam):**

- **coal:** ST1–ST5 default. Weight ×1.0, crew ×1.0. Sustained full power decays (dirty fires and stoker fatigue): −10 % power after ~6 h unless fires are cleaned. Smoke signature is high.
- **mixed** (1905+): weight ×0.97. Crew ×0.85.
- **oil** (ST5 from 1910, required ST6+): weight ×0.9 relative to coal for the same boiler. SEC ×0.97. Crew ×0.45 relative to coal. No full-power decay. Fuel mass ×0.73 for the same energy.
- **Coal on ST6+:** allowed for anyone. Weight ×1.15, SEC ×1.05, crew ×2.2, full-power decay applies.

**Transmission:**

These are physical, not policy:

- **direct:** ST1–ST5 and DIS. These run at propeller rpm.
- **geared:** required for, and already included in the weights of, ST6+, DI1–DI6, PE1 and GT*. Their rpm is too high for direct drive.
- **electric** (turbo-/diesel-/GT-electric; 1912+, modern IEP from 1990):
  - Weight ×1.3 for 1912–1950, ×1.15 for modern plants. SEC ×1.06 at full power.
  - Generator rooms do not need to sit in line with the shafts. They can be placed anywhere, and the motor room goes aft, which gives shorter shafts and freer subdivision.
  - Part load is better because whole gen-sets shut down.
  - **Flooding of the switchboard or motor room can drop all propulsion** (Saratoga 1942). Model this as a component.
- **combining gearbox** (CODOG/COGAG etc.): +6 % plant weight for "OR" plants, +12 % for "AND".

**Combined plants:**

- Cruise sub-plant A + boost sub-plant B. Weight = A + B + gearbox. Volume = (V_A + V_B) × 0.95.
- **OR** (CODOG, COGOG): top power = max(A, B).
- **AND** (CODAG, COGAG, COSAG, CODAD): top power = A + B.
- Earliest years: COSAG 1958, CODAG 1961, CODOG 1962, COGOG 1972, CODLAG 1990.

**Arrangement:**

- **Unit system** (alternating boiler and engine rooms, 1937+ in the USN): L ×1.10. One hit no longer stops the ship.
- **Centreline bulkhead:** rows are computed per side. It creates the asymmetric-flooding trade-off from `01_capital_subdivision.md`.

**Reliability / overhaul** (feed into breakdown and repair):

```
reliability     = lerp(0.6, 0.95, m) * (1.0 - 0.15*s) * tech_rel * variant_rel
overhaul_hours  = base_overhaul(tech) * (1.0 - 0.6*s)
```

`tech_rel` is 0.85 for ST8 at m < 0.5, for GT5, and for DI1. It is 1.0 otherwise.

---

## 6. Height & protrusion (makes H matter)

- If `h_u > H_avail`, the plant protrudes. Choose one of:
  - (a) Disallow.
  - (b) Allow, add an armoured casing or glacis over the protrusion, and treat the protrusion as an above-deck hit location. This is historical for ST3/ST4 vertical engines poking through protective decks.
- A tall-plant tech pushes the generator toward a deeper hull or a higher armoured deck. That raises the belt and costs weight. This is the main lever by which old tech makes the whole ship worse, not just the machinery.
- Turbines (ST5+) are the first steam plants that sit comfortably low. That is a real historical reason they won besides power.

---

## 6b. Funnels, uptakes & draught (why early centreline battleships are hard)

The mechanism, in one line: early plants make a lot of slow, hot gas per MW. Natural draught can only move it slowly. Uptakes can't be bent far without killing the draught. So you get several big, tall funnels sitting directly over spread-out boiler rooms, and they eat the centreline that turrets want. Better firing, forced draught and lower gas temperature shrink every one of those factors.

### Draught systems (a plant option, gated by year)

| id | name | available | funnel gas velocity `v` | trunk reach `R` (m), intro → mature | notes |
|---|---|---|---|---|---|
| NAT | natural draught | always | from stack height (below) | 4 → 6 | Only option for ST1, and for ST2 before 1880. |
| FDB | forced draught, boost only (closed stokehold) | 1880 | 7 → 9 m/s | 7 → 9 | Before ~1900, continuous power is limited to `nat_frac`. Running above that counts as overload wear (§5). |
| FDC | forced draught, continuous | 1900 (coal), 1905 (oil) | coal 8 → 10, oil 10 → 14 | coal 8 → 10, oil 12 → 20 | Standard from about 1905. |
| FDA | forced draught + air heaters/economisers | with ST7/ST8 | 12 → 15 | 20 → 30 | Cooler gas, so lower `q_gas` (already in the table below). |
| PF | pressure-fired / supercharged boiler | 1955 (Velox-type experiments 1935) | 18 → 22 | 30 | Boiler block weight ×0.85. Reliability ×0.9 at m < 0.5. |
| EXH-D | diesel exhaust | with diesel | 30–40 (pipe) | 60 | Pressurised, so it can be routed anywhere, including side or transom exhaust with **no funnel at all**. |
| EXH-G | gas turbine intake + exhaust | with GT | 30 (exhaust), 15 (intake) | 30 | Big ducts. Intake area is about 0.15 m²/MW extra and needs demisters and silencers. |

`nat_frac` is the fraction of rated power sustainable on natural draught. HMS Victoria (1887) made 7,500 hp natural and 14,000 hp forced.

| tech | nat_frac |
|---|---|
| ST2 | 0.55 |
| ST3 | 0.6 |
| ST4 | 0.7 |
| ST5 coal | 0.8 |

### Gas flow

```
q_gas (m³/s per MW, at funnel exit) = (sfc/3600) * (1 + AFR) / (353 / T_gas)
```

| firing / draught | AFR (kg air/kg fuel) | T_gas (K) |
|---|---|---|
| coal, natural | 20 | 620 |
| coal, forced | 16 | 600 |
| oil, forced | 15 | 570 |
| oil, forced + air heaters (ST7+) | 15 | 450 |
| diesel | 38 | 620 |
| gas turbine | 55 | 780 |

Resulting `q_gas` at mature sfc, in m³/s per MW:

| plant | q_gas |
|---|---|
| ST1 | 23.6 |
| ST2 | 13.8 |
| ST3 (natural) | 10.8 |
| ST3 (forced) | 8.4 |
| ST4 | 7.5 |
| ST5 coal | 6.4 |
| ST5 oil | 4.2 |
| ST6 | 3.1 |
| ST7 | 1.9 |
| ST8 | 1.7 |
| DI5 | 3.5 |
| GT4 | 7.0 (but small pipes, since v is high) |

### Natural-draught velocity (this is what makes funnel *height* matter)

```
H_stack = (H_avail - 1.0) + deck_to_funnel_base + H_f          # grate -> funnel top, metres
v_nat   = 0.3 * sqrt(2 * 9.81 * H_stack * (1 - 288 / T_gas)) * max(0.5, 1 - 0.02 * trunk_len)
```

This gives roughly 3.8 / 4.3 / 4.9 / 5.3 / 5.8 m/s at H_stack 15 / 20 / 25 / 30 / 35 m. Tall Victorian funnels weren't style; they were draught. Every metre of horizontal trunking costs 2 % of v.

### Required funnel area and count

```
A_req = max( P_rated * q_gas(forced) / v_forced ,          # full power on fans (if forced draught is fitted)
             P_rated * nat_frac * q_gas(nat) / v_nat )      # continuous steaming on natural draught (pre-FDC)
        # pure NAT plant: A_req = P_rated * q_gas(nat) / v_nat

# single-funnel size limit (structure, wind load, deck space)
w_f_max = min(0.22 * B_deck, 7.0) ; l_f_max = 1.5 * w_f_max
A_f_max = 0.785 * w_f_max * l_f_max
n_area  = ceil(A_req / A_f_max)

# uptake reach: each funnel can only collect boilers within ±R of its base
span    = 2*R + l_f
n_reach = sum over boiler groups g of ceil(L_boiler_g / span)
          # A boiler group is a run of boiler rooms not split by an engine room. Two groups share a
          # funnel only if the gap between them (the engine room length) is <= 2R - l_f.

n_funnels = max(n_area, n_reach, 1)      # diesel or GT may be 0 (side/transom exhaust)
# the player may add more (redundancy, or dummies for silhouette); never fewer
```

**Placement:** each funnel's base lies within ±R of the centroid of the boilers it serves. Trunking further than about 0.5 R costs:

- weight: `0.18 t × perimeter × trunk_len`;
- volume taken from the deck above the boiler rooms;
- the v_nat penalty above (natural draught only).

### Costs & conflicts

- **Deck footprint:** each funnel blocks `l_f + 2 m` of centreline. Centreline barbettes cannot overlap it. Funnels are arc obstacles up to height `H_f` for the gun-arc system. **This is the battleship lever:** three or four funnels spread over a long boiler block leave no room for superfiring centreline turrets amidships. Designers then go to wing turrets (Dreadnought, Nassau) or echelon layouts (Neptune, Colossus).
- **Weight and topweight:**
  - funnel `W_f = 0.12 t × perimeter × H_f`, with its centre of gravity at mid-height above the base;
  - uptakes `0.18 t × perimeter × (vertical + 1.5 × horizontal length)`;
  - armoured gratings where uptakes pierce an armoured deck, about 0.6 t/m² × A_req (estimate).
- **Smoke:** any manned control position (bridge, spotting top, director) aft of a funnel inside the cone `d_aft < k_smoke·sqrt(P_MW·q_gas)` and below `funnel_top + 0.3·d_aft` gets a visibility and accuracy penalty.
  - k_smoke values: coal-NAT 4, coal-FD 3, oil 1.5, oil-FDA 1, diesel 0.5, GT 0.3. Gas turbines get an IR-signature penalty instead.
  - Historical examples: Colossus's spotting top sat behind the fore funnel, which took 12 of 18 boilers; Nagato's bridge was smoked out until the 1930s rebuild removed the fore funnel.
- **Power cap:** `P_max_draught = Σ(A_eff × v_eff) / q_gas`. Undersized or damaged funnels limit speed.

### Damage hooks

- **Funnel holed** (fraction d):
  - natural draught: v_nat × (1 − 0.5 d), because leaks kill the stack effect;
  - forced draught: A_eff × (1 − 0.2 d) only.
  Boilers on that funnel lose output through the power cap.
- **Funnel destroyed:** its boilers drop to 30 % with forced draught, or 0 % with natural draught. Fumes enter the boiler room, giving a crew penalty.
- **Uptake hit inside the hull:** fumes enter the boiler rooms it serves (temporary loss, see the Yorktown note in 04_carriers). If the uptake pierces armour, treat it as a path through the armoured deck at grating protection.
- **Coal-NAT plants** are the most sensitive. Diesel and GT exhausts are nearly indifferent, but a GT intake hit ingests debris and trips the turbine.

### Sanity checks (rough, using §2 lengths)

| ship-like case | key inputs | A_req | n_area | n_reach | model | historical |
|---|---|---|---|---|---|---|
| 1895 pre-dreadnought | ST3 coal FDB, 6.6 MW, H_stack 28 m, boilers 22 m | 8 m² | 1 | 2 | **2** | 2 |
| Dreadnought 1906 | ST5 coal FDC, 17 MW, boilers ~33 m | 12 m² | 1 | 2 | **2** | 2 |
| Lion 1912 | ST5 coal, 52 MW, boilers ~55 m in 2 groups | 35 m² | 1 | 3 | **3** | 3 |
| Hood 1920 | ST6 oil, 107 MW, boilers ~50 m | 28 m² | 1 | 2 | **2** | 2 |
| Yamato 1941 | ST7 FDA, 110 MW, boilers ~40 m | 15 m² | 1 | 1 | **1** | 1 (trunked) |
| Fletcher 1942 | ST7 FDA, 45 MW, unit system, 2 groups | 6 m² | 1 | 1 (R reaches across the engine room) | **1 minimum** | 2 by USN choice; British J class trunked to 1 |

---

## 7. Maturity & step upgrades

- `m = clamp((year - intro) / (mature - intro), 0, 1)`, or drive it from research points.
- Optional over-maturity: m up to 1.2 with 25 % effectiveness. Clamp so the result never passes the next tech's `intro` value on its headline stat.
- **Invariants to unit-test** (within a lineage, next = N+1):
  1. `next.SEC_intro <= prev.SEC_mature * 1.05` and `next.SEC_mature <= prev.SEC_mature * 0.9`. Steam SEC uses coal 30 / oil 41 MJ/kg.
  2. `next.unit_max_mature > prev.unit_max_mature`.
  3. kW/t at maturity and s = 1 is strictly increasing.
  4. For steam ST5 onward, `h_ref/unit_MW` falls.
  - Exception: early turbines (ST5) may be no lighter than mature ST4. Their headline stats are height, unit power and sustained speed. Gas turbines lose to diesels on SFC; the trade-off is weight and unit power. Do not test across families.
- Sanity check on thermal efficiency: `η = 3600 / SEC`. It should read about 4 % for ST1, 11 % for ST3, 15 % for ST5, 26 % for ST7, 29–30 % for ST8, 29 % for GT2, 41 % for GT4, 45–49 % for DI5/DIS.

---

## 8. Anchors (sourced)

| fact | value | source |
|---|---|---|
| Compound engine coal rate, 1872 | 2–2.5 lb coal/ihp-h at 45–60 psi | [WP Compound engine](https://en.wikipedia.org/wiki/Compound_steam_engine) |
| Triple expansion coal rate, 1891 | ~1.5 lb/ihp-h at 160 psi | same |
| 1920 prime movers | VTE 1.54, quad 1.34, turbine 1.0–1.2 (high speed), 2.4 (low speed) lb coal/shp-h; diesel 0.44–0.47 oil; thermal η: VTE 11 %, quad 13 %, turbine 14 %, diesel 29–31 %. Two VTE engines 280 t for 6,700 ihp vs turbo-electric 156 t for 6,300 shp | [NavWeaps tech-077](https://www.navweaps.com/index_tech/tech-077.php) |
| Scotch boiler (HMS Trafalgar 1890) | 84 t each, 16 ft 1 in diameter × 10 ft 3 in long, 1,400 (natural draught) / 2,100 (forced) ihp | [Shipping Wonders](https://www.shippingwondersoftheworld.com/modern_boilers.html) |
| Water-tube boilers | Belleville 250 psi; Yarrow 1903 280 psi; oil-fired Yarrow 1924 425 psi | same |
| Powerful class 1895 | 48 Belleville boilers, 210 psi, 25,000 ihp, 2 VTE | [WP](https://en.wikipedia.org/wiki/Powerful-class_cruiser) |
| Diesel vs steam, 1938 | Deutschland diesel plant 48.5 lb/shp all-in, 0.385 lb/shp-h; steam 40 lb/shp (heavy cruiser), 30 (destroyer), 0.6 lb/shp-h "good practice" | [USNI 1938](https://www.usni.org/magazines/proceedings/1938/november/diesel-vs-steam-comparison-5000-ton-cruiser) |
| US destroyer plants (Friedman) | Fletcher 787 t, Sumner 823 t, Gearing 930 t, all 60,000 shp (~29–35 lb/shp) | [NavWeaps forum](https://www.tapatalk.com/groups/warships1discussionboards/propulsion-plant-weight-of-gearing-class-destroyer-t43258.html) |
| MB 501 E-boat diesel | 4,220 kg, 2,000 hp max, 241 g/kWh; MB 518 3,000–3,500 hp at ~5.1 t | [Old Machine Press](https://oldmachinepress.com/2017/03/05/mercedes-benz-500-series-diesel-marine-engines/) |
| Napier Deltic 18 | 2,500 hp, 4.2 lb/hp | [WP](https://en.wikipedia.org/wiki/Napier_Deltic) |
| Olympus TM3 | 28,000 shp, 0.47 lb/hp-h (287 g/kWh), in service 1968 | [WP](https://en.wikipedia.org/wiki/Rolls-Royce_Marine_Olympus) |
| LM2500 / + / +G4 | 25.1 / 30.2 / 35.3 MW; 227 / 215 / 214 g/kWh; module ~22–23 t, 8 m long | [WP](https://en.wikipedia.org/wiki/General_Electric_LM2500), [GE frigate brochure](https://www.geaerospace.com/sites/default/files/ge-marine-gas-turbines-for-frigates-2018-march.pdf) |
| WR-21 ICR | 25.2 MW, ~190 g/kWh, module ~46 t wet, −30 % fuel over profile | [WP](https://en.wikipedia.org/wiki/Rolls-Royce_WR-21) |
| Forced draught | introduced to the RN ~1880 in torpedo vessels, then standard; closed stokehold or closed ashpit | [Shipping Wonders: Early Marine Boilers](https://shippingwondersoftheworld.com/marine_boilers.html) |
| HMS Victoria (1887) | 7,500 hp natural vs 14,000 hp forced draught; forced draught unpopular and used only for high speed | [Naval Gazing: Propulsion 1](https://www.navalgazing.net/Engineering-Part-1) |
| Stack draught physics | ΔP ∝ h·(1 − T_o/T_i); Q = A·C·√(2gH(T_i − T_o)/T_i) | [WP Flue-gas stack](https://en.wikipedia.org/wiki/Flue-gas_stack) |
| Funnel count history | Great Eastern 5 funnels for gas volume; fewer funnels as efficiency rose; liners added dummies | [WP Funnel (ship)](https://en.wikipedia.org/wiki/Funnel_(ship)) |
| Colossus smoke | fore funnel took 12 boilers vs 6 aft; tripod top behind it "uninhabitable"; funnel raised 1912 | [WP Colossus class](https://en.wikipedia.org/wiki/Colossus-class_battleship_(1910)) |
| Nagato smoke | bridge choked; deflector 1922; serpentine fore funnel 1924; funnel eliminated in 1930s rebuild with 10 oil boilers | [WP Nagato](https://en.wikipedia.org/wiki/Japanese_battleship_Nagato) |

## 9. Out of scope / later

- Nuclear steam: it would slot in as an ST8-like turbine with a heavy reactor block, no fuel mass, and a huge shielding weight.
- Hotel/electrical generation as a separate plant: it matters post-1960, and the Ark Royal lesson that steam-only generation is a single point of failure.
- Waterjets and CPP.
- Cross-connected steam (running all shafts off part of the boilers). Today the steam part-load curve already assumes boilers are cut out at cruise.
- The optional split of steam into independent boiler × engine axes: boiler choices (Scotch / large-tube / express / oil 3-drum / HP superheat / forced-circulation) combined with engine choices (simple → HP turbine) and a min-pressure compatibility check. The package list above is the collapsed version.

---

## Changelog v2 → v2.1

- **`r` (rating) → `s` (design stress), inverted** (s = 0 conservative, s = 1 max stress). Table `w` values are now at s = 0.
  - Gas turbine and high-speed diesel/petrol `w` values were rebased (÷ stress_floor), so outputs at s = 1 are unchanged.
- **Ship-type assumptions removed:**
  - The petrol size ban is gone; replaced by a vapour-risk mechanic.
  - "Light-only" techs (DI3, DI4, DI6, PE1) and "boost-only" GT1 now have a full s range.
  - The "merchant/backward navy" coal-on-ST6+ restriction is gone.
  - Wing bunkers are a design flag instead of being implied by coal firing.
  - The capital-ship examples were reframed as presets.
- **Boiler-type variants split out** from the old ST2/ST3/ST4 light multipliers: `loco_boiler` and `express_boilers`. The stress floors for these techs now reflect only the base boiler type.
- **New:** a continuous vs. rated split, overload headroom, operational overload with wear, SEC penalty for stress, damage tolerance, and overhaul hours.
- **Still deliberately physical constraints, not policy:** gearing needs, protrusion from unit height, unit_max, and year/maturity gating.

## Changelog v2.1 → v2.2

- **Added §6b, funnels, uptakes & draught:**
  - draught-system options (NAT / FDB / FDC / FDA / PF / diesel / GT exhaust);
  - a gas-flow formula;
  - natural-draught velocity from stack height;
  - funnel count from area and uptake reach;
  - centreline footprint and arc conflicts, weight and topweight, smoke cones, a power cap, and damage hooks.
- The trunk-area note in §3 is replaced by §6b.