# PuD multistandard substrate implementation plan

Status: Phase 1 complete on 2026-09-16; DDR4 equivalence verified.
G0 is Accepted. G1–G7 remain unresolved; target PuD implementation is not authorized.
Baseline: `093af06009f0d3e403fc9e949682ce6722a8ec3a` on
`feature/pud-multistandard-substrate`.

Recover [AGENTS.md](../../../AGENTS.md), the
[audit](../references/pud-multistandard-substrate-audit.md), its linked current
Accepted authorities, and the [Accepted architecture](../decisions/pud-multistandard-substrate.md)
before implementation. This plan authorizes no new modeling choice. G0–G7
refer to the audit's gate table; do not reconstruct current authority from
historical plans. Record acceptances at their canonical modeling boundaries.

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

Phase 1 is complete. G0 was accepted on 2026-09-16; G1–G7 remain unresolved.
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

## Phase 2 — complete GDDR7 primitive substrate binding

Invariant: an explicitly approved GDDR7 configuration supports all five
compute operations plus LC/GB with one common ownership/completion model,
and preserves the existing conventional GDDR7 behavior except separately
accepted baseline corrections.

Entry: Phase 1 complete; resolve G1/G2/G3/G4/G6 together before the target
profile/timing/issue consumers. Obtain physical geometry or explicit approval
of a hypothetical profile; approve calibration, CK4 anchoring, movement graph,
bus/command occupancy, engine scope, GDDR7 channel interpretation and PREab
gap disposition. A registerable but unsafe intermediate binding is not a
phase exit. No DDR4 numerical fallback.

Work units: (1) target profile/map and declarative binding with provenance;
(2) common PuD integration into existing GDDR7 dual-bus/RCK arbitration and
complete ordinary/maintenance recovery edges; (3) primitive and mixed-traffic
validation. Changed boundaries are standard declarations/generated registration,
approved profile, common binding consumers and small GDDR7 integration hooks.
Do not duplicate the controller tick or invocation state machine.

Focused tests: target capacity and bit-map inverse/coverage, missing Rank/BG,
transaction width, group correspondence, rejected topology, independently
derived primitive timelines and one-tick-early rejection, command reception
offsets, actual bus occupancy and RCK modes, all six footprint pair classes,
no-SALP and delayed dependency completion. Cover PREpb/PREab, AP, REFab/REFpb
and RFM commands at their real scopes; preserve recovery of disjoint contexts.
Use direct paired Requests initially, so G5 trace-format work is not forced
before primitive validation. Regression: DDR4 Phase-1 fixtures plus GDDR7
Device/controller/RCK/refresh/smoke; broaden when shared code changes.

## Phase 3 — complete HBM3 primitive substrate binding

Invariant: approved HBM3 placement and timing operate through the same common
substrate, retaining PC/Sid identity, dual-bus/half-cycle legality and full
maintenance protection. No synthetic Rank and no loss of PC/Sid coordinates.

Entry: Phase 1 complete and HBM3 G1/G2/G3/G4/G6 resolved together. Sequential
execution after Phase 2 is recommended to exercise the shared boundary on the
smaller hierarchy first; HBM3 research can precede GDDR7 completion without
committing executable semantics. Neither target's acceptance accepts the other.

Work units: (1) approved HBM profile and phase/command/tick binding;
(2) HBM34 issue integration, ACT-like pairing classification and PC/Sid shared
constraint publication; (3) primitive/ordinary/refresh integration verification.
Keep HBM34's conventional behavior. Any shared clock-precision correction is
a separately reviewed G6 change with its own affected-standard regression scope.

Focused tests: distinguish otherwise-identical banks in different PCs/Sids;
profile footprint identity; independently calculated half-cycle timelines,
reception/terminal recovery anchors; row/column occupancy, rising/falling PRE
pairing including ACT-like PuD commands; chosen engine sharing, disjoint PuD
pair classes and no-SALP; per-bank and PC-wide maintenance across Sids,
HBM34 refresh retries/set behavior, exact-once dependent completion.
Regression: DDR4 equivalence fixtures, completed GDDR7 binding cases, and
HBM3/HBM34 Device/edge/refresh/smoke tests; HBM4 tests when shared HBM34 code changes.

## Phase 4 — reusable operation/GEMV integration and characterization

Invariant: the existing arithmetic/lowering, two GEMV schedules, PuDTrace
dependency engine and experiment runner execute all three approved profiles,
with physical placement and timing units explicit in results.

Entry gates: G5 exact trace encoding/DDR4 compatibility and G7 target placement
enumeration/group ordering. Resolve them before new parser/emitter or placement
code. A changed HFF width/mat extent must pass the existing reduction graph's
alignment/partial-mat conditions; do not silently add padding, tail handling,
cross-position shuffles or a new arithmetic baseline.

Work units: (1) select/export the canonical profile and generalize physical
context parsing/emission while preserving current DDR4 trace bytes;
(2) bind GEMV bank/domain placement and runner configuration to approved
profiles; (3) run both schedules for all three formats and characterize
isolated versus contended timing/concurrency. Keep lower_to_physical and
operation requirements common, with explicit target row-capacity checks.

Focused tests: old DDR4 trace compatibility, target round-trip coordinates and
rejection of mismatched profiles, retry/fair dependency chains, exact Request
counts versus emitted streams, functional replay of each existing arithmetic
graph, row/constant preservation, partial-final-mat and capacity boundaries,
and actual overlapping issues. Cross-standard traces/counts need not equal
each other when physical mat geometry differs; symbolic arithmetic semantics
and the selected baseline graph remain fixed. DDR4 artifacts/cycles must
remain equal to Phase 1's baseline throughout refactoring.

Report standard, organization/profile, calibration/fidelity, engine/issue
configuration, native tick duration, CK/CK4 interpretation, physical-time
conversion, requests/commands and overlap. Do not compare raw HBM half-ticks,
GDDR7 CK4 and DDR4 CK as equal time units. Keep simulation wall time separate.
Final integration closure covers the three bindings, conventional regressions,
operation/lowering requirements, all six GEMV profiles, full diff review and
`git diff --check`; no energy or full-system GEMV claim is introduced.

## Handoff

Phase 1 is complete with the frozen local evidence above. GDDR7 and HBM3 remain
conventional-only. The next implementation task requires explicit authorization
and resolution of the target gates before their first consumers; G0 does not
accept G1–G7. Preserve the DDR4 baseline rather than updating expectations.
No commit, target calibration/profile, new trace/GEMV placement, new GB topology,
SALP, payload simulation, energy modeling or CACTI integration is authorized.
