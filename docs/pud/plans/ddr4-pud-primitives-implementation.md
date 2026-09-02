# DDR4_PuD Basic Primitives Implementation Plan

Status: Complete (Phases 1–9 complete)

## Scope

Extend Ramulator2 with a separate DDR4-based substrate, tentatively named
DDR4_PuD, that accepts PuD memory requests with row operands and executes the
modeled DRAM command sequences for:

- RowCopy: one source row and one or more destination rows
- TRA (triple-row activation), exposed through request identifier `MAJ3`
- 5RA (five-row activation), exposed through request identifier `MAJ5`
- NOT

The reference sequences are:

```text
RowCopy:     A_S*(src) -> A(dst0) -> ... -> A(dstN) -> P
TRA (MAJ3): A*(X) -> A(Y) -> A_S(Z) -> P
5RA (MAJ5): A*(V) -> A(W) -> A(X) -> A(Y) -> A_S(Z) -> P
NOT:         A_S*(X) -> N -> P
```

## Accepted project decisions

- Preserve the existing standard DDR4 model.
- Implement PuD support through a separate DDR4-based substrate.
- Limit this task to RowCopy, MAJ3, MAJ5, and NOT.
- Retain `MAJ3` and `MAJ5` as a consistent pair of request-level identifiers.
  `MAJ3` represents the TRA PuD primitive, which realizes 3-input majority;
  `MAJ5` represents the 5RA PuD primitive, which realizes 5-input majority.
  `5RA` cannot itself be a C++ identifier because it begins with a digit;
  `MAJ3` is retained as the paired naming choice, not as a C++ language
  requirement.
- RowCopy has one source and one or more destinations.
- Do not impose an arbitrary maximum RowCopy destination count.
- Model NOT from `A_S*(X) -> N -> P`.
- Represent `N` as one explicit lower-level DRAM command. Keep its internal
  circuit phases internal rather than exposing independently schedulable
  Ramulator2 commands.
- Accept PuD requests carrying the required row operands and execute their
  modeled DRAM command sequences.
- Represent `A`, `A*`, `A_S`, and `A_S*` as the explicit lower-level commands
  `ACT_PUD`, `ACT_PUD_OC`, `ACT_PUD_S`, and `ACT_PUD_S_OC`, respectively.
- Keep RowCopy, MAJ3, MAJ5, and NOT as request-level operations only.
- Add only `PuDChargeSharing` and `PuDSensed` as PuD device states, returning
  to the existing `Closed` state after final precharge.
- Keep primitive identity, operands, counts, sequence progress, and the next
  expected command as controller responsibilities.
- Use a phase-only device legality model and map final `P` to ordinary per-bank
  `PREpb`, with the detailed transitions and conventional-command legality
  recorded by Decision Gate 7.
- Use the DDR4_2400R baseline and the accepted bank-local directed PuD timing,
  aggregate-`N`, command-bus, activation-window, and RowCopy scaling rules
  recorded by Decision Gate 8.
- Derive bank-scoped ownership and atomicity from the retained active PuD
  request from its first activation through final `PREpb`, while permitting
  timing-legal work to non-owned banks, as recorded by Decision Gate 9.
- Use the Gate 9 pre-prerequisite eligibility rule as the sole protection from
  conflicting refresh, row-policy, priority-maintenance, and plugin-generated
  work, as recorded by Decision Gate 10.
- Use a configurable, entry-counted pending-PuD buffer; oldest-ready
  PuD-versus-Read/Write arbitration; completion after final `PREpb` plus
  `nRP`; and operation-based PuD statistics, as recorded by Decision Gate 11.
- Use the existing C++ `IMemorySystem::send(Request&)` interface as the
  supported PuD submission surface for Phase 9. Do not add a public Python or
  multi-operand frontend API in that phase.
- Use the existing command-trace, callback, and statistics facilities for
  Phase 9 latency observability; do not add production instrumentation.
- Add one focused DDR4_PuD user guide under `docs/pud/` and link it from the
  main README.

## Out of scope

- DRAM data-value tracking or functional result validation
- Energy modeling
- Inter-column movement
- Higher-level PuD operations

## Decision status conventions

- **Accepted** records an approved project decision.
- **Decision gate** must be resolved with user approval before dependent work.
- **Missing reference** identifies information that must be supplied before a
  physically dependent model can be implemented.

## Phase 1 — Establish the DDR4_PuD substrate boundary

Status: Complete

