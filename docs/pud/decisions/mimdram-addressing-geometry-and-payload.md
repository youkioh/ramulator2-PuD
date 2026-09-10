Status: Accepted

Question

What common address, geometry, affected-location, and payload contract should
ordinary DRAM access and MIMDRAM-v2 PuD use, and which initial modeled
placement profile makes that contract concrete?

Decision

**Current status (2026-09-10).** W1-W9 implemented this geometry and placement
authority for the canonical
[unified DDR4 PuD substrate](ddr4-pud-unified-substrate.md). Development-era
`v2` and `legacy` labels below record the transition from opaque/bare
operands to paired resolved locations; they do not name runtime models.
Gate A, Gate C, concrete C++ retention, and public execution are now resolved.
The corresponding acceptance-time open statements below are historical; the
additional-profile, mapping, and physical-evidence limits remain live.

Accept Gate B on 2026-09-08 with the initial
**MIMDRAM-DDR4_8Gb_x8 modeled placement profile v1** below. This is the
canonical addressing/geometry authority for MIMDRAM-v2 and the successor to
[movement addressing, geometry, and payload](mimdram-movement-addressing-geometry-and-payload.md).
It carries forward the shared placement and movement-payload contracts while
replacing the legacy opaque-selector model for v2. The old file remains
historical provenance. Existing DDR4, DDR4_PuD, and DDR4_PuD_Movement
executable behavior is unchanged by this documentation decision.

**Generic, replaceable geometry and placement contract**

A profile binds the selected DDR organization, external channel/controller
mappers and routing context, internal geometry, logical-mat topology, and
physical/layout bit placement. The generic contract is not specialized to
x8. Chip/mat counts, cells per mat-row, HFF width, row subdivision, group
numbering, and striping are coordinated profile properties, not constants
embedded in PuD operation semantics. Another DDR4 organization may require a
different coordinated profile; no physical x4/x16 MIMDRAM profile is claimed.

A common source is a physical/layout placement origin sufficient to identify
each operand's region, not necessarily one scalar physical byte address per
PuD operand. It can be a physical byte address with bit/region information or
a resolvable layout-region reference. Retain sufficient original information
and profile/address-space/routing context until resolution. Do not discard
offsets or assume that compact AddrVec coordinates can reconstruct them.
A layout reference describes actual modeled placement, not a second lane
address space.

Use one canonical storage-location authority:

```text
physical/layout bit location + profile/routing context
    -> canonical modeled CellID
```

CellID identifies Channel, Rank, BankGroup, Bank, Subarray, LocalRow, Chip,
Mat, and mat-local CellColumn. Ordinary ACT/RD/WR footprints and PuD
compute/LC-MOV/GB-MOV footprints must obtain affected cells through this same
canonical placement map or its retained results. Neither path may
independently reconstruct CellIDs using separate formulas after mapping.
Region/group resolution is allowed; this does not mandate one scalar call
per cell. The map also supplies ordered cell and local-SA/HFF-position
correspondence. These position identities do not specify temporal state.

Preserve the external hierarchy
`[Channel, Rank, BankGroup, Bank, Row, Column]`. External Row is the full
Bank-row coordinate and Column is the conventional compact BurstColumn B.
Internal group G is a distinct coordinate type. No `G = B` or other
arithmetic decode is part of the generic contract, and no Chip/Subarray/Mat
external hierarchy level or movement-only duplicate Column is required.

The v2 core submission contract uses paired, resolver-produced external and
internal operands with an origin/profile association. A shared resolver
accepts source descriptors and explicit operation scope before routing and
placement validation; direct callers and later frontends use this same
authority. Synthetic internal layouts must have profile-backed physical
correspondence. Reject regions requiring unsupported per-mat selectors or
multiple routing contexts rather than silently expanding an invocation.

Resolved internal-location information, operand identity, explicit ranges,
and origin/profile association must survive queueing, copies, retries,
occurrence switches, command dispatch, and functional use. External vectors
are checked projections, not an independently writable location authority.
Concrete C++ storage, handles, bundles, envelopes, and Device transport remain
undecided. Remapping cannot silently change only one view; the initial
profile excludes it, and any later support requires coherent context and
validation.

For every profile validate positive integer dimensions, coordinate bounds,
exact divisions where required, and these relationships where applicable:

```text
organization_columns * DQ
  == mats_per_chip_context * cells_per_mat_row

DQ * prefetch
  == participating_mats_per_ordinary_burst * HFFs_per_mat

# For exhaustive disjoint HFF-width grouping:
organization_columns / prefetch
  == cells_per_mat_row / HFFs_per_mat
```

