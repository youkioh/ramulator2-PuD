Status: Accepted

Question

How should directly generated reductions merge mat-local fragments using the
accepted directed GB topology, while distinguishing the project's supported
movement unit from MIMDRAM's ranged GB-MOV interface and unspecified generic
`bbop_mov` lowering?

Decision

The user accepted this project direction on 2026-09-09. This is a
reduction-orchestration and movement-lowering boundary, not a new substrate
Gate. It preserves Accepted [Gate A](mimdram-substrate-and-movement-request-boundary.md),
[Gate B](mimdram-addressing-geometry-and-payload.md), and Gate C's
[execution](mimdram-movement-execution-ownership-and-device.md) and
[timing/transport](mimdram-movement-timing-and-resource-model.md) behavior.

**A. Scope**

The project does not reproduce MIMDRAM's generic compiler or accept arbitrary
compiler-generated `bbop_mov` operations. It will generate the required
reduction request streams directly. Solving the complete generic MIMDRAM
movement-routing problem is therefore not a prerequisite for continuing
substrate implementation.

This decision records placement and composition policy only. Arithmetic and
reduction macros remain outside the existing
[substrate implementation plan](../plans/mimdram-pud-substrate-v2-implementation-plan.md);
its W3-W9 work remains unchanged. No compiler, generic lowering, or reduction
implementation is authorized by this documentation decision.

**B. Low-level modeled GB operation**

Retain the existing singleton directed GB request as the project's
source-defensible low-level inter-mat movement unit:

```text
one source mat
    ->
one profile-supported directed neighboring destination mat
```

Each request transfers one HFF-width source/destination group, with Gate B's
ordered position correspondence and shared placement context. This is a
supported conservative subset/lowering unit. It is **not** a claim that
MIMDRAM's published GB-MOV interface is singleton-only: that interface accepts
source and destination logical mat ranges, whose wider-range execution is
not fully specified by the cited source.

The profile-defined directed GB topology is authoritative. Do not invent
reverse, wrapping, cross-chip, or magical arbitrary-distance GB edges.

**C. Direct reduction placement policy**

Divide each reduction input into mat-local fragments according to the Accepted
Gate B placement profile. Within each connected GB domain, arrange and reason
about the participating fragments in the forward order of the directed
physical/modeled topology. Select a reduction sink reachable through forward
neighboring edges; do not generate a schedule requiring a reverse GB edge.

For the initial linear chip-local topology, reduce from lower local mats toward
the highest selected local mat. For K consecutive participating mats in one
connected linear domain, use the conceptual forward fold:

```text
fragment0 -> mat1, ADD
accumulated01 -> mat2, ADD
...
accumulated[0..K-2] -> mat[K-1], ADD
```

Here `mat0` through `mat[K-1]` denote the selected consecutive mats in topology
order, not necessarily local IDs starting at zero. Each arrow copies the
current full partial fragment using repeated supported one-hop requests;
the destination ADD combines it with that mat's local fragment. After the
inter-mat fold, perform the source-described intra-mat LC-MOV + ADD tree in
the sink to four residual elements. A single participating mat needs only
the intra-mat reduction.

The extension from the two-mat example to this K-mat fold is an Accepted
project orchestration choice, not a merge schedule explicitly supplied by
MIMDRAM. It adds no interconnect. It also does not select an ADD primitive
sequence, scratch-row allocation, or numeric macro contract. Dependent work
remains subject to Gate C's producer-completion boundary.

**D. Reachability boundary**

If selected fragments cannot be connected by the accepted directed GB
topology, do not invent reverse or cross-chip GB and do not silently assume
arbitrary multi-hop routing. Placement for the current direct-reduction
workload must avoid such unreachable moves within a reduction domain.

Each connected chip-local reduction domain produces its own four residual
elements. Multiple disconnected/chip-local domains finish separately and
are combined by the host under Gate A's existing completion and accounting
boundary. Four residuals per domain does not mean four residuals for the
whole workload when connectivity cannot merge all contributions.

Forward multi-hop through intermediate scratch is structurally expressible in
the project model by composing accepted directed one-hop transfers. It is not
required by
the selected consecutive-mat placement and forward fold: each fold step
merges at the next participating neighbor. Scratch/dependency semantics for
such composition and generic multi-hop `bbop_mov` routing are neither
source-established nor accepted capabilities; they require a later decision.

**E. Movement-count derivation boundary**

Let:

- `L` be the number of elements represented in one source mat fragment;
- `H` be the HFF/interconnect width in element positions per bit-plane transfer
  (initial profile `H = 4`);
