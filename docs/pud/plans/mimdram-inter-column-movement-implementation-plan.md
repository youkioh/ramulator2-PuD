# Initial MIMDRAM Inter-Column Movement Implementation Plan

Status: Implementation in progress; six implementation Phases are defined.
Final Integration Closure is a separate validation activity, not a seventh
Phase.

| Milestone | Progress |
| --- | --- |
| Phase 1 | Complete and committed |
| Phase 2.A | Complete |
| Phase 2.B implementation/tests | Complete |
| Phase 2 | Complete; ready for commit |
| Phases 3–6 | Not started |

## Goal

Add the accepted initial MIMDRAM LC-MOV / GB-MOV substrate as a distinct
experimental standard derived from the completed DDR4_PuD baseline. Preserve
ordinary DDR4 and all existing DDR4_PuD behavior, keep shared changes minimal,
and implement the feature through stable Phase invariants that can each contain
multiple context-sized Codex work units.

This plan is an implementation handoff, not movement architecture authority.
One Phase normally produces one user-reviewed commit. A work unit or fresh
Codex chat is not automatically a Phase, Decision Gate, audit, or commit.

## Authority / required reading

Before implementing a work unit, read these sources in order:

1. `AGENTS.md`.
2. `docs/pud/references/mimdram-inter-column-data-movement.md`.
3. `docs/pud/adding-pud-primitives.md`.
4. The four current canonical Accepted movement decisions:
   - `docs/pud/decisions/mimdram-substrate-and-movement-request-boundary.md`;
   - `docs/pud/decisions/mimdram-movement-addressing-geometry-and-payload.md`;
   - `docs/pud/decisions/mimdram-movement-execution-ownership-and-device.md`;
   - `docs/pud/decisions/mimdram-movement-timing-and-resource-model.md`.
5. This plan and the current source/tests named by the active work unit.

The four canonical decisions are the complete current movement-design
authority. Do not reconstruct current semantics from Superseded MIMDRAM
decisions unless a concrete provenance question cannot be answered from current
authority. The completed DDR4_PuD plan is workflow history only.

## Scope

- A separate combined standard derived from DDR4_PuD, with inherited RowCopy,
  MAJ3, MAJ5, and NOT behavior unchanged.
- LC-MOV and GB-MOV request representation, routing, validation, payload width,
  command/state behavior, Device timing, controller sequencing, ownership,
  primitive-local timing, lifecycle, supported maintenance/policy/plugin/trace
  behavior, and statistics.
- Minimal shared request, configuration, controller, scheduler, Device, refresh,
  and observability changes required by those semantics.
- Generated registration/build integration and test-only harness observability.
- Directed movement tests and DDR4, DDR4_PuD, GenericDDR, and unrelated-standard
  regressions proportionate to each shared change.

## Non-goals

- Changing ordinary DDR4 or inherited DDR4_PuD primitive semantics.
- Same-Bank disjoint-mat MIMD, per-mat state or scoreboards, multiple movement
  owners in one Bank, or finer-grained ownership/timing resources.
- T1/T2 mat transport, an explicit mat queue, transport queue pressure, or
  transport-specific command-bus contention; the initial model remains T3.
- Wider, reverse, cross-chip, non-neighbor, automatically multi-hop GB-MOV, or
  physical movement-Column mapping.
- Functional data values, HFF/global-SA contents, array placement, `bbop_mov`
  lowering, vector-reduction orchestration, or a new public frontend.
- New movement `tRRD`, `tFAW`, activation-current, ordinary same-Bank `nRC`,
  external DQ/CAS/turnaround, or undocumented Rank/Channel timing.
- Movement energy. It is outside this implementation milestone and belongs to
  separate accepted PuD-energy authority/work. No movement energy values or
  model are invented here.
- Unrelated refactoring or documentation cleanup.

## Authority crosswalk

| Implementation area | Canonical authority |
| --- | --- |
| Combined-standard boundary, inherited behavior, request identity, one-invocation request lifecycle | `mimdram-substrate-and-movement-request-boundary.md` |
| Ordered operands, derived subarray, logical mats, LC/GB placement, Columns, HFF width, exact bits, `size_bytes` | `mimdram-movement-addressing-geometry-and-payload.md` |
| Occurrence sequences, semantic commands, controller ownership, Device states/actions, PRE/refresh legality | `mimdram-movement-execution-ownership-and-device.md` |
| T3 scope, timing-domain split, directed constraints, numeric cycles, recovery, intentional timing omissions | `mimdram-movement-timing-and-resource-model.md` |
| Reusable implementation/testing method only | `docs/pud/adding-pud-primitives.md` |

If this plan conflicts with a canonical Accepted decision, the decision wins
and implementation stops until the plan is corrected.

## Exact implementation contracts retained by this plan

These compact contracts are repeated here because implementation and tests use
them directly. Their rationale remains in the canonical decisions.

### Requests, placement, and payload

- LC-MOV and GB-MOV each have exactly two ordered `AddrVec_t` operands: source
  at index 0 and destination at index 1.
- Logical-mat metadata and primitive occurrence history are copy-safe
  request/controller state, not hierarchy coordinates or Device Bank state.
- The hierarchy remains `[Channel, Rank, BankGroup, Bank, Row, Column]`.
- `rows_per_subarray=1024`; `subarray_id=row/1024`; the selected 64K-row Bank
  organization therefore has 64 derived subarrays. There are 128 logical mats
  per accepted Channel/Rank/BankGroup/Bank/derived-subarray context; logical
  chip is `id >> 4` and local logical mat is `id & 0xF`.
- LC uses one nonempty inclusive logical range common to both operands. Both
  operands share Channel, Rank, BankGroup, Bank, and derived subarray. The range
  may cross logical-chip IDs and executes in lockstep. Source and destination
  Row and Column values may differ.
- Initial GB uses singleton endpoints in one logical chip with destination
  local mat exactly source local mat plus one (`i-1 -> i`). Reverse,
  non-neighbor, wrapping, wider, cross-chip, cross-subarray, and cross-Bank
  requests are rejected.
