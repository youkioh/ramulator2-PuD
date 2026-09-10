Status: Accepted

Question

Where should MIMDRAM inter-column movement live relative to the completed
DDR4_PuD baseline, and what does one externally submitted movement request
represent? What experiment, hybrid-compute, concurrency, timing-fidelity, and
reduction boundary should MIMDRAM-based PuD substrate v2 support?

Decision

**Current status (2026-09-10).** The
[unified-substrate decision](ddr4-pud-unified-substrate.md) is now the
top-level public execution-model authority, and W1-W9 implemented this
document's retained hybrid, concurrency, movement, and fidelity boundaries.
`v2`, `legacy`, and the distinct-combined-standard wording below record
development and internal composition, not separate selectable public models.
Acceptance-time statements that implementation was unavailable or that Gate C
still had to supply substrate costs are historical; T-A and the current Gate C
authorities govern those details.

Accept v2 Gate A on 2026-09-08, including the compute-phase/overhead,
substrate/macro, and overlap-validation clarifications below. This document
is the canonical experiment and substrate-boundary authority. Accepted
[Gate B](mimdram-addressing-geometry-and-payload.md) remains fixed. Gate C was
accepted on 2026-09-09 in the canonical
[execution](mimdram-movement-execution-ownership-and-device.md) and
[timing/transport](mimdram-movement-timing-and-resource-model.md) authorities.
The same-subarray clarification below was accepted with Gate C. These
acceptances authorize neither code changes nor an implementation plan.

**Existing combined-standard boundary**

Introduce MIMDRAM LC-MOV and GB-MOV in a distinct combined experimental DRAM
standard derived at the Python-definition level from DDR4_PuD. Independently
copy inherited mutable standard definitions before extending them. Leave the
existing DDR4 and DDR4_PuD standards unchanged.

The combined standard inherits existing DDR4_PuD RowCopy, MAJ3, MAJ5, NOT,
and NOT_COPY behavior without changing their semantics. Movement-specific addressing,
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

The existing executable combined standard is `DDR4_PuD_Movement`; its name
does not imply a complete MIMDRAM model. Its Bank-conservative execution and
timing remain governed by the accepted
[execution](mimdram-movement-execution-ownership-and-device.md) and
[timing](mimdram-movement-timing-and-resource-model.md) decisions. Gate B
supplies current v2 addressing authority and preserves the legacy placement
boundary. Legacy Bank serialization and transport abstractions do not
override the accepted v2 Gate C refinements or the experiment contract below.

**V2 target claim and hybrid boundary**

Accepted Gate A project choice: an experimental PRADA/MIMDRAM hybrid
supporting functional mat-scoped computation and LC/GB movement under Gate B
placement, with independent same-Bank compute execution and conservative
movement scheduling. This supports architectural timing experiments under
declared assumptions, not physical equivalence to either complete design or
reproduction of MIMDRAM's published end-to-end performance.

Source facts: the curated PRADA references describe RowCopy, MAJ3, MAJ5,
NOT, and NOT-and-copy; MIMDRAM describes mat selection, independent execution,
and LC/GB movement. The supplied sources do not establish that MIMDRAM
physically validates PRADA's complete circuit/timing model unchanged.

Accepted Gate A hybrid assumption: apply all five PRADA mechanisms and Gate
B's conditional pointwise compute effects to its explicitly selected
mat-rows. This accepts those effects, including destructive majority and NOT
behavior, without changing Gate B geometry or placement. Initially support
majority only with distinct physical-row operands; repeated-row charge-sharing
semantics are unsupported. Unselected locations remain preserved under Gate B.

**Required MIMD concurrency fidelity**

Source fact: MIMDRAM supports independent PUD execution on available disjoint
mat ranges. Its overlapping GB endpoint activations describe concurrency
within one movement invocation, not between independent GB requests. The
curated reference does not establish pairwise movement shared-resource rules.

Accepted Gate A project policy:

| Independent request pair in one Bank | Initial policy |
| --- | --- |
| Compute/compute on disjoint resolved mat ranges within one subarray | Overlap allowed and required as a supported capability. |
| Compute/compute in different subarrays of one Bank | Serialized in the baseline; SALP-style concurrency is outside scope. |
| Compute/compute on intersecting resolved mat ranges | Conflicting execution is serialized. |
| Compute/LC-MOV or compute/GB-MOV | Bank-serialized. |
| LC-MOV/LC-MOV | Bank-serialized, even for disjoint ranges. |
| GB-MOV/GB-MOV | Bank-serialized, even for disjoint endpoint pairs. |
| LC-MOV/GB-MOV | Bank-serialized. |

