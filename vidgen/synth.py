#!/usr/bin/env python3
"""
synth: a small offline orchestra in numpy, for the trailer score (score.py) and later the game.

Every voice is additive synthesis: a note is a sum of partials, each with its own amplitude envelope, so a
spectrum can change over time (a horn brightening as it swells, a harp's upper partials dying first) without any
time-varying filters. Everything returns float32 mono at SR; the Mixer places notes with equal-power panning into
named buses, gives each bus its own convolution hall, and sums them into stems.

No samples and no AI models: every sound is code, so there's nothing to license.

    ~/.venv/bin/python vidgen/synth.py          # -> vidgen/out/synth_demo.wav, every instrument in turn
"""
from __future__ import annotations

import numpy as np
from scipy.signal import fftconvolve, butter, sosfilt

SR = 48000
RNG = np.random.default_rng(1916)


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def _t(n):
    return np.arange(n, dtype=np.float32) / SR


def adsr(n, a, d, s, r_at, r, curve=2.0):
    """An envelope n samples long: attack a s (eased), decay d s to level s, held until r_at s, released over r s."""
    t = _t(n)
    a = max(a, 0.004)
    # ease-out attack: fast at first but with a finite slope, so even an 8 ms attack doesn't click
    e = (1 - (1 - np.clip(t / a, 0, 1)) ** curve).astype(np.float32)
    if d > 0:
        dd = np.clip((t - a) / d, 0, 1)
        e = np.where(t >= a, 1 - (1 - s) * (1 - (1 - dd) ** 2), e)
    rel = np.clip((t - r_at) / max(r, 1e-4), 0, 1)
    e = e * (1 - rel) ** 2
    lvl_at_r = e  # release scales whatever level the envelope had
    return lvl_at_r.astype(np.float32)


def _phase(f0, n, vib=0.0, vib_rate=5.5, vib_delay=0.25, drift=0.0, glide=None):
    """Instantaneous phase (cycles) of a voice: vibrato that fades in after vib_delay, slow random drift, and an
    optional glide (ratio, seconds): the pitch starts at f0*ratio and settles exponentially."""
    t = _t(n)
    f = np.full(n, f0, np.float32)
    if vib:
        ve = np.clip((t - vib_delay) / 0.4, 0, 1)
        f *= 1 + vib * ve * np.sin(2 * np.pi * vib_rate * t + RNG.uniform(0, 6.28))
    if drift:
        k = max(2, int(n / SR * 3) + 2)
        pts = RNG.standard_normal(k).astype(np.float32)
        f *= 1 + drift * np.interp(np.linspace(0, k - 1, n), np.arange(k), pts)
    if glide:
        ratio, tau = glide
        f *= 1 + (ratio - 1) * np.exp(-t / tau)
    return np.cumsum(f) / SR


def _partials(phase, ratios, amps):
    """Sum of sin(2 pi r phase) * amp, where amps is (P,) or (P, n) for time-varying spectra. Partials above
    Nyquist are dropped by the caller."""
    out = np.zeros(phase.shape[0], np.float32)
    off = RNG.uniform(0, 1, len(ratios))
    for r, a, o in zip(ratios, amps, off):
        out += np.sin(2 * np.pi * (r * phase + o)).astype(np.float32) * a
    return out


def _body(freqs, peaks, lo=80.0, hi=5000.0):
    """A smooth spectral envelope: resonance peaks [(Hz, gain, width octaves)] on a band between lo and hi."""
    f = np.maximum(np.asarray(freqs, np.float64), 1.0)
    g = 1 / (1 + (lo / f) ** 4) / (1 + (f / hi) ** 2.5)
    for fc, a, w in peaks:
        g *= 1 + a * np.exp(-0.5 * (np.log2(f / fc) / w) ** 2)
    return g


# ----------------------------------------------------------------------------------------------------- strings
VIOLIN_BODY = [(280, 1.2, 0.3), (500, 0.8, 0.4), (1100, 0.6, 0.5), (2900, 1.4, 0.4)]
CELLO_BODY = [(110, 1.0, 0.4), (220, 1.0, 0.4), (600, 0.6, 0.5), (1500, 0.8, 0.5)]


