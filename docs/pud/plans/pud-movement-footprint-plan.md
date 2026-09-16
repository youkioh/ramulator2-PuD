# PuD movement physical-mat resource milestone

Status: Complete. User accepted the footprint policy and WU1–WU4 on
2026-09-16. Implementation, verification and the fresh-context audit are
complete. No commit made.

## Authority and invariant

Recover the [movement reference](../references/mimdram-inter-column-data-movement.md),
[mapping/reduction reference](../references/mimdram-data-mapping-and-vector-reduction.md),
[execution authority](../decisions/mimdram-movement-execution-ownership-and-device.md),
[timing authority](../decisions/mimdram-movement-timing-and-resource-model.md),
[locations](../decisions/mimdram-addressing-geometry-and-payload.md), and
[unified substrate](../decisions/ddr4-pud-unified-substrate.md).

One implementation Phase: independent compute/LC/GB invocations protect only
their physical mat footprints through recovery; disjoint work in the same
legal Bank/subarray may execute concurrently. Shared issue/timing, compute
capacity, ordinary traffic, maintenance, topology, dependencies and numeric
latencies retain their existing contracts. Same-Bank cross-subarray execution
remains excluded. The six pair classes require overlap and intersection tests.

## Pre-implementation audit

- GenericDDR derives movement ownership from the Request cursor (`owns_bank`),
  tests active/pending owners and delayed completions by flat Bank, and gives
  acquired movement continuation precedence even after failed promotion.
- ControllerBase blocks movement against every protected compute Bank;
  compute allocation also rejects active movement and non-Closed conventional
  Bank state. Compute already retains one context per invocation through nRP.
- Raw Device movement actions use Bank `MovementActive/MovementDataValid`.
  LC source PRE retains valid metadata; terminal PRE closes the Bank. Request
  cursor/history already derives source/destination/valid phases and retains
  immutable resolved endpoints.
- ACT_MOV→PRE/WR and PRE→ACT_MOV use Bank history; occurrence-specific LC/GB
  edges use Request history. Range compute dispatch already preserves shared
  Channel timing and incoming conventional recovery without publishing local
  PRE into Bank/Rank history.
- FRFCFS variants resolve prerequisites from command/address only. Located
  movement needs request-associated prerequisite/issue dispatch to avoid raw
  Bank actions. Ordinary dispatch remains unchanged.
- Existing conflict tests explicitly serialize disjoint movement and expose
  `owns_bank`; these assumptions must be updated. Raw command tests remain
  low-level action/timing fixtures, not canonical located execution.

The existing invocation context/protected-record mechanism can be extended to
movement at first ACT, with no compute engine. Request remains the only cursor
and history; resolved endpoints remain placement authority. This is concrete
factoring of the accepted local lifecycle, not a new lifecycle policy. No
additional Decision Gate was identified.

## Work units and verification

1. WU1: canonical derived resource footprint and PuD intersection eligibility.
2. WU2: request-associated movement state/timing/close, atomic first-ACT
   protection, and delayed local recovery. WU1/WU2 complete one invariant;
   an intermediate build is not a Phase exit.
3. WU3: all six pair classes, intersecting serialization and actual disjoint
   execution overlap; close isolation, retry atomicity, exact accounting,
   no SALP and unchanged isolated LC/GB anchors. Run affected regressions.
4. WU4: unchanged INT8 M=17,N=516 under both
   [GEMV baselines](../decisions/pud-gemv-macro-contract.md). Output 16 wraps
   16 BLP slots to Bank 0 mats 2..3; output 0 uses mats 0..1, subarray 0.
   Record before/after cycles, peak inflight, counts and command overlap.

Finish with directly affected build/codegen, complete diff self-review,
fresh-context independent audit, local documentation links and
`git diff --check`. Historical completed plans remain unchanged.

## Results

