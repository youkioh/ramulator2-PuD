# MIMDRAM-based PuD substrate v2 implementation plan

Status: Complete — Phases 1 and 2 (W1-W8) and W9 fresh-context final integration closure complete.

This file is a historical implementation record. W1-W9 are complete, and
`v2` is development-era terminology for the work that produced the canonical
unified DDR4 PuD substrate. Current execution semantics are governed by
[`ddr4-pud-unified-substrate.md`](../decisions/ddr4-pud-unified-substrate.md);
the work-unit chronology, superseded W6 transport work, and verification
evidence below remain implementation provenance.

## Implementation progress (2026-09-09)

- **W1: Completed.** Geometry/profile resolver and canonical location authority
  implemented, including profile-owned GB topology and mat-range segmentation;
  focused and legacy verification completed, subject to the broader-suite note
  below.
- **W2: Completed.** Paired request/location retention, routing and validation
  integrated; ordinary/PuD shared-location consistency established. Incomplete
  v2 execution remains disabled.
- **Phase 1: Completed.** The common placement and submission contract exit
  invariant is satisfied.
- **W3: Completed.** Explicit range Device contexts retain W2 location identity,
  phase, activated operands and local recovery; the Request retains the sole
  cursor and occurrence timing history. V2 dispatch validates exact association
  before mutation and applies inherited PRADA edges locally while preserving
  conventional/shared timing. No allocation, transport, completion ownership
  or public v2 execution is enabled.
- **W4: Completed.** Controller-owned protected records retain explicit engine
  reservations and W3 range contexts through recovery, independently of command
  buffers. Request copies carry weak invocation associations; the shared delayed
  completion path releases protection before exact-once accounting/callback.
  Fixture reservations exercise this internal lifecycle; public v2 execution,
  admission policy, mixed-traffic exclusion and transport remain disabled/deferred.
- **W5: Completed.** Protected compute records guard ordinary, movement and
  maintenance scopes before prerequisites and final issue, including pre-ACT
  and recovery. Compute-start eligibility drains ordinary/movement activity and
  conventional recovery; maintenance validates its whole scope before mutation.
  Retained movement history exposes endpoint activation/source validity without
  payloads or another cursor. Movement recovery and continuation precedence also
  cover failed active-buffer promotion. Internal fixtures preserve disjoint
  compute progress; transport, allocation/arbitration and public v2 execution
  remain W6+ work.
- **W6: Completed — baseline aligned.** The
  [Accepted transport abstraction](../decisions/mimdram-mat-target-transport-abstraction.md)
  is implemented: each ACT_PUD* consumes its current resolved occurrence
  association at issue. Target queues, descriptors, setup/PRE
  pairing and successor transport are removed. W3-W5 fixtures share the single
  baseline compute timing/issue path. `PuDComputeContext` remains minimal;
  actual ordinary/movement and compute command-cycle occupancy is retained.
- **W7: Completed.** GenericDDR allocates configurable `pud_compute_engines`
  (positive E, default 8) from the existing protected records, shared across
  its Banks/Ranks. A stable oldest-first view of the PuD buffer skips blocked
  requests and reserves an engine plus the complete canonical range atomically.
  Disjoint same-subarray ranges overlap; intersecting ranges and same-Bank
  different subarrays conflict through recovery. Allocation does not test first
  ACT command readiness. No allocator ownership table or context field was added.
  Pending and allocated compute Requests remain in the existing PuD buffer,
  without active-buffer promotion or another schedulable container, as selected
  by the user. E is the modeled compute-engine capacity; `pud_buffer_size`
  independently bounds resident-request admission. Configuring `pud_buffer_size`
  below E can limit attainable concurrent allocations without redefining E.
  The defaults (`pud_buffer_size=32`, E=8) do not impose that limitation.
  Completion/refresh/hooks precede allocation; ready allocated compute competes
  with active work before priority and ordinary/movement pending arbitration.
  The local candidate path leaves both generic schedulers unchanged. W4 releases
  engine/range before completion accounting/callback; public v2 ingress stays closed.
- **W8: Completed.** Explicit GenericDDR profile selection installs the W1/W2
  shared resolver and validates setup compatibility. Normal GenericDRAM/controller
  ingress accepts paired compute and movement Requests; compute enters the
  existing PuD buffer and W7 allocation/protection/arbitration path. Priority and
  unallocated direct compute issue remain closed. Both existing benchmarks now
  have explicit v2 scenarios and profile-backed export configurations, preserving
  legacy invocations. Results retain immutable RequestLocations and use existing
  traces/callbacks. External core counts bound all benchmark source IDs; the
  shared W5-W7 fixture configures twelve cores for W6's sources 0..11 and W7's
  ninth request, with explicit source bounds checks. Live architecture comments
  describe W1-W8 and the T-A baseline.
- **Phase 2: Completed.** Public v2 substrate integration and the W8 exit checks
  are complete.
- **W9: Completed.** Fresh-context audit of `main` (`d75944a`) through W8
  (`e1f51c2`) plus the W9 closure delta covered source, tests/test seams,
  generated wrappers, comments and documentation against A/B/C-E/C-T/T-A.
  The public path retains one resolver/location authority and one schedulable
  Request progression, allocates engine plus complete range before ACT, and
  releases recovery protection before exact-once accounting/callback. No new
  modeling choice or excluded functionality was introduced.

W9 found one cleanup defect: the Device conflict registry retained expired weak
context references after recovery until a later allocation. Recovery release now
prunes them before callbacks, including final drain. The extended W4 drain and
callback assertions failed all 35 tests before the fix (exit 1), then passed all
35 after it (exit 0). Engine/range lifetime, command timing and scheduling are
unchanged. Stale implementation-progress statements in C-E/C-T/T-A now point here.

Executed behavior-to-test mapping (controller filenames are in
`tests/controller_scheduling/GenericDDRController/`):

| Unit | Executed evidence |
| --- | --- |
| W1 | `tests/unit_tests/test_pud_location.py`: capacity/bijection, bounds, topology, segmentation, replacement profile and mapper agreement. |
| W2 | `tests/unit_tests/test_pud_request_locations.py`: paired validation, copy/retry lifetime, common ordinary/PuD footprints, ingress rejection and forwarding/coalescing. |
| W3 | `tests/device_timings/test_pud_compute_ranges.py`: exact PRADA boundaries, independent range phases, rejected-issue atomicity and local/shared timing inventory. |
| W4 | `test_pud_protected_lifecycle.py`: protection through recovery, registry drain, exact-once release/accounting, reordered and simultaneous completions, reentrant callbacks. |
| W5 | `test_pud_conflicts.py`: complete maintenance scopes, ordinary/movement exclusion, retained movement validity, recovery and promotion backpressure. |
| W6 | `test_pud_resolved_targets.py`: exact occurrence association, T-A consumption, pure probes, no transport queues/setup, actual command-cycle occupancy. |
| W7 | `test_pud_allocation.py`: E=1/2/8, first fit, same-subarray MIMD/no SALP, complete-range atomicity, pre-ACT ownership, issue-ready arbitration and engine reuse. |
| W8 | `test_pud_public.py`: configured GenericDRAM path, all primitive anchors, contention, dependency joins, exact accounting, compatibility and 6000-CK mixed-refresh drain. |

W9 final validation: source codegen and a clean build of `ramulator`,
`_ramulator`, `_ramulator_test`, `ddr4_pud_microbenchmark` and
`mimdram_movement_microbenchmark` passed; all five targets were rebuilt after
the cleanup fix. The final full matrix passed 370 W1/W2 location tests,
255 Device tests, 785 controller tests (including HBM/GDDR/LPDDR coverage),
13 smoke tests and the DDR4 fast latency/throughput test (10 non-DDR4 cases
deselected). Every suite exited 0. Both documented legacy benchmark export/run
pairs and both public v2 benchmarks at E=1/2/8 passed, all exits 0. No native
heap failure appeared; this does not establish that every historical allocator
failure is fixed. Generated DRAM definitions and generic schedulers remain
unchanged. Full-boundary review and W9 `git diff --check` passed; an unrestricted
`git diff main --check` still reports only the 55 previously documented trailing
whitespace lines in untouched historical `git_diff.log`.

