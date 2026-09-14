Status: Accepted

Question

What input-length and partial-group contract do the INT8, FP8-E4M3 and
FP8-E5M2 GEMV macros implement on the existing four-position movement model?

Decision

Accepted by the user on 2026-09-14:

- N must be positive and divisible by HFFS_PER_MAT (four in this baseline).
- N need not be divisible by MAT_SIZE (512). Partial final mats remain
  supported, including N=516.
- Arbitrary one-to-three-element tails are unsupported: the accepted LC/GB
  movement model transfers whole four-position groups and has no partial-group
  masking or write semantics.
- Reject unsupported lengths explicitly. This milestone introduces no
  partial-group movement, masking, padding, or host fallback.

The [canonical CUDA specification](../references/gpu-pud-gemv-programming-model.cu)
and its [summary](../references/gpu-pud-gemv-programming-model.md) supply the
three separate arithmetic/macro interfaces and exact reduction graph. Apply
the existing forward fold and highest-reachable sink, then the intra-mat
LC-MOV/ADD graph and specified GPU scalar residual/domain combination.
That final combination is the existing completion boundary, not a tail fallback.

PuD micro-operation-level temporary rows remain private to lowered ADD/MUL operations;
their counts come from the operation generator. PuD macro-operation-level temporary rows
hold values across operations. Same-mat micro-operations are serialized.
This acceptance closes the length gate before WU2 in the
[integration plan](../plans/pud-gemv-trace-integration-plan.md).

Rationale

Whole-group alignment preserves the specified graph with existing movement
and full-mat-row compute. For N=516, the final mat has four valid local
products; its moved suffix starts at a group boundary and can be restored
without overwriting those four results. Irregular lengths such as N=12 also
have aligned prepass moves. Unconsumed physical columns are outside the logical
result, not extra zero-valued GEMV terms.

The earlier counterexamples explain the unsupported domain: N=3 requires
column 2 to column 0, changing HFF position; N=7 and N=513 require preservation
copies splitting a group containing new ADD results. Rounding such copies
would overwrite live results. Additional temporary rows alone supply neither
cross-position movement nor partial writes. Padding or changing the FP8 graph
is not an equivalent repair under the existing arithmetic contract.

This is a project macro-domain choice, not a MIMDRAM or PRADA source fact.
The broader arbitrary-tail alternative is not accepted.

Evidence

- [CUDA programming-model specification](../references/gpu-pud-gemv-programming-model.cu):
  the three reduction helpers and partial-final-mat suffix copies.
- [Accepted placement/payload](mimdram-addressing-geometry-and-payload.md):
  whole-row compute, ordered HFF positions, fixed groups and no active-lane mask.
- [Accepted reduction policy](mimdram-reduction-placement-and-movement-lowering.md):
  forward topology and the macro layer's responsibility for partial fragments.
- [Accepted substrate boundary](mimdram-substrate-and-movement-request-boundary.md):
  GPU/host final residual combination outside substrate timing.
- [MIMDRAM mapping/reduction reference](../references/mimdram-data-mapping-and-vector-reduction.md):
  physical movement granularity and source limits.
- [Current resolver](../../../src/ramulator/dram/pud_location.cpp) and
  [request validation](../../../src/ramulator/controller/pud_request_validation.cpp):
  whole compute mat-rows and explicit ordered movement groups.
- User acceptance of the positive, HFF-divisible N constraint.

Open issues

None blocks this baseline. Arbitrary tails and other movement capabilities
remain outside this milestone and require separate future authority.
