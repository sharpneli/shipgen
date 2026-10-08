"""Magazine explosions for vidgen (numpy only): the jet phase, the fireball or the vented flame column, the smoke
cap, stem fires, boiler steam, debris and the thrown gunhouse.

A port of magazine_explosion_ref.py (research: magazine_explosion.md). The particles' physics is the reference's:
buoyancy from a slowly decaying heat content, drag toward a sheared wind, entrainment growth, the mushroom's poloidal
circulation and the soot skin. What vidgen adds or changes is marked DEPARTURE. The reference hand-places its
scene; here every opening and source comes from the exported ship: the magazine room and the mounts it serves, the
machinery rooms beside it, the barbette and the hull outline (`plan`). There's no mechanics resolver yet (research
7 item 1), so the magazine pressure and the opening fail times are the reference's stand-ins.

Units: metres, seconds, kg. World axes are vidgen's (screen x right, y down), z up from the water. Ship-local
positions are +x bow, +y starboard, z up from the water.
"""
from __future__ import annotations

import math

import numpy as np

import muzzle

G, P0 = 9.81, 101325.0
KAPPA = 900.0          # m^2 of extinction per unit particle mass (the reference's)
DH = 4.0e6             # J/kg, cordite's heat of explosion, order of magnitude (research 2.1)
# The propellant burned in the cascade window, as a share of what the magazine holds (research 2.2: M is "not the
# whole magazine"). DEPARTURE, a tuning value until the mechanics resolver gives M: Queen Mary's forward group held
# ~43 t of cordite and fits M ~ 20 t, Invincible's Q ~15 t and fits 2-3 t
F_FAST = 0.3
P_PEAK = 3.0           # bar absolute at the main event (the reference's stand-in for the ODE)
# vented column (tier 1): Lion's "200 ft" needs ~380 kg/s through an 8.5 m barbette (research 2.1), so the burn
# rate is taken as that flux over the barbette's area. DEPARTURE: the reference fixes Q for its one scene
COLUMN_FLUX = 6.7      # kg/s per m^2 of barbette
COLUMN_S = 14.0        # the column's life (the reference's)
# the jet phase (research 2.5, the prototype's sequence), seconds after the first opening fails
T_PORTS, T_HOOD, T_HATCH, T_SCUTTLE, T_VENT, T_LIFT, T_MAIN = 0.0, 0.05, 0.12, 0.22, 0.35, 0.45, 0.9
# the soot skin's extra cooling of the fireball's top and outside. DEPARTURE: 1.8, not the reference's 0.9,
# which was tuned at night; in daylight the whole cap glowed for 10 s
SOOT_SKIN = 1.8
TRAIL_GAP = 1.5        # m of flight per debris trail puff (DEPARTURE, see Blast.step)
# DEPARTURE: the reference's scene is one 20 t event, and its side vents, stem fires and debris speeds are fixed
# numbers. Here they scale with the fireball against that event's (D_REF), so a destroyer's 0.3 t magazine
# doesn't throw a battleship's smoke and wreckage
D_REF = 157.0
HIT_LEAD = 0.5         # from the shell's hit to the first opening failing (the hoists carry the flash down and back)


def fireball(M):
    """Diameter (m) and duration (s) for M kg burned in the fast phase (research 2.2). The two duration laws meet at
    ~14 s, so the switch at 30 t is continuous."""
    D = 5.8 * M ** (1 / 3)
    t = 0.45 * M ** (1 / 3) if M < 30000 else 2.6 * M ** (1 / 6)
    return D, t


def heskestad(Q_kW, D):
    return max(0.235 * Q_kW ** 0.4 - 1.02 * D, 0.0)


def blast_lambda(M, eff=0.5):
    return (eff * DH * M / P0) ** (1 / 3)


def shear(z):
    """Wind at height z over the 10 m wind (power law 0.14, research 2.2)."""
    return (np.maximum(z, 1.0) / 10.0) ** 0.14


# the fire's colour: DEPARTURE, the reference's stylised 0..1 temperature drives a physical blackbody (muzzle.py's
# tables, research 2.6), so fire and muzzle flash share one luminance scale: 1 -> 2000 K (white-yellow core),
# 0.5 -> 1450 K (orange-red), 0.25 -> 1175 K (deep crimson, nearly dark in daylight)
_LT = muzzle._BB_T
_LL = muzzle._BB_L


def fire_K(T):
    return 900.0 + 1100.0 * np.clip(T, 0, 1)


def fire_luminance(T):
    """cd/m^2 of a black surface at the fire temperature for stylised T (vectorised muzzle.bb_luminance)."""
    lnT = np.log(fire_K(T))
    return 10 ** np.interp(lnT, _LT, _LL, left=-40)


def fire_rgb(T):
    K = fire_K(T)
    return np.stack([np.interp(K, muzzle._RGB_T, muzzle._RGB[:, i]) for i in range(3)], -1)


