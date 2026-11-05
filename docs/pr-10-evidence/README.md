# PR #10: actual proxy and benchmark evidence

```sh
uv run --with openai python docs/pr-10-evidence/reproduce.py
uv run --with pillow python docs/pr-10-evidence/render.py
```

The reproducer exports exact before/after commits. For each version it launches
the real `agentic/strip_proxy.py` process with `UPSTREAM_STREAM=1`, then runs
`python -m benchmarks.hle` through it. The local upstream fixture returns
`ANSWER: 4` in every response, with 20 LF streams and 20 CRLF streams per version
(80 benchmark task executions total). A separate local judge returns YES.

Before: all 20 CRLF responses become empty responses and error; 20 LF tasks pass.
After: all 40 tasks pass, with correct content, finish reason, and token usage.
Both benchmark commands exit 0 because this harness records per-item errors
rather than exiting nonzero. The improvement is in recorded task outcomes, not
the benchmark process exit code.

The same script imports the exact parser from each revision and tests every
two-chunk split plus byte-at-a-time reads: 348 LF and 356 CRLF partitions per
version. The fixed parser recovers content and usage in all 704 cases. This
direct parser check makes chunk boundaries deterministic; HTTP buffering alone
does not guarantee where reads will split.

`evidence.json` records revisions, commands, stdout/stderr, proxy logs, summaries,
per-task results, endpoint counts, and parser split checks. `render.py` derives
the image from those observations. This is a synthetic regression test, not a
live Pareto benchmark or a claim of improved model reasoning. No credentials
or external model calls are needed.
