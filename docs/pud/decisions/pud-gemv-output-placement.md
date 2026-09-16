Status: Superseded

Question

How should the GEMV macro generator place independent outputs for controlled
characterization of mat-level MIMD under the existing resolver and execution
model, separately from the final GEMV evaluation baseline placement policy?

Decision

Superseded on 2026-09-14 by the [Accepted GEMV baseline contract](pud-gemv-macro-contract.md).
The placement below is preserved only as historical characterization authority;
it is no longer an active generator policy. Its rationale and completed
measurements remain historical evidence.

Accepted by the user on 2026-09-14 as a **mat-level parallelism characterization
placement**, with the no-SALP boundary below. Alternative A is not the final
GEMV baseline placement policy. This authority covers the characterization
placement and its static capacity fallback, separately from the Accepted
[numeric/macro contract](pud-gemv-macro-contract.md) and the substrate's
[location authority](mimdram-addressing-geometry-and-payload.md). It selects
allocation order, not new topology, timing, scheduling, or arithmetic.

The actual GEMV baseline evaluation policy will be defined separately and is
expected to exploit bank-level parallelism (BLP) before serialization is
attributed to the MIMDRAM-style baseline. The same-bank characterization below
does not establish that baseline's performance or placement policy.

Select alternative A:

| Alternative | Order after filling disjoint ranges across the chips of one bank/subarray | Trade-off |
| --- | --- | --- |
| A: banks before subarrays | Next bank within the bank group, then next bank group; after all banks, next subarray index across those banks | Uses another bank that can progress independently before using a different subarray that must serialize with its bank's current work. |
| B: subarrays before banks | Next subarray of the same bank; after all subarrays, next bank and bank group | Preserves the current generator's context order, but delays access to independent banks and adds no same-bank subarray execution parallelism. |

This controlled experiment intentionally excludes bank-level placement
parallelism and SALP to isolate mat-level PuD MIMD. Keep M=2,N=12 and M=2,N=516
in the same bank and same subarray, using mats 0/1 and ranges 0..1/2..3
respectively. Do not stripe these experiments across banks. Subarrays are
static capacity fallback only, never independent parallel execution resources.
SALP under the open-bitline organization remains undecided; this acceptance
introduces no SALP model or concurrency claim. Command/resource timelines
characterize the remaining serialization within this controlled placement.

Use the following bounded static policy:

1. Keep one channel and one rank. Obtain dimensions and directed successors
   from the existing C++ placement-profile binding. Within each chip's forward
   path, take consecutive, non-overlapping ranges from low to high. Verify
   every required edge through `gb_successor`; numerical adjacency alone is
   insufficient. A range never crosses a chip or subarray boundary. If fewer
   than K mats remain, leave them unused and advance to the next chip.
2. For domain d of an output, retain the existing input partition and derive
   `K_d = ceil(elements_in_reduction_domain_d / MAT_SIZE)`. Reserve one range
   of `K_output = max_d(K_d)` mats for that output. Each domain uses its first
   K_d mats, in forward order, with the last participating mat as sink.
   For a single domain, K_output equals K_d. With N greater than 8192 in the
   current profile, K_output is 16; a final partial domain uses a prefix.
3. Keep all domains of an output in its one placement context and chain,
   in increasing input-index order. Retain distinct preplaced A/x rows for
   every domain, the three reused macro workspaces, protected constants, and
   the generated maximum ADD/MUL micro-operation temporary-row requirement.
   Retain external domain readout before workspace reuse and the exact GPU
   residual/domain combination. Do not distribute one output's domains over
   new contexts or introduce cross-domain movement.
4. Exhaust unused ranges in the current chip, then other chips in the same
   bank/subarray. Apply A to advance contexts. Exhaust all physical
   range slots in the rank before revisiting them in another row band.
   Assign increasing output IDs in that order; placement does not depend on
   engine count, observed timing, runtime completion, or workload values.
5. A row band belongs to one output on its reserved mat range. Identical
   local-row numbers in disjoint ranges name different physical storage;
   they do not share temporary rows. Revisited ranges use a new, disjoint
   band. This retains static storage ownership and permits capacity fallback
   without pretending that new rows provide new mat execution resources.
   Reject an output footprint larger than one subarray's row extent, or M
   beyond the resulting static capacity. No runtime allocator is introduced.

For A, the implemented fastest-to-slowest enumeration remains:

```text
K-mat range within chip -> chip -> bank within bank group -> bank group
    -> subarray -> output row band
```

Advancement beyond the same-bank/same-subarray ranges retains static capacity
fallback. It does not define the final evaluation policy; the two controlled
measurements below that capacity boundary intentionally exercise neither
bank-level placement parallelism nor SALP.

