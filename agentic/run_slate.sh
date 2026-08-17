#!/usr/bin/env bash
# =============================================================================
# v2 agentic slate — run the whole slate in one swoop.
#
# The 2026 launch benchmarks (DeepSWE, Terminal-Bench 3.0, Toolathlon, CyberGym)
# each run under their own harness via a ./run_*.sh wrapper. This is the one-command
# alias that runs all four against a single model and prints a combined summary.
# It only orchestrates the individual wrappers — each is still runnable on its own,
# and every env knob those wrappers document still works (it's inherited here).
#
#   MODEL_BASE_URL=https://your-endpoint/v1  MODEL_API_KEY=sk-...  MODEL_NAME=your-model \
#     ./agentic/run_slate.sh
#
# Prereqs are the union of the four wrappers' prereqs (Docker + harbor + pier +
# .../ the CyberGym clone & data). See the per-benchmark sections in this README.
# Against the Pareto endpoint you also need strip_proxy.py (see the proxy section);
# point the slate at it with the per-benchmark base-URL overrides below.
#
# Knobs:
#   SLATE="deepswe tb"                 # subset (space/comma list; default: all four)
#   SLATE_OUT=slate_<UTC>              # parent output dir (per-benchmark subdirs under it)
#   <NAME>_MODEL_BASE_URL=...          # per-benchmark base-URL override (NAME in
#                                      #   DEEPSWE|TB|TOOLATHLON|CYBERGYM). DeepSWE needs
#                                      #   this when using the strip proxy — pier's egress
#                                      #   allows only ports 80/443, so run the proxy on a
#                                      #   safe port and set DEEPSWE_MODEL_BASE_URL to it.
# Any benchmark that fails is reported and the slate continues to the next one.
# =============================================================================
set -uo pipefail   # deliberately NOT -e: one failing benchmark must not abort the slate
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MODEL_BASE_URL="${MODEL_BASE_URL:?set MODEL_BASE_URL (OpenAI-compatible /v1 base)}"
MODEL_API_KEY="${MODEL_API_KEY:-dummy}"
MODEL_NAME="${MODEL_NAME:?set MODEL_NAME}"
SLATE="${SLATE:-deepswe tb toolathlon cybergym}"
SLATE="${SLATE//,/ }"
OUT_ROOT="${SLATE_OUT:-slate_$(date -u +%Y%m%d-%H%M%S)}"
mkdir -p "$OUT_ROOT"

# name -> wrapper script
declare -A SCRIPT=(
  [deepswe]=run_deepswe.sh
  [tb]=run_tb.sh
  [toolathlon]=run_toolathlon.sh
  [cybergym]=run_cybergym.sh
)
declare -A STATUS RESULT

echo "v2 agentic slate: model=$MODEL_NAME  benchmarks='$SLATE'  out=$OUT_ROOT"

for name in $SLATE; do
  script="${SCRIPT[$name]:-}"
  if [ -z "$script" ]; then
    echo "!! unknown slate member '$name' (known: ${!SCRIPT[*]})" >&2
    STATUS[$name]="unknown"; continue
  fi
  # per-benchmark base-URL override: <NAME>_MODEL_BASE_URL
  ov_var="${name^^}_MODEL_BASE_URL"
  base="${!ov_var:-$MODEL_BASE_URL}"
  log="$OUT_ROOT/$name.log"
  echo; echo "==================== $name ===================="
  # OUT is honored by deepswe/tb/cybergym as-is; toolathlon resolves it under
  # TOOLATHLON_DIR, so give it a plain name and record where its stats land.
  case "$name" in
    toolathlon) out_arg="${name}_$(date -u +%H%M%S)" ;;
    *)          out_arg="$OUT_ROOT/$name" ;;
  esac
  MODEL_BASE_URL="$base" MODEL_API_KEY="$MODEL_API_KEY" MODEL_NAME="$MODEL_NAME" OUT="$out_arg" \
    bash "$HERE/$script"
  rc=$?
  STATUS[$name]=$([ "$rc" -eq 0 ] && echo ok || echo "FAIL(rc=$rc)")
  RESULT[$name]="$out_arg"
done

echo; echo "==================== slate summary ===================="
printf '%-12s %-12s %s\n' BENCHMARK STATUS OUTPUT
for name in $SLATE; do
  printf '%-12s %-12s %s\n' "$name" "${STATUS[$name]:-skipped}" "${RESULT[$name]:-}"
done
echo
echo "Per-benchmark headline metric lives in each output dir (see the sections in"
echo "agentic/README.md): deepswe */verifier/reward.json · tb */*/result.json ·"
echo "toolathlon <TOOLATHLON_DIR>/<out>/eval_stats.json · cybergym verify stdout in $OUT_ROOT/cybergym.* ."
