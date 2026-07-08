"""HMMT Feb 2026 — hard competition math (the AIME replacement; public/self-runnable).

Dataset: a JSON list [{id, problem, answer}]. A good public source is the MathArena
HMMT-Feb-2026 set (download to datasets/hmmt_2026.json). Model reasons then boxes a
final answer; we extract \\boxed{} and grade by normalized equality.

CAVEAT: string-normalized equality is fine for integer/simple answers (most of HMMT) but
brittle for symbolic ones. For the real run, wire a sympy-equivalence or LLM-judge grader
(hook: `grade`). FrontierMath is the stronger frontier-math target but is GATED (Epoch AI
holds problems out) — not self-runnable/publishable, so HMMT is our headline math bench.
"""
from __future__ import annotations

import json
import os
import re

from model import model_complete
from harness import run_benchmark

DATA = os.environ.get("HMMT2026_FILE", "datasets/hmmt_2026.json")


def load_items() -> list[dict]:
    return json.load(open(DATA))


def _prompt(it: dict) -> str:
    return ("Solve this competition math problem. Show concise reasoning, then give the final answer "
            f"on the last line as \\boxed{{...}}.\n\nProblem:\n{it['problem']}")


def _extract(text: str | None):
    """Return the content of the LAST \\boxed{...}, brace-balanced (handles \\frac{a}{b})."""
    if not text:
        return None
    idx = text.rfind("\\boxed")
    if idx != -1:
        i = text.find("{", idx)
        if i != -1:
            depth = 0
            for j in range(i, len(text)):
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        return text[i + 1:j].strip()
    nums = re.findall(r"-?\d+(?:/\d+)?", text)
    return nums[-1] if nums else None


def _norm(s) -> str:
    """Best-effort LaTeX-ish normalizer. NOTE: not true math equivalence — for the real
    run, replace `grade` with a sympy-equivalence or LLM-judge grader (e.g. math-verify)."""
    s = str(s)
    s = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(\1)/(\2)", s)
    s = re.sub(r"\\d?frac", "", s)
    for tok in ("\\left", "\\right", "\\,", "\\!", "\\ ", "$", "\\displaystyle"):
        s = s.replace(tok, "")
    return re.sub(r"\s+", "", s).strip().rstrip(".").lower()


def solve(it: dict):
    content, meta = model_complete(
        [{"role": "user", "content": _prompt(it)}],
        max_tokens=int(os.environ.get("HMMT_MAXTOK", "16000")),
    )
    return _extract(content), meta


def grade(it: dict, pred) -> bool:
    return pred is not None and _norm(pred) == _norm(it["answer"])


def main():
    run_benchmark("hmmt_2026", load_items(), solve, grade,
                  concurrency=int(os.environ.get("CONC", "4")),
                  cost_log=os.environ.get("ATXP_MODEL_COST_LOG"))


if __name__ == "__main__":
    main()