def strings(m, dur, vel=0.7, attack=0.35, release=0.6, voices=4, bright=1.0, body=None, vib=0.0035,
            trem=0.0, detune=7.0):
    """A string section: `voices` players, each a bowed sawtooth with its own detune (cents), vibrato and drift,
    through a body resonance. trem > 0 gives measured tremolo bowing at that rate (Hz)."""
    f0 = mtof(m)
    body = body or (CELLO_BODY if m < 55 else VIOLIN_BODY)
    n = int((dur + release + 0.05) * SR)
    hi = 1800 + 3200 * vel * bright
    out = np.zeros(n, np.float32)
    for v in range(voices):
        # low notes beat slowly and deeply between few players, so they spread less
        dt = detune * float(np.clip(f0 / 300, 0.35, 1.0))
        cents = (v - (voices - 1) / 2) / max(1, voices - 1) * 2 * dt + RNG.normal(0, 1.0)
        fv = f0 * 2 ** (cents / 1200)
        P = int(min(60, (SR / 2 - 500) / fv))
        k = np.arange(1, P + 1)
        amps = (1 / k) * _body(k * fv, body, hi=hi)
        ph = _phase(fv, n, vib=vib * RNG.uniform(0.8, 1.2), vib_rate=RNG.uniform(4.8, 6.0), drift=0.0015)
        sig = _partials(ph, k, amps)
        dl = int(RNG.uniform(0, 0.03) * SR)                 # players don't start together
        sig *= np.clip(_t(n) / max(attack, 0.006), 0, 1)     # each fades in on their own: a late entry mid-attack clicked
        out[dl:] += sig[: n - dl]
    env = adsr(n, attack, 0.0, 1.0, dur, release, curve=1.6)
    if trem:
        t = _t(n)
        env *= 0.55 + 0.45 * np.abs(np.sin(np.pi * trem * t))
    bow = sosfilt(butter(2, [1500, 7000], "band", fs=SR, output="sos"), RNG.standard_normal(n)).astype(np.float32)
    out = out / voices + bow * 0.012 * vel
    return (out * env * vel).astype(np.float32)


def spiccato(m, vel=0.8, length=0.11, bright=1.0):
    """A short, bouncing bow stroke: strings with a hard attack and a quick decay."""
    n = int((length + 0.25) * SR)
    s = strings(m, length, vel, attack=0.012, release=0.18, voices=3, bright=1.2 * bright, vib=0.0)
    t = _t(len(s))
    return s * np.exp(-t / (length * 1.2)).astype(np.float32)


def pizz(m, vel=0.8):
    """Pizzicato: a plucked string with a short, woody decay."""
    return pluck(m, vel, decay=0.35 if m < 50 else 0.25, bright=0.6, pos=0.18)


# ------------------------------------------------------------------------------------------------------- brass
def brass(m, dur, vel=0.7, attack=0.07, release=0.35, kind="horn", voices=2, swell=0.0):
    """Horns (dark, round) or trombones/trumpets (brighter). The spectrum brightens with loudness and through the
    attack, which is what makes it read as brass; a small pitch scoop and breath noise at the start.
    swell > 0 makes the note crescendo over its length (0..1)."""
    f0 = mtof(m)
    n = int((dur + release + 0.05) * SR)
    t = _t(n)
    base = {"horn": 2.2, "trombone": 3.4, "trumpet": 4.2}[kind]
    cut = {"horn": 2200, "trombone": 3800, "trumpet": 6000}[kind]
    env = adsr(n, attack, 0.15, 0.82, dur, release, curve=1.3)
    if swell:
        env *= (1 - swell) + swell * np.clip(t / max(dur, 0.1), 0, 1) ** 1.5
    bright = base * (0.45 + 0.9 * vel) * (0.4 + 0.6 * env)        # partial count that's "lit", follows the envelope
    out = np.zeros(n, np.float32)
    for v in range(voices):
        fv = f0 * 2 ** (RNG.normal(0, 4) / 1200)
        P = int(min(40, 12000 / fv))
        k = np.arange(1, P + 1, dtype=np.float32)
        tilt = _body(k * fv, [(1100 if kind == "horn" else 1500, 0.6, 0.6)], lo=60, hi=cut)
        amps = np.exp(-(k[:, None] - 1) / bright[None, :]) * tilt[:, None].astype(np.float32)
        ph = _phase(fv, n, vib=0.0018, vib_rate=5.0, vib_delay=0.5, drift=0.001, glide=(0.985, 0.03))
        dl = int(RNG.uniform(0, 0.02) * SR)
        # each player saturates on their own: through one shared tanh the players' beating made low rumble
        sig = np.tanh(_partials(ph, k, amps) * env * vel * 1.4) / 1.4
        out[dl:] += sig[: n - dl]
    breath = sosfilt(butter(2, [400, 3000], "band", fs=SR, output="sos"), RNG.standard_normal(n)).astype(np.float32)
    out = out / voices + breath * 0.02 * np.exp(-t / 0.08) * env * vel
    return out.astype(np.float32)


