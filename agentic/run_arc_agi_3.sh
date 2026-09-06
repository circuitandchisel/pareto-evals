#!/usr/bin/env bash
# =============================================================================
# ARC-AGI-3 (interactive reasoning) via the OFFICIAL arcprize/arc-agi-3-benchmarking
# harness — the same agent + scoring ARC Prize uses for its verified leaderboard.
#
# ARC-AGI-3 replaced the static ARC-AGI-2 grids with turn-based game environments:
# no instructions, no stated goal — the agent explores a 64x64 grid world, works out
# the rules, and clears levels. 135 games total; 25 are PUBLIC (free API key) and the
# other 110 are semi-private/private (only ARC Prize can run them). This wrapper runs
# the public 25, which is what anyone outside ARC Prize can reproduce. Public-set
# numbers are NOT directly comparable to the leaderboard's semi-private numbers.
#
# The harness hard-codes ONLINE mode: games are served by ARC Prize's hosted API and
# every scorecard is stored on their server (browse at arcprize.org/scorecards). It
# talks to your model through the `openai` Python SDK, so any OpenAI-compatible
# Chat-Completions endpoint works. Only the keys listed under `request:` in the
# generated config are sent (model, max_completion_tokens[, reasoning_effort]) —
# no temperature/top_p/stop, so Pareto's strict sampler is fine without the proxy.
#
# Prereqs:  git clone https://github.com/arcprize/arc-agi-3-benchmarking  (into $ARC3_DIR)
#           cd arc-agi-3-benchmarking && uv venv -p 3.12 && uv sync      (needs Python >= 3.12)
#           ARC_API_KEY  — free; register at https://arcprize.org (Platform -> API key)
#
# Point it at your model:
#   ARC_API_KEY=arc-... MODEL_BASE_URL=https://your-endpoint/v1 MODEL_API_KEY=sk-... \
#   MODEL_NAME=your-model ./run_arc_agi_3.sh
#
# Knobs:
#   ARC3_GAMES="ls20,ft09"     comma list of game_id prefixes (default: all public games)
#   CONC=5                     games played concurrently per harness invocation. Each game
#                              is one model call in flight, so CONC == max in-flight calls.
#                              Games are run in batches of CONC (one scorecard per batch).
#   MAX_TOKENS=32768           request.max_completion_tokens (official configs use 128k;
#                              Pareto's cap is 32768)
#   ARC3_REASONING_EFFORT=     optional request.reasoning_effort (e.g. high) — only if
#                              your endpoint accepts it
#   ARC3_MULTIPLIER=5.0        MAX_ACTIONS_BASELINE_MULTIPLIER — per-level action budget as
#                              a multiple of the human baseline. 5.0 is the official value
#                              and matches the scoring cutoff (beyond 5x scores 0 anyway).
#   ARC3_MAX_CONTEXT=175000    MAX_CONTEXT_LENGTH (official value); lower for small-ctx models
#   ARC3_MAX_RUNTIME_SECONDS=  optional per-game wall-clock cap (harness default: none).
#                              Budgets are large (ls20 allows 3,880 actions; each is a model
#                              call over a ~50k-token transcript), so set this for smoke tests
#                              (e.g. 1500) — the game ends as TIMEOUT and still scores.
#   ARC3_TAGS=                 extra comma-separated scorecard tags
#   ARC3_DIR=./arc-agi-3-benchmarking   harness checkout;  ARC3_PYTHON=$ARC3_DIR/.venv/bin/python
#
# Score: mean over games of the per-game score (0-100). Per level the harness awards
#        min(1, human_baseline_actions / agent_actions)^2, later levels weighted more, and
#        averages across games — i.e. "Relative Human Action Efficiency"; 100 = as
#        efficient as the human baseline on every level of every game. Frontier models at
#        launch (2026-03) scored < 1 on the semi-private set. Reported in
#        <out>/summary.json (+ per-batch scorecard_N.json and the harness's per-step
#        recordings under <out>/recordings/).
# =============================================================================
set -euo pipefail

