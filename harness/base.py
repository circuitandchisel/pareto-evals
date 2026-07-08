"""Shared runner for the non-agentic benchmarks (ARC-AGI-2, HMMT, HLE-no-tools,
MMMU-Pro, DRACO-scoring). Handles concurrency, per-item results, and the summary
(accuracy / latency / cost). Agentic benchmarks use their own official harnesses
(see ../agentic/) and are NOT run through here.
"""
from __future__ import annotations

import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from .cost import cost_since


def _usage(u) -> dict | None:
    if u is None:
        return None
    try:
        return {"prompt": u.prompt_tokens, "completion": u.completion_tokens, "total": u.total_tokens}
    except Exception:
        return None


def run_benchmark(
    name: str,
    items: list[dict],
    solve: Callable[[dict], tuple],   # solve(item) -> (pred, meta)  (must call model_complete)
    grade: Callable[[dict, object], bool],  # grade(item, pred) -> bool
    *,
    concurrency: int = 4,
    out_dir: str = "results",
    cost_log: str | None = None,      # server cost log for authoritative $/task
) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    t_start = time.time()
    rows: list[dict] = []

    def _one(it: dict) -> dict:
        try:
            pred, meta = solve(it)
            return {
                "id": it.get("id"),
                "correct": bool(grade(it, pred)),
                "latency_s": round(meta.get("latency_s", 0.0), 3),
                "usage": _usage(meta.get("usage")),
                "finish": meta.get("finish_reason"),
                "pred": (str(pred)[:800] if pred is not None else None),
            }
        except Exception as e:  # never let one item kill the run
            return {"id": it.get("id"), "correct": False, "error": f"{type(e).__name__}: {e}"[:300]}

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        for fut in as_completed([ex.submit(_one, it) for it in items]):
            rows.append(fut.result())

    n = len(rows)
    correct = sum(1 for r in rows if r["correct"])
    errored = sum(1 for r in rows if r.get("error"))
    lats = [r["latency_s"] for r in rows if r.get("latency_s")]
    summary = {
        "benchmark": name,
        "n": n,
        "resolved": correct,
        "accuracy": round(100 * correct / n, 2) if n else 0.0,
        "errored": errored,
        "latency_median_s": round(statistics.median(lats), 2) if lats else None,
        "latency_mean_s": round(statistics.mean(lats), 2) if lats else None,
        "wall_s": round(time.time() - t_start, 1),
        "cost_usd_total": cost_since(cost_log, t_start) if cost_log else None,
    }
    if summary["cost_usd_total"] is not None and n:
        summary["cost_usd_per_task"] = round(summary["cost_usd_total"] / n, 5)

    with open(os.path.join(out_dir, f"{name}.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    with open(os.path.join(out_dir, f"{name}.summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(f"[{name}] {summary['accuracy']}%  ({correct}/{n}, {errored} err)  "
          f"lat_med={summary['latency_median_s']}s  $/task={summary.get('cost_usd_per_task')}")
    return summary
