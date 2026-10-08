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

## Sampling-param proxy (`strip_proxy.py`) — needed for Pareto

These harnesses drive your model through reference agents (mini-swe-agent,
terminus-2, OpenHands) that **hard-code sampling params** — `temperature=0`, often
a `stop` sequence. The **Pareto gpu-router rejects any non-default sampler with
HTTP 400** (it accepts only `temperature=1`/`top_p=1`/… and an empty `stop`), so
every agent call fails on the first request. `strip_proxy.py` sits in front of the
endpoint, strips the offending keys, and forwards everything else (auth, path,
streaming). Point the wrappers' `MODEL_BASE_URL` at it.

```bash
# host-side harnesses (Terminal-Bench, Toolathlon, CyberGym):
UPSTREAM="$PARETO_BASE_URL" PORT=8900 python3 agentic/strip_proxy.py &
export MODEL_BASE_URL=http://172.17.0.1:8900/v1   # Docker gateway (reachable from host + containers)

# DeepSWE only: pier isolates the agent behind a squid egress proxy that allows
# ONLY ports 80/443, so run a SECOND instance on a safe port for that harness:
sudo env UPSTREAM="$PARETO_BASE_URL" PORT=80 python3 agentic/strip_proxy.py &
#   ...then run_deepswe.sh with MODEL_BASE_URL=http://172.17.0.1/v1
```

**Behind a gateway with a non-streaming timeout** (one that answers a non-streaming
call only once the whole generation is done and times out long agent steps, e.g. a
multi-thousand-token file write), add `UPSTREAM_STREAM=1`: the proxy turns each
non-streaming `/chat/completions` into a streaming call upstream and folds the SSE
frames (text, tool_calls, finish_reason, usage) back into the single JSON object the
agent asked for. Requests the agent already streams pass through unchanged.

If your endpoint accepts standard sampling params, skip this — point the wrappers
straight at it.

## The v2 agentic slate

The 2026 frontier launches (GLM-5.3, Grok 4.6, DeepSeek-V4-Pro, Claude Fable 5,
GPT-5.6 Sol) featured almost entirely agentic, long-horizon benchmarks. These four are
the **open** ones (dataset + harness runnable by anyone) that appeared across those
releases. Each has a small `./run_*.sh` wrapper that pins the exact upstream
invocation, and `run_slate.sh` runs the whole slate in one command.

| Wrapper | Benchmark | In N/5 launches | Category | Headline metric |
|---|---|---|---|---|
| `run_deepswe.sh` | DeepSWE v1.1 (Datacurve, 113 tasks) | 4/5 | Long-horizon SWE agent | mean binary `reward` |
| `run_tb.sh` | Terminal-Bench 4.0 (66 tasks; 3.0 = 74, 2.1 = 89 selectable; agent terminus-2 or `TB_AGENT=dirac`) | 5/5 (as 3.0/2.1) | Terminal/CLI agent | resolved / total |
| `run_toolathlon.sh` | Toolathlon-Verified (HKUST, 108 tasks) | 3/5 | Tool-use / MCP orchestration | `average_success_rate` (Pass@1) |
| `run_cybergym.sh` | CyberGym (UC Berkeley, 1,507 vulns) | 3/5 | Vulnerability reproduction | fraction with a working PoC |
| `run_arc_agi_3.sh` | ARC-AGI-3 public set (ARC Prize, 25 games) | — (added 2026-09) | Interactive reasoning / skill acquisition | mean per-game score, 0–100 (human action-efficiency) |
| `run_tb_science.sh` | Terminal-Bench-Science 0.1 (70 tasks) | — (Hermes Index suite, 2026-10) | Scientific research workflows in the terminal | resolved / total |
| `run_skillsbench.sh` | SkillsBench (87 tasks, curated skills) | — (Hermes Index suite, 2026-10) | Agent skill use | resolved / total ("clean": leaked tasks dropped) |
| `run_hermes_index.sh` | the three open Hermes Index suites (TB 4.0 + the two above) through the **Hermes Agent** harness, then `hermes_index.py` | — | Hermes Index estimate | mean of 4 suites (Hermes Bench predicted) + $/task |

### Run the whole slate in one command — `run_slate.sh`

