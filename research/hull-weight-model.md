# Hull structure weight model

*First researched 2026-10-03. Revision 2 adds construction technology (materials and joining) and integration notes for `navarch.py`. It replaces `Weight("Hull structure", …, hull_k * (L*B*D) ** hull_exp)` with `hull_k=0.112`, `hull_exp=1.0`.*

## TL;DR

- **The box-volume law has the wrong scaling.**
  - Structural weight grows faster than volume because bigger hulls must resist hull-girder bending.
  - Bending moment grows with Δ·L (about L⁴). Section modulus per mm of plate only grows with about L².
  - So small ships are **minimum-gauge driven**: their plate is as thin as handling, corrosion and local loads allow. Big ships are **strength driven**.
  - That is why battleships are "more heavily constructed" than destroyers.
- **Technology is the second lever, and it acts mostly on big ships.**
  - Better steel raises the allowable hull-girder stress. Better joining (welding instead of riveting) removes laps and straps.
  - Both shrink the strength-driven part. They barely touch the minimum-gauge part.
  - An Iowa-sized hull costs about **12,200 t** with 1942 US practice (HTS + structural STS, increasingly welded). It costs **~14,800 t (+21 %)** with 1914 materials and riveting, and **~16,300 t (+34 %)** with 1900 mild steel. A Fletcher-sized destroyer only varies by about ±8 % across the same span.
- **Recommended: an area × thickness model ("Tier 2").**
  - Inputs are areas from the real hull geometry. Thickness is the larger of a minimum gauge and a longitudinal-strength requirement.
  - The material sets the stress and the joining method sets a weight multiplier. Armour decks get strength credit.
  - Use the Watson–Gilfillan E-numeral ("Tier 1") only as a sanity band.
