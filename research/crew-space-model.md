# Crew Space Model v1: hand-off spec

**Goal:** given a complement N, a habitability standard and an endurance, return the volume the crew needs: living space, provisions, fresh water and distilling. It should work unchanged from a 13-man MTB to a 5,000-man carrier.
**Companion to:** `powerplant-model.md`. That model supplies engineering crew (`crew_k`) and the electrical/steam hotel load hooks used here.

> **Design-freedom rule.** Nothing here depends on ship type, role or size. The habitability standard, berth ratio and water policy are design choices. A destroyer can carry carrier-grade accommodation, and a carrier can be built to WWII-destroyer squalor. The cost is volume, and the penalty for skimping is fatigue and morale over time (§6), not a rule.

> **Data honesty.** The *Anchors* (§9) are sourced. The standard tables are **estimates fitted to those anchors** plus rough hull-volume sanity checks. Treat them as tuning defaults.

---

## 1. Why per-person volume is not constant

Three effects stack, and only the first is a true economy of scale:

1. **Shared spaces scale sub-linearly.** One galley, one sickbay, one office serve the crew. Galley ∝ N^0.8, services ∝ N^0.85, with fixed minimums. Small crews pay a premium: about **+25–30 % per head at N = 10 vs N = 300**. Above ~300 the curve is nearly flat, because big ships add functions (hospital, chapel, store, gym) that offset the savings.
2. **Duration-driven stores are linear in N × days.** Provisions always scale with endurance. Fresh water scales with endurance only if there is no distiller; with one, tanks hold a few days' buffer.
3. **The habitability standard is the big lever.** Per-head living space varies roughly **×15 between "sleep at your station" and merchant single cabins**. Historically, short-sortie craft used low standards and long-deployment ships used high ones. That is why per-head space *looks* like it grows with ship size. In this model that comes from the player's choice of standard against the deployment length (§6), not from size.

---

## 2. Units & conventions

- Areas in m² (net deck area), volumes in m³.
- **Living volume** = net area × passage factor `k_pass` × deck height `h_d`. This is gross volume of the accommodation zone, including its own internal passages, but **excluding** main fore-aft passages and ladders shared with the rest of the ship. The general-arrangement layer adds those.
- **Stores volume** is gross stowage, including shelving, aisles and refrigeration insulation.
- **Water** is tankage. It can live in the double bottom or the TDS liquid layers, like fuel oil, so it is reported separately from habitable volume.

---

## 3. Core model

```
inputs:  N_ops (operational crew: engineering + weapons + deck/command + air group ...),
         std (H0..H5), fo/fc (officer / CPO fractions), b (berth ratio, 1.0 = berth per man),
         T_end (provisioned endurance, days), water policy {w_day, distiller, T_buf},
         H_avail_accom (clear height available in the accommodation zone)

# hotel crew (cooks, stewards, medics, supply, admin) are crew too -> closed-form roll-up
N   = N_ops / (1 - hotel[std])
No  = fo * N ; Nc = fc * N ; Nr = N - No - Nc
     # defaults: fo = 0.15 if N < 30 else 0.08 ; fc = 0 for H0, else 0.08

# --- net areas, m² ---
A_sleep   = Nr * b * a_r[std] + Nc * a_c[std] + No * a_o[std]
A_mess    = seat[std] * (Nr + Nc) * 1.1                 # 1.1 m² per seat incl. serving/passage
          + (std == H0 ? 0 : 0.8 * No * 1.6)            # wardroom (doubles as officers' lounge)
A_galley  = max(g_min[std], g[std] * N^0.8)              # galley + pantry + scullery + bakery
A_san     = max(1.0, s[std] * N)                         # heads, washrooms, showers
beds      = (N >= 15 and T_end > 3) ? ceil(med[std] * N) : 0
A_med     = (beds ? 6 + 4*beds : 0) + (N > 1000 and std >= H2 ? 40 : 0)   # +OR/dental on big ships
A_welfare = r[std] * N                                    # lounges, gym, library, separate from messes
A_serv    = sv[std] * N^0.85 * (T_end > 7 ? 1 : 0.5)     # offices, laundry, barber, store, chapel, post

A_net   = A_sleep + A_mess + A_galley + A_san + A_med + A_welfare + A_serv
h_eff   = min(h_d[std], H_avail_accom)
V_live  = A_net * k_pass[std] * h_eff
          # if h_eff < h_d: living volume shrinks, but comfort drops too (§6). Below 1.85 m: stooping.

# --- stores ---
V_prov  = N * T_end * vp[std] * 1.4                      # 1.4 = stowage factor
V_water = N * w_day * (distiller ? min(T_buf, T_end) : T_end) / 1000      # tankage, m³
Q_dist  = distiller ? 1.2 * N * w_day / 1000 : 0         # distiller capacity, m³/day
V_dist  = 0.06 * Q_dist                                  # distiller plant volume, goes in machinery
E_dist  = Q_dist * (evaporator ? 70 kWh_th : 4.5 kWh_e) per m³   # RO from 1980; hotel-load hook

outputs: V_live, V_prov, V_water, V_dist, comfort inputs (A_sleep per man, crowding, h_eff)
```

