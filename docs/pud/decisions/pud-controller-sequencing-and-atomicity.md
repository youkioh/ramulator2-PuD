Status: Accepted

Question

What controller sequencing, ownership, interleaving, and fairness policy should
apply while a PuD request executes its lower-level command sequence?

Decision

Use bank-scoped ownership and atomicity for each PuD request, but do not add a
separate bank-to-owner table. After the first PuD activation, retain that PuD
request in the controller's active buffer. The retained active PuD request is
the authoritative continuation request for its target bank, and the
controller derives ownership and eligibility from it. Do not add primitive
ownership or sequence progress to DRAM device state.

From the first PuD activation through the final `PREpb`, the target bank is
owned by the retained active request. Before prerequisite resolution, reject
any other candidate whose command scope intersects that bank. This applies to
ordinary requests, other PuD requests, row-policy requests, refresh and other
priority maintenance, and plugin-generated requests. The owner remains alive
until final `PREpb` issues and releases the bank.

Track request progress with the minimum monotonic phase/operand cursor needed
to derive the next command and operand from the request type and its stored
operands. Promote the request to the active buffer only after its first PuD
activation. Later PuD activations advance that retained request in place even
though their command metadata is opening; do not re-promote it after every
PuD activation.

The required command-role ordering is:

- RowCopy issues source `ACT_PUD_S_OC` first, issues `ACT_PUD` exactly once
  for every destination, and issues final `PREpb` last. Destination order is
  not a physical correctness requirement in the accepted model.
- MAJ3 and MAJ5 issue first `ACT_PUD_OC`, the required intermediate
  `ACT_PUD` commands, final `ACT_PUD_S`, and `PREpb` in that role order. The
  order among equivalent intermediate `ACT_PUD` operands is not a
  simulator-visible physical requirement.
- NOT issues `ACT_PUD_S_OC`, exactly one `N`, and final `PREpb`.

Preserve submitted operand order as the deterministic traversal and role
assignment convention for implementation and testing. This convention does
not claim that RowCopy destination order or the order among equivalent
majority intermediates affects physical correctness.

Commands targeting non-owned banks may issue between PuD commands when legal
under all existing DDR4 and PuD timing constraints. Sequence arrows therefore
specify ordered execution, not contiguous channel issue.

Retain RowCopy bank ownership across its entire destination list. Other-bank
work may issue between destination activations, but do not introduce a
destination quantum, same-bank preemption, or sequence save-and-restore
mechanism. Variable-length RowCopy receives no special fairness mechanism
beyond timing-ready scheduling of active requests and the fact that its
finite destination list eventually completes.

`N` remains one issued lower-level command under the accepted Gate 5
abstraction. The surrounding NOT sequence has the same bank-scoped ownership
as the other primitives.

This is an explicit simulator modeling decision, not a verified physical
atomicity or reservation requirement. This decision does not define refresh,
row-policy, priority-maintenance, or controller-plugin interaction; those
remain Decision Gate 10.

Rationale

The accepted phase-only device state cannot record how many RowCopy
destinations, intermediate majority activations, or NOT phases have completed.
A monotonic request cursor is therefore required, but a separate owner record
is redundant when the initiating request remains active until final
precharge. The active request supplies both continuation identity and progress.

Eligibility must be checked before prerequisite resolution because
conventional command prerequisites reject PuD states, while commands such as
`PREpb`, `ACT_PUD`, or `N` can be phase-legal without belonging to the active
primitive. The active-request rule prevents both invalid prerequisite queries
and phase-legal interruption without adding ownership to device state.

Allowing unrelated-bank work uses the accepted target-bank-local PuD timing
and resource model. Channel-wide atomicity would unnecessarily idle unrelated
banks during PuD timing gaps, while same-bank interleaving would require
unsupported interruption or context-restoration semantics. Holding the active
request for the complete RowCopy destination list preserves sequence
correctness without inventing a destination quantum.

The accepted device states and timings do not distinguish one RowCopy
destination ordering from another or distinguish permutations of equivalent
intermediate majority activations. A deterministic cursor through submitted
operands is sufficient and avoids a variable-size completion bitmap.

Evidence

Ramulator2 issues at most one command per controller cycle and can select work
from another bank when an active request is timing-stalled. Its active buffer
retains a request after an opening command. LPDDR split activation also shows
that the continuing request, rather than device state alone, must remain
identifiable, although LPDDR uses additional ACT2 deadline state that the PuD
model does not require. The accepted Gate 8 model makes PuD constraints
target-bank-local, assigns one CK of command-bus occupancy per command, and
imposes no additional restriction on unrelated banks.

The accepted PRADA command model distinguishes the first offset-cancelled
activation, intermediate unsensed activations, and final sensing activation.
Within each equivalent intermediate or RowCopy-destination class, the accepted
state and timing model gives every command the same simulator-visible effect.

The available PuD reference does not establish physical atomicity,
interleaving, reservation scope, or interruption behavior. The policy above is
therefore accepted as a simulator modeling choice rather than source-backed
physical behavior.

Open issues

- Refresh, row-policy, priority-maintenance, and controller-plugin interaction
  remain unresolved at Decision Gate 10.
- Physical validation of PuD atomicity, reservation scope, and interruption
  behavior remains unavailable.
- The available reference does not physically validate arbitrary RowCopy
  destination ordering or majority-operand permutation. Their equivalence is
  limited to the accepted simulator-visible state and timing model.