The movement-capable `supports_pud_v2()` baseline and single named public profile
remain intentional future extension points, with no current correctness or
authority violation. T-A omitted transport costs, conservative movement, absent
refresh-deadline guarantees and the separate functional-simulator boundary remain
unchanged. W1-W9 are closed; no blocker remains.

W8 verification: final public/paired-boundary run passed 309 tests (66 W8 and
243 W2, exit 0). Public cases cover all five 61/66/76/99/104 CK anchors,
multi-destination 40+5D+16, widths including chip crossings/full range, E=1/2/8,
same-operation/heterogeneous progress, first fit and ninth-engine waiting,
pre-ACT ownership, actual C/A contention, movement exclusion through recovery,
LC/GB 130/75, callback dependency joins, enqueue backpressure and exact-once
recovery accounting. Both schedulers drain the 6000-CK AllBank mixed stream.
Malformed direct movement issue probes reject before prerequisite indexing.
The controller regression run passed 783 tests (exit 0); the final focused
run additionally covers two subsequently added public contention cases.
Device/location/smoke regressions passed 395 tests (exit 0).
After the final source-ID fixture correction, all 237 directly affected W5-W7
tests passed again (exit 0).

Both documented legacy export/run commands and both v2 benchmarks at E=1/2/8
passed. Codegen and builds of `ramulator`, `_ramulator`, `_ramulator_test`,
`ddr4_pud_microbenchmark` and `mimdram_movement_microbenchmark` passed.
Generated DRAM definitions and both generic scheduler implementations are
unchanged. Phase 2 production diff and the complete W8 diff were reviewed for
ingress bypass, legacy compute fallback, duplicate authoritative state,
transport resurrection and excluded workload scope; `git diff --check` passed.
Reproducible usage and T-A fidelity limits are in the existing
[user guide](../ddr4-pud-user-guide.md#canonical-benchmark-commands).
No W8 blocker remains; W9 final closure is recorded above.

W7 verification: 63 focused tests passed, including both schedulers, E=1/2/8,
pre-ACT and recovery capacity, pool scope, homogeneous/heterogeneous interleaving,
first fit with distinct arrivals and equal-age queue ties, complete-range atomicity,
profile replacement, local gaps, maintenance generation/FIFO/drain, conventional
preparation/recovery, active-buffer backpressure, callback reuse and late issue
revalidation. All 308 affected W3-W6 tests passed, including W3's unchanged
61/66/76/99/104 CK anchors and W4's simultaneous-recovery/reentrant completion
fixtures. Device, W1/W2 public-boundary/location and smoke regressions passed
(638 tests, exit 0). Codegen and `ramulator`, `_ramulator`, `_ramulator_test`
builds passed; generated DRAM definitions are unchanged. Only the generated
GenericDDR wrapper gains the engine-count parameter.

Controller regression limitation: an earlier complete run passed 718 tests
(exit 0) with `getpass` imported before pytest. Later normal and pre-import
runs aborted during tests (exit 134); pre-importing is not a reliable fix.
The final per-file run passed 691 tests in 26 files (each exit 0), while the
28-test movement-local-timing file aborted, also on retry. An in-process
diagnostic override of that file's default fixture `num_cores` to 8 passed all
28 tests (exit 0), without changing repository code/tests. Source inspection
shows legacy tests supplying source IDs up to 4 to a default one-core fixture,
while per-core statistics index by source ID without bounds checks. This is
pre-existing source evidence, not a diagnosis of every recorded heap failure.
A freshly built clean pre-W7 HEAD `44a830a` passed all 656 controller assertions
then aborted at shutdown with `munmap_chunk(): invalid pointer` (exit 134); its
isolated movement-local-timing run passed 28 tests. These observations preserve
the known native-instability limitation and do not establish an identical root
cause or attribute it to W7. No allocator/legacy-fixture fix was attempted in
that initial verification.

Narrow W7 closure investigation: a temporary statistics-entry bounds guard,
outside the repository, intercepted the same four invalid Read accesses on W7
and clean pre-W7 `44a830a`: `(CK, source ID, command)` = `(2, 2, ACT)`,
`(33, 2, RD)`, `(18, 1, ACT)`, `(16, 2, ACT)`, each with one per-core entry.
Both guarded runs reported the same four failing cases and 24 passing cases.
The existing ordinary selection/final-validation path calls `update_request_stats`
before issue; these requests have no resolved PuD locations and do not enter
W7 compute allocation/arbitration. Thus the invalid fixture already executes
out-of-bounds statistics accesses before W7; it is not newly reachable through
W7. This concrete memory-corrupting defect is distinct from claiming a common
root cause for every earlier native abort. With user approval, only the two
fixture core counts were corrected: 3 for `make_movement_dut()` and 5 for the
ClosedCAP multi-source test. The corrected file passed all 28 tests normally
and all 28 with the bounds guard enabled (both exit 0). Executable production
code and Accepted semantics were unchanged; no broad suite or W7 test rerun
was needed for this fixture/comment-only closure. Live W1-W7 architecture
comments and the independent E/resident-buffer capacity wording were updated;
closure diff and changed-file whitespace checks passed. W7 remains complete;
W8 remains unstarted. This resolves the identified movement-fixture defect,
not every historical allocator failure.

Full W7 diff review covered public ingress, transport resurrection, canonical
geometry, sole Request/context authority, recovery release, first-fit priority
and probe purity. Changed-file whitespace checks pass. W7 adds no W8 execution
entry point or microbenchmark and no physical mat-target transport costs.

W6 baseline verification: 48 resolved-target tests and 260 W3-W5 tests passed
(exit 0), covering exact row/range/occurrence association, copies/retries,
multi-destination RowCopy, NOT_COPY across N, replacement profiles, rejected
issue/probe purity, cold/late starts, next-cycle ordinary/movement progress,
and unchanged PRADA and LC/GB anchors. The W1-W5 audit preserved canonical
locations, pre-ACT protection, recovery and exclusion; removed the obsolete
local/transport Device split, W3/W5 fixture bus mirrors and live architecture paths;
and retained ordinary PRE, request queues and GB topology helpers. The W5
maintenance fixture now starts compute after the ordinary ACT's occupied cycle.

Full Device plus W1/W2 tests passed (625, exit 0), as did all controller tests
on rerun (656, exit 0) and smoke tests (13, exit 0). Codegen and `ramulator`,
`_ramulator`, `_ramulator_test` builds passed with unchanged generated
definitions. Full source/test diff review found no live detailed target
transport dependencies; no W7 behavior was added.

Verification limits: the initial controller run passed 656 assertions then
aborted at shutdown with `munmap_chunk(): invalid pointer` (exit 134).
A freshly built clean pre-change HEAD `0ce6922` also aborted with allocator
corruption during tests, then passed 659 tests on repeat (exit 0). This
reproduces pre-existing allocator instability, not an identical root-cause
diagnosis or a clean initial run. `git diff --check` passes for the W6
source/tests/documentation, including the new test file; the unrestricted
check reports only pre-existing whitespace in the untouched `git_diff.log`.
Baseline results omit target-delivery latency, queue stalls and target-specific
C/A contention; those costs are not physically zero.

Historical W6 verification (Alternative A, not validation of the new baseline):
51 focused transport tests and 255 W3-W5 tests passed. Full
Device and controller regression runs passed (250 and 656 tests respectively);
the final focused run also includes three subsequently added ordinary-C/A and
rank-PRE cases. Coverage includes Q=8/credit release independent of engines,
multi-chip capacity/head rejection without mutation, reserved successors, FIFO
drain with maintenance arrival, cold/late setup, distinct PRE close/target
contexts, NOT_COPY across N, replacement-profile targeting, exact successor
counts and unchanged 61/66/76/99/104 CK local recovery-inclusive anchors.
LC/GB retained timing and shared C/A contention passed. Build/codegen passed for
`ramulator`, `_ramulator` and `_ramulator_test`; generated definitions were
unchanged. Full W6 diff review and `git diff --check` passed. Historical source
architecture comments included W6 queues. Production allocation, oldest-first
admission, scheduler integration and public v2 execution remain W7+ work.

W5 verification: 126 focused conflict/drain tests and the 31 W4 lifecycle plus
96 W3 range/timing tests passed together (253 tests, exit 0). The complete
controller suite passed (604 tests, exit 0), including movement ownership,
timing, refresh/row-policy, statistics/plugin compatibility, ordinary forwarding/
coalescing and cross-standard final-issue regressions. The complete Device suite
and W1/W2 location/retention tests passed (622 tests, exit 0). Tests cover both
schedulers, full-scope rejection without partial state/history/deadline mutation,
generated and queued refresh, last-context recovery, existing nRFC, FIFO heads,
late eligibility/command changes, conventional PRE/AP recovery, and unchanged
LC/GB 130/75 CK anchors. Paired movement endpoint retention uses the W2 component
seam; scheduled movement remains on the legacy path. Codegen and the `ramulator`,
`_ramulator` and `_ramulator_test` builds passed with unchanged generated
definitions. Full W5 diff review and `git diff --check` passed. The known
intermittent shutdown abort was not reproduced in these runs; no allocator
diagnosis or fix was attempted.

W4 verification: 31 focused lifecycle tests, 96 W3 range/timing tests and 370
W1/W2 location/retention tests passed together (497 tests, exit 0). The focused
checks cover terminal-PRE/recovery boundaries, pre-ACT protection, intersecting
reuse, disjoint progress, buffer backpressure/copies/retries, stale associations,
release-before-callback, exact-once accounting, simultaneous recoveries and
mixed departure ordering with reentrant successor/forwarded-read submission.
The simultaneous-recovery fixture supplies equal terminal timestamps solely
to test completion handling; it does not model multi-command C/A issue.
Directly affected legacy lifecycle/statistics/occurrence/ingress regressions
passed (139 tests, exit 0), as did legacy PuD/movement Device tests (119, exit 0).
Codegen and the `ramulator`, `_ramulator` and `_ramulator_test` builds passed;
generated legacy definitions were unchanged. Full W4 diff review and
`git diff --check` passed. W5+ policy/transport/public integration is unimplemented.

W4 broader-suite limitation: both full controller runs passed all 478 assertions
then aborted at shutdown with `munmap_chunk(): invalid pointer` (exit 134).
A freshly built, clean W3 HEAD `99f7879` reproduced the same failure form after
447 passing assertions (exit 134). The unchanged 447-test selection also passed
on the W4 build with exit 0. These observations reproduce the existing
intermittent limitation; they do not establish an identical allocator root cause
or make the aborting runs clean passes. Allocator diagnosis remains deferred.

W3 verification: 96 focused range tests passed, including independent same-operation
and heterogeneous progress, exact occurrence association/rejection, ready-1/ready
boundaries, width-independent primitive/recovery anchors, and the ACT upper-envelope
check. The full Device suite passed (252 tests, including W3); W1/W2 and directly
affected occurrence, timing, ingress/validation and lifecycle regressions passed
(598 tests). All test processes exited 0. Codegen and the `ramulator`, `_ramulator`
and `_ramulator_test` build passed; generated legacy definitions were unchanged.
Complete W3 diff review and `git diff --check` passed. At W3 exit, protected
recovery/completion and later integration remained W4+ work.

Phase 1 verification: 243 W2 location/request tests, 127 W1 location tests,
and 184 directly affected ingress/validation/occurrence/classification/lifecycle
regressions passed together (554 tests, exit 0). Mapper, DDR4/PuD/movement
Device and smoke regressions passed (156 tests, exit 0). Codegen and the
`ramulator`, `_ramulator`, and `_ramulator_test` build passed (exit 0).
Full W1+W2 diff review, local documentation-link checks and `git diff --check`
completed successfully; no Gate authority or W3+ implementation changed.

Verification limitation: the broader controller suite passed all 447 assertions
but aborted during allocator shutdown with `munmap_chunk(): invalid pointer`
(exit 134), so it is **not a clean pass**. Clean W1 checkpoint `b7aa67e` also
reproduced intermittent native exit-134 aborts, during tests in this comparison,
alongside clean 447-test runs (exit 0). An identical root cause is not established
and is not attributed to W2; allocator diagnosis remains deferred.

## Baseline, authority, and scope

Planning snapshot: 2026-09-09. `git fetch origin main` verified local `main`,
`HEAD`, and `origin/main` at
`d75944ad2f846d3888680d11cdf0309ecd463b57` (merge of NOT_COPY support).
The inspected source has no working-tree delta from that baseline. The current
Accepted decision updates and gap analysis supplied in the working tree are
planning authority even where not yet committed. Preserve those files; do not
replace them with older documentation from the baseline commit. At implementation
handoff, verify the then-current main and inspect any intervening source delta
before applying this plan. Do not merge the separate functional-simulator branch.

Read [AGENTS.md](../../../AGENTS.md), the relevant curated references below,
the canonical authorities and transport abstraction below, this plan, and the
source/tests for the selected work unit. Historical completed plans supply
conventions, not v2 semantics.

| Key | Current authority and use |
| --- | --- |
| A | [Substrate and movement request boundary](../decisions/mimdram-substrate-and-movement-request-boundary.md): accepted hybrid, five primitives, same-subarray MIMD, conservative movement, substrate/macro boundary. |
| B | [Addressing, geometry, and payload](../decisions/mimdram-addressing-geometry-and-payload.md): replaceable profile, paired operands, canonical CellID, initial v1 placement, compute ranges, movement topology/payload. |
| C-E | [Execution, ownership, and Device](../decisions/mimdram-movement-execution-ownership-and-device.md): v2 range contexts, engines, allocation, lifecycle, maintenance and functional split; retained movement provisions. |
| C-T | [Timing and resource model](../decisions/mimdram-movement-timing-and-resource-model.md): v2 local/shared scopes, ACT-overhead rounding and retained movement timing graph. |
| T-A | [Mat-target transport abstraction](../decisions/mimdram-mat-target-transport-abstraction.md): current baseline resolved-target consumption; supersedes Alternative-A/Q=8 transport requirements. |

All three Gates A/B/C are **Accepted and closed**. T-A supersedes the earlier
physical target-transport requirements, including A's transport-overhead and
C-E's pre-first-ACT transport-wait references. All other C-E/C-T v2 refinements
retain precedence over retained Bank-wide behavior. B's older
forward references to A/C, and proposal-era questions in the
[gap analysis](mimdram-pud-substrate-v2-gap-analysis.md), do not reopen them.
The gap analysis's §§9.4–9.6 identify the current authority. Unresolved physical
fidelity questions are not prerequisites for implementing the accepted model.

Source evidence is in [MIMDRAM movement](../references/mimdram-inter-column-data-movement.md),
[MIMDRAM geometry](../references/mimdram-geometry.md),
[PuD primitives](../references/pud-primitives.md), and
[DDR4 PuD timing](../references/ddr4-pud-timing-reference.md).
[Existing PRADA timing authority](../decisions/pud-timing-resource-and-command-bus-rules.md)
supplies retained intervals, with C-T's range scope and the current NOT_COPY
edge. The completed [compute](ddr4-pud-primitives-implementation.md) and
[movement](mimdram-inter-column-movement-implementation-plan.md) plans establish
codegen, focused-test, and handoff conventions; their old gate numbering and
four-compute descriptions are not current requirements.

Implement the timing/state/location substrate for the accepted PRADA/MIMDRAM
hybrid. Canonical locations describe affected cells and resource identity;
they do not store or evaluate bits. The timing callback provides completion
ordering. This task does not extend the separate functional simulator.

Explicit exclusions: functional data-value simulation (DRAM, SA, HFF or working
values); INT8/FP8 ADD/MUL; GEMV/GEMM/reduction macro generation; allocator,
transposition, compiler or full ISA support; host final reduction; new movement
topology or movement concurrency; SALP/cross-subarray same-Bank MIMD; energy
and area modeling. No staged functional commit or dependency-graph scheduler.

## Migration inventory and implementation boundaries

The following are source findings at the baseline, not new modeling choices.
Abbreviated C++ paths are relative to `src/ramulator/`; fully qualified source,
Python, test and example paths are relative to the repository root. Named
GenericDDR test files live in `tests/controller_scheduling/GenericDDRController/`.

| Existing abstraction | Retain | Required v2 refinement / protected legacy behavior |
| --- | --- | --- |
| `base/request.{h,cpp}` | Explicit request classification, ordered owned operands, copyable occurrence history, callback and statistics identities. IDs remain Read/Write 0/1, five compute types 2–6, LC/GB 7/8. | Add opt-in resolved location/range retention; mutable `addr_vec` alone cannot identify an occurrence. Bare legacy operands remain valid only under their legacy contracts. |
| `memory_system/pud_request_routing.h`, `controller/pud_request_validation.*` | Shape/count/Channel validation at ingress; placement validation in controller; exact-bit movement accounting and N/A size. | Resolve before v2 routing/placement checks; profile-supplied bounds/topology replace v2 use of hard-coded 128/16. Keep legacy opaque Column bounds 0..1023 and positive HFF overrides intact. |
| `dram/dram_spec.h`, channel/controller mappers | Six-level external hierarchy, full Bank Row, subarray quotient, existing ordinary mapping. | One coordinated profile and canonical resolver; local-row and cell/group identities. No generic Chip/Mat/Subarray hierarchy levels. Ordinary consumers retain full origin information before compaction. |
| `controller/pud_sequence.*` | All five compute and two movement sequences, occurrence roles, operand indices, terminal flags, prerequisite-safe cursor and retained issue history. | Associate every v2 occurrence with its resolved context; extend localized timing beyond the existing six movement occurrence edges. Do not create timing-only command aliases. |
| `GenericDDRController` active/pending buffers | Request-count pending buffering; movement first-ACT ownership; active precedence, priority FIFO, ordinary/movement arbitration. | Compute allocation precedes first ACT and has E engines shared across controller/channel Banks/Ranks. Protected range records survive removal from command scheduling. Active-buffer membership or first-issued history no longer defines v2 compute ownership. |
| `DRAMNode::m_state`, `m_row_state` | Conventional Bank row state and legacy aggregate compute/movement phases. | One temporal context per active lockstep compute range. Preserve operand/activated-row identity, phase and local history independently; no Bank-global selected-target variable or full Device replica per mat. |
| `DRAMDevice` command + AddrVec dispatch | Hierarchical ordinary/shared timing and complete target-Bank traversal/validation. | A narrow v2 context-aware dispatch path must carry target/occurrence identity through prerequisite, timing, action and close checks. Coarse `BankTarget::Single` cannot distinguish ordinary PRE from range PRE. Legacy calls retain their behavior. |
| Python `ddr4_pud.py` / `ddr4_pud_movement.py`, generated C++ | Independently copied definitions, semantic commands, PRADA phase costs, movement graphs, ordinary timings. | V2 compute dependencies and recovery leave Bank compute history. Range PRE must not update conventional Bank PRE deadlines. Retain real shared C/A effects and ordinary/maintenance history. Generate C++ from definitions, never hand-edit generated implementations. |
| `ControllerBase::check_request_timing`, schedulers and final issue validation | Composite readiness concept, before-prerequisite filters, final recheck; default behavior for other controllers. | Current prerequisite calls lose Request identity. Provide the smallest request-aware seam or local v2 candidate path needed; inspect both FRFCFS and FRFCFSRowHit passes. Do not redesign generic scheduling. |
| `retire_request`, `serve_completed_requests`, `m_pending` | Delayed depart, departure reordering, extraction before callback, existing per-operation accounting. | Release v2 compute engine/range at recovery completion before callback. `m_active_per_bank` counts only schedulable active requests and cannot alone protect pre-ACT allocations or recovery. |
| Row policies, refresh, plugins and test harness | Ordinary forwarding/coalescing, Open/ClosedCAP behavior, priority policy, existing trace schemas. | Check full maintenance scope against all protected v2 contexts, including recovery. Test-only context/transport observation must distinguish overlapped requests without changing production trace formats. |

Use a clearly selected v2 capability/profile path; existing DDR4, DDR4_PuD and
DDR4_PuD_Movement configurations keep their current behavior. A v2 request must
not silently fall back to legacy execution. The concrete registration name,
configuration spelling, context container and C++ handle representation are
implementation details to settle at their first consumers below. Prefer local
extensions of the existing combined substrate. A separate derived definition
can isolate changed timing; an explicit opt-in path can reduce registration
duplication but needs equally strict default isolation. Inspect that trade-off
before choosing packaging; this plan does not select a new physical model.

Similarly, assess a small v2 Device-side context store with request-held stable
identity against a retained context passed explicitly to Device. Both must give
Device independent phase legality and preserve identity across copies; neither
justifies replicating DRAMNode trees or globally changing command handlers.
Follow AGENTS.md before committing to a non-trivial implementation design.
Ordinary naming/factoring is not an unresolved A/B/C modeling gate.

## Work structure and progression rules

Two implementation Phases establish separate testable invariants. Work units
are focused chat boundaries, not automatic Phase, audit, or commit boundaries.
There is no requirement to commit after each unit or to create further plans.

| Boundary | Work units | Exit invariant |
| --- | --- | --- |
| Phase 1: common placement and submission contract | W1 geometry/profile; W2 paired requests and shared location consumers | One tested location authority supplies ordinary and PuD footprints; invalid v2 placements cannot reach legacy execution. V2 execution remains unavailable. |
| Phase 2: coherent range execution | W3 local state/timing; W4 recovery lifecycle; W5 movement/ordinary/maintenance exclusion; W6 resolved-target consumption; W7 allocation/arbitration; W8 public integration and microbenchmarks | All five v2 primitives support safe same-subarray disjoint-range overlap with explicit resolved targets, recovery and mixed-traffic rules; movement retains its accepted behavior. |
| Final integration closure | W9 validation and fresh-context audit | Entire implementation satisfies authority, integration tests and legacy regressions, with limitations and process failures reported accurately. |

Major dependency chain:

```text
W1 -> W2 -> W3 -> W4 -> W5 -> W6 -> W7 -> W8 -> W9
      placement   local state/lifecycle   targets     allocation   closure
```

W6 consumes W2/W3 resolved occurrences and preserves W4/W5 protection and
eligibility. W7 consumes those completed contracts for allocation/arbitration,
with implementation and verification recorded above. W8 is integration and
reproducibility, not deferred implementation of fundamental conflict rules.

During W3–W7, use focused test seams for incomplete components; do not advertise
or enable a partial public v2 execution path. The public path opens in W8 only
after the coupled invariant works. An E=1 or Bank-serial intermediate result
is a control/test configuration, never a completed v2 Phase. If a unit exceeds
a careful chat, split its work across chats while retaining this Phase boundary.

For each unit, run its focused tests, directly affected regressions, and the
smallest relevant build after code changes; review the full unit diff. For
Phase exits review the entire Phase diff and run `git diff --check`. Compilation
alone is not a timing/state oracle. Add narrow harness exposure only when the
specified invariant cannot otherwise be observed. Avoid broad suite repetition
unless the diff or a failure adds risk.

**Common stop rule:** stop before the first code consumer of a genuinely new
modeling choice. Identify the failing accepted invariant, source evidence,
alternatives and behavioral trade-offs; ask the user. Do not adjust an Accepted
decision or make a test invent semantics. An implementation bug, absent API,
or larger-than-expected refactor is not itself a new modeling decision. Each
unit below identifies its particular stop boundary.

## Phase 1 — Common placement and submission contract

### W1 — Replaceable geometry/profile and canonical location resolver

**Goal / observable behavior.** Implement B's shared, value-free location
authority and the initial **MIMDRAM-DDR4_8Gb_x8 modeled placement profile v1**.
Resolve scalar physical bit and explicit layout/region origins to paired
external/internal locations, ordered groups and canonical CellIDs. A mat-row
region need not be represented by one fabricated scalar address. Preserve
profile and routing association; distinguish BurstColumn B and group G types.

Use B's forward/inverse formulas directly as the selected profile contract;
do not derive a replacement layout. Validate one channel, CacheLineInterleave,
RoBaRaCoCh, no row remapping/reserved offsets, rank replication N=1 or N=4,
and the coordinated dimensions: DQ8/prefetch8, 1024 organization Columns,
8 chips, 16 mats/chip context, 512 cells/mat-row, 4 HFF positions, and
1024-row subdivision. These are profile properties, not operation constants.
Reject out-of-domain origins instead of wrapping; retain all low address bits
and bit-within-byte information. Expose ordinary ACT and burst RD/WR footprints
and selected compute/LC/GB footprints from the same resolver, without payloads.

Ordinary requests must be resolvable through this same canonical placement/CellID
authority, with ordinary/PuD same-cell consistency tested in W2. Retain internal-
location metadata in an ordinary Request only if an actual runtime consumer
requires it. Prefer resolver-level consistency and on-demand resolution over
changing the ordinary Request lifecycle merely for symmetry with PuD requests.

**Authority:** B; A/C-E for the value-free substrate boundary.

**Inspect/change:** `src/ramulator/dram/dram_spec.{h,cpp}` and localized
profile/resolution support; `base/request.*` only as required for shared types;
`memory_system/channel_mapper/impl/cache_line_interleave.cpp`,
`controller/addr_mapper/addr_mapper_base.cpp`,
`controller/addr_mapper/impl/ro_ba_ra_co_ch.cpp`; Python standard configuration,
`python/ramulator/codegen.py`, DRAM registration/build lists if needed;
`tests/utils/test_harness.cpp` and focused geometry tests. Inspect packaging
alternatives above before introducing v2 capability/configuration.

**Dependencies:** none beyond baseline/authority recovery. First implementation
session records baseline test outcomes for affected configuration/mapping paths.

**Validation before W2:** exact forward/inverse round trips; all coordinate and
negative/out-of-capacity bounds; positive dimensions and exact-division checks;
enumerate all 65,536 bits in a rank-row for uniqueness and full coverage, all
128 groups/mat and their four ordered positions; test BankGroup/Bank/Rank and
first/last row/subarray boundaries and N=1/N=4 replication. Verify 8192
bits/chip-row, 64 bits/chip/burst, 64 B/rank/burst, 8 KiB/rank-row,
8 Gibit/chip and 8 GiB/rank using B's equations. Do not allocate full DRAM
contents to test capacity.

Include a coherent synthetic profile with non-identity G/B mapping, compatible
inverse and coverage, to prove replacement works without editing operation
semantics. It is a software contract fixture, not a new supported physical
x4/x16 model. Verify unsupported mapper/remap and inconsistent HFF-only
overrides fail for v2; legacy overrides retain their meaning.

**Regressions:** existing DDR4/PuD/movement configuration, mutable-definition
isolation, classification and mapper tests; codegen/build if definitions change.

**Completion:** one resolver, tested inverse/coverage and profile replacement;
legacy configurations unchanged; no public v2 execution claimed.

**Stop:** a supported origin cannot be resolved under B without assuming new
placement, wiring, aliasing, remapping or grouping. First consumer is the
profile decode/validation; do not invent a broader production profile.

### W2 — Paired submission, compute ranges and shared consumer consistency

**Goal / observable behavior.** Direct v2 callers construct resolver-produced
paired operands with origin/profile association and explicit scope. All five
compute types require the same non-empty inclusive contiguous legal mat range
for every operand and occurrence. Column and size_bytes do not narrow compute
mat-rows; full range must be explicit. MAJ3/MAJ5 require distinct physical-row
operands. Keep all current primitive operand counts and RowCopy's arbitrary
destination list rather than imposing a new fixed limit.

Route from resolved operand 0; retain the memory-system/controller validation
split. Check external projections against internal locations and profile,
common Bank/subarray context, and operation-specific topology. Reject missing
origins/ranges, bare legacy vectors, incoherent pairs, unsupported per-mat
selectors or multi-routing-context regions; no modulo/alignment migration.
LC uses a common range and two ordered groups; GB uses directed singleton
local neighbors within a chip/subarray. Keep movement N/A size and exact bits.

Integrate the resolver with the ordinary v2 mapping path as well as PuD
submission. Check the final conventional mapper result against its paired
projection; retain origins before compaction and use final Row for subdivision.
Ordinary consumers may resolve on demand under W1's runtime-consumer constraint;
shared resolution does not require every ordinary Request to persist internal-
location metadata. V2 PuD operands must still retain the resolved location
information needed throughout request and occurrence lifetime. Do not require
new ordinary functional values or alter forwarding/coalescing. Distinguish a
full RD/WR burst footprint from a requested byte subregion without adding
partial writes.

**Authority:** B's generic contract, affected locations and compatibility;
A's distinct-row majority boundary; C-E's functional split.

**Inspect/change:** `base/request.*`, `memory_system/pud_request_routing.h`,
`memory_system/impl/generic_dram_system.cpp`,
`controller/pud_request_validation.*`, `ControllerBase::send`,
`GenericDDRController::try_send_special_request`, `pud_sequence.*`, W1 resolver;
ingress/occurrence harness helpers and focused location/request tests.

**Dependencies:** W1. V2 validation/retention can be tested without enabling
the incomplete execution capability.

**Validation before W3:** all five range/count cases, singleton/full/chip-crossing
legal ranges, empty/reversed/out-of-bounds/noncontiguous targets, mismatched
operand ranges, same-Bank/different-subarray rejection, repeated-row majority
rejection, incorrect profile/context/external projection, illegal LC/GB shapes
and arbitrary bit anchors masquerading as movement groups. Verify retention
through copy, failed enqueue/retry, occurrence switches and completion copies.

Compare ordinary ACT/RD/WR footprints against compute and LC/GB footprint
intersections and ordered HFF positions using actual consumer paths. Cover low
offsets, nibble/chip/mat/group/row boundaries and W1's non-identity fixture;
independent arithmetic bijection tests alone do not prove common consumption.
Confirm invalid requests acquire nothing and do not increment acceptance.

**Regressions:** `test_pud_request_ingress.py`,
`test_movement_request_validation.py`, `test_pud_occurrence_sequences.py`,
`test_request_classification.py`, ordinary mapping/size/forwarding/coalescing.
Keep legacy opaque movement selectors and existing compute streams unchanged.

**Completion / Phase 1 exit:** shared location identity reaches all required
consumers; v2 request and footprint tests pass; profile/operand lifetime is
documented in the implementation; incomplete v2 execution is unavailable and
cannot fall through to legacy. Run Phase 1 diff review and `git diff --check`.

**Stop:** an accepted operation needs new alias, majority, scope, origin or
partial-write semantics. First consumers are resolver-backed validation and
operand construction; unsupported forms remain rejected, not guessed.

## Phase 2 — Coherent range execution

### W3 — Range-local Device phases, occurrence identity and timing

**Goal / observable behavior.** Keep primitive identity, ordered operands,
the occurrence cursor and sequence progress controller/request-owned. Each
range execution context holds stable context identity, the resolved mat range,
temporal phase, activated-row/operand identity needed for Device legality,
context-local timing history and recovery state. There is only one authoritative
occurrence cursor; do not duplicate sequence progress inside Device/range state
merely to simplify context-aware dispatch.

Every ACT, N and terminal PRE receives its own resolved context. Conventional
Bank row state remains separate. Reuse `describe_pud_occurrence` and issue
history; preserve the exact five sequences, including N retaining the source
and NOT_COPY's subsequent destination ACT. No payload values or per-mat Device
replicas.

Move only v2 compute phase dependencies out of latest-Bank history. The local
intervals are: A*→A 11; A→A/A_S/PRE 5; A_S*→A/N 40; A_S→PRE 34;
N→A/PRE 43 CK. Scope terminal PRE/nRP to its range. Keep each edge authoritative
in one domain; explicitly inventory inherited Python/Device edges so local
and Bank constraints do not both apply. Retain shared C/A and conventional
PREpb/PREab/RDA/WRA/REFab recovery at their original scopes. Retain the hybrid
compute ACT exclusion from nRRD/nFAW while preserving ordinary activation-current
constraints; movement's documented omissions remain its own fidelity boundary.
Do not simply bypass all Device timing for v2 commands.

**Authority:** C-E range-state occurrence table; C-T history scopes and
rounding; A's width-independent local compute costs.

**Inspect/change:** `pud_sequence.*`; `dram/device.{h,cpp}`, `node.{h,cpp}`,
`func_types.h`, `commands/ACT_PUD*.h`, `N.h`, `PREpb.h`; v2 definition/config
and generated bindings only where needed. Inspect explicit context transport
versus a narrow Device-side store before implementing it. Preserve legacy
handler paths and generic hierarchy APIs where a local seam suffices.

**Dependencies:** W2. Component tests may establish protected contexts directly;
this does not enable public allocation or bypass resolved-target validation
in the final path.

**Validation before W4:** interleave two same-operation and heterogeneous
range contexts, checking independent row identity, charge-sharing/sensed phases,
controller-owned cursors and each edge at ready−1/ready. Include N in one range
while the other
activates/senses/closes. Charge-sharing PRE, premature terminal PRE, incompatible
phase, wrong/stale context and unassociated command dispatch must fail without
mutation. Closing A cannot modify B's phase, rows or deadlines.

Check isolated first-ACT-through-recovery anchors: RowCopy(D)=40+5D+16;
MAJ3=66, MAJ5=76, NOT=99, NOT_COPY=104 CK (RowCopy D=1 gives 61).
Check widths do not change local intervals. Verify C-T's 1.005 upper envelope
on continuous ACT phases still ceilings to 11/5/40/34 at 0.833 ns; N=43 and
nRP=16 stay unchanged. No extra CK per ACT or aggregate multiplier.

**Regressions:** DDR4, DDR4_PuD and movement Device timing/state tests and
existing occurrence tests; compare generated legacy timings/metadata unchanged.
Broaden Device regressions if shared dispatch rather than a local seam changes.

**Completion:** context-local legal transitions and timing are independently
testable; no v2 range PRE writes a Bank-wide compute recovery deadline; inherited
ordinary/maintenance and legacy behavior remain demonstrably intact.

**Stop:** implementation appears to require a new phase, early close, extra
timing edge, per-mat independent execution or changed ordinary scope. The first
consumer is context-aware legality/timing dispatch. Inspect smaller storage
before claiming a full per-mat representation is necessary.

### W4 — Protected lifecycle through recovery and exact-once completion

**Goal / observable behavior.** Represent allocated/pre-first-ACT, active and
recovering compute with protected range records. Terminal PRE at T removes only
that invocation from command scheduling, closes its activated rows and starts
local recovery; engine and range remain reserved until T+nRP. At that boundary,
release both resources and complete accounting/callback exactly once. No early
engine reuse. Allocation policy itself is W7.

Reuse delayed completion and extract/erase before callback. A callback may
submit a successor or append a forwarded read without stale handles, duplicate
release or iterator invalidation. Preserve depart-based reordering and request
acceptance/completion counters; unallocated pending requests own nothing.

**Authority:** C-E resources/recovery/completion; C-T range recovery.

**Inspect/change:** `GenericDDRController` retained contexts,
`ControllerBase::retire_request`, `serve_completed_requests`, active/pending
buffers and `m_active_per_bank`, W3 context lifetime; lifecycle test harness.
Prefer a narrow completion-release hook over a second completion subsystem.

**Dependencies:** W3. Test allocation/recovery with explicit fixture reservations
before introducing the real allocator.

**Validation before W5:** at T and T+nRP−1, sequence is unschedulable but range
and engine remain held and callback absent; at T+nRP resources are released
before the callback and completion count advances once. A disjoint B progresses
during A's PRE/recovery. Intersecting work cannot reuse A early. Include two
recoveries on one tick, mixed read/PuD departure reordering, callback-submitted
compute and forwarded-read completion, buffer moves/retries, and no surviving
context/queue/completion reference after drain. Pre-first-ACT reservations
must not be mistaken for unowned pending work.

**Regressions:** compute/movement lifecycle and statistics, ordinary completion,
reentrancy and backpressure. Legacy release-at-terminal-issue behavior remains
unchanged, including existing tests that inspect schedulable Bank ownership.

**Completion:** protected lifetime spans allocation through recovery and shares
the established completion path; lifecycle tests prove exact release/callback
ordering without relying on command-buffer occupancy alone.

**Stop:** a proposed fix requires early engine release, abort/preemption,
different departure timing or functional visibility. First consumers are
retirement/release and callbacks; none may silently change C-E.

### W5 — Coherent movement, ordinary and maintenance exclusion

**Goal / observable behavior.** Install the complete conflict and drain rules
before overlapping compute is scheduled. Device-issued ordinary ACT/RD/WR/RDA/WRA
and unrelated Bank PRE conflict with allocated/active/recovering v2 compute.
Existing ordinary active work drains and conventional close/autoprecharge
recovery completes before allocation. A necessary preparatory ordinary PRE is
Bank-wide and does not advance a PuD cursor.

Retain LC/GB's per-Bank context, topology, exact bits, local timing graph and
first-ACT acquisition. Movement does not consume compute engines. Terminal
movement PRE retires its sequence, with Bank exclusion through recovery.
Compute/movement and all LC/LC, LC/GB and GB/GB pairs remain Bank-serialized.
Retain resolved endpoint/row metadata: LC source PRE closes source activation
but preserves source-valid metadata through recovery/destination ACT until WR;
GB retains both activation conditions and source validity through WR, and its
terminal PRE closes both endpoints. These are validity/identity records only.

Queued priority maintenance stops new allocations under the existing FIFO-head
policy, while already allocated contexts drain. Validate whole PREab/refresh
scope against all intersecting protected contexts and recoveries before any
mutation. After drain, issue PREab only if ordinary row state requires it;
honor nRP/nRFC and existing autoprecharge constraints. Maintenance already in
progress blocks affected starts. Preserve active-continuation precedence and
no scope-aware priority bypass, deadline/retention guarantee or preemption.

**Authority:** C-E admission, maintenance and movement metadata; C-T retained
LC/GB graphs and conventional recovery; A's pairwise concurrency policy; B's
resolved movement endpoints.

**Inspect/change:** `GenericDDRController::is_pud_eligible_before_prerequisite`
and final issue checks; `ControllerBase::would_close_active`; `dram/device.*`,
PREpb/PREab/REFab and ordinary/movement handlers; `refresh/impl/all_bank.cpp`,
Open/ClosedCAP, controller plugins and existing movement accounting helpers.
Retain full-scope Bank traversal and add range-aware guards locally.

**Dependencies:** W2–W4. This unit provides the eligibility predicate consumed
by resolved-target dispatch and real allocation; no later unit may defer it.

**Validation before W6:** compute blocks LC and GB while active and recovering,
and movement blocks compute through its recovery. Test all movement/movement
pairs in both submission orders, including disjoint mats; different-Bank
movement still progresses subject to shared resources. Assert unchanged LC
issues 0/16/39/55/94/114, depart 130, and GB 0/1/39/41/59, depart 75 CK.
Verify LC source-valid retention and GB endpoint close identities.

Exercise ordinary activity before allocation, RDA/WRA recovery, unrelated PRE,
maintenance queued before allocation, after allocation but before first ACT,
during charge sharing/N and during recovery. PREab/REFab must wait for the
last intersecting recovery; a conflicting Bank anywhere in a scope prevents
partial action/timing mutation on earlier Banks. Check already-active nRFC,
another Rank's legal maintenance, FIFO head blocking, row-policy and
plugin-injected commands, and final rechecks after command upgrade.

**Regressions:** movement ownership/local timing/refresh/row-policy/statistics/
plugin tests; ordinary forwarding/coalescing remain allowed at ingress with
their existing timing even when Device issue is blocked. Preserve AQUA/RRS
movement/remap rejection and existing capability rejections; do not add remap
support or change legacy trace schemas. Run DDR4/PuD maintenance regressions.

**Completion:** full mixed-traffic and maintenance exclusion is tested against
allocated, active and recovering contexts; movement retains its graphs and
per-Bank lifecycle; no ordinary functional/coherence model added.

**Stop:** a consumer needs new movement transport/topology/concurrency, plugin
remapping, maintenance interruption or refresh deadlines. First consumers are
eligibility, scope validation and movement actions; retain accepted rejection
and conservative behavior instead of inventing missing physical details.

### W6 — Resolved-target consumption without physical transport resources

**Goal / observable behavior.** Apply T-A: the Device consumes the row and
resolved `MatRange` associated with each `ACT_PUD*` atomically at issue.
Retain W1 profile-defined mat/chip topology, W2 request/occurrence identity,
W3 range-local state and PRADA timing, and W4/W5 protection and conflict rules.
Every compute occurrence retains its explicit range/context association,
including N and terminal PRE; no Bank-global selected-target state is implied.

The production ordering remains:

```text
pending compute request
    -> allocate/acquire compute engine + complete mat range
    -> ACT_PUD* consumes its resolved target at issue
    -> subsequent occurrences consume their own resolved associations
```

No physical target-delivery step occurs between allocation and activation.
Remove baseline dependence on per-chip FIFO occupancy, Q=8, descriptor
preparation, ACT/PRE enqueue/dequeue, initial one-CK target-only setup,
T+1 transport, T+2 target readiness, or target-specific C/A reservations.
Preserve ordinary shared command issue and applicable timing; local ACT
anchors do not shift. Target metadata does not acquire execution ownership.

**Historical / optional fidelity.** The completed Alternative-A/Q=8
implementation and its verification are recorded in progress above and Git
history at `0ce6922`. Alternative A was a project mapping of MIMDRAM transport
onto PRADA activations, not a MIMDRAM-specified PRADA mechanism. It remains
available for possible sensitivity analysis, not a baseline requirement.
Current baseline source no longer contains it; validation is recorded above.

**Authority:** T-A; C-T local/shared timing and ACT-overhead rounding;
C-E allocation/maintenance lifetime; B resolved chip/range identity.

**Inspect/change:** existing W6 queue/setup/successor dependencies in
`dram/pud_target_queue.*`, Device and controller dispatch, `pud_sequence.*`
and test-only transport fixtures. Reuse W2/W3 resolved occurrences and W4/W5
checks. Preserve legacy command-cycle generation, shared issue constraints
and production trace schemas. No new generic event, pin or bus framework.

**Dependencies:** W2–W5. Component fixtures may construct protected contexts;
production allocation remains W7 work. Baseline alignment does not begin W7.

**Validation before W7:** every activation receives its exact resolved row,
range and occurrence association, across copies/retries, repeated equal ranges,
multi-destination RowCopy and NOT_COPY across N. Check profile-driven ranges
including chip boundaries and replacement profiles. Missing/stale/mismatched
associations fail before mutation; readiness probes remain pure.

Verify a legal cold/late activation needs no target-only setup, successor
event or queue capacity/readiness. No mat-target transport reserves T+1 or
blocks otherwise eligible ordinary/movement work; applicable command issue
and local timing still govern readiness. Preserve W3 local anchors and
W4/W5 recovery, maintenance and exclusion, including rejected-issue behavior.

**Regressions:** W3 timing and W4/W5 lifecycle/maintenance tests; directly
affected legacy command-cycle, Device, LC/GB timing and other-Bank scheduling
tests. Broaden coverage if shared bus/dispatch changes warrant it.

**Completion:** validated resolved-target consumption implements T-A with no
physical target-transport resource model. Preserve local compute timing and
independent engine/range ownership. Report omitted transport latency,
mat-queue stalls and target-delivery C/A contention as fidelity limitations,
not physically zero costs.

**Stop:** baseline alignment appears to require changed target identity,
placement, local timing, recovery or exclusion beyond Accepted authority.
First consumer is occurrence validation/Device issue; present the conflict
before changing those semantics.

### W7 — First-fit engine allocation and concurrent command arbitration

**Goal / observable behavior.** Add configurable positive E compute engines
per controller/channel control-unit instance, shared across Banks and Ranks;
initial E=8, validation E=2 and E=1 serialized control. On allocation scan
pending compute oldest-to-newest and select the first eligible request whose
complete range is available and for which an engine is free. Reserve both
atomically before waiting for initial ACT. No allocation based on
local command timing readiness; unallocated pending requests own nothing.

Enforce W6's production allocation-before-ACT ordering. Once allocation
succeeds, the context may wait for shared C/A arbitration or local timing
while retaining its accepted engine/range ownership. T-A adds no target
transport or mat-queue waiting.

Disjoint ranges within one Bank/subarray may make independent progress.
Intersecting ranges conflict even with different operand rows. A Bank cannot
allocate another subarray until all existing protected ranges drain. Different
Banks share the same E pool, C/A and applicable maintenance/timing limits.

Keep allocation separate from command arbitration. Use W5's before-prerequisite
eligibility and final issue checks, W3's context-local readiness and W6's
resolved-target validation with shared command-issue readiness. Already
allocated continuations keep active precedence; preserve priority FIFO and
ordinary/movement arbitration. A timing-blocked
context must not monopolize shared issue. Avoid reserving
resources as a side effect of FRFCFS/FRFCFSRowHit readiness probes.

**Authority:** C-E resources/admission/precedence and engine scope; C-T shared
issue versus local readiness; A's required same-subarray overlap.

**Inspect/change:** `GenericDDRController::tick`, pending/allocated context
management, retained-resource predicates; `ControllerBase` request-aware
prerequisite/readiness/final validation seams if needed; both scheduler
implementations and test harness. Reuse the shared request-count queue and
candidate machinery where compatible, without replacing ordinary scheduling.

**Dependencies:** W3–W6 complete, plus W2 request lifetime. Inspect the exact
tick ordering of completion release, refresh generation, allocation
and arbitration before wiring them together; document any non-trivial design
choice according to AGENTS.md without treating it as a reopened Gate.

**Validation before W8:** E=2 permits two same-operation disjoint ranges and
at least one heterogeneous pair to issue/progress before either completes.
Show later occurrences interleaving, not just co-admission. Stagger starts so
one PRE/recovery overlaps the other's active phase. Intersecting ranges and
same-Bank different subarrays stay blocked through recovery. E=1 serializes
compute even across Banks; E=2/E=8 enforce capacity including pre-ACT waits
and recovery; a ninth eligible request at E=8 waits for actual release. Pool
scope spans multiple Banks/Ranks and movement uses no compute slot.

Verify unallocated pending requests own no execution resources, and allocated
contexts retain engine/range ownership throughout pre-first-ACT waiting.

First-fit fixture: older A holds a range; oldest pending B conflicts with A;
younger C fits a disjoint range; still younger D also fits. With one free
engine C allocates first, B remains pending/unowned, and D waits for capacity.
After A recovers, B precedes younger eligible work. Also show an oldest
range-eligible compute may allocate despite its ACT being timing blocked;
allocation order is not oldest-ready command order. Use deterministic existing
queue order for equal ages and test both configured schedulers.

Recheck exclusion before prerequisites and after policy/plugin changes. Include
other-Bank work during local gaps, shared command-issue contention, multiple
simultaneous recoveries, active-buffer capacity/backpressure and callback reuse
of a just-released engine. Pending capacity must not become an undocumented
compute-engine limit. Keep command issue at one shared C/A action per tick.

**Regressions:** complete GenericDDR compute/movement scheduling and lifecycle
tests. If common scheduler/prerequisite/completion APIs changed, run the full
controller-scheduling suite, including HBM/GDDR users, now; record results for
closure instead of automatically repeating unchanged coverage per unit.

**Completion:** real allocation and command issue demonstrate MIMD with fully
coherent state, resolved targets, recovery and exclusion. No legacy ownership
predicate or Bank compute history silently serializes v2 disjoint progress.

**Stop:** integration requires changing engine scope/release, allocation policy,
subarray concurrency or existing mixed-traffic arbitration beyond C-E. First
consumer is allocation/tick integration. Do not introduce a throughput policy
or fairness guarantee absent from authority merely to improve results.

### W8 — Public v2 integration and reproducible substrate microbenchmarks

**Goal / observable behavior.** Enable the complete explicit v2 path after
W1–W7 pass. Exercise normal C++ Request → GenericDRAM → GenericDDR → Device →
completion, with the accepted profile and E=8 default/E=2/E=1 controls. Setup
rejects incompatible profile/mappers/remappers or incomplete capability instead
of accepting legacy vectors under a v2 label. All five compute primitives and
both movement requests consume W2's paired locations.

Extend the existing compute/movement microbenchmark and export-config patterns
with explicitly selected v2 scenarios while keeping legacy default invocations
and expectations. Existing benchmark configurations use pass-through mapping;
v2 configurations must use B's profile-backed mapping/origins instead of
silently treating those legacy vectors as placements. No arithmetic macro is
needed: use independent primitives and callback-submitted dependent primitives.

Report profile, E, the T-A transport abstraction, primitive/range identity,
arrival, first ACT, issued occurrences, terminal PRE and recovery/departure.
Distinguish local execution anchors and observed waiting/contention; terminal
nRP is already included in primitive totals. State that transport latency,
mat-queue stalls and target-delivery C/A contention are omitted, not physically
zero. Test-only observation can expose allocation and resolved context identity.
Existing production command traces lack unique request/range reconstruction;
do not infer arbitrary concurrent histories from them or require a new trace
schema. Deliberately unique source
IDs can identify commands in these controlled benchmarks.

**Authority:** A experiment/scope and dependency boundary; B profile/consumer
contract; C-E lifecycle/accounting/functional split; C-T latency accounting;
T-A transport abstraction and fidelity limits.

**Inspect/change:** Python v2 configuration/capability and generated registration;
GenericDRAM/GenericDDR public ingress; `examples/ddr4_pud_microbenchmark.cpp`,
`examples/mimdram_movement_microbenchmark.cpp`, their export configurations,
root `CMakeLists.txt` if necessary; existing harness, smoke tests and
`docs/pud/ddr4-pud-user-guide.md` for concise usage. Reuse existing documentation;
do not create additional persistent documents without authorization.

**Dependencies:** W1–W7; no fundamental safety rule remains deferred here.

**Validation before W9:** normal-path uncontended 61/66/76/99/104 CK local
anchors, multi-destination 40+5D+16, several range widths, and LC/GB 130/75.
Verify engine/range and arbitration waiting increases request latency when
expected without adding physical target-transport costs or shifting local
anchors. Reproduce same-operation and heterogeneous overlap with E=2/E=8
and serialization with E=1; movement
blocked through compute recovery; longer AllBank-refresh mixed traffic drains
without stale contexts. A dependent primitive is submitted only
after all required producer callbacks; submission order alone is not an oracle.

Confirm acceptance once after successful enqueue, completion/latency and moved
bits once at recovery, movement N/A sizes and exclusion from ordinary byte
throughput, unchanged forwarding/coalescing and legacy statistics names.
No test asserts arithmetic result values or a GEMV/reduction speedup.

**Regressions:** both original microbenchmarks and their documented export/run
commands; DDR4/PuD/movement smoke/configuration and directly affected statistics,
trace/plugin tests. Build the excluded-from-all benchmark targets explicitly.

**Completion / Phase 2 exit:** public path exposes the complete accepted
substrate; benchmark commands and limitations are reproducible; review the
entire Phase diff and run `git diff --check`. Proceed to final closure, not a
separate functional or macro implementation.

**Stop:** a requested observable requires new production trace/statistic
semantics, functional results, scalar reduction or a new public workload ISA.
First consumers are benchmark/API/reporting changes; use existing/test-only
observability where sufficient and keep the excluded layer outside this plan.

## W9 — Final integration closure and independent review

**Goal / observable behavior.** Validate the complete v2 invariant against the
baseline and authority in a fresh context. This is validation/review work, not
another implementation Phase or an automatic commit. One fresh-context audit
is justified by context-aware Device dispatch, scheduler integration and
reentrant recovery release; no audit is required after every small unit.

**Authority:** A/B/C-E/C-T/T-A; AGENTS.md risk-tiered review rules.

**Inspect:** full main-to-implementation diff, generated files and test seams;
all changed call sites of prerequisites, timing, issue, close, completion,
capability checks and profile resolution. Audit actual v2 source and tests,
not just this plan or historical test counts.

**Dependencies:** W8 and both Phase exits complete. Reuse recorded broad results
only if their covered source has not changed; fixes require affected reruns.

**Validation and regressions required for closure:**

- Map every unit's accepted behavior to an executed test; inspect exact event
  boundaries and absence of state/resource mutation on rejected actions.
- Verify common resolver consumption, no formula copies in operation code,
  copy/retry lifetime, no Bank-global target, no duplicate local/Bank timing,
  no physical target-transport resource dependence, and no surviving
  engines/ranges or completion references after drain. Review full maintenance
  scopes and callback reentrancy explicitly.
- Regenerate/build from source and run v2 tests, all relevant DDR4/PuD/movement
  Device and GenericDDR tests, both legacy benchmarks and v2 scenarios. Run
  broader shared-infrastructure suites at the level warranted below.
- Review legacy defaults, IDs, generated definitions, forwarding/coalescing,
  movement topology/graphs/bits and conservative pairwise reservation. Confirm
  no functional simulator, arithmetic macros, hierarchy redesign, movement
  concurrency or unsupported physical fidelity claim entered the diff.

Available baseline commands (use the actual build directory and focused new
test paths established during implementation):

```sh
PYTHONPATH=python python -m ramulator codegen
cmake --build build --target ramulator _ramulator _ramulator_test -j2
cmake --build build --target ddr4_pud_microbenchmark mimdram_movement_microbenchmark -j2
PYTHONPATH=python pytest tests/device_timings -q
PYTHONPATH=python pytest tests/controller_scheduling -q
PYTHONPATH=python pytest tests/smoke -q
PYTHONPATH=python pytest tests/latency_throughput/test_fast.py -v -s -k DDR4
git diff --check
```

Run focused tests after the relevant rebuild throughout development; this broad
matrix is for shared-risk/closure coverage, not every unit. If generic bus or
timing generation changes, include relevant HBM/GDDR/multi-cycle cases and
their smoke coverage. Full expensive throughput campaigns need a concrete
timing/refresh change or unresolved failure to justify them.

The historical movement plan records a full controller-suite allocator abort
after pytest assertions passed; this planning task did not rerun or diagnose
it. Capture baseline and implementation process exit codes as well as assertion
results. Do not report an aborting suite as a clean pass, skip the affected suite,
or assume the historical failure is fixed. If reproduced, compare the same
environment/baseline and identify the remaining verification limitation; a
new regression must be fixed before closure.

**Completion:** all behavior-specific tests and required regression checks
have reviewable results; the full diff passes self-review and the independent
audit; `git diff --check` passes; any environment/baseline process failure is
explicitly reported with its comparison evidence, not hidden as success. No
claim of functional-value correctness or physical MIMDRAM equivalence follows
from these timing/state checks.

**Stop:** audit exposes a genuine new model choice or an unexplained validation
failure that prevents establishing the accepted invariant. Identify the first
affected consumer; fix implementation defects and rerun affected tests, or
return the modeling question to the user before changing semantics.

## Planning self-review and blockers

- A/B/C are treated as fixed authority. No historical gate or unresolved
  physical-wiring question is used to reopen accepted scope, T-A's abstraction,
  engine release, same-subarray concurrency or geometry.
- All CellID/footprint work is identity-only. No functional storage/interpreter,
  ADD/MUL, GEMV, reduction/host-combination implementation is scheduled.
- Reuse is localized to the current request/occurrence/controller/Device and
  delayed-completion boundaries. Generic hierarchy, scheduling, event systems,
  trace formats and physical queue replicas are not independent goals.
- Ordering puts location identity before consumers, local state/timing before
  recovery and exclusion, and all of those plus resolved-target consumption
  before allocation and public overlap. Mixed-traffic safety is part of the coherent execution
  Phase, not cleanup after enabling MIMD.
- No genuine blocker prevents planning from the Accepted decisions. Concrete
  C++ packaging/retention and integration details remain bounded implementation
  choices at their first consumers. New semantic conflicts, if implementation
  reveals one, follow the explicit stop conditions rather than being decided
  by this plan.

The original plan-creation task changed only this plan. The 2026-09-09
transport-abstraction update records T-A, narrowly updates C-T and this plan,
and leaves code, source references, AGENTS.md and W7 execution unchanged.
The separately authorized W6 baseline alignment and W7 allocation/arbitration
are now implemented and validated as recorded above, including the recorded
native-regression limitations. W8 is now implemented and validated as recorded
above; W9 fresh-context final integration closure is complete as recorded above.
