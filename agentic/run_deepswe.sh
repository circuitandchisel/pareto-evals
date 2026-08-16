#!/usr/bin/env bash
# =============================================================================
# DeepSWE v1.1 (Datacurve) — long-horizon agentic coding, 113 hand-written tasks.
#
# The new cross-lab consensus SWE-agent benchmark: featured in the GLM-5.3,
# Grok 4.6, DeepSeek-V4-Pro, and GPT-5.6 Sol launches. Contamination-resistant
# (original specs, not mined PRs) and still has headroom (frontier ~62-74%), so
# it's the v2 replacement for SWE-bench Verified (which no 2026 launch featured).
#
# It's a repo of Harbor-format tasks run by `pier` (Datacurve's Harbor fork) with
# the reference `mini-swe-agent` driving your model over an OpenAI-compatible
# endpoint. Not a run.py benchmark — this wraps the exact invocation.
#
# Prereqs:  uv tool install datacurve-pier   (or: pip install datacurve-pier)
#           # v1.1 grading needs pier > 0.3.0 (separate verifier container)
#           git clone https://github.com/datacurve-ai/deep-swe   (into $DEEPSWE_DIR)
#           Docker running (per-task images pulled from public ECR; NO GPU).
#
# Point it at your model:
#   MODEL_BASE_URL=https://your-endpoint/v1  MODEL_API_KEY=sk-...  MODEL_NAME=your-model \
#     ./run_deepswe.sh
#
# Score: mean `reward` (binary 0/1 per task) over the 113 tasks — printed by pier
#        at end of run and in <jobs>/<job>/result.json (stats.evals[...].metrics).
# =============================================================================
set -euo pipefail

MODEL_BASE_URL="${MODEL_BASE_URL:?set MODEL_BASE_URL (OpenAI-compatible /v1 base)}"
MODEL_API_KEY="${MODEL_API_KEY:-dummy}"
MODEL_NAME="${MODEL_NAME:-your-model}"          # pier/litellm sees this as openai/$MODEL_NAME
DEEPSWE_DIR="${DEEPSWE_DIR:-./deep-swe}"        # git clone of datacurve-ai/deep-swe
CONC="${CONC:-4}"
OUT="${OUT:-deepswe_$(date -u +%Y%m%d-%H%M%S)}"
ENV_MODE="${DEEPSWE_ENV:-docker}"               # docker (default) or modal
# Chat-Completions endpoints must override the Responses-API default that the
# `openai/` model prefix selects. Set DEEPSWE_CHAT=1 for vLLM/sglang-style servers.
CHAT_OVERRIDE=()
if [ "${DEEPSWE_CHAT:-1}" = "1" ]; then
  CHAT_OVERRIDE=(--ak model_class=litellm)
fi

# mini-swe-agent reads these from the host env, injects them into the sandbox, and
# auto-allowlists the base URL (tasks are otherwise no-network).
export OPENAI_API_KEY="$MODEL_API_KEY" MSWEA_API_KEY="$MODEL_API_KEY"
export OPENAI_BASE_URL="$MODEL_BASE_URL" OPENAI_API_BASE="$MODEL_BASE_URL"

if [ ! -d "$DEEPSWE_DIR/tasks" ]; then
  echo "ERROR: $DEEPSWE_DIR/tasks not found. Clone it first:" >&2
  echo "  git clone https://github.com/datacurve-ai/deep-swe $DEEPSWE_DIR" >&2
  exit 1
fi

echo "DeepSWE v1.1: model=openai/$MODEL_NAME  conc=$CONC  env=$ENV_MODE  out=$OUT"
pier run \
  -p "$DEEPSWE_DIR/tasks" \
  --agent mini-swe-agent \
  --model "openai/$MODEL_NAME" \
  "${CHAT_OVERRIDE[@]}" \
  -n "$CONC" \
  -e "$ENV_MODE" \
  -o "$OUT" ${LIMIT:+-l "$LIMIT"}

echo "Done. Score = mean reward over trials in $OUT/*/verifier/reward.json"
echo "       (or read stats.evals[...].metrics[0].reward in $OUT/result.json)."
