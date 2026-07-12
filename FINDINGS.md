# RC Benchmark Findings — Consolidated (2026-07-12)

**RC = consensus-gated cascade**: cheap self-hosted **tier-1 flash panel**
(deepseek-v4-flash, qwen3.6-35b-a3b, llama-3.3-70b) → route/agreement gate →
**tier-2 flagship** (Grok-4.5 via direct xAI; GLM-5.2 for some paths). Agentic
work uses the **leader** path (GLM-solo-leader + gated flash reviewer + sparse
Grok escalation). All numbers below are the grok-RC config, self-hosted stack
(3.135.204.148 gpu-router + 8× H200 tier-1 replicas + GLM corp endpoint + xAI).

## Scorecard vs Opus (contamination-checked, properly graded)

| Benchmark | Type | Cascade RC | Comparison | Verdict |
|---|---|---|---|---|
| **HLE** (text, no-tools) | mixed reasoning/knowledge | **38%** @ $0.115/task | Opus-4.8 **30-33%** | **WIN** (acc + ~⅓ cheaper) |
| **GPQA-Diamond** | knowledge-reasoning MCQ | **87–97%** @ ~½ Opus cost | Opus-4.8 86% | **WIN** |
| **TB2.1** (terminus-2) | agentic terminal | **27.7/40** (n=3) | solo-Grok 28.3/40 | **PARITY** (~2% grok escalation) |
| **SWE-rebench** (clean) | agentic coding | **62.5%** (15/24) | solo-Grok 66.7%; Opus-4.6 LB 65.3% | **PARITY, frontier-competitive** |
| **MMMU-Pro** | vision | **76.5%** | qwen-vl 63.2%, grok-solo 78.8% | qwen-vl→Grok swap +13pts |
| ArXivMath (clean) | all-hard math | ~35% (capped) / ≈solo uncapped | solo-Grok 52.5% | cascade ≈ solo (no edge) |
| ~~HMMT-2026~~ | math | — | — | **DROPPED — Grok-contaminated (100%)** |
| ~~SWE-Bench Pro~~ | agentic coding | — | — | **DROPPED — contaminated (92% & solo 83%)** |

**Pattern that holds up to scrutiny:** the cascade **wins on mixed
reasoning/knowledge** (HLE, GPQA), **ties solo-Grok on agentic** (TB2.1,
SWE-rebench) at a fraction of the Grok cost, and has **no edge on all-hard math**
(everything escalates → cascade ≈ solo).

## Key methodology findings

- **Contamination caught on two benchmarks.** HMMT-Feb-2026: Grok-solo scored
  100% (public MathArena set ≤ model cutoff) → dropped. SWE-Bench Pro: both
  cascade (92%) and solo-Grok (83%) scored ~2× frontier on public repos → dropped.
  Replaced with **contamination-clean** sets: **ArXivMath** (arXiv-derived,
  post-cutoff months) for math, **SWE-rebench** (GitHub issues filed+resolved
  after model cutoffs, monthly splits) for coding.
- **Graders matter more than expected.** (1) `math-verify` silently fails to
  parse `\dfrac`/bare-symbolic → false negatives; fixed with canonicalization +
  numeric guard, and for research-math answers use an **LLM judge** (gpt-5.5).
  (2) Free-form/symbolic answers (HLE, ArXivMath) require an LLM judge, not string
  match. (3) SWE grading MUST apply the official `test_patch` (the Scale/Pro
  grader skipped it → gameable); the SWE-rebench fork does it right.
- **The cascade's cost win is on MIXED difficulty.** On agentic (TB2.1) it calls
  Grok on only ~2% of steps yet matches solo-Grok — huge cost saving. On all-hard
  math everything escalates → no saving (cascade ≈ solo in cost + accuracy).

## Engineering delivered

- **3× tier-1 replica capacity** across 8× H200 (deepseek TP2 + qwen + llama +
  bge, ×2 replicas + router-node originals), registered as gpu-router backends
  (load-balanced). `max-num-seqs` raised 24→64 → **clean concurrency** (two
  grok-heavy benchmarks run together with 0 flash-502s). qwen-vl decommissioned
  (Grok replaced it for vision + tier-2).
- **Cascade code (committed, draco-bench-box):** synth-skip when tier-2 panel has
  one draft (halves tier-2 latency/cost, no degradation); xAI direct-cost patch
  (`usage.cost_in_usd_ticks/1e10`); tier-1 reasoning **scoped to flagships**
  (`LC_REASONING_EFFORT_MODELS`) so tier-1 is the FAST tier — **HLE 206s→69s
  (~3×), accuracy held, GPQA 96.7% (no regression)**.
- **Harnesses:** pareto-evals runners (HLE, GPQA, ArXivMath, MMMU-Pro, Arc,
  HMMT) via one `model_complete` endpoint; SWE-rebench via mini-swe-agent +
  the **SWE-rebench fork** grader (reads `install_config`, applies `test_patch`).
  mini needed 4 patches for images/cost/entrypoint (documented).

## Caveats (for honest publication)

- **Latency:** the cascade is much slower per item than Opus on hard reasoning
  (HLE ~69s tuned vs Opus ~14s) — accuracy+cost win comes with a latency cost.
- **n / variance:** HLE cascade side is n=100 (s1 too slow to finish); HLE
  100-slice variance ±6. SWE-rebench n=24, single-attempt (leaderboard uses
  best-of-5). GPQA tuned n=30. These want larger n before final publication.
- **Cost basis:** "cheaper" is API-priced (~⅓–½ Opus), not the aspirational
  "¼ cost" (that assumed owned-GPU amortization).
- **run.ts** (old harness) has a grok-direct-xAI flagship-drop bug → use the
  **8095 server path** for grok-RC benchmarks.

## Next (clean-repro slate)

Autonomous clean-slate batch kicked off on the bench box (`run_slate.sh`):
GPQA (full 197) → ArXivMath (full 40) → HLE (300-slice) → SWE-rebench (40-slice),
each with the tuned RC config, seeded, proper grading, logged to
`slate_summary.txt`. Remaining for a full clean pass: larger n on all, matched-Opus
latency capture, MMMU-Pro full + DRACO, and TB2.1 clean full-89.
