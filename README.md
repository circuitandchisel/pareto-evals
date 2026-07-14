# pareto-evals

Reproducible, **head-to-head** LLM benchmarking. Point it at your model's API and a
comparison model (e.g. Claude Opus), choose which benchmarks to run and at what size,
and get a single table:

| Benchmark | n | Pareto score | Pareto $/task | Opus score | Opus $/task |
|---|---|---|---|---|---|
| gpqa | 198 | 86.9% | $0.0251 | 88.4% | $0.0643 |
| … | | | | | |

- **Accuracy + cost-per-task only** — no latency tracking.
- **Cost comes from the API's own response** when it reports one; otherwise it's computed
  from token usage × prices you configure (for models that don't return cost).
- **Contamination-checked datasets** and proper graders (exact match / LLM judge / symbolic).
- **Bring any OpenAI-compatible endpoint** for either side — nothing here is tied to a
  specific provider.

---

## The slate

| Name | What | Grader | Judge needed? |
|---|---|---|---|
| `gpqa` | GPQA-Diamond (graduate science MCQ) | exact letter A–D | no |
| `hle` | Humanity's Last Exam (text, no tools) | LLM judge | **yes** |
| `arxiv_math` | MathArena ArXiv problems (post-cutoff) | symbolic math match | no |
| `mmmu_pro` | MMMU-Pro (multimodal MCQ) | exact | no |
| `arc_agi_2` | ARC-AGI-2 (abstract grids) | exact grid | no |

> **Agentic coding (SWE-rebench)** runs through a separate harness (Docker + the
> SWE-rebench eval fork), not this runner — see [`agentic/README.md`](agentic/README.md).

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

---

## Notes on graders & fairness

- **`hle` requires a judge.** Free-form answers are graded by an independent LLM
  (`JUDGE_*`). Without one it falls back to a containment match — fine for smoke tests,
  **not** publication-grade.
- **`arxiv_math`** uses a strict symbolic-equivalence check; it can undercount answers that
  are correct but written in an unusual form.
- **Determinism:** temperature defaults to 0; slices are seeded. Transient upstream 5xx/429
  are retried (bounded) so one flaky call never zeros an item.
- **`hmmt_2026`** ships in `benchmarks/` but is **excluded** from the default slate
  (found to be contaminated for recent models). Run it explicitly if you want it.

---

## Reproducing a full head-to-head

```bash
cp .env.example .env    # set PARETO_* to your API, COMPARISON_* to Opus, JUDGE_* to your judge
python run.py           # all benchmarks, full size, both models
cat results/comparison.md
```
