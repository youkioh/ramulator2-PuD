Status: Accepted

Question

What addressing, derived geometry, logical-mat placement, payload-width, and
Column-selector model should the initial LC-MOV and GB-MOV substrate use?

Decision

Use exactly two ordered, request-owned `AddrVec_t` operands for each movement
request: operand 0 is the source and operand 1 is the destination. Retain the
ordinary Ramulator hierarchy:

```text
[Channel, Rank, BankGroup, Bank, Row, Column]
```

Do not add Chip, Subarray, or Mat hierarchy coordinates. Preserve each Row as
the full Bank-row coordinate used by the inherited DDR4_PuD substrate.

Use this derived-subarray organization for movement placement:

```text
rows_per_subarray = 1024
subarray_id       = row / rows_per_subarray
local_row         = row % rows_per_subarray
```

This is an accepted simulator organization assumption, not a verified
MIMDRAM or physical DDR4 row-to-subarray map. With the selected 64K-row-per-
Bank organization, it yields 64 derived subarrays per Bank.

Scope one 128-entry logical-mat namespace to each `(Channel, Rank, BankGroup,
Bank, derived_subarray_id)` context. A seven-bit logical mat ID contains three
logical-chip bits and four local-logical-mat bits. Logical mat selection is
movement-specific request/controller metadata; do not derive it from Row or
Column or promote it into the DRAM hierarchy. Its exact mapping to physical
mats remains unresolved.

LC-MOV carries one nonempty contiguous inclusive logical range
`[mat_begin, mat_end]`, common to the source and destination. Both operands
must share Channel, Rank, BankGroup, Bank, and derived-subarray context. They
provide one common source Row/Column pair and one common destination
Row/Column pair for every selected mat; the source and destination Row and
Column values may differ.

All selected LC mats execute the same movement sequence in lockstep. Each mat
moves through its own local datapath, so an LC range may cross logical-chip
IDs without implying chip-to-chip payload transfer. Range-wide LC-MOV is one
architectural invocation, not one independently scheduled request per mat.

The initial GB-MOV subset has one singleton source mat and one singleton
destination mat. Both endpoints must share Channel, Rank, BankGroup, Bank,
derived-subarray context, and logical chip. The accepted direct direction is:

```text
local logical mat i-1 -> local logical mat i
```

Keep distinct the source-backed physical neighboring-global-SA direction
`SA_(i-1) -> SA_i` and the project assumption that consecutive local logical
mat IDs map to that adjacency. Reject reverse, non-neighbor, cross-chip,
cross-subarray, cross-Bank, cross-controller, and wider-range GB-MOV, and do
not automatically lower a request into multiple hops. Singleton support is
an intentionally conservative initial subset, not a claim that the source
interface is intrinsically singleton-only.

GenericDRAMSystem validates movement request shape, required metadata, and
same-Channel routing, using operand 0 as the route. GenericDDR validates
ordinary hierarchy shape/bounds and shared Rank, BankGroup, Bank, and derived
subarray placement. Movement-specific validation enforces logical-ID bounds,
a nonempty ordered LC range common to both phases, and the singleton
same-chip directional-neighbor GB subset. This responsibility split does not
prescribe the exact code factoring of movement-specific checks.
GB source and destination Row coordinates and Column selectors may differ.

The retained request and controller preserve semantic logical-mat targets for
every occurrence. Device Bank state does not store logical mat identities.
Bank-level Device state is a simulator legality/resource abstraction and does
not imply that physical movement `ACT`, `RD`, `WR`, or `PRE` targets an entire
Bank. Do not add explicit Mat state, hierarchy, open-row entries, or a mat
scoreboard for this initial model.

Represent HFF width as a configurable combined-standard/device organization
parameter:

```text
hffs_per_mat = 4
```

The initial evaluated value means four one-bit HFFs per mat. It is not a DDR4
property, a universal MIMDRAM constant, request metadata, or a hierarchy
count. A future supported organization may use another evidence-backed
value. The exact configuration path and C++ storage representation are
implementation choices.

Derive exact architectural movement width rather than storing a duplicated
request field. For LC-MOV:

```text
selected_mat_count = mat_end - mat_begin + 1
moved_bits         = selected_mat_count * hffs_per_mat
```

For the initial singleton GB-MOV:

```text
moved_bits = hffs_per_mat
```

Count a GB payload once, not once per endpoint. Width does not multiply the
request count, visible occurrence count, or modeled latency.

