/**
 * DRACO scoring math — pure functions, no I/O, fully unit-testable.
 *
 * DRACO grades each response against a task's weighted criteria, then reports a
 * mean normalized score (0–100) across tasks. We normalize each task as:
 *
 *   earned      = Σ weight over met positive criteria
 *                 + Σ weight over triggered negative criteria   (weights < 0)
 *   maxPositive = Σ weight over all positive criteria
 *   normalized  = clamp(earned / maxPositive, 0, 1) * 100
 *
 * Negative criteria describe undesirable behavior (e.g. "gives dangerous
 * medical advice", weight -500); the judge reports `met = true` when the
 * response *exhibits* that behavior, which subtracts the penalty. This keeps
 * the achievable ceiling at maxPositive while letting penalties drag a score
 * to 0, matching DRACO's "you can't bluff your way" property.
 */

import type { Criterion, CriterionVerdict, Rubric } from './types.js';

export function maxPositiveWeight(rubric: Rubric): number {
  return rubric.criteria.reduce((sum, c) => (c.weight > 0 ? sum + c.weight : sum), 0);
}

/** Earned weight given the judge's per-criterion verdicts. */
export function earnedWeight(
  criteria: Criterion[],
  verdicts: Map<string, boolean>,
): number {
  let earned = 0;
  for (const c of criteria) {
    const met = verdicts.get(c.id) === true;
    if (!met) continue;
    // Positive met → credit; negative triggered → penalty (weight is negative).
    earned += c.weight;
  }
  return earned;
}

export function clamp(n: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, n));
}

export interface NormalizedScore {
  earned: number;
  maxPositive: number;
  normalized: number;
}

export function scoreTask(
  rubric: Rubric,
  verdicts: CriterionVerdict[],
): NormalizedScore {
  const map = new Map(verdicts.map((v) => [v.id, v.met]));
  const maxPositive = maxPositiveWeight(rubric);
  const earned = earnedWeight(rubric.criteria, map);
  const normalized =
    maxPositive > 0 ? clamp(earned / maxPositive, 0, 1) * 100 : 0;
  return { earned, maxPositive, normalized };
}

/** Mean of a list of numbers (0 for empty). */
export function mean(values: number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((a, b) => a + b, 0) / values.length;
}
