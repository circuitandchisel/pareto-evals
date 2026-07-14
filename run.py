#!/usr/bin/env python3
"""Pareto-evals head-to-head runner.

Runs the benchmarks you choose against your **Pareto API** and a **comparison
model** (e.g. Claude Opus), and prints one table:

    benchmark | Pareto score | Pareto $/task | <comparison> score | <comparison> $/task

Everything is configured in `.env` (copy `.env.example`) plus a few CLI flags.
No latency is tracked — only accuracy and cost-per-task.

Examples
--------
    # full slate, full size, both models (uses .env)
    python run.py

    # just GPQA + HLE, 100 items each
    python run.py --benchmarks gpqa,hle --slice 100

    # per-benchmark slice sizes; Pareto only (skip the comparison model)
    python run.py --benchmarks gpqa,arxiv_math --slice gpqa=200,arxiv_math=all --models pareto
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"

# Benchmark registry. Each entry maps a short name -> the module run via
# `python -m <module>`. `judge=True` means the benchmark grades free-form answers
# with an LLM judge (needs JUDGE_* in .env). All are non-agentic (single API call
# per item). Agentic SWE-rebench uses a separate harness — see agentic/README.md.
BENCHMARKS: dict[str, dict] = {
    "gpqa":       {"module": "benchmarks.gpqa",       "judge": False, "grader": "exact letter (A-D)"},
    "hle":        {"module": "benchmarks.hle",        "judge": True,  "grader": "LLM judge"},
    "arxiv_math": {"module": "benchmarks.arxiv_math", "judge": False, "grader": "symbolic math match"},
    "mmmu_pro":   {"module": "benchmarks.mmmu_pro",   "judge": False, "grader": "exact (MCQ)"},
    "arc_agi_2":  {"module": "benchmarks.arc_agi_2",  "judge": False, "grader": "exact grid"},
}
DEFAULT_ORDER = ["gpqa", "hle", "arxiv_math", "mmmu_pro", "arc_agi_2"]


def load_env(path: str = ".env") -> None:
    """Minimal .env loader (no dependency). Existing env vars win."""
    p = ROOT / path
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


def model_cfg(prefix: str) -> dict | None:
    """Read a model's config from PREFIX_* env vars. Returns None if unconfigured."""
    base = os.environ.get(f"{prefix}_BASE_URL")
    if not base:
        return None
    return {
        "key": prefix.lower(),
        "label": os.environ.get(f"{prefix}_LABEL", prefix.capitalize()),
        "base_url": base,
        "api_key": os.environ.get(f"{prefix}_API_KEY", "dummy"),
        "model": os.environ.get(f"{prefix}_MODEL", "route"),
        "in_price": _f(os.environ.get(f"{prefix}_INPUT_PRICE_PER_MTOK")),
        "out_price": _f(os.environ.get(f"{prefix}_OUTPUT_PRICE_PER_MTOK")),
    }


