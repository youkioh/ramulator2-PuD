# GEMV Mat-Level Parallelism Characterization Placement Plan

Status: Complete. WU1-WU2 and the phase-exit checks passed. The user accepted
[Alternative A](../decisions/pud-gemv-output-placement.md) on 2026-09-14 and
authorized WU1-WU2 as a **mat-level parallelism characterization placement**
with an explicit no-SALP boundary. The controlled experiments keep both outputs
in the same bank and same subarray on disjoint legal mat ranges, intentionally
excluding bank-level placement parallelism and SALP. Subarrays remain static
capacity fallback only. This completed milestone does not establish the final
GEMV baseline placement policy. No commit made.

## Recovery and authority

Read `AGENTS.md`, the
[canonical CUDA specification](../references/gpu-pud-gemv-programming-model.cu)
and [programming-model reference](../references/gpu-pud-gemv-programming-model.md),
[mapping/reduction reference](../references/mimdram-data-mapping-and-vector-reduction.md),
then the Accepted [macro contract](../decisions/pud-gemv-macro-contract.md),
[placement/resolver contract](../decisions/mimdram-addressing-geometry-and-payload.md),
[forward reduction](../decisions/mimdram-reduction-placement-and-movement-lowering.md),
[operation lowering](../decisions/pud-operation-physical-lowering.md),
[execution/resources](../decisions/mimdram-movement-execution-ownership-and-device.md),
and [timing](../decisions/mimdram-movement-timing-and-resource-model.md).
The completed [trace integration](pud-gemv-trace-integration-plan.md) and
[chain execution](pud-gemv-chain-execution-plan.md) plans describe prior work.
The Accepted characterization placement decision supplies the enumeration,
capacity formulas, and no-SALP boundary; only that placement gate is closed.
The actual GEMV baseline evaluation policy will be defined separately and is
expected to exploit BLP before serialization is attributed to the
MIMDRAM-style baseline, as recorded in that decision.

## Pre-implementation source audit

- [`generator.py`](../../../tools/pud_gemv_generator/generator.py),
  `placement_profile()` / `generate()`: the C++ binding supplies topology and
  dimensions. The generator follows successors starting at logical mat 0
  through one 16-mat domain, then requires the sequence to equal 0..15.
  All eight chips exist in the profile, but only chip 0 is used. For domain d,
  `elements=min(N-d*8192,8192)` and `K=ceil(elements/512)`; MUL uses mats
  0..K-1, the forward fold ends at K-1, and LC reduction remains at that sink.
- Output placement is capacity-first. The row footprint F includes 16 input
  rows per domain, 24 macro-workspace rows, protected constants and generated
  micro-operation temporaries. With `R=floor(1024/F)`, the generator computes
  `(context_index, slot)=divmod(output,R)`, then divides context_index by 64
  subarrays and by four banks/group. Thus it fills row bands first, then
  subarrays, banks and bank groups. Channel/rank are fixed to zero. It rejects
  F>1024 or M>16*64*R. Mat capacity is absent from this calculation.
- INT8 M=2, N=12: both outputs use bank group 0, bank 0, subarray 0, mat 0.
  Output 0 owns rows 0..59: input bases 0/8, macro bases 16/24/32,
  constants 40/41, micro-operation temporary rows 42..59. Output 1 shifts
  all of those rows by 60. The rows do not alias, but compute mat resources
  intersect. INT8 M=2, N=516 instead gives K=2 for both: MUL ranges 0..1,
  GB edge 0->1, sink 1; the same resource intersection persists.
- Multiple domains currently reuse the same physical range prefix and the
  three macro workspaces, with distinct domain input rows. For N=8196,
  K values are 16 then 1; sinks are 15 then 0. F=76 for INT8. One output's
  requests stay in one chain; completion indices remain flattened physical
  Request indices for external readout before workspace reuse.
- [`pud_location.cpp`](../../../src/ramulator/dram/pud_location.cpp),
  `PlacementProfile::mimdram_ddr4_8gb_x8_v1`, `layout`, `resolve`,
  `directed_neighbors`, `segment_range`: the profile has 4 bank groups,
  4 banks/group, 64 subarrays/bank, 8 chips and 16 mats/chip. External row
  determines subarray/local row by division/remainder by 1024. Logical mat
  `16*chip+local_mat` identifies a mat within the bank/subarray context.
  All 128 mats are resolvable; GB successors are chip-local forward neighbors
  with no edge 15->16. Other chips and shifted legal ranges require no resolver
  changes. Physical-row lowering already accepts caller-selected row bindings.
- [`controller_base.cpp`](../../../src/ramulator/controller/controller_base.cpp),
  `pud_compute_resources_available`: compute conflicts on intersecting
  chip/local-mat ranges in the same bank/subarray regardless of local rows.
  Disjoint ranges in the same subarray can coexist. A different subarray of
  that bank conflicts even when CellIDs are distinct; all protected contexts,
  including pre-ACT allocation and recovery, must drain first.
  [`generic_ddr_controller.cpp`](../../../src/ramulator/controller/impl/generic_ddr_controller.cpp),
  `allocate_pud_compute`: eight engines by default, shared per channel/controller
  across banks/ranks; one engine per primitive Request, not per mat or GEMV
  output. Complete range and engine are reserved together through recovery.
  A wide K-mat MUL uses one engine. Allocation scans pending compute by age.
