#!/bin/bash
# One-command eval SLICE with a machine-readable verdict (gpu-router#185).
#
# Runs seeded representative subsamples of the non-agentic benchmarks against
# an endpoint and writes verdicts/verdict-<tag>-<ts>.json. Same instrument for
# three uses:
#   - deploy gate:   slice `pareto` (baseline) vs `pareto-next` (candidate),
#                    then: python -m harness.verdict compare base.json cand.json
#   - model card:    verdict JSON is the citable record (config hash + numbers)
#   - regression:    re-run the same tag/seed after serving changes
#
# Usage (candidate via the router's standing staging model):
#   ATXP_MODEL_BASE_URL=https://gpu-router.corp.circuitandchisel.com/v1 \
#   ATXP_MODEL_API_KEY=$KEY ATXP_MODEL_NAME=pareto-next \
#   SLICE_TAG=identity-prompt PARETO_APP_COMMIT=<sha> ./run_slice.sh
#
# Knobs: BENCHES (default "gpqa arxiv_math hle"), LIMIT (default 30),
#        LIMIT_SEED (default 0 — keep it fixed so slices stay comparable),
#        CONC, RC_ENV (path to the rc.env under test, hashed into the verdict).
set -euo pipefail
cd "$(dirname "$0")"
PY="${PY:-.venv/bin/python}"

export ATXP_MODEL_BASE_URL="${ATXP_MODEL_BASE_URL:?set the endpoint under test}"
export ATXP_MODEL_NAME="${ATXP_MODEL_NAME:?set the model under test (pareto | pareto-next | route)}"
export LIMIT="${LIMIT:-30}"
export LIMIT_SEED="${LIMIT_SEED:-0}"
export CONC="${CONC:-4}"
BENCHES="${BENCHES:-gpqa arxiv_math hle}"
TAG="${SLICE_TAG:-slice}"
TS=$(date -u +%Y%m%dT%H%M%SZ)
RESULTS="results/slice-$TAG-$TS"
mkdir -p "$RESULTS" verdicts

echo "slice: model=$ATXP_MODEL_NAME endpoint=$ATXP_MODEL_BASE_URL"
echo "       benches=[$BENCHES] LIMIT=$LIMIT seed=$LIMIT_SEED -> $RESULTS"

for bench in $BENCHES; do
  echo "=== $bench ==="
  case "$bench" in
    hle) HLE_MODE=no_tools OUT_DIR="$RESULTS" "$PY" -m benchmarks.hle ;;
    *)   OUT_DIR="$RESULTS" "$PY" -m "benchmarks.$bench" ;;
  esac || { echo "FATAL: $bench failed — no verdict without every gated bench" >&2; exit 1; }
done

"$PY" -m harness.verdict collect \
  --results "$RESULTS" \
  --out "verdicts/verdict-$TAG-$TS.json" \
  --tag "$TAG" \
  ${RC_ENV:+--config-file "$RC_ENV"}
