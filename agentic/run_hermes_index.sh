#!/usr/bin/env bash
# =============================================================================
# Hermes Index — run the three OPEN suites through the Hermes Agent harness and
# extrapolate the full index (score + $/task). One command:
#
#   MODEL_BASE_URL=https://your-endpoint/v1  MODEL_API_KEY=sk-...  MODEL_NAME=your-model \
#   MODEL_INPUT_PRICE_PER_MTOK=3  MODEL_OUTPUT_PRICE_PER_MTOK=15 \
#     ./agentic/run_hermes_index.sh
#
# Nous Research's Hermes Index (2026-10-06, portal.nousresearch.com/bench) = mean score
# (and mean $/task) over four suites, all run inside Hermes Agent at pass@1 with
# reasoning effort high: Hermes Bench (closed, 150 tasks), Terminal-Bench 4.0 without
# its GPU tasks (63), Terminal-Bench-Science 0.1 (70) and SkillsBench clean (87 minus
# leaked). This runs the three open ones:
#
#   tb4     run_tb.sh          TB_VERSION=4.0, GPU tasks excluded (as Nous), TB_AGENT=hermes
#   tbsci   run_tb_science.sh  TBSCI_VERSION=0.1.0,                          TB_AGENT=hermes
#   skills  run_skillsbench.sh skills surfaced to Hermes,                    TB_AGENT=hermes
#
# then calls hermes_index.py, which measures the three, predicts Hermes Bench from
# them (fit on the published leaderboard, leave-one-out error printed) and reports
# the estimated index, $/task and leaderboard rank.
#
# Prereqs: Docker + harbor >= 0.24.0 (uv tool install 'harbor[modal]>=0.24.0'); task
# containers need internet (Hermes installs itself in each, ~6-10 min/container).
# Against Pareto, start strip_proxy.py first and point MODEL_BASE_URL at it (see README).
# Per-task $ comes from harbor token counts × MODEL_*_PRICE_PER_MTOK (Hermes reports
# tokens, not cost); or pass a strip_proxy USAGE_LOG per suite to hermes_index.py.
#
# Knobs: SUITES="tb4 tbsci skills" (subset), HERMES_INDEX_OUT (parent dir), CONC,
#        TB_ENV (docker|modal — note modal would INCLUDE TB4's GPU tasks; keep docker or
#        set TB_INCLUDE_GPU=0 semantics via docker), HERMES_REASONING / HERMES_VERSION /
#        HERMES_MAX_TURNS / HERMES_AGENT_KWARGS, plus every per-wrapper knob.
# A suite that fails is reported and the others still run; the estimate needs all three.
# =============================================================================
set -uo pipefail   # not -e: one failing suite must not abort the others
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MODEL_BASE_URL="${MODEL_BASE_URL:?set MODEL_BASE_URL (OpenAI-compatible /v1 base)}"
MODEL_API_KEY="${MODEL_API_KEY:-dummy}"
MODEL_NAME="${MODEL_NAME:?set MODEL_NAME}"
SUITES="${SUITES:-tb4 tbsci skills}"; SUITES="${SUITES//,/ }"
OUT_ROOT="${HERMES_INDEX_OUT:-hermes_index_$(date -u +%Y%m%d-%H%M%S)}"
mkdir -p "$OUT_ROOT"
export TB_AGENT="${TB_AGENT:-hermes}"
if [ "$TB_AGENT" != "hermes" ]; then
  echo "WARNING: TB_AGENT=$TB_AGENT — the Hermes Index is defined on the Hermes Agent harness; the estimate will not be comparable." >&2
fi
if [ "${TB_INCLUDE_GPU:-0}" = "1" ] || [ "${TB_ENV:-docker}" = "modal" ]; then
  echo "WARNING: TB4 would include its GPU tasks (Nous runs 63 tasks without them)." >&2
fi
if [ -z "${MODEL_INPUT_PRICE_PER_MTOK:-}" ] || [ -z "${MODEL_OUTPUT_PRICE_PER_MTOK:-}" ]; then
  echo "NOTE: MODEL_INPUT_PRICE_PER_MTOK / MODEL_OUTPUT_PRICE_PER_MTOK unset — scores will be estimated, \$/task will not (add prices or --usage-log later)." >&2
fi

declare -A STATUS
echo "Hermes Index: model=$MODEL_NAME  agent=$TB_AGENT  suites='$SUITES'  out=$OUT_ROOT"
for s in $SUITES; do
  echo; echo "══ $s ══"
  case "$s" in
    tb4)    OUT="$OUT_ROOT/tb4"    TB_VERSION=4.0 "$HERE/run_tb.sh" ;;
    tbsci)  OUT="$OUT_ROOT/tbsci"  "$HERE/run_tb_science.sh" ;;
    skills) OUT="$OUT_ROOT/skills" "$HERE/run_skillsbench.sh" ;;
    *) echo "!! unknown suite '$s' (tb4|tbsci|skills)" >&2; STATUS[$s]=unknown; continue ;;
  esac
  rc=$?
  STATUS[$s]=$([ $rc -eq 0 ] && echo ok || echo "FAILED($rc)")
done

echo; echo "══ suites ══"
for s in $SUITES; do printf "  %-7s %s\n" "$s" "${STATUS[$s]:-skipped}"; done

ARGS=()
[ -d "$OUT_ROOT/tb4" ]    && ARGS+=(--tb4 "$OUT_ROOT/tb4")
[ -d "$OUT_ROOT/tbsci" ]  && ARGS+=(--tbsci "$OUT_ROOT/tbsci")
[ -d "$OUT_ROOT/skills" ] && ARGS+=(--skills "$OUT_ROOT/skills")
if [ ${#ARGS[@]} -eq 0 ]; then echo "nothing to score"; exit 1; fi
echo; python3 "$HERE/hermes_index.py" "${ARGS[@]}" --label "$MODEL_NAME" --json "$OUT_ROOT/hermes_index.json" --summary-if-partial \
  | tee "$OUT_ROOT/hermes_index.md"