The first checks chip-row capacity. The second checks per-chip burst payload
when each participating mat contributes one HFF-width group. The third
checks exact burst/group counts for the declared exhaustive grouping.
Together they imply that participating mats equal all mats in the chip
context. A different transfer/grouping model must explicitly justify
applicability and replacement coverage relationships, not silently bypass a
failed invariant. Reconcile chip count times DQ with rank/channel payload
width and validate total Bank/Rank/Channel capacity as well.

**Initial MIMDRAM-DDR4_8Gb_x8 modeled placement profile v1**

The following values and decode are specific to this initial instance.

| Property | Selected value and evidence class |
| --- | --- |
| DDR organization | 1,024 organization Columns, DQ 8, prefetch 8, 64-bit channel width, four BankGroups × four Banks, 65,536 rows/Bank: DDR4/Ramulator facts. |
| External configuration | One channel, CacheLineInterleave, RoBaRaCoCh, no row-remapping or reserved-row offsets: explicit simulator configuration choice. Default one rank; four ranks repeat the same per-rank placement to match the paper's rank count. |
| Internal dimensions | Eight chips/rank, 16 mats/chip context, 512 cells/mat-row, four one-bit HFF positions/mat; all 16 mats/chip participate in each ordinary burst. MIMDRAM supplies the evaluated dimensions/contribution evidence; their complete placement in each derived-subarray context is an explicit simulator assumption. |
| Row subdivision | Contiguous 1,024-row groups: retain the accepted simulator assumption, not a vendor Row-to-Subarray decode. This yields 64 subarrays/Bank. |
| Mat namespace/topology | Logical mat ID `16 * Chip + Mat`, 0..127 per external bank/subarray context. The seven-bit encoding is source-backed; mapping consecutive local IDs to the modeled directed neighbor path is an accepted simulator assumption. |
| Striping and bit order | Chip-major: eight consecutive line bytes per chip, successive nibbles in mats 0..15; byte offsets increase with address and byte bit 0 is least significant. Explicit simulator placement/numbering conventions. |
| Groups and positions | Group G contains numbered cells `[4G, 4G+1, 4G+2, 4G+3]`, assigned to HFF positions 0..3 in that order. Explicit simulator convention; 128 disjoint exhaustive groups is its derived consequence. |

Chip-major striping is **not a claim about vendor DDR4 DQ, beat, bitline, or
column-select wiring**. It completes the documented cache-line contribution
pattern with a reproducible modeled placement.

All divisions below are integer divisions. Let A be a post-translation
physical byte address, b its bit index in 0..7, and N the selected rank count
(1 for the baseline, or 4 for the stated rank replication). Require
`0 <= A < N * 8 GiB`; reject out-of-domain locations instead of wrapping or
truncating them into aliases. The external formulas follow from the selected
existing mappers:

```text
o           = A % 64
Channel     = 0
B           = (A / 64) % 128
Rank        = (A / 8192) % N
BankGroup   = (A / (8192 * N)) % 4
Bank        = (A / (32768 * N)) % 4
Row         = A / (131072 * N)
```

The canonical map resolves internal locations as follows:

```text
Subarray    = Row / 1024
LocalRow    = Row % 1024
t           = 8 * o + b
Chip        = t / 64
Mat         = (t % 64) / 4
h           = t % 4
q           = 64 * B + (t % 64)
G           = q / 64
CellColumn  = 4 * G + h
```

q enumerates 0..8191 bits of a chip-row in its burst-payload order.
Consequently `G = B` in this selected profile because `t % 64 < 64`;
this numerical equality follows from the complete placement convention and
does not collapse the coordinate types. Per-mat group ordering is stable
across operand rows. Local-SA position is CellColumn and ordered HFF position
is h in the identified mat; neither creates separate storage per operand.

The inverse is:

```text
Row = 1024 * Subarray + LocalRow
B   = CellColumn / 4
h   = CellColumn % 4
o   = 8 * Chip + Mat / 2
b   = 4 * (Mat % 2) + h
A   = o + 64 * B
        + 8192 * (Rank + N * (BankGroup + 4 * (Bank + 4 * Row)))
```

For scalar bit origins the six low byte-offset bits and bit index distinguish
the contributions absent from AddrVec: `o[5:3]` selects Chip,
`2 * o[2:0] + b[2]` selects Mat, and `b[1:0]` selects h.
A group origin must identify the nibble and explicit group extent; an
individual bit also selects h. A mat-row/layout origin may describe a union
of the corresponding physical bit locations without a single scalar address.
An arbitrary bit anchor must not be silently widened to a movement group.

**Affected locations and retained placement/payload semantics**

All PuD operands share Channel, Rank, BankGroup, Bank, and derived subarray.
Route using operand 0's Channel. Preserve the existing split: memory-system
validation covers request shape, operand count, and same-Channel routing;
controller validation covers hierarchy bounds and shared placement, with
operation-specific range/topology validation. This does not prescribe C++
factoring.

