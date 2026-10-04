# Hull construction templates

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

## Wrought iron, riveted (up to about 1885)

```json
"construction": {"name": "Wrought iron, riveted", "yield_mpa": 190, "join_factor": 1.12, "standard": 1.0}
```

## Mild steel, riveted (1885-1905)

```json
"construction": {"name": "Mild steel, riveted", "yield_mpa": 235, "join_factor": 1.1, "standard": 1.0}
```

## Mild steel hull, high-tensile strength deck, riveted (1905-1920)

```json
"construction": {"name": "Mild steel hull, high-tensile strength deck, riveted", "yield_mpa": 290, "join_factor": 1.1, "standard": 1.0}
```

## High-tensile steel (D, Ducol, HTS), riveted (1920-1935: D steel, Ducol, USN HTS)

```json
"construction": {"name": "High-tensile steel (D, Ducol, HTS), riveted", "yield_mpa": 340, "join_factor": 1.08, "standard": 1.0}
```

## High-tensile steel, riveted shell, welded internals (1933-1942)

```json
"construction": {"name": "High-tensile steel, riveted shell, welded internals", "yield_mpa": 350, "join_factor": 1.04, "standard": 1.0}
```

## High-tensile and structural STS, mostly welded (1940-1945, USN)

```json
"construction": {"name": "High-tensile and structural STS, mostly welded", "yield_mpa": 420, "join_factor": 1.02, "standard": 1.0}
```

## High-tensile steel, all welded (1943 on)

```json
"construction": {"name": "High-tensile steel, all welded", "yield_mpa": 350, "join_factor": 1.0, "standard": 1.0}
```

## HY-80, all welded (1955 on)

```json
"construction": {"name": "HY-80, all welded", "yield_mpa": 420, "join_factor": 1.0, "standard": 1.0}
```