- **Calibration:** within ±12 % on consistently booked data (six USN escorts and Bismarck's structural steel), with ±10–18 % on Hood and Dreadnought.
- **Recalibration warning:** the old hull term is 30–55 % heavy, so totals will drop.
  - Expect about −4,000 t on an Iowa-like design and −400 t on a Fletcher-like one.
  - Machinery is not affected. See §6 for what needs re-checking.

---

## 1. Why hull_k·L·B·D fails

| Ship | Hull struct. (t) | hull / (L·B·D) |
|---|---|---|
| Claud Jones, Dealey, Bronstein, Garcia, Knox, FFG-7 (USN Group 1, incl. superstructure) | 589–1,351 | 0.072–0.093 |
| Bismarck, structural steel only (all armour excluded) | 10,505 | 0.081 |
| Bismarck, plus outfit groups SII–SIV | 11,902 | 0.091 |
| Hood (strength/protective plating counted as hull) | 14,830 | 0.126 |

The scatter has three causes:

- **(a) Bookkeeping.** The RN counted protective plating as hull. The German "Schiffskörper" excluded every armour plate.
- **(b) A box ignores** fineness, deck count, freeboard and superstructure.
- **(c) A box can't respond to technology or armour.** It has no way to model armour carrying hull-girder load.

## 2. Tier 1: Watson–Gilfillan E-numeral (sanity check)

```
E   = L(B+T) + 0.85·L(D−T) + 0.85·Σ l1·h1 + 0.75·Σ l2·h2
        l1,h1 = full-width erections, l2,h2 = deckhouses
Cb' = Cb + (1−Cb)·(0.8D − T)/(3T)
W_s = K · E^1.36 · [1 + 0.5·(Cb' − 0.70)]
```

- **Merchant K values** are 0.029–0.037.
- **Fitted K for warship structure without armour** is **≈ 0.030**, valid for 1935–75 practice (escorts 0.025–0.030, Bismarck 0.031).
- **Hood and Dreadnought give ~0.047** because protective plating is booked as hull.
- **Tier 1 is technology-blind.** Use it as a band check only: flag a design when it and Tier 2 differ by more than 25 % for WWII-era tech.

## 3. Tier 2: area × thickness model (recommended)

### 3.1 Geometry inputs (integrate real sections from geometry.py)

| Symbol | Meaning |
|---|---|
| `A_shell` | Shell area from keel to strength deck (∫ girth dx) |
| `A_sdeck` | Strength (upper) deck area |
| `A_int` | Internal decks and platforms, Σ area |
| `A_bhd` | Transverse bulkheads, Σ section area. Subdivision gives one about every 0.055–0.06 L. |
| `A_db` | Inner-bottom area × 1.6 (floors and girders). Use 0 for a single bottom. |
| `A_super` | Superstructure plating. **Set to 0 in navarch.** Superstructure is already weighed there at `superstructure_t_per_m2`. |
| `L, B, D, Δ_full` | D is the depth to the strength deck (navarch: `T + design_freeboard(L)`) |

Box-free approximations were used for calibration only:

```
A_shell ≈ 2·0.90·D·L + 0.95·B·L·√Cb
A_sdeck ≈ B·L·Cwp,  Cwp ≈ 0.66 + 0.33·Cb
A_int   ≈ n_int · 0.85 · A_sdeck
A_bhd   ≈ (1 + 1/0.06) · 0.75·B·D · 0.8
```

### 3.2 Thickness

```
t_min  [mm] = (4.0 + 0.03·L) · f_std                 # minimum gauge

σ_eff  [MPa] = min(σ_y / 2.1, 185)                   # material → allowable girder stress (§4)
M      [kN·m] = Δ_full · 9.81 · L / C_M              # C_M = 40 (fitted; hogging incl. standard wave)
I_req  [m⁴]   = M / (σ_eff·1000) · D/2
I_arm  [m⁴]   = Σ continuous armour decks: 0.85·B_deck·t_a·(h_a − 0.45·D)²
t_str  [mm]   = max(0, I_req − I_arm) / (D/2) / (D·(B + D/3)) · 1000
```

The 185 MPa cap stands for buckling and fatigue. Elastic modulus is the same for every steel, so compression panels don't get stronger with higher-yield steel.

### 3.3 Weight (t; A in m², t in mm)

```
W_min  = 7.85e-3 · k_s · [ (A_shell+A_sdeck)·t_min + A_int·0.6·t_min
                           + A_bhd·0.7·t_min + A_db·t_min + A_super·0.5·t_min ]
W_str  = 7.85e-3 · 0.75 · (A_shell+A_sdeck) · max(0, t_str − t_min)
W_hull = (W_min + W_str) · (1 + f_fit) · f_join
```

The fitted constants are:

- **k_s = 2.5.** Framing and stiffeners plus minor structure.
- **f_fit = 0.10.** Brackets and foundations.
- **f_join** comes from the technology preset (§4).

## 4. Construction technology

### 4.1 What changed, with evidence

| Development | When | Effect on hull weight | Evidence |
|---|---|---|---|
| **Mild steel** replaces wrong iron | 1875–1890 | Baseline. Yield ~35 ksi (≈240 MPa), UTS ~60 ksi. | [NavWeaps forum](https://www.tapatalk.com/groups/warships1discussionboards/mild-steel-hts-and-sts-properties-t10418.html) |
| **Admiralty "HT" (high-tensile) steel** | ~1900 on (destroyers, then strength decks and sheer strakes of big ships) | Higher allowable stress where used. Riveted HTS saved about as much as welding mild steel did. | [Ducol (Wiki)](https://en.wikipedia.org/wiki/Ducol); same forum |
| **USN HTS** | 1920s–40s; "liberally applied in all American treaty battleship construction" | Yield ~47–53 ksi (≈325–365 MPa) | [forum](https://www.tapatalk.com/groups/warships1discussionboards/mild-steel-hts-and-sts-properties-t10418.html), [generalstaff](https://www.generalstaff.org/BBOW/NAV/Sub_Hull_Materials.htm) |
| **"D" steel / Ducol (D.W.)** | early 1920s on: Nelson/Rodney, KGV, Ark Royal; IJN Nagato refit, Takao, Mogami, Yamato, Shōkaku | Tougher HT steel. Cited as a weight saver on Nelson/Rodney (not quantified). "Type D" yield ≈390–440 MPa. | [Ducol (Wiki)](https://en.wikipedia.org/wiki/Ducol), [generalstaff](https://www.generalstaff.org/BBOW/NAV/Sub_Hull_Materials.htm) |
| **St 52** (Germany) | 1930s | Yield ≈355 MPa | [generalstaff](https://www.generalstaff.org/BBOW/NAV/Sub_Hull_Materials.htm) |
| **STS** (Special Treatment Steel, USN homogeneous Ni-Cr armour steel) | ~1930–45, "virtually every class" | Yield 75–85 ksi (520–590 MPa). Used as **structure and protection at once**: Iowa's outer hull is 60 lb (1.5 in) STS and its splinter decks are STS. Unlike armour plate, it is not dead weight. | [STS (Wiki)](https://en.wikipedia.org/wiki/Special_treatment_steel), [Naval Gazing Armor 4](https://www.navalgazing.net/Armor-Part-4) |
| **Welding** | Partial from about 1930. Deutschland class (1929–34) >90 % welded. | **−15 % hull weight** on Deutschland, which included redesign. HMS Seagull (1937, all-welded) launched at 313 t against riveted sister Leda's 338 t with **plating thickness unchanged: −7.4 %**. | [Deutschland (Wiki)](https://en.wikipedia.org/wiki/Deutschland-class_cruiser), [Nature 1939](https://www.nature.com/articles/144322d0) |
| **Welding risk / too-light structure** | IJN 1930s | Hatsuharu saved 66.5 t of hull vs Fubuki with early electric welding and lightening. After the Fourth Fleet Incident (1935, typhoon tore bows off Fubukis) the ships were rebuilt **+54 t**. | [Hatsuharu (Wiki)](https://en.wikipedia.org/wiki/Hatsuharu-class_destroyer) |
| **HY-80** | 1950s+ (subs first; surface combatants later and selectively) | Yield 80 ksi (550 MPa). Surface hulls gain little beyond the buckling/fatigue cap. | [HY-80 (Wiki)](https://en.wikipedia.org/wiki/HY-80), [generalstaff](https://www.generalstaff.org/BBOW/NAV/Sub_Hull_Materials.htm) |

Two key physical points:

- **Higher yield only pays where the hull is strength driven.** That means the midship girder of long, heavy ships. Minimum gauge (corrosion, handling, local loads, slamming) and buckling (same elastic modulus for all steels) don't improve. This matches history: destroyers adopted HT steel early, but their hulls didn't get dramatically lighter, while capital ships gained a lot.
- **Joining is a flat multiplier on all structure.** Rivets need lapped seams, butt straps and heads. Welding removes them.

### 4.2 Technology presets (game parameters)

`σ_y` is the effective yield of the girder steel *mix*: ships used HT/STS mostly in the strength deck, sheer strake and protective layers, with mild steel elsewhere. `σ_eff = min(σ_y/2.1, 185)`. With the 2.1 factor, mild steel lands at about 112 MPa, close to the RN's traditional ~8 tons/in² for mild steel (≈124 MPa; this figure is from memory and unverified).

| Preset | Era | σ_y mix (MPa) | σ_eff | f_join |
|---|---|---|---|---|
| `iron_1880` | ≤1885 | 190 | 90 | 1.12 |
| `ms_riv_1900` | 1885–1905 | 235 | 112 | 1.10 |
| `ht_riv_1914` | 1905–1920: mild steel hull, HT strength deck | 290 | 138 | 1.10 |
| `hts_riv_1925` | 1920–35: D/Ducol/USN HTS | 340 | 162 | 1.08 |
| `hts_mix_1937` | 1933–42: riveted shell, welded internals | 350 | 167 | 1.04 |
| `sts_weld_1942` | 1940–45 USN: HTS + structural STS | 420 | 185 (cap) | 1.02 |
| `weld_1945` | 1943+: all-welded HTS/mild steel | 350 | 167 | 1.00 |
| `hy80_1960` | 1955+ | 420 | 185 (cap) | 1.00 |

Two further knobs need more data before they can be calibrated:

- **`f_std` (construction standard).** Light 0.85, naval 1.0, robust 1.25. It scales t_min only. Light construction should cost structural hit points or fatigue/seaworthiness risk (Fourth Fleet Incident).
- **Early welding** (pre-1937, IJN/Germany): it could carry a defect chance that triggers a "strengthening refit" weight penalty of about +5–10 % of hull.

### 4.3 Result: same hull, different technology

**Iowa-like** (L 262, B 33, D 16.5, Cb 0.59, 57,500 t full; 150 mm armour deck credited at 11.5 m):

| Preset | σ_eff | W_hull (t) | vs 1942 | t_str mm | Without deck credit |
|---|---|---|---|---|---|
| iron_1880 | 90 | 18,523 | +52 % | 51 | 20,600 |
| ms_riv_1900 | 112 | 16,309 | +34 % | 39 | 18,349 |
| ht_riv_1914 | 138 | 14,800 | +21 % | 29 | 16,840 |
| hts_riv_1925 | 162 | 13,601 | +11 % | 23 | 15,604 |
| hts_mix_1937 | 167 | 12,948 | +6 % | 22 | 14,877 |
| **sts_weld_1942** | 185 | **12,209** | 0 | 18 | 14,100 |
| hy80_1960 | 185 | 11,969 | −2 % | 18 | 13,824 |

**Fletcher-like** (L 114.7, B 12, D 7, 2,900 t full):

- **Result:** 886 t (1880), 832 t (1900–1914), 786 t (1937), 756–771 t (1942+).
- **Why so little change:** t_str (4–9 mm) sits at or below t_min (7.4 mm), so only the joining factor and the earliest steels matter.

## 5. Calibration

Constants: k_s 2.5, C_M 40, f_fit 0.10. Weights are in tonnes.

| Ship | Preset | Actual | Tier 2 | err | σ_eff | t_str | t_min |
|---|---|---|---|---|---|---|---|
| FFG-7 | weld_1945 | 1,277 | 1,264 | −1 % | 167 | 4 | 7.7 |
| Knox | weld_1945 | 1,351 | 1,265 | −6 % | 167 | 5 | 7.8 |
| Garcia | weld_1945 | 1,140 | 1,155 | +1 % | 167 | 4 | 7.6 |
| Bronstein | weld_1945 | 814 | 913 | +12 % | 167 | 3 | 7.2 |
| Dealey | weld_1945 | 605 | 556 | −8 % | 167 | 3 | 6.8 |
| Claud Jones | weld_1945 | 589 | 571 | −3 % | 167 | 3 | 6.8 |
| Bismarck (100 mm deck credit) | hts_mix_1937 | 10,505 | 12,063 | +15 % | 167 | 20 | 11.2 |
| Hood | hts_riv_1925 | 14,830 | 13,275 | −10 % | 162 | 32 | 11.4 |
| Dreadnought (recalled, unverified) | ht_riv_1914 | 6,198 | 5,085 | −18 % | 138 | 16 | 8.8 |

**How firm each data point is:**

- **The escort data is firm.** It comes from SNAME tables with D given, and it includes superstructure, so A_super was used in the fit.
- **Bismarck's hull weight is firm, but its D and T are estimates.**
- **Hood is a percentage** of load displacement.
- **The Dreadnought legend is recalled from D.K. Brown** and was not found online.
- **The pre-1920 points are the weakest part of the fit.** The early-era multipliers rest on one recalled ship plus physics.
- **More capital-ship data is in print only.** The best next step is 3–5 points from Friedman, Brown's *Nelson to Vanguard*, Raven & Roberts, or Garzke & Dulin: Iowa, KGV, a Treaty cruiser, a riveted WWI destroyer.

## 6. Integration notes for navarch.py

1. **Replace** the "Hull structure" Weight with `W_hull`.
   - Add the TUNING keys `hull_ks=2.5`, `hull_cm=40`, `hull_fit=0.10`, `hull_sf=2.1`, `hull_sig_cap=185`.
   - Add a design key `"tech": "<preset>"`. It defaults by year or nation style; for example, `de` with `era: 1914` maps to `ht_riv_1914`.
2. **Set A_super = 0.** Superstructure is already weighed (`superstructure_t_per_m2`).
3. **Armour stays where it is** (`armour_weights()`). Only pass the deck armour's I_arm into the strength calculation. Don't move any weight between groups.
4. **Δ_full is already inside the 60-step fixed-point loop**, so no structural change is needed. W_str is weakly coupled, so convergence is unaffected.
5. **D still comes from `design_freeboard`.** Hull weight is now more sensitive to D through t_str, so a deep hull costs more and is stiffer. Consider exposing freeboard to the player.
6. **Recalibration (machinery untouched).** Totals will drop by roughly 25–30 % of the old hull weight. Candidates to re-check, in order:
   - **Protective/structural plating not modelled anywhere.** This covers STS outer shell, splinter decks and torpedo-bulkhead plating that `armour_weights()` doesn't include. In USN booking it was hull or "protection". Either add it to the armour model as area × thickness, or add a `t_prot` layer in Tier 2.
   - **`misc_frac` (0.055).** It is plausibly low for full outfit. Bismarck's outfit groups alone were 13 % of hull weight.
   - **`superstructure_t_per_m2`.**
7. **Free by-product: hull-girder margin.** σ_eff, t_str and I_arm give a margin for the damage model. Losing strength-deck or armour-deck area reduces I, which allows breaking-in-two events (Hood, Fubuki bows).

## Sources

- Garzke & Kerr, "Major Factors in Frigate Design", SNAME Trans. 89 (1981): [PDF](https://www.naval.com.br/blog/wp-content/uploads/2025/12/Major-Factors-in-Frigate-Design.pdf)
- Bismarck weight statement: [kbismarck.com](https://www.kbismarck.com/bsweights.html)
- Hood weight percentages (ASNE Journal XXXII): [hmshood.org.uk](https://www.hmshood.org.uk/reference/written/asnejournal32.htm)
- E.J. King, USNI Proceedings, Mar 1919: [usni.org](https://www.usni.org/magazines/proceedings/1919/march/some-ideas-about-effects-increasing-size-battleships)
- Special treatment steel: [Wikipedia](https://en.wikipedia.org/wiki/Special_treatment_steel)
- Ducol / D.W. steel: [Wikipedia](https://en.wikipedia.org/wiki/Ducol)
- HY-80: [Wikipedia](https://en.wikipedia.org/wiki/HY-80)
- Mild steel, HTS and STS properties: [NavWeaps forum p.1](https://www.tapatalk.com/groups/warships1discussionboards/mild-steel-hts-and-sts-properties-t10418.html), [p.2](https://www.tapatalk.com/groups/warships1discussionboards/mild-steel-hts-and-sts-properties-t10418-s10.html)
- Hull steel yield table: [generalstaff.org](https://www.generalstaff.org/BBOW/NAV/Sub_Hull_Materials.htm)
- Iowa STS shell and belt backing: [Naval Gazing, Armor Part 4](https://www.navalgazing.net/Armor-Part-4)
- Deutschland-class welding (−15 %): [Wikipedia](https://en.wikipedia.org/wiki/Deutschland-class_cruiser)
- HMS Seagull all-welded vs Leda: [Nature 144, 322 (1939)](https://www.nature.com/articles/144322d0)
- Hatsuharu weight saving and strengthening: [Wikipedia](https://en.wikipedia.org/wiki/Hatsuharu-class_destroyer)
- Watson–Gilfillan summary: [slideshare](https://www.slideshare.net/slideshow/preliminary-shipdesign/74998098)
- Not reached: ASSET/Straubinger SWBS-100 weight estimating relationships (DTIC, blocked), SpringSharp's internal method, RN design stress tables (print only).