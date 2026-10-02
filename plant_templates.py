#!/usr/bin/env python3
"""
plant_templates: writes the example tech blocks of plant-templates.md (everything from its first year heading on)
from the technology tables of research/powerplant-model.md. Edit the tables or the year list here and rerun:

    python plant_templates.py

Each block is the tech as a navy would have it in that year: values eased by maturity, 1 - (1 - m)^2, with m from
0 at the tech's introduction to 1 at maturity. ST7 and ST8 densities are raised from the spec's 0.34 and 0.36 to 0.42
and 0.44, which brings 1935-45 machinery lengths within the spec's +-20% of the old length formula (its section 2
calibration note).
"""
import json
import re

T = {
 "ST2": dict(name="Compound engines, cylindrical (Scotch) boilers", years=(1865, 1885), fuel="coal", sfc=(1800, 1350), w=(260, 200), floor=0.75, rho=0.24, umax=(2, 5), ref=(3, 5.5, 4.5, 6), bf=0.6, crew=40, curve="REC", nat=0.55),
 "ST3": dict(name="Triple expansion, Scotch boilers", years=(1885, 1900), fuel="coal", sfc=(1250, 1050), w=(190, 150), floor=0.75, rho=0.26, umax=(4, 9), ref=(5, 7.5, 4.5, 9), bf=0.6, crew=38, curve="REC", nat=0.6),
 "ST4": dict(name="Triple expansion, large-tube water-tube boilers", years=(1893, 1910), fuel="coal", sfc=(1050, 930), w=(150, 115), floor=0.45, rho=0.28, umax=(6, 12), ref=(5, 7.5, 4.5, 9), bf=0.55, crew=34, curve="REC", nat=0.7),
 "ST5": dict(name="Direct-drive turbines, water-tube boilers", years=(1905, 1918), fuel="coal", sfc=(950, 800), w=(120, 95), floor=0.35, rho=0.30, umax=(8, 20), ref=(10, 4.5, 4.5, 7), bf=0.6, crew=30, curve="DT", nat=0.8),
 "ST6": dict(name="Geared turbines, oil-fired small-tube boilers", years=(1915, 1930), fuel="oil", sfc=(520, 430), w=(75, 52), floor=0.42, rho=0.32, umax=(15, 35), ref=(15, 4.5, 4.5, 8), bf=0.55, crew=12, curve="GTB"),
 "ST7": dict(name="High-pressure geared turbines", years=(1930, 1945), fuel="oil", sfc=(420, 340), w=(45, 34), floor=0.5, rho=0.42, umax=(25, 45), ref=(30, 5.0, 5.0, 8), bf=0.5, crew=10, curve="GTB"),
 "ST8": dict(name="Very-high-pressure geared turbines (1200 psi)", years=(1937, 1965), fuel="oil", sfc=(340, 300), w=(34, 26), floor=0.55, rho=0.44, umax=(40, 55), ref=(40, 5.0, 5.0, 8), bf=0.45, crew=9, curve="GTB"),
 "PE1": dict(name="Petrol engines", years=(1905, 1945), fuel="petrol", sfc=(340, 290), w=(8.5, 6.5), floor=0.7, rho=0.40, umax=(0.2, 1.1), ref=(1, 1.2, 1.1, 2.5), bf=0.0, crew=3, curve="DSL"),
 "DI1": dict(name="Early marine diesels", years=(1910, 1925), fuel="diesel", sfc=(270, 240), w=(140, 100), floor=0.6, rho=0.42, umax=(0.4, 2), ref=(1, 4.5, 2.5, 7), bf=0.0, crew=6, curve="DSL"),
 "DI2": dict(name="Lightweight double-acting 2-stroke diesels", years=(1928, 1945), fuel="diesel", sfc=(250, 230), w=(50, 38), floor=0.75, rho=0.42, umax=(3, 7), ref=(5, 4.5, 3.5, 10), bf=0.0, crew=5, curve="DSL"),
 "DI3": dict(name="High-speed diesels (E-boat)", years=(1933, 1945), fuel="diesel", sfc=(245, 230), w=(14, 11.5), floor=0.7, rho=0.45, umax=(0.9, 2.2), ref=(1.5, 1.8, 1.6, 4), bf=0.0, crew=3, curve="DSL"),
 "DI4": dict(name="Turbocharged high-speed diesels (Deltic)", years=(1950, 1970), fuel="diesel", sfc=(235, 220), w=(11.5, 9.3), floor=0.7, rho=0.45, umax=(1.5, 3), ref=(2.5, 2.0, 2.0, 3.5), bf=0.0, crew=3, curve="DSL"),
 "DI5": dict(name="Medium-speed diesels", years=(1965, 2010), fuel="diesel", sfc=(215, 185), w=(30, 20), floor=0.8, rho=0.42, umax=(3, 12), ref=(6, 4.0, 3.0, 7), bf=0.0, crew=3, curve="DSL"),
 "DIS": dict(name="Slow-speed 2-stroke crosshead diesels (merchant)", years=(1912, 2010), fuel="diesel", sfc=(230, 165), w=(150, 60), floor=0.9, rho=0.40, umax=(2, 60), ref=(10, 9, 6, 15), bf=0.0, crew=3, curve="DSL"),
 "GT1": dict(name="Early naval gas turbines (boost)", years=(1947, 1962), fuel="diesel", sfc=(520, 400), w=(16.5, 13), floor=0.85, rho=0.22, umax=(1.8, 3.5), ref=(3, 1.5, 1.5, 4), bf=0.0, crew=3, curve="GTS"),
 "GT2": dict(name="Marinised aero gas turbines (Olympus/Tyne)", years=(1962, 1978), fuel="diesel", sfc=(330, 285), w=(19, 14), floor=0.85, rho=0.22, umax=(4, 21), ref=(20, 3.2, 2.8, 8), bf=0.0, crew=2.5, curve="GTS"),
}
DRAUGHT = {  # system: (intro, mature, velocity range, reach range)
 "natural": (1840, 1880, None, (4, 6)),
 "forced_boost": (1880, 1900, (7, 9), (7, 9)),
 "forced_coal": (1900, 1915, (8, 10), (8, 10)),
 "forced_oil": (1905, 1925, (10, 14), (12, 20)),
 "forced_heated": (1930, 1945, (12, 15), (20, 30)),
}


