Status: Superseded

Superseded by
`docs/pud/decisions/mimdram-movement-minimum-device-state-and-actions.md`.

Question

What minimum Device-visible state, prerequisite policy, action semantics, and
ordinary-command legality should the initial LC-MOV and GB-MOV model use?

Decision

Use the existing Bank node state as the sole Device-visible representation of
active LC-MOV and GB-MOV phases. Do not use conventional `Opened` or the
conventional row-state map to represent movement endpoint activation.

This decision depends on the currently accepted command granularity in
`docs/pud/decisions/mimdram-movement-command-granularity.md`: LC-MOV exposes
six movement-specific roles and GB-MOV exposes five movement-specific roles.
The number and meaning of the aggregate movement phase states below follow
those visible role boundaries. This dependency is not a claim that the
accepted command granularity is the only valid abstraction of MIMDRAM. If
that decision is later superseded by a more aggregate or hybrid LC-MOV or
GB-MOV representation, this Device-state decision must be revalidated and may
also need to be superseded. Do not reopen or alter the accepted
command-granularity decision here.

Represent LC-MOV with these five conceptual aggregate Bank phases:

```text
LC source active
LC source captured
LC payload retained after source close
LC destination active
LC transfer committed
```

Represent GB-MOV with these four conceptual aggregate Bank phases:

```text
GB source activated
GB both endpoints activated
GB source path valid
GB transfer committed
```

The exact implementation identifiers for these states are not prescribed
here. These states represent only the physical distinctions required for
movement-role legality. They do not store transferred data, request identity,
source or destination addresses, logical mat identity or range, per-mat
progress, timing progress, or the identity of the next intended command.

Keep operation identity, both ordered operands, LC range metadata, GB endpoint
metadata, and monotonic movement-role progress in the retained controller
request. Do not add a separate HFF-valid flag, global-SA/link-valid flag,
source/destination active-row record, per-mat state, mat scoreboard, or owner
table. Retained-payload and source-path validity are implicit invariants of
the corresponding aggregate phase.

All movement roles use one-address, single-Bank Device dispatch. One LC state
collectively represents all selected mats executing in lockstep; it does not
identify the range or imply that every physical mat in the Bank participates.
One GB state collectively represents the owned ordered endpoint pair; the
endpoint identities remain in the request. Do not insert movement rows into
the conventional row-state map.

Require a conventional `Closed` Bank before the first movement-specific role.
If the Bank is conventionally `Opened`, return ordinary `PREpb` as a
preparatory prerequisite. That `PREpb` does not acquire movement ownership and
does not advance the movement cursor. If unrelated work invalidates the
preparation before the first movement role issues, the prerequisite may be
resolved again. A first movement role presented in an inherited-PuD or
movement intermediate state is illegal.

During an active movement, each role is legal only in its defined predecessor
phase and returns itself from prerequisite resolution. A phase mismatch is an
illegal-state error. Do not synthesize an earlier or later movement role, and
do not use ordinary `ACT` or precharge commands to repair an out-of-order
movement sequence. Timing readiness remains a separate check after state
legality. The controller cursor remains authoritative for selecting the
intended movement role and advances only when that role itself issues.

Use these LC-MOV action transitions:

| Role | Required state | Resulting state and abstract action |
| --- | --- | --- |
| Source activation | `Closed` | Enter LC-source-active; do not populate conventional row state. |
| Source read/capture | LC-source-active | Enter LC-source-captured; retained-payload validity becomes implicit. |
| Source retained-close | LC-source-captured | Enter LC-payload-retained; the source is abstractly closed while the payload remains valid. |
| Destination activation | LC-payload-retained | Enter LC-destination-active; retained-payload validity remains implicit. |
| Destination write/commit | LC-destination-active | Enter LC-transfer-committed; model commitment without modeling data values. |
| Destination close | LC-transfer-committed | Enter conventional `Closed`, clear conventional row state defensively, and invalidate all implicit LC movement conditions. |

Use these GB-MOV action transitions:

| Role | Required state | Resulting state and abstract action |
| --- | --- | --- |
| Source activation | `Closed` | Enter GB-source-activated; do not populate conventional row state. |
| Destination activation | GB-source-activated | Enter GB-both-endpoints-activated, representing overlapping activation abstractly. |
| Source read/drive | GB-both-endpoints-activated | Enter GB-source-path-valid; HFF/global-SA path validity becomes implicit. |
| Destination write/transfer | GB-source-path-valid | Enter GB-transfer-committed; model commitment without modeling data values. |
| Terminal close | GB-transfer-committed | Enter conventional `Closed`, clear conventional row state defensively, and invalidate all implicit GB movement conditions. |

