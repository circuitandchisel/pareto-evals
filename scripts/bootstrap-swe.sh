#!/usr/bin/env bash
# One-time setup for the opt-in agentic `swe_rebench` benchmark:
#   - mini-swe-agent   (the agent harness)      -> .venv-mini
#   - SWE-rebench fork  (the grader)            -> .venv-swegrader
# Requires Docker already installed & running, and Python 3.10+. Run from the repo root:
#   bash scripts/bootstrap-swe.sh
set -euo pipefail

echo "== checking Docker =="
if ! docker info >/dev/null 2>&1; then
  echo "  Docker is not available/running. Install and start it first:"
  echo "  https://docs.docker.com/engine/install/   (then: sudo usermod -aG docker \$USER && re-login)"
  exit 1
fi

echo "== mini-swe-agent -> .venv-mini =="
python3 -m venv .venv-mini
./.venv-mini/bin/pip install -q --upgrade pip
./.venv-mini/bin/pip install -q mini-swe-agent

echo "== SWE-rebench fork of swebench -> .venv-swegrader =="
[ -d SWE-bench-fork ] || git clone --depth 1 https://github.com/SWE-rebench/SWE-bench-fork.git
python3 -m venv .venv-swegrader
./.venv-swegrader/bin/pip install -q --upgrade pip
./.venv-swegrader/bin/pip install -q -e ./SWE-bench-fork

echo ""
echo "== done =="
echo "Add these to your .env:"
echo "  SWE_MINI_BIN=$(pwd)/.venv-mini/bin/mini-extra"
echo "  SWE_GRADER_PYTHON=$(pwd)/.venv-swegrader/bin/python"
echo "  PARETO_INPUT_PRICE_PER_MTOK=...   # for agentic \$/task (tokens × price)"
echo "  PARETO_OUTPUT_PRICE_PER_MTOK=..."
echo ""
echo "Then smoke-test (pulls a couple of Docker images the first time):"
echo "  python run.py --benchmarks swe_rebench --slice 2"