def ease(year, y0, y1):
    m = max(0.0, min(1.0, (year - y0) / (y1 - y0)))
    return 1 - (1 - m) ** 2


def lerp(a, b, k):
    return a + (b - a) * k


def r(v, n=0):
    v = round(v, n)
    return int(v) if n == 0 else v


def tech(code, year, variant=None, fuel=None):
    t = T[code]
    k = ease(year, *t["years"])
    w, sfc, umax = lerp(*t["w"], k), lerp(*t["sfc"], k), lerp(*t["umax"], k)
    mw, h, wd, l = t["ref"]
    crew, bf, curve, floor, name = t["crew"], t["bf"], t["curve"], t["floor"], t["name"]
    fuel = fuel or t["fuel"]
    if variant == "loco":
        w, umax, name = w * 0.6, min(umax, 1.5 if code == "ST2" else 2.0), name.replace("Scotch", "locomotive")
        name = name.replace("cylindrical (locomotive)", "locomotive")
    if variant == "express":
        w, h, name = w * 0.6, h * 0.85, "Triple expansion, express small-tube boilers"
    if variant == "quad":
        sfc, w, l, name = sfc * 0.92, w * 1.05, l * 1.2, "Quadruple expansion, large-tube water-tube boilers"
    if variant == "cruising":
        w, curve, name = w * 1.05, "GTB", name + " and cruising turbines"
    if t["fuel"] == "coal" and fuel == "oil":
        w, sfc, crew, name = w * 0.9, sfc * 0.97 * 30 / 41, crew * 0.45, name + ", oil-fired"
    if t["fuel"] == "coal" and fuel == "mixed":
        w, sfc, crew, fuel, name = w * 0.97, sfc * 0.985, crew * 0.85, "coal", name + ", mixed firing (coal, oil spray)"
    if t["fuel"] == "oil" and fuel == "coal":
        w, sfc, crew, name = w * 1.15, sfc * 1.05 * 41 / 30, crew * 2.2, name + ", coal-fired"
    # draught
    if bf == 0:
        dr = dict(system="exhaust", velocity_m_s=35, reach_m=60, gas_temp_k=620, air_fuel_ratio=38)
    else:
        if fuel == "coal":
            sys_ = "natural" if year < 1880 else "forced_boost" if year < 1900 else "forced_coal"
        else:
            sys_ = "forced_heated" if code in ("ST7", "ST8") else "forced_oil" if year >= 1905 else "forced_boost"
        y0, y1, vr, rr = DRAUGHT[sys_]
        kd = ease(year, y0, y1)
        dr = dict(system={"forced_coal": "forced", "forced_oil": "forced", "forced_heated": "forced"}.get(sys_, sys_))
        if vr:
            dr["velocity_m_s"] = r(lerp(*vr, kd), 1)
        dr["reach_m"] = r(lerp(*rr, kd), 1)
        if sys_ == "forced_boost":
            dr["natural_fraction"] = t.get("nat", 0.7)
        if fuel == "coal":
            dr.update(gas_temp_k=620 if sys_ == "natural" else 600, air_fuel_ratio=20 if sys_ == "natural" else 16)
        else:
            dr.update(gas_temp_k=450 if sys_ == "forced_heated" else 570, air_fuel_ratio=15)
    return dict(name=f"{name} ({year})", fuel=fuel, weight_kg_per_kw=r(w, 1), stress_floor=floor,
                sfc_g_per_kwh=r(sfc), density_t_per_m3=t["rho"], unit_max_mw=r(umax, 1),
                unit=dict(mw=mw, height_m=r(h, 2), width_m=wd, length_m=r(l, 1)),
                boiler_fraction=bf, crew_k=r(crew, 1), part_load=curve, draught=dr)


