# Plant templates by year

Copy-paste values for a design's `machinery.tech` block during development. A design names no year: it carries the technology itself, because in the game a navy may research things earlier or later than history did. These blocks are what a navy of that year would typically have.

The blocks below are written by `python plant_templates.py` from the tables in `research/powerplant-model.md`, eased by the tech's maturity in that year (`1 - (1 - m)^2`, where m runs from 0 at the tech's introduction to 1 at maturity). They are tuning defaults, not historical truth. `powerplant.py` documents every field. A design that gives no `tech` gets the 1940 high-pressure turbine (`powerplant.DEFAULT_TECH`); a planing craft gets 1940 petrol engines.

## How to use

```json
"machinery": {
  "tech": { ...a block below... },
  "stress": 0.2,
  "shafts": 4,
  "arrangement": "grouped",
  "bunkers": "wing"
}
```

The tech block is what the navy has researched. The rest are design choices, made per ship. Every one is optional:

| choice | values | default | effect |
|---|---|---|---|
| `stress` | 0..1 | 0 | Higher: lighter (down to `stress_floor` × the weight at 1) and more compact, but 8% thirstier at 1, with less continuous power and no overload margin. |
| `shafts` | 1..8 | the fewest the units allow, 1..4 | More shafts mean smaller units, so lower ones that fit narrower hulls. |
| `units_per_shaft` | 1.. | 1 | Raised automatically if a unit would exceed `unit_max_mw`. |
| `transmission` | `mechanical`, `electric` | mechanical | Electric (turbo-/diesel-electric, 1912+): weight ×1.3, fuel ×1.06. |
| `arrangement` | `grouped`, `unit` | grouped | Unit: boiler and engine rooms alternate, so one hit can't stop the ship. Machinery ×1.1 longer. |
| `centreline_bulkhead` | true/false | false | Splits the rooms port and starboard. Each side fits its own rows of units, so the machinery may get longer. |
| `bunkers` | `wing`, `ends` | wing for coal | Wing bunkers stand beside the machinery (narrowing it, but shielding it); end bunkers add length. Liquid fuel goes in the double bottom first. |
| `wing_bunker_m` | metres | 2.0 | Width of each wing bunker. |

Merchants also take `"position": "amidships" | "aft"`.

Historical stress presets (for AI and quick designs only; any ship may use any value): torpedo boats and destroyers 0.8–1, cruisers about 0.5, capital ships and merchants 0–0.2, fast battleships and battlecruisers 0.4–0.6.

What the plant decides on the ship:
- **Weight** (`weight_kg_per_kw`, `stress_floor`), **fuel** (`sfc_g_per_kwh` at full power, `part_load` curve at cruise) and **engineering crew** (`crew_k`).
- **Machinery length**: its volume (weight / `density_t_per_m3`) fitted into the hull's width and height. Units sit abreast in rows, so a hull too narrow for another row gets a longer machinery space. A unit taller than the room under the armour deck protrudes through it under an armoured casing.
- **Funnels** (`draught`): enough of them for the gas, each within `reach_m` of the boilers it serves. Old coal plants need many big funnels spread over long boiler rooms, and amidships turrets can only stand between boiler groups. Natural and boost draught (`natural`, `forced_boost`) also want tall funnels.

## 1880

Compound engines and Scotch boilers. Forced draught arrives, for boosting only.

**Capital ships, cruisers** (`ST2`)
```json
"tech": {"name": "Compound engines, cylindrical (Scotch) boilers (1880)", "fuel": "coal", "weight_kg_per_kw": 203.8, "stress_floor": 0.75, "sfc_g_per_kwh": 1378, "density_t_per_m3": 0.24, "unit_max_mw": 4.8, "unit": {"mw": 3, "height_m": 5.5, "width_m": 4.5, "length_m": 6}, "boiler_fraction": 0.6, "crew_k": 40, "part_load": "REC", "draught": {"system": "forced_boost", "velocity_m_s": 7.0, "reach_m": 7.0, "natural_fraction": 0.55, "gas_temp_k": 600, "air_fuel_ratio": 16}}
```

**Torpedo boats (locomotive boilers)** (`ST2`)
```json
"tech": {"name": "Compound engines, locomotive boilers (1880)", "fuel": "coal", "weight_kg_per_kw": 122.2, "stress_floor": 0.75, "sfc_g_per_kwh": 1378, "density_t_per_m3": 0.24, "unit_max_mw": 1.5, "unit": {"mw": 3, "height_m": 5.5, "width_m": 4.5, "length_m": 6}, "boiler_fraction": 0.6, "crew_k": 40, "part_load": "REC", "draught": {"system": "forced_boost", "velocity_m_s": 7.0, "reach_m": 7.0, "natural_fraction": 0.55, "gas_temp_k": 600, "air_fuel_ratio": 16}}
```

## 1890

Triple expansion engines. Forced draught for full power; natural draught for steaming.

**Capital ships, cruisers** (`ST3`)
```json
"tech": {"name": "Triple expansion, Scotch boilers (1890)", "fuel": "coal", "weight_kg_per_kw": 167.8, "stress_floor": 0.75, "sfc_g_per_kwh": 1139, "density_t_per_m3": 0.26, "unit_max_mw": 6.8, "unit": {"mw": 5, "height_m": 7.5, "width_m": 4.5, "length_m": 9}, "boiler_fraction": 0.6, "crew_k": 38, "part_load": "REC", "draught": {"system": "forced_boost", "velocity_m_s": 8.5, "reach_m": 8.5, "natural_fraction": 0.6, "gas_temp_k": 600, "air_fuel_ratio": 16}}
```

