Status: Accepted

Question

What initial contract should `tools/pud_operation_generator` use to lower one
fixed symbolic PuD primitive trace to legal physical local-row bindings within
an already selected canonical execution context?

Decision

## Scope

Lower one fixed symbolic PuD primitive trace to legal physical local-row
bindings. Preserve primitive order, the arithmetic-core primitive sequence,
symbolic identity semantics, and destructive primitive semantics.

Do not reorder primitives, recompute values, alias identities merely because
their values are equal, or generally coalesce internal copies. The only
sequence rewrite accepted in this milestone is elimination of the terminal
output-export RowCopy operations defined below.

## Physical execution context

Allocation operates within one already selected canonical execution context:
one Bank, one subarray, and one explicit `MatRange`. It assigns symbolic rows
to local physical row numbers within that context; it does not choose the
Bank, subarray, or `MatRange` placement.

One symbolic-to-local-row binding applies uniformly across the selected
`MatRange`. Mat placement and GEMV layout are separate higher-level concerns.

## Inputs

Every input symbolic row has a caller-provided designated physical row. Inputs
are precolored to those rows and protected for the complete operation. The
allocator must not reuse an input row as scratch, including after that input's
final arithmetic read. This preserves the current generator contract and
permits later macro operations to reuse operands.

## Constants

Every declared `CONST_ZERO` or `CONST_ONE` symbolic row has a designated
physical row. Declared constants are precolored to those rows and protected
for the complete operation; their rows are not part of the reusable scratch
pool. This decision does not prescribe how a higher-level runtime initializes
or shares constant rows across separate operation invocations.

## Outputs

The GEMV-facing INT8 and FP8 ADD/MUL profiles consume and expose 8-bit values;
their only output names are `R0..R7`. INT8 ADD retains its full signed nine-bit
internal computation. INT8 MUL retains its full signed 16-bit product,
generating and reducing all columns 0..15 in LSB-to-MSB order with the existing
signed corrections. Only the low eight result bits are exported. High bits
are diagnostics, not designated outputs, and do not extend physical lifetimes.
This is an accepted project interface choice, not a claim about PRADA's
original output interface. UINT8 and FP8 arithmetic policies are unchanged.
UINT8 MUL uses the same column-streaming schedule through columns 0..15 while
retaining its exact full 16-bit output `R0..R15`.

Future GEMV composes the existing MUL and ADD PuD operations. No separate FMA
PuD operation is introduced. GEMV implementation and placement remain deferred.
There is no explicit truncation primitive or extra RowCopy sequence; the
export selection defines the fixed-width boundary. The physical lowerer
preserves the resulting emitted sequence under the contract below.

Every output `Rn` has a caller- or layout-provided designated physical row
`P(Rn)`. Output rows are precolored physical colors, but they are not reserved
from operation entry. Before the live interval of the final symbolic producer
assigned to `Rn` begins, `P(Rn)` may hold earlier nonoverlapping temporary
identities.

For every terminal symbolic export:

```text
RowCopy(final_source, Rn)
```

physical lowering removes that RowCopy and requires:

```text
phys(final_source) = P(Rn)
```

for the complete live interval of `final_source`. The output name `Rn` denotes
that designated binding and does not require a second physical identity or
primitive after lowering. After the final result value is produced, the value
in `P(Rn)` remains valid through operation completion. The deleted RowCopy
contributes no physical primitive, timing, or energy cost to the lowered
trace.

Different live outputs require distinct designated physical rows. Protected
input and declared-constant rows must not overlap designated output rows in
this initial contract. Caller-provided precoloring must itself satisfy all
simultaneous-lifetime and primitive-legality constraints; otherwise lowering
fails.

## Work-row allocation

All non-input, non-constant, non-output symbolic identities are work rows. A
work identity may reuse a physical row only after the previous identity using
that row has completed its final required primitive command.

Primitive command points are closed lifetime endpoints. Therefore, an
identity ending at primitive `i` cannot share a physical row with an identity
beginning at primitive `i`; reuse may begin only at a later command. One
symbolic identity has one physical binding for its complete live interval.
The initial model does not allow live-range splitting.

## Primitive physical distinctness

Require distinct physical local rows for every simultaneously distinct
operand role required by the modeled primitive:

- RowCopy: the source and every destination are pairwise distinct.
- `NOT_COPY`: the source and every destination are pairwise distinct.
- `MAJ3`: all three participants are pairwise distinct.
- `MAJ5`: all five participants are pairwise distinct.

`NOT` operates in place and introduces no additional distinct-row
requirement. Equal post-operation values never authorize aliasing distinct
symbolic identities.

## Diagnostic state

Diagnostic taps and discarded carries are validation observations, not
architectural live-outs. They do not extend a physical-row lifetime merely so
that the final post-execution symbolic dictionary can reproduce every
intermediate name. A future physical validator may observe or snapshot such a
value at its defined observation point without reserving its row through
operation completion.

The required final functional state is preserved inputs, preserved declared
constants, and designated outputs.