MODEL_BASE_URL="${MODEL_BASE_URL:?set MODEL_BASE_URL (OpenAI-compatible /v1 base)}"
MODEL_API_KEY="${MODEL_API_KEY:-dummy}"
MODEL_NAME="${MODEL_NAME:?set MODEL_NAME}"
ARC_API_KEY="${ARC_API_KEY:?set ARC_API_KEY (free at https://arcprize.org — the hosted game API needs it; anonymous is 401)}"
ARC3_DIR="${ARC3_DIR:-./arc-agi-3-benchmarking}"
PYBIN="${ARC3_PYTHON:-$ARC3_DIR/.venv/bin/python}"
OUT="${OUT:-arc3_$(date -u +%Y%m%d-%H%M%S)}"
CONC="${CONC:-5}"
MAX_TOKENS="${MAX_TOKENS:-32768}"
ARC3_MULTIPLIER="${ARC3_MULTIPLIER:-5.0}"
ARC3_MAX_CONTEXT="${ARC3_MAX_CONTEXT:-175000}"
ARC3_GAMES="${ARC3_GAMES:-}"
ARC3_TAGS="${ARC3_TAGS:-}"

if [ ! -f "$ARC3_DIR/main.py" ] || [ ! -f "$ARC3_DIR/benchmarking/model_configs.yaml" ]; then
  echo "ERROR: $ARC3_DIR does not look like arc-agi-3-benchmarking. Clone it first:" >&2
  echo "  git clone https://github.com/arcprize/arc-agi-3-benchmarking $ARC3_DIR" >&2
  echo "  (cd $ARC3_DIR && uv venv -p 3.12 && uv sync)" >&2
  exit 1
fi
if [ ! -x "$PYBIN" ]; then
  echo "ERROR: $PYBIN not found. Create the harness venv: (cd $ARC3_DIR && uv venv -p 3.12 && uv sync)" >&2
  exit 1
fi

OUT="$(mkdir -p "$OUT" && cd "$OUT" && pwd)"   # absolute — we cd into the harness dir below
ARC3_DIR="$(cd "$ARC3_DIR" && pwd)"
CFG_ID="pareto-evals-$(printf '%s' "$MODEL_NAME" | tr -c 'A-Za-z0-9._' '-')"

# The model key is read from an env var NAMED in the config (client.api_key_env).
export PARETO_EVALS_MODEL_API_KEY="$MODEL_API_KEY" ARC_API_KEY

# --- 1. Inject our model config into the harness's model_configs.yaml -----------------
# (model_config.py only reads benchmarking/model_configs.yaml — no override path.) We keep
# the official entries and (re)place any prior `pareto-evals-*` entry. Keep a pristine copy.
[ -f "$ARC3_DIR/benchmarking/model_configs.yaml.orig" ] || \
  cp "$ARC3_DIR/benchmarking/model_configs.yaml" "$ARC3_DIR/benchmarking/model_configs.yaml.orig"
CFG_ID="$CFG_ID" MODEL_BASE_URL="$MODEL_BASE_URL" MODEL_NAME="$MODEL_NAME" MAX_TOKENS="$MAX_TOKENS" \
ARC3_MULTIPLIER="$ARC3_MULTIPLIER" ARC3_MAX_CONTEXT="$ARC3_MAX_CONTEXT" \
ARC3_REASONING_EFFORT="${ARC3_REASONING_EFFORT:-}" ARC3_MAX_RUNTIME_SECONDS="${ARC3_MAX_RUNTIME_SECONDS:-}" \
"$PYBIN" - "$ARC3_DIR/benchmarking/model_configs.yaml" <<'PY'
import os, sys, yaml
path = sys.argv[1]
cfgs = [c for c in (yaml.safe_load(open(path)) or []) if not str(c.get("id", "")).startswith("pareto-evals-")]
agent = {"MAX_ACTIONS_BASELINE_MULTIPLIER": float(os.environ["ARC3_MULTIPLIER"]),
         "MAX_CONTEXT_LENGTH": int(os.environ["ARC3_MAX_CONTEXT"])}
if os.environ.get("ARC3_MAX_RUNTIME_SECONDS"):
    agent["MAX_RUNTIME_SECONDS"] = float(os.environ["ARC3_MAX_RUNTIME_SECONDS"])
request = {"model": os.environ["MODEL_NAME"], "max_completion_tokens": int(os.environ["MAX_TOKENS"])}
if os.environ.get("ARC3_REASONING_EFFORT"):
    request["reasoning_effort"] = os.environ["ARC3_REASONING_EFFORT"]
