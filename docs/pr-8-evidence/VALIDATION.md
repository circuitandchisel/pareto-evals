# Follow-up validation

Reran `uv run --with openai python docs/pr-8-evidence/reproduce.py` and
`uv run --with pillow python docs/pr-8-evidence/render.py` on October 1, 2026.
The checked-in evidence and image come from this rerun, not estimated values.

All 160 synthetic task executions completed without task errors: two exact
code revisions, each tested on 40 items with no judge and with a local HTTP 503
judge outage. In each condition:

- Before: 20/20 blank model responses incorrectly earned credit.
- After: 0/20 blank model responses earned credit.
- All 10 correct nonblank answers remain correct; all 10 wrong answers remain wrong.
- The score changes from 75% to 25% by removing false credit, not by worsening
  the model. The model responses are controlled and identical between revisions.

Reference answers are valid, nonblank answer keys. This reproduces the actual
blank-candidate bug through the real HLE command and local HTTP endpoints.

## Live validation status

This is **not** a live Pareto HLE benchmark. The local workspace has no HLE
dataset, and the prior dataset preflight returned a gated-access error for
`cais/hle`. An independent judge is also required for publication-quality HLE
scores. We did not replace it with Pareto judging itself or treat containment
fallback scores as comparable to the advertised benchmark.

The GPQA live run for PR #7 does not validate this HLE-specific grading change.
Full HLE accuracy/noninferiority and advertised-score parity remain unverified.
