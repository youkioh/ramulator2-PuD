# PuD multistandard substrate implementation plan

Status: Phase 1 and the common execution-model correction complete on 2026-09-16.
Phase 2 GDDR7 primitive substrate binding and validation are complete.
Phase 3 HBM3 primitive substrate binding and validation are complete on 2026-09-17.
Phase 1's frozen DDR4 equivalence evidence remains unchanged.
G0, the common no-finite-control-engine model and GDDR7/HBM3 G1/G2/G3/G4/G6
are Accepted. G5 remains Accepted and G7 is re-Accepted with utilization-aware
packing and path-bounded Request fusion before Channel striping. Phase 4 is
implemented and validated following the user's separate implementation
authorization; frozen DDR4 artifacts and primitive evidence remain unchanged.
Phase 2 was explicitly authorized by the user's implementation request.
HBM3 G1/G2/G3/G4/G6 investigation and modeling acceptance are complete.
Phase 3 was separately authorized by the user's implementation request.
Phase-1 baseline: `093af06009f0d3e403fc9e949682ce6722a8ec3a` on
`feature/pud-multistandard-substrate`.

Recover [AGENTS.md](../../../AGENTS.md), the
[audit](../references/pud-multistandard-substrate-audit.md), its linked current
Accepted authorities, and the [Accepted architecture](../decisions/pud-multistandard-substrate.md)
before implementation. This plan authorizes no new modeling choice. G0–G7
refer to the audit's gate table; do not reconstruct current authority from
historical plans. Record acceptances at their canonical modeling boundaries.
For GDDR7 Phase 2, recover the
[evidence and alternatives](../references/gddr7-pud-modeling-reference.md) and
[canonical policy/status](../decisions/pud-multistandard-substrate.md)
before the implementation work below. Phase 1 and older completed plans/audits
record the old E=8 implementation; the common correction below intentionally
changes its scheduling model without rewriting that historical proof.

## Phase 1 — one common substrate with identical DDR4 behavior

Invariant: the common path executes the current DDR4 configuration with
identical commands, timestamps, placement, ownership, completion and generated
workloads. GDDR7/HBM3 remain conventional-only until complete bindings exist.

Entry gate: G0 architecture review. A newly discovered semantic change is a
stop condition, not refactoring discretion. G1–G4 are not prerequisites for
extracting existing DDR4 behavior; leave their consumers unconfigured.

Reviewable work units within this single integration phase:

1. **Capture the baseline before any production edit.** Verify clean HEAD and
   build/import paths in this checkout. Build the local `_ramulator` and
   `_ramulator_test` targets as needed, plus the two existing microbenchmarks.
   Save resolved configs, requirements/layout/physical trace artifacts,
   command traces and callback/ownership observations in a checkout-local
   ignored build output directory. Record commands, HEAD and fixture inputs.
   No dependency on another checkout, historical binary or old `/tmp` results.
2. **Factor declarations and location identity.** Isolate common PRADA/movement
   definitions, DDR4 calibration/recovery/shared edges and current profile
   factory. Generalize location hierarchy identity/projection and validation
   while retaining the same DDR4 mapping, association checks and public input
   behavior. Touch `pud_location.*`, RequestLocations identity checks,
   validation/routing and necessary profile exposure only. Keep existing
   table/permutation authority and fallback rejection. Do not invent profiles.
3. **Factor execution integration.** Move reusable PuD admission, first-fit
   allocation and candidate/issue helpers out of GenericDDR-specific code into
   the common controller boundary. Keep GenericDDR tick order/tie breaking,
   priority head behavior, recovery release ordering, active-buffer pressure
   and notifications exact. Parameterize command/timing/recovery inputs in
   `pud_sequence.*`, ControllerBase and associated Device dispatch. DDR4 is
   the sole populated binding; preserve its one-bus/Channel publication and
   invocation-local timing behavior. No target command classes are added.
4. **Close the DDR4 compatibility proof.** Rebuild, compare the frozen artifacts
   and events below, run directly affected and cross-cutting conventional
   regressions, review the whole Phase diff and run `git diff --check`.
   Keep the existing PuDTrace grammar and GEMV outputs unchanged. Do not end
   the phase with a provisional command, close, conflict or recovery path.

Work-unit checks: definition/config equality after declaration factoring;
resolver inverse/nonidentity/boundary tests after location changes;
occurrence/range timing, allocation, conflict and reentrant lifecycle tests
after controller/Device changes. Rebuild the smallest affected target each
time. Do not run the full arithmetic exhaustive suite after each C++ edit.

### Required before/after proof

Compare the same fixtures/configuration and source IDs, not just success codes.
Do not normalize away cycles, order, addresses or payload footprints. Only
artifact path prefixes and infrastructure wall-clock measurements may differ.

| Observable | Baseline fixtures and equality requirement |
| --- | --- |
| Resolved configuration | Commands/IDs, timing values/edges, command occupancy, geometry, mapper and engine settings exactly equal. |
| Primitive streams/latency | All five compute types over singleton, cross-chip and FULL_MAT ranges; RowCopy with 1/2/5/32 destinations. Full issue records and callback times equal. Isolated anchors: RowCopy=40+5D+16, MAJ3=66, MAJ5=76, NOT=99, NOT_COPY=104 CK. |
| Movement streams/latency | LC singleton/range/cross-chip and legal GB singleton edge; LC clocks 0,16,39,55,94,114 then completion 130; GB 0,1,39,41,59 then completion 75, relative to first issue. Invalid topology stays rejected. |
| Physical placement | Forward/inverse bit identities, ordinary ACT/burst and PuD regions, groups/positions, GB successors, chip boundary 15/16, row/subarray boundary 1023/1024, rank replication 1/4 and nonidentity software profile cases equal. |
| Concurrency/resources | All six unordered compute/LC/GB pair classes in both relevant arrival orders, disjoint/intersecting footprints, no-SALP, E=1/2/8, pre-ACT reservations, LC source close, terminal recovery, ordinary traffic and full-scope maintenance. Compare issue and release events, not peak inflight alone. |
| Lifecycle/accounting | Admission retries, promotion pressure, equal-time departures, completion reordering and reentrant callbacks; accepted/completed counts, moved bits, latency totals and exact-once release/callback equal. |
| Higher-layer artifacts | Operation requirements and deterministic lowering; all six GEMV profiles at M=2,N=12 and M=2,N=516. Physical trace bytes and layout data equal, including counts and phase boundaries. |
| GEMV runtime | For those twelve runs, exact command streams, controller cycles, Request/occurrence counts and chain checkpoints equal; include M=8,N=128 INT8 for both schedules to exercise multiple banks. |

