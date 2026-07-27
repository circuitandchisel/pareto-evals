# DRACO — deep-research agentic benchmark

DRACO evaluates multi-step, tool-using research answers against per-task rubrics
(LLM-judged). This is a small, self-contained TypeScript runner that drives **any
OpenAI-compatible endpoint** — same "bring your own model" model as the rest of
`pareto-evals`, just in Node instead of Python (the upstream harness is TS).

- **Dataset:** [`perplexity-ai/draco`](https://huggingface.co/datasets/perplexity-ai/draco) (MIT). Auto-downloaded to `draco/data/test.jsonl` on first run.
- **Grader:** LLM judge over the row's rubric (set `JUDGE_MODEL`).
- **Score:** 0–100 rubric score per task (not %-correct); reported as a mean.

## Run

```bash
cd draco
npm install
cp .env.example .env      # fill in GATEWAY_BASE_URL / GATEWAY_API_KEY / BENCH_MODEL / JUDGE_MODEL
npm run fetch-dataset     # downloads test.jsonl (MIT) from HuggingFace
npm run bench -- --limit 50 --out ../results/draco_mymodel.json
```

CLI: `tsx src/run.ts [--limit N] [--domain D] [--tasks id1,id2] [--out file.json] [--model M] [--judge M] [--dry-run]`
(`--dry-run` lists tasks without calling any model.)

## Config (env)

| var | meaning |
|---|---|
| `GATEWAY_BASE_URL` | your endpoint base (OpenAI-compatible) |
| `GATEWAY_API_KEY` | Bearer key for that endpoint |
| `BENCH_MODEL` | model id to evaluate |
| `JUDGE_MODEL` | model id used to grade rubrics |
| `JUDGE_CONNECTION_TOKEN` | optional separate judge key (defaults to `GATEWAY_API_KEY`) |
| `BENCH_CONCURRENCY` | parallel tasks (default 3) |

Results write to a JSON file (per-task rows + mean score + cost). Nothing here is
tied to any specific provider — point it at whatever OpenAI-compatible API you want
to benchmark.