**Defaults:** `T_buf` = 5 days. `w_day` defaults from the standard (table) but is its own setting, because rationing is a policy.

---

## 4. Habitability standards

These work like a tech ladder: year-gated, with research making them available. Using one is a choice. `T_ok` feeds §6.

```yaml
H0: {name: "Sleep at station / open boat", from: 1840,
     a_r: 0.6, a_c: 0.8, a_o: 1.5, seat: 0.0, g: 0.25, g_min: 1.0, s: 0.06, med: 0,
     r: 0.0, sv: 0.0, k_pass: 1.10, h_d: 1.9, vp: 0.006, w_day: 8, hotel: 0.00, T_ok: 2,
     note: "Few or shared berths, primus/stove corner, one head. CMB/MTB/PT/E-boat practice."}
H1: {name: "Hammocks over mess tables", from: 1840, until_default: 1955,
     a_r: 1.1, a_c: 1.8, a_o: 5.0, seat: 0.0, g: 0.30, g_min: 4, s: 0.10, med: 0.010,
     r: 0.0, sv: 0.03, k_pass: 1.15, h_d: 2.3, vp: 0.007, w_day: 15, hotel: 0.05, T_ok: 30,
     note: "14 in hammock spacing (RN). Sleeping and messing share one deck, so seat = 0.
            Hammocks stowed by day. RN destroyers used this into the 1950s."}
H2: {name: "Tiered bunks + separate messdecks", from: 1925,
     a_r: 1.3, a_c: 2.5, a_o: 6.0, seat: 0.33, g: 0.30, g_min: 5, s: 0.20, med: 0.010,
     r: 0.03, sv: 0.05, k_pass: 1.20, h_d: 2.4, vp: 0.009, w_day: 60, hotel: 0.06, T_ok: 60,
     note: "USN WWII / early Cold War. 3-4 tier pipe bunks, ~7 sq ft walkable per man, 3 meal sittings. Needs refrigeration."}
H3: {name: "Cold-war 3-tier with lockers & lounges", from: 1965,
     a_r: 1.9, a_c: 3.5, a_o: 7.5, seat: 0.30, g: 0.35, g_min: 6, s: 0.35, med: 0.012,
     r: 0.15, sv: 0.08, k_pass: 1.25, h_d: 2.6, vp: 0.010, w_day: 120, hotel: 0.07, T_ok: 120,
     note: "Spruance/Burke/Nimitz generation. Separate lounges, laundry, ship's store."}
H4: {name: "Modern habitability (small messes, 2-3 tier)", from: 1995,
     a_r: 2.8, a_c: 5.0, a_o: 9.0, seat: 0.30, g: 0.40, g_min: 8, s: 0.45, med: 0.015,
     r: 0.30, sv: 0.10, k_pass: 1.28, h_d: 2.8, vp: 0.011, w_day: 180, hotel: 0.07, T_ok: 180,
     note: "Type 45/26-class 6-berth messes, gym, services in deckhead (taller h_d)."}
H5: {name: "Single cabins (merchant / MLC 2006 grade)", from: 1950,
     a_r: 5.0, a_c: 7.0, a_o: 10.0, seat: 0.50, g: 0.40, g_min: 8, s: 0.60, med: 0.015,
     r: 0.50, sv: 0.12, k_pass: 1.30, h_d: 2.8, vp: 0.011, w_day: 200, hotel: 0.08, T_ok: 365,
     note: "MLC: 4.5 m² single rating cabin, en-suite (in s), 1 WC/basin/shower per 6 otherwise."}
```