def gun_of(comp):
    """(bore m, calibre length) of a mount's hitbox component (its calibre_mm and calibre_length)."""
    return comp.get("calibre_mm", 150.0) / 1000, comp.get("calibre_length", 45.0)


def propellant_share(comp):
    """The propellant's share of a round's weight: muzzle.py's charge fit against its shell fit (380/52: 23 %)."""
    d, L = gun_of(comp)
    charge = muzzle.Gun(d, L).charge
    return charge / (charge + 14000.0 * d ** 3)


# ---------------------------------------------------------------- particles
class Particles:
    FIELDS = dict(pos=3, vel=3, r=1, m=1, temp=1, heat=1, age=1, life=1, kind=1, tcool=1, seed=1)
    # kind: 0 fire/smoke (soot), 1 steam (white), 2 debris (solid, ballistic), 3 spark. seed: 0..1, picks how the
    # drawing breaks a puff into clumps

    def __init__(self, rng):
        self.d = {k: np.zeros((0, n)) if n > 1 else np.zeros(0) for k, n in self.FIELDS.items()}
        self.rng = rng

    def add(self, **kw):
        n = len(kw["pos"])
        if not n:
            return
        kw.setdefault("seed", self.rng.random(n))
        for k, w in self.FIELDS.items():
            v = np.broadcast_to(np.asarray(kw.get(k, 0.0), float), (n, w) if w > 1 else (n,))
            self.d[k] = np.concatenate([self.d[k], v])

    def keep(self, mask):
        for k in self.d:
            self.d[k] = self.d[k][mask]

    def __len__(self):
        return len(self.d["r"])


