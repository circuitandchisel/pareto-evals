# PR #8: actual-command regression evidence

Run from the repository root:

```sh
uv run --with openai python docs/pr-8-evidence/reproduce.py
uv run --with pillow python docs/pr-8-evidence/render.py
```

The reproducer exports the exact before/after commits into temporary directories
and runs `python -m benchmarks.hle` against controlled local HTTP endpoints.
Each version runs the same 40 synthetic tasks twice: without a judge, then with a
judge returning HTTP 503. There are 20 blank answers, 10 correct answers, and 10
wrong answers per run (160 task executions total). The SDK retries failed judge
requests twice; the evidence counts HTTP requests including those retries.

`evidence.json` records revisions, commands, exit codes, full stdout/stderr,
per-task results, summaries, and endpoint request counts. `render.py` reads those
observations to produce `before-after.png`. This is a regression test, not a live
Pareto accuracy measurement. No credentials or external model calls are needed.
The existing nonempty containment fallback remains unsuitable for publication.
