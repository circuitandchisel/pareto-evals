#!/bin/bash
# Run the non-agentic benchmarks end-to-end against the RC endpoint.
# Agentic benchmarks (SWE-Bench Pro, Terminal-Bench 2.1, Finance Agent v2, DRACO,
# HLE-with-tools) run via their own harnesses — see agentic/README.md.
set -e
cd "$(dirname "$0")"
PY="${PY:-.venv/bin/python}"   # venv built on python3.12 (uv-managed); math-verify needs 3.10+
export ATXP_MODEL_BASE_URL="${ATXP_MODEL_BASE_URL:-http://localhost:8097/v1}"
export ATXP_MODEL_API_KEY="${ATXP_MODEL_API_KEY:-dummy}"
export ATXP_MODEL_NAME="${ATXP_MODEL_NAME:-route}"
export CONC="${CONC:-4}"
echo "RC endpoint: $ATXP_MODEL_BASE_URL  (model=$ATXP_MODEL_NAME)"

for bench in arc_agi_2 hmmt_2026 mmmu_pro; do
  echo "=== $bench ==="
  "$PY" -m "benchmarks.$bench" || echo "  ($bench failed — see error above)"
done

echo "=== hle (text-only, no-tools) ==="
HLE_MODE=no_tools "$PY" -m benchmarks.hle || echo "  (hle failed)"

echo "Done. Agentic benchmarks: see agentic/README.md"
