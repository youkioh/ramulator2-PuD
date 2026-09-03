Status: Superseded

Superseded by
`docs/pud/decisions/mimdram-movement-addressing-geometry-and-payload.md`.

Question

What placement, logical-mat-range metadata, direct reachability, and
range-execution contract should one architectural LC-MOV or GB-MOV request
use?

Decision

Keep the combined movement substrate's ordinary Ramulator hierarchy unchanged
as `[Channel, Rank, BankGroup, Bank, Row, Column]`. Do not add Chip, Subarray,
or Mat as explicit hierarchy levels for this placement model.

Represent each LC-MOV and GB-MOV request with exactly two ordered,
request-owned `AddrVec_t` operands. Operand 0 is the source and operand 1 is the
destination. Preserve each operand's Row coordinate as the full bank-row
coordinate used by the inherited DDR4_PuD substrate.

Adopt the combined substrate's existing 1024-row derived-subarray mapping for
movement placement:

```text
subarray_id = row / 1024
local_row   = row % 1024
```

This mapping is an explicit simulator organization assumption, not a verified
MIMDRAM or physical DDR4 address mapping. For an organization with 64K rows per
bank, it produces 64 derived subarrays per bank.

Scope one 128-entry logical-mat namespace to each `(Channel, Rank, BankGroup,
Bank, derived_subarray_id)` context. Represent logical mat selection as
movement-specific request metadata using the MIMDRAM-compatible 7-bit logical
mat identifier: a 3-bit logical chip ID and a 4-bit local logical-mat ID. Do not
derive logical chip or mat identity from Row or Column. The exact mapping from
these logical identifiers to physical mats remains unresolved.

LC-MOV carries one nonempty contiguous inclusive logical mat range
`[mat_begin, mat_end]`. Source and destination use the same target range. Their
Channel, Rank, BankGroup, Bank, and derived Subarray coordinates must match;
their Row and Column coordinates may differ. The invocation supplies one
source Row/Column pair and one destination Row/Column pair common to every
selected mat.

Model all mats selected by one LC-MOV range as executing the same movement
phase sequence in lockstep. Each selected mat performs its movement through
its own local path and moves one local HFF width. In MIMDRAM's evaluated
four-HFF organization, an LC-MOV selecting `N` mats therefore has an inferred
aggregate movement width of `4N` bits. This range-wide parallel interpretation
is a strong architectural inference from MIMDRAM's explicit range operand,
shared-state range execution, and per-mat local datapath. The paper directly
demonstrates only a singleton LC-MOV walkthrough.

An LC-MOV range may include mats belonging to multiple logical chips. This
does not represent cross-chip data transfer: each selected mat performs its
own intra-mat source-to-destination movement locally. Do not require one common
logical chip ID for all mats selected by an LC-MOV range.

MIMDRAM exposes separate source and destination logical mat ranges for GB-MOV.
The initial simulator-supported GB-MOV subset remains one singleton source mat
and one singleton destination mat. Both must be in the same accepted
derived-subarray context and the same logical chip. The initially supported
direct reachability is from local logical mat `i-1` to local logical mat `i`.
The source-backed physical topology is the directional neighboring-global-SA
path `SA_(i-1) -> SA_i`; associating consecutive local logical-mat IDs with
that physical adjacency is a conservative simulator mapping assumption.

Reject wider GB-MOV ranges, cross-chip GB-MOV, reverse direct GB-MOV,
non-neighbor direct GB-MOV, and automatic multi-hop lowering at this primitive
boundary. Singleton GB-MOV support is an intentionally conservative initial
subset, not a claim that MIMDRAM's GB-MOV interface is fundamentally
singleton-only. The source does not define wider-range equality, pairing,
simultaneous execution, overlap, alignment or displacement, or internal
expansion semantics.

Reject cross-subarray, cross-bank, and cross-controller LC-MOV and GB-MOV.
Non-neighbor routing or orchestration, if later supported, belongs to a
separate decision above this primitive boundary.

GenericDRAMSystem handles request shape, required movement metadata, channel
validation, and routing using operand 0. GenericDDR handles ordinary hierarchy
shape and bounds and shared Rank, BankGroup, Bank, and derived-Subarray
placement. Movement-specific placement validation enforces logical-ID and
range bounds, a nonempty ordered LC range shared by both phases, and the
singleton same-chip directional-neighbor GB subset. This decision does not
prescribe how movement-specific validation is factored in code.

This decision does not define the movement Column address unit,
movement-specific valid Column range, alignment, transfer quantization, or
mapping between Column and MIMDRAM's HFF-selected datapath. It establishes only
that source and destination Column coordinates are preserved and may differ.
The inferred LC aggregate width does not resolve those Column or quantization
questions.

Range-wide LC-MOV is one architectural invocation with SIMD-like movement in
each selected mat. It is not multiple independently scheduled LC-MOV requests.
This decision neither permits nor prohibits concurrent execution of
independent LC-MOV, GB-MOV, or PUD requests on disjoint mat ranges. Such
inter-request MIMD concurrency remains unresolved for the timing/resource-scope
and ownership/atomicity decisions.

Rationale

MIMDRAM explicitly gives LC-MOV one logical mat range and one common source
and destination Row/Column pair. Its general range mechanism selects a
contiguous group of mats that shares state while executing the same ACT-PRE
sequence. Combined with LC-MOV's per-mat local HFF/column-select datapath, this
strongly implies one lockstep local movement in every selected mat. Restricting
LC-MOV to a singleton would discard the range semantics exposed by the source
without a placement or datapath reason.

MIMDRAM gives GB-MOV separate source and destination ranges, but its detailed
walkthrough establishes only one directional neighboring pair. The source
does not explain how wider ranges are paired or whether overlapping or
multiple pairs execute together. Retaining a singleton directional-neighbor
GB subset avoids inventing those semantics while preserving room for a later
evidence-backed or explicitly chosen expansion.

