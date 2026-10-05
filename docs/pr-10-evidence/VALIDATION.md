# Follow-up validation

Reran the checked-in reproduction on October 1, 2026:

```sh
uv run --with openai python docs/pr-10-evidence/reproduce.py
uv run --with pillow python docs/pr-10-evidence/render.py
```

All assertions passed. The checked-in evidence and image come from this rerun.
It launches the real proxy from each exact commit and then runs the real HLE
benchmark entry point through it with controlled local endpoints. The same 40
items run against each revision: 20 LF streams and 20 CRLF streams.

| Outcome | Before | After |
| --- | ---: | ---: |
| LF responses correct | 20/20 | 20/20 |
| CRLF responses correct | 0/20 | 20/20 |
| CRLF empty-response errors | 20 | 0 |
| Correct responses with usage | LF only | LF and CRLF |

The reproduction also feeds identical LF and CRLF payloads to the parser at
every two-chunk split and one byte at a time. Before the fix, 356/356 CRLF
partitions lose the answer; after the fix, 356/356 recover it. LF remains 348/348
in both versions.

## Scope and limits

This is a controlled wire-framing test, not an external model call. It validates
that CRLF-delimited SSE streams are preserved and LF behavior is unchanged. It
does not measure live Pareto accuracy, use the gated HLE dataset, validate an
agentic benchmark, or verify advertised website scores. Docker was unavailable,
so no agentic benchmark was run.