- Movement Columns are opaque selectors checked only against the configured
  Column bound. Equality, difference, values above 127, and lack of HFF/byte
  alignment carry no extra semantics.
- `hffs_per_mat` is typed combined-standard/device configuration, initially 4.
  LC moved bits are selected-mat count times `hffs_per_mat`; singleton GB moved
  bits are `hffs_per_mat`. The result is derived, not stored in Request.
- Movement `size_bytes` is the explicit N/A sentinel `-1`; other movement sizes
  are rejected. Movement contributes nothing to ordinary byte throughput.

### Occurrences, states, and ownership

```text
LC: ACT_MOV(src) -> RD_MOV(src) -> PREpb
    -> ACT_MOV(dst) -> WR_MOV(dst) -> PREpb

GB: ACT_MOV(src) -> ACT_MOV(dst) -> RD_MOV(src)
    -> WR_MOV(dst) -> PREpb
```

`ACT_MOV`, `RD_MOV`, and `WR_MOV` are shared semantic command identities across
primitive and operand roles. `PREpb` remains shared.

```text
LC Device state:
Closed
-> ACT_MOV -> MovementActive
-> RD_MOV  -> MovementDataValid
-> PREpb   -> MovementDataValid
-> ACT_MOV -> MovementDataValid
-> WR_MOV  -> MovementActive
-> PREpb   -> Closed

GB Device state:
Closed
-> ACT_MOV -> MovementActive
-> ACT_MOV -> MovementActive
-> RD_MOV  -> MovementDataValid
-> WR_MOV  -> MovementActive
-> PREpb   -> Closed
```

Movement never populates `m_row_state`. The retained request is sequence and
ownership authority. Ownership begins when the first `ACT_MOV` issues, not
while pending or at a preparatory `PREpb`, and ends when terminal `PREpb`
issues. Every independent candidate whose complete scope intersects the owned
Bank is rejected before prerequisite resolution. Different Banks may progress
when otherwise ready.

### Timing and refresh

Primitive-local dependencies:

| Primitive | Edge | Delay |
| --- | --- | ---: |
| LC | occurrence 0 source ACT_MOV -> occurrence 1 RD_MOV | `nRCD=16` |
| LC | occurrence 1 RD_MOV -> occurrence 2 source PREpb | `nRTP=9` |
| LC | occurrence 4 WR_MOV -> occurrence 5 terminal PREpb | `nRELOC+nWR=20` |
| GB | occurrence 0 source ACT_MOV -> occurrence 2 RD_MOV | `nRAS=39` |
| GB | occurrence 2 RD_MOV -> occurrence 3 WR_MOV | `nRELOC=2` |
| GB | occurrence 3 WR_MOV -> occurrence 4 terminal PREpb | `nWR=18` |

Context-independent Device relationships include latest target-Bank
`ACT_MOV -> PREpb = nRAS`, latest `ACT_MOV -> WR_MOV = nRAS`, and
`PREpb -> ACT_MOV = nRP`. Recovery into the first ACT_MOV is
`PREab -> ACT_MOV = nRP`, `RDA -> ACT_MOV = nRTP+nRP`,
`WRA -> ACT_MOV = nCWL+nBL+nWR+nRP`, and `REFab -> ACT_MOV = nRFC`.
Terminal PREpb imposes `nRP` before ordinary ACT, inherited PuD opening,
another ACT_MOV, or REFab as applicable.

At DDR4_2400R with accepted `nRELOC=2`, isolated issue/recovery cycles are:

```text
LC issues: 0, 16, 39, 55, 94, 114; recovery complete: 130
GB issues: 0,  1, 39, 41, 59;      recovery complete: 75
```

There are no timing aliases and no initial movement `tRRD`, `tFAW`, same-Bank
`nRC`, external-DQ, or extra Rank/Channel rules. GenericDDR F-A refresh policy
is retained: queued refresh blocks movement start; refresh arriving during
ownership waits; no deadline-aware admission, bypass, pause, or resume is
added; terminal `PREpb -> REFab` respects `nRP`.

## Current-code and shared-change inventory

| Current limitation / required shared change | Owning Phase | Baseline risk and required evidence |
| --- | ---: | --- |
| Four contiguous PuD request IDs and arithmetic statistic slots | 1 | Preserve IDs/names and DDR4_PuD counts; DDR4 still rejects PuD/movement |
| Capability checks recognize only RowCopy/MAJ3/MAJ5/NOT | 1, 4 | Do not expose LC/GB on DDR4_PuD; combined capability ultimately requires all six mappings |
| No typed `hffs_per_mat`; combined standard/registration absent | 1 | Cross-standard config serialization, mutable-definition isolation, codegen/smoke |
| AllBankRefresh has standard-name coupling | 1 | Preserve existing DDR/HBM scope selection while registering the combined name |
| Generic ingress rejects all non-positive sizes and lacks movement metadata routing | 2 | Preserve Read/Write and legacy PuD size/routing semantics |
| Request lacks logical-mat metadata and occurrence history | 2, 4 | Copy/promotion correctness; no Device/hierarchy leakage |
| Generated commands and Device movement states/actions do not exist | 3 | Combined-only registration; DDR4/DDR4_PuD definitions unchanged |
| Shared PREpb, PREab, and REFab are not movement-aware | 3 | Full conventional/PuD Device state and refresh regression |
| GenericDDR sequencing is hard-coded for four inherited primitives | 4 | Preserve every legacy sequence, operand role, and lifecycle |
| Device-only timing readiness is used by schedulers and final issue lacks a complete recheck | 5 | Preserve FRFCFS/FRFCFS-RowHit and unrelated controller semantics |
| Row policy/plugins may interpret generic command metadata or inject conflicting work | 3, 6 | Resolve metadata policy early; enforce supported configurations before use |
| Movement traces and exact-bit/lifecycle statistics are absent | 6 | Avoid schema churn unless Gate F requires it; preserve all legacy statistic names and throughput |