Run existing tests described in audit §7, including the full directly affected
PuD location/Device/controller suites and GEMV composition/frontend cases.
Because ControllerBase/Device and command templates are shared, Phase exit
also covers DDR4/GDDR7/HBM3 conventional Device/controller, refresh and smoke
tests, plus other standards' relevant shared-controller tests. Extend scope
to timing/codegen tests if their shared machinery changed. A separate fresh
context review is warranted for shared timing publication and callback/
reentrancy changes; it is not a requirement to create another implementation
phase or spawn an agent. Any behavioral mismatch blocks Phase exit until
explained and fixed; updating expectations to the changed result is not proof.

## Phase 1 evidence — 2026-09-16

Phase 1 is complete. At its closure, G0 was accepted and G1–G7 were unresolved.
No GDDR7/HBM3 PuD registration, timing, geometry, trace format or GEMV placement
was introduced. No commit was made.

### Extraction and remaining boundaries

- Common: `PuDCommand` mechanism roles and occurrence sequencing; hierarchy-path
  `BankIdentity`; region/group/footprint operations and no-SALP conflict policy;
  ControllerBase admission, oldest-first first-fit allocation, candidate issue,
  pre-issue notification snapshots and progression. The existing Device context,
  protected records, movement acquisition, recovery ownership, accounting and
  dependency/callback lifetime remain common.
- The sole `DDR4PuDBinding` supplies command IDs, Bank-declared local numeric
  edges, LC/GB occurrence delays, channel-wide engine-pool identity, combined
  command-bus resource/occupancy, Channel-only timing publication, conventional
  closed/drained checks, terminal-occurrence + nRP recovery and profile selection.
  Existing DRAMSpec metadata and DDR4 Python calibration/shared edges remain
  authoritative. GenericDDR retains its tick arbitration and configuration.
- DDR4 profile construction, organization checks, scalar forward/inverse mapping
  and spec validation are isolated in `pud_location_ddr4.cpp`. These are still
  the sole nonvirtual resolver definitions, not an already pluggable scalar-map
  registry. Add target construction/dispatch with the first approved target
  profile after G1/G3; do not duplicate common footprint/ownership operations.
  Legacy profile organization/export fields and `rank_row_bits` naming,
  unlocated DDR4 movement diagnostics (publicly rejected), the five-coordinate
  DDR4 trace adapter and existing GEMV defaults remain compatibility boundaries.
  Target trace and GEMV consumers still wait for G5/G7.

Changed code/build/test files (27; generated standard files remain byte-identical):

| Boundary | Files, relative to repository root |
| --- | --- |
| Declarations | `python/ramulator/dram/{pud,ddr4_pud,ddr4_pud_movement}.py` |
| Placement/identity | `src/ramulator/dram/pud_location.{h,cpp}`, `pud_location_ddr4.cpp`, `pud_location_internal.h`; `src/ramulator/base/request.cpp`; `src/ramulator/controller/pud_request_validation.{h,cpp}` |
| Binding | `src/ramulator/dram/pud_binding.h`, `pud_binding_ddr4.cpp` |
| Execution | `src/ramulator/controller/pud_execution.cpp`, `controller_base.{h,cpp}`, `pud_sequence.{h,cpp}`, `impl/generic_ddr_controller.cpp`; `src/ramulator/dram/device.{h,cpp}` |
| Build lists | `src/ramulator/{controller,dram}/CMakeLists.txt` |
| Existing DDR4 adapters | `src/ramulator/frontend/impl/memory_trace/pud_trace.cpp`; `examples/pud_microbenchmark.h`; `tests/utils/{pud_location_harness.h,pud_request_harness.h,test_harness.cpp}` |

Documentation updates are this plan and the G0 decision acceptance. The source
audit remains the pre-extraction inventory at the recorded baseline HEAD.

### Reproducible local evidence

Initial production/workload sources were clean at
`093af06009f0d3e403fc9e949682ce6722a8ec3a`; the three preceding audit documents
were uncommitted additions. Branch: `feature/pud-multistandard-substrate`.
HEAD is unchanged. All builds, imports and artifacts came from this checkout,
`/workspaces/ramulator2-PuD`, its local virtual environment and local `ext/`
dependencies. CMake cache, import paths, linked-library inspection, source hashes,
fixture inputs and exact command logs are retained under ignored
`build/pud-phase1/before/`. No other checkout or historical /tmp evidence was used.

Before any production edit, `capture.py before` captured configs, 106 execution
scenarios, placement, requirements/lowering, 1,197 test observations, fourteen
GEMV runs and microbenchmarks. The read-only observer was restricted to valid
execution harnesses; recorder-path corrections were completed by
`finish_baseline.py` before freezing the baseline. Failed attempts are retained in logs/separate directories and are not result
authorities.

From the repository root:

```sh
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=python:.:build/pud-phase1
export LD_LIBRARY_PATH=.
ramulator2-venv/bin/python3 build/pud-phase1/capture.py before
ramulator2-venv/bin/python3 build/pud-phase1/finish_baseline.py
ramulator2-venv/bin/python3 build/pud-phase1/capture.py after
ramulator2-venv/bin/python3 build/pud-phase1/compare.py
```

