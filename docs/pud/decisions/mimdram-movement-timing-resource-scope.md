Status: Superseded

Superseded by
`docs/pud/decisions/mimdram-movement-timing-and-resource-model.md`.

Question

What initial timing/resource scope and inter-request concurrency fidelity
should the combined movement substrate use while preserving range-wide
LC-MOV execution and overlapping GB-MOV endpoint activations?

Decision

Adopt a primitive-first, Bank-conservative inter-request timing/resource
abstraction for the initial combined movement substrate.

One range-wide LC-MOV is one controller-sequenced invocation. Each of its six
movement roles collectively targets the entire accepted logical mat range,
and all selected mats progress through that role in lockstep using their local
datapaths. The number of issued roles and the modeled role timing are not
multiplied by the number of selected mats. In the evaluated four-HFF
organization, an LC-MOV selecting `N` mats represents an inferred aggregate
movement of `4N` bits.

Later resolution: the replacement command-identity decision in
`docs/pud/decisions/mimdram-movement-occurrences-and-command-identities.md`
preserves these six LC-MOV roles and the five GB-MOV roles below as command
occurrences, not unique semantic command types. This does not change the
timing/resource scope accepted here.

One singleton GB-MOV is one controller-sequenced invocation that retains
distinct ordered source and destination endpoint semantics and the derivable
same-chip directional-neighbor path. Its separately issued source- and
destination-activation roles may represent overlapping physical activation
intervals. The later timing graph must not require source activation to
physically finish before destination activation merely because the simulator
issues the two roles in successive ticks.

For concurrency between independent requests, movement command roles
targeting the same flat Bank are assigned to one conservative modeled
timing/resource domain. Independent LC-MOV and GB-MOV roles in that Bank
conflict with one another and with inherited DDR4_PuD command roles in that
Bank. Logical range, chip, mat, endpoint, and directional-path metadata remains
available for semantics, validation, and future refinement, but is not
initially used to permit same-bank independent-request concurrency. Different
Banks receive no new movement-specific conflict beyond later accepted shared
Rank/Channel timing constraints.

In this decision, a "conflict" means only that command roles are assigned to
the same conservative modeled timing/resource domain. It does not decide
whether that resource is continuously reserved between command roles, whether
another same-bank request may interleave between movement roles,
whole-request exclusion, ownership lifetime, atomicity, or preemption. Those
questions belong to Decision 5.

Use the existing hierarchy timing representation plus minimal movement-local
request/controller context. The minimum retained identities are the existing
Channel, Rank, BankGroup, and Bank coordinates; the accepted derived-subarray
placement context; LC-MOV's two Row/Column operands and one inclusive logical
mat range; GB-MOV's ordered Row/Column endpoints, singleton logical-mat IDs,
common logical-chip ID, and derivable directional-neighbor path; and the
current movement-role progress. An LC range collectively identifies the
selected local resources without creating one independently scheduled object
per mat.

Do not introduce a mat scoreboard, per-mat or per-link availability sidecar,
explicit Chip/Subarray/Mat hierarchy levels, a multi-address Device command,
or true same-cycle multi-command issue for this initial timing/resource
scope. The conclusion that no generic Ramulator architecture extension is
required applies specifically to the timing/resource representation selected
here. It does not decide whether later ownership or state decisions require
localized controller or device changes.

Future MIMDRAM-MIMD work may refine the conservative Bank domain with
mat/range/link availability and multiple same-bank contexts without changing
the accepted LC-MOV/GB-MOV request boundary, placement contract, or visible
command-role semantics.

Rationale

The accepted LC-MOV abstraction requires parallel work within one invocation,
not independent scheduling of each selected mat. Treating one range as one
collective target preserves its six-role sequence and inferred aggregate width
without multiplying command count or latency by range length.

The accepted GB-MOV command granularity preserves its two endpoint identities
as separate one-address roles. Ramulator issues them in different ticks, but
Bank-level directed constraints can still represent overlapping activation
intervals because issue order does not require the earlier physical interval
to complete before the later one begins.

MIMDRAM generally supports independent PUD operations on available mat ranges,
but it does not directly specify movement-specific LC/LC, LC/GB, GB/GB, or
movement/arithmetic-PUD compatibility and shared-resource rules. Enabling such
same-bank concurrency now would require project assumptions about mat,
global-I/O, and neighboring-link conflicts as well as multiple retained
same-bank contexts. The Bank-conservative domain avoids that unsupported
precision while preserving existing different-Bank parallelism.