### Objective

Create a separate DDR4-based substrate without changing standard DDR4
behavior.

### Relevant existing components

- `python/ramulator/dram/ddr4.py`
- `python/ramulator/codegen.py`
- `src/ramulator/dram/impl/DDR4.cpp`
- `src/ramulator/dram/dram_spec.h`
- DRAM registration and Python bindings
- Existing DDR4 smoke, device-timing, and controller-scheduling tests

### Expected code changes

- Introduce the DDR4_PuD standard and configuration.
- Reuse the DDR4 baseline through the structure selected at Decision Gate 1.
- Add construction and baseline-behavior tests.
- Do not add PuD behavior in this phase.

### Decision Gate 1 — DDR4_PuD code structure

Status: Accepted. See `docs/pud/decisions/ddr4-pud-code-structure.md`.

Use an independent generated DDR4_PuD standard whose Python definition reuses
DDR4 while keeping mutable definition collections independent.

### Prerequisite decisions

- Satisfied by the accepted Decision Gate 1 decision.

### Validation before proceeding

- Existing DDR4 tests pass unchanged.
- DDR4_PuD can be instantiated.
- Before PuD commands are added, conventional DDR4_PuD Read/Write behavior
  matches the selected DDR4 baseline.

### Completion criteria

- DDR4_PuD has a stable implementation boundary.
- Standard DDR4 contains no PuD commands, states, timings, or request mappings.

## Phase 2 — Define the PuD request and operand interface

Status: Complete

### Objective

Represent all in-scope requests and preserve their ordered row operands through
memory-system and controller ingress.

Required operand forms are:

- RowCopy: one source and one or more destinations
- MAJ3: exactly three ordered rows
- MAJ5: exactly five ordered rows
- NOT: exactly one source row

### Relevant existing components

- `src/ramulator/base/request.h`
- `src/ramulator/base/request.cpp`
- `src/ramulator/memory_system/impl/generic_dram_system.cpp`
- Channel and address mappers
- `ControllerBase::send()`
- `DRAMSpec::supported_requests`
- Python `supported_requests`
- Controller test-harness request injection

### Expected code changes

- Add the accepted PuD operation identifiers.
- Add the accepted variable-length operand representation.
- Preserve operand ordering at request ingress.
- Route and validate PuD requests without changing Read/Write behavior.
- Extend the test harness to inject PuD operations and variable-length operand
  lists.
- Reject malformed requests and unsupported placements explicitly.

The request representation must support RowCopy without imposing a fixed
primitive-specific destination maximum unless a concrete implementation or
reference requirement establishes one.

### Decision Gate 2 — Request taxonomy and operand representation

Status: Accepted. See
`docs/pud/decisions/pud-request-taxonomy-and-operands.md`.

Use four explicit request types and request-owned ordered `AddrVec_t` operands.
For RowCopy, operand 0 is the source and operands 1 through N are destinations.

The accepted representation must support:

```text
RowCopy(source, destinations[1..N])
MAJ3(rows[3])
MAJ5(rows[5])
NOT(source)
```

### Decision Gate 3 — Operand placement and address semantics

Status: Accepted for the current primitives. See
`docs/pud/decisions/pud-operand-placement-and-routing.md`.

### Resolved placement basis

Current primitives use the accepted logical-subarray placement model and split
memory-system/controller validation recorded by Decision Gate 3. Mat-level
identity and interleaving remain deferred and are not required by Phase 2.

### Prerequisite decisions

- Satisfied by the accepted Decision Gates 2 and 3 decisions.

### Validation before proceeding

- RowCopy accepts one source and any nonempty destination list.
- RowCopy with zero destinations is rejected.
- RowCopy preserves every destination and its submitted order.
- Large destination lists are not rejected by an arbitrary primitive-specific
  limit.
- MAJ3 accepts exactly three rows.
- MAJ5 accepts exactly five rows.
- NOT accepts exactly one row.
- Ordinary Read/Write requests remain unchanged.
- Invalid operation identifiers, operand counts, and accepted placement
  violations are rejected deterministically.

### Completion criteria

- Every in-scope PuD request reaches the selected controller with its operation
  and ordered operands intact.
- Variable-length RowCopy requests are supported by the interface.
- No DRAM command sequence is generated yet.

### Deferred cleanup — not blockers for Phase 3

- Remove the temporary public pending-PuD-request test accessor and localize
  the PuD buffer when controller sequencing and request lifecycle work make
  that appropriate.