No generic Mat hierarchy, owner table, scoreboard, transport queue, or energy
interface is justified by the initial substrate.

## Operational boundary model

- Implementation Phases: **6**.
- Final Integration Closure: separate validation activity, not a Phase.
- Expected Phase commits: **6**, one after each completed Phase; Phase 6 is
  accepted only after Final Integration Closure.
- Logical work units: approximately **13–15**.
- Fresh Codex chats: approximately **8–12**, depending on context and debugging.
- Independent audits: Phase 5 only by default.

These are guidance, not quotas. Keep a cohesive Phase intact and use another
work unit/chat when context pressure grows.

## Phase dependency overview

```text
1. Extension-safe foundations and combined-standard boundary
  -> 2. Movement request contract and validation
  -> 3. Device movement substrate [Gates C/D/E]
  -> 4. Controller movement execution, lifecycle, and ownership [Gate A]
  -> 5. Primitive-local timing and shared readiness integration
  -> 6. Supported integration, observability, and accounting [Gates F/B]
  -> Final Integration Closure
```

Phase 4 does not enable executable LC/GB mappings until sequence, ownership,
and Gate A lifecycle handling all exist. Phase 5 remains separate because its
shared scheduler/readiness risk is materially broader than controller sequence
execution.

## Decision Gate and implementation-choice map

Resolve a Gate with the user immediately before its first code consumer. If an
accepted result refines existing modeling authority, update the appropriate
canonical decision under `AGENTS.md`; do not automatically create a new file.

| Item | Owning work unit | Exact first consumer | Treatment |
| --- | --- | --- | --- |
| Gate C: movement `is_opening`/`is_accessing`/`is_closing` and `BankTarget` | 3.A | Final movement command metadata in Python/generated handlers | Resolve together with D/E before encoding metadata |
| Gate D: row-policy interpretation/protection | 3.A | The same command metadata, later consumed by controller row-policy callbacks/upgrades | Decide safe interpretation in 3.A; enforce/test in 6.A |
| Gate E: plugin observe/ignore/reject compatibility | 3.A | The same metadata and eventual unconditional issue notifications | Decide supported compatibility in 3.A; enforce/test in 6.B |
| Gate A: terminal PRE issue/recovery versus depart/callback boundary | 4.C | Movement retirement/completion code and enabling executable mappings | Resolve immediately before 4.C; do not decide statistics here |
| Gate F: trace observability and any schema change | 6.C | First production trace/schema-dependent edit | Resolve immediately before 6.C |
| Gate B: movement accepted/completed, latency, and moved-bit statistics | 6.D | First movement-specific statistic registration, storage, or update | Resolve immediately before 6.D, using Gate A as fixed input; do not reopen lifecycle |
| Combined-standard name | 1.B | Python class/module, generated C++, CMake, tests, AllBankRefresh | Implementation choice; present briefly and confirm if useful, but no Decision Gate by default |
| Movement energy | None | No consumer in this milestone | Explicit Non-goal; future work requires separate accepted authority |

Phase 1 may make statistic lookup/storage sparse-safe but must remain
movement-statistics-neutral. It must not register movement counters or make a
choice reserved for Gate B.

## Shared risk-tiered testing and review policy

### Work-unit check

After each focused work unit:

- run the smallest new directed tests;
- run regressions directly affected by that unit;
- run codegen/build only when relevant;
- inspect the local diff and abstraction boundaries.

A work-unit check is not a commit boundary. Do not run the most expensive
matrix after every work unit.

### Phase-exit check

For every Phase:

1. Review the complete Phase diff, including generated and test-only files.
2. Verify every generic/shared change is necessary and remains local to the
   responsibility that requires it.
3. Run the Phase-level regression subset below and investigate behavioral—not
   merely compilation—failures.
4. Run `git diff --check`.
5. Stop for user review and one Phase commit; Codex does not create the commit.

### Expected Phase-exit escalation

| Phase | Required regression level |
| ---: | --- |
| 1 | DDR4/DDR4_PuD ingress, legacy statistics, configuration, smoke, mutable-definition isolation, and refresh-scope users |
| 2 | Movement request/validation plus ordinary Read/Write and legacy PuD ingress/routing regressions |
| 3 | Full relevant DDR4 and DDR4_PuD Device state/timing/refresh regressions because shared PRE/refresh handlers change |
| 4 | Full GenericDDR movement and legacy PuD sequence/lifecycle/priority/mixed-completion/callback/reentrancy regressions |
| 5 | Full controller-scheduling suite plus unrelated GDDR/HBM users of shared scheduler/readiness paths |
| 6 | Row-policy/plugin/refresh/trace/statistics suites; do not automatically repeat all Phase 5 scheduler tests unless readiness code changed |

### Independent audit policy

After normal Phase 5 implementation, self-review, and tests, use one separate
fresh-context audit before accepting its commit. The audit must inspect the
complete readiness/scheduler diff, all callers, FRFCFS-RowHit pass semantics,
priority behavior, final pre-issue validation, and unrelated-standard evidence.
The extra audit is justified because the shared multi-pass scheduler contract
can regress standards that do not use movement.

No other Phase automatically receives an independent audit. Add one only if
the actual diff develops comparable unanticipated cross-cutting risk.

## Phase 1 — Extension-safe foundations and combined-standard boundary

### Stable invariant

Shared request/capability/configuration infrastructure can represent movement
safely, and an isolated combined standard builds and remains
behavior-equivalent to DDR4_PuD before movement execution is added.

### Work unit 1.A — Request classification and capability foundations

Code areas likely include:

- `src/ramulator/base/request.h` and `request.cpp`;
- `generic_dram_system.cpp`;
- `controller_base.h/.cpp`;
- `generic_ddr_controller.cpp`;
- focused request/stat/capability tests and test harness exposure.

Intended changes:

- Reserve explicit stable LC-MOV and GB-MOV request IDs after the existing IDs;
  keep Read/Write at 0/1 and RowCopy/MAJ3/MAJ5/NOT at 2–5.