Field meanings:

- `a_r`, `a_c`, `a_o`: sleeping area per rating, CPO and officer (m² net, including lockers).
- `seat`: mess seats per non-officer.
- `g`: galley coefficient; `g_min` is the galley floor area minimum.
- `s`: sanitary area per head.
- `med`: sickbay beds per head.
- `r`: welfare area per head.
- `sv`: services coefficient.
- `vp`: provisions in m³ per person-day, net.
- `w_day`: fresh water in L per person-day.
- `hotel`: hotel-crew fraction of the total complement.

`b` (berth ratio) is independent of the standard:

- `b < 1` is **hot-bunking**: two or three men share a berth across watches. Submarines, some small craft and austere designs used it. It saves sleeping area, costs comfort (§6), and works only with H2+ bunks.
- `b > 1` is **surge berths** for troops, flag staff, air-group detachments, or a planned wartime complement.

---

## 5. Resulting per-head volumes

Living + provisions in m³/person at T_end = 30 days, with a distiller (water excluded):

| std | N=10 | 30 | 100 | 300 | 1,000 | 3,000 | 6,000 |
|---|---|---|---|---|---|---|---|
| H0 | 2.3 | 2.0 | 2.0 | 1.9 | 1.9 | 1.9 | 1.9 |
| H1 | 6.8 | 6.0 | 5.3 | 5.2 | 5.1 | 5.0 | 5.0 |
| H2 | 10.1 | 8.9 | 8.1 | 7.9 | 7.8 | 7.8 | 7.7 |
| H3 | 15.0 | 13.3 | 12.4 | 12.1 | 12.0 | 11.9 | 11.9 |
| H4 | 22.0 | 19.4 | 18.3 | 18.0 | 17.8 | 17.7 | 17.6 |
| H5 | 31.6 | 29.4 | 28.2 | 27.9 | 27.7 | 27.6 | 27.5 |

Endurance sensitivity, N = 300, including water tankage (m³/person):

| case | 1 d | 3 d | 14 d | 45 d | 90 d | 180 d |
|---|---|---|---|---|---|---|
| H2, distiller | 7.4 | 7.6 | 8.0 | 8.4 | 9.0 | 10.1 |
| H2, no distiller | 7.4 | 7.6 | 8.5 | 10.8 | 14.1 | 20.6 |
| H4, distiller | 17.4 | 17.8 | 18.6 | 19.1 | 19.8 | 21.2 |
| H4, no distiller | 17.4 | 17.8 | 20.2 | 26.3 | 35.1 | 52.7 |

So endurance is cheap *if you can make water*. Without distillers, modern water consumption makes long endurance prohibitive. That is why pre-distiller navies rationed hard (H1 default 15 L; sail-era ~2–4 L, §9).

---

## 6. Comfort, crowding & duration (where the standard pays off)

Volume is the cost; this section is the benefit. Keep it simple, since it only drives crew fatigue/efficiency and morale.

```
crowd  = N_aboard / (N_design * b)          # >1 when the wartime complement exceeds berths
space  = A_sleep_per_man_actual / a_r[std]  # <1 if the designer squeezed below the table value
head   = h_eff >= 1.85 ? 1 : 0.7            # stooping accommodation

T_tol  = T_ok[std] * space * head / crowd^2           # days before decline starts
after T_tol at sea:  morale -= k_m * (t/T_tol - 1) per day ; fatigue recovery x (T_tol/t)

crowd 1.0-1.5 : extras hot-bunk or sling hammocks in passages (H1-H2 can do this; H3+ cannot,
                because there are no hammock bars)
crowd > 1.5   : men sleep at action stations. T_tol capped at 3 days.
food endurance: T_food = T_end / crowd ; water likewise when there is no distiller
```