def braam(root, dur=3.5, vel=1.0):
    """The trailer horn: low brass in octaves and a fifth, overblown and saturated, with a sub under it."""
    parts = [brass(root, dur, vel, attack=0.12, release=1.2, kind="trombone", voices=3),
             brass(root + 12, dur, vel * 0.8, attack=0.12, release=1.2, kind="trombone", voices=3),
             brass(root + 19, dur, vel * 0.6, attack=0.15, release=1.2, kind="horn", voices=2),
             brass(root - 12, dur, vel * 0.7, attack=0.1, release=1.2, kind="trombone", voices=2)]
    n = max(len(p) for p in parts)
    out = sum(np.pad(p, (0, n - len(p))) for p in parts)
    t = _t(n)
    sub = np.sin(2 * np.pi * mtof(root - 12) * t) * np.exp(-t / 1.8) * np.clip(t / 0.08, 0, 1)
    return (np.tanh(out * 1.8) * 0.7 + sub * 0.5).astype(np.float32)


# ------------------------------------------------------------------------------------------------------- choir
# formants: (Hz, gain, width in octaves). Broad and moderate: narrow, tall peaks made any note whose fundamental
# sat on one (A4 on the "o" at 450 Hz) jump 12 dB out of a chord
VOWELS = {"a": [(800, 3, 0.4), (1150, 1.5, 0.4), (2900, 0.8, 0.3)],
          "o": [(450, 3, 0.4), (800, 1.5, 0.4), (2830, 0.4, 0.3)],
          "u": [(325, 3, 0.4), (700, 0.8, 0.4), (2530, 0.2, 0.3)]}


def choir(m, dur, vel=0.6, vowel="o", attack=0.6, release=1.0, voices=6):
    """A choir section on one pitch: breathy voices with wide vibrato through vowel formants."""
    f0 = mtof(m)
    n = int((dur + release + 0.05) * SR)
    out = np.zeros(n, np.float32)
    for v in range(voices):
        fv = f0 * 2 ** (RNG.normal(0, 8) / 1200)
        P = int(min(50, (SR / 2 - 500) / fv))
        k = np.arange(1, P + 1)
        amps = (1 / k ** 1.2) * _body(k * fv, VOWELS[vowel], lo=90, hi=3500)
        amps *= 1.9 / np.sqrt((amps ** 2).sum())           # every pitch at the same energy, whatever the vowel
        ph = _phase(fv, n, vib=0.006, vib_rate=RNG.uniform(4.5, 5.8), vib_delay=0.3, drift=0.002)
        out += _partials(ph, k, amps)
    t = _t(n)
    air = sosfilt(butter(2, [600, 5000], "band", fs=SR, output="sos"), RNG.standard_normal(n)).astype(np.float32)
    out = out / voices + air * 0.03
    return (out * adsr(n, attack, 0, 1, dur, release, curve=1.5) * vel).astype(np.float32)


# ---------------------------------------------------------------------------------------------- plucked, struck
def pluck(m, vel=0.7, decay=2.5, bright=1.0, pos=0.28, inharm=1.5e-4):
    """A harp string: partials shaped by where it's plucked, each dying faster the higher it is."""
    f0 = mtof(m)
    tau = decay * (220 / max(f0, 60)) ** 0.35
    n = int(min(tau * 5, 8) * SR)
    t = _t(n)
    P = int(min(40, (SR / 2 - 500) / f0))
    out = np.zeros(n, np.float32)
    for k in range(1, P + 1):
        fk = f0 * k * np.sqrt(1 + inharm * k * k)
        if fk > SR / 2 - 500:
            break
        a = abs(np.sin(np.pi * k * pos)) / k ** (1.6 - 0.5 * bright)
        out += (a * np.sin(2 * np.pi * fk * t + RNG.uniform(0, 6.28)) * np.exp(-t * (1 + 0.6 * (k - 1)) / tau)
                ).astype(np.float32)
    click = sosfilt(butter(2, 3000, "high", fs=SR, output="sos"), RNG.standard_normal(n)).astype(np.float32)
    out += click * 0.05 * np.exp(-t / 0.003)
    tail = np.clip((n / SR - t) / (0.2 * n / SR), 0, 1)        # fade the last fifth, no cut-off
    return (out * vel * np.clip(t / 0.002, 0, 1) * tail).astype(np.float32)


