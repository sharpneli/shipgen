#!/usr/bin/env python3
"""
score: the Fleetwright trailer's music, "Line of Battle", composed in code on synth.py's orchestra and cut to
trailer.py's edit.

D minor, a hymn-like theme (A-D-E-F, rising out of the sea) that's stated three times: a lone horn over the cold
open, the strings over the zoom, the brass over the battle; then a D major cadence under the title.

The tempo map comes from the cut, not the other way round. From Lion's sheet in the design montage to the hit that
sets off her magazine, the edit sits on a 100 BPM grid almost exactly: the APPROVED stamp lands 2 beats after Lion's
sheet, the drop into the sea is 5 beats later, the zoom pulls out on a bar line, the cut to the straddled Lion is a
bar line and the hit is a downbeat 63 beats on. So that stretch is one grid anchored on those frames (G). Around it:
the cold open is rubato (O), the montage's sheets are an accelerando, one beat per sheet (M), the slow motion of the
explosion is free time, and the end card has its own slow grid so the title lands on a downbeat (E).

    ~/.venv/bin/python vidgen/score.py           # -> vidgen/out/fleetwright_score.wav, stems, and the muxed
                                                 #    vidgen/out/fleetwright_trailer_scored.mp4
    ~/.venv/bin/python vidgen/score.py --no-mux  # audio only
    ~/.venv/bin/python vidgen/score.py --from 33 --to 54   # render just that stretch (seconds), for quick drafts

Moments taken from the footage itself (flashes, measured off the render, trailer time): Lion's salvos in the zoom at
24.37 and 27.20, the squadron's at 29.60/29.83/31.07/31.30, the jets at 54.0 and the fireball at 55.07.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import synth as S  # noqa: E402
import trailer as TR  # noqa: E402

OUT = HERE / "out"
FPS = TR.FPS


# ------------------------------------------------------------------------------------------------- the timeline
def _n(s):
    return int(round(s * FPS))


def timeline():
    """Section starts (s) from trailer.py's own constants, frame-exact as cut() builds them."""
    T = {}
    f = 0
    T["open"] = 0.0
    f += _n(6.0)                                                   # cold open: lion_s6 1.0 .. 7.0
    T["card1"] = f / FPS
    f += _n(1.7)
    T["sheets"] = []
    for d in TR.MONTAGE_S:
        T["sheets"].append(f / FPS)
        f += _n(d)
    T["lion"] = f / FPS
    T["stamp"] = T["lion"] + TR.STAMP_AT
    f += _n(TR.LION_HOLD_S)
    T["to_sea"] = f / FPS
    f += _n(TR.TO_SEA[2][1])
    T["zoom"] = f / FPS
    f0 = TR.TO_SEA[2][1] - TR.TO_SEA[2][0]
    zoom = [(f0, 4.0, 1.0), (4.0, 7.5, 2.0), (7.5, 12.0, 1.0), (12.0, 22.0, 2.0)]     # as in cut()
    for i, (a, b, sp) in enumerate(zoom):
        if i == 3:
            T["zoom_out"] = f / FPS
        f += _n((b - a) / sp)
    T["card2"] = T["zoom"] + 10.4
    T["swing"] = f / FPS
    f += TR.swing_n()
    for name, pieces in (("wide", TR.BATTLE_WIDE), ("enemy", TR.BATTLE_ENEMY), ("ours", TR.BATTLE_OURS)):
        T[name] = f / FPS
        f += sum(_n((b - a) / sp) for a, b, sp in pieces)
    T["hit"] = f / FPS
    T["card3"] = T["hit"] + TR.EXPLOSION_CARD
    f += _n(sum((b - a) / sp for a, b, sp in TR.EXPLOSION))
    T["end"] = f / FPS
    f += _n(TR.END_S)
    T["total"] = f / FPS
    T["title"] = T["end"] + 1.7                                    # the wordmark fades in (end_frame)
    T["aside"] = T["end"] + 5.1                                    # "[HAH, AS IF]"
    T["end_salvo"] = T["end"] + 5.6
    return T


T = timeline()


def grid(anchors):
    """Beat -> seconds through anchors {beat: time}, linear between them (and beyond, from the nearest pair)."""
    ks = np.array(sorted(anchors), float)
    ts = np.array([anchors[k] for k in sorted(anchors)], float)

    def g(k):
        k = np.asarray(k, float)
        i = np.clip(np.searchsorted(ks, k) - 1, 0, len(ks) - 2)
        return ts[i] + (k - ks[i]) * (ts[i + 1] - ts[i]) / (ks[i + 1] - ks[i])
    return lambda k: float(g(k))


# the 100 BPM spine: beat 0 = Lion's sheet; bars start at k = 3, 7, 11, ... (7 = the sea, 63 = the hit). The wide
# shot is beat 38 (the anticipation, beat 4 of the swing's last bar) and the cut to the second Lion is 55; holding
# those exactly moves the tempo by under 3 %
G = grid({0: T["lion"], 2: T["stamp"], 7: T["zoom"], 38: T["wide"], 55: T["ours"], 63: T["hit"]})
# the cold open: 80 BPM, the card on beat 8, then a ritardando into the montage
O = grid({0: 0.0, 8: T["card1"], 10: T["sheets"][0]})
# the montage: one beat per sheet, Lion's sheet is beat 8
M = grid({**{i: t for i, t in enumerate(T["sheets"])}, 8: T["lion"]})
# the end card: the title lands on beat 2
EB = (T["title"] - T["end"]) / 2
E = grid({0: T["end"], 1: T["end"] + EB})

NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def nm(s):
    """'D4', 'Bb2', 'C#5' -> MIDI."""
    p = NOTE[s[0]]
    i = 1
    while s[i] in "#b":
        p += 1 if s[i] == "#" else -1
        i += 1
    return 12 * (int(s[i:]) + 1) + p


def nms(s):
    return [nm(x) for x in s.split()]


# ------------------------------------------------------------------------------------------------------ the parts
# pans: an orchestra seen from the stalls
PAN = dict(vln1=-0.5, vln2=-0.2, vla=0.15, vc=0.35, cb=0.5, hn=-0.35, tbn=0.35, tpt=0.1, timp=-0.15, harp=0.55,
           cel=-0.55, bell=0.3, perc=0.0, snare=0.15, cym=0.25, choirL=-0.4, choirR=0.4)


class Score:
    def __init__(self, t0=0.0, t1=None):
        self.t0, self.t1 = t0, T["total"] if t1 is None else t1
        self.mx = S.Mixer(T["total"] + 0.02)
        for b, wet in (("strings", 0.32), ("brass", 0.28), ("choir", 0.4), ("keys", 0.38), ("perc", 0.22),
                       ("fx", 0.3), ("sea", 0.05)):
            self.mx.bus(b, wet)

    def on(self, t, length=6.0):
        return t + length >= self.t0 and t <= self.t1

    def put(self, bus, sig, t, pan=0.0, gain=1.0, send=None):
        self.mx.add(bus, sig, t, pan, gain, send)

    # instruments, placed in seconds
    def str_(self, part, m, t, dur, vel=0.6, **kw):
        if self.on(t, dur + 2):
            vo = kw.pop("voices", 4 if part in ("vln1", "vln2") else 3)
            self.put("strings", S.strings(m, dur, vel, voices=vo, **kw), t, PAN[part])

    def chord_str(self, ms, t, dur, vel=0.5, parts=None, **kw):
        parts = parts or (["cb", "vc", "vla", "vln2", "vln1"] if len(ms) >= 5 else ["vc", "vla", "vln2", "vln1"])
        for m, p in zip(sorted(ms), parts[-len(ms):] if len(ms) < len(parts) else parts):
            self.str_(p, m, t, dur, vel, **kw)

    def hn(self, m, t, dur, vel=0.6, kind="horn", part="hn", **kw):
        if self.on(t, dur + 2):
            self.put("brass", S.brass(m, dur, vel, kind=kind, **kw), t, PAN[part])

    def choir(self, ms, t, dur, vel=0.4, vowel="o", **kw):
        if self.on(t, dur + 2):
            for i, m in enumerate(ms):
                self.put("choir", S.choir(m, dur, vel, vowel, **kw), t, PAN["choirL" if i % 2 else "choirR"] * 0.8)

    def harp(self, m, t, vel=0.5, **kw):
        if self.on(t, 4):
            self.put("keys", S.pluck(m, vel, **kw), t, PAN["harp"])

    def cel(self, m, t, vel=0.4):
        if self.on(t, 3):
            self.put("keys", S.celesta(m, vel), t, PAN["cel"])

    def bell(self, m, t, vel=0.5):
        if self.on(t, 7):
            self.put("keys", S.bell(m, vel), t, PAN["bell"], send=0.6)

    def timp(self, m, t, vel=0.7, roll=0.0, **kw):
        if self.on(t, roll + 5):
            self.put("perc", S.timpani(m, vel, roll=roll, **kw), t, PAN["timp"])

    def drum(self, sig, t, pan=0.0, gain=1.0, send=None, bus="perc"):
        if self.on(t, len(sig) / S.SR):
            self.put(bus, sig, t, pan, gain, send)

    def harp_arp(self, notes, t, step, vel=0.4):
        for i, m in enumerate(notes):
            self.harp(m, t + i * step, vel * (1.0 if i % 4 == 0 else 0.8))

    def spic(self, m, t, vel=0.7, part="vc", bright=1.0):
        if self.on(t, 1):
            self.put("strings", S.spiccato(m, vel, bright=bright), t, PAN[part])


# ------------------------------------------------------------------------------------------------ the composition
THEME = [  # (beat, beats, MIDI): 8 bars of 4, quarter = 100 BPM; harmony Dm Bb F C | Dm Gm Bb A
    (0, 2, "A4"), (2, 1, "D5"), (3, 1, "E5"),
    (4, 3, "F5"), (7, .5, "E5"), (7.5, .5, "D5"),
    (8, 2, "C5"), (10, 1, "A4"), (11, 1, "C5"),
    (12, 4, "E5"),
    (16, 2, "A4"), (18, 1, "D5"), (19, 1, "E5"),
    (20, 1.5, "F5"), (21.5, .5, "G5"), (22, 2, "A5"),
    (24, 2, "Bb5"), (26, 1, "A5"), (27, 1, "G5"),
    (28, 3.5, "A5"),
]
THEME_CHORDS = [("D2", "D3 A3 D4 F4"), ("Bb1", "Bb2 F3 D4 F4"), ("F1", "F2 C4 F4 A4"), ("C2", "C3 G3 C4 E4"),
                ("D2", "D3 A3 D4 F4"), ("G1", "G2 D4 G4 Bb4"), ("Bb1", "Bb2 F3 D4 F4"), ("A1", "A2 E3 C#4 E4")]


