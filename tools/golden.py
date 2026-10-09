#!/usr/bin/env python3
"""
golden: capture the Python output the C# port (../fleetwright, Fleetwright.Shipgen) is tested against. See
fleetwright/PORTING.md, Step 1. Everything is written under OUT (default ../fleetwright/shipgen):

    python tools/golden.py mutants                  fuzz mutants -> OUT/designs/fuzz/*.json + OUT/golden/cases.json
    python tools/golden.py design --platform windows [--golden DIR] [--jobs N]
                                                    validate/build every case -> DIR/<case>.json.gz + DIR/capture.json
    python tools/golden.py sprites                  (needs cairosvg: WSL) sprite.json + reference images per design
    python tools/golden.py svgs                     (WSL) the SVGs (hull, turrets, height map) with the C# port's RNG
    python tools/golden.py diff A B                 compare two design captures, print every differing case

Run `mutants` once and capture from the saved mutants on every platform: mutate() draws numbers through libm
(exp/log), so regenerating on another platform could give other mutants.

Each design case file holds:
    validate_limits, validate_no_limits, looks_validate   the exact strings (or {"raised": ...})
    build        the whole ship dict (design, report, hitboxes, render), private "_" keys included, or absent when
                 validate(limits=False) fails; {"raised": {"type", "message"}} if build() raised
    hint         {"length_m", "equal"}: build(design, hint=length_m) against the unhinted build
    build_s      seconds for the unhinted build (the performance baseline; see capture.json for the job count)

Run with PYTHONHASHSEED=0 (the script refuses otherwise, unless --any-hashseed for the determinism check).
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import platform
import random
import shutil
import subprocess
import sys
import time
import types
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

CASES = 150             # mutants per half: with limits (seed 1) and without (seed 2)


def write_json_gz(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = json.dumps(obj, indent=1, allow_nan=True).encode()
    with open(path, "wb") as fh:          # mtime=0: the same capture gives the same bytes
        with gzip.GzipFile(fileobj=fh, mode="wb", mtime=0, filename="") as gz:
            gz.write(data)


def read_json_gz(path):
    with gzip.open(path, "rb") as fh:
        return json.loads(fh.read())


def gzip_file(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        with gzip.GzipFile(fileobj=fo, mode="wb", mtime=0, filename="") as gz:
            shutil.copyfileobj(fi, gz)


def commit_hash():
    try:
        h = subprocess.check_output(["git", "-C", ROOT, "rev-parse", "HEAD"], text=True).strip()
        # Line endings ignored: WSL's git sees the Windows checkout's CRLF as changes.
        changed = subprocess.run(["git", "-C", ROOT, "diff", "HEAD", "--ignore-cr-at-eol", "--quiet", "--", "*.py"]
                                 ).returncode != 0
        untracked = subprocess.check_output(["git", "-C", ROOT, "ls-files", "--others", "--exclude-standard",
                                             "--", "*.py"], text=True).strip()
        return h + ("+dirty" if changed or untracked else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def design_paths():
    return sorted(os.path.join(ROOT, "designs", f) for f in os.listdir(os.path.join(ROOT, "designs"))
                  if f.endswith(".json"))


# --- mutants ---------------------------------------------------------------------------------------------------

def cmd_mutants(args):
    sys.modules.setdefault("resource", types.ModuleType("resource"))    # Unix-only, used only by fuzz's workers
    import fuzz
    bases = []
    for p in design_paths():
        with open(p) as fh:
            bases.append((os.path.basename(p), json.load(fh)))
    choices = fuzz.corpus_choices([b for _, b in bases])
    out_designs = os.path.join(args.out, "designs")
    fuzz_dir = os.path.join(out_designs, "fuzz")
    shutil.rmtree(fuzz_dir, ignore_errors=True)
    os.makedirs(fuzz_dir)
    cases = []
    for name, _ in bases:
        shutil.copyfile(os.path.join(ROOT, "designs", name), os.path.join(out_designs, name))
        cases.append(dict(case=name[:-5], design=f"designs/{name}", source=None, limits=True, changes=[]))
    for half, seed, use_limits in (("lim", 1, True), ("free", 2, False)):
        rng = random.Random(seed)
        for i in range(CASES):
            src, base = bases[i % len(bases)]
            d, changes = fuzz.mutate(base, rng, use_limits, choices, "all")
            case = f"fuzz_{half}_{i:03d}"
            with open(os.path.join(fuzz_dir, case + ".json"), "w", newline="\n") as fh:
                json.dump(d, fh, indent=1)
            cases.append(dict(case=case, design=f"designs/fuzz/{case}.json", source=f"designs/{src}",
                              limits=use_limits, changes=[f"{p} {a} -> {b}" for p, a, b in changes]))
    gold = os.path.join(args.out, "golden")
    os.makedirs(gold, exist_ok=True)
    with open(os.path.join(gold, "cases.json"), "w", newline="\n") as fh:
        json.dump(dict(shipgen_commit=commit_hash(), python=sys.version.split()[0], platform=platform.platform(),
                       note=f"designs/*.json are ../shipgen/designs; fuzz mutants from fuzz.mutate, mode all, "
                            f"{CASES} with limits (seed 1) and {CASES} without (seed 2), base = case % designs",
                       cases=cases), fh, indent=1)
    print(f"{len(cases)} cases ({len(bases)} designs, {2 * CASES} mutants) -> {gold}/cases.json")


# --- design side -----------------------------------------------------------------------------------------------

def raised(e):
    return {"raised": {"type": type(e).__name__, "message": str(e)}}


def capture_case(args):
    case, path = args
    import looks
    import shipdesign
    with open(path) as fh:
        d = json.load(fh)
    rec = {}
    for key, fn in (("validate_limits", lambda: shipdesign.validate(json.loads(json.dumps(d)), limits=True)),
                    ("validate_no_limits", lambda: shipdesign.validate(json.loads(json.dumps(d)), limits=False)),
                    ("looks_validate", lambda: looks.validate(json.loads(json.dumps(d))))):
        try:
            rec[key] = fn()
        except Exception as e:        # noqa: BLE001 - a raise is part of the golden
            rec[key] = raised(e)
    if rec["validate_no_limits"] == []:
        t = time.perf_counter()
        try:
            ship = shipdesign.build(json.loads(json.dumps(d)))
            rec["build_s"] = round(time.perf_counter() - t, 3)
            rec["build"] = json.loads(json.dumps(ship, allow_nan=True))
        except Exception as e:        # noqa: BLE001
            rec["build_s"] = round(time.perf_counter() - t, 3)
            rec["build"] = raised(e)
        if "raised" not in rec["build"]:
            L = rec["build"]["report"]["results"]["length_m"]
            try:
                hinted = json.loads(json.dumps(shipdesign.build(json.loads(json.dumps(d)), hint=L), allow_nan=True))
                rec["hint"] = dict(length_m=L, equal=hinted == rec["build"])
            except Exception as e:    # noqa: BLE001
                rec["hint"] = dict(length_m=L, **raised(e))
    return case, rec


def cmd_design(args):
    gold_root = os.path.join(args.out, "golden")
    with open(os.path.join(gold_root, "cases.json")) as fh:
        cases = json.load(fh)["cases"]
    out = args.golden or os.path.join(gold_root, "design")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    jobs = [(c["case"], os.path.join(args.out, c["design"])) for c in cases]
    t0 = time.time()
    times = {}
    with ProcessPoolExecutor(args.jobs) as pool:
        for n, (case, rec) in enumerate(pool.map(capture_case, jobs), 1):
            write_json_gz(os.path.join(out, case + ".json.gz"), rec)
            times[case] = rec.get("build_s")
            b = rec.get("build")
            state = "invalid" if b is None else "RAISED" if "raised" in b else "ok"
            print(f"[{n:>3}/{len(jobs)}] {case:<24} {state:<7} {rec.get('build_s', 0):6.2f} s", flush=True)
    with open(os.path.join(out, "capture.json"), "w", newline="\n") as fh:
        json.dump(dict(platform=args.platform, shipgen_commit=commit_hash(), python=sys.version.split()[0],
                       platform_detail=platform.platform(), hashseed=os.environ.get("PYTHONHASHSEED"),
                       jobs=args.jobs, wall_s=round(time.time() - t0, 1), build_s=times), fh, indent=1)
    print(f"{len(jobs)} cases in {time.time() - t0:.0f} s -> {out}")


# --- sprites ---------------------------------------------------------------------------------------------------

def capture_sprite(args):
    path, out, tmp = args
    import render
    import shipdesign
    with open(path) as fh:
        d = json.load(fh)
    case = os.path.basename(path)[:-5]
    if shipdesign.validate(d, limits=True):       # design.py renders only what validates
        return case, "invalid"
    import looks
    if looks.validate(d):
        return case, "invalid look"
    work = os.path.join(tmp, case)
    shutil.rmtree(work, ignore_errors=True)
    meta = render.render_ship(shipdesign.build(d), work, 10.0, 5, previews=False)
    dst = os.path.join(out, case)
    shutil.rmtree(dst, ignore_errors=True)
    write_json_gz(os.path.join(dst, "sprite.json.gz"), meta)
    for rel in ["hull.png", "height.png"] + [f"turrets/{f}" for f in sorted(os.listdir(os.path.join(work, "turrets")))
                                             if f.endswith(".png") and not f.endswith("_mips.png")]:
        os.makedirs(os.path.dirname(os.path.join(dst, rel)), exist_ok=True)
        shutil.copyfile(os.path.join(work, rel), os.path.join(dst, rel))
    gzip_file(os.path.join(work, "hull.svg"), os.path.join(dst, "hull.svg.gz"))
    shutil.rmtree(work, ignore_errors=True)
    return case, "ok"


def cmd_sprites(args):
    import tempfile
    out = os.path.join(args.out, "golden", "sprite")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    tmp = tempfile.mkdtemp(prefix="golden_sprites_")
    jobs = [(p, out, tmp) for p in design_paths()]
    states = {}
    with ProcessPoolExecutor(args.jobs) as pool:
        for case, state in pool.map(capture_sprite, jobs):
            states[case] = state
            print(f"{case:<24} {state}", flush=True)
    shutil.rmtree(tmp, ignore_errors=True)
    with open(os.path.join(out, "capture.json"), "w", newline="\n") as fh:
        json.dump(dict(shipgen_commit=commit_hash(), python=sys.version.split()[0], platform=platform.platform(),
                       scale_px_per_m=10.0, mips=5, previews=False, cases=states), fh, indent=1)


# --- svgs ------------------------------------------------------------------------------------------------------

class PortRandom:
    """The C# port's RNG (Fleetwright.Shipgen.Render.ShipRng), for the svgs capture: FNV-1a 64 of the seed text,
    then SplitMix64. With it the drawing's random parts (clutter, dazzle, vents) come out the same on both sides,
    so whole SVGs can be compared. Only what the drawing calls: random, uniform, choice, randrange(n)."""
    M = (1 << 64) - 1

    def __init__(self, seed=None):
        h = 0xcbf29ce484222325
        for b in str(seed).encode():
            h = ((h ^ b) * 0x100000001b3) & self.M
        self.s = h

    def _next(self):
        self.s = (self.s + 0x9E3779B97F4A7C15) & self.M
        z = self.s
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & self.M
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & self.M
        return z ^ (z >> 31)

    def random(self):
        return (self._next() >> 11) * (1.0 / 9007199254740992.0)

    def uniform(self, a, b):
        return a + (b - a) * self.random()

    def randrange(self, n):
        return int(self.random() * n)

    def choice(self, seq):
        return seq[int(self.random() * len(seq))]


def capture_svg(args):
    path, out = args
    random.Random = PortRandom      # this worker only; the design side draws no random numbers
    import copy
    import clutter
    import looks
    import shadow
    import shipdesign
    import shipgen
    with open(path) as fh:
        d = json.load(fh)
    case = os.path.basename(path)[:-5]
    if shipdesign.validate(d, limits=False) or looks.validate(d):
        return case, "invalid"
    ship = shipdesign.build(d)
    design, rd = ship["design"], ship["render"]
    S, align = 10.0, 2 ** (5 + 1)          # as the sprite capture: 10 px/m, 5 mips
    spec = copy.deepcopy(rd["spec"])       # render.render_ship's set-up
    spec["palette"] = looks.palette(design)
    pal = {**shipgen.DEFAULT_PALETTE, **spec["palette"]}
    turret_look = looks.get(design)["turrets"]
    spec["shapes"] = looks.shapes(design)
    dst = os.path.join(out, case)
    shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(os.path.join(dst, "turrets"))
    def save(rel, text):
        with open(os.path.join(dst, rel), "wb") as fh:
            with gzip.GzipFile(fileobj=fh, mode="wb", mtime=0, filename="") as gz:
                gz.write(text.encode())
    for tid, t in spec["turret_types"].items():
        save(f"turrets/{tid}.svg.gz", shipgen.build_turret(t, pal, S, align, shadows=False, look=turret_look,
                                                           shapes=spec["shapes"]))
    hull_svg, vb, mounts, hull = shipgen.build_hull(spec, S, align, shadows=False)
    save("hull.svg.gz", hull_svg)
    columns = rd["columns"] + clutter.height_columns(spec.get("_clutter", []), rd["columns"], hull)
    height_svg, max_h = shadow.build_height_svg(columns, vb, S, hull)
    save("height.svg.gz", height_svg)
    return case, dict(max_height_m=max_h, clutter=len(spec.get("_clutter", [])))


def cmd_svgs(args):
    out = os.path.join(args.out, "golden", "svg")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    with open(os.path.join(args.out, "golden", "cases.json")) as fh:
        cases = json.load(fh)["cases"]
    jobs = [(os.path.join(args.out, c["design"]), out) for c in cases]
    states = {}
    with ProcessPoolExecutor(args.jobs) as pool:
        for case, state in pool.map(capture_svg, jobs):
            states[case] = state
            print(f"{case:<24} {state}", flush=True)
    with open(os.path.join(out, "capture.json"), "w", newline="\n") as fh:
        json.dump(dict(shipgen_commit=commit_hash(), python=sys.version.split()[0], platform=platform.platform(),
                       scale_px_per_m=10.0, mips=5, rng="PortRandom (FNV-1a 64 + SplitMix64)", cases=states),
                  fh, indent=1)


# --- diff ------------------------------------------------------------------------------------------------------

def first_diff(a, b, path="$"):
    """The first path where two JSON trees differ, with both values (exact: this is for platform diffs)."""
    if type(a) is not type(b):
        return path, a, b
    if isinstance(a, dict):
        if list(a) != list(b):
            return path + " (keys)", sorted(set(a) ^ set(b)) or list(a), list(b)
        for k in a:
            r = first_diff(a[k], b[k], f"{path}.{k}")
            if r:
                return r
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return path + " (length)", len(a), len(b)
        for i, (x, y) in enumerate(zip(a, b)):
            r = first_diff(x, y, f"{path}[{i}]")
            if r:
                return r
        return None
    return None if a == b or (a != a and b != b) else (path, a, b)


def rel_diffs(a, b, path="$", rtol=1e-9, out=None):
    """Every difference between two JSON trees under the golden rules (PORTING.md Step 1): floats within rtol,
    everything else exact. -> (max relative float difference, [(path, a, b)] beyond that)."""
    if out is None:
        out = [0.0, []]
    if isinstance(a, float) and isinstance(b, (int, float)) and not isinstance(b, bool) or \
            isinstance(b, float) and isinstance(a, (int, float)) and not isinstance(a, bool):
        if a != b and not (a != a and b != b):
            r = abs(a - b) / max(abs(a), abs(b))
            out[0] = max(out[0], r)
            if r > rtol:
                out[1].append((path, a, b))
    elif type(a) is not type(b):
        out[1].append((path, a, b))
    elif isinstance(a, dict):
        if list(a) != list(b):
            out[1].append((path + " (keys)", list(a), list(b)))
        for k in a:
            if k in b:
                rel_diffs(a[k], b[k], f"{path}.{k}", rtol, out)
    elif isinstance(a, list):
        if len(a) != len(b):
            out[1].append((path + " (length)", len(a), len(b)))
        for i, (x, y) in enumerate(zip(a, b)):
            rel_diffs(x, y, f"{path}[{i}]", rtol, out)
    elif a != b:
        out[1].append((path, a, b))
    return out


def cmd_diff(args):
    names = sorted(f for f in os.listdir(args.a) if f.endswith(".json.gz"))
    if args.tolerant:
        worst, n = 0.0, 0
        for f in names:
            a, b = read_json_gz(os.path.join(args.a, f)), read_json_gz(os.path.join(args.b, f))
            a.pop("build_s", None)
            b.pop("build_s", None)
            m, bad = rel_diffs(a, b)
            worst = max(worst, m)
            if bad:
                n += 1
                print(f"{f[:-8]}: {len(bad)} differences beyond tolerance (max float rel {m:.2e})")
                for p, x, y in bad[:args.show]:
                    print(f"    {p}\n        {str(x)[:160]}\n        {str(y)[:160]}")
        print(f"{n} of {len(names)} cases differ beyond the golden tolerance; max float rel difference {worst:.2e}")
        return
    other = set(f for f in os.listdir(args.b) if f.endswith(".json.gz"))
    n = 0
    for f in names:
        if f not in other:
            print(f"{f}: missing in {args.b}")
            n += 1
            continue
        a, b = read_json_gz(os.path.join(args.a, f)), read_json_gz(os.path.join(args.b, f))
        a.pop("build_s", None)
        b.pop("build_s", None)
        r = first_diff(a, b)
        if r:
            n += 1
            print(f"{f[:-8]}: {r[0]}\n    {str(r[1])[:200]}\n    {str(r[2])[:200]}")
    for f in sorted(other - set(names)):
        print(f"{f}: missing in {args.a}")
        n += 1
    print(f"{n} of {len(names)} cases differ")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(ROOT, "..", "fleetwright", "shipgen"))
    ap.add_argument("--any-hashseed", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("mutants")
    p = sub.add_parser("design")
    p.add_argument("--platform", required=True)
    p.add_argument("--golden", help="output directory (default OUT/golden/design)")
    p.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    p = sub.add_parser("sprites")
    p.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    p = sub.add_parser("svgs")
    p.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    p = sub.add_parser("diff")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--tolerant", action="store_true", help="the golden rules: floats within 1e-9 relative")
    p.add_argument("--show", type=int, default=5, help="differences shown per case with --tolerant")
    args = ap.parse_args()
    if args.cmd != "diff" and os.environ.get("PYTHONHASHSEED") != "0" and not args.any_hashseed:
        raise SystemExit("run with PYTHONHASHSEED=0")
    args.out = os.path.abspath(args.out)
    dict(mutants=cmd_mutants, design=cmd_design, sprites=cmd_sprites, svgs=cmd_svgs, diff=cmd_diff)[args.cmd](args)


if __name__ == "__main__":
    main()