- Replace range/arithmetic assumptions with explicit classification for
  inherited PuD operations, movement operations, their union, and operations
  with defined legacy statistics.
- Centralize request names and optional statistic-slot lookup so sparse or
  future non-contiguous IDs fail safely.
- Generalize fixed-width storage/reset/average loops only enough to remove the
  four-slot hazard. Continue registering and updating only the four existing
  DDR4_PuD statistic families; make no Gate B decision.
- Add reusable capability queries for controller-sequenced operations,
  inherited PuD support, and eventual movement support. Do not infer LC/GB
  capability from the inherited four requests.
- Preserve all existing DDR4_PuD buffer names, statistics names, and values.

Work-unit tests:

- type/name/classification and invalid/sparse-safe lookup;
- Python/C++ request-ID ordering consistency;
- plain DDR4 rejects all PuD/movement IDs;
- DDR4_PuD supports exactly its inherited four and rejects LC/GB;
- existing PuD ingress/lifecycle/statistics tests remain unchanged.

### Work unit 1.B — Combined-standard skeleton and typed configuration

Choose the exact class/module/generated/registration name at the beginning of
this work unit as an implementation choice. The name must identify a combined
DDR4_PuD-derived movement experiment without claiming full MIMDRAM support.

Code areas likely include:

- a new Python standard module and generated C++ standard;
- `python/ramulator/dram/spec.py` and codegen only as required;
- `dram_spec.h/.cpp`, DRAM CMake/export registration;
- `all_bank.cpp`;
- smoke, configuration, isolation, and refresh-scope tests.

Intended changes:

- Derive from DDR4_PuD and independently copy every inherited mutable
  definition: levels, commands, states, timing parameters/constraints,
  supported requests, command cycles, bus lists, organizations, presets, and
  geometry.
- Keep the skeleton behavior-equivalent to DDR4_PuD. Do not yet add movement
  request mappings, commands, states, or timing.
- Add the narrowest typed `hffs_per_mat` configuration path. The combined
  standard defaults to 4, accepts positive overrides, and rejects missing or
  non-positive values when movement capability requires the field.
- Keep the field absent/unsupported for DDR4 and DDR4_PuD. It is not a
  hierarchy level, transaction byte width, Column bound, or request field.
- Register the combined standard through normal codegen/build paths; never
  hand-edit generated output.
- Extend the existing AllBankRefresh name/scope handling minimally so the new
  standard uses the inherited Rank scope. Avoid an unrelated metadata refactor.
- Add no movement energy field, counter, or value.

Work-unit tests:

- construction, import, codegen, build, and registration smoke;
- ordinary and inherited-PuD behavior equivalence with DDR4_PuD;
- three-way mutable-definition isolation across DDR4, DDR4_PuD, and combined;
- HFF default 4, positive override, zero/negative rejection, and absence on
  non-movement standards;
- combined AllBankRefresh construction/scope plus existing DDR/HBM scope tests.

### Phase completion criteria

- No production logic indexes all PuD request types by a four-contiguous-ID
  assumption.
- The combined skeleton builds and runs inherited behavior without advertising
  movement execution.
- DDR4 and DDR4_PuD definitions, behavior, and public statistics are unchanged.
- Typed HFF configuration and refresh registration are localized and tested.
- Phase 1 exit review and regressions pass.

### Risks

- Numeric request-ID or public statistic drift.
- Accidentally exposing LC/GB on DDR4_PuD.
- Mutable Python class data aliasing into the baseline.
- Generated registration/config mismatches.
- Letting generic statistic cleanup prematurely decide Gate B.

## Phase 2 — Movement request contract and validation

### Stable invariant

Every LC/GB request is complete, copy-safe, routable, structurally valid,
placement-valid, width-valid, and deterministically accepted or rejected while
movement execution remains disabled.

### Work unit 2.A — Request metadata, size contract, and ingress routing

Code areas likely include Request, PuD routing helpers, GenericDRAMSystem,
GenericDDR validation entry points, and controller/memory-system harnesses.

Intended changes:

- Add a named N/A `size_bytes=-1` contract and a request-type-aware predicate.
  Preserve the existing internal direct-command use of `-1` without conflating
  it with an external movement request.
- Add copy-safe typed movement metadata representing LC's inclusive common
  range and GB's singleton source/destination endpoints. Avoid loose fields
  whose relationships are only implicit.
- Require exactly two ordered operands and all required metadata at generic
  ingress. Validate every Channel coordinate, route by operand 0, and require
  both operands on the same Channel.
- Make size validation type-aware: movement accepts exactly the N/A sentinel;
  Read/Write and existing PuD requests retain their positive, at-most-one-
  transaction behavior.
- Keep LC/GB mappings disabled in the combined standard.

Work-unit tests cover both request types, exact operand count, missing/malformed
metadata, copy/retry behavior, same/mixed Channel routing, every invalid size,
legacy sizes, and continued DDR4/DDR4_PuD rejection.

### Work unit 2.B — Placement, selector, and exact-bit validation

Intended changes:

- Reuse hierarchy shape/bounds and derived-subarray checks without changing
  current RowCopy/MAJ3/MAJ5/NOT placement behavior.
- LC requires logical bounds `0..127`, a nonempty ordered inclusive range,
  identical source/destination selection, and one shared
  Channel/Rank/BankGroup/Bank/derived-subarray context.
- GB requires singleton selections, one shared context and logical chip, and
  destination local mat exactly source local mat plus one. Reject reverse,
  non-neighbor, wrap, cross-chip, wider, cross-subarray, and cross-Bank cases.
- Validate movement Columns only against the configured hierarchy bound.
  Accept 0 and 1023 for the current organization, equal or unequal selectors,
  and structurally valid values above 127; add no alignment or arithmetic rule.
- Add one production helper returning a sufficiently wide exact moved-bit
  value from validated metadata and typed HFF width. Do not duplicate the value
  in Request or convert it to bytes.

