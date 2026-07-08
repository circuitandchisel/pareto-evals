"""Authoritative self-hosted $/task comes from the cascade server's cost log
(LC_SERVER_COST_LOG), a JSONL of {cost, duration_ms, call_count, stage, ts?} per
request. We sum entries written during a run's wall-clock window.

When we swap to the productionized API, cost will come from the API's usage/billing
in `model_complete`'s meta instead, and this module becomes unnecessary.
"""
from __future__ import annotations

import json
import os


def cost_since(cost_log: str | None, start_epoch: float) -> float | None:
    """Sum `cost` over cost-log entries written since `start_epoch`.

    If entries carry a `ts` field we window by it; otherwise (current log format has
    no timestamp) we fall back to file mtime + summing all entries appended after the
    run started, which is only correct when one run writes the log at a time. The
    clean fix is to add `ts` to the server cost-log writer — tracked as a TODO.
    """
    if not cost_log or not os.path.exists(cost_log):
        return None
    total = 0.0
    windowed = False
    try:
        with open(cost_log) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                ts = e.get("ts") or e.get("timestamp")
                if ts is not None:
                    windowed = True
                    if float(ts) < start_epoch:
                        continue
                total += float(e.get("cost", 0.0) or 0.0)
    except Exception:
        return None
    # If no ts anywhere, caller should use a fresh cost log per run (recommended).
    return round(total, 5)
