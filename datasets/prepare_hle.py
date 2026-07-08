"""Prepare the HLE TEXT-ONLY subset -> datasets/hle_text_only.json  ([{id,question,answer}]).

Source: HF `cais/hle`. NOTE this dataset is commonly GATED (accept terms + HF token). If it
fails to load, accept at https://huggingface.co/datasets/cais/hle and set HF_TOKEN, then rerun.
Text-only = items with no image attached (the ~86% text subset used by the Scale text-only track).
Field names vary by dataset revision, so we probe defensively and print the row schema.
"""
import json
import os

from datasets import load_dataset

OUT = os.path.join(os.path.dirname(__file__), "hle_text_only.json")
IMG_FIELDS = ("image", "image_preview", "images", "figure")
Q_FIELDS = ("question", "problem", "prompt")
A_FIELDS = ("answer", "solution", "final_answer")


def _first(ex, fields):
    for f in fields:
        if ex.get(f):
            return ex[f]
    return None


def main():
    try:
        ds = load_dataset("cais/hle", split="test", token=os.environ.get("HF_TOKEN"))
    except Exception as e:
        print("FAILED to load cais/hle:", str(e)[:250])
        print("If gated: accept terms at https://huggingface.co/datasets/cais/hle and export HF_TOKEN.")
        return
    print("row schema:", list(ds[0].keys()))
    items = []
    for i, ex in enumerate(ds):
        if any(ex.get(f) for f in IMG_FIELDS):
            continue  # skip multimodal
        q = _first(ex, Q_FIELDS)
        a = _first(ex, A_FIELDS)
        if q and a is not None:
            items.append({"id": ex.get("id", str(i)), "question": q, "answer": a})
    json.dump(items, open(OUT, "w"))
    print(f"wrote {len(items)} text-only HLE items -> {OUT}")


if __name__ == "__main__":
    main()