Work-unit tests cover hierarchy/address shape and bounds; all shared/mismatched
placement coordinates; LC singleton/multi-mat/chip-crossing ranges; every GB
direction/neighbor/chip restriction; Column boundary and opacity cases;
`hffs_per_mat=4` and positive overrides; LC `N*HFF` and GB one-HFF payload.

### Phase completion criteria

- Every accepted request, placement, selector, size, and payload rule has a
  deterministic directed accept/reject test.
- Source/destination order and logical metadata remain request/controller facts.
- No movement command can issue and no movement statistic is registered.
- Shared ingress changes preserve ordinary and inherited-PuD behavior.

### Risks

- Sentinel leakage into legacy request behavior.
- Metadata loss across Request copies or backpressure retry.
- Off-by-one LC widths or double-counted GB endpoints.
- Treating logical mats or Columns as physical hierarchy coordinates.

## Phase 3 — Device movement substrate

### Stable invariant

The combined standard has a complete Device-layer movement model: semantic
commands, aggregate states/actions, PRE behavior, defensive maintenance
legality, and all accepted context-independent Device timing.

### Decision session C/D/E — before work unit 3.A

Resolve together before final command metadata is encoded:

- **Gate C:** `is_opening`, `is_accessing`, `is_closing`, and `BankTarget` for
  ACT_MOV/RD_MOV/WR_MOV and shared PRE behavior.
- **Gate D:** how those choices prevent movement from being upgraded,
  autoprecharged, counted as an ordinary row-buffer access, or closed by row
  policy.
- **Gate E:** which observational, exact-ID, metadata-driven RowHammer, and
  behavior-changing plugins may observe, ignore, or reject movement.

The session must define enough compatibility policy to choose safe metadata.
Phase 6 implements detailed setup/runtime enforcement and configuration tests.
Do not select metadata merely to reuse a controller branch. Record accepted
refinements in the appropriate canonical decision when required.

### Work unit 3.A — Commands, states, actions, and defensive legality

Code areas likely include new movement command headers, combined Python/
generated definitions, shared PREpb/PREab/REFab handlers, DRAM CMake, and
Device-state harness/tests.

Intended changes:

- Add exactly one combined-standard command identity each for `ACT_MOV`,
  `RD_MOV`, and `WR_MOV`, plus exactly `MovementActive` and
  `MovementDataValid` states. Add no role/type/timing aliases.
- Apply accepted C/D/E metadata and a single-Bank target without encoding
  request role or cursor in Device command metadata.
- Implement `ACT_MOV`: Closed first activation becomes MovementActive with no
  row entry; later activation preserves MovementActive or MovementDataValid as
  appropriate. Opened before acquisition yields ordinary PREpb prerequisite;
  inherited PuD intermediate states are illegal.
- Implement `RD_MOV` only from MovementActive, producing MovementDataValid.
- Implement `WR_MOV` only from MovementDataValid, producing MovementActive.
- Make shared PREpb state-dependent only for standards defining movement:
  MovementDataValid remains MovementDataValid; MovementActive becomes Closed
  and defensively clears row state. Preserve every conventional/inherited path.
- Make PREab and REFab reject intersecting movement states before any partial
  all-Bank mutation. They must not synthesize a repair/reset sequence.
- Verify ordinary ACT/RD/WR/RDA/WRA and inherited PuD handlers reject movement
  states; add focused diagnostics only where default handling is ambiguous.
- Add only test-harness state/row-state observability, not production
  introspection for tests.

Work-unit tests reproduce both exact state traces, verify empty movement row
state throughout, source-PRE retention, terminal cleanup, preparatory PRE from
Opened, malformed direct transitions, ordinary/inherited-command rejection,
and non-mutating PREab/REFab failure.

### Work unit 3.B — Context-independent Device timing

Intended changes:

- Add `nRELOC=2` to the combined DDR4_2400R timing preset for controller use.
- Add latest-ACT Bank edges `ACT_MOV -> PREpb=nRAS` and
  `ACT_MOV -> WR_MOV=nRAS`, history window 1, plus `PREpb -> ACT_MOV=nRP`.
- Add inherited PREab/RDA/WRA/REFab recovery into ACT_MOV and verify terminal
  PREpb recovery into ordinary ACT, inherited PuD opening, ACT_MOV, and REFab.
- Add only missing edges; do not duplicate constraints already inherited.
- Do not encode occurrence-role dependencies here. Add no timing aliases,
  ordinary ACT nRRD/nFAW membership, ACT_MOV-to-ACT_MOV nRC, external-DQ
  membership, or extra cross-Bank/Rank/Channel constraints.

Work-unit tests check each new edge at `delay-1` and `delay`, latest-ACT
selection, recovery predecessors/followers, same-Bank blocking, different-Bank
locality, successive GB ACT command availability, and deliberate exclusion
from ordinary activation-current/DQ groups.

### Phase completion criteria

- Device-only tests reproduce the accepted LC/GB states and every accepted
  context-independent timing/recovery edge.
- Shared PRE/refresh changes are conditional/localized and preserve DDR4 and
  DDR4_PuD behavior under their full relevant Device regressions.
- Primitive-local dependencies remain absent from Device timing.
- Movement request mappings remain disabled.

### Risks

- Shared PRE changes affecting all standards.
- Partial PREab mutation before detecting movement.
- Command metadata silently determining later policy/plugin behavior.
- Duplicated or mis-scoped timing constraints.
- Device state becoming a second request cursor.

## Phase 4 — Controller movement execution, lifecycle, and ownership

### Stable invariant

LC/GB execute their exact occurrence sequences using one retained controller
context under the complete accepted Bank ownership model, with correct
lifecycle boundaries, arbitration, callback behavior, and occurrence history.

No Phase boundary may expose executable movement without this ownership model.
Primitive-local timing remains the separately testable Phase 5 responsibility;
Phase 4 sequence tests do not claim final isolated cycles.

### Work unit 4.A — Occurrence descriptors and retained sequence context

