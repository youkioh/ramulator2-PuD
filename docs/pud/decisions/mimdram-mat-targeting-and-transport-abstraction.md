Status: Superseded

Its addressing and logical-mat-targeting authority is superseded by
`docs/pud/decisions/mimdram-movement-addressing-geometry-and-payload.md`.
Its T3 mat-information-transport authority is superseded by
`docs/pud/decisions/mimdram-movement-timing-and-resource-model.md`.

Question

What minimum mat-targeting representation and mat-information-transport
fidelity should the initial LC-MOV/GB-MOV substrate use before movement
command granularity and role-dependent Device state are revalidated?

Decision

Retain the combined movement substrate's existing hierarchy:

```text
[Channel, Rank, BankGroup, Bank, Row, Column]
```

Do not add explicit Chip, Subarray, or Mat hierarchy nodes, per-mat open-row
state, or a mat scoreboard for the initial LC-MOV/GB-MOV substrate.

Keep LC-MOV's accepted logical mat range as authoritative metadata in the
retained request/controller throughout execution. Keep GB-MOV's ordered
logical source and destination mat endpoints as authoritative metadata in the
retained request/controller throughout execution.

The controller sequence associates every later-visible LC-MOV and GB-MOV
`ACT`, `RD`, `WR`, and `PRE` occurrence with its semantic target range or
endpoint. This association does not decide exact Ramulator command IDs,
whether ordinary command handlers can be reused, command granularity, or exact
Device-state transitions. Those questions belong to the revalidation of the
movement command-granularity decision.

Device-visible Bank state may aggregate the physical phase of the selected-mat
operation for legality and resource modeling without storing individual
logical mat IDs or active rows. A Bank-level aggregate simulator state does
not mean that the physical MIMDRAM `ACT`, `RD`, `WR`, or `PRE` targets the
entire Bank.

Use T3 mat-information-transport fidelity initially. Do not explicitly model
the per-chip mat queue or `ACT-enqueue`, `PRE-enqueue`, and `ACT-dequeue` as
LC-MOV/GB-MOV Device commands. The initial simulator therefore does not model:

- the evaluated eight-entry mat-queue capacity or queue pressure;
- mat-information C/A-bus contention; or
- transport-specific cross-Bank or Rank throughput effects.

This is an explicit simulator scope abstraction. It does not mean that
mat-information transport has zero physical cost, that MIMDRAM lacks a mat
queue or its enqueue/dequeue command variants, or that physical movement
commands operate at whole-Bank granularity.

The initial LC-MOV/GB-MOV timing model may use the published movement timing
structure without separately exposing mat-information transport, while
documenting that transport-induced contention is outside the initial model.

Revisit the transport and Device-context boundary before adding:

- command-bus-accurate mat-transport throughput;
- mat-queue pressure;
- same-Bank disjoint-mat MIMD;
- mat-selective ordinary-command coexistence; or
- Device legality, timing, or resource behavior whose result depends on
  individual mat identity.

This decision supports and does not supersede the accepted movement
range/placement decision. That decision remains unchanged. The currently
accepted movement command-granularity decision must be revalidated next under
this boundary. Revalidate the exact role-dependent Device
state/prerequisite/action model only after command granularity is resolved;
neither downstream decision is modified or superseded here.

Rationale

MIMDRAM physically selects contiguous sets of DRAM mats using logical range
identifiers communicated by the controller. A selected range shares one
ACT-PRE sequence/state, so initial range-wide LC-MOV execution does not require
independent per-mat progress or open-row state. Singleton GB-MOV still requires
distinct ordered endpoint semantics, but those identities remain available in
the retained request while whole-Bank ownership prevents independent same-Bank
work from observing or interfering with either endpoint.

The existing Bank-level Device representation can therefore preserve the
legality and timing phases required by the initial Bank-conservative model
without claiming that the underlying physical operation targets the whole
Bank. Explicit Mat hierarchy or dynamic Device context would add fidelity only
when legality, timing, or arbitration can distinguish selected mats within one
Bank.

MIMDRAM explicitly defines a per-chip mat queue and transport command variants,
but the source does not provide the LC-MOV/GB-MOV-specific mapping needed to
place every enqueue and dequeue in their command sequences or determine their
contribution to published movement latency. Abstracting that transport avoids
inventing a schedule while preserving a clear refinement boundary for later
command-bus or queue-sensitive studies.

Evidence

MIMDRAM source facts:

- `docs/pud/references/mimdram-inter-column-data-movement.md` records the
  logical range interface, per-chip translation to a selected physical mat
  range, shared ACT-PRE state within a selected range, and LC-MOV/GB-MOV
  semantic targets.
- The same reference records the general `ACT-enqueue`, `PRE-enqueue`, and
  `ACT-dequeue` mechanism, the evaluated eight-entry mat queue, and the source
  gaps in applying that mechanism specifically to LC-MOV and GB-MOV.
- The reference records LC-MOV's published timing structure and GB-MOV's
  published timing structure with overlapping source and destination
  activation.

Accepted project decisions:

- `docs/pud/decisions/mimdram-substrate-and-movement-request-boundary.md`
  keeps movement in a distinct combined substrate and places request lifecycle
  and sequencing in the controller.
- `docs/pud/decisions/mimdram-movement-range-and-placement.md` keeps the
  ordinary hierarchy unchanged, retains movement-specific logical-mat
  metadata in the request, accepts range-wide lockstep LC-MOV, and accepts an
  initial singleton ordered GB-MOV subset.
- `docs/pud/decisions/mimdram-movement-timing-resource-scope.md` selects an
  initial Bank-conservative inter-request timing/resource abstraction without
  an explicit Mat hierarchy or mat scoreboard.
- `docs/pud/decisions/mimdram-movement-ownership-and-atomicity.md` makes the
  retained active request the authoritative Bank owner and excludes
  independent same-Bank work throughout the protected sequence.

Repository evidence:

- `src/ramulator/base/request.h` provides request-owned operand storage and
  retained sequence progress.
- `src/ramulator/dram/impl/DDR4_PuD.cpp` uses the hierarchy `[Channel, Rank,
  BankGroup, Bank, Row, Column]`.
- `src/ramulator/dram/node.h`, `src/ramulator/dram/device.cpp`, and
  `src/ramulator/dram/func_types.h` provide Bank-level state/action dispatch
  without request-owned dynamic metadata in Device handler calls.

Open issues

- Revalidation of movement command granularity, including ordinary
  `ACT`/`RD`/`WR`/`PRE` reuse versus movement-specific variants and command
  type versus command occurrence.
- Whether GB-MOV's two activation occurrences require distinct simulator
  command identities.
- Movement `RD`/`WR` internal-I/O semantics versus ordinary external-I/O
  command semantics.
- Movement `PRE` reuse, LC-MOV HFF retention, and exact physical movement
  precharge scope.
- Minimum role-dependent Device state, prerequisites, and actions after
  command granularity is resolved.
- Exact directed timing correspondence to the published LC-MOV and GB-MOV
  timing structures.
- LC-MOV/GB-MOV-specific enqueue/dequeue orchestration and whether transport
  affects their published latency.
- A future T1 or T2 model of command-bus occupancy, queue capacity/pressure,
  and transport-specific cross-Bank or Rank throughput.
- Future same-Bank disjoint-mat MIMD and any resulting per-mat legality,
  timing, or resource representation.
