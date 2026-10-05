"""Download pinned GPQA Diamond and prepare the runner's multiple-choice JSONL.

Requires access to Idavidrein/gpqa and HF_TOKEN or a cached Hugging Face login.
"""
import csv
import json
import os
from pathlib import Path
import random
import tempfile

from huggingface_hub import hf_hub_download

REPO = "Idavidrein/gpqa"
REVISION = "83022cefff930aea54f654c0b282e74b9eeda5c6"
OUT = Path(__file__).parent / "gpqa_diamond.jsonl"
SEED = 0


def prepare(rows: list[dict]) -> list[dict]:
    items = []
    seen = set()
    for row in rows:
        required = ("Record ID", "Question", "Correct Answer", "Incorrect Answer 1",
                    "Incorrect Answer 2", "Incorrect Answer 3")
        if any(not isinstance(row.get(key), str) or not row[key].strip() for key in required):
            raise ValueError("GPQA row has missing or empty required fields")
        item_id = row["Record ID"].strip()
        if item_id in seen:
            raise ValueError(f"Duplicate GPQA ID: {item_id}")
        seen.add(item_id)
        answers = [row["Correct Answer"], *(row[f"Incorrect Answer {number}"] for number in range(1, 4))]
        order = list(range(4))
        random.Random(f"{SEED}:{item_id}").shuffle(order)
        choices = "\n".join(f"{label}. {answers[index].strip()}" for label, index in zip("ABCD", order))
        items.append({"id": item_id, "problem": f"{row['Question'].strip()}\n\n{choices}",
                      "answer": "ABCD"[order.index(0)]})
    if len(items) != 198:
        raise ValueError(f"Expected 198 GPQA Diamond rows, got {len(items)}")
    return items


def main():
    source = hf_hub_download(REPO, "gpqa_diamond.csv", repo_type="dataset",
                             revision=REVISION, token=os.environ.get("HF_TOKEN"))
    with open(source, encoding="utf-8-sig", newline="") as handle:
        items = prepare(list(csv.DictReader(handle)))
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=OUT.parent,
                                         prefix=f".{OUT.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            for item in items:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
        temporary.replace(OUT)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(f"wrote {len(items)} GPQA Diamond items -> {OUT} (revision {REVISION}, seed {SEED})")


if __name__ == "__main__":
    main()
