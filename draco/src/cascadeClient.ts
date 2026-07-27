/**
 * Runs one DRACO task through the system-under-test (the gateway's auto-cascade)
 * and captures the answer, cost, and cascade telemetry.
 */

import { chat } from './gatewayClient.js';
import type { BenchConfig } from './config.js';
import type { Task, CascadeRunResult } from './types.js';

const SYSTEM_PROMPT = `You are a deep-research assistant. Answer the user's research request thoroughly and accurately. Synthesize across sources, analyze trade-offs, and cite primary sources with working references. Be precise; do not fabricate facts or citations.`;

export async function runCascadeTask(
  task: Task,
  cfg: BenchConfig,
  now: () => number = Date.now,
): Promise<CascadeRunResult> {
  const startedAt = now();
  try {
    const result = await chat({
      baseUrl: cfg.gatewayBaseUrl,
      token: cfg.connectionToken,
      model: cfg.model,
      maxTokens: cfg.maxTokens,
      timeoutMs: cfg.timeoutMs,
      // Stream so the cascade's keepalive heartbeats hold the connection open
      // through long (multi-minute) tool-using runs.
      stream: true,
      messages: [
        { role: 'system', content: SYSTEM_PROMPT },
        { role: 'user', content: task.problem },
      ],
      extraBody:
        Object.keys(cfg.cascadeOverrides).length > 0
          ? { cascade: cfg.cascadeOverrides }
          : undefined,
    });

    return {
      taskId: task.id,
      content: result.content,
      model: result.model,
      usage: result.usage,
      costUsd: result.costUsd,
      latencyMs: now() - startedAt,
      cascadeMeta: result.cascadeMeta,
    };
  } catch (err) {
    return {
      taskId: task.id,
      content: '',
      model: cfg.model,
      usage: { inputTokens: 0, outputTokens: 0 },
      costUsd: 0,
      latencyMs: now() - startedAt,
      cascadeMeta: null,
      error: err instanceof Error ? err.message : String(err),
    };
  }
}