MIMDRAM's subarray-scoped execution, 128-bit mat scoreboard with one bit per
DRAM mat per subarray, and evaluation of up to 64 subarrays per bank support a
subarray-scoped interpretation of the 128-entry control/scheduling mat set more
strongly than a single bank-wide interpretation. They do not establish the
physical mapping of logical mat IDs or DDR4 row addresses.

The existing full bank-row coordinate and derived 1024-row subarray partition
provide one coherent row-address space for inherited DDR4_PuD primitives and
movement operations. For the 64K-row `DDR4_8Gb_x8` organization, the resulting
64 derived subarrays align with the evaluated MIMDRAM subarray count while
remaining explicitly classified as a simulator mapping assumption.

Movement-specific logical-mat metadata preserves chip and mat distinctions
without changing the generic address hierarchy, address-vector shape, DRAM
timing tree, or memory-system routing topology. Deferring Column semantics
avoids equating an ordinary DDR4 Column coordinate with MIMDRAM's HFF-selected
transfer before the relevant units and quantization are accepted.

Evidence

MIMDRAM source facts:

- `docs/pud/references/mimdram-inter-column-data-movement.md` records that
  LC-MOV accepts one logical target-mat range plus one source and one
  destination Row/Column pair. Its detailed walkthrough demonstrates a
  four-bit movement in one mat.
- The same reference records that MIMDRAM restricts a PUD operation to a
  physically contiguous mat range and that mats in one range share state while
  executing the same ACT-PRE sequence. The evaluated organization has four
  HFFs per mat.
- The reference records that GB-MOV accepts separate source and destination
  logical mat ranges, while its detailed walkthrough demonstrates only one
  neighboring source/destination pair.
- The source-backed direct GB topology is `SA_(i-1) -> SA_i`. The source does
  not establish a reverse or arbitrary non-neighbor direct path, a cross-chip
  data path, a multi-hop protocol, or wider-range GB equality, pairing,
  simultaneous execution, overlap, alignment/displacement, or expansion
  semantics.
- MIMDRAM communicates a 7-bit logical mat identifier composed of a 3-bit chip
  ID and a 4-bit mat ID. Its per-chip selection logic determines which part of
  an operation's logical range belongs to each chip.

Architectural inferences:

- A multi-mat LC-MOV applies its common source and destination addresses to all
  selected mats in lockstep, with each mat moving one local HFF width. For the
  evaluated organization, `N` selected mats therefore move `4N` aggregate
  bits. MIMDRAM does not explicitly walk through this multi-mat case.
- Because each selected LC mat uses only its local datapath, selecting mats in
  more than one logical chip does not imply data transfer between chips.
- The subarray-scoped execution and scoreboard evidence makes a
  subarray-scoped 128-entry control/scheduling mat set better supported than a
  single bank-wide set. It does not make the logical namespace a definitively
  identified physical subarray namespace.
- The depicted physical-neighbor connection does not establish that
  consecutive local logical-mat identifiers always correspond to adjacent
  physical global-SA sets.

Repository evidence:

- `src/ramulator/base/request.h` provides request-owned ordered
  `std::vector<AddrVec_t>` operand storage.
- `src/ramulator/dram/impl/DDR4_PuD.cpp` uses the hierarchy `[Channel, Rank,
  BankGroup, Bank, Row, Column]` without explicit Subarray or Mat levels.
- `src/ramulator/dram/dram_spec.h` provides `rows_per_subarray` and derives a
  subarray ID by integer division of the full Row coordinate.
- `python/ramulator/dram/ddr4_pud.py` configures
  `rows_per_subarray = 1024`.
- `docs/pud/references/mimdram-geometry.md` records that the selected
  `DDR4_8Gb_x8` organization has 64K rows per bank and that the existing
  project mapping therefore produces 64 derived subarrays per bank.
- `src/ramulator/memory_system/pud_request_routing.h` and
  `src/ramulator/memory_system/impl/generic_dram_system.cpp` route an ordered
  multi-operand PuD request using operand 0 after same-channel validation.
- `src/ramulator/controller/impl/generic_ddr_controller.cpp` owns ordinary
  hierarchy shape, bounds, and derived-subarray placement validation.

Simulator mapping assumptions:

- Contiguous groups of 1024 full bank-row coordinates form derived subarrays
  for movement placement.
- Each derived-subarray context has one 128-entry logical-mat namespace.
- Consecutive local logical-mat IDs `i-1` and `i` represent the initially
  supported directional physical-neighbor path for GB-MOV.

Open issues

- Movement Column units, valid range, alignment, transfer quantization, and
  HFF-selected datapath mapping.
- Movement timing and resource scope, including mat, interconnect, bank, rank,
  channel, and command-bus constraints and permitted inter-request overlap.
- Movement ownership and atomicity scope, including interaction with ordinary
  requests, inherited PuD requests, refresh, maintenance, and independent
  requests on disjoint mats.
- Movement device-state visibility, including source/destination active state,
  HFF retention, global-SA/link state, prerequisites, and precharge behavior.
- Wider GB-MOV range equality, pairing, simultaneous execution, overlapping
  ranges, alignment/displacement, internal expansion, and any associated
  transfer-width interpretation.
- Non-neighbor GB-MOV orchestration and any multi-hop placement policy.
- The exact mapping from logical mat IDs to physical mats, the complete
  relationship between the section 2.1 physical hierarchy and
  logical/evaluated organization, and the physical DDR4
  row-address-to-subarray mapping.
- Whether multiple independent movement or PUD requests may execute
  concurrently on disjoint mat ranges.
