"""ArXivMath (MathArena, arXiv-derived, contamination-resistant). Final-answer, \\boxed{}."""
from __future__ import annotations
import json, os
from model import model_complete
from harness import run_benchmark
from benchmarks.hmmt_2026 import _extract, grade  # reuse the fixed math-verify+numeric grader

DATA = os.environ.get("ARXIV_FILE", "datasets/arxivmath_0526.json")
INSTR = ("You are given a difficult question. Your task is to solve the problem.\n"
         "Put the final answer you find within \\boxed{}.")

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

def main():
    run_benchmark("arxiv_math", load_items(), solve, grade,
                  concurrency=int(os.environ.get("CONC", "4")),
                  cost_log=os.environ.get("ATXP_MODEL_COST_LOG"))

if __name__ == "__main__":
    main()
