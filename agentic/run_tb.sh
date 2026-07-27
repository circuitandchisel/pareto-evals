#!/usr/bin/env bash
# =============================================================================
# Terminal-Bench 2.1 (agentic terminal tasks) via the `harbor` runner.
#
# TB isn't a run.py benchmark — it uses the external `harbor` harness + the
# `terminus-2` agent driving your model over an OpenAI-compatible endpoint.
# This wraps the exact invocation so it's reproducible.
#
# Prereqs:  pip install harbor    (https://github.com/laude-institute/harbor)
#           Docker running (tasks execute in containers).
#
# Point it at your model:
#   MODEL_BASE_URL=https://your-endpoint/v1  MODEL_API_KEY=sk-...  MODEL_NAME=your-model \
#     ./run_tb.sh
#
# Score: fraction of tasks the agent resolves (verifier reward == 1).
# =============================================================================
set -euo pipefail

MODEL_BASE_URL="${MODEL_BASE_URL:?set MODEL_BASE_URL (OpenAI-compatible /v1 base)}"
MODEL_API_KEY="${MODEL_API_KEY:-dummy}"
MODEL_NAME="${MODEL_NAME:-your-model}"     # harbor sees this as openai/$MODEL_NAME
LIMIT="${LIMIT:-89}"                        # 89 = full TB-2.1 set
CONC="${CONC:-4}"
TIMEOUT_MULT="${AGENT_TIMEOUT_MULTIPLIER:-3}"
OUT="${OUT:-tb_$(date -u +%Y%m%d-%H%M%S)}"

export OPENAI_API_BASE="$MODEL_BASE_URL" OPENAI_BASE_URL="$MODEL_BASE_URL" OPENAI_API_KEY="$MODEL_API_KEY"

echo "TB-2.1: model=openai/$MODEL_NAME  limit=$LIMIT  conc=$CONC  out=$OUT"
harbor run \
  -d terminal-bench/terminal-bench-2-1 \
  -a terminus-2 \
  -m "openai/$MODEL_NAME" \
  -l "$LIMIT" -n "$CONC" \
  --agent-timeout-multiplier "$TIMEOUT_MULT" \
  --yes -o "$OUT"

echo "Done. Score = resolved/total across $OUT/*/*/result.json (verifier_result.rewards.reward == 1)."