For equal K_output=K and the current linear profile, let
`q=floor(16/K)`, `P=8*q`, `B=4*4=16`, `S=65536/1024=64`.
Every output has the same N/profile, so no variable-size packing is needed.

| Quantity | Bound or capacity |
| --- | --- |
| Disjoint complete output ranges per chip | q |
| Disjoint complete output ranges per bank/subarray | P |
| Disjoint physical range slots across the rank | B*S*P |
| Concurrent compute allocations using these complete K-mat ranges, with ready work in all banks and no other blockers | At most min(E, B*P), E=8 by default |
| Same-bank concurrent compute allocations in one subarray | At most min(E, P) |

Thus K=1 gives 16 ranges/chip and 128/bank/subarray; K=2 gives 8 and 64;
K=16 gives 1 and 8. The engine pool is shared across banks/ranks. S and
additional row bands increase placement capacity, not the same-bank compute
concurrency bound. These are resource bounds, not guaranteed overlap or
complete-GEMV speedups: later requests may target smaller ranges; LC/GB remains
bank-exclusive, and shared command issue and existing timing still apply.

Let D be the unchanged domain count, w the operation output-row width, C the
number of protected constant rows, and T the generated maximum ADD/MUL
micro-operation temporary-row count. Preserve the current footprint:

```text
F = 2*w*D + 3*w + C + T
R = floor(rows_per_subarray / F)
M_capacity = B*S*P*R
```

This is capacity for the selected uniform reservation, not a global optimum
using gaps or packing differently sized domains. For one-domain INT8, F=60
and R=17; E4M3 uses F=64/R=16, E5M2 F=59/R=17. Derive these from operation
requirements, never hard-code them. Exhausting all B*S*P slots begins band 1
at local row F on the first range. Exhausting R bands rejects the layout.

Rationale

The programming model duplicates x per output to permit independent dot
products. Range placement exposes that opportunity while preserving operand
colocation and the existing forward fold. Reserving the maximum domain width
preserves the existing sequential workspace reuse instead of adding a domain
allocator. Filling mats before advancing contexts keeps the controlled
experiments in one bank/subarray, isolating mat-level concurrency.

Alternative A was selected because the Accepted execution model prohibits
same-bank subarray parallelism. Extra chips supply disjoint compute resources
within that bank's active subarray, and extra banks can also overlap movement.
Neither distinct chips nor disjoint mats bypass same-bank movement exclusion.
The row-band fallback preserves useful static storage capacity after unused
physical ranges are exhausted. It creates no runtime waves or dependencies.

Evidence

- [Canonical CUDA specification](../references/gpu-pud-gemv-programming-model.cu)
  and [programming-model reference](../references/gpu-pud-gemv-programming-model.md):
  x duplication, per-domain K, workspace ownership, exact reduction and host
  completion graph. Domain-local mat numbering is mapped to selected physical
  ranges; it does not require physical mat zero.
- [Mapping/reduction reference](../references/mimdram-data-mapping-and-vector-reduction.md):
  mat-range execution and operand colocation; it does not prescribe this
  application's static traversal order.
- Accepted [forward reduction](mimdram-reduction-placement-and-movement-lowering.md),
  [placement profile](mimdram-addressing-geometry-and-payload.md), and
  [execution/resources](mimdram-movement-execution-ownership-and-device.md)
  permit shifted chip-local ranges but preserve no SALP and bank-exclusive
  movement. [Physical lowering](pud-operation-physical-lowering.md) explicitly
  leaves bank/subarray/mat selection to its caller.
- [LocationResolver](../../../src/ramulator/dram/pud_location.cpp),
  [profile binding](../../../src/ramulator/python/bindings.cpp),
  [controller resource checks](../../../src/ramulator/controller/controller_base.cpp),
  and [engine allocation](../../../src/ramulator/controller/impl/generic_ddr_controller.cpp)
  implement these dimensions and restrictions. The
  [milestone plan](../plans/pud-gemv-output-placement-plan.md) records the
  current generator audit and focused verification.

Open issues

- The GEMV baseline evaluation placement policy remains to be defined
  separately under the BLP expectation above. The characterization's LC/GB
  bank-exclusive bottleneck must not be generalized to that baseline.
- SALP under the open-bitline organization remains undecided and excluded.
  Subarray advancement must not be interpreted as concurrent execution.
- Mat-level gains remain subject to bank-exclusive movement and shared command
  issue. Measurement evidence belongs in the milestone plan; static capacity
  and peak inflight alone do not establish execution overlap.
