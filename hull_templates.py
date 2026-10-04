#!/usr/bin/env python3
"""
hull_templates: writes hull-templates.md from hullweight.PRESETS (research/hull-weight-model.md, section 4.2).

    python hull_templates.py
"""
import json

import hullweight

ERAS = {
    "iron_1880": "up to about 1885",
    "ms_riv_1900": "1885-1905",
    "ht_riv_1914": "1905-1920",
    "hts_riv_1925": "1920-1935: D steel, Ducol, USN HTS",
    "hts_mix_1937": "1933-1942",
    "sts_weld_1942": "1940-1945, USN",
    "weld_1945": "1943 on",
    "hy80_1960": "1955 on",
}

HEAD = """# Hull construction templates

Copy-paste values for a design's `hull.construction` block. A design names no year: it carries the construction
technology itself, because in the game a navy may research things earlier or later than history did. These blocks
are the presets of `research/hull-weight-model.md` (section 4.2). They are tuning defaults, not historical truth.
`hullweight.py` documents the model. Written by `python hull_templates.py` from `hullweight.PRESETS`.

A design that gives no construction gets the all-welded 1945 block. Planing craft ignore it: they keep the old
volume law (`hull_k`) until wooden and light-alloy hulls are researched.

## How to use

```json
"hull": {
  "block_coefficient": 0.59,
  "construction": { ...a block below... }
}
```

| field | effect |
|---|---|
| `yield_mpa` | Yield stress of the hull-girder steel mix (high-tensile steel in the strength deck and sheer strake, mild steel elsewhere). The allowable stress is yield / 2.1, capped at 185 MPa. It only matters where the hull is strength driven: big, long ships. Small ships are built to minimum plate gauge whatever the steel. |
| `join_factor` | Multiplies all structure: riveted laps and butt straps (1.08-1.12) against all welded (1.0). |
| `standard` | Scales the minimum plate gauge: 0.85 light, 1.0 naval, 1.25 robust. Light structure saves weight on small ships. |

A continuous armour deck over amidships is part of the hull girder, so it saves strength plating: more the
thicker it is and the farther it is from the neutral axis (0.45 of the depth above the keel).
"""


def main():
    out = [HEAD]
    for key, p in hullweight.PRESETS.items():
        block = json.dumps({**p, "standard": 1.0}, ensure_ascii=False)
        out.append(f"## {p['name']} ({ERAS[key]})\n\n```json\n\"construction\": {block}\n```\n")
    open("hull-templates.md", "w").write("\n".join(out))


if __name__ == "__main__":
    main()
