#!/usr/bin/env bash
# Bootstrap a fresh Ubuntu/Debian cloud VM for the pareto-evals slate.
# The non-agentic slate is pure API traffic — no GPU needed. Run from the repo root:
#   bash scripts/bootstrap.sh
set -euo pipefail

echo "== installing system packages =="
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y python3 python3-venv python3-pip git tmux
else
  echo "  (non-apt system: ensure python3.10+, pip, venv, git, tmux are installed)"
fi

echo "== python venv + deps =="
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

echo ""
echo "== done =="
echo "Next:"
echo "  1) cp .env.example .env   &&   edit .env with your credentials"
echo "  2) source .venv/bin/activate"
echo "  3) python run.py --benchmarks gpqa --slice 10     # smoke test"
echo "  4) tmux new -s evals && python run.py             # full slate (survives disconnect)"