- Add a lightweight test-only consistency check for Python and C++ request IDs.
- Retain `DRAMGeometry` unchanged until Mat-level geometry requirements are
  defined.

## Phase 3 — Define the PuD command and state model

Status: Complete

### Objective

Define simulator representations for the activation variants, NOT operation
`N`, and final precharge.

### Relevant existing components

- `src/ramulator/dram/commands/ACT.h`
- `src/ramulator/dram/commands/PREpb.h`
- `src/ramulator/dram/commands/ACT1.h`
- `src/ramulator/dram/commands/ACT2.h`
- `src/ramulator/dram/node.h`
- `src/ramulator/dram/func_types.h`
- `src/ramulator/dram/commands/populate.h`
- DDR4_PuD command and state declarations

### Expected code changes

After the decision gates:

- Add the accepted representations of `A`, `A*`, `A_S`, and `A_S*`.
- Add the accepted representation of `N`.
- Register command metadata and bank targeting.
- Add only the intermediate state needed to enforce the accepted behavior.
- Keep conventional DDR4 ACT/PRE behavior unchanged.

### Decision Gate 4 — Activation-command representation

Status: Accepted. See
`docs/pud/decisions/pud-activation-command-representation.md`.

Represent `A`, `A*`, `A_S`, and `A_S*` as the explicit lower-level commands
`ACT_PUD`, `ACT_PUD_OC`, `ACT_PUD_S`, and `ACT_PUD_S_OC`, respectively.
RowCopy, MAJ3, MAJ5, and NOT remain request-level operations only. This
decision establishes command identity only; state transitions, prerequisites,
legality, and timing remain unresolved.

### Decision Gate 5 — Minimum simulator abstraction for `N`

Status: Accepted. See
`docs/pud/decisions/pud-not-command-granularity.md`.

Represent `N` as one explicit lower-level DRAM command. Separate BL/BL-bar
precharge, BL-BL-bar charge sharing, sensing, and other internal circuit phases
remain internal to `N` and are not independently schedulable Ramulator2
commands.

This is a simulator abstraction, not a claim that `N` is physically a single
indivisible circuit operation. Detailed state transitions, numeric timing,
resource occupancy, and interleaving or interruption of the surrounding NOT
sequence remain unresolved.

### Decision Gate 6 — Intermediate state representation

Status: Accepted. See
`docs/pud/decisions/pud-intermediate-state-representation.md`.

Add only `PuDChargeSharing` and `PuDSensed`. Use the existing `Closed` state
after final precharge. Unsensed `A*`/`A` sequences use `PuDChargeSharing`;
sensing through `A_S` or `A_S*` enters `PuDSensed`; RowCopy destination `A`
commands and `N` may remain in `PuDSensed`.

Do not add a finalized or primitive-specific device state. Primitive identity,
operand identities and role assignment, activation and destination counts,
exact sequence progress, and the next expected command remain controller
responsibilities.

This decision does not define precharge or conventional-command legality,
interleaving, timing, resource occupancy, interruption, or scheduling.

### Prerequisite decisions

- Satisfied by the accepted Decision Gates 4, 5, and 6 decisions.

### Validation before proceeding

- Specify device-level tests for every accepted simulator-visible state and
  command transition before controller sequencing begins.
- Keep request-specific operand role, deterministic traversal, and operation
  ownership tests at the controller layer.

### Completion criteria

- Every reference-level operation has an accepted simulator representation.
- The representation covers NOT without unnecessarily exposing circuit detail.
- The state model supports the accepted repeated destination activation
  semantics for RowCopy and the accepted activation semantics for the
  fixed-arity majority operations.
- No numeric timing assumptions have been introduced.

## Phase 4 — Add device-level PuD command behavior

Status: Complete

### Objective

Implement device actions and prerequisite legality for the accepted command
and state abstractions.

### Relevant existing components

- PuD command handlers
- `DRAMDevice::get_preq_command()`
- `DRAMDevice::issue_command()`
- `DRAMDevice::apply_action()`
- `DRAMNode::m_state`
- `DRAMNode::m_row_state`
- Device-timing test harness

### Expected code changes

- Permit the accepted sequential activation behavior.
- Record rows and operation phases only as required by the accepted state
  model.
- Support repeated RowCopy destination activations according to the accepted
  semantics.
- Implement the accepted state effects of `N`.
- Enforce the state and command legality assigned to the device by the decision
  gates.