def celesta(m, vel=0.6):
    """Celesta / glockenspiel: a struck bar (inharmonic overtones that die quickly) over a resonator."""
    f0 = mtof(m)
    n = int(2.2 * SR)
    t = _t(n)
    out = np.zeros(n, np.float32)
    for r, a, tau in ((1, 1.0, 1.1), (2.0, 0.2, 0.6), (3.0, 0.08, 0.3), (2.76, 0.3, 0.25), (4.0, 0.12, 0.2),
                      (5.40, 0.15, 0.08), (8.93, 0.06, 0.04)):
        if f0 * r < SR / 2 - 500:
            out += (a * np.sin(2 * np.pi * f0 * r * t + RNG.uniform(0, 6.28)) * np.exp(-t / tau)).astype(np.float32)
    hammer = sosfilt(butter(2, [1500, 7000], "band", fs=SR, output="sos"), RNG.standard_normal(n))
    out += hammer * 0.25 * np.exp(-t / 0.004)
    return (out * vel * np.clip(t / 0.001, 0, 1)).astype(np.float32)


def bell(m, vel=0.7, decay=4.0):
    """A ship's bell: a small bronze bell's partials (hum, prime, minor tierce, quint, nominal, ...)."""
    f0 = mtof(m)
    n = int(decay * 1.6 * SR)
    t = _t(n)
    out = np.zeros(n, np.float32)
    for r, a, td in ((0.5, 0.35, 1.0), (1.0, 1.0, 0.75), (1.19, 0.55, 0.5), (1.5, 0.3, 0.45), (2.0, 0.6, 0.35),
                     (2.51, 0.25, 0.2), (2.66, 0.2, 0.18), (3.01, 0.18, 0.15), (4.1, 0.1, 0.08)):
        fr = f0 * r
        if fr < SR / 2 - 500:
            beat = 1 + 0.06 * np.sin(2 * np.pi * RNG.uniform(0.6, 2.2) * t)    # slight beating of split partials
            out += (a * beat * np.sin(2 * np.pi * fr * t + RNG.uniform(0, 6.28)) * np.exp(-t / (decay * td))
                    ).astype(np.float32)
    clang = sosfilt(butter(2, [2000, 9000], "band", fs=SR, output="sos"), RNG.standard_normal(n)).astype(np.float32)
    out += clang * 0.25 * np.exp(-t / 0.006)
    return (out * vel * 0.5).astype(np.float32)


# -------------------------------------------------------------------------------------------------- percussion
def timpani(m, vel=0.8, decay=1.6, roll=0.0):
    """A kettle drum: the membrane's near-harmonic modes over a dull thump, the pitch sagging just after the hit.
    roll > 0: a single-stroke roll that long (s), crescendo from vel/4 to vel."""
    if roll:
        hits = []
        rate = 0.055
        k = int(roll / rate)
        n = int((roll + decay * 3) * SR)
        out = np.zeros(n, np.float32)
        for i in range(k):
            v = vel * (0.25 + 0.75 * (i / max(1, k - 1)) ** 1.6) * RNG.uniform(0.85, 1.0)
            h = timpani(m, v, decay * 0.9)
            o = int((i * rate + RNG.normal(0, 0.004)) * SR)
            o = max(0, o)
            out[o:o + len(h)] += h[: n - o]
        return out * 0.6
    f0 = mtof(m)
    n = int(decay * 3 * SR)
    t = _t(n)
    sag = 1 + 0.025 * vel * np.exp(-t / 0.05)
    ph = np.cumsum(f0 * sag) / SR
    out = np.zeros(n, np.float32)
    for r, a, td in ((0.52, 0.5, 0.15), (1.0, 1.0, 1.0), (1.504, 0.55, 0.6), (1.742, 0.3, 0.45), (2.0, 0.25, 0.4),
                     (2.245, 0.12, 0.3), (2.494, 0.1, 0.25), (2.8, 0.06, 0.2)):
        out += (a * np.sin(2 * np.pi * r * ph) * np.exp(-t / (decay * td))).astype(np.float32)
    mallet = sosfilt(butter(2, 900, "low", fs=SR, output="sos"), RNG.standard_normal(n)).astype(np.float32)
    out += mallet * 0.6 * vel * np.exp(-t / 0.012)
    felt = sosfilt(butter(2, [1000, 4000], "band", fs=SR, output="sos"), RNG.standard_normal(n)).astype(np.float32)
    out += felt * 0.25 * vel * np.exp(-t / 0.005)
    return (out * vel * np.clip(t / 0.0015, 0, 1)).astype(np.float32)


