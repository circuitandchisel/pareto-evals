/**
 * Orchestrates a benchmark run: for each task, run the cascade, judge the
 * answer, score it, and aggregate into a {@link BenchmarkReport}.
 */

import { runCascadeTask } from './cascadeClient.js';
import { judgeTask } from './judge.js';
import { scoreTask, mean } from './scoring.js';
import type { BenchConfig } from './config.js';
import type { Task, TaskScore, BenchmarkReport } from './types.js';

export interface RunHooks {
  /** Called after each task finishes (for progress logging). */
  onTask?: (score: TaskScore | null, task: Task, index: number, total: number) => void;
  now?: () => number;
  nowIso?: () => string;
}

/** Run a bounded-concurrency pool over tasks. */
async function pool<T, R>(
  items: T[],
  concurrency: number,
  worker: (item: T, index: number) => Promise<R>,
): Promise<R[]> {
  const results: R[] = new Array(items.length);
  let next = 0;
  const runners = Array.from({ length: Math.max(1, concurrency) }, async () => {
    while (true) {
      const i = next++;
      if (i >= items.length) break;
      results[i] = await worker(items[i], i);
    }
  });
  await Promise.all(runners);
  return results;
}

export async function runBenchmark(
  tasks: Task[],
  cfg: BenchConfig,
  hooks: RunHooks = {},
): Promise<BenchmarkReport> {
  const now = hooks.now ?? Date.now;
  const nowIso = hooks.nowIso ?? (() => new Date().toISOString());
  const startedAt = nowIso();

  const taskScores: TaskScore[] = [];
  const errors: { taskId: string; error: string }[] = [];

  await pool(tasks, cfg.concurrency, async (task, index) => {
    const run = await runCascadeTask(task, cfg, now);
    if (run.error || !run.content) {
      errors.push({ taskId: task.id, error: run.error ?? 'empty response' });
      hooks.onTask?.(null, task, index, tasks.length);
      return;
    }

    let judged;
    try {
      judged = await judgeTask(task, run.content, {
        baseUrl: cfg.gatewayBaseUrl,
        token: cfg.judgeConnectionToken,
        model: cfg.judgeModel,
        timeoutMs: cfg.timeoutMs,
      });
    } catch (err) {
      errors.push({
        taskId: task.id,
        error: `judge failed: ${err instanceof Error ? err.message : String(err)}`,
      });
      hooks.onTask?.(null, task, index, tasks.length);
      return;
    }

    const { earned, maxPositive, normalized } = scoreTask(task.rubric, judged.verdicts);
    const m = run.cascadeMeta ?? {};
    const score: TaskScore = {
      taskId: task.id,
      domain: task.domain,
      earned,
      maxPositive,
      normalized,
      verdicts: judged.verdicts,
      runCostUsd: run.costUsd,
      judgeCostUsd: judged.costUsd,
      latencyMs: run.latencyMs,
      stage: typeof m.stage === 'string' ? m.stage : undefined,
      escalated: typeof m.escalated === 'boolean' ? m.escalated : undefined,
      escalationReason: (m.escalation_reason as string | null | undefined) ?? null,
      classifierTier: typeof m.tier === 'string' ? m.tier : undefined,
      agreementMethod:
        m.agreement && typeof m.agreement === 'object'
          ? ((m.agreement as Record<string, unknown>).method as string | undefined)
          : undefined,
      finalModel: typeof m.final_model === 'string' ? m.final_model : undefined,
    };
    taskScores.push(score);
    hooks.onTask?.(score, task, index, tasks.length);
  });

  const byDomain: Record<string, number> = {};
  const domainBuckets = new Map<string, number[]>();
  for (const s of taskScores) {
    if (!domainBuckets.has(s.domain)) domainBuckets.set(s.domain, []);
    domainBuckets.get(s.domain)!.push(s.normalized);
  }
  for (const [domain, vals] of domainBuckets) byDomain[domain] = mean(vals);

  // Per-stage rollup: how often each tier produced the answer, and its score/cost.
  const stageBuckets = new Map<string, { scores: number[]; costs: number[] }>();
  for (const s of taskScores) {
    const key = s.stage ?? 'unknown';
    if (!stageBuckets.has(key)) stageBuckets.set(key, { scores: [], costs: [] });
    const b = stageBuckets.get(key)!;
    b.scores.push(s.normalized);
    b.costs.push(s.runCostUsd);
  }
  const stageOrder = ['tier0', 'tier1', 'tier2', 'solo', 'unknown'];
  const byStage = [...stageBuckets.entries()]
    .sort((a, b) => stageOrder.indexOf(a[0]) - stageOrder.indexOf(b[0]))
    .map(([stage, b]) => ({
      stage,
      count: b.scores.length,
      meanNormalized: mean(b.scores),
      meanRunCostUsd: mean(b.costs),
    }));

  const totalRunCostUsd = taskScores.reduce((s, t) => s + t.runCostUsd, 0);
  const totalJudgeCostUsd = taskScores.reduce((s, t) => s + t.judgeCostUsd, 0);

  return {
    startedAt,
    finishedAt: nowIso(),
    model: cfg.model,
    judgeModel: cfg.judgeModel,
    config: {
      gatewayBaseUrl: cfg.gatewayBaseUrl,
      concurrency: cfg.concurrency,
      maxTokens: cfg.maxTokens,
      cascadeOverrides: cfg.cascadeOverrides,
    },
    taskScores,
    meanNormalized: mean(taskScores.map((t) => t.normalized)),
    byDomain,
    byStage,
    totalRunCostUsd,
    totalJudgeCostUsd,
    totalCostUsd: totalRunCostUsd + totalJudgeCostUsd,
    errors,
  };
}
