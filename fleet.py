"""
Fleet and turret definitions for shipgen.py.

Units are metres in ship-local space: +x toward the bow, +y toward starboard, origin at
the ship's centre. Any list item may use:
    "mirror": True   -> also generate a copy at -y (dir/rest are mirrored too)
    "edge": d        -> set y to (hull half-width at x) - d, on the side given by the sign of "y"

Superstructure blocks: x0/x1 (aft/fwd ends), w (width), y, level (1 = lowest),
    rf/rb (front/back corner radius). Level 1 goes on the base layer, level 2+ on the upper layer,
    unless you set "layer" yourself.
Turret mounts: type, x, y, z (draw order), rest (degrees, 0 = ahead), traverse (+/- degrees).
"""

# ---------------------------------------------------------------------------
from looks import DEFAULT_PALETTE  # noqa: F401  (re-exported)
# Palette: looks.DEFAULT_PALETTE (WWII haze grey). Override per ship with "palette": {...}
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Turret types (sprites are drawn with the barrels pointing +x, pivot at centre)
#   r: body radius, barrel_len measured from barrel root, barrel_w, spacing between barrels
# ---------------------------------------------------------------------------
TURRET_TYPES = {
    "main_3x406": dict(desc="Triple 16in battleship turret", shape="bb", r=7.4,
                       barrels=3, barrel_len=19.5, barrel_w=0.95, spacing=2.7),
    "main_3x203": dict(desc="Triple 8in cruiser turret", shape="bb", r=4.6,
                       barrels=3, barrel_len=10.5, barrel_w=0.55, spacing=1.75),
    "dp_2x127": dict(desc="Twin 5in dual-purpose mount", shape="dp", r=2.9,
                     barrels=2, barrel_len=4.9, barrel_w=0.3, spacing=1.55),
    "dp_1x127": dict(desc="Single enclosed 5in mount", shape="dp", r=2.3,
                     barrels=1, barrel_len=4.9, barrel_w=0.3, spacing=0),
    "deck_1x102": dict(desc="Open 4in submarine deck gun", shape="open", r=1.3, barbette=False,
                       barrels=1, barrel_len=4.6, barrel_w=0.24, spacing=0),
    "torp_5x533": dict(desc="Quintuple 21in torpedo tube mount", shape="torp", r=1.9,
                       barrels=5, barrel_len=7.6, barrel_w=0.55, spacing=0.66,
                       centered=True, barbette=False),
}

# ---------------------------------------------------------------------------
# Ships
# ---------------------------------------------------------------------------
BATTLESHIP = dict(
    id="battleship", name="Battleship", class_="BB",
    length=262, beam=33,
    bow=dict(taper=0.36, power=1.7), stern=dict(taper=0.2, transom=0.42),
    deck="wood", chain_x=104, breakwater_x=84, bollards=[118, 96, -60, -110],
    turrets=[
        dict(id="A", type="main_3x406", x=70, z=1),
        dict(id="B", type="main_3x406", x=52, z=2),
        dict(id="C", type="main_3x406", x=-72, z=1, rest=180),
        dict(id="S1", type="dp_2x127", x=31, y=10.3, rest=90, traverse=110, z=3, mirror=True),
        dict(id="S2", type="dp_2x127", x=18, y=11.0, rest=90, traverse=100, z=3, mirror=True),
        dict(id="S3", type="dp_2x127", x=5, y=11.0, rest=90, traverse=100, z=3, mirror=True),
        dict(id="S4", type="dp_2x127", x=-8, y=11.0, rest=90, traverse=100, z=3, mirror=True),
        dict(id="S5", type="dp_2x127", x=-21, y=10.3, rest=90, traverse=110, z=3, mirror=True),
    ],
    superstructure=[
        dict(x0=-28, x1=38, w=26, level=1, rf=6, rb=5),
        dict(x0=12, x1=37, w=11, level=2, rf=4.5, rb=1),
        dict(x0=-25, x1=-12, w=8, level=2, rf=1, rb=3),
        dict(x0=21, x1=35, w=8.5, level=3, rf=4, rb=1),
        dict(x0=26, x1=32, w=5.5, level=4, rf=2.7, rb=2.7),
        dict(x0=-22, x1=-16.5, w=5, level=3, rf=2.5, rb=2.5),
    ],
    funnels=[dict(x=6, l=9, w=6.2, pipes=2), dict(x=-6.5, l=9, w=6.2, pipes=2)],
    masts=[dict(x=12.5, yard=9), dict(x=-13.5, yard=7)],
    aa=[
        dict(type="quad40", x=-42, y=12.5, dir=90, mirror=True),
        dict(type="quad40", x=-55, y=11.5, dir=90, mirror=True),
        dict(type="quad40", x=93, y=4.5, dir=0, mirror=True),
        dict(type="quad40", x=17, y=6.8, dir=90, mirror=True, layer="upper"),
        dict(type="quad40", x=-18.5, y=5.5, dir=90, mirror=True, layer="upper"),
        dict(type="single20", x=82, edge=1.5, y=1, dir=90, mirror=True),
        dict(type="single20", x=78, edge=1.5, y=1, dir=90, mirror=True),
        dict(type="single20", x=-35, edge=1.5, y=1, dir=90, mirror=True),
        dict(type="single20", x=-90, edge=1.5, y=1, dir=90, mirror=True),
        dict(type="single20", x=-95, edge=1.5, y=1, dir=90, mirror=True),
        dict(type="single20", x=-121, y=0, dir=180),
    ],
    boats=[dict(x=0, y=8.2, l=8, w=2.4, mirror=True)],
    fittings=[dict(x=-118, y=0, l=4, w=6, color="fitting")],  # aircraft crane base at the stern
)

