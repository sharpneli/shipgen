"""Figures for claude/muzzle-flash-smoke-research.md (uses muzzle_flash_ref.py).

  mf_strip.png   calibre x time, day and night rows
  mf_zoom.png    one 16" triple + a 40 mm quad, rendered at four map zooms, day / night
  mf_los.png     line-of-sight transmittance through own smoke vs time
"""
import math
import numpy as np
from PIL import Image, ImageDraw
import muzzle_flash_ref as M

WIND = (5.0, 2.0)
T = 160  # tile px


def label(im, txt, xy=(4, 3)):
    d = ImageDraw.Draw(im)
    for o in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        d.text((xy[0] + o[0], xy[1] + o[1]), txt, fill=(0, 0, 0))
    d.text(xy, txt, fill=(255, 235, 140))
    return im


def strip():
    guns = [M.LADDER[0], M.LADDER[2], M.LADDER[7], M.LADDER[8], M.LADDER[12]]
    rows = []
    for g in guns:
        shot = M.Shot(g, h=10, az=0.0, el=0.08, wind=WIND, seed=3)
        shot.sec_on = shot.D["P_sec"] > 0.5
        D = shot.D
        ts = [0.4 * D["t_e"], 0.15 * shot.t_s, 0.5 * shot.t_s, 0.9 * shot.t_s, 3.0, 20.0]
        if not shot.sec_on:
            ts[1:4] = [0.8 * D["t_e"], 0.05, 0.3]
        for night in (False, True):
            tiles = []
            for i, t in enumerate(ts):
                smoke_col = i >= 4
                if smoke_col:
                    p = shot.puff(t)
                    mpp = max(6 * p["sh"], 3 * D["flash_len"]) / T
                    c = (p["xy"][0], p["xy"][1] + 0.6 * 450 * (1 - math.exp(-p["z"] / 450)))
                else:
                    mpp = 1.6 * D["flash_len"] / T
                    c = (0.45 * D["flash_len"], 0.6 * 450 * (1 - math.exp(-10 / 450)))
                img = M.render([shot], t, mpp, T, T, c, night=night, frame_dt=min(1 / 60, max(t, 1e-4)))
                im = Image.fromarray(img[::-1])
                label(im, f"t={t*1e3:.0f}ms" if t < 1 else f"t={t:.0f}s")
                label(im, f"{T*mpp:.0f} m" if T * mpp >= 10 else f"{T*mpp:.1f} m", (4, T - 14))
                tiles.append(im)
            row = Image.new("RGB", (T * len(tiles) + 170, T), (20, 20, 22))
            d = ImageDraw.Draw(row)
            d.text((6, T // 2 - 14), g.name, fill=(230, 230, 230))
            d.text((6, T // 2 + 2), "night" if night else "day", fill=(160, 160, 160))
            for i, im in enumerate(tiles):
                row.paste(im, (170 + i * T, 0))
            rows.append(row)
    sheet = Image.new("RGB", (rows[0].width, T * len(rows) + 2 * len(rows)), (0, 0, 0))
    for i, r in enumerate(rows):
        sheet.paste(r, (0, i * (T + 2)))
    sheet.save("mf_strip.png")


def zoom_ladder():
    big = M.Gun("16\"/50 SPD", 0.406, 50, 297.0, "single_base", igniter=0.01)
    aa = M.Gun("40 mm Bofors", 0.040, 56, 0.31, "single_base", igniter=0.003)
    shots = [M.Shot(big, pos=(0, 3.0 * k), h=12, az=math.pi / 2, el=0.15, t0=0.01 * k, seed=k, wind=WIND) for k in range(3)]
    for s in shots:
        s.sec_on = True
    shots += [M.Shot(aa, pos=(-120 + 2 * k, 10), h=8, az=math.pi / 2 + 0.6, el=0.9, t0=0.1 + 0.005 * k, seed=10 + k,
                     wind=WIND) for k in range(4)]
    for s in shots[3:]:
        s.sec_on = True
    S = 256
    rows = []
    for night in (False, True):
        tiles = []
        for mpp, name in ((0.06, "Detail 15 m"), (0.7, "Ship 180 m"), (3.0, "Squadron 770 m"), (40.0, "Theatre 10 km")):
            c = (-116, 18) if mpp < 0.1 else ((-55, 35) if mpp < 1 else (0, 0))
            img = M.render(shots, 0.12, mpp, S, S, c, night=night)
            im = label(Image.fromarray(img[::-1]), f"{name}  ({mpp} m/px)")
            tiles.append(im)
        row = Image.new("RGB", (S * 4 + 6, S), (0, 0, 0))
        for i, im in enumerate(tiles):
            row.paste(im, (i * (S + 2), 0))
        rows.append(row)
    sheet = Image.new("RGB", (rows[0].width, 2 * S + 2), (0, 0, 0))
    sheet.paste(rows[0], (0, 0)); sheet.paste(rows[1], (0, S + 2))
    sheet.save("mf_zoom.png")


def los_chart():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    # gun at origin fires +y (broadside), wind +x. Observer LOS: horizontal line 15 m high, x = 150 m downwind,
    # running across the wind from y=-3 km to y=+3 km (a spotter looking past the cloud)
    a, b = (150, -3000, 15), (150, 3000, 15)
    tgrid = np.linspace(0.05, 90, 300)
    cases = []
    sp = M.Gun("16\"/50 SPD", 0.406, 50, 297.0, "single_base", igniter=0.01)
    fl = M.Gun("16\"/50 SPCG flashless", 0.406, 50, 312.0, "triple_base", igniter=0.01, salt=0.005)
    five = M.Gun("5\"/38 twin", 0.127, 38, 7.0, "single_base", igniter=0.003, n=2)
    bp = M.Gun("6\" black powder (1880s)", 0.152, 30, 25.0, "black_powder", igniter=0.0)
    def series(name, shots, merge=False):
        T = []
        for t in tgrid:
            puffs = [p for p in (s.puff(t) for s in shots) if p]
            if merge:
                puffs = M.merge_puffs(puffs)
            T.append(math.exp(-M.tau_los(puffs, a, b)))
        cases.append((name, np.array(T)))
    w = (5.0, 0.0)
    series("16\" triple, SPD", [M.Shot(sp, pos=(0, 3 * k), h=12, az=math.pi / 2, el=0.15, wind=w, seed=k) for k in range(3)])
    series("16\" triple, SPCG flashless", [M.Shot(fl, pos=(0, 3 * k), h=12, az=math.pi / 2, el=0.15, wind=w, seed=k) for k in range(3)])
    series("5\"/38 twin, 15 rpm for 60 s", [M.Shot(five, h=10, az=math.pi / 2, el=0.1, wind=w, t0=4.0 * k, seed=k) for k in range(15)], merge=True)
    series("6\" black powder, 1 round", [M.Shot(bp, h=6, az=math.pi / 2, el=0.05, wind=w, seed=1)])
    cols = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
    fig, ax = plt.subplots(figsize=(8.2, 4.2), dpi=130)
    for (name, T), c in zip(cases, cols):
        ax.plot(tgrid, T, color=c, lw=2, label=name)
    ax.set_xlabel("time after first round, s", color="#52514e")
    ax.set_ylabel("transmittance along the LOS", color="#52514e")
    ax.set_ylim(0, 1.02); ax.set_xlim(0, 90)
    ax.grid(color="#e6e5e0", lw=0.8); [s.set_visible(False) for s in ax.spines.values()]
    ax.tick_params(colors="#52514e")
    ax.set_title("Own-smoke obscuration: LOS 15 m high, 150 m downwind of the gun, wind 5 m/s, RH 70 %",
                 fontsize=9.5, color="#0b0b0b", loc="left")
    ax.legend(frameon=False, fontsize=8.5, loc="lower right")
    fig.tight_layout(); fig.savefig("mf_los.png")
    for name, T in cases:
        print(f"{name:32s} min T {T.min():.3f} at {tgrid[T.argmin()]:.1f}s; T>0.9 after {tgrid[np.where(T<0.9)[0].max()] if (T<0.9).any() else 0:.0f}s")


if __name__ == "__main__":
    import time
    t0 = time.time(); strip(); print("strip", round(time.time() - t0, 1), "s")
    t0 = time.time(); zoom_ladder(); print("zoom", round(time.time() - t0, 1), "s")
    los_chart()