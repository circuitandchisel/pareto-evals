"""THE single model entry point for the entire eval suite.

Every benchmark — simple or agentic — resolves the model through `model_complete()`
here. Nothing else in this repo talks to the model directly.

  TODAY:  routes to our self-hosted cascade RC via its OpenAI-compatible endpoint
          (the cascade server; default http://localhost:8097/v1, model "route").
  LATER:  to swap in the productionized model API, change ONLY this module
          (point base_url at the API and adjust auth). No runner needs to change.

Third-party agentic harnesses (harbor / mini-swe-agent / vals-ai) can't import this
function — they make their own HTTP calls — but they point at the SAME endpoint via
`model/config.py`, so the swap point is still singular. See `agentic/README.md`.
"""
from __future__ import annotations

import os
import time
from typing import Any

from openai import (
    OpenAI,
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    InternalServerError,
    APIStatusError,
)

from .config import CONFIG

_client = OpenAI(base_url=CONFIG.base_url, api_key=CONFIG.api_key, timeout=CONFIG.request_timeout)

# Transient upstream failures (rate limits, gateway/backend hiccups) are expected
# at full-benchmark scale. The cascade itself already retries 429/5xx upstream, but
# it can still surface a wrapped 5xx/backend-4xx to us; retry here too so a single
# flaky call never zeros out an item. Retrying in THIS one entry point covers every
# benchmark uniformly. Deterministic (no jitter) so runs stay reproducible.
_MAX_RETRIES = int(os.environ.get("MODEL_MAX_RETRIES", "4"))
_BACKOFF_BASE_S = float(os.environ.get("MODEL_BACKOFF_BASE_S", "2.0"))
_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


def _is_retryable(e: Exception) -> bool:
    if isinstance(e, (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)):
        return True
    status = getattr(e, "status_code", None)
    if isinstance(e, APIStatusError) and status in _RETRYABLE_STATUS:
        return True
    # The cascade wraps upstream failures in a 500 whose message looks like
    #   [local] OpenRouter 502 for "model": {... "Backend returned HTTP 400" ...}
    # These are transient upstream issues, not a defect in our request — retry them.
    msg = str(getattr(e, "message", "") or e)
    if "Backend returned HTTP" in msg or "OpenRouter 5" in msg or "OpenRouter 429" in msg:
        return True
    return False


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

    attempt = 0
    while True:
        t0 = time.perf_counter()
        try:
            resp = _client.chat.completions.create(**kwargs)
            latency = time.perf_counter() - t0
            break
        except Exception as e:  # noqa: BLE001 — decide by type/message below
            if attempt >= _MAX_RETRIES or not _is_retryable(e):
                raise
            time.sleep(_BACKOFF_BASE_S * (2 ** attempt))
            attempt += 1

    # Per-call cost straight from the cascade's response (_meta.cascade.cost_usd).
    # This is concurrency-safe (attributed to THIS call), unlike summing a shared
    # server cost log — so $/task stays correct even with many benchmarks in flight.
    cost_usd = None
    try:
        extra = getattr(resp, "model_extra", None) or {}
        # Read cost from the response in priority order:
        #   1) self-hosted cascade meta  2) top-level cost/cost_usd  3) usage.cost
        cost_usd = ((extra.get("_meta") or {}).get("cascade") or {}).get("cost_usd")
        if cost_usd is None:
            cost_usd = extra.get("cost_usd") or extra.get("cost")
        if cost_usd is None:
            _u = getattr(resp, "usage", None)
            _ue = getattr(_u, "model_extra", None) or {}
            cost_usd = _ue.get("cost") or _ue.get("cost_usd")
        cost_usd = float(cost_usd) if cost_usd is not None else None
    except Exception:
        cost_usd = None

    choice = resp.choices[0]
    meta = {
        "latency_s": latency,
        "finish_reason": choice.finish_reason,
        "tool_calls": getattr(choice.message, "tool_calls", None),
        "usage": getattr(resp, "usage", None),
        "cost_usd": cost_usd,
        "retries": attempt,
        "raw": resp,
    }
    return choice.message.content, meta