## Optimization objective and accounting

The primary objective is:

```text
minimize additional scratch physical rows
```

subject to all precoloring, protection, lifetime, placement-capacity, and
primitive-legality constraints above. Report these quantities separately:

1. `additional_scratch_rows`: physical local rows required beyond the
   caller-provided designated input, constant, and output rows.
2. `designated_rows`: the number of unique caller-provided input, constant,
   and output physical rows.
3. `physical_footprint_rows`: the number of unique physical local-row numbers
   used by the lowered operation.
4. `peak_live_identities`: the maximum number of simultaneously live symbolic
   identities under this lifetime contract.

Do not equate `peak_live_identities` with the optimal scratch requirement when
precoloring constraints are present. Do not claim a global minimum across
variants that permit reordering, recomputation, value-equivalence merging, or
different arithmetic programs.

## Capacity and failure

The initial modeled subarray supplies the local-row pool defined by the
current placement profile. Physical lowering must fail explicitly when no
legal allocation exists within the available local rows. It must not silently
spill, insert RowCopy operations, change the primitive sequence, or select a
different `MatRange`.

## Validation contract

A future physical validator must establish that:

- every symbolic identity has its expected physical binding, including each
  output name's designated binding through its coalesced final source;
- no overlapping live identities illegally share a physical row;
- primitive-specific physical distinctness holds;
- inputs and declared constants remain unchanged;
- terminal output-export RowCopies are absent from the physical trace;
- every output value resides in its designated physical output row;
- physical primitive replay matches symbolic primitive replay and the
  existing arithmetic reference over the same validation domain;
- reported allocation counts match the physical binding; and
- allocation failure is explicit when capacity is insufficient.

## Explicitly deferred

Defer allocator algorithm selection, value-equivalence coalescing, general
RowCopy coalescing, primitive scheduling or reordering, live-range splitting,
spilling or rematerialization, `MatRange`-aware concurrent functional replay,
LC-MOV, GB-MOV, GEMV layout and macro generation, and host read/write
amplification. Each requires a later implementation or modeling gate.

Rationale

The generated programs are fixed destructive traces whose logical work-row
counts are not physical-row requirements. Identity-preserving lifetime reuse
reduces physical storage without changing the arithmetic program. Closed
command-point lifetimes and primitive-role distinctness preserve the modeled
multi-row operations even when a source dies or a destination begins at the
same primitive.

Protecting precolored inputs and constants retains the generator's current
functional contract and leaves cross-invocation management to a higher layer.
Precoloring each final source to its designated output row removes only a
terminal copy whose independent output identity is not otherwise needed. It
also permits safe earlier use of that row, while keeping output placement
explicit and preserving the result through operation completion.

Separating designated rows, additional scratch, total physical footprint, and
peak live identities prevents an unconstrained liveness bound from being
reported as the optimum of a constrained precolored allocation. Explicit
failure keeps capacity shortages visible instead of silently changing the
program or placement.

Evidence

- [Physical-row allocation for fixed PuD primitive traces](../references/pud-physical-row-allocation.md)
  is the research and reference basis for current generator behavior,
  primitive read/write effects, closed lifetime endpoints, physical
  distinctness, constrained precoloring, terminal-output-copy elimination,
  accounting limits, and validation requirements. It remains non-normative;
  this decision is the normative project policy.
- [Unified DDR4 PuD substrate](ddr4-pud-unified-substrate.md) defines the
  canonical range-aware public execution path and requires every compute
  invocation to carry one explicit resolved `MatRange` in its placement
  context.
- [Addressing, geometry, and payload](mimdram-addressing-geometry-and-payload.md)
  defines the canonical Bank/subarray/local-row placement authority, the
  current profile's 1,024 local rows per subarray, common compute `MatRange`,
  and the pointwise destructive effects of the five compute request types.
- [Activation command representation](pud-activation-command-representation.md),
  [NOT command granularity](pud-not-command-granularity.md), and
  [timing/resource rules](pud-timing-resource-and-command-bus-rules.md) define
  the request-level primitive boundary and physical-command costs that a
  removed terminal RowCopy no longer contributes.
- The current generator [README](../../../tools/pud_operation_generator/README.md),
  [builder and interpreter](../../../tools/pud_operation_generator/core.py),
  [artifact writer](../../../tools/pud_operation_generator/artifacts.py), and
  [validator](../../../tools/pud_operation_generator/validation.py) establish
  the fixed symbolic order, destructive semantics, protected inputs and
  constants, terminal output exports, diagnostic observations, and absence of
  an existing physical allocator.

Open issues

- The allocator algorithm remains unselected. It must satisfy and permit
  independent validation of this contract before allocator implementation.
- The other explicitly deferred transformations and higher-level placement,
  movement, macro, concurrent-replay, and host-accounting concerns require
  separate later gates; none is part of initial physical lowering.
- No additional physical-lowering modeling decision is required before an
  implementation plan can be written. The plan must keep algorithm selection
  as a pre-implementation engineering gate and must not broaden this accepted
  contract.