cfgs.append({
    "id": os.environ["CFG_ID"],
    "agent": agent,
    # Standard harness (provider-neutral text history) — the mode ARC Prize uses for
    # cross-provider comparisons. NOT the provider-adapter/continuous-conversation mode.
    "runtime": {"sdk": "openai-python", "api": "chat_completions", "state": "manual_rolling"},
    "client": {"base_url": os.environ["MODEL_BASE_URL"], "api_key_env": "PARETO_EVALS_MODEL_API_KEY"},
    "request": request,
    "pricing": {},
})
yaml.safe_dump(cfgs, open(path, "w"), sort_keys=False)
print(f"config {os.environ['CFG_ID']}: base_url={os.environ['MODEL_BASE_URL']} model={os.environ['MODEL_NAME']} "
      f"max_completion_tokens={os.environ['MAX_TOKENS']} agent={agent}")
PY
# Validate: the harness parses + validates every entry when listing.
( cd "$ARC3_DIR" && "$PYBIN" main.py --list-configs ) | grep -qx -- "- $CFG_ID" \
  || { echo "ERROR: injected config $CFG_ID failed the harness's validation." >&2; exit 1; }

# --- 2. Resolve the game list from the hosted API ------------------------------------
mapfile -t ALL_GAMES < <( cd "$ARC3_DIR" && "$PYBIN" main.py --list-games 2>/dev/null | sed -nE 's/^- +//p' )
if [ "${#ALL_GAMES[@]}" -eq 0 ]; then
  echo "ERROR: the API returned no games. Check ARC_API_KEY (and ARC_BASE_URL if set)." >&2
  ( cd "$ARC3_DIR" && "$PYBIN" main.py --list-games ) >&2 || true
  exit 1
fi
GAMES=()
if [ -n "$ARC3_GAMES" ]; then
  IFS=',' read -r -a WANT <<< "$ARC3_GAMES"
  for g in "${ALL_GAMES[@]}"; do
    for w in "${WANT[@]}"; do [[ "$g" == "$w"* ]] && { GAMES+=("$g"); break; }; done
  done
  [ "${#GAMES[@]}" -gt 0 ] || { echo "ERROR: no game matches ARC3_GAMES='$ARC3_GAMES' (available: ${ALL_GAMES[*]})" >&2; exit 1; }
else
  GAMES=("${ALL_GAMES[@]}")
fi

TAGS="pareto-evals,$MODEL_NAME${ARC3_TAGS:+,$ARC3_TAGS}"
echo "ARC-AGI-3 (public set): model=$MODEL_NAME  games=${#GAMES[@]}/${#ALL_GAMES[@]}  conc=$CONC  max_tokens=$MAX_TOKENS  multiplier=$ARC3_MULTIPLIER  out=$OUT"
echo "games: ${GAMES[*]}"
mkdir -p "$OUT/recordings"

