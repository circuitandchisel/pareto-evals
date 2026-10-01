# Follow-up validation

Reran the checked-in reproduction on October 1, 2026:

```sh
uv run --with openai python docs/pr-9-evidence/reproduce.py
uv run --with pillow python docs/pr-9-evidence/render.py
```

All assertions passed. The checked-in image and evidence come from that rerun.
Both versions execute the actual benchmark entry point with controlled local
model and judge endpoints. Scores remain 2/2; the cost formula alone changes.

## Real-data replay

The PR #7 live GPQA audit saved 100 task rows per arm, each with a response-reported
`cost_usd`. Replaying those unchanged rows through the two formulas gives the
same result because all 200 tasks are priced:

| Arm | Tasks / priced tasks | Known subtotal | Before formula | After formula |
| --- | ---: | ---: | ---: | ---: |
| Before | 100 / 100 | $0.44146241 | $0.0044146241 | $0.0044146241 |
| After | 100 / 100 | $0.46195564 | $0.0046195564 | $0.0046195564 |

Replay source: local, gitignored original artifacts at
`results/performance-audit/live-preview/gpqa-pr7/runs/`. Export:
`results/performance-audit/live-preview/gpqa-pr7/pr9-real-cost-replay.json`.
The replay does not call the API or alter task outputs.

## Interpretation

At full observed cost coverage, this PR cannot change the reported mean. With
partial coverage, it intentionally reports the known-cost mean instead of treating
unknown costs as zero. That is a reporting correction, not a model accuracy change.
It does not independently verify Pareto benchmark accuracy or advertised scores.