YEARS = [
 (1880, "Compound engines and Scotch boilers. Forced draught arrives, for boosting only.", [
   ("Capital ships, cruisers", "ST2", None, None), ("Torpedo boats (locomotive boilers)", "ST2", "loco", None)]),
 (1890, "Triple expansion engines. Forced draught for full power; natural draught for steaming.", [
   ("Capital ships, cruisers", "ST3", None, None), ("Torpedo boats (locomotive boilers)", "ST3", "loco", None),
   ("Early water-tube boilers (Belleville)", "ST4", None, None)]),
 (1900, "Water-tube boilers take over. Continuous forced draught.", [
   ("Capital ships, cruisers", "ST4", None, None), ("Destroyers (express boilers)", "ST4", "express", None),
   ("Merchants, older warships", "ST3", None, None)]),
 (1905, "The first turbines (Dreadnought).", [
   ("Turbine ships", "ST5", None, None), ("Reciprocating capital ships", "ST4", None, None),
   ("Quadruple expansion (economical cruisers, merchants)", "ST4", "quad", None),
   ("Destroyers (express boilers)", "ST4", "express", None)]),
 (1910, "Turbines everywhere; oil spray on coal, then all-oil destroyers. Petrol motor boats; early diesels.", [
   ("Coal turbine ships", "ST5", None, None), ("Mixed firing", "ST5", None, "mixed"),
   ("All-oil turbine ships (destroyers, Queen Elizabeth)", "ST5", None, "oil"),
   ("Reciprocating (merchants, older designs)", "ST4", None, None), ("Petrol motor boats", "PE1", None, None),
   ("Early diesels (submarines, motor ships)", "DI1", None, None)]),
 (1915, "Oil firing standard in new warships; first geared turbines.", [
   ("Oil-fired direct turbines", "ST5", None, "oil"), ("With cruising turbines", "ST5", "cruising", "oil"),
   ("Geared turbines", "ST6", None, None), ("Coal-fired direct turbines", "ST5", None, None),
   ("Petrol (coastal motor boats)", "PE1", None, None), ("Early diesels", "DI1", None, None)]),
 (1920, "Geared turbines and oil.", [
   ("Geared turbines", "ST6", None, None), ("Merchant triple expansion, oil-fired", "ST4", None, "oil"),
   ("Merchant slow-speed diesels", "DIS", None, None), ("Petrol", "PE1", None, None)]),
 (1930, "Mature geared turbines; high-pressure steam arrives. Light diesels.", [
   ("Geared turbines", "ST6", None, None), ("High-pressure geared turbines", "ST7", None, None),
   ("Light 2-stroke diesels (Deutschland)", "DI2", None, None), ("Merchant slow-speed diesels", "DIS", None, None),
   ("Petrol", "PE1", None, None)]),
 (1935, "High-pressure steam spreads; E-boat diesels.", [
   ("High-pressure geared turbines", "ST7", None, None), ("Light 2-stroke diesels", "DI2", None, None),
   ("High-speed diesels (E-boats)", "DI3", None, None), ("Petrol", "PE1", None, None)]),
 (1940, "The WWII generation.", [
   ("High-pressure geared turbines (Fletcher, KGV, Iowa)", "ST7", None, None),
   ("Very-high-pressure steam (German Wagner/Benson plants)", "ST8", None, None),
   ("Merchant triple expansion, oil-fired (Liberty)", "ST4", None, "oil"),
   ("Merchant geared turbines (T2, Victory)", "ST6", None, None),
   ("Merchant slow-speed diesels", "DIS", None, None), ("Light 2-stroke diesels", "DI2", None, None),
   ("High-speed diesels (E-boats)", "DI3", None, None), ("Petrol (PT boats, MTBs)", "PE1", None, None)]),
 (1945, "Mature WWII plants.", [
   ("High-pressure geared turbines", "ST7", None, None), ("Very-high-pressure steam", "ST8", None, None),
   ("High-speed diesels", "DI3", None, None), ("Petrol", "PE1", None, None)]),
 (1950, "Post-war steam; the first naval gas turbines.", [
   ("Very-high-pressure steam", "ST8", None, None), ("Early gas turbines (boost)", "GT1", None, None),
   ("Turbocharged high-speed diesels (Deltic)", "DI4", None, None)]),
 (1960, "1200 psi steam matures; gas turbines grow.", [
   ("Very-high-pressure steam", "ST8", None, None), ("Early gas turbines", "GT1", None, None),
   ("Turbocharged high-speed diesels", "DI4", None, None), ("Merchant slow-speed diesels", "DIS", None, None)]),
 (1970, "Aero-derived gas turbines and medium-speed diesels.", [
   ("Very-high-pressure steam", "ST8", None, None), ("Marinised aero gas turbines (Olympus, Tyne)", "GT2", None, None),
   ("Medium-speed diesels", "DI5", None, None), ("Turbocharged high-speed diesels", "DI4", None, None)]),
]



def blocks():
    out = []
    for year, blurb, entries in YEARS:
        out.append(f"## {year}\n\n{blurb}\n")
        for label, code, var, fuel in entries:
            out.append(f"**{label}** (`{code}`)\n```json\n\"tech\": " + json.dumps(tech(code, year, var, fuel)) +
                       "\n```\n")
    return "\n".join(out)


if __name__ == "__main__":
    path = "plant-templates.md"
    doc = open(path).read()
    head = doc[:re.search(r"^## \d{4}$", doc, re.M).start()]
    with open(path, "w") as fh:
        fh.write(head + blocks() + "\n")
    print(f"wrote {path}")