- **Wartime growth is the key historical case.** WWII ships routinely grew their complements 30–80 % for AA crews and radar without new accommodation (Fletcher: designed 273, wartime ~329). The model handles this through `crowd`. You don't rebuild the ship; you live with shortened tolerance and food endurance.
- **Port and replenishment reset `t`.** A tender alongside or a rest period also resets it. Underway replenishment resets food and water but only half-resets `t`.
- **Small craft** on H0 are fine for sorties (T_ok = 2 days). They need a base, depot ship or tender for accommodation between sorties. A good hook: tenders and depot ships have value.

---

## 7. Hooks into other systems

- **Crew roll-up:** `N_ops` = engineering crew from `powerplant-model.md` (`crew_k · P_MW^0.75`, firing multipliers) + weapons crews + command/deck + air group. The hotel fraction is solved in closed form (§3); there is no iteration.
- **Hotel load:** refrigeration and distilling scale with N and the standard. A suggested hotel electrical load is `0.25 kW/person (H1) … 1.5 kW/person (H4)`, plus `E_dist`. This feeds the out-of-scope hotel-plant item in the powerplant spec.
- **Damage:**
  - **Fire load:** accommodation is a fire-load zone. Pre-1940 standards carry wood, linoleum, bedding and paint; give H1/H2 fire load ×1.5. H4 uses low-flammability fittings, ×0.7.
  - **Casualties:** crew casualties from a hit on an accommodation compartment depend on watch state. Off-watch men are asleep there, so the hit kills off-watch men, not watchkeepers.
  - **Messdecks as damage-control stations:** messdecks served as DC and first-aid stations, so a hit there hurts DC.
  - **Sickbay as a component:** if it is destroyed, the wounded-recovery rate drops.
- **Placement:** living volume generally goes where machinery and magazines don't: forward under the fo'c'sle, aft, and in superstructure. Constraints on where it can go belong to the GA/subdivision layer (`01_capital_subdivision.md`). Placing accommodation outside the armoured citadel is the historical default and has consequences in damage play.

---

## 8. Worked checks

The model outputs below come from the defaults above. "Share" is the model's V_live against a rough enclosed-volume estimate (hull × Cb + superstructure). Both columns are estimates, meant as a plausibility check.

| case | inputs | V_live | per head (live + prov) | share of enclosed vol. |
|---|---|---|---|---|
| Vosper 73 ft MTB | N 13, H0, T 2 d, no distiller | 26 m³ | 2.0 | ~15 % of ~180 m³ |
| USS Constitution 1813 | N 485, H1, T 180 d, no distiller, w_day 4 | 2,070 m³ | 6.0 | high; she relied on the hold and gun deck doubling as living space |
| RN destroyer 1942 | N 220, H1, T 21 d | 1,090 m³ | 5.1 | — |
| Fletcher 1943 (wartime) | N 329, H2, T 30 d | 2,480 m³ | 7.9 | ~30 % of ~7,400 m³. Designed for 273 → crowd 1.2 |
| Iowa 1944 | N 2,700, H2, T 45 d | 20,000 m³ | 8.0 | ~25 % |
| Burke Flt I | N 300, H3, T 45 d | 3,500 m³ | 12.3 | ~15 % |
| Type 45 | N 200, H4, T 45 d | 3,500 m³ | 18.3 | ~12 % |
| Nimitz | N 5,700, H3, T 70 d | 65,000 m³ | 12.4 | ~15 % |

**Calibration knobs:** `a_r` and `k_pass` per standard. If the GA layer finds that destroyers can't fit their crews, lower H2 `a_r` toward 1.1 (the 1965 USN figure was only 7 sq ft walkable per man) before touching anything else.

**Unit-test invariants:**

1. Per-head volume is non-increasing in N at a fixed standard and T.
2. It is strictly increasing across H0 → H5 at fixed N and T.
3. With a distiller, V_water is independent of T_end once T_end > T_buf.
4. `crowd` = 1 and space = 1 gives T_tol = T_ok exactly.

---

## 9. Anchors (sourced)

