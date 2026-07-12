"""GPQA-Diamond MCQ via the cascade (regression check for tier-1 reasoning tuning)."""
from __future__ import annotations
import json, os, re
from model import model_complete
from harness import run_benchmark
DATA=os.environ.get("GPQA_FILE","datasets/gpqa_diamond.jsonl")
def load_items():
    return [json.loads(l) for l in open(DATA) if l.strip()]
def _prompt(it):
    return it["problem"]+"\n\nAnswer with ONLY the single letter (A, B, C, or D) on the last line."
def _extract(t):
    if not t: return None
    m=re.findall(r"\\boxed\{([A-D])\}", t) or re.findall(r"(?:answer|Answer)[^A-D]{0,10}([A-D])\b", t) or re.findall(r"\b([A-D])\b", t)
    return m[-1] if m else None
def solve(it):
    c,meta=model_complete([{"role":"user","content":_prompt(it)}], max_tokens=int(os.environ.get("GPQA_MAXTOK","24000")))
    return _extract(c), meta
def grade(it, pred):
    return pred is not None and str(pred).strip().upper()==str(it["answer"]).strip().upper()
def main():
    run_benchmark(os.environ.get("GPQA_RESULT_NAME","gpqa"), load_items(), solve, grade,
                  concurrency=int(os.environ.get("CONC","6")), cost_log=os.environ.get("ATXP_MODEL_COST_LOG"))
if __name__=="__main__": main()
