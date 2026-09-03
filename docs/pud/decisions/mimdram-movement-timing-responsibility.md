Status: Superseded

Superseded by
`docs/pud/decisions/mimdram-movement-timing-and-resource-model.md`.

Question

How should the initial MIMDRAM movement model divide command-occurrence
timing readiness between the retained controller PuD primitive execution
context and the DRAM Device timing machinery?

Decision

Use two complementary timing domains when deciding whether a movement command
occurrence may issue. The occurrence must be request-eligible, prerequisite-
compatible, PuD primitive-local-timing-ready, and Device-timing-ready. Failure
of any condition prevents that occurrence from issuing.

The retained controller PuD primitive execution context owns timing
relationships whose meaning depends on occurrence identity or primitive
structure. This includes dependencies on a particular earlier occurrence of a
repeated semantic command, source-versus-destination roles, LC-versus-GB
structure, and other occurrence-specific relationships that one unconditional
semantic-command timing edge cannot represent faithfully. The context may
retain the minimum issue history needed to compute the next occurrence's local
ready cycle, including the maximum imposed by multiple predecessors. This
decision does not mandate its C++ representation.

Implement primitive-local timing through one localized, generalizable
mechanism rather than LC-MOV/GB-MOV request-type conditionals scattered through
the controller or scheduler. MIMDRAM movement is its initial user. Existing
DDR4_PuD primitives need not migrate unless later implementation planning finds
that generalization clearly beneficial.

The existing Device timing machinery remains authoritative for
context-independent DRAM protocol, resource, and recovery constraints that can
be represented correctly using the hierarchy, command identity, and command
history without request context. This includes accepted Bank, BankGroup, Rank,
or Channel constraints and recovery rules such as precharge or refresh
recovery. Primitive-local timing supplements rather than replaces Device
timing and `Device::check_ready` or its generated timing graph.

Classify each later timing constraint as follows:

- Use controller primitive-local timing when readiness depends on a repeated
  command's particular predecessor occurrence, source or destination role,
  LC or GB structure, or another occurrence-specific relationship that cannot
  be expressed faithfully by one unconditional semantic-command edge.
- Use Device timing when the constraint is a general DRAM resource or recovery
  rule, applies independently of primitive occurrence identity, and fits the
  existing hierarchy/command timing model without request context.

Do not enforce the same constraint in both domains unless a later
implementation audit explicitly establishes that duplication is necessary and
harmless.

Do not introduce timing-only command identities. The accepted semantic command
identities remain `ACT_MOV`, `RD_MOV`, `WR_MOV`, and `PREpb`; the controller's
occurrence-aware context distinguishes timing roles without separate history
buckets. Any future need for an alias requires a new explicit decision.

The accepted Device states remain `MovementActive` and `MovementDataValid`.
They represent aggregate legality and physical-condition information, not
timing readiness or physical completion. Primitive-local timing must not be
encoded as additional Device states. A Bank may therefore already be
`MovementActive` while the next occurrence remains locally blocked, and a
terminal `PREpb` may close it at issue while Device recovery still prevents a
later opening.

An active movement whose next occurrence is not primitive-local-timing-ready is
not issueable in that cycle, but it does not reserve the controller or Channel
while waiting. Other eligible work outside its owned Bank may still be
selected, subject to the accepted ownership, arbitration, and shared-resource
rules. This preserves different-Bank progress without changing the arbitration
policy.

The mechanism may support future PuD primitives with occurrence-relative
timing, but this decision does not add same-Bank mat-level MIMD, a mat
scoreboard, multiple simultaneous primitive contexts, or an explicit Mat
hierarchy. It uses only the retained active primitive context already required
by accepted sequencing and ownership decisions.

Exact LC-MOV and GB-MOV timing values, directed edges, history distances, and
quantization are deferred to the next timing decision. The simulator continues
to issue at most one command per tick while allowing the represented physical
activation intervals of the two GB `ACT_MOV` occurrences to overlap. This does
not decide whether those activations occupy different command/address cycles in
the described hardware.