- Return the bank to the accepted closed state after final precharge.
- Implement the accepted interaction with conventional ACT, RD, WR, and PRE
  during PuD intermediate states.

Request-specific operand roles, deterministic traversal, and sequence
ownership are controller responsibilities and are implemented and tested at
the controller layer.

### Decision Gate 7 — Precharge and legality semantics

Status: Accepted. See
`docs/pud/decisions/pud-precharge-and-legality-semantics.md`.

Use a phase-only legality model. Reference `P` maps to ordinary per-bank
`PREpb`. PuD activations and `N` follow the accepted phase transitions;
conventional `ACT`, `RD`, and `WR` are illegal in either PuD state. `PREpb` is
illegal in `PuDChargeSharing` and returns `PuDSensed` to `Closed`.

Exact primitive sequencing and request-level premature precharge remain
controller responsibilities. This gate does not define `PREab`, refresh,
scheduling or interleaving, numeric timing, or interruption semantics.

### Prerequisite decisions

- Satisfied by the accepted Decision Gates 4, 5, 6, and 7 decisions.

### Validation before proceeding

At the device layer, validate only the responsibilities assigned to it by the
accepted gates:

- Legal state transitions for the accepted RowCopy command pattern, including
  repeated destination activations.
- Legal state transitions for MAJ3 and MAJ5.
- `N` is illegal before its required source activation state.
- Repeated or misplaced `N` is rejected at the controller layer.
- The accepted state transitions of the explicit `N` command are tested.
- Final precharge clears the accepted intermediate state.
- Conventional DDR4_PuD accesses retain ordinary behavior outside a PuD
  operation.

Request-specific operand roles, operand identity, deterministic traversal, and
sequence ownership are validated later at the controller layer.

### Completion criteria

- The device implements its accepted PuD state transitions and prerequisites.
- The device does not assume responsibility for request-specific sequencing
  beyond what the decision gates explicitly assign to it.
- RowCopy device behavior supports repeated destination activations without a
  fixed destination-count limit or an assumption that every destination is
  simultaneously represented as active.

## Phase 5 — Add the PuD timing model

### Objective

Express all supported PuD timing and resource relationships using the existing
timing engine or an explicitly approved minimal extension.

### Relevant existing components

- DDR4_PuD timing parameters
- Python `TimingConstraint`
- `DRAMSpec::timing_vals`
- `DRAMSpec::timing_cons`
- `DRAMNode::update_timing()`
- `DRAMNode::check_timing()`
- Command-cycle configuration
- Device-timing tests

### Expected code changes

- Add accepted timing parameters.
- Add PuD-to-PuD constraints.
- Add PuD-to-conventional and conventional-to-PuD constraints.
- Add command-bus or internal-resource occupancy where applicable.
- Represent `N` through aggregate constraints or accepted exposed phases.
- Apply repeated `A(dst)` constraints according to the accepted RowCopy model.
- Do not invent missing values.

### Decision Gate 8 — Timing, resource, and command-bus rules

Status: Accepted. See
`docs/pud/decisions/pud-timing-resource-and-command-bus-rules.md`.

Use the actual Ramulator2 DDR4_2400R baseline, the accepted continuous-time
derivation and ceiling conversion, and target-bank-local directed timing
constraints. Model `N` as one aggregate bank-local command, use one CK of
command-bus occupancy per PuD command, exclude PuD activations from `tRRD` and
`tFAW`, and add one 5 CK interval per RowCopy destination. The evidence,
derived values, explicit modeling assumptions, and vendor-validation issues
are recorded in the decision document.

Refresh during an intermediate PuD phase remains unsupported. Do not infer a
timing or interruption behavior for it in Phase 5.

### Prerequisite decisions

- Satisfied by the accepted Decision Gate 8 decision.

### Validation before proceeding

- Every timing boundary is illegal one cycle early and legal at the specified
  cycle.
- Repeated destination activations obey the accepted constraints for both short
  and long RowCopy destination lists.
- NOT timing matches the accepted abstraction of `N`.
- Same-bank and relevant cross-bank/rank effects are covered.
- Existing standard DDR4 timing remains unchanged.

### Completion criteria

- Every supported transition has accepted timing behavior whose provenance is
  identified as source-backed evidence, a derived value, or an explicit
  project modeling assumption.
- `N` exposes no more internal timing structure than required by the accepted
  model.
- No PuD timing is inferred silently from ordinary DDR4.

