"""
Harbor "installed agent" adapter for Dirac (https://dirac.run), the efficiency-
focused open-source coding agent (a Cline fork: hash-anchored edits, AST tools,
parallel tool calls). Lets `run_tb.sh` drive Terminal-Bench with Dirac instead of
harbor's terminus-2 reference agent:

    TB_AGENT=dirac MODEL_BASE_URL=... MODEL_API_KEY=... MODEL_NAME=... ./run_tb.sh

harbor loads it by import path (`-a harbor_agents.dirac_agent:DiracAgent`, with
PYTHONPATH pointing at `agentic/`), so nothing has to be installed into harbor's
venv. Verified against harbor 0.21.0 and dirac-cli 0.5.15.

How it maps onto Dirac's CLI (cli/src/index.ts, cli/src/utils/options.ts):
  * BYO OpenAI-compatible endpoint = `--provider <base-url> --model <id>` plus the
    key in `OPENAI_COMPATIBLE_CUSTOM_KEY`. A URL-valued --provider selects Dirac's
    "openai" (OpenAI-compatible) provider and overrides its base URL for the session.
  * `--yolo` auto-approves every tool action, and yolo/--json/non-TTY stdout all
    force "plain text mode": no Ink UI, exit 0 on completion / 1 on failure.
  * `--json` prints one DiracMessage per line; `api_status` messages carry
    tokensIn/tokensOut/cacheReads/cacheWrites/cost, which populate_context_post_run
    sums into harbor's AgentContext (result.json "agent_result": tokens + cost).
  * Any env-provided key already counts as "authenticated", but we also seed
    globalState.json with welcomeViewCompleted so no onboarding path can trigger.

Agent kwargs (`--agent-kwarg key=value`; harbor parses values as JSON):
  version=<npm version>          dirac-cli version to install (default: latest)
  timeout_sec=<int>              Dirac's own -t wall clock (harbor's task timeout still applies)
  max_consecutive_mistakes=<int> --max-consecutive-mistakes (halts a looping run)
  thinking=<tokens>              --thinking <budget>  (Anthropic-style extended thinking)
  reasoning_effort=<str>         --reasoning-effort   (OpenAI-style reasoning models)
  auto_condense=true             --auto-condense (AI compaction instead of truncation)
  auto_condense_at=<tokens>      --auto-condense-at <n> (context-size trigger)
  subagents=true                 --subagents
  double_check_completion=true   --double-check-completion
  verbose=true                   --verbose
"""

from __future__ import annotations

import json
import shlex
from typing import Any, override

from harbor.agents.installed.base import (
    BaseInstalledAgent,
    CliFlag,
    with_prompt_template,
)
from harbor.agents.installed.node_install import nvm_node_install_snippet
from harbor.agents.model_connection import ModelConnectionSpec
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

# dirac-cli declares engines.node ">=22.13.0 <25.0.0".
_NODE_MAJOR = 22
_OUTPUT_FILENAME = "dirac.txt"
# Dirac state (task history, settings, logs) goes under /logs/agent so harbor copies
# it back into the trial directory alongside the stdout capture.
_DIRAC_DIR = "/logs/agent/dirac"
# Model-name prefixes that mean "plain OpenAI-compatible endpoint" for harbor/litellm
# and must NOT be sent to Dirac as part of the model id.
_STRIP_PREFIXES = ("openai/", "litellm_proxy/")


