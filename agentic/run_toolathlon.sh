#!/usr/bin/env bash
# =============================================================================
# Toolathlon-Verified (HKUST-NLP) — agentic tool-use / MCP orchestration, 108 tasks.
#
# The v2 slate's tool-use entry (featured in GLM-5.3, Grok 4.6 via APEX, DeepSeek-V4-Pro,
# GPT-5.6 Sol). The `main` branch IS the Verified release — all 108 tasks in
# tasks/finalpool/ are the verified set (there is no split flag).
#
# EASIEST path (used here): the maintainers' PUBLIC EVAL SERVICE hosts every tool
# environment, so you need no Docker, no MCP servers, and no external accounts —
# just eval_client.py + simple_client_ws.py from the repo. Your endpoint/key are
# tunneled over a WebSocket proxy in --mode private and never leave your machine.
#
# Prereqs:  git clone https://github.com/hkust-nlp/Toolathlon   (into $TOOLATHLON_DIR)
#           pip install httpx typer websockets
#
# Point it at your model:
#   MODEL_BASE_URL=https://your-endpoint/v1  MODEL_API_KEY=sk-...  MODEL_NAME=your-model \
#     ./run_toolathlon.sh
#
# Score: average_success_rate (Pass@1) over 108 tasks, in <out>/eval_stats.json.
#
# NOTE: The public service rate-limits to 180 min cumulative execution per IP / 24h.
#       A full 108-task run exceeds that, so for a complete run use a dedicated
#       instance (email jlini@cse.ust.hk) or the full local Path B (see repo README:
#       needs Docker + real Google/GitHub/HF/Snowflake/Serper accounts).
# LICENSING: the repo ships NO license file (GitHub reports license: null). Tasks are
#       downloaded from upstream at run time; review terms before redistributing.
# =============================================================================
set -euo pipefail

MODEL_BASE_URL="${MODEL_BASE_URL:?set MODEL_BASE_URL (OpenAI-compatible /v1 base)}"
MODEL_API_KEY="${MODEL_API_KEY:-dummy}"
MODEL_NAME="${MODEL_NAME:-your-model}"
TOOLATHLON_DIR="${TOOLATHLON_DIR:-./Toolathlon}"
OUT="${OUT:-toolathlon_$(date -u +%Y%m%d-%H%M%S)}"
CONC="${CONC:-10}"                              # public service caps workers at 10
SERVER_HOST="${TOOLATHLON_SERVER_HOST:-47.253.6.47}"
SERVER_PORT="${TOOLATHLON_SERVER_PORT:-8080}"
WS_PROXY_PORT="${TOOLATHLON_WS_PROXY_PORT:-8081}"
# --mode private tunnels a non-public endpoint through the WS proxy (key never leaves
# the box). Use --mode public only for a genuinely public API (e.g. api.openai.com).
MODE="${TOOLATHLON_MODE:-private}"
# Optional: a newline-delimited task-name file to run a subset (smoke test).
TASK_LIST_ARGS=()
if [ -n "${TOOLATHLON_TASK_LIST:-}" ]; then
  TASK_LIST_ARGS=(--task-list-file "$TOOLATHLON_TASK_LIST")
fi

if [ ! -f "$TOOLATHLON_DIR/eval_client.py" ]; then
  echo "ERROR: $TOOLATHLON_DIR/eval_client.py not found. Clone it first:" >&2
  echo "  git clone https://github.com/hkust-nlp/Toolathlon $TOOLATHLON_DIR" >&2
  exit 1
fi

echo "Toolathlon-Verified: model=$MODEL_NAME  mode=$MODE  workers=$CONC  out=$OUT"
# `eval_client.py run` submits the job, starts a detached worker that serves model
# calls (private mode tunnels them over a WebSocket) + downloads results, and returns
# immediately. We `setsid` it so the worker survives this shell exiting, then poll
# `status` until the job reaches a terminal state — otherwise the worker's process
# group is SIGHUP'd the moment the wrapper returns and the job stalls with no model.
# The server handles ONE job at a time, so a stale job must be cancelled first.
RUN_LOG="$(mktemp)"
( cd "$TOOLATHLON_DIR" && setsid python eval_client.py run \
    --mode "$MODE" \
    --base-url "$MODEL_BASE_URL" \
    --model-name "$MODEL_NAME" \
    --api-key "$MODEL_API_KEY" \
    --output-dir "$OUT" \
    --server-host "$SERVER_HOST" \
    --server-port "$SERVER_PORT" \
    --ws-proxy-port "$WS_PROXY_PORT" \
    --workers "$CONC" \
    "${TASK_LIST_ARGS[@]}" ) 2>&1 | tee "$RUN_LOG"

JOB_ID="$(grep -oE 'job_[a-f0-9]+' "$RUN_LOG" | head -1)"
if [ -z "$JOB_ID" ]; then
  echo "ERROR: could not parse a Job ID from the run output (see above)." >&2
  rm -f "$RUN_LOG"; exit 1
fi

echo "Polling job $JOB_ID until complete (worker runs detached; safe to Ctrl-C — reattach with"
echo "  cd $TOOLATHLON_DIR && python eval_client.py status --job-id $JOB_ID --server-host $SERVER_HOST --server-port $SERVER_PORT)"
DEADLINE=$(( $(date +%s) + ${TOOLATHLON_MAX_WAIT:-7200} ))
while :; do
  S="$(cd "$TOOLATHLON_DIR" && python eval_client.py status \
        --job-id "$JOB_ID" --server-host "$SERVER_HOST" --server-port "$SERVER_PORT" 2>&1)"
  ST="$(printf '%s\n' "$S" | sed -nE 's/.*Status: *([A-Za-z]+).*/\1/p' | head -1 | tr 'A-Z' 'a-z')"
  echo "  status=${ST:-unknown}  ($(date -u +%H:%M:%S)Z)"
  case "$ST" in completed|failed|cancelled|error) break ;; esac
  if [ "$(date +%s)" -ge "$DEADLINE" ]; then echo "  ! timed out waiting (job still $ST)"; break; fi
  sleep 30
done
rm -f "$RUN_LOG"

STATS="$TOOLATHLON_DIR/$OUT/eval_stats.json"
if [ -f "$STATS" ]; then
  python3 -c "import json;d=json.load(open('$STATS'));print('Done. average_success_rate =', d.get('average_success_rate'))"
else
  echo "Done (status=$ST). eval_stats.json not present yet at $STATS — poll status manually."
fi
