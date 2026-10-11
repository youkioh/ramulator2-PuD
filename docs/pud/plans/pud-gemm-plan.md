# DDR4-packed GEMM implementation plan

Status: Initial implementation and validation complete, 2026-10-11. No commit.

## Authority and recovery

Follow [AGENTS.md](../../../AGENTS.md): relevant references first, then current
Accepted decisions, then this plan. References are the
[mapping/reduction](../references/mimdram-data-mapping-and-vector-reduction.md),
[geometry](../references/mimdram-geometry.md),
[packing investigation, section 11](../references/pud-phase4-g5-g7-investigation.md#11-utilization-aware-output-packing-and-request-fusion),
[DDR4 timing](../references/ddr4-pud-timing-reference.md), and
[programming model](../references/gpu-pud-gemv-programming-model.md).
Source takes precedence over older implementation-status statements.

Current authority: the [GEMM macro contract](../decisions/pud-gemv-macro-contract.md)
and [G7 GEMM contract](../decisions/pud-multistandard-substrate.md#accepted-gemm-placement-and-fusion--2026-10-11).
Preserve [physical lowering](../decisions/pud-operation-physical-lowering.md),
[addressing](../decisions/mimdram-addressing-geometry-and-payload.md),
[execution/completion](../decisions/mimdram-movement-execution-ownership-and-device.md)
and [timing/resources](../decisions/mimdram-movement-timing-and-resource-model.md).

The accepted 16-CHAIN replacement supersedes 32 CHAINs and D1's predecessor
extension. The former frontend-extension Phase is removed: existing per-chain
full-completion ordering already enforces the required bank-local band order.
No compatibility path, new scheduling mechanism or parser change is needed.

## Phase 1 — complete mapped GEMM using existing execution

Invariant: every accepted logical output is computed once with its chip's query,
legal cross-chip compute/LC fusion, and bank-local band ordering in 16 CHAINs.
Per-output completion observations inherit their owning band's completion
timestamp; they are not independent output latency measurements or GEMV
MUL/reduction instrumentation. Existing GEMV behavior and artifacts are preserved.

Execute these work units sequentially. They are not separate Phases or commits.

**WU1 — mapping and composition:** implement a separate GEMM API/CLI and layout
schema v1 for the accepted shape. Reuse the operation generator, physical lowering
and GEMV composition. Derive row requirements; validate full mapping coverage,
distinct query identities, shared K replication, row capacity and ownership.
Compose both band streams in each Bank CHAIN. Preserve separate row storage and
per-output residual locations. Do not generalize the public workload silently.

**WU2 — replay and execution integration:** validate trace/layout association,
initialize chip-specific Q and shared K, and replay using the existing physical
arithmetic mechanism. Compare with an independent indexed reduction oracle using
the accepted scalar operations, and compare chip-local versus cross-chip fused
execution on identical placement/data. Preserve packed-slice isolation and
workspace lifetimes. Use the current DDR4-packed/multistandard `PUD_TRACE 2`
grammar. Configure one intermediate checkpoint per Bank at band-0 completion;
final completion belongs to band 1. Report per-output observations without
duplicating physical callbacks or treating them as independent chain samples.

**WU3 — integration closure:** verify actual frontend/controller behavior with
small execution cases: band 1 follows full band-0 recovery, independent banks
overlap, retries preserve exactly-once Request completion/accounting, and
checkpoint/readout ownership remains correct. Validate all three arithmetic
formats and both existing schedules using small numerical fixtures. Use
target-size placement/coverage tests for all 16,384 outputs and exactly 16 Bank
CHAINs; an expensive full target-size timing run is not an initial exit gate.

## Verification and review

Each work unit gets focused tests and local diff review. Phase exit adds full
diff review, relevant GEMV/shared-substrate regressions and `git diff --check`.
Primary anchors: `tools/pud_gemv_generator/{test_integration,test_multistandard}.py`,
`tests/unit_tests/test_pud_{gemv_frontend,trace_multistandard,request_locations}.py`
and `tests/device_timings/test_pud_compute_ranges.py`. Preserve frozen legacy
DDR4 evidence and DDR4-packed/GDDR7/HBM3 behavior without regenerating baselines.
Use poisoned unused test positions and check both bands' retained residuals.

No shared frontend change is planned. If a genuine new decision would require
shared scheduling/completion changes, stop before that consumer, present the
alternatives, and obtain approval; such changes also warrant a fresh-context
audit. Ordinary tests and final diff self-review are required regardless.
Phases, work units, Decision Gates, audits and commit boundaries are distinct.

Actual full-size latency remains unmeasured. Approximately 1 ms is an unverified
expectation, never a pass/fail threshold. Future measurement uses preplaced and
replicated inputs, NoRefresh, terminal recovery included, with loading/readout/
host folding excluded. Report logical arithmetic, physical Requests, command
occurrences, modeled time and simulator wall time separately. No lower-bound
calculation or reproduction task is required.

## Completion evidence — 2026-10-11

WU1-WU3 are complete. The separate generator/API/CLI and schema reader live in
`tools/pud_gemm_generator/`; `experiments/pud_gemm.py` owns band timestamps and
reporting. The shared Python physical replay accepts per-output vectors and
can verify retained residuals. GEMV keeps its original validation and vector
contract. No C++ frontend, parser, scheduling, controller or timing code changed.
The [user guide](../ddr4-pud-user-guide.md#ddr4-packed-shared-k-gemm) documents use.

- 38 tests passed across `tools/pud_gemm_generator/test_gemm.py` and
  `tests/unit_tests/test_pud_gemm_frontend.py`: all six format/schedule mappings,
  exact full-size coverage, distinct queries, poisoned slices, retained bands,
  actual cross-chip versus chip-local replay, artifact rejection, recovery,
  independent bank progress and exact physical accounting.
  Final focused regressions confirm identical InterMatFirst/IntraMatFirst
  physical Request bodies at N=128 for all three formats. Unmodified generated
  streams for one complete Bank (both bands, 1,024 outputs, 4,096 residuals)
  match between cross-chip fused and chip-local replay for every format;
  scalar outputs also match the independent oracle.
- 506 existing tests passed across GEMV `test_integration.py` and
  `test_multistandard.py`, frontend `test_pud_gemv_frontend.py` and
  `test_pud_trace_multistandard.py`, and `test_pud_compute_ranges.py`.
  Frozen DDR4 generation and existing GEMV phase instrumentation are preserved.
- Public write/read API, requirements artifact generation and both CLI entry
  points passed smoke checks. Full diff self-review, Python syntax, local links
  and whitespace checks passed, including new files; `git diff --check` passed.

Small physical execution cases and target-size mapping tests establish this
milestone. No full target-size GEMM timing run was performed, and the 1 ms
expectation remains unverified. No separate fresh-context audit was needed:
shared frontend execution was reused unchanged.
