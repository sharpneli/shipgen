#!/usr/bin/env python3
"""
fuzz: robustness test for the design side. Mutates designs and builds every mutant that passes
validate(), each in its own worker with a memory cap and a time limit. The contract (permissive generator): any
valid design builds, with errors and warnings if it's silly, but never an exception, a hang, a memory blow-up or
a NaN in the published result.

    python fuzz.py designs/*.json [--cases 400] [--seed 1] [--jobs 16] [--mem-gb 3] [--timeout 120]
                   [--mode all|numbers|choices|structure] [--slow 30] [--no-limits] [--out fuzz_out]

A mutant makes 1-4 changes (--mode picks the kind; "all" mixes them):
  numbers    a number with an input limit (styles COMMON_LIMITS, style LIMITS) is drawn inside its range (a third
             of the time at an end of it); any other number (plant tech, crew standard, ...) is scaled by 0.25-4x,
             or zeroed now and then
  choices    a tickbox flipped, or a multiple choice swapped for another option the fleet uses for that key: the
             designer's promise is that any combination of ticks gives a ship
  structure  a list entry (a battery, a raised stretch, an armour deck) duplicated or dropped, or an optional key
             deleted so its default applies
Labels (id, name, look, materials) are left alone. --no-limits skips the ranges as design.py does: every number
is scaled, and the contract is the same. Every failure is written to --out as <id>_<case>.json (the mutant, ready for design.py)
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


def set_at(d, path, v):
    for k in path[:-1]:
        d = d[k]
    d[path[-1]] = v


def limit_of(limits, path):
    """The input range for a leaf, matching the limits' paths with list indices taken out."""
    return limits.get(tuple(k for k in path if not isinstance(k, int)))


LABELS = ("id", "name", "look", "material", "materials", "type")    # free text for the game, not choices


def leaves_of(d, kinds, path=()):
    """[(path, value)] of every leaf of the given types (bools apart from ints) in a design, list entries by index,
    labels left out."""
    out = []
    items = d.items() if isinstance(d, dict) else enumerate(d) if isinstance(d, list) else ()
    for k, v in items:
        if k in LABELS:
            continue
        if isinstance(v, (dict, list)):
            out += leaves_of(v, kinds, path + (k,))
        elif (bool in kinds) == isinstance(v, bool) and isinstance(v, kinds):
            out.append((path + (k,), v))
    return out


def containers(d, path=()):
    """[(path, container)] of every dict and list below the top, labels left out."""
    out = []
    items = d.items() if isinstance(d, dict) else enumerate(d) if isinstance(d, list) else ()
    for k, v in items:
        if k not in LABELS and isinstance(v, (dict, list)):
            out.append((path + (k,), v))
            out += containers(v, path + (k,))
    return out


def corpus_choices(designs):
    """{key: sorted string values} the fleet gives each key: the multiple-choice options a mutant may swap in."""
    seen = {}
    for d in designs:
        for path, v in leaves_of(d, (str,)):
            key = next(k for k in reversed(path) if not isinstance(k, int))
            seen.setdefault(key, set()).add(v)
    return {k: sorted(v) for k, v in seen.items()}


def mutate_number(d, rng, limits):
    nums = leaves_of(d, (int, float))
    if not nums:
        return None
    path, v = rng.choice(nums)
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
    nv = int(round(nv)) if isinstance(v, int) else round(nv, 3)
    set_at(d, path, nv)
    return ".".join(map(str, path)), v, nv


def mutate_choice(d, rng, choices):
    """A tickbox flipped, or a multiple choice swapped for another option the fleet uses for that key."""
    opts = leaves_of(d, (bool,)) + [(p, v) for p, v in leaves_of(d, (str,))
                                    if len(choices.get(next(k for k in reversed(p) if not isinstance(k, int)), ())) > 1]
    if not opts:
        return None
    path, v = rng.choice(opts)
    if isinstance(v, bool):
        nv = not v
    else:
        key = next(k for k in reversed(path) if not isinstance(k, int))
        nv = rng.choice([c for c in choices[key] if c != v])
    set_at(d, path, nv)
    return ".".join(map(str, path)), v, nv


def mutate_structure(d, rng):
    """A list entry (a battery, a raised stretch, an armour deck) duplicated or dropped, or an optional key deleted
    (its default then applies)."""
    conts = [(p, c) for p, c in containers(d) if c]
    if not conts:
        return None
    path, c = rng.choice(conts)
    if isinstance(c, list) and isinstance(c[0], dict) and rng.random() < 0.5:
        i = rng.randrange(len(c))
        c.insert(i, json.loads(json.dumps(c[i])))
        return ".".join(map(str, path)), f"{len(c) - 1} entries", f"{len(c)} (entry {i} twice)"
    if isinstance(c, list):
        i = rng.randrange(len(c))
        c.pop(i)
        return ".".join(map(str, path)), f"{len(c) + 1} entries", f"{len(c)} (entry {i} dropped)"
    k = rng.choice(list(c))
    v = c.pop(k)
    return ".".join(map(str, path + (k,))), json.dumps(v)[:40], "(deleted)"


def mutate(design, rng, use_limits, choices, mode):
    """1-4 changes: numbers, choices (tickboxes, options) and structure, as mode asks ("all": mostly numbers)."""
    import styles
    d = json.loads(json.dumps(design))
    changes = []
    for _ in range(rng.randint(1, 4)):
        kind = mode if mode != "all" else rng.choices(("numbers", "choices", "structure"), (0.6, 0.25, 0.15))[0]
        try:
            limits = styles.get(d).limits() if use_limits else {}
        except KeyError:        # the style itself was swapped for one that doesn't exist: validate says so
            limits = {}
        ch = (mutate_number(d, rng, limits) if kind == "numbers" else
              mutate_choice(d, rng, choices) if kind == "choices" else mutate_structure(d, rng))
        if ch:
            changes.append(ch)
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
    ap.add_argument("--mode", choices=("all", "numbers", "choices", "structure"), default="all",
                    help="what mutants change (all: numbers 60%%, choices 25%%, structure 15%%)")
    ap.add_argument("--out", default="fuzz_out")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    bases = []
    for p in args.designs:
        with open(p) as fh:
            bases.append((p, json.load(fh)))
    choices = corpus_choices([b for _, b in bases])
    jobs = []
    for case in range(args.cases):
        src, base = bases[case % len(bases)]
        d, changes = mutate(base, rng, not args.no_limits, choices, args.mode)
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
