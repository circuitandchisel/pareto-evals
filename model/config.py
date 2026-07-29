"""Model endpoint configuration for the eval suite.

Everything is driven by env vars so the SAME code runs against the self-hosted
cascade today and the productionized model API later — you only change env
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
    send_sampling: bool    # False => omit sampling params (endpoint rejects them)
    max_tokens: int
    cost_log: str | None   # optional server-side JSONL that records per-call cost, if your endpoint writes one
    request_timeout: float


def load() -> ModelConfig:
    return ModelConfig(
        # Your model's OpenAI-compatible endpoint. Set MODEL_BASE_URL / MODEL_NAME
        # (run.py sets these per-model from PARETO_* / COMPARISON_*).
        base_url=os.environ.get("MODEL_BASE_URL", "http://localhost:8000/v1"),
        api_key=os.environ.get("MODEL_API_KEY", "dummy"),
        model=os.environ.get("MODEL_NAME", "default"),
        temperature=float(os.environ.get("MODEL_TEMPERATURE", "0.0")),
        # Some endpoints REJECT sampling parameters rather than ignoring them —
        # e.g. a cascade that fans out over many models and sets sampling per
        # internal call cannot honor a caller's temperature, so it 400s instead
        # of silently pretending. Set MODEL_SEND_SAMPLING=false for those.
        # Left ON by default: baselines rely on temperature=0 for reproducibility.
        send_sampling=os.environ.get("MODEL_SEND_SAMPLING", "true").lower() not in ("false", "0", "no"),
        max_tokens=int(os.environ.get("MODEL_MAX_TOKENS", "8192")),
        cost_log=os.environ.get("MODEL_COST_LOG"),
        request_timeout=float(os.environ.get("MODEL_TIMEOUT", "600")),
    )


CONFIG = load()
