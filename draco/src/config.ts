/** Central configuration, sourced from environment (.env loaded by callers). */

export interface BenchConfig {
  gatewayBaseUrl: string;
  connectionToken: string;
  model: string;
  judgeModel: string;
  judgeConnectionToken: string;
  concurrency: number;
  timeoutMs: number;
  maxTokens: number;
  /** Per-request cascade overrides forwarded on the request body (if set). */
  cascadeOverrides: Record<string, number>;
}

function num(value: string | undefined, fallback: number): number {
  const n = value === undefined || value === '' ? NaN : Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function optionalNum(
  out: Record<string, number>,
  key: string,
  value: string | undefined,
): void {
  if (value !== undefined && value !== '') {
    const n = Number(value);
    if (Number.isFinite(n)) out[key] = n;
  }
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): BenchConfig {
  // Bearer API key for your OpenAI-compatible endpoint. GATEWAY_API_KEY is the
  // generic name; ATXP_CONNECTION_TOKEN kept as a fallback for legacy configs.
  const connectionToken = env.GATEWAY_API_KEY ?? env.ATXP_CONNECTION_TOKEN ?? '';
  const cascadeOverrides: Record<string, number> = {};
  optionalNum(cascadeOverrides, 'tier0_confidence', env.CASCADE_TIER0_CONFIDENCE);
  optionalNum(cascadeOverrides, 'embedding_high', env.CASCADE_EMBEDDING_HIGH);
  optionalNum(cascadeOverrides, 'embedding_low', env.CASCADE_EMBEDDING_LOW);

  return {
    gatewayBaseUrl: (env.GATEWAY_BASE_URL ?? 'http://localhost:3000').replace(/\/$/, ''),
    connectionToken,
    model: env.BENCH_MODEL ?? 'auto',
    judgeModel: env.JUDGE_MODEL ?? 'google-ai-studio/gemini-3-pro',
    judgeConnectionToken: env.JUDGE_CONNECTION_TOKEN || connectionToken,
    concurrency: num(env.BENCH_CONCURRENCY, 3),
    timeoutMs: num(env.BENCH_TIMEOUT_MS, 1_200_000),
    maxTokens: num(env.BENCH_MAX_TOKENS, 4000),
    cascadeOverrides,
  };
}