| Access | Canonically resolved footprint |
| --- | --- |
| Ordinary ACT | Addressed subarray/local row and all conventional participating mats, with their full configured cell/local-SA rows. |
| Ordinary RD/WR | Ordered per-mat group contributions of the external burst; initially group B in all 128 mats, four positions each. Distinguish the complete burst from any requested byte subregion; do not infer partial-write semantics from size_bytes. |
| Mat-scoped compute | One explicit, non-empty contiguous inclusive legal mat range common to every operand row; all configured columns in each selected mat (512 in v1). Column does not narrow it. Missing/empty/noncontiguous ranges are invalid; full-range execution must explicitly name that range. |
| LC-MOV | Exactly two ordered operands, source then destination; one common non-empty inclusive mat range and common source/destination row and internal selector for all selected mats. Each endpoint resolves its ordered HFF-width group through the canonical map. |
| GB-MOV | Exactly two ordered singleton endpoints in the same chip and derived subarray, using the directed local-mat neighbor `i-1 -> i`. Source/destination rows and groups may differ. No reverse, wraparound, cross-chip, wider-range, or automatic multihop movement. |

The singleton GB footprint is the project's conservative supported low-level
subset, not a claim that MIMDRAM's published GB-MOV interface is singleton-only.
Its range/lowering distinction and direct-reduction use are recorded in the
[reduction placement and movement-lowering decision](mimdram-reduction-placement-and-movement-lowering.md).
This clarification preserves the accepted topology and executable behavior.

LC's selected range may cross chips because each mat copies locally; this
does not imply chip-to-chip payload transfer. The range denotes one invocation.
LC moves `range_length * HFFs_per_mat` bits; singleton GB moves
`HFFs_per_mat` bits counted once. Retain movement `size_bytes = -1` as the
explicit N/A sentinel and reject supplied movement byte sizes; no rounded
byte accounting or contribution to ordinary read/write byte throughput.
These payload contracts are independent of concrete location storage.

For movement, source position h copies to destination position h. Capture
the ordered source payload before destination writes. Preserve every cell
outside the destination vectors; reading does not erase source cells.
Identical source/destination vectors give a data no-op that is still a
movement invocation. Initial groups in the same mat-row are identical or
disjoint; different mats/rows never alias. Any later profile permitting
partial overlap must preserve source-capture semantics and may change source
cells only where those cells are destinations.

The following logical compute effects are conditional on Gate A selecting
the PRADA/MIMDRAM hybrid. They apply pointwise by canonical cell identity
over the explicit selected mat-rows, using pre-operation operand values:

| Primitive | Final cell effects |
| --- | --- |
| RowCopy | Copy source to every destination; preserve source. |
| MAJ3 / MAJ5 | Write the majority to all participating rows, for distinct physical-row operands. |
| NOT | Invert and overwrite source. |
| NOT_COPY | Write inverted original source to both source and destination. |

Unselected mats, nonoperand rows, and other contexts retain their data.
Scratch/constants must be managed over the whole selected region; there is
no implicit active-lane mask. This effect contract does not establish
electrical intermediate visibility or repeated-row charge-sharing behavior.
Fixed ordered groups provide no cross-position shuffle or scalar reduction;
Gate A must resolve any required additional capability.

**Validation and compatibility boundary**

Validate the map's forward/inverse correspondence, bounds, full capacity,
disjoint/exhaustive group coverage, and ordered positions. For v1:

```text
1024 * 8 == 16 * 512 == 8192 bits/chip-row
8 * 8    == 16 * 4   == 64 bits/chip/burst
1024 / 8 == 512 / 4  == 128 bursts/row and groups/mat-row
8 * 16 * 4          == 512 bits/rank/burst == 64 B
8 * 16 * 512        == 65536 bits/rank-row == 8 KiB
```

With 65,536 rows and 16 banks this covers 8 Gibit/chip and 8 GiB/rank.
The inverse establishes uniqueness across all bank/rank/row contexts.
Arithmetic enumeration of all 65,536 rank-row bits verified unique coverage,
four bits per mat per burst, and matching inverses during Gate B review.

A bijective physical-bit <-> CellID map proves non-aliasing/completeness of
the selected placement profile. Ordinary/PuD same-cell behavior follows by
construction only if both paths consume that same canonical resolver.
Implementation tests must verify that they actually do, exercising ordinary
ACT/RD/WR and compute/LC-MOV/GB-MOV, footprint intersections, payload order,
low offsets and mat/chip/group/row boundaries. Include a valid non-identity
test mapping and profile replacement checks to expose duplicated x8 or
`G = B` formulas. Synthetic test geometry is not physical x4/x16 evidence.
The arithmetic review is not an implementation-test result.