- Compute/movement and independent movement/movement remain bank-exclusive
  through recovery. Different banks can progress independently within shared
  issue, timing, and engine constraints. Bank groups add placement contexts;
  they do not introduce extra compute-engine pools. One command per channel
  tick means command overlap is interleaved execution intervals, not issuing
  multiple commands in the same cycle.
- [`validation.py`](../../../tools/pud_gemv_generator/validation.py),
  `execute_trace()`: preplacement currently initializes mats
  `range(domain["mat_count"])`; it must consume the selected physical mat
  origin and keep element indices domain-local. Its execution memory keys
  already include channel/rank/bank-group/bank/mat with full external rows.
  [`test_integration.py`](../../../tools/pud_gemv_generator/test_integration.py)
  also assumes `sink_mat == mat_count-1`. These are affected consumers of
  placement metadata, not arithmetic changes.

No Accepted placement authority prohibits disjoint ranges. The fixed mat-zero
and row-band-first behavior is the prototype implementation, not a resolver
restriction. The now-Accepted characterization choice fixes static allocation
order and capacity fallback for this milestone. Its authority does not select
the final evaluation baseline. It does not replace the Accepted numeric
macro contract or broaden the generic reduction/topology authority.

## Completed implementation

One phase: generated GEMV outputs use the selected legal static ranges, and
the resulting physical stream preserves functional composition and demonstrates
independent compute command overlap through the unchanged substrate for the
controlled same-bank/same-subarray characterization.

| Work unit | Work and focused checks | Status |
| --- | --- | --- |
| WU1 | Deterministic output placement and early capacity rejection; schema 3 per-domain `mat_begin`; replay initialization and sink assertions updated together. Existing lowering and reduction sequence retained. Disjoint K=1/K=2 placement, topology/capacity boundaries, temporary ownership and all three functional profiles checked. | Passed |
| WU2 | Generated M=2,N=12 and N=516 command overlap; shifted range/context Requests completed through the installed resolver; before/after placement cycles and resource timeline recorded below. Reference/user guide updated; complete diff, affected composition/frontend regressions and whitespace checked. | Passed |

Keep WU1's slot calculation independently callable within the generator so
boundary checks can select high output indices without constructing enormous
arithmetic traces. This needs no general optimizer, new allocation subsystem,
public policy modes, or controller work. No separate fresh-context audit is
required for this generator-local phase unless implementation reveals new
cross-cutting risk. Do not modify PuD arithmetic, chain semantics/dependencies,
LC/GB timing, scheduling, resolver semantics, or operation lowering.

## Focused acceptance evidence

- M=2,N=12: disjoint physical mat resources; full result equality separately
  for INT8/E4M3/E5M2; actual generated compute starts on both outputs before
  either selected primitive reaches terminal PRE. Peak inflight 2 alone is
  insufficient. Reuse the existing command recorder/Request harness; if equal
  row numbers obscure output identity, correlate recorded commands with the
  known generated first-primitive stream and its resolved mat ranges.
- M=2,N=516: K=2 with legal ranges 0..1 and 2..3 under the Accepted policy, GB edges
  0->1 and 2->3, sinks 1 and 3, in the same bank/subarray. Establish actual
  compute overlap here too. Preserve partial-mat suffix handling, primitive
  and movement counts, whole-group selectors, and all three functional graphs.
- Exercise the first output after a chip's q ranges, after all chips' ranges,
  after all banks, and after all subarrays; inspect full physical identities.
  Include K=3 leaving one mat at the end of a chip: advance rather than use an
  illegal chip-crossing range. Check first repeated range's next row band,
  last fitting band, one output beyond capacity, and F>1024 rejection.
  Use placement-only checks for large indices and a few representative
  Requests through the existing resolver/frontend, not huge timing workloads
  or a replacement geometry/resolver.
- Multiple domains: use two outputs at N=8196 to check K=16 then K=1 on each
  output's own reserved prefix, unchanged domain ordering/readout indices,
  distinct inputs, and reused macro/micro temporary ownership. Existing full
  N=8196 composition plus one focused two-output INT8 replay is sufficient;
  do not multiply expensive multi-domain timing runs across formats.
- Reuse the affected composition cases and frontend regression file. Verify
  Request/command counts and complete callbacks, explicit ranges, same-context
  operands and unchanged row/group legality. Compare cycles against the old
  capacity-first placement using the same per-output chains and configuration,
  retaining the old trace only as a temporary investigation artifact. Do not
  add a permanent old-policy mode, fixed cycle oracle, or required speedup.
  Focus timing on INT8 M=2,N=12 and M=2,N=516 in one bank/subarray. If gains
  remain small, collect command/resource timelines and identify serialization
  within the controlled characterization. Cycles still exclude GPU
  duplication, transposition, readout and final combine.

