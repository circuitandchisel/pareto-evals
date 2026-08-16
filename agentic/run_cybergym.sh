#!/usr/bin/env bash
# =============================================================================
# CyberGym (UC Berkeley, sunblaze-ucb) — agentic vulnerability reproduction.
#
# The v2 slate's cybersecurity entry. Cybersecurity was the newest featured
# category across the 2026 launches (GLM-5.3's headline theme; also in
# DeepSeek-V4-Pro and GPT-5.6 Sol), and CyberGym is its clearly-OPEN, defensively
# framed representative: given a pre-patch codebase + vuln info, the agent must
# produce a PoC that crashes the pre-patch build but NOT the post-patch build.
# 1,507 real OSS vulns (from OSS-Fuzz/ARVO), Apache-2.0.
#
# BRING-YOUR-OWN AGENT: CyberGym scores PoCs; the agent scaffold is separate
# (OpenHands / Codex / EnIGMA / Cybench from sunblaze-ucb/cybergym-agent-examples).
# This wraps the loop: start the scoring server, run the chosen agent over a task
# set at level1 (the reported difficulty), then aggregate. Reads your model over an
# OpenAI-compatible endpoint via LLM_BASE_URL + OPENAI_API_KEY + --model.
#
# Prereqs:  pip3 install -e '.[dev,server]'   (in a clone of sunblaze-ucb/cybergym)
#           build an agent image (see cybergym-agent-examples), Docker running.
#           task data: python scripts/server_data/download_subset.py  (10-task smoke;
#           binary-only ~130GB or full ~10TB for the complete set).
#
#   MODEL_BASE_URL=https://your-endpoint/v1  MODEL_API_KEY=sk-...  MODEL_NAME=your-model \
#     ./run_cybergym.sh
#
# Score: fraction of tasks with a successful PoC (report the final-submission
#        metric for comparability), via scripts/verify_agent_result.py.
#
# SAFETY: CyberGym's own guidance — deploy everything locally, never expose the
#         server to the public internet; agents run firewalled on cybergym-internal.
# =============================================================================
set -euo pipefail

MODEL_BASE_URL="${MODEL_BASE_URL:?set MODEL_BASE_URL (OpenAI-compatible /v1 base)}"
MODEL_API_KEY="${MODEL_API_KEY:-dummy}"
MODEL_NAME="${MODEL_NAME:-your-model}"
CYBERGYM_DIR="${CYBERGYM_DIR:-.}"                       # clone of sunblaze-ucb/cybergym
CYBERGYM_DATA_DIR="${CYBERGYM_DATA_DIR:?set CYBERGYM_DATA_DIR (downloaded task data)}"
AGENT="${CYBERGYM_AGENT:-openhands}"                    # openhands|codex|enigma|cybench
AGENT_RUNNER="${CYBERGYM_AGENT_RUNNER:-examples/agents/$AGENT/run.py}"
DIFFICULTY="${CYBERGYM_DIFFICULTY:-level1}"             # level0..level3; level1 is reported
OUT="${OUT:-cybergym_$(date -u +%Y%m%d-%H%M%S)}"
MAX_ITER="${CYBERGYM_MAX_ITER:-100}"
POC_DIR="${POC_SAVE_DIR:-$OUT/server_poc}"
PORT="${CYBERGYM_PORT:-8666}"
# Bind the server to the Docker gateway, never 0.0.0.0 (see SAFETY above).
HOST="${CYBERGYM_HOST:-$(docker network inspect cybergym-internal \
        -f '{{(index .IPAM.Config 0).Gateway}}' 2>/dev/null || echo 127.0.0.1)}"
# Task IDs: newline/space-delimited file, or the built-in 10-task smoke subset.
TASKS_FILE="${CYBERGYM_TASKS_FILE:-}"
SMOKE_TASKS="arvo:47101 arvo:3938 arvo:24993 arvo:1065 arvo:10400 arvo:368 \
oss-fuzz:42535201 oss-fuzz:42535468 oss-fuzz:370689421 oss-fuzz:385167047"
export CYBERGYM_API_KEY="${CYBERGYM_API_KEY:-cybergym-local-$(id -u)}"
export OPENAI_API_KEY="$MODEL_API_KEY" LLM_BASE_URL="$MODEL_BASE_URL"

if [ -n "$TASKS_FILE" ]; then
  read -r -a TASKS <<< "$(tr '\n' ' ' < "$TASKS_FILE")"
else
  echo "NOTE: no CYBERGYM_TASKS_FILE set — using the 10-task smoke subset." >&2
  read -r -a TASKS <<< "$SMOKE_TASKS"
fi

mkdir -p "$POC_DIR"
echo "CyberGym: model=$MODEL_NAME  agent=$AGENT  diff=$DIFFICULTY  tasks=${#TASKS[@]}  out=$OUT"
echo "  starting scoring server on http://$HOST:$PORT ..."
python3 -m cybergym.server --host "$HOST" --port "$PORT" \
  --mask_map_path "$CYBERGYM_DIR/mask_map.json" \
  --log_dir "$POC_DIR" --db_path "$POC_DIR/poc.db" &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT
sleep 5

for TASK_ID in "${TASKS[@]}"; do
  echo "  ▶ $TASK_ID"
  python3 "$CYBERGYM_DIR/$AGENT_RUNNER" \
    --model "$MODEL_NAME" \
    --log_dir "$OUT/logs" \
    --tmp_dir "$OUT/tmp" \
    --task_id "$TASK_ID" \
    --data_dir "$CYBERGYM_DATA_DIR" \
    --max_iter "$MAX_ITER" \
    --server "http://$HOST:$PORT" \
    --difficulty "$DIFFICULTY" || echo "    ! $TASK_ID errored (continuing)"
done

echo "Aggregating..."
python3 "$CYBERGYM_DIR/scripts/verify_agent_result.py" \
  --server "http://$HOST:$PORT" \
  --pocdb_path "$POC_DIR/poc.db" \
  --agent_id "${CYBERGYM_AGENT_ID:-$AGENT}" || true

echo "Done. Score = fraction of tasks with a successful PoC (final-submission metric)."
