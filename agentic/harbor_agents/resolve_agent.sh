# Shared by run_tb.sh / run_tb_science.sh / run_skillsbench.sh — NOT executable on its own.
#
# Maps the user-facing agent names to harbor agents and appends their --agent-kwarg
# flags. Expects the caller to have set:
#   AGENT       the requested agent (terminus-2 | dirac | hermes | any harbor name or
#               module.path:ClassName import path)
#   EXTRA       a bash array of extra `harbor run` args (appended to)
#   SCRIPT_DIR  the agentic/ directory (added to PYTHONPATH for the import-path adapters)
# and mutates AGENT / EXTRA / PYTHONPATH in place.
#
#   dirac   -> harbor_agents/dirac_agent.py   (Dirac coding agent; see run_tb.sh header)
#   hermes  -> harbor_agents/hermes_agent.py  (NousResearch Hermes Agent as run for the
#              Hermes Index: reasoning effort high, in-image skills surfaced; needs
#              harbor >= 0.24.0 for the openai/<model> -> openai-api provider routing)
#              Knobs: HERMES_REASONING (default high), HERMES_VERSION (git tag/branch of
#              hermes-agent to install; default main), HERMES_MAX_TURNS, HERMES_TOOLSETS,
#              HERMES_AGENT_KWARGS="k=v ..." (any extra --agent-kwarg).

resolve_harbor_agent() {
  case "$AGENT" in
    dirac|dirac-cli)
      AGENT="harbor_agents.dirac_agent:DiracAgent"
      export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
      if [ -n "${DIRAC_VERSION:-}" ]; then EXTRA+=(--agent-kwarg "version=$DIRAC_VERSION"); fi
      if [ -n "${DIRAC_TIMEOUT_SEC:-}" ]; then EXTRA+=(--agent-kwarg "timeout_sec=$DIRAC_TIMEOUT_SEC"); fi
      if [ -n "${DIRAC_MAX_MISTAKES:-}" ]; then EXTRA+=(--agent-kwarg "max_consecutive_mistakes=$DIRAC_MAX_MISTAKES"); fi
      for kv in ${DIRAC_AGENT_KWARGS:-}; do EXTRA+=(--agent-kwarg "$kv"); done
      # Dirac's analog of terminus-2's proactive summarization: with
      # MODEL_MAX_INPUT_TOKENS set, switch Dirac from mechanical truncation to
      # AI compaction that triggers at that context size (--auto-condense-at is
      # a no-op without --auto-condense; see ContextManager.ts in the Dirac repo).
      if [ -n "${MODEL_MAX_INPUT_TOKENS:-}" ]; then
        EXTRA+=(--agent-kwarg "auto_condense=true" --agent-kwarg "auto_condense_at=${MODEL_MAX_INPUT_TOKENS}")
        echo "NOTE: dirac --auto-condense --auto-condense-at ${MODEL_MAX_INPUT_TOKENS} (from MODEL_MAX_INPUT_TOKENS)." >&2
      fi
      ;;
    hermes|hermes-agent)
      AGENT="harbor_agents.hermes_agent:HermesAgent"
      export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
      # harbor's Hermes adapter routes openai/<model> through Hermes's openai-api provider
      # (honouring OPENAI_BASE_URL) only from 0.24.0 (#3426); older harbor sends it to
      # OpenRouter and the run dies for want of OPENROUTER_API_KEY.
      local ver
      ver="$(harbor --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"
      if [ -n "$ver" ] && [ "$(printf '%s\n' 0.24.0 "$ver" | sort -V | head -1)" != "0.24.0" ]; then
        echo "ERROR: TB_AGENT=hermes needs harbor >= 0.24.0 (found $ver): uv tool install --force 'harbor[modal]>=0.24.0'" >&2
        exit 1
      fi
      EXTRA+=(--agent-kwarg "reasoning_effort=${HERMES_REASONING:-high}")
      if [ -n "${HERMES_VERSION:-}" ]; then EXTRA+=(--agent-kwarg "version=$HERMES_VERSION"); fi
      if [ -n "${HERMES_MAX_TURNS:-}" ]; then EXTRA+=(--agent-kwarg "max_turns=$HERMES_MAX_TURNS"); fi
      if [ -n "${HERMES_TOOLSETS:-}" ]; then EXTRA+=(--agent-kwarg "toolsets=$HERMES_TOOLSETS"); fi
      for kv in ${HERMES_AGENT_KWARGS:-}; do EXTRA+=(--agent-kwarg "$kv"); done
      echo "NOTE: Hermes Agent (reasoning_effort=${HERMES_REASONING:-high}, hermes-agent@${HERMES_VERSION:-main}); install takes ~6-10 min per task container." >&2
      ;;
  esac
}
