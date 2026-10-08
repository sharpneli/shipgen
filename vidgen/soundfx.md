# Trailer soundtrack — handoff brief for the next Claude session

**Task:** score the Naval game trailer with a soundtrack (music + gun SFX + ambience) generated entirely in code with ZzFX. Deliver a mixed WAV, matching stems, and a muxed preview video.
**Written:** 2026-10-08, after the sound-design research and the Naval ZzFX Kit prototype.
**Read first:** `claude/sound-design-gunfire.md` (gun layering, caliber scaling and distance model; v0.1 and v0.2 prototypes).
**Working reference:** Naval ZzFX Kit, https://claude.ai/artifact/Kqa8qtVbgfsLrSQm1Bd5ZV. Its HTML contains every parameter below. Read it with the Artifact tool (`action: "read"`).

**Where this runs:** Claude Code in WSL (Ubuntu), in the repo where the trailer was storyboarded and rendered. Everything below is Linux-native; no browser is needed.

---

## Setup (WSL)

The whole chain was tested on 2026-10-08 on Linux (Node 22, Python 3, ffmpeg): ZzFX in Node → WAV → numpy/scipy reverb, resample and loudness → ffmpeg mux.

**1. System packages.** Check first; most may already be present from the trailer render.
```bash
node -v; python3 --version; ffmpeg -version | head -1
sudo apt update && sudo apt install -y ffmpeg python3-venv python3-pip   # if anything is missing
# Node 18+ is needed. If absent or old, install via nvm:
# curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash && nvm install --lts
```

**2. Project folder.** Keep it on the Linux filesystem (e.g. `~/naval/...`), not under `/mnt/c`, where I/O is very slow. A sibling `audio/` folder next to the trailer render works well:
```bash
mkdir -p audio/stems audio/out && cd audio
npm init -y && npm i zzfx                         # ZzFX 1.4.x, MIT
python3 -m venv .venv && . .venv/bin/activate
pip install numpy scipy soundfile pyloudnorm     # soundfile bundles libsndfile on x86_64
```

**3. `zzfx-node.mjs`:** loads ZzFX in plain Node and writes float WAVs. Copy it verbatim; this exact file was tested.
```js
import fs from 'fs';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
globalThis.AudioContext = class {};           // ZzFX only needs this to exist; buildSamples is pure math
const src = fs.readFileSync(require.resolve('zzfx/ZzFX.js'), 'utf8').replace(/^export /gm, '');
export const ZZFX = new Function(src + '; return ZZFX;')();
export function writeWav(path, channels, sr = 44100) {   // 32-bit float WAV, 1 or 2 channels
  const n = channels[0].length, ch = channels.length, data = Buffer.alloc(n * ch * 4);
  for (let i = 0; i < n; i++) for (let c = 0; c < ch; c++) data.writeFloatLE(channels[c][i] || 0, (i * ch + c) * 4);
  const h = Buffer.alloc(44);
  h.write('RIFF', 0); h.writeUInt32LE(36 + data.length, 4); h.write('WAVEfmt ', 8); h.writeUInt32LE(16, 16);
  h.writeUInt16LE(3, 20); h.writeUInt16LE(ch, 22); h.writeUInt32LE(sr, 24); h.writeUInt32LE(sr * ch * 4, 28);
  h.writeUInt16LE(ch * 4, 32); h.writeUInt16LE(32, 34); h.write('data', 36); h.writeUInt32LE(data.length, 40);
  fs.writeFileSync(path, Buffer.concat([h, data]));
}
```