`Request::size_bytes` is not applicable to LC-MOV and GB-MOV. Its canonical
value is `-1`; this must be an explicit named sentinel, predicate, or
equivalent request-type contract rather than incidental uninitialized state.
Movement ingress accepts that representation and rejects caller-supplied
movement byte sizes. Do not substitute the ordinary transaction size or use
`ceil(moved_bits / 8)`. Future movement accounting derives and accumulates
exact bits before any presentation conversion. Movement does not contribute
to ordinary Read/Write byte-throughput accounting. Existing DDR4_PuD request
semantics remain unchanged.

For movement only, interpret each operand's existing Column coordinate as an
opaque logical movement-column selector; do not add a movement-specific
Column field. The source selector names the
payload location used by `RD_MOV`; the destination selector names the
payload location used by `WR_MOV`. It selects a location but does not define
payload width.

Source and destination selectors are independent; equal and unequal values
are both valid. Do not assign physical meaning to selector arithmetic,
ordering, equality, difference, or adjacency. Do not impose HFF, bit, byte,
prefetch, burst, cache-line, or other movement-specific alignment or
divisibility requirements.
Column values, equality, and arithmetic do not affect `moved_bits`, visible
occurrence count, or modeled latency.

Movement operands must only satisfy the configured Ramulator Column
organization bound for structural well-formedness. In the current combined
DDR4-based organization:

```text
0 <= Column < 1024
```

This is a simulator operand namespace, not a physical movement-Column range.
It does not imply 1024 physical movement locations, a one-to-one mapping to
the evaluated 512 physical columns, 128 HFF groups, ordinary DDR external-
column equivalence, physical ordering, or any HFF/byte/prefetch alignment.
Do not restrict address-vector-native movement selectors to the 128 values
currently produced by ordinary flat-address mapping. Movement continues to
use final device-visible operands and does not change ordinary mapping.

Implementation impact is limited by these accepted semantics: request
storage must retain logical-mat metadata copy-safely; ingress validation must
be request-type aware for the `-1` sentinel; and `hffs_per_mat` needs typed,
configured runtime access. Existing fixed four-PuD request/statistics
assumptions must be generalized without assigning movement a byte width.

Rationale

The unchanged hierarchy and derived-subarray mapping preserve one coherent
address space for inherited DDR4_PuD and movement requests without asserting
a physical DDR4-to-MIMDRAM map. Request-owned logical metadata retains the
source's chip/mat distinctions while avoiding unsupported Mat-level Device
state and timing machinery.

MIMDRAM gives LC one range and one source/destination address pair, and its
per-mat local path supports the accepted lockstep interpretation. Its GB
walkthrough establishes one directional neighboring pair but does not define
wider pairing or routing, so the singleton logical-neighbor subset avoids
inventing those semantics.

HFF count determines parallel payload width; Column identifies the selected
location. Keeping them independent preserves exact sub-byte widths and avoids
inventing a physical Column unit. The explicit `size_bytes` N/A contract
prevents callbacks and future accounting from observing a fictitious rounded
byte quantity.

Evidence

Source facts are maintained in
`docs/pud/references/mimdram-inter-column-data-movement.md`: physical
mat/subarray hierarchy, the seven-bit logical-mat encoding, contiguous range
selection, the four-HFF evaluated organization, LC local movement, GB's
directional neighboring-SA path, and the source's unresolved wider-range and
physical-mapping details. The reference classifies range-wide LC execution
and absence of cross-chip LC payload transfer as architectural inferences;
this decision explicitly adopts those inferences as simulator choices.

Repository evidence for the chosen representation is the existing
`[Channel, Rank, BankGroup, Bank, Row, Column]` hierarchy, the configured
`rows_per_subarray = 1024` mapping, request-owned ordered operands, final-
operand PuD routing, and controller-owned placement validation. Current
request ingress and statistics handling also establish why the accepted N/A
sentinel and exact-bit accounting require request-type-aware treatment.

This document consolidates the current accepted authority formerly carried by
`mimdram-movement-range-and-placement.md`, the targeting/metadata portion of
`mimdram-mat-targeting-and-transport-abstraction.md`,
`mimdram-movement-width-and-request-size-semantics.md`, and
`mimdram-movement-column-selector-semantics.md`. Those files remain as
historical provenance.

Open issues

- Exact logical-to-physical mat mapping and reconciliation of the source's
  physical and logical/evaluated organizations.
- Exact mapping from the opaque movement selector to physical column-select,
  HFF, bitline, or movement locations, and any future functional alias model.
- Mapping from host addresses, arrays, layouts, or `bbop_mov` operands into
  movement operands and selectors.
- Wider GB range pairing, overlap/alignment rules, non-neighbor routing, and
  any explicit multi-hop policy.
- Geometry and payload refinements for another standard, physical
  organization, or HFF width.