Code areas likely include Request sequence fields, GenericDDR sequence helpers,
combined request mappings held disabled until 4.C, and controller harnesses.

Intended changes:

- Generalize DDR4_PuD-specific cursor terminology only where necessary while
  preserving the four inherited sequences unchanged.
- Add request-owned occurrence issue history initialized to not-issued and
  preserved across queue copies/promotion. Size it to the architectural
  occurrence list rather than an arbitrary maximum.
- Localize sequence description behind a controller helper/descriptor that
  returns semantic command, operand index/retained PRE address, occurrence
  role/index, and terminal status.
- Encode the exact LC and GB occurrence/address lists. Both GB activations use
  `ACT_MOV`; source/destination/type are roles, not command IDs.
- Advance cursor and record history only when the intended final command
  issues. Preparatory prerequisites do neither.
- Preserve all RowCopy/MAJ3/MAJ5/NOT command lists, operand addressing, and
  cursor behavior.

Work-unit tests verify exact identities/addresses without final timing claims,
shared IDs across roles, copy/promotion history retention, preparatory PRE not
advancing the cursor, and unchanged inherited sequences.

### Work unit 4.B — Bank ownership and mixed arbitration

Intended changes:

- Use the retained active movement request as the Bank owner; add no owner map.
- Acquire atomically only when occurrence 0 `ACT_MOV` issues. Pending movement
  and preparatory PREpb own nothing.
- Release when terminal PREpb issues, independently of any later Gate A
  departure/callback.
- Before prerequisite resolution, reject every independent candidate whose
  complete `BankTarget` scope intersects an owner: Read/Write, LC/GB, inherited
  PuD, priority PRE/refresh/maintenance, row-policy, and plugin work.
- After ownership acquisition, only the owner's next intended architectural
  occurrence remains eligible in the owned Bank; an incompatible movement state
  is an error and must not be repaired by synthesizing, skipping, or reordering
  prerequisites.
  Allow different-Bank work under existing timing/arbitration. The initial
  model has at most one retained movement owner per flat Bank, while different
  Banks may each have an independent retained owner.
- Preserve active > FIFO priority head > oldest-ready pending PuD/Read/Write
  behavior, deterministic ties, and blocked priority-head semantics. Add no
  movement-specific precedence or bypass.
- If unrelated work reopens a Bank before acquisition, let the pending
  movement resolve another preparatory PREpb.

Work-unit tests cover pending/preparatory non-ownership, first-ACT acquisition,
all same-Bank interrupter classes, different-Bank progress, complete-scope
intersection, terminal-PRE release, priority blocking, oldest-ready ties, and
legacy PuD ownership.

### Gate A and work unit 4.C — Lifecycle and executable capability

Immediately before lifecycle code, decide separately:

- terminal PREpb issue and ownership/state cleanup;
- terminal `nRP` recovery completion;
- request `depart` timestamp;
- callback invocation.

Gate A must not decide movement counters, statistic registration, latency
names, or moved-bit accounting. Those remain Gate B in Phase 6. It must only
provide lifecycle facts that Gate B later consumes. Preserve existing
DDR4_PuD lifecycle unless the accepted answer explicitly applies more broadly.

Then:

- implement the chosen movement retirement/depart/callback boundary;
- preserve remove/extract-before-callback reentrancy safety and departure-time-
  independent completion scanning;
- enable LC/GB as controller-sequenced only after sequence and ownership logic
  are complete;
- make combined capability require both movement operations plus the inherited
  four mappings;
- retain ownership release at terminal PRE issue even if departure is later;
- add no provisional movement statistic semantics.

Work-unit tests distinguish terminal issue, recovery, release, depart, and
callback; verify callback exactly once, mixed departure ordering, reentrant
submission, mapping/capability boundaries, and that DDR4_PuD lacks movement.

### Phase completion criteria

- The combined standard executes exact LC/GB occurrence/address sequences with
  continuous ownership from first ACT through terminal PRE.
- No same-Bank independent work interrupts; different Banks progress normally.
- Gate A is recorded where required and lifecycle/callback behavior is exact.
- Existing PuD sequences, ownership, arbitration, lifecycle, and statistics are
  unchanged.
- No movement statistic has been defined or registered.

### Risks

- Enabling mappings before ownership is complete.
- Pointer/reference identity errors after promotion.
- Recording a prerequisite as an occurrence or acquiring at preparatory PRE.
- Priority deadlock, unintended bypass, or overblocking other Banks.
- Callback/container reentrancy or departure-order regressions.

## Phase 5 — Primitive-local timing and shared readiness integration

### Stable invariant

Scheduler candidate comparison and final issue validation use one complete
readiness contract, preserve existing scheduler semantics for unrelated
requests/standards, reproduce exact LC/GB cycles, and do not block unrelated
Banks during primitive-local timing gaps.

This is the highest shared-code-risk Phase.

### Work unit 5.A — Primitive-local timing and composite readiness

Code areas likely include ControllerBase readiness, GenericDDR movement timing,
Request occurrence history, scheduler interfaces, and timing harnesses.

Intended changes:

- Add one request-aware controller readiness query whose default for all other
  requests/controllers is exactly Device `check_timing(command,address)`.
- Have GenericDDR combine Device readiness with the six accepted occurrence-
  specific dependencies listed near the front of this plan.
- Key local dependencies by primitive and occurrence index so GB RD uses source
  ACT occurrence 0 after destination ACT occurrence 1 becomes latest in Device
  history.
- Keep local checks pure: no cursor/history mutation and no controller/Channel
  reservation during a local gap.
- Do not duplicate Device nRAS/nRP/recovery edges in the local table.

Work-unit tests isolate every local edge at predecessor+delay-1 and the exact
boundary, distinguish local blocking from Device blocking, verify GB source-ACT
selection, and show different-Bank work can issue during local gaps.

### Work unit 5.B — Scheduler and final-issue integration

Prefer a fresh Codex chat before this work unit.

Intended changes:

- Preserve candidate flow: ownership/eligibility before prerequisites, then
  existing command filter, composite readiness, and scheduler comparison.
