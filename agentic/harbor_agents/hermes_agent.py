"""
Harbor adapter for NousResearch's Hermes Agent, configured the way Nous runs the
Hermes Index (https://portal.nousresearch.com/bench): the stock harbor `hermes`
installed agent plus the two things the index methodology fixes that harbor's
adapter leaves at Hermes defaults —

  * reasoning effort "high" ("reasoning effort set to high where the model offers
    it") — written to Hermes's config.yaml as `agent.reasoning_effort`; and
  * skills baked into a task image (SkillsBench) surfaced to Hermes, whose only
    skills root is $HERMES_HOME/skills — harbor copies `environment.skills_dir`
    there, and this adapter additionally copies a few well-known in-image skill
    dirs (see EXTRA_SKILL_DIRS) so run_skillsbench.sh's `COPY skills /harbor/skills`
    patch is picked up even on a task.toml without `skills_dir`.

Everything else (install from NousResearch/hermes-agent main, `hermes --yolo chat
-q ... -Q`, the openai-api provider on `openai/<model>` honouring OPENAI_BASE_URL /
OPENAI_API_KEY, session export → ATIF trajectory + token totals) is inherited from
harbor.agents.installed.hermes.Hermes. **harbor >= 0.24.0** is required: the
`openai/<model>` → Hermes `openai-api` provider routing (#3426) landed there; older
harbor sends openai/* through OpenRouter and the run fails without an OpenRouter key.

Loaded by import path from the run_*.sh wrappers (nothing installed into harbor's venv):

    harbor run ... -a harbor_agents.hermes_agent:HermesAgent -m openai/<model> \
        --ak reasoning_effort=high [--ak version=<git tag/branch>] [--ak max_turns=N]

Agent kwargs (`--agent-kwarg key=value`):
  reasoning_effort=<level>   minimal|low|medium|high|xhigh|max|ultra|none (default high);
                             "default" leaves Hermes's own default (medium)
  version=<ref>              hermes-agent git branch/tag (or commit SHA) to install (default: main, like Nous)
  max_turns=<int>            Hermes agent.max_turns (default: Hermes's own — unlimited)
  toolsets=<csv>             Hermes --toolsets
  extra_skill_dirs=<csv>     in-image dirs copied into $HERMES_HOME/skills if present
"""

from __future__ import annotations

import shlex
from typing import Any, override

import yaml
from pydantic import Field

import json
import re

from harbor.agents.installed.hermes import Hermes, HermesOptions
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

# Two things in hermes-agent main (2026-10) break harbor's install step, which runs
# `hermes version` under HERMES_HOME=/tmp/hermes:
#   1. a HERMES_HOME other than the install root (~/.hermes) is a separate "data root"
#      and refuses to run until `hermes pm repair` has installed its dependency env
#      ("no dependency environment is committed for this install");
#   2. the `hermes version` subcommand is gone — it is `hermes --version` now
#      ("'version' is not a `hermes` command").
# So: repair the data root first (no-op/absent on older releases), then probe the
# version with either spelling. Verified 2026-10-08 in a SkillsBench task image.
_HERMES_REPAIR_CMD = "(hermes pm repair >/dev/null 2>&1 || true)"
_HERMES_VERSION_CMD = "(hermes --version 2>/dev/null || hermes version)"
_INSTALL_URL = "https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh"

DEFAULT_REASONING_EFFORT = "high"
# Hermes's VALID_REASONING_EFFORTS + its "disabled" spellings.
_VALID_EFFORTS = ("minimal", "low", "medium", "high", "xhigh", "max", "ultra", "none", "false", "disabled")
# Where SkillsBench-style images (and run_skillsbench.sh's Dockerfile patch) put curated
# skills; copied into Hermes's native skills dir when present. /harbor/skills is also
# harbor's default injected-skills root.
EXTRA_SKILL_DIRS = ("/harbor/skills", "/root/.agents/skills", "/root/.claude/skills")
_HERMES_SKILLS = "/tmp/hermes/skills"  # $HERMES_HOME/skills with harbor's HERMES_HOME=/tmp/hermes


class HermesIndexOptions(HermesOptions):
    reasoning_effort: str | None = Field(
        default=DEFAULT_REASONING_EFFORT,
        description="Hermes agent.reasoning_effort (Hermes Index runs 'high'); 'default' leaves Hermes's own.",
    )
    extra_skill_dirs: str | None = Field(
        default=",".join(EXTRA_SKILL_DIRS),
        description="Comma-separated in-image skill dirs copied into $HERMES_HOME/skills when they exist.",
    )


