#!/usr/bin/env bash
# =============================================================================
# Terminal-Bench (agentic terminal tasks) via the `harbor` runner.
#
# The only benchmark featured in ALL FIVE 2026 launches (GLM-5.3, Grok 4.6,
# DeepSeek-V4-Pro, Fable 5, GPT-5.6 Sol). TB isn't a run.py benchmark — it uses
# the external `harbor` harness + a reference agent driving your model over an
# OpenAI-compatible endpoint. This wraps the exact invocation so it's reproducible.
#
# Three versions are selectable (TB is now a continuous, semver'd benchmark):
#   * 4.0  — CURRENT (released 2026-08-26): 3.0 minus 8 tasks (saturated / refusals /
#            leaked solutions / quality) = 66 tasks, 19 tasks fixed, resources (time,
#            cpu, memory) calibrated and a flat 8h agent timeout on every task, so
#            timeouts/errors are rarer than 3.0. Hub id `terminal-bench/terminal-bench@4.0.0`.
#            THIS IS THE DEFAULT. Scores are NOT comparable to 3.0 (task set changed).
#   * 3.0  — the 2026-launch version (74 tasks, 7 domains; frontier ~34-43%). Keep for
#            comparing against the five launch posts. Hub id `...@3.0.0`.
#   * 2.1  — near-saturated for frontier models (~87-92%) but maximally comparable
#            to prior published numbers. Legacy-registry id.
# Select with TB_VERSION=4.0 (default), 3.0, or 2.1.
#
# Prereqs:  uv tool install 'harbor[modal]'   (harbor is NOT on PyPI as `pip install
#           harbor`; use uv. https://github.com/harbor-framework/harbor)
#           # Use CURRENT harbor (>= v0.21.0; 4.0 verified with v0.21.0). TB 3.0/4.0 use
#           # the newer task.toml schema (separate verifier containers, schema 1.1);
#           # a TB-2.1-era install will not grade them.
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
TB_VERSION="${TB_VERSION:-4.0}"

export OPENAI_API_BASE="$MODEL_BASE_URL" OPENAI_BASE_URL="$MODEL_BASE_URL" OPENAI_API_KEY="$MODEL_API_KEY"

EXTRA=()
# GPU-only tasks (task.toml `gpus = 1`, H100) fail on a plain Docker box. Excluded unless
# the sandbox has a GPU (TB_INCLUDE_GPU=1 or --env modal). Task names are namespaced
# ("terminal-bench/<task>"), so bare-name excludes silently DON'T match (a bare exclude
# let math-eval-grader schedule and crash a whole run on GPU allocation) — exclude BOTH.
exclude_gpu_tasks() {
  if [ "${TB_INCLUDE_GPU:-0}" != "1" ] && [ "$ENV_MODE" != "modal" ]; then
    for gt in "$@"; do
      EXTRA+=(--exclude-task-name "$gt" --exclude-task-name "terminal-bench/$gt")
    done
    echo "NOTE: excluding TB-$TB_VERSION's $# GPU tasks ($*); set TB_INCLUDE_GPU=1 or TB_ENV=modal to include." >&2
  fi
}
case "$TB_VERSION" in
  4.0)
    DATASET="terminal-bench/terminal-bench@4.0.0"
    DEFAULT_LIMIT=66
    # 4.0 dropped exam-pdf-eval; three H100 tasks remain.
    exclude_gpu_tasks fp8-rmsnorm-gemm math-eval-grader jax-speedrun-gpu
    # Every 4.0 task has a flat 8h agent timeout baked in; do NOT impose a global multiplier.
    ;;
  3.0)
    DATASET="terminal-bench/terminal-bench@3.0.0"
    DEFAULT_LIMIT=74
    exclude_gpu_tasks fp8-rmsnorm-gemm math-eval-grader exam-pdf-eval jax-speedrun-gpu
    # TB3 tasks set their own timeouts (up to 8h); do NOT impose a global multiplier.
    ;;
  2.1)
    DATASET="terminal-bench/terminal-bench-2-1"
    DEFAULT_LIMIT=89
    EXTRA+=(--agent-timeout-multiplier "${AGENT_TIMEOUT_MULTIPLIER:-3}")
    ;;
  *)
    echo "ERROR: TB_VERSION must be 4.0, 3.0 or 2.1 (got '$TB_VERSION')." >&2; exit 1 ;;
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
