Status: Accepted

Question

What minimum Ramulator command representation preserves every source-described
LC-MOV and GB-MOV `ACT`, `RD`, `WR`, and `PRE` occurrence and the timing
structure needed for later modeling?

Decision

Keep LC-MOV and GB-MOV as controller-sequenced request-level operations.
Preserve every source-described physical `ACT`, `RD`, `WR`, and `PRE`
occurrence as a controller-issued, Ramulator-visible command occurrence and
potential timing boundary. Do not collapse adjacent occurrences into hybrid
macro phases.

Use these Ramulator semantic command identities:

```text
ACT_MOV
RD_MOV
WR_MOV
PREpb
```

`ACT_MOV`, `RD_MOV`, and `WR_MOV` are simulator identities. They are not names
claimed by the MIMDRAM source. `PREpb` is the existing Ramulator command
identity.

Represent LC-MOV with six ordered occurrences:

```text
ACT_MOV(source) -> RD_MOV(source) -> PREpb
-> ACT_MOV(destination) -> WR_MOV(destination) -> PREpb
```

Represent GB-MOV with five ordered occurrences:

```text
ACT_MOV(source) -> ACT_MOV(destination)
-> RD_MOV(source) -> WR_MOV(destination) -> PREpb
```

Use one shared `ACT_MOV` semantic identity for every LC-MOV and GB-MOV
activation occurrence. Use one shared `RD_MOV` identity for both LC-MOV and
GB-MOV source-column occurrences. Use one shared `WR_MOV` identity for both
LC-MOV and GB-MOV destination-column occurrences. Reuse the existing `PREpb`
identity for both LC-MOV PRE occurrences and the GB-MOV terminal PRE.

Source versus destination, LC versus GB, and position within either sequence
are occurrence roles, not additional semantic command identities. The
retained controller request owns the operation identity, ordered operands,
logical-mat range or endpoints, and exact occurrence cursor. Each occurrence
uses the corresponding controller-selected operand and logical-mat metadata.

Do not introduce source/destination-specific or LC/GB-specific semantic
command IDs. Do not introduce a generic `CLOSE` or a movement-specific PRE
command.

Reusing the Ramulator `PREpb` identity does not decide the exact movement-state
action of either LC-MOV PRE occurrence or the GB-MOV terminal PRE. In
particular, this decision does not decide whether LC source PRE leaves an
explicit payload-retained Device state, leaves Device conventionally `Closed`
while retention is controller-implied, or uses another minimum state
representation. Those questions belong to the immediate revalidation of the
movement Device-state decision.

Reusing the Ramulator `PREpb` identity also does not claim that the physical
MIMDRAM movement PRE necessarily precharges the entire physical Bank. The
physical mat scope of movement-related PRE remains unresolved in the source.
Bank-level Ramulator dispatch or state is an accepted simulator abstraction,
not a physical whole-Bank targeting claim.

Do not reuse ordinary `ACT`, `RD`, or `WR` unchanged. Ordinary `ACT` creates
conventional flat-Bank `Opened` and row-map state, resolves a different-row
second activation through `PREpb`, and inherits ordinary Bank, Rank,
BankGroup, metadata, row-policy, and plugin behavior. Ordinary `RD` and `WR`
require conventional row state and inherit ordinary host-visible DQ, CAS,
row-hit, auto-precharge, row-policy, and statistics behavior. Those semantics
are not established for MIMDRAM's internal movement operations.

Do not reuse `ACT_PUD`, `ACT_PUD_OC`, `ACT_PUD_S`, or `ACT_PUD_S_OC` for
movement activation. Those identities represent accepted PRADA-specific
charge-sharing or sensing roles, state transitions, and timing semantics.
MIMDRAM movement ACT is mat-selective row activation for LC-MOV and GB-MOV.
Reusing a PRADA identity would incorrectly import PRADA physical semantics.
The separate `ACT_MOV` simulator identity is not a claim that MIMDRAM defines
a physical command with that name.

Keep the two GB-MOV `ACT_MOV` occurrences separately issued and timing-visible.
Their physical activation intervals must remain capable of overlap so the
later timing graph can reproduce the source-reported single effective `tRAS`
term. Do not require the source activation interval to finish before the
destination occurrence issues merely because the controller issues one
command per tick.

Current Bank-level timing history can retain multiple issue cycles for one
command identity. The existence of two GB-MOV activation occurrences therefore
does not by itself justify `ACT_SRC` and `ACT_DST` semantic commands. Do not
introduce a timing alias in this decision.

It remains unresolved whether one `ACT_MOV` history is sufficient for the
final numeric timing graph. LC-MOV may need a relationship to its most recent
`ACT_MOV`, while GB-MOV may need a relationship to its source `ACT_MOV` after
the destination `ACT_MOV` has become the most recent occurrence. Current
static timing constraints may be unable to select different history windows
according to LC versus GB request context. If the numeric timing gate proves
that this cannot be expressed using one semantic identity, it may introduce a
simulator-only timing alias. Such an alias would distinguish timing-history
occurrences of the same physical MIMDRAM ACT semantics; it would not represent
a different physical ACT command semantic.

Command occurrence count does not determine Device-state count. Do not accept
any replacement movement state, prerequisite, or action table here. The exact
minimum movement Device state must be established by revalidating the existing
Device-state decision against these shared command identities.

Rationale