The GB transition to both-endpoints-activated records the logical movement
phase established by the two issued activation roles. It does not mean the
source activation interval must finish before destination activation begins.
The later timing graph must preserve the accepted ability of the physical
activation intervals to overlap.

Ordinary `ACT`, `RD`, `WR`, auto-precharge accesses, `PREpb`, `PREab`, refresh,
and refresh-related close operations are illegal whenever their complete
scope includes a Bank in any movement phase. They must not abort, reset, or
repair a movement. Controller ownership eligibility remains the primary
protection and rejects independent intersecting work before prerequisite
resolution; Device illegality is a defensive invariant for direct Device
tests, controller bugs, and future paths. This defines active-state legality
only and does not add a refresh-interruption or deadline policy.

The terminal movement-close role is movement-specific. When it issues, its
Device action returns the Bank to conventional `Closed`, clears conventional
row state, and removes all implicit retained-payload, endpoint-activation,
and transfer-path validity. Controller Bank ownership is released at that
same issue point. Later timing constraints may keep subsequent commands
unready while the Bank is already logically `Closed`; timing recovery and
external request completion remain separate.

Do not expose MIMDRAM's `ACT-enqueue`, `PRE-enqueue`, `ACT-dequeue`, or mat
queue as additional Device states or commands in the initial movement model.
The accepted movement roles and request-owned logical-mat metadata abstract
the required mat-information transport. Exact command-bus behavior is not
decided here.

No generic Ramulator hierarchy, multi-address command, same-cycle issue,
Device-function, or timing API extension is required for this state,
prerequisite, and action model. Existing Bank states, one-address command
handlers, `BankTarget::Single`, prerequisite/action function pointers, and
command-history timing can represent it. Movement-aware legality for ordinary
single-Bank and all-Bank close/refresh paths must use those existing
interfaces.

This initial Bank-aggregate model may later be refined to per-range or per-mat
contexts if MIMDRAM-MIMD concurrency is accepted. The request already retains
the metadata needed for such a refinement, and the accepted movement roles
need not change. A refinement must revisit ownership eligibility,
conventional-row coexistence, movement close scope, and timing dispatch. Do
not prebuild that finer-grained state now.

Rationale

MIMDRAM physically retains LC source data in HFFs across the source precharge
and physically overlaps GB source and destination row activation. Those facts
require the simulator to preserve the legality of distinct movement phases,
but they do not require payload values, two conventional open-row entries, or
explicit circuit objects. Each accepted visible role changes a condition
needed to make the following role or terminal close legal, so one aggregate
state at each intervening role boundary is the minimum robust phase model for
the currently accepted command granularity.

Controller-only progress with no movement state would leave the Bank in a
conventional state and could make ordinary commands appear legal. One coarse
active marker would block ordinary commands but could not reject source close
before capture, destination activation before retained payload, destination
write before destination activation, or terminal close before transfer. The
selected phases enforce these physical-legality boundaries without moving
request identity or detailed sequence bookkeeping into the Device.

An orthogonal HFF, payload, global-SA, or link-valid flag would duplicate
information already implied by the aggregate phase and permit meaningless
state combinations. Per-mat state would add no initial fidelity because an LC
range executes in lockstep and one retained request continuously owns the
Bank; GB likewise has one owned endpoint pair. Whole-Bank ownership already
prevents independent same-Bank interference.

Using conventional `Opened` would be incorrect for the accepted abstraction.
Ordinary `ACT` records one Row coordinate in a Bank-wide row map, while GB may
physically have two rows in different mats active and logical mat identity is
not part of the ordinary address hierarchy. The current row map cannot
distinguish equal Row coordinates in different mats. Conversely, leaving the
Bank conventionally `Closed` during movement would expose ordinary commands.
Movement-specific Bank states preserve the physical distinction without
inventing a detailed mat hierarchy.

Requiring conventional `Closed` before the first role is conservative and
preserves ordinary-data correctness. The current flat Bank abstraction cannot
prove that an ordinary open row resides in a physically nonconflicting mat.
Reusing preparatory `PREpb` also preserves the accepted ownership boundary:
preparation occurs before the first movement-specific role and therefore does
not acquire ownership or advance progress.

