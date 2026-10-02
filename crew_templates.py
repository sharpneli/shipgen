#!/usr/bin/env python3
"""
crew_templates: writes crew-templates.md, the habitability standards of research/crew-space-model.md (crew.STANDARDS)
as blocks to copy into a design's "crew": {"standard": ...}.

    python crew_templates.py
"""
import json

import crew

INTRO = """# Crew standard templates

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
| `endurance_days` | the fuel's range at cruise speed | Provisions carried. A tender may loiter far longer than \
its fuel range; shorter than the range only warns. |
| `distiller` | true | Makes fresh water: the tanks then hold `buffer_days` (default 5). Without one, water for \
the whole endurance (the double bottom takes what the fuel leaves). |
| `water_l_per_day` | the standard's | Rationing is a policy. |
| `berth_ratio` | 1.0 | Below 1 hot-bunking (men share berths across watches), above 1 surge berths. |
| `officer_fraction` | 0.15 under 30 men, else 0.08 | |

The complement comes from the ship: engineering from the plant, gun and torpedo crews per mount, deck and command
by size, an air group on carriers, then the standard's hotel crew. The crew lives wherever the ship has empty
volume; too little makes the hull grow.

"""

BLURB = {
    "H0": "Few or shared berths, a stove corner, one head. CMB, MTB, PT boat and E-boat practice.",
    "H1": "Hammocks slung over the mess tables (14 in per man, RN). 1840s onward; RN destroyers into the 1950s.",
    "H2": "Three- and four-tier pipe bunks, separate messdecks, refrigeration (USN WWII). From about 1925.",
    "H3": "Bunks with lockers, lounges, laundry, ship's store (Spruance, Nimitz generation). From about 1965.",
    "H4": "Six-berth messes, gym, services in the deckhead (Type 45 generation). From about 1995.",
    "H5": "Single cabins, en-suite or one wash place per six (merchant MLC grade). From about 1950.",
}

if __name__ == "__main__":
    out = [INTRO]
    for k, s in crew.STANDARDS.items():
        out.append(f"## {k}: {s['name']}\n\n{BLURB[k]}\n\n```json\n\"standard\": {json.dumps(s)}\n```\n")
    with open("crew-templates.md", "w") as fh:
        fh.write("\n".join(out))
    print("wrote crew-templates.md")
