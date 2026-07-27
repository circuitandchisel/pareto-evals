/**
 * The judge grades a response against a task's weighted rubric, returning a
 * met/not-met verdict per criterion. Routed through the gateway so its cost is
 * visible too. Mirrors DRACO's methodology (Perplexity used a strong model as
 * judge; OpenRouter used Gemini 3.1 Pro).
 */

import { chat, type ChatResult } from './gatewayClient.js';
import type { Task, CriterionVerdict, Usage } from './types.js';

export const JUDGE_SYSTEM = `You are a meticulous grader for the DRACO deep-research benchmark.
You are given a research TASK, a model's RESPONSE, and a list of weighted CRITERIA.
For each criterion, decide whether it is "met".

Semantics:
- Positive-weight criteria describe something the response SHOULD do. met=true means the response satisfies it.
- Negative-weight criteria describe something the response should NOT do (e.g. dangerous advice, fabricated citations). met=true means the response EXHIBITS that undesirable behavior.

Grade strictly and literally against each requirement. Do not reward plausible-sounding but unverifiable claims. If a criterion requires a citation or a specific fact and it is absent or wrong, it is not met.

Return ONLY a JSON object: {"verdicts":[{"id":"<criterion id>","met":true|false,"rationale":"<≤8 words>"}]}. Keep rationale extremely short (≤8 words, no quotes). Include every criterion id exactly once.`;

/** Rough per-model judge pricing (USD per 1M tokens) for cost estimation. */
const JUDGE_PRICE: Record<string, { in: number; out: number }> = {
  gemini: { in: 1.25, out: 10 },
  opus: { in: 5, out: 25 },
  sonnet: { in: 3, out: 15 },
  'gpt-5': { in: 1.25, out: 10 },
};

function estimateJudgeCost(model: string, usage: Usage): number {
  const key = Object.keys(JUDGE_PRICE).find((k) => model.toLowerCase().includes(k));
  if (!key) return 0;
  const p = JUDGE_PRICE[key];
  return (usage.inputTokens * p.in + usage.outputTokens * p.out) / 1_000_000;
}

export function buildUserPrompt(task: Task, response: string): string {
  const criteria = task.rubric.criteria
    .map(
      (c) =>
        `- id: ${c.id} | weight: ${c.weight} | section: ${c.section}\n  requirement: ${c.requirement}`,
    )
    .join('\n');
  return [
    `TASK:\n${task.problem}`,
    `\nRESPONSE:\n${response || '(empty response)'}`,
    `\nCRITERIA (${task.rubric.criteria.length}):\n${criteria}`,
  ].join('\n');
}

export interface JudgeOutcome {
  verdicts: CriterionVerdict[];
  costUsd: number;
  usage: Usage;
}

/** Parse the judge's JSON, tolerating fenced code blocks and stray prose. */
/**
 * Salvage verdicts from a possibly-truncated judge response. Strict JSON parse
 * first; on failure (e.g. the judge ran out of tokens mid-array), recover every
 * complete {"id":...,"met":...} pair by regex so a cut-off tail loses only the
 * trailing verdicts, not the whole grade.
 */
export function parseJudgeResponse(text: string): CriterionVerdict[] {
  let payload = text.trim();
  const fence = payload.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (fence) payload = fence[1].trim();
  if (!payload.startsWith('{')) {
    const start = payload.indexOf('{');
    const end = payload.lastIndexOf('}');
    if (start >= 0 && end > start) payload = payload.slice(start, end + 1);
  }

  try {
    const parsed = JSON.parse(payload) as { verdicts?: Array<Partial<CriterionVerdict>> };
    const out: CriterionVerdict[] = [];
    for (const v of parsed.verdicts ?? []) {
      if (typeof v.id !== 'string') continue;
      out.push({ id: v.id, met: v.met === true, rationale: String(v.rationale ?? '') });
    }
    if (out.length > 0) return out;
  } catch {
    // fall through to salvage
  }

  return salvageVerdicts(text);
}

/** Regex-recover id/met pairs, tolerant of key order and truncation. */
export function salvageVerdicts(text: string): CriterionVerdict[] {
  const out: CriterionVerdict[] = [];
  const seen = new Set<string>();
  // Match objects exposing both "id" and "met" in either order.
  const re =
    /\{[^{}]*?"id"\s*:\s*"([^"]+)"[^{}]*?"met"\s*:\s*(true|false)[^{}]*?\}|\{[^{}]*?"met"\s*:\s*(true|false)[^{}]*?"id"\s*:\s*"([^"]+)"[^{}]*?\}/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    const id = m[1] ?? m[4];
    const met = (m[2] ?? m[3]) === 'true';
    if (!id || seen.has(id)) continue;
    seen.add(id);
    out.push({ id, met, rationale: '' });
  }
  return out;
}

export async function judgeTask(
  task: Task,
  response: string,
  opts: { baseUrl: string; token: string; model: string; timeoutMs?: number },
): Promise<JudgeOutcome> {
  const result: ChatResult = await chat({
    baseUrl: opts.baseUrl,
    token: opts.token,
    model: opts.model,
    timeoutMs: opts.timeoutMs,
    jsonMode: true,
    maxTokens: 16000,
    messages: [
      { role: 'system', content: JUDGE_SYSTEM },
      { role: 'user', content: buildUserPrompt(task, response) },
    ],
  });

  const verdicts = parseJudgeResponse(result.content);
  // Any criterion the judge omitted is treated as not-met (no credit, no penalty).
  const seen = new Set(verdicts.map((v) => v.id));
  for (const c of task.rubric.criteria) {
    if (!seen.has(c.id)) {
      verdicts.push({ id: c.id, met: false, rationale: 'omitted by judge' });
    }
  }

  return {
    verdicts,
    usage: result.usage,
    costUsd: result.costUsd || estimateJudgeCost(opts.model, result.usage),
  };
}
