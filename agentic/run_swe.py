#!/usr/bin/env python3
"""Agentic SWE-rebench benchmark, wired into the head-to-head runner.

Invoked by ../run.py exactly like the other benchmarks (via env: RESULT_NAME,
MODEL_*, LIMIT, LIMIT_SEED, CONC). It:
  1. samples N clean SWE-rebench instances (default the post-cutoff 2026_03 split),
  2. runs mini-swe-agent against the model (its own agentic loop + Docker),
  3. grades with the SWE-rebench eval fork,
  4. writes results/<RESULT_NAME>.jsonl (one row per instance: resolved + cost),
so run.py can tabulate it identically to the API benchmarks.

Cost: the agentic harness (mini/litellm) does not propagate an API's inline cost,
so $/task is computed from token usage — which mini records per turn in the
trajectory — times the configured per-1M-token prices
(MODEL_INPUT_PRICE_PER_MTOK / MODEL_OUTPUT_PRICE_PER_MTOK). If those are unset,
the score is still reported and $/task is left blank.

Extra setup (see ../README.md "Agentic benchmark"): Docker, mini-swe-agent, and the
SWE-rebench fork of `swebench`. Point SWE_MINI_BIN and SWE_GRADER_PYTHON at them.
"""
from __future__ import annotations

import glob
import json
import os
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"

DATASET = os.environ.get("SWE_DATASET", "nebius/SWE-rebench-leaderboard")
SPLIT = os.environ.get("SWE_SPLIT", "2026_03")
MINI_BIN = os.environ.get("SWE_MINI_BIN", "mini-extra")          # mini-swe-agent entrypoint
GRADER_PY = os.environ.get("SWE_GRADER_PYTHON", sys.executable)  # MUST be the SWE-rebench fork's python


def sample_ids(limit: int | None, seed: int) -> list[str]:
    override = os.environ.get("SWE_FILTER_IDS")
    if override:
        return [x.strip() for x in override.split(",") if x.strip()]
    from datasets import load_dataset
    ds = load_dataset(DATASET, split=SPLIT)
    ids = sorted(ds["instance_id"])
    if limit is None or limit >= len(ids):
        return ids
    return sorted(random.Random(seed).sample(ids, limit))


def sum_tokens(traj_path: Path) -> tuple[int, int]:
    """Sum prompt/completion tokens across every assistant turn in a trajectory."""
    pt = ct = 0
    try:
        d = json.loads(traj_path.read_text())
        for m in d.get("messages", []):
            resp = ((m.get("extra") or {}).get("response")) or {}
            u = resp.get("usage") or {}
            pt += u.get("prompt_tokens") or 0
            ct += u.get("completion_tokens") or 0
    except Exception:
        pass
    return pt, ct


def main() -> None:
    result_name = os.environ.get("RESULT_NAME", "swe_rebench")
    limit = os.environ.get("LIMIT")
    limit = int(limit) if limit else None
    seed = int(os.environ.get("LIMIT_SEED", "0"))
    conc = int(os.environ.get("CONC", "3"))
    base_url = os.environ["MODEL_BASE_URL"]
    api_key = os.environ.get("MODEL_API_KEY", "dummy")
    model = os.environ.get("MODEL_NAME", "route")
    in_price = os.environ.get("MODEL_INPUT_PRICE_PER_MTOK")
    out_price = os.environ.get("MODEL_OUTPUT_PRICE_PER_MTOK")

    ids = sample_ids(limit, seed)
    if not ids:
        sys.exit("swe_rebench: no instances selected")
    id_filter = "(" + "|".join(ids) + ")"
    outdir = RESULTS / f"swe_out_{result_name}"

    # 1) run mini-swe-agent against the model
    env = dict(os.environ)
    env["OPENAI_API_BASE"] = base_url
    env["OPENAI_BASE_URL"] = base_url
    env["OPENAI_API_KEY"] = api_key
    env["MSWEA_COST_TRACKING"] = "ignore_errors"
    env["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    print(f"    swe_rebench: {len(ids)} instances, model={model}, workers={conc}", flush=True)
    subprocess.run(
        [MINI_BIN, "swebench", "--subset", DATASET, "--split", SPLIT,
         "--filter", id_filter, "-m", f"openai/{model}", "-w", str(conc), "-o", str(outdir)],
        cwd=ROOT, env=env,
    )

    preds = outdir / "preds.json"
    if not preds.exists():
        sys.exit(f"swe_rebench: mini produced no predictions at {preds}")

    # 2) grade with the SWE-rebench fork
    run_id = f"{result_name}_grade"
    subprocess.run(
        [GRADER_PY, "-m", "swebench.harness.run_evaluation",
         "--dataset_name", DATASET, "--split", SPLIT,
         "--predictions_path", str(preds), "--run_id", run_id,
         "--max_workers", str(min(conc + 1, 4))],
        cwd=ROOT,
    )
    reports = sorted(glob.glob(str(ROOT / f"*{run_id}*.json")), key=os.path.getmtime)
    resolved: set[str] = set()
    if reports:
        rep = json.loads(Path(reports[-1]).read_text())
        resolved = set(rep.get("resolved_ids") or [])
    else:
        print("    swe_rebench: WARNING no grade report found — scores will be 0", flush=True)

    # 3) per-instance rows: resolved + cost (tokens x price)
    RESULTS.mkdir(exist_ok=True)
    rows = []
    for iid in ids:
        traj = outdir / iid / f"{iid}.traj.json"
        cost = None
        if traj.exists() and in_price and out_price:
            pt, ct = sum_tokens(traj)
            if pt or ct:
                cost = pt * float(in_price) / 1e6 + ct * float(out_price) / 1e6
        rows.append({"id": iid, "correct": iid in resolved, "cost_usd": cost})
    with open(RESULTS / f"{result_name}.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    n = len(rows)
    res = sum(1 for r in rows if r["correct"])
    priced = sum(1 for r in rows if r["cost_usd"] is not None)
    note = "" if priced == n else f" (cost for {priced}/{n}; set *_PRICE_PER_MTOK)"
    print(f"[{result_name}] {round(100 * res / n, 1)}%  ({res}/{n} resolved){note}", flush=True)


if __name__ == "__main__":
    main()