**4. Smoke test:** run all three steps; each should print `ok`.
```js
// smoke.mjs  ->  node smoke.mjs
import { ZZFX, writeWav } from './zzfx-node.mjs';
const boom = ZZFX.buildSamples(3,.05,62,.004,.05,1.6,0,1.4,-.035,0,0,0,0,.35,0,0,0,.7,.25,0,0);
let peak = 0; for (const v of boom) peak = Math.max(peak, Math.abs(v));
writeWav('smoke_boom.wav', [boom.map(v => v / peak * 0.9)]);
console.log(`ok: ${(boom.length / 44100).toFixed(2)} s boom -> smoke_boom.wav`);
```
```python
# smoke.py  ->  python smoke.py   (reverb, 44.1->48 kHz, 24-bit, loudness)
import numpy as np, soundfile as sf, pyloudnorm as pyln
from scipy.signal import fftconvolve, resample_poly
x, sr = sf.read("smoke_boom.wav")
t = np.arange(int(sr * 3.4)) / sr
ir = np.random.default_rng(1).standard_normal((len(t), 2)) * ((1 - t / t[-1]) ** 3.2)[:, None]
wet = np.stack([fftconvolve(x, ir[:, c]) for c in range(2)], 1)
mix = np.pad(np.stack([x, x], 1), ((0, len(wet) - len(x)), (0, 0))) + 0.15 * wet / np.abs(wet).max()
mix = resample_poly(mix, 160, 147, axis=0)          # 44.1 kHz -> 48 kHz
mix *= 0.89 / np.abs(mix).max()
sf.write("smoke_mix.wav", mix, 48000, subtype="PCM_24")
print(f"ok: smoke_mix.wav {len(mix)/48000:.2f} s, {pyln.Meter(48000).integrated_loudness(mix):.1f} LUFS")
```
```bash
# mux onto the real trailer (or a dummy) and read loudness and true peak
ffmpeg -y -loglevel error -i ../trailer.mp4 -i smoke_mix.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 256k -shortest smoke_preview.mp4
ffmpeg -nostats -i smoke_mix.wav -af ebur128=peak=true -f null - 2>&1 | tail -12   # summary: I (LUFS) and Peak
```
Expected: about a 1.9 s boom, a 5.3 s mix, around −12 LUFS, peak around −1 dBFS.

**5. Listening (the user, not Claude).**
- **WSLg** (Windows 11) routes Linux audio to Windows, so `ffplay -autoexit -nodisp smoke_mix.wav` plays directly.
- **Otherwise** open it from Windows: `explorer.exe .` opens the folder, or `cmd.exe /c start smoke_preview.mp4` (from a path on the Linux filesystem it opens through `\\wsl$`).
- Claude can't hear the result. Check it objectively instead (section 7) and ask the user to listen at every draft.

**6. Optional:**
- `pip install matplotlib` for spectrogram PNGs, which Claude can view to check the mix.
- Keep the `.venv` and `node_modules` out of git.

---

## 0. Before starting: read the storyboard and the render

The trailer was storyboarded and rendered in the same WSL repo. Find the storyboard and the rendered video and read them first:
- **The video:** use `ffprobe` for duration, fps and any existing audio, and pull stills every second or two (`ffmpeg -i trailer.mp4 -vf fps=1 stills/%03d.png`) to watch the cut.
- **The storyboard:** take timecodes per shot and what happens in each (salvo, hit, magazine explosion, sinking, title card). If the render scripts know the event times, read them from there for frame-exact cues.

Build a **cue sheet** (section 4) from it and confirm it with the user before rendering anything long. Also ask:
- the target length
- the mood (the default is a slow, tense build, then the battle, then a quiet sting under the title)
- whether the trailer has a voice-over or on-screen text that the music must leave room for

---

## 1. What's decided and proven

- **Approach:** everything procedural, no sample files and no AI audio. That means zero licensing friction, and no Steam AI disclosure (Valve's disclosure is for generative AI content, and code-generated synthesis isn't that). If a gap appears that ZzFX can't fill, fall back to CC0 sources (Kenney, Freesound with the CC0 filter, Sonniss GDC bundles) before any AI model, and log every file used.
- **Library:** ZzFX v1.4.0 (MIT, `npm i zzfx`). `ZZFX.buildSamples(...params)` is a **pure function** that returns a Float32 sample array at 44.1 kHz. That makes offline rendering easy (section 3).
- **ZzFXM is not on npm.** The prototype uses its own small scheduler (note arrays → buffers cached per note). Keep doing that; it's simpler for a trailer timeline anyway.
- **User feedback so far:** the prototype "is very promising." The gun and the music loop haven't had detailed tuning notes yet, so treat the parameters as a solid starting point rather than final.