HEAVY_CRUISER = dict(
    id="heavy_cruiser", name="Heavy Cruiser", class_="CA",
    length=185, beam=21,
    bow=dict(taper=0.34, power=1.7), stern=dict(taper=0.2, transom=0.48),
    deck="steel", chain_x=73, breakwater_x=60, bollards=[83, 66, -45, -80],
    turrets=[
        dict(id="A", type="main_3x203", x=52, z=1),
        dict(id="B", type="main_3x203", x=40, z=2),
        dict(id="C", type="main_3x203", x=-56, z=1, rest=180),
        dict(id="S1", type="dp_1x127", x=20, y=7.6, rest=90, traverse=110, z=3, mirror=True),
        dict(id="S2", type="dp_1x127", x=9, y=7.6, rest=90, traverse=100, z=3, mirror=True),
        dict(id="S3", type="dp_1x127", x=-4, y=7.6, rest=90, traverse=100, z=3, mirror=True),
        dict(id="S4", type="dp_1x127", x=-15, y=7.6, rest=90, traverse=110, z=3, mirror=True),
    ],
    superstructure=[
        dict(x0=-22, x1=28, w=18, level=1, rf=4, rb=3),
        dict(x0=14, x1=29, w=8, level=2, rf=3.5, rb=1),
        dict(x0=19, x1=28, w=6, level=3, rf=2.8, rb=1),
        dict(x0=22.5, x1=26.5, w=3.6, level=4, rf=1.8, rb=1.8),
        dict(x0=-25, x1=-15, w=6.5, level=2, rf=1, rb=2.5),
        dict(x0=-22, x1=-18, w=3.6, level=3, rf=1.8, rb=1.8),
    ],
    funnels=[dict(x=6, l=6.5, w=4.6, pipes=2), dict(x=-6, l=6.5, w=4.6, pipes=2)],
    masts=[dict(x=11, yard=7), dict(x=-11, yard=6)],
    aa=[
        dict(type="quad40", x=-32, y=7.5, dir=90, mirror=True),
        dict(type="quad40", x=64, y=0, dir=0),
        dict(type="twin40", x=12, y=5.2, dir=90, mirror=True, layer="upper"),
        dict(type="single20", x=-40, edge=1.3, y=1, dir=90, mirror=True),
        dict(type="single20", x=-68, edge=1.3, y=1, dir=90, mirror=True),
        dict(type="single20", x=34, edge=1.3, y=1, dir=90, mirror=True),
    ],
    boats=[dict(x=0, y=5.6, l=6, w=2, mirror=True)],
    fittings=[
        dict(x=-75, y=0, l=14, w=1.4, color="fitting"),          # aircraft catapult track
        dict(x=-82, y=0, l=3, w=3, color="fitting"),
    ],
)

DESTROYER = dict(
    id="destroyer", name="Destroyer", class_="DD",
    length=115, beam=12,
    bow=dict(taper=0.4, power=1.6), stern=dict(taper=0.16, transom=0.58),
    deck="steel", chain_x=47, bollards=[52, 38, -40, -50],
    turrets=[
        dict(id="A", type="dp_1x127", x=42, z=1),
        dict(id="B", type="dp_1x127", x=33, z=2),
        dict(id="C", type="dp_1x127", x=-20, z=2, rest=180),
        dict(id="D", type="dp_1x127", x=-31, z=1, rest=180),
        dict(id="T1", type="torp_5x533", x=3, rest=90, traverse=75, z=1),
        dict(id="T2", type="torp_5x533", x=-10, rest=90, traverse=75, z=1),
    ],
    superstructure=[
        dict(x0=17, x1=30, w=7.5, level=1, rf=2.5, rb=1),
        dict(x0=21, x1=29.5, w=6, level=2, rf=3, rb=1),
        dict(x0=24, x1=27.5, w=3, level=3, rf=1.5, rb=1.5),
        dict(x0=-25, x1=-14, w=5.6, level=1, rf=1, rb=1),
    ],
    funnels=[dict(x=11, l=4.6, w=3.1, pipes=1), dict(x=-3.5, l=4.6, w=3.1, pipes=1)],
    masts=[dict(x=17.5, yard=6, tripod=False)],
    aa=[
        dict(type="twin40", x=-15.6, y=2.0, dir=90, mirror=True),
        dict(type="twin40", x=16, y=4.3, dir=90, mirror=True, layer="upper"),
        dict(type="single20", x=-41, edge=1.2, y=1, dir=90, mirror=True),
        dict(type="single20", x=31, edge=1.2, y=1, dir=90, mirror=True, layer="upper"),
    ],
    boats=[dict(x=6.5, y=4.0, l=5, w=1.7, layer="upper")],
    fittings=[
        dict(x=-54, y=3.4, l=6, w=1.1, color="barrel"),           # depth charge racks
        dict(x=-54, y=-3.4, l=6, w=1.1, color="barrel"),
        dict(x=-44, y=4.0, l=1.2, w=1.2, color="barrel", mirror=True),  # K-guns
        dict(x=-47, y=4.0, l=1.2, w=1.2, color="barrel", mirror=True),
    ],
)

