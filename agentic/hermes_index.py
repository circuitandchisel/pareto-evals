#!/usr/bin/env python3
"""Hermes Index estimator — score the three OPEN Hermes Index suites you ran through
the Hermes Agent harness and extrapolate the full index (score + $/task).

Background. Nous Research's Hermes Index (2026-10-06, https://portal.nousresearch.com/bench)
is the plain mean of four suites, every run inside the Hermes Agent harness at pass@1 with
reasoning effort "high" where the model offers it, and its $/task is the plain mean of
the four suites' $/task:

    index = (HermesBench + TB4 + TBScience + SkillsBench) / 4
    cost  = (HB_cost    + TB4_cost + TBSci_cost + Skills_cost) / 4

Three of the four suites are open and runnable here (../agentic/run_hermes_index.sh):

    tb4     Terminal-Bench 4.0 minus its GPU tasks (63 tasks)   run_tb.sh  TB_AGENT=hermes
    tbsci   Terminal-Bench-Science 0.1 (70 tasks)                run_tb_science.sh
    skills  SkillsBench, "clean" score (87 tasks minus leaked)   run_skillsbench.sh

Hermes Bench (150 tasks) is Nous-internal, so it is *predicted* from the open suites using
the published leaderboard (hermes_index/leaderboard_2026-10-06.csv): an ordinary-least-
squares fit of HB on the SkillsBench and TB4 scores (HB varies far less than the open
suites — 54..77 vs 0..70 — and tracks SkillsBench most closely), and a log-linear fit of
HB $/task on the SkillsBench and TB4 $/task. Leave-one-out error on the 14 launch rows is
printed with every estimate so the extrapolation is never reported as a measurement:
roughly ±1 index point typical (worst ≈2.5) and ±2% on $/task.

Usage
-----
    # from harbor output dirs (what run_hermes_index.sh calls):
    python3 agentic/hermes_index.py --tb4 OUT/tb4 --tbsci OUT/tbsci --skills OUT/skills \
        --in-price 3 --out-price 15 [--cache-price 0.3] [--json OUT/hermes_index.json]

    # what-if from numbers you already have (scores in %, costs in $/task):
    python3 agentic/hermes_index.py --scores tb4=54,tbsci=52.9,skills=69.6 \
        --costs tb4=6.27,tbsci=12.65,skills=0.51

    # how good is the extrapolation? leave-one-out over the published leaderboard:
    python3 agentic/hermes_index.py --check

Per-trial cost = harbor's `agent_result.cost_usd` when the agent reported one, else
tokens × --in-price/--out-price (per 1M; env MODEL_INPUT_PRICE_PER_MTOK /
MODEL_OUTPUT_PRICE_PER_MTOK / MODEL_CACHE_PRICE_PER_MTOK are the fallbacks; cached
input tokens are billed at the cache price when given), else Hermes's own list-price
estimate from its session record (`metadata.hermes_session.estimated_cost_usd`). With
--usage-log NAME=path (a strip_proxy.py USAGE_LOG), that suite's $/task is instead the
log's summed inline `cost` / tasks — the authoritative number for endpoints that bill
inline (Pareto).

SkillsBench "clean" score: Nous drops tasks where the agent found the public SkillsBench
repo and used its oracle solutions. We flag a trial as leaked when its agent transcript
mentions the repo / dataset / site (see LEAK_RE) and report both the raw and the clean
score; the clean one feeds the index. Review the flagged trials — the regex is a net.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEADERBOARD = HERE / "hermes_index" / "leaderboard_2026-10-06.csv"

OPEN = ("tb4", "tbsci", "skills")
SUITES = {
    "hb":     {"label": "Hermes Bench (closed; predicted)", "n": 150},
    "tb4":    {"label": "Terminal-Bench 4.0 (no GPU tasks)", "n": 63},
    "tbsci":  {"label": "Terminal-Bench-Science 0.1", "n": 70},
    "skills": {"label": "SkillsBench (clean)", "n": 87},
}
# Default extrapolation features (see module docstring / --check for alternatives).
HB_SCORE_FEATURES = ("skills", "tb4")
HB_COST_FEATURES = ("skills", "tb4")

# Agent transcript evidence that the trial looked at the public SkillsBench sources.
LEAK_RE = re.compile(
    r"github\.com/benchflow-ai|benchflow-ai/skillsbench|huggingface\.co/(?:datasets/)?benchflow"
    r"|skillsbench\.ai|\bskillsbench\b",
    re.I,
)
# Files under a trial dir that hold the agent's own transcript (not the task files).
TRANSCRIPT_GLOBS = ("agent/*.txt", "agent/*.jsonl", "agent/trajectory.json", "agent/**/*.json")


# ───────────────────────────────────────────── leaderboard + fit ──
def load_leaderboard(path: Path = LEADERBOARD) -> list[dict]:
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(l for l in f if not l.startswith("#")):
            row = {"model": r["model"], "org": r["org"], "provisional": r.get("provisional", "")}
            for k, v in r.items():
                if k not in row:
                    try:
                        row[k] = float(v)
                    except (TypeError, ValueError):
                        row[k] = None
            rows.append(row)
    return rows


def _ols(X: list[list[float]], y: list[float]) -> list[float]:
    """Least squares via normal equations + Gaussian elimination (no numpy dependency)."""
    n = len(X[0])
    A = [[sum(X[i][a] * X[i][b] for i in range(len(X))) for b in range(n)] for a in range(n)]
    b = [sum(X[i][a] * y[i] for i in range(len(X))) for a in range(n)]
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        if abs(M[c][c]) < 1e-12:
            raise ValueError("singular design matrix")
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                M[r] = [M[r][k] - f * M[c][k] for k in range(n + 1)]
    return [M[i][n] / M[i][i] for i in range(n)]


def _score_feats(scores: dict, feats: tuple[str, ...]) -> list[float]:
    if feats == ("mean3",):
        return [1.0, sum(scores[k] for k in OPEN) / 3]
    return [1.0] + [scores[k] for k in feats]


def _cost_feats(costs: dict, feats: tuple[str, ...]) -> list[float]:
    if feats == ("mean3",):
        return [1.0, math.log(sum(costs[k] for k in OPEN) / 3)]
    return [1.0] + [math.log(max(costs[k], 1e-6)) for k in feats]


class Extrapolator:
    """HB score / HB $/task predicted from the open suites, with leave-one-out error."""

    def __init__(self, rows: list[dict], score_feats=HB_SCORE_FEATURES, cost_feats=HB_COST_FEATURES):
        self.rows = rows
        self.score_feats, self.cost_feats = tuple(score_feats), tuple(cost_feats)
        self.w_score = _ols([_score_feats(r, self.score_feats) for r in rows], [r["hb"] for r in rows])
        self.w_cost = _ols([_cost_feats({k: r[f"{k}_cost"] for k in OPEN}, self.cost_feats) for r in rows],
                           [math.log(r["hb_cost"]) for r in rows])
        self.hb_min = min(r["hb"] for r in rows)
        self.hb_max = max(r["hb"] for r in rows)  # cap for hb_score(); must be set before _loo()
        self.loo = self._loo()

    def hb_score(self, scores: dict, w=None) -> float:
        """Linear prediction, capped at the best Hermes Bench score on the board: HB saturates
        (the top five models sit within 73–77) so extrapolating above it is not credible."""
        w = w or self.w_score
        v = sum(a * b for a, b in zip(w, _score_feats(scores, self.score_feats)))
        return max(0.0, min(self.hb_max, v))

    def hb_cost(self, costs: dict, w=None) -> float:
        w = w or self.w_cost
        return math.exp(sum(a * b for a, b in zip(w, _cost_feats(costs, self.cost_feats))))

    def _loo(self) -> dict:
        """Leave-one-out: refit without each leaderboard row and predict it."""
        out = []
        for i, r in enumerate(self.rows):
            tr = [x for j, x in enumerate(self.rows) if j != i]
            ws = _ols([_score_feats(x, self.score_feats) for x in tr], [x["hb"] for x in tr])
            wc = _ols([_cost_feats({k: x[f"{k}_cost"] for k in OPEN}, self.cost_feats) for x in tr],
                      [math.log(x["hb_cost"]) for x in tr])
            scores = {k: r[k] for k in OPEN}
            costs = {k: r[f"{k}_cost"] for k in OPEN}
            hb = self.hb_score(scores, ws)
            hbc = self.hb_cost(costs, wc)
            idx = (hb + sum(scores.values())) / 4
            cost = (hbc + sum(costs.values())) / 4
            out.append({"model": r["model"], "index": r["index"], "index_pred": idx,
                        "index_err": idx - r["index"], "hb": r["hb"], "hb_pred": hb,
                        "cost": r["cost"], "cost_pred": cost, "cost_ratio": cost / r["cost"]})
        errs = [abs(o["index_err"]) for o in out]
        ratios = [o["cost_ratio"] for o in out]
        return {"rows": out,
                "index_mae": sum(errs) / len(errs),
                "index_rmse": math.sqrt(sum(e * e for e in errs) / len(errs)),
                "index_max": max(errs),
                "cost_ratio_min": min(ratios), "cost_ratio_max": max(ratios)}

    def estimate(self, scores: dict, costs: dict | None) -> dict:
        hb = self.hb_score(scores)
        index = (hb + sum(scores[k] for k in OPEN)) / 4
        est = {
            "hb_pred": hb,
            "index": index,
            # typical / worst-case error from leave-one-out on the published rows
            "index_err_typical": self.loo["index_mae"],
            "index_err_max": self.loo["index_max"],
            # hard bounds: HB can only be as low/high as any model on the launch board
            "index_lo": (self.hb_min + sum(scores[k] for k in OPEN)) / 4,
            "index_hi": (self.hb_max + sum(scores[k] for k in OPEN)) / 4,
            "rank": 1 + sum(1 for r in self.rows if r["index"] > index),
            "rank_of": len(self.rows),
        }
        if costs and all(costs.get(k) is not None for k in OPEN):
            hbc = self.hb_cost(costs)
            cost = (hbc + sum(costs[k] for k in OPEN)) / 4
            est.update({
                "hb_cost_pred": hbc,
                "cost": cost,
                "cost_lo": cost * self.loo["cost_ratio_min"],
                "cost_hi": cost * self.loo["cost_ratio_max"],
            })
        return est


# ───────────────────────────────────────────── harbor output scanning ──
def _price(n_in, n_out, n_cache, in_p, out_p, cache_p):
    if in_p is None or out_p is None:
        return None
    n_in, n_out, n_cache = n_in or 0, n_out or 0, n_cache or 0
    if cache_p is not None and n_cache:
        return (max(n_in - n_cache, 0) * in_p + n_cache * cache_p + n_out * out_p) / 1e6
    return (n_in * in_p + n_out * out_p) / 1e6


def _is_leaked(trial_dir: Path) -> bool:
    for g in TRANSCRIPT_GLOBS:
        for p in trial_dir.glob(g):
            if not p.is_file():
                continue
            try:
                if LEAK_RE.search(p.read_text(errors="replace")):
                    return True
            except OSError:
                continue
    return False


def scan_job(root: Path, in_p=None, out_p=None, cache_p=None, leak_scan=False) -> list[dict]:
    """One row per harbor trial under `root` (any depth): task, reward, tokens, cost, leak flag."""
    trials = []
    for rj in sorted(root.rglob("result.json")):
        try:
            d = json.loads(rj.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(d, dict) or "task_name" not in d:
            continue
        vr = d.get("verifier_result") or {}
        reward = (vr.get("rewards") or {}).get("reward")
        ar = d.get("agent_result") or {}
        exc = d.get("exception_info")
        cost = ar.get("cost_usd")
        cost_src = "agent cost_usd" if cost is not None else None
        if cost is None:
            cost = _price(ar.get("n_input_tokens"), ar.get("n_output_tokens"), ar.get("n_cache_tokens"),
                          in_p, out_p, cache_p)
            cost_src = "tokens x price" if cost is not None else None
        if cost is None:
            # Hermes's own list-price estimate (session record), kept by the adapter in metadata.
            hs = (ar.get("metadata") or {}).get("hermes_session") or {}
            est = hs.get("estimated_cost_usd")
            if isinstance(est, (int, float)):
                cost, cost_src = float(est), "hermes estimate"
        trials.append({
            "task": d["task_name"].split("/")[-1],
            "trial": rj.parent.name,
            "reward": float(reward) if reward is not None else None,
            "error": (exc or {}).get("exception_type") if exc else None,
            "n_input_tokens": ar.get("n_input_tokens"),
            "n_output_tokens": ar.get("n_output_tokens"),
            "n_cache_tokens": ar.get("n_cache_tokens"),
            "cost_usd": cost,
            "cost_source": cost_src,
            "leaked": _is_leaked(rj.parent) if leak_scan else False,
        })
    return trials


def summarize(trials: list[dict], usage_log: Path | None = None) -> dict:
    """Score = mean over tasks of mean trial reward (errored/unscored trials count 0, as on the
    leaderboard). $/task = mean trial cost (or usage-log total / tasks)."""
    by_task: dict[str, list[dict]] = {}
    for t in trials:
        by_task.setdefault(t["task"], []).append(t)

    def task_score(ts):
        return sum((t["reward"] or 0.0) for t in ts) / len(ts)

    n = len(by_task)
    raw = 100 * sum(task_score(ts) for ts in by_task.values()) / n if n else None
    leaked = sorted(k for k, ts in by_task.items() if any(t["leaked"] for t in ts))
    clean_tasks = [k for k in by_task if k not in leaked]
    clean = (100 * sum(task_score(by_task[k]) for k in clean_tasks) / len(clean_tasks)
             if clean_tasks else None)
    costs = [t["cost_usd"] for t in trials if t["cost_usd"] is not None]
    cost = sum(costs) / len(costs) if costs else None
    srcs = sorted({t["cost_source"] for t in trials if t.get("cost_source")})
    cost_src = f"{'/'.join(srcs)} ({len(costs)}/{len(trials)} trials priced)" if costs else "unpriced"
    if usage_log:
        tot, rows = 0.0, 0
        for line in usage_log.read_text().splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows += 1
            if isinstance(r.get("cost"), (int, float)):
                tot += r["cost"]
        if n:
            cost = tot / n
            cost_src = f"usage log ({rows} requests, ${tot:.2f} total / {n} tasks)"
    errored = sum(1 for t in trials if t["error"])
    return {"n_tasks": n, "n_trials": len(trials), "errored": errored, "score_raw": raw,
            "leaked_tasks": leaked, "n_clean": len(clean_tasks), "score": clean,
            "cost_per_task": cost, "cost_source": cost_src}


# ───────────────────────────────────────────── cli ──
def _kv(arg: str | None) -> dict[str, str]:
    out = {}
    for part in (arg or "").split(","):
        if part.strip():
            k, _, v = part.partition("=")
            out[k.strip()] = v.strip()
    return out


def _fmt(v, f="{:.1f}", dash="—"):
    return f.format(v) if isinstance(v, (int, float)) else dash


def _env_price(name):
    v = os.environ.get(name)
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k in OPEN:
        ap.add_argument(f"--{k}", metavar="DIR", help=f"harbor output dir of the {SUITES[k]['label']} run")
    ap.add_argument("--scores", help="manual scores in %%: tb4=54,tbsci=52.9,skills=69.6 (dirs override)")
    ap.add_argument("--costs", help="manual $/task: tb4=6.27,tbsci=12.65,skills=0.51")
    ap.add_argument("--usage-log", help="NAME=path[,NAME=path] strip_proxy USAGE_LOG per suite (inline-cost $/task)")
    ap.add_argument("--in-price", type=float, default=_env_price("MODEL_INPUT_PRICE_PER_MTOK"), help="$ per 1M input tokens")
    ap.add_argument("--out-price", type=float, default=_env_price("MODEL_OUTPUT_PRICE_PER_MTOK"), help="$ per 1M output tokens")
    ap.add_argument("--cache-price", type=float, default=_env_price("MODEL_CACHE_PRICE_PER_MTOK"), help="$ per 1M cached input tokens (optional)")
    ap.add_argument("--no-leak-scan", action="store_true", help="skip the SkillsBench transcript scan (clean == raw)")
    ap.add_argument("--hb-features", default=",".join(HB_SCORE_FEATURES), help="HB score predictors: skills,tb4 | skills | tb4,tbsci,skills | mean3")
    ap.add_argument("--hb-cost-features", default=",".join(HB_COST_FEATURES), help="HB $/task predictors (log-linear), same choices")
    ap.add_argument("--label", default=os.environ.get("MODEL_NAME", "model"), help="row label")
    ap.add_argument("--json", metavar="PATH", help="also write the full result as JSON")
    ap.add_argument("--summary", action="store_true", help="only summarize the given suite dir(s) (score, clean score, $/task); no index")
    ap.add_argument("--summary-if-partial", action="store_true", help="like --summary when not all three suites are available, else the full estimate")
    ap.add_argument("--check", action="store_true", help="print leave-one-out accuracy over the published leaderboard and exit")
    args = ap.parse_args()

    rows = load_leaderboard()
    ex = Extrapolator(rows, tuple(args.hb_features.split(",")), tuple(args.hb_cost_features.split(",")))

    if args.check:
        print(f"Leave-one-out over the {len(rows)} published rows "
              f"(HB score ~ {'+'.join(ex.score_feats)}; HB $/task ~ log {'+'.join(ex.cost_feats)}):\n")
        print("| Model | index | predicted | err | $/task | predicted | ratio |")
        print("|---|---|---|---|---|---|---|")
        for o in ex.loo["rows"]:
            print(f"| {o['model']} | {o['index']:.2f} | {o['index_pred']:.2f} | {o['index_err']:+.2f} "
                  f"| ${o['cost']:.3f} | ${o['cost_pred']:.3f} | {o['cost_ratio']:.3f} |")
        l = ex.loo
        print(f"\nindex: MAE {l['index_mae']:.2f}  RMSE {l['index_rmse']:.2f}  max {l['index_max']:.2f} points; "
              f"$/task ratio range {l['cost_ratio_min']:.3f}–{l['cost_ratio_max']:.3f}")
        return

    scores = {k: float(v) for k, v in _kv(args.scores).items()}
    costs = {k: float(v) for k, v in _kv(args.costs).items()}
    usage_logs = _kv(args.usage_log)
    suites: dict[str, dict] = {}
    for k in OPEN:
        d = getattr(args, k)
        if d:
            root = Path(d)
            if not root.is_dir():
                sys.exit(f"--{k}: {d} is not a directory")
            trials = scan_job(root, args.in_price, args.out_price, args.cache_price,
                              leak_scan=(k == "skills" and not args.no_leak_scan))
            if not trials:
                sys.exit(f"--{k}: no harbor result.json under {d}")
            s = summarize(trials, Path(usage_logs[k]) if k in usage_logs else None)
            s["dir"] = str(root)
            suites[k] = s
            if s["score"] is not None:
                scores[k] = s["score"]
            if s["cost_per_task"] is not None:
                costs[k] = s["cost_per_task"]
            if s["n_tasks"] != SUITES[k]["n"]:
                print(f"NOTE: {k}: {s['n_tasks']} tasks scored, leaderboard uses {SUITES[k]['n']} — "
                      f"partial runs are fine for a smoke test, not for a comparable number.", file=sys.stderr)
    missing = [k for k in OPEN if k not in scores]
    if args.summary or (missing and args.summary_if_partial):
        if not suites:
            sys.exit("--summary needs at least one suite dir (--tb4/--tbsci/--skills)")
        print(f"Suite summary — {args.label}\n")
        print("| Suite | tasks | trials | errored | score | $/task | note |")
        print("|---|---|---|---|---|---|---|")
        for k, s in suites.items():
            note = s["cost_source"]
            if k == "skills":
                note += (f"; raw {s['score_raw']:.1f}%, {len(s['leaked_tasks'])} leaked task(s) dropped: "
                         f"{', '.join(s['leaked_tasks'])}" if s["leaked_tasks"] else "; no leaked trials flagged")
            print(f"| {SUITES[k]['label']} | {s['n_tasks']} | {s['n_trials']} | {s['errored']} "
                  f"| {_fmt(s['score'])}% | {_fmt(s['cost_per_task'], '${:.3f}')} | {note} |")
        if missing:
            print(f"\nNo index estimate: missing {', '.join(missing)}.")
        if args.json:
            Path(args.json).write_text(json.dumps({"label": args.label, "suites": suites}, indent=2) + "\n")
        return
    if missing:
        sys.exit(f"need a score for every open suite; missing: {', '.join(missing)} "
                 f"(pass --<suite> DIR or --scores; --summary for per-suite numbers only)")
    have_costs = all(k in costs for k in OPEN)
    est = ex.estimate(scores, costs if have_costs else None)

    # ── report ──
    print(f"Hermes Index estimate — {args.label}\n")
    print("| Suite | n | score | $/task | note |")
    print("|---|---|---|---|---|")
    for k in OPEN:
        s = suites.get(k)
        if s:
            note = s["cost_source"]
            if s["errored"]:
                note += f"; {s['errored']} errored"
            if k == "skills":
                note += (f"; raw {s['score_raw']:.1f}% on {s['n_tasks']}, "
                         f"{len(s['leaked_tasks'])} leaked dropped" if s["leaked_tasks"]
                         else "; no leaked trials flagged")
            n = f"{s['n_clean']}/{s['n_tasks']}" if k == "skills" and s["leaked_tasks"] else str(s["n_tasks"])
        else:
            note, n = "given", str(SUITES[k]["n"])
        print(f"| {SUITES[k]['label']} | {n} | {_fmt(scores[k])}% | {_fmt(costs.get(k), '${:.3f}')} | {note} |")
    print(f"| {SUITES['hb']['label']} | {SUITES['hb']['n']} | {est['hb_pred']:.1f}% "
          f"| {_fmt(est.get('hb_cost_pred'), '${:.3f}')} | fit on the 2026-10-06 leaderboard |")
    print()
    print(f"**Hermes Index ≈ {est['index']:.1f}**  (±{est['index_err_typical']:.1f} typical, "
          f"±{est['index_err_max']:.1f} worst-case from leave-one-out; "
          f"{est['index_lo']:.1f}–{est['index_hi']:.1f} if Hermes Bench lands anywhere in the board's range)  "
          f"→ would rank #{est['rank']} of {est['rank_of']} on the launch leaderboard")
    if "cost" in est:
        print(f"**$/task ≈ ${est['cost']:.2f}**  (range ${est['cost_lo']:.2f}–${est['cost_hi']:.2f} from leave-one-out)")
    else:
        print("$/task: not estimated — give --costs for all three suites, or prices (--in-price/--out-price) "
              "so harbor token counts can be priced.")
    for k in OPEN:
        s = suites.get(k)
        if s and s["leaked_tasks"]:
            print(f"\nSkillsBench tasks flagged as leaked (transcript mentions the public repo) — review: "
                  f"{', '.join(s['leaked_tasks'])}")
    print("\nExtrapolation: HB score ~ " + " + ".join(ex.score_feats) + "; HB $/task ~ log(" + ", ".join(ex.cost_feats) + ")."
          " The three open suites are measured; Hermes Bench and therefore the index are estimates.")

    if args.json:
        out = {"label": args.label, "scores": scores, "costs": costs, "suites": suites, "estimate": est,
               "fit": {"score_features": ex.score_feats, "cost_features": ex.cost_feats,
                       "w_score": ex.w_score, "w_cost": ex.w_cost, "loo": {k: v for k, v in ex.loo.items() if k != "rows"}},
               "leaderboard": str(LEADERBOARD.name)}
        Path(args.json).write_text(json.dumps(out, indent=2) + "\n")
        print(f"\nWrote {args.json}")


if __name__ == "__main__":
    main()
