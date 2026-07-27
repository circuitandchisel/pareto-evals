/** Human-readable summary of a benchmark report. */

import { fileURLToPath } from 'node:url';
import type { BenchmarkReport } from './types.js';

export function formatReport(r: BenchmarkReport): string {
  const lines: string[] = [];
  lines.push('═══════════════════════════════════════════════');
  lines.push(`DRACO × cascade — ${r.model}`);
  lines.push('═══════════════════════════════════════════════');
  lines.push(`Mean normalized score : ${r.meanNormalized.toFixed(2)} / 100`);
  lines.push(`Tasks scored          : ${r.taskScores.length}`);
  lines.push(`Errors                : ${r.errors.length}`);
  lines.push('');
  lines.push('By domain:');
  for (const [domain, score] of Object.entries(r.byDomain).sort()) {
    lines.push(`  ${domain.padEnd(22)} ${score.toFixed(1)}`);
  }
  if (r.byStage && r.byStage.length > 0) {
    const total = r.byStage.reduce((s, x) => s + x.count, 0) || 1;
    lines.push('');
    lines.push('By stage (tier distribution):');
    lines.push(`  ${'stage'.padEnd(8)} ${'n'.padStart(3)} ${'share'.padStart(6)} ${'score'.padStart(6)} ${'$/task'.padStart(8)}`);
    for (const s of r.byStage) {
      lines.push(
        `  ${s.stage.padEnd(8)} ${String(s.count).padStart(3)} ` +
          `${((s.count / total) * 100).toFixed(0).padStart(5)}% ` +
          `${s.meanNormalized.toFixed(1).padStart(6)} ` +
          `$${s.meanRunCostUsd.toFixed(4).padStart(7)}`,
      );
    }
  }
  lines.push('');
  const lats = r.taskScores.map((t) => t.latencyMs).filter((x): x is number => typeof x === 'number').sort((a, b) => a - b);
  if (lats.length) {
    const med = lats[Math.floor(lats.length / 2)] / 1000;
    const p95 = lats[Math.min(lats.length - 1, Math.floor(lats.length * 0.95))] / 1000;
    lines.push('');
    lines.push(`Latency/task : median ${med.toFixed(0)}s, p95 ${p95.toFixed(0)}s, max ${(lats[lats.length - 1] / 1000).toFixed(0)}s`);
  }
  lines.push('');
  lines.push('Cost:');
  lines.push(`  run (SUT)  : $${r.totalRunCostUsd.toFixed(5)}`);
  lines.push(`  judge      : $${r.totalJudgeCostUsd.toFixed(5)}  (estimated)`);
  lines.push(`  total      : $${r.totalCostUsd.toFixed(5)}`);
  if (r.taskScores.length > 0) {
    lines.push(
      `  per task   : $${(r.totalCostUsd / r.taskScores.length).toFixed(5)} avg`,
    );
  }
  if (r.errors.length > 0) {
    lines.push('');
    lines.push('Errors:');
    for (const e of r.errors) lines.push(`  ${e.taskId}: ${e.error}`);
  }
  return lines.join('\n');
}

// CLI: `tsx src/report.ts results/run-*.json` to re-print a saved report.
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const path = process.argv[2];
  if (path) {
    const { readFile } = await import('node:fs/promises');
    const r = JSON.parse(await readFile(path, 'utf8')) as BenchmarkReport;
    console.log(formatReport(r));
  }
}