- `w` be the represented bit width moved at that reduction stage.

One low-level GB request transfers one bit from each of H element positions,
not H complete w-bit elements. For a full one-hop transfer of an L-element
fragment, with L divisible by H:

```text
N_GB_one_hop = (L / H) * w
```

For the initial `L = 512`, `H = 4` profile:

```text
N_GB_one_hop = 128 * w
```

For the selected K-mat forward fold, with L elements in each transferred
partial fragment and constant represented width:

```text
N_GB = (K - 1) * (L / H) * w
```

If represented width changes between fold stages:

```text
N_GB = (L / H) * sum(w_j)
```

The sum runs over the K-1 inter-mat fold transfers, with `w_j` the width
actually moved at transfer j. These equations count the project's conservative
singleton lowering requests, not ISA instructions, ranged-command parallelism,
or elapsed cycles. They do not claim MIMDRAM's minimum GB-MOV command count:
its unspecified wider-range semantics might exploit parallel range execution.

These equations are **project derivations** from the source-described
HFF-width granularity, repeated copying until all source elements move, and
the selected forward-fold schedule. They are not equations explicitly
provided by MIMDRAM. No INT8/FP8 accumulator precision is selected here;
input precision alone must not be substituted for the represented width of
an accumulated fragment.

Exact LC-MOV and ADD counts depend on the future reduction/numeric macro
contract. The source establishes the single-mat adder-tree endpoint of four
elements, without fixing this project's full primitive sequence or counts.
Partially occupied final fragments and element counts not divisible by H also
remain for the future reduction/numeric macro contract.

**F. Terminology**

`LogicalMatID` denotes the simulator's global mat identifier across the chips
of a placement-profile bank/subarray context. Under that profile and the
retained external context it identifies a modeled physical mat; the bare
integer is not unique across Banks, Ranks, or subarrays. The initial profile
decodes it to `(Chip, LocalMat)` using Gate B's `16 * Chip + LocalMat` encoding.
This is not a claim about vendor-secret physical mat numbering.

Physical/modeled GB adjacency comes from the profile topology. Consumers
must not reconstruct adjacency from numerical ID adjacency. Consecutive IDs
at a chip boundary, for example, do not create a GB edge.

Rationale

The motivation extends beyond Figure 6's two-mat example. At 512 represented
elements per mat, a 2048-element vector spans four mat-local fragments; larger
vectors likewise need an explicit rule for merging contributions across mats.
The forward fold supplies that rule using only accepted movement units.

Direct generation lets the project choose reachable placement and schedules
without inventing the unspecified parts of generic MIMDRAM movement lowering.
Keeping disconnected domains separate preserves Gate A's host-completion
boundary. Separating the published ranged interface from the supported
singleton unit avoids presenting a conservative model as the complete ISA.

Evidence

- [Curated MIMDRAM movement reference](../references/mimdram-inter-column-data-movement.md),
  §§1.3, 1.5, 1.6, and 4: source instruction/interface, directed neighboring
  datapath, reduction example, precision dependence, and explicit lowering
  gaps. The underlying paper sections are §§4.1, 4.1.1, 4.2, 5, and 6.1.
- [Geometry reference](../references/mimdram-geometry.md) records evaluated
  dimensions; Gate B supplies the accepted simulator placement and topology.
  Neither reference establishes vendor physical numbering or the K-mat fold.
- Current W1/W2 [location authority](../../../src/ramulator/dram/pud_location.cpp)
  and [request validation](../../../src/ramulator/controller/pud_request_validation.cpp)
  retain profile-defined directed neighbors and validate singleton GB
  endpoints. This verifies existing terminology and supported request shape,
  not implemented reduction behavior.
- The user selected direct generation, forward-fold placement, the retained
  low-level GB unit, and the count framework. These are project decisions
  and derivations, not additional source facts or changes to Gates A/B/C.

Open issues

- The source/specification gaps catalogued in the movement reference remain:
  multi-mat GB pairing and simultaneous execution, overlapping ranges,
  non-neighbor/forward multi-hop lowering and scratch interaction, reverse
  routing, cross-chip routing, and the exact lowering algorithm for those
  cases. They are not established paper errors or substrate prerequisites.
- The future reduction/numeric macro must determine represented and accumulator
  precision, arithmetic behavior, concrete ADD/LC-MOV sequences and counts,
  scratch use, and explicit dependencies. This decision fixes none of those
  implementation details or INT8/FP8 choices.
- Generic `bbop_mov` routing or additional supported placement/topology would
  require a later decision; neither is promised by this boundary.
