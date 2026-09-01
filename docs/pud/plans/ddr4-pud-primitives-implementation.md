# DDR4_PuD Basic Primitives Implementation Plan

Status: Phases 1 and 2 complete; Phase 3 not started

## Scope

Extend Ramulator2 with a separate DDR4-based substrate, tentatively named
DDR4_PuD, that accepts PuD memory requests with row operands and executes the
modeled DRAM command sequences for:

- RowCopy: one source row and one or more destination rows
- TRA / MAJ3
- 5RA / MAJ5
- NOT

The reference sequences are:

```text
RowCopy: A_S*(src) -> A(dst0) -> ... -> A(dstN) -> P
MAJ3:    A*(X) -> A(Y) -> A_S(Z) -> P
MAJ5:    A*(V) -> A(W) -> A(X) -> A(Y) -> A_S(Z) -> P
NOT:     A_S*(X) -> N -> P
```

## Accepted project decisions

- Preserve the existing standard DDR4 model.
- Implement PuD support through a separate DDR4-based substrate.
- Limit this task to RowCopy, MAJ3, MAJ5, and NOT.
- RowCopy has one source and one or more destinations.
- Do not impose an arbitrary maximum RowCopy destination count.
- Model NOT from `A_S*(X) -> N -> P`.
- Do not assume that the internal circuit operations within `N` require
  separate Ramulator2 commands.
- Accept PuD requests carrying the required row operands and execute their
  modeled DRAM command sequences.

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

Determine whether the four activation variants are:

- Four explicit DRAM commands.
- A smaller command set with explicit variant or phase metadata.
- Another approved abstraction.

Also decide whether RowCopy, MAJ3, MAJ5, and NOT exist as device-level
primitive commands or only as request-level operations expanded into
lower-level commands.

### Decision Gate 5 — Minimum simulator abstraction for `N`

Evaluate two principal alternatives:

1. Model `N` as one DRAM command whose internal circuit behavior is abstracted
   into aggregate timing, state transitions, resource occupancy, and
   prerequisites.
2. Expose one or more internal phases as separate Ramulator2 commands or
   states.

Separate BL/BL-bar precharge, BL-BL-bar charge sharing, sensing, or another
internal phase should be exposed only if it independently affects at least one
of:

- command legality;
- timing boundaries;
- resource occupancy;
- scheduling or interleaving;
- interruptibility or atomicity;
- observable DRAM state;
- interaction with conventional commands or refresh.

This gate must document why the selected abstraction is sufficient. It must
not assume that circuit-level phases map one-to-one to Ramulator2 commands.

### Decision Gate 6 — Intermediate state representation

Define the minimum representation for:

- Sequential activation of the participating rows.
- Wordline-only versus sensed activation.
- Offset-cancellation effects when relevant to legality or timing.
- State before, during, and after `N`.
- PuD operation ownership if the accepted model requires the device to track
  it.
- Repeated RowCopy destination activations according to the accepted RowCopy
  semantics.

This gate does not assume that request-specific operand ordering or sequence
ownership must be validated by the device model. It also does not assume that
multi-destination RowCopy requires all destination rows to be represented as
simultaneously activated.

### Missing reference information

References are needed to determine:

- Which intermediate activation distinctions affect simulator-visible
  behavior.
- Whether any internal `N` phase can be interrupted or interleaved.
- Whether internal `N` phases have independently observable timing or resource
  effects.
- The state effects of repeated RowCopy destination activations.

### Prerequisite decisions

- Resolve Decision Gates 4, 5, and 6.
- Supply the missing state and `N` behavior references required by those gates.

### Validation before proceeding

- Specify device-level tests for every accepted simulator-visible state and
  command transition before controller sequencing begins.
- Keep request-specific operand ordering and operation ownership tests at the
  layer selected by the corresponding decision gates.

### Completion criteria

- Every reference-level operation has an accepted simulator representation.
- The representation covers NOT without unnecessarily exposing circuit detail.
- The state model supports the accepted repeated destination activation
  semantics for RowCopy and the accepted activation semantics for the
  fixed-arity majority operations.
- No numeric timing assumptions have been introduced.

## Phase 4 — Add device-level PuD command behavior

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

Request-specific operand ordering and sequence ownership are not inherently
device responsibilities. They are implemented and tested at whichever layer is
selected by the corresponding decision gates.

### Decision Gate 7 — Precharge and legality semantics

Confirm:

