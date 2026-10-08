#!/usr/bin/env python3
"""Parallel "Search Capability Leaderboard" projector — estimate a model's Search Intelligence
Score from the two OPEN suites, with the closed one (WISER) predicted from the published board.

Background (https://parallel.ai/leaderboard, update of 2026-10-05, 31 models). Parallel scores
"how effective models are at using search": each model answers the same 100 questions per
benchmark through one agent harness with Parallel Search (Fast mode) + Extract as tools, fixed
tool budgets, code execution disabled, provider-recommended reasoning settings; once the budget
is spent the model is asked for a final answer with tools off. Everything is also run once with
tools disabled ("without search"; lift = with − without).

    Search Intelligence Score = (DSQA F1 + HLE accuracy + WISER accuracy) / 3     (0–100)

  dsqa   DeepSearchQA (Google DeepMind; 900 public multi-step research tasks, 100 sampled) —
         answer extracted without the reference, then graded as F1 (partial credit).
  hle    Humanity's Last Exam (public; 100 sampled) — correct / incorrect.
  wiser  Parallel's own WISER business-research benchmark (100 questions) — CLOSED.

Failed/pending tasks count as 0. Cost per 1K tasks = inference + estimated Search/Extract
usage (grading excluded; Parallel says its cost records are incomplete). The "Search
Efficiency" board ranks models at or above the median score (62.7) by that cost.

Projection. WISER tracks the open suites (corr 0.85 with HLE, 0.81 with DSQA, both with
search); an OLS fit WISER ~ DSQA + HLE on the 31 rows has leave-one-out MAE ≈ 4.2 WISER
points, i.e. ≈ ±1.4 on the index (worst case ≈ 4.3). Both Pareto rows already on the board
are poorly fit — 26.9's WISER is ~6 below the fit, 26.10's ~13 above — so for Pareto treat
the projection as "index ≈ (DSQA + HLE + WISER_pred)/3 within about ±4", and prefer the
measured rows when Parallel has them (`--model` prints them).

Usage
-----
    python3 agentic/parallel_search_index.py --dsqa 87.6 --hle 58.0           # project
    python3 agentic/parallel_search_index.py --dsqa 87.6 --hle 58.0 --cost-per-1k 184
    python3 agentic/parallel_search_index.py --model "Pareto 26.9"              # board row
    python3 agentic/parallel_search_index.py --check                             # LOO table

The DSQA/HLE inputs must be *with-search* numbers from a comparable harness (Parallel Search
Fast + Extract, 100-question samples, F1 / binary grading). This repo does not yet ship that
harness; see agentic/README.md "Parallel Search Capability Leaderboard".
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEADERBOARD = HERE / "search_index" / "leaderboard_2026-10-05.csv"
OPEN = ("dsqa", "hle")
MEDIAN_EFFICIENCY_CUTOFF = 62.7


def load(path: Path = LEADERBOARD) -> list[dict]:
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(l for l in f if not l.startswith("#")):
            row = {k: r[k] for k in ("model", "slug", "model_id")}
            for k, v in r.items():
                if k not in row:
                    try:
                        row[k] = float(v)
                    except (TypeError, ValueError):
                        row[k] = None
            rows.append(row)
    return rows


def _ols(X, y):
    n = len(X[0])
    A = [[sum(X[i][a] * X[i][b] for i in range(len(X))) for b in range(n)] for a in range(n)]
    b = [sum(X[i][a] * y[i] for i in range(len(X))) for a in range(n)]
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                M[r] = [M[r][k] - f * M[c][k] for k in range(n + 1)]
    return [M[i][n] / M[i][i] for i in range(n)]


def feats(dsqa: float, hle: float) -> list[float]:
    return [1.0, dsqa, hle]


class Projector:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.w = _ols([feats(r["dsqa"], r["hle"]) for r in rows], [r["wiser"] for r in rows])
        self.wiser_max = max(r["wiser"] for r in rows)
        self.loo = self._loo()

    def wiser(self, dsqa, hle, w=None) -> float:
        v = sum(a * b for a, b in zip(w or self.w, feats(dsqa, hle)))
        return max(0.0, min(100.0, v))

    def _loo(self) -> dict:
        out = []
        for i, r in enumerate(self.rows):
            tr = [x for j, x in enumerate(self.rows) if j != i]
            w = _ols([feats(x["dsqa"], x["hle"]) for x in tr], [x["wiser"] for x in tr])
            p = self.wiser(r["dsqa"], r["hle"], w)
            out.append({"model": r["model"], "wiser": r["wiser"], "wiser_pred": p, "err": p - r["wiser"],
                        "score": r["score"], "score_pred": (r["dsqa"] + r["hle"] + p) / 3})
        errs = [abs(o["err"]) for o in out]
        return {"rows": out, "wiser_mae": sum(errs) / len(errs),
                "wiser_rmse": math.sqrt(sum(e * e for e in errs) / len(errs)), "wiser_max": max(errs)}

    def project(self, dsqa, hle, wiser=None) -> dict:
        wp = self.wiser(dsqa, hle) if wiser is None else wiser
        score = (dsqa + hle + wp) / 3
        return {"wiser_pred": wp, "score": score,
                "err_typical": self.loo["wiser_mae"] / 3, "err_max": self.loo["wiser_max"] / 3,
                "rank": 1 + sum(1 for r in self.rows if r["score"] > score), "rank_of": len(self.rows)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dsqa", type=float, help="DeepSearchQA F1 with search (0-100)")
    ap.add_argument("--hle", type=float, help="HLE accuracy with search (0-100)")
    ap.add_argument("--wiser", type=float, help="override the WISER prediction (e.g. a measured value)")
    ap.add_argument("--cost-per-1k", type=float, help="$ per 1,000 tasks, to place on the efficiency board")
    ap.add_argument("--label", default="model")
    ap.add_argument("--model", help="print a board row by (case-insensitive substring of) model name")
    ap.add_argument("--check", action="store_true", help="leave-one-out accuracy over the published board")
    args = ap.parse_args()

    rows = load()
    pj = Projector(rows)

    if args.model:
        hits = [r for r in rows if args.model.lower() in r["model"].lower()]
        if not hits:
            sys.exit(f"no board row matches {args.model!r}")
        print("| Model | Score | w/o search | Lift | $/1K | s/task | DSQA | HLE | WISER | fit WISER | resid |")
        print("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in hits:
            fp = pj.wiser(r["dsqa"], r["hle"])
            print(f"| {r['model']} | {r['score']:.1f} | {r['score_nosearch']:.1f} | +{r['lift']:.1f} | ${r['cost_per_1k']:.0f} "
                  f"| {r['time_s']:.0f} | {r['dsqa']:.1f} | {r['hle']:.1f} | {r['wiser']:.1f} | {fp:.1f} | {r['wiser']-fp:+.1f} |")
        return

    if args.check:
        l = pj.loo
        print(f"WISER ~ {pj.w[0]:.2f} + {pj.w[1]:.3f}·DSQA + {pj.w[2]:.3f}·HLE (with search), leave-one-out over {len(rows)} rows:\n")
        print("| Model | WISER | predicted | err | score | score if WISER predicted |")
        print("|---|---|---|---|---|---|")
        for o in sorted(l["rows"], key=lambda o: -o["score"]):
            print(f"| {o['model']} | {o['wiser']:.0f} | {o['wiser_pred']:.1f} | {o['err']:+.1f} | {o['score']:.1f} | {o['score_pred']:.1f} |")
        print(f"\nWISER: MAE {l['wiser_mae']:.1f}  RMSE {l['wiser_rmse']:.1f}  max {l['wiser_max']:.1f} points "
              f"→ Search Intelligence Score MAE {l['wiser_mae']/3:.1f}, worst {l['wiser_max']/3:.1f}")
        return

    if args.dsqa is None or args.hle is None:
        sys.exit("need --dsqa and --hle (with-search numbers), or --model / --check")
    est = pj.project(args.dsqa, args.hle, args.wiser)
    print(f"Parallel Search Intelligence projection — {args.label}\n")
    print("| Suite | value | source |")
    print("|---|---|---|")
    print(f"| DSQA (F1, with search) | {args.dsqa:.1f} | given |")
    print(f"| HLE (acc, with search) | {args.hle:.1f} | given |")
    print(f"| WISER (closed) | {est['wiser_pred']:.1f} | {'given' if args.wiser is not None else 'predicted from DSQA+HLE (board fit)'} |")
    print(f"\n**Search Intelligence Score ≈ {est['score']:.1f}**  (±{est['err_typical']:.1f} typical, ±{est['err_max']:.1f} worst-case "
          f"from leave-one-out; Pareto rows on the board missed the fit by −6 and +13 WISER points, i.e. ∓2 / ±4 on the score)  "
          f"→ would rank #{est['rank']} of {est['rank_of']} on the 2026-10-05 board")
    if args.cost_per_1k is not None:
        elig = [r for r in rows if r["score"] >= MEDIAN_EFFICIENCY_CUTOFF]
        cheaper = sum(1 for r in elig if r["cost_per_1k"] < args.cost_per_1k)
        dom = [r["model"] for r in rows if r["cost_per_1k"] <= args.cost_per_1k and r["score"] >= est["score"]]
        print(f"**$/1K tasks {args.cost_per_1k:.0f}** → "
              + (f"#{cheaper+1} of {len(elig)+1} on the Search Efficiency board (score ≥ {MEDIAN_EFFICIENCY_CUTOFF}); "
                 if est["score"] >= MEDIAN_EFFICIENCY_CUTOFF else "below the efficiency-board cutoff; ")
              + ("on the Pareto frontier (nothing cheaper scores higher)" if not dom else f"dominated by: {', '.join(dom)}"))


if __name__ == "__main__":
    main()
