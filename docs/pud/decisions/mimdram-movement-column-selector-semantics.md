Status: Superseded

Superseded by
`docs/pud/decisions/mimdram-movement-addressing-geometry-and-payload.md`.

Question

What does the existing `Column` coordinate in an LC-MOV or GB-MOV source or
destination `AddrVec_t` operand mean in the initial simulator, and what
structural bounds, alignment rules, and source/destination relationships apply?

Decision

Continue to represent LC-MOV and GB-MOV source and destination locations with
the existing two ordered, request-owned `AddrVec_t` operands. Do not add a
movement-specific Column field.

For movement requests only, interpret each operand's existing `Column`
coordinate as an opaque logical movement-column selector. The source selector
identifies the payload location associated with the source `RD_MOV`
occurrence. The destination selector identifies the payload location associated
with the destination `WR_MOV` occurrence. The selector identifies which
HFF-selected payload location participates; it does not determine payload
width.

LC-MOV and GB-MOV source and destination selectors are independent. Equal and
unequal selector values are both permitted. Do not impose an equality,
inequality, displacement, or other arithmetic relationship between them. The
accepted GB-MOV directed-neighbor constraint applies to the logical-mat and
neighboring-global-SA path, not to the source and destination Column values.

Arithmetic on selector values has no accepted physical meaning:

```text
Column + 1 does not imply a neighboring physical movement location.
abs(source.Column - destination.Column) does not represent physical distance.
Ordering of Column values does not establish physical ordering.
```

Do not impose HFF-count, bit, byte, prefetch, burst, cache-line, or other
movement-specific alignment or divisibility requirements. In particular, no
alignment or numbering relationship follows from `hffs_per_mat = 4`.

Movement operands must satisfy the existing `AddrVec_t` organization bound for
structural well-formedness. For the current combined DDR4-based organization,
this means:

```text
0 <= Column < 1024
```

This is only the accepted simulator operand-namespace bound. It is not the
physical or architectural legal movement-Column range. It does not mean that:

- MIMDRAM physically provides 1024 movement-column locations per mat;
- Ramulator Column values `0..1023` map one-to-one to MIMDRAM's evaluated 512
  physical columns;
- the namespace contains 128 four-HFF groups; or
- movement Column uses ordinary DDR4 external-address Column semantics.

Do not restrict movement selectors to the 128 values produced by current
DDR4 flat-address mapping, to the evaluated MIMDRAM physical-mat Column count,
or to a count derived from `hffs_per_mat`. The exact mapping from the opaque
selector to MIMDRAM physical column-select/HFF datapath locations remains
outside the initial model.

Column selection remains independent of the accepted movement-width
derivation:

```text
LC moved_bits = selected_mat_count * hffs_per_mat
GB moved_bits = hffs_per_mat
```

The Column values, their equality or difference, and any arithmetic between
them do not affect `moved_bits`, command count, or modeled latency.

Reuse the existing movement operand shape and ordinary hierarchy
shape/bounds validation. This Column abstraction requires no new movement
Column field, geometry parameter, address-mapper behavior, Request storage,
Device state, Device action, timing rule, or trace format. Ordinary address
mapping remains unchanged. Movement requests continue to bypass ordinary
flat-address decomposition and supply final device-visible operands.

Rationale

MIMDRAM gives LC-MOV and GB-MOV separate source and destination Row/Column
information. Its evaluated walkthroughs use one source Column selection to
capture four bits in four HFFs and one destination Column selection to write
that retained payload. The source does not define the selector's numeric unit,
progression, alignment, physical ordering, or mapping to an external DDR4
address.

Using an opaque request-specific selector preserves the source and destination
identities required by `RD_MOV` and `WR_MOV` without inventing a physical
bitline layout. It also keeps selection independent of width: the accepted
`hffs_per_mat` parameter states how many parallel bits one participating mat
moves, not how Column values enumerate payload locations.

