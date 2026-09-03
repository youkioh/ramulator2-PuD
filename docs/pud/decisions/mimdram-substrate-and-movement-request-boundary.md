Status: Accepted

Question

1. Where should MIMDRAM inter-column movement live relative to the completed
   DDR4_PuD baseline?
2. What does one externally submitted LC-MOV or GB-MOV request represent?

Decision

Introduce MIMDRAM inter-column movement in a distinct combined experimental
DRAM standard derived at the Python-definition level from the completed
DDR4_PuD standard. Independently copy all inherited mutable standard
definitions before extending them. Leave the existing DDR4 and DDR4_PuD
standards unchanged.

The combined standard inherits the existing DDR4_PuD RowCopy, MAJ3, MAJ5,
and NOT behavior without changing its semantics. Whether the combined
standard later adds other mat-selective computation mechanisms is not decided
here.

Represent LC-MOV and GB-MOV as distinct request-level operations. One
submitted request represents one architectural LC-MOV or GB-MOV command
invocation. The exact physical transfer granularity, single-mat versus
mat-range execution semantics, and source/destination range pairing are not
decided here.

The controller owns the movement request lifecycle and any command sequencing
required by the subsequently accepted command-granularity decision. Whether
an LC-MOV or GB-MOV invocation maps to an aggregate DRAM command or exposes
internal phases is not decided here.

Reuse shared request, controller, scheduler, device, and completion
infrastructure only where their abstractions fit. Do not treat DDR4_PuD-specific
placement, timing/resource, ownership, or state choices as MIMDRAM facts.

Larger multi-invocation movements, vector-reduction orchestration, ISA-level
`bbop_mov` lowering, array placement, and software/frontend integration are
outside this initial request boundary.

Defer the exact class and registration name for the combined experimental
standard. Its name must not imply that the substrate models all of MIMDRAM.

Rationale

Modifying DDR4_PuD directly would make the completed PRADA-only research
baseline and the combined movement experiment share one standard identity.
Even if legacy operations initially remained behaviorally unchanged, later
movement-specific geometry, resource, state, or timing work would be coupled
to that baseline. A distinct derived standard preserves DDR4_PuD as a
reproducible PRADA-only baseline while providing an explicit boundary for
combined PRADA and movement experiments.

A pure DDR4-derived MIMDRAM sibling would also isolate DDR4_PuD, but it would
not directly provide the intended combined PRADA and movement substrate. It
would either duplicate the completed DDR4_PuD behavior or require another
combined standard later. Deriving the combined standard from DDR4_PuD reuses
the established substrate-isolation pattern and the proven request/controller
lifecycle methodology without copying DDR4_PuD's physical modeling choices
into the MIMDRAM movement model by analogy.

Defining one request as one architectural LC-MOV or GB-MOV invocation keeps
the initial interface at the movement-command boundary described by MIMDRAM.
A request spanning multiple physical transfers would prematurely require
batching, address progression, placement, and routing semantics. Making
ISA-level `bbop_mov` the initial boundary would additionally require array
placement and software/control-unit lowering that Ramulator2 does not
currently provide. Keeping those mechanisms above the initial physical
movement request abstraction allows later vector reduction and system
integration to build on LC-MOV and GB-MOV without making them prerequisites
for modeling the movement substrate.

Evidence

MIMDRAM source facts:

- `docs/pud/references/mimdram-inter-column-data-movement.md` records
  `bbop_mov` as an ISA-level operation over arrays, indices, element count,
  and precision. It records that the MIMDRAM control unit derives placement
  and translates that operation to LC-MOV or GB-MOV.
- The same reference records LC-MOV and GB-MOV as distinct architectural
  movement commands with source and destination location information. It also
  preserves unresolved physical details, including multi-mat LC behavior,
  GB range pairing, and non-neighbor reachability.

Repository evidence:

- `python/ramulator/dram/ddr4_pud.py` defines DDR4_PuD separately from DDR4
  through Python inheritance and independently copies mutable command, state,
  timing, request, preset, and geometry definitions before extending them.
  The generator emits a separately registered DRAM standard.
- `src/ramulator/base/request.h` provides request-owned ordered
  `std::vector<AddrVec_t>` operand storage that survives request copying and
  buffering.
- `src/ramulator/controller/impl/generic_ddr_controller.cpp` retains active
  PuD requests, advances monotonic request progress, and uses the shared
  controller lifecycle for admission, arbitration, issue, and retirement.
- `docs/pud/decisions/ddr4-pud-code-structure.md` accepts the isolated
  generated-standard pattern for DDR4_PuD.
- `docs/pud/decisions/pud-request-taxonomy-and-operands.md`,
  `docs/pud/decisions/pud-controller-sequencing-and-atomicity.md`, and
  `docs/pud/decisions/pud-request-lifecycle-queueing-and-statistics.md` record
  the existing DDR4_PuD request ownership, controller sequencing, and
  lifecycle methodology. Their DDR4_PuD-specific physical and policy choices
  do not establish MIMDRAM behavior.

Open issues

- Logical-mat placement and metadata, placement legality, and movement
  reachability remain unresolved.
- Movement command granularity remains unresolved, including whether LC-MOV
  and GB-MOV are aggregate commands or expose internal phases.
- Movement timing and resource scope remain unresolved.
- Movement ownership and atomicity scope remain unresolved.
- Required movement state visibility remains unresolved.
- Physical transfer width remains unresolved.
- Single-mat versus mat-range execution semantics remain unresolved.
- Source/destination range pairing remains unresolved.
- The exact combined-standard class and registration name remain unresolved.
- Whether the combined standard later adds mat-selective computation
  mechanisms remains unresolved.
