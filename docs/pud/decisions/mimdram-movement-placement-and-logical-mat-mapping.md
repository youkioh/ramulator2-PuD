Status: Superseded

Superseded by `docs/pud/decisions/mimdram-movement-range-and-placement.md`.

Question

What minimum placement, logical-mat metadata, and direct reachability contract
should one architectural LC-MOV or GB-MOV request use?

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
Bank, derived_subarray_id)` context. Represent logical mat identity as
movement-specific request metadata using the MIMDRAM-compatible 7-bit
identifier: a 3-bit logical chip ID and a 4-bit local logical-mat ID. Do not
derive logical chip or mat identity from Row or Column.

LC-MOV initially supports one singleton logical mat range. Its source and
destination must share Channel, Rank, BankGroup, Bank, derived Subarray,
logical chip, and local logical mat. Source and destination Row and Column
coordinates may differ.

GB-MOV initially supports one singleton source logical mat and one singleton
destination logical mat. Its source and destination must share Channel, Rank,
BankGroup, Bank, derived Subarray, and logical chip. The initially supported
direct reachability is from local logical mat `i-1` to local logical mat `i`.
Associating consecutive local logical-mat IDs with the depicted
`SA_(i-1) -> SA_i` physical neighbor path is a conservative simulator mapping
assumption. MIMDRAM does not fully specify the mapping between logical mat
numbering and physical global-SA adjacency.

Reject wider LC-MOV and GB-MOV ranges, cross-subarray, cross-bank,
cross-controller, cross-chip, reverse-direction, and non-neighbor direct
movement. Do not automatically lower a non-neighbor GB-MOV into repeated hops
at this primitive boundary. Any such lowering belongs to a later routing or
orchestration decision.

GenericDRAMSystem handles request shape, required movement metadata, channel
validation, and routing using operand 0. GenericDDR handles ordinary hierarchy
shape and bounds and shared Rank, BankGroup, Bank, and derived-Subarray
placement. Movement-specific placement validation enforces logical-ID bounds,
singleton ranges, LC-MOV same-mat placement, and GB-MOV same-chip directional
neighbor reachability. This decision does not prescribe how movement-specific
validation is factored in code.

This decision does not define the movement Column address unit,
movement-specific valid Column range, alignment, transfer width, transfer
quantization, or mapping between Column and MIMDRAM's HFF-selected datapath. It
establishes only that source and destination Column coordinates are preserved
and may differ.

Restricting one request to one LC-MOV mat or one GB-MOV mat pair defines only
the placement of one architectural invocation. It neither permits nor
prohibits concurrent execution of independent movement or PUD requests on
disjoint mat resources. Such concurrency remains unresolved until later
timing/resource-scope and ownership/atomicity decisions.

Rationale

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
timing tree, or memory-system routing topology. Singleton LC-MOV placement and
one same-chip directional neighbor pair for GB-MOV are the minimum subsets
supported by the detailed movement walkthroughs without assuming multi-mat LC
execution, GB range pairing, arbitrary direct connectivity, or implicit
multi-hop routing.

Deferring Column semantics avoids equating an ordinary DDR4 Column coordinate
with MIMDRAM's HFF-selected transfer before command and transfer granularity
are accepted. Separating invocation placement from resource concurrency also
preserves MIMDRAM's broader MIMD capability for the later timing, resource,
and ownership decisions.

Evidence

MIMDRAM source facts:

- `docs/pud/references/mimdram-inter-column-data-movement.md` records that
  MIMDRAM communicates a 7-bit logical mat identifier composed of a 3-bit chip
  ID and a 4-bit mat ID, describes fine-grained and independent PUD execution
  across mats within a DRAM subarray, and describes LC-MOV as intra-mat and
  GB-MOV as inter-mat within a DRAM chip.
- The same reference records the depicted neighboring global-SA connection
  `SA_(i-1) -> SA_i`, the worked `mat_(M-2) -> mat_(M-1)` GB-MOV example, the
  128-bit mat scoreboard with one bit per DRAM mat per subarray, and evaluation
  across 1–64 subarrays per bank.
- The source does not define multi-mat LC-MOV behavior, wider GB-MOV range
  pairing, arbitrary non-neighbor routing, a cross-chip datapath, the exact
  logical-to-physical mat mapping, or the physical DDR4 row-address-to-subarray
  mapping.

Architectural inference:

- The subarray-scoped execution and scoreboard evidence makes a
  subarray-scoped 128-entry control/scheduling mat set better supported than a
  single bank-wide set. It does not make the logical namespace a definitively
  identified physical subarray namespace.
- The depicted neighbor connection does not establish that consecutive local
  logical-mat identifiers always correspond to physically adjacent global-SA
  sets.

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
  project mapping therefore produces 64 logical subarrays per bank.
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

- Movement command granularity, including aggregate versus exposed phases,
  concurrent GB-MOV activation representation, mat-information transport, and
  physical transfer granularity.
- Movement Column units, valid range, alignment, transfer quantization, and
  HFF-selected datapath mapping.
- Movement timing and resource scope, including mat, interconnect, bank, rank,
  channel, and command-bus constraints and permitted overlap.
- Movement ownership and atomicity scope, including interaction with ordinary
  requests, inherited PuD requests, refresh, maintenance, and independent
  requests on disjoint mats.
- Movement device-state visibility, including source/destination active state,
  HFF retention, global-SA/link state, prerequisites, and precharge behavior.
- Wider LC-MOV/GB-MOV ranges, GB-MOV source/destination range pairing,
  non-neighbor orchestration, and any multi-hop placement policy.
- The exact mapping from logical mat IDs to physical mats, the complete
  relationship between the §2.1 physical hierarchy and logical/evaluated
  organization, and the physical DDR4 row-address-to-subarray mapping.