The current Ramulator hierarchy provides a structurally validated Column slot,
but the field does not have one universally enforced physical unit. Current
DDR4 flat-address mapping removes transaction and internal-prefetch bits and
produces 128 transaction-granular Column values for the selected organization,
while address-vector-native paths can supply values in the full 1024-entry
organization namespace. Reusing only the namespace bound avoids changing
ordinary address mapping or claiming that either existing ordinary convention
describes the MIMDRAM datapath.

Evidence

MIMDRAM source facts:

- `docs/pud/references/mimdram-inter-column-data-movement.md` records that
  LC-MOV accepts one source Row/Column pair and one destination Row/Column pair.
  Source `RD(column_src)` selects a four-bit source location through the column
  select logic into the HFFs, and destination `WR(column_dst)` connects the
  retained HFF value to the destination local row buffer.
- The same reference records separate GB-MOV source and destination
  Row/Column information. Source `RD(column_src)` places the selected four-bit
  value in the source HFF/global-SA path, and destination `WR(column_dst)`
  consumes it through the neighboring-global-SA path.
- The evaluated organization has 512 columns per mat and four HFFs per mat,
  while the general architectural description gives typical mat dimensions of
  512--1024 columns. The source does not specify a numeric mapping between
  those physical counts and movement Column values.
- The source does not establish Column progression, adjacency, alignment,
  source/destination equality, or equivalence to ordinary external DDR4
  addressing.

Accepted project decisions:

- `docs/pud/decisions/mimdram-movement-range-and-placement.md` keeps two
  ordered `AddrVec_t` operands, permits distinct source and destination Column
  coordinates, applies the common LC source/destination selectors across the
  selected range, and constrains GB direction through logical-mat placement
  rather than Column arithmetic.
- `docs/pud/decisions/mimdram-movement-width-and-request-size-semantics.md`
  makes `hffs_per_mat` an organization parameter, derives moved bits from that
  width and accepted mat geometry, and keeps movement width independent of
  Column mapping and alignment.
- `docs/pud/decisions/mimdram-movement-occurrences-and-command-identities.md`
  associates `RD_MOV` with the selected source operand and `WR_MOV` with the
  selected destination operand while retaining one-address command dispatch.

Repository evidence:

- `python/ramulator/dram/ddr4.py` defines 1024 Columns and an internal prefetch
  size of eight for the inherited DDR4 organizations;
  `python/ramulator/dram/ddr4_pud.py` copies those organization presets.
- `src/ramulator/controller/addr_mapper/addr_mapper_base.cpp` reduces the
  mapped Column bit count by the internal-prefetch bit count. With 1024
  organization Columns and eight-way prefetch, ordinary flat-address mapping
  uses seven Column bits and therefore produces 128 transaction-granular
  values.
- `src/ramulator/memory_system/pud_request_routing.h` routes request-owned PuD
  operands without applying ordinary flat-address mapping.
- `src/ramulator/controller/impl/generic_ddr_controller.cpp` validates every
  PuD operand coordinate against its configured hierarchy bound. Existing PuD
  command sequencing preserves operand Columns but does not use them for
  placement, width, or timing.
- Current command prerequisites, actions, and hierarchy timing do not inspect
  a PuD operand's Column value, and existing command traces already serialize
  the selected `AddrVec_t`.

Open issues

- Exact mapping from the opaque selector to physical column-select logic,
  HFF lanes, bitlines, or physical movement locations.
- Mapping from host linear addresses, arrays, layouts, bitslice placement, or
  higher-level `bbop_mov` operands to movement selectors.
- Column semantics for another DRAM standard, a different physical mat
  organization, or a wider HFF organization.
- Whether later functional data modeling requires alias semantics beyond
  accepting equal and unequal selectors.
- Refresh admission, maximum deferral, and deadline treatment remain the
  remaining identified candidate plan-shaping issue. This decision makes no
  refresh-policy choice.
  Later resolution: the focused refresh investigation classified the initial
  model as F-A; existing GenericDDR deferred-refresh behavior is retained, and
  no new refresh-policy decision is required before planning.