def cold_open(s):
    """0 .. the montage: the sea, a low D, the ship's bell under the caption, and the theme's head on a lone horn."""
    s.drum(S.sea(T["card1"] + 0.6, 0.5), 0.0, 0.0, 1.0, bus="sea")
    end = T["card1"]
    s.str_("cb", nm("D2"), 0.0, end - 0.2, 0.3, attack=2.5, release=1.0)
    s.str_("vc", nm("A2"), 0.3, end - 0.5, 0.22, attack=2.5, release=1.0)
    s.chord_str(nms("D4 F4 A4"), 0.9, end - 0.9, 0.15, parts=["vla", "vln2", "vln1"], attack=2.2, release=0.8)
    s.bell(nm("D5"), 1.2, 0.45)                                     # two bells, under the caption
    s.bell(nm("D5"), 1.62, 0.38)
    for b, d, n, v in ((2, 2, "A3", .62), (4, 1, "D4", .66), (5, 1, "E4", .68), (6, 2.9, "F4", .74),
                       (9, 1, "E4", .66), (10, 1.2, "D4", .55)):
        s.hn(nm(n), O(b), O(b + d) - O(b) + 0.05, v, attack=0.12, release=0.5)
    # the card: Bb, then A, the timpani rolling into the montage
    c = T["card1"]
    s.timp(nm("F2"), c, 0.45)
    s.harp(nm("Bb1"), c, 0.5)
    s.harp(nm("F2"), c + 0.02, 0.4)
    s.str_("cb", nm("Bb1"), c, O(9) - c, 0.45, attack=0.15, release=0.4)
    s.chord_str(nms("F3 Bb3 D4"), c, O(9) - c, 0.3, parts=["vla", "vln2", "vln1"], attack=0.2, release=0.4)
    s.str_("cb", nm("A1"), O(9), O(10) - O(9), 0.45, attack=0.1, release=0.3)
    s.chord_str(nms("E3 A3 C#4"), O(9), O(10) - O(9), 0.32, parts=["vla", "vln2", "vln1"], attack=0.1, release=0.3)
    s.timp(nm("A2"), O(9), 0.55, roll=O(10) - O(9) - 0.05)


MONTAGE_CHORDS = [("D2", "D4 F4 A4"), ("E2", "C4 E4 G4"), ("F2", "C4 F4 A4"), ("G2", "D4 G4 Bb4"),
                  ("A2", "D4 F4 A4"), ("Bb2", "D4 F4 Bb4"), ("C3", "E4 G4 C5"), ("C#3", "E4 A4 C#5")]


def montage(s):
    """The design bureau: one chord per sheet over a bass climbing D to C#, harp in sixteenths that speed up with
    the cuts, a pizzicato and a timpani on every sheet, ruling-pen ticks; then Lion, a snare roll and the stamp."""
    n = len(MONTAGE_CHORDS)
    for i, (b, up) in enumerate(MONTAGE_CHORDS):
        t0, t1 = M(i), M(i + 1)
        d = t1 - t0
        x = i / (n - 1)
        bass, ups = nm(b), nms(up)
        s.put("strings", S.pizz(bass, 0.7 + 0.25 * x), t0, PAN["cb"])
        s.put("strings", S.pizz(bass + 12, 0.55 + 0.25 * x), t0 + 0.01, PAN["vc"])
        s.timp(bass if bass >= nm("D2") + 0 and bass <= nm("A2") else bass - 12, t0, 0.35 + 0.35 * x)
        s.str_("cb", bass - 12 if bass > nm("G2") else bass, t0, d + 0.05, 0.3 + 0.25 * x, attack=0.06, release=0.25)
        s.chord_str(ups, t0, d + 0.05, 0.2 + 0.32 * x, parts=["vla", "vln2", "vln1"], attack=0.08, release=0.25)
        arp = [ups[0], ups[1], ups[2], ups[0] + 12]
        for j in range(4):
            tj = M(i + j / 4)
            s.harp(arp[j] + (12 if x > 0.5 else 0), tj, 0.42 + 0.2 * x)
            s.drum(S.tick(0.22 if j == 0 else 0.12), tj, -0.3 if j % 2 else 0.3, bus="perc", send=0.1)
            if i >= 3 and j % 2 == 0:
                s.cel(arp[j] + 24, tj, 0.25 + 0.15 * x)
        for j in (0, 2):                                            # eighths in the violas
            s.spic(bass + 12 + (7 if j else 0), M(i + j / 4), 0.35 + 0.35 * x, "vla")
    # Lion's sheet: D, sixteenths at the 100 BPM grid from here on, a snare roll into the stamp
    t0 = G(0)
    for j in range(8):
        tj = G(j / 4)
        s.harp([nm("D5"), nm("A5"), nm("D6"), nm("F6")][j % 4], tj, 0.62)
        s.cel([nm("D6"), nm("A6")][j % 2], tj, 0.38)
        s.drum(S.tick(0.25 if j % 4 == 0 else 0.14), tj, -0.3 if j % 2 else 0.3, send=0.1)
        if j % 2 == 0:
            s.spic(nm("D3") + (7 if j % 4 else 0), tj, 0.75, "vla")
    s.put("strings", S.pizz(nm("D2"), 0.95), t0, PAN["cb"])
    s.timp(nm("D2"), t0, 0.75)
    s.str_("cb", nm("D2"), t0, G(2) - t0, 0.6, attack=0.05, release=0.2)
    s.chord_str(nms("D4 A4 D5"), t0, G(2) - t0, 0.55, parts=["vla", "vln2", "vln1"], attack=0.05, release=0.2)
    s.drum(S.snare_roll(G(2) - t0 - 0.03, 0.15, 0.85), t0, PAN["snare"])
    s.drum(S.reverse_cymbal(2.4, 0.6), G(2) - 2.4, PAN["cym"], bus="fx")