## Phase 6 — Add controller-side sequence execution

### Objective

Translate each PuD request into its role-ordered, operand-specific command
sequence.

### Relevant existing components

- `GenericDDRController::tick()`
- `ControllerBase` buffers and helpers
- `Request::command` and `Request::final_command`
- FR-FCFS schedulers
- Active-buffer promotion and retirement
- Device prerequisite and timing queries
- Refresh and row-policy hooks

### Expected code changes

- Add the minimum monotonic per-request phase/operand cursor selected by
  Decision Gate 9.
- Select the correct operand address for every phase.
- Iterate through all RowCopy destinations without a fixed
  primitive-specific limit.
- Retain a PuD request in the active buffer after its first activation and
  advance it in place rather than re-promoting later PuD activations.
- Before prerequisite resolution, exclude non-owner candidates whose command
  scope intersects a bank containing an active PuD request.
- Execute `N` using its accepted abstraction.
- Keep the request alive until final precharge.
- Consult device prerequisites and timing before every issued command.
- Preserve the existing Read/Write path.

The expected request-level sequences are:

```text
RowCopy: A_S*(src) -> A(dst0) -> ... -> A(dstN) -> P
MAJ3:    A*(X) -> A(Y) -> A_S(Z) -> P
MAJ5:    A*(V) -> A(W) -> A(X) -> A(Y) -> A_S(Z) -> P
NOT:     A_S*(X) -> N -> P
```

`N` appears exactly once as an explicit command in the NOT sequence; its
internal circuit phases are not exposed in that sequence.

The sequence fixes command roles. RowCopy visits every destination exactly
once after sensing the source, but destination order is not a physical
correctness requirement in the accepted model. Likewise, the order among
equivalent intermediate `A` operands in MAJ3/MAJ5 has no simulator-visible
physical significance. Submitted operand order remains the deterministic
traversal and role-assignment convention for implementation and testing.

### Decision Gate 9 — Controller sequencing and scheduling atomicity

Status: Accepted. See
`docs/pud/decisions/pud-controller-sequencing-and-atomicity.md`.

Use the retained active PuD request as the authoritative continuation request
and derive bank-scoped ownership and eligibility from it; do not add a
bank-to-owner table. Track only a monotonic phase/operand cursor, advance the
active request in place, and exclude intersecting non-owner candidates before
prerequisite resolution. Preserve the accepted command-role order and the
submitted-order deterministic traversal convention without treating
equivalent destination or intermediate ordering as a physical requirement.
Allow timing-legal work to non-owned banks between PuD commands; sequence
arrows are role-ordered but not contiguous channel issue.

RowCopy retains ownership across its entire destination list without a
destination quantum or preemption mechanism. `N` remains one issued
lower-level command. This is an explicit simulator modeling decision, not a
verified physical requirement. Refresh, row-policy, priority-maintenance, and
plugin interaction follow the accepted Decision Gate 10 policy.

### Decision Gate 10 — Refresh and row-policy interaction

Status: Accepted. See
`docs/pud/decisions/pud-refresh-row-policy-and-maintenance-interaction.md`.

Apply the Gate 9 eligibility rule before prerequisite resolution to every
candidate source. Conflicting refresh, row-policy, priority-maintenance, and
plugin-generated work remains queued until the retained active PuD request
issues final `PREpb`. Do not preempt PuD, add refresh-aware admission, or
bypass a blocked FIFO priority head. Preserve existing active-buffer priority,
priority-buffer behavior, and hook ordering. Already-active nonintersecting
requests retain existing scheduling behavior.

`ClosedCAP` may not precharge an active PuD sequence. Observational plugin
hooks remain unchanged, but behavior that depends on conventional activation
or maintenance semantics is not physically validated. Adding the
`DDR4_PuD` standard name to `AllBankRefresh` is a Phase 6 implementation
detail.

### Missing reference information

The accepted Gate 10 policy may postpone refresh for an arbitrarily long
RowCopy. No postponement limit, credit model, retention guarantee, or
queue-overflow policy is modeled, and physical DDR4 support for unbounded
postponement is not claimed. PuD interaction with RowHammer-sensitive or other
behavior-changing plugins is also not physically validated. These are explicit
limitations rather than blockers for the accepted simulator policy.

### Prerequisite decisions

- Decision Gate 9 is satisfied by the accepted controller sequencing and
  bank-scoped atomicity decision.