**Torpedo boats (locomotive boilers)** (`ST3`)
```json
"tech": {"name": "Triple expansion, locomotive boilers (1890)", "fuel": "coal", "weight_kg_per_kw": 100.7, "stress_floor": 0.75, "sfc_g_per_kwh": 1139, "density_t_per_m3": 0.26, "unit_max_mw": 2.0, "unit": {"mw": 5, "height_m": 7.5, "width_m": 4.5, "length_m": 9}, "boiler_fraction": 0.6, "crew_k": 38, "part_load": "REC", "draught": {"system": "forced_boost", "velocity_m_s": 8.5, "reach_m": 8.5, "natural_fraction": 0.6, "gas_temp_k": 600, "air_fuel_ratio": 16}}
```

**Early water-tube boilers (Belleville)** (`ST4`)
```json
"tech": {"name": "Triple expansion, large-tube water-tube boilers (1890)", "fuel": "coal", "weight_kg_per_kw": 150.0, "stress_floor": 0.45, "sfc_g_per_kwh": 1050, "density_t_per_m3": 0.28, "unit_max_mw": 6.0, "unit": {"mw": 5, "height_m": 7.5, "width_m": 4.5, "length_m": 9}, "boiler_fraction": 0.55, "crew_k": 34, "part_load": "REC", "draught": {"system": "forced_boost", "velocity_m_s": 8.5, "reach_m": 8.5, "natural_fraction": 0.7, "gas_temp_k": 600, "air_fuel_ratio": 16}}
```

## 1900

Water-tube boilers take over. Continuous forced draught.

**Capital ships, cruisers** (`ST4`)
```json
"tech": {"name": "Triple expansion, large-tube water-tube boilers (1900)", "fuel": "coal", "weight_kg_per_kw": 127.1, "stress_floor": 0.45, "sfc_g_per_kwh": 972, "density_t_per_m3": 0.28, "unit_max_mw": 9.9, "unit": {"mw": 5, "height_m": 7.5, "width_m": 4.5, "length_m": 9}, "boiler_fraction": 0.55, "crew_k": 34, "part_load": "REC", "draught": {"system": "forced", "velocity_m_s": 8.0, "reach_m": 8.0, "gas_temp_k": 600, "air_fuel_ratio": 16}}
```

**Destroyers (express boilers)** (`ST4`)
```json
"tech": {"name": "Triple expansion, express small-tube boilers (1900)", "fuel": "coal", "weight_kg_per_kw": 76.3, "stress_floor": 0.45, "sfc_g_per_kwh": 972, "density_t_per_m3": 0.28, "unit_max_mw": 9.9, "unit": {"mw": 5, "height_m": 6.38, "width_m": 4.5, "length_m": 9}, "boiler_fraction": 0.55, "crew_k": 34, "part_load": "REC", "draught": {"system": "forced", "velocity_m_s": 8.0, "reach_m": 8.0, "gas_temp_k": 600, "air_fuel_ratio": 16}}
```

**Merchants, older warships** (`ST3`)
```json
"tech": {"name": "Triple expansion, Scotch boilers (1900)", "fuel": "coal", "weight_kg_per_kw": 150.0, "stress_floor": 0.75, "sfc_g_per_kwh": 1050, "density_t_per_m3": 0.26, "unit_max_mw": 9.0, "unit": {"mw": 5, "height_m": 7.5, "width_m": 4.5, "length_m": 9}, "boiler_fraction": 0.6, "crew_k": 38, "part_load": "REC", "draught": {"system": "forced", "velocity_m_s": 8.0, "reach_m": 8.0, "gas_temp_k": 600, "air_fuel_ratio": 16}}
```

## 1905

The first turbines (Dreadnought).

**Turbine ships** (`ST5`)
```json
"tech": {"name": "Direct-drive turbines, water-tube boilers (1905)", "fuel": "coal", "weight_kg_per_kw": 120.0, "stress_floor": 0.35, "sfc_g_per_kwh": 950, "density_t_per_m3": 0.3, "unit_max_mw": 8.0, "unit": {"mw": 10, "height_m": 4.5, "width_m": 4.5, "length_m": 7}, "boiler_fraction": 0.6, "crew_k": 30, "part_load": "DT", "draught": {"system": "forced", "velocity_m_s": 9.1, "reach_m": 9.1, "gas_temp_k": 600, "air_fuel_ratio": 16}}
```

**Reciprocating capital ships** (`ST4`)
```json
"tech": {"name": "Triple expansion, large-tube water-tube boilers (1905)", "fuel": "coal", "weight_kg_per_kw": 118.0, "stress_floor": 0.45, "sfc_g_per_kwh": 940, "density_t_per_m3": 0.28, "unit_max_mw": 11.5, "unit": {"mw": 5, "height_m": 7.5, "width_m": 4.5, "length_m": 9}, "boiler_fraction": 0.55, "crew_k": 34, "part_load": "REC", "draught": {"system": "forced", "velocity_m_s": 9.1, "reach_m": 9.1, "gas_temp_k": 600, "air_fuel_ratio": 16}}
```