- Update FRFCFS readiness comparisons/caches without changing age semantics.
- Preserve FRFCFS-RowHit's two-pass contract: pre-prerequisite eligibility may
  apply in pass 1, but existing command-filter semantics must not move into a
  new pass or alter row-hit discovery.
- Use the same complete readiness contract in `pick_best_ready_from()` and the
  priority path where applicable; internal direct requests use Device readiness
  because they have no movement history.
- After row-policy mutation and immediately before issue, revalidate candidate
  eligibility, compatible prerequisite/final-command relationship,
  primitive-local timing, and Device timing.
- Never issue a stale scheduler result after command mutation.

Required timing/integration tests:

- LC issues at `0,16,39,55,94,114`, recovery at 130.
- GB issues at `0,1,39,41,59`, recovery at 75.
- No timing-only command alias exists.
- A ready different-Bank request beats an older locally blocked movement.
- Different-Bank Read/Write and inherited PuD progress during local gaps.
- FRFCFS-RowHit row-hit protection and pass/filter semantics remain unchanged.
- A staged post-selection command/readiness change is caught by final
  validation and does not issue illegally.
- Full controller-scheduling and unrelated GDDR/HBM shared-path regressions.

### Independent audit before Phase acceptance

After implementation, self-review, and tests, start one fresh-context audit.
It must determine whether scheduler and final validation use the same
readiness meaning; inspect every scheduler caller/pass; verify ownership is
still checked before prerequisites; examine priority and row-policy mutation;
and review unrelated-standard regressions. Resolve any audit finding and rerun
affected tests before the Phase 5 commit.

### Phase completion criteria

- Exact isolated issue/recovery cycles emerge from non-duplicated local and
  Device constraints.
- Every issued movement occurrence satisfies eligibility, prerequisite
  compatibility, primitive-local readiness, and Device readiness.
- Local stalls reserve no unrelated controller/Channel resource.
- Non-movement scheduler behavior is unchanged under the full shared suite.
- The independent audit is complete with no unresolved finding.

### Risks

- Changing readiness semantics for unrelated controllers.
- FRFCFS-RowHit pass-1 semantic drift.
- Scheduler/final-check disagreement or stale commands.
- Wrong predecessor occurrence or off-by-one delay.
- Accidental Channel serialization during local gaps.

## Phase 6 — Supported integration, observability, and accounting

### Stable invariant

Every supported refresh/row-policy/plugin/trace configuration has explicit safe
movement behavior, and movement lifecycle/statistics/bit accounting are
externally coherent.

This Phase uses several narrow work units and may span two to four chats. It
has one exit review and one commit, accepted only after Final Integration
Closure.

### Work unit 6.A — Refresh and row-policy enforcement

Consume Gate D without reopening it.

Intended changes and tests:

- Ensure movement cannot be upgraded to RDA/WRA, interpreted as an ordinary
  row-buffer access/hit, or trigger an unsafe policy PRE.
- Define shared source/terminal PRE notification bookkeeping exactly as Gate D
  requires while preserving ordinary ClosedCAP behavior.
- Verify queued-before-start refresh wins; refresh arriving after first ACT
  waits; no refresh-generated PREab issues during ownership; REFab waits until
  terminal PRE plus `nRP`; no admission deadline, deferral credit, or bypass is
  introduced.
- Verify policy/refresh work on other Banks may progress when otherwise legal.
- Run existing ClosedCAP, AllBankRefresh, DDR4_PuD maintenance, and relevant
  DDR/HBM refresh-scope regressions.

### Work unit 6.B — Plugin compatibility enforcement

Consume Gate E without reopening it.

- Audit observational command consumers, exact ordinary-ID observers,
  metadata-driven activation/RowHammer observers, and behavior-changing
  plugins that inject priority or ordinary work.
- Implement the accepted observe, ignore/filter, or deterministic
  reject-at-setup behavior for each supported class.
- Ensure permitted plugin-generated work still passes ownership eligibility
  and cannot interrupt/reset movement.
- Use low-threshold directed tests where needed to expose unsafe generic
  `is_opening`/`is_accessing` interpretations.
- Treat observation as command visibility only; it does not imply functional
  movement-data knowledge.

### Gate F and work unit 6.C — Trace observability

Immediately before any production trace edit, decide whether existing command
identity, occurrence address, request type/source ID, and request grouping are
sufficient for the initial milestone or whether logical range/endpoints and
moved bits must be emitted.

- If existing traces suffice, add no production schema and test/document the
  intended interpretation through existing surfaces.
- If added metadata is required, update only the selected trace surfaces and
  add exact LC/GB metadata tests.
- Any binary/live format change requires explicit versioning and decoder/layout
  compatibility tests.
- If Gate F selects a substantial versioned binary/live trace redesign, stop
  and reassess with the user whether that work deserves its own scoped Phase.
  The base plan does not assume that outcome.

### Gate B and work unit 6.D — Movement statistics and exact bits

Gate B's first consumer is movement-specific statistic registration/storage/
updates in this work unit. Gate A is fixed input; do not reopen departure or
callback semantics.

Decide:

- accepted and completed counter boundaries;
- latency start/end, aggregate/average names, and denominators;
- whether exact moved bits accumulate on acceptance, completion, or explicitly
  named both;
- whether memory-system and controller layers both expose counters or one is
  authoritative;
- reset/finalize behavior.

Then:

- register counters only when the combined standard supports both movement
  requests as required;
- count successful admission once and never count a rejected/backpressured
  attempt;
- count completion/callback exactly once at the Gate B boundary derived from
  Gate A;
- compute end-to-end latency from accepted `arrive` to the accepted completion
  boundary, including queueing and prerequisite work;
- derive exact bits from validated metadata and typed HFF width without storing
  rounded bytes;
- keep operation count independent of LC range width and count one GB payload;
- exclude movement from Read/Write served bytes, throughput, forwarding,
  coalescing, and row-buffer statistics;