The legacy combined-standard baseline used movement-only opaque Column
selectors bounded by the organization (0..1023), request-owned external
operands and logical-mat metadata, configurable HFF width for accounting,
and no internal CellID interpretation. These remain descriptions of existing
behavior, not the v2 submission contract. Its old Bank-state and timing
abstractions remain governed by the existing
[execution](mimdram-movement-execution-ownership-and-device.md) and
[timing](mimdram-movement-timing-and-resource-model.md) decisions for that
baseline; they do not decide v2 Gate C. Legacy DDR4_PuD placement remains
described by [compute placement](pud-operand-placement-and-routing.md).

Bare legacy AddrVec operands do not become valid v2 placements automatically,
even when Column is below 128. Require profile-resolved paired operands and
origin association. Do not use modulo, invented bit offsets, or an assumed
G/B identity to migrate streams. Changing HFF count alone cannot establish a
new coordinated placement profile. This decision neither changes executable
baselines nor authorizes implementation or an implementation plan.

Rationale

Updating the actively evolving addressing boundary into one common canonical
authority avoids reconstructing v2 storage semantics from legacy movement
selectors and separate functional lane maps. It preserves the established
external hierarchy, row placement assumptions, routing, movement shape, and
exact-bit payload rules while making every addressed cell explicit.

Chip-major striping follows ascending logical mat IDs with simple formulas
and matches the source's contribution counts and endpoint nibbles.
**Byte-lane striping was considered but not selected:** it uses
`Chip = o % 8`, `Mat = 2 * (o / 8) + b / 4`, and `h = b % 4`.
It also satisfies the documented endpoints, all geometry equations, and
bijection checks, but needs an additional byte-lane ordering convention.
Neither intermediate ordering is established as vendor wiring. Both fit
the same generic contract; only chip-major is selected for v1.

The coordinated equations reject geometrically inconsistent combinations
without hard-coding x8 into operation effects. Canonical resolver consumption
makes ordinary/PuD location equality structural, while implementation tests
are still needed to detect paths that bypass that authority. Retained results
satisfy execution lifetime without prematurely selecting C++ storage.

Evidence

- [MIMDRAM geometry](../references/mimdram-geometry.md) and
  [movement reference](../references/mimdram-inter-column-data-movement.md),
  especially §§1.1, 1.3–1.5, 3, and 4: evaluated geometry, logical encoding,
  movement datapaths, payload width, and source limits.
- [MIMDRAM paper](https://ghose.web.illinois.edu/papers/24hpca_mimdram.pdf),
  §§4.1–4.2 and 6.3 footnote 13, Table 2: checked during Gate B review.
  Four bits per mat and the first/last cache-line nibbles are source facts;
  the complete chip-major order, group numbering, and HFF/cell numbering
  are explicit simulator assumptions. The paper does not supply complete
  vendor DQ/beat/bitline wiring.
- [DDR4 organization](../../../python/ramulator/dram/ddr4.py),
  [transaction dimensions and geometry](../../../src/ramulator/dram/dram_spec.h),
  [PuD row configuration](../../../python/ramulator/dram/ddr4_pud.py),
  [mapper compaction](../../../src/ramulator/controller/addr_mapper/addr_mapper_base.cpp),
  [CacheLineInterleave](../../../src/ramulator/memory_system/channel_mapper/impl/cache_line_interleave.cpp),
  and [RoBaRaCoCh](../../../src/ramulator/controller/addr_mapper/impl/ro_ba_ra_co_ch.cpp):
  current source basis for the external formulas and dimensions.
- [PuD primitives](../references/pud-primitives.md): PRADA effect evidence.
  Applying those effects to MIMDRAM-shaped regions remains conditional on A;
  neither this reference nor the placement profile establishes hybrid
  physical compatibility.
- The predecessor movement decision and existing compute placement decision
  established contiguous 1024-row grouping, same-subarray placement, movement
  ranges, the directed singleton GB subset, and exact-bit/N/A payload rules
  as project choices. Their source facts and assumptions remain distinguished
  above; the predecessor's rationale is preserved at its stable path.

Open issues

- Gate A: hybrid primitive scope, physical/fidelity claims, and any required
  cross-position/reduction capability. Repeated physical-row majority
  interpretation beyond the distinct-row effects above is not established
  by placement and must be resolved before supporting such invocations.
- Gate C: mat-local temporal state, SA/HFF state and lifetime, ownership,
  concurrency, command transport, maintenance interaction, and timing.
  An affected-cell footprint is not a resource/conflict domain.
- Concrete C++ retention/transport representation and shared-resolver
  implementation/verification; none is selected or implemented here.
- Additional coordinated organizations, physical x4/x16 evidence, and other
  mapping/remap contexts require their own explicit supported profiles.
  The generic contract permits them without rewriting PuD operation semantics.
