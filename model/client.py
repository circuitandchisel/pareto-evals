"""THE single model entry point for the entire eval suite.

Every benchmark — simple or agentic — resolves the model through `model_complete()`
here. Nothing else in this repo talks to the model directly.

  TODAY:  routes to our self-hosted cascade RC via its OpenAI-compatible endpoint
          (the cascade server; default http://localhost:8097/v1, model "route").
  LATER:  to swap in the productionized ATXP model API, change ONLY this module
          (point base_url at the API and adjust auth). No runner needs to change.

Third-party agentic harnesses (harbor / mini-swe-agent / vals-ai) can't import this
function — they make their own HTTP calls — but they point at the SAME endpoint via
`model/config.py`, so the swap point is still singular. See `agentic/README.md`.
"""
from __future__ import annotations

import time
from typing import Any

from openai import OpenAI

from .config import CONFIG

_client = OpenAI(base_url=CONFIG.base_url, api_key=CONFIG.api_key, timeout=CONFIG.request_timeout)


def model_complete(
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
    tool_choice: Any | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    model: str | None = None,
    **extra: Any,
) -> tuple[str | None, dict]:
    """One chat completion against the RC model.

    Returns (content, meta):
      content : the assistant text (may be None if it only returned tool_calls)
      meta    : {latency_s, finish_reason, tool_calls, usage, raw}

    Cost ($/task): latency is captured here (client-side, always available). Token
    usage is captured from the response when the endpoint returns it. The AUTHORITATIVE
    self-hosted $/task comes from the server cost log (see `harness/cost.py`); the
    productionized API will return usage/cost inline and this meta will carry it.
    """
    kwargs: dict[str, Any] = {
        "model": model or CONFIG.model,
        "messages": messages,
        "temperature": CONFIG.temperature if temperature is None else temperature,
        "max_tokens": max_tokens or CONFIG.max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
    kwargs.update(extra)

    t0 = time.perf_counter()
    resp = _client.chat.completions.create(**kwargs)
    latency = time.perf_counter() - t0

    choice = resp.choices[0]
    meta = {
        "latency_s": latency,
        "finish_reason": choice.finish_reason,
        "tool_calls": getattr(choice.message, "tool_calls", None),
        "usage": getattr(resp, "usage", None),
        "raw": resp,
    }
    return choice.message.content, meta