MIMDRAM explicitly describes six LC-MOV operations and five GB-MOV operations
using `ACT`, `RD`, `WR`, and `PRE`. Keeping every occurrence visible preserves
the two LC activation/restoration and PRE/recovery intervals, the overlapping
GB activation intervals, the relocation interval, destination write
restoration, and terminal precharge. A macro-phase representation would hide
source-described timing structure needed to explain the published latency
equations.

Occurrence roles do not require command identities when the retained request
and controller cursor already preserve operation type, endpoint selection, and
sequence position. One shared semantic identity for each physical operation
class is therefore sufficient unless Device behavior, timing, resource use,
or metadata requires a distinction.

Ordinary `ACT`, `RD`, and `WR` do require semantic separation. Their current
handlers and timing metadata describe conventional flat-Bank activation and
host-visible column access. Movement activation is mat-selective under the
accepted request-owned targeting abstraction, and movement RD/WR use internal
datapaths rather than ordinary host DQ transfers. One movement variant of each
avoids importing those conventional behaviors without multiplying identities
by occurrence role.

The source describes movement precharge as `PRE` and does not establish
different source, destination, LC, or GB PRE command types. Reusing `PREpb`
preserves that architectural operation. Its exact aggregate Device action can
depend on the later state decision without requiring a different command
identity.

The timing engine stores history per hierarchy node and command ID and can
retain multiple prior occurrences. This makes separate semantic ACT identities
unnecessary at this gate. Because constraints select static history windows
rather than request-relative roles, the numeric timing graph must still prove
that the shared identity is sufficient before timing aliases are rejected
permanently.

Evidence

MIMDRAM source facts:

- `docs/pud/references/mimdram-inter-column-data-movement.md` records LC-MOV's
  source `ACT -> RD -> PRE`, retained HFF payload, and destination
  `ACT -> WR -> PRE` sequence.
- The same reference records GB-MOV's source and destination activation
  occurrences, their overlapping physical activation intervals, source `RD`,
  destination `WR`, terminal precharge/recovery, and
  `T_GB-MOV = tRAS + tRELOC + tWR + tRP`.
- The reference records that LC/GB RD and WR remain internal to the described
  DRAM datapaths rather than ordinary host-visible DQ transfers.
- The source uses `ACT`, `RD`, `WR`, and `PRE` terminology. It does not define
  commands named `ACT_MOV`, `RD_MOV`, or `WR_MOV`, does not establish distinct
  source/destination command semantics, and does not establish the physical
  precharge scope of every movement PRE occurrence.

Accepted project decisions:

- `docs/pud/decisions/mimdram-mat-targeting-and-transport-abstraction.md`
  retains the ordinary hierarchy, keeps logical-mat targeting in the request
  and controller, permits aggregate Bank state as a simulator abstraction,
  and accepts T3 without explicit mat-transport commands.
- `docs/pud/decisions/mimdram-movement-range-and-placement.md` accepts
  range-wide lockstep LC-MOV and the initial singleton ordered GB-MOV subset.
- `docs/pud/decisions/mimdram-movement-timing-resource-scope.md` accepts a
  Bank-conservative inter-request resource domain while requiring overlapping
  GB activation intervals to remain representable.
- `docs/pud/decisions/mimdram-movement-ownership-and-atomicity.md` keeps the
  retained request as the Bank owner and the controller cursor as the exact
  sequence authority.

Repository evidence:

- `src/ramulator/dram/commands/ACT.h` makes ordinary `ACT` set conventional
  `Opened`, populate `m_row_state`, and request `PREpb` for a different Row.
- `src/ramulator/dram/commands/RD.h` and
  `src/ramulator/dram/commands/WR.h` use conventional ACT prerequisites and
  row-hit/open queries.
- `python/ramulator/dram/ddr4.py` assigns ordinary ACT/RD/WR their conventional
  Bank, BankGroup, Rank, Channel, data-bus, and recovery constraints.
- `src/ramulator/dram/commands/ACT_PUD*.h` implements PRADA-specific
  charge-sharing and sensing states and prerequisites rather than MIMDRAM
  movement activation.
- `src/ramulator/dram/node.h` and `src/ramulator/dram/node.cpp` store a deque of
  issue cycles per hierarchy node and command ID and use a static timing
  history window for each directed constraint.
- `src/ramulator/base/request.h` and
  `src/ramulator/controller/impl/generic_ddr_controller.cpp` provide retained
  operands and monotonic controller-owned sequence progress.

Open issues

- Revalidation of the exact minimum movement Device states, prerequisites,
  actions, and ordinary-command legality under the shared identities.
- Exact numeric directed timing edges and independent CK quantization for both
  published latency equations.
- Whether LC-versus-GB selection of different `ACT_MOV` history occurrences
  requires a simulator-only timing alias or another timing mechanism.
- The GB-MOV activation-occurrence issue gap and its treatment in end-to-end
  latency.
- Exact movement command encoding and command/address-bus occupancy.
- `ACT_MOV` participation in `tRRD`, `tFAW`, activation-current, and other
  Rank/Channel constraints.
- Exact movement command metadata and interaction with row policies,
  disturbance/maintenance plugins, tracing, and statistics.
- Movement Column units, valid range, alignment, HFF-selected datapath mapping,
  and detailed transfer quantization.
- Exact physical movement PRE scope and its relation to the Bank-level
  simulator abstraction.
