"""Shared runner for the non-agentic benchmarks (ARC-AGI-2, HMMT, HLE-no-tools,
MMMU-Pro, DRACO-scoring). Handles concurrency, per-item results, and the summary
(accuracy / latency / cost). Agentic benchmarks use their own official harnesses
(see ../agentic/) and are NOT run through here.
"""
from __future__ import annotations

import json
import os
import random
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from .cost import cost_since


def _apply_limit(items: list[dict]) -> list[dict]:
    """LIMIT=N env -> a REPRESENTATIVE seeded-random subsample of N items (never first-N).
    LIMIT_SEED (default 0) fixes the draw. Used for smoke tests / quick reps."""
    n = os.environ.get("LIMIT")
    if not n:
        return items
    n = int(n)
    if n >= len(items):
        return items
    rng = random.Random(int(os.environ.get("LIMIT_SEED", "0")))
    return rng.sample(items, n)


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
    # OUT_DIR env overrides the default so slice runs (run_slice.sh) can land
    # in a per-run directory without touching every benchmark module.
    out_dir = os.environ.get("OUT_DIR", out_dir)
    os.makedirs(out_dir, exist_ok=True)
    items = _apply_limit(items)
    t_start = time.time()
    rows: list[dict] = []

    def _one(it: dict) -> dict:
        t0 = time.time()
        try:
            pred, meta = solve(it)
            return {
                "id": it.get("id"),
                "correct": bool(grade(it, pred)),
                "started_at": round(t0, 3),
                "finished_at": round(time.time(), 3),
                "latency_s": round(meta.get("latency_s", 0.0), 3),
                "usage": _usage(meta.get("usage")),
                "cost_usd": meta.get("cost_usd"),
                "retries": meta.get("retries"),
                "finish": meta.get("finish_reason"),
                "pred": (str(pred)[:800] if pred is not None else None),
            }
        except Exception as e:  # never let one item kill the run
            # Record enough to correlate a failure with server-side logs: when it
            # ran, how long it survived, and the provider's request id if the SDK
            # attached one. Without these a failed item is undebuggable downstream.
            rid = getattr(e, "request_id", None)
            if rid is None:
                resp = getattr(e, "response", None)
                if resp is not None:
                    try:
                        rid = resp.headers.get("x-request-id") or resp.headers.get("request-id")
                    except Exception:
                        rid = None
            return {
                "id": it.get("id"),
                "correct": False,
                "started_at": round(t0, 3),
                "finished_at": round(time.time(), 3),
                "latency_s": round(time.time() - t0, 3),
                "request_id": rid,
                "error": f"{type(e).__name__}: {e}"[:300],
            }

    total = len(items)
    jsonl_path = os.path.join(out_dir, f"{name}.jsonl")
    # Incremental: write each row as it completes (flushed) + log progress, so a long
    # run is visibly progressing and its partial results are recoverable (a crash or a
    # kill leaves the completed items on disk). Rewritten once more at the end is
    # unnecessary — this IS the file.
    with ThreadPoolExecutor(max_workers=concurrency) as ex, open(jsonl_path, "w") as _jf:
        for i, fut in enumerate(as_completed([ex.submit(_one, it) for it in items]), 1):
            r = fut.result()
            rows.append(r)
            _jf.write(json.dumps(r) + "\n"); _jf.flush()
            if i % 10 == 0 or i == total:
                _ok = sum(1 for x in rows if x["correct"])
                _er = sum(1 for x in rows if x.get("error"))
                print(f"[{name}] progress {i}/{total}  ok={_ok} err={_er}", flush=True)

    n = len(rows)
    correct = sum(1 for r in rows if r["correct"])
    errored = sum(1 for r in rows if r.get("error"))
    lats = [r["latency_s"] for r in rows if r.get("latency_s")]
    # Authoritative cost = sum of per-item cost from each response (concurrency-safe).
    # Fall back to the shared server cost log only if the endpoint returned no cost.
    item_costs = [r["cost_usd"] for r in rows if r.get("cost_usd") is not None]
    if item_costs:
        cost_total = round(sum(item_costs), 6)
        cost_source = "per_item_response"
    elif cost_log:
        cost_total = cost_since(cost_log, t_start)
        cost_source = "server_log"
    else:
        cost_total = None
        cost_source = None
    summary = {
        "benchmark": name,
        "n": n,
        "resolved": correct,
        "accuracy": round(100 * correct / n, 2) if n else 0.0,
        "errored": errored,
        "latency_median_s": round(statistics.median(lats), 2) if lats else None,
        "latency_mean_s": round(statistics.mean(lats), 2) if lats else None,
        "wall_s": round(time.time() - t_start, 1),
        "cost_usd_total": cost_total,
        "cost_source": cost_source,
        "n_priced": len(item_costs),
        "total_retries": sum(r.get("retries") or 0 for r in rows),
    }
    if summary["cost_usd_total"] is not None and n:
        summary["cost_usd_per_task"] = round(summary["cost_usd_total"] / n, 5)

    # jsonl already written incrementally above; just the summary here.
    with open(os.path.join(out_dir, f"{name}.summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(f"[{name}] {summary['accuracy']}%  ({correct}/{n}, {errored} err)  "
          f"lat_med={summary['latency_median_s']}s  $/task={summary.get('cost_usd_per_task')}")
    return summary
