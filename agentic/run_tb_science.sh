#!/usr/bin/env bash
# =============================================================================
# Terminal-Bench-Science (TB-Science) via the `harbor` runner.
#
# 70 expert-curated research-workflow tasks (life / physical / earth / mathematical /
# engineering sciences; Apache-2.0; harbor-framework/terminal-bench-science, v0.1.0
# released 2026-08) graded strictly pass/fail by each task's own verifier. One of the
# three OPEN suites of Nous Research's Hermes Index (2026-10-06), which runs it inside
# the Hermes Agent harness — so the agent here defaults to `hermes` (see
# harbor_agents/hermes_agent.py). TB_AGENT=terminus-2 gives harbor's reference agent
# (the TB-Science leaderboard itself pairs models with claude-code / codex).
#
# Prereqs:  uv tool install 'harbor[modal]'   # >= 0.24.0 for the hermes agent
#           Docker running, or TB_ENV=modal.   No GPU: none of the 70 tasks asks for one.
#           Agent containers need internet (Hermes installs itself in each one).
#
#   MODEL_BASE_URL=https://your-endpoint/v1  MODEL_API_KEY=sk-...  MODEL_NAME=your-model \
#     ./run_tb_science.sh
#
# Knobs: TBSCI_VERSION=0.1.0 (Harbor Hub tag; 70 tasks), TB_AGENT (hermes | terminus-2 |
#        dirac | any harbor agent / import path), CONC, TB_ENV (docker | modal), OUT,
#        LIMIT, TASKS_FILE / TB_EXCLUDE_FILE (one task name per line), the HERMES_* knobs
#        in harbor_agents/resolve_agent.sh, MODEL_MAX_INPUT_TOKENS (terminus only).
#
# Score: resolved/total across <out>/*/*/result.json (verifier_result.rewards.reward == 1).
#        Tasks have their own agent timeouts (most 8h) — no global multiplier is imposed.
# =============================================================================
set -euo pipefail

command -v harbor >/dev/null 2>&1 || export PATH="$HOME/.local/bin:$PATH"

MODEL_BASE_URL="${MODEL_BASE_URL:?set MODEL_BASE_URL (OpenAI-compatible /v1 base)}"
MODEL_API_KEY="${MODEL_API_KEY:-dummy}"
MODEL_NAME="${MODEL_NAME:-your-model}"     # harbor/litellm/hermes see this as openai/$MODEL_NAME
AGENT="${TB_AGENT:-hermes}"
CONC="${CONC:-4}"
ENV_MODE="${TB_ENV:-docker}"
OUT="${OUT:-tbsci_$(date -u +%Y%m%d-%H%M%S)}"
TBSCI_VERSION="${TBSCI_VERSION:-0.1.0}"
DATASET="terminal-bench-science/terminal-bench-science@$TBSCI_VERSION"
LIMIT="${LIMIT:-70}"

export OPENAI_API_BASE="$MODEL_BASE_URL" OPENAI_BASE_URL="$MODEL_BASE_URL" OPENAI_API_KEY="$MODEL_API_KEY"

EXTRA=()
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harbor_agents/resolve_agent.sh
source "$SCRIPT_DIR/harbor_agents/resolve_agent.sh"
resolve_harbor_agent

# terminus agents only: register the served context window so proactive summarization
# fires (see run_tb.sh for the why).
if [ -n "${MODEL_MAX_INPUT_TOKENS:-}" ] && [[ "$AGENT" == terminus* ]]; then
  EXTRA+=(--agent-kwarg "model_info={\"max_input_tokens\": ${MODEL_MAX_INPUT_TOKENS}, \"max_output_tokens\": ${MODEL_MAX_OUTPUT_TOKENS:-32768}}")
fi

# Hub task names are namespaced ("terminal-bench-science/<task>"); pass both spellings.
if [ -n "${TASKS_FILE:-}" ]; then
  while IFS= read -r t; do [ -n "$t" ] && EXTRA+=(--include-task-name "$t" --include-task-name "terminal-bench-science/$t"); done < "$TASKS_FILE"
fi
if [ -n "${TB_EXCLUDE_FILE:-}" ]; then
  while IFS= read -r t; do [ -n "$t" ] && EXTRA+=(--exclude-task-name "$t" --exclude-task-name "terminal-bench-science/$t"); done < "$TB_EXCLUDE_FILE"
fi

echo "TB-Science $TBSCI_VERSION: dataset=$DATASET  agent=$AGENT  model=openai/$MODEL_NAME  limit=$LIMIT  conc=$CONC  env=$ENV_MODE  out=$OUT"
harbor run \
  -d "$DATASET" \
  -a "$AGENT" \
  -m "openai/$MODEL_NAME" \
  -l "$LIMIT" -n "$CONC" \
  -e "$ENV_MODE" \
  ${EXTRA[@]+"${EXTRA[@]}"} \
  --yes -o "$OUT"

echo "Done. Score = resolved/total across $OUT/*/*/result.json (verifier_result.rewards.reward == 1)."
echo "      Hermes Index: python3 $SCRIPT_DIR/hermes_index.py --tbsci $OUT --summary"
