/**
 * DRACO dataset loader.
 *
 * Source: https://huggingface.co/datasets/perplexity-ai/draco (MIT).
 * Single file `test.jsonl`; each row's `answer` is a JSON-encoded rubric of the
 * shape { id, sections: [{ id, criteria: [{ id, weight, requirement }] }] }.
 */

import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RawDracoRow, Rubric, Criterion, Task } from './types.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const DATA_DIR = join(HERE, '..', 'data');
export const DATASET_PATH = join(DATA_DIR, 'test.jsonl');
const HF_URL =
  'https://huggingface.co/datasets/perplexity-ai/draco/resolve/main/test.jsonl';

/** Download test.jsonl from HuggingFace if not already present. */
export async function ensureDataset(force = false): Promise<string> {
  if (!force && existsSync(DATASET_PATH)) return DATASET_PATH;
  await mkdir(DATA_DIR, { recursive: true });
  const res = await fetch(HF_URL);
  if (!res.ok) {
    throw new Error(`Failed to download DRACO dataset: ${res.status} ${res.statusText}`);
  }
  const text = await res.text();
  await writeFile(DATASET_PATH, text, 'utf8');
  return DATASET_PATH;
}

/** Parse a rubric `answer` blob into a flat, section-tagged criteria list. */
export function parseRubric(answer: string): Rubric {
  const parsed = JSON.parse(answer) as {
    id?: string;
    sections?: Array<{ id?: string; criteria?: Array<Partial<Criterion>> }>;
  };
  const criteria: Criterion[] = [];
  for (const section of parsed.sections ?? []) {
    const sectionId = section.id ?? 'unknown';
    for (const c of section.criteria ?? []) {
      if (c.id === undefined || c.weight === undefined || c.requirement === undefined) {
        continue;
      }
      criteria.push({
        id: c.id,
        weight: Number(c.weight),
        requirement: c.requirement,
        section: sectionId,
      });
    }
  }
  return { id: parsed.id ?? 'unknown', criteria };
}

/** Convert a raw row to a Task. */
export function rowToTask(row: RawDracoRow): Task {
  return {
    id: row.id,
    domain: row.domain,
    problem: row.problem,
    rubric: parseRubric(row.answer),
  };
}

/** Load and parse all tasks from a JSONL file (defaults to the cached dataset). */
export async function loadTasks(path = DATASET_PATH): Promise<Task[]> {
  const text = await readFile(path, 'utf8');
  const tasks: Task[] = [];
  for (const line of text.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    tasks.push(rowToTask(JSON.parse(trimmed) as RawDracoRow));
  }
  return tasks;
}

// CLI: `tsx src/dataset.ts --download` to fetch + report basic stats.
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const force = process.argv.includes('--download');
  ensureDataset(force)
    .then(loadTasks)
    .then((tasks) => {
      const domains = new Map<string, number>();
      let crit = 0;
      for (const t of tasks) {
        domains.set(t.domain, (domains.get(t.domain) ?? 0) + 1);
        crit += t.rubric.criteria.length;
      }
      console.log(`Loaded ${tasks.length} tasks, ${crit} criteria total.`);
      console.log('Domains:', Object.fromEntries([...domains].sort()));
    })
    .catch((err) => {
      console.error(err instanceof Error ? err.message : err);
      process.exit(1);
    });
}