## 2. Gotchas already paid for

1. **The `filter` parameter's sign is inverted from what you'd guess:** negative = low-pass, positive = high-pass (Hz).
2. **Raw ZzFX levels vary wildly** (peaks of 0.03 to 3+). Normalize every layer to peak 1, then mix with explicit gains.
3. **Set `randomness` (param 2) to 0 for musical notes** or they'll be detuned. Keep a little (.05–.1) on SFX for variety.
4. **Browser playback in the artifact viewer:** create the `AudioContext` *inside* the first click (Chrome in the embedded viewer refused to resume one created at load). The ZzFX file ships with `audioContext: new AudioContext`; patch it to `null` and assign it later. This only matters for interactive previews, not for offline renders.
5. **Headless Chromium's audio clock is unreliable** for timing checks. Verify timing on the offline render instead.
6. **You can't listen to the output.** Check it objectively (peak/RMS per section, spectrogram images, cue alignment) and get the user's ears on a short draft early.

## 3. Recommended pipeline (offline, deterministic, no browser)

```
cue sheet (JSON) ──► node render.mjs ──► stems/*.wav (music, guns, ambience)
                                   └──► python mix.py (numpy/scipy: filters, convolution reverb, ducking, limiter)
                                         ──► trailer_mix.wav (48 kHz stereo) ──► ffmpeg mux ──► trailer_preview.mp4
```
- **Node:** stub `globalThis.AudioContext = class{}`. Load ZzFX.js with the `export` keywords stripped, either via `new Function(src + '; return ZZFX;')()` or by importing the module. Call `ZZFX.buildSamples`. This was verified working on 2026-10-08.
- **Rendering:** place every event at an exact sample offset from the cue sheet, so timing is frame-accurate.
- **Varispeed** (caliber scaling, playback rate r): resample by linear interpolation in Node or with `scipy.signal.resample_poly` in Python.
- **Reverb:** convolve with a generated impulse response (stereo noise × (1 − t/T)^3.2, T ≈ 3.4 s) using `scipy.signal.fftconvolve`. Use a longer T (5–6 s) for the far-range rolling tail.
- **Output:** resample to 48 kHz for video. Use a final tanh soft clip plus a peak limiter with a −1 dBFS ceiling, and aim for around −14 LUFS integrated. Measure with ffmpeg's `ebur128` filter (`ffmpeg -i mix.wav -af ebur128 -f null -`).
- **Mux:** `ffmpeg -i trailer.mp4 -i trailer_mix.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 256k -shortest trailer_preview.mp4`
- **Optional:** a browser preview page synced to the video, using the Naval ZzFX Kit code. The offline WAV is the deliverable.

## 4. Cue sheet format

```json
{ "fps": 30, "duration": 75.0, "bpm": 66,
  "cues": [
    { "t": 0.0,  "type": "music",  "section": "intro",  "note": "pads only, swell, bell x2" },
    { "t": 12.4, "type": "gun",    "caliber": 356, "range_km": 0.8, "salvo": 3, "note": "first broadside" },
    { "t": 31.0, "type": "magazine", "range_km": 5, "note": "hero explosion; music drops out at t-0.5" },
    { "t": 68.0, "type": "music",  "section": "sting",  "note": "title card" }
  ] }
```
- **Snap big visual hits to the beat grid where you can** (66 BPM, so 0.909 s per beat, 3.64 s per bar). If the cut can't move, change the tempo locally or let the music drop out for the hit.
- **Distance delay:** the flash is on the frame; the boom lands `range_km × 1000 / 343 / 10` s later (real time ÷ 10, same as the prototype). Do this only when the shot shows a distant ship. A close shot fires on the frame.
- **Ducking:** music ducks 4–8 dB under each gun cue (attack 10 ms, release 0.8 s), and fully under the hero explosion.