def taiko(vel=0.9, f=58.0, decay=0.55):
    """A big drum: a low membrane with a sharp pitch drop, a slap on top."""
    n = int((decay * 4) * SR)
    t = _t(n)
    fr = f * (1 + 0.9 * np.exp(-t / 0.025))
    ph = np.cumsum(fr) / SR
    out = np.sin(2 * np.pi * ph) * np.exp(-t / decay)
    out += 0.35 * np.sin(2 * np.pi * 1.6 * ph) * np.exp(-t / (decay * 0.35))
    out += 0.2 * np.sin(2 * np.pi * 2.3 * ph) * np.exp(-t / (decay * 0.2))
    slap = sosfilt(butter(2, [150, 1800], "band", fs=SR, output="sos"), RNG.standard_normal(n))
    out += slap * 0.7 * np.exp(-t / 0.018)
    return (np.tanh(out * 1.3) * vel * np.clip(t / 0.0008, 0, 1)).astype(np.float32)


def gran_cassa(vel=0.9, f=42.0, decay=1.6):
    """Orchestral bass drum: a deep, long boom."""
    return taiko(vel, f, decay) * 0.9


def snare(vel=0.7, tone=175.0, head=1.0):
    """A field drum. The batter head rings in two modes that sag in pitch; the wires under the bottom head buzz
    only while it moves, so their noise is gated by the head's own motion and coloured by a resonance around 4 kHz,
    not a flat hiss. Louder hits get relatively more wire."""
    n = int(0.45 * SR)
    t = _t(n)
    sag = 1 + 0.12 * np.exp(-t / 0.012)
    hd = (np.sin(2 * np.pi * np.cumsum(tone * sag) / SR) * np.exp(-t / 0.07)
            + 0.45 * np.sin(2 * np.pi * np.cumsum(tone * 1.59 * sag) / SR) * np.exp(-t / 0.04))
    stick = sosfilt(butter(2, [800, 3000], "band", fs=SR, output="sos"), RNG.standard_normal(n)) * np.exp(-t / 0.003)
    wires = sosfilt(butter(2, [2500, 6500], "band", fs=SR, output="sos"), RNG.standard_normal(n))
    wires = sosfilt(butter(2, 8000, "low", fs=SR, output="sos"), wires)
    gate = np.abs(hd) ** 0.7 * np.clip((t - 0.002) / 0.004, 0, 1)            # the wires follow the head
    wires = wires * (gate * 0.7 + 0.3 * np.exp(-t / 0.05)) * np.exp(-t / 0.09)
    out = hd * 0.75 * head + stick * 0.3 * head + wires * (0.35 + 0.35 * vel)
    return (out * vel * np.clip(t / 0.0005, 0, 1)).astype(np.float32)


def snare_roll(dur, v0=0.2, v1=0.8):
    """A buzz roll, crescendo from v0 to v1 over dur seconds."""
    rate = 0.04
    k = int(dur / rate)
    n = int((dur + 0.5) * SR)
    out = np.zeros(n, np.float32)
    for i in range(k):
        v = v0 + (v1 - v0) * (i / max(1, k - 1)) ** 1.4
        h = snare(v * RNG.uniform(0.75, 1.0) * (0.85 if i % 2 else 1.0), head=0.3)
        o = int((i * rate + RNG.normal(0, 0.003)) * SR)
        o = max(0, o)
        out[o:o + len(h)] += h[: n - o]
    return out * 1.0