## Investigation verification (2026-09-14)

Read-only generation confirmed the placements and footprints above. Two
existing tests passed using `ramulator2-venv/bin/python -m pytest -q -s`:
`test_generated_chains_preserve_stream_and_overlap[int8-gemv]` and
`test_independent_ranges_execute_concurrently` in
[`test_pud_gemv_frontend.py`](../../../tests/unit_tests/test_pud_gemv_frontend.py).
The former reproduced capacity-first INT8 M=2,N=12 at 105373 cycles and peak
inflight 2 (one-chain comparison 106828); the latter established existing
substrate command overlap on disjoint mats. Neither validates the proposed
generator policy. The user subsequently accepted the decision and authorized
implementation with the scope recorded above.

## Implementation verification and timing evidence (2026-09-14)

All 85 tests passed (45 composition/placement, 40 frontend):

```bash
ramulator2-venv/bin/python -m pytest -q tools/pud_gemv_generator/test_integration.py tests/unit_tests/test_pud_gemv_frontend.py
```

Checks include all three formats at M=2,N=12/516, shifted multi-domain
INT8 replay at M=2,N=8196, physical temporary-row non-aliasing, chip/bank/group/
subarray/row-band boundaries, capacity rejection before lowering, and real
resolver/frontend compute/LC/GB completion at sampled boundary placements.
Subarray tests check capacity/legal completion, not parallelism. No C++ or
operation-lowerer change required a rebuild or broader substrate suite.

Measured INT8 with DDR4_8Gb_x8/DDR4_2400R, one channel/rank, default E=8,
FRFCFS, NoRefresh, Open policy and both clock ratios one, using the existing
frontend test configuration. Both outputs stay in bank group 0, bank 0,
subarray 0 in every comparison; the old placement differs only in mat ranges
and row-band offsets. Both executions use one chain per output. A complete
stream comparison verified unchanged opcodes, groups, sequence/counts,
micro-operation requirements and flattened completion indices.

| M=2 | Old intersecting-mat cycles | Disjoint-mat cycles | Reduction | Requests / command occurrences (both) |
| --- | ---: | ---: | ---: | ---: |
| N=12: mats 0 / 1 | 105373 | 56511 | 46.37% (1.865x) | 1456 / 5808 |
| N=516: ranges 0..1 / 2..3 | 822669 | 753275 | 8.44% (1.092x) | 8072 / 42568 |

Peak inflight is two for old and new placements. Actual initial compute
overlap is visible in both new traces: source ACTs at CK 1/2, destination ACTs
at 41/42, terminal PREs at 46/47, recovery ends at 62/63. Both first Requests
therefore execute before either closes. The old trace starts the second
output at CK 62, after the first output's initial recovery. Permanent tests
assert overlap and legal placement, not these clocks or a required speedup.

Within this same-bank/same-subarray characterization, the small N=516 gain is
explained by unchanged bank-exclusive movement. This is not a performance
conclusion about the separately defined GEMV baseline evaluation policy.
Summing recorded first-ACT-to-terminal-PRE-plus-16-CK-recovery intervals:

| N=516 observed resource interval | Old cycles | New cycles |
| --- | ---: | ---: |
| GB bank occupancy: 2048 requests at 75 CK | 153600 | 153600 |
| LC bank occupancy: 4064 requests at 130 CK | 528320 | 528320 |
| Exactly one compute request executing/recovering | 140748 | 1960 |
| Two compute requests executing/recovering | 0 | 69394 |
| Initial idle interval | 1 | 1 |

No movement interval overlaps another movement or compute interval. Movement
occupies 681920 cycles, 90.53% of the new runtime. The unchanged total compute
request durations are `1960 + 2*69394 = 140748`; overlap saves exactly 69394
wall-clock cycles. These observed intervals include recovery, not pre-ACT
engine reservations, and are not electrical data-visibility measurements.

At the compute-to-GB transition, the two last MUL primitives close at CK
43226/43227. GB starts only at 43243 after both recover, performs its RD at
43282, WR at 43284, PRE at 43302, and releases the bank at 43318. The next GB
starts at 43318. This agrees with
`ControllerBase::is_pud_eligible_before_prerequisite` and
`GenericDDRController::is_pud_eligible_before_prerequisite`: movement waits for
protected same-bank compute; retained movement and its recovery exclude other
same-bank work. More mats cannot remove that accepted movement conflict.
No bank striping, SALP, scheduler, timing or movement changes were made.

Raw old/new traces, layouts, command CSVs and statistics were collected under
`/tmp/gemv-placement-evidence/{before,after}-{12,516}/` for this investigation;
they are temporary artifacts, not permanent test oracles. The durable evidence
is summarized above. Cycles exclude the existing GPU/host costs and are not
full end-to-end GEMV latency. Complete phase diff and local document links
were reviewed; `git diff --check` passed. No commit made.
