# Hull structure weight model

*First researched 2026-10-03. Rev 2 added construction technology. **Rev 3 pins every constant and per-ship input so the tables reproduce exactly;** the reference implementation is `claude/hull_weight_ref.py` in this project. It replaces `Weight("Hull structure", …, hull_k * (L*B*D) ** hull_exp)` with `hull_k=0.112`, `hull_exp=1.0`.*

> **Rev 3 note on reproducibility.** The rev 2 tables were produced with two unstated conventions: (1) the calibration ships carried a per-ship superstructure area `A_super` (because their source weights include superstructure), while the Iowa-like and Fletcher-like illustrations used `A_super = 0` (because navarch weighs superstructure separately); (2) the internal deck count, bulkhead count and inner-bottom extent were fixed numbers, listed now in §3.1. With those pinned, `hull_weight_ref.py` reproduces every figure in §4.3 and §5 to the tonne. If a re-implementation lands near 14.1 kt for Iowa-like, it has most likely dropped the armour-deck credit (that case is 14,100 t); near 14.3 kt it has probably also counted 4 internal decks or added superstructure.

## TL;DR

- **The box-volume law has the wrong scaling.**
  - Structural weight grows faster than volume because bigger hulls must resist hull-girder bending.
  - Bending moment grows with Δ·L (about L⁴). Section modulus per mm of plate only grows with about L².
  - So small ships are **minimum-gauge driven** and big ships are **strength driven**. That is why battleships are "more heavily constructed" than destroyers.
- **Technology is the second lever, and it acts mostly on big ships.**
  - Better steel raises the allowable hull-girder stress; welding removes rivet laps and straps. Both shrink the strength-driven part and barely touch the minimum-gauge part.
  - An Iowa-sized hull costs **12,209 t** with 1942 US practice, **14,800 t (+21 %)** with 1914 materials and riveting, **16,309 t (+34 %)** with 1900 mild steel. A Fletcher-sized destroyer varies only 756–886 t across the same span.