At least two independent compute requests on disjoint resolved mat ranges
must be able to overlap in execution while preserving independent state,
data, and recovery, within one subarray. Same-Bank cross-subarray compute
remains serialized through recovery; SALP-style concurrency is outside scope.
One range's close or recovery must not reset another disjoint range in that
subarray. Finite capacity and legitimate shared-resource waiting still apply.
Disjointness is evaluated in the full Gate B resolved execution context
(Channel, Rank, BankGroup, Bank, Subarray, Chip, Mat), not by comparing bare
logical mat numbers from different subarrays or Banks. Mat-resource overlap
is distinct from equality of operand cell footprints.

The architectural requirement does not require different primitive types.
Validation must cover same-operation overlap and at least one heterogeneous
compute-operation overlap case. Overlap means independent execution progress,
not merely simultaneous admission. Shared command issue and legitimate shared
constraints still apply; same-cycle multi-command issue and linear speedup
are not required. Exact arbitration, capacity, and reservation/recovery
boundaries are defined by the accepted Gate C authorities linked above.

Movement serialization is a conservative project reservation policy, not a
claim that every pair physically conflicts. Disjoint mats do not establish
independence of local/global I/O, control, or transport resources. The target
therefore supports MIMD compute performance under conservative movement
scheduling, not full movement-concurrency fidelity. Fully Bank-serial compute
could support functional studies but would not meet this v2 MIMD target.

**Compute timing and substrate overhead**

Accepted existing timing decision: retain the PRADA-derived phase decomposition,
including the assumed `tCS`, derived sensing/restoration interval, and
independently rounded timing intervals. Source evidence and derivation remain
in the timing reference; not every phase cost is directly reported by PRADA.

Accepted Gate A hybrid timing assumption: initial local compute phase costs
are independent of selected mat-range width. Retain the existing incremental
cost per RowCopy destination. Do not invent width-dependent compute timing;
the supplied evidence does not establish such a model.

Distinguish:

```text
local PRADA-derived compute phase cost
    +
MIMDRAM substrate scheduling/target-transport/shared-resource overhead
```

Current implementation fact: isolated legacy single-destination RowCopy,
MAJ3, MAJ5, NOT, and NOT_COPY totals are respectively 61/66/76/99/104 CK at
`DDR4_2400R`, including final legacy precharge recovery. These are baseline
calibration results, not complete MIMDRAM-v2 request latencies or measurements
of mat-width scaling. Gate C must account for queueing, mat-target transport,
arbitration, resource contention, and recovery interactions, which may
increase observed request latency. It must distinguish local work from
overlapping/shared costs and avoid double-counting the recovery already
included in the legacy totals. Gate A does not select overhead values, timing
edges, or their resource scope.

**Reduction mechanisms and host completion**

Source fact: MIMDRAM describes inter-mat GB-MOV + ADD followed by an intra-mat
LC-MOV + ADD tree reducing to four residual elements. Movement counts depend
on precision; four transferred bits are not four complete arbitrary-precision
elements. The curated source supplies no subsequent 4-to-1 mechanism.

Accepted Gate A substrate requirement: provide mat-scoped compute, GB-MOV,
LC-MOV, and dependency-safe request execution/completion sufficient to express
that source-described path under Gate B. The concrete ADD primitive sequence,
scratch placement, precision-specific movement counts, arithmetic policy, and
complete reduction request stream belong to the later operation/macro layer.
Neither an INT/FP ADD implementation nor a reduction macro is a substrate
implementation requirement. Submission order alone must not be assumed to
establish cross-request dependencies; the completion/dependency contract is
resolved in Gate C.

Accepted Gate A completion boundary: four residuals per legally reduced
domain, with all remaining combination performed by the host. Where supported
connectivity cannot merge contributions, retain separate partial outputs for
host combination rather than claiming four residuals for the whole workload.
No cross-position shuffle or all-in-DRAM scalar reduction is added to Gate B.

Substrate reduction timing, when a later explicit macro is evaluated, ends
after recovery of its final required primitive. Host readout, representation
conversion, and remaining arithmetic require separate accounting before
claiming scalar-result latency. A concrete macro's correctness and timing
require its precision, scratch use, legal movements, and dependencies to be
specified; Gate A supplies no reduction latency or request count.

**Connectivity and experiment limits**

