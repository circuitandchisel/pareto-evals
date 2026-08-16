#!/usr/bin/env bash
# =============================================================================
# Terminal-Bench (agentic terminal tasks) via the `harbor` runner.
#
# The only benchmark featured in ALL FIVE 2026 launches (GLM-5.3, Grok 4.6,
# DeepSeek-V4-Pro, Fable 5, GPT-5.6 Sol). TB isn't a run.py benchmark — it uses
# the external `harbor` harness + a reference agent driving your model over an
# OpenAI-compatible endpoint. This wraps the exact invocation so it's reproducible.
#
# v2 runs BOTH versions:
#   * 3.0  — the current frontier version (74 tasks, 7 domains). Where the spread
#            is: frontier models score ~34-43%, so it discriminates. HUB-ONLY id
#            `terminal-bench/terminal-bench@3.0.0`. THIS IS THE DEFAULT.
#   * 2.1  — near-saturated for frontier models (~87-92%) but maximally comparable
#            to prior published numbers. Legacy-registry id.
# Select with TB_VERSION=3.0 (default) or TB_VERSION=2.1.
#
# Prereqs:  uv tool install 'harbor[modal]'   (or: pip install harbor; https://github.com/harbor-framework/harbor)
#           # Use CURRENT harbor (>= v0.21.0). TB 3.0 needs the new task.toml schema
#           # (separate verifier containers); a TB-2.1-era install will not grade it.
#           Docker running (tasks execute in containers), or --env modal.
#
# Point it at your model:
#   MODEL_BASE_URL=https://your-endpoint/v1  MODEL_API_KEY=sk-...  MODEL_NAME=your-model \
#     ./run_tb.sh
#
# Score: fraction of tasks the agent resolves (verifier reward == 1), computed from
#        each trial's result.json (verifier_result.rewards.reward == 1).
# =============================================================================
set -euo pipefail

MODEL_BASE_URL="${MODEL_BASE_URL:?set MODEL_BASE_URL (OpenAI-compatible /v1 base)}"
MODEL_API_KEY="${MODEL_API_KEY:-dummy}"
MODEL_NAME="${MODEL_NAME:-your-model}"     # harbor/litellm sees this as openai/$MODEL_NAME
AGENT="${TB_AGENT:-terminus-2}"            # harbor's reference agent (BYO model via LiteLLM)
CONC="${CONC:-4}"                          # harbor -n / --n-concurrent
ENV_MODE="${TB_ENV:-docker}"               # docker (default) or modal
OUT="${OUT:-tb_$(date -u +%Y%m%d-%H%M%S)}"
TB_VERSION="${TB_VERSION:-3.0}"

export OPENAI_API_BASE="$MODEL_BASE_URL" OPENAI_BASE_URL="$MODEL_BASE_URL" OPENAI_API_KEY="$MODEL_API_KEY"

EXTRA=()
case "$TB_VERSION" in
  3.0)
    DATASET="terminal-bench/terminal-bench@3.0.0"
    DEFAULT_LIMIT=74
    # TB 3.0 has 4 GPU-only tasks that fail on a plain Docker box. Exclude them
    # unless the sandbox has a GPU (set TB_INCLUDE_GPU=1 or use --env modal).
    if [ "${TB_INCLUDE_GPU:-0}" != "1" ] && [ "$ENV_MODE" != "modal" ]; then
      EXTRA+=(--exclude-task-names 'fp8-rmsnorm-gemm' \
              --exclude-task-names 'math-eval-grader' \
              --exclude-task-names 'exam-pdf-eval' \
              --exclude-task-names 'jax-speedrun-gpu')
      echo "NOTE: excluding TB3's 4 GPU tasks (set TB_INCLUDE_GPU=1 or TB_ENV=modal to include)." >&2
    fi
    # TB3 tasks set their own timeouts (up to 8h); do NOT impose a global multiplier.
    ;;
  2.1)
    DATASET="terminal-bench/terminal-bench-2-1"
    DEFAULT_LIMIT=89
    EXTRA+=(--agent-timeout-multiplier "${AGENT_TIMEOUT_MULTIPLIER:-3}")
    ;;
  *)
    echo "ERROR: TB_VERSION must be 3.0 or 2.1 (got '$TB_VERSION')." >&2; exit 1 ;;
esac
LIMIT="${LIMIT:-$DEFAULT_LIMIT}"

echo "TB-$TB_VERSION: dataset=$DATASET  agent=$AGENT  model=openai/$MODEL_NAME  limit=$LIMIT  conc=$CONC  env=$ENV_MODE  out=$OUT"
harbor run \
  -d "$DATASET" \
  -a "$AGENT" \
  -m "openai/$MODEL_NAME" \
  -l "$LIMIT" -n "$CONC" \
  -e "$ENV_MODE" \
  "${EXTRA[@]}" \
  --yes -o "$OUT"

echo "Done. Score = resolved/total across $OUT/*/*/result.json (verifier_result.rewards.reward == 1)."