- Decision Gate 10 is satisfied by the accepted refresh, row-policy,
  priority-maintenance, and plugin-interaction decision.

### Validation before proceeding

At the controller layer:

- Every issued command uses the correct request operand row.
- RowCopy visits each destination exactly once using submitted order as the
  deterministic traversal convention rather than a physical requirement.
- RowCopy works with one destination and longer destination lists.
- MAJ3 and MAJ5 issue the accepted first, intermediate, final-sensing, and
  precharge roles, using submitted order as the deterministic role/traversal
  convention.
- NOT issues the accepted `N` representation exactly once.
- The request does not retire before final precharge.
- Timing stalls do not lose, duplicate, or skip phases.
- Accepted contention and interleaving behavior is tested.
- Competing requests cannot corrupt PuD sequence progress or ownership.
- Conflicting row-policy, refresh, and plugin-generated priority work cannot
  interrupt an active PuD request and remains queued through final `PREpb`.
- A blocked priority-buffer head retains existing FIFO blocking behavior.
- Already-active nonintersecting requests retain existing scheduling behavior.

### Completion criteria

- Valid requests for all four primitives deterministically produce their
  complete accepted sequences.
- Request-specific operand roles, deterministic traversal, sequence progress,
  and active-request-derived ownership are enforced at the controller layer.
- RowCopy sequence length is determined by its destination list rather than a
  hard-coded maximum.

## Phase 7 — Complete request lifecycle integration

Status: Complete

### Objective

Give PuD requests complete external ingress, backpressure, completion, and
statistics behavior.

### Relevant existing components

- `GenericDRAMSystem::send()`
- `ControllerBase::send()`
- `ControllerBase::retire_request()`
- Controller buffers
- Callback handling
- Controller and memory-system statistics

### Expected code changes

- Define PuD queue admission and backpressure.
- Account for variable-size RowCopy request metadata safely.
- Release ownership at final `PREpb` issue and invoke external completion after
  its accepted `nRP` recovery through the shared completion infrastructure.
- Add minimal approved PuD statistics.
- Prevent Read forwarding and Write coalescing from applying to PuD requests.

### Decision Gate 11 — Completion, queueing, and statistics semantics

Status: Accepted. See
`docs/pud/decisions/pud-request-lifecycle-queueing-and-statistics.md`.

Use a configurable dedicated pending-PuD buffer with a default capacity of 32
entries and count one request per entry regardless of operand count. Preserve
active-buffer and FIFO priority-buffer behavior. When priority work does not
block new work, arbitrate oldest-ready between the pending-PuD candidate and
the existing Read/Write candidate. This supersedes the Phase 6 strict
pending-PuD-over-Read/Write scaffolding.

Final `PREpb` issue ends the sequence and releases ownership. Retain the now
unschedulable request through a minimally generalized shared completion path
until `PREpb` issue plus `nRP`, then set `depart` and invoke its callback once.
Measure end-to-end latency as `depart - arrive`. Record the accepted
per-operation, queue-occupancy, and memory-system counts without adding PuD to
Read/Write byte-throughput or row-buffer statistics. Phase 7 uses the existing
Request-level memory-system ingress and does not add a multi-operand frontend
API.

### Prerequisite decisions

- Satisfied by the accepted Decision Gate 11 decision.

### Validation before proceeding

- Admission failure leaves the request retryable and its operand list intact.
- Completion occurs exactly once after final `PREpb` recovery at its issue
  cycle plus `nRP`; ownership ends when `PREpb` issues.
- RowCopy completion is independent of destination count except for modeled
  execution latency.
- NOT completes only after `N` and the final-`PREpb` recovery completion.
- Existing Read/Write completion and statistics remain unchanged.

### Completion criteria

- Each primitive has a complete and testable request lifecycle.
- Variable-length requests do not introduce ownership or lifetime errors.

## Phase 8 — End-to-end validation

Status: Complete

### Objective

Validate the complete modeled execution path without claiming functional DRAM
value correctness.

### Relevant existing components

- DDR4_PuD configuration
- Device-timing harness
- Controller-scheduling harness
- Smoke and regression suites

### Expected code changes

- Add focused end-to-end tests for all four primitives.
- Add mixed PuD and ordinary traffic tests.
- Add malformed-request and illegal-placement tests.
- Add regression coverage confirming standard DDR4 remains unaffected.

### Validation before completion

For RowCopy:

