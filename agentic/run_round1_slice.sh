#!/usr/bin/env bash
# =============================================================================
# Re-run the ROUND-1 comparison slice (2026-08-21/22: Pareto 26.8 CF+EC2 vs
# OpenRouter Auto vs Ramp Router vs Fable/Sol/Sonnet/Cursor) against ONE new
# OpenAI-compatible endpoint, on exactly the same items.
#
# The slice, pinned in agentic/round1_slice/*.txt and by seed:
#   QA      gpqa=100 hle=40 arxiv_math=30 mmmu_pro=30   (run.py, LIMIT_SEED=0 draw)
#   SWE-V   10 + 10 instances (swev_set1 / swev_set2; SWE_FILTER_IDS)
#   DeepSWE 10 core tasks (all arms) + 20 extension tasks (Ramp was n=10 only)
#   TB 3.0  5 tasks, terminus-2, CONC=2
# Prior arms live on pareto-bench under ~/eval-lanes/<arm>/results (QA),
# ~/pareto-evals/results/round1_swev*_<arm>.jsonl, ~/pareto-evals/round1_deepswe*_<arm>,
# ~/pareto-evals/round1_tb_<arm>.  Ramp Router == arm "router" (model router-ladder).
#
# Usage (on the box, from ~/pareto-evals):
#   NAME=newmodel MODEL_BASE_URL=https://.../v1 MODEL_API_KEY=... MODEL_NAME=vendor/model \
#   [LABEL=NewModel] [PHASES="qa swev deepswe tb"] [DEEPSWE_N=30|10] [MODEL_MAX_TOKENS=32000] \
#   [PARALLEL=1] [QA_CONC=4 SWEV_CONC=2 DS_CONC=2 TB_CONC=2] [QA_BENCHES=gpqa,hle,arxiv_math,mmmu_pro] \
#   [MODEL_INPUT_PRICE_PER_MTOK=.. MODEL_OUTPUT_PRICE_PER_MTOK=..] \
#     bash agentic/run_round1_slice.sh
#
# Notes
#  * MODEL_MAX_TOKENS defaults to 32000: the final Round-1 table used the 32k-cap
#    reruns for HLE (all arms) and for Ramp's ArXiv-Math; the first pass was 8192.
#  * If the endpoint 400s on temperature/stop/top_p (Pareto-style), point
#    MODEL_BASE_URL at agentic/strip_proxy.py instead of the raw endpoint.
#  * Prices are only needed when the endpoint doesn't return usage.cost.
#  * PARALLEL=1 runs the selected phases concurrently (QA is API-bound; the three
#    agentic legs are docker-bound) instead of back to back. Round-1 used CONC=4/2/2/2.
#  * QA_BENCHES restricts the QA leg, e.g. to finish a lane whose gpqa already completed.
# =============================================================================
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/.." && pwd)"; LISTS="$HERE/round1_slice"
NAME="${NAME:?set NAME (short arm tag, e.g. newmodel)}"
MODEL_BASE_URL="${MODEL_BASE_URL:?}"; MODEL_API_KEY="${MODEL_API_KEY:?}"; MODEL_NAME="${MODEL_NAME:?}"
LABEL="${LABEL:-$NAME}"
PHASES="${PHASES:-qa swev deepswe tb}"
DEEPSWE_N="${DEEPSWE_N:-30}"
export MODEL_MAX_TOKENS="${MODEL_MAX_TOKENS:-32000}"
PARALLEL="${PARALLEL:-0}"
QA_CONC="${QA_CONC:-4}"; SWEV_CONC="${SWEV_CONC:-2}"; DS_CONC="${DS_CONC:-2}"; TB_CONC="${TB_CONC:-2}"
QA_BENCHES="${QA_BENCHES:-gpqa,hle,arxiv_math,mmmu_pro}"
LANE="${LANE_DIR:-$HOME/eval-lanes/$NAME}"; mkdir -p "$LANE/results"
export PATH="$PATH:$HOME/.local/bin"
cd "$ROOT" && source .venv/bin/activate
has() { case " $PHASES " in *" $1 "*) return 0;; *) return 1;; esac; }
log() { echo "=== [$NAME] $(date -u +%H:%M:%S) $*"; }
export MODEL_BASE_URL MODEL_API_KEY MODEL_NAME
[ -n "${MODEL_INPUT_PRICE_PER_MTOK:-}" ]  && export MODEL_INPUT_PRICE_PER_MTOK  PARETO_INPUT_PRICE_PER_MTOK="$MODEL_INPUT_PRICE_PER_MTOK"
[ -n "${MODEL_OUTPUT_PRICE_PER_MTOK:-}" ] && export MODEL_OUTPUT_PRICE_PER_MTOK PARETO_OUTPUT_PRICE_PER_MTOK="$MODEL_OUTPUT_PRICE_PER_MTOK"

