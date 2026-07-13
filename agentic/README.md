# Agentic benchmarks (official third-party harnesses)

These benchmarks run inside their **own official harnesses** (which own the tool/agent
loop and spin up task containers). We do **not** re-implement them. They call the model
over HTTP, so we point them at the **same endpoint** as the simple runners — set by
`model/config.py` env (`PARETO_MODEL_BASE_URL`, default the cascade server). That endpoint
is the single swap point: change it (here, or in `model/client.py` for the Python
runners) to move from the self-hosted cascade to the productionized Pareto API.

Common env for all of these:
```bash
export OPENAI_API_BASE=$PARETO_MODEL_BASE_URL      # e.g. http://localhost:8097/v1
export OPENAI_BASE_URL=$PARETO_MODEL_BASE_URL
export OPENAI_API_KEY=${PARETO_MODEL_API_KEY:-dummy}
export PARETO_MODEL_COST_LOG=/path/to/server_cost.jsonl   # for $/task
```

---

## 1. Terminal-Bench 2.1  — `harbor`
Official harness `harbor`, agent `terminus-2`. **Use 2.1, not 2.0** (2.1 fixed 28/89 tasks:
drifted deps, too-tight timeouts, instruction/test mismatches; turn-limits → time-limits).
```bash
harbor run -d terminal-bench@2.1 -a terminus-2 -m openai/route \
  -n 4 --agent-timeout-multiplier 3 --yes -o results/terminal_bench_2_1
```
Status: harness proven at 2.0 on our stack; **work: bump version to 2.1, re-pull task images.**

## 2. SWE-Bench Pro  — `mini-swe-agent` + Scale grader
Agent: `mini-extra swebench` (backticks config — our models emit ```bash blocks, not tool_calls).
Grading: official `scaleapi/SWE-bench_Pro-os` (`--use_local_docker --dockerhub_username=jefzda`,
image repo path `/app`). Validated 100% on gold in prior work.
```bash
mini-extra swebench --subset pro --split test -m openai/route -w 4 -o results/swe_pro_out
# then grade with the scaleapi harness
```
Status: **work: full Pro set (not a slice), confirm jefzda images, run official grader.**

## 3. Finance Agent v2  — `vals-ai/finance-agent-v2`
Public harness (927 expert-verified agentic tasks; needs financial-data tool access the
harness provides). Point its model config at our endpoint.
```bash
git clone https://github.com/vals-ai/finance-agent-v2 && cd finance-agent-v2
# configure model = openai-compatible @ $PARETO_MODEL_BASE_URL, then run their entrypoint
```
Status: **work: clone, wire their model config to our endpoint, provision their data tools.**

## 4. DRACO  — existing `draco-cascade-bench` harness
Deep-research (tools: Exa web_search/web_fetch, maxSteps 20) + `gemini-3.1-pro-preview` judge
on the weighted rubric. Contamination guard blocks `huggingface.co` + `r2cdn.perplexity.ai`.
Cascade result we keep: **73.1 vs solo-Opus 68.9 at <½ cost.**
Harness lives in `draco-cascade-bench` (ported to `src/local/run.ts` on the bench box; now in
`circuitandchisel/draco-bench-box`). It already calls the cascade via the router — same endpoint.
```bash
# from the draco harness:
npm run local -- --bench draco --limit 100      # points at the cascade endpoint
```
Status: **works today.** Work: run full 100 on the frozen RC endpoint; keep the gemini judge.

## 5. HLE — with-tools track
The with-tools HLE config is agentic (web search). Plan: in `benchmarks/hle.py` (MODE=tools),
give the model `web_search`/`web_fetch` tools via `model_complete(tools=...)` and run a bounded
tool loop. Status: **scaffolded (`NotImplementedError`), needs the tool loop wired.**