The capture driver builds `_ramulator`, `_ramulator_test`,
`ddr4_pud_microbenchmark` and `mimdram_movement_microbenchmark` via
`cmake --build build --target ... -j 4`. Its command JSONL records full argv,
environment and GEMV call inputs; resolved JSON/YAML and physical workloads
are retained. The completion helper is only for the original pre-edit capture;
the corrected driver completes new captures itself. Do not overwrite the
frozen `before/` directory.

Frozen manifest SHA-256:
`e0d9f5890a4ac9f427e0c4975f1e39afbe15b4f4ed2b6ed86a42b272072f68fd`.
The comparison verifies every baseline artifact hash before comparing.

### Equality results

`build/pud-phase1/comparison.json`: **84 comparison units passed**, comprising
82 artifact files and both microbenchmark stdout streams; 79 files are
byte-identical. The two YAML files differ only in capture-directory prefixes.
All 1,197 test outcomes and modeled observation records match. The observer
also captured non-modeled test locals: two ephemeral TCP ports, eight final
`kind/key` values from unordered set iteration, and one asynchronously collected
GB live-trace transport `done` marker. Independent review verified these exact
differences; the comparison excludes only those bookkeeping fields, retains
exact init/ordered-event payload comparison, and changes no baseline artifact.
The transport marker is not a modeled Request completion.

The proof covers the full table above: command IDs/metadata/timings; all five
primitive streams/callbacks and RowCopy destination counts; LC/GB streams and
130/75 CK anchors; resolver inverse/nonidentity/footprints; all six pair classes,
both orders, E=1/2/8 and no-SALP; protection/recovery/accounting and reentrancy;
requirements/lowering; physical trace bytes, layout metadata, Request/command
counts, chain checkpoints and controller cycles for all fourteen GEMV workloads.

Exact controller cycles, equal before/after:

| GEMV profile | M=2,N=12 | M=2,N=516 | M=8,N=128 |
| --- | ---: | ---: | ---: |
| InterMatFirst int8 | 53,415 | 415,373 | 93,361 |
| InterMatFirst fp8-e4m3 | 201,241 | 1,071,255 | — |
| InterMatFirst fp8-e5m2 | 164,692 | 924,516 | — |
| IntraMatFirst int8 | 53,415 | 205,061 | 93,361 |
| IntraMatFirst fp8-e4m3 | 201,241 | 860,943 | — |
| IntraMatFirst fp8-e5m2 | 164,692 | 714,204 | — |

All profile names have the `MIMDRAM-` prefix in artifacts. Complete per-workload
Request/command totals are in the comparison JSON and per-workload result JSON.

### Verification and review

Work-unit checks: **480 passed** for location/request/range tests; **816 passed**
for compute/movement Device timing and GenericDDR execution after binding
extraction. These overlap; they are not additive unique-test counts.
Both full captures passed **1,197 tests** each, and both microbenchmarks passed.

Phase-exit command (same exports, with the test PYTHONPATH below):

```sh
PYTHONPATH=python:. ramulator2-venv/bin/python3 -m pytest -q \
  tests/device_timings tests/controller_scheduling tests/unit_tests tests/smoke \
  tools/pud_operation_generator/tests/test_physical_lowering.py \
  tools/pud_operation_generator/tests/test_requirements.py \
  tools/pud_gemv_generator/test_integration.py \
  --junitxml=build/pud-phase1/regressions.xml
```

**1,656 passed; 108 subtests passed**, with no failures. Collected test cases:
255 Device timing, 751 controller/refresh, 483 unit/frontend, 13 smoke,
33 physical lowering, 3 requirements and 118 GEMV composition. This includes
conventional DDR4/GDDR7/HBM3 and the other shared-controller standards.
The exhaustive arithmetic checks in the lowering suite ran only at this closure,
not after each work unit. Logs/XML and collection inventory are under
`build/pud-phase1/`.

Complete diff self-review and the requested independent fresh-context review
covered timing publication, resource scopes, completion and reentrancy. The
review identified residual selected-candidate issue/progression in GenericDDR;
it was extracted into `issue_pud_aware_candidate`, then re-reviewed as identical
to the original block apart from indentation. No blocking findings remain.
Local documentation links/anchors, new-file whitespace checks and
`git diff --check` passed.

## Common execution-model correction — before GDDR7 implementation