# ---------------------------------------------------------------- the plan, from the exported ship
def plan(hit, mounts, mag_ids, tier, t_hit, freeboard, rng):
    """One Blast spec per magazine in mag_ids (room ids, or the id of a mount they serve), the later ones following
    0.3-0.8 s apart (research 4: tier 4's fireballs 0.2-1 s apart along the hull).

    hit: hitboxes.json. mounts: {id: dict(pos=(x, y), top_m, bearing (deg from the bow, as trained), el (rad),
    ports=[(x, y) in the mount's frame, one per barrel, where it leaves the gunhouse])}, from vidgen's mounts.
    tier: 'blast' (tier 3: fireball, gunhouse thrown) or 'column' (tier 1: the roof lifts, the barbette vents a
    flame column, the ship survives). Returns the specs; Blast(spec, rng) runs one."""
    rooms = {r["id"]: r for r in hit["rooms"]}
    comps = {c["id"]: c for c in hit["components"]}
    hull = np.asarray(hit["hull"]["points"] if isinstance(hit["hull"], dict) else hit["hull"], float)
    B = float(hit.get("beam") or 2 * np.abs(hull[:, 1]).max())
    by_mount = {}
    for r in hit["rooms"]:
        if r["kind"] == "magazine":
            for m in ([r["mount"]] if r.get("mount") else r.get("mounts", [])):
                by_mount[m] = r["id"]
    specs, t0 = [], t_hit + HIT_LEAD
    for k, mid in enumerate(mag_ids):
        rid = mid if mid in rooms else by_mount.get(mid) or by_mount.get(mid.upper())
        if rid is None or rooms[rid]["kind"] != "magazine":
            raise ValueError(f"no magazine {mid!r}: magazines are "
                             + ", ".join(r["id"] for r in hit["rooms"] if r["kind"] == "magazine"))
        room = rooms[rid]
        served = [room["mount"]] if room.get("mount") else list(room.get("mounts", []))
        share = np.mean([propellant_share(comps.get(m, {})) for m in served]) if served else 0.23
        M = room["tonnes"] * 1000 * share * F_FAST
        x0, x1 = room["x0"], room["x1"]
        xc = 0.5 * (x0 + x1)
        # the mount over the magazine: its own one, or the served mount nearest the centreline and the room's middle
        own = [m for m in served if m in mounts]
        top = min(own, key=lambda m: abs(mounts[m]["pos"][1]) + abs(mounts[m]["pos"][0] - xc)) if own else None
        barb = comps.get(f"{top} barbette") if top else None
        if barb:
            centre = np.array([barb["x"], barb["y"]])
            bar = dict(xy=centre, r=barb["r"], z=freeboard + barb["top"])
        else:
            centre = np.array([xc, 0.0])
            bar = None
        hw = half_breadth(hull, np.array([xc]))[0]
        t_main = t0 + T_MAIN
        ops = []
        for m in served:
            if m not in mounts:
                continue
            mt = mounts[m]
            a = math.radians(mt["bearing"])
            ca, sa = math.cos(a), math.sin(a)
            hz = mt["top_m"] - 1.5
            for j, p in enumerate(mt["ports"]):
                # gun ports: along the barrels, horizontal but for the guns' elevation (research 2.5)
                x = mt["pos"][0] + p[0] * ca - p[1] * sa
                y = mt["pos"][1] + p[0] * sa + p[1] * ca
                d_eq = 2.5 * gun_of(comps.get(m, {}))[0]
                ops.append(dict(pos=(x, y, hz), dir=(ca * math.cos(mt["el"]), sa * math.cos(mt["el"]),
                                                     math.sin(mt["el"]) + 0.05),
                                d=d_eq, t_fail=t0 + T_PORTS + 0.02 * j, Lmax=90.0))
            # the sighting hood on the roof, a little aft of the pivot: straight up
            ops.append(dict(pos=(mt["pos"][0] - 2.0 * ca, mt["pos"][1] - 2.0 * sa, mt["top_m"]), dir=(0, 0, 1),
                            d=0.6, t_fail=t0 + T_HOOD, Lmax=50.0))
        # deck hatches and ventilators over the magazine, beside the barbette: up, leaning outboard a little
        n_h = max(2, int(round((x1 - x0) / 4.0)))
        off = (bar["r"] + 2.0) if bar else 3.0
        for j in range(n_h):
            x = x0 + (j + 0.5) * (x1 - x0) / n_h
            side = 1 if j % 2 else -1
            y = side * min(off, 0.8 * max(half_breadth(hull, np.array([x]))[0], 1.0))
            ops.append(dict(pos=(x, y, freeboard + 0.5), dir=(0, 0.15 * side, 1), d=0.8,
                            t_fail=t0 + T_HATCH + 0.05 * j / max(1, n_h - 1), Lmax=60.0))
        # side scuttles: sideways from the hull just under the deck edge, abreast the magazine
        for j, side in enumerate((-1, 1, -1, 1)):
            x = x0 + (0.3 + 0.4 * (j // 2)) * (x1 - x0)
            y = side * half_breadth(hull, np.array([x]))[0]
            ops.append(dict(pos=(x, y, max(1.0, freeboard - 1.5)), dir=(0, side, 0.25), d=0.4,
                            t_fail=t0 + T_SCUTTLE + 0.02 * j, Lmax=30.0))
        # machinery rooms beside the magazine (Hood: the flame came out of the engine-room ventilators)
        vents = []
        for r in hit["rooms"]:
            if r["kind"] in ("boiler_room", "engine_room") and (abs(r["x0"] - x1) < 0.6 or abs(r["x1"] - x0) < 0.6):
                vx = 0.5 * (r["x0"] + r["x1"])
                vents.append(np.array([vx, 0.0]))
                for side in (-1, 1):
                    ops.append(dict(pos=(vx, side * 3.0, freeboard + 4.0), dir=(0, 0.1 * side, 1), d=1.2,
                                    t_fail=t0 + T_VENT, Lmax=60.0))
        if bar:   # the roof lifts and the barbette is an opening (capped by its Heskestad column, research 2.5)
            ops.append(dict(pos=(*bar["xy"], bar["z"]), dir=(0, 0, 1), d=2 * bar["r"], t_fail=t0 + T_LIFT,
                            Lmax=120.0))
        boilers = [r for r in hit["rooms"] if r["kind"] == "boiler_room"]
        steam = None
        if boilers:
            b = min(boilers, key=lambda r: abs(0.5 * (r["x0"] + r["x1"]) - xc))
            steam = np.array([0.5 * (b["x0"] + b["x1"]), 0.0])
        D, t_fb = fireball(M)
        specs.append(dict(id=rid, tier=tier, M=M, D=D, t_fb=t_fb, lam=blast_lambda(M if tier == "blast" else 0.05 * M),
                          t_hit=t_hit if k == 0 else None, t0=t0, t_lift=t0 + T_LIFT, t_main=t_main,
                          centre=centre, span=(x0, x1), half_w=hw, B=B, deck_z=freeboard, barbette=bar,
                          mount=top, openings=ops, vents=vents, steam=steam,
                          k=max(0.25, D / D_REF),
                          n_debris=int(round(8 + 70 * (1 - math.exp(-M / 15000.0))))))
        t0 += rng.uniform(0.3, 0.8)
    return specs


def half_breadth(poly, x):
    a, b = poly, np.roll(poly, -1, 0)
    lo, hi = np.minimum(a[:, 0], b[:, 0]), np.maximum(a[:, 0], b[:, 0])
    t = (x[None, :] - a[:, 0:1]) / np.where(b[:, 0] == a[:, 0], 1, b[:, 0] - a[:, 0])[:, None]
    yy = np.abs(a[:, 1:2] + t * (b[:, 1] - a[:, 1])[:, None])
    yy = np.where((x[None, :] >= lo[:, None]) & (x[None, :] <= hi[:, None]), yy, 0)
    return yy.max(0)


# ---------------------------------------------------------------- the event
class Blast:
    """One magazine going up, stepped with the scene. pose (vidgen's) maps ship-local to world: world(xy),
    local(xy), dirw(v), vel (the ship's), on_hull(xy) -> bool. Each step leaves: p (the particles), lights
    [(xyz, I)], new_splashes [(xy, size)], and the shock (xy, t, lam) once the main event has happened. flyers are
    thrown gunhouses: dict(p, v, ang, spin, tilt, tilt_rate, mount, landed), landed None (in the air), "sunk" or
    (ship-local xy, z, ang) on the deck."""

    def __init__(self, spec, rng, wind):
        self.s, self.rng = spec, rng
        self.wind = np.asarray(wind, float)
        self.p = Particles(rng)
        self.done = set()
        self.lights, self.new_splashes, self.flyers = [], [], []
        self.shock = None
        self.thrown = False             # the gunhouse has left its barbette (vidgen stops drawing the mount)
        self.Q = 0.0

    # ---- helpers
    def _w3(self, pose, local3):
        """Ship-local (n, 3) points -> world (n, 3)."""
        local3 = np.atleast_2d(np.asarray(local3, float))
        return np.c_[pose.world(local3[:, :2]), local3[:, 2]]

    def _d3(self, pose, v3):
        v3 = np.atleast_2d(np.asarray(v3, float))
        return np.c_[pose.dirw(v3[:, :2]), v3[:, 2]]

    def pressure(self, t):
        """Magazine pressure (bar abs): the reference's stand-in for the mechanics ODE (07 6.2). It rises while the
        burn races the vents, peaks as the boundaries fail, then vents down. The column (DEPARTURE) plateaus while
        its charges burn instead, so the jets keep going for seconds (research 2.5, 'a burn-out')."""
        s = self.s
        a = t - s["t0"]
        tm = s["t_main"] - s["t0"]
        if a < tm:
            return 1.0 + (P_PEAK - 1.0) * (max(a, 0) / tm) ** 2
        if s["tier"] == "column":
            return 1.0 + (P_PEAK - 1.0) * (0.35 + 0.65 * math.exp(-(a - tm) / 0.7)) * max(0.0, 1 - (a - tm) / COLUMN_S)
        return 1.0 + (P_PEAK - 1.0) * math.exp(-(a - tm) / 0.7)

    # ---- spawners
    def _hit(self, pose):
        """The shell bursting on the gunhouse (or the deck over the magazine): a flash, a dark puff, sparks."""
        s, rng = self.s, self.rng
        z = (s["barbette"]["z"] + 2.0) if s["barbette"] else s["deck_z"] + 1
        c = self._w3(pose, [(*s["centre"], z)])[0]
        n = 10
        u = rng.normal(size=(n, 3))
        u[:, 2] = np.abs(u[:, 2])
        self.p.add(pos=c + u * 1.5, vel=u * 12 + np.r_[pose.vel, 0], r=2.5 + 2 * rng.random(n), m=0.25, temp=1.0,
                   heat=0.3, life=1e9, kind=0, tcool=0.06 + 0.06 * rng.random(n))
        k = 30
        v = rng.normal(0, 25, (k, 3))
        v[:, 2] = np.abs(v[:, 2]) + 5
        self.p.add(pos=np.repeat(c[None], k, 0), vel=v, r=0.4, m=1.0, temp=1.0, life=rng.uniform(0.4, 1.0, k),
                   kind=3, tcool=0.5)

    def _fireball(self, pose):
        s, rng, n = self.s, self.rng, 320
        R, t_fb = s["D"] / 2, s["t_fb"]
        u = rng.normal(size=(n, 3))
        u /= np.linalg.norm(u, axis=1, keepdims=True)
        u[:, 2] = np.abs(u[:, 2]) * 1.6 + 0.2          # hemispherical, biased upward (decks vent up)
        u /= np.linalg.norm(u, axis=1, keepdims=True)
        f = rng.random(n) ** 0.5
        v = u * (f[:, None] * 2.2 * R / t_fb) + np.r_[pose.vel, 0]
        c = self._w3(pose, [(*s["centre"], s["deck_z"])])[0]
        # DEPARTURE: soot mass by the fireball's area (k^2, so a small one starts as opaque as the reference's and
        # thins as it entrains air), not a fixed 1.6 a puff
        self.p.add(pos=c + u * 4 * s["k"], vel=v, r=0.14 * R + 0.06 * R * rng.random(n), m=1.6 * s["k"] ** 2,
                   temp=0.55 + 0.45 * (1 - f) ** 0.5 * rng.uniform(0.7, 1, n), heat=1.0, life=1e9, kind=0,
                   tcool=t_fb * (0.35 + 0.6 * rng.random(n)))
        # gas out through the sides along the magazine (Hood): low flat jets. DEPARTURE: from the hull's sides
        # abreast the magazine (and 15 m past each end), not a fixed box
        sk = s["k"]
        k = max(8, int(round(50 * sk)))
        side = rng.choice([-1.0, 1.0], k)
        x = rng.uniform(s["span"][0] - 15 * sk, s["span"][1] + 15 * sk, k)
        loc = np.c_[x, side * s["half_w"], np.full(k, max(1.0, s["deck_z"] - 2))]
        lv = np.c_[rng.normal(0, 6, k), side * rng.uniform(10, 35, k), rng.uniform(2, 12, k)] * math.sqrt(sk)
        self.p.add(pos=self._w3(pose, loc), vel=self._d3(pose, lv) + np.r_[pose.vel, 0], r=(4 + 4 * rng.random(k)) * sk,
                   m=0.8 * sk ** 2, temp=0.8, heat=0.4, life=1e9, kind=0, tcool=0.6 + 0.6 * rng.random(k))

    def _debris(self, pose, n, vmax=None, roof=False, z=None):
        rng, s = self.rng, self.s
        if vmax is None:   # "hurled hundreds of feet" -> ~140 m apex for the 20 t event, lower for smaller ones
            vmax = math.sqrt(2 * G * 140.0 * min(1.0, s["k"]))
        el = np.radians(rng.uniform(35, 88, n))
        az = rng.uniform(0, 2 * np.pi, n)
        sp = vmax * rng.random(n) ** 0.6
        v = np.c_[np.cos(el) * np.cos(az) * sp, np.cos(el) * np.sin(az) * sp, np.sin(el) * sp]
        c = self._w3(pose, [(*s["centre"], z if z is not None else s["deck_z"] + 2.5)])[0]
        burning = rng.random(n) < (0.2 if roof else 0.5)
        self.p.add(pos=np.repeat(c[None], n, 0), vel=v + np.r_[pose.vel, 0], r=1.2 + 1.5 * rng.random(n), m=1.0,
                   temp=np.where(burning, 1.0, 0.0), heat=0.0, life=1e9, kind=2, tcool=4 + 6 * rng.random(n))

    def _roof(self, pose):
        """Gunhouse roof plates: big, slow, tumbling up out of the smoke."""
        s, rng = self.s, self.rng
        if not s["barbette"]:
            return
        c = self._w3(pose, [(*s["barbette"]["xy"], s["barbette"]["z"] + 3)])[0]
        v = np.c_[rng.normal(0, 4, 3), rng.normal(0, 4, 3), rng.uniform(28, 40, 3)] + np.r_[pose.vel, 0]
        # cold steel, not burning: no smoke trails (theirs looped into hoops as the ship steamed on)
        self.p.add(pos=c + rng.normal(0, 2, (3, 3)), vel=v, r=[4.0, 2.5, 2.0], m=1.0, temp=0.0, heat=0.0, life=1e9,
                   kind=2, tcool=6.0)

    def _throw_gunhouse(self, pose):
        """DEPARTURE (research 3.4 'Turret / roof' layer, 07 4.4): the whole gunhouse goes up a few tens of metres and
        lands near the wreck, ~40 m off (Vanguard). Its launch is a fraction of the debris' speed: it weighs
        hundreds of tonnes."""
        s, rng = self.s, self.rng
        if not s["mount"] or not s["barbette"]:
            return
        c = self._w3(pose, [(*s["barbette"]["xy"], s["barbette"]["z"])])[0]
        az = rng.uniform(0, 2 * math.pi)
        vz = rng.uniform(20, 30)
        t_air = 2 * vz / G
        vh = rng.uniform(25, 50) / t_air
        self.flyers.append(dict(p=c.copy(), v=np.r_[pose.vel + vh * np.array([math.cos(az), math.sin(az)]), vz],
                                ang=0.0, spin=rng.uniform(-60, 60), tilt=0.0, tilt_rate=rng.uniform(40, 110)
                                * rng.choice([-1, 1]), mount=s["mount"], landed=None))
        self.thrown = True

    def _jets(self, pose, t, dt):
        """Directional flame jets from every failed opening (research 2.5): length ~ 45 d sqrt(P/p0), capped, puffs
        spawned along the jet axis, narrow (2-8 % spread) and short-lived."""
        rng, P = self.rng, self.pressure(t)
        if P < 1.15:
            return 0.0
        q = 0.0
        for o in self.s["openings"]:
            a = t - o["t_fail"]
            if a < 0:
                continue
            env = min(1.0, a / 0.08)
            L = min(45.0 * o["d"] * math.sqrt(P), o["Lmax"]) * env
            if L < 2:
                continue
            dirv = self._d3(pose, o["dir"])[0]
            dirv /= np.linalg.norm(dirv)
            perp1 = np.cross(dirv, [0, 0, 1.0])
            if np.linalg.norm(perp1) < 1e-3:
                perp1 = np.array([1.0, 0, 0])
            perp1 /= np.linalg.norm(perp1)
            perp2 = np.cross(dirv, perp1)
            n = int(rng.poisson(max(4, 16 * L / 30) / 0.05 * dt))   # DEPARTURE: a rate, so it holds at any dt
            if n:
                f = rng.random(n) ** 0.8
                spread = (0.015 + 0.07 * f) * L
                jit = (rng.normal(size=(n, 1)) * perp1 + rng.normal(size=(n, 1)) * perp2) * spread[:, None] * 0.5
                base = self._w3(pose, [o["pos"]])[0]
                w = L / 0.35                                    # jet speed scale (near-sonic at the exit)
                vel = dirv * (w * (1 - f) * 0.12)[:, None] + rng.normal(0, 2, (n, 3)) + np.r_[pose.vel, 0]
                # DEPARTURE: half the reference's mass (0.02-0.06): burning gas leaves only light smoke (research
                # 2.5), and the reference's left dense dark knots along every jet
                self.p.add(pos=base + dirv * (f * L)[:, None] + jit, vel=vel, r=o["d"] * 0.45 + 0.06 * f * L,
                           m=0.02 + 0.04 * f, temp=1.0 - 0.3 * f * rng.random(n), heat=0.25,
                           life=0.6 + 1.2 * rng.random(n), kind=0, tcool=0.08 + 0.2 * f)
                k = int(rng.poisson(6 / 0.05 * dt * env))
                if k:   # burning grains thrown out of the opening
                    v = dirv * w * rng.uniform(0.15, 0.4, (k, 1)) + rng.normal(0, 6, (k, 3)) + np.r_[pose.vel, 0]
                    self.p.add(pos=np.repeat(base[None], k, 0), vel=v, r=0.5, m=1.0, temp=1.0,
                               life=rng.uniform(0.8, 2.0, k), kind=3, tcool=1.5)
            q += 2e4 * L
        return q

    def _column(self, pose, t, dt):
        """Tier 1: Q(t) from the barbette's burn rate -> flame height by Heskestad; jet puffs and sparks."""
        s, rng = self.s, self.rng
        bar = s["barbette"]
        a = t - s["t_lift"]
        if not bar or a < 0 or a > COLUMN_S:
            return 0.0
        Dbar = 2 * bar["r"]
        env = min(1.0, a / 0.4) * min(1.0, (COLUMN_S - a) / 4.0)
        pulse = 0.75 + 0.25 * math.sin(2 * math.pi * 0.7 * a) * math.sin(2 * math.pi * 0.23 * a + 1)
        Q = COLUMN_FLUX * math.pi * bar["r"] ** 2 * DH / 1000 * env * pulse
        L = heskestad(Q, Dbar)
        if L <= 0:
            return 0.0
        n = int(rng.poisson(30 * env / 0.05 * dt)) + 1
        w0 = 2.2 * L / 1.5                              # puffs reach L in ~1.5 s
        ang = rng.uniform(0, 2 * np.pi, n)
        rr = Dbar / 2 * np.sqrt(rng.random(n))
        c = self._w3(pose, [(*bar["xy"], bar["z"])])[0]
        pos = c + np.c_[rr * np.cos(ang), rr * np.sin(ang), np.zeros(n)]
        vel = np.c_[rng.normal(0, 2.5, n) + pose.vel[0], rng.normal(0, 2.5, n) + pose.vel[1],
                    w0 * (0.7 + 0.5 * rng.random(n))]
        self.p.add(pos=pos, vel=vel, r=Dbar * (0.5 + 0.25 * rng.random(n)), m=0.6, temp=0.95, heat=0.7, life=1e9,
                   kind=0, tcool=1.1 * (0.6 + 0.6 * rng.random(n)))
        k = int(rng.poisson(25 * env / 0.05 * dt))
        if k:
            v = np.c_[rng.normal(0, 9, k), rng.normal(0, 9, k), w0 * rng.uniform(0.6, 1.4, k)]
            self.p.add(pos=pos[:1].repeat(k, 0), vel=v, r=0.6, m=1.0, temp=1.0, life=rng.uniform(1.5, 3.5, k),
                       kind=3, tcool=2.0)
        return Q

    def _fires(self, pose, t, dt):
        """After the blast: the burning wreck and oil feed a low-buoyancy stem; boiler steam (white) early on."""
        s, rng = self.s, self.rng
        a = t - s["t_main"]
        if a < 0.6 * s["t_fb"]:
            return 0.0
        env = math.exp(-(a - s["t_fb"]) / 40.0) if a > s["t_fb"] else 1.0
        sk = s["k"]
        n = int(rng.poisson((0.5 + 3 * env * 0.05) / 0.05 * dt * sk))
        if n:
            L = s["span"][1] - s["span"][0]
            loc = np.c_[s["centre"][0] + rng.normal(0, max(10.0 * sk, L), n), rng.normal(0, s["B"] / 4, n),
                        np.full(n, s["deck_z"])]
            vel = np.c_[rng.normal(0, 2, n), rng.normal(0, 2, n), rng.uniform(8, 20, n)]
            pos, up = pose.deck(loc)     # a broken wreck carries its fires, and they go out where it's gone under
            if up.any():
                n = int(up.sum())
                self.p.add(pos=pos[up], vel=vel[up], r=(10 + 6 * rng.random(n)) * max(sk, 0.4), m=2.5 * sk,
                           temp=0.75, heat=0.35,
                           life=1e9, kind=0, tcool=0.8)
        if s["steam"] is not None and a < 12:
            k = int(rng.poisson(0.6 / 0.05 * dt))
            if k:
                loc = np.c_[s["steam"][0] + rng.normal(0, 0.3 * s["B"], k), rng.normal(0, 0.2 * s["B"], k),
                            np.full(k, s["deck_z"] + 3)]
                pos, up = pose.deck(loc)
                pos[~up] = pos[~up] * [1, 1, 0]      # under water: the steam boils up at the surface
                # DEPARTURE: the puffs sized by the ship's beam (the reference's 9 m on its 31 m ship), not fixed
                self.p.add(pos=pos, vel=np.c_[rng.normal(0, 2, k), rng.normal(0, 2, k),
                                              rng.uniform(15, 30, k)],
                           r=0.29 * s["B"], m=1.2 * (s["B"] / 31) ** 2, temp=0.0, heat=0.3, life=1e9, kind=1,
                           tcool=1)
        return 3e5 * env

    def _vents(self, pose, t, dt):
        """Vent jets from the machinery rooms beside the magazine for 6 s after the main event (Hood's mainmast)."""
        q, rng = 0.0, self.rng
        for vxy in self.s["vents"]:
            a = t - self.s["t_main"] - 0.4
            if 0 < a < 6:
                env = math.sin(math.pi * a / 6)
                n = int(rng.poisson(30 * env / 0.05 * dt)) + 1
                loc = np.c_[vxy[0] + rng.normal(0, 3, n), rng.normal(0, 3, n), np.full(n, self.s["deck_z"] + 8)]
                vel = np.c_[rng.normal(0, 3, n) + pose.vel[0], rng.normal(0, 3, n) + pose.vel[1],
                            rng.uniform(50, 90, n) * env]
                self.p.add(pos=self._w3(pose, loc), vel=vel, r=4 + 3 * rng.random(n), m=0.4, temp=1.0, heat=0.6,
                           life=1e9, kind=0, tcool=0.9)
                q += 8e5 * env
        return q

    # ---- step
    def step(self, t, dt, pose):
        s, rng = self.s, self.rng
        self.new_splashes = []
        if s["t_hit"] is not None and t >= s["t_hit"] and "hit" not in self.done:
            self.done.add("hit")
            self._hit(pose)
        if t >= s["t_lift"] and "lift" not in self.done:
            self.done.add("lift")
            self._roof(pose)
            if s["tier"] == "column":
                self._debris(pose, max(6, s["n_debris"] // 6), vmax=28.0, roof=True,
                             z=(s["barbette"] or {}).get("z"))
                c = self._w3(pose, [(*s["centre"], 0)])[0]
                self.shock = (c[:2], t, s["lam"])
        main = s["tier"] == "blast" and t >= s["t_main"]
        if main and "main" not in self.done:
            self.done.add("main")
            self._fireball(pose)
            self._debris(pose, s["n_debris"])
            self._throw_gunhouse(pose)
            c = self._w3(pose, [(*s["centre"], 0)])[0]
            self.shock = (c[:2], t, s["lam"])
        q = self._jets(pose, t, dt)
        q += self._column(pose, t, dt) if s["tier"] == "column" else (self._fires(pose, t, dt) if main else 0.0)
        q += self._vents(pose, t, dt) if main else 0.0
        self.Q = q
        self._fly(pose, dt)
        d = self.p.d
        if not len(self.p):
            self.lights = []
            return
        z = d["pos"][:, 2]
        kind = d["kind"]
        gas = kind < 2
        # gas: buoyancy from heat content, drag toward the sheared wind, entrainment growth
        uw = np.c_[shear(z)[:, None] * self.wind[None, :], np.zeros(len(z))]
        tau = np.where(gas, 1.6, 1e9)
        d["vel"][:, 2] += np.where(gas, 26.0 * d["heat"], 0.0) * dt
        d["vel"] += (uw - d["vel"]) * ((1 - np.exp(-dt / tau)) * gas)[:, None]
        d["vel"][:, :2] += (uw[:, :2] - d["vel"][:, :2]) * (1 - math.exp(-dt / 6.0)) * (~gas)[:, None] * 0.3
        # mushroom: poloidal circulation around the rising cap (blast only)
        if main and t - s["t_main"] > 0.5 * s["t_fb"]:
            hot = gas & (d["heat"] > 0.25)
            if hot.sum() > 20:
                w = d["heat"][hot] * d["m"][hot]
                c = (d["pos"][hot] * w[:, None]).sum(0) / w.sum()
                R0 = 0.35 * max(np.sqrt(((d["pos"][hot, :2] - c[:2]) ** 2).sum(1)).mean(), 10)
                dxy = d["pos"][:, :2] - c[:2]
                rh = np.linalg.norm(dxy, axis=1) + 1e-3
                er = dxy / rh[:, None]
                rel_r, rel_z = rh - R0, d["pos"][:, 2] - c[2]
                wgt = np.exp(-(rel_r ** 2 + rel_z ** 2) / (2.2 * R0) ** 2) * gas
                k = 0.18 * math.sqrt(G * max(R0, 1)) / max(R0, 1)
                d["vel"][:, :2] += (k * rel_z * wgt)[:, None] * er * dt * 4
                d["vel"][:, 2] += -k * rel_r * wgt * dt * 4
        d["vel"][:, 2] -= np.where(gas, 0.0, G) * dt
        d["pos"] += d["vel"] * dt
        # solids land: on the deck (gone, no splash) or in the sea (a splash)
        solid = ~gas
        low = solid & (d["pos"][:, 2] < s["deck_z"]) & (d["vel"][:, 2] < 0)
        hit = np.zeros(len(kind), bool)
        if low.any():
            idx = np.nonzero(low)[0]
            on = pose.on_hull(d["pos"][idx, :2])
            hit[idx[on]] = True
            sea = idx[~on & (d["pos"][idx, 2] < 0)]
            hit[sea] = True
            for i in sea:
                if kind[i] == 2:
                    self.new_splashes.append((d["pos"][i, :2].copy(), float(d["r"][i])))
        speed = np.linalg.norm(d["vel"], axis=1)
        d["r"] += np.where(gas, (0.12 * speed + 0.35) * dt, 0.0)
        # soot skin: the top and outside of the fireball cool first; the fire keeps burning underneath
        cool = np.ones(len(kind))
        hotm = gas & (d["temp"] > 0.1)
        if s["tier"] == "blast" and hotm.sum() > 10:
            w = d["temp"][hotm] ** 2
            c = (d["pos"][hotm] * w[:, None]).sum(0) / w.sum()
            Rf = max(np.sqrt(((d["pos"][hotm] - c) ** 2).sum(1)).mean(), 5.0)
            rel = d["pos"] - c
            outer = np.clip((rel[:, 2] + 0.6 * np.linalg.norm(rel[:, :2], axis=1)) / Rf - 0.8, 0, None)
            cool = 1 + SOOT_SKIN * outer * (d["tcool"] > 1.0)
        d["temp"] *= np.exp(-dt * cool / d["tcool"])
        d["heat"] *= math.exp(-dt / (28.0 if s["tier"] == "blast" else 14.0))
        d["age"] += dt
        tau_c = d["m"] / np.maximum(d["r"], 1) ** 2
        alive = (d["age"] < d["life"]) & ~hit & ~(gas & (tau_c < 6e-5) & (d["temp"] < 0.05))
        # debris smoke trails (the "octopus" tendrils) from the burning pieces (research 2.3: about half).
        # DEPARTURE: one puff per TRAIL_GAP m flown, so a trail is a line and not a string of beads, and thin
        # (m 0.07, not 1.6): the reference's trail puffs were each as dense as a fireball puff
        deb = np.nonzero(alive & (kind == 2) & (d["pos"][:, 2] > 0) & (d["temp"] > 0.05) & (d["age"] < 6))[0]
        idx = np.repeat(deb, rng.poisson(speed[deb] * dt / TRAIL_GAP))
        back = rng.random((len(idx), 1))
        src = (d["pos"][idx] - d["vel"][idx] * dt * back, d["vel"][idx] * 0.05, d["temp"][idx].copy())
        self.p.keep(alive)
        if len(idx):
            n = len(idx)
            self.p.add(pos=src[0], vel=src[1], r=1.5 + 1.0 * rng.random(n), m=0.07, temp=src[2] * 0.9, heat=0.05,
                       life=1e9, kind=0, tcool=0.35)
        # the fire light: emission-weighted centroid of the hot particles. DEPARTURE: weighted by the blackbody
        # luminance (per 1e5 cd/m^2, a 1800 K surface), not T^3: with T^3 a huge, barely warm cap still lit itself
        # orange half a minute on
        d = self.p.d
        e = fire_luminance(d["temp"]) / 1e5 * d["m"] * d["r"] ** 2 * (d["kind"] != 2)
        self.lights = []
        if e.sum() > 1e-3:
            self.lights = [((d["pos"] * e[:, None]).sum(0) / e.sum(), float(e.sum()))]

    def _fly(self, pose, dt):
        for f in self.flyers:
            if f["landed"] is not None:
                continue
            f["v"][2] -= G * dt
            f["p"] += f["v"] * dt
            f["ang"] += f["spin"] * dt
            f["tilt"] += f["tilt_rate"] * dt
            if f["v"][2] < 0 and f["p"][2] < self.s["deck_z"]:
                if pose.on_hull(f["p"][None, :2])[0]:
                    f["landed"] = (pose.local(f["p"][None, :2])[0], self.s["deck_z"], f["ang"])   # drawn flat
                elif f["p"][2] < 0:
                    self.new_splashes.append((f["p"][:2].copy(), 8.0))
                    f["landed"] = "sunk"