- **Recommended: the area × thickness model ("Tier 2") in §3.** Watson–Gilfillan ("Tier 1", §2) is a sanity band only.
- **Calibration:** within ±12 % on consistently booked data (six USN escorts and Bismarck's structural steel); −10 % Hood, −18 % Dreadnought.
- **Recalibration warning:** the old hull term is 30–55 % heavy, so totals will drop (about −4,000 t Iowa-like, −400 t Fletcher-like). Machinery is not affected. See §6.

---

## 1. Why hull_k·L·B·D fails

| Ship | Hull struct. (t) | hull / (L·B·D) |
|---|---|---|
| Claud Jones, Dealey, Bronstein, Garcia, Knox, FFG-7 (USN Group 1, incl. superstructure) | 589–1,351 | 0.072–0.093 |
| Bismarck, structural steel only (all armour excluded) | 10,505 | 0.081 |
| Bismarck, plus outfit groups SII–SIV | 11,902 | 0.091 |
| Hood (strength/protective plating counted as hull) | 14,830 | 0.126 |

The scatter has three causes: **(a) bookkeeping** (RN counted protective plating as hull; German "Schiffskörper" excluded every armour plate); **(b) a box ignores** fineness, deck count, freeboard and superstructure; **(c) a box can't respond** to technology or to armour carrying girder load.

## 2. Tier 1: Watson–Gilfillan E-numeral (sanity check)

```
E   = L(B+T) + 0.85·L(D−T) + 0.85·Σ l1·h1 + 0.75·Σ l2·h2
Cb' = Cb + (1−Cb)·(0.8D − T)/(3T)
W_s = K · E^1.36 · [1 + 0.5·(Cb' − 0.70)]
```

Merchant K is 0.029–0.037. **Fitted K for warship structure without armour ≈ 0.030** (1935–75 practice). Hood and Dreadnought give ~0.047 because protective plating is booked as hull. Tier 1 is technology-blind; flag a design when it and Tier 2 differ by more than 25 % at WWII-era tech.

## 3. Tier 2: area × thickness model — explicit specification

All of §3 is implemented verbatim in `claude/hull_weight_ref.py`. Units: m, m², mm (plate), MPa, kN·m, t.

### 3.1 Inputs

**Per design:**

| Symbol | Meaning | navarch source |
|---|---|---|
| `L` | waterline length | design |
| `B` | max beam | design |
| `D` | depth keel → strength deck, amidships | `T + design_freeboard(L)` |
| `Cb` | block coefficient | design |
| `Δ_full` | full-load displacement | fixed-point loop |
| `n_int` | number of internal (non-strength) decks and platforms | **1** for ≤ ~2,000 t full, **2** for 2,000–10,000 t, **3** for capital ships (see table below) |
| `double_bottom` | inner bottom fitted | **false** for destroyers/escorts, **true** for cruisers and capital ships |
| `A_super` | superstructure plating area | **0 in navarch** (weighed separately at `superstructure_t_per_m2`); non-zero only when matching a source weight that includes superstructure |
| `tech` | technology preset (§4.2) | design / era |
| `arm_deck_mm`, `arm_deck_h` | continuous armour deck thickness and height above keel | `armour_weights()` geometry |
| `f_std` | construction standard | 0.85 light / **1.0** naval / 1.25 robust |

**Constants** (all fitted or fixed; nothing else is free):

| Name | Value | Meaning |
|---|---|---|
| `ρ` | 7.85e-3 t/(m²·mm) | steel |
| `k_s` | **2.5** | framing, stiffeners, minor structure, multiplier on min-gauge plate (fitted) |
| `C_M` | **40** | hogging moment coefficient, `M = Δ·g·L/C_M` (fitted) |
| `f_fit` | **0.10** | brackets, foundations (fitted) |
| `SF` | 2.1 | `σ_eff = σ_y/SF` |
| `σ_cap` | 185 MPa | buckling/fatigue ceiling |
| `t_min` | `(4.0 + 0.03·L)·f_std` mm | minimum gauge |
| shell side factor | 0.90 | `2·0.90·D·L` |
| shell bottom factor | 0.95 | `0.95·B·L·√Cb` |
| `Cwp` | `0.66 + 0.33·Cb` | waterplane coefficient |
| internal deck area factor | 0.85 | each internal deck = 0.85 · A_sdeck |
| internal deck thickness | 0.60 · t_min | |
| bulkhead spacing | 0.06 · L | N_bhd = 1 + 1/0.06 = **17.67**, independent of L |
| bulkhead section factor | 0.75 · B · D | hull section isn't a rectangle |
| bulkhead full-depth fraction | 0.80 | |
| bulkhead thickness | 0.70 · t_min | |
| inner-bottom extent | 0.80 · L (as `B·L·Cb·0.80`) | Hipper 72 %, Bismarck 83 %, Nassau 88 % |
| inner-bottom floors/girders | ×1.60 | |
| superstructure thickness | 0.50 · t_min | only if A_super > 0 |
| girder taper | 0.75 | strength plating area that carries `t_str − t_min` |
| neutral axis | 0.45 · D above keel | |
| armour deck effective width | 0.85 · B | |

### 3.2 Areas (calibration approximations; in the game integrate real sections but keep the deck/bulkhead/bottom factors)

```
A_shell = 2·0.90·D·L + 0.95·B·L·√Cb
A_sdeck = B·L·Cwp
A_int   = n_int · 0.85 · A_sdeck
A_bhd   = 17.67 · 0.75·B·D · 0.80
A_db    = double_bottom ? B·L·Cb·0.80·1.60 : 0
```

### 3.3 Thickness

```
t_min   = (4.0 + 0.03·L) · f_std
σ_eff   = min(σ_y(tech) / 2.1, 185)
M       = Δ_full · 9.81 · L / 40                              [kN·m]
I_req   = M / (σ_eff · 1000) · (D/2)                          [m⁴]
I_arm   = 0.85·B · (arm_deck_mm/1000) · (arm_deck_h − 0.45·D)²  [m⁴]   (0 if no armour deck)
Z_per_mm= D · (B + D/3) / 1000                                 [m³ per mm of smeared plate]
t_str   = max(0, I_req − I_arm) / (D/2) / Z_per_mm             [mm]
```

### 3.4 Weight

```
W_min  = ρ · k_s · [ (A_shell + A_sdeck)·t_min
                     + A_int · 0.60·t_min
                     + A_bhd · 0.70·t_min
                     + A_db · t_min
                     + A_super · 0.50·t_min ]
W_str  = ρ · 0.75 · (A_shell + A_sdeck) · max(0, t_str − t_min)
W_hull = (W_min + W_str) · (1 + 0.10) · f_join(tech)
```

### 3.5 Worked example — Iowa-like, `sts_weld_1942`

Inputs: L 262, B 33, D 16.5, Cb 0.59, Δ_full 57,500, n_int 3, double bottom, A_super 0, armour deck 150 mm at 11.5 m.

| Step | Value |
|---|---|
| Cwp | 0.8547 |
| A_shell / A_sdeck / A_int / A_bhd / A_db | 14,090 / 7,390 / 18,844 / 5,772 / 6,529 m² |
| t_min | 11.86 mm |
| σ_eff | min(420/2.1, 185) = 185 MPa |
| M | 57,500·9.81·262/40 = 3,694,691 kN·m |
| I_req | 3,694,691/185,000 · 8.25 = 164.8 m⁴ |
| I_arm | 0.85·33·0.150·(11.5 − 7.425)² = 69.9 m⁴ |
| Z_per_mm | 16.5·(33 + 5.5)/1000 = 0.6353 m³/mm |
| t_str | (164.8 − 69.9)/8.25/0.6353 = 18.1 mm |
| W_min | 7.85e-3·2.5·[21,480·11.86 + 18,844·7.12 + 5,772·8.30 + 6,529·11.86] = 5,000 + 2,632 + 940 + 1,520 = **10,091 t** |
| W_str | 7.85e-3·0.75·21,480·(18.1 − 11.86) = **790 t** |
| W_hull | 10,881 · 1.10 · 1.02 = **12,209 t** |

Same inputs with `arm_deck_mm = 0`: t_str 31.4 mm, W_str 2,476 t, W_hull 14,100 t.

## 4. Construction technology

### 4.1 What changed, with evidence

| Development | When | Effect on hull weight | Evidence |
|---|---|---|---|
| **Mild steel** replaces wrought iron | 1875–1890 | Baseline. Yield ~35 ksi (≈240 MPa), UTS ~60 ksi. | [NavWeaps forum](https://www.tapatalk.com/groups/warships1discussionboards/mild-steel-hts-and-sts-properties-t10418.html) |
| **Admiralty "HT" steel** | ~1900 on (destroyers, then strength decks and sheer strakes of big ships) | Higher allowable stress where used. Riveted HTS saved about as much as welding mild steel. | [Ducol (Wiki)](https://en.wikipedia.org/wiki/Ducol); same forum |
| **USN HTS** | 1920s–40s; "liberally applied in all American treaty battleship construction" | Yield ~47–53 ksi (≈325–365 MPa) | [forum](https://www.tapatalk.com/groups/warships1discussionboards/mild-steel-hts-and-sts-properties-t10418.html), [generalstaff](https://www.generalstaff.org/BBOW/NAV/Sub_Hull_Materials.htm) |
| **"D" steel / Ducol** | early 1920s on: Nelson/Rodney, KGV, Ark Royal; IJN Nagato refit, Takao, Mogami, Yamato, Shōkaku | Tougher HT steel. Cited as a weight saver on Nelson/Rodney (not quantified). "Type D" yield ≈390–440 MPa. | [Ducol (Wiki)](https://en.wikipedia.org/wiki/Ducol), [generalstaff](https://www.generalstaff.org/BBOW/NAV/Sub_Hull_Materials.htm) |
| **St 52** (Germany) | 1930s | Yield ≈355 MPa | [generalstaff](https://www.generalstaff.org/BBOW/NAV/Sub_Hull_Materials.htm) |
| **STS** (USN homogeneous Ni-Cr armour steel) | ~1930–45, "virtually every class" | Yield 75–85 ksi (520–590 MPa). **Structure and protection at once**: Iowa's outer hull is 60 lb (1.5 in) STS; splinter decks are STS. Not dead weight. | [STS (Wiki)](https://en.wikipedia.org/wiki/Special_treatment_steel), [Naval Gazing Armor 4](https://www.navalgazing.net/Armor-Part-4) |
| **Welding** | Partial from ~1930. Deutschland class >90 % welded. | **−15 % hull weight** on Deutschland (included redesign). HMS Seagull (1937, all-welded) 313 t vs riveted sister Leda 338 t, **plating unchanged: −7.4 %**. | [Deutschland (Wiki)](https://en.wikipedia.org/wiki/Deutschland-class_cruiser), [Nature 1939](https://www.nature.com/articles/144322d0) |
| **Welding risk / too-light structure** | IJN 1930s | Hatsuharu saved 66.5 t of hull vs Fubuki; after the Fourth Fleet Incident (1935) rebuilt **+54 t**. | [Hatsuharu (Wiki)](https://en.wikipedia.org/wiki/Hatsuharu-class_destroyer) |
| **HY-80** | 1950s+ | Yield 80 ksi (550 MPa). Surface hulls gain little beyond the buckling/fatigue cap. | [HY-80 (Wiki)](https://en.wikipedia.org/wiki/HY-80) |

Two physical points: **higher yield only pays where the hull is strength driven** (minimum gauge and buckling don't improve, since E is the same for all steels), and **joining is a flat multiplier on all structure**.

### 4.2 Technology presets

`σ_y` is the yield of the girder steel *mix* (HT/STS in strength deck and sheer strake, mild steel elsewhere). `σ_eff = min(σ_y/2.1, 185)`.

| Preset | Era | σ_y mix (MPa) | σ_eff | f_join |
|---|---|---|---|---|
| `iron_1880` | ≤1885 | 190 | 90.5 | 1.12 |
| `ms_riv_1900` | 1885–1905 | 235 | 111.9 | 1.10 |
| `ht_riv_1914` | 1905–1920: mild-steel hull, HT strength deck | 290 | 138.1 | 1.10 |
| `hts_riv_1925` | 1920–35: D/Ducol/USN HTS | 340 | 161.9 | 1.08 |
| `hts_mix_1937` | 1933–42: riveted shell, welded internals | 350 | 166.7 | 1.04 |
| `sts_weld_1942` | 1940–45 USN: HTS + structural STS | 420 | 185 (cap) | 1.02 |
| `weld_1945` | 1943+: all-welded HTS/mild steel | 350 | 166.7 | 1.00 |
| `hy80_1960` | 1955+ | 420 | 185 (cap) | 1.00 |

Uncalibrated knobs: **`f_std`** (0.85/1.0/1.25, scales t_min only; light construction should cost structural HP or seaworthiness risk) and an **early-welding defect chance** (pre-1937 IJN/Germany) that triggers a +5–10 % strengthening-refit penalty.

### 4.3 Result: same hull, different technology (A_super = 0)

**Iowa-like** (L 262, B 33, D 16.5, Cb 0.59, 57,500 t full, n_int 3, double bottom; 150 mm deck at 11.5 m):

| Preset | σ_eff | W_hull (t) | vs 1942 | t_str mm | W_min | W_str | Without deck credit |
|---|---|---|---|---|---|---|---|
| iron_1880 | 90 | 18,523 | +52 % | 51.0 | 10,091 | 4,944 | 20,600 |
| ms_riv_1900 | 112 | 16,309 | +34 % | 38.6 | 10,091 | 3,387 | 18,349 |
| ht_riv_1914 | 138 | 14,800 | +21 % | 28.8 | 10,091 | 2,140 | 16,840 |
| hts_riv_1925 | 162 | 13,601 | +11 % | 22.6 | 10,091 | 1,357 | 15,604 |
| hts_mix_1937 | 167 | 12,948 | +6 % | 21.6 | 10,091 | 1,227 | 14,877 |
| **sts_weld_1942** | 185 | **12,209** | 0 | 18.1 | 10,091 | 790 | 14,100 |
| weld_1945 | 167 | 12,450 | +2 % | 21.6 | 10,091 | 1,227 | 14,305 |
| hy80_1960 | 185 | 11,969 | −2 % | 18.1 | 10,091 | 790 | 13,824 |

**Fletcher-like** (L 114.7, B 12, D 7, Cb 0.50, 2,900 t full, n_int 1, no double bottom): W_min = 687 t in every case; t_min 7.4 mm.

| Preset | t_str mm | W_str | W_hull (t) |
|---|---|---|---|
| iron_1880 | 9.0 | 32 | 886 |
| ms_riv_1900 / ht_riv_1914 | 7.3 / 5.9 | 0 | 832 |
| hts_riv_1925 | 5.0 | 0 | 817 |
| hts_mix_1937 | 4.9 | 0 | 786 |
| sts_weld_1942 | 4.4 | 0 | 771 |
| weld_1945 / hy80_1960 | 4.9 / 4.4 | 0 | 756 |

## 5. Calibration

Every input in this table is in `CAL` in `hull_weight_ref.py`. Escort actuals are USN Group 1 (includes superstructure), hence non-zero A_super. Weights in tonnes.

| Ship | L | B | D | Cb | Δ_full | n_int | DB | A_super | Preset | Arm deck | Actual | Tier 2 | err | σ_eff | t_str | t_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| FFG-7 | 124.4 | 13.78 | 9.14 | 0.47 | 3,730 | 2 | no | 1,300 | weld_1945 | – | 1,277 | 1,264 | −1 % | 167 | 4.4 | 7.7 |
| Knox | 126.5 | 13.96 | 8.63 | 0.47 | 4,080 | 2 | no | 1,200 | weld_1945 | – | 1,351 | 1,265 | −6 % | 167 | 5.2 | 7.8 |
| Garcia | 118.9 | 13.38 | 9.14 | 0.47 | 3,525 | 2 | no | 1,100 | weld_1945 | – | 1,140 | 1,155 | +1 % | 167 | 4.1 | 7.6 |
| Bronstein | 106.7 | 12.04 | 8.78 | 0.47 | 2,600 | 2 | no | 900 | weld_1945 | – | 814 | 913 | +12 % | 167 | 3.1 | 7.2 |
| Dealey | 93.9 | 11.09 | 6.25 | 0.47 | 1,907 | 1 | no | 500 | weld_1945 | – | 605 | 556 | −8 % | 167 | 3.2 | 6.8 |
| Claud Jones | 91.7 | 11.77 | 6.49 | 0.47 | 1,720 | 1 | no | 500 | weld_1945 | – | 589 | 571 | −3 % | 167 | 2.6 | 6.8 |
| Bismarck | 241.6 | 36.0 | 15.0 | 0.56 | 50,900 | 3 | yes | 3,000 | hts_mix_1937 | 100 mm @ 10.5 m | 10,505 | 12,063 | +15 % | 167 | 20.1 | 11.2 |
| Hood | 246.9 | 31.7 | 15.0 | 0.57 | 46,680 | 3 | yes | 3,000 | hts_riv_1925 | – | 14,830 | 13,275 | −10 % | 162 | 31.7 | 11.4 |
| Dreadnought (recalled) | 160.6 | 25.0 | 13.4 | 0.60 | 21,800 | 3 | yes | 1,500 | ht_riv_1914 | – | 6,198 | 5,085 | −18 % | 138 | 15.7 | 8.8 |

**Firmness:** escort data is firm (SNAME tables, D given). Bismarck's hull weight is firm but D and T are estimates. Hood is a percentage of load displacement. Dreadnought is recalled from D.K. Brown and unverified. The pre-1920 presets rest on one recalled ship plus physics. Best next step: 3–5 print-only points (Iowa, KGV, a Treaty cruiser, a riveted WWI destroyer) from Friedman, Brown, Raven & Roberts or Garzke & Dulin.

## 6. Integration notes for navarch.py

1. **Replace** the "Hull structure" Weight with `W_hull`. TUNING keys: `hull_ks=2.5`, `hull_cm=40`, `hull_fit=0.10`, `hull_sf=2.1`, `hull_sig_cap=185`, plus the geometry factors in §3.1 if you want them tunable. Add design key `"tech"`, defaulting by era/nation (`de` + `era: 1914` → `ht_riv_1914`).
2. **A_super = 0.** Superstructure is already weighed at `superstructure_t_per_m2`.
3. **`n_int` and `double_bottom`** can come from the layout (deck count below the strength deck; inner bottom present for cruisers and up) or from the Δ thresholds in §3.1.
4. **Armour stays in `armour_weights()`.** Pass only the continuous armour deck's I_arm into the strength step; don't move weight between groups.
5. **Δ_full is already inside the fixed-point loop**; W_str is weakly coupled, convergence unaffected.
6. **D from `design_freeboard`** now matters more (t_str ∝ 1/D roughly). Consider exposing freeboard to the player.
7. **Recalibration (machinery untouched).** Totals drop by roughly 25–30 % of the old hull weight. Re-check in order: protective/structural plating no group models today (STS shell, splinter decks, torpedo bulkheads: add as area × thickness to the armour model or as a `t_prot` layer here); `misc_frac` (0.055 looks low; Bismarck's outfit alone was 13 % of hull); `superstructure_t_per_m2`.
8. **By-product:** σ_eff, t_str and I_arm give a hull-girder margin for the damage model (strength-deck or armour-deck loss → breaking-in-two).

## Sources

- Garzke & Kerr, "Major Factors in Frigate Design", SNAME Trans. 89 (1981): [PDF](https://www.naval.com.br/blog/wp-content/uploads/2025/12/Major-Factors-in-Frigate-Design.pdf)
- Bismarck weight statement: [kbismarck.com](https://www.kbismarck.com/bsweights.html)
- Hood weight percentages (ASNE Journal XXXII): [hmshood.org.uk](https://www.hmshood.org.uk/reference/written/asnejournal32.htm)
- E.J. King, USNI Proceedings, Mar 1919: [usni.org](https://www.usni.org/magazines/proceedings/1919/march/some-ideas-about-effects-increasing-size-battleships)
- Special treatment steel: [Wikipedia](https://en.wikipedia.org/wiki/Special_treatment_steel) · Ducol: [Wikipedia](https://en.wikipedia.org/wiki/Ducol) · HY-80: [Wikipedia](https://en.wikipedia.org/wiki/HY-80)
- Mild steel, HTS and STS properties: [NavWeaps forum p.1](https://www.tapatalk.com/groups/warships1discussionboards/mild-steel-hts-and-sts-properties-t10418.html), [p.2](https://www.tapatalk.com/groups/warships1discussionboards/mild-steel-hts-and-sts-properties-t10418-s10.html)
- Hull steel yield table: [generalstaff.org](https://www.generalstaff.org/BBOW/NAV/Sub_Hull_Materials.htm)
- Iowa STS shell: [Naval Gazing, Armor Part 4](https://www.navalgazing.net/Armor-Part-4)
- Deutschland-class welding: [Wikipedia](https://en.wikipedia.org/wiki/Deutschland-class_cruiser) · HMS Seagull vs Leda: [Nature 144, 322 (1939)](https://www.nature.com/articles/144322d0) · Hatsuharu: [Wikipedia](https://en.wikipedia.org/wiki/Hatsuharu-class_destroyer)
- Watson–Gilfillan summary: [slideshare](https://www.slideshare.net/slideshow/preliminary-shipdesign/74998098)
- Not reached: ASSET/Straubinger SWBS-100 WERs (DTIC blocked), SpringSharp's internal method, RN design stress tables (print only).