**Quadruple expansion (economical cruisers, merchants)** (`ST4`)
```json
"tech": {"name": "Quadruple expansion, large-tube water-tube boilers (1905)", "fuel": "coal", "weight_kg_per_kw": 123.9, "stress_floor": 0.45, "sfc_g_per_kwh": 865, "density_t_per_m3": 0.28, "unit_max_mw": 11.5, "unit": {"mw": 5, "height_m": 7.5, "width_m": 4.5, "length_m": 10.8}, "boiler_fraction": 0.55, "crew_k": 34, "part_load": "REC", "draught": {"system": "forced", "velocity_m_s": 9.1, "reach_m": 9.1, "gas_temp_k": 600, "air_fuel_ratio": 16}}
```

**Destroyers (express boilers)** (`ST4`)
```json
"tech": {"name": "Triple expansion, express small-tube boilers (1905)", "fuel": "coal", "weight_kg_per_kw": 70.8, "stress_floor": 0.45, "sfc_g_per_kwh": 940, "density_t_per_m3": 0.28, "unit_max_mw": 11.5, "unit": {"mw": 5, "height_m": 6.38, "width_m": 4.5, "length_m": 9}, "boiler_fraction": 0.55, "crew_k": 34, "part_load": "REC", "draught": {"system": "forced", "velocity_m_s": 9.1, "reach_m": 9.1, "gas_temp_k": 600, "air_fuel_ratio": 16}}
```

## 1910

Turbines everywhere; oil spray on coal, then all-oil destroyers. Petrol motor boats; early diesels.

**Coal turbine ships** (`ST5`)
```json
"tech": {"name": "Direct-drive turbines, water-tube boilers (1910)", "fuel": "coal", "weight_kg_per_kw": 104.5, "stress_floor": 0.35, "sfc_g_per_kwh": 857, "density_t_per_m3": 0.3, "unit_max_mw": 15.5, "unit": {"mw": 10, "height_m": 4.5, "width_m": 4.5, "length_m": 7}, "boiler_fraction": 0.6, "crew_k": 30, "part_load": "DT", "draught": {"system": "forced", "velocity_m_s": 9.8, "reach_m": 9.8, "gas_temp_k": 600, "air_fuel_ratio": 16}}
```

**Mixed firing** (`ST5`)
```json
"tech": {"name": "Direct-drive turbines, water-tube boilers, mixed firing (coal, oil spray) (1910)", "fuel": "coal", "weight_kg_per_kw": 101.3, "stress_floor": 0.35, "sfc_g_per_kwh": 844, "density_t_per_m3": 0.3, "unit_max_mw": 15.5, "unit": {"mw": 10, "height_m": 4.5, "width_m": 4.5, "length_m": 7}, "boiler_fraction": 0.6, "crew_k": 25.5, "part_load": "DT", "draught": {"system": "forced", "velocity_m_s": 9.8, "reach_m": 9.8, "gas_temp_k": 600, "air_fuel_ratio": 16}}
```

**All-oil turbine ships (destroyers, Queen Elizabeth)** (`ST5`)
```json
"tech": {"name": "Direct-drive turbines, water-tube boilers, oil-fired (1910)", "fuel": "oil", "weight_kg_per_kw": 94.0, "stress_floor": 0.35, "sfc_g_per_kwh": 608, "density_t_per_m3": 0.3, "unit_max_mw": 15.5, "unit": {"mw": 10, "height_m": 4.5, "width_m": 4.5, "length_m": 7}, "boiler_fraction": 0.6, "crew_k": 13.5, "part_load": "DT", "draught": {"system": "forced", "velocity_m_s": 11.8, "reach_m": 15.5, "gas_temp_k": 570, "air_fuel_ratio": 15}}
```

**Reciprocating (merchants, older designs)** (`ST4`)
```json
"tech": {"name": "Triple expansion, large-tube water-tube boilers (1910)", "fuel": "coal", "weight_kg_per_kw": 115.0, "stress_floor": 0.45, "sfc_g_per_kwh": 930, "density_t_per_m3": 0.28, "unit_max_mw": 12.0, "unit": {"mw": 5, "height_m": 7.5, "width_m": 4.5, "length_m": 9}, "boiler_fraction": 0.55, "crew_k": 34, "part_load": "REC", "draught": {"system": "forced", "velocity_m_s": 9.8, "reach_m": 9.8, "gas_temp_k": 600, "air_fuel_ratio": 16}}
```

