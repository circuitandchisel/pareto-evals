"""Humanity's Last Exam — TEXT-ONLY track (the frontier knowledge/reasoning bench).

Scope decision (see repo README): we run the Scale-style TEXT-ONLY track — text-only
questions (~86% of HLE), all public questions, temperature 0 — and compare ONLY to the
Scale text-only leaderboard's numbers for other models, NOT vendors' full/headline HLE
figures (HLE is methodology-fragile; the same model swings 20+ points by harness/judge/tools).

Two configs:
  MODE=no_tools  (default): closed-book, single completion.
  MODE=tools               : agentic loop with web search — SCAFFOLDED below (needs tool wiring).

Grading: HLE answers are free-form → the official protocol uses an LLM JUDGE. That judge
must be an INDEPENDENT model (not our RC). Configure it via JUDGE_BASE_URL/JUDGE_MODEL/
JUDGE_API_KEY; if unset we fall back to normalized containment match and print a WARNING
(not valid for a published number).
"""
from __future__ import annotations

import json
import os

from openai import OpenAI

from model import model_complete
from harness import run_benchmark

DATA = os.environ.get("HLE_FILE", "datasets/hle_text_only.json")  # [{id, question, answer}]
MODE = os.environ.get("HLE_MODE", "no_tools")

_JUDGE = None
if os.environ.get("JUDGE_BASE_URL"):
    _JUDGE = OpenAI(base_url=os.environ["JUDGE_BASE_URL"], api_key=os.environ.get("JUDGE_API_KEY", "dummy"), timeout=float(os.environ.get("JUDGE_TIMEOUT", "90")), max_retries=2)


def load_items() -> list[dict]:
    return json.load(open(DATA))


def _prompt(it: dict) -> str:
    return (f"{it['question']}\n\nThink step by step, then end with your final answer on the last line as: "
            f"ANSWER: <answer>")


def solve(it: dict):
    if MODE == "tools":
        raise NotImplementedError(
            "HLE with-tools: agentic search loop not yet wired. Plan: give the model web_search/"
            "web_fetch tools via model_complete(tools=...), run a bounded tool loop, then answer.")
    content, meta = model_complete([{"role": "user", "content": _prompt(it)}])
    pred = None
    if content and "ANSWER:" in content:
        pred = content.rsplit("ANSWER:", 1)[1].strip()
    else:
        pred = (content or "").strip()[-300:]
    return pred, meta


def grade(it: dict, pred) -> bool:
    ref = str(it["answer"]).strip()
    if _JUDGE is not None:
        judge_model = os.environ.get("JUDGE_MODEL", "gpt-5.5")
        # NOTE: reasoning judges (gpt-5.5) reject a tiny max_tokens — they need room
        # for reasoning tokens, so max_tokens=5 -> 400 "max_output_tokens below minimum"
        # and every grade errors. 4000 gives reasoning room; the final answer is YES/NO.
        try:
            r = _JUDGE.chat.completions.create(
                model=judge_model, temperature=0, max_tokens=4000,
                messages=[{"role": "user", "content":
                           f"Question: {it['question']}\nReference answer: {ref}\nCandidate answer: {pred}\n"
                           f"Is the candidate correct? Reply only YES or NO."}])
            verdict = (r.choices[0].message.content or "").strip().upper()
            return verdict.startswith("YES") or verdict.endswith("YES")
        except Exception as e:
            print(f"WARNING: judge failed ({type(e).__name__}: {e}); containment fallback for this item")
            return ref.lower() in str(pred).lower() or str(pred).lower() in ref.lower()
    # fallback (NOT publishable)
    print("WARNING: no JUDGE configured — using normalized containment match (not valid for publication)")
    return ref.lower() in str(pred).lower() or str(pred).lower() in ref.lower()


def main():
    run_benchmark(os.environ.get("RESULT_NAME") or f"hle_text_{MODE}", load_items(), solve, grade,
                  concurrency=int(os.environ.get("CONC", "4")),
                  cost_log=os.environ.get("MODEL_COST_LOG"))


if __name__ == "__main__":
    main()
