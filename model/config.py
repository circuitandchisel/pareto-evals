"""Model endpoint configuration for the eval suite.

Everything is driven by env vars so the SAME code runs against the self-hosted
cascade today and the productionized Pareto API later — you only change env
(or, if the swap is more than a URL change, `model/client.py`).
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelConfig:
    base_url: str          # OpenAI-compatible base URL
    api_key: str           # bearer key (cascade server ignores it; router/API need it)
    model: str             # model name the endpoint expects
    temperature: float
    max_tokens: int
    cost_log: str | None   # server-side JSONL that records per-call cost (self-hosted only)
    request_timeout: float


def load() -> ModelConfig:
    return ModelConfig(
        # Default = the self-hosted cascade server (leader/RC config) on the bench box.
        base_url=os.environ.get("PARETO_MODEL_BASE_URL", "http://localhost:8097/v1"),
        api_key=os.environ.get("PARETO_MODEL_API_KEY", "dummy"),
        model=os.environ.get("PARETO_MODEL_NAME", "route"),
        temperature=float(os.environ.get("PARETO_MODEL_TEMPERATURE", "0.0")),
        max_tokens=int(os.environ.get("PARETO_MODEL_MAX_TOKENS", "8192")),
        cost_log=os.environ.get("PARETO_MODEL_COST_LOG"),
        request_timeout=float(os.environ.get("PARETO_MODEL_TIMEOUT", "600")),
    )


CONFIG = load()