def cymbal(vel=0.7, decay=3.0, dark=False):
    """A suspended cymbal: a few hundred inharmonic plate modes (log-spread 250 Hz .. 11 kHz), the higher ones dying
    faster, each wobbling a little so it shimmers; a short stick tick on top. Noise is only a trace, so it reads
    as metal rather than hiss. dark: the top rolled off (a larger, lower cymbal)."""
    n = int(decay * 1.5 * SR)
    t = _t(n)
    out = np.zeros(n, np.float32)
    top = 7000 if dark else 12000
    fs = np.exp(RNG.uniform(np.log(280), np.log(top), 700))
    for f in fs:
        a = (f / 3000) ** 0.25 * RNG.uniform(0.3, 1.0)            # a cymbal's energy sits at 3-8 kHz
        a *= min(1.0, (f / 700) ** 2)                              # and tapers off below 700 Hz
        if f > 7000:
            a *= np.exp(-(f - 7000) / 3000)
        td = min(decay, decay * 0.6 * (f / 3000) ** -0.35) * RNG.uniform(0.6, 1.2)
        wob = 1 + 0.25 * np.sin(2 * np.pi * RNG.uniform(2, 7) * t + RNG.uniform(0, 6.28))
        out += (a * wob * np.sin(2 * np.pi * f * t + RNG.uniform(0, 6.28)) * np.exp(-t / td)).astype(np.float32)
    out /= np.sqrt(len(fs))
    # the bloom: a crash gets brighter for a moment after the stick lands as the plate's energy spreads upward
    out *= (1 - 0.5 * np.exp(-t / 0.03))
    tickn = sosfilt(butter(2, [3000, 8000], "band", fs=SR, output="sos"), RNG.standard_normal(n))
    out += tickn * 0.4 * np.exp(-t / 0.006)
    hiss = sosfilt(butter(2, 5000, "high", fs=SR, output="sos"), RNG.standard_normal(n))
    out += hiss * 0.12 * np.exp(-t / (decay * 0.25))
    return (out * vel * 0.6 * np.clip(t / 0.001, 0, 1)).astype(np.float32)


def reverse_cymbal(dur, vel=0.7):
    """A cymbal played backwards: swells for dur s and stops dead (place it to end on the hit)."""
    c = cymbal(vel, decay=dur * 0.5)
    n = int(dur * SR)
    c = c[:n][::-1].copy()
    if len(c) < n:
        c = np.pad(c, (n - len(c), 0))
    c *= np.clip(np.linspace(-0.2, 1, n), 0, 1) ** 2
    return c.astype(np.float32)


def riser(dur, f0=200.0, f1=2400.0, vel=0.4):
    """A filtered noise sweep upward, for builds."""
    n = int(dur * SR)
    out = np.zeros(n, np.float32)
    seg = SR // 100
    noise = RNG.standard_normal(n).astype(np.float32)
    zi = None
    for i in range(0, n, seg):                       # the band moves every 10 ms, the filter state carried over
        fc = f0 * (f1 / f0) ** (i / n)
        sos = butter(1, [fc * 0.7, min(fc * 1.4, SR / 2 - 100)], "band", fs=SR, output="sos")
        if zi is None:
            zi = np.zeros((sos.shape[0], 2))
        out[i:i + seg], zi = sosfilt(sos, noise[i:i + seg], zi=zi)
    env = np.linspace(0, 1, n) ** 2
    return (out * env * vel).astype(np.float32)


def sub_drop(vel=0.9, f0=90.0, f1=32.0, decay=2.5):
    """A sub-bass hit sliding down: felt more than heard."""
    n = int(decay * 2 * SR)
    t = _t(n)
    f = f1 + (f0 - f1) * np.exp(-t / 0.18)
    out = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / decay) * np.clip(t / 0.004, 0, 1)
    return (out * vel).astype(np.float32)


def tick(vel=0.3):
    """A drafting-room tick: a dry, tiny metallic click (a ruling pen on a straightedge)."""
    n = int(0.06 * SR)
    t = _t(n)
    out = sosfilt(butter(2, [3000, 9000], "band", fs=SR, output="sos"), RNG.standard_normal(n)) * np.exp(-t / 0.004)
    for f, a in ((3170, 0.15), (4730, 0.1), (6900, 0.06)):         # a few short, inharmonic metal rings
        out += np.sin(2 * np.pi * f * t + RNG.uniform(0, 6.28)) * np.exp(-t / 0.004) * a
    return (out * vel).astype(np.float32)


