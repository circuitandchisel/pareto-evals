"""MMMU-Pro — multimodal expert reasoning (replaces the old MMMU-Val slice).

MMMU-Pro is the harder variant: 10 answer options (vs 4) and a vision-only track.
Dataset: HF `MMMU/MMMU-Pro`. Each item has a question, options (up to 10), an answer
letter, and one or more images. We send a multimodal message (text + image_url data
URIs) and grade the extracted letter.

Requires the model endpoint to accept image content (our cascade routes images to the
qwen3-vl VLM). Set MMMU_PRO_FILE to a prepared JSON [{id, question, options, answer, images:[b64...]}]
(prepare with datasets/prepare_mmmu_pro.py) OR adapt load_items() to stream from HF.
"""
from __future__ import annotations

import json
import os
import re
import string

from model import model_complete
from harness import run_benchmark

DATA = os.environ.get("MMMU_PRO_FILE", "datasets/mmmu_pro.json")


def load_items() -> list[dict]:
    return json.load(open(DATA))


def _prompt_text(it: dict) -> str:
    letters = string.ascii_uppercase
    opts = "\n".join(f"{letters[i]}. {o}" for i, o in enumerate(it["options"]))
    return (f"{it['question']}\n\n{opts}\n\nAnswer with ONLY the letter of the correct option.")


def _content(it: dict) -> list[dict]:
    parts: list[dict] = [{"type": "text", "text": _prompt_text(it)}]
    for b64 in it.get("images", []):
        parts.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
    return parts


def _n_options(it: dict) -> int:
    return len(it.get("options", []))


def _extract_letter(text: str | None, n_opts: int = 10):
    """Pull the answer letter, tolerant of chatty output. Preference order:
    an explicit 'Answer: X' / 'answer is X', then '(X)', then a lone trailing
    letter, then the first standalone letter. Only letters within range."""
    if not text:
        return None
    up = text.strip().upper()
    hi = string.ascii_uppercase[max(0, n_opts - 1)]  # e.g. 'J' for 10 options
    rng = f"A-{hi}"
    for pat in (
        rf"ANSWER\s*(?:IS|:|=)?\s*\(?([{rng}])\)?",
        rf"\(([{rng}])\)",
        rf"(?:^|\n)\s*([{rng}])\s*(?:$|\.|\))",
    ):
        ms = re.findall(pat, up)
        if ms:
            return ms[-1]
    m = re.search(rf"\b([{rng}])\b", up)
    return m.group(1) if m else None


def solve(it: dict):
    if not it.get("images"):
        # Every MMMU-Pro item carries >=1 image; an empty list is a prep defect,
        # not a model failure. Fail loud with a clear reason instead of silently
        # sending a text-only question that references a missing "<image N>".
        raise ValueError(f"prep-defect: item {it.get('id')} has no images")
    content, meta = model_complete([{"role": "user", "content": _content(it)}])
    return _extract_letter(content, _n_options(it)), meta


def grade(it: dict, pred) -> bool:
    return pred is not None and pred.upper() == str(it["answer"]).strip().upper()


def main():
    run_benchmark("mmmu_pro", load_items(), solve, grade,
                  concurrency=int(os.environ.get("CONC", "4")),
                  cost_log=os.environ.get("PARETO_MODEL_COST_LOG"))


if __name__ == "__main__":
    main()