phase_qa() {
  local slice; slice="$(python3 -c "import sys; m={'gpqa':100,'hle':40,'arxiv_math':30,'mmmu_pro':30}; print(','.join(f'{b}={m[b]}' for b in '$QA_BENCHES'.split(',')))")"
  log "QA $slice (seed 0, conc $QA_CONC, max_tokens $MODEL_MAX_TOKENS) -> $LANE/results"
  EVAL_RESULTS_DIR="$LANE/results" \
  PARETO_BASE_URL="$MODEL_BASE_URL" PARETO_API_KEY="$MODEL_API_KEY" PARETO_MODEL="$MODEL_NAME" PARETO_LABEL="$LABEL" \
  PARETO_MAX_TOKENS="$MODEL_MAX_TOKENS" \
    python -u run.py --benchmarks "$QA_BENCHES" \
      --slice "$slice" --seed 0 --concurrency "$QA_CONC" \
      --models pareto --out "$LANE/results/round1_$NAME.md"
  log "QA done (exit $?)"
}

phase_swev() {
  for set in 1 2; do
    ids="$(paste -sd, "$LISTS/swev_set$set.txt")"
    rn="round1_swev_$NAME"; [ "$set" = 2 ] && rn="round1_swev2_$NAME"
    log "SWE-Verified set $set (10 instances) -> results/$rn.jsonl"
    SWE_MINI_BIN="${SWE_MINI_BIN:-$ROOT/.venv-mini/bin/mini-extra}" SWE_FILTER_IDS="$ids" RESULT_NAME="$rn" CONC="$SWEV_CONC" \
      python -u agentic/run_swe_verified.py
    log "SWE-Verified set $set done (exit $?)"
  done
}

phase_deepswe() {
  tf="$LANE/deepswe_tasks.txt"; cat "$LISTS/deepswe_core10.txt" > "$tf"
  [ "$DEEPSWE_N" = 30 ] && cat "$LISTS/deepswe_extra20.txt" >> "$tf"
  log "DeepSWE $(wc -l < "$tf") pinned tasks -> round1_deepswe_$NAME"
  TASKS_FILE="$tf" CONC="$DS_CONC" OUT="round1_deepswe_$NAME" bash agentic/run_deepswe.sh
  log "DeepSWE done (exit $?)"
}

phase_tb() {
  log "Terminal-Bench 3.0, 5 pinned tasks (conc $TB_CONC) -> round1_tb_$NAME"
  TB_VERSION=3.0 TASKS_FILE="$LISTS/tb3_5.txt" LIMIT=5 CONC="$TB_CONC" OUT="round1_tb_$NAME" bash agentic/run_tb.sh
  log "TB3 done (exit $?)"
}

pids=()
for ph in qa swev deepswe tb; do
  has "$ph" || continue
  if [ "$PARALLEL" = 1 ]; then
    "phase_$ph" > "$LANE/phase_$ph.log" 2>&1 & pids+=($!)
    log "started phase $ph in background (pid ${pids[-1]}, log $LANE/phase_$ph.log)"
  else
    "phase_$ph"
  fi
done
[ "${#pids[@]}" -gt 0 ] && wait "${pids[@]}"
echo "ROUND1-SLICE-$NAME-COMPLETE"