# --- 3. Play in batches of CONC (the harness plays every game it is given in parallel) --
BATCH=0
for ((i = 0; i < ${#GAMES[@]}; i += CONC)); do
  BATCH=$((BATCH + 1))
  CHUNK=("${GAMES[@]:i:CONC}")
  CHUNK_CSV="$(IFS=','; echo "${CHUNK[*]}")"
  LOG="$OUT/batch_${BATCH}.log"
  echo; echo "== batch $BATCH: ${CHUNK[*]}  ($(date -u +%H:%M:%S)Z) -> $LOG"
  # run_dir is hard-coded to ./recordings/<name>.<uuid> under the harness cwd, so diff
  # the directory before/after and move the new run dirs into $OUT.
  mkdir -p "$ARC3_DIR/recordings"   # absent on a fresh clone; `ls | sort` would trip pipefail
  BEFORE="$(mktemp)"; ls -1 "$ARC3_DIR/recordings" | sort > "$BEFORE"
  set +e
  # PYTHONUNBUFFERED: the harness logs to stdout, which is block-buffered through the tee pipe.
  ( cd "$ARC3_DIR" && PYTHONUNBUFFERED=1 "$PYBIN" main.py --config="$CFG_ID" --game="$CHUNK_CSV" --tags="$TAGS" ) 2>&1 | tee "$LOG"
  rc=${PIPESTATUS[0]}
  set -e
  [ "$rc" -eq 0 ] || echo "!! harness exited rc=$rc for batch $BATCH (see $LOG)" >&2
  comm -13 "$BEFORE" <(ls -1 "$ARC3_DIR/recordings" | sort) | while read -r d; do
    mv "$ARC3_DIR/recordings/$d" "$OUT/recordings/"
  done
  rm -f "$BEFORE"
  [ -f "$ARC3_DIR/logs.log" ] && cp "$ARC3_DIR/logs.log" "$OUT/batch_${BATCH}.harness.log"
  # Pull the FINAL SCORECARD REPORT JSON out of the log (logged as one multi-line record).
  "$PYBIN" - "$LOG" "$OUT/scorecard_${BATCH}.json" <<'PY'
import json, re, sys
log, dst = sys.argv[1], sys.argv[2]
lines = open(log, encoding="utf-8", errors="replace").read().splitlines()
idx = max((i for i, l in enumerate(lines) if "--- FINAL SCORECARD REPORT ---" in l), default=None)
if idx is None:
    print(f"!! no FINAL SCORECARD REPORT in {log} (batch failed before the scorecard closed)"); sys.exit(0)
first = re.sub(r"^.*?\| (INFO|DEBUG|WARNING|ERROR) \| ", "", lines[idx + 1])
buf = [first]
for l in lines[idx + 2:]:
    buf.append(l)
    if l == "}":
        break
try:
    card = json.loads("\n".join(buf))
except Exception as e:
    print(f"!! could not parse scorecard JSON from {log}: {e}"); sys.exit(0)
url = next((l.split("View your scorecard online: ", 1)[1].strip() for l in lines if "View your scorecard online:" in l), None)
card["_scorecard_url"] = url
json.dump(card, open(dst, "w"), indent=2)
envs = card.get("environments", [])
print(f"batch scorecard: score={card.get('score')}  games={len(envs)}  url={url}")
PY
done

# --- 4. Aggregate ------------------------------------------------------------------------
"$PYBIN" - "$OUT" "$MODEL_NAME" <<'PY'
import glob, json, os, sys
out, model = sys.argv[1], sys.argv[2]
games, urls = [], []
for f in sorted(glob.glob(os.path.join(out, "scorecard_*.json"))):
    card = json.load(open(f))
    if card.get("_scorecard_url"): urls.append(card["_scorecard_url"])
    for env in card.get("environments", []):
        runs = env.get("runs") or []
        best = max(runs, key=lambda r: r.get("score", 0.0)) if runs else {}
        games.append({
            "game_id": env.get("id"),
            "score": env.get("score", best.get("score", 0.0)),
            "levels_completed": env.get("levels_completed", best.get("levels_completed", 0)),
            "levels": env.get("level_count", best.get("number_of_levels")),
            "actions": env.get("actions", best.get("actions", 0)),
            "completed": env.get("completed", best.get("completed", False)),
            "state": best.get("state"),
        })
n = len(games)
summary = {
    "benchmark": "arc_agi_3_public",
    "model": model,
    "games": n,
    "score": (sum(g["score"] for g in games) / n) if n else None,   # 0-100, mean over games
    "games_completed": sum(1 for g in games if g["completed"]),
    "levels_completed": sum(g["levels_completed"] for g in games),
    "levels_total": sum(g["levels"] or 0 for g in games),
    "actions_total": sum(g["actions"] for g in games),
    "scorecard_urls": urls,
    "per_game": games,
}
json.dump(summary, open(os.path.join(out, "summary.json"), "w"), indent=2)
print()
print(f"{'GAME':<16} {'SCORE':>7} {'LEVELS':>8} {'ACTIONS':>8}  STATE")
for g in games:
    print(f"{str(g['game_id']):<16} {g['score']:>7.2f} {str(g['levels_completed'])+'/'+str(g['levels']):>8} {g['actions']:>8}  {g['state']}")
if n:
    print(f"\nDone. ARC-AGI-3 (public {n} games) score = {summary['score']:.2f} / 100   "
          f"games completed {summary['games_completed']}/{n}, levels {summary['levels_completed']}/{summary['levels_total']}")
else:
    print("\nDone, but no scorecards were produced — see the batch logs.")
print(f"summary: {os.path.join(out, 'summary.json')}")
for u in urls: print(f"scorecard: {u}")
PY
