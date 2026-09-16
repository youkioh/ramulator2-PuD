Status: Accepted

Question

What are the final MIMDRAM GEMV evaluation schedules, common static placement,
and input-length contract for INT8, FP8-E4M3 and FP8-E5M2?

Decision

Accepted by the user on 2026-09-14:

Exactly two active evaluation baselines use the existing arithmetic and timing:
`MIMDRAM-InterMatFirst` and `MIMDRAM-IntraMatFirst`. Each supports INT8,
FP8-E4M3 and FP8-E5M2. CLI profiles are the baseline name followed by
`-int8`, `-fp8-e4m3`, or `-fp8-e5m2`, respectively. No generic GEMV profile,
compatibility alias, or selectable characterization placement remains active.
This cleanup maintains one unambiguous source of truth for evaluation and
avoids silently retaining a third GEMV policy. The former same-bank placement
is historical evidence in its [Superseded decision](pud-gemv-output-placement.md)
and [completed plan](../plans/pud-gemv-output-placement-plan.md).

Both baselines use one channel/rank and identical deterministic BLP-first
static placement, fastest to slowest:

```text
bank within bank group -> bank group -> legal K-mat range slot within chip
    -> chip -> subarray capacity fallback -> row-band capacity fallback
```

Every bank consumes a range slot before any bank consumes the next slot.
Select disjoint, low-to-high forward-connected ranges, checking each edge
against the existing profile's `gb_successor`. Leave a chip's remainder unused
if it cannot fit K; never cross a chip boundary. Each output reserves the
maximum K across its domains and each domain uses the required prefix.
M=2,N=12 uses bank0/mat0 and bank1/mat0; M=2,N=516 uses bank0/mats0..1
and bank1/mats0..1, all in subarray0. Banks here enumerate all bank-group/bank
pairs. Resolver and topology authority are unchanged.

Keep domains sequential in one chain per output, distinct preplaced inputs,
three reused macro workspaces, protected constants and the generated maximum
ADD/MUL micro-operation temporary-row requirement. All unused rank range slots
precede reuse in a disjoint row band. The unchanged footprint is
`F = 2*w*D + 3*w + C + T`; capacity is
`banks * subarrays * chips * floor(mats_per_chip/K) * floor(rows_per_subarray/F)`.
Reject excess capacity before lowering. Subarrays and row bands provide static
capacity only. Same-bank cross-subarray execution remains serialized; SALP for
the open-bitline organization is undecided and excluded.

For each domain, both schedules start with ranged element-wise MUL over its
participating mats and finish at the highest participating reachable mat:

- **MIMDRAM-InterMatFirst:** forward full-vector GB-MOV and destination ADD,
  preserving a partial destination's moved suffix, then the existing intra-mat
  LC-MOV/ADD tree at the sink. Preserve the characterization's physical
  arithmetic/movement order, translating placement only. This is the
  Figure-6-style GEMV adaptation; the K>2 fold remains a project composition.
- **MIMDRAM-IntraMatFirst:** apply that same local tree to each mat's valid
  products first. Full mats execute identical local stages as one range within
  this output; a partial final mat uses its own valid-count graph. Forward only
  the resulting HFF-width residual vector with singleton GB-MOV and destination
  ADD, taking destination local residuals as left operand and the incoming
  accumulator as right operand. Output rows are distinct from inputs. No
  further sink tree is required. With the accepted length constraint each
  participating mat returns exactly four residuals in the current profile.

Ranged LC uses the Accepted common rows/selectors at every selected mat and
copies locally, never between those mats. Ranged operations are confined to
one GEMV output. Existing primitives, controller scheduling, timing parameters
and no-SALP behavior remain unchanged.

For each domain, GPU completion starts at zero, adds residuals in ascending
lane order, then adds the domain sum to the output accumulator in ascending
domain order. Its costs remain outside PuD timing. FP8 is non-associative:
validate each baseline against its own scalar execution graph, without
requiring equality between baselines or adding accuracy evaluation. Primitive,
LC, GB, total Request counts, controller cycles and peak inflight are reported
under identical placement/configuration. Cycle differences are evidence, not
fixed correctness oracles.

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
separate arithmetic interfaces and both exact reduction graphs. Apply the
selected baseline and the specified GPU scalar residual/domain combination.
That final combination is the existing completion boundary, not a tail fallback.

PuD micro-operation-level temporary rows remain private to lowered ADD/MUL operations;
their counts come from the operation generator. PuD macro-operation-level temporary rows
hold values across operations. Same-mat micro-operations are serialized.
This acceptance closes the length gate before WU2 in the
[integration plan](../plans/pud-gemv-trace-integration-plan.md).

Accepted by the user on 2026-09-15: the standalone phase-latency experiment
measures MUL and reduction within one normal full execution, using generator
layout boundary indices and opaque PuDTrace acceptance/completion checkpoints.
It rejects multi-domain inputs because their chains interleave MUL and
reduction; general GEMV generation/execution retains multi-domain support.
Physical Requests, traces, placement, scheduling and controller timing stay
unchanged. The [user guide](../ddr4-pud-user-guide.md#gemv-trace-generation-and-execution)
defines the timestamp and output conventions.

Rationale

Bank striping exposes BLP before additional same-bank mat placement. Comparing
the Figure-6-style inter-mat-first order with local-first reduction isolates
the reduction schedule while preserving placement, supported operations and
completion boundaries. Existing ranged LC authority permits the identical
local stages within one output; it requires no movement-model extension.

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

- User acceptance of both named baseline policies and WU1-WU4 on 2026-09-14.
- [Accepted addressing/payload](mimdram-addressing-geometry-and-payload.md):
  LC's common nonempty range, common rows/selectors and per-mat local copies.
  [Substrate boundary](mimdram-substrate-and-movement-request-boundary.md)
  explicitly calls this a lockstep range. Current request validation accepts it.
- [Baseline implementation plan](../plans/pud-gemv-baselines-plan.md):
  characterization audit, functional/Request validation and timing evidence.

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
