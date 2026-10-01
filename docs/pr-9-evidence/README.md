# PR #9: actual-command regression evidence

```sh
uv run --with openai python docs/pr-9-evidence/reproduce.py
uv run --with pillow python docs/pr-9-evidence/render.py
```

The reproducer exports the exact before/after commits and runs
`python -m benchmarks.hle` against local model and judge fixtures. Two correct
tasks are sufficient to isolate the denominator error: one reports $0.10, the
other omits cost. This is a deterministic regression test, not a statistical
estimate of model quality or actual billed spend. No external API calls.

`original-evidence.json` preserves the earlier run used in the PR table.
`evidence.json` captures the reproducible rerun, including revisions, commands,
output, summaries, per-task results, and HTTP request counts. `render.py` reads
the rerun observations to create `before-after.png`. Both runs agree: $0.05
before, $0.10 after, with 1/2 cost coverage and 2/2 correct answers unchanged.