```bash
MODEL_BASE_URL=https://your-endpoint/v1 MODEL_API_KEY=sk-... MODEL_NAME=your-model \
  ./agentic/run_slate.sh
```

Runs all five wrappers in sequence against one model and prints a combined
pass/fail summary with each benchmark's output dir. A benchmark that fails is
reported and the slate continues to the next one.

- **Subset:** `SLATE="deepswe tb" ./agentic/run_slate.sh` (space/comma list).
- **Prereqs** are the union of the five wrappers' prereqs (Docker + harbor + pier +
  the CyberGym clone/data + the Toolathlon clone + the `arc-agi-3-benchmarking` clone
  and a free `ARC_API_KEY`) — see the per-benchmark sections below. `arc3` fails fast
  (and the slate continues) if `ARC_API_KEY` is unset.
- **Against Pareto**, start `strip_proxy.py` first (see the proxy section) and point
  the slate at it; DeepSWE needs the safe-port instance via a per-benchmark override:
  ```bash
  MODEL_BASE_URL=http://172.17.0.1:8900/v1 DEEPSWE_MODEL_BASE_URL=http://172.17.0.1/v1 \
  MODEL_API_KEY=sk-... MODEL_NAME=your-model ./agentic/run_slate.sh
  ```
  (`<NAME>_MODEL_BASE_URL` overrides the base URL for one member — `NAME` ∈
  `DEEPSWE|TB|TOOLATHLON|CYBERGYM|ARC3`.)

> The slate is **not** a `run.py` benchmark. `python run.py` (`--benchmarks all`)
> runs only the core non-agentic slate (`hle, arxiv_math, hmmt_2026, mmmu_pro`);
> the agentic slate always runs through these wrappers.

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