def stamp(s):
    """APPROVED: a B-flat major tutti, then it rings out while the sheet sinks into the sea."""
    t = G(2)
    for m, v in zip(nms("Bb2 F3 D4"), (1.0, 0.95, 0.9)):
        s.hn(m, t, 0.5, v, kind="trombone", part="tbn", attack=0.02, release=1.4)
    for m in nms("F4 Bb4 D5"):
        s.hn(m, t, 0.7, 0.9, attack=0.03, release=1.6)
    s.str_("cb", nm("Bb1"), t, 1.2, 0.85, attack=0.01, release=1.6)
    s.chord_str(nms("Bb2 F3 D4 F4 Bb4 D5"), t, 1.0, 0.7, parts=["vc", "vc", "vla", "vln2", "vln1", "vln1"],
                attack=0.01, release=1.8)
    s.choir(nms("Bb3 D4 F4 Bb4"), t, 1.2, 0.45, "a", attack=0.05, release=2.0)
    s.timp(nm("F2"), t, 1.0)
    s.timp(nm("Bb1"), t + 0.005, 0.8)
    s.drum(S.gran_cassa(1.0), t, 0.0, 0.9)
    s.drum(S.sub_drop(0.8), t, 0.0, 0.8)
    s.drum(S.cymbal(0.9, 3.5), t, PAN["cym"], bus="fx")
    # it rings on: high strings hold D and F, the low end fades, the sea comes up, a single bell
    s.chord_str(nms("D5 F5"), t + 0.3, G(7) - t - 0.2, 0.28, parts=["vln2", "vln1"], attack=0.8, release=1.2)
    s.str_("vc", nm("Bb2"), t + 0.3, 1.8, 0.3, attack=0.6, release=1.2)
    s.drum(S.sea(G(7) - T["to_sea"] + 0.5, 0.45), T["to_sea"], bus="sea")
    s.bell(nm("D5"), T["to_sea"] + 0.9, 0.35)
    s.harp_arp(nms("D3 A3 D4 F4 A4 D5"), G(7) - 0.9, 0.15, 0.32)


def theme_zoom(s):
    """The sea: the theme on the strings over harp eighths, horns join, the zoom pulls out on bar 5 and the whole
    line turns up; drums on Lion's salvos."""
    k0 = 7
    for i in range(6):
        b, up = THEME_CHORDS[i]
        t0, t1 = G(k0 + 4 * i), G(k0 + 4 * i + 4)
        d = t1 - t0
        x = i / 5
        s.str_("cb", nm(b), t0, d + 0.1, 0.4 + 0.3 * x, attack=0.4, release=0.6)
        s.chord_str(nms(up), t0, d + 0.1, 0.15 + 0.2 * x, parts=["vc", "vla", "vln2", "vln2"], attack=0.5,
                    release=0.6)
        ups = nms(up)
        pat = [nm(b) + 12, ups[1], ups[2], ups[3], ups[2] + 12, ups[3], ups[2], ups[1]]
        for j, m in enumerate(pat):
            s.harp(m, G(k0 + 4 * i + j / 2), 0.36 + 0.12 * x)
        if i >= 3:
            s.choir([u for u in ups[1:]], t0, d + 0.1, 0.18 + 0.12 * (i - 3), "o", attack=0.8)
    # the theme: violins (with violas below from bar 4), up the octave and with horns from bar 5
    for b, d, n in THEME:
        if b >= 24:
            break
        t0, t1 = G(k0 + b), G(k0 + b + d)
        m = nm(n)
        loud = b >= 16
        v = 0.42 + 0.0125 * b
        s.str_("vln1", m + (12 if loud else 0), t0, t1 - t0 + 0.04, v, attack=0.18, release=0.45, voices=5)
        if b >= 12:
            s.str_("vla", m - 12, t0, t1 - t0 + 0.04, v * 0.7, attack=0.18, release=0.45)
        if loud:
            s.hn(m, t0, t1 - t0 + 0.02, 0.62 + 0.02 * (b - 16), attack=0.07, release=0.35)
    # horns answer at the end of the first phrase
    for b, d, n in ((12, 1, "C4"), (13, 1, "E4"), (14, 1, "G4"), (15, 1, "A4")):
        s.hn(nm(n), G(k0 + b), G(k0 + b + d) - G(k0 + b), 0.45 + 0.03 * (b - 12), attack=0.06, release=0.3)
    # Lion's salvos and the squadron firing as she pulls out
    s.timp(nm("F2"), 24.37, 0.6)
    s.drum(S.gran_cassa(0.45), 24.37, 0.0, 0.7)
    s.timp(nm("G2"), 27.20, 0.62)
    s.drum(S.gran_cassa(0.45), 27.20, 0.0, 0.7)
    for t, v in ((29.60, .35), (29.83, .3), (31.07, .3), (31.30, .26)):
        s.drum(S.taiko(v, 52, 0.7), t, 0.0, 0.7, send=0.6)
    # the pull-out: a cymbal swell into bar 5, gran cassa on it
    s.drum(S.reverse_cymbal(1.8, 0.45), G(23) - 1.8, PAN["cym"], bus="fx")
    s.drum(S.gran_cassa(0.7), G(23), 0.0, 0.8)
    s.timp(nm("D2"), G(23), 0.7)
    s.drum(S.sea(G(31) - G(7) + 1.0, 0.35), G(7), bus="sea")