Accepted existing Gate B boundary: LC copies locally across its selected
lockstep range; GB uses singleton directed local-mat neighbors `i-1 -> i`
within one chip and derived subarray, with the accepted common external
placement context. A chip-crossing LC range does not transfer data across
chips. Retain this topology without refinement. Arbitrary non-neighbor or
reverse GB, wrapping, cross-chip movement, wider GB endpoint ranges, and
automatic multihop routing remain unsupported. A later supplied stream may
compose legal operations with explicit scratch/dependencies; Gate A promises
neither arbitrary endpoint reachability nor an automatic routing service.

Accepted Gate A experiment boundary: inputs may already be allocated,
initialized, bitsliced, and placed according to Gate B. Allocator, compiler,
transposition machinery, full ISA integration, the full INT8/FP8/GEMV macro
library, and their costs are outside substrate scope.

Once implemented and validated, supported claims are functional correctness
of mat-scoped operations and explicit compositions, modeled primitive latency,
same-Bank compute overlap on supported disjoint resources, and reduction timing
under the declared placement/movement/resource model. These are target
capabilities, not current implementation results.

Unsupported claims include complete MIMDRAM throughput or end-to-end GEMV
speedup, physically exact mat-transport/C/A occupancy or queue saturation,
fully validated local/global-I/O contention, activation-current constraints,
refresh-retention guarantees, unchanged hybrid circuit compatibility,
physical reliability, energy, or area. Conservative movement serialization
does not make total predicted performance a proven physical lower bound:
omitted costs can bias results in the opposite direction. Existing T3
transport and movement-timing omissions remain evidence limits, not physical
zero-cost or resource-exemption claims; their v2 treatment is defined by Gate C.

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

For v2, disjoint compute overlap preserves MIMDRAM's defining MIMD capability;
retaining full Bank serialization would lose that performance behavior.
Conservative movement serialization avoids inventing pairwise physical I/O
concurrency. Fixed local compute phase costs expose the hybrid timing
assumption without inventing width scaling or hiding substrate overhead.
The four-residual/host boundary follows the available reduction evidence and
accepted connectivity while leaving arithmetic construction to the macro
layer. These are accepted project choices, not additional source facts.

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

For v2 Gate A:

- **Source facts and limits:** [PRADA primitives](../references/pud-primitives.md),
  [compute timing evidence](../references/ddr4-pud-timing-reference.md), and
  [MIMDRAM movement reference](../references/mimdram-inter-column-data-movement.md),
  especially §§1.2, 1.4–1.6, 3, and 4. These distinguish reported mechanisms
  from timing derivations, architectural inferences, and absent conflict or
  scalar-reduction evidence.
- **Accepted existing authority:** [Gate B](mimdram-addressing-geometry-and-payload.md),
  [compute timing/resources](pud-timing-resource-and-command-bus-rules.md),
  [historical compute lifecycle](pud-request-lifecycle-queueing-and-statistics.md), and
  the legacy movement execution/timing decisions linked above. Legacy
  ownership release and recovery/callback separation do not resolve v2 state,
  conflict, or data-visibility semantics.
- **Current implementation facts:** [GenericDDR ownership](../../../src/ramulator/controller/impl/generic_ddr_controller.cpp),
  [compute timing configuration](../../../python/ramulator/dram/ddr4_pud.py),
  [occurrence sequencing](../../../src/ramulator/controller/pud_sequence.cpp),
  and [movement read/write actions](../../../src/ramulator/dram/commands/RD_MOV.h)
  retain Bank-level exclusion, timing, and phase markers rather than
  mat-scoped functional execution. [Compute timing tests](../../../tests/device_timings/test_ddr4_pud.py),
  [movement timing tests](../../../tests/controller_scheduling/GenericDDRController/test_movement_local_timing.py),
  and [ownership tests](../../../tests/controller_scheduling/GenericDDRController/test_movement_ownership.py)
  assert the legacy model, not v2 mat independence or physical correctness.
  Source/tests were inspected for Gate A; runtime suites were not rerun.
- **Newly accepted project assumptions:** the v2 hybrid, fixed local compute
  phase costs, pairwise overlap policy, substrate/macro boundary, host
  completion, and qualified experiment claims above were approved by the user
  on 2026-09-08. They do not derive authority from implementation behavior.

Open issues

- Gate C is accepted in the execution and timing/transport authorities linked
  above. Its implementation and validation remain future work; acceptance is
  not evidence of executable v2 support.
- Future workload/frontend integration, `bbop_mov` lowering, array placement,
  arithmetic/reduction macros, batching, and routing above the accepted
  one-invocation request boundary remain later operation-layer work.
