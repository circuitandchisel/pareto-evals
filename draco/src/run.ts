/**
 * CLI entry point: run the DRACO benchmark against the cascade.
 *
 * Usage:
 *   tsx src/run.ts [--limit N] [--domain D] [--tasks id1,id2] [--out file.json]
 *                  [--model M] [--judge M] [--dry-run]
 */

import 'dotenv/config';
import { writeFile, mkdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadConfig } from './config.js';
import { ensureDataset, loadTasks } from './dataset.js';
import { runBenchmark } from './runner.js';
import { formatReport } from './report.js';
import type { Task } from './types.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const RESULTS_DIR = join(HERE, '..', 'results');

function parseArgs(argv: string[]): Record<string, string | boolean> {
  const out: Record<string, string | boolean> = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) continue;
    const key = a.slice(2);
    const next = argv[i + 1];
    if (next === undefined || next.startsWith('--')) {
      out[key] = true;
    } else {
      out[key] = next;
      i++;
    }
  }
  return out;
}

function selectTasks(all: Task[], args: Record<string, string | boolean>): Task[] {
  let tasks = all;
  if (typeof args.domain === 'string') {
    const d = args.domain.toLowerCase();
    tasks = tasks.filter((t) => t.domain.toLowerCase() === d);
  }
  if (typeof args.tasks === 'string') {
    const ids = new Set(args.tasks.split(',').map((s) => s.trim()));
    tasks = tasks.filter((t) => ids.has(t.id));
  }
  const offset = typeof args.offset === 'string' ? Number(args.offset) : 0;
  if (offset || typeof args.limit === 'string') {
    const end = typeof args.limit === 'string' ? offset + Number(args.limit) : undefined;
    tasks = tasks.slice(offset, end);
  }
  return tasks;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const cfg = loadConfig();
  if (typeof args.model === 'string') cfg.model = args.model;
  if (typeof args.judge === 'string') cfg.judgeModel = args.judge;

  if (!cfg.connectionToken && !args['dry-run']) {
    console.error('ATXP_CONNECTION_TOKEN is required (set it in .env). Use --dry-run to list tasks only.');
    process.exit(1);
  }

  await ensureDataset();
  const all = await loadTasks();
  const tasks = selectTasks(all, args);

  console.log(`DRACO × cascade benchmark`);
  console.log(`  gateway:  ${cfg.gatewayBaseUrl}`);
  console.log(`  model:    ${cfg.model}`);
  console.log(`  judge:    ${cfg.judgeModel}`);
  console.log(`  tasks:    ${tasks.length} / ${all.length}`);
  if (Object.keys(cfg.cascadeOverrides).length) {
    console.log(`  overrides: ${JSON.stringify(cfg.cascadeOverrides)}`);
  }
  console.log('');

  if (args['dry-run']) {
    for (const t of tasks) {
      console.log(`  ${t.id}  [${t.domain}]  ${t.rubric.criteria.length} criteria  ${t.problem.slice(0, 70)}…`);
    }
    console.log(`\nDry run: ${tasks.length} tasks selected, nothing executed.`);
    return;
  }

  const report = await runBenchmark(tasks, cfg, {
    onTask: (score, task, index, total) => {
      const n = String(index + 1).padStart(String(total).length);
      if (score) {
        console.log(
          `  [${n}/${total}] ${task.id} [${task.domain}] score=${score.normalized.toFixed(1)} cost=$${score.runCostUsd.toFixed(5)}`,
        );
      } else {
        console.log(`  [${n}/${total}] ${task.id} [${task.domain}] ERROR`);
      }
    },
  });

  await mkdir(RESULTS_DIR, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const outPath =
    typeof args.out === 'string' ? args.out : join(RESULTS_DIR, `run-${stamp}.json`);
  await writeFile(outPath, JSON.stringify(report, null, 2), 'utf8');

  console.log('');
  console.log(formatReport(report));
  console.log(`\nFull results written to ${outPath}`);
}

main().catch((err) => {
  console.error(err instanceof Error ? err.stack || err.message : err);
  process.exit(1);
});