Making out-of-order active roles illegal rather than synthesizing other
movement roles preserves the accepted controller sequence. Prerequisites
prepare an eligible intended role; they do not replace the architectural
movement program. Separating state legality from command-history timing also
allows the later timing graph to express every accepted LC/GB edge, including
GB activation overlap, without encoding delay in Device state.

Terminal cleanup at issue makes the Bank logically available when accepted
ownership ends. Directed timing can independently enforce physical recovery,
and lifecycle logic can independently choose the external completion point.

Evidence

- `docs/pud/references/mimdram-inter-column-data-movement.md` records LC-MOV's
  source `ACT -> RD -> PRE`, HFF retention across source `PRE`, destination
  `ACT -> WR -> PRE`, GB-MOV's concurrent source/destination activation,
  source HFF/global-SA path after `RD`, destination consumption after `WR`,
  and terminal precharge/recovery. It explicitly distinguishes those physical
  conditions from required simulator-visible state.
- `docs/pud/decisions/mimdram-movement-command-granularity.md` accepts six
  LC-MOV roles and five GB-MOV roles, separate one-address GB activation
  roles, overlapping physical activation intervals, and controller-owned
  monotonic progress. This decision is conditional on that accepted role
  boundary.
- `docs/pud/decisions/mimdram-movement-range-and-placement.md` accepts
  range-wide lockstep LC-MOV, singleton directional-neighbor GB-MOV, an
  unchanged ordinary hierarchy, and request-owned logical-mat metadata.
- `docs/pud/decisions/mimdram-movement-timing-resource-scope.md` accepts an
  initial Bank-conservative inter-request domain and rejects an initial mat
  scoreboard, per-link sidecar, or explicit Mat hierarchy.
- `docs/pud/decisions/mimdram-movement-ownership-and-atomicity.md` accepts
  retained-request Bank ownership from the first movement-specific role
  through terminal-close issue, pre-prerequisite conflict rejection, and
  controller-owned monotonic sequence progress.
- `src/ramulator/dram/node.h` stores one state and one Row-keyed state map in
  each Bank node, while hierarchy traversal is used for timing.
- `src/ramulator/dram/commands/ACT.h` makes ordinary `ACT` set `Opened` and
  insert one Row entry. `src/ramulator/dram/commands/PREpb.h` makes ordinary
  `PREpb` set `Closed` and clear that map. `src/ramulator/dram/commands/PREab.h`
  applies the same cleanup across its all-Bank target scope.
- The current DDR4_PuD command handlers store only `PuDChargeSharing` and
  `PuDSensed`, reject conventional accesses through prerequisite state checks,
  and leave primitive identity and exact progress to
  `src/ramulator/controller/impl/generic_ddr_controller.cpp`.
- `src/ramulator/dram/device.cpp` already separates prerequisite resolution,
  hierarchical timing checks, and Bank-level actions. Its BankTarget dispatch
  supports both single-Bank movement roles and movement-aware validation of
  broader close/refresh scopes without a new Device API.
- Current DDR4_PuD tests verify preparatory `PREpb`, exact retained-request
  sequences, cursor preservation across prerequisites, rejection of ordinary
  accesses in PuD phases, same-Bank ownership exclusion, different-Bank
  progress, final cleanup, and ownership release separate from completion.

Open issues

- Timing: exact numeric LC/GB directed edges; mapping of `tRAS`, `tRP`, `tWR`,
  and `tRELOC`; the GB activation-role issue gap; CK quantization; command
  encoding and command-bus occupancy; `tRRD`, `tFAW`, and other shared
  Rank/Channel constraints; terminal recovery duration and constrained
  successor commands.
- Maintenance: refresh deadlines and maximum deferral, credit or retention
  guarantees, admission near a refresh deadline, priority-buffer overflow,
  scope-aware priority bypass, and physical validation of row-policy and
  behavior-changing plugin interaction.
- Lifecycle: exact request departure, callback, statistics-completion, and
  modeled data-availability cycles; movement completion ordering relative to
  inherited PuD and ordinary requests; movement queueing and mixed-traffic
  arbitration details.
- Column: movement Column unit and valid range, mapping to the HFF-selected
  datapath, alignment, detailed transfer quantization, GB width
  interpretation, and any address progression above one invocation.
- Statistics: movement accepted/completed counters, latency boundaries,
  pending-queue occupancy, whether moved-bit or range-length metrics are
  meaningful, and whether movement is excluded from existing byte-throughput
  and row-hit statistics.
