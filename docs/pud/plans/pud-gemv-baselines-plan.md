# Final GEMV evaluation baselines

Authority: [Accepted GEMV contract](../decisions/pud-gemv-macro-contract.md),
[addressing/payload](../decisions/mimdram-addressing-geometry-and-payload.md),
[reduction topology](../decisions/mimdram-reduction-placement-and-movement-lowering.md),
and [programming-model specification](../references/gpu-pud-gemv-programming-model.cu).

One implementation Phase: exactly two explicit, functionally validated GEMV
schedules use the same BLP-first placement and legal existing Requests; the
characterization runtime is removed. WU boundaries are inspection/check units,
not separate executable architecture phases or commits.

| Work unit | Deliverable | Status |
| --- | --- | --- |
| WU1 | Accepted contract; BLP-first static placement, metadata/replay; K/range/context/capacity and no-SALP checks | Passed |
| WU2 | Explicit InterMatFirst; unchanged physical reduction order; all three arithmetic formats and legal Requests | Passed |
| WU3 | IntraMatFirst local reduction then residual merge; schedule-specific scalar checks and counts/timing | Passed |
| WU4 | Remove generic paths; update canonical CUDA/reference/guide; identical-placement comparison; fresh-context audit and affected regressions | Passed |

## Recovered authority and characterization audit

On 2026-09-14, inspected the mapping/movement references, Accepted macro,
placement, reduction, addressing and execution contracts, completed placement
plan, generator, replay, frontend and controller/resolver consumers. Existing
characterization suites passed: 85 tests in 46.60 seconds. Captured old streams
for M=2,N=12/516/1028 in `/tmp/gemv-baseline-before` for sequence comparison.

The current controller prohibits protected same-bank cross-subarray compute;
movement remains bank-exclusive. Accepted LC explicitly supports a common
lockstep range; validation and existing frontend range tests implement it.
No modeling gate remained. At recovery, replay interpreted LC endpoints as a
singleton; implementation now copies independently across the full LC range.
No resolver, controller, topology, arithmetic primitive or timing change needed.

## Verification

Work-unit checks use the generator composition/placement tests and frontend
tests. Placement-only checks cover bank/group striping, legal K=1/2/3/16
ranges, chip remainder, subarray and row-band fallback, last capacity and
rejection, plus maximum-domain reservation. Sample boundary Requests use the
installed resolver; retain a focused controller no-SALP recovery regression.

Compare InterMatFirst captured streams after removing only context/mat
translation. For both schedules, replay physical effects with poisoned unused
lanes and compare INT8/E4M3/E5M2 to their own scalar graphs, including partial
mats, multiple mats and multiple domains. Check range scope stays within one
output, LC local copies and GB directed neighbors. Exercise generated Requests
through the simulator and record counts, cycles, placement and peak inflight
for all formats at M=2,N=12/516. Include a full multi-mat IntraMatFirst trace
to exercise ranged LC. Timing uses the existing test configuration and is not
an exact-clock oracle.

Phase exit: complete diff review, affected regressions, `git diff --check`,
and one fresh-context audit of current authority/source/tests. No commit.

## Completed verification and evaluation evidence (2026-09-14)

WU1 passed 35 focused placement/context/capacity, multi-domain and no-SALP
checks. WU2's nine captured M=2,N=12/516/1028 streams, all three formats,
match final InterMatFirst exactly after context/mat translation; opcode/row/
group order, counts and flattened completion indices are preserved. The
full directly affected suite passed **149 tests**:

```bash
ramulator2-venv/bin/python -m pytest -q -s tools/pud_gemv_generator/test_integration.py tests/unit_tests/test_pud_gemv_frontend.py
```

Final review added six focused cases: both-baseline M=2,N=8196 reservation and
IntraMatFirst ranged LC replay at shifted mat/chip/subarray/row-band contexts.
All 28 selected checks passed (new/affected cases and existing no-SALP recovery
regressions); the affected suite now contains 155 tests. No shared C++ code
changed, so no substrate rebuild or broad cross-standard suite was required.
The canonical CUDA source passed a C++ syntax projection using generated
requirements and stub CUDA declarations; GPU annotations/launch syntax were
removed for that check. This is not a CUDA build: the interfaces remain
specification declarations.

A fresh-context independent audit found **no correctness findings** after
reviewing current authority, placement/capacity, ranged LC replay, workspace
parity, domain prefixes, singleton GB, old-profile removal and the canonical
CUDA schedules. Its 42 additional physical-replay cases passed: all six
profiles at N=520/528/540/768/1020/8700/9224 with poison 0x3C, each compared to
its own scalar graph. These extend partial-tail parity and final-domain
prefix coverage without adding accuracy analysis. Root's complete diff review
also found no correctness issue. Local documentation links and
`git diff --check` passed.

