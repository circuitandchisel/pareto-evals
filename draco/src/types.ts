/**
 * Shared types for the DRACO × cascade benchmark.
 *
 * DRACO ships as a single `test.jsonl` (perplexity-ai/draco, MIT). Each row is
 * a deep-research task whose `answer` field is a JSON-encoded weighted rubric.
 */

/** One DRACO row as it appears on disk. */
export interface RawDracoRow {
  id: string;
  domain: string;
  problem: string;
  /** JSON-encoded {@link Rubric}. */
  answer: string;
}

/** A single weighted grading criterion. Weight may be negative (a penalty). */
export interface Criterion {
  id: string;
  /** Integer in DRACO's range (~ -500..+20). Negative = penalty if triggered. */
  weight: number;
  /** Natural-language description the judge evaluates the response against. */
  requirement: string;
  /** Axis this criterion belongs to (factual-accuracy, citation-quality, ...). */
  section: string;
}

/** Parsed rubric for one task. */
export interface Rubric {
  id: string;
  criteria: Criterion[];
}

/** A benchmark task: the problem plus its parsed rubric. */
export interface Task {
  id: string;
  domain: string;
  problem: string;
  rubric: Rubric;
}

/** Token usage for a single model call. */
export interface Usage {
  inputTokens: number;
  outputTokens: number;
}

/** Result of running the system-under-test on one task. */
export interface CascadeRunResult {
  taskId: string;
  /** Final assistant answer text. */
  content: string;
  /** Model label returned by the gateway (e.g. "auto-cascade:anthropic/..."). */
  model: string;
  usage: Usage;
  /** USD cost of the run, summed across every internal cascade call. */
  costUsd: number;
  /** Wall-clock latency of the run in ms. */
  latencyMs: number;
  /** Raw `_meta.cascade` telemetry from the gateway, if present. */
  cascadeMeta: Record<string, unknown> | null;
  /** Set when the run failed; `content` will be empty. */
  error?: string;
}

/** The judge's verdict on a single criterion. */
export interface CriterionVerdict {
  id: string;
  /**
   * For positive-weight criteria: true = requirement satisfied.
   * For negative-weight criteria: true = the penalized behavior was present.
   */
  met: boolean;
  rationale: string;
}

/** Scored result for one task. */
export interface TaskScore {
  taskId: string;
  domain: string;
  /** Sum of earned weights (positives met minus penalties triggered). */
  earned: number;
  /** Sum of all positive weights — the achievable ceiling. */
  maxPositive: number;
  /** Normalized 0–100 = clamp(earned / maxPositive, 0, 1) * 100. */
  normalized: number;
  verdicts: CriterionVerdict[];
  /** Cost of the SUT run for this task. */
  runCostUsd: number;
  /** Cost of the judge call for this task. */
  judgeCostUsd: number;
  /** End-to-end wall-clock latency of the SUT run (ms). */
  latencyMs?: number;
  /** Cascade stage that produced the answer: tier0|tier1|tier2|solo (if known). */
  stage?: string;
  /** Whether the cascade escalated to the Tier 2 panel. */
  escalated?: boolean;
  /** Why it escalated (probe-disagreement | reasoning-tier), if it did. */
  escalationReason?: string | null;
  /** Classifier tier (SIMPLE|MEDIUM|COMPLEX|REASONING). */
  classifierTier?: string;
  /** How the Tier-1 agreement was decided (embedding|judge). */
  agreementMethod?: string;
  /** Final model that produced the answer. */
  finalModel?: string;
}

/** Per-stage rollup for tuning visibility. */
export interface StageStats {
  stage: string;
  count: number;
  meanNormalized: number;
  meanRunCostUsd: number;
}

/** A full benchmark run across many tasks. */
export interface BenchmarkReport {
  /** ISO timestamp injected by the caller (Date is unavailable in some envs). */
  startedAt: string;
  finishedAt: string;
  model: string;
  judgeModel: string;
  config: Record<string, unknown>;
  taskScores: TaskScore[];
  /** Mean normalized score across scored tasks (DRACO's headline metric). */
  meanNormalized: number;
  /** Mean normalized score per domain. */
  byDomain: Record<string, number>;
  /** Per-stage distribution (count, mean score, mean cost) for tuning. */
  byStage: StageStats[];
  totalRunCostUsd: number;
  totalJudgeCostUsd: number;
  totalCostUsd: number;
  /** Tasks that errored during the SUT run (excluded from scoring). */
  errors: { taskId: string; error: string }[];
}
