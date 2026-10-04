#!/usr/bin/env python3
"""
calibrate: weighs each design that models a real ship at that ship's waterline length and beam, and compares its
standard displacement with the real one (for pre-1920 ships, normal displacement less its coal). Fixing the size
separates the weight model from the size search. -g also prints the weight groups.

    python calibrate.py [-g] [design ids]
"""
import json
import sys

import shipdesign as sd

REAL = {  # id: (L wl, B, target std-equivalent t, note)
    "bismarck": (241.6, 36.0, 41700, "std"),
    "battleship_layered": (262.0, 33.0, 46000, "Iowa std, as built ~45-48k"),
    "heavy_cruiser": (202.4, 21.6, 14700, "Baltimore std"),
    "destroyer": (112.5, 12.0, 2080, "Fletcher std (design has 80 mm guns)"),
    "fleet_carrier": (250.0, 28.3, 27500, "Essex std"),
    "supercarrier": (301.8, 39.5, 60600, "Forrestal std"),
    "escort_carrier": (149.4, 19.9, 7900, "Casablanca std"),
    "dreadnought": (160.6, 25.0, 17500, "normal 18.4k less 0.9k coal"),
    "mikasa": (126.5, 23.2, 14700, "normal 15.4k less 0.7k coal"),
    "connecticut": (139.0, 23.4, 15350, "normal 16.3k less 0.9k coal"),
    "nassau": (146.1, 26.9, 17900, "normal 18.9k less 1.0k coal"),
    "kongo": (211.8, 28.0, 26400, "normal 27.4k less 1.0k coal"),
    "invincible": (167.6, 23.9, 16500, "normal 17.5k less 1.0k coal"),
    "battlecruiser": (210.3, 27.0, 25700, "Lion normal 26.7k less 1.0k coal"),
    "liberty": (134.6, 17.3, 3400, "light ship"),
}
groups_out = "-g" in sys.argv
names = [a for a in sys.argv[1:] if not a.startswith("-")] or list(REAL)
tot = []
for n in names:
    L, B, real, note = REAL[n]
    d = json.load(open(f"designs/{n}.json"))
    lay, r, _ = sd.balance(sd.with_hull(d, L, B))
    err = 100 * (r.std - real) / real
    tot.append(abs(err))
    g = {k: round(v) for k, v in sorted(r.groups.items(), key=lambda kv: -kv[1]) if k != "fuel"}
    print(f"{n:19} std {r.std:7,.0f} real {real:7,} {err:+5.0f}%  T {r.draught:4.1f} GM {r.gm_full:4.2f}  {note}")
    if groups_out:
        print("    ", g)
print(f"mean |err| {sum(tot) / len(tot):.1f}%")