**Petrol motor boats** (`PE1`)
```json
"tech": {"name": "Petrol engines (1910)", "fuel": "petrol", "weight_kg_per_kw": 8.0, "stress_floor": 0.7, "sfc_g_per_kwh": 328, "density_t_per_m3": 0.4, "unit_max_mw": 0.4, "unit": {"mw": 1, "height_m": 1.2, "width_m": 1.1, "length_m": 2.5}, "boiler_fraction": 0.0, "crew_k": 3, "part_load": "DSL", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

**Early diesels (submarines, motor ships)** (`DI1`)
```json
"tech": {"name": "Early marine diesels (1910)", "fuel": "diesel", "weight_kg_per_kw": 140.0, "stress_floor": 0.6, "sfc_g_per_kwh": 270, "density_t_per_m3": 0.42, "unit_max_mw": 0.4, "unit": {"mw": 1, "height_m": 4.5, "width_m": 2.5, "length_m": 7}, "boiler_fraction": 0.0, "crew_k": 6, "part_load": "DSL", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

## 1915

Oil firing standard in new warships; first geared turbines.

**Oil-fired direct turbines** (`ST5`)
```json
"tech": {"name": "Direct-drive turbines, water-tube boilers, oil-fired (1915)", "fuel": "oil", "weight_kg_per_kw": 86.7, "stress_floor": 0.35, "sfc_g_per_kwh": 573, "density_t_per_m3": 0.3, "unit_max_mw": 19.4, "unit": {"mw": 10, "height_m": 4.5, "width_m": 4.5, "length_m": 7}, "boiler_fraction": 0.6, "crew_k": 13.5, "part_load": "DT", "draught": {"system": "forced", "velocity_m_s": 13.0, "reach_m": 18.0, "gas_temp_k": 570, "air_fuel_ratio": 15}}
```

**With cruising turbines** (`ST5`)
```json
"tech": {"name": "Direct-drive turbines, water-tube boilers and cruising turbines, oil-fired (1915)", "fuel": "oil", "weight_kg_per_kw": 91.0, "stress_floor": 0.35, "sfc_g_per_kwh": 573, "density_t_per_m3": 0.3, "unit_max_mw": 19.4, "unit": {"mw": 10, "height_m": 4.5, "width_m": 4.5, "length_m": 7}, "boiler_fraction": 0.6, "crew_k": 13.5, "part_load": "GTB", "draught": {"system": "forced", "velocity_m_s": 13.0, "reach_m": 18.0, "gas_temp_k": 570, "air_fuel_ratio": 15}}
```

**Geared turbines** (`ST6`)
```json
"tech": {"name": "Geared turbines, oil-fired small-tube boilers (1915)", "fuel": "oil", "weight_kg_per_kw": 75.0, "stress_floor": 0.42, "sfc_g_per_kwh": 520, "density_t_per_m3": 0.32, "unit_max_mw": 15.0, "unit": {"mw": 15, "height_m": 4.5, "width_m": 4.5, "length_m": 8}, "boiler_fraction": 0.55, "crew_k": 12, "part_load": "GTB", "draught": {"system": "forced", "velocity_m_s": 13.0, "reach_m": 18.0, "gas_temp_k": 570, "air_fuel_ratio": 15}}
```

**Coal-fired direct turbines** (`ST5`)
```json
"tech": {"name": "Direct-drive turbines, water-tube boilers (1915)", "fuel": "coal", "weight_kg_per_kw": 96.3, "stress_floor": 0.35, "sfc_g_per_kwh": 808, "density_t_per_m3": 0.3, "unit_max_mw": 19.4, "unit": {"mw": 10, "height_m": 4.5, "width_m": 4.5, "length_m": 7}, "boiler_fraction": 0.6, "crew_k": 30, "part_load": "DT", "draught": {"system": "forced", "velocity_m_s": 10.0, "reach_m": 10.0, "gas_temp_k": 600, "air_fuel_ratio": 16}}
```

**Petrol (coastal motor boats)** (`PE1`)
```json
"tech": {"name": "Petrol engines (1915)", "fuel": "petrol", "weight_kg_per_kw": 7.6, "stress_floor": 0.7, "sfc_g_per_kwh": 318, "density_t_per_m3": 0.4, "unit_max_mw": 0.6, "unit": {"mw": 1, "height_m": 1.2, "width_m": 1.1, "length_m": 2.5}, "boiler_fraction": 0.0, "crew_k": 3, "part_load": "DSL", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

**Early diesels** (`DI1`)
```json
"tech": {"name": "Early marine diesels (1915)", "fuel": "diesel", "weight_kg_per_kw": 117.8, "stress_floor": 0.6, "sfc_g_per_kwh": 253, "density_t_per_m3": 0.42, "unit_max_mw": 1.3, "unit": {"mw": 1, "height_m": 4.5, "width_m": 2.5, "length_m": 7}, "boiler_fraction": 0.0, "crew_k": 6, "part_load": "DSL", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

## 1920

Geared turbines and oil.

**Geared turbines** (`ST6`)
```json
"tech": {"name": "Geared turbines, oil-fired small-tube boilers (1920)", "fuel": "oil", "weight_kg_per_kw": 62.2, "stress_floor": 0.42, "sfc_g_per_kwh": 470, "density_t_per_m3": 0.32, "unit_max_mw": 26.1, "unit": {"mw": 15, "height_m": 4.5, "width_m": 4.5, "length_m": 8}, "boiler_fraction": 0.55, "crew_k": 12, "part_load": "GTB", "draught": {"system": "forced", "velocity_m_s": 13.8, "reach_m": 19.5, "gas_temp_k": 570, "air_fuel_ratio": 15}}
```

**Merchant triple expansion, oil-fired** (`ST4`)
```json
"tech": {"name": "Triple expansion, large-tube water-tube boilers, oil-fired (1920)", "fuel": "oil", "weight_kg_per_kw": 103.5, "stress_floor": 0.45, "sfc_g_per_kwh": 660, "density_t_per_m3": 0.28, "unit_max_mw": 12.0, "unit": {"mw": 5, "height_m": 7.5, "width_m": 4.5, "length_m": 9}, "boiler_fraction": 0.55, "crew_k": 15.3, "part_load": "REC", "draught": {"system": "forced", "velocity_m_s": 13.8, "reach_m": 19.5, "gas_temp_k": 570, "air_fuel_ratio": 15}}
```

**Merchant slow-speed diesels** (`DIS`)
```json
"tech": {"name": "Slow-speed 2-stroke crosshead diesels (merchant) (1920)", "fuel": "diesel", "weight_kg_per_kw": 135.9, "stress_floor": 0.9, "sfc_g_per_kwh": 220, "density_t_per_m3": 0.4, "unit_max_mw": 11.1, "unit": {"mw": 10, "height_m": 9, "width_m": 6, "length_m": 15}, "boiler_fraction": 0.0, "crew_k": 3, "part_load": "DSL", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

**Petrol** (`PE1`)
```json
"tech": {"name": "Petrol engines (1920)", "fuel": "petrol", "weight_kg_per_kw": 7.3, "stress_floor": 0.7, "sfc_g_per_kwh": 310, "density_t_per_m3": 0.4, "unit_max_mw": 0.7, "unit": {"mw": 1, "height_m": 1.2, "width_m": 1.1, "length_m": 2.5}, "boiler_fraction": 0.0, "crew_k": 3, "part_load": "DSL", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

## 1930

Mature geared turbines; high-pressure steam arrives. Light diesels.

**Geared turbines** (`ST6`)
```json
"tech": {"name": "Geared turbines, oil-fired small-tube boilers (1930)", "fuel": "oil", "weight_kg_per_kw": 52.0, "stress_floor": 0.42, "sfc_g_per_kwh": 430, "density_t_per_m3": 0.32, "unit_max_mw": 35.0, "unit": {"mw": 15, "height_m": 4.5, "width_m": 4.5, "length_m": 8}, "boiler_fraction": 0.55, "crew_k": 12, "part_load": "GTB", "draught": {"system": "forced", "velocity_m_s": 14.0, "reach_m": 20.0, "gas_temp_k": 570, "air_fuel_ratio": 15}}
```

**High-pressure geared turbines** (`ST7`)
```json
"tech": {"name": "High-pressure geared turbines (1930)", "fuel": "oil", "weight_kg_per_kw": 45.0, "stress_floor": 0.5, "sfc_g_per_kwh": 420, "density_t_per_m3": 0.42, "unit_max_mw": 25.0, "unit": {"mw": 30, "height_m": 5.0, "width_m": 5.0, "length_m": 8}, "boiler_fraction": 0.5, "crew_k": 10, "part_load": "GTB", "draught": {"system": "forced", "velocity_m_s": 12.0, "reach_m": 20.0, "gas_temp_k": 450, "air_fuel_ratio": 15}}
```

**Light 2-stroke diesels (Deutschland)** (`DI2`)
```json
"tech": {"name": "Lightweight double-acting 2-stroke diesels (1930)", "fuel": "diesel", "weight_kg_per_kw": 47.3, "stress_floor": 0.75, "sfc_g_per_kwh": 246, "density_t_per_m3": 0.42, "unit_max_mw": 3.9, "unit": {"mw": 5, "height_m": 4.5, "width_m": 3.5, "length_m": 10}, "boiler_fraction": 0.0, "crew_k": 5, "part_load": "DSL", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

**Merchant slow-speed diesels** (`DIS`)
```json
"tech": {"name": "Slow-speed 2-stroke crosshead diesels (merchant) (1930)", "fuel": "diesel", "weight_kg_per_kw": 120.0, "stress_floor": 0.9, "sfc_g_per_kwh": 208, "density_t_per_m3": 0.4, "unit_max_mw": 21.3, "unit": {"mw": 10, "height_m": 9, "width_m": 6, "length_m": 15}, "boiler_fraction": 0.0, "crew_k": 3, "part_load": "DSL", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

**Petrol** (`PE1`)
```json
"tech": {"name": "Petrol engines (1930)", "fuel": "petrol", "weight_kg_per_kw": 6.8, "stress_floor": 0.7, "sfc_g_per_kwh": 297, "density_t_per_m3": 0.4, "unit_max_mw": 1.0, "unit": {"mw": 1, "height_m": 1.2, "width_m": 1.1, "length_m": 2.5}, "boiler_fraction": 0.0, "crew_k": 3, "part_load": "DSL", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

## 1935

High-pressure steam spreads; E-boat diesels.

**High-pressure geared turbines** (`ST7`)
```json
"tech": {"name": "High-pressure geared turbines (1935)", "fuel": "oil", "weight_kg_per_kw": 38.9, "stress_floor": 0.5, "sfc_g_per_kwh": 376, "density_t_per_m3": 0.42, "unit_max_mw": 36.1, "unit": {"mw": 30, "height_m": 5.0, "width_m": 5.0, "length_m": 8}, "boiler_fraction": 0.5, "crew_k": 10, "part_load": "GTB", "draught": {"system": "forced", "velocity_m_s": 13.7, "reach_m": 25.6, "gas_temp_k": 450, "air_fuel_ratio": 15}}
```

**Light 2-stroke diesels** (`DI2`)
```json
"tech": {"name": "Lightweight double-acting 2-stroke diesels (1935)", "fuel": "diesel", "weight_kg_per_kw": 42.2, "stress_floor": 0.75, "sfc_g_per_kwh": 237, "density_t_per_m3": 0.42, "unit_max_mw": 5.6, "unit": {"mw": 5, "height_m": 4.5, "width_m": 3.5, "length_m": 10}, "boiler_fraction": 0.0, "crew_k": 5, "part_load": "DSL", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

**High-speed diesels (E-boats)** (`DI3`)
```json
"tech": {"name": "High-speed diesels (E-boat) (1935)", "fuel": "diesel", "weight_kg_per_kw": 13.2, "stress_floor": 0.7, "sfc_g_per_kwh": 240, "density_t_per_m3": 0.45, "unit_max_mw": 1.3, "unit": {"mw": 1.5, "height_m": 1.8, "width_m": 1.6, "length_m": 4}, "boiler_fraction": 0.0, "crew_k": 3, "part_load": "DSL", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

**Petrol** (`PE1`)
```json
"tech": {"name": "Petrol engines (1935)", "fuel": "petrol", "weight_kg_per_kw": 6.6, "stress_floor": 0.7, "sfc_g_per_kwh": 293, "density_t_per_m3": 0.4, "unit_max_mw": 1.0, "unit": {"mw": 1, "height_m": 1.2, "width_m": 1.1, "length_m": 2.5}, "boiler_fraction": 0.0, "crew_k": 3, "part_load": "DSL", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

## 1940

The WWII generation.

**High-pressure geared turbines (Fletcher, KGV, Iowa)** (`ST7`)
```json
"tech": {"name": "High-pressure geared turbines (1940)", "fuel": "oil", "weight_kg_per_kw": 35.2, "stress_floor": 0.5, "sfc_g_per_kwh": 349, "density_t_per_m3": 0.42, "unit_max_mw": 42.8, "unit": {"mw": 30, "height_m": 5.0, "width_m": 5.0, "length_m": 8}, "boiler_fraction": 0.5, "crew_k": 10, "part_load": "GTB", "draught": {"system": "forced", "velocity_m_s": 14.7, "reach_m": 28.9, "gas_temp_k": 450, "air_fuel_ratio": 15}}
```

**Very-high-pressure steam (German Wagner/Benson plants)** (`ST8`)
```json
"tech": {"name": "Very-high-pressure geared turbines (1200 psi) (1940)", "fuel": "oil", "weight_kg_per_kw": 32.4, "stress_floor": 0.55, "sfc_g_per_kwh": 332, "density_t_per_m3": 0.44, "unit_max_mw": 43.0, "unit": {"mw": 40, "height_m": 5.0, "width_m": 5.0, "length_m": 8}, "boiler_fraction": 0.45, "crew_k": 9, "part_load": "GTB", "draught": {"system": "forced", "velocity_m_s": 14.7, "reach_m": 28.9, "gas_temp_k": 450, "air_fuel_ratio": 15}}
```

**Merchant triple expansion, oil-fired (Liberty)** (`ST4`)
```json
"tech": {"name": "Triple expansion, large-tube water-tube boilers, oil-fired (1940)", "fuel": "oil", "weight_kg_per_kw": 103.5, "stress_floor": 0.45, "sfc_g_per_kwh": 660, "density_t_per_m3": 0.28, "unit_max_mw": 12.0, "unit": {"mw": 5, "height_m": 7.5, "width_m": 4.5, "length_m": 9}, "boiler_fraction": 0.55, "crew_k": 15.3, "part_load": "REC", "draught": {"system": "forced", "velocity_m_s": 14.0, "reach_m": 20.0, "gas_temp_k": 570, "air_fuel_ratio": 15}}
```

**Merchant geared turbines (T2, Victory)** (`ST6`)
```json
"tech": {"name": "Geared turbines, oil-fired small-tube boilers (1940)", "fuel": "oil", "weight_kg_per_kw": 52.0, "stress_floor": 0.42, "sfc_g_per_kwh": 430, "density_t_per_m3": 0.32, "unit_max_mw": 35.0, "unit": {"mw": 15, "height_m": 4.5, "width_m": 4.5, "length_m": 8}, "boiler_fraction": 0.55, "crew_k": 12, "part_load": "GTB", "draught": {"system": "forced", "velocity_m_s": 14.0, "reach_m": 20.0, "gas_temp_k": 570, "air_fuel_ratio": 15}}
```

**Merchant slow-speed diesels** (`DIS`)
```json
"tech": {"name": "Slow-speed 2-stroke crosshead diesels (merchant) (1940)", "fuel": "diesel", "weight_kg_per_kw": 105.9, "stress_floor": 0.9, "sfc_g_per_kwh": 198, "density_t_per_m3": 0.4, "unit_max_mw": 30.4, "unit": {"mw": 10, "height_m": 9, "width_m": 6, "length_m": 15}, "boiler_fraction": 0.0, "crew_k": 3, "part_load": "DSL", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

**Light 2-stroke diesels** (`DI2`)
```json
"tech": {"name": "Lightweight double-acting 2-stroke diesels (1940)", "fuel": "diesel", "weight_kg_per_kw": 39.0, "stress_floor": 0.75, "sfc_g_per_kwh": 232, "density_t_per_m3": 0.42, "unit_max_mw": 6.7, "unit": {"mw": 5, "height_m": 4.5, "width_m": 3.5, "length_m": 10}, "boiler_fraction": 0.0, "crew_k": 5, "part_load": "DSL", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

**High-speed diesels (E-boats)** (`DI3`)
```json
"tech": {"name": "High-speed diesels (E-boat) (1940)", "fuel": "diesel", "weight_kg_per_kw": 11.9, "stress_floor": 0.7, "sfc_g_per_kwh": 233, "density_t_per_m3": 0.45, "unit_max_mw": 2.0, "unit": {"mw": 1.5, "height_m": 1.8, "width_m": 1.6, "length_m": 4}, "boiler_fraction": 0.0, "crew_k": 3, "part_load": "DSL", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

**Petrol (PT boats, MTBs)** (`PE1`)
```json
"tech": {"name": "Petrol engines (1940)", "fuel": "petrol", "weight_kg_per_kw": 6.5, "stress_floor": 0.7, "sfc_g_per_kwh": 291, "density_t_per_m3": 0.4, "unit_max_mw": 1.1, "unit": {"mw": 1, "height_m": 1.2, "width_m": 1.1, "length_m": 2.5}, "boiler_fraction": 0.0, "crew_k": 3, "part_load": "DSL", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

## 1945

Mature WWII plants.

**High-pressure geared turbines** (`ST7`)
```json
"tech": {"name": "High-pressure geared turbines (1945)", "fuel": "oil", "weight_kg_per_kw": 34.0, "stress_floor": 0.5, "sfc_g_per_kwh": 340, "density_t_per_m3": 0.42, "unit_max_mw": 45.0, "unit": {"mw": 30, "height_m": 5.0, "width_m": 5.0, "length_m": 8}, "boiler_fraction": 0.5, "crew_k": 10, "part_load": "GTB", "draught": {"system": "forced", "velocity_m_s": 15.0, "reach_m": 30.0, "gas_temp_k": 450, "air_fuel_ratio": 15}}
```

**Very-high-pressure steam** (`ST8`)
```json
"tech": {"name": "Very-high-pressure geared turbines (1200 psi) (1945)", "fuel": "oil", "weight_kg_per_kw": 30.1, "stress_floor": 0.55, "sfc_g_per_kwh": 320, "density_t_per_m3": 0.44, "unit_max_mw": 47.3, "unit": {"mw": 40, "height_m": 5.0, "width_m": 5.0, "length_m": 8}, "boiler_fraction": 0.45, "crew_k": 9, "part_load": "GTB", "draught": {"system": "forced", "velocity_m_s": 15.0, "reach_m": 30.0, "gas_temp_k": 450, "air_fuel_ratio": 15}}
```

**High-speed diesels** (`DI3`)
```json
"tech": {"name": "High-speed diesels (E-boat) (1945)", "fuel": "diesel", "weight_kg_per_kw": 11.5, "stress_floor": 0.7, "sfc_g_per_kwh": 230, "density_t_per_m3": 0.45, "unit_max_mw": 2.2, "unit": {"mw": 1.5, "height_m": 1.8, "width_m": 1.6, "length_m": 4}, "boiler_fraction": 0.0, "crew_k": 3, "part_load": "DSL", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

**Petrol** (`PE1`)
```json
"tech": {"name": "Petrol engines (1945)", "fuel": "petrol", "weight_kg_per_kw": 6.5, "stress_floor": 0.7, "sfc_g_per_kwh": 290, "density_t_per_m3": 0.4, "unit_max_mw": 1.1, "unit": {"mw": 1, "height_m": 1.2, "width_m": 1.1, "length_m": 2.5}, "boiler_fraction": 0.0, "crew_k": 3, "part_load": "DSL", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

## 1950

Post-war steam; the first naval gas turbines.

**Very-high-pressure steam** (`ST8`)
```json
"tech": {"name": "Very-high-pressure geared turbines (1200 psi) (1950)", "fuel": "oil", "weight_kg_per_kw": 28.3, "stress_floor": 0.55, "sfc_g_per_kwh": 311, "density_t_per_m3": 0.44, "unit_max_mw": 50.7, "unit": {"mw": 40, "height_m": 5.0, "width_m": 5.0, "length_m": 8}, "boiler_fraction": 0.45, "crew_k": 9, "part_load": "GTB", "draught": {"system": "forced", "velocity_m_s": 15.0, "reach_m": 30.0, "gas_temp_k": 450, "air_fuel_ratio": 15}}
```

**Early gas turbines (boost)** (`GT1`)
```json
"tech": {"name": "Early naval gas turbines (boost) (1950)", "fuel": "diesel", "weight_kg_per_kw": 15.2, "stress_floor": 0.85, "sfc_g_per_kwh": 477, "density_t_per_m3": 0.22, "unit_max_mw": 2.4, "unit": {"mw": 3, "height_m": 1.5, "width_m": 1.5, "length_m": 4}, "boiler_fraction": 0.0, "crew_k": 3, "part_load": "GTS", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

**Turbocharged high-speed diesels (Deltic)** (`DI4`)
```json
"tech": {"name": "Turbocharged high-speed diesels (Deltic) (1950)", "fuel": "diesel", "weight_kg_per_kw": 11.5, "stress_floor": 0.7, "sfc_g_per_kwh": 235, "density_t_per_m3": 0.45, "unit_max_mw": 1.5, "unit": {"mw": 2.5, "height_m": 2.0, "width_m": 2.0, "length_m": 3.5}, "boiler_fraction": 0.0, "crew_k": 3, "part_load": "DSL", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

## 1960

1200 psi steam matures; gas turbines grow.

**Very-high-pressure steam** (`ST8`)
```json
"tech": {"name": "Very-high-pressure geared turbines (1200 psi) (1960)", "fuel": "oil", "weight_kg_per_kw": 26.3, "stress_floor": 0.55, "sfc_g_per_kwh": 301, "density_t_per_m3": 0.44, "unit_max_mw": 54.5, "unit": {"mw": 40, "height_m": 5.0, "width_m": 5.0, "length_m": 8}, "boiler_fraction": 0.45, "crew_k": 9, "part_load": "GTB", "draught": {"system": "forced", "velocity_m_s": 15.0, "reach_m": 30.0, "gas_temp_k": 450, "air_fuel_ratio": 15}}
```

**Early gas turbines** (`GT1`)
```json
"tech": {"name": "Early naval gas turbines (boost) (1960)", "fuel": "diesel", "weight_kg_per_kw": 13.1, "stress_floor": 0.85, "sfc_g_per_kwh": 402, "density_t_per_m3": 0.22, "unit_max_mw": 3.5, "unit": {"mw": 3, "height_m": 1.5, "width_m": 1.5, "length_m": 4}, "boiler_fraction": 0.0, "crew_k": 3, "part_load": "GTS", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

**Turbocharged high-speed diesels** (`DI4`)
```json
"tech": {"name": "Turbocharged high-speed diesels (Deltic) (1960)", "fuel": "diesel", "weight_kg_per_kw": 9.9, "stress_floor": 0.7, "sfc_g_per_kwh": 224, "density_t_per_m3": 0.45, "unit_max_mw": 2.6, "unit": {"mw": 2.5, "height_m": 2.0, "width_m": 2.0, "length_m": 3.5}, "boiler_fraction": 0.0, "crew_k": 3, "part_load": "DSL", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

**Merchant slow-speed diesels** (`DIS`)
```json
"tech": {"name": "Slow-speed 2-stroke crosshead diesels (merchant) (1960)", "fuel": "diesel", "weight_kg_per_kw": 83.4, "stress_floor": 0.9, "sfc_g_per_kwh": 182, "density_t_per_m3": 0.4, "unit_max_mw": 44.9, "unit": {"mw": 10, "height_m": 9, "width_m": 6, "length_m": 15}, "boiler_fraction": 0.0, "crew_k": 3, "part_load": "DSL", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

## 1970

Aero-derived gas turbines and medium-speed diesels.

**Very-high-pressure steam** (`ST8`)
```json
"tech": {"name": "Very-high-pressure geared turbines (1200 psi) (1970)", "fuel": "oil", "weight_kg_per_kw": 26.0, "stress_floor": 0.55, "sfc_g_per_kwh": 300, "density_t_per_m3": 0.44, "unit_max_mw": 55.0, "unit": {"mw": 40, "height_m": 5.0, "width_m": 5.0, "length_m": 8}, "boiler_fraction": 0.45, "crew_k": 9, "part_load": "GTB", "draught": {"system": "forced", "velocity_m_s": 15.0, "reach_m": 30.0, "gas_temp_k": 450, "air_fuel_ratio": 15}}
```

**Marinised aero gas turbines (Olympus, Tyne)** (`GT2`)
```json
"tech": {"name": "Marinised aero gas turbines (Olympus/Tyne) (1970)", "fuel": "diesel", "weight_kg_per_kw": 15.2, "stress_floor": 0.85, "sfc_g_per_kwh": 296, "density_t_per_m3": 0.22, "unit_max_mw": 16.8, "unit": {"mw": 20, "height_m": 3.2, "width_m": 2.8, "length_m": 8}, "boiler_fraction": 0.0, "crew_k": 2.5, "part_load": "GTS", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

**Medium-speed diesels** (`DI5`)
```json
"tech": {"name": "Medium-speed diesels (1970)", "fuel": "diesel", "weight_kg_per_kw": 27.9, "stress_floor": 0.8, "sfc_g_per_kwh": 209, "density_t_per_m3": 0.42, "unit_max_mw": 4.9, "unit": {"mw": 6, "height_m": 4.0, "width_m": 3.0, "length_m": 7}, "boiler_fraction": 0.0, "crew_k": 3, "part_load": "DSL", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

**Turbocharged high-speed diesels** (`DI4`)
```json
"tech": {"name": "Turbocharged high-speed diesels (Deltic) (1970)", "fuel": "diesel", "weight_kg_per_kw": 9.3, "stress_floor": 0.7, "sfc_g_per_kwh": 220, "density_t_per_m3": 0.45, "unit_max_mw": 3.0, "unit": {"mw": 2.5, "height_m": 2.0, "width_m": 2.0, "length_m": 3.5}, "boiler_fraction": 0.0, "crew_k": 3, "part_load": "DSL", "draught": {"system": "exhaust", "velocity_m_s": 35, "reach_m": 60, "gas_temp_k": 620, "air_fuel_ratio": 38}}
```

