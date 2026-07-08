"""Prepare HMMT Feb 2026 -> datasets/hmmt_2026.json  ([{id,problem,answer}]).

MathArena publishes competition sets (AIME/HMMT) on HF. The exact repo id for the Feb-2026
HMMT set may need confirming; we try known candidates and print what worked. If none resolve,
the set needs manual sourcing (drop a JSON list of {problem,answer} at datasets/hmmt_2026.json).
"""
import json
import os

from datasets import load_dataset

OUT = os.path.join(os.path.dirname(__file__), "hmmt_2026.json")
CANDIDATES = [
    ("MathArena/hmmt_feb_2026", "train"),
    ("MathArena/hmmt_feb_2026", "test"),
    ("MathArena/hmmt-feb-2026", "train"),
    ("MathArena/hmmt_2026", "train"),
]
Q = ("problem", "question", "statement")
A = ("answer", "final_answer", "solution")


def _first(ex, fields):
    for f in fields:
        if ex.get(f) is not None:
            return ex[f]
    return None


def main():
    tok = os.environ.get("HF_TOKEN")
    for repo, split in CANDIDATES:
        try:
            ds = load_dataset(repo, split=split, token=tok)
        except Exception as e:
            print(f"{repo}[{split}]: {str(e)[:120]}")
            continue
        print(f"loaded {repo}[{split}] — schema:", list(ds[0].keys()))
        items = [{"id": str(i), "problem": _first(ex, Q), "answer": _first(ex, A)}
                 for i, ex in enumerate(ds)]
        items = [it for it in items if it["problem"] and it["answer"] is not None]
        json.dump(items, open(OUT, "w"))
        print(f"wrote {len(items)} HMMT-2026 items from {repo} -> {OUT}")
        return
    print("No HMMT-2026 source auto-resolved. Provide datasets/hmmt_2026.json manually "
          "([{id,problem,answer}]).")


if __name__ == "__main__":
    main()