CARRIER = dict(
    id="carrier", name="Fleet Carrier", class_="CV",
    length=266, beam=28,
    bow=dict(taper=0.3, power=1.5), stern=dict(taper=0.15, transom=0.6),
    deck="steel", chain_x=124, hawse_back=5,
    flight_deck=dict(
        x0=-126, x1=118, half_width=15.5, bow_taper=14, number="17",
        elevators=[dict(x=72, l=14, w=13), dict(x=-52, l=14, w=13)],
        edge_elevators=[dict(x=4, y=-18, l=18, w=6)],
        wires=[-118, -112, -106, -100, -94, -88, -82, -76, -70],
    ),
    sponsons=[
        dict(x=82, y=-17.8, l=8, w=5), dict(x=45, y=-17.8, l=8, w=5),
        dict(x=-26, y=-17.8, l=8, w=5), dict(x=-80, y=-17.8, l=8, w=5),
        dict(x=-108, y=-17.8, l=8, w=5),
        dict(x=96, y=17.8, l=8, w=5), dict(x=-62, y=17.8, l=8, w=5), dict(x=-100, y=17.8, l=8, w=5),
    ],
    turrets=[
        dict(id="F1", type="dp_2x127", x=44, y=13, z=1, traverse=170),
        dict(id="F2", type="dp_2x127", x=35, y=13, z=2, traverse=170),
        dict(id="A1", type="dp_2x127", x=-20, y=13, z=2, rest=180, traverse=170),
        dict(id="A2", type="dp_2x127", x=-29, y=13, z=1, rest=180, traverse=170),
    ],
    superstructure=[
        dict(x0=-14, x1=28, y=14.6, w=7.0, level=1, rf=2.5, rb=1.5, layer="upper"),
        dict(x0=3, x1=24, y=14.4, w=5.0, level=2, rf=2.5, rb=1),
        dict(x0=9, x1=22, y=14.4, w=3.8, level=3, rf=1.9, rb=0.8),
        dict(x0=14, x1=19, y=14.4, w=2.8, level=4, rf=1.4, rb=1.4),
    ],
    funnels=[dict(x=-5, y=14.6, l=10, w=4.6, pipes=2)],
    masts=[dict(x=8, y=14.2, yard=5, tripod=False)],
    aa=[
        dict(type="quad40", x=82, y=-17.8, dir=-90), dict(type="quad40", x=45, y=-17.8, dir=-90),
        dict(type="quad40", x=-26, y=-17.8, dir=-90), dict(type="quad40", x=-80, y=-17.8, dir=-90),
        dict(type="quad40", x=-108, y=-17.8, dir=-90),
        dict(type="quad40", x=96, y=17.8, dir=90), dict(type="quad40", x=-62, y=17.8, dir=90),
        dict(type="quad40", x=-100, y=17.8, dir=90),
        dict(type="quad40", x=-129.5, y=0, dir=180),
        dict(type="quad40", x=25.5, y=14.6, dir=0, layer="upper"),
    ],
)

SUBMARINE = dict(
    id="submarine", name="Fleet Submarine", class_="SS",
    length=95, beam=8.3,
    bow=dict(taper=0.2, power=2.2, shape="round"),
    stern=dict(taper=0.4, power=1.5, shape="pointed", transom=0.0),
    deck="wood", deck_inset=0.8, deck_max_hw=2.3, deck_x0=-38, deck_x1=44, plank_spacing=0.9,
    palette=dict(hull="#2c3237", wood="#4a4741", deck_line="#191919",
                 levels=["#3e454b", "#4a5258", "#586168", "#66707a"], turret="#535b62", tub="#3c4349"),
    turrets=[dict(id="G", type="deck_1x102", x=18, z=1, traverse=160)],
    superstructure=[
        dict(x0=1, x1=15.5, w=3.8, level=2, rf=1.9, rb=1.2),
        dict(x0=6, x1=13.5, w=2.6, level=3, rf=1.3, rb=0.6),
        dict(x0=9.5, x1=11.5, w=1.2, level=4, rf=0.6, rb=0.6),
    ],
    aa=[dict(type="single20", x=3.0, y=0, dir=180, layer="upper"),
        dict(type="single20", x=-4, y=0, dir=180)],
    fittings=[dict(x=-20, y=0, l=6, w=1.4, color="fitting")],  # aft escape trunk / hatch
)

FLEET = [BATTLESHIP, HEAVY_CRUISER, DESTROYER, CARRIER, SUBMARINE]
for _s in FLEET:
    _s["class"] = _s.pop("class_")
