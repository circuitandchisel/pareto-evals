# pareto-evals

Reproducible, **head-to-head** LLM benchmarking. Point it at your model's API and a
comparison model (e.g. Claude Opus), choose which benchmarks to run and at what size,
and get a single table:

| Benchmark | n | Pareto score | Pareto $/task | Opus score | Opus $/task |
|---|---|---|---|---|---|
| hle | 200 | 38.0% | $0.0674 | 33.0% | $0.1120 |
| … | | | | | |

- **Accuracy + cost-per-task only** — no latency tracking.
- **Cost comes from the API's own response** when it reports one; otherwise it's computed
  from token usage × prices you configure (for models that don't return cost).
- **Contamination-checked datasets** and proper graders (exact match / LLM judge / symbolic).
- **Bring any OpenAI-compatible endpoint** for either side — nothing here is tied to a
  specific provider.

---

## The slate (v2)

The v2 slate tracks what the 2026 frontier launches (GLM-5.3, Grok 4.6, DeepSeek-V4-Pro,
Claude Fable 5, GPT-5.6 Sol) actually featured. Two shifts: classic MCQ benchmarks are
mostly saturated and no longer featured (GPQA/ARC-AGI-2 moved to **legacy**), and the
center of gravity moved to **open, long-horizon agentic** benchmarks. A hard rule: every
benchmark here is **open** — dataset + harness runnable by anyone. Featured-but-closed
evals (GDPval-AA, Artificial Analysis indices, CursorBench, FrontierMath, Agents' Last
Exam, etc.) are excluded by design. ARC-AGI-3 is the one partial exception: its 25
**public** games + official harness are open (free API key), so we run those; the 110
semi-private/private games behind the leaderboard are not reproducible by anyone else.

**Core (`--benchmarks all`):**

| Name | What | Grader | Judge needed? |
|---|---|---|---|
| `hle` | Humanity's Last Exam (text, no tools) | LLM judge | **yes** |
| `arxiv_math` | MathArena ArXiv problems (post-cutoff) | symbolic math match | no |
| `hmmt_2026` | HMMT Feb 2026 competition math (AIME replacement) | normalized `\boxed{}` | no |
| `mmmu_pro` | MMMU-Pro (multimodal MCQ) | exact | no |

**Legacy (`--benchmarks legacy` — saturated / no longer featured in frontier launches):**

| Name | What | Grader |
|---|---|---|
| `gpqa` | GPQA-Diamond (graduate science MCQ) | exact letter A–D |
| `arc_agi_2` | ARC-AGI-2 (abstract grids) | exact grid |

### Agentic (opt-in — need Docker + extra harnesses; excluded from `--benchmarks all`)

The v2 update is here — these are the open agentic benchmarks that showed up across the
five launches:

| Name | What | In N/5 launches | Harness |
|---|---|---|---|
| DeepSWE v1.1 | long-horizon SWE agent (113 tasks) | 4/5 | [`pier`](agentic/run_deepswe.sh) |
| Terminal-Bench 4.0 (+3.0, 2.1) | agentic terminal tasks (66 / 74 / 89) | 5/5 (as 3.0/2.1) | [`harbor`](agentic/run_tb.sh) |
| Toolathlon-Verified | tool-use / MCP orchestration (108) | 3/5 | [public service](agentic/run_toolathlon.sh) |
| CyberGym | vulnerability reproduction (1,507 vulns) | 3/5 | [server + BYO agent](agentic/run_cybergym.sh) |
| ARC-AGI-3 (public set) | interactive reasoning — 25 public game envs, human-efficiency-normalized | — (added 2026-09; leaderboard uses the semi-private set) | [official `arc-agi-3-benchmarking`](agentic/run_arc_agi_3.sh) |
| Terminal-Bench-Science 0.1 | research-workflow terminal tasks across 5 sciences (70) | — (Hermes Index suite, added 2026-10) | [`harbor`](agentic/run_tb_science.sh) |
| SkillsBench | agent skill use, curated skills + deterministic verifiers (87) | — (Hermes Index suite, added 2026-10) | [`harbor`](agentic/run_skillsbench.sh) |
| DRACO | deep-research, LLM-judged rubrics | — (kept) | vendored Node runner in [`draco/`](draco/) |

**Hermes Index (Nous Research, 2026-10-06).** The index is the mean score (and mean $/task)
of four suites run inside the open-source **Hermes Agent** harness at pass@1, reasoning
effort high: Hermes Bench (closed), Terminal-Bench 4.0 minus GPU tasks, Terminal-Bench-Science
and SkillsBench. The three open suites run here through harbor's Hermes agent
(`TB_AGENT=hermes`, [adapter](agentic/harbor_agents/hermes_agent.py)), and
[`agentic/hermes_index.py`](agentic/hermes_index.py) extrapolates the full index from them
(Hermes Bench is predicted from the published leaderboard; leave-one-out error ≈ ±1 point,
±2% on $/task). One command: [`agentic/run_hermes_index.sh`](agentic/run_hermes_index.sh).
Details in [`agentic/README.md`](agentic/README.md#hermes-index).

**Legacy agentic** (still selectable; no 2026 launch featured them — DeepSWE supersedes):
`swe_verified` (SWE-bench Verified) and `swe_rebench`, both via `mini-swe-agent`.

See [`agentic/README.md`](agentic/README.md) for all of them. They call your model over
the same OpenAI-compatible endpoint — nothing provider-specific.

### Datasets & licensing

Datasets are **not** redistributed here — each `datasets/prepare_*.py` (and DRACO's
`fetch-dataset`) downloads from the upstream source, which carries its own license and
terms of use:

| Benchmark | Source | License |
|---|---|---|
| HLE | `cais/hle` (HF) | per dataset card |
| MMMU-Pro | `MMMU/MMMU_Pro` (HF) | per dataset card |
| ArXiv-math | `MathArena/arxivmath-0526` (HF) | CC BY-SA 4.0 |
| HMMT Feb 2026 | MathArena HMMT-Feb-2026 | per source |
| DeepSWE v1.1 | `datacurve-ai/deep-swe` (GitHub) | Apache-2.0 (Datacurve parts; upstream repos keep their own) |
| Terminal-Bench 4.0 / 3.0 | `harbor-framework/terminal-bench` (Harbor Hub) | per repo |
| Toolathlon-Verified | `hkust-nlp/Toolathlon` (GitHub) | **none stated** — review before redistributing |
| CyberGym | `sunblaze-ucb/cybergym` (GitHub/HF) | Apache-2.0 |
| ARC-AGI-3 (public) | hosted game API at `arcprize.org` (free key); harness `arcprize/arc-agi-3-benchmarking` | harness MIT; games served under ARC Prize's terms (scorecards are stored on their server) |
| Terminal-Bench-Science 0.1 | `harbor-framework/terminal-bench-science` (Harbor Hub `terminal-bench-science/terminal-bench-science@0.1.0`) | Apache-2.0 |
| SkillsBench | `benchflow-ai/skillsbench` (Harbor Hub `benchflow/skillsbench@latest`) | Apache-2.0 |
| Hermes Agent (harness) | `NousResearch/hermes-agent`, installed into each task container by harbor's adapter | MIT |
| DRACO | `perplexity-ai/draco` (HF) | MIT |
| GPQA-Diamond *(legacy)* | `Idavidrein/gpqa` (HF) | CC BY 4.0 (gated) |
| ARC-AGI-2 *(legacy)* | ARC Prize | Apache-2.0 |
| SWE-bench Verified *(legacy)* | `princeton-nlp/SWE-bench_Verified` (HF) | per dataset card |

You are responsible for complying with each dataset's terms. This repo (the harness) is
MIT-licensed; the datasets are not.

### Dataset download commands

After installing `requirements.txt`, prepare all six non-agentic datasets:

```bash
# Export HF_TOKEN in your shell, or use an existing Hugging Face login.
# The account must have accepted the access terms for cais/hle and Idavidrein/gpqa.
python datasets/prepare_all.py

# Or prepare only selected benchmarks:
python datasets/prepare_all.py --benchmarks gpqa arxiv_math
```

This downloads and prepares files locally under `datasets/`; it does not upload to
S3 or call a model. It includes the four core benchmarks plus legacy GPQA and
ARC-AGI-2, not the external agentic harnesses. Scripts use the shell's `HF_TOKEN`
or cached Hugging Face login; they do not load `.env`. MMMU-Pro produces a large
image-containing JSON file (roughly 540 MB). Preparation stops at the first failure;
reruns regenerate selected outputs and may reuse upstream download caches.

The new GPQA and ArXivMath scripts pin upstream revisions and validate row counts
(198 and 40). GPQA choice order uses seed 0 and each record ID, so repeated
preparation gives the same questions and answer letters. ArXivMath uses the
published `train` split as its evaluation set and preserves source-paper metadata.
The older preparation scripts still follow their upstream defaults; this command
does not yet provide version locking for all six datasets.

---

## Prerequisites

- **Python 3.10+**
- An **OpenAI-compatible** chat-completions endpoint + API key for **your model**.
- *(optional)* An OpenAI-compatible endpoint + key for the **comparison model**.
  Opus works via any OpenAI-compatible gateway/proxy (OpenRouter, litellm, a hosted
  gateway) — not Anthropic's native API.
- *(for `hle`)* An **independent judge** endpoint (must not be the model under test).

No GPU is required for this slate — every benchmark is remote API calls.

---

## Quick start (local)

```bash
git clone https://github.com/circuitandchisel/pareto-evals.git
cd pareto-evals
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then edit .env with your credentials

python datasets/prepare_all.py  # requires authorized HF login/token for HLE and GPQA

# smoke test: 10 GPQA items, both models
python run.py --benchmarks gpqa --slice 10

# the full slate, full size, head-to-head (this takes hours — see "Cloud" below)
python run.py
```

The final table prints to your terminal and is written to `results/comparison.md`
and `results/comparison.csv`.

---

## Run on a cloud instance (recommended for full runs)

Full-slate runs take **hours to days**, so run them on an always-on VM rather than your
laptop. Because the slate is pure API traffic, a **small CPU instance is plenty** — no GPU.

**Easiest target: a plain Ubuntu 22.04 VM** (AWS EC2 `t3.large`, or the equivalent on
GCP / DigitalOcean / Lambda / Hetzner — 2 vCPU / 8 GB / 20 GB disk is more than enough).

```bash
# 1. Launch an Ubuntu 22.04 VM and SSH in. On AWS, e.g.:
#    aws ec2 run-instances --image-id <ubuntu-22.04-ami> --instance-type t3.large \
#      --key-name <your-key> --security-groups <sg-with-ssh>
#    then: ssh ubuntu@<public-ip>

# 2. Set it up (installs python, deps, tmux):
git clone https://github.com/circuitandchisel/pareto-evals.git
cd pareto-evals
bash scripts/bootstrap.sh

# 3. Configure credentials:
cp .env.example .env && nano .env

# 4. Run inside tmux so it survives disconnects:
tmux new -s evals
source .venv/bin/activate
python run.py                      # full slate, both models
#   detach with Ctrl-b then d;  reattach later with:  tmux attach -t evals
```

When it finishes, `results/comparison.md` has your table. Copy it back with
`scp ubuntu@<ip>:~/pareto-evals/results/comparison.md .`

---

## Configuration (`.env`)

Copy `.env.example` → `.env` and fill in:

| Variable | Meaning |
|---|---|
| `PARETO_BASE_URL` / `PARETO_API_KEY` / `PARETO_MODEL` | Your model's OpenAI-compatible endpoint, key, model name |
| `PARETO_LABEL` | Column label in the output (default `Pareto`) |
| `COMPARISON_BASE_URL` / `_API_KEY` / `_MODEL` / `_LABEL` | The comparison model (leave `BASE_URL` blank to skip) |
| `COMPARISON_INPUT_PRICE_PER_MTOK` / `_OUTPUT_PRICE_PER_MTOK` | Per-1M-token prices — used to compute $/task **only if** the comparison endpoint doesn't return cost in its responses |
| `JUDGE_BASE_URL` / `_API_KEY` / `_MODEL` | Independent judge for `hle` (free-form grading) |

Cost handling: for **each** side, the runner uses the response's own cost field if present
(`cost_usd` / `cost`, or a cascade `_meta`), and otherwise falls back to
`tokens × price`. Configure prices only for endpoints that don't report cost.

---

## Choosing benchmarks and sizes

```bash
# which benchmarks (default: all)
python run.py --benchmarks gpqa,hle,arxiv_math

# slice size — default is FULL. One number applies to all:
python run.py --slice 200

# or per-benchmark (use 'all' for full on a given one):
python run.py --benchmarks gpqa,hle --slice gpqa=200,hle=all

# Pareto only (skip the comparison model):
python run.py --models pareto

# concurrency (parallel requests per benchmark):
python run.py --concurrency 8
```

Slices are a **seeded representative random subsample** (not the first N), so a slice is a
fair mini-estimate of the full set. `--seed` controls the draw (default `0`) for
reproducibility.

---

## Output

```
| Benchmark | n | Pareto score | Pareto $/task | Opus score | Opus $/task |
|---|---|---|---|---|---|
| gpqa | 200 | 86.9% | $0.0251 | 88.4% | $0.0643 |
| hle  | 200 | 38.0% | $0.0674 | 33.0% | $0.1120 |
```

Written to `results/comparison.md` and `results/comparison.csv`. Per-item detail for each
run is in `results/<benchmark>__pareto.jsonl` and `…__comparison.jsonl` (one row per item:
correctness, token usage, cost, prediction), plus a `.summary.json` per run.

Per-response cost averages use only items with a known cost, including explicit
zero costs; missing costs are not treated as free tasks. The summary's `n_priced`
field records how many items have a response cost, and `cost_usd_total` is their
known subtotal, not an estimate of missing costs. When no response costs exist,
an optional server-log total is divided by all tasks. The comparison runner can
add token-price estimates for unpriced responses, so its cost coverage may be
higher than the summary's.

---

## Notes on graders & fairness

- **`hle` requires a judge.** Free-form answers are graded by an independent LLM
  (`JUDGE_*`). Without one it falls back to a containment match — fine for smoke tests,
  **not** publication-grade.
- **`arxiv_math`** uses a strict symbolic-equivalence check; it can undercount answers that
  are correct but written in an unusual form.
- **Determinism:** temperature defaults to 0; slices are seeded. Transient upstream 5xx/429
  are retried (bounded) so one flaky call never zeros an item.
- **`hmmt_2026`** is the v2 core math benchmark (FrontierMath, the labs' preferred frontier-math
  target, is gated by Epoch AI and can't be self-run). **Caveat:** competition sets risk
  contamination once they predate a model's knowledge cutoff — treat a saturated score as a
  contamination signal, and rotate to the newest MathArena set each cycle. Its `\boxed{}`
  grader is also string-normalized; wire a sympy/LLM-judge grader (`grade` hook) for a real run.

---

## Agentic benchmark (swe_rebench)

`swe_rebench` runs real repository-fixing tasks through [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent)
and grades them with the [SWE-rebench fork](https://github.com/SWE-rebench/SWE-bench-fork)
of `swebench`. It slots into the same table (score = % resolved, plus $/task) but has
**extra prerequisites**, so it's opt-in:

1. **Docker** (each task runs in a container; images are pulled on first use — tens of GB
   across the full split, so give the box ≥100 GB disk for large runs).
2. **mini-swe-agent** installed in its own venv.
3. **The SWE-rebench fork** of `swebench` installed in a venv (it reads each instance's
   `install_config`, which stock `swebench` lacks for these repos).

One-time setup:

```bash
bash scripts/bootstrap-swe.sh      # installs docker check + mini-swe-agent + the fork
```

Then point `.env` at them and set Pareto token prices (agentic $/task is `tokens × price`,
because the agentic harness can't read an inline cost field):

```bash
SWE_MINI_BIN=/path/to/mini/venv/bin/mini-extra
SWE_GRADER_PYTHON=/path/to/fork/venv/bin/python
PARETO_INPUT_PRICE_PER_MTOK=...
PARETO_OUTPUT_PRICE_PER_MTOK=...
```

Run it (add the comparison model's prices too if you include it):

```bash
python run.py --benchmarks swe_rebench --slice 30        # 30 clean instances
python run.py --benchmarks gpqa,hle,swe_rebench          # mix API + agentic
```

Defaults to the contamination-clean `nebius/SWE-rebench-leaderboard` `2026_03` split
(override with `SWE_DATASET` / `SWE_SPLIT`). **Note:** the endpoint must return standard
`usage` token counts for $/task to be computed; if it returns none, the score is still
reported and $/task is left blank.

## Reproducing a full head-to-head

```bash
cp .env.example .env    # set PARETO_* to your API, COMPARISON_* to Opus, JUDGE_* to your judge
python run.py           # all benchmarks, full size, both models
cat results/comparison.md
```
