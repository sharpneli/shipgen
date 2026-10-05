#!/usr/bin/env python3
"""
fuzz: robustness test for the design side. Mutates the numbers in designs and builds every mutant that passes
validate(), each in its own worker with a memory cap and a time limit. The contract (permissive generator): any
valid design builds, with errors and warnings if it's silly, but never an exception, a hang, a memory blow-up or
a NaN in the published result.

    python fuzz.py designs/*.json [--cases 400] [--seed 1] [--jobs 16] [--mem-gb 3] [--timeout 120]
                   [--no-limits] [--out fuzz_out]

A mutant changes 1-4 numbers: a number with an input limit (styles COMMON_LIMITS, style LIMITS) is drawn inside
its range (a third of the time at an end of it); any other number (plant tech, crew standard, ...) is scaled by
0.25-4x, or zeroed now and then. --no-limits skips the ranges as design.py does: everything is scaled, and the
contract is the same. Every failure is written to --out as <id>_<case>.json (the mutant, ready for design.py)
with <id>_<case>.txt (what broke); builds slower than --slow seconds are saved the same way (the designer
rebuilds on every knob change) but don't fail the run. The run is reproducible from --seed.
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import os
import random
import resource
import signal
import time
import traceback


def numeric_leaves(d, path=()):
    """[(path, value)] of every int/float leaf (not bools) in a design, list entries by index."""
    out = []
    items = d.items() if isinstance(d, dict) else enumerate(d) if isinstance(d, list) else ()
    for k, v in items:
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            out.append((path + (k,), v))
        elif isinstance(v, (dict, list)):
            out += numeric_leaves(v, path + (k,))
    return out


def set_at(d, path, v):
    for k in path[:-1]:
        d = d[k]
    d[path[-1]] = v


def limit_of(limits, path):
    """The input range for a leaf, matching the limits' paths with list indices taken out."""
    return limits.get(tuple(k for k in path if not isinstance(k, int)))


def mutate(design, rng, use_limits):
    import styles
    d = json.loads(json.dumps(design))
    limits = styles.get(d).limits() if use_limits else {}
    leaves = [(p, v) for p, v in numeric_leaves(d) if p[0] not in ("look",)]
    changes = []
    for path, v in rng.sample(leaves, min(len(leaves), rng.randint(1, 4))):
        lim = limit_of(limits, path)
        if lim:
            lo, hi = lim
            if rng.random() < 1 / 3:
                nv = rng.choice((lo, hi))
            elif lo > 0 and hi / lo > 20:
                nv = math.exp(rng.uniform(math.log(lo), math.log(hi)))
            else:
                nv = rng.uniform(lo, hi)
        elif rng.random() < 0.1:
            nv = 0
        else:
            nv = v * math.exp(rng.uniform(math.log(0.25), math.log(4)))
        if isinstance(v, int):
            nv = int(round(nv))
        else:
            nv = round(nv, 3)
        set_at(d, path, nv)
        changes.append((".".join(map(str, path)), v, nv))
    return d, changes


def finite(x):
    """Is every number in a JSON-like value finite?"""
    if isinstance(x, float):
        return math.isfinite(x)
    if isinstance(x, dict):
        return all(finite(v) for v in x.values())
    if isinstance(x, (list, tuple)):
        return all(finite(v) for v in x)
    return True


def _init(mem_gb):
    lim = int(mem_gb * 2 ** 30)
    resource.setrlimit(resource.RLIMIT_AS, (lim, lim))


class Hang(Exception):
    pass


def _alarm(*_):
    raise Hang()


def run_case(args):
    """Build one mutant: (case, design path, mutant, changes, timeout) -> (case, path, outcome, detail, s, ...)."""
    case, src, d, changes, timeout, use_limits = args
    import shipdesign
    errs = shipdesign.validate(d, limits=use_limits)
    if errs:
        return case, src, "invalid", errs[0], 0.0, d, changes
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(timeout)
    t = time.time()
    try:
        ship = shipdesign.build(d)
        json.dumps(ship["report"], allow_nan=False)
        if not finite(ship["hitboxes"]) or not finite(ship["render"]["columns"]):
            raise ValueError("a NaN or infinity in the hitboxes or height columns")
        outcome = "ok" if ship["report"]["valid"] else "errors"
        detail = "" if outcome == "ok" else ship["report"]["errors"][0]
    except Hang:
        outcome, detail = "hang", f"no result after {timeout} s"
    except MemoryError:
        outcome, detail = "memory", traceback.format_exc()
    except Exception as e:      # noqa: BLE001 - every exception is a finding
        outcome, detail = "crash", f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    finally:
        signal.alarm(0)
    return case, src, outcome, detail, time.time() - t, d, changes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("designs", nargs="+")
    ap.add_argument("--cases", type=int, default=400)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    ap.add_argument("--mem-gb", type=float, default=3.0, help="address-space cap per worker (default 3 GB)")
    ap.add_argument("--timeout", type=int, default=120, help="seconds per build before it counts as a hang")
    ap.add_argument("--slow", type=float, default=30.0, help="save builds slower than this (s) as findings too")
    ap.add_argument("--no-limits", action="store_true", help="skip the input ranges, as design.py --no-limits")
    ap.add_argument("--out", default="fuzz_out")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    bases = []
    for p in args.designs:
        with open(p) as fh:
            bases.append((p, json.load(fh)))
    jobs = []
    for case in range(args.cases):
        src, base = bases[case % len(bases)]
        d, changes = mutate(base, rng, not args.no_limits)
        jobs.append((case, src, d, changes, args.timeout, not args.no_limits))
    counts, bad, slow = {}, [], []
    with mp.Pool(args.jobs, initializer=_init, initargs=(args.mem_gb,), maxtasksperchild=1) as pool:
        for case, src, outcome, detail, dt, d, changes in pool.imap_unordered(run_case, jobs):
            counts[outcome] = counts.get(outcome, 0) + 1
            if dt > args.slow and outcome not in ("crash", "memory", "hang"):
                slow.append((dt, case, src))
                outcome, detail = "slow", f"{dt:.0f} s ({outcome})"
            if outcome in ("crash", "memory", "hang", "slow"):
                if outcome != "slow":
                    bad.append(case)
                os.makedirs(args.out, exist_ok=True)
                stem = os.path.join(args.out, f"{d['id']}_{case}")
                with open(stem + ".json", "w") as fh:
                    json.dump(d, fh, indent=1)
                with open(stem + ".txt", "w") as fh:
                    fh.write(f"{src}, changed: " + "; ".join(f"{p} {a} -> {b}" for p, a, b in changes) + "\n\n")
                    fh.write(f"{outcome}: {detail}\n")
                if outcome == "slow":
                    continue
                print(f"{outcome.upper():>7} {stem}.json  ({'; '.join(f'{p} {a} -> {b}' for p, a, b in changes)})"
                      f"\n        {detail.splitlines()[0] if detail else ''}", flush=True)
    print("outcomes:", ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    for dt, case, src in sorted(slow, reverse=True)[:10]:
        print(f"   slow: case {case} ({src}) {dt:.0f} s")
    if bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