## 5. Sound palette

### Guns (from the prototype; param order is ZzFX's 21 slots)
`[volume, randomness, frequency, attack, sustain, release, shape, shapeCurve, slide, deltaSlide, pitchJump, pitchJumpTime, repeatTime, noise, modulation, bitCrush, delay, sustainVolume, decay, tremolo, filter]`
```js
crack: [2.2,.08,1400,0,.01,.35,4,1,0,0,0,0,0,0,0,0,0,.6,.06,0,350]     // mix .45
boom:  [3,.05,62,.004,.05,1.6,0,1.4,-.035,0,0,0,0,.35,0,0,0,.7,.25,0,0] // mix 1.0
roar:  [1.8,.1,90,.01,.25,2.4,4,1,0,0,0,0,0,.4,0,0,0,.5,.3,0,-520]      // mix .7
tail:  [1.2,.1,60,.25,.6,3.5,4,1,0,0,0,0,0,.6,0,0,0,.6,.5,0,-260]       // mix .55, plus echoes at +0.45/+1.15/+2.1 s (×.35/.22/.12)
clank: [.6,.05,420,0,.01,.12,3,2,0,0,-180,.04,0,0,0,0,.05,1,0,0,0]      // mix .22, unscaled, only at < 1 km
```
- **Caliber:** playback rate = 203 ÷ caliber_mm on everything except the clank (pulse duration T ∝ caliber).
- **Range:** air low-pass at 16000/(1+1.2·km)^1.1 Hz; crack gain × max(.05, 1 − .18·km); more reverb as range grows; a tanh shaper on the gun bus.
- **Salvo:** 3 guns staggered 0–240 ms, pitch ±4 %.
- **Known weakness:** 14"/16" guns may sound thin in pure ZzFX. For hero shots, consider porting the v0.1 Friedlander + modal-body synth (Gun Voice Bench, https://claude.ai/artifact/AeL5XsBUYQWHnWc7SJmwkH) into the offline renderer, or layer it under the ZzFX boom.

### Sounds still to design for the trailer
These are new; derive them from the project's VFX docs so the sound matches the visuals.
- **Magazine explosion** (`claude/magazine-explosion-vfx-research.md` §4 timeline, `07_magazine_explosions.md`):
  - jet phase −1…0 s: rising hiss/roar from the openings
  - t = 0: fireball. A much longer, lower boom (rate around 0.25–0.35) plus a debris crackle (short noise bursts randomized over 0–6 s)
  - 2–15 s: a long rumble; the pall drifting
  - long range: real delay ÷ 10 and a heavy low-pass
- **Shell incoming:** a pitch-falling noise "freight train" (noise shape, slide down, band-limited around 300–1200 Hz), then the splash or hit.
- **Water splash / near miss:** a noise burst with a high-pass, then a low-passed wash; a soft thump underneath.
- **Sinking** (`claude/sinking-vfx-research.md`): metal groans (sine/saw, slow pitch-drift modulation, slight bitCrush), air bursts, boils.
- **Ambience bed:** sea wash (low-passed noise swells, 6–10 s period), wind (band-passed noise with a slow LFO on the filter, done in the Python mix), distant gunfire as low thuds.

### Music: "Night Watch" (from the prototype) and how to extend it
- **Key and tempo:** D minor, 66 BPM, 8 bars: Dm–B♭–F–C–Dm–Gm–B♭–A. MIDI for bass and pads:
  `[["Dm",38,[62,65,69]],["B♭",46,[62,65,70]],["F",41,[60,65,69]],["C",36,[60,64,67]],["Dm",38,[62,65,69]],["Gm",43,[62,67,70]],["B♭",46,[62,65,70]],["A",45,[61,64,69]]]`
- **Instruments** (frequency slot = note):
  - pad `[.5,0,f,.9,1.6,2.2,1,1,0,0,0,0,0,0,0,0,0,1,0,0,-1100]` (gain .2, panned −.3/0/.3)
  - bass `[.8,0,f,.08,1.2,2,0,1,0,0,0,0,0,0,0,0,0,.8,.4,0,-600]` (root on beat 1, fifth on beat 3)
  - lead `[.35,0,f,.03,.15,1.1,0,1,0,0,0,0,0,0,0,0,.25,.6,.2,0,-2400]`
  - swell `[.5,0,f,1.8,.8,3,4,1,0,0,0,0,0,.5,0,0,0,1,0,0,-700]`
  - ship's bell: sine with partials at ×1, ×2.76 (.45) and ×5.4 (.2), release 2.6 s
- **Lead melody** ([bar, beat, midi]): `[[0,0,74],[0,2,77],[0,3,76],[1,0,74],[1,3,72],[2,0,69],[2,2,72],[2,3,77],[3,0,76],[4,0,77],[4,1.5,76],[4,2,74],[5,0,70],[5,2,74],[6,0,72],[6,1,74],[6,2,77],[7,0,76],[7,2,73]]`
- **Trailer arc** (suggested; adapt to the cut):
  1. **Intro (calm sea):** swell plus pads, two bell strikes, no drums.
  2. **Build:** add the bass, then the lead. Add a low pulse on every beat (a sine kick, e.g. `[1,0,55,0,.02,.3,0,1,-.2]`) and rising noise swells into the battle.
  3. **Battle:** double-time feel (pulse on eighths), and add a low ostinato on D2/A1 (saw, low-pass 400). The guns *are* the percussion, so leave gaps on their cue points.
  4. **Hero hit:** music cuts or drops out 0.5 s before; only the explosion, and silence after.
  5. **Sting/title:** one held Dm(add9) pad chord plus a single bell, 4–6 s fade.

## 6. Deliverables
- `trailer_mix.wav`: 48 kHz, 24-bit, stereo, about −14 LUFS, −1 dBFS peak.
- `stems/music.wav`, `stems/sfx.wav`, `stems/ambience.wav`: same length, so the user can rebalance.
- `trailer_preview.mp4`: the video with the new mix.
- `cue_sheet.json` plus the render scripts (`render.mjs`, `mix.py`): the soundtrack is code, so the scripts *are* the source.
- Send the files to the user, and write the scripts plus a short results note to the project (e.g. `claude/trailer-soundtrack.md` and `claude/trailer_render.mjs`), the same way the other `_ref.py` files are kept.

## 7. Checks before handing back
- **Cue alignment:** per cue, print its time and the measured onset (the first sample above −30 dBFS after the cue). The error should be within 1 frame, except for intended distance delays.
- **Levels:** the integrated LUFS and true peak meet the targets. No clipping in any stem.
- **Spectrogram PNG of the full mix:** the guns should own 30–150 Hz at their hits, and the music should sit out of their way. Look at it.
- **Duration:** matches the video to within 1 frame.
- **Early draft:** send a 20–30 s draft of the first battle section before rendering everything, so the user can react to the sound.

## 8. Related project docs
- `claude/sound-design-gunfire.md`: gun physics, scaling law, distance model, prototypes v0.1 and v0.2
- `claude/magazine-explosion-vfx-research.md`, `claude/damage-research/07_magazine_explosions.md`: explosion timeline to sync against
- `claude/damage-research/08_gunfire_effects.md`, `claude/muzzle-flash-smoke-research.md`: what each shot looks like
- `claude/sinking-vfx-research.md`, `claude/wake-vfx-research.md`, `claude/ocean-surface-research.md`: sea and sinking visuals for the ambience
- `claude/realtime-tech-stack-plan.md`: the eventual in-game audio stack (keep the trailer code reusable for it)