- preserve every existing DDR4_PuD statistic name/value and keep movement
  fields absent from DDR4/DDR4_PuD.

Work-unit tests cover successful admission versus retry, accepted/completed and
callback-once boundaries, queued latency, LC singleton/multi-mat bits, GB one
payload, HFF override, reset/finalize/zero averages, mixed traffic isolation,
and zero ordinary byte throughput for movement-only traffic.

### Phase completion criteria

- Gates D/E are enforced for every relevant row-policy/plugin actor without
  metadata ambiguity.
- Refresh follows the accepted F-A behavior and terminal recovery exactly.
- Gate F's minimal compatible trace contract is implemented and tested.
- Gate B's movement counters/latency/exact bits are defined, implemented, and
  tested without changing Gate A lifecycle or ordinary byte metrics.
- Existing DDR4, DDR4_PuD, policy, plugin, trace, refresh, and statistic
  behavior is preserved.
- Phase implementation/self-review is complete and ready for Final Integration
  Closure; do not accept the Phase 6 commit before Closure passes.

### Risks

- Metadata-driven plugins treating ACT_MOV as ordinary hammering activation.
- ClosedCAP producing delayed or spurious PRE work.
- Trace-format incompatibility or unnecessary schema expansion.
- Double-counting between memory-system acceptance and controller completion.
- Using the wrong Gate A boundary or converting sub-byte payloads to bytes.

## Final Integration Closure

Final Integration Closure is a mandatory fresh-context validation activity,
not Phase 7 and not a new architectural invariant. Run it after all Phase 6
implementation work and before accepting the Phase 6 milestone commit.

### Closure review

- Read current authority, this plan, and the complete milestone diff.
- Regenerate/build from source and confirm generated definitions/exports are in
  sync.
- Review every generic change for necessity, locality, and baseline impact.
- Verify no owner, movement Device state, row state, occurrence history, or
  delayed-completion entry leaks after any scenario.
- Map every canonical behavior to at least one narrow test and one composed
  path where cross-layer interaction matters.
- Confirm no Superseded decision is needed to understand implementation or
  tests and no future MIMD/T1/T2/physical-Column/energy work entered the diff.

### Required composed scenarios

- LC and GB from Closed and conventionally Opened Banks.
- Exact LC/GB occurrence/address/state/timing behavior, including source PRE
  retention and terminal cleanup.
- Mixed LC/GB/inherited PuD/Read/Write on same and different Banks.
- Ownership acquisition/release, priority behavior, and different-Bank work
  during primitive-local gaps.
- Refresh queued before movement and generated during movement, with no PREab
  interruption and terminal `nRP` before REFab.
- Backpressure/retry, Gate A lifecycle/callback once, Gate B statistics/exact
  bits, completion reordering, and callback reentrancy.
- Gates C/D/E/F policy/plugin/trace outcomes.
- Final Closed Device state, empty movement row state, and no retained owner or
  history leak.

### Broad regression matrix

Run, using the repository's actual build directory:

```shell
PYTHONPATH=python python -m ramulator codegen
cmake --build build -j
PYTHONPATH=python pytest <new movement test files> -q
PYTHONPATH=python pytest tests/device_timings -q
PYTHONPATH=python pytest tests/controller_scheduling/GenericDDRController -q
PYTHONPATH=python pytest tests/controller_scheduling -q
PYTHONPATH=python pytest tests/smoke -q
PYTHONPATH=python pytest tests/latency_throughput/test_fast.py -v -s -k DDR4
git diff --check
```

Include relevant unrelated GDDR/HBM scheduler/refresh tests and all existing
DDR4_PuD tests. Run a more expensive latency/throughput matrix only if shared
timing/refresh changes, project policy, or a failure makes it necessary.

If Closure finds an implementation defect, fix it and rerun the affected
targeted and broad tests. If it exposes a new modeling question, stop and
return to the relevant canonical authority rather than deciding it in code or
a test.

### Closure acceptance criteria

- All directed and broad regressions pass from fresh generated sources.
- Every accepted architecture item has an implementation location and
  validation path.
- DDR4 and DDR4_PuD behavior remains unchanged.
- Complete diff review finds no abstraction leakage, unnecessary generic
  change, unsupported fidelity claim, or future-scope implementation.
- `git diff --check` passes and the Phase 6 milestone is ready for user review
  and commit.

## Old-to-new coverage map

| Expanded-plan work | Optimized owner | Preservation |
| --- | --- | --- |
| Old Phase 1 request classification/capability infrastructure | Phase 1.A | Preserved; movement statistics remain deferred to Gate B |
| Old Phase 2 combined skeleton/config/registration | Phase 1.B | Preserved; name is implementation choice and energy is a Non-goal |
| Old Phase 3 request metadata/routing/validation/payload | Phase 2.A–B | Preserved as a distinct request-contract Phase |
| Old Phase 4 commands/states/actions/PRE defense | Phase 3.A | Preserved; Gates C/D/E move before metadata first consumes them |
| Old Phase 5 context-independent Device timing | Phase 3.B | Preserved in the complete Device substrate |
| Old Phase 6 sequencing/lifecycle | Phase 4.A and 4.C | Preserved without a Phase exit before ownership exists |
| Old Phase 7 primitive-local readiness/scheduler work | Phase 5.A–B | Preserved as an isolated highest-risk Phase plus one independent audit |
| Old Phase 8 ownership/arbitration | Phase 4.B | Preserved alongside sequence execution before mappings are enabled |
| Old Phase 9 refresh/policy/plugins/traces | Phase 6.A–C | Preserved as narrow work units consuming early C/D/E and local F |
| Old Phase 10 lifecycle statistics/exact bits | Phase 6.D | Preserved; Gate B remains here and consumes fixed Gate A lifecycle |
| Old Phase 11 end-to-end validation | Final Integration Closure | Preserved, but not counted as an implementation Phase |

This mapping leaves no old implementation requirement intentionally behind.
The optimized structure changes only execution boundaries, Gate placement, and
duplicated plan text—not accepted movement architecture.