class DiracAgent(BaseInstalledAgent):
    """Dirac coding agent (https://dirac.run) driven over an OpenAI-compatible API."""

    # Resolve the API key from OPENAI_API_KEY and the base URL from
    # OPENAI_BASE_URL / OPENAI_API_BASE regardless of the model-name prefix.
    MODEL_CONNECTION = ModelConnectionSpec(default_provider="openai")

    CLI_FLAGS = [
        CliFlag("timeout_sec", cli="-t", type="int"),
        CliFlag("max_consecutive_mistakes", cli="--max-consecutive-mistakes", type="int"),
        CliFlag("thinking", cli="--thinking", type="int"),
        CliFlag("reasoning_effort", cli="--reasoning-effort", type="str"),
        CliFlag("auto_condense", cli="--auto-condense", type="bool"),
        CliFlag("auto_condense_at", cli="--auto-condense-at", type="int"),
        CliFlag("subagents", cli="--subagents", type="bool"),
        CliFlag("double_check_completion", cli="--double-check-completion", type="bool"),
        CliFlag("verbose", cli="--verbose", type="bool"),
    ]

    @staticmethod
    @override
    def name() -> str:
        return "dirac"

    @override
    def get_version_command(self) -> str | None:
        return ". ~/.nvm/nvm.sh; dirac --version"

    @override
    async def install(self, environment: BaseEnvironment) -> None:
        # procps: Dirac's process-tree cleanup shells out to `ps --ppid`; 39 of the 63
        # TB-4.0 env images ship without it and Dirac dies with "spawn ps ENOENT"
        # (exit 1) the first time it terminates a child process (seen 2026-09-23 on
        # protein-autointerp-disulfide and vba-userform-port).
        await self.ensure_system_dependencies(environment, ("curl", "bash", "procps"))
        version_spec = f"@{self._version}" if self._version else "@latest"
        await self.exec_as_agent(
            environment,
            command=(
                "set -euo pipefail; "
                f"{nvm_node_install_snippet(_NODE_MAJOR)} && "
                f"npm i -g dirac-cli{version_spec} && "
                "dirac --version"
            ),
        )

    # ------------------------------------------------------------------ run --

    def _model_id(self) -> str:
        if not self.model_name:
            raise ValueError("DiracAgent needs a model name (harbor -m openai/<model>)")
        model = self.model_name
        for prefix in _STRIP_PREFIXES:
            if model.startswith(prefix):
                return model[len(prefix):]
        return model

    def _endpoint(self) -> tuple[str, str]:
        conn = self.model_connection
        base_url = conn.configured_base_url or conn.base_url
        if not base_url:
            raise ValueError(
                "DiracAgent needs an OpenAI-compatible base URL: set OPENAI_BASE_URL "
                "(run_tb.sh exports it from MODEL_BASE_URL)."
            )
        api_key = conn.api_key or self._get_env("OPENAI_API_KEY") or "dummy"
        return base_url, api_key

    def build_run_command(self, instruction: str) -> tuple[str, dict[str, str]]:
        """Shell command + env that run Dirac once over `instruction` and capture
        its JSON stream to /logs/agent/dirac.txt. Exposed for tests / dry runs."""
        instruction = instruction.strip()
        if not instruction:
            raise ValueError("Instruction is empty before invoking dirac")
        base_url, api_key = self._endpoint()
        model = self._model_id()

        env = {
            # Dirac's OpenAI-compatible provider key; also makes isAuthConfigured() true.
            "OPENAI_COMPATIBLE_CUSTOM_KEY": api_key,
            # Belt and braces: maps to the openAiBaseUrl setting even without --provider.
            "OPENAI_API_BASE": base_url,
            "DIRAC_DIR": _DIRAC_DIR,
            "DIRAC_NO_AUTO_UPDATE": "1",
            "DIRAC_NO_EMOJI": "1",
            # Dump the exact system prompt / request artifacts next to the transcript.
            "DIRAC_WRITE_PROMPT_ARTIFACTS": "1",
            "DIRAC_PROMPT_ARTIFACT_DIR": "/logs/agent",
        }

        global_state = shlex.quote(
            json.dumps({"welcomeViewCompleted": True, "isNewUser": False})
        )
        setup = (
            f"mkdir -p /logs/agent {_DIRAC_DIR}/data && "
            f"{{ [ -f {_DIRAC_DIR}/data/globalState.json ] || "
            f"echo {global_state} > {_DIRAC_DIR}/data/globalState.json; }}"
        )
        nvm = (
            'export NVM_DIR="$HOME/.nvm"; '
            'if [ -s "$NVM_DIR/nvm.sh" ]; then . "$NVM_DIR/nvm.sh"; '
            f"nvm use {_NODE_MAJOR} >/dev/null 2>&1 || true; fi"
        )
        flags = [
            "--provider", shlex.quote(base_url),
            "--model", shlex.quote(model),
            "--json",
            "--yolo",
        ]
        descriptor_flags = self.build_cli_flags()
        if descriptor_flags:
            flags.append(descriptor_flags)
        run = (
            f"dirac task {' '.join(flags)} -- {shlex.quote(instruction)} "
            f"</dev/null 2>&1 | stdbuf -oL tee /logs/agent/{_OUTPUT_FILENAME}; "
            'status=${PIPESTATUS[0]}; '
            f'echo "__DIRAC_EXIT=${{status}}" | tee -a /logs/agent/{_OUTPUT_FILENAME}; '
            'exit "${status}"'
        )
        return f"{nvm}; {setup} && {run}", env

    @override
    @with_prompt_template
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        command, env = self.build_run_command(instruction)
        await self.exec_as_agent(environment, command=command, env=env)

    # ------------------------------------------------------- usage metrics --

    def _iter_messages(self):
        path = self.logs_dir / _OUTPUT_FILENAME
        if not path.is_file():
            return
        for line in path.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue

    @override
    def populate_context_post_run(self, context: AgentContext) -> None:
        """Sum Dirac `api_status` messages (one per model request; a message may be
        re-emitted as its request progresses, so the last copy per `ts` wins)."""
        try:
            latest: dict[Any, dict[str, Any]] = {}
            errors: list[str] = []
            for i, msg in enumerate(self._iter_messages()):
                if not isinstance(msg, dict):
                    continue
                if msg.get("type") == "error" and msg.get("message"):
                    errors.append(str(msg["message"]))
                content = msg.get("content")
                if not isinstance(content, dict) or content.get("type") != "api_status":
                    continue
                status = content.get("status")
                if isinstance(status, dict):
                    latest[msg.get("ts", f"idx{i}")] = status
            if not latest and not errors:
                return

            def total(key: str) -> float:
                return sum(
                    s[key] for s in latest.values()
                    if isinstance(s.get(key), (int, float))
                )

            if latest:
                context.n_input_tokens = int(total("tokensIn"))
                context.n_output_tokens = int(total("tokensOut"))
                context.n_cache_tokens = int(total("cacheReads"))
                cost = total("cost")
                context.cost_usd = cost if cost > 0 else None
            context.metadata = {
                **(context.metadata or {}),
                "dirac_api_requests": len(latest),
                **({"dirac_errors": errors[:5]} if errors else {}),
            }
        except Exception:  # never let bookkeeping fail a graded trial
            self.logger.exception("Failed to parse dirac output for usage metrics")