BATTLE_TUNE = [  # (beat from bar B1, beats, note) for the horns; trombones an octave down, trumpets up from B5
    (0, 1.5, "A3"), (1.5, .5, "D4"), (2, 1, "E4"), (3, 1, "F4"),
    (4, 2, "F4"), (6, 1, "E4"), (7, 1, "D4"),
    (8, 1.5, "D4"), (9.5, .5, "Bb3"), (10, 1, "D4"), (11, 1, "G4"),
    (12, 2, "E4"), (14, 1, "C#4"), (15, 1, "E4"),
    (16, 1.5, "A4"), (17.5, .5, "G4"), (18, 1, "F4"), (19, 1, "A4"),
    (20, 2, "Bb4"), (22, 2, "A4"),
]
BATTLE_CHORDS = [("D2", "D3 A3 D4 F4"), ("Bb1", "Bb2 F3 D4 F4"), ("G1", "G2 D3 G3 Bb3"), ("A1", "A2 E3 A3 C#4"),
                 ("D2", "D3 A3 D4 F4"), ("Bb1", "Bb2 F3 Bb3 D4")]
TAIKO = {0: 1.0, 3: 0.7, 6: 0.8, 10: 0.7, 12: 0.9, 14: 0.6}       # sixteenths in the bar: 3+3+4+2+2+2


