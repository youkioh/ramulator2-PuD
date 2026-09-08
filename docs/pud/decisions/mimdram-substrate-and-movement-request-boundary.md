Status: Accepted

Question

Where should MIMDRAM inter-column movement live relative to the completed
DDR4_PuD baseline, and what does one externally submitted movement request
represent?

Decision

Introduce MIMDRAM LC-MOV and GB-MOV in a distinct combined experimental DRAM
standard derived at the Python-definition level from DDR4_PuD. Independently
copy inherited mutable standard definitions before extending them. Leave the
existing DDR4 and DDR4_PuD standards unchanged.

The combined standard inherits existing DDR4_PuD RowCopy, MAJ3, MAJ5, and NOT
behavior without changing their semantics. Movement-specific addressing,
state, ownership, and timing choices do not retroactively become DDR4_PuD or
PRADA properties.

Represent LC-MOV and GB-MOV as distinct architectural request types. One
submitted request is one LC-MOV or one GB-MOV invocation. The controller owns
the request lifecycle and the sequencing boundary for its visible movement
occurrences. Detailed operands, placement, payload, execution, Device state,
and timing are defined by the other canonical movement decisions rather than
duplicated here.

The initial request boundary does not include ISA-level `bbop_mov` lowering,
array placement, a batch of movement invocations, multi-invocation
orchestration, vector-reduction orchestration, automatic multi-hop routing, a
software frontend, or the full MIMDRAM control stack. Those mechanisms may
later construct or coordinate LC-MOV/GB-MOV requests, but are not part of one
architectural movement request.

Reuse shared request, controller, scheduler, Device, and completion
infrastructure only where their abstractions fit. Do not infer movement
placement, timing/resource, ownership, state, or maintenance semantics from
the inherited DDR4_PuD implementation.

Defer the exact final class and registration name to implementation planning.
The name must identify a combined experimental substrate without implying
that it models all of MIMDRAM. Capability detection must include LC-MOV and
GB-MOV rather than accepting a standard merely because the four inherited
PuD requests exist. Existing fixed four-PuD request/statistics assumptions
must be generalized, and the selected name must be accounted for by the
current AllBankRefresh registration/name coupling. These are implementation
impacts, not additional architecture decisions.

The current accepted movement architecture is completed by:

- `mimdram-movement-addressing-geometry-and-payload.md`;
- `mimdram-movement-execution-ownership-and-device.md`; and
- `mimdram-movement-timing-and-resource-model.md`.

Rationale

A separate derived standard preserves DDR4_PuD as a reproducible PRADA-only
baseline while directly supporting the intended combined PRADA-and-movement
experiment. Deriving instead from plain DDR4 would either duplicate the
existing DDR4_PuD behavior or require another combined boundary later.

One request per architectural movement invocation matches the LC-MOV/GB-MOV
boundary described by MIMDRAM without prematurely defining batching,
high-level address progression, arbitrary routing, or software lowering.
Controller ownership follows from the compound, ordered nature of the
accepted visible movement sequence.

Evidence

`docs/pud/references/mimdram-inter-column-data-movement.md` records
`bbop_mov` as an ISA-level operation that the MIMDRAM control unit lowers and
records LC-MOV and GB-MOV as distinct architectural movement mechanisms. The
reference remains the authority for those source facts; it does not by itself
select the simulator request boundary or combined-standard inheritance.

The repository's separate generated DDR4_PuD definition, request-owned
operand representation, retained controller sequence context, and shared
lifecycle provide the implementation evidence for this boundary.
`docs/pud/adding-pud-primitives.md` supplies the reusable methodology while
explicitly requiring substrate-specific physical and policy decisions.

Open issues

- Whether a future combined standard also adds other mat-selective compute
  mechanisms.
- Future workload/frontend integration, `bbop_mov` lowering, array placement,
  vector reduction, batching, and routing above the accepted one-invocation
  request boundary.