- Whether reference `P` maps to ordinary `PREpb`.
- Which conventional commands are legal during each PuD phase.
- Whether premature precharge aborts, completes, or is illegal.
- The device-visible legality rules for repeated RowCopy destination
  activations.
- Whether operation ownership is enforced by the device, controller, or both.
- How illegal interruption of `N` is represented.

### Prerequisite decisions

- Resolve Decision Gates 4 through 7.

### Validation before proceeding

At the device layer, validate only the responsibilities assigned to it by the
accepted gates:

- Legal state transitions for the accepted RowCopy command pattern, including
  repeated destination activations.
- Legal state transitions for MAJ3 and MAJ5.
- `N` is illegal before its required source activation state.
- Repeated or misplaced `N` is rejected if the device state model is assigned
  that responsibility.
- If internal `N` phases are exposed, their accepted state transitions are
  tested.
- Final precharge clears the accepted intermediate state.
- Conventional DDR4_PuD accesses retain ordinary behavior outside a PuD
  operation.

Request-specific operand order, operand identity, and sequence ownership are
validated later at the layer selected by the relevant decisions.

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

Approve:

- Numeric timings for all activation variants, `N`, and precharge.
- Whether `N` has one aggregate duration or separately relevant phase
  boundaries.
- Resource occupancy during `N`.
- Constraint hierarchy levels.
- Command duration and bus occupancy.
- Interactions with conventional ACT, PRE, RD, WR, and refresh.
- Activation-window or rolling-history limits.
- Whether RowCopy timing depends on destination count beyond the repeated
  destination activation relationships.

### Missing reference information

The current material does not provide:

- Numeric PuD timings.
- Timing relationships with ordinary commands or refresh.
- Command-bus occupancy.
- Resource occupancy of `N`.
- Independently relevant timing boundaries for the internal `N` operations.
- Destination-count-dependent RowCopy timing, if any.

### Prerequisite decisions

- Resolve Decision Gate 8.
- Supply the timing and resource references listed above.

### Validation before proceeding

- Every timing boundary is illegal one cycle early and legal at the specified
  cycle.
- Repeated destination activations obey the accepted constraints for both short
  and long RowCopy destination lists.
- NOT timing matches the accepted abstraction of `N`.
- Same-bank and relevant cross-bank/rank effects are covered.
- Existing standard DDR4 timing remains unchanged.

### Completion criteria

- Every supported transition has source-backed timing behavior.
- `N` exposes no more internal timing structure than required by the accepted
  model.
- No PuD timing is inferred silently from ordinary DDR4.

## Phase 6 — Add controller-side sequence execution

### Objective

Translate each PuD request into its ordered, operand-specific command sequence.

### Relevant existing components

- `GenericDDRController::tick()`
- `ControllerBase` buffers and helpers
- `Request::command` and `Request::final_command`
- FR-FCFS schedulers
- Active-buffer promotion and retirement
- Device prerequisite and timing queries
- Refresh and row-policy hooks

### Expected code changes

- Add request-owned sequence progress if selected by Decision Gate 9.
- Select the correct operand address for every phase.
- Iterate through all RowCopy destinations without a fixed
  primitive-specific limit.
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

If Decision Gate 5 exposes internal `N` phases, the NOT sequence uses the
accepted expanded representation.

### Decision Gate 9 — Sequence ownership and scheduling atomicity

Define:

- Which layer owns request-specific operand ordering and sequence progress.
- Whether the device, controller, or both track operation ownership.
- Whether same-bank commands may interleave.
- Whether other-bank, rank, or channel commands may interleave.
- Whether sequence arrows require contiguous issue.
- Whether a PuD request reserves a bank or another resource.
- Whether `N` is indivisible at the scheduler level.
- Whether RowCopy may be interrupted between destination activations.
- Fairness expectations for variable-length RowCopy operations.

### Decision Gate 10 — Refresh and row-policy interaction

Define interaction with:

- Refresh requests.
- Open and ClosedCAP row policies.
- Priority maintenance commands.
- Controller plugins.
- Intermediate NOT state.
- Long-running RowCopy requests.

### Missing reference information

The available material does not specify:

- Atomicity or interleaving requirements.
- Reservation scope.
- Whether `N` or an internal phase is interruptible.
- Whether RowCopy may be interrupted between destination activations.

### Prerequisite decisions

- Resolve Decision Gates 9 and 10.
- Supply the atomicity, interleaving, and resource references required by those
  gates.