The existing timing tree already provides Channel-, Rank-, BankGroup-, and
Bank-level directed command constraints. Request-owned endpoints and movement
metadata plus controller-held progress can preserve the accepted LC range and
GB endpoint semantics. Explicit lower hierarchy nodes or resource-availability
sidecars add no fidelity to this initial inter-request model.

Evidence

MIMDRAM source facts:

- `docs/pud/references/mimdram-inter-column-data-movement.md` records that
  MIMDRAM schedules independent PUD bbops across available mat ranges using a
  mat scheduler, a mat scoreboard, and multiple μProgram processing engines.
- The same reference records that a contiguous range shares state while
  executing one ACT-PRE sequence, and that each μProgram engine maintains the
  timing of its allocated operation.
- The reference records LC-MOV's one logical target range, one common source
  Row/Column pair, one common destination Row/Column pair, and local per-mat
  HFF/column-select datapath. Together these facts support the accepted
  range-wide lockstep inference, while the paper directly demonstrates only a
  singleton LC-MOV.
- The reference records that GB-MOV activates its source and destination rows
  in different mats concurrently and uses a directional neighboring-global-SA
  path. It does not establish the exact C/A-cycle relationship of the two
  activations.
- The reference does not explicitly establish pairwise concurrent execution
  or shared-resource/conflict rules for two LC-MOVs, two GB-MOVs, LC-MOV with
  GB-MOV, or movement with an arithmetic PUD operation.

Accepted project decisions:

- `docs/pud/decisions/mimdram-substrate-and-movement-request-boundary.md`
  defines one request as one architectural LC-MOV or GB-MOV invocation and
  preserves the inherited DDR4_PuD baseline.
- `docs/pud/decisions/mimdram-movement-range-and-placement.md` accepts one
  range-wide lockstep LC-MOV with inferred `4N`-bit aggregate movement in the
  evaluated organization, the initial singleton directional-neighbor GB-MOV
  subset, movement-specific logical metadata, the derived-subarray placement
  context, and the unchanged ordinary hierarchy.
- `docs/pud/decisions/mimdram-movement-occurrences-and-command-identities.md`
  accepts six visible LC-MOV occurrences and five visible GB-MOV occurrences,
  represents GB activation endpoints as separate one-address occurrences,
  requires their physical activation intervals to be able to overlap, and
  rejects true same-cycle multi-command issue and a combined multi-address
  Device command.

Repository evidence:

- `src/ramulator/dram/impl/DDR4_PuD.cpp` uses the hierarchy `[Channel, Rank,
  BankGroup, Bank, Row, Column]`.
- `src/ramulator/dram/node.cpp` builds timing nodes through Bank and applies
  directed constraints along one hierarchical address path.
- `src/ramulator/dram/device.h` and `src/ramulator/dram/func_types.h` expose
  one-command, one-address timing, prerequisite, and Bank-level action
  interfaces.
- `src/ramulator/controller/impl/generic_ddr_controller.cpp` issues at most
  one command per tick and already retains request-owned operands and monotonic
  controller sequence progress.

Open issues

- Exact numeric timing values and directed timing edges, including `tRAS`,
  `tRP`, `tWR`, and `tRELOC` relationships.
- The exact GB-MOV activation-role issue gap and whether it affects aggregate
  latency.
- CK conversion and quantization of each independently enforced edge.
- Movement command encoding and command-bus occupancy.
- Movement treatment under `tRRD`, `tFAW`, and other shared Rank/Channel
  constraints.
- Resource acquisition, continuous reservation, ownership lifetime, release,
  whole-request exclusion, atomicity, preemption, and phase interleaving.
- Persistent movement state and legality, including LC retained-payload
  visibility, GB dual-active-endpoint or transfer-path visibility, and exact
  movement close/precharge behavior.
- Interaction with ordinary requests, inherited PUD requests, row policy,
  maintenance, refresh, priority work, and plugins.
- Terminal recovery, sequence retirement, request departure, callback, and
  statistics-completion boundaries.
- Movement Column units, valid range, alignment, and detailed transfer
  quantization.
- Future mat/range/link availability, μProgram-engine capacity, multiple
  same-bank contexts, and movement-specific pairwise concurrency rules.