WU1–WU4 complete. `RequestLocations::mat_footprint()` derives the normalized
union of resolver-produced `MatSegment{chip, first_local_mat, last_local_mat}`
values for all operands. The retained origin supplies Channel/Rank/BankGroup/
Bank/subarray identity. Rows/groups do not narrow ownership. The shared
`conflicts()` method checks physical intersection plus the separate no-SALP
boundary. There is no second placement map or Bank-wide movement fallback.

`ProtectedPuD` owns a `PuDExecutionContext` from first movement ACT through
terminal recovery, with engine=-1. Compute keeps its allocation-time engine
policy. Request cursor/history remains authoritative; `sequence_active`
describes only sequence progress, while protection persists through recovery.
Device dispatch localizes movement phase and history, preserves source-valid
state through LC source PRE, and leaves conventional Bank state unchanged.
Unlocated movement cannot enter the controller execution path; old execution
fixtures now construct resolved operands. Raw Device command/action and legacy
metadata-validation fixtures remain isolated low-level tests.

All six classes passed intersection serialization and actual disjoint
execution overlap under both FRFCFS variants: compute/compute, compute/LC,
compute/GB, LC/LC, LC/GB, GB/GB (including reverse mixed order). The focused
suite also covers LC cross-chip ranges, close isolation, no-SALP for all
pairings, engine-free movement, and retry with absent context/no partial
ownership. Affected lifecycle, maintenance, accounting and reentrant-completion
regressions passed. Isolated LC remains
`[0,16,39,55,94,114] + 16 = 130 CK`; GB remains
`[0,1,39,41,59] + 16 = 75 CK`.

### GEMV evidence

INT8 M=17,N=516, one channel/rank, DDR4_2400R, E=8, FRFCFS,
NoRefresh, Open, clock ratios 1. Outputs 0..15 use mats 0..1 in the 16
BankGroup/Bank slots. Output 16 reuses BankGroup 0/Bank 0 at mats 2..3.
All use chip 0, subarray 0 and first input row 0. Both baseline schedules and
before/after layout JSON/physical trace bytes are identical.

| Baseline | Before cycles | After cycles | Peak inflight before/after | Compute Requests | LC Requests | GB Requests |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| MIMDRAM-InterMatFirst | 822368 | 510405 | 17 / 17 | 16660 | 34544 | 17408 |
| MIMDRAM-IntraMatFirst | 389528 | 282694 | 17 / 17 | 16660 | 17272 | 136 |

Counts are unchanged and submitted/completed accounting matches exactly.
Production command traces establish overlap beyond peak inflight:
InterMatFirst Bank 0 issues two GB endpoint pairs at CK 91649/91650 and
91652/91653 before either terminal PRE. Its LC source RDs at 191474 and
191513 precede the first corresponding WR at 191554. IntraMatFirst Bank 0
issues LC source RDs at 91667/91673 before either WR. Counting RD_MOV minus
WR_MOV in each Bank/type proves simultaneous retained source-valid invocations;
the maximum LC count rises from one to two in both baselines. Both also show
compute overlapping LC and GB. IntraMatFirst's short GB folds do not happen
to overlap each other in this workload; deterministic pair tests establish
that permission separately. One command per cycle remains enforced.

These are modeled timing observations, not correctness criteria or full GEMV
latency. Shared C/A/arbitration, applicable timing, the unchanged compute-engine
pool, producer dependencies, ordinary/maintenance scopes, and the no-SALP
boundary can still limit disjoint progress. No numeric command interval,
placement, arithmetic, reduction schedule or GB topology changed.

### Closure

Direct build/codegen passed. The affected controller/Device/location run
passed 1015 tests before final audit corrections; final shared-path regression
results are recorded below. Complete diff self-review, local documentation
links and `git diff --check` passed. The read-only fresh-context audit found no
production correctness defect; its ownership-wording and retry-observability
findings were corrected and rechecked. Temporary raw evidence remains at
`/tmp/pud-footprint-{before,after}-{inter,intra}*`.

Final validation: **1488 passed** in 709.63 s across `tests/controller_scheduling`,
`tests/device_timings`, `tests/smoke`, and the canonical location, Request
locations and GEMV frontend unit suites.