Later resolution: `docs/pud/decisions/mimdram-movement-numeric-timing-and-directed-edges.md`
accepts the initial numeric parameters, directed edges, history selection, and
quantization under this responsibility boundary.

Rationale

Conventional command-history timing is sufficient when hierarchy node and
semantic command identity identify the relevant predecessor. GB-MOV instead
has source and destination `ACT_MOV` occurrences that can remain
simultaneously timing-relevant. A later occurrence may depend on a selected
earlier `ACT_MOV` even after another `ACT_MOV` has become the most recent
history entry. The required predecessor can also vary with primitive and
occurrence role. Static command-ID timing edges cannot always express that
selection cleanly without artificial command identities.

A memory controller tracks issued commands and the protocol timing needed to
schedule subsequent commands. Ramulator's Device state and timing objects are
software abstractions of DRAM protocol and resource behavior, not literal
cycle-by-cycle state feedback from the DRAM chip. Retaining occurrence issue
times in the controller's active primitive context is therefore consistent
with controller command scheduling. This is an accepted simulator
architecture, not a claim that the MIMDRAM source specifies the implementation
of LC-MOV or GB-MOV timing logic.

Keeping context-independent constraints in Device timing preserves the shared
DRAM resource model, while the controller context supplies only the
primitive-relative information that Device command history lacks. Treating
local readiness as part of candidate issueability also avoids turning an
internal movement delay into unnecessary cross-Bank blocking.

Evidence

- `docs/pud/decisions/mimdram-movement-occurrences-and-command-identities.md`
  accepts the five-occurrence GB sequence, shared movement command identities,
  separately visible source and destination activations, and one-command-per-
  tick issue while preserving overlapping physical activation intervals.
- `docs/pud/decisions/mimdram-movement-timing-resource-scope.md` accepts the
  existing hierarchy timing representation plus movement-local request and
  controller context, a Bank-conservative inter-request domain, and no new
  movement-specific conflict between different Banks.
- `docs/pud/decisions/mimdram-movement-ownership-and-atomicity.md` retains the
  active request as Bank owner and the controller cursor as sequence authority,
  excludes conflicting work in the owned Bank, and permits unrelated work in
  other Banks subject to normal arbitration and resources.
- `docs/pud/decisions/mimdram-movement-minimum-device-state-and-actions.md`
  accepts `MovementActive` and `MovementDataValid` as aggregate Device states
  and keeps directed timing separate from state transitions.
- `docs/pud/decisions/mimdram-mat-targeting-and-transport-abstraction.md`
  retains request/controller-owned logical targeting without adding explicit
  Mat hierarchy or per-mat Device state.
- `src/ramulator/dram/node.h` and `src/ramulator/dram/node.cpp` store command
  issue history per hierarchy node and command identity and evaluate static
  directed timing constraints using configured history distances.
- `src/ramulator/controller/impl/generic_ddr_controller.cpp` retains active
  request progress, asks the scheduler for ready work, validates timing before
  issue, and can continue to other queues when no active candidate is ready.
- The FRFCFS scheduler implementations compare active candidates using the
  controller timing-readiness query, so primitive-local readiness must
  participate in that same candidate-level readiness path to preserve
  different-Bank progress.

Open issues

- The exact numeric LC-MOV and GB-MOV timing graph, parameters, directed edges,
  history relationships, and independent CK quantization.
- The exact localized controller representation and API for primitive-local
  dependency data and occurrence issue history.
- The implementation audit needed to integrate composite readiness consistently
  into scheduler candidate comparison and final pre-issue validation.
- Which accepted context-independent movement constraints belong at Bank,
  BankGroup, Rank, or Channel scope.
- Whether later implementation work would benefit from sharing the mechanism
  with existing DDR4_PuD primitives.