### Validation before proceeding

At the layer selected by Decision Gate 9:

- Every issued command uses the correct request operand row.
- RowCopy visits each destination exactly once and in submitted order.
- RowCopy works with one destination and longer destination lists.
- MAJ3 and MAJ5 issue the accepted variants for the correct operands and order.
- NOT issues the accepted `N` representation exactly once.
- The request does not retire before final precharge.
- Timing stalls do not lose, duplicate, or skip phases.
- Accepted contention and interleaving behavior is tested.
- Competing requests cannot corrupt PuD sequence progress or ownership.

### Completion criteria

- Valid requests for all four primitives deterministically produce their
  complete accepted sequences.
- Request-specific operand ordering and sequence ownership are enforced at the
  layer selected by Decision Gate 9.
- RowCopy sequence length is determined by its destination list rather than a
  hard-coded maximum.

## Phase 7 — Complete request lifecycle integration

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
- Invoke completion after final precharge.
- Add minimal approved PuD statistics.
- Prevent Read forwarding and Write coalescing from applying to PuD requests.

### Decision Gate 11 — Completion, queueing, and statistics semantics

Choose:

- Which buffer holds PuD requests.
- Whether PuD has a dedicated buffer.
- Whether variable-length RowCopy affects queue-capacity accounting.
- Callback timing.
- Required per-operation statistics.
- Whether latency is measured across the complete sequence.
- Whether PuD contributes to existing throughput counters.

### Prerequisite decisions

- Resolve Decision Gate 11.

### Validation before proceeding

- Admission failure leaves the request retryable and its operand list intact.
- Completion occurs exactly once after final precharge.
- RowCopy completion is independent of destination count except for modeled
  execution latency.
- NOT completes only after `N` and final precharge.
- Existing Read/Write completion and statistics remain unchanged.

### Completion criteria

- Each primitive has a complete and testable request lifecycle.
- Variable-length requests do not introduce ownership or lifetime errors.

## Phase 8 — End-to-end validation

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
- Verify preservation of destination order at the layer selected by Decision
  Gate 9.
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
- Verify any exposed internal `N` phases if Decision Gate 5 requires them.
- Verify accepted state, timing, resource, and scheduling behavior of `N`.
- Reject malformed requests and verify final cleanup.

Across all primitives:

- Verify accepted placement rules.
- Verify device state and prerequisites.
- Verify timing legality.
- Verify the accepted scheduling and interleaving policy.
- Verify refresh and row-policy behavior.
- Verify mixed ordinary/PuD traffic.
- Verify completion after final precharge.
- Run standard DDR4 regression tests unchanged.

Physical copy, majority, and inversion results are not validated because DRAM
data-value tracking is out of scope.

### Completion criteria

- RowCopy, MAJ3, MAJ5, and NOT execute end-to-end on DDR4_PuD.
- RowCopy supports one or more destinations without an arbitrary fixed maximum.
- Repeated RowCopy destination activations follow the accepted state semantics.
- `N` uses the minimum abstraction accepted at Decision Gate 5.
- Request-specific operand ordering and sequence ownership are handled at the
  layer selected by the corresponding decision gates.
- Every accepted modeling decision is covered by tests.
- Missing references are never replaced with undocumented assumptions.
- Existing standard DDR4 behavior remains unchanged.

## Decisions still requiring user approval

- Activation-command representation.
- Minimum simulator abstraction for `N`.
- Intermediate activation and NOT state.
- Mapping of reference `P` to Ramulator2 precharge.
- Conventional-command legality during PuD operations.
- Ownership of request-specific operand ordering and sequence progress.
- Atomicity and interleaving policy, including interruption between RowCopy
  destinations.
- Refresh, row-policy, and plugin interaction.
- Queueing, callback, completion, and statistics behavior.

## Missing reference information blocking implementation

- Simulator-visible intermediate activation behavior.
- State effects of repeated RowCopy destination activations.
- Numeric timings for PuD activation variants, `N`, and precharge.
- Timing relationships with ordinary commands and refresh.
- Command-bus and internal-resource occupancy.
- Whether internal `N` phases independently affect timing, legality,
  scheduling, interruptibility, or observable state.
- Atomicity and interleaving requirements for all primitives.
- Whether RowCopy may be interrupted between destination activations.
- Whether RowCopy timing or legality depends on destination count beyond the
  accepted repeated destination activation relationships.
