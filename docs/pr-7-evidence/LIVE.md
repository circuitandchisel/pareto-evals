# Live GPQA validation for PR #7

`live-before-after.png` comes from 200 actual task executions: the same seeded
100-question GPQA-Diamond sample against each exact commit. The requested model
was `pareto-26.10-preview` at `https://api.unbiased.ai/v1`.

| Measure | Before `984f576` | After `a0734c2` |
| --- | ---: | ---: |
| Correct / tasks | 95 / 100 | 94 / 100 |
| Task errors | 0 | 0 |
| Response-reported cost total | $0.44146241 | $0.46195564 |
| Mean response cost / task | $0.0044146241 | $0.0046195564 |
| Median task wall time | 19.22 s | 19.79 s |

The paired accuracy change is -1 percentage point, with an approximate normal
95% interval of -4.4 to +2.4 points. One question improved, two regressed, and
97 were unchanged. This does not establish a regression caused by the PR,
nor establish equivalence or noninferiority. No acceptable-loss margin was
prespecified. Prompts, grading, client, and harness files are byte-identical
between the two snapshots; the PR changes runner failure handling.

## Method and provenance

- Source: `Idavidrein/gpqa`, `gpqa_diamond.csv`, 198 questions. The source hash
  is recorded in `live-evidence.json`; no question text or answer key is published.
- Python seeded sampling: seed 20261001, 100 source rows without replacement.
  Choices shuffled per row with seed `20261001:<zero-based source row>`.
- Ten batches of ten, before/after on even zero-based batches and after/before
  on odd batches. Concurrency 4, maximum output tokens 24000; sampling parameters
  omitted because the endpoint rejects them. Provider defaults are nondeterministic.
- Command per snapshot: `python run.py --benchmarks gpqa --models pareto --slice all --concurrency 4 --seed 20261001`.
  `GPQA_FILE` selects the batch; `GPQA_MAXTOK=24000` and
  `PARETO_SEND_SAMPLING=false`. Credentials were supplied locally, not committed.
- Interrupted after six complete batches per arm; incomplete attempt preserved
  locally and the remaining batches resumed with unchanged settings. Interrupted
  requests may have incurred charges outside the reported totals.
- All twenty completed batch subprocesses exited zero. Export checks ten unique,
  expected IDs per batch, no task errors, and grades against the local answer key.
- Separate HTTP-attempt logs were not written. The original wrapper's report
  step failed after completing all tasks because it expected those logs.
  `live_report.py` instead validates and summarizes the saved task rows, without
  pretending to recover missing logs. Returned model identity, all SDK retry
  attempts, and complete billed costs remain unverified.

## Recompute and render

`live-evidence.json` includes sanitized task-level scores, costs, timings, batch
timestamps, and SHA-256 hashes of original local JSONL artifacts. The renderer
recomputes the summary from those rows and checks it matches the saved summary.

```sh
uv run --with pillow python docs/pr-7-evidence/live_report.py
```

Rendering uses macOS Arial fonts. To re-export from the original local audit
artifacts, add `--source results/performance-audit/live-preview/gpqa-pr7`.
That export requires every completed batch and the local sampled answer keys.

## Limits

This is only PR #7's nonstreaming GPQA path, not the full dataset, HLE, streaming,
agentic benchmarks, other PRs, or confirmation of advertised website scores.
Costs are API-response values, not independently verified billing. Latencies
include task wall time and may vary with provider load. The existing controlled
failure reproduction separately demonstrates the stale-results bug and fix.