## Terminal-Bench 4.0 (+ 3.0, 2.1) — `run_tb.sh`
External harness `harbor` with the `terminus-2` reference agent by default, or
[Dirac](https://dirac.run) with `TB_AGENT=dirac` (see below). Terminal-Bench is now a
continuous, semver'd benchmark; **the wrapper defaults to 4.0** (released 2026-08-26):
3.0's 74 tasks minus 8 removed for saturation / refusals / leaked solutions / quality
= **66 tasks**, 19 tasks fixed, task resources (time, CPU, memory) calibrated and a flat
8h agent timeout everywhere, so timeouts and infra errors are rarer than in 3.0.
Set `TB_VERSION=3.0` to compare against the 2026 launch posts (all five reported 3.0 or
2.1), or `TB_VERSION=2.1` for the near-saturated older set. **4.0 scores are not
comparable to 3.0** — the task set changed.

```bash
uv tool install 'harbor[modal]'   # use current harbor (>= v0.21.0); + Docker or --env modal
MODEL_BASE_URL=https://your-endpoint/v1 MODEL_API_KEY=sk-... MODEL_NAME=your-model \
  ./agentic/run_tb.sh                       # TB 4.0
TB_VERSION=3.0 ... ./agentic/run_tb.sh      # TB 3.0
TB_VERSION=2.1 ... ./agentic/run_tb.sh      # TB 2.1
```

3.0 and 4.0 are **Hub-only** (`terminal-bench/terminal-bench@{3,4}.0.0`) and their tasks
carry their own timeouts — the wrapper imposes no global timeout multiplier for them.
Both have **H100-only tasks** (4.0: `fp8-rmsnorm-gemm`, `math-eval-grader`,
`jax-speedrun-gpu`; 3.0 also `exam-pdf-eval`) that the wrapper excludes on a plain
Docker box; set `TB_INCLUDE_GPU=1` or `TB_ENV=modal` to include them. Score =
resolved/total across `<out>/*/*/result.json` (`verifier_result.rewards.reward == 1`).

**Agent choice.** `TB_AGENT` selects the scaffold. `terminus-2` (default) is harbor's
reference agent, the one the launch posts use. `TB_AGENT=hermes` runs NousResearch's
Hermes Agent the way the [Hermes Index](#hermes-index) does (reasoning effort high;
`harbor_agents/hermes_agent.py`; harbor ≥ 0.24.0) — the index's TB4 number is this
wrapper's default run (4.0, Docker, 3 GPU tasks excluded = 63 tasks) with that agent.
`TB_AGENT=dirac` runs
[Dirac](https://dirac.run) — the open-source, token-efficiency-focused Cline fork
(hash-anchored edits, AST tools, parallel tool calls) that posted 65.2% on TB-2 with
gemini-3-flash-preview, ahead of every agent on the leaderboard at the time. The adapter
lives in `agentic/harbor_agents/dirac_agent.py` and is loaded by import path; harbor
npm-installs `dirac-cli` (Node 22 via nvm) into each task container and runs
`dirac task --provider $MODEL_BASE_URL --model $MODEL_NAME --json --yolo`, so the same
`MODEL_*` variables apply. Any other value is handed to harbor as a built-in agent name
or a `module.path:ClassName` import path.

```bash
TB_AGENT=dirac MODEL_BASE_URL=... MODEL_API_KEY=... MODEL_NAME=... ./agentic/run_tb.sh
# knobs: DIRAC_VERSION (pin npm version), DIRAC_TIMEOUT_SEC (Dirac's own -t),
#        DIRAC_MAX_MISTAKES (--max-consecutive-mistakes), DIRAC_AGENT_KWARGS="k=v ..."
```

Scores from different agents are **not comparable** with each other — TB measures the
model+scaffold pair — so label runs with the agent. Per-trial Dirac transcripts land in
`<out>/*/*/agent/dirac.txt` (JSON lines); token and cost totals are summed into each
trial's `result.json` `agent_result`. `MODEL_MAX_INPUT_TOKENS` maps to Dirac's
`--auto-condense --auto-condense-at N` (AI compaction at that context size) instead of
terminus-2's `model_info` summarization hint.

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

## ARC-AGI-3 (public set) — `run_arc_agi_3.sh`
ARC Prize's interactive-reasoning benchmark (launched 2026-03-25): turn-based game
environments on a 64×64 grid with no instructions — the agent has to discover the rules
and the goal, then clear levels. 135 games; **25 are public**, the other 110 are
semi-private/private and only ARC Prize can run them, so the leaderboard's numbers are
not reproducible by anyone else. This wrapper runs the public 25 through the **official
harness** (`arcprize/arc-agi-3-benchmarking`, MIT — the same agent + scoring ARC Prize
uses) in its *Standard* mode (provider-neutral text history), against any
OpenAI-compatible Chat-Completions endpoint.

```bash
git clone https://github.com/arcprize/arc-agi-3-benchmarking   # into ./arc-agi-3-benchmarking (or set ARC3_DIR)
(cd arc-agi-3-benchmarking && uv venv -p 3.12 && uv sync)      # Python >= 3.12
export ARC_API_KEY=...            # free — register at https://arcprize.org (anonymous requests are 401)
MODEL_BASE_URL=https://your-endpoint/v1 MODEL_API_KEY=sk-... MODEL_NAME=your-model \
  ./agentic/run_arc_agi_3.sh
ARC3_GAMES=ls20 ... ./agentic/run_arc_agi_3.sh                 # one-game smoke test
```

Games are served by ARC Prize's hosted API and **every scorecard is stored on their
server** (browse at arcprize.org/scorecards; the wrapper tags them `pareto-evals,<model>`).
The wrapper injects a `pareto-evals-<model>` entry into the harness's
`model_configs.yaml` (pristine copy kept as `model_configs.yaml.orig`), plays games in
batches of `CONC` (each game = one in-flight model call), and writes
`<out>/summary.json` + per-batch `scorecard_N.json` + the harness's per-step
`recordings/`. Only `model` / `max_completion_tokens` (/ optional `reasoning_effort`)
are sent — no temperature/top_p/stop — so Pareto needs no strip proxy here.

**Score** = mean over games of the per-game score (0–100). Per level the harness awards
`min(1, human_baseline_actions / agent_actions)²` (later levels weighted more; > 5×
the baseline scores 0), so 100 means "as action-efficient as the human baseline on
every level". At launch every frontier model scored < 1 on the semi-private set; by
2026-09 several score well, which is why it is in the slate. Knobs: `MAX_TOKENS`
(default 32768 — official configs use 128k), `ARC3_MULTIPLIER` (per-level action budget
as a multiple of the human baseline; 5.0 is official), `ARC3_MAX_CONTEXT` (175k
official), `ARC3_MAX_RUNTIME_SECONDS` (per-game wall-clock cap), `ARC3_TAGS`.
Caveat: public-set scores are **not** comparable to the leaderboard (semi-private set),
and the two harness modes (Standard vs provider-adapter) are reported separately upstream.

**Budget your time.** The per-level action budget is 5× the human baseline, so a single
game can allow thousands of actions (ls20: 3,880) and each action is a full model call
over a ~50k-token transcript — a model that never clears a level can grind for a day per
game. For smoke tests set `ARC3_MAX_RUNTIME_SECONDS` (e.g. 1500); the game ends with
outcome `TIMEOUT`, the scorecard still closes, and `summary.json` is still produced. For
real runs decide the cap up front and report it alongside the score.

**Pareto note (2026-09):** the gpu-router returned deterministic `400 upstream provider
rejected the request` for some ~60k- and ~175k-token transcripts (not a length limit —
230k-token prompts pass) plus intermittent 500s. The harness retries 4× ~2s apart and
then abandons the game (`AGENT_ERROR`, scored 0), so until the router is fixed a full
run will lose games to endpoint errors; check `AGENT EXIT REASON` lines in the batch
logs before trusting a score.

---

## Hermes Index

[Nous Research's Hermes Index](https://portal.nousresearch.com/bench) (launched
2026-10-06) ranks models by how they perform **inside Hermes Agent**, Nous's open-source
agent (MIT, `NousResearch/hermes-agent`). It is the plain mean of four suites' scores,
reported next to the plain mean of their $/task, every run pass@1 with reasoning effort
set to high where the model offers it:

| Suite | Tasks | Open? | Here |
|---|---|---|---|
| Hermes Bench | 150 (25 scenarios: skills, research, charts, memory, tool use, safety) | **no** — Nous-internal | predicted (below) |
| Terminal-Bench 4.0, GPU tasks removed | 63 | yes | `run_tb.sh` (`TB_VERSION=4.0`, Docker, default GPU exclusion) |
| Terminal-Bench-Science 0.1 | 70 | yes | `run_tb_science.sh` |
| SkillsBench, "clean" score | 87 minus leaked | yes | `run_skillsbench.sh` |

All four go through the same harness, so this slate runs the three open suites with
**`TB_AGENT=hermes`**: harbor's built-in Hermes installed agent (it installs
`hermes-agent` from `main` into each task container — 6–10 min per container — and
runs `hermes --yolo chat -q <instruction> -Q --provider openai-api`, honouring
`OPENAI_BASE_URL`/`OPENAI_API_KEY`, i.e. the same `MODEL_*` variables as every other
wrapper), subclassed in `harbor_agents/hermes_agent.py` to set
`agent.reasoning_effort: high` and to surface in-image skills to Hermes. **harbor ≥
0.24.0** is required (the `openai/<model>` → `openai-api` provider routing landed there;
older harbor sends it to OpenRouter). Hermes sends its own sampling params, so against
Pareto run it through `strip_proxy.py` like the other harnesses.

```bash
uv tool install --force 'harbor[modal]>=0.24.0'
MODEL_BASE_URL=https://your-endpoint/v1 MODEL_API_KEY=sk-... MODEL_NAME=your-model \
MODEL_INPUT_PRICE_PER_MTOK=3 MODEL_OUTPUT_PRICE_PER_MTOK=15 \
  ./agentic/run_hermes_index.sh            # tb4 + tbsci + skills, then the estimate
SUITES="skills" ... ./agentic/run_hermes_index.sh   # subset; per-suite summaries only
```

Each suite is also runnable on its own (`run_tb.sh` with `TB_AGENT=hermes`,
`run_tb_science.sh`, `run_skillsbench.sh` — the latter two default to the Hermes agent;
`TB_AGENT=terminus-2` gives harbor's reference agent instead). Knobs:
`HERMES_REASONING` (default `high`), `HERMES_VERSION` (git tag/branch of hermes-agent to
install; default `main`, like Nous — pin for reproducibility), `HERMES_MAX_TURNS`,
`HERMES_TOOLSETS`, `HERMES_AGENT_KWARGS`, plus `CONC`, `TB_ENV`, `OUT`, `LIMIT`,
`TASKS_FILE`/`TB_EXCLUDE_FILE` as in `run_tb.sh`.

**Scoring and the extrapolation — `hermes_index.py`.** It reads each suite's harbor
output (`result.json` per trial: `verifier_result.rewards.reward`, `agent_result`
tokens), prices tokens with `MODEL_*_PRICE_PER_MTOK` (Hermes reports tokens, not cost;
`--usage-log suite=path` takes a `strip_proxy.py` USAGE_LOG for inline-cost endpoints
such as Pareto), and then predicts Hermes Bench from the open suites with a fit on the
14-row launch leaderboard shipped in `hermes_index/leaderboard_2026-10-06.csv`:
HB score ≈ linear in the SkillsBench and TB4 scores (HB only spans 54–77 while the open
suites span 0–70, and it tracks SkillsBench most closely), capped at the best HB on the
board; HB $/task ≈ log-linear in the SkillsBench and TB4 $/task. The index is then the
mean of the three measured scores and the predicted HB, likewise for $/task. Leave-one-out
over the published rows (`python3 agentic/hermes_index.py --check`): **index MAE 0.9
points, worst 2.4; $/task within ±2%** — printed with every estimate, together with the
index range you would get for any Hermes Bench score on the board, and where the estimate
would rank on the launch leaderboard.

```bash
# what-if from numbers you already have (scores in %, $/task):
python3 agentic/hermes_index.py --scores tb4=54,tbsci=52.9,skills=69.6 --costs tb4=6.27,tbsci=12.65,skills=0.51
# per-suite summary of one run (clean SkillsBench score, $/task), no index:
python3 agentic/hermes_index.py --skills skillsbench_<ts> --summary
```

**Caveats.**
- *Hermes Bench is predicted, not measured.* Treat the index as "≈ ±1 point"; the three
  open scores are the measurements. Refit automatically picks up new rows if you append
  to the leaderboard CSV (the first commented lines record provenance; `*`-marked
  provisional entries are noted in the `provisional` column).
- *SkillsBench skills.* The Hub package keeps each task's curated skills in
  `environment/skills/`, and only 2/87 Dockerfiles copy them into the image (SkillsBench's
  own `bench` CLI injects them). `run_skillsbench.sh` therefore downloads the dataset once
  into `SKILLSBENCH_DIR` and patches every task (`COPY skills /harbor/skills` +
  `[environment] skills_dir = "/harbor/skills"`), which harbor passes to the agent and the
  Hermes adapter copies into Hermes's skills directory. How Nous surfaced the skills to
  Hermes is not published; this is the benchmark's "curated skills" condition.
  `SKILLSBENCH_NO_SKILLS=1` runs the unpatched copy (the paper's no-skills ablation).
- *SkillsBench "clean" score.* Nous drops tasks where the agent found the public
  SkillsBench repo and used its solutions (tasks allow internet). `hermes_index.py` flags
  a trial whose Hermes transcript mentions the repo / HF dataset / site and reports raw
  and clean; review the flagged tasks — it is a regex, not a judgment.
- *Task counts.* TB4 denominators on the leaderboard are 63 (= 66 − 3 H100 tasks), which
  is this wrapper's default on Docker; `TB_ENV=modal` or `TB_INCLUDE_GPU=1` would include
  them and break comparability. TB-Science denominators are 70.
- *Costs.* Nous prices input, cache-hit, cache-write, reasoning and answer tokens
  separately at each provider's list price. The adapter reads Hermes's session totals
  (input / cache-read / cache-write / output tokens — harbor's stock adapter reports 0 for
  current Hermes) into `agent_result`, so `tokens × price` honours
  `MODEL_CACHE_PRICE_PER_MTOK` when set; without prices, `hermes_index.py` falls back to
  Hermes's own list-price estimate from the session record (`cost_status: estimated`),
  and a strip_proxy USAGE_LOG with inline cost is exact.
- *Hermes version.* Nous does not publish the hermes-agent commit used. The adapter
  installs `main` by default; set `HERMES_VERSION=<tag>` to pin a run. (With hermes-agent
  `main` as of 2026-10, harbor ≤ 0.24.0's own install step fails every trial in setup:
  Hermes treats harbor's `HERMES_HOME=/tmp/hermes` as a separate data root that needs
  `hermes pm repair` first, and `hermes version` became `hermes --version`. The adapter's
  install step does the repair and probes either spelling, so current main and older tags
  both work.)

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
