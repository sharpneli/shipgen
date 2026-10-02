# Crew standard templates

Copy-paste values for a design's `crew.standard` block. A standard is the habitability a navy builds to; in the
game a slider picks it, and the crew's comfort is rated from the numbers smoothly, so these six are only reference
points (research/crew-space-model.md, section 4). They are tuning defaults, not historical truth. `crew.py`
documents every field. Written by `python crew_templates.py` from `crew.STANDARDS`.

A design that gives no standard gets H2 (warships, carriers), H3 (merchants) or H0 (planing craft).

## How to use

```json
"crew": {
  "standard": { ...a block below... },
  "endurance_days": 45,
  "distiller": true,
  "berth_ratio": 1.0
}
```

| choice | default | effect |
|---|---|---|
| `endurance_days` | the fuel's range at cruise speed | Provisions carried. A tender may loiter far longer than its fuel range; shorter than the range only warns. |
| `distiller` | true | Makes fresh water: the tanks then hold `buffer_days` (default 5). Without one, water for the whole endurance (the double bottom takes what the fuel leaves). |
| `water_l_per_day` | the standard's | Rationing is a policy. |
| `berth_ratio` | 1.0 | Below 1 hot-bunking (men share berths across watches), above 1 surge berths. |
| `officer_fraction` | 0.15 under 30 men, else 0.08 | |

The complement comes from the ship: engineering from the plant, gun and torpedo crews per mount, deck and command
by size, an air group on carriers, then the standard's hotel crew. The crew lives wherever the ship has empty
volume; too little makes the hull grow.


## H0: Sleep at station (MTB, PT boat)

Few or shared berths, a stove corner, one head. CMB, MTB, PT boat and E-boat practice.

```json
"standard": {"name": "Sleep at station (MTB, PT boat)", "sleep_rating_m2": 0.6, "sleep_cpo_m2": 0.8, "sleep_officer_m2": 1.5, "mess_seats_per_man": 0.0, "galley_k": 0.25, "galley_min_m2": 1.0, "sanitary_m2": 0.06, "sickbay_beds_per_man": 0.0, "welfare_m2": 0.0, "services_k": 0.0, "passage_factor": 1.1, "deck_height_m": 1.9, "provisions_m3_per_day": 0.006, "water_l_per_day": 8, "hotel_fraction": 0.0, "cpo_fraction": 0.0, "tolerance_days": 2}
```

## H1: Hammocks over mess tables

Hammocks slung over the mess tables (14 in per man, RN). 1840s onward; RN destroyers into the 1950s.

```json
"standard": {"name": "Hammocks over mess tables", "sleep_rating_m2": 1.1, "sleep_cpo_m2": 1.8, "sleep_officer_m2": 5.0, "mess_seats_per_man": 0.0, "galley_k": 0.3, "galley_min_m2": 4.0, "sanitary_m2": 0.1, "sickbay_beds_per_man": 0.01, "welfare_m2": 0.0, "services_k": 0.03, "passage_factor": 1.15, "deck_height_m": 2.3, "provisions_m3_per_day": 0.007, "water_l_per_day": 15, "hotel_fraction": 0.05, "cpo_fraction": 0.08, "tolerance_days": 30}
```

## H2: Tiered bunks and separate messdecks

Three- and four-tier pipe bunks, separate messdecks, refrigeration (USN WWII). From about 1925.

```json
"standard": {"name": "Tiered bunks and separate messdecks", "sleep_rating_m2": 1.3, "sleep_cpo_m2": 2.5, "sleep_officer_m2": 6.0, "mess_seats_per_man": 0.33, "galley_k": 0.3, "galley_min_m2": 5.0, "sanitary_m2": 0.2, "sickbay_beds_per_man": 0.01, "welfare_m2": 0.03, "services_k": 0.05, "passage_factor": 1.2, "deck_height_m": 2.4, "provisions_m3_per_day": 0.009, "water_l_per_day": 60, "hotel_fraction": 0.06, "cpo_fraction": 0.08, "tolerance_days": 60}
```

## H3: Cold-war bunks with lockers and lounges

Bunks with lockers, lounges, laundry, ship's store (Spruance, Nimitz generation). From about 1965.

```json
"standard": {"name": "Cold-war bunks with lockers and lounges", "sleep_rating_m2": 1.9, "sleep_cpo_m2": 3.5, "sleep_officer_m2": 7.5, "mess_seats_per_man": 0.3, "galley_k": 0.35, "galley_min_m2": 6.0, "sanitary_m2": 0.35, "sickbay_beds_per_man": 0.012, "welfare_m2": 0.15, "services_k": 0.08, "passage_factor": 1.25, "deck_height_m": 2.6, "provisions_m3_per_day": 0.01, "water_l_per_day": 120, "hotel_fraction": 0.07, "cpo_fraction": 0.08, "tolerance_days": 120}
```

## H4: Modern small messes

Six-berth messes, gym, services in the deckhead (Type 45 generation). From about 1995.

```json
"standard": {"name": "Modern small messes", "sleep_rating_m2": 2.8, "sleep_cpo_m2": 5.0, "sleep_officer_m2": 9.0, "mess_seats_per_man": 0.3, "galley_k": 0.4, "galley_min_m2": 8.0, "sanitary_m2": 0.45, "sickbay_beds_per_man": 0.015, "welfare_m2": 0.3, "services_k": 0.1, "passage_factor": 1.28, "deck_height_m": 2.8, "provisions_m3_per_day": 0.011, "water_l_per_day": 180, "hotel_fraction": 0.07, "cpo_fraction": 0.08, "tolerance_days": 180}
```

## H5: Single cabins (merchant)

Single cabins, en-suite or one wash place per six (merchant MLC grade). From about 1950.

```json
"standard": {"name": "Single cabins (merchant)", "sleep_rating_m2": 5.0, "sleep_cpo_m2": 7.0, "sleep_officer_m2": 10.0, "mess_seats_per_man": 0.5, "galley_k": 0.4, "galley_min_m2": 8.0, "sanitary_m2": 0.6, "sickbay_beds_per_man": 0.015, "welfare_m2": 0.5, "services_k": 0.12, "passage_factor": 1.3, "deck_height_m": 2.8, "provisions_m3_per_day": 0.011, "water_l_per_day": 200, "hotel_fraction": 0.08, "cpo_fraction": 0.08, "tolerance_days": 365}
```
