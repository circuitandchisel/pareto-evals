"""Download pinned MathArena ArXivMath May 2026; no arXiv bulk access needed."""
import json
import os
from pathlib import Path
import tempfile

from datasets import load_dataset

REPO = "MathArena/arxivmath-0526"
REVISION = "69f701c7f266bfba235ef302ff9b19093f7455bb"
OUT = Path(__file__).parent / "arxivmath_0526.json"


def prepare(rows) -> list[dict]:
    items = []
    seen = set()
    for row in rows:
        if row.get("problem_idx") is None:
            raise ValueError("ArXivMath row has no problem_idx")
        if any(not isinstance(row.get(key), str) or not row[key].strip() for key in ("problem", "answer")):
            raise ValueError("ArXivMath row has a missing or empty problem/answer")
        item_id = str(row["problem_idx"]).strip()
        if not item_id:
            raise ValueError("ArXivMath row has an empty problem_idx")
        if item_id in seen:
            raise ValueError(f"Duplicate ArXivMath ID: {item_id}")
        seen.add(item_id)
        items.append({"id": item_id, "problem": row["problem"], "answer": row["answer"],
                      **{key: row[key] for key in ("source", "title", "authors") if key in row}})
    if len(items) != 40:
        raise ValueError(f"Expected 40 ArXivMath May 2026 rows, got {len(items)}")
    return items


def main():
    rows = load_dataset(REPO, split="train", revision=REVISION, token=os.environ.get("HF_TOKEN"))
    items = prepare(rows)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=OUT.parent,
                                         prefix=f".{OUT.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(items, handle, ensure_ascii=False)
        temporary.replace(OUT)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(f"wrote {len(items)} ArXivMath items -> {OUT} (revision {REVISION})")


if __name__ == "__main__":
    main()
