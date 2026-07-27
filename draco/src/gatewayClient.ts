/**
 * Thin client for the ATXP LLM gateway's OpenAI-compatible chat endpoint.
 * Used for both the system-under-test (auto-cascade) and the judge.
 */

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface ChatResult {
  content: string;
  model: string;
  usage: { inputTokens: number; outputTokens: number };
  /** USD cost for the call, when the gateway reports it (cascade: _meta). */
  costUsd: number;
  cascadeMeta: Record<string, unknown> | null;
  raw: unknown;
}

export interface ChatOptions {
  baseUrl: string;
  token: string;
  model: string;
  messages: ChatMessage[];
  maxTokens?: number;
  timeoutMs?: number;
  /** Extra top-level body fields (e.g. cascade per-request overrides). */
  extraBody?: Record<string, unknown>;
  /** Force a JSON object response (judge). */
  jsonMode?: boolean;
  /**
   * Request a streamed (SSE) response. The cascade emits keepalive heartbeats
   * while it works, so long tool-using runs don't trip the load balancer's idle
   * timeout. The final SSE chunk still carries usage + _meta (cost).
   */
  stream?: boolean;
}

function extractContent(json: unknown): string {
  const choices = (json as { choices?: unknown })?.choices;
  if (!Array.isArray(choices) || choices.length === 0) return '';
  const message = (choices[0] as { message?: { content?: unknown } })?.message;
  const content = message?.content;
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    return content
      .map((p) =>
        p && typeof p === 'object' && 'text' in p ? String((p as { text?: unknown }).text ?? '') : '',
      )
      .join('');
  }
  return '';
}

/** Read base cost from cascade telemetry; falls back to 0 when absent. */
function costFromMeta(meta: Record<string, unknown> | null): number {
  if (!meta) return 0;
  const raw = meta['base_cost_usd'] ?? meta['baseCostUsd'] ?? meta['cost_usd'];
  const n = Number(raw);
  return Number.isFinite(n) ? n : 0;
}

/**
 * Collapse an SSE stream (OpenAI chat.completion.chunk format) into a single
 * pseudo chat.completion object. Ignores `:` heartbeat comment lines. Reads the
 * content from delta chunks and usage/_meta from whichever chunk carries them.
 */
export function parseSSE(text: string): unknown {
  let content = '';
  let usage: unknown;
  let meta: unknown;
  let model: unknown;
  let id: unknown;
  for (const rawLine of text.split('\n')) {
    const line = rawLine.trimEnd();
    if (!line.startsWith('data:')) continue; // skip ": keepalive" comments + blanks
    const payload = line.slice(5).trim();
    if (!payload || payload === '[DONE]') continue;
    let chunk: Record<string, unknown>;
    try {
      chunk = JSON.parse(payload) as Record<string, unknown>;
    } catch {
      continue;
    }
    if ((chunk as { error?: unknown }).error) {
      const e = (chunk as { error?: { message?: string } }).error;
      throw new Error(`gateway stream error: ${e?.message ?? JSON.stringify(e)}`);
    }
    if (chunk.model) model = chunk.model;
    if (chunk.id) id = chunk.id;
    if (chunk.usage) usage = chunk.usage;
    if (chunk._meta) meta = chunk._meta;
    const choices = chunk.choices as Array<{ delta?: { content?: unknown } }> | undefined;
    const delta = choices?.[0]?.delta?.content;
    if (typeof delta === 'string') content += delta;
  }
  return {
    id,
    model,
    usage,
    _meta: meta,
    choices: [{ index: 0, message: { role: 'assistant', content }, finish_reason: 'stop' }],
  };
}

export async function chat(opts: ChatOptions): Promise<ChatResult> {
  const body: Record<string, unknown> = {
    model: opts.model,
    messages: opts.messages,
    stream: !!opts.stream,
    ...(opts.maxTokens ? { max_tokens: opts.maxTokens } : {}),
    ...(opts.jsonMode ? { response_format: { type: 'json_object' } } : {}),
    ...(opts.extraBody ?? {}),
  };

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), opts.timeoutMs ?? 300_000);
  let res: Response;
  let text: string;
  try {
    res = await fetch(`${opts.baseUrl}/v1/chat/completions`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        authorization: `Bearer ${opts.token}`,
        ...(opts.stream ? { accept: 'text/event-stream' } : {}),
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    // Read the full body before clearing the timeout — for a streamed cascade
    // run this blocks (kept alive by heartbeats) until the server finishes.
    text = await res.text();
  } finally {
    clearTimeout(timer);
  }

  if (!res.ok) {
    let errJson: unknown = null;
    try {
      errJson = text ? JSON.parse(text) : null;
    } catch {
      /* not JSON */
    }
    const detail =
      (errJson as { error?: { message?: string } })?.error?.message ||
      (errJson as { error?: string })?.error ||
      text.slice(0, 300) ||
      res.statusText;
    throw new Error(`gateway ${res.status}: ${detail}`);
  }

  let json: unknown = null;
  if (opts.stream) {
    json = parseSSE(text);
  } else {
    try {
      json = text ? JSON.parse(text) : null;
    } catch {
      json = null;
    }
  }

  const usageRaw = (json as { usage?: { prompt_tokens?: number; completion_tokens?: number } })
    ?.usage;
  const meta = ((json as { _meta?: { cascade?: Record<string, unknown> } })?._meta?.cascade ??
    null) as Record<string, unknown> | null;

  return {
    content: extractContent(json),
    model: String((json as { model?: unknown })?.model ?? opts.model),
    usage: {
      inputTokens: Number(usageRaw?.prompt_tokens ?? 0),
      outputTokens: Number(usageRaw?.completion_tokens ?? 0),
    },
    costUsd: costFromMeta(meta),
    cascadeMeta: meta,
    raw: json,
  };
}