- Test one source with one destination.
- Test one source with multiple destination-list lengths.
- Verify submitted-order destination traversal as the deterministic
  implementation convention selected by Decision Gate 9, without treating it
  as a physical correctness requirement.
- Reject zero destinations.
- Do not impose an arbitrary primitive-specific maximum.
- Verify the exact accepted command/address sequence and final completion.
- Verify repeated destination activation state behavior without assuming that
  all destinations are simultaneously represented as active.

For MAJ3 and MAJ5:

- Verify exact operand counts.
- Verify command variants, order, addresses, and timing at the layer assigned
  those responsibilities.
- Reject malformed requests.

For NOT:

- Verify `A_S*(X) -> N -> P` under the accepted abstraction.
- Verify that `N` is issued exactly once and no internal circuit phase is
  exposed as a command.
- Verify accepted state, timing, resource, and scheduling behavior of `N`.
- Reject malformed requests and verify final cleanup.

Across all primitives:

- Verify accepted placement rules.
- Verify device state and prerequisites.
- Verify timing legality.
- Verify the accepted scheduling and interleaving policy.
- Verify refresh and row-policy behavior.
- Verify mixed ordinary/PuD traffic.
- Verify completion after the accepted final-`PREpb` recovery boundary.
- Run standard DDR4 regression tests unchanged.

Physical copy, majority, and inversion results are not validated because DRAM
data-value tracking is out of scope.

### Completion criteria

- RowCopy, MAJ3, MAJ5, and NOT execute end-to-end on DDR4_PuD.
- RowCopy supports one or more destinations without an arbitrary fixed maximum.
- Repeated RowCopy destination activations follow the accepted state semantics.
- `N` uses the minimum abstraction accepted at Decision Gate 5.
- Request-specific operand roles, deterministic traversal, and
  active-request-derived sequence ownership are handled at the controller
  layer.
- Every accepted modeling decision is covered by tests.
- Missing references are never replaced with undocumented assumptions.
- Existing standard DDR4 behavior remains unchanged.

## Phase 9 — Add usability and observability guidance

Status: Complete

### Objective

Make the completed DDR4_PuD primitive model understandable, configurable,
runnable, and measurable through focused documentation and a small
reproducible example, without changing any accepted simulator semantics.

### Relevant existing components

- `README.md`
- `docs/pud/decisions/`
- `docs/pud/references/`
- `python/ramulator/dram/ddr4_pud.py`
- `python/ramulator/controller/generic_ddr.py`
- `src/ramulator/base/request.h`
- `src/ramulator/memory_system/i_memory_system.h`
- `src/ramulator/controller/plugin/impl/cmd_trace_recorder.cpp`
- Controller callback and statistics interfaces
- Existing DDR4_PuD device-timing, controller-sequencing, lifecycle, and
  statistics tests

### Expected documentation and example work

- Add one focused DDR4_PuD user guide under `docs/pud/` and link it from the
  main README.
- Summarize the separate DDR4_PuD substrate, the four request-level
  operations, their lower-level command sequences, and the division of
  responsibility between requests, the controller, and the DRAM device.
- Keep `MAJ3` and `MAJ5` as the request identifiers. When discussing the
  physical primitives, prefer TRA and 5RA, and state explicitly that TRA and
  5RA realize 3-input and 5-input majority, respectively. Explain the
  consistent request-identifier naming without claiming that both names are
  required by C++ identifier rules.
- Document a complete DDR4_PuD configuration using the supported
  `DDR4_2400R` timing preset, `GenericDDR`, the configurable
  `pud_buffer_size`, and appropriate address/channel mappers, row policy,
  refresh manager, and optional command trace.
- Document C++ request construction and submission through
  `Request(std::vector<AddrVec_t>, type)` and
  `IMemorySystem::send(Request&)`, including `size_bytes`, callbacks,
  backpressure, and retry behavior. Do not use the test-only Python controller
  harness as a supported user interface.
- Document the ordered operand roles and counts for RowCopy, MAJ3, MAJ5, and
  NOT. Explain that RowCopy has one source followed by one or more
  destinations and no arbitrary primitive-specific destination limit.
- Document that operands are full final device-visible address vectors. State
  the common channel, rank, bank-group, bank, and logical-subarray placement
  requirements; the `row / 1024` logical-subarray mapping; hierarchy bounds;
  and the fact that columns are preserved without PuD operation semantics.
- Document final-`PREpb` ownership release, completion after final `PREpb`
  plus `nRP`, callback behavior, and the meanings of `arrive` and `depart`.