def sea(dur, vel=0.3, period=7.0):
    """A calm sea alongside: a mid-band wash (pink noise, 120 Hz .. 2.5 kHz) rising and falling with the swell, and
    on each crest the foam: a brighter hiss with a sparse fizz of bursting bubbles. Little below 100 Hz, so it sits
    under the music without muddying it."""
    n = int(dur * SR)
    t = _t(n)
    w = np.fft.irfft(np.fft.rfft(RNG.standard_normal(n)) / np.sqrt(np.maximum(np.arange(n // 2 + 1), 1)), n)
    wash = sosfilt(butter(2, [120, 2500], "band", fs=SR, output="sos"), w).astype(np.float32)
    wash /= np.abs(wash).std() + 1e-9
    hiss = sosfilt(butter(2, [2000, 8000], "band", fs=SR, output="sos"), RNG.standard_normal(n)).astype(np.float32)
    pops = (RNG.random(n) < 300 / SR) * RNG.uniform(0.3, 1.0, n)   # ~300 bubbles a second
    fizz = sosfilt(butter(2, [2500, 9000], "band", fs=SR, output="sos"), pops).astype(np.float32) * 6
    ph = RNG.uniform(0, 6.28)
    swell = 0.5 + 0.5 * np.sin(2 * np.pi * t / period + ph) * (0.8 + 0.2 * np.sin(2 * np.pi * t / (period * 2.7)))
    crest = np.clip(np.sin(2 * np.pi * t / period + ph - 0.7), 0, 1) ** 2
    out = wash * (0.35 + 0.65 * swell) * 0.25 + (hiss * 0.06 + fizz * 0.05) * crest
    return (out * vel).astype(np.float32)


# ----------------------------------------------------------------------------------------------------- the mix
def hall_ir(seconds=3.2, t60=(3.0, 2.4, 1.3), predelay=0.02, seed=3):
    """A stereo hall impulse: decorrelated noise decaying per band (low, mid, high T60s), early reflections first."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = _t(n)
    bands = [butter(2, 300, "low", fs=SR, output="sos"), butter(2, [300, 3500], "band", fs=SR, output="sos"),
             butter(2, 3500, "high", fs=SR, output="sos")]
    ir = np.zeros((n, 2), np.float32)
    for c in range(2):
        w = rng.standard_normal(n).astype(np.float32)
        for sos, T in zip(bands, t60):
            ir[:, c] += sosfilt(sos, w).astype(np.float32) * np.exp(-6.9 * t / T)
        for _ in range(14):                                   # early reflections
            d = int(rng.uniform(0.008, 0.09) * SR)
            ir[d, c] += rng.uniform(-0.6, 0.6)
    ir *= np.clip(t / 0.03, 0, 1)[:, None] ** 0.5               # a soft onset
    ir = np.pad(ir, ((int(predelay * SR), 0), (0, 0)))
    return ir / np.sqrt((ir ** 2).sum(0, keepdims=True))


class Mixer:
    """Buses of stereo audio at SR. add() places a mono note at t seconds with a pan (-1..1) and gain, and sends
    it to the bus's hall. render() returns {bus: stereo array} with each bus's reverb mixed in."""

    def __init__(self, seconds):
        self.n = int(seconds * SR)
        self.dry, self.wet, self.mix = {}, {}, {}

    def bus(self, name, wet=0.3):
        if name not in self.dry:
            self.dry[name] = np.zeros((self.n, 2), np.float32)
            self.wet[name] = np.zeros((self.n, 2), np.float32)
            self.mix[name] = wet
        return name

    def add(self, bus, sig, t, pan=0.0, gain=1.0, send=None):
        o = int(round(t * SR))
        if o >= self.n or len(sig) == 0:
            return
        if o < 0:
            sig, o = sig[-o:], 0
        sig = sig[: self.n - o]
        a = (pan + 1) * np.pi / 4
        st = np.stack([sig * np.cos(a), sig * np.sin(a)], 1) * gain
        self.dry[bus][o:o + len(sig)] += st
        self.wet[bus][o:o + len(sig)] += st * (self.mix[bus] if send is None else send)

    def render(self, ir=None):
        ir = hall_ir() if ir is None else ir
        out = {}
        for b in self.dry:
            w = self.wet[b]
            if np.any(w):
                r = np.stack([fftconvolve(w[:, c], ir[:, c])[: self.n] for c in range(2)], 1).astype(np.float32)
                # a little crossfeed so the hall surrounds rather than mirrors the panning
                r = r * 0.8 + r[:, ::-1] * 0.2
            else:
                r = 0
            out[b] = self.dry[b] + r * 1.4
        return out


def limiter(x, ceiling=0.89, look=0.004, release=0.08):
    """A transparent peak limiter: gain from a sliding minimum (lookahead) smoothed with a moving average, so it
    never exceeds the ceiling and never clicks."""
    from scipy.ndimage import minimum_filter1d, uniform_filter1d
    peak = np.abs(x).max(1)
    g = np.minimum(1.0, ceiling / np.maximum(peak, 1e-9))
    L = max(3, int(look * SR))
    g = minimum_filter1d(g, L * 2 + 1)
    g = uniform_filter1d(g, L * 2 + 1)
    R = int(release * SR)
    g = np.minimum(g, minimum_filter1d(uniform_filter1d(g, R), 3))     # a slower release on top
    return x * g[:, None]


def write_wav(path, x, subtype="PCM_24"):
    import soundfile as sf
    sf.write(str(path), x, SR, subtype=subtype)


def place(parts, seconds=None):
    """Mono sum of [(t, sig), ...]: a quick way to line notes up outside a Mixer."""
    n = int(seconds * SR) if seconds else max(int(t * SR) + len(s) for t, s in parts)
    out = np.zeros(n, np.float32)
    for t, s in parts:
        o = int(t * SR)
        if o < n:
            out[o:o + len(s)] += s[: n - o]
    return out


def demo():
    """Every instrument in turn, so each voice can be judged on its own."""
    from pathlib import Path
    seq = [("strings", lambda: strings(62, 2.0, 0.6) + strings(65, 2.0, 0.5) + strings(69, 2.0, 0.5), 3.0),
           ("cellos", lambda: strings(38, 2.0, 0.8) + strings(45, 2.0, 0.6), 3.0),
           ("tremolo", lambda: strings(74, 1.6, 0.5, trem=12, attack=0.1), 2.4),
           ("spiccato", lambda: np.concatenate([np.pad(spiccato(m, 0.8), (0, 0))[: int(0.15 * SR)]
                                               for m in [38, 38, 50, 38, 38, 50, 41, 40] * 2]), 2.6),
           ("horn", lambda: np.concatenate([brass(m, 0.55, 0.6)[: int(0.6 * SR)] for m in (57, 62, 64, 65)]
                                           + [brass(65, 1.5, 0.8)]), 4.6),
           ("trombones", lambda: brass(38, 1.8, 0.95, kind="trombone", voices=3) + brass(45, 1.8, 0.9,
                                                                                      kind="trombone"), 3.0),
           ("braam", lambda: braam(26, 2.5), 4.5),
           ("choir", lambda: choir(62, 2.5, 0.6, "o") + choir(69, 2.5, 0.5, "o") + choir(74, 2.5, 0.4, "a"), 4.0),
           ("harp", lambda: place([(i * 0.18, pluck(m, 0.7)) for i, m in enumerate([50, 57, 62, 65, 69, 74, 77, 81])],
                                     3.2), 3.2),
           ("celesta", lambda: place([(i * 0.2, celesta(m, 0.5)) for i, m in enumerate([86, 81, 77, 74])], 2.6), 2.6),
           ("bell", lambda: place([(0, bell(81)), (0.45, bell(81))], 5.0), 5.0),
           ("timpani", lambda: np.concatenate([timpani(38, 0.9)[: int(0.8 * SR)], timpani(45, 0.8)[: int(0.8 * SR)],
                                               timpani(38, 0.9, roll=1.6)]), 5.0),
           ("taiko", lambda: place([(t, taiko(0.9)) for t in (0, 0.45, 0.9, 1.2, 1.65, 2.1)], 3.0), 3.0),
           ("snare", lambda: np.concatenate([snare(0.7)[: int(0.3 * SR)]] * 3 + [snare_roll(1.5)]), 3.0),
           ("cymbal", lambda: np.concatenate([reverse_cymbal(1.5), cymbal(0.8)]), 6.0),
           ("sea", lambda: sea(6.0, 0.5), 6.0)]
    total = sum(s for _, _, s in seq) + 1
    mx = Mixer(total)
    mx.bus("all", 0.3)
    t = 0.5
    for name, fn, secs in seq:
        s = fn()
        s = s / max(1e-6, np.abs(s).max()) * 0.5
        mx.add("all", s, t)
        print(f"{t:6.1f} s  {name}")
        t += secs
    x = mx.render()["all"]
    x = limiter(x / np.abs(x).max() * 0.9)
    out = Path(__file__).resolve().parent / "out" / "synth_demo.wav"
    write_wav(out, x)
    print("wrote", out)


if __name__ == "__main__":
    demo()
