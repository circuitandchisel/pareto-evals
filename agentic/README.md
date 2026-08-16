# Agentic benchmarks

These run inside their **own official harnesses** (which own the tool/agent loop and
spin up task containers) — we don't re-implement them. Each calls your model over an
**OpenAI-compatible** HTTP endpoint, so they use the same "bring your own model" swap
point as the rest of `pareto-evals`. Set the endpoint via env:

```bash
export MODEL_BASE_URL="https://your-endpoint/v1"   # OpenAI-compatible /v1 base
export MODEL_API_KEY="sk-..."
export MODEL_NAME="your-model"
# most wrappers also export the OPENAI_* aliases the harnesses expect
```

These are **opt-in** (excluded from `--benchmarks all`) because they need Docker and
extra tooling.

## The v2 agentic slate

The 2026 frontier launches (GLM-5.3, Grok 4.6, DeepSeek-V4-Pro, Claude Fable 5,
GPT-5.6 Sol) featured almost entirely agentic, long-horizon benchmarks. These four are
the **open** ones (dataset + harness runnable by anyone) that appeared across those
releases. All are launched with a small `./run_*.sh` wrapper that pins the exact
upstream invocation.

| Wrapper | Benchmark | In N/5 launches | Category | Headline metric |
|---|---|---|---|---|
| `run_deepswe.sh` | DeepSWE v1.1 (Datacurve, 113 tasks) | 4/5 | Long-horizon SWE agent | mean binary `reward` |
| `run_tb.sh` | Terminal-Bench 3.0 (74 tasks) + 2.1 (89) | 5/5 | Terminal/CLI agent | resolved / total |
| `run_toolathlon.sh` | Toolathlon-Verified (HKUST, 108 tasks) | 3/5 | Tool-use / MCP orchestration | `average_success_rate` (Pass@1) |
| `run_cybergym.sh` | CyberGym (UC Berkeley, 1,507 vulns) | 3/5 | Vulnerability reproduction | fraction with a working PoC |

**Legacy (kept, not in the v2 headline):** `run_swe_verified.py` and `run_swe.py`
(SWE-bench Verified / SWE-rebench). No 2026 launch featured SWE-bench Verified —
DeepSWE is its successor here — but the harnesses work and history is useful, so they
remain selectable via `run.py --benchmarks swe_verified,swe_rebench`.

---