def battle(s):
    """The swing round to the battle: the theme's last two bars, huge, a timpani roll and an anticipation on the
    cut to the wide shot; then six bars of battle: spiccato ostinato, taiko, field drum, the tune on the brass."""
    # the swing: theme bars 7-8 (Bb, A) at full strength
    for i, k in enumerate((31, 35)):
        b, up = THEME_CHORDS[6 + i]
        t0, t1 = G(k), G(k + 4)
        s.str_("cb", nm(b), t0, t1 - t0, 0.75, attack=0.15, release=0.4)
        s.chord_str(nms(up), t0, t1 - t0, 0.55, parts=["vc", "vla", "vln2", "vln2"], attack=0.2, release=0.4)
        s.choir(nms(up)[1:], t0, t1 - t0, 0.38, "a", attack=0.4)
        s.hn(nm(up.split()[0]) - 0, t0, t1 - t0, 0.7, kind="trombone", part="tbn", attack=0.1, release=0.4)
        ups = nms(up)
        for j in range(16):                                          # rising violas in sixteenths
            s.spic(ups[j % 4] + 12 * (j // 8), G(k + j / 4), 0.35 + 0.3 * (j / 15), "vla")
    for b, d, n in THEME[16:]:
        if b < 24:
            continue
        t0 = G(7 + b)
        t1 = G(7 + b + d) if b < 28 else G(38)
        s.str_("vln1", nm(n) + 0, t0, t1 - t0 + 0.04, 0.78, attack=0.12, release=0.35, voices=5)
        s.str_("vln2", nm(n) - 12, t0, t1 - t0 + 0.04, 0.6, attack=0.12, release=0.35)
        s.hn(nm(n) - 12, t0, t1 - t0 + 0.02, 0.85, attack=0.06, release=0.3)
    s.timp(nm("A2"), G(35), 0.85, roll=G(38) - G(35) - 0.04)
    s.drum(S.snare_roll(G(38) - G(35.5), 0.15, 0.75), G(35.5), PAN["snare"])
    s.drum(S.riser(G(38) - G(34), 300, 3000, 0.12), G(34), 0.0, bus="fx")
    # the anticipation on the cut to the wide shot (beat 38): D minor, tied over into the battle
    ta = G(38)
    s.drum(S.taiko(1.0), ta, 0.0, 1.0)
    s.drum(S.gran_cassa(0.9), ta, 0.0, 0.8)
    s.drum(S.cymbal(0.85, 3.0), ta, PAN["cym"], bus="fx")
    s.timp(nm("D2"), ta, 0.95)
    for m in nms("D3 A3 D4"):
        s.hn(m, ta, G(39) - ta + 0.3, 0.95, kind="trombone", part="tbn", attack=0.02, release=0.6)
    for m in nms("D4 F4 A4"):
        s.hn(m, ta, G(39) - ta + 0.3, 0.9, attack=0.03, release=0.6)
    s.chord_str(nms("D2 D3 A3 D4 F4 A4 D5"), ta, G(39) - ta + 0.2, 0.75,
                parts=["cb", "vc", "vc", "vla", "vln2", "vln1", "vln1"], attack=0.02, release=0.5)

    # six bars of battle, B1 = k39
    for i, (b, up) in enumerate(BATTLE_CHORDS):
        k = 39 + 4 * i
        t0, t1 = G(k), G(k + 4)
        x = i / 5
        root = nm(b)
        ups = nms(up)
        # ostinato: cellos and basses in eighths, violas in sixteenths (root, fifth, octave, fifth)
        last = i == 5
        for j in range(8):
            r = root + 12 if not (last and j >= 4) else nm("A2")
            acc = 1.0 if j in (0, 3, 6) else 0.75
            s.spic(r, G(k + j / 2), 0.62 * acc + 0.1 * x, "vc")
            s.spic(r - 12, G(k + j / 2) + 0.004, 0.55 * acc, "cb", bright=0.7)
        for j in range(16):
            rr = (root + 24 if not (last and j >= 8) else nm("A3"))
            m = [rr, rr + 7, rr + 12, rr + 7][j % 4]
            s.spic(m, G(k + j / 4), (0.32 if j % 4 else 0.45) + 0.2 * x, "vla")
        # sustained harmony: violins and choir, growing
        s.chord_str(ups[1:], t0, t1 - t0 + 0.05, 0.2 + 0.2 * x, parts=["vla", "vln2", "vln1"], attack=0.3,
                    release=0.3, trem=12 if i >= 4 else 0)
        s.choir(ups[1:], t0, t1 - t0 + 0.05, 0.22 + 0.25 * x, "a", attack=0.4, release=0.4)
        # drums
        for j, v in TAIKO.items():
            s.drum(S.taiko(v * (0.8 + 0.2 * x)), G(k + j / 4), 0.0, 0.85)
        s.timp(root + 12 if root + 12 <= nm("A2") else root, t0, 0.8 + 0.15 * x)
        s.timp(nm("A2") if root != nm("A1") else nm("E2"), G(k + 2), 0.6 + 0.15 * x)
        if i < 4:
            for j in (4, 12):
                s.drum(S.snare(0.55 + 0.1 * x), G(k + j / 4), PAN["snare"])
                s.drum(S.snare(0.18), G(k + (j - 0.5) / 4), PAN["snare"])          # a drag before it
            if i % 2 == 1:
                for j in (13, 14, 15):
                    s.drum(S.snare(0.35 + 0.1 * (j - 13)), G(k + j / 4 + 0.125), PAN["snare"])
        if i in (0, 4):
            s.drum(S.gran_cassa(0.85), t0, 0.0, 0.9)
    # accents on the cuts: the enemy lead (near the 'a' of beat 1 in B3, with the taiko), the second Lion (B5's
    # downbeat)
    s.drum(S.cymbal(0.7, 2.5), T["enemy"], PAN["cym"], bus="fx")
    s.drum(S.cymbal(0.85, 3.0), G(55), PAN["cym"], bus="fx")
    # the tune
    for b, d, n in BATTLE_TUNE:
        t0, t1 = G(39 + b), G(39 + b + d)
        m = nm(n)
        hv = 0.8 + 0.01 * b
        s.hn(m, t0, t1 - t0 + 0.02, hv, attack=0.05, release=0.25, voices=3)
        s.hn(m - 12, t0, t1 - t0 + 0.02, hv * 0.9, kind="trombone", part="tbn", attack=0.04, release=0.25)
        if b >= 16:
            s.hn(m + 12, t0, t1 - t0 + 0.02, 0.75, kind="trumpet", part="tpt", attack=0.03, release=0.25)
            s.str_("vln1", m + 12, t0, t1 - t0 + 0.03, 0.75, attack=0.06, release=0.3, voices=5)
    # into the hit: snare roll, timpani roll, reverse cymbal, riser
    s.drum(S.snare_roll(G(63) - G(55) - 0.03, 0.2, 0.95), G(55), PAN["snare"])
    s.timp(nm("A2"), G(61), 0.95, roll=G(63) - G(61) - 0.03)
    s.drum(S.reverse_cymbal(G(63) - G(59), 0.75), G(59), PAN["cym"], bus="fx")
    s.drum(S.riser(G(63) - G(57), 250, 4000, 0.15), G(57), 0.0, bus="fx")


def explosion(s):
    """The hit: one D minor tutti, then the bottom drops out. Slow motion: a high violin harmonic over a low choir.
    The fireball: the braam. The card: the theme's head, alone on a horn, turning to A for the end card."""
    t = T["hit"]
    for m in nms("D2 D3 A3"):
        s.hn(m, t, 0.35, 1.0, kind="trombone", part="tbn", attack=0.01, release=1.2)
    for m in nms("D4 F4 A4"):
        s.hn(m, t, 0.35, 0.95, attack=0.02, release=1.2)
    s.hn(nm("D5"), t, 0.35, 0.9, kind="trumpet", part="tpt", attack=0.01, release=1.0)
    s.chord_str(nms("D1 D2 D3 A3 D4 F4 A4 D5"), t, 0.35, 0.85,
                parts=["cb", "cb", "vc", "vc", "vla", "vln2", "vln1", "vln1"], attack=0.01, release=1.4)
    s.choir(nms("D4 F4 A4 D5"), t, 0.4, 0.55, "a", attack=0.03, release=2.0)
    s.timp(nm("D2"), t, 1.0)
    s.drum(S.taiko(1.0), t, 0.0, 1.0)
    s.drum(S.gran_cassa(1.0), t, 0.0, 1.0)
    s.drum(S.sub_drop(1.0), t, 0.0, 1.0)
    s.drum(S.cymbal(1.0, 4.0), t, PAN["cym"], bus="fx")
    # slow motion (from t + 0.7): time stretches
    sm0, fire = t + 0.7, 55.07
    s.chord_str(nms("A5 D6"), sm0, 4.6, 0.2, parts=["vln2", "vln1"], attack=1.2, release=1.5, vib=0.002)
    s.choir(nms("D3 A3"), sm0, 4.0, 0.3, "u", attack=1.5, release=1.5)
    s.str_("cb", nm("D2"), sm0, 4.3, 0.35, attack=1.5, release=1.2)
    s.drum(S.reverse_cymbal(fire - 54.0, 0.5), 54.0, PAN["cym"], bus="fx")
    s.drum(S.riser(fire - 54.0, 120, 900, 0.1), 54.0, 0.0, bus="fx")
    # the fireball
    s.put("brass", S.braam(nm("D2"), 2.6, 1.0), fire, 0.0, 0.9)
    s.drum(S.gran_cassa(1.0, 38, 2.2), fire, 0.0, 1.0)
    s.drum(S.sub_drop(1.0, 70, 28, 3.0), fire, 0.0, 0.9)
    s.drum(S.cymbal(0.8, 4.0, dark=True), fire, PAN["cym"], bus="fx")
    s.choir(nms("D3 A3 D4 F4"), fire, 2.5, 0.5, "a", attack=0.2, release=2.0)
    s.str_("vc", nm("D2"), fire + 0.5, 3.4, 0.4, attack=1.0, release=1.0)
    s.str_("cb", nm("D1") + 12, fire + 0.5, 3.4, 0.35, attack=1.0, release=1.0)
    # the card: the theme's head on the horn, D minor, B-flat, C, A
    c, q = T["card3"], 0.9
    for b, d, n, v in ((0, 2, "A3", .55), (2, 1, "D4", .58), (3, 1, "E4", .6), (4, 0.6, "E4", .5)):
        s.hn(nm(n), c + b * q, d * q + 0.03, v, attack=0.1, release=0.5)
    for b, d, bass, up in ((0, 2, "D2", "D3 A3 F4"), (2, 1, "Bb1", "D3 F3 D4"), (3, 1, "C2", "E3 G3 C4"),
                           (4, 1.4, "A1", "E3 A3 C#4")):
        t0 = c + b * q
        s.str_("cb", nm(bass), t0, d * q + 0.05, 0.35, attack=0.4, release=0.6)
        s.chord_str(nms(up), t0, d * q + 0.05, 0.28, parts=["vc", "vla", "vln2"], attack=0.4, release=0.6)
    # into the white
    s.drum(S.reverse_cymbal(1.6, 0.6), T["end"] - 1.6, PAN["cym"], bus="fx")
    s.drum(S.riser(1.6, 400, 6000, 0.11), T["end"] - 1.6, 0.0, bus="fx")
    s.drum(S.sea(T["end"] - sm0, 0.25), sm0, bus="sea")


def end_card(s):
    """Out of the white on the dominant; the title on D major, the whole orchestra; it lets go on the aside, two
    timpani for the little salvo, and the ship's bell to close."""
    t0, ti = E(0), E(2)
    # A major, shimmering, the melody E - C# into the title's D
    s.chord_str(nms("A4 C#5 E5"), t0, ti - t0 + 0.05, 0.4, parts=["vla", "vln2", "vln1"], attack=0.25,
                release=0.3, trem=10)
    s.str_("cb", nm("A1"), t0, ti - t0, 0.45, attack=0.3, release=0.3)
    s.choir(nms("A3 E4"), t0, ti - t0, 0.3, "o", attack=0.4)
    s.harp_arp(nms("A2 E3 A3 C#4 E4 A4 C#5 E5"), t0, 0.06, 0.4)
    s.hn(nm("E4"), E(0), E(1) - E(0), 0.6, attack=0.08, release=0.25)
    s.hn(nm("C#4"), E(1), E(2) - E(1), 0.62, attack=0.08, release=0.25)
    s.timp(nm("A2"), E(1), 0.5, roll=E(2) - E(1) - 0.04)
    # the title: D major
    hold = T["aside"] - ti
    s.str_("cb", nm("D1") + 12, ti, hold, 0.8, attack=0.03, release=0.9)
    s.chord_str(nms("D2 D3 A3 F#4 A4 D5 F#5 A5"), ti, hold, 0.62,
                parts=["cb", "vc", "vc", "vla", "vla", "vln2", "vln1", "vln1"], attack=0.05, release=0.9)
    for m in nms("D3 A3 D4"):
        s.hn(m, ti, hold, 0.75, kind="trombone", part="tbn", attack=0.05, release=0.9, swell=0.15)
    for m in nms("F#4 A4 D5"):
        s.hn(m, ti, hold, 0.75, attack=0.06, release=0.9, swell=0.15)
    s.choir(nms("D4 F#4 A4 D5"), ti, hold, 0.42, "a", attack=0.3, release=1.2)
    s.timp(nm("D2"), ti, 0.95)
    s.drum(S.gran_cassa(0.8), ti, 0.0, 0.85)
    s.drum(S.cymbal(0.75, 3.5), ti, PAN["cym"], bus="fx")
    # NAVAL BATTLES: a celesta sparkle; the release line typing
    sub = T["end"] + 3.2
    for i, m in enumerate(nms("D6 A6 F#6 D7")):
        s.cel(m, sub + i * 0.11, 0.3)
    # [HAH, AS IF]: it lets go; a plucked D, two soft timpani for the little salvo, the bell
    a = T["aside"]
    s.harp(nm("D3"), a + 0.05, 0.55)
    s.harp(nm("A2"), a + 0.45, 0.4)
    s.timp(nm("D2"), T["end_salvo"], 0.35)
    s.timp(nm("A1") + 12, T["end_salvo"] + 0.15, 0.3)
    s.chord_str(nms("D4 F#4 A4"), a + 0.3, T["total"] - a - 0.6, 0.18, parts=["vla", "vln2", "vln1"],
                attack=1.0, release=0.6)
    s.bell(nm("D5"), T["end"] + 6.3, 0.4)
    s.bell(nm("D5"), T["end"] + 6.72, 0.33)
    s.drum(S.sea(T["total"] - a, 0.35), a, bus="sea")


# ------------------------------------------------------------------------------------------------------ the mix
GAINS = dict(strings=0.8, brass=1.15, choir=0.55, keys=0.8, perc=1.15, fx=0.5, sea=0.9)


def render(t0=0.0, t1=None):
    s = Score(t0, t1)
    for part in (cold_open, montage, stamp, theme_zoom, battle, explosion, end_card):
        print(f"  {part.__name__}", flush=True)
        part(s)
    print("  reverb", flush=True)
    stems = s.mx.render()
    n = int(round(T["total"] * S.SR))
    stems = {k: v[:n] * GAINS[k] for k, v in stems.items()}
    # the trailer's own fades: in over the first second, out with the end card's last 0.7 s
    tt = np.arange(n) / S.SR
    fade = np.clip(tt / 0.5, 0, 1) * np.clip((T["total"] - tt) / 0.7, 0, 1) ** 1.5
    stems = {k: v * fade[:, None] for k, v in stems.items()}
    return stems


def master(stems, lufs=-14.0):
    """Sum, soft-clip, limit to -1 dBFS and bring the integrated loudness to `lufs` (iterating, since the limiter
    eats some of each push)."""
    import pyloudnorm as pyln
    mix = sum(stems.values())
    meter = pyln.Meter(S.SR)
    g = 1.0
    for _ in range(6):
        y = S.limiter(np.tanh(mix * g * 1.1) / 1.1, ceiling=10 ** (-1.2 / 20))
        L = meter.integrated_loudness(y)
        g *= 10 ** ((lufs - L) / 20)
        if abs(L - lufs) < 0.2:
            break
    return y, L, g


def mux(wav, out):
    exe = TR.ffmpeg()
    subprocess.run([exe, "-loglevel", "error", "-y", "-i", str(OUT / "fleetwright_trailer.mp4"), "-i", str(wav),
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-shortest",
                    str(out)], check=True)


def cue_report(stems):
    """Each scored hit: where the steepest rise in the drums lands relative to its cue (should be within a frame,
    33 ms)."""
    from scipy.ndimage import uniform_filter1d
    x = stems["perc"].mean(1)
    env = uniform_filter1d(np.abs(x), int(0.004 * S.SR))
    rise = np.diff(env, prepend=0)
    cues = [("stamp", T["stamp"]), ("salvo 1", 24.37), ("salvo 2", 27.20), ("zoom-out", G(23)),
            ("wide shot", T["wide"]), ("enemy cut", T["enemy"]), ("ours cut", T["ours"]), ("hit", T["hit"]),
            ("fireball", 55.07), ("title", T["title"])]
    for name, t in cues:
        i0 = int((t - 0.1) * S.SR)
        on = i0 + int(np.argmax(rise[i0:i0 + int(0.2 * S.SR)]))
        print(f"    {name:10s} {t:7.3f} s  onset {on / S.SR - t:+.3f} s")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--no-mux", action="store_true")
    ap.add_argument("--from", dest="t0", type=float, default=0.0)
    ap.add_argument("--to", dest="t1", type=float, default=None)
    ap.add_argument("--lufs", type=float, default=-14.0)
    args = ap.parse_args()
    print("timeline:", {k: (round(v, 3) if isinstance(v, float) else [round(x, 3) for x in v]) for k, v in T.items()})
    stems = render(args.t0, args.t1)
    y, L, g = master(stems, args.lufs)
    part = args.t0 > 0 or args.t1 is not None
    if part:
        a, b = int(args.t0 * S.SR), int((args.t1 or T["total"]) * S.SR)
        y = y[a:b]
        out = OUT / f"fleetwright_score_{args.t0:g}-{(args.t1 or T['total']):g}.wav"
        S.write_wav(out, y)
        print("wrote", out)
        return
    sd = OUT / "score_stems"
    sd.mkdir(exist_ok=True)
    for k, v in stems.items():
        S.write_wav(sd / f"{k}.wav", v * g, subtype="FLOAT")
    wav = OUT / "fleetwright_score.wav"
    S.write_wav(wav, y)
    print(f"wrote {wav}: {len(y) / S.SR:.2f} s, {L:.1f} LUFS, peak {20 * np.log10(np.abs(y).max()):.1f} dBFS, "
          f"stems in {sd} (x{g:.2f} to match the mix before limiting)")
    cue_report(stems)
    if not args.no_mux:
        mp4 = OUT / "fleetwright_trailer_scored.mp4"
        mux(wav, mp4)
        print("wrote", mp4)


if __name__ == "__main__":
    main()
