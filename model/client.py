"""THE single model entry point for the entire eval suite.

Every benchmark — simple or agentic — resolves the model through `model_complete()`
here. Nothing else in this repo talks to the model directly.

Point it at any OpenAI-compatible endpoint via MODEL_BASE_URL / MODEL_API_KEY /
MODEL_NAME (run.py sets these per-model from your PARETO_* / COMPARISON_* config).
To retarget the whole suite at a different endpoint, change ONLY this module.

Third-party agentic harnesses (harbor / mini-swe-agent) can't import this
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
# at full-benchmark scale. The endpoint may already retry 429/5xx upstream, but
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
    # Some endpoints wrap upstream failures in a 500 whose message looks like
    #   [local] OpenRouter 502 for "model": {... "Backend returned HTTP 400" ...}
    # These are transient upstream issues, not a defect in our request — retry them.
    msg = str(getattr(e, "message", "") or e)
    if ("Backend returned HTTP" in msg or "OpenRouter 5" in msg or "OpenRouter 429" in msg
            or "fetch failed" in msg or "upstream failure" in msg):
        return True
    return False


_STREAM = os.environ.get("MODEL_STREAM", "").lower() in ("1", "true", "yes")


def _consume_stream(stream) -> dict:
    """Accumulate a streaming chat completion into content + usage + cost meta.

    Streaming avoids some proxies' non-stream wall-clock timeout
    (NON_STREAM_TIMEOUT_MS): as long as the backend keeps emitting chunks, a long
    high-effort generation completes (governed only by TTFB + per-chunk stall).
    """
    parts, finish, usage, cost_meta = [], None, None, None
    for chunk in stream:
        ce = getattr(chunk, "model_extra", None) or {}
        if ce.get("_meta"):
            cost_meta = ce["_meta"]
        if getattr(chunk, "usage", None) is not None:
            usage = chunk.usage
        chs = getattr(chunk, "choices", None) or []
        if chs:
            delta = getattr(chs[0], "delta", None)
            if delta is not None and getattr(delta, "content", None):
                parts.append(delta.content)
            if getattr(chs[0], "finish_reason", None):
                finish = chs[0].finish_reason
    return {"content": ("".join(parts) or None), "finish": finish, "usage": usage, "cost_meta": cost_meta}


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
    """One chat completion against the configured model.

    Returns (content, meta):
      content : the assistant text (may be None if it only returned tool_calls)
      meta    : {latency_s, finish_reason, tool_calls, usage, raw}

    Cost ($/task): latency is captured here (client-side, always available). Token
    usage is captured from the response when the endpoint returns it. The AUTHORITATIVE
    $/task can come from a server cost log (see `harness/cost.py`); the
    productionized API will return usage/cost inline and this meta will carry it.
    """
    kwargs: dict[str, Any] = {
        "model": model or CONFIG.model,
        "messages": messages,
        "max_tokens": max_tokens or CONFIG.max_tokens,
    }
    # Sampling is omitted entirely for endpoints that reject it (see
    # ModelConfig.send_sampling). Omitting is not the same as sending a default:
    # the endpoint applies its own sampling, so runs against such an endpoint are
    # NOT greedy and not bit-reproducible — record that when reporting.
    if CONFIG.send_sampling:
        kwargs["temperature"] = CONFIG.temperature if temperature is None else temperature
    if tools:
        kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
    kwargs.update(extra)

    # Streaming (opt-in via MODEL_STREAM) dodges some proxies' non-stream wall
    # timeout for long high-effort generations. Not used for tool calls.
    if _STREAM and not tools:
        kwargs["stream"] = True

    streamed = None
    attempt = 0
    while True:
        t0 = time.perf_counter()
        try:
            resp = _client.chat.completions.create(**kwargs)
            streamed = _consume_stream(resp) if kwargs.get("stream") else None
            latency = time.perf_counter() - t0
            break
        except Exception as e:  # noqa: BLE001 — decide by type/message below
            # A rejected sampling parameter is a config error, not a blip: fail
            # fast with the fix rather than burning retries on a guaranteed 400.
            msg = str(getattr(e, "message", "") or e)
            if "unsupported_parameter" in msg or "Unsupported sampling parameter" in msg:
                raise RuntimeError(
                    f"{msg}\n\nThis endpoint rejects sampling parameters. Set "
                    f"MODEL_SEND_SAMPLING=false (or <PREFIX>_SEND_SAMPLING=false in .env) "
                    f"for this model."
                ) from e
            if attempt >= _MAX_RETRIES or not _is_retryable(e):
                raise
            time.sleep(_BACKOFF_BASE_S * (2 ** attempt))
            attempt += 1

    if streamed is not None:
        # Cost from the streamed _meta (if present), else usage.cost, else None.
        _cm = streamed.get("cost_meta") or {}
        cost_usd = ((_cm.get("cascade") or {}).get("cost_usd"))
        _u = streamed.get("usage")
        if cost_usd is None and _u is not None:
            _ue = getattr(_u, "model_extra", None) or {}
            cost_usd = _ue.get("cost") or _ue.get("cost_usd")
        try:
            cost_usd = float(cost_usd) if cost_usd is not None else None
        except (TypeError, ValueError):
            cost_usd = None
        return streamed.get("content"), {
            "latency_s": latency,
            "finish_reason": streamed.get("finish"),
            "tool_calls": None,
            "usage": _u,
            "cost_usd": cost_usd,
            "retries": attempt,
            "raw": None,
        }

    # Per-call cost from the response, if the endpoint reports it (_meta.cascade.cost_usd).
    # This is concurrency-safe (attributed to THIS call), unlike summing a shared
    # server cost log — so $/task stays correct even with many benchmarks in flight.
    cost_usd = None
    try:
        extra = getattr(resp, "model_extra", None) or {}
        # Read cost from the response in priority order:
        #   1) _meta.cascade.cost_usd  2) top-level cost/cost_usd  3) usage.cost
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
