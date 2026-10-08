#!/usr/bin/env bash
# =============================================================================
# SkillsBench via the `harbor` runner.
#
# benchflow-ai/skillsbench (Apache-2.0): 87 tasks across 11 domains, each shipping a
# curated skill folder (SKILL.md + scripts) and a deterministic verifier; measures how
# well an agent uses skills. One of the three OPEN suites of Nous Research's Hermes
# Index (2026-10-06), which runs it inside the Hermes Agent harness — so the agent
# defaults to `hermes` (harbor_agents/hermes_agent.py).
#
# Dataset: Harbor Hub `benchflow/skillsbench@latest` (87 tasks; the only tag published
# as of 2026-10). The hub package is harbor-format (task.toml 1.1), BUT the curated
# skills sit in each task's `environment/skills/` and only 2/87 Dockerfiles copy them
# into the image — SkillsBench's own `bench` CLI injects them per task, and plain harbor
# has no per-task skills injection. So this wrapper downloads the dataset once into
# SKILLSBENCH_DIR and patches every task idempotently:
#     Dockerfile : + `COPY skills /harbor/skills`
#     task.toml  : + `[environment] skills_dir = "/harbor/skills"`
# harbor then hands `skills_dir` to the agent, and the Hermes adapter copies it into
# Hermes's native skills dir ($HERMES_HOME/skills) — the benchmark's "curated skills"
# condition. SKILLSBENCH_NO_SKILLS=1 runs the unpatched copy instead (the paper's
# "no skills" ablation; NOT what the Hermes Index measures).
#
# "Clean" score: Nous drops tasks where the agent found the public SkillsBench repo and
# used its oracle solutions (tasks allow internet). hermes_index.py scans the agent
# transcripts for mentions of the repo/dataset/site and reports raw + clean.
#
# Prereqs:  uv tool install 'harbor[modal]'   # >= 0.24.0 for the hermes agent
#           Docker running, or TB_ENV=modal.   No GPU. Agent containers need internet.
#
#   MODEL_BASE_URL=https://your-endpoint/v1  MODEL_API_KEY=sk-...  MODEL_NAME=your-model \
#     ./run_skillsbench.sh
#
# Knobs: SKILLSBENCH_VERSION=latest (hub tag), SKILLSBENCH_DIR (local patched copy;
#        default ./skillsbench-tasks), SKILLSBENCH_NO_SKILLS=1, TB_AGENT, CONC, TB_ENV,
#        OUT, LIMIT, TASKS_FILE / TB_EXCLUDE_FILE (plain task dir names), HERMES_* knobs.
#
# Score: resolved/total across <out>/*/*/result.json (verifier_result.rewards.reward == 1);
#        clean score via hermes_index.py --skills <out> --summary.
# =============================================================================
set -euo pipefail

command -v harbor >/dev/null 2>&1 || export PATH="$HOME/.local/bin:$PATH"

MODEL_BASE_URL="${MODEL_BASE_URL:?set MODEL_BASE_URL (OpenAI-compatible /v1 base)}"
MODEL_API_KEY="${MODEL_API_KEY:-dummy}"
MODEL_NAME="${MODEL_NAME:-your-model}"
AGENT="${TB_AGENT:-hermes}"
CONC="${CONC:-4}"
ENV_MODE="${TB_ENV:-docker}"
OUT="${OUT:-skillsbench_$(date -u +%Y%m%d-%H%M%S)}"
SKILLSBENCH_VERSION="${SKILLSBENCH_VERSION:-latest}"
DATASET="benchflow/skillsbench@$SKILLSBENCH_VERSION"
NO_SKILLS="${SKILLSBENCH_NO_SKILLS:-0}"
TASK_DIR="${SKILLSBENCH_DIR:-$PWD/skillsbench-tasks}"
if [ "$NO_SKILLS" = "1" ]; then TASK_DIR="${TASK_DIR%/}-noskills"; fi
LIMIT="${LIMIT:-87}"

export OPENAI_API_BASE="$MODEL_BASE_URL" OPENAI_BASE_URL="$MODEL_BASE_URL" OPENAI_API_KEY="$MODEL_API_KEY"