| fact | value | source |
|---|---|---|
| USN berthing, 1965 standard | 7 sq ft (0.65 m²) net walkable per man on large surface ships; 5 sq ft amphibious troops; 2.5 sq ft submarines. Roosevelt (CVA-42) 8.9 sq ft; Enterprise/America/Kennedy/Nimitz designed to 7. Locker 7.5 ft³ per man (10 proposed) | [USNI Proceedings 1971](https://www.usni.org/magazines/proceedings/1971/january/shipboard-habitability-restricted-areas) |
| USN mess seating (1971 survey) | new ships had only 60 % of required mess seats and 50 % of showers | same |
| USN habitability criteria (OPNAVINST 9640.1A) | max 3 berths per tier (4 in amphibious surge); clearance 20 in crew / 23 in CPO / 25 in officer; mess seats 15–35 % of accommodations; officer seating 60–80 %; WC 1 per 8–30, shower 1 per 10–50, basin 1 per 7–35 by category; recreation space for ⅓ of accommodations; officer staterooms 20–90 sq ft by rank/ship size | [OPNAVINST 9640.1A](https://www.habitability.net/WebData/9640a1.pdf), [NAVSEA T9640-AC-DSP-010](https://www.mscorphab.com/MiscFiles/Shipboard%20Habitability%20Design%20Criteria%20Manual.pdf) |
| RN hammock spacing | 14 in per man; hammocks still in RN destroyers into the late 1950s (bunks on HMS Eastbourne, 1958) | [Fourteen Inches! Memories of the Hammock](https://irishroversbooks.wordpress.com/2015/10/23/fourteen-inches-memories-of-the-hammock/) |
| MLC 2006 (merchant) | single rating cabin 4.0 m² (<3,000 GT) / 4.5 m² (≥3,000 GT); officer 7.5 m²; 2.35 m² per berth in double cabins; berth ≥ 190×68 cm; headroom ≥ 203 cm; 1 WC + basin + shower per 6 without en-suite; hospital required for ≥15 persons on voyages > 3 days | [ShipCalculators MLC summary](https://shipcalculators.com/wiki/marine-crew-accommodation-and-welfare) |
| USS Constitution 1813 | 485 crew, 47,265 US gal water for a cruise intended to last ≥6 months (≈2 L/man/day stored; resupplied en route) | [WP Provisioning of USS Constitution](https://en.wikipedia.org/wiki/Provisioning_of_USS_Constitution) |
| USN provisions | 45-day standard endurance base for stores; milk chill stowage 1,063 ft³ per 1,000 men per 30 days (≈0.001 m³/person-day for milk alone) | [NAVSUP / tpub MMS](https://www.tpub.com/mms/138.htm) |
| Carrier water | Nimitz distils ~400,000 US gal/day (≈1,500 m³/day ≈ 260 L/person-day, incl. non-potable hotel uses) | [19FortyFive](https://www.19fortyfive.com/2026/09/uss-nimitz-makes-400000-gallons-of-fresh-water-a-day-and-in-september-2022-that-water-tasted-like-jp-5-jet-fuel-and-sickened-11-sailors-off-southern-california-after-residue-sat-in-an-unused-tank-for/) |
| Vosper 73 ft MTB | 22 m × 5.9 m × 0.9 m draught, 45–50 t, complement 13 | [WP](https://en.wikipedia.org/wiki/Vosper_73_ft_motor_torpedo_boat) |

**Estimates, not sourced:** the provisions rates `vp` (0.006–0.011 m³/person-day net); water rates for H2–H4 (60/120/180 L); the galley and services exponents; the distiller volume and energy coefficients; the enclosed-volume shares in §8.

---

## 10. Out of scope / later

- Submarines. They need their own table (2.5 sq ft walkable, hot-bunking standard, air revitalisation instead of space).
- Troop/passenger lift as cargo. This would use `b > 1` with a separate austere "troop" standard (5 sq ft walkable, 4-tier bunks).
- Flag staff and air-group detachments as surge blocks with their own standard.
- Climate: tropical service without air conditioning cuts T_ok (H3+ assumes AC; earlier standards suffer ×0.6 in the tropics).
- Women at sea and the resulting mess separation (granularity of berthing blocks). Model it as a +5–10 % sleeping-area penalty if desired.