- Document all existing per-operation accepted/completed counts, total and
  average end-to-end latency statistics, pending-PuD queue occupancy
  statistics, and memory-system accepted-operation counts. Explain why PuD
  requests are excluded from Read/Write throughput, forwarding, coalescing,
  and row-buffer statistics.
- Add a small reproducible C++ example or microbenchmark under `examples/`
  with an exportable Python configuration. It must submit valid RowCopy,
  MAJ3, MAJ5, and NOT requests through `IMemorySystem::send(Request&)`, handle
  retryable backpressure, receive callbacks, emit an existing command trace,
  and expose the relevant statistics.
- Keep the isolated-latency run free of unrelated traffic and refresh, use
  initially closed banks, and use unique request source identifiers so that
  trace commands and callbacks can be associated with each request.
- Add only the smallest validation needed to keep the documented example
  reproducible. Reuse the existing DDR4_PuD timing, sequence, lifecycle, and
  statistics tests rather than duplicating their model validation.

### Latency observability

Use the existing command trace to obtain the first PuD command issue cycle,
the callback to obtain `arrive` and `depart`, and the existing statistics for
aggregate end-to-end measurements. Document or report:

```text
isolated modeled primitive latency = depart - first PuD command issue
pre-start delay                    = first PuD command issue - arrive
end-to-end request latency         = depart - arrive
```

The pre-start delay includes queueing, arbitration, and any prerequisite work
before the primitive begins. The end-to-end latency statistics therefore may
exceed the isolated modeled primitive latency.

For the accepted DDR4_2400R model, document the existing isolated timing
results, including final `PREpb` recovery:

```text
RowCopy with D destinations = 40 + 5*D + 16 CK
TRA (MAJ3 request)          = 66 CK
5RA (MAJ5 request)          = 76 CK
NOT                         = 99 CK
```

Do not add a new production timestamp, trace field, latency counter, or other
instrumentation for these measurements.

### Current limitations to document

- No DRAM data-value tracking or functional result validation.
- No energy model, inter-column movement, or higher-level PuD operations.
- Logical subarray placement is a simulator assumption; physical mat identity
  and interleaving remain undefined.
- The completion boundary is a simulator lifecycle definition, not a claim
  about earliest physical data availability.
- No PuD preemption, abort, resume, refresh-postponement bound, retention
  guarantee, or variable-operand metadata-cost model.
- Physical validation remains unavailable for the accepted atomicity,
  reservation, command-encoding, shared-resource, activation-window,
  cross-bank, refresh, and behavior-changing-plugin assumptions identified in
  the existing decision documents.
- Future real-workload or external-simulator integration must provide a
  multi-operand PuD ingress path to the existing Request-level
  `IMemorySystem::send(Request&)` interface.

### Explicitly out of scope

- Changes to accepted DRAM commands, states, timing, placement, scheduling,
  arbitration, ownership, refresh, completion, or statistics semantics.
- Renaming the `MAJ3` or `MAJ5` request identifiers.
- New production latency instrumentation, trace formats, visualization
  features, or performance-sweep tooling.
- A public Python or multi-operand frontend API.
- Functional result checking, energy modeling, physical mat placement,
  inter-column movement, and higher-level PuD operations.
- Unrelated implementation or test-harness cleanup.

### Validation before completion

- The documented configuration exports and constructs DDR4_PuD successfully.
- The example builds and submits all four request types through the public C++
  request-level memory-system interface.
- The example's trace, callback timestamps, and statistics reproduce the
  documented distinction between isolated, pre-start, and end-to-end
  latency.
- The documented isolated timing results agree with the existing device and
  controller tests.
- No standard DDR4 behavior or accepted DDR4_PuD behavior changes.

### Completion criteria

- A user can understand, configure, submit, observe, and reproduce every
  completed DDR4_PuD primitive using the documented supported interface.
- TRA/MAJ3 and 5RA/MAJ5 terminology is explicit and consistent.
- Isolated modeled latency is clearly distinguished from end-to-end request
  latency.
- Completion, callback, statistics, placement requirements, and current
  modeling limitations are documented.
- Phase 9 introduces no new modeling semantics or production instrumentation.

## Decisions still requiring user approval

- None.

## Missing reference information blocking implementation

- None. Remaining physical-validation limitations are recorded in
  the accepted decision documents and are not replaced by undocumented
  assumptions.
