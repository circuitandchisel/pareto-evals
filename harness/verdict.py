"""Machine-readable eval verdicts (gpu-router#185, pipeline v0).

Turns a slice run (results/*.summary.json) into ONE verdict JSON tied to the
exact config under test, and compares a candidate verdict against a baseline.
This replaces "run some benchmarks and tick a PR checkbox" with an artifact:

    verdict collect  -> verdicts/verdict-<tag>-<ts>.json
    verdict compare baseline.json candidate.json [--max-acc-drop 5]

Compare is deliberately honest about noise: per-benchmark accuracy deltas are
reported with a binomial 95% CI on the diff, and a regression only FAILS the
gate when the drop exceeds --max-acc-drop AND the CI excludes zero. Small-n
slices (LIMIT=30) can therefore pass on noise — the gate catches collapses,
not single-point differences. Full-slate runs remain the bar for RC claims
(see FINDINGS.md methodology).
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import os
import subprocess
import sys
import time


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=os.path.dirname(os.path.dirname(__file__)),
            text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def collect(args: argparse.Namespace) -> int:
    summaries = {}
    for path in sorted(glob.glob(os.path.join(args.results, "*.summary.json"))):
        with open(path) as f:
            s = json.load(f)
        summaries[s["benchmark"]] = s
    if not summaries:
        print(f"no *.summary.json under {args.results}/", file=sys.stderr)
        return 1

    config_hash = None
    if args.config_file and os.path.exists(args.config_file):
        config_hash = hashlib.sha256(open(args.config_file, "rb").read()).hexdigest()

    verdict = {
        "schema": "pareto-eval-verdict/v0",
        "tag": args.tag,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "endpoint": os.environ.get("ATXP_MODEL_BASE_URL"),
        "model": os.environ.get("ATXP_MODEL_NAME"),
        "limit": os.environ.get("LIMIT"),
        "limit_seed": os.environ.get("LIMIT_SEED", "0"),
        "config": {
            # What was measured: pin/hash of the serving config under test.
            "app_commit": args.app_commit or os.environ.get("PARETO_APP_COMMIT"),
            "config_file": args.config_file,
            "config_sha256": config_hash,
        },
        "harness_sha": _git_sha(),
        "benchmarks": summaries,
    }

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(verdict, f, indent=2)
    print(f"verdict: {args.out}")
    for name, s in summaries.items():
        print(f"  {name}: {s['accuracy']}% (n={s['n']}, err={s['errored']}) "
              f"lat_med={s['latency_median_s']}s $/task={s.get('cost_usd_per_task')}")
    return 0


def _diff_ci(p1: float, n1: int, p2: float, n2: int) -> float:
    """95% CI half-width for the difference of two proportions (in pct points)."""
    if not n1 or not n2:
        return float("inf")
    v = p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2
    return 1.96 * math.sqrt(v) * 100.0


def compare(args: argparse.Namespace) -> int:
    base = json.load(open(args.baseline))
    cand = json.load(open(args.candidate))
    print(f"baseline : {base.get('tag')} model={base.get('model')} "
          f"commit={base.get('config', {}).get('app_commit')}")
    print(f"candidate: {cand.get('tag')} model={cand.get('model')} "
          f"commit={cand.get('config', {}).get('app_commit')}")

    failures = []
    for name, b in base.get("benchmarks", {}).items():
        c = cand.get("benchmarks", {}).get(name)
        if not c:
            print(f"  {name}: MISSING in candidate")
            failures.append(f"{name}: missing")
            continue
        d = c["accuracy"] - b["accuracy"]
        ci = _diff_ci(b["accuracy"] / 100, b["n"], c["accuracy"] / 100, c["n"])
        sig = abs(d) > ci
        lat_note = ""
        if b.get("latency_median_s") and c.get("latency_median_s"):
            lat_note = f"  lat {b['latency_median_s']}s -> {c['latency_median_s']}s"
        print(f"  {name}: {b['accuracy']}% -> {c['accuracy']}%  "
              f"Δ{d:+.1f} (±{ci:.1f} CI95{', significant' if sig else ', noise'})"
              f"{lat_note}")
        if d < -args.max_acc_drop and sig:
            failures.append(f"{name}: {d:+.1f} beyond ±{ci:.1f}")

    extra = set(cand.get("benchmarks", {})) - set(base.get("benchmarks", {}))
    for name in sorted(extra):
        print(f"  {name}: (candidate-only, not gated)")

    if failures:
        print(f"VERDICT: FAIL — {'; '.join(failures)}")
        return 1
    print("VERDICT: PASS (no significant regression beyond "
          f"{args.max_acc_drop}pp)")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="harness.verdict")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="merge results/*.summary.json into one verdict")
    c.add_argument("--results", default="results")
    c.add_argument("--out", required=True)
    c.add_argument("--tag", default="slice")
    c.add_argument("--app-commit", default=None,
                   help="draco-bench-box commit under test (defaults to $PARETO_APP_COMMIT)")
    c.add_argument("--config-file", default=None,
                   help="path to the rc.env under test (hashed into the verdict)")
    c.set_defaults(fn=collect)

    d = sub.add_parser("compare", help="gate a candidate verdict against a baseline")
    d.add_argument("baseline")
    d.add_argument("candidate")
    d.add_argument("--max-acc-drop", type=float, default=5.0,
                   help="fail when accuracy drops more than this (pct points) AND beyond CI noise")
    d.set_defaults(fn=compare)

    args = p.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