Entry: Phase 1 is complete and the
[common no-finite-engine decision](../decisions/pud-multistandard-substrate.md#accepted-common-execution-model--no-finite-control-engine-capacity-2026-09-16)
and reciprocal DDR4 amendments are Accepted. The user separately authorized
this correction; completion evidence is recorded below.
No engine-driven G5/G7 gate remains.

Invariant: remove artificial primitive-level finite-engine admission while
preserving every physical execution constraint. Compute and LC/GB movement
have no finite control-engine charge. Protected physical invocation ownership
continues independently of engine IDs; removing E must not remove real
serialization.

One cohesive correction, with focused work units:

1. Remove finite-E admission/pool checks from the common compute path and
   decouple protected footprint/recovery records from engine IDs. Keep
   first-fit physical eligibility, atomic ownership, priority maintenance,
   command arbitration and delayed exact-once/reentrant-safe completion.
   Inspect `pud_compute_engines` and its binding/config/test/experiment consumers:
   remove the parameter or explicitly deprecate it if compatibility requires
   retention. Do not leave a silently ignored parameter. Update generated
   configuration from its source when required.
2. Validate more than eight disjoint compute Requests admitted/progressing
   without an eight-active-Request stall, with sufficient independently modeled
   queue space. Pair this with blocking cases for footprint/mat intersection,
   same-Bank different-subarray no-SALP, Bank state, command-bus occupancy,
   timing edges, terminal PRE+nRP recovery and dependency ordering. Preserve
   each standard's actual issue resources; DDR4's single bus is not dual-bus.
3. Verify LC/GB footprint protection and occurrence dependencies, conventional
   traffic/maintenance exclusion across active and recovering regions,
   pre-ACT reservations, recovery release and callback/retry safety.
   Compare DDR4 primitive command/timing sequences under matched physical
   conditions; isolated timing must remain unchanged even though contention
   and whole-workload latency can change.

No GEMV generation, arithmetic lowering, reduction order, physical trace
schema, OPERATION identity, parent metadata or completion-join redesign belongs
in this milestone. CHAIN remains dependency ordering. Preserve independently
modeled buffers, movement acquisition, mat ownership/conflicts, no-SALP,
command timing/contention, conventional/PuD protection and delayed completion.

Phase exit: review the complete common diff, run focused tests and affected
shared controller/Device/conventional/frontend regressions, then
`git diff --check`. Shared ownership/completion changes warrant a separate
fresh-context audit. Keep Phase-1 frozen E=8 results as historical evidence;
establish a **new DDR4 execution baseline** after this intentional scheduling
correction. Reuse unchanged arithmetic/placement/sequence fixtures; never
rewrite Phase-1 expectations to claim behavior equivalence.

### Correction completion — 2026-09-16

Implemented from clean `6765dc673d32d73bd15e644ec2d8f304a4b4c35c` on
`feature/pud-multistandard-substrate`, following separate user authorization.
The Accepted modeling decision is unchanged.

The dependency audit found that `ProtectedPuD::engine`, the count/default,
pool identity binding and slot search served only finite-E admission.
Compute and movement already shared `ProtectedPuD`; movement used the
sentinel -1. Engine numbers had no physical-correctness purpose.
The shared context retains invocation identity, immutable locations/footprint
and lifecycle phase; `completion_pending` and the delayed Request's `depart`
retain terminal recovery. None of those physical lifetime fields were removed.

`protect_pending_pud_compute()` now performs oldest-first physical reservation
without an engine allocator. The binding pool API and record engine field are
gone. Physical conflict/start eligibility, command issue resources/timing,
movement acquisition, maintenance priority, real queue capacities and
terminal-PRE recovery release remain unchanged. No arithmetic, generation,
trace/CHAIN, SALP, target binding or energy behavior was changed.

`pud_compute_engines` was removed from its C++ declaration and the regenerated
Python schema. Python rejects it as unknown; raw configs explicitly reject
the key, including null values, with a removal diagnostic. This follows the
requested immediate-removal preference: no compatibility requirement justified
retaining an inert option. Example configs, microbenchmark overlap checks,
the experiment runner's config and the user guide were updated.

Validation:

- **415 focused controller cases passed** in the final regression, covering
  admission, public execution, protected lifecycle, conflicts, mat concurrency
  and resolved targets. The expanded admission module separately passed
  **87 tests**. These counts overlap.
- **1,673 tests and 108 subtests passed** in the same full Phase-exit suite
  listed above, using `--junitxml=build/pud-no-engine-regressions.xml`
  (806.79 seconds). This includes DDR4 PuD/movement, shared conventional
  controller/Device regressions, trace/frontend, GEMV generation and arithmetic
  lowering/requirements.
- Both canonical microbenchmarks passed. Full diff self-review and a separately
  authorized fresh-context read-only code/test audit found no issues. Capture
  audit findings concerning both frozen-tree checks and source/binary provenance
  were fixed and independently rechecked.
- `git diff --check` passed.

The new baseline is under ignored `build/pud-no-engine/`, with
`comparison.json`, per-case results/traces/layouts/chain CSVs, microbenchmark
configs/logs, `source.patch`, runtime/binary provenance and `sha256.json`.
Capture command executed:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. LD_LIBRARY_PATH=. \
  ramulator2-venv/bin/python3 build/pud-no-engine/capture.py
```

The driver refuses to overwrite case directories. New baseline manifest SHA-256:
`f8ec33ac76cf89a13f7c6753aa5b885f752762bc6bf24b9bbea45df8de2443e1`.
Both frozen Phase-1 `before/` and `after/` manifests and their files were verified
before and after capture; neither was modified.

All **14** previous GEMV workloads were rerun: all six profiles at M=2,N=12
and M=2,N=516, plus both int8 profiles at M=8,N=128. Every controller-cycle
value equals its entry in the Phase-1 table above (**delta 0**).
All physical/compute Request counts, command counts, arithmetic/placement
metadata and 56 generation artifacts are unchanged. Every recorded command
trace and chain-latency CSV is byte-identical too. These workloads have at most
eight outstanding Requests, so they do not exercise the removed capacity limit.
The focused disjoint-NOT test exposes the correction: the ninth Request starts
at CK9 instead of the old E=8 CK100; same-mat and no-SALP conflicts still wait
through the relevant recovery boundaries.

Focused end-to-end characterization (outside the canonical baseline suite):
M=16,N=12 with `MIMDRAM-InterMatFirst-int8` and `MIMDRAM-IntraMatFirst-int8`
each completed in **59,520 controller cycles**, with **11,648 physical Requests**,
**11,264 compute primitives** and **46,464 issued commands**. The real
PuDTrace/GEMV path reached 16 inflight Requests. Its command trace shows compute
ACTs in 16 distinct Banks at CK1–CK16, before the first terminal PRE at CK46:
all **16 compute invocations held protection simultaneously at CK16**.

Generation/arithmetic sources are byte-identical to the correction's clean
starting commit. Each generated chain matches the frozen N=12 primitive stream
after accounting only for its Bank coordinates; counts are exactly eight times
the frozen M=2,N=12 counts. The emitted physical traces produce the expected
INT8 scalar results under both existing interpreter poison patterns (0xA5/0x5A).
No comparable preserved M=16 result or old-model runtime binary was found, so
no cycle delta is reported. All Phase-1 and post-removal baseline manifests and
files were verified unchanged.

Characterization artifacts and driver are in ignored
`build/pud-no-engine-characterization/`; reproduce in a fresh output directory
with the same driver (it refuses to overwrite case directories):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. LD_LIBRARY_PATH=. \
  ramulator2-venv/bin/python3 build/pud-no-engine-characterization/characterize.py
```

Its `sha256.json` digest is
`b52c6381801931b99865de713e98f98f17c1f0415bc0ebb3c5ce4cec7f0bfa29`.
Final reruns passed **415 controller tests** and **53 INT8 frontend/generator
tests** (`build/pud-no-engine-final-focused.xml` and
`build/pud-no-engine-final-int8.xml`); the build and `git diff --check` passed.

## Phase 2 — complete GDDR7 primitive substrate binding

The [reference](../references/gddr7-pud-modeling-reference.md) contains
G1/G2/G3/G4/G6 evidence, calculations and alternatives. The
[canonical decision](../decisions/pud-multistandard-substrate.md) owns policy:
G1/G2/G3/G4/G6 are Accepted, and the common execution-model correction is
complete. The [Accepted G6 policy](../decisions/pud-multistandard-substrate.md#accepted-g6--gddr7-evaluation-baseline-preab-repair-and-rfm-policy-b-2026-09-17)
fixes the evaluation baseline, PREab repair and RFM Policy B. Phase 2 was
explicitly authorized and is complete; do not reopen Accepted choices. This plan
selects no independent timing, resource, PREab-repair or RFM policy.

Invariant: the fixed project GDDR7 evaluation baseline supports all five
compute operations plus LC/GB through directly constructed Requests with one
common ownership/completion model, including the Accepted PREab repair and
REF/RFM conflict safety. Preserve conventional GDDR7 behavior except that
Accepted timing repair. This establishes primitive behavior within the stated
fidelity limits, not vendor-calibrated timing or JESD239 completeness.

Entry: Phase 1 and the common execution-model correction complete;
G1/G2/G3/G4/G6 resolved, with explicit GDDR7 implementation authorization
received. G5/G7 and GEMV integration are not prerequisites;
use directly constructed Requests throughout this phase.
Carry forward the Accepted G3 command-resource/RCK rules.
A registerable but unsafe intermediate binding is not a phase exit.
No DDR4 numerical fallback.

Work sequence within this cohesive phase:

1. GDDR7 PuD binding/profile registration and compatibility map with provenance.
2. Compute command/timing/resource binding into existing dual-bus/RCK arbitration.
3. Recovery/shared-timing behavior, including local versus shared publication.
4. LC-MOV/GB-MOV binding with the Accepted occurrence timing and footprints.
5. The exact Accepted G6 PREab timing-definition repair.
6. REF/RFM conflict safety across active, reserved and recovering regions.
7. Direct-Request primitive and mixed-traffic tests, with focused checks during
   each work unit and complete primitive coverage at phase exit.

These work units are not independently executable phase exits. Trace-format
and GEMV integration remain later under G5/G7; no engine dependency is added.
Changed boundaries are standard declarations/generated registration,
approved profile, common binding consumers and small GDDR7 integration hooks.
Do not duplicate the controller tick or invocation state machine.

Focused tests: target capacity and compatibility-map inverse/coverage, explicit
PuD placement independent of scalar PA input, missing Rank/BG,
transaction width, group correspondence, rejected topology, independently
derived primitive timelines and one-tick-early rejection, command reception
offsets, actual bus occupancy and RCK modes, all six footprint pair classes,
no-SALP and delayed dependency completion. Reuse the common correction's
more-than-eight disjoint Request and physical-serialization tests on the
target, including both command buses. Cover PREpb/PREab,
incoming ACT/RD/WR/AP and outgoing ACT/REF recovery, including one-tick-early
rejection across Banks.
Validate G6's exact repair edges, including full RDA/WRA recovery before a
redundant PREab and one G2 reception conversion, and both RFM
target scopes with injected conflict/recovery safety probes, while asserting
zero RFM in the selected evaluation workload/maintenance traces. Plumbing
tests must not be reported as physical RFM-latency validation. Preserve
recovery of disjoint contexts.
Use directly constructed primitive Requests, including paired concurrency
cases; target hierarchy syntax under G5 and GEMV placement under G7 follow
primitive validation in Phase 4.
Regression: approved DDR4 common-milestone baseline (Phase-1 fixtures for
unchanged contracts) plus GDDR7 Device/controller/RCK/refresh/smoke; broaden
when shared code changes.

### Phase-2 completion evidence (2026-09-17)

Started from clean `feature/pud-multistandard-substrate` at
`c3e7511c98048105f85d7a8381fdf76e9728f2db`.
`GDDR7_PuD` and `MIMDRAM_GDDR7_16Gb_x8_v1` use the actual Channel/Bank
hierarchy, shared placement/ownership/occurrence machinery, and one common
controller issue/completion path. All five compute primitives and LC/GB
execute through direct Requests. The binding supplies reception-adjusted
timing, row/column resources and local recovery; conventional RCK remains
integrated. The Accepted G6 PREab repair applies to both GDDR7 registrations.

Focused work-unit checks preceded integration. Final target coverage comprises
**724 cases** across placement, compute, movement, PREab and controller tests:
all ordered primitive pairs, disjoint/intersecting footprints, different Banks,
no-SALP, more than eight invocations, buses/RCK, maintenance reservations and
recovery, exact issue boundaries and exactly-once/reentrant completion.
The broad regression run passed **2,384 tests plus 108 subtests** across
Device, controller, unit/frontend, smoke, lowering/requirements and GEMV
integration suites (`build/pud-phase2/regressions.xml`). After the audit's
compatibility adjustment, all controller tests and focused target tests passed
again: **1,492 tests** (`final-controller-and-target.xml` in the same directory).
Builds and both DDR4 microbenchmarks passed. Generation/config checks matched
all **18 standards and 61 Python files**; full diff review and `git diff --check`
passed. A fresh-context audit and its focused follow-up closed without blockers.

Audit limitation: ordinary GDDR7 `ClosedCAP(cap=1)` can strand an active Read
through a WRA upgrade. Phase 2 preserves this existing behavior rather than
importing DDR4's extra post-upgrade ordinary-close check. PuD ownership and
actual-command timing checks remain unconditional; regression tests cover
ordinary stream compatibility and PuD recovery protection. Repairing this
conventional defect is separate work.

Reproducible ignored evidence is under `build/pud-phase2/evidence-final/`:
configs, command/completion/statistic traces, source/binary/import provenance,
and SHA-256 manifests. All **14 DDR4 post-engine-removal workloads** match
`build/pud-no-engine` results and generated artifacts exactly, including command
and CHAIN CSV files. Frozen Phase-1 and no-engine manifests/artifacts were
verified before and after capture; none were overwritten. Evaluation REF traces
contain zero RFM; injected RFM safety evidence is separate and makes no physical
latency claim. The final evidence manifest SHA-256 is
`b9d381d38089a662e8b96733aa04d5db2e83fd8c7ae70899249ca0aaa3ddb65d`.

With `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. LD_LIBRARY_PATH=.`, run
`ramulator2-venv/bin/python3 build/pud-phase2/capture.py --output build/pud-phase2/replay`
using a new output directory to reproduce capture; run
`ramulator2-venv/bin/python3 build/pud-phase2/verify.py` to verify the recorded
final evidence, generated files and regression results. `final-checks.json`
records these checks. No G5/G7, trace/GEMV, CHAIN, HBM3, finite-engine or SALP
semantics changed; decisions and references remain unchanged.

## Phase 3 — complete HBM3 primitive substrate binding

Invariant: approved HBM3 placement and timing operate through the same common
substrate, retaining PC/Sid identity, dual-bus/half-cycle legality and full
maintenance protection. No synthetic Rank and no loss of PC/Sid coordinates.

Entry: Phase 1, the common execution-model correction and Phase 2 are complete.
HBM3 G1/G2/G3/G4/G6 are Accepted. Separate implementation authorization
was received for this Phase; modeling acceptance alone did not grant it.
The 2026-09-17 investigation is complete at clean source HEAD
`74b7a59210f7da85191e2066cbe95213a5a75730`; only documentation was changed.
Recover the [HBM3 reference](../references/hbm3-pud-modeling-reference.md) and
[Accepted HBM3 policy](../decisions/pud-multistandard-substrate.md#accepted--hbm3-g1g2g3g4g6-2026-09-17).
GDDR7 acceptance does not select HBM3 geometry, timings or repair policy.

Work units within this cohesive Phase, after separate implementation approval:

1. Correct shared clock-duration precision transport to preserve exact
   **312.5 ps per HBM3 half-CK tick** through serialization, runtime duration
   and reporting before using HBM3 PuD physical-time calibration. The 312-ps
   export is a truncation/reporting artifact, not the selected model. Preserve
   integer half-tick scheduling semantics and conventional command timestamps.
   Apply the Accepted G6 maintenance-recovery edges and nRREFD=13 CK correction,
   with focused conventional validation before dependent PuD timings and review
   of affected-standard regressions for shared duration consumers.
2. Add the approved HBM profile and primitive declarations/binding. Generalize
   the currently DDR4/GDDR7-only profile constructor without changing those
   profiles; reuse mixed-radix placement and complete BankIdentity.
3. Integrate common compute reservation, ACT-like HBM34 pairing and addressed-PC
   shared timing publication. Reuse HBMControllerBase's common candidate/issue
   seam and invocation-local recovery. Carry incoming conventional nRC/AP/REF
   recovery into first openings.
4. Complete LC/GB, ordinary/maintenance interaction and primitive validation
   through directly constructed Requests. Add the new AllBank PC-scope
   registration for the Accepted Open-row/AllBank-REF evaluation baseline.
   Assert zero evaluation RFM; injected RFM is only for structural safety tests.
   Automatic per-bank refresh evaluation is deferred until issue-based
   set/cooldown bookkeeping is corrected; command support alone does not
   validate that policy.

These work units are not separately executable Phase exits. Do not expose a
partially protected target. Shared dispatcher/default binding methods and
generalized placement logic currently in DDR4-named files may move while adding
the third binding where this isolates actual target validation; no filename-only
cleanup or duplicated execution machinery is needed. G5/G7 remain untouched.

Focused tests: distinguish otherwise-identical banks in different PCs/Sids;
profile footprint identity; independently calculated half-cycle timelines,
reception/terminal recovery anchors; row/column occupancy, rising/falling PRE
pairing including ACT-like PuD commands; the common no-finite-engine policy,
disjoint PuD pair classes and no-SALP; per-bank and PC-wide maintenance across Sids,
HBM34 refresh retries/set behavior, exact-once dependent completion.
Cover each approved G6 recovery edge at its exact boundary and one tick early,
late AP→per-bank maintenance, conventional ACT→PuD nRC after early AP,
cross-PC independence, canonical wildcard scopes and zero evaluation RFM.
Verify duration reporting agrees with calibration without double CK scaling.
If automatic per-bank refresh is approved, test final-set issue delay under
priority backpressure; enqueue success is not refresh completion.
Regression: DDR4 equivalence fixtures, completed GDDR7 binding cases, and
HBM3/HBM34 Device/edge/refresh/smoke tests; HBM4 tests when shared HBM34 code changes.

### Phase-3 completion evidence — 2026-09-17

Started clean on `feature/pud-multistandard-substrate` at
`29305b7d6f7b8bb9237da7625b3f14266cd85f0a`.
HBM3 now executes all five compute primitives and LC/GB movement through
direct Requests and the common occurrence/protection/completion substrate.
The accepted profile preserves Channel/PC/Sid/BG/Bank identity and local GB
topology. HBM34 handles ACT-like occupancy/pairing, Channel row/column buses
and addressed-PC publication. G6 repairs are limited to the Accepted edges
and nRREFD=13 CK. Open/AllBank evaluation produces zero RFM; injected RFM
tests establish structural safety only. Automatic per-bank REF remains deferred.

Exact 312.5-ps duration reaches configuration, runtime consumers, reporting,
binary/live trace export and viewer load/edit paths. Integer scheduling is
unchanged by duration transport. At fixed HBM3 ticks, reported elapsed time
increases by 0.160256% and throughput decreases by 0.16% relative to the old
312-ps truncation. RAM2BIN uses v1.2 float64 timing metadata only for fractional
durations; integer-duration standards retain byte-compatible v1.1. This does
not change PuDTrace or command-event timestamps. Selected HBM4/DDR4/GDDR7
durations remain unchanged.

Validation: **3,430 tests and 108 subtests passed** across Device/controller,
unit/smoke, operation lowering/requirements and GEMV integration suites,
including HBM3/HBM4 and completed DDR4/GDDR7 behavior. After the audit's
clock-export correction, **1,052 focused HBM3/export/legacy-recorder tests
passed**. Independent oracles cover primitive/LC/GB timelines, exact and
one-tick-early boundaries, pairing, all ordered footprint classes, PC/Sid
identity, no-SALP serialization, more than eight disjoint Requests, maintenance,
retry/backpressure and reentrant exact-once completion. All **14** DDR4
post-engine-removal GEMV baselines match exactly; **31** GDDR7 evidence files
are byte-identical. Both microbenchmarks pass; generation/config checks match
**19** standards and **61** generated Python files.

The separately authorized fresh-context read-only audit independently passed
1,138 HBM tests, found the clock-export gap, and closed it after reviewing the
repair and passing 19 exporter/actual-viewer/legacy tests without skips.
Full diff review, whitespace checks and prior-evidence hash verification pass.
No finite engine, SALP, G5/G7, HBM3 GEMV, CHAIN, energy or payload work was added.

Reproducible ignored evidence: `build/pud-phase3/validation-commands.json`,
`source.patch`, `changed-files.json`, `audit.md`, `manifest.sha256.json`, and
the drivers `capture.py`, `verify.py`, `closure.py`. Final captures are
`evidence-final/` (HBM3) and `prior-baseline-regression-final/` (DDR4/GDDR7),
with source/binary hashes and nested manifests. Run captures with fresh output
paths; `verify.py --final` checks the recorded final paths. Earlier Phase-1,
Phase-2 and no-engine evidence trees are unchanged; development attempts and
pre-audit captures remain separately recorded within the new Phase-3 tree.

## Phase 4 — reusable operation/GEMV integration and characterization

Investigation completed on 2026-09-17 at source HEAD
`1072848f5c3360f12caa7921cca9fb4d3aabada5`; see the
[Phase-4 evidence and alternatives](../references/pud-phase4-g5-g7-investigation.md).
G5 remains Accepted in the
[canonical decision](../decisions/pud-multistandard-substrate.md#accepted-g5--common-trace-and-global-channel-identity-2026-09-17).
G7 is re-Accepted with the final packing/fusion contract; its
[evidence and alternatives](../references/pud-phase4-g5-g7-investigation.md#11-utilization-aware-output-packing-and-request-fusion)
remain in the reference.
The user's subsequent explicit Phase-4 implementation request authorized the
implementation, validation, new target characterization and one fresh-context
read-only audit. These are complete; see the completion evidence below.
Frozen DDR4 artifacts and prior target primitive evidence remain unchanged.

Invariant: the common operation/lowering, both GEMV schedules and dependency
machinery execute the selected profiles with global Channel identity and
explicit PuD in-memory phase latency reporting. Evaluation units are one
DDR4 Channel/rank, one GDDR7 x32 device represented by four independent x8
Channel controllers, and one selected HBM3 stack represented by sixteen HBM34
controllers, each containing two PseudoChannels.

Fixed entry contracts are G5 global association/codec and per-controller
frontend admission, and G7 profile H/path, evaluation scopes, hierarchy order,
arithmetic and refresh. Do not reopen them at their first consumers.

The final G7 contract packs equal-N, contiguous Group-aligned slices only for
H <= N <= 512 and N % H == 0, with floor(512/N) outputs/mat. For N>512 retain
existing multi-mat placement without tail sharing. Synchronize members' stages
in one physical CHAIN per packed output group, preserving original suffix
restoration order and every output's residual/checkpoint identity.
Maximize compatible compute/LC fusion within a 16/32/16-mat connected path,
then stripe the fused ranges across Channels; never split a legal range only
to expose more Channels. Keep distinct LC Group pairs and singleton GB edges.
DDR4 chip paths remain separate for fusion. Row sharing changes accounting,
not arithmetic liveness. All frozen DDR4 generation stays on its legacy path;
later packed DDR4 characterization requires a separate mode/artifact identity.

Implementation work completed:

1. Establish shared immutable system association initialization across existing
   homogeneous per-Channel controllers. Validate local Channel size1 separately
   from global 1/4/16 bounds; preserve association identity, global root IDs and
   ordinary channel-compaction consistency. Check nonzero Channels, foreign
   associations, wrong roots and cross-Channel operand rejection.
2. Export profile/global bounds and implement the common versioned codec/layout
   replay, preserving legacy DDR4 trace and layout v4 bytes. Represent packed
   output membership, Group origins, residual positions and physical checkpoint
   ownership; merge shared input slices and snapshot every output at coincident
   completion events. Configure one checkpoint per physical CHAIN and derive
   output observations through metadata. Apply at most one
   ready Request admission attempt per controller per frontend tick; preserve
   CHAIN ordering/retries and deterministic same-controller arbitration.
   Static destinations are not dynamic load balancing.
3. Bind logical GEMV placement and runner configuration/reporting to the
   Accepted G7 packed output group contract and output-specific residual/
   checkpoint metadata. Form the widest legal compatible range within one
   connected path before Channel assignment; allow unused Channels when too
   few ranges exist. Count shared rows and physical Requests once while
   retaining per-output arithmetic and host work.
   Use profile H=4/8/16 and connected paths=16/32/16 mats. Preserve frozen DDR4
   order; use Channel -> Bank for GDDR7 and
   Channel -> PseudoChannel -> BankGroup -> Bank -> Sid for HBM3, followed by
   range slot, subarray and row band. One output stays within one
   Channel/Bank/subarray; preserve x duplication, sequential domains, arithmetic
   and both schedules. Keep local-row allocation common and reject excess
   capacity without padding, shuffle, cross-Channel movement or SALP.
4. Validate both schedules for all three formats and characterize isolated
   versus contended PuD in-memory phase latency and concurrency. Keep the
   runner's D=1 bound, where D counts domains belonging to one GEMV output,
   not outputs. General generator coverage includes sequential domains.

Retain DDR4 NoRefresh, use GDDR7 Open/AllBank REF + zero RFM independently per
x8 Channel controller, and retain HBM3 Accepted Open/AllBank REF + zero RFM.
Add no device-wide refresh barrier or staggering policy. Collect every
per-Channel command/statistic output; separate maintenance commands, total
issued commands and completed PuD occurrences. Sum counts, not controller
elapsed cycles. Report D * H residual values/output and host ADD work outside
PuD timing; host readout/folding and inter-domain accumulation are not timed.
Cross-target FP8 bit-exact equality is not claimed; INT8 semantics stay fixed.

Common binding defaults/dispatch and placement validation in DDR4-named files
may move only where the shared association/export consumers benefit. Preserve
all target geometry/timing and primitive evidence; no filename-only cleanup.

Focused checks cover codec/layout round trips and malformed bounds, per-controller
admission budgets (including rejection), deterministic same-controller retries,
cross-controller CHAIN completion, selected Channel/PC/BG/Bank enumeration,
capacity boundaries and D>1 placement, exact Request counts, arithmetic replay,
row/constant preservation, partial final mats and actual overlapping issues.
For the selected packed policy, additionally verify Group-aligned slice isolation,
non-divisor tails, destructive stages, range-fusion eligibility, singleton GB,
DDR4 chip-path boundaries, fusion before Channel striping (including fewer
ranges than Channels), multiple output readouts at one checkpoint, exact-once
physical completion and deterministic retries. Separate storage utilization,
Request counts, concurrency and latency; fewer Requests do not establish a
proportional speedup.
DDR4 traces, layouts, CHAIN CSVs, Request counts and all fourteen workload cycles
must remain exact. Complete Phase validation includes all three bindings,
affected conventional regressions, lowering/requirements and all six GEMV
profiles, full diff review and `git diff --check`.

Report evaluation scope, standard/organization/profile, calibration/fidelity,
the omitted finite-engine bottleneck, per-controller queues/admission rate,
tick duration, CK/CK4 interpretation and physical-time conversion. DDR4 CK,
GDDR7 CK4 and HBM3 half-CK counts are not equal time units. Keep simulation
wall time separate from PuD in-memory phase latency. No end-to-end GEMV timing,
energy or payload-simulation claim is introduced.

### Phase-4 completion evidence

Implemented from clean HEAD `fa2f8d113aaa2d00d45e2a0995d825efe4afdc88` on
`feature/pud-multistandard-substrate`, without a new modeling
decision. Shared global association/routing, versioned trace/layout, per-controller
admission, packed/fused GEMV generation and replay, and multi-controller
characterization are complete. The runner retains its D=1 bound; generator/
replay coverage includes sequential domains.

The final relevant regression suite passed **3,649 tests and 108 subtests**,
including DDR4/GDDR7/HBM3, shared HBM34/HBM4, frontend, lowering/requirements,
smoke/config/codegen and all six GEMV profiles. Focused checks include sustained
rejection fairness, packed non-divisor slices, poisoned inactive positions,
physical checkpoint ownership and multi-domain replay. All 19 generated DRAM
declarations and 61 Python files are consistent; full diff review and
`git diff --check` passed.

All fourteen frozen DDR4 workloads retain exact cycles, traces, layouts, CHAIN
CSVs, Request counts and generated artifacts. Reproduced 31 GDDR7 and 192 HBM3
primitive artifacts are byte-identical; all 1,563 files in prior evidence trees
remain unchanged.

Both new targets completed all six M=2048,N=128 configurations and six isolated
M=1,N=128 runs each, with full-output target-specific functional replay.
Observed Channel/CHAIN overlap and separate maintenance/PuD command accounting
are verified, with zero RFM. Both schedules have byte-identical physical streams
and equal timing at N=128. These are new characterization results, not frozen
performance baselines.

The one authorized fresh-context read-only audit closed with no blocking
findings. It independently verified source/binary/evidence hashes and passed
24 additional in-memory replay probes. No audit fix was required.

Ignored evidence is under `build/pud-phase4/`: `manifest.sha256.json`,
`source.patch`, `provenance.json`, `validation-index.json`, `final-checks.json`,
`audit.md`, and reproducible drivers. Current captures are
`prior-regression-final/`, `hbm3-primitive-final/` and
`characterization-final/{GDDR7,HBM3}/`; `characterization-analysis.json`
records physical time and observed overlap. Earlier development captures are
explicitly nonfinal. Decision and reference documents are unchanged.

## Handoff

Phases 1–4 and the common execution-model correction are complete.
G0 and target G1/G2/G3/G4/G6 remain fixed; G5/G7 are Accepted.
Recover the canonical decision, Phase-4 reference, current source/tests and
the completion evidence above for subsequent work. Phase-4 changes remain
uncommitted. New target characterization awaits review before any promotion
to a frozen baseline; prior frozen artifacts remain authoritative.