### Identical-placement comparison

Configuration is the existing frontend test setup: DDR4_8Gb_x8/DDR4_2400R,
MIMDRAM_DDR4_8Gb_x8_v1, one channel/rank, default eight shared compute engines,
FRFCFS, NoRefresh, Open row policy, and frontend/memory clock ratios one.
No controller, resolver, topology, timing or primitive changes were made.

For every row below, M=2 and placement is identical between schedules:

- N=12: output0 -> bank group0/bank0/subarray0/mat0;
  output1 -> bank group0/bank1/subarray0/mat0.
- N=516: output0 -> bank group0/bank0/subarray0/mats0..1;
  output1 -> bank group0/bank1/subarray0/mats0..1; both sinks are mat1.

Compute counts are physical compute primitive Requests, not ADD/MUL macro
invocations or command occurrences. LC/GB counts likewise count Requests:
ranged LC counts once while moving four bits in each selected mat. All counts
are totals for both outputs. Peak inflight is accepted but not fully completed
Requests. Actual initial compute overlap was verified with command recordings.

| N | Format | Baseline | Compute | LC-MOV | GB-MOV | Total Requests | Controller cycles | Peak inflight |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 12 | int8 | MIMDRAM-InterMatFirst | 1408 | 48 | 0 | 1456 | 53415 | 2 |
| 12 | fp8-e4m3 | MIMDRAM-InterMatFirst | 5960 | 48 | 0 | 6008 | 201241 | 2 |
| 12 | fp8-e5m2 | MIMDRAM-InterMatFirst | 4832 | 48 | 0 | 4880 | 164692 | 2 |
| 12 | int8 | MIMDRAM-IntraMatFirst | 1408 | 48 | 0 | 1456 | 53415 | 2 |
| 12 | fp8-e4m3 | MIMDRAM-IntraMatFirst | 5960 | 48 | 0 | 6008 | 201241 | 2 |
| 12 | fp8-e5m2 | MIMDRAM-IntraMatFirst | 4832 | 48 | 0 | 4880 | 164692 | 2 |
| 516 | int8 | MIMDRAM-InterMatFirst | 1960 | 4064 | 2048 | 8072 | 415373 | 2 |
| 516 | fp8-e4m3 | MIMDRAM-InterMatFirst | 21932 | 4064 | 2048 | 28044 | 1071255 | 2 |
| 516 | fp8-e5m2 | MIMDRAM-InterMatFirst | 17372 | 4064 | 2048 | 23484 | 924516 | 2 |
| 516 | int8 | MIMDRAM-IntraMatFirst | 1960 | 2032 | 16 | 4008 | 205061 | 2 |
| 516 | fp8-e4m3 | MIMDRAM-IntraMatFirst | 21932 | 2032 | 16 | 23980 | 860943 | 2 |
| 516 | fp8-e5m2 | MIMDRAM-IntraMatFirst | 17372 | 2032 | 16 | 19420 | 714204 | 2 |

At N=12, K=1 makes the two physical streams identical. At N=516, each
output uses one full local mat and a four-element tail. Local-first reduces
each GB hop from 1024 to 8 Requests and removes 1016 suffix-preservation LC
Requests per output; compute counts remain equal. Both outputs together save
4064 physical Requests and 210312 modeled cycles in this configuration.
At N=1024, generated ranged LC also completed for all three formats; moved-bit
accounting confirmed two independent local copies per ranged invocation.

Cycles are comparison evidence, not an exact timing oracle or end-to-end GEMV
latency. GPU launch/x duplication, transposition, readout/conversion, and
residual/domain combination remain outside timing, including readout before
workspace reuse. The performance comparison does not require cross-schedule
FP8 equality or evaluate model accuracy.

### Runtime closure

Only the six profiles in the Accepted contract are accepted by the CLI/API.
Negative CLI/API tests reject the three old generic names; no compatibility
aliases or selectable old placement remain. Metadata schema 4 names baseline,
format and BLP-first placement. Canonical CUDA kernels, the programming-model
reference, mapping/reduction reference and DDR4 PuD guide explicitly describe
both schedules. Characterization authority is Superseded with a successor
pointer; its completed plan and historical rationale are retained.

No blocker remains before baseline performance evaluation can begin within
the Accepted scope. WU1-WU4 and the Phase are complete. No commit made.
