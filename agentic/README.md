# Agentic benchmarks

These run inside their **own official harnesses** (which own the tool/agent loop and
spin up task containers) — we don't re-implement them. Each calls your model over an
**OpenAI-compatible** HTTP endpoint, so they use the same "bring your own model" swap
point as the rest of `pareto-evals`. Set the endpoint via env:

```bash
export OPENAI_API_BASE="$MODEL_BASE_URL"      # e.g. https://your-endpoint/v1
export OPENAI_BASE_URL="$MODEL_BASE_URL"
export OPENAI_API_KEY="${MODEL_API_KEY:-dummy}"
export MODEL_COST_LOG=/path/to/cost.jsonl     # optional: enables $/task if your endpoint logs cost
```

These are **opt-in** (excluded from `--benchmarks all`) because they need Docker and
extra tooling.

---

## SWE-bench Verified — `mini-swe-agent`
First-class `run.py` benchmark. Needs Docker + `mini-swe-agent`; generates patches, then
grades with the official `swebench` harness.

```bash
python run.py --benchmarks swe_verified --models yourmodel,comparison --slice 500
```

Grading note: the official grader pulls a per-instance eval image from Docker Hub. On a
fresh host you can hit Docker Hub's anonymous pull-rate-limit mid-run; either `docker login`,
or re-grade with local builds (`run_evaluation ... --namespace ""`). `swe_rebench` is a
second, similar SWE benchmark selectable the same way.

## Terminal-Bench 2.1 — `harbor`
External harness `harbor` with the `terminus-2` agent. Use 2.1 (2.1 fixed drifted deps,
tight timeouts, and instruction/test mismatches in 2.0).

```bash
pip install harbor   # + Docker running
MODEL_BASE_URL=https://your-endpoint/v1 MODEL_API_KEY=sk-... MODEL_NAME=your-model \
  ./agentic/run_tb.sh          # wraps the exact harbor invocation; see the script for knobs
```

Score = resolved/total across the run's `result.json` files.

## DRACO — deep-research agentic (vendored TS runner)
See [`../draco/`](../draco/) — a small self-contained Node runner (public MIT dataset,
LLM-judged rubrics) pointed at your endpoint:

```bash
cd draco && npm install && cp .env.example .env   # fill in GATEWAY_BASE_URL / GATEWAY_API_KEY / BENCH_MODEL / JUDGE_MODEL
npm run fetch-dataset && npm run bench -- --limit 50
```