## DeepSWE v1.1 — `run_deepswe.sh`
The new cross-lab consensus SWE-agent benchmark: 113 original, contamination-resistant
tasks across TS/Go/Python/JS/Rust, run by `pier` (Datacurve's Harbor fork) with the
reference `mini-swe-agent`. Still has headroom (frontier ~62–74%).

```bash
uv tool install datacurve-pier          # v1.1 grading needs pier > 0.3.0
git clone https://github.com/datacurve-ai/deep-swe   # into ./deep-swe (or set DEEPSWE_DIR)
MODEL_BASE_URL=https://your-endpoint/v1 MODEL_API_KEY=sk-... MODEL_NAME=your-model \
  ./agentic/run_deepswe.sh
```

No GPU. Per-task Docker images are pulled from public ECR. Chat-Completions endpoints
keep the default `--ak model_class=litellm` override (`DEEPSWE_CHAT=1`); set
`DEEPSWE_CHAT=0` only if your endpoint speaks the OpenAI **Responses** API.
Score = mean `reward` over `<out>/*/verifier/reward.json` (or
`stats.evals[...].metrics[0].reward` in `<out>/result.json`).

## Terminal-Bench 3.0 (+ 2.1) — `run_tb.sh`
External harness `harbor` with the `terminus-2` reference agent. **v2 defaults to 3.0**
(74 tasks, 7 domains, frontier ~34–43% — this is where the spread is); set
`TB_VERSION=2.1` for the near-saturated but maximally-comparable older set.

```bash
uv tool install 'harbor[modal]'   # use current harbor (>= v0.21.0); + Docker or --env modal
MODEL_BASE_URL=https://your-endpoint/v1 MODEL_API_KEY=sk-... MODEL_NAME=your-model \
  ./agentic/run_tb.sh                       # TB 3.0
TB_VERSION=2.1 ... ./agentic/run_tb.sh      # TB 2.1
```

TB 3.0 is **Hub-only** (`terminal-bench/terminal-bench@3.0.0`) and its tasks set their
own timeouts (up to 8h) — the wrapper imposes no global timeout multiplier for 3.0. It
has **4 GPU-only tasks** that the wrapper excludes on a plain Docker box; set
`TB_INCLUDE_GPU=1` or `TB_ENV=modal` to include them. Score = resolved/total across
`<out>/*/*/result.json` (`verifier_result.rewards.reward == 1`).

## Toolathlon-Verified — `run_toolathlon.sh`
HKUST-NLP's tool-use / MCP-orchestration benchmark: 108 verified tasks over 32 apps and
604 tools. The `main` branch **is** the Verified release. Uses the maintainers' **public
eval service** so you need no Docker and no external accounts — your endpoint/key tunnel
over a WebSocket proxy (`--mode private`) and never leave your machine.

```bash
git clone https://github.com/hkust-nlp/Toolathlon   # into ./Toolathlon (or set TOOLATHLON_DIR)
pip install httpx typer websockets
MODEL_BASE_URL=https://your-endpoint/v1 MODEL_API_KEY=sk-... MODEL_NAME=your-model \
  ./agentic/run_toolathlon.sh
```

Score = `average_success_rate` (Pass@1) in `<out>/eval_stats.json`. Two caveats: (1) the
public service rate-limits to 180 min cumulative execution per IP / 24h, so a full
108-task run needs a dedicated instance (email the maintainers) or the full local setup
(Docker + real Google/GitHub/HF/Snowflake/Serper accounts — see the repo README);
(2) the repo ships **no license file** — review terms before redistributing anything.

## CyberGym — `run_cybergym.sh`
UC Berkeley's vulnerability-reproduction benchmark (Apache-2.0): 1,507 real OSS vulns;
the agent must produce a PoC that crashes the pre-patch build but not the post-patch one.
This is the open, defensively-framed representative of the cybersecurity category that
GLM-5.3 headlined. **Bring-your-own agent** — CyberGym scores PoCs; the scaffold
(OpenHands / Codex / …) comes from `sunblaze-ucb/cybergym-agent-examples`.

```bash
git clone https://github.com/sunblaze-ucb/cybergym && cd cybergym
pip3 install -e '.[dev,server]'
python scripts/server_data/download_subset.py       # 10-task smoke set (full is ~10TB)
# build an agent image per cybergym-agent-examples, then:
MODEL_BASE_URL=https://your-endpoint/v1 MODEL_API_KEY=sk-... MODEL_NAME=your-model \
CYBERGYM_DATA_DIR=./cybergym_data CYBERGYM_AGENT=openhands \
  ../pareto-evals/agentic/run_cybergym.sh
```

The wrapper starts the scoring server, runs the agent over each task at `level1` (the
difficulty labs report), then aggregates with `verify_agent_result.py`. Score = fraction
of tasks with a successful PoC (report the **final-submission** metric for comparability).
**Safety:** deploy everything locally — never expose the server to the public internet;
the wrapper binds it to the Docker gateway and agents run firewalled on
`cybergym-internal`.

---

## Legacy SWE benchmarks

### SWE-bench Verified — `run_swe_verified.py`
First-class `run.py` benchmark. Needs Docker + `mini-swe-agent`; generates patches, then
grades with the official `swebench` harness.

```bash
python run.py --benchmarks swe_verified --models yourmodel,comparison --slice 500
```

Grading note: the official grader pulls a per-instance eval image from Docker Hub. On a
fresh host you can hit Docker Hub's anonymous pull-rate-limit mid-run; either `docker login`,
or re-grade with local builds (`run_evaluation ... --namespace ""`). `swe_rebench` is a
second, similar SWE benchmark selectable the same way.

## DRACO — deep-research agentic (vendored TS runner)
See [`../draco/`](../draco/) — a small self-contained Node runner (public MIT dataset,
LLM-judged rubrics) pointed at your endpoint. Kept as the deep-research entry: no open
deep-research benchmark was featured across the five launches, and DRACO's dataset is
cleanly public.

```bash
cd draco && npm install && cp .env.example .env   # fill in GATEWAY_BASE_URL / GATEWAY_API_KEY / BENCH_MODEL / JUDGE_MODEL
npm run fetch-dataset && npm run bench -- --limit 50
```