def _f(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def parse_slices(slice_arg: str | None, benches: list[str]) -> dict[str, int | None]:
    """None => full size. "200" => 200 for all. "gpqa=100,hle=300" => per-benchmark."""
    out: dict[str, int | None] = {b: None for b in benches}
    if not slice_arg or slice_arg.lower() == "all":
        return out
    if "=" in slice_arg:
        for part in slice_arg.split(","):
            k, _, v = part.partition("=")
            k, v = k.strip(), v.strip()
            if k not in out:
                sys.exit(f"--slice: unknown benchmark '{k}' (known: {', '.join(benches)})")
            out[k] = None if v.lower() == "all" else int(v)
    else:
        n = int(slice_arg)
        for b in benches:
            out[b] = n
    return out


def run_benchmark_for_model(bench: str, m: dict, limit: int | None, concurrency: int, seed: int) -> str:
    """Run one benchmark against one model in a subprocess. Returns the result name."""
    info = BENCHMARKS[bench]
    result_name = f"{bench}__{m['key']}"
    env = dict(os.environ)
    env["MODEL_BASE_URL"] = m["base_url"]
    env["MODEL_API_KEY"] = m["api_key"]
    env["MODEL_NAME"] = m["model"]
    env["RESULT_NAME"] = result_name          # standardized across all benchmark mains
    env["CONC"] = str(concurrency)
    env["LIMIT_SEED"] = str(seed)
    if limit is not None:
        env["LIMIT"] = str(limit)
    else:
        env.pop("LIMIT", None)
    # Judge (free-form graders) — passed straight through from .env if present.
    for k in ("JUDGE_BASE_URL", "JUDGE_API_KEY", "JUDGE_MODEL", "JUDGE_TIMEOUT"):
        if os.environ.get(k):
            env[k] = os.environ[k]

    print(f"  ▶ {bench} × {m['label']}  (limit={limit or 'full'}, model={m['model']})", flush=True)
    proc = subprocess.run([sys.executable, "-m", info["module"]], cwd=ROOT, env=env)
    if proc.returncode != 0:
        print(f"    ! {bench} × {m['label']} exited {proc.returncode} (see output above)", flush=True)
    return result_name


def score_and_cost(result_name: str, m: dict) -> dict:
    """Read results/<name>.jsonl and compute accuracy + $/task.

    Cost per item = the response's own cost if the API returned one (`cost_usd`),
    else tokens × configured price (PREFIX_INPUT/OUTPUT_PRICE_PER_MTOK). $/task is
    the mean over items that have a cost; `cost_cov` reports coverage.
    """
    jl = RESULTS / f"{result_name}.jsonl"
    if not jl.exists():
        return {"n": 0, "score": None, "cost_per_task": None, "cost_cov": 0, "note": "no results"}
    rows = [json.loads(l) for l in jl.read_text().splitlines() if l.strip()]
    n = len(rows)
    correct = sum(1 for r in rows if r.get("correct"))
    errored = sum(1 for r in rows if r.get("error"))
    costs = []
    for r in rows:
        c = r.get("cost_usd")
        if c is None and m.get("in_price") is not None and m.get("out_price") is not None:
            u = r.get("usage") or {}
            pt, ct = u.get("prompt") or 0, u.get("completion") or 0
            if pt or ct:
                c = pt * m["in_price"] / 1e6 + ct * m["out_price"] / 1e6
        if c is not None:
            costs.append(c)
    return {
        "n": n,
        "errored": errored,
        "score": round(100 * correct / n, 1) if n else None,
        "cost_per_task": round(sum(costs) / len(costs), 5) if costs else None,
        "cost_cov": len(costs),
        "note": "" if not errored else f"{errored} errored",
    }


def render_table(rows: list[dict], pareto_label: str, comp_label: str | None) -> str:
    def fmt_score(v):
        return f"{v:.1f}%" if isinstance(v, (int, float)) else "—"

    def fmt_cost(v):
        return f"${v:.4f}" if isinstance(v, (int, float)) else "—"

    cols = ["Benchmark", "n", f"{pareto_label} score", f"{pareto_label} $/task"]
    if comp_label:
        cols += [f"{comp_label} score", f"{comp_label} $/task"]
    md = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for r in rows:
        cells = [r["bench"], str(r["pareto"]["n"]),
                 fmt_score(r["pareto"]["score"]), fmt_cost(r["pareto"]["cost_per_task"])]
        if comp_label:
            cells += [fmt_score(r["comp"]["score"]), fmt_cost(r["comp"]["cost_per_task"])]
        md.append("| " + " | ".join(cells) + " |")
    return "\n".join(md)


def main() -> None:
    load_env()
    ap = argparse.ArgumentParser(description="Pareto-evals head-to-head runner.")
    ap.add_argument("--benchmarks", default="all",
                    help=f"comma list or 'all'. Known: {', '.join(DEFAULT_ORDER)}")
    ap.add_argument("--slice", default=None,
                    help="'all' (default), an int (all benchmarks), or 'gpqa=100,hle=300'")
    ap.add_argument("--models", default="pareto,comparison",
                    help="which to run: 'pareto', 'comparison', or 'pareto,comparison' (default)")
    ap.add_argument("--concurrency", type=int, default=int(os.environ.get("CONC", "6")))
    ap.add_argument("--seed", type=int, default=int(os.environ.get("LIMIT_SEED", "0")))
    ap.add_argument("--out", default="results/comparison.md")
    args = ap.parse_args()

    benches = DEFAULT_ORDER if args.benchmarks == "all" else [b.strip() for b in args.benchmarks.split(",")]
    for b in benches:
        if b not in BENCHMARKS:
            sys.exit(f"unknown benchmark '{b}'. Known: {', '.join(BENCHMARKS)}")
    slices = parse_slices(args.slice, benches)

    which = [w.strip() for w in args.models.split(",")]
    pareto = model_cfg("PARETO") if "pareto" in which else None
    comp = model_cfg("COMPARISON") if "comparison" in which else None
    if "pareto" in which and not pareto:
        sys.exit("PARETO_BASE_URL not set (see .env.example). Configure your Pareto API creds.")
    if "comparison" in which and not comp:
        print("NOTE: COMPARISON_BASE_URL not set — running Pareto only.", flush=True)

    # Warn if a judge-graded benchmark is selected without a judge configured.
    if any(BENCHMARKS[b]["judge"] for b in benches) and not os.environ.get("JUDGE_BASE_URL"):
        print("WARNING: a selected benchmark grades with an LLM judge but JUDGE_BASE_URL is "
              "unset — it will fall back to containment match (not publication-grade).", flush=True)

    print(f"Benchmarks: {', '.join(benches)}")
    print(f"Models: {', '.join(m['label'] for m in (pareto, comp) if m)}")
    print(f"Slices: " + ", ".join(f"{b}={slices[b] or 'full'}" for b in benches) + "\n")

    table_rows = []
    for b in benches:
        row = {"bench": b}
        for role, m in (("pareto", pareto), ("comp", comp)):
            if not m:
                row[role] = {"n": 0, "score": None, "cost_per_task": None}
                continue
            name = run_benchmark_for_model(b, m, slices[b], args.concurrency, args.seed)
            row[role] = score_and_cost(name, m)
        table_rows.append(row)
        # incremental line so long runs show progress
        p, c = row["pareto"], row.get("comp", {})
        print(f"  ✓ {b}: Pareto {p.get('score')}% ${p.get('cost_per_task')}"
              + (f" | {comp['label']} {c.get('score')}% ${c.get('cost_per_task')}" if comp else ""), flush=True)

    table = render_table(table_rows, pareto["label"] if pareto else "Pareto",
                         comp["label"] if comp else None)
    print("\n" + table + "\n")
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(table + "\n")
    # also CSV
    csv = out.with_suffix(".csv")
    hdr = ["benchmark", "n", "pareto_score", "pareto_cost_per_task"]
    if comp:
        hdr += ["comparison_score", "comparison_cost_per_task"]
    lines = [",".join(hdr)]
    for r in table_rows:
        vals = [r["bench"], str(r["pareto"]["n"]), str(r["pareto"]["score"]), str(r["pareto"]["cost_per_task"])]
        if comp:
            vals += [str(r["comp"]["score"]), str(r["comp"]["cost_per_task"])]
        lines.append(",".join(vals))
    csv.write_text("\n".join(lines) + "\n")
    print(f"Wrote {out} and {csv}")


if __name__ == "__main__":
    main()
