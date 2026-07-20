"""ArXivMath (MathArena, arXiv-derived, contamination-resistant). Final-answer, \\boxed{}.

Grading: the strict symbolic/numeric matcher (from hmmt_2026) is the FLOOR — a match is
definitely correct (no false positives). But it UNDERCOUNTS badly on equivalent-but-
differently-formatted answers (measured: Opus 12.5% symbolic vs 42.5% judge). So on a
symbolic MISS we ask an INDEPENDENT LLM judge (gpt-5.5) whether the candidate is
mathematically equivalent to the reference. correct = symbolic OR judge. The judge is only
called on misses (cheap) and must NOT be our RC (set JUDGE_BASE_URL/JUDGE_MODEL). Without a
judge configured it falls back to symbolic-only and prints a warning (not the headline).
"""
from __future__ import annotations
import json, os
from model import model_complete
from harness import run_benchmark
from benchmarks.hmmt_2026 import _extract, grade as symbolic_grade  # strict math-verify+numeric
from openai import OpenAI

DATA = os.environ.get("ARXIV_FILE", "datasets/arxivmath_0526.json")
INSTR = ("You are given a difficult question. Your task is to solve the problem.\n"
         "Put the final answer you find within \\boxed{}.")

_JUDGE = None
if os.environ.get("JUDGE_BASE_URL"):
    _JUDGE = OpenAI(base_url=os.environ["JUDGE_BASE_URL"], api_key=os.environ.get("JUDGE_API_KEY", "dummy"),
                    timeout=float(os.environ.get("JUDGE_TIMEOUT", "90")), max_retries=2)


def load_items() -> list[dict]:
    return json.load(open(DATA))


def _prompt(it: dict) -> str:
    return INSTR + "\n\nProblem:\n" + it["problem"]


def solve(it: dict):
    content, meta = model_complete(
        [{"role": "user", "content": _prompt(it)}],
        max_tokens=int(os.environ.get("ARXIV_MAXTOK", "40000")),
    )
    return _extract(content), meta


def grade(it: dict, pred) -> bool:
    # Strict symbolic/numeric match is the floor — a match is definitely correct.
    if symbolic_grade(it, pred):
        return True
    # Symbolic missed: ask the independent judge for mathematical equivalence (formatting-agnostic).
    if _JUDGE is None:
        print("WARNING: no JUDGE configured — symbolic-only grade (undercounts; not the headline number)")
        return False
    judge_model = os.environ.get("JUDGE_MODEL", "gpt-5.5")
    try:
        r = _JUDGE.chat.completions.create(
            model=judge_model, temperature=0, max_tokens=4000,
            messages=[{"role": "user", "content":
                       f"Problem:\n{it['problem']}\n\nReference final answer: {it['answer']}\n"
                       f"Candidate final answer: {pred}\n\n"
                       "Is the candidate's final answer mathematically equivalent to the reference "
                       "(same value/set/expression, ignoring formatting, ordering, and notation)? "
                       "Reply only YES or NO."}])
        v = (r.choices[0].message.content or "").strip().upper()
        return v.startswith("YES") or v.endswith("YES")
    except Exception as e:  # judge hiccup -> fall back to the symbolic miss (conservative)
        print(f"WARNING: arxiv judge failed ({type(e).__name__}: {e}); symbolic-only for this item")
        return False


def main():
    run_benchmark(os.environ.get("RESULT_NAME") or "arxiv_math", load_items(), solve, grade,
                  concurrency=int(os.environ.get("CONC", "4")),
                  cost_log=os.environ.get("MODEL_COST_LOG"))


if __name__ == "__main__":
    main()
