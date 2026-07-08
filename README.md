# atxp-evals

Clean, reproducible benchmark suite for the self-hosted cascade **release candidate**.
Built so that (a) every model call goes through **one swappable function**, and (b) each
benchmark uses the **official/standard harness** so published numbers hold up to scrutiny.

## The one rule: all model access goes through `model.model_complete()`

```python
from model import model_complete
content, meta = model_complete(messages, tools=..., max_tokens=...)
# meta = {latency_s, finish_reason, tool_calls, usage, raw}
```

Today `model_complete` points at our self-hosted cascade over its OpenAI-compatible
endpoint (`model/config.py`, default `http://localhost:8097/v1`, model `route`). **To swap
in the productionized ATXP model API later, change only `model/client.py`** (base_url +
auth). Third-party agentic harnesses can't import the function, so they point at the *same
endpoint* via env — still a single swap point (see `agentic/README.md`).

Config (env): `ATXP_MODEL_BASE_URL`, `ATXP_MODEL_API_KEY`, `ATXP_MODEL_NAME`,
`ATXP_MODEL_MAX_TOKENS`, `ATXP_MODEL_COST_LOG` (server cost log → `$/task`).

## The slate (8)

| benchmark | role | harness | status |
|---|---|---|---|
| **ARC-AGI-2** | fluid reasoning (replaces GPQA) | `benchmarks/arc_agi_2.py` (ours) | code done; needs eval JSONs + pass@2 for official parity |
| **HMMT 2026** | hard math (replaces AIME) | `benchmarks/hmmt_2026.py` (ours) | code done; needs dataset + sympy/LLM-judge grader |
| **HLE (text-only)** | frontier knowledge; no-tools + tools | `benchmarks/hle.py` (ours) | no-tools done (needs independent judge); tools scaffolded |
| **MMMU-Pro** | multimodal | `benchmarks/mmmu_pro.py` (ours) | code done; needs dataset prep (images→b64) |
| **SWE-Bench Pro** | agentic coding | mini-swe-agent + Scale grader | `agentic/` — proven pipeline, needs full Pro set |
| **Terminal-Bench 2.1** | agentic terminal | harbor + terminus-2 | `agentic/` — proven at 2.0, bump to 2.1 |
| **Finance Agent v2** | agentic finance | `vals-ai/finance-agent-v2` | `agentic/` — clone + wire endpoint + data tools |
| **DRACO** | deep research (cascade WINS) | existing `draco-cascade-bench` harness | `agentic/` — works today |

"Ours" = simple runners through `model_complete` + `harness/run_benchmark` (accuracy,
latency, `$/task`). "Agentic" = official third-party harness pointed at our endpoint.

## Layout
```
model/      config.py, client.py   ← the single swap point
harness/    base.py (run loop), cost.py ($/task from server cost log)
benchmarks/ arc_agi_2, hmmt_2026, hle, mmmu_pro   ← run: python -m benchmarks.<name>
agentic/    README.md — SWE-Bench Pro, Terminal-Bench 2.1, Finance Agent v2, DRACO, HLE-tools
datasets/   dataset files + prep scripts (gitignored if large)
results/    per-run .jsonl + .summary.json (gitignored)
```

## Run
```bash
pip install -r requirements.txt
export ATXP_MODEL_BASE_URL=http://localhost:8097/v1   # cascade RC endpoint
python -m benchmarks.arc_agi_2         # etc.
./run_all.sh                            # simple runners; agentic per agentic/README.md
```

## Reproducibility / scrutiny (we self-publish, so this matters)
- Use the **official harness** per benchmark and compare against numbers produced by that
  **same harness** (e.g. Scale / Artificial-Analysis leaderboard runs, which evaluate all
  models identically) — never a vendor's cherry-picked headline. HLE especially is
  methodology-fragile; we run the **text-only track** and compare only to the Scale
  text-only leaderboard.
- Independent JUDGE for free-form graders (HLE, DRACO) — never grade with our own RC model.
- Freeze one RC config, run all 8 end-to-end, commit results here.

## Not yet
Datasets aren't vendored (download per benchmark). Live runs are deferred until the RC
config is frozen and the bench GPUs are free. See per-file docstrings for exact TODOs.
