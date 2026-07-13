"""ARC-AGI-2 — fluid-reasoning / abstraction (the GPQA replacement).

Public eval tasks are JSON files (ARC-Prize `ARC-AGI-2` repo, data/evaluation/*.json),
each {"train":[{input,output}], "test":[{input,output}]} of 2-D integer grids. We give
the model the train pairs + the test input and ask for the output grid; exact-match grade.

NOTE: official ARC-AGI-2 scoring allows 2 attempts (pass@2). This runner does 1 attempt;
add a second sample + OR the grades for official comparability (TODO).
"""
from __future__ import annotations

import glob
import json
import os
import re

from model import model_complete
from harness import run_benchmark

DATA_DIR = os.environ.get("ARC_AGI2_DIR", "datasets/arc-agi-2/evaluation")


def load_items() -> list[dict]:
    items = []
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "*.json"))):
        task = json.load(open(path))
        base = os.path.basename(path)[:-5]
        for i, test in enumerate(task["test"]):
            items.append({"id": f"{base}#{i}", "train": task["train"],
                          "input": test["input"], "answer": test.get("output")})
    return items


def _grid(g) -> str:
    return "\n".join(" ".join(str(c) for c in row) for row in g)


def _prompt(it: dict) -> str:
    ex = "\n\n".join(
        f"Example {k+1}:\nINPUT:\n{_grid(p['input'])}\nOUTPUT:\n{_grid(p['output'])}"
        for k, p in enumerate(it["train"])
    )
    return ("You are solving an ARC-AGI abstract reasoning puzzle. Infer the single transformation "
            "rule from the examples, then produce the OUTPUT grid for the final input. Reply with ONLY "
            "the output grid as rows of space-separated integers — no prose.\n\n"
            f"{ex}\n\nFINAL INPUT:\n{_grid(it['input'])}\n\nOUTPUT:")


def _parse(text: str | None):
    if not text:
        return None
    rows = []
    for line in text.strip().splitlines():
        nums = re.findall(r"-?\d+", line)
        if nums:
            rows.append([int(x) for x in nums])
    return rows or None


def solve(it: dict):
    content, meta = model_complete([{"role": "user", "content": _prompt(it)}])
    return _parse(content), meta


def grade(it: dict, pred) -> bool:
    return pred is not None and it.get("answer") is not None and pred == it["answer"]


def main():
    run_benchmark("arc_agi_2", load_items(), solve, grade,
                  concurrency=int(os.environ.get("CONC", "4")),
                  cost_log=os.environ.get("PARETO_MODEL_COST_LOG"))


if __name__ == "__main__":
    main()