# ── 1. local copy of the hub dataset (once) ─────────────────────────────────────
# `harbor datasets download` writes ./<dataset-short-name>/<task>/ under the cwd.
if [ ! -f "$TASK_DIR/.downloaded" ]; then
  echo "Downloading $DATASET into $TASK_DIR ..."
  tmp="$(mktemp -d)"
  harbor datasets download "$DATASET" --output-dir "$tmp"
  src="$(find "$tmp" -mindepth 1 -maxdepth 1 -type d | head -1)"
  [ -n "$src" ] || { echo "ERROR: download produced nothing under $tmp" >&2; exit 1; }
  mkdir -p "$(dirname "$TASK_DIR")"
  rm -rf "$TASK_DIR" && mv "$src" "$TASK_DIR" && rm -rf "$tmp"
  echo "$DATASET $(date -u +%FT%TZ)" > "$TASK_DIR/.downloaded"
fi
N_TASKS="$(find "$TASK_DIR" -mindepth 2 -maxdepth 2 -name task.toml | wc -l | tr -d ' ')"

# ── 2. surface each task's curated skills (idempotent) ──────────────────────────
if [ "$NO_SKILLS" != "1" ]; then
  python3 - "$TASK_DIR" <<'PY'
import re, sys
from pathlib import Path
root = Path(sys.argv[1]); patched = 0
for toml in sorted(root.glob("*/task.toml")):
    task = toml.parent
    skills = task / "environment" / "skills"
    dockerfile = task / "environment" / "Dockerfile"
    if not skills.is_dir() or not dockerfile.is_file():
        continue
    df = dockerfile.read_text()
    if "/harbor/skills" not in df:
        dockerfile.write_text(df.rstrip("\n") + "\n\n# pareto-evals/run_skillsbench.sh: surface the curated skills "
                              "(harbor has no per-task skills injection)\nCOPY skills /harbor/skills\n")
        patched += 1
    tt = toml.read_text()
    if "skills_dir" not in tt:
        if re.search(r"^\[environment\]\s*$", tt, re.M):
            tt = re.sub(r"^\[environment\]\s*$", '[environment]\nskills_dir = "/harbor/skills"', tt, count=1, flags=re.M)
        else:
            tt = tt.rstrip("\n") + '\n\n[environment]\nskills_dir = "/harbor/skills"\n'
        toml.write_text(tt)
print(f"skills patch: {patched} task(s) newly patched; all tasks with environment/skills now expose /harbor/skills")
PY
else
  echo "SKILLSBENCH_NO_SKILLS=1: running the unpatched copy ($TASK_DIR) — the no-skills ablation, not the Hermes Index condition." >&2
fi

EXTRA=()
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harbor_agents/resolve_agent.sh
source "$SCRIPT_DIR/harbor_agents/resolve_agent.sh"
resolve_harbor_agent

if [ -n "${MODEL_MAX_INPUT_TOKENS:-}" ] && [[ "$AGENT" == terminus* ]]; then
  EXTRA+=(--agent-kwarg "model_info={\"max_input_tokens\": ${MODEL_MAX_INPUT_TOKENS}, \"max_output_tokens\": ${MODEL_MAX_OUTPUT_TOKENS:-32768}}")
fi
# Local tasks are named by directory, no namespace.
if [ -n "${TASKS_FILE:-}" ]; then
  while IFS= read -r t; do [ -n "$t" ] && EXTRA+=(--include-task-name "$t"); done < "$TASKS_FILE"
fi
if [ -n "${TB_EXCLUDE_FILE:-}" ]; then
  while IFS= read -r t; do [ -n "$t" ] && EXTRA+=(--exclude-task-name "$t"); done < "$TB_EXCLUDE_FILE"
fi

echo "SkillsBench ($DATASET, $N_TASKS tasks in $TASK_DIR, skills=$([ "$NO_SKILLS" = 1 ] && echo off || echo on)): agent=$AGENT  model=openai/$MODEL_NAME  limit=$LIMIT  conc=$CONC  env=$ENV_MODE  out=$OUT"
harbor run \
  -p "$TASK_DIR" \
  -a "$AGENT" \
  -m "openai/$MODEL_NAME" \
  -l "$LIMIT" -n "$CONC" \
  -e "$ENV_MODE" \
  ${EXTRA[@]+"${EXTRA[@]}"} \
  --yes -o "$OUT"

echo "Done. Raw score = resolved/total across $OUT/*/*/result.json; clean score (leaked tasks dropped):"
echo "      python3 $SCRIPT_DIR/hermes_index.py --skills $OUT --summary"