class HermesAgent(Hermes):
    """Hermes Agent as run for the Hermes Index (reasoning effort high, skills surfaced)."""

    options_model = HermesIndexOptions
    options: HermesIndexOptions

    @override
    def get_version_command(self) -> str | None:
        return f'export PATH="$HOME/.local/bin:$PATH"; {_HERMES_VERSION_CMD}'

    @override
    async def install(self, environment: BaseEnvironment) -> None:
        # Same as harbor's Hermes.install (0.24.0) except for the version probe at the end.
        await self.ensure_system_dependencies(environment, ("curl", "git", "ripgrep", "xz"))
        # install.sh takes --branch <name> or --commit <sha>; harbor only knows --branch, so a
        # pinned SHA (what you want for a multi-hour run whose containers install at different
        # times) is routed to --commit here.
        v = (self._version or "").strip()
        if not v:
            branch_flag = ""
        elif re.fullmatch(r"[0-9a-f]{7,40}", v):
            branch_flag = f" --commit {v}"
        else:
            branch_flag = f" --branch {v}"
        await self.exec_as_agent(
            environment,
            command=(
                "set -euo pipefail; "
                f"curl -fsSL {_INSTALL_URL} | bash -s -- --skip-setup{branch_flag} && "
                'export PATH="$HOME/.local/bin:$PATH" && '
                'export HERMES_HOME="${HERMES_HOME:-/tmp/hermes}" && '
                'mkdir -p "$HERMES_HOME" "$HERMES_HOME/sessions" "$HERMES_HOME/skills" "$HERMES_HOME/memories" && '
                f"{_HERMES_REPAIR_CMD} && {_HERMES_VERSION_CMD}"
            ),
        )

    # Hermes.run() calls self._build_config_yaml(model, max_turns) — an instance override
    # of the parent's staticmethod lets us add keys without re-implementing run().
    def _build_config_yaml(self, model: str, max_turns: int | None = None) -> str:  # type: ignore[override]
        cfg: dict[str, Any] = yaml.safe_load(Hermes._build_config_yaml(model, max_turns)) or {}
        effort = (self.options.reasoning_effort or "").strip().lower()
        if effort and effort != "default":
            if effort not in _VALID_EFFORTS:
                raise ValueError(
                    f"reasoning_effort={effort!r} is not a Hermes level ({', '.join(_VALID_EFFORTS)})"
                )
            cfg.setdefault("agent", {})["reasoning_effort"] = effort
        return yaml.dump(cfg, default_flow_style=False)

    # ------------------------------------------------------- usage metrics --
    # harbor's adapter sums per-message `usage` dicts out of the session export, but
    # current Hermes puts the totals on the session record instead (input_tokens,
    # output_tokens, cache_read_tokens, cache_write_tokens, reasoning_tokens,
    # estimated_cost_usd / actual_cost_usd) — so result.json showed 0 tokens
    # (seen 2026-10-08). Read the session record and fill harbor's context from it.
    def _session_record(self) -> dict[str, Any] | None:
        path = self.logs_dir / "hermes-session.jsonl"
        if not path.is_file():
            return None
        for line in path.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict) and ("input_tokens" in rec or "messages" in rec):
                return rec
        return None

    @override
    def populate_context_post_run(self, context: AgentContext) -> None:
        super().populate_context_post_run(context)  # ATIF trajectory + per-message usage (if any)
        try:
            rec = self._session_record()
            if not rec:
                return
            def _i(k: str) -> int:
                v = rec.get(k)
                return int(v) if isinstance(v, (int, float)) else 0
            inp, out = _i("input_tokens"), _i("output_tokens")
            cache_read, cache_write = _i("cache_read_tokens"), _i("cache_write_tokens")
            if inp or out:
                # harbor convention (see mini-swe-agent / dirac): n_input_tokens is the full
                # prompt size incl. cached tokens, n_cache_tokens the cached subset.
                # Hermes's input_tokens excludes cache reads/writes, so add them back.
                context.n_input_tokens = inp + cache_read + cache_write
                context.n_cache_tokens = cache_read
                context.n_output_tokens = out
            actual = rec.get("actual_cost_usd")
            if isinstance(actual, (int, float)):
                context.cost_usd = float(actual)
            context.metadata = {
                **(context.metadata or {}),
                "hermes_session": {
                    k: rec.get(k)
                    for k in ("id", "model", "input_tokens", "output_tokens", "cache_read_tokens",
                              "cache_write_tokens", "reasoning_tokens", "estimated_cost_usd",
                              "actual_cost_usd", "cost_status", "cost_source", "end_reason",
                              "message_count", "tool_call_count")
                },
            }
        except Exception:  # bookkeeping must never fail a graded trial
            self.logger.exception("Failed to read Hermes session totals")

    def _build_register_skills_command(self) -> str | None:
        parts: list[str] = []
        base = super()._build_register_skills_command()  # harbor's skills_dir -> /tmp/hermes/skills
        if base:
            parts.append(base)
        dirs = [d.strip() for d in (self.options.extra_skill_dirs or "").split(",") if d.strip()]
        for d in dirs:
            if self.skills_dir and d == self.skills_dir:
                continue
            q = shlex.quote(d)
            parts.append(
                f"{{ [ -d {q} ] && mkdir -p {_HERMES_SKILLS} && cp -r {q}/. {_HERMES_SKILLS}/; }} "
                "2>/dev/null || true"
            )
        return " ; ".join(parts) if parts else None
